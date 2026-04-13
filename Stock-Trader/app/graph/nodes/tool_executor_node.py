"""Tool execution node for mocked stock price lookups."""

from __future__ import annotations

from app.graph.state import AgentState
from app.tools.stock_api import get_stock_quote
from app.utils.logging import log_event
from app.utils.validation import normalize_symbol


def tool_executor_node(state: AgentState) -> AgentState:
    """Fetch stock data for direct price lookup requests."""

    symbol = state.get("requested_symbol")
    normalized_symbol = normalize_symbol(symbol)
    if not normalized_symbol:
        log_event(
            "validation_failure",
            node_name="tool_executor_node",
            thread_id=state.get("thread_id"),
            intent=state.get("intent"),
            requested_symbol=symbol,
        )
        return {
            "error": "Please specify a supported stock symbol such as AAPL, MSFT, or TSLA.",
            "response_text": "I need a supported stock symbol like AAPL, MSFT, or TSLA to look up a price.",
        }

    try:
        quote = get_stock_quote(normalized_symbol)
    except Exception as exc:
        log_event(
            "tool_failure",
            node_name="tool_executor_node",
            thread_id=state.get("thread_id"),
            intent=state.get("intent"),
            requested_symbol=normalized_symbol,
            error=str(exc),
        )
        return {
            "error": f"Unable to fetch the current price for {normalized_symbol}.",
            "response_text": f"Unable to fetch the current price for {normalized_symbol}.",
        }

    log_event(
        "tool_lookup",
        node_name="tool_executor_node",
        thread_id=state.get("thread_id"),
        intent=state.get("intent"),
        requested_symbol=normalized_symbol,
        price=quote["price"],
        source=quote["source"],
    )
    warning = None
    if quote["is_stale"]:
        warning = (
            f"Live price data is currently unavailable. The displayed price for {normalized_symbol} "
            "is fallback data and may be stale."
        )
    return {
        "latest_prices": {**state.get("latest_prices", {}), normalized_symbol: quote["price"]},
        "latest_price_metadata": {**state.get("latest_price_metadata", {}), normalized_symbol: quote},
        "last_tool_result": {"symbol": normalized_symbol, "price": quote["price"], "source": quote["source"]},
        "market_data_warning": warning,
        "response_text": None,
    }
