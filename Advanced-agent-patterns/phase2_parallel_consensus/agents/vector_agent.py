"""Simulates a semantic retrieval worker for billing knowledge search."""

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


VECTOR_AGENT_SYSTEM_PROMPT = (
    "Simulate semantic billing knowledge search. Return JSON with relevant_chunks "
    "and confidence_score using only the provided query context."
)


class VectorQueryEntities(BaseModel):
    """Defines the standardized entity fields accepted by the vector agent."""

    account_id: str | None = None
    issue: str | None = None


class VectorQueryPayload(BaseModel):
    """Defines the standardized query payload for the vector agent."""

    intent: Literal["billing"]
    entities: VectorQueryEntities
    query: str = Field(min_length=1)


class VectorAgentData(BaseModel):
    """Defines the structured semantic retrieval payload returned on success."""

    relevant_chunks: list[dict[str, Any]]
    confidence_score: float = Field(ge=0.0, le=1.0)


class VectorAgentResult(BaseModel):
    """Defines the strictly typed output returned by the vector agent."""

    agent: Literal["vector_agent"]
    status: Literal["success", "error", "timeout"]
    data: dict[str, Any]
    execution_time_ms: int
    tokens_used: int
    error_message: str | None


class VectorAgent(BaseAgent):
    """Uses `gpt-4o-mini` to simulate semantic billing knowledge retrieval."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)
        self.monitor = AgentMonitor()

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the vector agent safely and never raise exceptions to the caller."""
        start = time.perf_counter()
        tokens_used = 0
        result: VectorAgentResult

        try:
            query_payload = VectorQueryPayload.model_validate(payload)
        except ValidationError as exc:
            result = VectorAgentResult(
                agent="vector_agent",
                status="error",
                data={},
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message=f"Invalid vector query payload: {exc}",
            )
            self._log_result(result, payload)
            return result.model_dump()

        try:
            response_data, tokens_used = self._simulate_search(query_payload)
            result = VectorAgentResult(
                agent="vector_agent",
                status="success",
                data=response_data,
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message=None,
            )
        except APITimeoutError:
            result = VectorAgentResult(
                agent="vector_agent",
                status="timeout",
                data={},
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message="Vector agent request timed out.",
            )
        except RetryError as exc:
            final_exception = exc.last_attempt.exception()
            if isinstance(final_exception, APITimeoutError):
                result = VectorAgentResult(
                    agent="vector_agent",
                    status="timeout",
                    data={},
                    execution_time_ms=self._elapsed_ms(start),
                    tokens_used=tokens_used,
                    error_message="Vector agent request timed out after retries.",
                )
            else:
                result = VectorAgentResult(
                    agent="vector_agent",
                    status="error",
                    data={},
                    execution_time_ms=self._elapsed_ms(start),
                    tokens_used=tokens_used,
                    error_message=f"Vector agent failed after retries: {final_exception}",
                )
        except Exception as exc:
            result = VectorAgentResult(
                agent="vector_agent",
                status="error",
                data={},
                execution_time_ms=self._elapsed_ms(start),
                tokens_used=tokens_used,
                error_message=f"Vector agent failed: {exc}",
            )

        self._log_result(result, query_payload.model_dump())
        return result.model_dump()

    def _simulate_search(self, payload: VectorQueryPayload) -> tuple[dict[str, Any], int]:
        """Run the LLM-backed simulated semantic search with retry and timeout behavior."""
        retryer = Retrying(
            stop=stop_after_attempt(max(1, self.settings.max_retries)),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            reraise=False,
        )
        for attempt in retryer:
            with attempt:
                return self._completion_once(payload)
        raise RetryError(attempt)  # pragma: no cover

    def _completion_once(self, payload: VectorQueryPayload) -> tuple[dict[str, Any], int]:
        """Call Chat Completions and parse a structured semantic retrieval response."""
        completion = self.client.chat.completions.create(
            model="gpt-4o-mini",
            timeout=self.settings.agent_timeout_seconds,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": VECTOR_AGENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Return JSON with keys relevant_chunks and confidence_score.\n"
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
        typed_data = VectorAgentData.model_validate(parsed)
        filtered_data = self._apply_confidence_threshold(typed_data)
        tokens_used = getattr(completion.usage, "total_tokens", 0) or 0
        return filtered_data.model_dump(), int(tokens_used)

    def _apply_confidence_threshold(self, data: VectorAgentData) -> VectorAgentData:
        """Filter low-confidence semantic results using the configured threshold."""
        if data.confidence_score >= self.settings.confidence_threshold:
            return data
        return VectorAgentData(
            relevant_chunks=[],
            confidence_score=data.confidence_score,
        )

    def _log_result(self, result: VectorAgentResult, payload: dict[str, Any]) -> None:
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
