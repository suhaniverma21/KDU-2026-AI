"""Integration tests for the end-to-end FixIt support flow."""

from __future__ import annotations

import pytest

from src.config_loader import load_all_config
from src.cost_tracker import CostTracker
from src.llm_client import BaseProviderAdapter, LLMClient, LLMRequest, TransientLLMError
from src.main import analyze_query, handle_query


class DeterministicAdapter(BaseProviderAdapter):
    """Return stable mock responses by model tier and query text."""

    def generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        if request.prompt_id == "hybrid_classifier":
            normalized_query = request.user_query.lower()
            if "appointment issue" in normalized_query or "help me with something" in normalized_query:
                return {
                    "response_text": '{"category":"booking","complexity":"medium","confidence":0.8,"reasoning":"Appointment-related support request.","classifier_source":"stage2_llm"}',
                    "token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    "estimated_cost_usd": 0.001,
                }
        return {
            "response_text": f"Mocked {request.model_tier} response for: {request.user_query}",
            "token_usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            "estimated_cost_usd": 0.002,
        }


class PremiumFailingAdapter(BaseProviderAdapter):
    """Fail premium requests and let lower tiers succeed."""

    def generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        if request.model_tier == "premium":
            raise TransientLLMError("premium unavailable")
        return {
            "response_text": f"Recovered via {request.model_tier}",
            "token_usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            "estimated_cost_usd": 0.002,
        }


class AlwaysFailingAdapter(BaseProviderAdapter):
    """Fail every provider call."""

    def generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        raise TransientLLMError("provider down")


class ClassificationFailingAdapter(BaseProviderAdapter):
    """Fail only the hybrid classifier stage."""

    def generate(self, request: LLMRequest, model_config: dict[str, object]) -> dict[str, object]:
        if request.prompt_id == "hybrid_classifier":
            raise TransientLLMError("classifier down")
        return {
            "response_text": f"Mocked {request.model_tier} response for: {request.user_query}",
            "token_usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            "estimated_cost_usd": 0.002,
        }


def build_mock_client(adapter: BaseProviderAdapter | None = None) -> LLMClient:
    """Create an LLM client with a deterministic mock adapter."""
    config = load_all_config()
    return LLMClient(
        config=config,
        provider_adapters={"google_ai_studio": adapter or DeterministicAdapter()},
    )


def test_handle_query_faq_low_complexity_flow_returns_expected_metadata() -> None:
    result = handle_query("What are your hours?", llm_client=build_mock_client())

    assert result["response_text"] == "Mocked cheap response for: What are your hours?"
    assert result["metadata"]["classification"]["category"] == "FAQ"
    assert result["metadata"]["classification"]["complexity"] == "low"
    assert result["metadata"]["route"]["selected_tier"] == "cheap"
    assert result["metadata"]["prompt"]["prompt_id"] == "faq"


def test_handle_query_booking_medium_complexity_flow_returns_expected_metadata() -> None:
    result = handle_query(
        "Can I reschedule my cleaning appointment?",
        llm_client=build_mock_client(),
    )

    assert result["response_text"] == "Mocked medium response for: Can I reschedule my cleaning appointment?"
    assert result["metadata"]["classification"]["category"] == "booking"
    assert result["metadata"]["classification"]["complexity"] == "medium"
    assert result["metadata"]["route"]["selected_tier"] == "medium"
    assert result["metadata"]["prompt"]["prompt_id"] == "booking"


def test_handle_query_complaint_high_complexity_flow_returns_expected_metadata() -> None:
    result = handle_query(
        "My plumber didn't show up and I need a refund.",
        llm_client=build_mock_client(),
    )

    assert result["response_text"] == "Mocked premium response for: My plumber didn't show up and I need a refund."
    assert result["metadata"]["classification"]["category"] == "complaint"
    assert result["metadata"]["classification"]["complexity"] == "high"
    assert result["metadata"]["route"]["selected_tier"] == "premium"
    assert result["metadata"]["prompt"]["prompt_id"] == "complaint"


