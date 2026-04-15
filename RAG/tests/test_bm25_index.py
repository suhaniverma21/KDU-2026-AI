from __future__ import annotations

from pathlib import Path

from pipeline.bm25_index import build_bm25_index, bm25_search, load_index_artifacts


def test_bm25_persistence_and_load(tmp_path: Path) -> None:
    chunks = [
        {
            "chunk_id": "chunk_a",
            "source_id": "source_a",
            "raw_text": "Error code ABC123 means the index is stale.",
            "enriched_text": "This chunk documents error code ABC123.\n\nError code ABC123 means the index is stale.",
            "metadata": {"title": "Doc A"},
        },
        {
            "chunk_id": "chunk_b",
            "source_id": "source_a",
            "raw_text": "Semantic search uses embeddings.",
            "enriched_text": "This chunk explains semantic retrieval.\n\nSemantic search uses embeddings.",
            "metadata": {"title": "Doc A"},
        },
    ]

    build_bm25_index(chunks=chunks, source_id="source_a", base_path=tmp_path)
    artifact = load_index_artifacts(source_id="source_a", base_path=tmp_path)
    results = bm25_search("ABC123", source_id="source_a", top_k=1, base_path=tmp_path)

    assert artifact["source_id"] == "source_a"
    assert artifact["record_count"] == 2
    assert results[0]["chunk_id"] == "chunk_a"
    assert results[0]["retrieval_method"] == "bm25"
