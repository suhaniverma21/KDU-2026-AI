from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI
from env_loader import load_local_env


DEFAULT_PROMPT_PATH = Path("prompts/grader_prompt.txt")


def require_api_key() -> None:
    load_local_env()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")


def load_grader_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def extract_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Grader output did not contain a parseable JSON object.") from None
        parsed = json.loads(stripped[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Expected grader output to be a JSON object.")
    return parsed


def normalize_grade(parsed: dict[str, Any], raw_text: str, usage: dict[str, int | None]) -> dict[str, Any]:
    score = parsed.get("score")
    if score not in (0, 1):
        raise ValueError(f"Grader score must be 0 or 1, received {score!r}.")

    reason = str(parsed.get("reason", "")).strip() or "No reason provided."
    return {"score": int(score), "reason": reason, "raw_response": raw_text, "usage": usage}


def judge_prediction(
    client: OpenAI,
    grader_model: str,
    grader_prompt: str,
    request: str,
    expected_dsl: str,
    predicted_dsl: str,
) -> dict[str, Any]:
    grader_input = json.dumps(
        {
            "request": request,
            "ground_truth_dsl": expected_dsl,
            "predicted_dsl": predicted_dsl,
        },
        ensure_ascii=True,
        indent=2,
    )
    response = client.responses.create(
        model=grader_model,
        instructions=grader_prompt,
        input=grader_input,
        temperature=0,
        max_output_tokens=200,
    )
    raw_text = response.output_text.strip()
    parsed = extract_json_object(raw_text)
    return normalize_grade(parsed, raw_text, extract_usage(response))


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade one DSL prediction with gpt-4o.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--expected-dsl", required=True)
    parser.add_argument("--predicted-dsl", required=True)
    parser.add_argument("--grader-model", default="gpt-4o")
    parser.add_argument("--grader-prompt", type=Path, default=DEFAULT_PROMPT_PATH)
    args = parser.parse_args()

    require_api_key()
    client = OpenAI()
    result = judge_prediction(
        client=client,
        grader_model=args.grader_model,
        grader_prompt=load_grader_prompt(args.grader_prompt),
        request=args.request,
        expected_dsl=args.expected_dsl,
        predicted_dsl=args.predicted_dsl,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
