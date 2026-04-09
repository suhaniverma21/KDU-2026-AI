"""Shared test fixtures."""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["ENVIRONMENT"] = "test"

from app.main import app
from app.core.config import get_settings
from app.db.base import Base
from app.models.user import User
from app.utils.dependencies import get_db

settings = get_settings()
test_engine = create_async_engine(settings.test_database_url, future=True)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Provide an isolated async database session for each test."""
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session
        await session.rollback()

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Provide an async client bound to the FastAPI app."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        """Yield the active test database session."""
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Backwards-compatible async client fixture alias."""
    yield client


@pytest.fixture
async def registered_user(db_session: AsyncSession) -> tuple[User, str]:
    """Create a registered user for authentication tests."""
    user = User(
        email="registered@example.com",
        hashed_password="$2b$12$N4TdaJ3wY0lL2w6t4wM0K.7lLfqkpC1Q6Q5r8n7mZ6mXc4iM7A.Ze",
        full_name="Registered User",
    )
    plain_password = "SecurePass123!"
    from app.core.security import get_password_hash

    user.hashed_password = get_password_hash(plain_password)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await db_session.execute(select(User).where(User.id == user.id))
    stored_user = result.scalar_one()
    return stored_user, plain_password


@pytest.fixture
async def auth_headers(async_client: AsyncClient) -> dict[str, str]:
    """Register and log in a user, returning bearer auth headers."""
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "authuser@example.com",
            "password": "SecurePass123!",
            "full_name": "Auth User",
        },
    )
    response = await async_client.post(
        "/api/v1/auth/login",
        data={
            "username": "authuser@example.com",
            "password": "SecurePass123!",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> tuple[User, str]:
    """Create an admin user for RBAC tests."""
    from app.core.security import get_password_hash

    plain_password = "AdminPass123!"
    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash(plain_password),
        full_name="Admin User",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user, plain_password


@pytest.fixture
async def admin_headers(
    async_client: AsyncClient,
    admin_user: tuple[User, str],
) -> dict[str, str]:
    """Log in as an admin and return bearer auth headers."""
    user, plain_password = admin_user
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": plain_password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
