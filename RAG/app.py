"""Streamlit entry point for the hybrid-search RAG chatbot."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pipeline.bm25_index import BM25IndexError, build_bm25_index
from pipeline.chunking import ChunkingError, chunk_document
from pipeline.embeddings import EmbeddingsError, upsert_chunks
from pipeline.enrichment import EnrichmentError, enrich_chunks
from pipeline.generator import GeneratorError, generate_answer
from pipeline.hybrid_search import HybridSearchError, hybrid_search
from pipeline.ingestion import IngestionError, ingest_pdf, ingest_url
from pipeline.reranker import RerankerError, rerank_results
from utils.helpers import ensure_directories, load_env_file


def bootstrap() -> None:
    """Prepare local directories and environment values."""
    load_env_file()
    ensure_directories(
        [
            Path("storage"),
            Path("storage/chroma_db"),
            Path("storage/bm25"),
            Path("storage/cache"),
            Path("pipeline"),
            Path("evaluation"),
            Path("utils"),
        ]
    )
    initialize_session_state()


def initialize_session_state() -> None:
    """Initialize Streamlit session state keys used by the app."""
    defaults = {
        "indexed_document": None,
        "indexed_chunks": [],
        "last_response": None,
        "chat_history": [],
        "is_indexed": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render_sidebar() -> None:
    """Render project status information."""
    st.sidebar.title("Hybrid-Search RAG")
    st.sidebar.caption("Local single-document teaching assistant")

    if st.session_state["is_indexed"] and st.session_state["indexed_document"]:
        document = st.session_state["indexed_document"]
        st.sidebar.success("Document indexed")
        st.sidebar.write(f"Title: {document['title']}")
        st.sidebar.write(f"Source ID: {document['source_id']}")
        st.sidebar.write(f"Type: {document['source_type']}")
    else:
        st.sidebar.info("No document indexed yet")


def render_source_controls() -> None:
    """Render source upload controls and indexing trigger."""
    st.subheader("Source")
    uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])
    url_input = st.text_input("Or enter a blog URL")

    if st.button("Index Source", type="primary"):
        if uploaded_file and url_input.strip():
            st.warning("Choose either a PDF or a URL, not both.")
            return
        if not uploaded_file and not url_input.strip():
            st.warning("Provide either a PDF file or a blog URL.")
            return

        try:
            index_source(uploaded_file=uploaded_file, url_input=url_input.strip())
            st.success("Indexing complete. You can now ask questions.")
        except (
            IngestionError,
            ChunkingError,
            EnrichmentError,
            EmbeddingsError,
            BM25IndexError,
            ValueError,
        ) as exc:
            st.session_state["is_indexed"] = False
            st.error(str(exc))


def index_source(uploaded_file, url_input: str) -> None:
    """Run the full indexing pipeline for one source."""
    progress = st.progress(0, text="Starting indexing...")
    status = st.empty()

    status.info("Ingesting source...")
    if uploaded_file is not None:
        document = ingest_pdf(uploaded_file)
    else:
        document = ingest_url(url_input)
    progress.progress(20, text="Source ingested")

    status.info("Chunking document...")
    chunks = chunk_document(document)
    progress.progress(40, text="Document chunked")

    status.info("Enriching chunks with document context...")
    enriched_chunks = enrich_chunks(
        chunks=chunks,
        document_text=document["text"],
        document_title=document["title"],
    )
    progress.progress(65, text="Chunks enriched")

    status.info("Building semantic index...")
    upsert_chunks(enriched_chunks, source_id=document["source_id"])
    progress.progress(82, text="Semantic index ready")

    status.info("Building BM25 index...")
    build_bm25_index(enriched_chunks, source_id=document["source_id"])
    progress.progress(100, text="BM25 index ready")

    st.session_state["indexed_document"] = document
    st.session_state["indexed_chunks"] = enriched_chunks
    st.session_state["last_response"] = None
    st.session_state["chat_history"] = []
    st.session_state["is_indexed"] = True
    status.success(f"Indexed: {document['title']}")


def render_document_summary() -> None:
    """Render a compact summary of the indexed document."""
    if not st.session_state["is_indexed"] or not st.session_state["indexed_document"]:
        return

    document = st.session_state["indexed_document"]
    with st.expander("Indexed Document", expanded=False):
        st.write(f"Title: {document['title']}")
        st.write(f"Source type: {document['source_type']}")
        st.write(f"Source ID: {document['source_id']}")
        st.write(f"Chunks indexed: {len(st.session_state['indexed_chunks'])}")
        st.write(document["text"][:800] + ("..." if len(document["text"]) > 800 else ""))


def render_chat() -> None:
    """Render chat history and answer generation flow."""
    st.subheader("Chat")
    if not st.session_state["is_indexed"]:
        st.info("Index a PDF or URL before asking questions.")
        return

    for message in st.session_state["chat_history"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    question = st.chat_input("Ask a question about the indexed document")
    if not question:
        return

    st.session_state["chat_history"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    try:
        with st.chat_message("assistant"):
            with st.spinner("Retrieving context and generating grounded answer..."):
                response = answer_query(question)
            st.write(response["final_answer"])
    except (HybridSearchError, RerankerError, GeneratorError, EmbeddingsError, BM25IndexError, ValueError) as exc:
        with st.chat_message("assistant"):
            st.error(str(exc))
        return

    st.session_state["last_response"] = response
    st.session_state["chat_history"].append({"role": "assistant", "content": response["final_answer"]})


def answer_query(question: str) -> dict:
    """Run retrieval, reranking, and grounded generation for one question."""
    source_id = st.session_state["indexed_document"]["source_id"]
    fused_results = hybrid_search(query=question, source_id=source_id, top_k=20)
    reranked_results = rerank_results(query=question, candidates=fused_results, top_k=5)
    return generate_answer(query=question, context_chunks=reranked_results)


def render_supporting_chunks() -> None:
    """Render supporting chunks from the most recent answer."""
    st.subheader("Evidence")
    last_response = st.session_state.get("last_response")
    if not last_response:
        st.write("Supporting chunks will appear here after you ask a question.")
        return

    with st.expander("Source Chunks", expanded=False):
        for index, chunk in enumerate(last_response["supporting_chunks"], start=1):
            st.markdown(f"**Chunk {index}**")
            st.write(f"Chunk ID: {chunk['chunk_id']}")
            if chunk.get("reranker_score") is not None:
                st.write(f"Reranker score: {chunk['reranker_score']:.4f}")
            if chunk.get("rrf_score") is not None:
                st.write(f"RRF score: {chunk['rrf_score']:.4f}")
            st.write(chunk["enriched_text"])
            st.divider()

    with st.expander("Debug Metadata", expanded=False):
        st.json(last_response["debug"])


def render_main() -> None:
    """Render the full application UI."""
    st.title("Hybrid-Search RAG Chatbot")
    st.write("Index one PDF or blog URL, then ask grounded questions against that source.")
    render_source_controls()
    render_document_summary()
    render_chat()
    render_supporting_chunks()


def main() -> None:
    """Run the Streamlit app."""
    bootstrap()
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
