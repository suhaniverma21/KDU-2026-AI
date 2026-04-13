"""Gemini integration helpers for structured request extraction."""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.observability.tracing import build_trace_metadata, maybe_traceable
from app.observability.usage import extract_usage_metadata, usage_record_to_dict
from app.utils.logging import log_event
from app.utils.retry import retry_call

try:
    from google import genai
except ImportError:  # pragma: no cover - optional dependency at runtime
    genai = None


EXTRACTION_PROMPT = """You extract structured trading-agent request data.

Return only valid JSON with exactly these keys:
- intent
- requested_symbol
- requested_quantity
- target_currency

Rules:
- intent must be one of: get_portfolio_value, get_stock_price, buy_stock, general_question
- requested_symbol must be a stock ticker string or null
- requested_quantity must be an integer or null
- target_currency must be a 3-letter currency code or null
- Do not include explanations

User message:
{message}
"""


def _strip_json_fence(text: str) -> str:
    """Remove common markdown code fences around JSON responses."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return cleaned


def is_gemini_enabled() -> bool:
    """Return whether Gemini is configured well enough to attempt a call."""

    settings = get_settings()
    return bool(settings.google_api_key)


@maybe_traceable(name="gemini_request_extraction", run_type="llm")
def extract_request_with_gemini(message: str) -> dict[str, Any]:
    """Use Google AI Studio Gemini to extract structured request fields."""

    settings = get_settings()
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured.")
    if genai is None:
        raise RuntimeError("google-genai is not installed.")

    client = genai.Client(api_key=settings.google_api_key)
    response = retry_call(
        lambda: client.models.generate_content(
            model=settings.gemini_model,
            contents=EXTRACTION_PROMPT.format(message=message),
        ),
        operation_name="gemini_generate_content",
        retry_on=(RuntimeError, ValueError, Exception),
    )
    raw_text = getattr(response, "text", "") or ""
    usage_record = extract_usage_metadata(response)
    parsed = json.loads(_strip_json_fence(raw_text))
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response was not a JSON object.")

    log_event(
        "gemini_extraction_succeeded",
        model=settings.gemini_model,
        usage=usage_record_to_dict(usage_record),
        trace_metadata=build_trace_metadata(model=settings.gemini_model, environment=settings.environment),
    )
    return parsed
