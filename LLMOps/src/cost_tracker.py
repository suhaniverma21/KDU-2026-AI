"""Cost tracking helpers for the FixIt LLMOps system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config_loader import load_all_config


@dataclass
class CostTracker:
    """Track request costs and monthly budget usage."""

    config: dict[str, Any] | None = None
    monthly_spend_usd: float = 0.0
    request_costs_usd: list[float] = field(default_factory=list)
    cost_by_type_usd: dict[str, float] = field(
        default_factory=lambda: {"classification": 0.0, "response_generation": 0.0}
    )

    def __post_init__(self) -> None:
        active_config = self.config or load_all_config()
        self.config = active_config
        self.models = active_config["models"]["models"]
        self.cost_limits = active_config["cost_limits"]["cost_limits"]

    def estimate_request_cost(self, model_tier: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate request cost using configured per-1K token pricing."""
        model_config = self.models.get(model_tier)
        if model_config is None:
            raise ValueError(f"Unknown model tier: {model_tier}")

        input_rate = float(model_config.get("input_cost_per_1k_tokens_usd", 0.0))
        output_rate = float(model_config.get("output_cost_per_1k_tokens_usd", 0.0))
        cost = (input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)
        return round(cost, 6)

    def add_request_cost(self, amount_usd: float) -> float:
        """Record a request cost and return the updated monthly spend."""
        return self.record_cost(amount_usd, cost_type="response_generation")

    def add_classifier_cost(self, amount_usd: float) -> float:
        """Record classification cost and return the updated monthly spend."""
        return self.record_cost(amount_usd, cost_type="classification")

    def record_cost(self, amount_usd: float, *, cost_type: str) -> float:
        """Record a typed request cost and return the updated monthly spend."""
        if amount_usd < 0:
            raise ValueError("Request cost cannot be negative.")
        if cost_type not in self.cost_by_type_usd:
            raise ValueError(f"Unsupported cost type: {cost_type}")

        rounded_amount = round(amount_usd, 6)
        self.request_costs_usd.append(rounded_amount)
        self.cost_by_type_usd[cost_type] = round(self.cost_by_type_usd[cost_type] + rounded_amount, 6)
        self.monthly_spend_usd = round(self.monthly_spend_usd + rounded_amount, 6)
        return self.monthly_spend_usd

    def get_budget_status(self) -> str:
        """Return the current budget status based on configured thresholds."""
        warning_threshold = float(self.cost_limits["warning_threshold_usd"])
        hard_limit = float(self.cost_limits["hard_limit_usd"])

        if self.monthly_spend_usd >= hard_limit:
            return "hard_limit"
        if self.monthly_spend_usd >= warning_threshold:
            return "warning"
        return "normal"

    def should_reduce_premium_usage(self) -> bool:
        """Return whether premium routing should be reduced under current spend."""
        return self.get_budget_status() in {"warning", "hard_limit"}

    def is_hard_limit_reached(self) -> bool:
        """Return whether monthly spend has reached the hard budget limit."""
        return self.get_budget_status() == "hard_limit"

    def get_monthly_summary(self) -> dict[str, Any]:
        """Return a lightweight summary of monthly cost usage."""
        monthly_budget = float(self.cost_limits["monthly_budget_usd"])
        request_count = len(self.request_costs_usd)
        average_cost = round(self.monthly_spend_usd / request_count, 6) if request_count else 0.0

        return {
            "monthly_spend_usd": self.monthly_spend_usd,
            "request_count": request_count,
            "average_cost_per_request_usd": average_cost,
            "remaining_budget_usd": round(max(monthly_budget - self.monthly_spend_usd, 0.0), 6),
            "budget_status": self.get_budget_status(),
            "cost_breakdown_usd": dict(self.cost_by_type_usd),
        }
