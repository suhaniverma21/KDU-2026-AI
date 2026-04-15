"""Cross-encoder reranking utilities."""

from __future__ import annotations

from functools import lru_cache

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class RerankerError(Exception):
    """Raised when reranking inputs or model calls fail."""


def rerank_results(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Score fused candidates with a CrossEncoder and return the best matches."""
    if not query or not query.strip():
        raise RerankerError("Query text is required for reranking.")
    if top_k <= 0:
        raise RerankerError("top_k must be greater than zero.")
    if not candidates:
        return []

    normalized_candidates = [_normalize_candidate(candidate) for candidate in candidates]
    model_inputs = [(query, candidate["enriched_text"]) for candidate in normalized_candidates]
    scores = get_reranker_model().predict(model_inputs)

    reranked_candidates: list[dict] = []
    for candidate, score in zip(normalized_candidates, scores):
        reranked_candidate = dict(candidate)
        reranked_candidate["reranker_score"] = float(score)
        reranked_candidates.append(reranked_candidate)

    reranked_candidates.sort(
        key=lambda item: (
            -item["reranker_score"],
            -item.get("rrf_score", 0.0),
            item.get("semantic_rank") if item.get("semantic_rank") is not None else float("inf"),
            item.get("bm25_rank") if item.get("bm25_rank") is not None else float("inf"),
            item["chunk_id"],
        )
    )
    return reranked_candidates[:top_k]


@lru_cache(maxsize=1)
def get_reranker_model(model_name: str = DEFAULT_RERANKER_MODEL):
    """Load and cache the cross-encoder reranker model."""
    try:
        from sentence_transformers import CrossEncoder
    except Exception as exc:
        raise RerankerError(
            "Failed to import sentence-transformers for reranking. This is usually an environment issue "
            "with torch/pandas/datasets installation. Reinstall the dependencies in the active venv."
        ) from exc

    try:
        return CrossEncoder(model_name)
    except Exception as exc:
        raise RerankerError(
            f"Failed to load reranker model '{model_name}'. Check the local Python environment and model dependencies."
        ) from exc


def _normalize_candidate(candidate: dict) -> dict:
    """Normalize fused candidates into a generator-ready schema."""
    enriched_text = candidate.get("enriched_text") or candidate.get("text") or ""
    if not enriched_text.strip():
        raise RerankerError("Each candidate must include non-empty enriched_text for reranking.")

    normalized = dict(candidate)
    normalized["enriched_text"] = enriched_text
    normalized["raw_text"] = candidate.get("raw_text") or candidate.get("metadata", {}).get("raw_text", "")
    normalized["metadata"] = dict(candidate.get("metadata", {}))
    return normalized
