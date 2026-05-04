"""Provides a singleton agent monitor for structured event logging and replay."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import get_settings


class AgentMonitor:
    """Stores structured agent events in JSONL and exposes summary and replay helpers."""

    _instance: AgentMonitor | None = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> AgentMonitor:
        """Return the shared singleton monitor instance for the current process."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the monitor lazily so all agents share one logging backend."""
        if getattr(self, "_initialized", False):
            return
        self._settings = get_settings()
        self._log_lock = threading.Lock()
        self._log_file_path = Path(self._settings.log_file_path)
        self._log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def log_event(
        self,
        agent_name: str,
        status: str,
        execution_time_ms: int,
        tokens_used: int,
        payload: dict[str, Any],
    ) -> None:
        """Write one masked JSONL event for an agent execution in a thread-safe way."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent_name,
            "status": status,
            "execution_time_ms": execution_time_ms,
            "tokens_used": tokens_used,
            "payload_snapshot": self._mask_payload(payload),
        }
        with self._log_lock:
            self._rotate_if_needed()
            with self._log_file_path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry, ensure_ascii=True) + "\n")

    def get_summary(self) -> dict[str, dict[str, float | int]]:
        """Return per-agent totals, success rate, average latency, and token usage."""
        summary: dict[str, dict[str, float | int]] = {}
        for entry in self._read_entries():
            agent_name = str(entry["agent"])
            stats = summary.setdefault(
                agent_name,
                {
                    "total_calls": 0,
                    "success_count": 0,
                    "total_execution_time_ms": 0,
                    "total_tokens_used": 0,
                },
            )
            stats["total_calls"] += 1
            stats["total_execution_time_ms"] += int(entry["execution_time_ms"])
            stats["total_tokens_used"] += int(entry["tokens_used"])
            if entry["status"] == "success":
                stats["success_count"] += 1

        formatted_summary: dict[str, dict[str, float | int]] = {}
        for agent_name, stats in summary.items():
            total_calls = int(stats["total_calls"])
            success_count = int(stats["success_count"])
            total_execution_time_ms = int(stats["total_execution_time_ms"])
            avg_execution_time_ms = (
                total_execution_time_ms / total_calls if total_calls else 0.0
            )
            formatted_summary[agent_name] = {
                "total_calls": total_calls,
                "success_rate": success_count / total_calls if total_calls else 0.0,
                "avg_execution_time_ms": avg_execution_time_ms,
                "total_tokens_used": int(stats["total_tokens_used"]),
            }

        return formatted_summary

    def replay_last_n(self, n: int) -> list[dict[str, Any]]:
        """Return the last `n` log entries from the structured JSONL file."""
        if n <= 0:
            return []
        entries = self._read_entries()
        return entries[-n:]

    def _read_entries(self) -> list[dict[str, Any]]:
        """Read and parse all structured log entries from the current JSONL file."""
        with self._log_lock:
            if not self._log_file_path.exists():
                return []
            entries: list[dict[str, Any]] = []
            with self._log_file_path.open("r", encoding="utf-8") as log_file:
                for line in log_file:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    entries.append(json.loads(stripped))
            return entries

    def _rotate_if_needed(self) -> None:
        """Archive the current log file if it exceeds the configured max size."""
        if not self._log_file_path.exists():
            return
        max_size_bytes = self._settings.max_log_file_size_mb * 1024 * 1024
        if self._log_file_path.stat().st_size <= max_size_bytes:
            return
        archive_name = (
            f"{self._log_file_path.stem}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            f"{self._log_file_path.suffix}"
        )
        archive_path = self._log_file_path.with_name(archive_name)
        self._log_file_path.replace(archive_path)

    def _mask_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a recursively masked copy of a payload safe for persistent logs."""
        return self._mask_value(payload)

    def _mask_value(self, value: Any) -> Any:
        """Mask account numbers and API keys within nested payload values."""
        if isinstance(value, dict):
            return {
                str(key): self._mask_value(nested_value)
                for key, nested_value in value.items()
            }
        if isinstance(value, list):
            return [self._mask_value(item) for item in value]
        if isinstance(value, str):
            masked = self._mask_api_keys(value)
            return self._mask_account_numbers(masked)
        return value

    @staticmethod
    def _mask_api_keys(value: str) -> str:
        """Mask API key-like substrings before they are written to disk."""
        return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***masked***", value)

    @staticmethod
    def _mask_account_numbers(value: str) -> str:
        """Mask long numeric account identifiers while preserving readability."""
        return re.sub(r"\b(\d{2})\d{4,}(\d{2})\b", r"\1****\2", value)
