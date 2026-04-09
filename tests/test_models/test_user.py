"""Tests for the user database model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest

from app.models.user import User


@pytest.mark.asyncio
async def test_user_model_creation(db_session) -> None:
    """A user should persist with expected defaults and generated fields."""
    user = User(
        email="john@example.com",
        hashed_password="hashed-password",
        full_name="John Doe",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert isinstance(user.id, UUID)
    assert user.email == "john@example.com"
    assert user.hashed_password == "hashed-password"
    assert user.full_name == "John Doe"
    assert user.role == "user"
    assert user.is_active is True
    assert isinstance(user.created_at, datetime)
    assert isinstance(user.updated_at, datetime)


@pytest.mark.asyncio
async def test_user_model_has_timestamps(db_session) -> None:
    """A user should receive created and updated timestamps automatically."""
    user = User(
        email="timestamps@example.com",
        hashed_password="hashed-password",
        full_name="Timestamp Test",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.created_at is not None
    assert user.updated_at is not None
