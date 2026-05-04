# Why exact JSON payload storage is critical for debugging and observability
# 1. Reproducing bugs exactly as they happened:
#    If a production issue depends on one missing field, one null value, or one malformed
#    nested object, summaries are not enough. Exact payloads let engineers reconstruct the
#    precise state that caused the bug instead of guessing.
# 2. Replaying failed requests without guessing:
#    When requests fail under load or during agent handoff, replay only works if the stored
#    event contains the exact structured input and output snapshots that moved through the
#    system. Approximate reconstructions can hide the real failure condition.
# 3. Auditing what each agent sent and received:
#    Multi-agent systems often fail at boundaries. Exact JSON logs make it possible to see
#    what one component actually emitted and what the next component actually consumed,
#    which is essential for compliance, incident review, and root-cause analysis.
# 4. Tracking down silent data corruption between agents:
#    Some of the hardest bugs are not crashes but subtle mutations: dropped keys, renamed
#    fields, wrong casing, partial truncation, or stale memory snapshots. Exact event logs
#    provide the before-and-after evidence needed to find where corruption entered.

"""Provides structured JSON logging and replay utilities for the standalone Phase 3 project."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from config.settings import get_settings


LogLevel = Literal["INFO", "WARNING", "ERROR"]
EventType = Literal["agent_call", "error", "routing", "pruning", "queue", "cost"]


class StructuredLogger:
    """Stores exact masked JSON events and supports replay by time, type, and session."""

    _instance: "StructuredLogger | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "StructuredLogger":
        """Return the shared singleton logger instance for the current process."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the logger lazily so the whole Phase 3 system shares one backend."""
        if getattr(self, "_initialized", False):
            return
        self.settings = get_settings()
        self._lock = threading.Lock()
        self._log_file_path = Path(self.settings.log_file_path)
        self._log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def log(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        level: LogLevel,
        session_id: str,
    ) -> dict[str, Any]:
        """Write one structured JSON event containing exact masked input and output snapshots."""
        request_id = self._extract_or_generate_request_id(payload)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "request_id": request_id,
            "event_type": event_type,
            "level": level,
            "payload": self._mask_value(payload),
        }
        with self._lock:
            self._rotate_if_needed()
            with self._log_file_path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry, ensure_ascii=True) + "\n")
        return entry

    def replay_last_n(self, n: int) -> list[dict[str, Any]]:
        """Return the most recent `n` structured log entries."""
        if n <= 0:
            return []
        entries = self._read_entries()
        return entries[-n:]

    def replay_by_timerange(
        self,
        start_iso: str,
        end_iso: str,
    ) -> list[dict[str, Any]]:
        """Return all log entries whose timestamps fall within the given ISO range."""
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
        return [
            entry
            for entry in self._read_entries()
            if start_dt <= datetime.fromisoformat(entry["timestamp"]) <= end_dt
        ]

    def replay_by_event_type(self, event_type: EventType) -> list[dict[str, Any]]:
        """Return all structured log entries matching one event type."""
        return [
            entry for entry in self._read_entries() if entry.get("event_type") == event_type
        ]

    def replay_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """Return every structured log entry associated with a single session."""
        return [
            entry for entry in self._read_entries() if entry.get("session_id") == session_id
        ]

    def export_session(self, session_id: str, output_path: str) -> dict[str, Any]:
        """Export all session log entries into a dedicated JSONL file for debugging or sharing."""
        session_entries = self.replay_by_session(session_id)
        export_path = Path(output_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with export_path.open("w", encoding="utf-8") as export_file:
            for entry in session_entries:
                export_file.write(json.dumps(entry, ensure_ascii=True) + "\n")
        return {
            "status": "exported",
            "session_id": session_id,
            "output_path": str(export_path),
            "entry_count": len(session_entries),
        }

    def _read_entries(self) -> list[dict[str, Any]]:
        """Read and parse every structured log line from the current Phase 3 log file."""
        with self._lock:
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
        """Archive the active JSONL file when it exceeds the configured max size."""
        if not self._log_file_path.exists():
            return
        max_size_bytes = self.settings.max_log_file_size_mb * 1024 * 1024
        if self._log_file_path.stat().st_size <= max_size_bytes:
            return
        archive_name = (
            f"{self._log_file_path.stem}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            f"{self._log_file_path.suffix}"
        )
        archive_path = self._log_file_path.with_name(archive_name)
        self._log_file_path.replace(archive_path)

    @staticmethod
    def _extract_or_generate_request_id(payload: dict[str, Any]) -> str:
        """Reuse a request ID from the payload when available or generate a new UUID."""
        request_id = payload.get("request_id")
        if isinstance(request_id, str) and request_id.strip():
            return request_id
        return str(uuid.uuid4())

    def _mask_value(self, value: Any) -> Any:
        """Recursively mask sensitive values before exact payloads are written to disk."""
        if isinstance(value, dict):
            return {str(key): self._mask_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._mask_value(item) for item in value]
        if isinstance(value, str):
            masked = self._mask_api_keys(value)
            return self._mask_account_numbers(masked)
        return value

    @staticmethod
    def _mask_api_keys(value: str) -> str:
        """Mask API-key-like strings before structured payloads are persisted."""
        return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***masked***", value)

    @staticmethod
    def _mask_account_numbers(value: str) -> str:
        """Mask account-number-like values while keeping them partially recognizable."""
        return re.sub(r"\b([A-Z]{2,5}-)?(\d{2})\d{3,}(\d{2})\b", r"\1\2****\3", value)
