"""Embedding pipeline for chunk vectors and Chroma persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from openai import OpenAI

from config import EMBEDDING_BATCH_SIZE, OPENAI_EMBEDDING_MODEL
from pipeline.chunker import TextChunk, count_tokens
from storage.cost_log import CostLogger, get_cost_logger
from storage.keyword_index import KeywordIndex, get_keyword_index
from storage.vectorstore import VectorStore, get_vector_store


@dataclass
class EmbeddingBatchResult:
    """Summary of a completed embedding run."""

    file_id: str
    embedded_chunk_count: int
    total_prompt_tokens: int
    vector_ids: list[str]


def embed_chunks(
    chunks: Sequence[TextChunk],
    *,
    file_id: str,
    vector_store: VectorStore | None = None,
    keyword_index: KeywordIndex | None = None,
    cost_logger: CostLogger | None = None,
    client: OpenAI | None = None,
    batch_size: int = EMBEDDING_BATCH_SIZE,
    model: str = OPENAI_EMBEDDING_MODEL,
) -> EmbeddingBatchResult:
    """Embed chunks in batches and persist them into the vector store."""
    if not chunks:
        return EmbeddingBatchResult(
            file_id=file_id,
            embedded_chunk_count=0,
            total_prompt_tokens=0,
            vector_ids=[],
        )

    store = vector_store or get_vector_store()
    keyword_store = keyword_index or get_keyword_index()
    logger = cost_logger or get_cost_logger()
    openai_client = client or OpenAI()

    all_ids: list[str] = []
    total_prompt_tokens = 0

    for batch in _iter_batches(list(chunks), batch_size):
        chunk_ids = [_chunk_id(chunk) for chunk in batch]
        inputs = [chunk.text for chunk in batch]
        prompt_tokens = sum(count_tokens(text, model=model) for text in inputs)

        try:
            response = openai_client.embeddings.create(model=model, input=inputs)
        except Exception as exc:
            logger.log_api_call(
                file_id=file_id,
                operation_type="embedding",
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                success=False,
                error_message=str(exc),
            )
            raise

        usage_prompt_tokens = _extract_prompt_tokens(response) or prompt_tokens
        total_prompt_tokens += usage_prompt_tokens
        embeddings = [item.embedding for item in response.data]

        store.insert_chunks(
            ids=chunk_ids,
            documents=inputs,
            embeddings=embeddings,
            metadatas=[chunk.metadata for chunk in batch],
        )
        keyword_store.upsert_chunks(
            ids=chunk_ids,
            documents=inputs,
            metadatas=[chunk.metadata for chunk in batch],
        )

        logger.log_api_call(
            file_id=file_id,
            operation_type="embedding",
            model=model,
            prompt_tokens=usage_prompt_tokens,
            completion_tokens=0,
            success=True,
            error_message="",
        )

        all_ids.extend(chunk_ids)

    return EmbeddingBatchResult(
        file_id=file_id,
        embedded_chunk_count=len(chunks),
        total_prompt_tokens=total_prompt_tokens,
        vector_ids=all_ids,
    )


def embed_query(
    query: str,
    *,
    client: OpenAI | None = None,
    model: str = OPENAI_EMBEDDING_MODEL,
) -> tuple[list[float], int]:
    """Embed a single query string for semantic search."""
    openai_client = client or OpenAI()
    response = openai_client.embeddings.create(model=model, input=query)
    embedding = response.data[0].embedding
    prompt_tokens = _extract_prompt_tokens(response) or count_tokens(query, model=model)
    return embedding, prompt_tokens


def _iter_batches(chunks: list[TextChunk], batch_size: int) -> list[list[TextChunk]]:
    """Yield chunk batches of at most the configured batch size."""
    return [chunks[index : index + batch_size] for index in range(0, len(chunks), batch_size)]


def _chunk_id(chunk: TextChunk) -> str:
    """Build a stable vector ID from chunk metadata."""
    return f"{chunk.file_id}:{chunk.chunk_index}"


def _extract_prompt_tokens(response: object) -> int | None:
    """Read prompt token usage from an embeddings response when available."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    if isinstance(prompt_tokens, int):
        return prompt_tokens
    return None
