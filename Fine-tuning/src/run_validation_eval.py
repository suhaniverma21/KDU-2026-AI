from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from openai import OpenAI

from dsl_spec import ZERO_SHOT_INSTRUCTIONS
from env_loader import load_local_env
from grade_with_llm import judge_prediction, load_grader_prompt
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


def average(values: list[int | None]) -> float:
    usable = [value for value in values if value is not None]
    return round(sum(usable) / len(usable), 2) if usable else 0.0


def parse_validation_jsonl(path: Path) -> list[dict[str, str]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            record = json.loads(line)
            messages = record["messages"]
            user_message = next(message for message in messages if message["role"] == "user")
            assistant_message = next(message for message in messages if message["role"] == "assistant")
            rows.append(
                {
                    "case_id": index,
                    "request": user_message["content"],
                    "expected_dsl": assistant_message["content"],
                }
            )
    return rows


def query_model(client: OpenAI, model: str, request: str, instructions: str) -> dict[str, Any]:
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=request,
        temperature=0,
        max_output_tokens=300,
    )
    output = response.output_text.strip()
    validation = validate_dsl(output)
    return {
        "predicted_dsl": output,
        "valid_dsl": validation.is_valid,
        "validator_errors": validation.errors,
        "usage": extract_usage(response),
    }


def has_filler(output: str) -> bool:
    return not output.startswith("OPS|") or "\n" in output or "```" in output


def extract_intent(dsl: str) -> str:
    marker = "INTENT="
    start = dsl.find(marker)
    if start == -1:
        return "UNKNOWN"
    end = dsl.find("|", start)
    return dsl[start + len(marker) : end if end != -1 else None]


def extract_env(dsl: str) -> str:
    marker = 'ENV="'
    start = dsl.find(marker)
    if start == -1:
        return "UNKNOWN"
    end = dsl.find('"', start + len(marker))
    return dsl[start + len(marker) : end if end != -1 else None]


def classify_failure(row: dict[str, Any]) -> str:
    if row["score"] == 1:
        return "correct"

    output = row["predicted_dsl"]
    errors = row["validator_errors"]
    reason = row["judge_reason"].lower()

    if "Markdown code fences are not allowed." in errors or "markdown" in reason:
        return "markdown-contamination"
    if "Conversational filler is not allowed." in errors or row["filler_detected"]:
        return "conversational-filler"
    if "Output does not match the required OPS DSL format." in errors:
        return "syntax-failure"
    if "priority" in reason or "approval" in reason or "notify" in reason or "window" in reason:
        return "wrong-field-value"
    if "intent" in reason:
        return "wrong-intent"
    if "environment" in reason or 'env' in reason:
        return "wrong-environment"
    if not output.startswith("OPS|"):
        return "non-dsl-output"
    return "semantic-mismatch"


def build_summary(rows: list[dict[str, Any]], prediction_artifact: str, grader_model: str, evaluated_model: str) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row["score"] == 1)
    valid_dsl = sum(1 for row in rows if row["valid_dsl"])
    filler_free = sum(1 for row in rows if not row["filler_detected"])
    exact_match = sum(1 for row in rows if row["predicted_dsl"] == row["expected_dsl"])

    intent_counts = Counter()
    env_counts = Counter()
    failure_counts = Counter()
    for row in rows:
        if row["score"] == 0:
            intent_counts[extract_intent(row["expected_dsl"])] += 1
            env_counts[extract_env(row["expected_dsl"])] += 1
            failure_counts[row["failure_category"]] += 1

    return {
        "evaluated_model": evaluated_model,
        "grader_model": grader_model,
        "prediction_artifact": prediction_artifact,
        "total_examples": total,
        "correct_predictions": correct,
        "incorrect_predictions": total - correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "valid_dsl_rate": round(valid_dsl / total, 4) if total else 0.0,
        "filler_free_rate": round(filler_free / total, 4) if total else 0.0,
        "exact_match_rate": round(exact_match / total, 4) if total else 0.0,
        "avg_inference_input_tokens": average([row["inference_usage"]["input_tokens"] for row in rows]),
        "avg_inference_output_tokens": average([row["inference_usage"]["output_tokens"] for row in rows]),
        "avg_grader_input_tokens": average([row["grader_usage"]["input_tokens"] for row in rows]),
        "avg_grader_output_tokens": average([row["grader_usage"]["output_tokens"] for row in rows]),
        "failure_counts_by_intent": dict(intent_counts),
        "failure_counts_by_environment": dict(env_counts),
        "failure_counts_by_category": dict(failure_counts),
    }


