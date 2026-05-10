from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from dsl_spec import HOLDOUT_CASES, ZERO_SHOT_INSTRUCTIONS, build_fewshot_prompt
from env_loader import load_local_env
from validate_dsl import validate_dsl


def require_api_key() -> None:
    load_local_env()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")


def extract_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def query_model(client: OpenAI, model: str, request: str, instructions: str) -> dict[str, Any]:
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=request,
        temperature=0,
        max_output_tokens=300,
    )
    text = response.output_text.strip()
    validation = validate_dsl(text)
    return {
        "output": text,
        "valid": validation.is_valid,
        "errors": validation.errors,
        "usage": extract_usage(response),
    }


def has_filler(output: str) -> bool:
    return not output.startswith("OPS|") or "\n" in output or "```" in output


def average(values: list[int | None]) -> float:
    usable = [value for value in values if value is not None]
    return round(sum(usable) / len(usable), 2) if usable else 0.0


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 1 Results",
        "",
        "## Summary",
        f"- Baseline model: `{payload['baseline_model']}`",
        f"- Fine-tuned model: `{payload['fine_tuned_model']}`",
        f"- Baseline exact-match accuracy: `{payload['baseline_exact_accuracy']}`",
        f"- Fine-tuned exact-match accuracy: `{payload['ft_exact_accuracy']}`",
        f"- Baseline valid-DSL rate: `{payload['baseline_valid_rate']}`",
        f"- Fine-tuned valid-DSL rate: `{payload['ft_valid_rate']}`",
        f"- Average baseline input tokens: `{payload['baseline_avg_input_tokens']}`",
        f"- Average fine-tuned input tokens: `{payload['ft_avg_input_tokens']}`",
        f"- Average input-token reduction: `{payload['input_token_reduction']}`",
        f"- Average input-token reduction percent: `{payload['input_token_reduction_pct']}`",
        "",
        "## Case Results",
        "",
    ]
    for row in payload["cases"]:
        lines.extend(
            [
                f"### Case {row['case_id']}",
                f"- Request: `{row['request']}`",
                f"- Expected: `{row['expected_dsl']}`",
                f"- Baseline output: `{row['baseline_output']}`",
                f"- Fine-tuned output: `{row['ft_output']}`",
                f"- Baseline exact match: `{row['baseline_exact']}`",
                f"- Fine-tuned exact match: `{row['ft_exact']}`",
                f"- Baseline valid: `{row['baseline_valid']}`",
                f"- Fine-tuned valid: `{row['ft_valid']}`",
                f"- Baseline filler detected: `{row['baseline_filler']}`",
                f"- Fine-tuned filler detected: `{row['ft_filler']}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1 zero-shot evaluation against holdout cases.")
    parser.add_argument("--baseline-model", default="gpt-4o")
    parser.add_argument("--fine-tuned-model", required=True, help="Fine-tuned model ID returned by the training job.")
    parser.add_argument("--output-json", type=Path, default=Path("reports/phase1_results.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/phase1_results.md"))
    args = parser.parse_args()

    require_api_key()
    client = OpenAI()
    baseline_prompt = build_fewshot_prompt()

    rows = []
    for index, case in enumerate(HOLDOUT_CASES, start=1):
        baseline = query_model(client, args.baseline_model, case.request, baseline_prompt)
        fine_tuned = query_model(client, args.fine_tuned_model, case.request, ZERO_SHOT_INSTRUCTIONS)
        rows.append(
            {
                "case_id": index,
                "request": case.request,
                "expected_dsl": case.dsl,
                "baseline_output": baseline["output"],
                "ft_output": fine_tuned["output"],
                "baseline_exact": baseline["output"] == case.dsl,
                "ft_exact": fine_tuned["output"] == case.dsl,
                "baseline_valid": baseline["valid"],
                "ft_valid": fine_tuned["valid"],
                "baseline_filler": has_filler(baseline["output"]),
                "ft_filler": has_filler(fine_tuned["output"]),
                "baseline_usage": baseline["usage"],
                "ft_usage": fine_tuned["usage"],
            }
        )

    baseline_exact = sum(1 for row in rows if row["baseline_exact"])
    ft_exact = sum(1 for row in rows if row["ft_exact"])
    baseline_valid = sum(1 for row in rows if row["baseline_valid"])
    ft_valid = sum(1 for row in rows if row["ft_valid"])

    baseline_avg_input_tokens = average([row["baseline_usage"]["input_tokens"] for row in rows])
    ft_avg_input_tokens = average([row["ft_usage"]["input_tokens"] for row in rows])
    reduction = round(baseline_avg_input_tokens - ft_avg_input_tokens, 2)
    reduction_pct = round((reduction / baseline_avg_input_tokens) * 100, 2) if baseline_avg_input_tokens else 0.0

    payload = {
        "baseline_model": args.baseline_model,
        "fine_tuned_model": args.fine_tuned_model,
        "num_cases": len(rows),
        "baseline_exact_accuracy": round(baseline_exact / len(rows), 4),
        "ft_exact_accuracy": round(ft_exact / len(rows), 4),
        "baseline_valid_rate": round(baseline_valid / len(rows), 4),
        "ft_valid_rate": round(ft_valid / len(rows), 4),
        "baseline_avg_input_tokens": baseline_avg_input_tokens,
        "ft_avg_input_tokens": ft_avg_input_tokens,
        "input_token_reduction": reduction,
        "input_token_reduction_pct": reduction_pct,
        "cases": rows,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_report(args.output_md, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
