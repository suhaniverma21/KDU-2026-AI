"""Post-ingestion text normalization and summarization gating."""

from __future__ import annotations

from dataclasses import dataclass
import re


SUMMARIZATION_MIN_TEXT_LENGTH = 150


@dataclass
class QualityGateResult:
    """Normalized text plus decisions used by downstream pipeline stages."""

    original_text: str
    normalized_text: str
    character_count: int
    should_skip_summary: bool


def normalize_text(text: str) -> QualityGateResult:
    """Normalize transcript text and determine summary eligibility."""
    original_text = text or ""
    normalized = _coerce_to_safe_utf8(original_text)
    normalized = _collapse_whitespace(normalized)
    normalized = normalized.strip()

    character_count = len(normalized)
    return QualityGateResult(
        original_text=original_text,
        normalized_text=normalized,
        character_count=character_count,
        should_skip_summary=character_count < SUMMARIZATION_MIN_TEXT_LENGTH,
    )


def should_skip_summarization(text: str) -> bool:
    """Return True when the text is too short to justify summarization."""
    return len((text or "").strip()) < SUMMARIZATION_MIN_TEXT_LENGTH


def _coerce_to_safe_utf8(text: str) -> str:
    """Replace unreadable characters with safe UTF-8-compatible output."""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _collapse_whitespace(text: str) -> str:
    """Reduce repeated whitespace while preserving paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text
