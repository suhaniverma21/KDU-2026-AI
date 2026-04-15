"""Embedding and vector storage utilities."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from utils.helpers import project_root


DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class EmbeddingsError(Exception):
    """Raised when semantic indexing or retrieval fails."""


def get_persistent_client(base_path: Path | None = None) -> chromadb.PersistentClient:
    """Return a Chroma PersistentClient rooted in storage/chroma_db."""
    storage_path = base_path or (project_root() / "storage" / "chroma_db")
    storage_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(storage_path))


def create_or_load_collection(source_id: str, base_path: Path | None = None) -> Collection:
    """Create or load a Chroma collection for one source document."""
    client = get_persistent_client(base_path=base_path)
    collection_name = collection_name_from_source_id(source_id)
    return client.get_or_create_collection(name=collection_name, metadata={"source_id": source_id})


def upsert_chunks(chunks: list[dict], source_id: str, base_path: Path | None = None) -> None:
    """Embed enriched chunks and upsert them into a persistent Chroma collection."""
    if not chunks:
        raise EmbeddingsError("No chunks were provided for semantic indexing.")

    collection = create_or_load_collection(source_id=source_id, base_path=base_path)
    model = get_embedding_model()

    documents: list[str] = []
    chunk_ids: list[str] = []
    metadatas: list[dict] = []

    for chunk in chunks:
        enriched_text = chunk.get("enriched_text", "").strip()
        if not enriched_text:
            raise EmbeddingsError("Each chunk must include non-empty enriched_text before embedding.")

        chunk_ids.append(chunk["chunk_id"])
        documents.append(enriched_text)
        metadatas.append(_serialize_chunk_metadata(chunk))

    embeddings = model.encode(documents, convert_to_numpy=True).tolist()
    collection.upsert(
        ids=chunk_ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def semantic_search(query: str, source_id: str, top_k: int = 5, base_path: Path | None = None) -> list[dict]:
    """Run semantic similarity search over a persistent Chroma collection."""
    if not query or not query.strip():
        raise EmbeddingsError("Query text is required for semantic search.")
    if top_k <= 0:
        raise EmbeddingsError("top_k must be greater than zero.")

    collection = create_or_load_collection(source_id=source_id, base_path=base_path)
    if collection.count() == 0:
        return []

    query_embedding = get_embedding_model().encode([query], convert_to_numpy=True).tolist()[0]
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    formatted_results: list[dict] = []
    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        normalized_metadata = _deserialize_chunk_metadata(metadata or {})
        formatted_results.append(
            {
                "chunk_id": chunk_id,
                "text": document,
                "enriched_text": document,
                "raw_text": normalized_metadata.get("raw_text", ""),
                "metadata": normalized_metadata,
                "score": _distance_to_similarity_score(distance),
                "retrieval_method": "semantic",
            }
        )

    return formatted_results


def collection_name_from_source_id(source_id: str) -> str:
    """Convert a source ID into a Chroma-safe collection name."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", source_id).strip("_")
    if not sanitized:
        raise EmbeddingsError("source_id cannot produce an empty Chroma collection name.")
    return f"source_{sanitized[:55]}"


@lru_cache(maxsize=1)
def get_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    """Load and cache the sentence-transformers embedding model."""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise EmbeddingsError(
            "Failed to import sentence-transformers. This is usually an environment issue "
            "with torch/pandas/datasets installation. Reinstall the dependencies in the active venv."
        ) from exc

    try:
        return SentenceTransformer(model_name)
    except Exception as exc:
        raise EmbeddingsError(
            f"Failed to load embedding model '{model_name}'. Check the local Python environment and model dependencies."
        ) from exc


def _serialize_chunk_metadata(chunk: dict) -> dict:
    """Flatten chunk data into Chroma-storable metadata."""
    metadata = dict(chunk.get("metadata", {}))
    metadata.update(
        {
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk["source_id"],
            "chunk_index": chunk["chunk_index"],
            "raw_text": chunk.get("raw_text", ""),
            "context_summary": chunk.get("context_summary", ""),
            "title": metadata.get("title", ""),
            "source_type": metadata.get("source_type", ""),
        }
    )
    return {key: _coerce_metadata_value(value) for key, value in metadata.items()}


def _deserialize_chunk_metadata(metadata: dict) -> dict:
    """Normalize Chroma metadata into a predictable result shape."""
    normalized = dict(metadata)
    if "chunk_index" in normalized:
        try:
            normalized["chunk_index"] = int(normalized["chunk_index"])
        except (TypeError, ValueError):
            pass
    return normalized


def _coerce_metadata_value(value: object) -> str | int | float | bool:
    """Convert metadata values into Chroma-supported primitive types."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    if value is None:
        return ""
    return str(value)


def _distance_to_similarity_score(distance: float | int | None) -> float:
    """Convert Chroma distance to a more intuitive similarity-like score."""
    numeric_distance = float(distance or 0.0)
    return 1.0 / (1.0 + numeric_distance)
