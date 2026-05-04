"""Runs DB and vector agents in true parallel and collects both results."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any

from agents.db_agent import DBAgent
from agents.vector_agent import VectorAgent
from config.settings import get_settings
from monitoring.agent_monitor import AgentMonitor


class Coordinator:
    """Coordinates parallel worker execution without processing worker outputs."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.monitor = AgentMonitor()
        self.db_agent = DBAgent()
        self.vector_agent = VectorAgent()

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Spawn DB and vector agents simultaneously and return coordination metadata."""
        start = time.perf_counter()
        db_result: dict[str, Any] = self._timeout_result("db_agent")
        vector_result: dict[str, Any] = self._timeout_result("vector_agent")

        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as executor:
            db_future = executor.submit(self.db_agent.run, payload)
            vector_future = executor.submit(self.vector_agent.run, payload)
            done, not_done = wait(
                {db_future, vector_future},
                timeout=self.settings.agent_timeout_seconds,
            )

            if db_future in done:
                try:
                    db_result = db_future.result()
                except Exception as exc:
                    db_result = self._error_result(
                        "db_agent",
                        f"Coordinator caught: {exc}",
                    )
            else:
                db_future.cancel()
                db_result = self._timeout_result("db_agent")

            if vector_future in done:
                try:
                    vector_result = vector_future.result()
                except Exception as exc:
                    vector_result = self._error_result(
                        "vector_agent",
                        f"Coordinator caught: {exc}",
                    )
            else:
                vector_future.cancel()
                vector_result = self._timeout_result("vector_agent")

        both_succeeded = (
            db_result.get("status") == "success"
            and vector_result.get("status") == "success"
        )
        any_succeeded = (
            db_result.get("status") == "success"
            or vector_result.get("status") == "success"
        )
        total_time_ms = self._elapsed_ms(start)

        coordinator_result = {
            "db_result": db_result,
            "vector_result": vector_result,
            "both_succeeded": both_succeeded,
            "any_succeeded": any_succeeded,
            "original_query": payload,
            "total_time_ms": total_time_ms,
            "execution_mode": "parallel",
        }

        self._log_coordination_event(coordinator_result, payload)
        return self._handle_cases(coordinator_result)

    def _handle_cases(self, coordinator_result: dict[str, Any]) -> dict[str, Any]:
        """Return the same coordination result after explicit case branching."""
        db_success = coordinator_result["db_result"].get("status") == "success"
        vector_success = coordinator_result["vector_result"].get("status") == "success"

        if db_success and vector_success:
            return coordinator_result
        if db_success and not vector_success:
            return coordinator_result
        if vector_success and not db_success:
            return coordinator_result
        return coordinator_result

    def _log_coordination_event(
        self,
        coordinator_result: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        """Persist one coordinator-level event to the shared AgentMonitor."""
        self.monitor.log_event(
            agent_name="coordinator",
            status=self._coordinator_status(coordinator_result),
            execution_time_ms=int(coordinator_result["total_time_ms"]),
            tokens_used=0,
            payload={
                "query_payload": payload,
                "db_status": coordinator_result["db_result"].get("status"),
                "vector_status": coordinator_result["vector_result"].get("status"),
                "both_succeeded": coordinator_result["both_succeeded"],
                "any_succeeded": coordinator_result["any_succeeded"],
                "original_query": coordinator_result["original_query"],
                "execution_mode": coordinator_result["execution_mode"],
            },
        )

    @staticmethod
    def _coordinator_status(coordinator_result: dict[str, Any]) -> str:
        """Map worker outcomes into a single coordinator logging status."""
        if coordinator_result["both_succeeded"]:
            return "success"
        if coordinator_result["any_succeeded"]:
            return "error"
        return "timeout" if (
            coordinator_result["db_result"].get("status") == "timeout"
            and coordinator_result["vector_result"].get("status") == "timeout"
        ) else "error"

    @staticmethod
    def _timeout_result(agent_name: str) -> dict[str, Any]:
        """Return a timeout-shaped worker result without raising to the caller."""
        return {
            "agent": agent_name,
            "status": "timeout",
            "data": {},
            "execution_time_ms": 0,
            "tokens_used": 0,
            "error_message": f"{agent_name} timed out in coordinator.",
        }

    @staticmethod
    def _error_result(agent_name: str, error_message: str) -> dict[str, Any]:
        """Return an error-shaped worker result without raising to the caller."""
        return {
            "agent": agent_name,
            "status": "error",
            "data": {},
            "execution_time_ms": 0,
            "tokens_used": 0,
            "error_message": error_message,
        }

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        """Convert a perf-counter start time into exact elapsed milliseconds."""
        return int((time.perf_counter() - start) * 1000)
