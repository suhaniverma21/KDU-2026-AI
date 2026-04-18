"""Tests for structured logging and request observability."""

from __future__ import annotations

import json
import logging

from src.config_loader import load_all_config
from src.llm_client import BaseProviderAdapter, LLMClient, LLMRequest
from src.main import handle_query
from src.observability import build_request_log_entry, create_request_trace


class ListHandler(logging.Handler):
    """Capture log messages for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class DeterministicAdapter(BaseProviderAdapter):
    """Return stable mock responses for observability tests."""

    def generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        return {
            "response_text": f"Mocked {request.model_tier} response",
            "token_usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            "estimated_cost_usd": 0.002,
        }


def test_build_request_log_entry_is_machine_readable_and_sanitized() -> None:
    trace = create_request_trace()
    metadata = {
        "classification": {"category": "FAQ", "complexity": "low", "confidence": 0.7},
        "route": {"selected_tier": "cheap"},
        "prompt": {"prompt_id": "faq", "version": "v1"},
        "model": {"name": "gemini-2.5-flash-lite", "latency_ms": 12.5},
        "cost": {
            "request_cost_usd": 0.001,
            "budget_status_after_request": "normal",
            "remaining_budget_usd": 499.0,
        },
        "budget_status_before_request": "normal",
        "fallback": {"applied": False, "events": []},
    }

    entry = build_request_log_entry(request_trace=trace, query="What are your hours?", metadata=metadata)

    assert entry["request_id"].startswith("req_")
    assert entry["query_length"] == 20
    assert entry["query_category"] == "FAQ"
    assert entry["fallback_applied"] is False
    assert "query" not in entry


def test_handle_query_emits_structured_log_without_raw_query_text() -> None:
    config = load_all_config()
    client = LLMClient(config=config, provider_adapters={"google_ai_studio": DeterministicAdapter()})
    logger = logging.getLogger("fixit_llmops_test")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    handler = ListHandler()
    logger.addHandler(handler)

    result = handle_query("What are your hours?", logger=logger, llm_client=client, config=config)

    assert result["metadata"]["request_id"].startswith("req_")
    assert len(handler.messages) == 1

    payload = json.loads(handler.messages[0])
    assert payload["request_id"] == result["metadata"]["request_id"]
    assert payload["query_category"] == "FAQ"
    assert payload["selected_model_tier"] == "cheap"
    assert payload["actual_model_name"] == "gemini-2.5-flash-lite"
    assert "What are your hours?" not in handler.messages[0]
