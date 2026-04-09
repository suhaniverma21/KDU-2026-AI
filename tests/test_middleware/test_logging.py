"""Structured logging middleware tests."""

from __future__ import annotations

import logging
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.logging import JsonFormatter, TextFormatter, resolve_log_formatter, resolve_log_level


@pytest.mark.asyncio
async def test_request_id_generated(async_client: AsyncClient) -> None:
    """Each response should include a valid request identifier."""
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert "x-request-id" in response.headers
    UUID(response.headers["x-request-id"])


class _ListHandler(logging.Handler):
    """Collect log records in memory for deterministic assertions."""

    def __init__(self) -> None:
        """Initialize the internal record store."""
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store each emitted log record."""
        self.records.append(record)


@pytest.mark.asyncio
async def test_request_logged(async_client: AsyncClient) -> None:
    """Completed requests should be emitted as structured log records."""
    logger = logging.getLogger("app.request")
    list_handler = _ListHandler()
    logger.addHandler(list_handler)
    logger.setLevel(logging.INFO)

    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "loguser@example.com",
            "password": "SecurePass123!",
            "full_name": "Log User",
        },
    )

    try:
        assert response.status_code == 201
        matching_records = [
            record
            for record in list_handler.records
            if getattr(record, "path", None) == "/api/v1/auth/register"
        ]

        assert matching_records
        record = matching_records[-1]
        assert record.method == "POST"
        assert record.path == "/api/v1/auth/register"
        assert record.status_code == 201
    finally:
        logger.removeHandler(list_handler)


def test_logging_configuration_is_environment_aware() -> None:
    """Logging format and level should change predictably by environment."""
    base_settings = Settings(_env_file=None, secret_key="x" * 64)
    production_settings = base_settings.model_copy(
        update={"environment": "production", "log_format": "auto"}
    )
    development_settings = base_settings.model_copy(
        update={"environment": "development", "log_format": "auto"}
    )
    test_settings = base_settings.model_copy(update={"environment": "test", "log_format": "auto"})

    assert isinstance(resolve_log_formatter(production_settings), JsonFormatter)
    assert isinstance(resolve_log_formatter(development_settings), TextFormatter)
    assert isinstance(resolve_log_formatter(test_settings), TextFormatter)
    assert resolve_log_level(test_settings) >= resolve_log_level(development_settings)
