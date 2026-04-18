"""Tests for fallback handling."""

from __future__ import annotations

import pytest

from src.config_loader import load_all_config
from src.fallback_handler import build_safe_fallback, resolve_fallback


def test_build_safe_fallback_returns_structured_response() -> None:
    result = build_safe_fallback("temporary issue")

    assert result["fallback_applied"] is True
    assert result["fallback_type"] == "safe_response"
    assert "support specialist" in result["response_text"]
    assert result["incident_metadata"]["reason"] == "temporary issue"


def test_resolve_fallback_handles_low_confidence() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "low_confidence",
        config=config,
        classification={"category": "FAQ", "complexity": "low", "confidence": 0.25},
    )

    assert result["fallback_type"] == "tier_downgrade"
    assert result["selected_tier"] == "medium"
    assert result["incident_metadata"]["scenario"] == "low_confidence"


def test_resolve_fallback_handles_low_confidence_rule_classification() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "low_confidence_rule_classification",
        config=config,
        classification={"confidence": 0.25},
    )

    assert result["fallback_type"] == "low_confidence_rule_classification"
    assert result["selected_tier"] == "medium"
    assert result["incident_metadata"]["scenario"] == "low_confidence_rule_classification"


def test_resolve_fallback_handles_missing_prompt_with_default_prompt() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "missing_prompt",
        config=config,
        error_message="Prompt file not found",
    )

    assert result["fallback_type"] == "default_prompt"
    assert result["prompt_id"] == "faq"
    assert result["prompt_version"] == "v2"
    assert "Prompt file not found" in result["fallback_reason"]


def test_resolve_fallback_handles_model_api_failure() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "model_api_failure",
        config=config,
        route={"selected_tier": "premium"},
        error_message="timeout",
    )

    assert result["fallback_type"] == "tier_downgrade"
    assert result["selected_tier"] == "medium"
    assert result["incident_metadata"]["requested_tier"] == "premium"
    assert result["incident_metadata"]["error_message"] == "timeout"


def test_resolve_fallback_handles_secondary_classifier_failure() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "secondary_classifier_failure",
        config=config,
        error_message="classifier down",
    )

    assert result["fallback_type"] == "secondary_classifier_failure"
    assert result["selected_tier"] == "medium"
    assert result["incident_metadata"]["scenario"] == "secondary_classifier_failure"


def test_resolve_fallback_handles_unresolved_classification() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "unresolved_classification",
        config=config,
        error_message="stage2 disabled",
    )

    assert result["fallback_type"] == "unresolved_classification"
    assert result["selected_tier"] == "medium"
    assert result["incident_metadata"]["scenario"] == "unresolved_classification"


def test_resolve_fallback_handles_budget_limit_exceeded() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "budget_limit_exceeded",
        config=config,
        route={"selected_tier": "premium"},
    )

    assert result["fallback_type"] == "budget_guardrail"
    assert result["selected_tier"] == "cheap"
    assert result["incident_metadata"]["scenario"] == "budget_limit_exceeded"


def test_resolve_fallback_reuses_prompt_metadata_when_provided() -> None:
    config = load_all_config()

    result = resolve_fallback(
        "model_api_failure",
        config=config,
        route={"selected_tier": "medium"},
        prompt={"prompt_id": "booking", "version": "v1"},
    )

    assert result["prompt_id"] == "booking"
    assert result["prompt_version"] == "v1"


def test_resolve_fallback_rejects_unknown_scenario() -> None:
    with pytest.raises(ValueError, match="Unknown fallback scenario"):
        resolve_fallback("not_a_real_scenario")
