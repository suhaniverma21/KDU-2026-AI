# Pseudo-code: Concurrency queue to protect databases from overload
# 1. Initialize a semaphore with `max_concurrent` slots from config.
# 2. Track active request IDs, queued count, processed count, rejected count, and wait times.
# 3. When a request calls `acquire(request_id)`:
#    - record the start wait time
#    - increment queued count
#    - try to acquire one semaphore slot, waiting at most `max_wait_seconds`
#    - if a slot opens in time:
#      - decrement queued count
#      - register request_id as active
#      - record its wait duration
#      - return a structured success payload
#    - if timeout happens:
#      - decrement queued count
#      - increment rejected count
#      - return a structured rejection payload instead of raising
# 4. When a request calls `release(request_id)`:
#    - remove request_id from the active set if present
#    - increment processed count
#    - release one semaphore slot so another waiting request can continue
# 5. When code calls `execute(func, *args, **kwargs)`:
#    - generate or accept a request_id
#    - call `acquire(request_id)`
#    - if rejected, return the rejection immediately
#    - otherwise run the provided function while the slot is held
#    - always call `release(request_id)` in a finally block
#    - return the function result without leaking semaphore state
# 6. `reject_if_full()` checks whether active work is already at capacity and returns a
#    structured retry response immediately instead of waiting.
# 7. `get_stats()` returns a snapshot of queue state:
#    active_requests, queued_requests, max_concurrent, total_processed,
#    total_rejected, and average wait time in milliseconds.

"""Implements a bounded concurrency queue that protects downstream systems from overload."""

from __future__ import annotations

import threading
import time
from contextlib import AbstractContextManager
from typing import Any, Callable

from config.settings import get_settings


class QueueExecutionContext(AbstractContextManager["QueueExecutionContext"]):
    """Wraps acquire and release so queue-managed execution can be used safely in `with` blocks."""

    def __init__(self, queue: "ConcurrencyQueue", request_id: str) -> None:
        """Store the queue reference and request identity for managed execution."""
        self.queue = queue
        self.request_id = request_id
        self.acquire_result: dict[str, Any] | None = None

    def __enter__(self) -> "QueueExecutionContext":
        """Acquire a queue slot and return the context object with the result attached."""
        self.acquire_result = self.queue.acquire(self.request_id)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Release the slot only if acquisition succeeded and the request became active."""
        if self.acquire_result and self.acquire_result.get("status") == "acquired":
            self.queue.release(self.request_id)
        return None


class ConcurrencyQueue:
    """Controls downstream concurrency with semaphore-based admission and queue statistics."""

    def __init__(self) -> None:
        """Initialize concurrency limits and thread-safe counters from environment config."""
        self.settings = get_settings()
        self.max_concurrent = self.settings.max_concurrent_db_requests
        self.max_wait_seconds = self.settings.max_queue_wait_seconds
        self._semaphore = threading.Semaphore(self.max_concurrent)
        self._stats_lock = threading.Lock()
        self._active_request_ids: set[str] = set()
        self._queued_requests = 0
        self._total_processed = 0
        self._total_rejected = 0
        self._total_wait_time_ms = 0.0
        self._wait_samples = 0

    def acquire(self, request_id: str) -> dict[str, Any]:
        """Wait for a slot up to the configured timeout and return a structured status."""
        start_wait = time.perf_counter()
        with self._stats_lock:
            self._queued_requests += 1

        acquired = self._semaphore.acquire(timeout=self.max_wait_seconds)
        wait_time_ms = int((time.perf_counter() - start_wait) * 1000)

        with self._stats_lock:
            self._queued_requests = max(0, self._queued_requests - 1)
            if acquired:
                self._active_request_ids.add(request_id)
                self._total_wait_time_ms += wait_time_ms
                self._wait_samples += 1
                return {
                    "status": "acquired",
                    "request_id": request_id,
                    "wait_time_ms": wait_time_ms,
                }

            self._total_rejected += 1
            return self._build_rejection_response()

    def release(self, request_id: str) -> dict[str, Any]:
        """Release an active slot and free capacity for the next waiting request."""
        with self._stats_lock:
            if request_id in self._active_request_ids:
                self._active_request_ids.remove(request_id)
                self._total_processed += 1
                self._semaphore.release()
                return {"status": "released", "request_id": request_id}
        return {"status": "ignored", "request_id": request_id}

    def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        request_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a function inside queue protection and always clean up slot ownership."""
        with QueueExecutionContext(self, request_id) as context:
            acquire_result = context.acquire_result or {"status": "rejected"}
            if acquire_result.get("status") != "acquired":
                return acquire_result
            result = func(*args, **kwargs)
            return {
                "status": "completed",
                "request_id": request_id,
                "result": result,
            }

    def get_stats(self) -> dict[str, int | float]:
        """Return a thread-safe snapshot of active load, rejection counts, and wait times."""
        with self._stats_lock:
            average_wait_ms = (
                self._total_wait_time_ms / self._wait_samples
                if self._wait_samples
                else 0.0
            )
            return {
                "active_requests": len(self._active_request_ids),
                "queued_requests": self._queued_requests,
                "max_concurrent": self.max_concurrent,
                "total_processed": self._total_processed,
                "total_rejected": self._total_rejected,
                "avg_wait_time_ms": average_wait_ms,
            }

    def reject_if_full(self) -> dict[str, Any]:
        """Return a structured overload response instead of blocking for more capacity."""
        with self._stats_lock:
            if len(self._active_request_ids) >= self.max_concurrent:
                self._total_rejected += 1
                return self._build_rejection_response()
            return {"status": "available"}

    def _build_rejection_response(self) -> dict[str, Any]:
        """Build the standardized rejection payload used for timeouts and pre-checks."""
        return {
            "status": "rejected",
            "reason": "queue_full",
            "retry_after_seconds": self.max_wait_seconds,
        }
