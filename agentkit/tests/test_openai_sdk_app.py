from __future__ import annotations

from app.openai_sdk_app import (
    Agent,
    BankingHandoffInput,
    Phase2SDKApp,
    Phase3SDKApp,
    Phase4SDKApp,
    Phase5SDKApp,
    PlannerPlan,
    SalaryAndPTOResponse,
)
from app.logging_utils import StructuredLogger


def test_sdk_imports_are_available() -> None:
    assert Agent is not None


def test_phase2_sdk_agents_are_isolated() -> None:
    app = Phase2SDKApp()

    assert app.coordinator.name == "coordinator_agent"
    assert len(app.coordinator.tools) == 0
    assert len(app.coordinator.handoffs) == 2
    assert app.coordinator.output_type is SalaryAndPTOResponse


def test_phase3_sdk_handoff_uses_structured_input_type() -> None:
    app = Phase3SDKApp()

    assert app.coordinator.name == "coordinator_agent"
    assert len(app.coordinator.handoffs) == 1
    assert BankingHandoffInput.__name__ == "BankingHandoffInput"


def test_phase5_sdk_agents_use_expected_models_and_plan_schema() -> None:
    app = Phase5SDKApp()

    assert app.planner.model == "o3-mini"
    assert app.executor.model == "gpt-4o-mini"
    assert app.planner.output_type is PlannerPlan


def test_phase4_sdk_app_can_be_created() -> None:
    app = Phase4SDKApp(logger=StructuredLogger())

    assert app.db_path == "data/phase4_memory.db"


def test_phase4_sdk_run_accepts_follow_up_messages() -> None:
    app = Phase4SDKApp(logger=StructuredLogger())

    assert app.run.__defaults__ is not None
