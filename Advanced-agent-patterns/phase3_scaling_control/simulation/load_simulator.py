"""Simulates concurrent users hitting the Phase 3 system to test scaling behavior."""

from __future__ import annotations

import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from config.settings import get_settings
from concurrency.concurrency_queue import ConcurrencyQueue
from core.token_pruner import TokenPruner
from monitoring.cost_tracker import CostTracker
from structured_logging.structured_logger import StructuredLogger


PREDEFINED_QUERIES = [
    "I was charged twice last month",
    "My invoice is incorrect",
    "I want to cancel my subscription",
    "What is my current balance?",
    "I need a refund for last week",
]


class LoadSimulator:
    """Runs a multi-user concurrent load simulation across pruning, queueing, logging, and cost tracking."""

    def __init__(self) -> None:
        """Initialize shared runtime helpers and thread-safe result counters."""
        self.settings = get_settings()
        self.token_pruner = TokenPruner()
        self.queue = ConcurrencyQueue()
        self.logger = StructuredLogger()
        self.cost_tracker = CostTracker()
        self._stats_lock = threading.Lock()
        self._successful_requests = 0
        self._rejected_requests = 0
        self._response_times_ms: list[int] = []
        self._active_users = 0
        self._peak_concurrent_users = 0
        self._requests_per_user = 1
        self._last_total_users = 0

    def run(self, num_users: int, requests_per_user: int) -> dict[str, Any]:
        """Spawn concurrent users and return aggregate simulation results."""
        self._requests_per_user = max(1, requests_per_user)
        self._last_total_users = max(1, num_users)
        completed_users = 0

        with ThreadPoolExecutor(
            max_workers=self.settings.max_concurrent_users
        ) as executor:
            futures = []
            for user_id in range(1, self._last_total_users + 1):
                session_id = str(uuid.uuid4())
                futures.append(
                    executor.submit(self.simulate_single_user, user_id, session_id)
                )

            for future in as_completed(futures):
                completed_users += 1
                print(f"Completed: {completed_users}/{self._last_total_users} users")
                try:
                    future.result()
                except Exception:
                    # One simulated user must never crash the entire load test.
                    with self._stats_lock:
                        self._rejected_requests += self._requests_per_user

        return self.get_results()

    def simulate_single_user(self, user_id: int, session_id: str) -> dict[str, Any]:
        """Simulate one user making several requests through pruning, queueing, logging, and cost tracking."""
        self._increment_active_users()
        user_results: list[dict[str, Any]] = []

        try:
            for request_index in range(self._requests_per_user):
                request_id = str(uuid.uuid4())
                query = random.choice(PREDEFINED_QUERIES)
                conversation_history = self._build_fake_history(query)

                start = time.perf_counter()
                pruned_result = self.token_pruner.prune(
                    conversation_history=conversation_history,
                    max_tokens=self.settings.max_tokens_per_handoff,
                )

                execution_result = self.queue.execute(
                    self._simulate_downstream_work,
                    query,
                    request_id=request_id,
                )

                response_time_ms = int((time.perf_counter() - start) * 1000)
                self._record_response_time(response_time_ms)

                status = execution_result.get("status", "rejected")
                if status == "completed":
                    self._mark_success()
                else:
                    self._mark_rejected()

                input_tokens = self.token_pruner.estimate_tokens(
                    pruned_result["pruned_history"]
                )
                output_tokens = random.randint(40, 120)
                self.cost_tracker.record(
                    agent_name="load_simulator",
                    model="gpt-4o-mini",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    session_id=session_id,
                )

                log_payload = {
                    "request_id": request_id,
                    "user_id": user_id,
                    "query": query,
                    "pruning_report": pruned_result["pruning_report"],
                    "queue_result": execution_result,
                    "response_time_ms": response_time_ms,
                }
                self.logger.log(
                    event_type="queue",
                    payload=log_payload,
                    level="INFO" if status == "completed" else "WARNING",
                    session_id=session_id,
                )

                user_results.append(
                    {
                        "request_id": request_id,
                        "status": status,
                        "response_time_ms": response_time_ms,
                    }
                )
                time.sleep(random.uniform(0.1, 0.5))
        finally:
            self._decrement_active_users()

        return {"user_id": user_id, "session_id": session_id, "requests": user_results}

    def get_results(self) -> dict[str, Any]:
        """Return aggregate success, rejection, latency, concurrency, cost, and queue stats."""
        with self._stats_lock:
            avg_response_time_ms = (
                sum(self._response_times_ms) / len(self._response_times_ms)
                if self._response_times_ms
                else 0.0
            )
            successful_requests = self._successful_requests
            rejected_requests = self._rejected_requests
            peak_concurrent_users = self._peak_concurrent_users
            total_users = self._last_total_users

        total_cost = self.cost_tracker.get_total_cost()
        return {
            "total_users": total_users,
            "successful_requests": successful_requests,
            "rejected_requests": rejected_requests,
            "avg_response_time_ms": avg_response_time_ms,
            "peak_concurrent_users": peak_concurrent_users,
            "total_cost_usd": total_cost["total_cost_usd"],
            "queue_stats": self.queue.get_stats(),
        }

    @staticmethod
    def _build_fake_history(query: str) -> list[dict[str, str]]:
        """Build a small synthetic conversation history for pruning under load."""
        return [
            {
                "role": "system",
                "content": "You are a billing support agent. Keep responses short and helpful.",
            },
            {"role": "user", "content": "Hi, I need help with my account."},
            {"role": "assistant", "content": "Sure, what seems to be the problem?"},
            {"role": "user", "content": query},
        ]

    @staticmethod
    def _simulate_downstream_work(query: str) -> dict[str, Any]:
        """Simulate protected downstream processing for one request."""
        time.sleep(random.uniform(0.05, 0.2))
        return {"processed_query": query, "status": "accepted"}

    def _increment_active_users(self) -> None:
        """Increase the active-user count and update the observed concurrency peak."""
        with self._stats_lock:
            self._active_users += 1
            self._peak_concurrent_users = max(
                self._peak_concurrent_users,
                self._active_users,
            )

    def _decrement_active_users(self) -> None:
        """Decrease the active-user count after one simulated user finishes."""
        with self._stats_lock:
            self._active_users = max(0, self._active_users - 1)

    def _record_response_time(self, response_time_ms: int) -> None:
        """Record one response duration for later aggregate reporting."""
        with self._stats_lock:
            self._response_times_ms.append(response_time_ms)

    def _mark_success(self) -> None:
        """Increment the successful request counter in a thread-safe way."""
        with self._stats_lock:
            self._successful_requests += 1

    def _mark_rejected(self) -> None:
        """Increment the rejected request counter in a thread-safe way."""
        with self._stats_lock:
            self._rejected_requests += 1
