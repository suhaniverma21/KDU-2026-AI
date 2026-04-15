from __future__ import annotations

from io import BytesIO

import fitz

from pipeline.ingestion import ingest_pdf, ingest_url


class MockResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None


def build_pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


def test_ingest_pdf_returns_expected_shape() -> None:
    pdf_file = BytesIO(build_pdf_bytes("Hybrid search improves retrieval quality."))
    pdf_file.name = "sample.pdf"

    result = ingest_pdf(pdf_file)

    assert result["source_type"] == "pdf"
    assert result["source_id"].startswith("pdf_")
    assert result["title"] == "sample"
    assert "Hybrid search" in result["text"]
    assert result["metadata"]["filename"] == "sample.pdf"


def test_ingest_url_returns_expected_shape(monkeypatch) -> None:
    html = """
    <html>
      <head><title>Sample Article</title></head>
      <body>
        <article>
          <h1>Hybrid Search</h1>
          <p>Semantic retrieval captures meaning.</p>
          <p>BM25 catches exact identifiers.</p>
        </article>
      </body>
    </html>
    """

    monkeypatch.setattr("pipeline.ingestion.requests.get", lambda *args, **kwargs: MockResponse(html))

    result = ingest_url("example.com/post")

    assert result["source_type"] == "url"
    assert result["source_id"].startswith("url_")
    assert result["title"] == "Sample Article"
    assert "Semantic retrieval captures meaning." in result["text"]
    assert result["metadata"]["domain"] == "example.com"
