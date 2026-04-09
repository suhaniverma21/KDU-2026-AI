"""Tests for authentication endpoints."""

from __future__ import annotations

import re

import pytest
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User


def assert_error_payload(
    payload: dict,
    *,
    code: str,
    message: str | None = None,
) -> dict:
    """Validate the standardized error envelope and return the error body."""
    assert payload["success"] is False
    assert payload["error"]["code"] == code
    if message is not None:
        assert payload["error"]["message"] == message
    assert "timestamp" in payload["error"]
    assert "path" in payload["error"]
    assert "request_id" in payload["error"]
    return payload["error"]


@pytest.mark.asyncio
async def test_register_new_user_success(
    async_client,
    db_session: AsyncSession,
) -> None:
    """Registering a new user should return a safe response and persist a hashed password."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "SecurePass123!",
            "full_name": "John Doe",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "user@example.com"
    assert payload["full_name"] == "John Doe"
    assert payload["role"] == "user"
    assert payload["is_active"] is True
    assert "id" in payload
    assert "created_at" in payload
    assert "password" not in payload
    assert "hashed_password" not in payload

    result = await db_session.execute(select(User).where(User.email == "user@example.com"))
    user = result.scalar_one()
    assert user.hashed_password != "SecurePass123!"


@pytest.mark.asyncio
async def test_register_duplicate_email(async_client) -> None:
    """Registering the same email twice should return a conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "SecurePass123!",
        "full_name": "John Doe",
    }

    first = await async_client.post("/api/v1/auth/register", json=payload)
    second = await async_client.post("/api/v1/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    error = assert_error_payload(
        second.json(),
        code="EMAIL_ALREADY_REGISTERED",
        message="Email already registered",
    )
    assert error["details"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("email", ["notanemail", "missing@domain", "@example.com"])
async def test_register_invalid_email_format(async_client, email: str) -> None:
    """Invalid email formats should be rejected by validation."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePass123!",
            "full_name": "John Doe",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "password",
    ["short", "NoNumber!", "nonumberorspecial", "nospecialchar1"],
)
async def test_register_weak_password(async_client, password: str) -> None:
    """Weak passwords should return validation errors with password guidance."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": password,
            "full_name": "John Doe",
        },
    )

    assert response.status_code == 422
    details = response.json()["error"]["details"]["validation_errors"]
    assert any("password" in ".".join(map(str, item["loc"])) for item in details)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "missing_field"),
    [
        ({"password": "SecurePass123!", "full_name": "John Doe"}, "email"),
        ({"email": "user@example.com", "full_name": "John Doe"}, "password"),
        ({"email": "user@example.com", "password": "SecurePass123!"}, "full_name"),
        ({}, "email"),
    ],
)
async def test_register_missing_fields(async_client, body: dict[str, str], missing_field: str) -> None:
    """Missing required fields should return field-specific validation errors."""
    response = await async_client.post("/api/v1/auth/register", json=body)

    assert response.status_code == 422
    details = response.json()["error"]["details"]["validation_errors"]
    assert any(missing_field in ".".join(map(str, item["loc"])) for item in details)


@pytest.mark.asyncio
async def test_password_is_hashed_in_database(
    async_client,
    db_session: AsyncSession,
) -> None:
    """Passwords should be stored as bcrypt hashes in the database."""
    plain_password = "SecurePass123!"
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "hashed@example.com",
            "password": plain_password,
            "full_name": "John Doe",
        },
    )

    assert response.status_code == 201

    result = await db_session.execute(select(User).where(User.email == "hashed@example.com"))
    user = result.scalar_one()

    assert user.hashed_password != plain_password
    assert re.match(r"^\$2b\$", user.hashed_password)


@pytest.mark.asyncio
async def test_login_success(async_client) -> None:
    """Logging in with valid credentials should return a bearer token."""
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "SecurePass123!",
            "full_name": "Login User",
        },
    )

    response = await async_client.post(
        "/api/v1/auth/login",
        data={
            "username": "login@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["access_token"], str)
    assert payload["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(async_client) -> None:
    """Wrong passwords should return a generic unauthorized error."""
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@example.com",
            "password": "SecurePass123!",
            "full_name": "Wrong Password",
        },
    )

    response = await async_client.post(
        "/api/v1/auth/login",
        data={
            "username": "wrongpass@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert_error_payload(
        response.json(),
        code="UNAUTHORIZED",
        message="Incorrect email or password",
    )


@pytest.mark.asyncio
async def test_login_nonexistent_user(async_client) -> None:
    """Unknown users should receive the same generic unauthorized error."""
    response = await async_client.post(
        "/api/v1/auth/login",
        data={
            "username": "missing@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 401
    assert_error_payload(
        response.json(),
        code="UNAUTHORIZED",
        message="Incorrect email or password",
    )


@pytest.mark.asyncio
async def test_login_inactive_user(
    async_client,
    db_session: AsyncSession,
    registered_user: tuple[User, str],
) -> None:
    """Inactive users should not be able to log in."""
    user, password = registered_user
    user.is_active = False
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/auth/login",
        data={
            "username": user.email,
            "password": password,
        },
    )

    assert response.status_code == 401
    assert_error_payload(
        response.json(),
        code="UNAUTHORIZED",
        message="Incorrect email or password",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "form_data",
    [
        {"password": "SecurePass123!"},
        {"username": "user@example.com"},
    ],
)
async def test_login_missing_credentials(async_client, form_data: dict[str, str]) -> None:
    """Missing login credentials should trigger validation errors."""
    response = await async_client.post("/api/v1/auth/login", data=form_data)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_token_contains_user_id(async_client) -> None:
    """Issued JWT tokens should contain the user ID and role claims."""
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "token@example.com",
            "password": "SecurePass123!",
            "full_name": "Token User",
        },
    )

    response = await async_client.post(
        "/api/v1/auth/login",
        data={
            "username": "token@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    decoded = jwt.decode(
        payload["access_token"],
        get_settings().secret_key,
        options={"verify_signature": False},
    )
    assert "sub" in decoded
    assert "role" in decoded
