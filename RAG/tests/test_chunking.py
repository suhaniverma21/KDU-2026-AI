from __future__ import annotations

from pipeline.chunking import chunk_document


def test_chunk_document_produces_non_empty_ordered_chunks() -> None:
    document = {
        "source_type": "url",
        "source_id": "source_123",
        "title": "Test Document",
        "text": (
            "Paragraph one explains embeddings.\n\n"
            "Paragraph two explains BM25 keyword retrieval.\n\n"
            "Paragraph three explains reranking and grounded generation."
        ),
        "metadata": {},
    }

    chunks = chunk_document(document, chunk_size=60, chunk_overlap=10)

    assert chunks
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk["raw_text"].strip() for chunk in chunks)
    assert all(chunk["source_id"] == "source_123" for chunk in chunks)
