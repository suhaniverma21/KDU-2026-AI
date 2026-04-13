"""Lightweight structured logging helpers for graph workflows."""

from __future__ import annotations

import json
import logging
from typing import Any


LOGGER_NAME = "stock_trader"


def get_logger() -> logging.Logger:
    """Return a configured application logger."""

    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def set_log_level(level: int) -> None:
    """Update the application logger level."""

    get_logger().setLevel(level)


def log_event(event: str, **metadata: Any) -> None:
    """Emit a compact structured log line."""

    payload = {"event": event, **metadata}
    get_logger().info(json.dumps(payload, sort_keys=True, default=str))
