"""Tests for protected user endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

import pytest
from jose import jwt

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_get_current_user_success(async_client, auth_headers: dict[str, str]) -> None:
    """A valid bearer token should return the current user profile."""
    response = await async_client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert "id" in payload
    assert payload["email"] == "authuser@example.com"
    assert payload["full_name"] == "Auth User"
    assert payload["role"] == "user"
    assert payload["is_active"] is True
    assert "created_at" in payload
    assert "password" not in payload
    assert "hashed_password" not in payload


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(async_client) -> None:
    """Invalid tokens should be rejected."""
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_expired_token(async_client) -> None:
    """Expired tokens should be rejected."""
    settings = get_settings()
    expired_token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000000",
            "role": "user",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    response = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_without_token(async_client) -> None:
    """Missing bearer tokens should be rejected."""
    response = await async_client.get("/api/v1/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_malformed_token(async_client) -> None:
    """Malformed tokens should be rejected."""
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer not.a.valid.jwt.token"},
    )

    assert response.status_code == 401
