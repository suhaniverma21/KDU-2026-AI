"""Tracks token usage and estimated API cost across requests, sessions, and agents."""

from __future__ import annotations

import logging
import threading
from typing import Any

from config.settings import get_settings


class CostTracker:
    """Stores per-call cost data and exposes session and system-level cost summaries."""

    _instance: "CostTracker | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "CostTracker":
        """Return the shared singleton cost tracker instance for the current process."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the in-memory ledger lazily so all modules share one tracker."""
        if getattr(self, "_initialized", False):
            return
        self.settings = get_settings()
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = []
        self._initialized = True

    def record(
        self,
        agent_name: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        session_id: str,
    ) -> dict[str, Any]:
        """Calculate per-call cost, store it, and return the recorded ledger entry."""
        safe_input_tokens = max(0, int(input_tokens or 0))
        safe_output_tokens = max(0, int(output_tokens or 0))
        input_cost = safe_input_tokens * self.settings.cost_per_input_token
        output_cost = safe_output_tokens * self.settings.cost_per_output_token
        total_cost = input_cost + output_cost

        record = {
            "agent_name": agent_name,
            "model": model,
            "session_id": session_id,
            "input_tokens": safe_input_tokens,
            "output_tokens": safe_output_tokens,
            "cost_usd": total_cost,
        }
        with self._lock:
            self._records.append(record)
        return record

    def get_session_cost(self, session_id: str) -> dict[str, Any]:
        """Return an aggregated cost summary for one session."""
        with self._lock:
            session_records = [
                record for record in self._records if record["session_id"] == session_id
            ]

        total_input_tokens = sum(record["input_tokens"] for record in session_records)
        total_output_tokens = sum(record["output_tokens"] for record in session_records)
        total_cost_usd = sum(record["cost_usd"] for record in session_records)
        breakdown_by_agent = self._build_agent_breakdown(session_records)

        return {
            "session_id": session_id,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_usd": total_cost_usd,
            "calls_made": len(session_records),
            "breakdown_by_agent": breakdown_by_agent,
        }

    def get_total_cost(self) -> dict[str, Any]:
        """Return total input tokens, output tokens, calls, and cost across all sessions."""
        with self._lock:
            records = list(self._records)

        return {
            "total_input_tokens": sum(record["input_tokens"] for record in records),
            "total_output_tokens": sum(record["output_tokens"] for record in records),
            "total_cost_usd": sum(record["cost_usd"] for record in records),
            "calls_made": len(records),
        }

    def get_cost_breakdown(self) -> dict[str, dict[str, float | int]]:
        """Return total token and cost usage grouped by agent across all sessions."""
        with self._lock:
            records = list(self._records)
        return self._build_agent_breakdown(records)

    def alert_if_over_budget(self, session_id: str, budget_usd: float) -> bool:
        """Log a warning if a session cost exceeds the supplied budget threshold."""
        session_cost = self.get_session_cost(session_id)
        if session_cost["total_cost_usd"] > budget_usd:
            logging.getLogger(__name__).warning(
                "session_cost_over_budget",
                extra={
                    "session_id": session_id,
                    "budget_usd": budget_usd,
                    "total_cost_usd": session_cost["total_cost_usd"],
                },
            )
            return True
        return False

    @staticmethod
    def _build_agent_breakdown(
        records: list[dict[str, Any]],
    ) -> dict[str, dict[str, float | int]]:
        """Aggregate input, output, and cost totals by agent name."""
        breakdown: dict[str, dict[str, float | int]] = {}
        for record in records:
            agent_name = str(record["agent_name"])
            agent_totals = breakdown.setdefault(
                agent_name,
                {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            )
            agent_totals["input_tokens"] += int(record["input_tokens"])
            agent_totals["output_tokens"] += int(record["output_tokens"])
            agent_totals["cost_usd"] += float(record["cost_usd"])
        return breakdown
