"""Tests for cost tracking."""

import pytest

from src.config_loader import load_all_config
from src.cost_tracker import CostTracker


def test_estimate_request_cost_uses_model_pricing() -> None:
    tracker = CostTracker(config=load_all_config())

    cost = tracker.estimate_request_cost("cheap", input_tokens=1000, output_tokens=500)

    assert cost == 0.0012


def test_add_request_cost_updates_monthly_spend() -> None:
    tracker = CostTracker(config=load_all_config())

    assert tracker.add_request_cost(1.25) == 1.25
    assert tracker.monthly_spend_usd == 1.25


def test_add_classifier_cost_updates_separate_cost_breakdown() -> None:
    tracker = CostTracker(config=load_all_config())

    tracker.add_classifier_cost(0.25)

    assert tracker.monthly_spend_usd == 0.25
    assert tracker.get_monthly_summary()["cost_breakdown_usd"]["classification"] == 0.25


def test_get_budget_status_is_normal_below_warning_threshold() -> None:
    tracker = CostTracker(config=load_all_config())
    tracker.add_request_cost(399.99)

    assert tracker.get_budget_status() == "normal"


def test_get_budget_status_transitions_to_warning() -> None:
    tracker = CostTracker(config=load_all_config())
    tracker.add_request_cost(400.0)

    assert tracker.get_budget_status() == "warning"
    assert tracker.should_reduce_premium_usage() is True


def test_get_budget_status_transitions_to_hard_limit() -> None:
    tracker = CostTracker(config=load_all_config())
    tracker.add_request_cost(500.0)

    assert tracker.get_budget_status() == "hard_limit"
    assert tracker.should_reduce_premium_usage() is True
    assert tracker.is_hard_limit_reached() is True


def test_budget_helpers_remain_false_below_warning_threshold() -> None:
    tracker = CostTracker(config=load_all_config())
    tracker.add_request_cost(100.0)

    assert tracker.should_reduce_premium_usage() is False
    assert tracker.is_hard_limit_reached() is False


def test_get_monthly_summary_returns_aggregate_fields() -> None:
    tracker = CostTracker(config=load_all_config())
    tracker.add_request_cost(1.0)
    tracker.add_request_cost(2.0)

    summary = tracker.get_monthly_summary()

    assert summary["monthly_spend_usd"] == 3.0
    assert summary["request_count"] == 2
    assert summary["average_cost_per_request_usd"] == 1.5
    assert summary["remaining_budget_usd"] == 497.0
    assert summary["budget_status"] == "normal"


def test_add_request_cost_rejects_negative_values() -> None:
    tracker = CostTracker(config=load_all_config())

    with pytest.raises(ValueError, match="cannot be negative"):
        tracker.add_request_cost(-0.01)


def test_estimate_request_cost_rejects_unknown_model_tier() -> None:
    tracker = CostTracker(config=load_all_config())

    with pytest.raises(ValueError, match="Unknown model tier"):
        tracker.estimate_request_cost("unknown", input_tokens=100, output_tokens=50)