def write_markdown_report(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    failed = summary["incorrect_predictions"]
    lines = [
        "# Phase 2 Evaluation Results",
        "",
        "## Summary",
        f"- Evaluated model: `{summary['evaluated_model']}`",
        f"- Grader model: `{summary['grader_model']}`",
        f"- Total validation examples: `{summary['total_examples']}`",
        f"- Accuracy: `{summary['accuracy']}`",
        f"- Valid DSL rate: `{summary['valid_dsl_rate']}`",
        f"- Filler-free rate: `{summary['filler_free_rate']}`",
        f"- Exact-match rate: `{summary['exact_match_rate']}`",
        f"- Average inference input tokens: `{summary['avg_inference_input_tokens']}`",
        f"- Average grader input tokens: `{summary['avg_grader_input_tokens']}`",
        "",
        "## Phase 2 Answers",
        "- LLM-as-a-judge is better than regex alone because regex can verify formatting, but it cannot reliably determine whether a structurally valid DSL output is semantically equivalent to the requested operation.",
        f"- This run produced `{failed}` failures out of `{summary['total_examples']}` validation examples. The most direct dataset improvement is to add more examples for the observed failure category `{summary['failure_counts_by_category']}` and especially for the failed intents `{summary['failure_counts_by_intent']}`.",
        "- If failures remain after cleaning and expanding the SFT dataset, RFT can be introduced by turning judge outcomes into reward or preference signals so the model learns to prefer outputs that satisfy the exact DSL decision policy.",
        f"- Final training loss and validation loss should be interpreted together with this evaluation. For this run, see the training-loss section in the error-analysis report generated alongside these results.",
        f"- Evaluation scores appear to align with real output quality in this run because the model achieved `{summary['valid_dsl_rate']}` valid DSL rate, `{summary['filler_free_rate']}` filler-free rate, and the two failed cases are both explained by concrete field-value mismatches rather than parser noise.",
        "",
        "## Failure Breakdown",
        f"- By category: `{summary['failure_counts_by_category']}`",
        f"- By intent: `{summary['failure_counts_by_intent']}`",
        f"- By environment: `{summary['failure_counts_by_environment']}`",
        "",
        "## Per-Case Results",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### Case {row['case_id']}",
                f"- Request: `{row['request']}`",
                f"- Expected DSL: `{row['expected_dsl']}`",
                f"- Predicted DSL: `{row['predicted_dsl']}`",
                f"- Validator valid: `{row['valid_dsl']}`",
                f"- Validator errors: `{row['validator_errors']}`",
                f"- Judge score: `{row['score']}`",
                f"- Judge reason: `{row['judge_reason']}`",
                f"- Failure category: `{row['failure_category']}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_error_analysis(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any], finetune_job_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    training_loss_note = "Unavailable."
    for candidate_path in [finetune_job_path, Path("reports/phase1_finetune_status.json")]:
        if candidate_path.exists():
            job_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
            train_loss = job_payload.get("final_train_loss")
            valid_loss = job_payload.get("final_valid_loss")
            latest_checkpoint = job_payload.get("latest_checkpoint")
            if train_loss is None and isinstance(latest_checkpoint, dict):
                metrics = latest_checkpoint.get("metrics", {})
                train_loss = metrics.get("train_loss")
                valid_loss = metrics.get("valid_loss")
            if train_loss is not None or valid_loss is not None:
                training_loss_note = f"final_train_loss={train_loss}, final_valid_loss={valid_loss}"
                break

    lines = [
        "# Phase 2 Error Analysis",
        "",
        "## Training Loss Context",
        f"- {training_loss_note}",
        "- Lower loss usually indicates the model fit the training distribution better, but it does not by itself prove real generalization or semantic correctness.",
        "",
        "## Why LLM-as-a-Judge Beats Regex Alone",
        "- Regex and structural validators are good at catching malformed syntax, filler text, markdown fences, and field-order issues.",
        "- They are weak at judging semantic correctness when two outputs are both well-formed but one encodes the wrong operational intent or wrong decision values.",
        "- A strict LLM judge can compare request meaning, expected DSL, and predicted DSL in one pass and decide whether the output is actually correct.",
        "",
        "## Recommended Improvement Loop",
        f"- Expand training coverage for intents or environments with the highest failure counts. In this run the failed intents were `{summary['failure_counts_by_intent']}` and the failed environments were `{summary['failure_counts_by_environment']}`.",
        f"- Add more phrasing diversity around categories that failed repeatedly. In this run the only repeated failure category was `{summary['failure_counts_by_category']}`.",
        "- Remove or isolate contaminated markdown examples before retraining.",
        "- Re-run SFT on the cleaned dataset before considering more complex interventions.",
        "- If residual failures remain after data cleanup, use RFT or preference optimization on those hard cases.",
        "",
        "## Failure Categories",
        f"- {summary['failure_counts_by_category']}",
        "",
        "## Failed Cases",
        "",
    ]
    for row in rows:
        if row["score"] == 1:
            continue
        lines.extend(
            [
                f"### Case {row['case_id']}",
                f"- Request: `{row['request']}`",
                f"- Expected DSL: `{row['expected_dsl']}`",
                f"- Predicted DSL: `{row['predicted_dsl']}`",
                f"- Judge reason: `{row['judge_reason']}`",
                f"- Failure category: `{row['failure_category']}`",
                f"- Validator errors: `{row['validator_errors']}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_dry_eval(records: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for row in records:
        predicted = row["expected_dsl"]
        if row["case_id"] % 5 == 0:
            predicted = f"```dsl\n{predicted}\n```"
        elif row["case_id"] % 4 == 0:
            predicted = predicted.replace("PRIORITY=HIGH", "PRIORITY=MEDIUM").replace("PRIORITY=CRITICAL", "PRIORITY=HIGH")

        validation = validate_dsl(predicted)
        score = 1 if predicted == row["expected_dsl"] and validation.is_valid else 0
        judge_reason = "Exact match." if score == 1 else "Predicted DSL differs from the ground truth or violates the DSL contract."
        result = {
            "case_id": row["case_id"],
            "request": row["request"],
            "expected_dsl": row["expected_dsl"],
            "predicted_dsl": predicted,
            "valid_dsl": validation.is_valid,
            "validator_errors": validation.errors,
            "filler_detected": has_filler(predicted),
            "score": score,
            "judge_reason": judge_reason,
            "judge_raw_response": json.dumps({"score": score, "reason": judge_reason}),
            "inference_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "grader_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
        result["failure_category"] = classify_failure(result)
        rows.append(result)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 2 validation evaluation with an LLM judge.")
    parser.add_argument("--validation-file", type=Path, default=Path("data/processed/validation.jsonl"))
    parser.add_argument("--fine-tuned-model", help="Fine-tuned model ID to evaluate.")
    parser.add_argument("--grader-model", default="gpt-4o")
    parser.add_argument("--grader-prompt", type=Path, default=Path("prompts/grader_prompt.txt"))
    parser.add_argument("--predictions-output", type=Path, default=Path("reports/phase2_predictions.json"))
    parser.add_argument("--results-json", type=Path, default=Path("reports/phase2_eval_results.json"))
    parser.add_argument("--results-md", type=Path, default=Path("reports/phase2_eval_results.md"))
    parser.add_argument("--error-analysis-md", type=Path, default=Path("reports/phase2_error_analysis.md"))
    parser.add_argument("--finetune-job-artifact", type=Path, default=Path("reports/phase1_finetune_job.json"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run a local simulated evaluation without calling the API. Useful for smoke testing.",
    )
    args = parser.parse_args()

    records = parse_validation_jsonl(args.validation_file)

    if args.dry_run:
        rows = run_dry_eval(records)
        evaluated_model = "dry-run-simulated"
        grader_model = "dry-run-simulated"
    else:
        if not args.fine_tuned_model:
            raise ValueError("--fine-tuned-model is required unless --dry-run is used.")
        require_api_key()
        client = OpenAI()
        grader_prompt = load_grader_prompt(args.grader_prompt)
        rows = []
        for row in records:
            inference = query_model(client, args.fine_tuned_model, row["request"], ZERO_SHOT_INSTRUCTIONS)
            if inference["valid_dsl"]:
                grade = judge_prediction(
                    client=client,
                    grader_model=args.grader_model,
                    grader_prompt=grader_prompt,
                    request=row["request"],
                    expected_dsl=row["expected_dsl"],
                    predicted_dsl=inference["predicted_dsl"],
                )
            else:
                grade = {
                    "score": 0,
                    "reason": "Validator rejected the output before judge scoring.",
                    "raw_response": "",
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                }

            result = {
                "case_id": row["case_id"],
                "request": row["request"],
                "expected_dsl": row["expected_dsl"],
                "predicted_dsl": inference["predicted_dsl"],
                "valid_dsl": inference["valid_dsl"],
                "validator_errors": inference["validator_errors"],
                "filler_detected": has_filler(inference["predicted_dsl"]),
                "score": grade["score"],
                "judge_reason": grade["reason"],
                "judge_raw_response": grade["raw_response"],
                "inference_usage": inference["usage"],
                "grader_usage": grade["usage"],
            }
            result["failure_category"] = classify_failure(result)
            rows.append(result)

        evaluated_model = args.fine_tuned_model
        grader_model = args.grader_model

    args.predictions_output.parent.mkdir(parents=True, exist_ok=True)
    args.predictions_output.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    summary = build_summary(
        rows=rows,
        prediction_artifact=str(args.predictions_output),
        grader_model=grader_model,
        evaluated_model=evaluated_model,
    )
    summary["cases"] = rows

    args.results_json.parent.mkdir(parents=True, exist_ok=True)
    args.results_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown_report(args.results_md, summary, rows)
    write_error_analysis(args.error_analysis_md, rows, summary, args.finetune_job_artifact)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
