"""Currency conversion node for read-only portfolio responses."""

from __future__ import annotations

from app.graph.state import AgentState
from app.tools.fx_api import get_fx_quote
from app.utils.logging import log_event
from app.utils.validation import normalize_currency


def currency_node(state: AgentState) -> AgentState:
    """Convert the computed portfolio value into the requested currency."""

    target_currency = state.get("target_currency")
    base_currency = state.get("base_currency", "USD")
    portfolio_value = state.get("portfolio_value", 0.0)

    if not target_currency:
        return {
            "converted_value": portfolio_value,
            "fx_rate": 1.0,
            "response_text": None,
        }

    normalized_currency = normalize_currency(target_currency)
    if not normalized_currency:
        log_event(
            "validation_failure",
            node_name="currency_node",
            thread_id=state.get("thread_id"),
            intent=state.get("intent"),
            target_currency=target_currency,
        )
        return {
            "error": f"Unsupported currency '{target_currency}'. Supported currencies are USD, INR, and EUR.",
            "response_text": f"Unsupported currency '{target_currency}'. Supported currencies are USD, INR, and EUR.",
        }

    try:
        fx_quote = get_fx_quote(base_currency, normalized_currency)
    except Exception as exc:
        log_event(
            "tool_failure",
            node_name="currency_node",
            thread_id=state.get("thread_id"),
            intent=state.get("intent"),
            target_currency=normalized_currency,
            error=str(exc),
        )
        return {
            "error": f"Unable to fetch the current FX rate for {base_currency} to {normalized_currency}.",
            "response_text": f"Unable to fetch the current FX rate for {base_currency} to {normalized_currency}.",
        }

    log_event(
        "tool_lookup",
        node_name="currency_node",
        thread_id=state.get("thread_id"),
        intent=state.get("intent"),
        target_currency=normalized_currency,
        fx_rate=fx_quote["rate"],
        source=fx_quote["source"],
    )
    warning = state.get("market_data_warning")
    if fx_quote["is_stale"]:
        fx_warning = (
            f"Live FX data is currently unavailable. The displayed {base_currency}->{normalized_currency} "
            "conversion uses fallback data and may be stale."
        )
        warning = f"{warning} {fx_warning}".strip() if warning else fx_warning
    return {
        "fx_rate": fx_quote["rate"],
        "fx_metadata": fx_quote,
        "converted_value": round(portfolio_value * fx_quote["rate"], 2),
        "market_data_warning": warning,
        "response_text": None,
    }
