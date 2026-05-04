"""Runs the standalone Phase 2 coordinator and consensus flow from one entry point."""

from __future__ import annotations

import sys
from typing import Any

from agents.consensus_agent import ConsensusAgent
from config.settings import get_settings
from monitoring.agent_monitor import AgentMonitor
from orchestration.coordinator import Coordinator


SAMPLE_QUERY: dict[str, Any] = {
    "intent": "billing",
    "entities": {"account_id": "ACC-12345", "issue": "double charge"},
    "query": "Customer was charged twice in March. Lookup account and find policy.",
}


def run_phase2(query: dict[str, Any]) -> dict[str, Any]:
    """Run the full Phase 2 flow and return the final consensus response."""
    coordinator = Coordinator()
    consensus_agent = ConsensusAgent()
    monitor = AgentMonitor()

    print("[Coordinator] Spawning agents in parallel...")
    coordinator_result = coordinator.run(query)

    db_result = coordinator_result["db_result"]
    vector_result = coordinator_result["vector_result"]

    print(
        "[DB Agent] Completed in "
        f"{db_result['execution_time_ms']}ms - status: {db_result['status']}"
    )
    print(
        "[Vector Agent] Completed in "
        f"{vector_result['execution_time_ms']}ms - status: {vector_result['status']}"
    )

    consensus_result = consensus_agent.run(coordinator_result)
    print(
        "[Consensus] Merging results - confidence: "
        f"{consensus_result['confidence']}"
    )
    print(f"[Result] {consensus_result['final_response']}")
    print(f"[Monitor] Summary: {monitor.get_summary()}")

    return consensus_result


def main() -> int:
    """Execute the sample Phase 2 request and return a process exit code."""
    try:
        get_settings()
        run_phase2(SAMPLE_QUERY)
        return 0
    except Exception as exc:
        print(f"[Error] Phase 2 execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
