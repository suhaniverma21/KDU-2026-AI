"""RBAC endpoint tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_new_user_has_default_user_role(async_client: AsyncClient) -> None:
    """Newly registered users should have the default user role."""
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "full_name": "New User",
        },
    )
    login_response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "newuser@example.com", "password": "SecurePass123!"},
    )

    token = login_response.json()["access_token"]
    response = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "user"


@pytest.mark.asyncio
async def test_admin_can_list_all_users(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    """Admins should be able to list users."""
    response = await async_client.get("/api/v1/admin/users", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload
    assert "page" in payload
    assert "size" in payload
    assert "pages" in payload
    assert isinstance(payload["items"], list)


@pytest.mark.asyncio
async def test_regular_user_cannot_list_all_users(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Regular users should be forbidden from admin listing endpoints."""
    response = await async_client.get("/api/v1/admin/users", headers=auth_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_delete_user(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    registered_user: tuple[User, str],
    db_session: AsyncSession,
) -> None:
    """Admins should be able to delete another user."""
    user, _ = registered_user

    response = await async_client.delete(
        f"/api/v1/admin/users/{user.id}",
        headers=admin_headers,
    )

    assert response.status_code == 204
    result = await db_session.execute(select(User).where(User.id == user.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_user_cannot_delete_users(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    registered_user: tuple[User, str],
) -> None:
    """Regular users should be forbidden from deleting users."""
    user, _ = registered_user

    response = await async_client.delete(
        f"/api/v1/admin/users/{user.id}",
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_user_role(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    registered_user: tuple[User, str],
    db_session: AsyncSession,
) -> None:
    """Admins should be able to update another user's role."""
    user, _ = registered_user

    response = await async_client.patch(
        f"/api/v1/admin/users/{user.id}/role",
        json={"role": "admin"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    result = await db_session.execute(select(User).where(User.id == user.id))
    updated_user = result.scalar_one()
    assert updated_user.role == "admin"


@pytest.mark.asyncio
async def test_user_cannot_update_roles(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    registered_user: tuple[User, str],
) -> None:
    """Regular users should be forbidden from updating roles."""
    user, _ = registered_user

    response = await async_client.patch(
        f"/api/v1/admin/users/{user.id}/role",
        json={"role": "admin"},
        headers=auth_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_invalid_role_rejected(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    registered_user: tuple[User, str],
) -> None:
    """Role updates should reject unsupported role values."""
    user, _ = registered_user

    response = await async_client.patch(
        f"/api/v1/admin/users/{user.id}/role",
        json={"role": "superuser"},
        headers=admin_headers,
    )

    assert response.status_code == 422

