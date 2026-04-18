"""Tests for the hybrid query classifier."""

from __future__ import annotations

from src.classifier import HybridClassifier, RulePreClassifier, classify_query
from src.config_loader import load_all_config
from src.llm_client import LLMClientError, LLMResponse


class MockClassifierClient:
    """Minimal mock client for stage 2 classification tests."""

    def __init__(self, response_text: str, estimated_cost_usd: float = 0.001) -> None:
        self.response_text = response_text
        self.estimated_cost_usd = estimated_cost_usd
        self.calls = 0

    def generate(self, _request) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            response_text=self.response_text,
            provider="google_ai_studio",
            model_name="gemini-2.5-flash-lite",
            model_tier="cheap",
            prompt_id="hybrid_classifier",
            prompt_version="v1",
            token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            latency_ms=10.0,
            estimated_cost_usd=self.estimated_cost_usd,
            retries_used=0,
        )


class FailingClassifierClient:
    """Mock client that simulates a classifier LLM failure."""

    def generate(self, _request) -> LLMResponse:
        raise LLMClientError("classifier unavailable")


def test_stage1_obvious_query_is_accepted_directly() -> None:
    config = load_all_config()
    result = classify_query("What are your hours?", config=config)

    assert result["category"] == "FAQ"
    assert result["complexity"] == "low"
    assert result["classifier_source"] == "stage1_rules"
    assert result["direct_accept"] is True
    assert result["stage2_triggered"] is False
    assert result["classification_cost_usd"] == 0.0


def test_ambiguous_query_escalates_to_stage2_classifier() -> None:
    config = load_all_config()
    mock_client = MockClassifierClient(
        '{"category":"booking","complexity":"medium","confidence":0.82,"reasoning":"Appointment-related support request.","classifier_source":"stage2_llm"}'
    )

    result = classify_query(
        "I have an appointment issue and need help.",
        config=config,
        llm_client=mock_client,
    )

    assert result["category"] == "booking"
    assert result["complexity"] == "medium"
    assert result["classifier_source"] == "stage2_llm"
    assert result["stage2_triggered"] is True
    assert result["classification_cost_usd"] == 0.001


def test_stage2_can_be_disabled_via_config() -> None:
    config = load_all_config()
    config["classifier"]["classifier"]["stage2"]["enabled"] = False

    result = classify_query("I have an appointment issue and need help.", config=config)

    assert result["resolved"] is False
    assert result["classifier_source"] == "classifier_fallback"
    assert result["complexity"] == "medium"
    assert any(
        event["incident_metadata"]["scenario"] == "unresolved_classification"
        for event in result["fallback_events"]
    )


def test_stage2_failure_falls_back_to_unresolved_classification() -> None:
    config = load_all_config()
    result = classify_query(
        "I have an appointment issue and need help.",
        config=config,
        llm_client=FailingClassifierClient(),
    )

    assert result["resolved"] is False
    assert result["classification_cost_usd"] == 0.0
    assert any(
        event["incident_metadata"]["scenario"] == "secondary_classifier_failure"
        for event in result["fallback_events"]
    )


def test_rule_preclassifier_exposes_competing_categories_for_ambiguous_cases() -> None:
    config = load_all_config()
    pre_classifier = RulePreClassifier(config["classifier"]["classifier"])
    result = pre_classifier.classify("I need help with my appointment issue.")

    assert result.should_escalate is True
    assert result.direct_accept is False


def test_hybrid_classifier_allows_pluggable_instance() -> None:
    config = load_all_config()
    classifier = HybridClassifier(config=config, llm_client=MockClassifierClient(
        '{"category":"complaint","complexity":"high","confidence":0.9,"reasoning":"Refund-related missed appointment.","classifier_source":"stage2_llm"}'
    ))
    result = classify_query("I need help with my appointment issue.", classifier=classifier)

    assert result["category"] == "complaint"
    assert result["stage2_triggered"] is True
