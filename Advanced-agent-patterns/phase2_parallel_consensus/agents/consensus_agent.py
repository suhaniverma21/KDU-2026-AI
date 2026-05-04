"""Combines coordinator outputs into one final customer-facing response."""

from __future__ import annotations

import time
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from agents.base import BaseAgent
from config.settings import get_settings
from monitoring.agent_monitor import AgentMonitor


CONSENSUS_SYSTEM_PROMPT = (
    "Merge DB facts and knowledge-search results into one concise answer. Prefer DB "
    "facts, mention uncertainty honestly, and do not invent missing details."
)


class WorkerResult(BaseModel):
    """Defines the worker result shape consumed by the consensus agent."""

    agent: str
    status: Literal["success", "error", "timeout"]
    data: dict[str, Any]
    execution_time_ms: int
    tokens_used: int
    error_message: str | None = None


class CoordinatorResultPayload(BaseModel):
    """Defines the coordinator output shape expected by the consensus agent."""

    db_result: WorkerResult
    vector_result: WorkerResult
    both_succeeded: bool
    any_succeeded: bool
    original_query: dict[str, Any]


class ConsensusAgentResponse(BaseModel):
    """Defines the final structured response returned by the consensus agent."""

    final_response: str = Field(min_length=1)
    sources_used: list[str]
    confidence: Literal["high", "partial", "fallback"]
    tokens_used: int = Field(ge=0)
    execution_time_ms: int = Field(ge=0)


class ConsensusAgent(BaseAgent):
    """Produces one final response from coordinator output and worker results."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)
        self.monitor = AgentMonitor()

    def run(self, coordinator_result: dict[str, Any]) -> dict[str, Any]:
        """Return one final structured response without raising to the caller."""
        start = time.perf_counter()
        tokens_used = 0

        try:
            payload = CoordinatorResultPayload.model_validate(coordinator_result)
        except ValidationError:
            response = self._fallback(start)
            self._log_response(response, coordinator_result)
            return response.model_dump()

        db_success = payload.db_result.status == "success"
        vector_success = payload.vector_result.status == "success"

        try:
            if db_success and vector_success:
                response, tokens_used = self._merge_both(payload)
            elif db_success and not vector_success:
                response, tokens_used = self._use_db_only(payload)
            elif vector_success and not db_success:
                response, tokens_used = self._use_vector_only(payload)
            else:
                response = self._fallback(start)
                self._log_response(response, coordinator_result)
                return response.model_dump()
        except Exception:
            response = self._fallback(start)
            self._log_response(response, coordinator_result)
            return response.model_dump()

        final_response = ConsensusAgentResponse(
            final_response=response["final_response"],
            sources_used=response["sources_used"],
            confidence=response["confidence"],
            tokens_used=tokens_used,
            execution_time_ms=self._elapsed_ms(start),
        )
        self._log_response(final_response, coordinator_result)
        return final_response.model_dump()

    def _merge_both(
        self,
        payload: CoordinatorResultPayload,
    ) -> tuple[dict[str, Any], int]:
        """Generate a merged answer when both worker agents succeeded."""
        return self._generate_response(
            user_context=payload.original_query,
            db_data=payload.db_result.data,
            vector_data=payload.vector_result.data,
            sources_used=["db_agent", "vector_agent"],
            confidence="high",
        )

    def _use_db_only(
        self,
        payload: CoordinatorResultPayload,
    ) -> tuple[dict[str, Any], int]:
        """Generate a response when only the DB agent succeeded."""
        return self._generate_response(
            user_context=payload.original_query,
            db_data=payload.db_result.data,
            vector_data={"note": "Vector results unavailable."},
            sources_used=["db_agent"],
            confidence="partial",
        )

    def _use_vector_only(
        self,
        payload: CoordinatorResultPayload,
    ) -> tuple[dict[str, Any], int]:
        """Generate a response when only the vector agent succeeded."""
        return self._generate_response(
            user_context=payload.original_query,
            db_data={"note": "DB results unavailable."},
            vector_data=payload.vector_result.data,
            sources_used=["vector_agent"],
            confidence="partial",
        )

    def _fallback(self, start: float) -> ConsensusAgentResponse:
        """Return the configured fallback response when no worker data is usable."""
        return ConsensusAgentResponse(
            final_response=self.settings.fallback_response,
            sources_used=[],
            confidence="fallback",
            tokens_used=0,
            execution_time_ms=self._elapsed_ms(start),
        )

    def _generate_response(
        self,
        user_context: dict[str, Any],
        db_data: dict[str, Any],
        vector_data: dict[str, Any],
        sources_used: list[str],
        confidence: Literal["high", "partial"],
    ) -> tuple[dict[str, Any], int]:
        """Use the model to turn structured worker outputs into one final response."""
        completion = self.client.chat.completions.create(
            model="gpt-4o-mini",
            timeout=self.settings.agent_timeout_seconds,
            messages=[
                {"role": "system", "content": CONSENSUS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"original_query: {user_context}\n"
                        f"db_result: {db_data}\n"
                        f"vector_result: {vector_data}\n"
                        "Write one concise final response for the user."
                    ),
                },
            ],
        )
        text = (completion.choices[0].message.content or "").strip()
        tokens_used = getattr(completion.usage, "total_tokens", 0) or 0
        return {
            "final_response": text or self.settings.fallback_response,
            "sources_used": sources_used,
            "confidence": confidence,
        }, int(tokens_used)

    def _log_response(
        self,
        response: ConsensusAgentResponse,
        coordinator_result: dict[str, Any],
    ) -> None:
        """Persist the final consensus execution through the shared monitor."""
        self.monitor.log_event(
            agent_name="consensus_agent",
            status="success" if response.confidence != "fallback" else "error",
            execution_time_ms=response.execution_time_ms,
            tokens_used=response.tokens_used,
            payload={
                "coordinator_result": coordinator_result,
                "final_response": response.final_response,
                "sources_used": response.sources_used,
                "confidence": response.confidence,
            },
        )

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        """Convert a perf-counter start time into exact elapsed milliseconds."""
        return int((time.perf_counter() - start) * 1000)
