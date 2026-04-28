"""Lightweight tests for core non-network logic."""

from __future__ import annotations

import tempfile
import unittest

from pipeline.quality_gate import normalize_text
from pipeline.search import (
    _distance_to_similarity,
    _normalize_where_filter,
    _to_chroma_where,
    search_chunks,
)
from pipeline.summarizer import _parse_summary_response
from storage.cost_log import CostLogger
from storage.filestore import FileStore
from storage.keyword_index import KeywordIndex
from storage.vectorstore import VectorStore


class FileStoreTests(unittest.TestCase):
    def test_create_and_lookup_by_md5(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileStore(store_path=f"{temp_dir}/files.json")
            created = store.create_file_record(
                md5="abc123",
                original_name="sample.pdf",
                source_type="pdf",
                mime_type="application/pdf",
            )

            fetched = store.get_by_md5("abc123")
            self.assertIsNotNone(fetched)
            self.assertEqual(created.file_id, fetched.file_id)


class CostLoggerTests(unittest.TestCase):
    def test_compute_cost_for_embedding_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = CostLogger(log_path=f"{temp_dir}/cost.jsonl")
            cost = logger.compute_cost(
                model="text-embedding-3-small",
                prompt_tokens=1000,
                completion_tokens=0,
            )
            self.assertGreater(cost, 0.0)


class KeywordIndexTests(unittest.TestCase):
    def test_upsert_and_filter_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            index = KeywordIndex(index_path=f"{temp_dir}/index.json")
            index.upsert_chunks(
                ids=["file-1:0", "file-2:0"],
                documents=["hello world", "another chunk"],
                metadatas=[
                    {"file_id": "file-1", "source_type": "pdf"},
                    {"file_id": "file-2", "source_type": "image"},
                ],
            )

            filtered = index.get_chunks(where={"file_id": "file-1"})
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].id, "file-1:0")
            self.assertEqual(filtered[0].tokens, ["hello", "world"])


class QualityGateTests(unittest.TestCase):
    def test_normalize_text_collapses_whitespace(self) -> None:
        result = normalize_text("Hello   world\r\n\r\n\r\nThis is\ta test.   ")
        self.assertEqual(result.normalized_text, "Hello world\n\nThis is a test.")


class SummaryParserTests(unittest.TestCase):
    def test_parse_labeled_summary_response(self) -> None:
        parsed = _parse_summary_response(
            "SUMMARY:\nA short summary.\nKEY POINTS:\n- one\n- two\nTAGS:\n- alpha\n- beta"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["summary"], "A short summary.")
        self.assertEqual(parsed["key_points"], ["one", "two"])
        self.assertEqual(parsed["tags"], ["alpha", "beta"])


class SearchMathTests(unittest.TestCase):
    def test_distance_to_similarity_bounds_result(self) -> None:
        self.assertEqual(_distance_to_similarity(None), 0.0)
        self.assertEqual(_distance_to_similarity(0.25), 0.75)
        self.assertEqual(_distance_to_similarity(2.0), 0.0)

    def test_normalize_where_filter_accepts_supported_keys(self) -> None:
        where = _normalize_where_filter({"file_id": "abc", "source_type": "pdf"})
        self.assertEqual(where, {"file_id": "abc", "source_type": "pdf"})

    def test_normalize_where_filter_rejects_unsupported_keys(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_where_filter({"page_number": 2})

    def test_to_chroma_where_wraps_multiple_filters_in_and(self) -> None:
        where = _to_chroma_where({"file_id": "abc", "source_type": "pdf"})
        self.assertEqual(
            where,
            {
                "$and": [
                    {"file_id": "abc"},
                    {"source_type": "pdf"},
                ]
            },
        )


class VectorStoreVerificationTests(unittest.TestCase):
    def test_verify_distance_metric_accepts_cosine(self) -> None:
        store = VectorStore.__new__(VectorStore)
        store.collection = type("CollectionStub", (), {"metadata": {"hnsw:space": "cosine"}})()
        store.verify_distance_metric()

    def test_verify_distance_metric_rejects_non_cosine(self) -> None:
        store = VectorStore.__new__(VectorStore)
        store.collection = type("CollectionStub", (), {"metadata": {"hnsw:space": "l2"}})()
        with self.assertRaises(RuntimeError):
            store.verify_distance_metric()


class SearchFlowTests(unittest.TestCase):
    def test_search_empty_store_returns_user_message(self) -> None:
        class EmptyStore:
            def is_empty(self) -> bool:
                return True

        response = search_chunks("hello", vector_store=EmptyStore())  # type: ignore[arg-type]
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Upload a file first before using search")

    def test_search_applies_filters_before_retrieval(self) -> None:
        class FilterAwareStore:
            def __init__(self) -> None:
                self.query_where = None

            def is_empty(self) -> bool:
                return False

            def query(self, *, query_embedding, n_results=10, where=None):
                self.query_where = where
                return []

        class FilterAwareKeywordIndex:
            def __init__(self) -> None:
                self.get_chunks_where = None

            def get_chunks(self, *, where=None):
                self.get_chunks_where = where
                return []

        store = FilterAwareStore()
        keyword_index = FilterAwareKeywordIndex()
        where = {"file_id": "file-123", "source_type": "pdf"}
        response = search_chunks(
            "hello",
            vector_store=store,  # type: ignore[arg-type]
            keyword_index=keyword_index,  # type: ignore[arg-type]
            where=where,
        )
        self.assertTrue(response.success)
        self.assertEqual(response.message, "No relevant content found")
        self.assertEqual(keyword_index.get_chunks_where, where)
        self.assertIsNone(store.query_where)

    def test_search_passes_filters_to_semantic_query_after_prefilter(self) -> None:
        class FilterAwareStore:
            def __init__(self) -> None:
                self.query_where = None

            def is_empty(self) -> bool:
                return False

            def query(self, *, query_embedding, n_results=10, where=None):
                self.query_where = where
                return []

        class FilterAwareKeywordIndex:
            def __init__(self) -> None:
                self.get_chunks_where = None

            def get_chunks(self, *, where=None):
                self.get_chunks_where = where
                return [
                    type(
                        "KeywordChunkStub",
                        (),
                        {
                            "id": "file-123:0",
                            "document": "gpt-4o-mini is mentioned here",
                            "tokens": ["gpt-4o-mini", "is", "mentioned", "here"],
                            "metadata": {"file_id": "file-123", "source_type": "pdf"},
                        },
                    )()
                ]

        class DummyLogger:
            def log_api_call(self, **kwargs):
                return None

        store = FilterAwareStore()
        keyword_index = FilterAwareKeywordIndex()
        where = {"file_id": "file-123", "source_type": "pdf"}

        original_embed_query = search_chunks.__globals__["embed_query"]
        try:
            search_chunks.__globals__["embed_query"] = lambda *args, **kwargs: ([0.1, 0.2], 2)
            response = search_chunks(
                "gpt-4o-mini",
                vector_store=store,  # type: ignore[arg-type]
                keyword_index=keyword_index,  # type: ignore[arg-type]
                cost_logger=DummyLogger(),  # type: ignore[arg-type]
                where=where,
            )
        finally:
            search_chunks.__globals__["embed_query"] = original_embed_query

        self.assertTrue(response.success)
        self.assertEqual(keyword_index.get_chunks_where, where)
        self.assertEqual(
            store.query_where,
            {
                "$and": [
                    {"file_id": "file-123"},
                    {"source_type": "pdf"},
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()
