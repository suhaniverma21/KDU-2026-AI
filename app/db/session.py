"""Async database engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()


def build_engine_kwargs(database_url: str) -> dict[str, object]:
    """Return engine configuration tailored to the current database backend."""
    if database_url.startswith("sqlite+aiosqlite"):
        return {"future": True}
    return {
        "future": True,
        "pool_pre_ping": True,
    }


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    **build_engine_kwargs(settings.database_url),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
