"""Streamlit entry point for the Content Accessibility Suite."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from dotenv import load_dotenv
import streamlit as st

from ingest.audio import ingest_audio
from ingest.image import ingest_image
from ingest.pdf import ingest_pdf
from ingest.validator import validate_upload
from pipeline.chunker import ChunkingResult, chunk_text
from pipeline.embedder import EmbeddingBatchResult, embed_chunks
from pipeline.quality_gate import normalize_text
from pipeline.search import SearchResponse, search_chunks
from pipeline.summarizer import SummaryResult, summarize_document
from storage.cost_log import CostLogger, get_cost_logger
from storage.filestore import FileRecord, FileStore, get_file_store
from storage.vectorstore import get_vector_store
from utils import read_file_bytes, to_plain_english_error


def main() -> None:
    """Render the Streamlit application and orchestrate processing flows."""
    load_dotenv()
    st.set_page_config(page_title="Content Accessibility Suite", layout="wide")

    file_store = get_file_store()
    cost_logger = get_cost_logger()

    st.title("Content Accessibility Suite")
    st.caption("Upload PDF, image, or audio files to extract transcripts, summaries, and search-ready chunks.")

    _initialize_session_state(file_store)
    _render_sidebar(file_store, cost_logger)

    uploaded_file = st.file_uploader(
        "Upload a file",
        type=["pdf", "png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp", "gif", "mp3", "wav", "m4a", "ogg", "flac", "aac", "mp4", "webm"],
        help="Supported types: PDF, common image formats, and common audio formats.",
    )

    if uploaded_file is not None:
        _handle_upload(uploaded_file, file_store, cost_logger)

    active_record = _resolve_active_record(file_store)
    if active_record is not None:
        _render_record_details(active_record)

    st.divider()
    _render_search_panel(file_store, cost_logger)


def _initialize_session_state(file_store: FileStore) -> None:
    """Initialize current-record session state."""
    if "current_file_id" not in st.session_state:
        records = file_store.get_all_file_records()
        st.session_state.current_file_id = records[-1].file_id if records else None
    if "search_response" not in st.session_state:
        st.session_state.search_response = None
    if "search_scope" not in st.session_state:
        st.session_state.search_scope = {"file_id": None, "source_type": "All types"}


def _render_sidebar(file_store: FileStore, cost_logger: CostLogger) -> None:
    """Render file navigation and cost overview."""
    with st.sidebar:
        st.header("Workspace")
        records = file_store.get_all_file_records()
        if records:
            record_options = {f"{record.original_name} [{record.status}]": record.file_id for record in records}
            labels = list(record_options.keys())
            current_id = st.session_state.get("current_file_id")
            default_index = 0
            for index, label in enumerate(labels):
                if record_options[label] == current_id:
                    default_index = index
                    break
            selected_label = st.selectbox("Saved Files", labels, index=default_index)
            st.session_state.current_file_id = record_options[selected_label]
        else:
            st.info("No files have been processed yet.")

        st.subheader("Cost Overview")
        session_total = cost_logger.get_session_total()
        per_file_totals = cost_logger.get_totals_by_file()
        total_cost = round(sum(per_file_totals.values()), 8)
        st.metric("Session Total (USD)", f"${session_total:.6f}")
        st.metric("Total Cost (USD)", f"${total_cost:.6f}")
        if per_file_totals:
            st.caption("Per-file cost")
            for file_id, total in per_file_totals.items():
                st.write(f"`{file_id}`: ${total:.6f}")


def _handle_upload(uploaded_file, file_store: FileStore, cost_logger: CostLogger) -> None:
    """Validate, deduplicate, and process an uploaded file."""
    file_bytes = read_file_bytes(uploaded_file)
    validation = validate_upload(
        file_bytes,
        filename=uploaded_file.name,
        mime_type=uploaded_file.type,
        file_store=file_store,
    )

    if not validation.is_valid:
        st.session_state.search_response = None
        st.error(validation.error_message)
        return

    if validation.cached_record is not None:
        st.session_state.current_file_id = validation.cached_record.file_id
        st.session_state.search_response = None
        st.success("Duplicate file detected. Returning cached result.")
        return

    record = file_store.create_file_record(
        md5=validation.md5 or "",
        original_name=uploaded_file.name,
        source_type=validation.source_type or "unknown",
        mime_type=validation.mime_type or "",
        status="PENDING",
    )
    st.session_state.current_file_id = record.file_id
    st.session_state.search_response = None

    status_placeholder = st.empty()
    try:
        _update_status(file_store, record.file_id, "PROCESSING", status_placeholder)
        processed_record = _process_file(
            record=record,
            file_bytes=file_bytes,
            filename=uploaded_file.name,
            file_store=file_store,
            cost_logger=cost_logger,
        )
        st.session_state.current_file_id = processed_record.file_id
        _update_status(file_store, processed_record.file_id, processed_record.status, status_placeholder)
        st.success("Processing completed.")
    except Exception as exc:
        user_message = to_plain_english_error(exc, "The file could not be processed.")
        failed = file_store.update_status(record.file_id, "FAILED", error_message=user_message)
        st.session_state.current_file_id = failed.file_id
        status_placeholder.error("FAILED")
        st.error(user_message)


def _process_file(
    *,
    record: FileRecord,
    file_bytes: bytes,
    filename: str,
    file_store: FileStore,
    cost_logger: CostLogger,
) -> FileRecord:
    """Run ingestion, chunking, embedding, and optional summarization."""
    ingestion_result = _run_ingestion(record=record, file_bytes=file_bytes, filename=filename)
    transcript_text = _extract_transcript_text(ingestion_result)
    quality_result = normalize_text(transcript_text)

    notes = _extract_processing_notes(ingestion_result)
    partial_notes = _extract_partial_notes(ingestion_result)
    should_skip_chunking = _should_skip_chunking(ingestion_result)
    should_skip_summary = quality_result.should_skip_summary or _should_skip_summary(ingestion_result)

    updated_record = file_store.update_file_record(
        record.file_id,
        transcript=quality_result.normalized_text,
        partial_notes=partial_notes + notes,
        error_message="",
    )

    chunking_result = ChunkingResult(
        chunks=[],
        total_tokens=0,
        chunk_size_tokens=0,
        chunk_overlap_tokens=0,
    )
    embedding_result = EmbeddingBatchResult(
        file_id=record.file_id,
        embedded_chunk_count=0,
        total_prompt_tokens=0,
        vector_ids=[],
    )
    if quality_result.normalized_text and not should_skip_chunking:
        chunking_result = chunk_text(
            quality_result.normalized_text,
            file_id=record.file_id,
            source_type=record.source_type,
            metadata={"original_name": record.original_name},
        )
        if chunking_result.chunks:
            embedding_result = embed_chunks(
                chunking_result.chunks,
                file_id=record.file_id,
                cost_logger=cost_logger,
            )

    summary_result = summarize_document(
        file_id=record.file_id,
        transcript_text=quality_result.normalized_text,
        chunks=chunking_result.chunks,
        cost_logger=cost_logger,
        file_store=file_store,
    ) if quality_result.normalized_text and not should_skip_summary else SummaryResult(
        summary=quality_result.normalized_text,
        key_points=[],
        tags=[],
        raw_response=quality_result.normalized_text,
        was_skipped=True,
        is_pending=False,
        processing_notes=["Summarization was skipped for this file."],
    )

    final_partial_notes = list(updated_record.partial_notes) + list(summary_result.processing_notes)
    final_status = _determine_final_status(
        transcript_text=quality_result.normalized_text,
        partial_notes=final_partial_notes,
        ingestion_result=ingestion_result,
    )

    final_record = file_store.update_file_record(
        record.file_id,
        transcript=quality_result.normalized_text,
        summary=summary_result.summary,
        key_points=summary_result.key_points,
        tags=summary_result.tags,
        partial_notes=final_partial_notes,
        error_message="" if not summary_result.is_pending else "Summary generation is pending due to a previous failure.",
        status=final_status,
    )

    st.info(
        f"Transcript characters: {quality_result.character_count} | "
        f"Chunks: {len(chunking_result.chunks)} | Embedded: {embedding_result.embedded_chunk_count}"
    )
    return final_record


def _run_ingestion(*, record: FileRecord, file_bytes: bytes, filename: str) -> Any:
    """Dispatch to the correct ingestion module."""
    if record.source_type == "pdf":
        return ingest_pdf(file_bytes, file_id=record.file_id)
    if record.source_type == "image":
        return ingest_image(file_bytes, file_id=record.file_id)
    if record.source_type == "audio":
        return ingest_audio(file_bytes, filename=filename)
    raise ValueError("Unsupported file type")


def _extract_transcript_text(result: Any) -> str:
    """Return transcript text from any ingestion result."""
    return getattr(result, "transcript_text", "")


def _extract_processing_notes(result: Any) -> list[str]:
    """Return processing notes from any ingestion result."""
    return list(getattr(result, "processing_notes", []))


def _extract_partial_notes(result: Any) -> list[str]:
    """Return partial notes from ingestion results that support them."""
    return list(getattr(result, "partial_notes", []))


def _should_skip_chunking(result: Any) -> bool:
    """Return whether downstream chunking should be skipped."""
    return bool(getattr(result, "should_skip_chunking", False))


def _should_skip_summary(result: Any) -> bool:
    """Return whether downstream summarization should be skipped."""
    return bool(getattr(result, "should_skip_summary", False))


def _determine_final_status(*, transcript_text: str, partial_notes: list[str], ingestion_result: Any) -> str:
    """Compute final record status from processing outcomes."""
    if not transcript_text:
        return "FAILED"
    if bool(getattr(ingestion_result, "is_partial", False)):
        return "PARTIAL"
    return "READY"


def _update_status(file_store: FileStore, file_id: str, status: str, placeholder) -> None:
    """Persist and display a status transition."""
    file_store.update_status(file_id, status)
    if status == "PROCESSING":
        placeholder.info(status)
    elif status == "READY":
        placeholder.success(status)
    elif status == "PARTIAL":
        placeholder.warning(status)
    elif status == "FAILED":
        placeholder.error(status)
    else:
        placeholder.write(status)


def _resolve_active_record(file_store: FileStore) -> FileRecord | None:
    """Return the current record selected in the UI."""
    current_file_id = st.session_state.get("current_file_id")
    if not current_file_id:
        return None
    return file_store.get_file_record(current_file_id)


def _render_record_details(record: FileRecord) -> None:
    """Render the details of the currently selected record."""
    st.subheader("Current File")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status", record.status)
    col2.metric("Type", record.source_type.upper())
    col3.metric("Created", record.created_at.split("T")[0])
    col4.metric("Updated", record.updated_at.split("T")[0])

    if record.error_message:
        st.warning(record.error_message)

    if record.partial_notes:
        st.subheader("Processing Notes")
        for note in record.partial_notes:
            st.write(f"- {note}")

    transcript_tab, summary_tab, metadata_tab = st.tabs(["Transcript", "Summary", "Metadata"])
    with transcript_tab:
        if record.transcript:
            st.text_area("Transcript", value=record.transcript, height=300)
        else:
            st.info("No transcript is available for this file.")

    with summary_tab:
        if record.summary:
            st.write(record.summary)
        else:
            st.info("No summary is available yet.")
            if "pending" in record.error_message.lower():
                st.caption("Search remains available while summary generation is pending.")

        if record.key_points:
            st.markdown("**Key Points**")
            for point in record.key_points:
                st.write(f"- {point}")

        if record.tags:
            st.markdown("**Tags**")
            st.write(", ".join(record.tags))

    with metadata_tab:
        st.json(asdict(record))


def _render_search_panel(file_store: FileStore, cost_logger: CostLogger) -> None:
    """Render the hybrid search interface."""
    st.subheader("Hybrid Search")
    records = file_store.get_all_file_records()
    if not records:
        st.info("Upload and process a file to enable search.")
        return

    file_filter_options = {"All files": None}
    for record in records:
        file_filter_options[f"{record.original_name} [{record.status}]"] = record.file_id
    source_type_options = ["All types"] + sorted({record.source_type for record in records})

    search_query = st.text_input("Search query")
    selected_file_filter = st.selectbox("File Scope", list(file_filter_options.keys()))
    selected_source_type = st.selectbox("Source Type", source_type_options)

    if st.button("Run Search", use_container_width=True):
        where: dict[str, Any] | None = None
        selected_file_id = file_filter_options[selected_file_filter]
        if selected_file_id is not None:
            where = {"file_id": selected_file_id}
        if selected_source_type != "All types":
            where = {**(where or {}), "source_type": selected_source_type}

        try:
            response = search_chunks(
                search_query,
                vector_store=get_vector_store(),
                cost_logger=cost_logger,
                where=where,
            )
        except Exception as exc:
            st.session_state.search_response = None
            st.error(to_plain_english_error(exc, "Search failed. Please try again."))
            return

        st.session_state.search_scope = {
            "file_id": selected_file_id,
            "source_type": selected_source_type,
        }
        st.session_state.search_response = response

    if st.session_state.search_response is not None:
        _render_search_scope_summary(file_store)
        _render_search_response(st.session_state.search_response)


def _render_search_response(response: SearchResponse) -> None:
    """Render search results or a user-facing message."""
    if not response.success and response.message:
        st.warning(response.message)
        return

    st.info(response.message)
    for index, match in enumerate(response.results, start=1):
        with st.expander(f"Result {index} | similarity {match.similarity_score:.4f}", expanded=index == 1):
            st.write(match.chunk_text)
            st.caption(f"Vector ID: {match.vector_id}")
            st.json(match.metadata)


def _render_search_scope_summary(file_store: FileStore) -> None:
    """Render a short summary of the currently displayed search scope."""
    scope = st.session_state.get("search_scope", {})
    file_id = scope.get("file_id")
    source_type = scope.get("source_type", "All types")

    file_label = "All files"
    if file_id:
        record = file_store.get_file_record(file_id)
        if record is not None:
            file_label = record.original_name

    st.caption(f"Search scope: {file_label} | Source type: {source_type}")


if __name__ == "__main__":
    main()
