"""Defines strongly typed runtime settings for the standalone Phase 3 project."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Stores all environment-driven configuration for scaling, queueing, and cost control."""

    openai_api_key: str = Field(alias="OPENAI_API_KEY", min_length=1)
    max_concurrent_users: int = Field(
        default=100,
        alias="MAX_CONCURRENT_USERS",
        ge=1,
    )
    max_concurrent_db_requests: int = Field(
        default=10,
        alias="MAX_CONCURRENT_DB_REQUESTS",
        ge=1,
    )
    max_queue_wait_seconds: int = Field(
        default=5,
        alias="MAX_QUEUE_WAIT_SECONDS",
        ge=1,
    )
    max_tokens_per_handoff: int = Field(
        default=2000,
        alias="MAX_TOKENS_PER_HANDOFF",
        ge=1,
    )
    summary_keep_last_n_exchanges: int = Field(
        default=5,
        alias="SUMMARY_KEEP_LAST_N_EXCHANGES",
        ge=1,
    )
    log_file_path: str = Field(
        default="logs/phase3_events.jsonl",
        alias="LOG_FILE_PATH",
        min_length=1,
    )
    max_log_file_size_mb: int = Field(
        default=10,
        alias="MAX_LOG_FILE_SIZE_MB",
        ge=1,
    )
    cost_per_input_token: float = Field(
        default=0.00000015,
        alias="COST_PER_INPUT_TOKEN",
        ge=0.0,
    )
    cost_per_output_token: float = Field(
        default=0.0000006,
        alias="COST_PER_OUTPUT_TOKEN",
        ge=0.0,
    )
    fallback_response: str = Field(
        default="System is busy, please try again.",
        alias="FALLBACK_RESPONSE",
        min_length=1,
    )

    model_config = SettingsConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_api_key(cls, value: str) -> str:
        """Ensure the OpenAI API key is present and not just whitespace."""
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("OPENAI_API_KEY is required and cannot be empty.")
        return cleaned_value

    @field_validator("log_file_path", "fallback_response")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        """Ensure required string settings are not blank after trimming."""
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("String settings cannot be blank.")
        return cleaned_value

    def __repr__(self) -> str:
        """Return a debug-safe representation that masks the API key."""
        masked_key = _mask_secret(self.openai_api_key)
        return (
            "Settings("
            f"openai_api_key='{masked_key}', "
            f"max_concurrent_users={self.max_concurrent_users}, "
            f"max_concurrent_db_requests={self.max_concurrent_db_requests}, "
            f"max_queue_wait_seconds={self.max_queue_wait_seconds}, "
            f"max_tokens_per_handoff={self.max_tokens_per_handoff}, "
            f"summary_keep_last_n_exchanges={self.summary_keep_last_n_exchanges}, "
            f"log_file_path='{self.log_file_path}', "
            f"max_log_file_size_mb={self.max_log_file_size_mb}, "
            f"cost_per_input_token={self.cost_per_input_token}, "
            f"cost_per_output_token={self.cost_per_output_token}, "
            f"fallback_response='{self.fallback_response}'"
            ")"
        )


def _mask_secret(secret: str) -> str:
    """Mask a secret value for safe display in logs and repr output."""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load `.env`, validate settings, and return a cached settings instance."""
    env_path = Path.cwd() / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
    try:
        return Settings()
    except ValidationError as exc:
        raise ValueError(f"Invalid Phase 3 settings: {exc}") from exc
