from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from crewai import Crew, Process, Task
from crewai.flow.flow import Flow, listen, router, start
from crewai.flow.persistence import persist

from .crew_builder import build_agents, build_embedder_config, build_memory
from .state import ResearchFlowState


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CrewAI Phase 3 flow.")
    parser.add_argument("--topic", required=True, help="Research topic for the flow.")
    parser.add_argument(
        "--run-mode",
        choices=("sequential",),
        default="sequential",
        help="Crew execution mode used inside each flow step.",
    )
    parser.add_argument(
        "--max-revisions",
        type=int,
        default=2,
        help="Maximum number of research revision loops before the flow stops.",
    )
    return parser.parse_args()


def _extract_json_block(raw_text: str) -> dict[str, Any]:
    start_index = raw_text.find("{")
    end_index = raw_text.rfind("}")
    if start_index == -1 or end_index == -1 or end_index <= start_index:
        raise ValueError("No JSON object found in model output.")
    json_blob = raw_text[start_index : end_index + 1]
    return json.loads(json_blob)


def _run_single_task(task: Task) -> str:
    crew = Crew(
        agents=[task.agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        memory=build_memory(),
        embedder=build_embedder_config(),
    )
    return str(crew.kickoff())


@persist()
class ResearchDepartmentFlow(Flow[ResearchFlowState]):
    """Phase 3 flow with structured state, routing, and loop guardrails."""

    def __init__(self, initial_state: ResearchFlowState | None = None, **kwargs: Any):
        super().__init__(
            state=initial_state or ResearchFlowState(),
            memory=build_memory(),
            **kwargs,
        )

    @start()
    def initialize(self) -> str:
        LOGGER.info("Initializing flow for topic: %s", self.state.topic)
        self.state.route_history.append("initialize")
        return self.state.topic

    @listen(initialize)
    def run_research(self, _: str) -> str:
        agents = build_agents()
        revision_context = ""
        if self.state.fact_check_issues:
            revision_context = (
                "\nAddress these prior fact-check issues explicitly:\n- "
                + "\n- ".join(self.state.fact_check_issues)
            )

        recall_matches = self.recall(self.state.topic, limit=5, depth="shallow")
        recalled_context = "\n".join(f"- {match.record.content}" for match in recall_matches)
        if recalled_context:
            revision_context += f"\nRelevant memory from earlier runs:\n{recalled_context}"

        task = Task(
            description=(
                f'Research the topic "{self.state.topic}" for an internal R&D briefing. '
                "Use available tools to gather current facts, notable trends, concrete examples, "
                "and explicit uncertainty. If a tool fails, record the failure and continue with "
                "the remaining evidence."
                f"{revision_context}"
            ),
            expected_output=(
                "Return a compact research brief with bullet points for key findings, source-backed "
                "observations, open questions, and a short note describing any tool failures."
            ),
            agent=agents["researcher"],
            name="flow_research_task",
        )
        result_text = _run_single_task(task)
        self.state.research_notes.append(result_text)
        self.state.route_history.append("run_research")

        for memory_item in self.extract_memories(result_text):
            self.remember(memory_item, scope=f"/research/{self.state.topic}")

        return result_text

    @listen("run_research")
    @listen("loop_to_research")
    def run_fact_check(self, research_output: str) -> dict[str, Any]:
        agents = build_agents()
        task = Task(
            description=(
                f'Review the following research brief for "{self.state.topic}" and produce a JSON '
                "object only. The object must include: "
                '`status` (one of "approved", "needs_revision", "insufficient_evidence"), '
                '`issues` (an array of short strings), and `summary` (a concise explanation).\n\n'
                f"Research brief:\n{research_output}"
            ),
            expected_output=(
                'JSON only, for example: {"status":"approved","issues":[],"summary":"..."}'
            ),
            agent=agents["fact_checker"],
            name="flow_fact_check_task",
        )
        raw_result = _run_single_task(task)
        parsed = _extract_json_block(raw_result)

        self.state.fact_check_status = str(parsed.get("status", "needs_revision"))
        self.state.fact_check_issues = [str(item) for item in parsed.get("issues", [])]
        self.state.fact_check_summary = str(parsed.get("summary", ""))
        self.state.route_history.append(f"run_fact_check:{self.state.fact_check_status}")
        return parsed

    @router(run_fact_check)
    def decide_next_step(self, _: dict[str, Any]) -> str:
        status = self.state.fact_check_status
        if status == "approved":
            self.state.route_history.append("route:approved")
            return "approved"

        if self.state.revision_count >= self.state.max_revisions:
            self.state.termination_reason = "max_revisions_reached"
            self.state.route_history.append("route:max_revisions_reached")
            return "max_revisions_reached"

        self.state.revision_count += 1
        self.state.route_history.append("route:needs_revision")
        return "needs_revision"

    @listen("needs_revision")
    def request_research_revision(self) -> str:
        LOGGER.info(
            "Fact-check requested revision %s/%s",
            self.state.revision_count,
            self.state.max_revisions,
        )
        return f"Revision requested: {self.state.revision_count}"

    @listen(request_research_revision)
    def loop_to_research(self, _: str) -> str:
        return self.run_research(self.state.topic)

    @listen("approved")
    def write_approved_report(self) -> str:
        return self._write_report(include_warning=False)

    @listen("max_revisions_reached")
    def write_fallback_report(self) -> str:
        warning = (
            "Warning: the report was generated after the revision cap was reached, "
            "so some claims may still need additional validation."
        )
        self.state.termination_reason = "max_revisions_reached"
        return self._write_report(include_warning=True, warning=warning)

    def _write_report(self, include_warning: bool, warning: str = "") -> str:
        agents = build_agents()
        caveat_block = ""
        if include_warning:
            caveat_block = f"\nInclude this warning verbatim in a caveats section:\n{warning}\n"

        task = Task(
            description=(
                f'Produce a final internal summary for "{self.state.topic}" using the latest '
                "research notes and the fact-check summary. Keep the report concise, "
                "decision-friendly, and explicit about confidence levels and missing evidence. "
                "Do not use persuasive language, speculation, emotional framing, or unsupported "
                f"recommendations.\n\nLatest research:\n{self.state.research_notes[-1]}\n\n"
                f"Fact-check summary:\nStatus: {self.state.fact_check_status}\n"
                f"Summary: {self.state.fact_check_summary}\n"
                f"Issues: {json.dumps(self.state.fact_check_issues)}{caveat_block}"
            ),
            expected_output=(
                "A strictly neutral report with an executive summary, validated findings, "
                "caveats, and short next steps based only on confirmed evidence."
            ),
            agent=agents["writer"],
            name="flow_writer_task",
        )
        report = _run_single_task(task)
        self.state.draft_report = report
        self.state.final_report = report
        self.state.route_history.append("write_report")

        for memory_item in self.extract_memories(report):
            self.remember(memory_item, scope=f"/reports/{self.state.topic}")

        if not self.state.termination_reason:
            self.state.termination_reason = "approved"

        return report


def write_flow_artifact(flow: ResearchDepartmentFlow, result: str) -> Path:
    output_dir = BASE_DIR / "runs" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "phase3_flow_result.json"
    payload = {
        "result": result,
        "state": flow.state.model_dump(),
        "state_id": getattr(flow.state, "id", None),
        "flow_guardrail": "revision_count capped by max_revisions",
        "structured_state_advantage": (
            "Structured state provides predictable routing, validation, safer branching, "
            "and easier persistence than raw text parsing."
        ),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main() -> None:
    configure_logging()
    args = parse_args()

    initial_state = ResearchFlowState(
        topic=args.topic,
        run_mode=args.run_mode,
        max_revisions=args.max_revisions,
    )
    flow = ResearchDepartmentFlow(initial_state=initial_state)
    result = flow.kickoff()
    artifact_path = write_flow_artifact(flow, str(result))

    print(f"[flow] artifact={artifact_path}")
    print(f"[flow] termination_reason={flow.state.termination_reason}")
    print(f"[flow] revision_count={flow.state.revision_count}/{flow.state.max_revisions}")
    print(f"[flow] fact_check_status={flow.state.fact_check_status}")
    print(f"[flow] route_history={flow.state.route_history}")


if __name__ == "__main__":
    main()
