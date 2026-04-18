"""Tests for routing logic."""

from src.config_loader import load_all_config
from src.router import route_query


def test_route_query_uses_routing_rules_for_normal_case() -> None:
    config = load_all_config()
    result = route_query({"category": "FAQ", "complexity": "low", "confidence": 0.9}, config=config)

    assert result["selected_tier"] == "cheap"
    assert result["selected_model_name"] == "gemini-2.5-flash-lite"
    assert result["fallback_applied"] is False
    assert result["downgrade_applied"] is False


def test_route_query_uses_low_confidence_override_when_enabled() -> None:
    config = load_all_config()

    result = route_query({"category": "FAQ", "complexity": "low", "confidence": 0.25}, config=config)

    assert result["selected_tier"] == "medium"
    assert result["selected_model_name"] == "gemini-2.5-flash"
    assert result["fallback_applied"] is True
    assert "low-confidence tier 'medium'" in result["decision_reason"]


def test_route_query_downgrades_premium_on_budget_warning() -> None:
    config = load_all_config()

    result = route_query(
        {"category": "complaint", "complexity": "high", "confidence": 0.95},
        config=config,
        budget_status="warning",
    )

    assert result["selected_tier"] == "medium"
    assert result["selected_model_name"] == "gemini-2.5-flash"
    assert result["fallback_applied"] is True
    assert result["downgrade_applied"] is True
    assert "downgraded to 'medium'" in result["decision_reason"]


def test_route_query_uses_budget_fallback_on_hard_limit() -> None:
    config = load_all_config()

    result = route_query(
        {"category": "complaint", "complexity": "high", "confidence": 0.95},
        config=config,
        budget_status="hard_limit",
    )

    assert result["selected_tier"] == "medium"
    assert result["selected_model_name"] == "gemini-2.5-flash"
    assert result["fallback_applied"] is True
    assert result["downgrade_applied"] is True


def test_route_query_blocks_premium_but_keeps_safe_complaint_path_on_hard_limit() -> None:
    config = load_all_config()

    result = route_query(
        {"category": "complaint", "complexity": "medium", "confidence": 0.95},
        config=config,
        budget_status="hard_limit",
    )

    assert result["selected_tier"] == "cheap"
    assert result["selected_model_name"] == "gemini-2.5-flash-lite"
    assert result["fallback_applied"] is True


def test_route_query_uses_unavailable_model_fallback_tier() -> None:
    config = load_all_config()
    config["models"]["models"]["cheap"]["enabled"] = False

    result = route_query({"category": "FAQ", "complexity": "low", "confidence": 0.9}, config=config)

    assert result["selected_tier"] == "medium"
    assert result["selected_model_name"] == "gemini-2.5-flash"
    assert result["fallback_applied"] is True
    assert result["downgrade_applied"] is True


def test_route_query_uses_safe_medium_path_for_unresolved_classification() -> None:
    config = load_all_config()

    result = route_query(
        {"category": "FAQ", "complexity": "medium", "confidence": 0.0, "resolved": False},
        config=config,
    )

    assert result["selected_tier"] == "medium"
    assert result["selected_model_name"] == "gemini-2.5-flash"
    assert result["fallback_applied"] is True
