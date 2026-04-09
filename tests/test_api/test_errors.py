"""Error response format tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.user_service import UserService


def assert_standard_error(
    payload: dict,
    *,
    code: str,
    message: str,
    path: str,
) -> dict:
    """Validate the shared API error structure."""
    assert payload["success"] is False
    error = payload["error"]
    assert error["code"] == code
    assert error["message"] == message
    assert error["path"] == path
    assert "timestamp" in error
    assert "request_id" in error
    return error


@pytest.mark.asyncio
async def test_404_error_format(async_client: AsyncClient) -> None:
    """Unknown routes should return the shared error envelope."""
    response = await async_client.get("/api/v1/nonexistent")

    assert response.status_code == 404
    error = assert_standard_error(
        response.json(),
        code="RESOURCE_NOT_FOUND",
        message="Not Found",
        path="/api/v1/nonexistent",
    )
    assert error["details"] == {}


@pytest.mark.asyncio
async def test_validation_error_format(async_client: AsyncClient) -> None:
    """Validation errors should be normalized into the shared error envelope."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "invalid-email", "password": "weak", "full_name": ""},
    )

    assert response.status_code == 422
    error = assert_standard_error(
        response.json(),
        code="VALIDATION_ERROR",
        message="Request validation failed",
        path="/api/v1/auth/register",
    )
    assert "validation_errors" in error["details"]
    assert isinstance(error["details"]["validation_errors"], list)


@pytest.mark.asyncio
async def test_http_exception_error_format(async_client: AsyncClient) -> None:
    """HTTP exceptions should be wrapped in the shared error envelope."""
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "missing@example.com", "password": "SecurePass123!"},
    )

    assert response.status_code == 401
    assert_standard_error(
        response.json(),
        code="UNAUTHORIZED",
        message="Incorrect email or password",
        path="/api/v1/auth/login",
    )


@pytest.mark.asyncio
async def test_custom_exception_error_format(async_client: AsyncClient) -> None:
    """Custom business exceptions should use the shared error envelope."""
    payload = {
        "email": "duplicate@example.com",
        "password": "SecurePass123!",
        "full_name": "Duplicate User",
    }
    await async_client.post("/api/v1/auth/register", json=payload)
    response = await async_client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 409
    assert_standard_error(
        response.json(),
        code="EMAIL_ALREADY_REGISTERED",
        message="Email already registered",
        path="/api/v1/auth/register",
    )


@pytest.mark.asyncio
async def test_generic_500_error_format(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected errors should be hidden behind a safe 500 response."""

    async def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(UserService, "create_user", explode)
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "error@example.com",
            "password": "SecurePass123!",
            "full_name": "Error User",
        },
    )

    assert response.status_code == 500
    error = assert_standard_error(
        response.json(),
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        path="/api/v1/auth/register",
    )
    assert error["details"] == {}
