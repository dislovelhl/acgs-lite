"""
ACGS-2 Shared Database Module
Constitutional Hash: cdd01ef066bc6cf2

Provides SQLAlchemy async database session management for SSO and other services.

Usage:
    from src.core.shared.database import SessionLocal, Base, get_async_session, engine

    # Create a database session
    async with get_async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    # Or use dependency injection pattern
    async def get_db():
        async with get_async_session() as session:
            yield session
"""

from .session import Base, SessionLocal, engine, get_async_session, init_db

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_async_session",
    "init_db",
]
