from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from crewai import Agent, Crew, Memory, Process, Task
from crewai_tools import SerperDevTool

from .tools.flaky_research_tool import FlakyResearchTool


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"


@dataclass
class RunArtifacts:
    """Structured result wrapper for one crew execution."""

    mode: str
    topic: str
    day_label: str
    status: str
    output_text: str
    output_path: Path
    memory_enabled: bool
    memory_storage_path: Path | None
    memory_artifacts: list[str]
    error_message: str | None = None


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}, received {type(data).__name__}")
    return data


def resolve_model_name(env_var: str, default: str) -> str:
    value = os.getenv(env_var) or os.getenv("MODEL_NAME") or default
    return value.strip()


def build_llm_model(model_name: str) -> str:
    """Return the model name string expected by CrewAI/LiteLLM."""
    return model_name


def resolve_memory_storage_path() -> Path:
    configured_root = os.getenv("CREWAI_STORAGE_DIR")
    if configured_root:
        return Path(configured_root).expanduser().resolve() / "memory"
    return (Path.cwd() / ".crewai" / "memory").resolve()


def build_embedder_config() -> dict[str, Any]:
    return {
        "provider": "openai",
        "config": {
            "model_name": os.getenv("EMBEDDER_MODEL_NAME", "text-embedding-3-small"),
        },
    }


def build_memory() -> Memory:
    storage_path = resolve_memory_storage_path()
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    memory_model = build_llm_model(resolve_model_name("MEMORY_MODEL_NAME", "gpt-4o-mini"))
    return Memory(
        storage=str(storage_path),
        llm=memory_model,
        embedder=build_embedder_config(),
    )


def list_memory_artifacts(storage_path: Path | None) -> list[str]:
    if storage_path is None or not storage_path.exists():
        return []
    return sorted(
        str(path.relative_to(storage_path.parent))
        for path in storage_path.rglob("*")
        if path.is_file()
    )


def build_observation_notes() -> dict[str, Any]:
    return {
        "intentional_contradiction": {
            "agent": "writer",
            "agent_backstory_conflict": (
                "Writer backstory pushes persuasive, opinionated language."
            ),
            "task_override": (
                "Writer task requires a strictly neutral, evidence-only report."
            ),
        },
        "prompt_construction_summary": (
            "CrewAI composes the active payload from agent persona fields, active task "
            "instructions, expected output, tool context, and recalled memory."
        ),
    }


def build_agents() -> dict[str, Agent]:
    agent_config = load_yaml(CONFIG_DIR / "agents.yaml")
    primary_model = build_llm_model(resolve_model_name("MODEL_NAME", "gpt-4o-mini"))

    researcher_tools = [SerperDevTool(), FlakyResearchTool()]

    agents = {
        "researcher": Agent(
            llm=primary_model,
            tools=researcher_tools,
            **agent_config["researcher"],
        ),
        "fact_checker": Agent(
            llm=primary_model,
            **agent_config["fact_checker"],
        ),
        "writer": Agent(
            llm=primary_model,
            **agent_config["writer"],
        ),
    }
    return agents


def build_tasks(agents: dict[str, Agent], topic: str) -> list[Task]:
    task_config = load_yaml(CONFIG_DIR / "tasks.yaml")
    tasks: list[Task] = []

    for task_name in ("research_task", "fact_check_task", "write_report_task"):
        config = task_config[task_name].copy()
        agent_key = config.pop("agent")
        description = config["description"].format(topic=topic)
        expected_output = config["expected_output"].format(topic=topic)
        tasks.append(
            Task(
                description=description,
                expected_output=expected_output,
                agent=agents[agent_key],
                name=task_name,
            )
        )

    return tasks


