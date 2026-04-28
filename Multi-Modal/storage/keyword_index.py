"""Persistent local keyword index for BM25 retrieval."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from config import KEYWORD_INDEX_PATH


@dataclass
class KeywordChunk:
    """Stored keyword-search document with pre-tokenized text."""

    id: str
    document: str
    tokens: list[str]
    metadata: dict[str, Any]


class KeywordIndex:
    """Small JSON-backed persistent store for BM25 documents."""

    def __init__(self, index_path: Path | None = None) -> None:
        self.index_path = Path(index_path or KEYWORD_INDEX_PATH)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index({})

    def upsert_chunks(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert or update chunk documents in the persistent keyword store."""
        if not (len(ids) == len(documents) == len(metadatas)):
            raise ValueError("Keyword index inputs must have the same length.")

        index = self._read_index()
        for chunk_id, document, metadata in zip(ids, documents, metadatas):
            chunk = KeywordChunk(
                id=chunk_id,
                document=document,
                tokens=self._tokenize(document),
                metadata=dict(metadata),
            )
            index[chunk_id] = asdict(chunk)
        self._write_index(index)

    def get_chunks(self, *, where: dict[str, Any] | None = None) -> list[KeywordChunk]:
        """Return stored keyword chunks, optionally filtered by metadata."""
        index = self._read_index()
        chunks = [KeywordChunk(**payload) for payload in index.values()]
        if where is None:
            return chunks
        return [chunk for chunk in chunks if self._matches_where(chunk.metadata, where)]

    def is_empty(self) -> bool:
        """Return True when the keyword index has no stored chunks."""
        return len(self._read_index()) == 0

    def _read_index(self) -> dict[str, dict[str, Any]]:
        with self.index_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_index(self, index: dict[str, dict[str, Any]]) -> None:
        with self.index_path.open("w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=2, sort_keys=True)

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in text.lower().split() if token]

    def _matches_where(self, metadata: dict[str, Any], where: dict[str, Any]) -> bool:
        for key, value in where.items():
            if metadata.get(key) != value:
                return False
        return True


def get_keyword_index(index_path: Path | None = None) -> KeywordIndex:
    """Return a persistent keyword index instance."""
    return KeywordIndex(index_path=index_path)
