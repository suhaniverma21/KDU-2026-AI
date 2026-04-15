"""Document ingestion utilities for PDFs and URLs."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO
from urllib.parse import urlparse

import fitz
import requests
from bs4 import BeautifulSoup
from requests import Response
from requests.exceptions import RequestException

from utils.helpers import normalize_url, normalize_whitespace, stable_text_hash


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT_SECONDS = 20


class IngestionError(Exception):
    """Raised when a source cannot be ingested into usable text."""


def ingest_pdf(file_obj: BinaryIO) -> dict:
    """Extract normalized text and metadata from a PDF file-like object."""
    pdf_bytes = _read_binary_input(file_obj)

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise IngestionError("Failed to read the PDF file.") from exc

    try:
        page_texts = [page.get_text("text") for page in document]
        raw_text = "\n\n".join(text.strip() for text in page_texts if text and text.strip())
        text = normalize_whitespace(raw_text)
        if not text:
            raise IngestionError("The PDF did not contain extractable text.")

        metadata = document.metadata or {}
        filename = getattr(file_obj, "name", "uploaded.pdf")
        title = metadata.get("title") or _filename_stem(filename)
        source_id = stable_text_hash(f"pdf::{filename}::{text}", prefix="pdf_")

        return {
            "source_type": "pdf",
            "source_id": source_id,
            "title": title,
            "text": text,
            "metadata": {
                "filename": filename,
                "page_count": document.page_count,
                "pdf_metadata": metadata,
            },
        }
    finally:
        document.close()


def ingest_url(url: str) -> dict:
    """Extract normalized text and metadata from a blog or article URL."""
    normalized_url = normalize_url(url)
    _validate_url(normalized_url)
    response = _fetch_url(normalized_url)
    soup = BeautifulSoup(response.text, "html.parser")
    _remove_non_content_elements(soup)

    title = _extract_title(soup, normalized_url)
    text = _extract_article_text(soup)
    if not text:
        raise IngestionError("The URL did not yield usable article text.")

    source_id = stable_text_hash(f"url::{normalized_url}::{text}", prefix="url_")

    return {
        "source_type": "url",
        "source_id": source_id,
        "title": title,
        "text": text,
        "metadata": {
            "url": normalized_url,
            "domain": urlparse(normalized_url).netloc,
            "status_code": response.status_code,
        },
    }


def _read_binary_input(file_obj: BinaryIO) -> bytes:
    """Read bytes from an uploaded file-like object."""
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        payload = file_obj.read()
    except Exception as exc:
        raise IngestionError("Failed to read the uploaded PDF bytes.") from exc

    if not payload:
        raise IngestionError("The uploaded PDF file is empty.")

    if isinstance(payload, str):
        payload = payload.encode("utf-8")

    return payload


def _fetch_url(url: str) -> Response:
    """Fetch HTML content from a URL with conservative defaults."""
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except RequestException as exc:
        raise IngestionError(f"Failed to fetch URL: {url}") from exc
    return response


def _validate_url(url: str) -> None:
    """Validate the basic URL structure before making a request."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise IngestionError("Invalid URL. Provide a full blog/article URL.")


def _remove_non_content_elements(soup: BeautifulSoup) -> None:
    """Remove common non-content elements before extracting text."""
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "iframe",
            "header",
            "footer",
            "nav",
            "aside",
            "form",
        ]
    ):
        tag.decompose()


def _extract_title(soup: BeautifulSoup, fallback_url: str) -> str:
    """Extract a human-readable document title."""
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    return urlparse(fallback_url).netloc


def _extract_article_text(soup: BeautifulSoup) -> str:
    """Extract article-like text while preserving rough paragraph structure."""
    candidates = [
        soup.find("article"),
        soup.find("main"),
        soup.find(attrs={"role": "main"}),
        soup.body,
    ]

    container = next((candidate for candidate in candidates if candidate is not None), None)
    if container is None:
        return ""

    paragraph_texts: list[str] = []
    for element in container.find_all(["h1", "h2", "h3", "p", "li"]):
        text = element.get_text(" ", strip=True)
        if text:
            paragraph_texts.append(text)

    if not paragraph_texts:
        fallback_text = container.get_text("\n", strip=True)
        return normalize_whitespace(fallback_text)

    return normalize_whitespace("\n\n".join(paragraph_texts))


def _filename_stem(filename: str) -> str:
    """Return a readable filename stem."""
    return filename.rsplit(".", maxsplit=1)[0] if "." in filename else filename


def ingest_pdf_bytes(pdf_bytes: bytes, filename: str = "uploaded.pdf") -> dict:
    """Convenience wrapper for tests or non-Streamlit callers."""
    file_obj = BytesIO(pdf_bytes)
    file_obj.name = filename
    return ingest_pdf(file_obj)
