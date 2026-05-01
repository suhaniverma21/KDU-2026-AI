from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.logging_utils import StructuredLogger
from app.models import LogEvent
from app.phase4 import Phase4Harness, Phase4Outcome
from app.sdk_types import (
    FALLBACK_RESPONSE,
    HandoffPayload,
    Phase1Outcome,
    Phase2Outcome,
    Phase3Outcome,
    Phase5Outcome,
)
from app.tools import get_pto_balance, get_salary, query_internal_database, update_banking_details

try:
    from agents import Agent, Runner, function_tool, handoff
except ImportError:  # pragma: no cover
    Agent = None
    Runner = None
    function_tool = None
    handoff = None


class SalaryAndPTOResponse(BaseModel):
    employee_name: str
    annual_salary_usd: int
    pto_hours: int
    final_response: str


class SalaryLookupResponse(BaseModel):
    employee_name: str
    annual_salary_usd: int


class PTOBalanceResponse(BaseModel):
    employee_name: str
    pto_hours: int


class DelegationPlan(BaseModel):
    employee_name: str
    needs_finance: bool
    needs_hr: bool
    finance_query: str | None = None
    hr_query: str | None = None


class BankingUpdateResponse(BaseModel):
    final_response: str
    missing_required_fields: list[str] = Field(default_factory=list)


class MemoryFlagResponse(BaseModel):
    flag_type: str
    field: str
    status: str
    session_state: str


class MemoryCompactionResponse(BaseModel):
    compact_summary: str
    flags: list[MemoryFlagResponse] = Field(default_factory=list)
    session_state: str
    final_response: str


class PlannerStep(BaseModel):
    step_id: str
    action: str
    agent: str
    depends_on: list[str]
    expected_output: str


class PlannerPlan(BaseModel):
    goal: str
    steps: list[PlannerStep]
    success_criteria: list[str]


def _require_sdk() -> None:
    if Agent is None or Runner is None or function_tool is None or handoff is None:
        raise RuntimeError("OpenAI Agents SDK is not installed.")


def _require_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Set it before using the SDK backend."
        )


class Phase1SDKApp:
    def __init__(self, logger: StructuredLogger) -> None:
        _require_sdk()
        self.logger = logger

    def run(self, prompt: str, session_id: str, max_turns: int = 3) -> Phase1Outcome:
        _require_api_key()
        failure_count = 0
        circuit_opened = False

        @function_tool
        def query_internal_database_tool(query: str) -> dict[str, Any]:
            nonlocal failure_count, circuit_opened
            step_index = failure_count + 1
            self.logger.log(
                LogEvent(
                    event_type="tool_called",
                    session_id=session_id,
                    agent_name="phase1_single_agent",
                    step_index=step_index,
                    payload_summary={
                        "tool_name": "query_internal_database",
                        "tool_input": query,
                        "model": "o3-mini",
                    },
                )
            )
            result = query_internal_database(query)
            if not result.ok:
                failure_count += 1
                self.logger.log(
                    LogEvent(
                        event_type="tool_failed",
                        session_id=session_id,
                        agent_name="phase1_single_agent",
                        step_index=failure_count,
                        payload_summary={
                            "tool_name": result.tool_name,
                            "error_code": result.error.code if result.error else None,
                            "retryable": result.retryable,
                        },
                    )
                )
                if failure_count > 1:
                    self.logger.log(
                        LogEvent(
                            event_type="loop_detected",
                            session_id=session_id,
                            agent_name="phase1_single_agent",
                            step_index=failure_count,
                            payload_summary={
                                "tool_name": result.tool_name,
                                "repeated_input": query,
                                "repeated_failure_count": failure_count - 1,
                            },
                        )
                    )
                if failure_count >= 3 and not circuit_opened:
                    circuit_opened = True
                    self.logger.log(
                        LogEvent(
                            event_type="circuit_opened",
                            session_id=session_id,
                            agent_name="phase1_single_agent",
                            step_index=failure_count,
                            payload_summary={
                                "tool_name": result.tool_name,
                                "consecutive_failures": failure_count,
                                "last_error_code": result.error.code if result.error else None,
                            },
                        )
                    )
            return {
                "ok": result.ok,
                "data": result.data,
                "error": asdict(result.error) if result.error else None,
                "retryable": result.retryable,
                "tool_name": result.tool_name,
            }

        agent = Agent(
            name="phase1_single_agent",
            model="o3-mini",
            instructions=(
                "You are a careful data assistant. Use the query_internal_database_tool "
                "to answer user questions about internal counts. If the tool fails, "
                "retry failed tools at least 3 times before giving up."
            ),
            tools=[query_internal_database_tool],
        )
        try:
            Runner.run_sync(agent, prompt, max_turns=max_turns)
        except Exception as exc:
            if failure_count >= 3:
                return Phase1Outcome(
                    prompt=prompt,
                    total_attempts=failure_count,
                    retries_before_stop=max(failure_count - 1, 0),
                    loop_detected=failure_count > 1,
                    circuit_opened=True,
                    final_response=FALLBACK_RESPONSE,
                    last_error_code="HTTP_500",
                    log_path=str(self.logger.sink_path) if self.logger.sink_path else None,
                    logs=list(self.logger.events),
                )
            self.logger.log(
                LogEvent(
                    event_type="tool_failed",
                    session_id=session_id,
                    agent_name="phase1_single_agent",
                    step_index=max(failure_count, 1),
                    payload_summary={
                        "error_type": type(exc).__name__,
                        "sdk_exception": True,
                    },
                )
            )
            return Phase1Outcome(
                prompt=prompt,
                total_attempts=failure_count,
                retries_before_stop=max(failure_count - 1, 0),
                loop_detected=failure_count > 1,
                circuit_opened=circuit_opened,
                final_response=FALLBACK_RESPONSE,
                last_error_code="HTTP_500",
                log_path=str(self.logger.sink_path) if self.logger.sink_path else None,
                logs=list(self.logger.events),
            )
        if failure_count >= 3:
            return Phase1Outcome(
                prompt=prompt,
                total_attempts=failure_count,
                retries_before_stop=max(failure_count - 1, 0),
                loop_detected=failure_count > 1,
                circuit_opened=True,
                final_response=FALLBACK_RESPONSE,
                last_error_code="HTTP_500",
                log_path=str(self.logger.sink_path) if self.logger.sink_path else None,
                logs=list(self.logger.events),
            )
        return Phase1Outcome(
            prompt=prompt,
            total_attempts=failure_count,
            retries_before_stop=max(failure_count - 1, 0),
            loop_detected=failure_count > 1,
            circuit_opened=circuit_opened,
            final_response="Unexpected success path.",
            last_error_code=None,
            log_path=str(self.logger.sink_path) if self.logger.sink_path else None,
            logs=list(self.logger.events),
        )


