"""Run a lightweight deterministic evaluation suite for the agent."""

from __future__ import annotations

from collections import Counter
from unittest.mock import patch

from app.evaluation.cases import EVALUATION_CASES
from app.evaluation.metrics import (
    is_approval_safe,
    is_extraction_correct,
    is_intent_correct,
    is_route_correct,
    response_passes,
)
from app.graph.builder import build_graph
from app.graph.nodes.llm_node import llm_node
from app.graph.routes import route_after_buy_preparation, route_after_llm, route_after_portfolio
from app.graph.state import create_initial_state


def evaluate_case(graph, case: dict) -> dict:
    """Evaluate a single prompt against the expected behavior."""

    state = create_initial_state(thread_id=f"eval-{case['name']}", user_message=case["prompt"])
    llm_updates = llm_node({"messages": state["messages"]})
    merged_state = {**state, **llm_updates}
    initial_route = route_after_llm(merged_state)
    if case.get("requires_interrupt"):
        with patch(
            "app.graph.nodes.buy_stock_node.get_stock_quote",
            return_value={"price": 172.10, "source": "live", "is_stale": False, "reason": None},
        ):
            result = graph.invoke(state, config={"configurable": {"thread_id": state["thread_id"]}})
    else:
        result = graph.invoke(state, config={"configurable": {"thread_id": state["thread_id"]}})

    post_portfolio_route = None
    if case.get("expected_post_portfolio_route"):
        post_portfolio_route = route_after_portfolio({**merged_state, "portfolio_value": result.get("portfolio_value", 0.0)})

    approval_route = None
    if case.get("expected_intent") == "buy_stock" and "approval_status" in result:
        approval_route = route_after_buy_preparation(result)

    interrupted = "__interrupt__" in result
    return {
        "name": case["name"],
        "intent_correct": is_intent_correct(merged_state.get("intent"), case["expected_intent"]),
        "extraction_correct": is_extraction_correct(merged_state, case),
        "route_correct": is_route_correct(initial_route, case["expected_route"]),
        "post_portfolio_route_correct": (
            True
            if case.get("expected_post_portfolio_route") is None
            else post_portfolio_route == case["expected_post_portfolio_route"]
        ),
        "approval_safety_correct": is_approval_safe(interrupted, case.get("requires_interrupt", False)),
        "response_pass": response_passes(result, case),
        "approval_route": approval_route,
    }


def summarize(results: list[dict]) -> Counter:
    """Summarize evaluation results into simple pass counts."""

    summary = Counter()
    for result in results:
        summary["total_cases"] += 1
        for key in (
            "intent_correct",
            "extraction_correct",
            "route_correct",
            "post_portfolio_route_correct",
            "approval_safety_correct",
            "response_pass",
        ):
            if result[key]:
                summary[key] += 1
    return summary


def main() -> None:
    """Run the evaluation suite and print a compact report."""

    graph = build_graph()
    results = [evaluate_case(graph, case) for case in EVALUATION_CASES]
    summary = summarize(results)
    total = summary["total_cases"]

    print("Stock Trading Agent Evaluation")
    print(f"Intent accuracy: {summary['intent_correct']}/{total}")
    print(f"Entity extraction accuracy: {summary['extraction_correct']}/{total}")
    print(f"Routing correctness: {summary['route_correct']}/{total}")
    print(f"Post-portfolio routing correctness: {summary['post_portfolio_route_correct']}/{total}")
    print(f"Approval safety correctness: {summary['approval_safety_correct']}/{total}")
    print(f"Response quality: {summary['response_pass']}/{total}")


if __name__ == "__main__":
    main()
