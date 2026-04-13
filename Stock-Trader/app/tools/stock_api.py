"""Stock price tool adapters backed by a real market data API."""

from __future__ import annotations

from typing import Any

import requests

from app.config import get_settings
from app.utils.logging import log_event
from app.utils.retry import retry_call

MOCK_STOCK_PRICES: dict[str, float] = {
    "AAPL": 195.40,
    "MSFT": 421.85,
    "TSLA": 172.10,
}

REQUEST_TIMEOUT_SECONDS = 10


def _build_quote(price: float, *, source: str, is_stale: bool, reason: str | None = None) -> dict[str, Any]:
    """Build normalized stock quote metadata."""

    return {
        "price": round(price, 2),
        "source": source,
        "is_stale": is_stale,
        "reason": reason,
    }


def _extract_twelve_data_price(payload: dict[str, Any], symbol: str) -> float:
    """Parse the Twelve Data /price payload."""

    if payload.get("status") == "error":
        message = payload.get("message", "Unknown error")
        raise RuntimeError(f"Stock API returned an error for {symbol}: {message}")

    raw_price = payload.get("price")
    if raw_price is None:
        raise RuntimeError(f"Stock API did not return a price for {symbol}.")

    return round(float(raw_price), 2)


def _fetch_live_stock_price(symbol: str) -> float:
    """Fetch a live stock price from Twelve Data."""

    settings = get_settings()
    if not settings.twelve_data_api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY is not configured.")

    def _operation() -> float:
        response = requests.get(
            f"{settings.twelve_data_base_url}/price",
            params={
                "symbol": symbol,
                "apikey": settings.twelve_data_api_key,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _extract_twelve_data_price(response.json(), symbol)

    return retry_call(
        _operation,
        operation_name=f"stock_price:{symbol}",
        retry_on=(requests.RequestException, RuntimeError),
    )


def get_stock_price(symbol: str) -> float:
    """Return a stock price for the given symbol using a live API when configured."""

    return get_stock_quote(symbol)["price"]


def get_stock_quote(symbol: str) -> dict[str, Any]:
    """Return stock quote data with freshness metadata."""

    normalized_symbol = symbol.upper()
    try:
        price = _fetch_live_stock_price(normalized_symbol)
        log_event("live_stock_price_fetched", symbol=normalized_symbol, price=price)
        return _build_quote(price, source="live", is_stale=False)
    except Exception as exc:
        if normalized_symbol in MOCK_STOCK_PRICES:
            fallback_price = MOCK_STOCK_PRICES[normalized_symbol]
            log_event(
                "live_stock_price_fallback",
                symbol=normalized_symbol,
                price=fallback_price,
                reason=str(exc),
            )
            return _build_quote(fallback_price, source="fallback", is_stale=True, reason=str(exc))
        raise RuntimeError(f"Unable to fetch a stock price for {normalized_symbol}: {exc}") from exc


def get_multiple_stock_prices(symbols: list[str]) -> dict[str, float]:
    """Return stock prices for a list of symbols."""

    return {symbol.upper(): get_stock_quote(symbol)["price"] for symbol in symbols}


def get_multiple_stock_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Return stock quotes with freshness metadata for a list of symbols."""

    return {symbol.upper(): get_stock_quote(symbol) for symbol in symbols}
