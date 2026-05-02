from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchFlowState(BaseModel):
    """Structured state for the CrewAI Phase 3 flow."""

    topic: str = ""
    run_mode: str = "sequential"
    research_notes: list[str] = Field(default_factory=list)
    fact_check_status: str = "pending"
    fact_check_issues: list[str] = Field(default_factory=list)
    fact_check_summary: str = ""
    draft_report: str = ""
    final_report: str = ""
    revision_count: int = 0
    max_revisions: int = 2
    termination_reason: str = ""
    route_history: list[str] = Field(default_factory=list)
