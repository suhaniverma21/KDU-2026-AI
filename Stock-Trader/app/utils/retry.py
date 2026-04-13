"""Retry helpers for external API calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from app.config import get_settings
from app.utils.logging import log_event

T = TypeVar("T")


def retry_call(
    operation: Callable[[], T],
    *,
    operation_name: str,
    retry_on: tuple[type[BaseException], ...],
) -> T:
    """Retry an external operation with exponential backoff."""

    settings = get_settings()
    max_attempts = max(1, settings.api_retry_attempts)
    base_delay = max(0.0, settings.api_retry_base_delay_seconds)
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except retry_on as exc:
            last_error = exc
            log_event(
                "api_retry_attempt",
                operation_name=operation_name,
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
            )
            if attempt >= max_attempts:
                break
            time.sleep(base_delay * (2 ** (attempt - 1)))

    assert last_error is not None
    raise last_error

