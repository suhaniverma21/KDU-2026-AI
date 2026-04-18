"""Routing logic for the FixIt LLMOps system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .config_loader import load_all_config


@dataclass(frozen=True)
class RoutingDecision:
    """Structured routing output for a classified query."""

    selected_tier: str
    selected_model_name: str | None
    decision_reason: str
    fallback_applied: bool
    downgrade_applied: bool
    budget_status: str


def route_query(
    classification: dict[str, Any],
    config: dict[str, Any] | None = None,
    budget_status: str = "normal",
    confidence_threshold: float = 0.6,
) -> dict[str, Any]:
    """Route a classified query to the appropriate model tier using external config."""
    active_config = config or load_all_config()
    routing_config = active_config["routing"]
    model_config = active_config["models"]["models"]
    feature_flags = active_config["feature_flags"]["feature_flags"]
    routing_rules = routing_config["routing_rules"]
    routing_defaults = routing_config.get("defaults", {})
    budget_guardrails = routing_config.get("budget_guardrails", {})

    category = classification.get("category", "FAQ")
    complexity = classification.get("complexity", "low")
    confidence = float(classification.get("confidence", 0.0))
    resolved = bool(classification.get("resolved", True))

    base_tier = routing_rules.get(category, {}).get(
        complexity,
        routing_defaults.get("budget_exceeded_fallback_tier", "cheap"),
    )
    selected_tier = base_tier
    reason_parts = [f"Base route matched category '{category}' and complexity '{complexity}' -> '{base_tier}'."]
    fallback_applied = False
    downgrade_applied = False

    if not resolved:
        selected_tier = routing_defaults.get("unresolved_classification_tier", "medium")
        fallback_applied = True
        downgrade_applied = selected_tier != base_tier
        reason_parts.append(
            f"Classification remained unresolved; using safe routing tier '{selected_tier}'."
        )

    if (
        feature_flags.get("enable_fallback", False)
        and feature_flags.get("enable_low_confidence_downgrade", False)
        and confidence < confidence_threshold
        and resolved
    ):
        selected_tier = routing_defaults.get("low_confidence_tier", selected_tier)
        fallback_applied = True
        reason_parts.append(
            f"Classification confidence {confidence:.2f} is below {confidence_threshold:.2f}; "
            f"using low-confidence tier '{selected_tier}'."
        )

    if feature_flags.get("enable_budget_guardrail", False):
        if budget_status == "warning" and selected_tier == "premium":
            selected_tier = budget_guardrails.get("warning", {}).get("premium_downgrade_tier", "medium")
            downgrade_applied = True
            fallback_applied = True
            reason_parts.append(
                f"Budget status is 'warning'; premium traffic downgraded to '{selected_tier}'."
            )
        elif budget_status == "hard_limit":
            selected_tier = _resolve_hard_limit_tier(
                category=category,
                complexity=complexity,
                routing_defaults=routing_defaults,
                budget_guardrails=budget_guardrails,
            )
            downgrade_applied = selected_tier != base_tier
            fallback_applied = True
            reason_parts.append(
                f"Budget status is 'hard_limit'; routing to budget fallback tier '{selected_tier}'."
            )

    model_details = model_config.get(selected_tier)
    if not model_details or not model_details.get("enabled", False):
        fallback_tier = routing_defaults.get("unavailable_model_fallback_tier", "medium")
        fallback_model = model_config.get(fallback_tier)
        if fallback_model and fallback_model.get("enabled", False):
            downgrade_applied = downgrade_applied or fallback_tier != selected_tier
            selected_tier = fallback_tier
            model_details = fallback_model
            fallback_applied = True
            reason_parts.append(f"Selected tier was unavailable; using fallback tier '{selected_tier}'.")
        else:
            reason_parts.append("Selected tier and configured fallback tier are unavailable.")
            model_details = None

    return asdict(
        RoutingDecision(
            selected_tier=selected_tier,
            selected_model_name=None if model_details is None else model_details.get("model_name"),
            decision_reason=" ".join(reason_parts),
            fallback_applied=fallback_applied,
            downgrade_applied=downgrade_applied,
            budget_status=budget_status,
        )
    )


def _resolve_hard_limit_tier(
    *,
    category: str,
    complexity: str,
    routing_defaults: dict[str, Any],
    budget_guardrails: dict[str, Any],
) -> str:
    """Resolve the safest allowed tier when the hard budget limit is reached."""
    hard_limit_policy = budget_guardrails.get("hard_limit", {})
    safe_overrides = hard_limit_policy.get("safe_category_overrides", {})
    category_override = safe_overrides.get(category, {})

    if complexity in category_override:
        return category_override[complexity]

    return hard_limit_policy.get(
        "default_fallback_tier",
        routing_defaults.get("budget_exceeded_fallback_tier", "cheap"),
    )
