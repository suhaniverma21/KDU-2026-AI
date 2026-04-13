"""Intent extraction node for read-only portfolio workflows."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import AgentState
from app.services.llm_service import extract_request_with_gemini, is_gemini_enabled
from app.utils.logging import log_event
from app.utils.validation import (
    SUPPORTED_CURRENCIES,
    SUPPORTED_SYMBOLS,
    normalize_currency,
    normalize_symbol,
    validate_quantity,
)


def _extract_symbol(message: str) -> str | None:
    """Extract a supported stock symbol from the message."""

    match = re.search(r"\b([A-Za-z]{2,5})\b", message)
    if not match:
        return None

    for token in re.findall(r"\b[A-Za-z]{2,5}\b", message):
        symbol = token.upper()
        if symbol in SUPPORTED_SYMBOLS:
            return symbol
    return None


def _extract_target_currency(message: str) -> str | None:
    """Extract a likely target currency code from the message."""

    normalized = message.upper()
    for currency in SUPPORTED_CURRENCIES:
        if currency in normalized:
            return currency

    # Avoid misreading phrases such as "to buy" as a currency request.
    if "PORTFOLIO" not in normalized and "VALUE" not in normalized and "WORTH" not in normalized:
        return None

    match = re.search(r"\b(?:IN|TO)\s+([A-Z]{3})\b", normalized)
    if match:
        return match.group(1)
    return None


def _extract_quantity(message: str) -> int | None:
    """Extract a positive integer quantity from a buy request."""

    match = re.search(r"\b(\d+)\b", message)
    if not match:
        return None

    quantity = int(match.group(1))
    return quantity if quantity > 0 else None


def _rule_based_extract(message: str) -> dict[str, Any]:
    """Deterministically extract request fields without calling an LLM."""

    normalized_message = message.lower()
    requested_symbol = _extract_symbol(message)
    extracted_currency = _extract_target_currency(message)
    requested_quantity = _extract_quantity(message)
    if "buy" in normalized_message:
        intent = "buy_stock"
    elif any(keyword in normalized_message for keyword in {"portfolio", "holdings", "worth"}):
        intent = "get_portfolio_value"
    elif any(keyword in normalized_message for keyword in {"price", "quote", "trading"}) and requested_symbol:
        intent = "get_stock_price"
    else:
        intent = "general_question"

    return {
        "intent": intent,
        "requested_symbol": requested_symbol,
        "requested_quantity": requested_quantity,
        "target_currency": extracted_currency,
        "raw_target_currency": extracted_currency,
    }


def _validate_extraction(extracted: dict[str, Any]) -> AgentState:
    """Validate and normalize extracted request fields before updating graph state."""

    intent = extracted.get("intent")
    requested_symbol = normalize_symbol(extracted.get("requested_symbol"))
    raw_quantity = extracted.get("requested_quantity")
    requested_quantity = raw_quantity if isinstance(raw_quantity, int) else None
    raw_target_currency = extracted.get("raw_target_currency", extracted.get("target_currency"))
    target_currency = normalize_currency(raw_target_currency)

    updates: AgentState = {
        "intent": intent if intent in {"get_portfolio_value", "get_stock_price", "buy_stock", "general_question"} else "general_question",
        "requested_symbol": requested_symbol,
        "requested_quantity": requested_quantity,
        "target_currency": target_currency,
        "response_text": None,
        "error": None,
    }

    if raw_target_currency and not target_currency:
        updates["error"] = (
            f"Unsupported currency '{raw_target_currency}'. Supported currencies are USD, INR, and EUR."
        )

    if updates["intent"] == "get_stock_price" and not requested_symbol:
        updates["intent"] = "general_question"
        updates["error"] = "Please specify a supported stock symbol such as AAPL, MSFT, or TSLA."

    if updates["intent"] == "buy_stock":
        if not requested_symbol:
            updates["error"] = "Please specify a supported stock symbol such as AAPL, MSFT, or TSLA."
        else:
            quantity_error = validate_quantity(requested_quantity)
            if quantity_error:
                updates["error"] = quantity_error

    return updates


def llm_node(state: AgentState) -> AgentState:
    """Classify the latest user message, preferring Gemini with a safe fallback."""

    messages = state.get("messages", [])
    latest_message = messages[-1]["content"] if messages else ""
    extraction_source = "rule_based"

    if is_gemini_enabled():
        try:
            gemini_result = extract_request_with_gemini(latest_message)
            updates = _validate_extraction(gemini_result)
            extraction_source = "gemini"
        except Exception as exc:  # pragma: no cover - exercised via unit tests with monkeypatch
            log_event(
                "gemini_extraction_failed",
                thread_id=state.get("thread_id"),
                error=str(exc),
            )
            updates = _validate_extraction(_rule_based_extract(latest_message))
    else:
        updates = _validate_extraction(_rule_based_extract(latest_message))

    log_event(
        "node_executed",
        node_name="llm_node",
        thread_id=state.get("thread_id"),
        intent=updates.get("intent"),
        extraction_source=extraction_source,
        requested_symbol=updates.get("requested_symbol"),
        target_currency=updates.get("target_currency"),
        error=updates.get("error"),
    )

    return updates
