"""Application configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    """Runtime settings for the stock trading agent."""

    app_name: str = "langgraph-stock-trader"
    default_base_currency: str = "USD"
    checkpoint_path: str = "data/checkpoints.sqlite"
    environment: str = "development"
    google_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    twelve_data_api_key: str = ""
    twelve_data_base_url: str = "https://api.twelvedata.com"
    fx_api_base_url: str = "https://api.frankfurter.app"
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "stock-trader-agent"
    api_retry_attempts: int = 3
    api_retry_base_delay_seconds: float = 0.25
    message_history_limit: int = 12
    message_history_keep_recent: int = 6


def get_settings() -> Settings:
    """Load settings from environment variables with safe defaults."""

    return Settings(
        app_name=os.getenv("APP_NAME", "langgraph-stock-trader"),
        default_base_currency=os.getenv("DEFAULT_BASE_CURRENCY", "USD"),
        checkpoint_path=os.getenv("CHECKPOINT_PATH", "data/checkpoints.sqlite"),
        environment=os.getenv("ENVIRONMENT", "development"),
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        twelve_data_api_key=os.getenv("TWELVE_DATA_API_KEY", ""),
        twelve_data_base_url=os.getenv("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com"),
        fx_api_base_url=os.getenv("FX_API_BASE_URL", "https://api.frankfurter.app"),
        langsmith_api_key=os.getenv("LANGSMITH_API_KEY", ""),
        langsmith_tracing=os.getenv("LANGSMITH_TRACING", "false").strip().lower() in {"1", "true", "yes", "on"},
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "stock-trader-agent"),
        api_retry_attempts=int(os.getenv("API_RETRY_ATTEMPTS", "3")),
        api_retry_base_delay_seconds=float(os.getenv("API_RETRY_BASE_DELAY_SECONDS", "0.25")),
        message_history_limit=int(os.getenv("MESSAGE_HISTORY_LIMIT", "12")),
        message_history_keep_recent=int(os.getenv("MESSAGE_HISTORY_KEEP_RECENT", "6")),
    )
