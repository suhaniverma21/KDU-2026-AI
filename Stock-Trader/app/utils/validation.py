"""Validation helpers shared across nodes."""

from __future__ import annotations


SUPPORTED_SYMBOLS = {"AAPL", "MSFT", "TSLA"}
SUPPORTED_CURRENCIES = {"USD", "INR", "EUR"}
SUPPORTED_APPROVAL_DECISIONS = {"APPROVE", "CANCEL"}


def normalize_symbol(symbol: str | None) -> str | None:
    """Normalize and validate a stock symbol."""

    if not symbol:
        return None
    normalized = symbol.strip().upper()
    return normalized if normalized in SUPPORTED_SYMBOLS else None


def validate_quantity(quantity: int | None) -> str | None:
    """Validate that quantity is a positive integer."""

    if quantity is None:
        return "Please specify how many shares you want to buy."
    if quantity <= 0:
        return "Quantity must be a positive whole number."
    return None


def normalize_currency(currency: str | None) -> str | None:
    """Normalize and validate a supported currency code."""

    if not currency:
        return None
    normalized = currency.strip().upper()
    return normalized if normalized in SUPPORTED_CURRENCIES else None


def validate_approval_decision(decision: str | None) -> str | None:
    """Validate a human approval decision."""

    if not decision:
        return "Approval decision must be either APPROVE or CANCEL."
    normalized = decision.strip().upper()
    if normalized not in SUPPORTED_APPROVAL_DECISIONS:
        return "Approval decision must be either APPROVE or CANCEL."
    return None