def test_handle_query_records_low_confidence_fallback_metadata() -> None:
    result = handle_query("Help me with something.", llm_client=build_mock_client())

    assert result["metadata"]["fallback"]["applied"] is True
    assert any(
        event["incident_metadata"]["scenario"] == "low_confidence_rule_classification"
        for event in result["metadata"]["fallback"]["events"]
    )
    assert result["metadata"]["classification"]["stage2_triggered"] is True
    assert result["metadata"]["cost"]["classification_cost_usd"] == 0.001


def test_handle_query_routes_safely_when_stage2_classifier_fails() -> None:
    config = load_all_config()
    client = LLMClient(config=config, provider_adapters={"google_ai_studio": ClassificationFailingAdapter()})

    result = handle_query("Help me with something.", config=config, llm_client=client)

    assert result["metadata"]["classification"]["resolved"] is False
    assert result["metadata"]["route"]["selected_tier"] == "medium"
    assert any(
        event["incident_metadata"]["scenario"] == "secondary_classifier_failure"
        for event in result["metadata"]["fallback"]["events"]
    )


def test_handle_query_falls_back_to_default_prompt_when_prompt_missing(tmp_path) -> None:
    result = handle_query(
        "What are your hours?",
        llm_client=build_mock_client(),
        prompts_dir=tmp_path,
    )

    assert result["metadata"]["fallback"]["applied"] is True
    assert any(
        event["incident_metadata"]["scenario"] == "missing_prompt"
        for event in result["metadata"]["fallback"]["events"]
    )
    assert result["metadata"]["prompt"]["prompt_id"] == "faq"


def test_handle_query_uses_budget_guardrail_when_hard_limit_reached() -> None:
    config = load_all_config()
    tracker = CostTracker(config=config, monthly_spend_usd=500.0)

    result = handle_query(
        "My plumber didn't show up and I need a refund.",
        config=config,
        cost_tracker=tracker,
        llm_client=build_mock_client(),
    )

    assert result["metadata"]["budget_status_before_request"] == "hard_limit"
    assert result["metadata"]["route"]["selected_tier"] == "medium"
    assert any(
        event["incident_metadata"]["scenario"] == "budget_limit_exceeded"
        for event in result["metadata"]["fallback"]["events"]
    )


def test_handle_query_retries_with_fallback_tier_on_model_failure() -> None:
    config = load_all_config()
    client = LLMClient(config=config, provider_adapters={"google_ai_studio": PremiumFailingAdapter()})

    result = handle_query(
        "My plumber didn't show up and I need a refund.",
        config=config,
        llm_client=client,
    )

    assert result["response_text"] == "Recovered via medium"
    assert result["metadata"]["model"]["tier"] == "medium"
    assert any(
        event["incident_metadata"]["scenario"] == "model_api_failure"
        for event in result["metadata"]["fallback"]["events"]
    )


def test_handle_query_returns_safe_response_when_all_models_fail() -> None:
    config = load_all_config()
    client = LLMClient(config=config, provider_adapters={"google_ai_studio": AlwaysFailingAdapter()})

    result = handle_query("Can I reschedule my appointment?", config=config, llm_client=client)

    assert "support specialist" in result["response_text"]
    assert result["metadata"]["model"]["name"] == "safe_fallback"
    assert result["metadata"]["cost"]["request_cost_usd"] == 0.0


def test_handle_query_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query cannot be empty"):
        handle_query("   ", llm_client=build_mock_client())


def test_handle_query_rejects_non_string_query() -> None:
    with pytest.raises(TypeError, match="query must be a string"):
        handle_query(123, llm_client=build_mock_client())  # type: ignore[arg-type]


def test_analyze_query_no_llm_mode_skips_generation_and_routes_safely() -> None:
    config = load_all_config()

    result = analyze_query(
        "Help me with something.",
        config=config,
        cost_tracker=CostTracker(config=config),
        disable_stage2_classifier=True,
    )

    assert result["response_text"] == "LLM generation was skipped."
    assert result["metadata"]["llm_generation_skipped"] is True
    assert result["metadata"]["classification"]["resolved"] is False
    assert result["metadata"]["route"]["selected_tier"] == "medium"
