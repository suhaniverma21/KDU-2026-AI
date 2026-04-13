"""Pure routing helpers for the LangGraph workflow."""

from __future__ import annotations

from app.graph.state import AgentState


def route_after_llm(state: AgentState) -> str:
    """Route based on the classified user intent."""

    if state.get("error"):
        return "reply_node"
    intent = state.get("intent", "general_question")

    if intent == "get_portfolio_value":
        return "portfolio_node"
    if intent == "get_stock_price":
        return "tool_executor_node"
    if intent == "buy_stock":
        return "buy_stock_node"
    return "reply_node"


def route_after_portfolio(state: AgentState) -> str:
    """Route to currency conversion only when needed."""

    if state.get("error"):
        return "reply_node"
    target_currency = state.get("target_currency")
    base_currency = state.get("base_currency", "USD")

    if not target_currency or target_currency == base_currency:
        return "reply_node"
    if target_currency in {"INR", "EUR"}:
        return "currency_node"

    return "reply_node"


def route_after_buy_preparation(state: AgentState) -> str:
    """Choose the next step once a buy request has been prepared."""

    if state.get("error"):
        return "reply_node"
    approval_status = state.get("approval_status")
    if approval_status == "approved":
        return "execute_buy_node"
    if approval_status in {"rejected", "cancelled"}:
        return "cancel_node"
    return "reply_node"
