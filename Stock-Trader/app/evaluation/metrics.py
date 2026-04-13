"""Deterministic evaluation metrics for the stock trading agent."""

from __future__ import annotations

from typing import Any


def is_intent_correct(actual: str | None, expected: str) -> bool:
    """Return whether the detected intent matches expectation."""

    return actual == expected


def is_extraction_correct(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Return whether extracted entities match expected values."""

    return (
        actual.get("requested_symbol") == expected.get("expected_symbol")
        and actual.get("requested_quantity") == expected.get("expected_quantity")
        and actual.get("target_currency") == expected.get("expected_currency")
    )


def is_route_correct(actual_route: str, expected_route: str) -> bool:
    """Return whether the selected route matches expectation."""

    return actual_route == expected_route


def is_approval_safe(interrupted: bool, expected_interrupt: bool) -> bool:
    """Return whether approval behavior matches expectation."""

    return interrupted == expected_interrupt


def response_passes(result: dict[str, Any], case: dict[str, Any]) -> bool:
    """Return whether the final response matches the expectation for a case."""

    error_fragment = case.get("expected_error_contains")
    if error_fragment:
        return error_fragment.lower() in (result.get("error") or result.get("response_text", "")).lower()

    required_fragments = case.get("response_contains", [])
    response_text = (result.get("response_text") or "").lower()
    return all(fragment.lower() in response_text for fragment in required_fragments)

