"""Structured logging and request tracing helpers for FixIt LLMOps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any
from uuid import uuid4


LOGGER_NAME = "fixit_llmops"
logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())


@dataclass(frozen=True)
class RequestTrace:
    """Trace identifiers attached to a single support request."""

    request_id: str
    started_at_utc: str


def create_request_trace() -> RequestTrace:
    """Create a request trace id and timestamp for auditability."""
    return RequestTrace(
        request_id=f"req_{uuid4().hex}",
        started_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def build_request_log_entry(
    *,
    request_trace: RequestTrace,
    query: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build a machine-readable log entry without logging raw query text."""
    classification = metadata["classification"]
    route = metadata["route"]
    prompt = metadata["prompt"]
    model = metadata["model"]
    cost = metadata["cost"]
    fallback = metadata["fallback"]

    return {
        "event": "support_request_completed",
        "request_id": request_trace.request_id,
        "started_at_utc": request_trace.started_at_utc,
        "query_length": len(query),
        "query_word_count": len(query.split()),
        "query_category": classification["category"],
        "complexity": classification["complexity"],
        "confidence": classification["confidence"],
        "selected_model_tier": route["selected_tier"],
        "actual_model_name": model["name"],
        "prompt_id": prompt["prompt_id"],
        "prompt_version": prompt["version"],
        "latency_ms": model["latency_ms"],
        "estimated_cost_usd": cost["request_cost_usd"],
        "fallback_applied": fallback["applied"],
        "fallback_types": [event["fallback_type"] for event in fallback["events"]],
        "fallback_scenarios": [
            event["incident_metadata"].get("scenario", event["fallback_type"])
            for event in fallback["events"]
        ],
        "budget_status_before_request": metadata["budget_status_before_request"],
        "budget_status_after_request": cost["budget_status_after_request"],
        "remaining_budget_usd": cost["remaining_budget_usd"],
    }


def emit_structured_log(
    entry: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Emit a machine-readable JSON log entry."""
    active_logger = logger or logging.getLogger(LOGGER_NAME)
    active_logger.info(json.dumps(entry, sort_keys=True))
