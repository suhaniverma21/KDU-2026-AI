"""Interactive terminal CLI for manually testing the FixIt LLMOps pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .config_loader import ConfigValidationError, load_all_config
from .cost_tracker import CostTracker
from .llm_client import LLMClient, LLMClientError, MissingAPIKeyError
from .main import analyze_query, handle_query


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the interactive FixIt demo CLI."""
    parser = argparse.ArgumentParser(
        description="Interactive terminal demo for the FixIt LLMOps support pipeline.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print full metadata as pretty JSON after each query.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip all live LLM calls and run only classification plus routing.",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """Run the interactive CLI loop."""
    args = build_parser().parse_args(argv)

    try:
        config = load_all_config()
    except ConfigValidationError as exc:
        print(f"Startup error: configuration could not be loaded.\nReason: {exc}", file=sys.stderr)
        return 1

    tracker = CostTracker(config=config)
    client = None if args.no_llm else LLMClient(config=config)

    print(_build_cli_banner(no_llm=args.no_llm, debug=args.debug))

    while True:
        try:
            query = input("Enter a customer query (type 'exit' to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0

        if not query:
            continue

        if query.lower() in {"exit", "quit"}:
            print("Goodbye.")
            return 0

        try:
            result = process_query(
                query,
                config=config,
                cost_tracker=tracker,
                llm_client=client,
                no_llm=args.no_llm,
            )
        except MissingAPIKeyError as exc:
            print(_render_error(f"Missing API key: {exc}"))
            continue
        except (LLMClientError, ValueError, TypeError) as exc:
            print(_render_error(str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            print(_render_error(f"Unexpected error while processing query: {exc}"))
            continue

        print(render_result(result, debug=args.debug))


def process_query(
    query: str,
    *,
    config: dict[str, Any],
    cost_tracker: CostTracker,
    llm_client: LLMClient | None,
    no_llm: bool,
) -> dict[str, Any]:
    """Process a single CLI query in either full or no-LLM mode."""
    if no_llm:
        return analyze_query(
            query,
            config=config,
            cost_tracker=cost_tracker,
            disable_stage2_classifier=True,
        )

    return handle_query(
        query,
        config=config,
        cost_tracker=cost_tracker,
        llm_client=llm_client,
    )


def render_result(result: dict[str, Any], *, debug: bool) -> str:
    """Render a query result in a friendly terminal format."""
    metadata = result["metadata"]
    classification = metadata["classification"]
    route = metadata["route"]
    fallback = metadata["fallback"]

    lines = [
        "",
        "=" * 62,
        "FixIt Support Result",
        "=" * 62,
        f"Query: {metadata['query']}",
        f"Category: {classification['category']}",
        f"Complexity: {classification['complexity']}",
        f"Confidence: {_format_confidence(classification.get('confidence'))}",
        f"Selected Tier: {route['selected_tier']}",
    ]

    model_name = metadata.get("model", {}).get("name")
    if model_name:
        lines.append(f"Model: {model_name}")

    if metadata.get("llm_generation_skipped"):
        lines.append(f"Response: {metadata['skip_reason']}")
    else:
        lines.append(f"Response: {result['response_text']}")

    if fallback.get("applied"):
        lines.append(f"Fallback: {summarize_fallbacks(fallback.get('events', []))}")

    lines.append("-" * 62)

    if debug:
        lines.append("Debug Metadata:")
        lines.append(json.dumps(metadata, indent=2, sort_keys=True))
        lines.append("-" * 62)

    return "\n".join(lines)


def summarize_fallbacks(events: list[dict[str, Any]]) -> str:
    """Build a short human-readable fallback summary for terminal display."""
    if not events:
        return "None"

    seen_reasons: list[str] = []
    for event in events:
        reason = str(event.get("fallback_reason", "")).strip()
        if reason and reason not in seen_reasons:
            seen_reasons.append(reason)

    if not seen_reasons:
        return "Fallback behavior was applied."
    if len(seen_reasons) == 1:
        return seen_reasons[0]
    return " | ".join(seen_reasons[:2])


def _format_confidence(confidence: Any) -> str:
    """Format a confidence value for human-friendly terminal output."""
    try:
        return f"{float(confidence):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _build_cli_banner(*, no_llm: bool, debug: bool) -> str:
    """Build the CLI startup banner."""
    mode = "routing-only / no live LLM calls" if no_llm else "full pipeline / live LLM generation"
    debug_text = "on" if debug else "off"
    return (
        "=" * 62
        + "\nFixIt LLMOps Interactive CLI\n"
        + "=" * 62
        + f"\nMode: {mode}"
        + f"\nDebug: {debug_text}\n"
    )


def _render_error(message: str) -> str:
    """Render a user-friendly CLI error block."""
    return "\n".join(
        [
            "",
            "!" * 62,
            "FixIt CLI Error",
            "!" * 62,
            message,
            "-" * 62,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(run_cli())