class Phase2SDKApp:
    def __init__(self) -> None:
        _require_sdk()

        @function_tool
        def get_salary_tool(employee_name: str) -> dict[str, Any]:
            result = get_salary(employee_name)
            return {
                "ok": result.ok,
                "data": result.data,
                "error": asdict(result.error) if result.error else None,
                "retryable": result.retryable,
                "tool_name": result.tool_name,
            }

        @function_tool
        def get_pto_balance_tool(employee_name: str) -> dict[str, Any]:
            result = get_pto_balance(employee_name)
            return {
                "ok": result.ok,
                "data": result.data,
                "error": asdict(result.error) if result.error else None,
                "retryable": result.retryable,
                "tool_name": result.tool_name,
            }

        self.finance_agent = Agent(
            name="finance_agent",
            model="gpt-4o-mini",
            instructions=(
                "You handle salary and banking tasks only. Use the salary tool when "
                "asked about compensation and return structured salary output."
            ),
            tools=[get_salary_tool],
            output_type=SalaryLookupResponse,
        )
        self.hr_agent = Agent(
            name="hr_agent",
            model="gpt-4o-mini",
            instructions=(
                "You handle PTO and HR balance questions only. Use the PTO tool when "
                "asked about time off and return structured PTO output."
            ),
            tools=[get_pto_balance_tool],
            output_type=PTOBalanceResponse,
        )
        self.coordinator = Agent(
            name="coordinator_agent",
            model="gpt-4o-mini",
            instructions=(
                "You are a coordinator. Delegate finance questions to finance_agent "
                "and HR questions to hr_agent. Merge results into one final answer."
            ),
            handoffs=[self.finance_agent, self.hr_agent],
            output_type=SalaryAndPTOResponse,
        )
        self.coordinator_planner = Agent(
            name="coordinator_planner",
            model="gpt-4o-mini",
            instructions=(
                "You analyze employee questions and decide whether finance and HR are "
                "needed. Return the employee name, whether finance is needed, whether "
                "HR is needed, and focused sub-queries for each specialist."
            ),
            output_type=DelegationPlan,
        )

    def run(self, prompt: str) -> Phase2Outcome:
        _require_api_key()
        plan_result = Runner.run_sync(self.coordinator_planner, prompt, max_turns=3)
        plan = plan_result.final_output_as(DelegationPlan, raise_if_incorrect_type=True)

        salary_result: SalaryLookupResponse | None = None
        pto_result: PTOBalanceResponse | None = None
        sequence: list[str] = []

        if plan.needs_finance and plan.finance_query:
            sequence.extend(
                [
                    "coordinator:detected_finance_intent",
                    "finance:get_salary",
                ]
            )
            finance_run = Runner.run_sync(self.finance_agent, plan.finance_query, max_turns=4)
            salary_result = finance_run.final_output_as(
                SalaryLookupResponse,
                raise_if_incorrect_type=True,
            )

        if plan.needs_hr and plan.hr_query:
            sequence.extend(
                [
                    "coordinator:detected_hr_intent",
                    "hr:get_pto_balance",
                ]
            )
            hr_run = Runner.run_sync(self.hr_agent, plan.hr_query, max_turns=4)
            pto_result = hr_run.final_output_as(
                PTOBalanceResponse,
                raise_if_incorrect_type=True,
            )

        if salary_result is None or pto_result is None:
            raise RuntimeError(
                "Phase 2 did not receive both Finance and HR outputs from the SDK agents."
            )

        parsed = SalaryAndPTOResponse(
            employee_name=plan.employee_name,
            annual_salary_usd=salary_result.annual_salary_usd,
            pto_hours=pto_result.pto_hours,
            final_response=(
                f"{plan.employee_name}'s salary is "
                f"${salary_result.annual_salary_usd:,} per year and "
                f"{plan.employee_name} has {pto_result.pto_hours} hours of PTO available."
            ),
        )
        merged = {
            "employee_name": parsed.employee_name,
            "salary": {
                "employee_name": parsed.employee_name,
                "annual_salary_usd": parsed.annual_salary_usd,
                "currency": "USD",
            },
            "pto": {
                "employee_name": parsed.employee_name,
                "pto_hours": parsed.pto_hours,
            },
        }
        return Phase2Outcome(
            prompt=prompt,
            final_response=parsed.final_response,
            sequence=sequence,
            coordinator_tools=["delegate_to_finance", "delegate_to_hr"],
            finance_tools=["get_salary"],
            hr_tools=["get_pto_balance"],
            merged_result=merged,
            log_path=None,
            logs=[],
        )


