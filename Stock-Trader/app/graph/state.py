"""Typed graph state used across all LangGraph nodes."""

from __future__ import annotations

from typing import Literal, Optional
from typing_extensions import TypedDict


class Message(TypedDict):
    """Simple serialized conversation message."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class Holding(TypedDict):
    """Represents a portfolio holding in the mock trading system."""

    symbol: str
    quantity: int
    avg_price: float


class PendingOrder(TypedDict, total=False):
    """Represents a pending mock order that requires approval."""

    symbol: str
    quantity: int
    order_type: Literal["buy"]
    status: str
    estimated_price: float
    estimated_total: float


class AgentState(TypedDict, total=False):
    """Shared state passed to every graph node."""

    messages: list[Message]
    conversation_summary: Optional[str]
    user_id: str
    thread_id: str
    base_currency: str
    target_currency: Optional[str]
    holdings: list[Holding]
    cash_balance: float
    latest_prices: dict[str, float]
    latest_price_metadata: dict[str, dict]
    fx_rate: Optional[float]
    fx_metadata: Optional[dict]
    portfolio_value: float
    converted_value: float
    intent: str
    requested_symbol: Optional[str]
    requested_quantity: Optional[int]
    approval_decision: Optional[str]
    pending_order: Optional[PendingOrder]
    pending_action: Optional[str]
    approval_status: Optional[Literal["pending", "approved", "rejected", "cancelled", "executed"]]
    last_tool_result: Optional[dict]
    portfolio_breakdown: list[dict]
    market_data_warning: Optional[str]
    error: Optional[str]
    response_text: Optional[str]


def compact_messages(
    messages: list[Message],
    *,
    max_messages: int = 12,
    keep_recent: int = 6,
) -> tuple[list[Message], Optional[str]]:
    """Compact long conversation history into a short deterministic summary."""

    if len(messages) <= max_messages:
        return messages, None

    keep_recent = max(1, min(keep_recent, len(messages)))
    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]
    summary_parts = [
        f"{message['role']}: {message['content'][:120].replace(chr(10), ' ')}"
        for message in old_messages
    ]
    summary = "Conversation summary: " + " | ".join(summary_parts)
    compacted_messages: list[Message] = [{"role": "system", "content": summary}, *recent_messages]
    return compacted_messages, summary


def create_initial_state(
    thread_id: str,
    user_message: str,
    *,
    user_id: str = "demo-user",
    base_currency: str = "USD",
) -> AgentState:
    """Create a clean initial state for a new graph run."""

    return AgentState(
        messages=[{"role": "user", "content": user_message}],
        conversation_summary=None,
        user_id=user_id,
        thread_id=thread_id,
        base_currency=base_currency,
        target_currency=None,
        holdings=[
            {"symbol": "AAPL", "quantity": 10, "avg_price": 180.0},
            {"symbol": "MSFT", "quantity": 5, "avg_price": 390.0},
        ],
        cash_balance=5000.0,
        latest_prices={},
        latest_price_metadata={},
        fx_rate=None,
        fx_metadata=None,
        portfolio_value=0.0,
        converted_value=0.0,
        intent="general_question",
        requested_symbol=None,
        requested_quantity=None,
        approval_decision=None,
        pending_order=None,
        pending_action=None,
        approval_status=None,
        last_tool_result=None,
        portfolio_breakdown=[],
        market_data_warning=None,
        error=None,
        response_text=None,
    )
