"""Configuration tests."""

from __future__ import annotations

from app.core.config import Settings


def test_settings_default_to_postgresql_urls() -> None:
    """PostgreSQL should be the primary default database configuration."""
    settings = Settings(_env_file=None, secret_key="x" * 64)

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.test_database_url.startswith("postgresql+asyncpg://")


def test_settings_accept_sqlite_override() -> None:
    """SQLite should remain available as an explicit local override."""
    settings = Settings(
        _env_file=None,
        secret_key="x" * 64,
        database_url="sqlite+aiosqlite:///./dev.db",
        test_database_url="sqlite+aiosqlite:///./test.db",
    )

    assert settings.database_url == "sqlite+aiosqlite:///./dev.db"
    assert settings.test_database_url == "sqlite+aiosqlite:///./test.db"
