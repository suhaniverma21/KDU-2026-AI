"""Local JSONL-backed cost logger for API usage tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from config import COST_LOG_PATH, MODEL_PRICING_USD_PER_1M_TOKENS
from utils import utc_timestamp


@dataclass
class CostLogEntry:
    """Single API usage record with computed cost metadata."""

    timestamp: str
    file_id: str
    operation_type: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_cost_usd: float
    success: bool
    error_message: str = ""


class CostLogger:
    """Append-only JSONL logger with aggregation helpers."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = Path(log_path or COST_LOG_PATH)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)

    def log_api_call(
        self,
        *,
        file_id: str,
        operation_type: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
        success: bool = True,
        error_message: str = "",
    ) -> CostLogEntry:
        """Create, persist, and return a cost log entry."""
        total_cost_usd = self.compute_cost(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        entry = CostLogEntry(
            timestamp=utc_timestamp(),
            file_id=file_id,
            operation_type=operation_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost_usd=total_cost_usd,
            success=success,
            error_message=error_message,
        )
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def compute_cost(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
    ) -> float:
        """Compute cost in USD for a supported model and token counts."""
        pricing = MODEL_PRICING_USD_PER_1M_TOKENS.get(model)
        if pricing is None:
            raise ValueError(f"Unsupported model pricing for '{model}'.")

        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 8)

    def get_entries(self) -> list[CostLogEntry]:
        """Return all recorded API usage entries."""
        entries: list[CostLogEntry] = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entries.append(CostLogEntry(**json.loads(line)))
        return entries

    def get_session_total(self) -> float:
        """Return the total recorded API cost across the current log."""
        return round(sum(entry.total_cost_usd for entry in self.get_entries()), 8)

    def get_totals_by_file(self) -> dict[str, float]:
        """Return total API cost grouped by file ID."""
        totals: dict[str, float] = {}
        for entry in self.get_entries():
            totals.setdefault(entry.file_id, 0.0)
            totals[entry.file_id] += entry.total_cost_usd
        return {file_id: round(total, 8) for file_id, total in totals.items()}

    def get_totals_by_operation(self) -> dict[str, float]:
        """Return total API cost grouped by operation type."""
        totals: dict[str, float] = {}
        for entry in self.get_entries():
            totals.setdefault(entry.operation_type, 0.0)
            totals[entry.operation_type] += entry.total_cost_usd
        return {operation: round(total, 8) for operation, total in totals.items()}

    def get_entries_for_file(self, file_id: str) -> list[CostLogEntry]:
        """Return API usage entries associated with a specific file."""
        return [entry for entry in self.get_entries() if entry.file_id == file_id]

    def to_dicts(self) -> list[dict[str, Any]]:
        """Return all entries as plain dictionaries for UI consumption."""
        return [asdict(entry) for entry in self.get_entries()]


def get_cost_logger(log_path: Path | None = None) -> CostLogger:
    """Return a cost logger instance for local API usage persistence."""
    return CostLogger(log_path=log_path)
