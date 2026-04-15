from __future__ import annotations

from pipeline.hybrid_search import reciprocal_rank_fusion


def test_rrf_deduplicates_and_boosts_shared_chunks() -> None:
    semantic_results = [
        {"chunk_id": "chunk_shared", "enriched_text": "shared", "raw_text": "shared", "metadata": {}, "score": 0.9},
        {"chunk_id": "chunk_semantic", "enriched_text": "semantic", "raw_text": "semantic", "metadata": {}, "score": 0.8},
    ]
    bm25_results = [
        {"chunk_id": "chunk_shared", "enriched_text": "shared", "raw_text": "shared", "metadata": {}, "score": 12.0},
        {"chunk_id": "chunk_bm25", "enriched_text": "bm25", "raw_text": "bm25", "metadata": {}, "score": 11.0},
    ]

    fused = reciprocal_rank_fusion(semantic_results=semantic_results, bm25_results=bm25_results)

    assert len(fused) == 3
    assert fused[0]["chunk_id"] == "chunk_shared"
    assert fused[0]["contributing_retrievers"] == ["bm25", "semantic"]
    assert fused[0]["semantic_rank"] == 1
    assert fused[0]["bm25_rank"] == 1
