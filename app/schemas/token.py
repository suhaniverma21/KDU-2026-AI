"""Schemas for authentication tokens."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class Token(BaseModel):
    """Response schema for a bearer access token."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Decoded token payload data."""

    user_id: UUID | None = None
