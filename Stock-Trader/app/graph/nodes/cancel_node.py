"""Pending action cancellation node."""

from __future__ import annotations

from app.graph.state import AgentState
from app.utils.logging import log_event


def cancel_node(state: AgentState) -> AgentState:
    """Cancel a pending mock trade without changing the portfolio."""

    pending_order = state.get("pending_order")
    if not pending_order:
        log_event("validation_failure", node_name="cancel_node", thread_id=state.get("thread_id"), approval_status=state.get("approval_status"))
        return {
            "approval_status": "cancelled",
            "response_text": "There is no pending order to cancel.",
        }
    symbol = pending_order["symbol"] if pending_order else "the pending"
    log_event(
        "cancellation_completed",
        node_name="cancel_node",
        thread_id=state.get("thread_id"),
        requested_symbol=symbol,
        approval_status="cancelled",
    )
    return {
        "pending_order": None,
        "pending_action": None,
        "approval_status": "cancelled",
        "response_text": f"The pending buy order for {symbol} was cancelled. No portfolio changes were made.",
    }
