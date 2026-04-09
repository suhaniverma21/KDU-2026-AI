"""Business logic for user operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


class UserService:
    """Service methods for user-related operations."""

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        """Create a new user after checking for duplicate email."""
        result = await db.execute(select(User).where(User.email == user_data.email))
        existing_user = result.scalar_one_or_none()
        if existing_user is not None:
            raise ConflictError(
                "Email already registered",
                code="EMAIL_ALREADY_REGISTERED",
            )

        user = User(
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            full_name=user_data.full_name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> User | None:
        """Authenticate a user by email and password."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    @staticmethod
    async def get_all_users(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[list[User], int]:
        """Return a paginated list of users and the total user count."""
        result = await db.execute(
            select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
        )
        users = list(result.scalars().all())

        count_result = await db.execute(select(func.count(User.id)))
        total = int(count_result.scalar_one())
        return users, total

    @staticmethod
    async def delete_user(db: AsyncSession, user_id: UUID) -> bool:
        """Delete a user by id and report whether deletion occurred."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return False

        await db.delete(user)
        await db.commit()
        return True

    @staticmethod
    async def update_user_role(
        db: AsyncSession,
        user_id: UUID,
        new_role: str,
    ) -> User | None:
        """Update a user's role and return the refreshed user."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        user.role = new_role
        await db.commit()
        await db.refresh(user)
        return user
