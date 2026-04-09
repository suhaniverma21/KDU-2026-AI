"""Pydantic schemas for user input and output."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_REQUIREMENTS_MESSAGE = (
    "Password must contain uppercase, lowercase, number, and special character"
)


class UserCreate(BaseModel):
    """Schema for registering a new user."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="Password")
    full_name: str = Field(..., min_length=1, max_length=100, description="Full name")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Enforce password complexity requirements."""
        if not re.search(r"[A-Z]", value):
            raise ValueError(PASSWORD_REQUIREMENTS_MESSAGE)
        if not re.search(r"[a-z]", value):
            raise ValueError(PASSWORD_REQUIREMENTS_MESSAGE)
        if not re.search(r"\d", value):
            raise ValueError(PASSWORD_REQUIREMENTS_MESSAGE)
        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError(PASSWORD_REQUIREMENTS_MESSAGE)
        return value


class UserResponse(BaseModel):
    """Safe API response for a user."""

    id: UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    """Schema for updating a user's role."""

    role: str = Field(..., description="New role")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Restrict role updates to supported role values."""
        if value not in {"user", "admin"}:
            raise ValueError('Role must be "user" or "admin"')
        return value


class PaginatedUsers(BaseModel):
    """Paginated response for listing users."""

    items: list[UserResponse]
    total: int
    page: int
    size: int
    pages: int
