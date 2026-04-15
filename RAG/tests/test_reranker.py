from __future__ import annotations

from pipeline.reranker import rerank_results


class FakeRerankerModel:
    def predict(self, pairs):
        score_map = {
            "chunk one": 0.2,
            "chunk two": 0.9,
            "chunk three": 0.5,
        }
        return [score_map[text] for _query, text in pairs]


def test_reranker_orders_candidates_by_score(monkeypatch) -> None:
    monkeypatch.setattr("pipeline.reranker.get_reranker_model", lambda: FakeRerankerModel())

    candidates = [
        {"chunk_id": "c1", "enriched_text": "chunk one", "raw_text": "one", "metadata": {}, "rrf_score": 0.02},
        {"chunk_id": "c2", "enriched_text": "chunk two", "raw_text": "two", "metadata": {}, "rrf_score": 0.01},
        {"chunk_id": "c3", "enriched_text": "chunk three", "raw_text": "three", "metadata": {}, "rrf_score": 0.03},
    ]

    reranked = rerank_results("Which chunk is best?", candidates, top_k=2)

    assert [item["chunk_id"] for item in reranked] == ["c2", "c3"]
    assert reranked[0]["reranker_score"] > reranked[1]["reranker_score"]
