"""Chunk enrichment utilities."""

from __future__ import annotations

from pathlib import Path

from utils.helpers import (
    call_google_ai_studio_generate_content,
    get_google_ai_studio_settings,
    normalize_whitespace,
    project_root,
    read_json_file,
    stable_text_hash,
    write_json_file,
)


DEFAULT_PROVIDER = "google_ai_studio"
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class EnrichmentError(Exception):
    """Raised when contextual enrichment cannot be completed."""


def enrich_chunks(chunks: list[dict], document_text: str, document_title: str = "") -> list[dict]:
    """Add contextual summaries and enriched text to chunk dictionaries."""
    if not chunks:
        return []
    if not document_text or not document_text.strip():
        raise EnrichmentError("Document text is required for contextual enrichment.")

    client = GoogleAIStudioEnricher()
    enriched_chunks: list[dict] = []

    for chunk in chunks:
        enriched_chunks.append(client.enrich_chunk(chunk=chunk, document_text=document_text, document_title=document_title))

    return enriched_chunks


class GoogleAIStudioEnricher:
    """Contextual enrichment client using the Google AI Studio Gemini API."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        settings = get_google_ai_studio_settings(
            model_env_name="ENRICHMENT_MODEL",
            default_model=DEFAULT_MODEL,
            default_provider=DEFAULT_PROVIDER,
            default_base_url=DEFAULT_BASE_URL,
        )
        self.provider = settings["provider"]
        self.model = settings["model"]
        self.base_url = settings["base_url"]
        self.api_key = settings["api_key"]
        self.cache_dir = cache_dir or project_root() / "storage" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def enrich_chunk(self, chunk: dict, document_text: str, document_title: str = "") -> dict:
        """Return a chunk with context summary and enriched text."""
        cache_key = build_enrichment_cache_key(
            chunk=chunk,
            document_text=document_text,
            document_title=document_title,
            model=self.model,
            provider=self.provider,
        )
        cache_path = self.cache_dir / f"{cache_key}.json"

        if cache_path.exists():
            cached_payload = read_json_file(cache_path)
            return _build_enriched_chunk(chunk, cached_payload["context_summary"])

        prompt = build_enrichment_prompt(
            document_text=document_text,
            chunk_text=chunk["raw_text"],
            document_title=document_title,
        )
        context_summary = self._request_summary(prompt)
        payload = {"context_summary": context_summary}
        write_json_file(cache_path, payload)
        return _build_enriched_chunk(chunk, context_summary)

    def _request_summary(self, prompt: str) -> str:
        """Call the Google AI Studio API and extract the summary text."""
        if self.provider != "google_ai_studio":
            raise EnrichmentError(f"Unsupported enrichment provider: {self.provider}")
        try:
            return call_google_ai_studio_generate_content(
                prompt=prompt,
                system_prompt="You produce strict, factual context summaries for RAG chunk enrichment.",
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=60,
                temperature=0,
            )
        except RuntimeError as exc:
            raise EnrichmentError(f"Failed to call the enrichment API: {exc}") from exc


def build_enrichment_prompt(document_text: str, chunk_text: str, document_title: str = "") -> str:
    """Build the strict prompt used for contextual enrichment."""
    title_line = f"Document title: {document_title}\n" if document_title else ""
    return (
        "Write a factual 1-2 sentence context summary for the chunk below.\n"
        "The summary must explain where this chunk fits in the overall document.\n"
        "Do not answer questions. Do not add outside knowledge. Do not invent facts.\n"
        "Use only information supported by the document.\n\n"
        f"{title_line}"
        f"Full document:\n{document_text}\n\n"
        f"Chunk:\n{chunk_text}\n\n"
        "Return only the summary."
    )


def build_enrichment_cache_key(
    chunk: dict,
    document_text: str,
    document_title: str,
    model: str,
    provider: str,
) -> str:
    """Build a stable cache key for one chunk enrichment result."""
    source_id = chunk.get("source_id", "")
    chunk_id = chunk.get("chunk_id", "")
    raw_text = chunk.get("raw_text", "")
    seed = f"{provider}::{model}::{source_id}::{chunk_id}::{document_title}::{document_text}::{raw_text}"
    return stable_text_hash(seed, prefix="enrich_")


def _build_enriched_chunk(chunk: dict, context_summary: str) -> dict:
    """Create the enriched chunk structure returned by the public API."""
    cleaned_summary = normalize_whitespace(context_summary)
    enriched_text = f"{cleaned_summary}\n\n{chunk['raw_text']}".strip()

    enriched_chunk = dict(chunk)
    enriched_chunk["context_summary"] = cleaned_summary
    enriched_chunk["enriched_text"] = enriched_text
    return enriched_chunk