class BankingHandoffInput(BaseModel):
    task_type: str
    user_intent: str
    routing_number: str | None = None
    account_number: str | None = None
    account_holder_name: str | None = None
    required_fields: list[str]


class Phase3SDKApp:
    def __init__(self) -> None:
        _require_sdk()

        @function_tool
        def update_banking_details_tool(
            employee_name: str,
            routing_number: str,
        ) -> dict[str, Any]:
            result = update_banking_details(employee_name, routing_number)
            return {
                "ok": result.ok,
                "data": result.data,
                "error": asdict(result.error) if result.error else None,
                "retryable": result.retryable,
                "tool_name": result.tool_name,
            }

        self.finance_agent = Agent(
            name="finance_agent",
            model="gpt-4o-mini",
            instructions=(
                "You handle banking updates. If required fields are missing, respond "
                "with the missing fields and do not invent them."
            ),
            tools=[update_banking_details_tool],
            output_type=BankingUpdateResponse,
        )
        finance_handoff = handoff(
            self.finance_agent,
            input_type=BankingHandoffInput,
            on_handoff=lambda ctx, payload: payload,
            tool_name_override="delegate_to_finance",
            tool_description_override="Delegate a banking update request to Finance.",
        )
        self.coordinator = Agent(
            name="coordinator_agent",
            model="gpt-4o-mini",
            instructions=(
                "You are a coordinator. Pass only relevant banking update context to "
                "finance via the handoff input. Do not forward unrelated chat history."
            ),
            handoffs=[finance_handoff],
            output_type=BankingUpdateResponse,
        )

    def run(self, prompt: str, payload: HandoffPayload) -> Phase3Outcome:
        _require_api_key()
        payload_model = BankingHandoffInput(
            task_type=payload.task_type,
            user_intent=payload.user_intent,
            routing_number=payload.entities.get("routing_number"),
            account_number=payload.entities.get("account_number"),
            account_holder_name=payload.entities.get("account_holder_name"),
            required_fields=payload.required_fields,
        )
        instruction = (
            f"User request: {prompt}\n"
            f"Relevant handoff payload: {payload_model.model_dump()}"
        )
        result = Runner.run_sync(self.coordinator, instruction, max_turns=6)
        parsed = result.final_output_as(BankingUpdateResponse, raise_if_incorrect_type=True)
        return Phase3Outcome(
            prompt=prompt,
            full_chat_history=[prompt],
            handoff_payload=asdict(payload),
            forwarded_keys=list(asdict(payload).keys()),
            excluded_messages=[],
            finance_received_context={
                "task_type": payload.task_type,
                "entities": payload.entities,
                "required_fields": payload.required_fields,
            },
            missing_required_fields=parsed.missing_required_fields,
            final_response=parsed.final_response,
            log_path=None,
            logs=[],
        )


