"""Final response formatting node."""

from __future__ import annotations

from app.config import get_settings
from app.graph.state import AgentState
from app.graph.state import compact_messages
from app.utils.logging import log_event


def _format_currency(value: float, currency: str) -> str:
    """Format a numeric value for display."""

    return f"{currency} {value:,.2f}"


def reply_node(state: AgentState) -> AgentState:
    """Create a user-facing reply based on structured graph state."""

    error = state.get("error")
    if error:
        response_text = error
    elif state.get("intent") == "get_stock_price" and state.get("requested_symbol"):
        symbol = state["requested_symbol"]
        price = state.get("latest_prices", {}).get(symbol)
        price_metadata = state.get("latest_price_metadata", {}).get(symbol, {})
        currency = state.get("base_currency", "USD")
        if price_metadata.get("is_stale"):
            response_text = (
                f"Live price data is unavailable right now. The fallback price for {symbol} is "
                f"{_format_currency(price or 0.0, currency)}, and it may be stale."
            )
        else:
            response_text = (
                f"The latest price for {symbol} is {_format_currency(price or 0.0, currency)}."
            )
    elif state.get("intent") == "get_portfolio_value":
        base_currency = state.get("base_currency", "USD")
        portfolio_value = state.get("portfolio_value", 0.0)
        target_currency = state.get("target_currency")
        warning = state.get("market_data_warning")

        if target_currency and target_currency != base_currency:
            converted_value = state.get("converted_value", 0.0)
            fx_rate = state.get("fx_rate", 1.0)
            response_text = (
                f"Your portfolio value is {_format_currency(portfolio_value, base_currency)}, "
                f"which is approximately {_format_currency(converted_value, target_currency)} "
                f"at an exchange rate of 1 {base_currency} = {fx_rate:.2f} {target_currency}."
            )
        else:
            response_text = f"Your portfolio value is {_format_currency(portfolio_value, base_currency)}."
        if warning:
            response_text = f"{response_text} Note: {warning}"
    elif state.get("intent") == "buy_stock" and state.get("response_text"):
        response_text = state["response_text"]
    else:
        response_text = (
            "I can help with stock price lookups and portfolio valuation. "
            "Try asking for the price of AAPL, your portfolio value in INR, or to buy 3 shares of AAPL."
        )

    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": response_text})
    settings = get_settings()
    compacted_messages, conversation_summary = compact_messages(
        messages,
        max_messages=settings.message_history_limit,
        keep_recent=settings.message_history_keep_recent,
    )
    log_event(
        "node_executed",
        node_name="reply_node",
        thread_id=state.get("thread_id"),
        intent=state.get("intent"),
        approval_status=state.get("approval_status"),
        messages_compacted=conversation_summary is not None,
    )
    return {
        "messages": compacted_messages,
        "conversation_summary": conversation_summary or state.get("conversation_summary"),
        "response_text": response_text,
    }
