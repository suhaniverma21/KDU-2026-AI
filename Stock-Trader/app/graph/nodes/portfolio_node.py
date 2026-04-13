"""Portfolio valuation node for read-only portfolio requests."""

from __future__ import annotations

from app.graph.state import AgentState
from app.tools.stock_api import get_multiple_stock_quotes
from app.utils.logging import log_event


def _calculate_breakdown(holdings: list[dict], latest_prices: dict[str, float]) -> tuple[list[dict], float]:
    """Calculate portfolio line items and total value in base currency."""

    breakdown: list[dict] = []
    total_value = 0.0

    for holding in holdings:
        symbol = holding["symbol"]
        quantity = holding["quantity"]
        current_price = latest_prices[symbol]
        position_value = quantity * current_price
        total_value += position_value
        breakdown.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "current_price": current_price,
                "position_value": round(position_value, 2),
            }
        )

    return breakdown, round(total_value, 2)


def portfolio_node(state: AgentState) -> AgentState:
    """Calculate portfolio value from holdings and current prices."""

    holdings = state.get("holdings", [])
    if not holdings:
        log_event("node_executed", node_name="portfolio_node", thread_id=state.get("thread_id"), intent=state.get("intent"))
        return {
            "portfolio_value": 0.0,
            "portfolio_breakdown": [],
            "response_text": "Your portfolio is currently empty.",
        }

    symbols = [holding["symbol"] for holding in holdings]
    try:
        fetched_quotes = get_multiple_stock_quotes(symbols)
    except Exception as exc:
        log_event(
            "tool_failure",
            node_name="portfolio_node",
            thread_id=state.get("thread_id"),
            intent=state.get("intent"),
            error=str(exc),
        )
        return {
            "error": "Unable to fetch one or more stock prices for portfolio valuation.",
            "response_text": "Unable to fetch one or more stock prices for portfolio valuation.",
        }
    fetched_prices = {symbol: quote["price"] for symbol, quote in fetched_quotes.items()}
    latest_prices = {**state.get("latest_prices", {}), **fetched_prices}
    latest_price_metadata = {**state.get("latest_price_metadata", {}), **fetched_quotes}
    breakdown, portfolio_value = _calculate_breakdown(holdings, latest_prices)
    stale_symbols = [symbol for symbol, quote in fetched_quotes.items() if quote["is_stale"]]
    warning = None
    if stale_symbols:
        joined = ", ".join(stale_symbols)
        warning = f"Some portfolio prices are fallback data and may be stale: {joined}."
    log_event(
        "node_executed",
        node_name="portfolio_node",
        thread_id=state.get("thread_id"),
        intent=state.get("intent"),
        portfolio_value=portfolio_value,
    )
    return {
        "latest_prices": latest_prices,
        "latest_price_metadata": latest_price_metadata,
        "portfolio_breakdown": breakdown,
        "portfolio_value": portfolio_value,
        "market_data_warning": warning,
        "response_text": None,
    }