def build_crew(mode: str, topic: str, enable_memory: bool = False) -> Crew:
    load_dotenv()
    agents = build_agents()
    tasks = build_tasks(agents, topic)
    memory = build_memory() if enable_memory else None

    if mode == "sequential":
        process = Process.sequential
        crew_kwargs: dict[str, Any] = {}
    elif mode == "hierarchical":
        process = Process.hierarchical
        manager_model = build_llm_model(resolve_model_name("MANAGER_MODEL_NAME", "gpt-4o-mini"))
        crew_kwargs = {"manager_llm": manager_model}
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    LOGGER.info("Building %s crew for topic: %s", mode, topic)
    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=process,
        verbose=True,
        memory=memory if enable_memory else False,
        embedder=build_embedder_config() if enable_memory else None,
        **crew_kwargs,
    )


def write_artifact(
    mode: str,
    topic: str,
    day_label: str,
    status: str,
    output_text: str,
    error_message: str | None,
    memory_enabled: bool,
    memory_storage_path: Path | None,
    memory_artifacts: list[str],
) -> Path:
    output_dir = BASE_DIR / "runs" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_mode = mode.replace(" ", "_")
    safe_day = day_label.replace(" ", "_")
    path = output_dir / f"{safe_mode}_{safe_day}_result.json"

    payload = {
        "mode": mode,
        "topic": topic,
        "day_label": day_label,
        "status": status,
        "output_text": output_text,
        "error_message": error_message,
        "memory_enabled": memory_enabled,
        "memory_storage_path": str(memory_storage_path) if memory_storage_path else None,
        "memory_artifacts": memory_artifacts,
        "observation_notes": build_observation_notes(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_memory_report(day_label: str, topic: str, memory_storage_path: Path | None) -> Path:
    report_dir = BASE_DIR / "runs" / "outputs"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"memory_report_{day_label.replace(' ', '_')}.json"
    report_payload = {
        "topic": topic,
        "day_label": day_label,
        "memory_storage_path": str(memory_storage_path) if memory_storage_path else None,
        "memory_artifacts": list_memory_artifacts(memory_storage_path),
        "storage_backend_note": (
            "CrewAI documentation states unified memory uses LanceDB by default."
        ),
    }
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    return report_path


def run_mode(mode: str, topic: str, enable_memory: bool = False, day_label: str = "day1") -> RunArtifacts:
    memory_storage_path = resolve_memory_storage_path() if enable_memory else None
    try:
        crew = build_crew(mode, topic, enable_memory=enable_memory)
        result = crew.kickoff(inputs={"topic": topic})
        output_text = str(result)
        memory_artifacts = list_memory_artifacts(memory_storage_path)
        output_path = write_artifact(
            mode=mode,
            topic=topic,
            day_label=day_label,
            status="success",
            output_text=output_text,
            error_message=None,
            memory_enabled=enable_memory,
            memory_storage_path=memory_storage_path,
            memory_artifacts=memory_artifacts,
        )
        if enable_memory:
            write_memory_report(day_label, topic, memory_storage_path)
        return RunArtifacts(
            mode=mode,
            topic=topic,
            day_label=day_label,
            status="success",
            output_text=output_text,
            output_path=output_path,
            memory_enabled=enable_memory,
            memory_storage_path=memory_storage_path,
            memory_artifacts=memory_artifacts,
            error_message=None,
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("%s run failed", mode)
        memory_artifacts = list_memory_artifacts(memory_storage_path)
        output_path = write_artifact(
            mode=mode,
            topic=topic,
            day_label=day_label,
            status="failed",
            output_text="",
            error_message=str(exc),
            memory_enabled=enable_memory,
            memory_storage_path=memory_storage_path,
            memory_artifacts=memory_artifacts,
        )
        if enable_memory:
            write_memory_report(day_label, topic, memory_storage_path)
        return RunArtifacts(
            mode=mode,
            topic=topic,
            day_label=day_label,
            status="failed",
            output_text="",
            output_path=output_path,
            memory_enabled=enable_memory,
            memory_storage_path=memory_storage_path,
            memory_artifacts=memory_artifacts,
            error_message=str(exc),
        )
