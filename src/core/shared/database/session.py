"""
ACGS-2 Database Session Configuration
Constitutional Hash: cdd01ef066bc6cf2

Provides SQLAlchemy async engine and session factory for database operations.
Supports PostgreSQL (production) and SQLite (development) backends.

Environment Variables:
    DATABASE_URL: Database connection URL (e.g., postgresql+asyncpg://user:pass@host/db)
    DATABASE_POOL_SIZE: Connection pool size (default: 5)
    DATABASE_MAX_OVERFLOW: Max overflow connections (default: 10)
    DATABASE_ECHO: Enable SQL logging (default: false)

Pool Sizing Recommendations:
    - Small deployment (1-2 workers): pool_size=5, max_overflow=10
    - Medium deployment (4-8 workers): pool_size=10, max_overflow=20
    - Large deployment (16+ workers): pool_size=20, max_overflow=40
    - Formula: pool_size = (2 * num_cores) + 1, max_overflow = pool_size * 2
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
# Constitutional hash constant
from src.core.shared.constants import CONSTITUTIONAL_HASH

# Default database URL (SQLite for development, PostgreSQL for production)
# SQLite async requires aiosqlite driver
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./acgs2_sso.db"


def get_database_url() -> str:
    """Get database URL from environment or settings.

    Priority:
    1. DATABASE_URL environment variable
    2. Default SQLite database (development only)

    Returns:
        Database connection URL with async driver
    """
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    # Handle PostgreSQL URL conversion to async driver
    # Standard postgres:// or postgresql:// should use asyncpg
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return database_url


def create_engine_with_config() -> AsyncEngine:
    """Create async SQLAlchemy engine with configuration from environment.

    Returns:
        Configured async SQLAlchemy engine
    """
    database_url = get_database_url()

    # Pool configuration from environment
    # Optimized for 10K RPS sustained throughput
    pool_size = int(os.getenv("DATABASE_POOL_SIZE", "100"))
    max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "200"))
    echo = os.getenv("DATABASE_ECHO", "false").lower() == "true"

    # SQLite doesn't support pool_size, so only apply for PostgreSQL
    is_sqlite = "sqlite" in database_url

    engine_kwargs = {
        "echo": echo,
        "future": True,
    }

    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_pre_ping": True,  # Verify connections before use
                "pool_recycle": 3600,  # Recycle connections after 1 hour
            }
        )

    engine = create_async_engine(database_url, **engine_kwargs)

    logger.info(
        "Database engine created",
        extra={
            "database_type": "sqlite" if is_sqlite else "postgresql",
            "pool_size": pool_size if not is_sqlite else "N/A",
            "echo": echo,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )

    return engine


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ACGS-2 models.

    All database models should inherit from this base class:

        from src.core.shared.database import Base

        class User(Base):
            __tablename__ = "users"
            id = Column(Integer, primary_key=True)
            ...
    """

    pass


# Create the async engine
engine = create_engine_with_config()

# Create async session factory
# Use async_sessionmaker for SQLAlchemy 2.0 async pattern
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Usage:
        async with get_async_session() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()

    Yields:
        AsyncSession: Database session that auto-commits on success
                      and rolls back on exception
    """
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except (RuntimeError, ValueError, TypeError):
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Initialize database by creating all tables.

    This should be called during application startup to ensure
    all tables exist. Uses CREATE TABLE IF NOT EXISTS semantics.

    Usage:
        @app.on_event("startup")
        async def startup():
            await init_db()
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info(
        "Database initialized",
        extra={
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )


async def close_db() -> None:
    """Close database engine and all connections.

    This should be called during application shutdown.

    Usage:
        @app.on_event("shutdown")
        async def shutdown():
            await close_db()
    """
    await engine.dispose()

    logger.info(
        "Database connections closed",
        extra={
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )
