"""Minimal environment-file loading helpers for local development."""

from __future__ import annotations

import os
from pathlib import Path


DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv_file(path: str | Path | None = None, *, override: bool = False) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ."""
    env_path = Path(path) if path is not None else DOTENV_PATH
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        normalized_key = key.strip()
        normalized_value = _strip_wrapping_quotes(value.strip())
        if not normalized_key:
            continue

        if override or normalized_key not in os.environ:
            os.environ[normalized_key] = normalized_value


def _strip_wrapping_quotes(value: str) -> str:
    """Remove matching single or double quotes around a .env value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
