"""Runs the standalone Phase 3 scaling, monitoring, and cost-control demonstration."""

from __future__ import annotations

import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from config.settings import get_settings
from concurrency.concurrency_queue import ConcurrencyQueue
from core.token_pruner import TokenPruner
from monitoring.cost_tracker import CostTracker
from simulation.load_simulator import LoadSimulator
from structured_logging.structured_logger import StructuredLogger


def run_phase3() -> dict[str, Any]:
    """Run the full Phase 3 demonstration and return a structured summary of all steps."""
    step_results: dict[str, Any] = {}

    step_results["step_1"] = _run_step_1_token_pruning_demo()
    step_results["step_2"] = _run_step_2_queue_demo()
    step_results["step_3"] = _run_step_3_load_simulation()
    step_results["step_4"] = _run_step_4_cost_report()
    step_results["step_5"] = _run_step_5_log_replay_demo()

    return step_results


def main() -> int:
    """Execute the Phase 3 demonstration and return a clean process exit code."""
    try:
        get_settings()
        run_phase3()
        return 0
    except Exception as exc:
        print(f"[Error] Phase 3 demonstration failed: {exc}", file=sys.stderr)
        return 1


def _run_step_1_token_pruning_demo() -> dict[str, Any]:
    """Demonstrate pruning a long handoff history and print the resulting report."""
    print("=== STEP 1: Token Pruning Demo ===")
    try:
        pruner = TokenPruner()
        conversation_history = agent_one()
        original_token_count = pruner.estimate_tokens(conversation_history)
        print(f"[Agent One] Finished. History has {original_token_count} tokens")
        result = pruner.prune(conversation_history=conversation_history, max_tokens=220)
        pruning_report = result["pruning_report"]
        print(
            "[Pruner] Strategy: "
            f"{pruning_report['strategy_used']} | "
            f"Tokens: {pruning_report['original_token_count']} → "
            f"{pruning_report['pruned_token_count']} | "
            f"Removed: {pruning_report['messages_removed']}"
        )
        handoff_payload = {"conversation_history": result["pruned_history"]}
        agent_two(handoff_payload)
        return result
    except Exception as exc:
        print(f"[Step 1 Error] {exc}")
        return {"status": "error", "message": str(exc)}


def _run_step_2_queue_demo() -> dict[str, Any]:
    """Demonstrate queue protection under simultaneous request pressure."""
    print("=== STEP 2: Concurrency Queue Demo ===")
    try:
        queue = ConcurrencyQueue()
        logger = StructuredLogger()
        session_id = str(uuid.uuid4())
        results: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(
                    queue.execute,
                    _slow_queue_task,
                    request_id=f"queue-demo-{index}",
                )
                for index in range(20)
            ]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                logger.log(
                    event_type="queue",
                    payload={"request_id": result.get("request_id"), "queue_result": result},
                    level="INFO" if result.get("status") == "completed" else "WARNING",
                    session_id=session_id,
                )

        queue_stats = queue.get_stats()
        print(f"Queue stats: {queue_stats}")
        return {"results": results, "queue_stats": queue_stats}
    except Exception as exc:
        print(f"[Step 2 Error] {exc}")
        return {"status": "error", "message": str(exc)}


def _run_step_3_load_simulation() -> dict[str, Any]:
    """Run the 100-user load simulation and print its final aggregate summary."""
    print("=== STEP 3: Load Simulation ===")
    try:
        simulator = LoadSimulator()
        results = simulator.run(num_users=100, requests_per_user=1)
        print(f"Load simulation results: {results}")
        return results
    except Exception as exc:
        print(f"[Step 3 Error] {exc}")
        return {"status": "error", "message": str(exc)}


def _run_step_4_cost_report() -> dict[str, Any]:
    """Print the aggregate cost summary and cost breakdown by agent."""
    print("=== STEP 4: Cost Report ===")
    try:
        cost_tracker = CostTracker()
        total_cost = cost_tracker.get_total_cost()
        breakdown = cost_tracker.get_cost_breakdown()
        print(f"Total cost: {total_cost}")
        print(f"Cost breakdown by agent: {breakdown}")
        return {"total_cost": total_cost, "breakdown": breakdown}
    except Exception as exc:
        print(f"[Step 4 Error] {exc}")
        return {"status": "error", "message": str(exc)}


def _run_step_5_log_replay_demo() -> dict[str, Any]:
    """Replay recent logs and export one session log file for debugging."""
    print("=== STEP 5: Log Replay Demo ===")
    try:
        logger = StructuredLogger()
        last_entries = logger.replay_last_n(5)
        print(f"Last 5 log entries: {last_entries}")

        session_id = _pick_session_id_for_export(last_entries, logger)
        if session_id is None:
            print("No session logs available to export yet.")
            return {"last_entries": last_entries, "export": None}

        export_result = logger.export_session(
            session_id=session_id,
            output_path=str(
                Path("logs") / "replay" / f"{session_id}_export.jsonl"
            ),
        )
        print(f"Session export: {export_result}")
        return {"last_entries": last_entries, "export": export_result}
    except Exception as exc:
        print(f"[Step 5 Error] {exc}")
        return {"status": "error", "message": str(exc)}


def _build_sample_conversation_history() -> list[dict[str, str]]:
    """Create a deterministic 20-message history for the token-pruning demonstration."""
    history: list[dict[str, str]] = [
        {
            "role": "system",
            "content": "You are a billing support assistant. Preserve critical account facts.",
        }
    ]
    for index in range(1, 20):
        role = "user" if index % 2 else "assistant"
        history.append(
            {
                "role": role,
                "content": (
                    f"Sample conversation turn {index}. "
                    "Customer is discussing repeated billing concerns and invoice history."
                ),
            }
        )
    return history


def agent_one() -> list[dict[str, str]]:
    """Return a completed agent history without any LLM calls."""
    return _build_sample_conversation_history()


def agent_two(handoff_payload: dict) -> None:
    """Read a handoff payload, count its history tokens, and print the received total."""
    conversation_history = handoff_payload.get("conversation_history", [])
    total_characters = 0
    for message in conversation_history:
        total_characters += len(message.get("role", ""))
        total_characters += len(message.get("content", ""))
    token_count = (total_characters + 3) // 4
    print(f"[Agent Two] Received handoff. History has {token_count} tokens")


def _slow_queue_task() -> dict[str, Any]:
    """Simulate a slow downstream dependency so some queued requests time out and reject."""
    settings = get_settings()
    time.sleep(settings.max_queue_wait_seconds + 0.5)
    return {"status": "processed"}


def _pick_session_id_for_export(
    last_entries: list[dict[str, Any]],
    logger: StructuredLogger,
) -> str | None:
    """Choose one session ID from recent logs or broader queue logs for export."""
    for entry in reversed(last_entries):
        session_id = entry.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id

    queue_entries = logger.replay_by_event_type("queue")
    for entry in queue_entries:
        session_id = entry.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
    return None


if __name__ == "__main__":
    raise SystemExit(main())
