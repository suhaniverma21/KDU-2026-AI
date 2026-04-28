"""Local JSON-backed metadata store for processed files."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import FILESTORE_PATH
from utils import utc_timestamp

VALID_FILE_STATUSES = {"PENDING", "PROCESSING", "READY", "PARTIAL", "FAILED"}


@dataclass
class FileRecord:
    """Persistent file metadata used across ingestion and pipeline stages."""

    file_id: str
    md5: str
    original_name: str
    source_type: str
    mime_type: str
    status: str = "PENDING"
    transcript: str = ""
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    partial_notes: list[str] = field(default_factory=list)
    error_message: str = ""
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)


class FileStore:
    """Simple JSON file registry for local development and small deployments."""

    def __init__(self, store_path: Path | None = None) -> None:
        self.store_path = Path(store_path or FILESTORE_PATH)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self._write_records({})

    def create_file_record(
        self,
        *,
        md5: str,
        original_name: str,
        source_type: str,
        mime_type: str,
        status: str = "PENDING",
    ) -> FileRecord:
        """Create and persist a new file record."""
        self._validate_status(status)
        records = self._read_records()
        file_id = str(uuid4())
        record = FileRecord(
            file_id=file_id,
            md5=md5,
            original_name=original_name,
            source_type=source_type,
            mime_type=mime_type,
            status=status,
        )
        records[file_id] = asdict(record)
        self._write_records(records)
        return record

    def get_file_record(self, file_id: str) -> FileRecord | None:
        """Return a single file record by file ID."""
        record = self._read_records().get(file_id)
        return self._to_record(record) if record else None

    def get_all_file_records(self) -> list[FileRecord]:
        """Return all persisted file records."""
        return [self._to_record(record) for record in self._read_records().values()]

    def get_by_md5(self, md5: str) -> FileRecord | None:
        """Return the first file record matching an MD5 hash."""
        for record in self._read_records().values():
            if record["md5"] == md5:
                return self._to_record(record)
        return None

    def update_file_record(self, file_id: str, **updates: Any) -> FileRecord:
        """Update a file record with arbitrary allowed fields."""
        records = self._read_records()
        if file_id not in records:
            raise KeyError(f"Unknown file_id: {file_id}")

        record = records[file_id]
        if "status" in updates:
            self._validate_status(str(updates["status"]))

        updates["updated_at"] = utc_timestamp()
        record.update(updates)
        records[file_id] = record
        self._write_records(records)
        return self._to_record(record)

    def update_status(
        self,
        file_id: str,
        status: str,
        *,
        error_message: str | None = None,
    ) -> FileRecord:
        """Update processing status and optionally attach an error message."""
        updates: dict[str, Any] = {"status": status}
        if error_message is not None:
            updates["error_message"] = error_message
        return self.update_file_record(file_id, **updates)

    def save_transcript(self, file_id: str, transcript: str) -> FileRecord:
        """Persist transcript text for a file."""
        return self.update_file_record(file_id, transcript=transcript)

    def save_summary(
        self,
        file_id: str,
        *,
        summary: str,
        key_points: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> FileRecord:
        """Persist summary artifacts for a file."""
        return self.update_file_record(
            file_id,
            summary=summary,
            key_points=key_points or [],
            tags=tags or [],
        )

    def mark_summary_pending(self, file_id: str) -> FileRecord:
        """Mark summary generation as pending without changing search readiness."""
        return self.update_file_record(
            file_id,
            summary="",
            error_message="Summary generation is pending due to a previous failure.",
        )

    def add_partial_note(self, file_id: str, note: str) -> FileRecord:
        """Append a partial processing note and mark the file as partial."""
        record = self.get_file_record(file_id)
        if record is None:
            raise KeyError(f"Unknown file_id: {file_id}")

        notes = list(record.partial_notes)
        notes.append(note)
        return self.update_file_record(file_id, partial_notes=notes, status="PARTIAL")

    def _read_records(self) -> dict[str, dict[str, Any]]:
        with self.store_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_records(self, records: dict[str, dict[str, Any]]) -> None:
        with self.store_path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2, sort_keys=True)

    def _validate_status(self, status: str) -> None:
        if status not in VALID_FILE_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Expected one of: {sorted(VALID_FILE_STATUSES)}"
            )

    def _to_record(self, data: dict[str, Any]) -> FileRecord:
        return FileRecord(**data)


def get_file_store(store_path: Path | None = None) -> FileStore:
    """Return a file store instance for local metadata persistence."""
    return FileStore(store_path=store_path)
