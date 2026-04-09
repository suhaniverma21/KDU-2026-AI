"""Structured logging configuration for the application."""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from typing import Any

from app.core.config import Settings, get_settings
from app.middleware.request_context import get_request_id


class JsonFormatter(logging.Formatter):
    """Render log records as JSON for machine-readable output."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert a log record into a JSON string."""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }

        for field_name in ("method", "path", "status_code", "duration_ms"):
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value

        return json.dumps(payload)


class TextFormatter(logging.Formatter):
    """Developer-friendly formatter for local and test environments."""

    def format(self, record: logging.LogRecord) -> str:
        """Render a concise human-readable log line."""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        request_id = getattr(record, "request_id", None) or get_request_id() or "-"
        method = getattr(record, "method", None)
        path = getattr(record, "path", None)
        status_code = getattr(record, "status_code", None)
        duration_ms = getattr(record, "duration_ms", None)

        parts = [f"{timestamp}", record.levelname, f"[request_id={request_id}]"]
        if method and path:
            parts.append(f"{method} {path}")
        if status_code is not None:
            parts.append(f"status={status_code}")
        if duration_ms is not None:
            parts.append(f"duration_ms={duration_ms}")
        parts.append(record.getMessage())
        return " | ".join(parts)


def resolve_log_level(settings: Settings) -> int:
    """Resolve the effective logging level from settings."""
    if settings.environment == "test" and settings.log_level == "INFO":
        return logging.WARNING
    return getattr(logging, settings.log_level, logging.INFO)


def resolve_log_formatter(settings: Settings) -> logging.Formatter:
    """Choose the correct formatter for the current environment."""
    if settings.log_format == "json":
        return JsonFormatter()
    if settings.log_format == "text":
        return TextFormatter()
    if settings.environment == "production":
        return JsonFormatter()
    return TextFormatter()


def configure_logging(settings: Settings | None = None) -> None:
    """Configure the application loggers once at startup."""
    active_settings = settings or get_settings()
    level = resolve_log_level(active_settings)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    app_logger.handlers.clear()
    app_handler = logging.StreamHandler()
    app_handler.setFormatter(resolve_log_formatter(active_settings))
    app_logger.addHandler(app_handler)
    app_logger.propagate = False

    for logger_name in ("app.request", "app.error"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(resolve_log_formatter(active_settings))
        logger.addHandler(handler)
        logger.propagate = False
