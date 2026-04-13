"""Helpers for LLM token usage and cost estimation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class UsageRecord:
    """Structured record for a single LLM interaction."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float


MODEL_PRICING_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    # Approximate placeholder pricing for observability purposes.
    # These values can be updated when the project chooses a definitive pricing reference.
    "gemini-1.5-flash": {"prompt": 0.000075, "completion": 0.0003},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate request cost from token counts using a simple pricing table."""

    pricing = MODEL_PRICING_PER_1K_TOKENS.get(model)
    if pricing is None:
        return 0.0

    prompt_cost = (prompt_tokens / 1000) * pricing["prompt"]
    completion_cost = (completion_tokens / 1000) * pricing["completion"]
    return round(prompt_cost + completion_cost, 8)


def build_usage_record(model: str, prompt_tokens: int, completion_tokens: int) -> UsageRecord:
    """Build a normalized usage record from token counts."""

    total_tokens = prompt_tokens + completion_tokens
    return UsageRecord(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimate_cost(model, prompt_tokens, completion_tokens),
    )


def extract_usage_metadata(response: Any) -> UsageRecord | None:
    """Extract usage metadata from a Gemini response when available."""

    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata is None:
        return None

    prompt_tokens = int(getattr(usage_metadata, "prompt_token_count", 0) or 0)
    completion_tokens = int(getattr(usage_metadata, "candidates_token_count", 0) or 0)
    model_name = getattr(response, "model_version", None) or getattr(response, "model", None) or "unknown-model"

    return build_usage_record(
        model=str(model_name),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def usage_record_to_dict(record: UsageRecord | None) -> dict[str, Any] | None:
    """Serialize a usage record to a plain dictionary."""

    if record is None:
        return None
    return asdict(record)

