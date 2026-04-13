"""Demo and CLI entrypoint for the LangGraph stock trading agent."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable

from app.config import get_settings
from app.graph.builder import build_graph
from app.observability.tracing import configure_langsmith, is_langsmith_enabled
from app.graph.state import create_initial_state
from app.utils.logging import log_event, set_log_level
from langgraph.types import Command


def _format_money(value: float, currency: str = "USD") -> str:
    """Format a currency value for display."""

    return f"{currency} {value:,.2f}"


def _extract_interrupt_payload(result: dict) -> dict | None:
    """Return the first interrupt payload when a graph pauses."""

    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None
    first = interrupts[0]
    return getattr(first, "value", None)


def _print_section(title: str) -> None:
    """Print a simple section header."""

    print(f"\n=== {title} ===")


def _print_result_summary(result: dict) -> None:
    """Print a concise summary of graph output."""

    interrupt_payload = _extract_interrupt_payload(result)
    if interrupt_payload:
        print("Agent: Approval required for a mock buy order.")
        print(f"  Symbol: {interrupt_payload['symbol']}")
        print(f"  Quantity: {interrupt_payload['quantity']}")
        print(f"  Estimated price: {_format_money(interrupt_payload['estimated_price'])}")
        print(f"  Estimated total: {_format_money(interrupt_payload['estimated_total'])}")
        print(f"  Remaining cash after buy: {_format_money(interrupt_payload['remaining_cash'])}")
        print("  Reply with APPROVE or CANCEL.")
        return

    response_text = result.get("response_text")
    if response_text:
        print(f"Agent: {response_text}")
        return

    print(json.dumps(result, indent=2, default=str))


def _invoke_message(graph, thread_id: str, user_message: str, base_currency: str) -> dict:
    """Invoke the graph with a new user message."""

    log_event("graph_run_start", thread_id=thread_id, user_message=user_message)
    initial_state = create_initial_state(
        thread_id=thread_id,
        user_message=user_message,
        base_currency=base_currency,
    )
    return graph.invoke(initial_state, config={"configurable": {"thread_id": thread_id}})


def _invoke_resume(graph, thread_id: str, decision: str) -> dict:
    """Resume a paused thread with an approval decision."""

    return graph.invoke(Command(resume=decision), config={"configurable": {"thread_id": thread_id}})


def run_demo() -> None:
    """Run a guided demo covering all key capabilities."""

    settings = get_settings()
    tracing_metadata = configure_langsmith()
    graph = build_graph(checkpoint_path=settings.checkpoint_path)
    if tracing_metadata:
        print(f"LangSmith tracing enabled for project: {tracing_metadata['project']}")
    scenarios: Iterable[tuple[str, str, str]] = [
        ("Stock Price Lookup", "demo-price-thread", "What is the price of AAPL?"),
        ("Portfolio Valuation", "demo-portfolio-thread", "What is my portfolio value?"),
        ("Portfolio Valuation In INR", "demo-inr-thread", "Show me my portfolio value in INR"),
    ]

    for title, thread_id, user_message in scenarios:
        _print_section(title)
        print(f"User: {user_message}")
        result = _invoke_message(graph, thread_id, user_message, settings.default_base_currency)
        _print_result_summary(result)

    _print_section("Buy Flow With Approval")
    print("User: Buy 3 shares of TSLA")
    interrupted = _invoke_message(graph, "demo-buy-thread", "Buy 3 shares of TSLA", settings.default_base_currency)
    _print_result_summary(interrupted)
    print("User: APPROVE")
    approved = _invoke_resume(graph, "demo-buy-thread", "APPROVE")
    _print_result_summary(approved)

    _print_section("Buy Flow With Cancellation")
    print("User: Buy 2 shares of AAPL")
    interrupted_cancel = _invoke_message(
        graph,
        "demo-cancel-thread",
        "Buy 2 shares of AAPL",
        settings.default_base_currency,
    )
    _print_result_summary(interrupted_cancel)
    print("User: CANCEL")
    cancelled = _invoke_resume(graph, "demo-cancel-thread", "CANCEL")
    _print_result_summary(cancelled)


def run_interactive_cli() -> None:
    """Run a simple terminal chat loop using a single thread."""

    settings = get_settings()
    tracing_metadata = configure_langsmith()
    graph = build_graph(checkpoint_path=settings.checkpoint_path)
    thread_id = "interactive-thread"
    awaiting_resume = False

    _print_section("Interactive Mode")
    if tracing_metadata:
        print(f"LangSmith tracing enabled for project: {tracing_metadata['project']}")
    print("Type a request such as 'What is the price of AAPL?' or 'Buy 3 shares of TSLA'.")
    print("If the graph pauses for approval, reply with APPROVE or CANCEL.")
    print("Type EXIT to quit.")

    while True:
        user_message = input("\nYou: ").strip()
        if not user_message:
            continue
        if user_message.upper() in {"EXIT", "QUIT"}:
            print("Session ended.")
            break

        if awaiting_resume:
            result = _invoke_resume(graph, thread_id, user_message.upper())
        else:
            result = _invoke_message(graph, thread_id, user_message, settings.default_base_currency)

        _print_result_summary(result)
        awaiting_resume = _extract_interrupt_payload(result) is not None


def main() -> None:
    """Parse CLI arguments and run either the guided demo or interactive mode."""

    parser = argparse.ArgumentParser(description="LangGraph stock trading agent demo")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run a simple interactive CLI instead of the guided demo.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show structured debug logs during the demo or interactive session.",
    )
    args = parser.parse_args()

    if args.verbose:
        set_log_level(logging.INFO)
    else:
        set_log_level(logging.WARNING)

    if args.verbose and is_langsmith_enabled():
        log_event("langsmith_tracing_requested")

    if args.interactive:
        run_interactive_cli()
    else:
        run_demo()


if __name__ == "__main__":
    main()
