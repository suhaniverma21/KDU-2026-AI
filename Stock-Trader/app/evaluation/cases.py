"""Evaluation dataset for the stock trading agent."""

from __future__ import annotations


EVALUATION_CASES = [
    {
        "name": "stock_price_lookup",
        "prompt": "What is the price of AAPL?",
        "expected_intent": "get_stock_price",
        "expected_symbol": "AAPL",
        "expected_quantity": None,
        "expected_currency": None,
        "expected_route": "tool_executor_node",
        "response_contains": ["AAPL", "latest price"],
    },
    {
        "name": "portfolio_value_in_inr",
        "prompt": "Show me my portfolio value in INR",
        "expected_intent": "get_portfolio_value",
        "expected_symbol": None,
        "expected_quantity": None,
        "expected_currency": "INR",
        "expected_route": "portfolio_node",
        "expected_post_portfolio_route": "currency_node",
        "response_contains": ["portfolio value", "INR"],
    },
    {
        "name": "buy_stock_with_approval",
        "prompt": "Buy 3 shares of TSLA",
        "expected_intent": "buy_stock",
        "expected_symbol": "TSLA",
        "expected_quantity": 3,
        "expected_currency": None,
        "expected_route": "buy_stock_node",
        "requires_interrupt": True,
    },
    {
        "name": "buy_stock_missing_quantity",
        "prompt": "Buy TSLA",
        "expected_intent": "buy_stock",
        "expected_symbol": "TSLA",
        "expected_quantity": None,
        "expected_currency": None,
        "expected_route": "reply_node",
        "expected_error_contains": "how many shares",
    },
    {
        "name": "unsupported_currency",
        "prompt": "Show me my portfolio value in GBP",
        "expected_intent": "get_portfolio_value",
        "expected_symbol": None,
        "expected_quantity": None,
        "expected_currency": None,
        "expected_route": "reply_node",
        "expected_error_contains": "Unsupported currency",
    },
]

