from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import load_project_env


def get_phase3_llm_config() -> dict[str, str]:
    load_project_env()

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing OPENROUTER_API_KEY. Phase 3 is configured to use OpenRouter.")

    return {
        "provider": "openrouter",
        "api_key": api_key,
        "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "model": os.getenv("PHASE3_LLM_MODEL", "meta-llama/llama-3.1-8b-instruct"),
    }


def build_path_summary(path_payload: dict[str, Any] | None) -> str:
    if not path_payload:
        return "No path found."

    nodes = path_payload["nodes"]
    relationships = path_payload["relationships"]
    if not nodes or not relationships:
        return "No path found."

    node_by_id = {node["id"]: node for node in nodes}
    segments: list[str] = []

    for relationship in relationships:
        start_name = node_by_id[relationship["start_node_id"]]["properties"].get("name", "Unknown")
        end_name = node_by_id[relationship["end_node_id"]]["properties"].get("name", "Unknown")
        source_pages = relationship["properties"].get("source_pages", [])
        segments.append(
            f"{start_name} -[{relationship['type']}]-> {end_name} (source_pages={source_pages})"
        )

    return "\n".join(segments)


def answer_from_path(question: str, path_payload: dict[str, Any] | None) -> dict[str, str]:
    config = get_phase3_llm_config()
    path_summary = build_path_summary(path_payload)

    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
    response = client.chat.completions.create(
        model=config["model"],
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer only from the provided graph path evidence. "
                    "State the ownership chain explicitly. If the path is incomplete, say the evidence is insufficient."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nGraph path evidence:\n{path_summary}",
            },
        ],
    )
    return {
        "provider": config["provider"],
        "model": config["model"],
        "path_summary": path_summary,
        "answer": (response.choices[0].message.content or "").strip(),
    }
