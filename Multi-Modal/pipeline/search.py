"""Hybrid search built on semantic retrieval, BM25, and RRF fusion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from rank_bm25 import BM25Okapi

from config import (
    OPENAI_EMBEDDING_MODEL,
    RRF_K,
    SEARCH_RETRIEVAL_COUNT,
    SEARCH_RETURN_COUNT,
    SEARCH_SIMILARITY_THRESHOLD,
)
from pipeline.embedder import embed_query
from storage.cost_log import CostLogger, get_cost_logger
from storage.keyword_index import KeywordChunk, KeywordIndex, get_keyword_index
from storage.vectorstore import SearchResult, VectorStore, get_vector_store

MIN_QUERY_LENGTH = 3
ALLOWED_FILTER_KEYS = {"file_id", "source_type"}


@dataclass
class SearchMatch:
    """User-facing search match with score and chunk metadata."""

    chunk_text: str
    metadata: dict[str, Any]
    similarity_score: float
    vector_id: str


@dataclass
class SearchResponse:
    """Structured search response for direct UI consumption."""

    success: bool
    message: str
    results: list[SearchMatch]
    query: str


def search_chunks(
    query: str,
    *,
    vector_store: VectorStore | None = None,
    keyword_index: KeywordIndex | None = None,
    cost_logger: CostLogger | None = None,
    client: OpenAI | None = None,
    similarity_threshold: float = SEARCH_SIMILARITY_THRESHOLD,
    retrieval_count: int = SEARCH_RETRIEVAL_COUNT,
    return_count: int = SEARCH_RETURN_COUNT,
    where: dict[str, Any] | None = None,
) -> SearchResponse:
    """Run hybrid search with validation, query embedding, BM25, and RRF fusion."""
    normalized_query = (query or "").strip()
    if len(normalized_query) < MIN_QUERY_LENGTH:
        return SearchResponse(
            success=False,
            message="Query must be at least 3 characters long",
            results=[],
            query=normalized_query,
        )

    normalized_where = _normalize_where_filter(where)
    chroma_where = _to_chroma_where(normalized_where)
    store = vector_store or get_vector_store()
    keywords = keyword_index or get_keyword_index()
    if store.is_empty():
        return SearchResponse(
            success=False,
            message="Upload a file first before using search",
            results=[],
            query=normalized_query,
        )

    filtered_chunks = keywords.get_chunks(where=normalized_where)
    if not filtered_chunks:
        return SearchResponse(
            success=True,
            message="No relevant content found",
            results=[],
            query=normalized_query,
        )

    logger = cost_logger or get_cost_logger()
    openai_client = client or OpenAI()

    try:
        query_embedding, prompt_tokens = embed_query(
            normalized_query,
            client=openai_client,
            model=OPENAI_EMBEDDING_MODEL,
        )
    except Exception as exc:
        logger.log_api_call(
            file_id="search",
            operation_type="search_query_embedding",
            model=OPENAI_EMBEDDING_MODEL,
            prompt_tokens=0,
            completion_tokens=0,
            success=False,
            error_message=str(exc),
        )
        raise

    logger.log_api_call(
        file_id="search",
        operation_type="search_query_embedding",
        model=OPENAI_EMBEDDING_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=0,
        success=True,
        error_message="",
    )

    semantic_results = store.query(
        query_embedding=query_embedding,
        n_results=retrieval_count,
        where=chroma_where,
    )
    keyword_results = _run_bm25_search(
        query=normalized_query,
        chunks=filtered_chunks,
        retrieval_count=retrieval_count,
    )
    matches = _merge_and_filter_results(
        semantic_results=semantic_results,
        keyword_results=keyword_results,
        similarity_threshold=similarity_threshold,
        return_count=return_count,
    )

    if not matches:
        return SearchResponse(
            success=True,
            message="No relevant content found",
            results=[],
            query=normalized_query,
        )

    return SearchResponse(
        success=True,
        message="Hybrid search completed successfully",
        results=matches,
        query=normalized_query,
    )


def _run_bm25_search(
    *,
    query: str,
    chunks: list[KeywordChunk],
    retrieval_count: int,
) -> list[KeywordChunk]:
    """Run BM25 keyword retrieval over the filtered chunk subset."""
    tokenized_corpus = [chunk.tokens for chunk in chunks]
    if not tokenized_corpus or not any(tokenized_corpus):
        return []

    query_tokens = _tokenize_for_bm25(query)
    if not query_tokens:
        return []

    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(query_tokens)
    ranked_pairs = sorted(
        zip(chunks, scores),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [chunk for chunk, score in ranked_pairs[:retrieval_count] if score > 0]


def _merge_and_filter_results(
    *,
    semantic_results: list[SearchResult],
    keyword_results: list[KeywordChunk],
    similarity_threshold: float,
    return_count: int,
) -> list[SearchMatch]:
    """Merge semantic and BM25 results using normalized Reciprocal Rank Fusion."""
    semantic_rank = {result.id: index + 1 for index, result in enumerate(semantic_results)}
    keyword_rank = {result.id: index + 1 for index, result in enumerate(keyword_results)}

    combined: dict[str, dict[str, Any]] = {}
    for result in semantic_results:
        combined[result.id] = {
            "document": result.document,
            "metadata": result.metadata,
            "semantic_similarity": _distance_to_similarity(result.distance),
        }

    for result in keyword_results:
        combined.setdefault(
            result.id,
            {
                "document": result.document,
                "metadata": result.metadata,
                "semantic_similarity": 0.0,
            },
        )

    max_rrf_score = (1 / (RRF_K + 1)) + (1 / (RRF_K + 1))
    matches: list[SearchMatch] = []
    for result_id, payload in combined.items():
        raw_rrf = 0.0
        if result_id in semantic_rank:
            raw_rrf += 1 / (RRF_K + semantic_rank[result_id])
        if result_id in keyword_rank:
            raw_rrf += 1 / (RRF_K + keyword_rank[result_id])

        normalized_rrf = raw_rrf / max_rrf_score if max_rrf_score else 0.0
        final_score = max(normalized_rrf, float(payload["semantic_similarity"]))
        if final_score < similarity_threshold:
            continue

        matches.append(
            SearchMatch(
                chunk_text=str(payload["document"]),
                metadata=dict(payload["metadata"]),
                similarity_score=round(final_score, 4),
                vector_id=result_id,
            )
        )

    matches.sort(key=lambda match: match.similarity_score, reverse=True)
    return matches[:return_count]


def _tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize text for simple BM25 retrieval."""
    return [token for token in text.lower().split() if token]


def _normalize_where_filter(where: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate and normalize supported metadata filters before retrieval."""
    if where is None:
        return None
    if not isinstance(where, dict):
        raise ValueError("Search filters must be provided as a dictionary.")

    normalized: dict[str, Any] = {}
    for key, value in where.items():
        if key not in ALLOWED_FILTER_KEYS:
            raise ValueError("Only file_id and source_type search filters are supported.")
        if value is None:
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("Search filter values must be simple scalar values.")
        normalized[key] = value

    return normalized or None


def _to_chroma_where(where: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a normalized metadata filter into Chroma's expected syntax."""
    if where is None:
        return None

    clauses = [{key: value} for key, value in where.items()]
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _distance_to_similarity(distance: float | None) -> float:
    """Convert cosine distance to similarity.

    Chroma returns cosine distance when the collection uses cosine space.
    With that setup, similarity is approximated as `1 - distance`.
    """
    if distance is None:
        return 0.0
    similarity = 1.0 - distance
    return max(0.0, min(1.0, similarity))
