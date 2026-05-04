"""Simulates a database lookup worker for billing and account information."""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from openai import APITimeoutError, OpenAI
from pydantic import BaseModel, Field, ValidationError
from tenacity import RetryError, Retrying, stop_after_attempt, wait_exponential

from agents.base import BaseAgent
from config.settings import get_settings
from monitoring.agent_monitor import AgentMonitor


DB_AGENT_SYSTEM_PROMPT = (
    "Simulate a billing account database lookup. Return JSON with account_balance, "
    "last_payment_date, and invoice_history using the provided query context only."
)


class DBQueryEntities(BaseModel):
    """Defines the standardized entity fields accepted by the DB agent."""

    account_id: str | None = None
    issue: str | None = None


class DBQueryPayload(BaseModel):
    """Defines the standardized query payload for the DB agent."""

    intent: Literal["billing"]
    entities: DBQueryEntities
    query: str = Field(min_length=1)


class DBAgentResult(BaseModel):
    """Defines the strictly typed output returned by the DB agent."""

    agent: Literal["db_agent"]
    status: Literal["success", "error", "timeout"]
    data: dict[str, Any]
    execution_time_ms: int
    tokens_used: int
    error_message: str | None


class DBAgent(BaseAgent):
    """Uses `gpt-4o-mini` to simulate a structured billing database lookup."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)
        self.monitor = AgentMonitor()

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the DB agent safely and never raise exceptions to the caller."""
        start = time.perf_counter()
        tokens_used = 0
        result: DBAgentResult

        try:
            query_payload = DBQueryPayload.model_validate(payload)
        except ValidationError as exc:
            result = DBAgentResult(
                agent="db_agent",
                status="error",
                data={},
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message=f"Invalid DB query payload: {exc}",
            )
            self._log_result(result, payload)
            return result.model_dump()

        try:
            response_data, tokens_used = self._simulate_lookup(query_payload)
            result = DBAgentResult(
                agent="db_agent",
                status="success",
                data=response_data,
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message=None,
            )
        except APITimeoutError:
            result = DBAgentResult(
                agent="db_agent",
                status="timeout",
                data={},
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message="DB agent request timed out.",
            )
        except RetryError as exc:
            final_exception = exc.last_attempt.exception()
            if isinstance(final_exception, APITimeoutError):
                result = DBAgentResult(
                    agent="db_agent",
                    status="timeout",
                    data={},
                    execution_time_ms=self._elapsed_ms(start),
                    tokens_used=tokens_used,
                    error_message="DB agent request timed out after retries.",
                )
            else:
                result = DBAgentResult(
                    agent="db_agent",
                    status="error",
                    data={},
                    execution_time_ms=self._elapsed_ms(start),
                    tokens_used=tokens_used,
                    error_message=f"DB agent failed after retries: {final_exception}",
                )
        except Exception as exc:
            result = DBAgentResult(
                agent="db_agent",
                status="error",
                data={},
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message=f"DB agent failed: {exc}",
            )

        self._log_result(result, query_payload.model_dump())
        return result.model_dump()

    def _simulate_lookup(self, payload: DBQueryPayload) -> tuple[dict[str, Any], int]:
        """Run the LLM-backed simulated lookup with retry and timeout behavior."""
        retryer = Retrying(
            stop=stop_after_attempt(max(1, self.settings.max_retries)),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            reraise=False,
        )
        for attempt in retryer:
            with attempt:
                return self._completion_once(payload)
        raise RetryError(attempt)  # pragma: no cover

    def _completion_once(self, payload: DBQueryPayload) -> tuple[dict[str, Any], int]:
        """Call Chat Completions and parse a structured billing data response."""
        completion = self.client.chat.completions.create(
            model="gpt-4o-mini",
            timeout=self.settings.agent_timeout_seconds,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": DB_AGENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Return JSON with keys account_balance, last_payment_date, "
                        "and invoice_history.\n"
                        f"intent: {payload.intent}\n"
                        f"account_id: {payload.entities.account_id}\n"
                        f"issue: {payload.entities.issue}\n"
                        f"query: {payload.query}"
                    ),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        parsed = json.loads(content)
        tokens_used = getattr(completion.usage, "total_tokens", 0) or 0
        return parsed, int(tokens_used)

    def _log_result(self, result: DBAgentResult, payload: dict[str, Any]) -> None:
        """Persist a structured execution record via the shared AgentMonitor."""
        self.monitor.log_event(
            agent_name=result.agent,
            status=result.status,
            execution_time_ms=result.execution_time_ms,
            tokens_used=result.tokens_used,
            payload={
                "query_payload": payload,
                "result_preview": result.data,
                "error_message": result.error_message,
            },
        )

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        """Convert a perf-counter start time into exact elapsed milliseconds."""
        return int((time.perf_counter() - start) * 1000)
