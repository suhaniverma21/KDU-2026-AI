"""Hybrid retrieval utilities."""

from __future__ import annotations

from pathlib import Path

from pipeline.bm25_index import bm25_search
from pipeline.embeddings import semantic_search


DEFAULT_RETRIEVER_TOP_K = 20
RRF_K = 60


class HybridSearchError(Exception):
    """Raised when hybrid retrieval inputs are invalid."""


def hybrid_search(query: str, source_id: str, top_k: int = 5, base_path: Path | None = None) -> list[dict]:
    """Run semantic and BM25 retrieval, then fuse results with RRF."""
    if not query or not query.strip():
        raise HybridSearchError("Query text is required for hybrid retrieval.")
    if top_k <= 0:
        raise HybridSearchError("top_k must be greater than zero.")

    semantic_results = semantic_search(
        query=query,
        source_id=source_id,
        top_k=DEFAULT_RETRIEVER_TOP_K,
        base_path=base_path,
    )
    bm25_results = bm25_search(
        query=query,
        source_id=source_id,
        top_k=DEFAULT_RETRIEVER_TOP_K,
        base_path=base_path,
    )
    fused_results = reciprocal_rank_fusion(semantic_results=semantic_results, bm25_results=bm25_results)
    return fused_results[:top_k]


def reciprocal_rank_fusion(semantic_results: list[dict], bm25_results: list[dict]) -> list[dict]:
    """Fuse semantic and BM25 ranked lists using Reciprocal Rank Fusion."""
    fused_by_chunk_id: dict[str, dict] = {}

    for rank, result in enumerate(semantic_results, start=1):
        normalized = normalize_retrieval_result(result, retrieval_method="semantic")
        fused_entry = fused_by_chunk_id.setdefault(
            normalized["chunk_id"],
            _create_fused_entry(normalized),
        )
        fused_entry["rrf_score"] += _rrf_increment(rank)
        fused_entry["contributing_retrievers"].append("semantic")
        fused_entry["semantic_rank"] = rank

    for rank, result in enumerate(bm25_results, start=1):
        normalized = normalize_retrieval_result(result, retrieval_method="bm25")
        fused_entry = fused_by_chunk_id.setdefault(
            normalized["chunk_id"],
            _create_fused_entry(normalized),
        )
        fused_entry["rrf_score"] += _rrf_increment(rank)
        fused_entry["contributing_retrievers"].append("bm25")
        fused_entry["bm25_rank"] = rank
        if not fused_entry["enriched_text"]:
            fused_entry["enriched_text"] = normalized["enriched_text"]
        if not fused_entry["raw_text"]:
            fused_entry["raw_text"] = normalized["raw_text"]
        if not fused_entry["metadata"]:
            fused_entry["metadata"] = normalized["metadata"]

    ranked_results = sorted(
        fused_by_chunk_id.values(),
        key=lambda item: (
            -item["rrf_score"],
            item["semantic_rank"] if item["semantic_rank"] is not None else float("inf"),
            item["bm25_rank"] if item["bm25_rank"] is not None else float("inf"),
            item["chunk_id"],
        ),
    )

    for item in ranked_results:
        item["contributing_retrievers"] = sorted(set(item["contributing_retrievers"]))

    return ranked_results


def normalize_retrieval_result(result: dict, retrieval_method: str) -> dict:
    """Normalize retriever outputs into a consistent fusion-ready shape."""
    metadata = dict(result.get("metadata", {}))
    enriched_text = result.get("enriched_text") or result.get("text") or ""
    raw_text = result.get("raw_text") or metadata.get("raw_text", "")

    return {
        "chunk_id": result["chunk_id"],
        "enriched_text": enriched_text,
        "raw_text": raw_text,
        "metadata": metadata,
        "retrieval_method": retrieval_method,
    }


def _create_fused_entry(result: dict) -> dict:
    """Create the initial fused record for a chunk."""
    return {
        "chunk_id": result["chunk_id"],
        "enriched_text": result["enriched_text"],
        "raw_text": result["raw_text"],
        "metadata": result["metadata"],
        "rrf_score": 0.0,
        "contributing_retrievers": [],
        "semantic_rank": None,
        "bm25_rank": None,
    }


def _rrf_increment(rank: int) -> float:
    """Compute the Reciprocal Rank Fusion contribution for one rank."""
    return 1.0 / (RRF_K + rank)
