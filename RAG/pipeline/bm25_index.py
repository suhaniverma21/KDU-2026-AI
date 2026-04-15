"""BM25 keyword indexing utilities."""

from __future__ import annotations

from pathlib import Path

from rank_bm25 import BM25Okapi

from utils.helpers import project_root, read_json_file, stable_text_hash, write_json_file


class BM25IndexError(Exception):
    """Raised when BM25 artifacts cannot be built or queried."""


def build_bm25_index(chunks: list[dict], source_id: str, base_path: Path | None = None) -> dict:
    """Build and persist BM25 artifacts for one source document."""
    if not chunks:
        raise BM25IndexError("No chunks were provided for BM25 indexing.")

    records: list[dict] = []
    tokenized_corpus: list[list[str]] = []

    for chunk in chunks:
        enriched_text = chunk.get("enriched_text", "").strip()
        raw_text = chunk.get("raw_text", "").strip()
        if not enriched_text:
            raise BM25IndexError("Each chunk must include non-empty enriched_text before BM25 indexing.")

        tokens = tokenize_text(enriched_text)
        tokenized_corpus.append(tokens)
        records.append(
            {
                "chunk_id": chunk["chunk_id"],
                "source_id": source_id,
                "enriched_text": enriched_text,
                "raw_text": raw_text,
                "metadata": dict(chunk.get("metadata", {})),
                "tokens": tokens,
            }
        )

    artifact = {
        "source_id": source_id,
        "record_count": len(records),
        "records": records,
    }
    save_index_artifacts(artifact=artifact, source_id=source_id, base_path=base_path)
    return artifact


def save_index_artifacts(artifact: dict, source_id: str, base_path: Path | None = None) -> Path:
    """Persist BM25 artifact JSON to disk."""
    storage_dir = _get_bm25_storage_dir(base_path)
    artifact_path = storage_dir / f"{bm25_artifact_name(source_id)}.json"
    write_json_file(artifact_path, artifact)
    return artifact_path


def load_index_artifacts(source_id: str, base_path: Path | None = None) -> dict:
    """Load persisted BM25 artifacts and reconstruct the BM25 object."""
    artifact_path = _get_bm25_storage_dir(base_path) / f"{bm25_artifact_name(source_id)}.json"
    if not artifact_path.exists():
        raise BM25IndexError(f"No BM25 index artifacts found for source_id={source_id}.")

    artifact = read_json_file(artifact_path)
    records = artifact.get("records", [])
    if not records:
        raise BM25IndexError(f"BM25 artifact for source_id={source_id} contains no records.")

    tokenized_corpus = [record.get("tokens", []) for record in records]
    artifact["bm25"] = BM25Okapi(tokenized_corpus)
    return artifact


def bm25_search(query: str, source_id: str, top_k: int = 5, base_path: Path | None = None) -> list[dict]:
    """Search the persisted BM25 index for top matching chunks."""
    if not query or not query.strip():
        raise BM25IndexError("Query text is required for BM25 search.")
    if top_k <= 0:
        raise BM25IndexError("top_k must be greater than zero.")

    artifact = load_index_artifacts(source_id=source_id, base_path=base_path)
    bm25 = artifact["bm25"]
    records = artifact["records"]
    query_tokens = tokenize_text(query)
    scores = bm25.get_scores(query_tokens)

    ranked_pairs = sorted(
        enumerate(scores),
        key=lambda item: item[1],
        reverse=True,
    )[:top_k]

    results: list[dict] = []
    for record_index, score in ranked_pairs:
        record = records[record_index]
        results.append(
            {
                "chunk_id": record["chunk_id"],
                "enriched_text": record["enriched_text"],
                "raw_text": record["raw_text"],
                "metadata": record["metadata"],
                "score": float(score),
                "retrieval_method": "bm25",
            }
        )

    return results


def tokenize_text(text: str) -> list[str]:
    """Tokenize text using lowercase and whitespace splitting."""
    if not text or not text.strip():
        return []
    return text.lower().split()


def bm25_artifact_name(source_id: str) -> str:
    """Build a stable BM25 artifact filename stem from source_id."""
    return stable_text_hash(source_id, prefix="bm25_")


def _get_bm25_storage_dir(base_path: Path | None = None) -> Path:
    """Return the BM25 artifact storage directory."""
    storage_dir = base_path or (project_root() / "storage" / "bm25")
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir
