"""Buy execution node for approved mock trades."""

from __future__ import annotations

from app.graph.state import AgentState
from app.utils.logging import log_event


def execute_buy_node(state: AgentState) -> AgentState:
    """Execute an approved mock buy order exactly once."""

    pending_order = state.get("pending_order")
    if not pending_order:
        log_event("validation_failure", node_name="execute_buy_node", thread_id=state.get("thread_id"), approval_status=state.get("approval_status"))
        return {"response_text": "There is no pending order to execute."}

    if pending_order.get("status") == "executed" or state.get("approval_status") == "executed":
        log_event("validation_failure", node_name="execute_buy_node", thread_id=state.get("thread_id"), approval_status=state.get("approval_status"))
        return {"response_text": "This mock buy order has already been executed."}

    if state.get("approval_status") != "approved":
        log_event("validation_failure", node_name="execute_buy_node", thread_id=state.get("thread_id"), approval_status=state.get("approval_status"))
        return {"response_text": "This mock buy order has not been approved for execution."}

    symbol = pending_order["symbol"]
    quantity = pending_order["quantity"]
    estimated_price = pending_order["estimated_price"]
    estimated_total = pending_order["estimated_total"]
    existing_holdings = [dict(holding) for holding in state.get("holdings", [])]
    cash_balance = round(state.get("cash_balance", 0.0) - estimated_total, 2)

    holding_updated = False
    for holding in existing_holdings:
        if holding["symbol"] == symbol:
            combined_quantity = holding["quantity"] + quantity
            total_cost_basis = (holding["avg_price"] * holding["quantity"]) + estimated_total
            holding["quantity"] = combined_quantity
            holding["avg_price"] = round(total_cost_basis / combined_quantity, 2)
            holding_updated = True
            break

    if not holding_updated:
        existing_holdings.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "avg_price": estimated_price,
            }
        )

    executed_order = dict(pending_order)
    executed_order["status"] = "executed"
    log_event(
        "execution_completed",
        node_name="execute_buy_node",
        thread_id=state.get("thread_id"),
        requested_symbol=symbol,
        approval_status="executed",
    )
    return {
        "holdings": existing_holdings,
        "cash_balance": cash_balance,
        "pending_order": None,
        "pending_action": None,
        "approval_status": "executed",
        "response_text": (
            f"Buy order executed successfully. Purchased {quantity} shares of {symbol} "
            f"at USD {estimated_price:,.2f} each for a total of USD {estimated_total:,.2f}. "
            f"Remaining cash balance: USD {cash_balance:,.2f}."
        ),
        "last_tool_result": {"executed_order": executed_order},
    }
