"""Persistent Chroma vector store wrapper."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings

from config import CHROMA_COLLECTION_NAME, CHROMA_PATH

LOGGER = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Single vector-search match returned from Chroma."""

    id: str
    document: str
    metadata: dict[str, Any]
    distance: float | None


@dataclass
class StoredChunk:
    """Stored chunk record used for local keyword retrieval."""

    id: str
    document: str
    metadata: dict[str, Any]


class VectorStore:
    """Wrapper around a persistent Chroma collection using cosine distance."""

    def __init__(
        self,
        *,
        persist_directory: Path | None = None,
        collection_name: str = CHROMA_COLLECTION_NAME,
    ) -> None:
        self.persist_directory = Path(persist_directory or CHROMA_PATH)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self._get_or_create_collection()
        self.verify_readable()

    def verify_readable(self) -> int:
        """Verify the collection is readable and log its total chunk count."""
        try:
            self.verify_distance_metric()
            total_chunks = self.count()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("Vector store is unreadable.") from exc

        LOGGER.info("Chroma collection '%s' is readable with %s chunks.", self.collection_name, total_chunks)
        return total_chunks

    def insert_chunks(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert or update chunk embeddings in the collection."""
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=[self._serialize_metadata(metadata) for metadata in metadatas],
        )

    def query(
        self,
        *,
        query_embedding: list[float],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Run a vector similarity query and return structured matches."""
        response = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = response.get("ids", [[]])[0]
        documents = response.get("documents", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        distances = response.get("distances", [[]])[0]

        results: list[SearchResult] = []
        for item_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            results.append(
                SearchResult(
                    id=item_id,
                    document=document,
                    metadata=self._deserialize_metadata(metadata or {}),
                    distance=distance,
                )
            )
        return results

    def count(self) -> int:
        """Return total vector count in the collection."""
        return self.collection.count()

    def verify_distance_metric(self) -> None:
        """Verify that the collection is configured for cosine distance."""
        space = (self.collection.metadata or {}).get("hnsw:space")
        if space != "cosine":
            raise RuntimeError(
                "Vector store is configured with the wrong distance metric. Expected cosine."
            )

    def get_chunks(
        self,
        *,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[StoredChunk]:
        """Return stored chunks for local keyword retrieval."""
        get_kwargs: dict[str, Any] = {
            "where": where,
            "include": ["documents", "metadatas"],
        }
        if limit is not None:
            get_kwargs["limit"] = limit

        response = self.collection.get(**get_kwargs)
        ids = response.get("ids", [])
        documents = response.get("documents", [])
        metadatas = response.get("metadatas", [])

        chunks: list[StoredChunk] = []
        for item_id, document, metadata in zip(ids, documents, metadatas):
            chunks.append(
                StoredChunk(
                    id=item_id,
                    document=document,
                    metadata=self._deserialize_metadata(metadata or {}),
                )
            )
        return chunks

    def is_empty(self) -> bool:
        """Return True when the collection contains no vectors."""
        return self.count() == 0

    def _get_or_create_collection(self) -> Collection:
        """Create the Chroma collection with cosine distance if absent."""
        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        if (collection.metadata or {}).get("hnsw:space") != "cosine":
            raise RuntimeError(
                "Chroma collection exists without cosine distance. Recreate it with cosine before use."
            )
        return collection

    def _serialize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Convert metadata into Chroma-compatible scalar values."""
        serialized: dict[str, Any] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                serialized[key] = value
            else:
                serialized[key] = json.dumps(value, ensure_ascii=True)
        return serialized

    def _deserialize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Best-effort restore JSON-encoded metadata fields."""
        restored: dict[str, Any] = {}
        for key, value in metadata.items():
            if not isinstance(value, str):
                restored[key] = value
                continue
            try:
                restored[key] = json.loads(value)
            except json.JSONDecodeError:
                restored[key] = value
        return restored


def get_vector_store(
    *,
    persist_directory: Path | None = None,
    collection_name: str = CHROMA_COLLECTION_NAME,
) -> VectorStore:
    """Return a vector store instance backed by persistent Chroma storage."""
    return VectorStore(
        persist_directory=persist_directory,
        collection_name=collection_name,
    )
