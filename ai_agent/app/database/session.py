"""Database session management with connection pooling and graceful error handling."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.database.models import Base
from app.monitoring.logger import get_logger

logger = get_logger("database.session")

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_db_available: bool = False


def is_database_available() -> bool:
    """Return whether the database connection has been established."""
    return _db_available


async def init_db() -> bool:
    """Initialize database engine, connection pool, and create tables."""
    global _engine, _session_factory, _db_available

    settings = get_settings()
    url = settings.database_url

    try:
        # SQLite async doesn't support max_overflow / pool_size arguments
        if "sqlite" in url:
            _engine = create_async_engine(
                url,
                echo=settings.database_echo,
                future=True,
            )
        else:
            _engine = create_async_engine(
                url,
                echo=settings.database_echo,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout,
                pool_pre_ping=True,
                future=True,
            )

        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # Create tables if not present
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        _db_available = True
        logger.info("Database initialized successfully", url=url.split("@")[-1])
        return True

    except Exception as exc:
        _db_available = False
        logger.warning(
            "Database initialization failed; proceeding in degraded mode (in-memory/cached)",
            error=str(exc),
        )
        return False


async def close_db() -> None:
    """Dispose of the database engine connection pool."""
    global _engine, _session_factory, _db_available
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        _db_available = False
        logger.info("Database connection closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[Optional[AsyncSession], None]:
    """Async context manager providing a database session or None if DB is unavailable."""
    if not _db_available or _session_factory is None:
        yield None
        return

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("Database transaction rolled back", error=str(exc))
            raise
