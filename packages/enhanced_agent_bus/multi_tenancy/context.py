"""
ACGS-2 Tenant Context Management
Constitutional Hash: cdd01ef066bc6cf2

Provides request-scoped tenant identification using Python contextvars.
Thread-safe and async-compatible for enterprise multi-tenant operations.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Context variable for tenant identification
_tenant_context: ContextVar["TenantContext" | None] = ContextVar("tenant_context", default=None)


@dataclass
class TenantContext:
    """Request-scoped tenant context.

    Constitutional Hash: cdd01ef066bc6cf2

    This class provides thread-safe, async-compatible tenant identification
    for all database operations. It uses Python's contextvars for automatic
    propagation across async boundaries.

    Usage:
        # Set tenant context for a request
        with tenant_context(tenant_id="acme-corp"):
            # All database operations within this context
            # will be automatically scoped to the tenant
            await repository.get_policies()

        # Or manually
        set_current_tenant(TenantContext(tenant_id="acme-corp"))
        try:
            await do_work()
        finally:
            clear_tenant_context()
    """

    tenant_id: str
    constitutional_hash: str = CONSTITUTIONAL_HASH

    # Optional context metadata
    user_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None

    # Audit fields
    source_ip: str | None = None
    user_agent: str | None = None

    # Permissions
    is_admin: bool = False
    roles: list = field(default_factory=list)
    permissions: list = field(default_factory=list)

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    # Token for context restoration
    _token: Token | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate context after initialization."""
        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {self.constitutional_hash}"
            )

    def is_expired(self) -> bool:
        """Check if context has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def validate(self) -> bool:
        """Validate the tenant context is still valid."""
        if not self.tenant_id:
            return False
        if self.is_expired():
            return False
        return self.constitutional_hash == CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert context to dictionary for serialization."""
        return {
            "tenant_id": self.tenant_id,
            "constitutional_hash": self.constitutional_hash,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "is_admin": self.is_admin,
            "roles": list(self.roles),
            "permissions": list(self.permissions),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    def to_sql_params(self) -> dict[str, str]:
        """Get parameters for PostgreSQL session variables."""
        return {
            "app.current_tenant_id": self.tenant_id,
            "app.constitutional_hash": self.constitutional_hash,
            "app.user_id": self.user_id or "",
            "app.is_admin": "true" if self.is_admin else "false",
        }

    def __enter__(self) -> "TenantContext":
        """Enter context manager - set current tenant."""
        self._token = _tenant_context.set(self)
        logger.debug(f"[{CONSTITUTIONAL_HASH}] Entered tenant context: {self.tenant_id}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager - restore previous context."""
        if self._token:
            _tenant_context.reset(self._token)
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Exited tenant context: {self.tenant_id}")

    async def __aenter__(self) -> "TenantContext":
        """Async context manager entry."""
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        self.__exit__(exc_type, exc_val, exc_tb)


def get_current_tenant() -> TenantContext | None:
    """Get the current tenant context.

    Returns:
        Current TenantContext or None if not set.
    """
    return _tenant_context.get()


def get_current_tenant_id() -> str | None:
    """Get the current tenant ID.

    Returns:
        Current tenant ID or None if not set.
    """
    ctx = get_current_tenant()
    return ctx.tenant_id if ctx else None


def require_tenant_context() -> TenantContext:
    """Get current tenant context, raising if not set.

    Returns:
        Current TenantContext.

    Raises:
        RuntimeError: If no tenant context is set.
    """
    ctx = get_current_tenant()
    if ctx is None:
        raise RuntimeError(
            f"[{CONSTITUTIONAL_HASH}] No tenant context set. "
            "Use set_current_tenant() or TenantContext context manager."
        )
    if not ctx.validate():
        raise RuntimeError(f"[{CONSTITUTIONAL_HASH}] Invalid or expired tenant context.")
    return ctx


def set_current_tenant(context: TenantContext) -> Token:
    """Set the current tenant context.

    Args:
        context: TenantContext to set.

    Returns:
        Token for restoring previous context.
    """
    logger.debug(f"[{CONSTITUTIONAL_HASH}] Setting tenant context: {context.tenant_id}")
    return _tenant_context.set(context)


def clear_tenant_context() -> None:
    """Clear the current tenant context."""
    logger.debug(f"[{CONSTITUTIONAL_HASH}] Clearing tenant context")
    _tenant_context.set(None)


class tenant_context:
    """Context manager for tenant scoping.

    Constitutional Hash: cdd01ef066bc6cf2

    Usage:
        with tenant_context(tenant_id="acme-corp"):
            # All operations scoped to tenant
            await repository.list_policies()

        # Or with additional context
        with tenant_context(
            tenant_id="acme-corp",
            user_id="user-123",
            is_admin=True
        ):
            await repository.create_policy(policy)
    """

    def __init__(
        self,
        tenant_id: str,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        user_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
        is_admin: bool = False,
        roles: list | None = None,
        permissions: list | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        """Initialize tenant context manager."""
        self._context = TenantContext(
            tenant_id=tenant_id,
            constitutional_hash=constitutional_hash,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            is_admin=is_admin,
            roles=roles or [],
            permissions=permissions or [],
            expires_at=expires_at,
        )
        self._token: Token | None = None

    def __enter__(self) -> TenantContext:
        """Enter context manager."""
        self._token = _tenant_context.set(self._context)
        logger.debug(f"[{CONSTITUTIONAL_HASH}] Entered tenant context: {self._context.tenant_id}")
        return self._context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager."""
        if self._token:
            _tenant_context.reset(self._token)
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Exited tenant context: {self._context.tenant_id}"
            )

    async def __aenter__(self) -> TenantContext:
        """Async context manager entry."""
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        self.__exit__(exc_type, exc_val, exc_tb)
