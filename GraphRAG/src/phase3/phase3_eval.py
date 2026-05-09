from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))

from phase3_answer import answer_from_path
from phase3_cypher import correct_cypher, generate_cypher
from phase3_query import execute_cypher
from utils import ATTACK_QUERY, save_json


DEFAULT_JSON_PATH = Path("outputs/phase3_query_result.json")
DEFAULT_ANSWER_PATH = Path("outputs/phase3_answer.md")
DEFAULT_REPORT_PATH = Path("outputs/phase3_report.md")


def run_phase3(question: str, allow_retry: bool = True) -> dict[str, Any]:
    cypher_result = generate_cypher(question)
    generated_cypher = cypher_result["validation"]["cypher"]

    execution = {
        "success": False,
        "path_found": False,
        "path": None,
        "error": None,
    }
    corrected_cypher = None
    retry_count = 0

    if cypher_result["validation"]["valid"]:
        execution = execute_cypher(generated_cypher)
    else:
        execution["error"] = "; ".join(cypher_result["validation"]["errors"])

    if allow_retry and (
        not cypher_result["validation"]["valid"]
        or not execution["success"]
        or (execution["success"] and not execution["path_found"])
    ):
        retry_count = 1
        correction = correct_cypher(
            question=question,
            failed_cypher=generated_cypher,
            error_message=execution["error"] or "Query executed but no path was found in Neo4j.",
        )
        corrected_cypher = correction["validation"]["cypher"]
        if correction["validation"]["valid"]:
            execution = execute_cypher(corrected_cypher)
        else:
            execution = {
                "success": False,
                "path_found": False,
                "path": None,
                "error": "; ".join(correction["validation"]["errors"]),
            }
    else:
        correction = None

    final_answer = None
    if execution["success"] and execution["path_found"]:
        final_answer = answer_from_path(question, execution["path"])

    return {
        "question": question,
        "generated_cypher": generated_cypher,
        "generated_cypher_validation": cypher_result["validation"],
        "corrected_cypher": corrected_cypher,
        "retry_count": retry_count,
        "query_success": execution["success"],
        "path_found": execution["path_found"],
        "neo4j_error": execution["error"],
        "path": execution["path"],
        "cypher_model": cypher_result["model"],
        "answer_model": None if final_answer is None else final_answer["model"],
        "path_summary": None if final_answer is None else final_answer["path_summary"],
        "final_answer": None if final_answer is None else final_answer["answer"],
    }


def build_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 3 Report",
        "",
        "## Query",
        "",
        f"- Question: `{payload['question']}`",
        f"- Cypher model: `{payload['cypher_model']}`",
        f"- Retry count: `{payload['retry_count']}`",
        f"- Query success: `{payload['query_success']}`",
        f"- Path found: `{payload['path_found']}`",
        "",
        "## Generated Cypher",
        "",
        "```cypher",
        payload["generated_cypher"],
        "```",
        "",
    ]

    if payload["corrected_cypher"]:
        lines.extend(
            [
                "## Corrected Cypher",
                "",
                "```cypher",
                payload["corrected_cypher"],
                "```",
                "",
            ]
        )

    if payload["neo4j_error"]:
        lines.extend(
            [
                "## Neo4j Error",
                "",
                payload["neo4j_error"],
                "",
            ]
        )

    if payload["path_summary"]:
        lines.extend(
            [
                "## Graph Path",
                "",
                "```text",
                payload["path_summary"],
                "```",
                "",
            ]
        )

    if payload["final_answer"]:
        lines.extend(
            [
                "## Final Answer",
                "",
                payload["final_answer"],
                "",
            ]
        )

    lines.extend(
        [
            "## Failure Handling",
            "",
            "The pipeline validates generated Cypher against the known schema, blocks unsafe write operations, and allows one correction retry if the first query is invalid or Neo4j returns an execution error.",
            "",
            "## Why Hybrid RAG Is Better",
            "",
            "Vector search helps interpret natural-language questions, while graph traversal retrieves exact ownership relationships. The final LLM step only summarizes the returned path, which is more reliable than asking a vector-only system to infer missing links.",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 3 graph-query pipeline.")
    parser.add_argument("--question", default=ATTACK_QUERY)
    parser.add_argument("--no-retry", action="store_true")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_PATH))
    parser.add_argument("--answer-output", default=str(DEFAULT_ANSWER_PATH))
    parser.add_argument("--report-output", default=str(DEFAULT_REPORT_PATH))
    args = parser.parse_args()

    payload = run_phase3(question=args.question, allow_retry=not args.no_retry)
    save_json(Path(args.json_output), payload)

    answer_text = payload["final_answer"] or "No grounded answer was produced."
    Path(args.answer_output).write_text(answer_text, encoding="utf-8")
    Path(args.report_output).write_text(build_report(payload), encoding="utf-8")

    print(f"Saved Phase 3 JSON output to {args.json_output}")
    print(f"Saved Phase 3 answer to {args.answer_output}")
    print(f"Saved Phase 3 report to {args.report_output}")


if __name__ == "__main__":
    main()