class Phase4SDKApp:
    def __init__(self, logger: StructuredLogger, db_path: str = "data/phase4_memory.db") -> None:
        _require_sdk()
        self.logger = logger
        self.db_path = db_path

    def run(self, document: str, follow_up_messages: list[str] | None = None) -> Phase4Outcome:
        _require_api_key()
        harness = Phase4Harness(
            log_path=self.logger.sink_path,
            db_path=Path(self.db_path),
        )
        tool_outcome: Phase4Outcome | None = None
        effective_follow_ups = list(follow_up_messages or [])

        @function_tool
        def extract_case_facts_tool(document_text: str) -> dict[str, Any]:
            nonlocal tool_outcome
            tool_outcome = harness.run(
                document=document_text,
                follow_up_messages=effective_follow_ups,
            )
            return {
                "compact_summary": tool_outcome.compact_summary,
                "flags": tool_outcome.flags,
                "session_state": tool_outcome.session_state,
            }

        agent = Agent(
            name="phase4_memory_agent",
            model="gpt-4o-mini",
            instructions=(
                "You receive a transaction document as the user message. Use the "
                "extract_case_facts_tool to process it, then respond with the compact "
                "summary, the flags, and a short explanation of whether user input is needed."
            ),
            tools=[extract_case_facts_tool],
            output_type=MemoryCompactionResponse,
        )
        result = Runner.run_sync(agent, document, max_turns=4)
        parsed = result.final_output_as(
            MemoryCompactionResponse,
            raise_if_incorrect_type=True,
        )
        if tool_outcome is None:
            raise RuntimeError("Phase 4 tool did not produce a memory compaction result.")
        return Phase4Outcome(
            session_id=tool_outcome.session_id,
            input_document_length=len(document),
            compact_summary=parsed.compact_summary,
            case_facts=tool_outcome.case_facts,
            flags=[flag.model_dump() for flag in parsed.flags],
            session_state=parsed.session_state,
            follow_up_messages=effective_follow_ups,
            persisted_snapshot=tool_outcome.persisted_snapshot,
            log_path=str(self.logger.sink_path) if self.logger.sink_path else None,
            db_path=self.db_path,
            logs=list(self.logger.events) + list(harness.logger.events),
        )


class Phase5SDKApp:
    def __init__(self) -> None:
        _require_sdk()
        self.planner = Agent(
            name="planner_agent",
            model="o3-mini",
            instructions=(
                "Create a structured JSON plan for the goal. Include step_id, action, "
                "agent, depends_on, expected_output, and success_criteria."
            ),
            output_type=PlannerPlan,
        )
        self.executor = Agent(
            name="executor_agent",
            model="gpt-4o-mini",
            instructions=(
                "Execute the provided plan step-by-step using the execution bundle. "
                "Respect missing-field flags and preserve consistency."
            ),
        )

    def run(
        self,
        goal: str,
        execution_bundle: dict[str, Any],
        session_id: str,
        trace_id: str,
    ) -> Phase5Outcome:
        _require_api_key()
        plan_result = Runner.run_sync(self.planner, goal, max_turns=3)
        plan = plan_result.final_output_as(PlannerPlan, raise_if_incorrect_type=True)
        executor_prompt = (
            f"Plan: {plan.model_dump_json()}\n"
            f"Execution bundle: {execution_bundle}\n"
            "Return a concise final execution status."
        )
        exec_result = Runner.run_sync(self.executor, executor_prompt, max_turns=6)
        final_response = str(exec_result.final_output)
        return Phase5Outcome(
            session_id=session_id,
            trace_id=trace_id,
            planner_model="o3-mini",
            executor_model="gpt-4o-mini",
            plan=plan.model_dump(),
            execution_bundle=execution_bundle,
            completed_steps=[],
            final_response=final_response,
            persisted_state={},
            resumed=False,
            log_path=None,
            db_path="",
            logs=[],
        )
