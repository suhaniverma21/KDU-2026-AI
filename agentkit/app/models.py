from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolError:
    code: str
    message: str


@dataclass(slots=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] | None
    error: ToolError | None
    retryable: bool
    tool_name: str


@dataclass(slots=True)
class LogEvent:
    event_type: str
    session_id: str
    agent_name: str
    step_index: int
    payload_summary: dict[str, Any] = field(default_factory=dict)
