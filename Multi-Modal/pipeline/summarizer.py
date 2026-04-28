"""Map-reduce summarization pipeline with resilient parsing and fallbacks."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Sequence

from openai import OpenAI

from config import OPENAI_SUMMARIZATION_MODEL
from pipeline.chunker import TextChunk, count_tokens
from storage.cost_log import CostLogger, get_cost_logger
from storage.filestore import FileStore, get_file_store
from utils import extract_chat_response_text, extract_usage_tokens

SUMMARY_SKIP_THRESHOLD = 150
REDUCE_TOKEN_LIMIT = 4000
INTERMEDIATE_GROUP_SIZE = 20


@dataclass
class SummaryResult:
    """Structured summary output for downstream persistence and UI display."""

    summary: str
    key_points: list[str]
    tags: list[str]
    raw_response: str
    was_skipped: bool
    is_pending: bool
    processing_notes: list[str] = field(default_factory=list)


def summarize_document(
    *,
    file_id: str,
    transcript_text: str,
    chunks: Sequence[TextChunk],
    cost_logger: CostLogger | None = None,
    file_store: FileStore | None = None,
    client: OpenAI | None = None,
    model: str = OPENAI_SUMMARIZATION_MODEL,
) -> SummaryResult:
    """Summarize a document with map-reduce, batching, and parser fallbacks."""
    text = (transcript_text or "").strip()
    if len(text) < SUMMARY_SKIP_THRESHOLD:
        return SummaryResult(
            summary=text,
            key_points=[],
            tags=[],
            raw_response=text,
            was_skipped=True,
            is_pending=False,
            processing_notes=["Transcript is under 150 characters, so raw text is used as the summary."],
        )

    logger = cost_logger or get_cost_logger()
    store = file_store or get_file_store()
    openai_client = client or OpenAI()
    notes: list[str] = []
    effective_chunks = list(chunks)
    if not effective_chunks:
        effective_chunks = [TextChunk(text=text, file_id=file_id, chunk_index=0, source_type="unknown")]
        notes.append("No chunks were provided, so summarization used the full transcript as a single chunk.")

    try:
        mini_summaries = [
            _summarize_chunk(
                chunk=chunk,
                file_id=file_id,
                client=openai_client,
                cost_logger=logger,
                model=model,
            )
            for chunk in effective_chunks
        ]

        reduce_inputs = mini_summaries
        combined_map_text = "\n\n".join(mini_summaries)
        if count_tokens(combined_map_text, model=model) > REDUCE_TOKEN_LIMIT:
            notes.append(
                "Combined map summaries exceeded the reduce token budget, so intermediate group reduction was used."
            )
            reduce_inputs = _build_intermediate_summaries(
                summaries=mini_summaries,
                file_id=file_id,
                client=openai_client,
                cost_logger=logger,
                model=model,
            )

        final_response = _reduce_summaries(
            summaries=reduce_inputs,
            file_id=file_id,
            client=openai_client,
            cost_logger=logger,
            model=model,
            operation_type="summary_reduce",
        )
    except Exception:
        store.mark_summary_pending(file_id)
        return SummaryResult(
            summary="",
            key_points=[],
            tags=[],
            raw_response="",
            was_skipped=False,
            is_pending=True,
            processing_notes=["Summary generation is pending because an API call failed."],
        )

    parsed = _parse_summary_response(final_response)
    if parsed is None:
        notes.append("Summary response could not be parsed, so the raw response was stored as fallback.")
        return SummaryResult(
            summary=final_response.strip(),
            key_points=[],
            tags=[],
            raw_response=final_response,
            was_skipped=False,
            is_pending=False,
            processing_notes=notes,
        )

    return SummaryResult(
        summary=parsed["summary"],
        key_points=parsed["key_points"],
        tags=parsed["tags"],
        raw_response=final_response,
        was_skipped=False,
        is_pending=False,
        processing_notes=notes,
    )


def _summarize_chunk(
    *,
    chunk: TextChunk,
    file_id: str,
    client: OpenAI,
    cost_logger: CostLogger,
    model: str,
) -> str:
    """Generate a 2-3 sentence summary for a single chunk."""
    system_prompt = "You summarize document chunks faithfully and concisely."
    user_prompt = (
        "Summarize the following document chunk in 2-3 sentences. "
        "Focus on the important content only.\n\n"
        f"{chunk.text}"
    )
    response_text = _run_chat_completion(
        file_id=file_id,
        operation_type="summary_map",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        client=client,
        cost_logger=cost_logger,
        model=model,
    )
    return response_text.strip()


def _build_intermediate_summaries(
    *,
    summaries: list[str],
    file_id: str,
    client: OpenAI,
    cost_logger: CostLogger,
    model: str,
) -> list[str]:
    """Reduce large map output into smaller grouped summaries before final reduce."""
    reduced_groups: list[str] = []
    for start_index in range(0, len(summaries), INTERMEDIATE_GROUP_SIZE):
        group = summaries[start_index : start_index + INTERMEDIATE_GROUP_SIZE]
        reduced_groups.append(
            _reduce_summaries(
                summaries=group,
                file_id=file_id,
                client=client,
                cost_logger=cost_logger,
                model=model,
                operation_type="summary_intermediate_reduce",
            )
        )
    return reduced_groups


def _reduce_summaries(
    *,
    summaries: Sequence[str],
    file_id: str,
    client: OpenAI,
    cost_logger: CostLogger,
    model: str,
    operation_type: str,
) -> str:
    """Combine summaries into labeled final output."""
    combined = "\n\n".join(summary.strip() for summary in summaries if summary.strip())
    system_prompt = (
        "You combine document summaries into a final structured result. "
        "Respond with these exact labels on separate lines: SUMMARY, KEY POINTS, TAGS."
    )
    user_prompt = (
        "Combine the following summaries into:\n"
        "- a 150-word summary\n"
        "- 5-7 key points\n"
        "- 3-5 tags\n\n"
        "Use exactly this format:\n"
        "SUMMARY:\n"
        "<summary>\n"
        "KEY POINTS:\n"
        "- point 1\n"
        "- point 2\n"
        "TAGS:\n"
        "- tag1\n"
        "- tag2\n\n"
        f"Summaries:\n{combined}"
    )
    return _run_chat_completion(
        file_id=file_id,
        operation_type=operation_type,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        client=client,
        cost_logger=cost_logger,
        model=model,
    ).strip()


def _run_chat_completion(
    *,
    file_id: str,
    operation_type: str,
    system_prompt: str,
    user_prompt: str,
    client: OpenAI,
    cost_logger: CostLogger,
    model: str,
) -> str:
    """Execute a summarization call and log token usage and failures."""
    prompt_tokens_fallback = count_tokens(system_prompt, model=model) + count_tokens(
        user_prompt,
        model=model,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        cost_logger.log_api_call(
            file_id=file_id,
            operation_type=operation_type,
            model=model,
            prompt_tokens=prompt_tokens_fallback,
            completion_tokens=0,
            success=False,
            error_message=str(exc),
        )
        raise

    prompt_tokens, completion_tokens = extract_usage_tokens(response)
    if prompt_tokens == 0:
        prompt_tokens = prompt_tokens_fallback

    cost_logger.log_api_call(
        file_id=file_id,
        operation_type=operation_type,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        success=True,
        error_message="",
    )
    return extract_chat_response_text(response)


def _parse_summary_response(response_text: str) -> dict[str, list[str] | str] | None:
    """Parse labeled summary output into structured fields."""
    text = (response_text or "").strip()
    if not text:
        return None

    pattern = re.compile(
        r"SUMMARY:\s*(?P<summary>.*?)\s*KEY POINTS:\s*(?P<key_points>.*?)\s*TAGS:\s*(?P<tags>.*)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None

    summary = match.group("summary").strip()
    key_points = _parse_list_section(match.group("key_points"))
    tags = _parse_list_section(match.group("tags"))
    return {
        "summary": summary,
        "key_points": key_points,
        "tags": tags,
    }


def _parse_list_section(section_text: str) -> list[str]:
    """Parse bullet-like lines into a clean list of strings."""
    items: list[str] = []
    for line in section_text.splitlines():
        cleaned = re.sub(r"^\s*[-*\d\.\)]*\s*", "", line).strip()
        if cleaned:
            items.append(cleaned)
    return items
