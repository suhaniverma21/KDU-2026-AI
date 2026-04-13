"""Buy order preparation and approval interrupt node."""

from __future__ import annotations

from app.graph.state import AgentState
from app.tools.stock_api import get_stock_quote
from app.utils.logging import log_event
from app.utils.validation import normalize_symbol, validate_approval_decision, validate_quantity
from langgraph.types import interrupt


def buy_stock_node(state: AgentState) -> AgentState:
    """Prepare a mock buy order and pause for explicit human approval."""

    if state.get("error"):
        return {"response_text": state["error"]}

    symbol = normalize_symbol(state.get("requested_symbol"))
    quantity = state.get("requested_quantity")
    cash_balance = state.get("cash_balance", 0.0)
    pending_order = state.get("pending_order")
    approval_status = state.get("approval_status")

    if approval_status == "executed":
        log_event("validation_failure", node_name="buy_stock_node", thread_id=state.get("thread_id"), approval_status=approval_status)
        return {"response_text": "This mock buy order has already been executed."}

    if pending_order and approval_status in {"cancelled", "rejected"}:
        log_event("validation_failure", node_name="buy_stock_node", thread_id=state.get("thread_id"), approval_status=approval_status)
        return {"response_text": "This pending mock order is no longer active."}

    if not symbol:
        log_event("validation_failure", node_name="buy_stock_node", thread_id=state.get("thread_id"), requested_symbol=state.get("requested_symbol"))
        return {
            "error": "Please specify a supported stock symbol such as AAPL, MSFT, or TSLA.",
            "response_text": "Please specify a supported stock symbol such as AAPL, MSFT, or TSLA.",
        }
    quantity_error = validate_quantity(quantity)
    if quantity_error:
        log_event("validation_failure", node_name="buy_stock_node", thread_id=state.get("thread_id"), requested_quantity=quantity)
        return {
            "error": quantity_error,
            "response_text": quantity_error,
        }

    quote = get_stock_quote(symbol)
    if quote["is_stale"]:
        message = (
            f"Live price data for {symbol} is unavailable right now, so I cannot prepare the buy order safely. "
            "Please try again when a fresh market quote is available."
        )
        log_event(
            "validation_failure",
            node_name="buy_stock_node",
            thread_id=state.get("thread_id"),
            requested_symbol=symbol,
            price_source=quote["source"],
        )
        return {
            "error": message,
            "response_text": message,
        }

    estimated_price = quote["price"]
    estimated_total = round(quantity * estimated_price, 2)
    remaining_cash = round(cash_balance - estimated_total, 2)

    if remaining_cash < 0:
        log_event("validation_failure", node_name="buy_stock_node", thread_id=state.get("thread_id"), requested_symbol=symbol, requested_quantity=quantity)
        return {
            "error": (
                f"Insufficient cash balance to buy {quantity} shares of {symbol}. "
                f"You need USD {estimated_total:,.2f} but only have USD {cash_balance:,.2f}."
            ),
            "response_text": (
                f"Insufficient cash balance to buy {quantity} shares of {symbol}. "
                f"You need USD {estimated_total:,.2f} but only have USD {cash_balance:,.2f}."
            ),
        }

    pending_order = {
        "symbol": symbol,
        "quantity": quantity,
        "order_type": "buy",
        "status": "pending_approval",
        "estimated_price": estimated_price,
        "estimated_total": estimated_total,
    }
    approval_prompt = {
        "symbol": symbol,
        "quantity": quantity,
        "estimated_price": estimated_price,
        "estimated_total": estimated_total,
        "remaining_cash": remaining_cash,
        "message": (
            f"Approve mock buy order for {quantity} shares of {symbol} at USD {estimated_price:,.2f} "
            f"per share for a total of USD {estimated_total:,.2f}? "
            "Reply with APPROVE to execute or CANCEL to abort."
        ),
    }
    log_event(
        "interrupt_triggered",
        node_name="buy_stock_node",
        thread_id=state.get("thread_id"),
        intent=state.get("intent"),
        requested_symbol=symbol,
        approval_status="pending",
        price_source=quote["source"],
    )
    decision = interrupt(approval_prompt)
    normalized_decision = str(decision).strip().upper()
    decision_error = validate_approval_decision(normalized_decision)
    log_event(
        "approval_received",
        node_name="buy_stock_node",
        thread_id=state.get("thread_id"),
        requested_symbol=symbol,
        approval_status=normalized_decision,
    )

    if not decision_error and normalized_decision == "APPROVE":
        return {
            "pending_order": pending_order,
            "pending_action": "buy_stock",
            "approval_status": "approved",
            "approval_decision": normalized_decision,
            "response_text": None,
        }
    if not decision_error and normalized_decision == "CANCEL":
        return {
            "pending_order": pending_order,
            "pending_action": "buy_stock",
            "approval_status": "cancelled",
            "approval_decision": normalized_decision,
            "response_text": None,
        }

    return {
        "pending_order": pending_order,
        "pending_action": "buy_stock",
        "approval_status": "rejected",
        "approval_decision": normalized_decision,
        "error": decision_error,
        "response_text": decision_error,
    }
