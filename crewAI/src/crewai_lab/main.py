from __future__ import annotations

import argparse
import logging
from typing import Iterable

from .crew_builder import RunArtifacts, run_mode


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CrewAI lab.")
    parser.add_argument("--topic", required=True, help="Research topic for the crew.")
    parser.add_argument(
        "--mode",
        choices=("sequential", "hierarchical", "compare"),
        default="compare",
        help="Execution mode to run.",
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Enable CrewAI shared memory for the run.",
    )
    parser.add_argument(
        "--day-label",
        default="day1",
        help="Label for the run, useful for Day 1 to Day 2 memory experiments.",
    )
    return parser.parse_args()


def expand_modes(mode: str) -> Iterable[str]:
    if mode == "compare":
        return ("sequential", "hierarchical")
    return (mode,)


def print_summary(result: RunArtifacts) -> None:
    print(f"[{result.mode}] status={result.status} artifact={result.output_path}")
    print(f"[{result.mode}] day_label={result.day_label} memory_enabled={result.memory_enabled}")
    if result.memory_storage_path:
        print(f"[{result.mode}] memory_storage={result.memory_storage_path}")
        print(f"[{result.mode}] memory_files={len(result.memory_artifacts)}")
    if result.error_message:
        print(f"[{result.mode}] error={result.error_message}")
    elif result.output_text:
        preview = result.output_text[:500].strip()
        print(f"[{result.mode}] preview={preview}")


def main() -> None:
    configure_logging()
    args = parse_args()

    for mode in expand_modes(args.mode):
        result = run_mode(mode, args.topic, enable_memory=args.memory, day_label=args.day_label)
        print_summary(result)


if __name__ == "__main__":
    main()
