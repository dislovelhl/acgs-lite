"""
ACGS-2 PostgreSQL Session Variable Management for RLS
Constitutional Hash: 608508a9bd224290

Provides utilities for managing PostgreSQL session variables used by
Row-Level Security (RLS) policies. These variables must be set before
any database queries to ensure proper tenant isolation.

Session Variables:
- app.current_tenant_id: Current tenant's UUID (required for RLS)
- app.is_admin: Boolean flag for admin bypass (default: false)

Usage:
    from enhanced_agent_bus.multi_tenancy.session_vars import (
        set_tenant_session_vars,
        clear_tenant_session_vars,
        tenant_session,
    )

    # Set session variables manually
    async with db.session() as session:
        await set_tenant_session_vars(session, tenant_id="tenant-uuid")
        # ... perform queries ...
        await clear_tenant_session_vars(session)

    # Use context manager for automatic cleanup
    async with tenant_session(db_session, tenant_id="tenant-uuid"):
        # ... queries are automatically scoped to tenant ...
        pass
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import CONSTITUTIONAL_HASH
from .system_tenant import SYSTEM_TENANT_ID

logger = get_logger(__name__)
# PostgreSQL session variable names
SESSION_VAR_TENANT_ID = "app.current_tenant_id"
SESSION_VAR_IS_ADMIN = "app.is_admin"


async def set_tenant_session_vars(
    session: AsyncSession,
    tenant_id: str,
    is_admin: bool = False,
) -> None:
    """Set PostgreSQL session variables for RLS tenant isolation.

    This must be called at the start of each request/transaction to
    ensure RLS policies can correctly filter data by tenant.

    Args:
        session: SQLAlchemy async session.
        tenant_id: Tenant UUID to set for the session.
        is_admin: Whether to enable admin bypass mode.

    Note:
        These variables are connection-scoped in PostgreSQL, so they
        persist for the duration of the database connection.
    """
    # Set tenant ID
    await session.execute(
        text(f"SET LOCAL {SESSION_VAR_TENANT_ID} = :tenant_id"),
        {"tenant_id": tenant_id},
    )

    # Set admin flag
    admin_value = "true" if is_admin else "false"
    await session.execute(
        text(f"SET LOCAL {SESSION_VAR_IS_ADMIN} = :is_admin"),
        {"is_admin": admin_value},
    )

    logger.debug(
        f"[{CONSTITUTIONAL_HASH}] Set session vars: tenant_id={tenant_id}, is_admin={is_admin}"
    )


async def clear_tenant_session_vars(session: AsyncSession) -> None:
    """Clear PostgreSQL session variables.

    Resets the session variables to their default values. This should
    be called at the end of each request to ensure clean state.

    Args:
        session: SQLAlchemy async session.
    """
    await session.execute(text(f"RESET {SESSION_VAR_TENANT_ID}"))
    await session.execute(text(f"RESET {SESSION_VAR_IS_ADMIN}"))

    logger.debug(f"[{CONSTITUTIONAL_HASH}] Cleared session vars")


async def get_current_tenant_from_session(session: AsyncSession) -> str | None:
    """Get the current tenant ID from PostgreSQL session variables.

    Args:
        session: SQLAlchemy async session.

    Returns:
        Current tenant ID, or None if not set.
    """
    result = await session.execute(text(f"SELECT current_setting('{SESSION_VAR_TENANT_ID}', true)"))  # nosec B608 - constant, not user input
    value = result.scalar()
    return value if value else None  # type: ignore[no-any-return]


async def get_is_admin_from_session(session: AsyncSession) -> bool:
    """Check if admin bypass is enabled in the current session.

    Args:
        session: SQLAlchemy async session.

    Returns:
        True if admin bypass is enabled, False otherwise.
    """
    result = await session.execute(text(f"SELECT current_setting('{SESSION_VAR_IS_ADMIN}', true)"))  # nosec B608 - constant, not user input
    value = result.scalar()
    return value == "true" if value else False


@asynccontextmanager
async def tenant_session(
    session: AsyncSession,
    tenant_id: str,
    is_admin: bool = False,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for tenant-scoped database sessions.

    Automatically sets and clears PostgreSQL session variables for
    RLS tenant isolation. Use this context manager to ensure proper
    tenant isolation and cleanup.

    Args:
        session: SQLAlchemy async session.
        tenant_id: Tenant UUID for the session scope.
        is_admin: Whether to enable admin bypass mode.

    Yields:
        The same session with tenant variables set.

    Example:
        async with tenant_session(db_session, "tenant-uuid") as session:
            # All queries are now scoped to the tenant
            users = await session.execute(select(User))
    """
    try:
        await set_tenant_session_vars(session, tenant_id, is_admin)
        yield session
    finally:
        await clear_tenant_session_vars(session)


@asynccontextmanager
async def system_tenant_session(
    session: AsyncSession,
    is_admin: bool = False,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for system tenant database sessions.

    Convenience wrapper for operations that should use the system
    tenant context.

    Args:
        session: SQLAlchemy async session.
        is_admin: Whether to enable admin bypass mode.

    Yields:
        The session with system tenant variables set.
    """
    async with tenant_session(session, SYSTEM_TENANT_ID, is_admin) as scoped_session:
        yield scoped_session


@asynccontextmanager
async def admin_session(
    session: AsyncSession,
    tenant_id: str | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for admin bypass database sessions.

    Enables admin bypass mode for operations that need to access
    data across all tenants.

    Args:
        session: SQLAlchemy async session.
        tenant_id: Optional tenant ID (defaults to system tenant).

    Yields:
        The session with admin bypass enabled.
    """
    effective_tenant = tenant_id or SYSTEM_TENANT_ID
    async with tenant_session(session, effective_tenant, is_admin=True) as scoped_session:
        yield scoped_session


async def set_tenant_for_request(
    session: AsyncSession,
    tenant_id: str | None,
    is_admin: bool = False,
) -> None:
    """Set tenant context for an HTTP request.

    Convenience function for setting tenant session variables from
    request middleware. Handles None tenant_id by using system tenant.

    Args:
        session: SQLAlchemy async session.
        tenant_id: Tenant UUID from request (may be None).
        is_admin: Whether the request has admin privileges.
    """
    effective_tenant = tenant_id or SYSTEM_TENANT_ID
    await set_tenant_session_vars(session, effective_tenant, is_admin)


__all__ = [
    "CONSTITUTIONAL_HASH",
    "SESSION_VAR_IS_ADMIN",
    "SESSION_VAR_TENANT_ID",
    "admin_session",
    "clear_tenant_session_vars",
    "get_current_tenant_from_session",
    "get_is_admin_from_session",
    "set_tenant_for_request",
    "set_tenant_session_vars",
    "system_tenant_session",
    "tenant_session",
]
