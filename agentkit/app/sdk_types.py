from __future__ import annotations

from dataclasses import dataclass, field


FALLBACK_RESPONSE = (
    "I’m unable to access the internal user database right now. "
    "Please try again later or contact support."
)


@dataclass(slots=True)
class HandoffPayload:
    session_id: str
    user_id: str
    source_agent: str
    target_agent: str
    task_type: str
    user_intent: str
    entities: dict[str, str | None]
    required_fields: list[str]


@dataclass(slots=True)
class Phase1Outcome:
    prompt: str
    total_attempts: int
    retries_before_stop: int
    loop_detected: bool
    circuit_opened: bool
    final_response: str
    last_error_code: str | None
    log_path: str | None
    logs: list[dict[str, object]] = field(default_factory=list)


@dataclass(slots=True)
class Phase2Outcome:
    prompt: str
    final_response: str
    sequence: list[str]
    coordinator_tools: list[str]
    finance_tools: list[str]
    hr_tools: list[str]
    merged_result: dict[str, object]
    log_path: str | None
    logs: list[dict[str, object]] = field(default_factory=list)


@dataclass(slots=True)
class Phase3Outcome:
    prompt: str
    full_chat_history: list[str]
    handoff_payload: dict[str, object]
    forwarded_keys: list[str]
    excluded_messages: list[str]
    finance_received_context: dict[str, object]
    missing_required_fields: list[str]
    final_response: str
    log_path: str | None
    logs: list[dict[str, object]] = field(default_factory=list)


@dataclass(slots=True)
class Phase5Outcome:
    session_id: str
    trace_id: str
    planner_model: str
    executor_model: str
    plan: dict[str, object]
    execution_bundle: dict[str, object]
    completed_steps: list[str]
    final_response: str
    persisted_state: dict[str, object]
    resumed: bool
    log_path: str | None
    db_path: str
    logs: list[dict[str, object]] = field(default_factory=list)
