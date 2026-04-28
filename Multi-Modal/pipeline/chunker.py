"""Token-aware document chunking utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken

from config import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    MAX_CHUNKS_PER_DOCUMENT,
    OPENAI_EMBEDDING_MODEL,
)


@dataclass
class TextChunk:
    """Single chunk of normalized text plus retrieval metadata."""

    text: str
    file_id: str
    chunk_index: int
    source_type: str
    page_number: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkingResult:
    """Chunking output plus token statistics used downstream."""

    chunks: list[TextChunk]
    total_tokens: int
    chunk_size_tokens: int
    chunk_overlap_tokens: int


def chunk_text(
    text: str,
    *,
    file_id: str,
    source_type: str,
    page_number: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ChunkingResult:
    """Split normalized text into token-aware chunks with attached metadata."""
    normalized_text = (text or "").strip()
    if not normalized_text:
        return ChunkingResult(
            chunks=[],
            total_tokens=0,
            chunk_size_tokens=CHUNK_SIZE_TOKENS,
            chunk_overlap_tokens=CHUNK_OVERLAP_TOKENS,
        )

    total_tokens = count_tokens(normalized_text)
    chunk_size_tokens = _determine_chunk_size(total_tokens)
    splitter = _build_splitter(chunk_size_tokens)
    split_texts = splitter.split_text(normalized_text)

    base_metadata = dict(metadata or {})
    chunks = [
        TextChunk(
            text=chunk_text_value,
            file_id=file_id,
            chunk_index=index,
            source_type=source_type,
            page_number=page_number,
            metadata={
                "file_id": file_id,
                "chunk_index": index,
                "source_type": source_type,
                "page_number": page_number,
                **base_metadata,
            },
        )
        for index, chunk_text_value in enumerate(split_texts)
    ]

    return ChunkingResult(
        chunks=chunks,
        total_tokens=total_tokens,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_tokens=CHUNK_OVERLAP_TOKENS,
    )


def count_tokens(text: str, model: str = OPENAI_EMBEDDING_MODEL) -> int:
    """Estimate token count for a string using tiktoken."""
    encoding = _get_encoding(model)
    return len(encoding.encode(text or ""))


def _determine_chunk_size(total_tokens: int) -> int:
    """Increase chunk size dynamically when the document would exceed the cap."""
    if total_tokens <= CHUNK_SIZE_TOKENS * MAX_CHUNKS_PER_DOCUMENT:
        return CHUNK_SIZE_TOKENS

    required_chunk_size = ceil(total_tokens / MAX_CHUNKS_PER_DOCUMENT)
    return max(CHUNK_SIZE_TOKENS, required_chunk_size + CHUNK_OVERLAP_TOKENS)


def _build_splitter(chunk_size_tokens: int) -> RecursiveCharacterTextSplitter:
    """Create a recursive splitter that measures chunk size in tokens."""
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size_tokens,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        length_function=count_tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _get_encoding(model: str) -> tiktoken.Encoding:
    """Return a best-effort tokenizer for the configured model."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")
