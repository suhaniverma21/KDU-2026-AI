"""Fallback handling utilities for the FixIt LLMOps system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .config_loader import load_all_config


SAFE_SUPPORT_RESPONSE = (
    "We are reviewing your request and a support specialist may need to assist further. "
    "Please share any relevant booking details if available."
)


@dataclass(frozen=True)
class FallbackResult:
    """Structured result describing a fallback action."""

    fallback_applied: bool
    fallback_type: str
    fallback_reason: str
    response_text: str
    selected_tier: str | None
    prompt_id: str | None
    prompt_version: str | None
    incident_metadata: dict[str, Any]


def build_safe_fallback(reason: str) -> dict[str, Any]:
    """Return a safe customer-facing fallback response."""
    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="safe_response",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=None,
            prompt_id=None,
            prompt_version=None,
            incident_metadata={"severity": "medium", "reason": reason},
        )
    )


def resolve_fallback(
    scenario: str,
    config: dict[str, Any] | None = None,
    *,
    classification: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
    prompt: dict[str, Any] | None = None,
    error_message: str | None = None,
    confidence_threshold: float = 0.6,
) -> dict[str, Any]:
    """Resolve a deterministic fallback action for a known failure scenario."""
    active_config = config or load_all_config()
    routing_defaults = active_config["routing"].get("defaults", {})
    prompt_defaults = active_config["prompts"].get("default_prompt", {})

    handlers = {
        "low_confidence_rule_classification": lambda: _handle_low_confidence_rule_classification(
            classification=classification,
            routing_defaults=routing_defaults,
            threshold=confidence_threshold,
        ),
        "low_confidence": lambda: _handle_low_confidence(
            classification=classification,
            routing_defaults=routing_defaults,
            threshold=confidence_threshold,
        ),
        "secondary_classifier_failure": lambda: _handle_secondary_classifier_failure(
            routing_defaults=routing_defaults,
            error_message=error_message,
        ),
        "unresolved_classification": lambda: _handle_unresolved_classification(
            routing_defaults=routing_defaults,
            error_message=error_message,
        ),
        "missing_prompt": lambda: _handle_missing_prompt(
            prompt_defaults=prompt_defaults,
            error_message=error_message,
        ),
        "model_api_failure": lambda: _handle_model_api_failure(
            route=route,
            routing_defaults=routing_defaults,
            error_message=error_message,
        ),
        "budget_limit_exceeded": lambda: _handle_budget_limit_exceeded(
            routing_defaults=routing_defaults,
            route=route,
        ),
    }

    if scenario not in handlers:
        raise ValueError(f"Unknown fallback scenario: {scenario}")

    result = handlers[scenario]()
    if prompt is not None and result["prompt_id"] is None:
        result["prompt_id"] = prompt.get("prompt_id")
        result["prompt_version"] = prompt.get("version")
    return result


def _handle_low_confidence_rule_classification(
    *,
    classification: dict[str, Any] | None,
    routing_defaults: dict[str, Any],
    threshold: float,
) -> dict[str, Any]:
    confidence = 0.0 if classification is None else float(classification.get("confidence", 0.0))
    selected_tier = routing_defaults.get("low_confidence_tier", "medium")
    reason = (
        f"Stage 1 rule classification confidence {confidence:.2f} is below threshold {threshold:.2f}; "
        f"escalating beyond the rule result."
    )
    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="low_confidence_rule_classification",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=selected_tier,
            prompt_id=None,
            prompt_version=None,
            incident_metadata={
                "scenario": "low_confidence_rule_classification",
                "severity": "low",
                "confidence": confidence,
                "threshold": threshold,
            },
        )
    )


def _handle_low_confidence(
    *,
    classification: dict[str, Any] | None,
    routing_defaults: dict[str, Any],
    threshold: float,
) -> dict[str, Any]:
    confidence = 0.0 if classification is None else float(classification.get("confidence", 0.0))
    selected_tier = routing_defaults.get("low_confidence_tier", "medium")
    reason = (
        f"Classification confidence {confidence:.2f} is below threshold {threshold:.2f}; "
        f"using fallback tier '{selected_tier}'."
    )
    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="tier_downgrade",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=selected_tier,
            prompt_id=None,
            prompt_version=None,
            incident_metadata={
                "scenario": "low_confidence",
                "severity": "low",
                "confidence": confidence,
                "threshold": threshold,
            },
        )
    )


def _handle_missing_prompt(*, prompt_defaults: dict[str, Any], error_message: str | None) -> dict[str, Any]:
    reason = "Requested prompt could not be loaded; using the default prompt."
    if error_message:
        reason = f"{reason} Error: {error_message}"

    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="default_prompt",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=None,
            prompt_id=prompt_defaults.get("prompt_id"),
            prompt_version=prompt_defaults.get("version"),
            incident_metadata={
                "scenario": "missing_prompt",
                "severity": "medium",
                "default_prompt_id": prompt_defaults.get("prompt_id"),
                "default_prompt_version": prompt_defaults.get("version"),
            },
        )
    )


def _handle_model_api_failure(
    *,
    route: dict[str, Any] | None,
    routing_defaults: dict[str, Any],
    error_message: str | None,
) -> dict[str, Any]:
    fallback_tier = routing_defaults.get("unavailable_model_fallback_tier", "medium")
    requested_tier = None if route is None else route.get("selected_tier")
    reason = f"Model generation failed; retry path should use fallback tier '{fallback_tier}'."
    if error_message:
        reason = f"{reason} Error: {error_message}"

    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="tier_downgrade",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=fallback_tier,
            prompt_id=None,
            prompt_version=None,
            incident_metadata={
                "scenario": "model_api_failure",
                "severity": "high",
                "requested_tier": requested_tier,
                "fallback_tier": fallback_tier,
                "error_message": error_message,
            },
        )
    )


def _handle_secondary_classifier_failure(
    *,
    routing_defaults: dict[str, Any],
    error_message: str | None,
) -> dict[str, Any]:
    safe_tier = routing_defaults.get("unresolved_classification_tier", "medium")
    reason = f"Secondary classifier failed; using unresolved safe routing tier '{safe_tier}'."
    if error_message:
        reason = f"{reason} Error: {error_message}"

    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="secondary_classifier_failure",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=safe_tier,
            prompt_id=None,
            prompt_version=None,
            incident_metadata={
                "scenario": "secondary_classifier_failure",
                "severity": "medium",
                "error_message": error_message,
            },
        )
    )


def _handle_unresolved_classification(
    *,
    routing_defaults: dict[str, Any],
    error_message: str | None,
) -> dict[str, Any]:
    safe_tier = routing_defaults.get("unresolved_classification_tier", "medium")
    reason = f"Classification remains unresolved; using safe routing tier '{safe_tier}'."
    if error_message:
        reason = f"{reason} Detail: {error_message}"

    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="unresolved_classification",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=safe_tier,
            prompt_id=None,
            prompt_version=None,
            incident_metadata={
                "scenario": "unresolved_classification",
                "severity": "medium",
                "error_message": error_message,
            },
        )
    )


def _handle_budget_limit_exceeded(
    *,
    routing_defaults: dict[str, Any],
    route: dict[str, Any] | None,
) -> dict[str, Any]:
    fallback_tier = routing_defaults.get("budget_exceeded_fallback_tier", "cheap")
    requested_tier = None if route is None else route.get("selected_tier")
    reason = f"Budget hard limit reached; routing to budget-safe tier '{fallback_tier}'."

    return asdict(
        FallbackResult(
            fallback_applied=True,
            fallback_type="budget_guardrail",
            fallback_reason=reason,
            response_text=SAFE_SUPPORT_RESPONSE,
            selected_tier=fallback_tier,
            prompt_id=None,
            prompt_version=None,
            incident_metadata={
                "scenario": "budget_limit_exceeded",
                "severity": "high",
                "requested_tier": requested_tier,
                "fallback_tier": fallback_tier,
            },
        )
    )
