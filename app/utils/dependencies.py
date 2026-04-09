"""Reusable FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import oauth2_scheme
from app.db.session import AsyncSessionLocal
from app.models.user import User


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for a single request."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate a bearer token and return the associated user."""
    settings = get_settings()
    credentials_exception = AuthenticationError(
        "Could not validate credentials",
        code="INVALID_CREDENTIALS",
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        parsed_user_id = UUID(user_id)
    except (JWTError, ValueError):
        raise credentials_exception from None

    result = await db.execute(select(User).where(User.id == parsed_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user is active."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


def require_role(required_role: str):
    """Create a dependency that restricts access to a specific role."""

    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        """Validate that the authenticated user has the required role."""
        if current_user.role != required_role:
            raise AuthorizationError(
                f"Access denied. Required role: {required_role}",
                code="INSUFFICIENT_ROLE",
            )
        return current_user

    return role_checker
