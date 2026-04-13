"""Foreign exchange rate tool adapters backed by a real FX API."""

from __future__ import annotations

from typing import Any

import requests

from app.config import get_settings
from app.utils.logging import log_event
from app.utils.retry import retry_call

MOCK_FX_RATES: dict[tuple[str, str], float] = {
    ("USD", "INR"): 83.20,
    ("USD", "EUR"): 0.92,
}
REQUEST_TIMEOUT_SECONDS = 10


def _build_fx_result(rate: float, *, source: str, is_stale: bool, reason: str | None = None) -> dict[str, Any]:
    """Build normalized FX metadata."""

    return {
        "rate": round(rate, 4),
        "source": source,
        "is_stale": is_stale,
        "reason": reason,
    }


def _extract_frankfurter_rate(payload: dict[str, Any], base_currency: str, target_currency: str) -> float:
    """Parse the Frankfurter latest-rates payload."""

    rates = payload.get("rates", {})
    raw_rate = rates.get(target_currency.upper())
    if raw_rate is None:
        raise RuntimeError(f"FX API did not return a rate for {base_currency}->{target_currency}.")
    return round(float(raw_rate), 4)


def _fetch_live_fx_rate(base_currency: str, target_currency: str) -> float:
    """Fetch a live FX rate from Frankfurter."""

    settings = get_settings()
    def _operation() -> float:
        response = requests.get(
            f"{settings.fx_api_base_url}/latest",
            params={
                "from": base_currency.upper(),
                "to": target_currency.upper(),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _extract_frankfurter_rate(response.json(), base_currency, target_currency)

    return retry_call(
        _operation,
        operation_name=f"fx_rate:{base_currency}->{target_currency}",
        retry_on=(requests.RequestException, RuntimeError),
    )


def get_fx_rate(base_currency: str, target_currency: str) -> float:
    """Return an FX rate using a live API when available."""

    return get_fx_quote(base_currency, target_currency)["rate"]


def get_fx_quote(base_currency: str, target_currency: str) -> dict[str, Any]:
    """Return FX data with freshness metadata."""

    normalized_pair = (base_currency.upper(), target_currency.upper())
    try:
        rate = _fetch_live_fx_rate(*normalized_pair)
        log_event("live_fx_rate_fetched", base_currency=normalized_pair[0], target_currency=normalized_pair[1], rate=rate)
        return _build_fx_result(rate, source="live", is_stale=False)
    except Exception as exc:
        if normalized_pair in MOCK_FX_RATES:
            fallback_rate = MOCK_FX_RATES[normalized_pair]
            log_event(
                "live_fx_rate_fallback",
                base_currency=normalized_pair[0],
                target_currency=normalized_pair[1],
                rate=fallback_rate,
                reason=str(exc),
            )
            return _build_fx_result(fallback_rate, source="fallback", is_stale=True, reason=str(exc))
        raise RuntimeError(f"Unable to fetch FX rate for {normalized_pair[0]}->{normalized_pair[1]}: {exc}") from exc
