"""Chunking utilities for document text."""

from __future__ import annotations

from utils.helpers import stable_text_hash, trim_to_max_length


DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100
SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "]


class ChunkingError(Exception):
    """Raised when a document cannot be chunked safely."""


def chunk_document(
    document: dict,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """Split an ingestion result into stable ordered chunk objects."""
    _validate_chunking_inputs(document, chunk_size, chunk_overlap)

    source_id = document["source_id"]
    source_text = document["text"].strip()
    raw_segments = _recursive_split(source_text, chunk_size, SEPARATORS)
    merged_segments = _merge_small_segments(raw_segments, chunk_size)

    chunks: list[dict] = []
    previous_chunk_text = ""

    for chunk_index, segment in enumerate(merged_segments):
        segment = segment.strip()
        if not segment:
            continue

        overlap_prefix = ""
        if previous_chunk_text and chunk_overlap > 0:
            overlap_prefix = trim_to_max_length(previous_chunk_text, chunk_overlap).strip()

        chunk_text = _combine_overlap_with_segment(overlap_prefix, segment)
        chunk_text = chunk_text[:chunk_size].strip()
        if not chunk_text:
            continue

        chunk_id = stable_text_hash(f"{source_id}::{chunk_index}::{chunk_text}", prefix="chunk_")
        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_id": source_id,
                "chunk_index": chunk_index,
                "raw_text": chunk_text,
                "metadata": {
                    "source_type": document.get("source_type"),
                    "title": document.get("title"),
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                },
            }
        )
        previous_chunk_text = chunk_text

    if not chunks:
        raise ChunkingError("No valid chunks were produced from the document text.")

    return chunks


def _validate_chunking_inputs(document: dict, chunk_size: int, chunk_overlap: int) -> None:
    """Validate chunking inputs early so failures are explicit."""
    if not isinstance(document, dict):
        raise ChunkingError("Document must be a dictionary from the ingestion step.")
    if not document.get("source_id"):
        raise ChunkingError("Document is missing source_id.")
    if not document.get("text") or not str(document["text"]).strip():
        raise ChunkingError("Document text is empty.")
    if chunk_size <= 0:
        raise ChunkingError("chunk_size must be greater than zero.")
    if chunk_overlap < 0:
        raise ChunkingError("chunk_overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise ChunkingError("chunk_overlap must be smaller than chunk_size.")


def _recursive_split(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    """Recursively split text using increasingly weaker separators."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    if not separators:
        return _hard_split(text, chunk_size)

    separator = separators[0]
    pieces = text.split(separator)
    if len(pieces) == 1:
        return _recursive_split(text, chunk_size, separators[1:])

    rebuilt_segments: list[str] = []
    current = ""

    for index, piece in enumerate(pieces):
        piece = piece.strip()
        if not piece:
            continue

        candidate = piece if not current else f"{current}{separator}{piece}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            rebuilt_segments.extend(_recursive_split(current, chunk_size, separators[1:]))
            current = piece
        else:
            rebuilt_segments.extend(_recursive_split(piece, chunk_size, separators[1:]))
            current = ""

        if index == len(pieces) - 1 and current:
            rebuilt_segments.extend(_recursive_split(current, chunk_size, separators[1:]))
            current = ""

    if current:
        rebuilt_segments.extend(_recursive_split(current, chunk_size, separators[1:]))

    return [segment.strip() for segment in rebuilt_segments if segment and segment.strip()]


def _hard_split(text: str, chunk_size: int) -> list[str]:
    """Split text by character count as a final fallback."""
    return [text[index : index + chunk_size].strip() for index in range(0, len(text), chunk_size) if text[index : index + chunk_size].strip()]


def _merge_small_segments(segments: list[str], chunk_size: int) -> list[str]:
    """Merge very small neighbor segments to avoid tiny standalone chunks."""
    merged: list[str] = []
    buffer = ""

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        if not buffer:
            buffer = segment
            continue

        candidate = f"{buffer}\n\n{segment}"
        if len(buffer) < chunk_size // 2 and len(candidate) <= chunk_size:
            buffer = candidate
        else:
            merged.append(buffer.strip())
            buffer = segment

    if buffer:
        merged.append(buffer.strip())

    return merged


def _combine_overlap_with_segment(overlap_prefix: str, segment: str) -> str:
    """Combine overlap text with the current segment without creating empty output."""
    if overlap_prefix:
        return f"{overlap_prefix}\n\n{segment}".strip()
    return segment.strip()
