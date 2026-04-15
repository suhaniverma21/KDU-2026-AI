from __future__ import annotations

from pathlib import Path

from pipeline.enrichment import GoogleAIStudioEnricher


def test_enrichment_uses_disk_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    monkeypatch.setenv("ENRICHMENT_MODEL", "fake-model")

    calls = {"count": 0}

    def fake_request_summary(self, prompt: str) -> str:
        calls["count"] += 1
        return "This chunk explains lexical retrieval in the document."

    monkeypatch.setattr(GoogleAIStudioEnricher, "_request_summary", fake_request_summary)

    enricher = GoogleAIStudioEnricher(cache_dir=tmp_path)
    chunk = {
        "chunk_id": "chunk_1",
        "source_id": "source_1",
        "chunk_index": 0,
        "raw_text": "BM25 retrieves exact keyword matches.",
        "metadata": {},
    }

    first = enricher.enrich_chunk(chunk=chunk, document_text="BM25 retrieves exact keyword matches.")
    second = enricher.enrich_chunk(chunk=chunk, document_text="BM25 retrieves exact keyword matches.")

    assert calls["count"] == 1
    assert first["context_summary"] == second["context_summary"]
    assert "BM25 retrieves exact keyword matches." in first["enriched_text"]
