"""Shared helper utilities used across the project."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException


def load_env_file() -> None:
    """Load environment variables from a local .env file when present."""
    load_dotenv(override=False)


def ensure_directories(paths: list[Path]) -> None:
    """Create directories if they do not already exist."""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def project_root() -> Path:
    """Return the repository root path."""
    return Path(__file__).resolve().parent.parent


def get_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    """Fetch an environment variable with optional required enforcement."""
    value = os.getenv(name, default)
    if required and (value is None or not str(value).strip()):
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def normalize_whitespace(text: str) -> str:
    """Normalize text while preserving paragraph boundaries."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    paragraphs: list[str] = []
    current_paragraph: list[str] = []

    for line in lines:
        if not line:
            if current_paragraph:
                paragraphs.append(" ".join(current_paragraph).strip())
                current_paragraph = []
            continue
        current_paragraph.append(line)

    if current_paragraph:
        paragraphs.append(" ".join(current_paragraph).strip())

    normalized = "\n\n".join(paragraph for paragraph in paragraphs if paragraph)
    return normalized.strip()


def stable_text_hash(text: str, prefix: str = "") -> str:
    """Create a stable short hash for deterministic IDs."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


def normalize_url(url: str) -> str:
    """Normalize a URL string for fetching and ID generation."""
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        return f"https://{url.strip()}"
    return url.strip()


def trim_to_max_length(text: str, max_length: int) -> str:
    """Trim text to a maximum length while keeping the end of the string."""
    if max_length <= 0:
        return ""
    return text[-max_length:]


def read_json_file(path: Path) -> dict:
    """Read a JSON object from disk."""
    with path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def write_json_file(path: Path, payload: dict) -> None:
    """Write a JSON object to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, ensure_ascii=True, indent=2)


def get_google_ai_studio_settings(
    model_env_name: str,
    default_model: str,
    provider_env_name: str = "LLM_PROVIDER",
    default_provider: str = "google_ai_studio",
    base_url_env_name: str = "GOOGLE_API_BASE_URL",
    default_base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    api_key_env_name: str = "GOOGLE_API_KEY",
) -> dict:
    """Return normalized settings for a Google AI Studio Gemini caller."""
    provider = get_env(provider_env_name, default_provider) or default_provider
    model = get_env(model_env_name, get_env("GEMINI_MODEL", default_model)) or default_model
    base_url = (get_env(base_url_env_name, default_base_url) or default_base_url).rstrip("/")
    api_key = get_env(api_key_env_name, required=True)
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
    }


def call_google_ai_studio_generate_content(
    *,
    prompt: str,
    system_prompt: str,
    model: str,
    base_url: str,
    api_key: str,
    timeout: int = 60,
    temperature: float = 0,
) -> str:
    """Call the Google AI Studio Gemini generateContent API and return text content."""
    url = f"{base_url}/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
    except RequestException as exc:
        response_text = ""
        if getattr(exc, "response", None) is not None:
            try:
                response_text = exc.response.text[:1000]
            except Exception:
                response_text = ""
        detail = f" Google API response: {response_text}" if response_text else ""
        raise RuntimeError(f"Failed to call the Google AI Studio API.{detail}") from exc

    try:
        response_json = response.json()
        parts = response_json["candidates"][0]["content"]["parts"]
        content = "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("The Google AI Studio API returned an unexpected response format.") from exc

    normalized = normalize_whitespace(str(content))
    if not normalized:
        raise RuntimeError("The Google AI Studio API returned an empty response.")
    return normalized
