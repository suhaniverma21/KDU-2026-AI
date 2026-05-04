"""Defines strongly typed runtime settings for the standalone Phase 2 workflow."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Stores all environment-driven configuration for the standalone Phase 2 app."""

    openai_api_key: str = Field(alias="OPENAI_API_KEY", min_length=1)
    max_workers: int = Field(default=2, alias="MAX_WORKERS", ge=1)
    agent_timeout_seconds: int = Field(
        default=10,
        alias="AGENT_TIMEOUT_SECONDS",
        ge=1,
    )
    max_retries: int = Field(default=2, alias="MAX_RETRIES", ge=0)
    log_file_path: str = Field(
        default="logs/agent_events.jsonl",
        alias="LOG_FILE_PATH",
        min_length=1,
    )
    max_log_file_size_mb: int = Field(
        default=10,
        alias="MAX_LOG_FILE_SIZE_MB",
        ge=1,
    )
    confidence_threshold: float = Field(
        default=0.7,
        alias="CONFIDENCE_THRESHOLD",
        ge=0.0,
        le=1.0,
    )
    fallback_response: str = Field(
        default="Sorry, unable to process your request.",
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
            f"max_workers={self.max_workers}, "
            f"agent_timeout_seconds={self.agent_timeout_seconds}, "
            f"max_retries={self.max_retries}, "
            f"log_file_path='{self.log_file_path}', "
            f"max_log_file_size_mb={self.max_log_file_size_mb}, "
            f"confidence_threshold={self.confidence_threshold}, "
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
        raise ValueError(f"Invalid Phase 2 settings: {exc}") from exc
