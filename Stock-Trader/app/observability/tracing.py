"""LangSmith tracing helpers."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from app.config import get_settings
from app.utils.logging import log_event

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - optional runtime dependency
    traceable = None


def is_langsmith_enabled() -> bool:
    """Return whether LangSmith tracing is enabled in configuration."""

    settings = get_settings()
    return bool(settings.langsmith_tracing and settings.langsmith_api_key)


def configure_langsmith() -> dict[str, str] | None:
    """Configure process environment variables for LangSmith tracing."""

    if not is_langsmith_enabled():
        return None

    settings = get_settings()
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project

    metadata = {
        "project": settings.langsmith_project,
        "environment": settings.environment,
    }
    log_event("langsmith_enabled", **metadata)
    return metadata


def maybe_traceable(*, name: str, run_type: str = "chain") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Return a LangSmith traceable decorator when available, otherwise a no-op."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if traceable is None or not is_langsmith_enabled():
            return func
        return traceable(name=name, run_type=run_type)(func)

    return decorator


def build_trace_metadata(**metadata: Any) -> dict[str, Any]:
    """Filter trace metadata down to non-empty values."""

    return {key: value for key, value in metadata.items() if value is not None}

