"""
ACGS-2 Tenant Manager
Constitutional Hash: cdd01ef066bc6cf2

High-level tenant management service providing business logic, quota enforcement,
event publishing, caching, and hierarchical tenant operations.
"""

import asyncio
import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import Enum

from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.types import JSONDict, JSONList

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import CONSTITUTIONAL_HASH, TenantContext, tenant_context
from .models import Tenant, TenantConfig, TenantQuota, TenantStatus, TenantUsage
from .repository import TenantRepository

logger = get_logger(__name__)
TENANT_EVENT_HANDLER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class TenantEvent(str, Enum):  # noqa: UP042
    """Tenant lifecycle events for publishing."""

    CREATED = "tenant.created"
    ACTIVATED = "tenant.activated"
    SUSPENDED = "tenant.suspended"
    DEACTIVATED = "tenant.deactivated"
    CONFIG_UPDATED = "tenant.config_updated"
    QUOTA_UPDATED = "tenant.quota_updated"
    QUOTA_EXCEEDED = "tenant.quota_exceeded"
    QUOTA_WARNING = "tenant.quota_warning"


class TenantManagerError(ACGSBaseError):
    """Base exception for tenant management errors."""

    http_status_code = 500
    error_code = "TENANT_MANAGER_ERROR"

    def __init__(
        self,
        message: str,
        tenant_id: str | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs: object,
    ) -> None:
        super().__init__(
            message,
            constitutional_hash=constitutional_hash,
            details={"tenant_id": tenant_id, **kwargs},
        )
        self.tenant_id = tenant_id


class TenantNotFoundError(TenantManagerError):
    """Raised when a tenant is not found."""

    http_status_code = 404
    error_code = "TENANT_NOT_FOUND"


class TenantQuotaExceededError(TenantManagerError):
    """Raised when a tenant exceeds quota limits."""

    http_status_code = 429
    error_code = "TENANT_QUOTA_EXCEEDED"

    def __init__(
        self,
        message: str,
        tenant_id: str,
        resource: str,
        current: int,
        limit: int,
    ) -> None:
        super().__init__(
            message,
            tenant_id=tenant_id,
            resource=resource,
            current=current,
            limit=limit,
        )
        self.resource = resource
        self.current = current
        self.limit = limit


class TenantValidationError(TenantManagerError):
    """Raised when tenant validation fails."""

    http_status_code = 400
    error_code = "TENANT_VALIDATION_ERROR"


class TenantManager:
    """High-level tenant management service.

    Constitutional Hash: cdd01ef066bc6cf2

    Provides business logic layer on top of TenantRepository:
    - Quota enforcement and warnings
    - Event publishing for tenant lifecycle
    - Caching for performance
    - Hierarchical tenant management
    - Provisioning workflows

    Usage:
        manager = TenantManager()

        # Create and activate tenant
        tenant = await manager.create_tenant(
            name="Acme Corp",
            slug="acme-corp",
        )
        await manager.activate_tenant(tenant.tenant_id)

        # Check quota
        await manager.check_quota(tenant.tenant_id, "agents", 10)

        # Subscribe to events
        manager.subscribe(TenantEvent.CREATED, on_tenant_created)
    """

    def __init__(
        self,
        repository: TenantRepository | None = None,
        cache_ttl_seconds: int = 300,
        quota_warning_threshold: float = 0.8,
    ) -> None:
        """Initialize the tenant manager.

        Args:
            repository: TenantRepository instance (creates new if None).
            cache_ttl_seconds: Cache TTL in seconds.
            quota_warning_threshold: Threshold (0-1) for quota warning events.
        """
        self.repository = repository or TenantRepository()
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._cache_ttl = cache_ttl_seconds
        self._quota_warning_threshold = quota_warning_threshold

        # In-memory cache
        self._cache: dict[str, tuple[Tenant, datetime]] = {}
        self._slug_to_id: dict[str, str] = {}

        # Usage tracking
        self._usage: dict[str, TenantUsage] = {}

        # Event subscribers
        self._subscribers: dict[TenantEvent, list[Callable]] = {event: [] for event in TenantEvent}

        logger.info(f"[{CONSTITUTIONAL_HASH}] TenantManager initialized")

    # ========================================================================
    # CRUD Operations
    # ========================================================================

    async def create_tenant(
        self,
        name: str,
        slug: str,
        config: TenantConfig | None = None,
        quota: TenantQuota | None = None,
        metadata: JSONDict | None = None,
        parent_tenant_id: str | None = None,
        auto_activate: bool = False,
    ) -> Tenant:
        """Create a new tenant with validation and event publishing.

        Args:
            name: Human-readable tenant name.
            slug: URL-safe tenant slug.
            config: Tenant configuration.
            quota: Resource quota.
            metadata: Additional metadata.
            parent_tenant_id: Parent tenant for hierarchical tenancy.
            auto_activate: Whether to automatically activate the tenant.

        Returns:
            Created tenant.

        Raises:
            TenantValidationError: If validation fails.
        """
        # Validate slug format
        if not self._validate_slug(slug):
            raise TenantValidationError(
                f"Invalid slug format: {slug}. Must be lowercase alphanumeric with hyphens.",
            )

        # Validate parent exists if specified
        if parent_tenant_id:
            parent = await self.get_tenant(parent_tenant_id)
            if not parent:
                raise TenantNotFoundError(
                    f"Parent tenant not found: {parent_tenant_id}",
                    tenant_id=parent_tenant_id,
                )
            if not parent.is_active():
                raise TenantValidationError(
                    f"Parent tenant is not active: {parent_tenant_id}",
                    tenant_id=parent_tenant_id,
                )

        # Inherit configuration from parent if not specified
        if parent_tenant_id and not config:
            parent = await self.get_tenant(parent_tenant_id)
            if parent:
                config = parent.config.model_copy()

        # Create tenant
        tenant = await self.repository.create_tenant(
            name=name,
            slug=slug,
            config=config,
            quota=quota,
            metadata=metadata,
            parent_tenant_id=parent_tenant_id,
        )

        # Initialize usage tracking
        self._usage[tenant.tenant_id] = TenantUsage()

        # Update cache
        self._cache_tenant(tenant)

        # Publish event
        await self._publish_event(TenantEvent.CREATED, tenant)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Created tenant: {tenant.tenant_id} ({tenant.slug})")

        # Auto-activate if requested
        if auto_activate:
            tenant = await self.activate_tenant(tenant.tenant_id)

        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID with caching.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Tenant if found, None otherwise.
        """
        # Check cache first
        cached = self._get_cached_tenant(tenant_id)
        if cached:
            return cached

        # Fetch from repository
        tenant = await self.repository.get_tenant(tenant_id)
        if tenant:
            self._cache_tenant(tenant)

        return tenant

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        """Get a tenant by slug with caching.

        Args:
            slug: Tenant slug.

        Returns:
            Tenant if found, None otherwise.
        """
        # Check slug cache
        tenant_id = self._slug_to_id.get(slug)
        if tenant_id:
            return await self.get_tenant(tenant_id)

        # Fetch from repository
        tenant = await self.repository.get_tenant_by_slug(slug)
        if tenant:
            self._cache_tenant(tenant)

        return tenant

    async def list_tenants(
        self,
        status: TenantStatus | None = None,
        parent_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Tenant]:
        """List tenants with optional filtering.

        Args:
            status: Filter by status.
            parent_id: Filter by parent tenant.
            skip: Number of records to skip.
            limit: Maximum records to return.

        Returns:
            List of tenants.
        """
        tenants = await self.repository.list_tenants(status=status, skip=0, limit=1000)

        # Filter by parent if specified
        if parent_id is not None:
            tenants = [t for t in tenants if t.parent_tenant_id == parent_id]

        # Apply pagination
        return tenants[skip : skip + limit]

    async def update_tenant(
        self,
        tenant_id: str,
        name: str | None = None,
        metadata: JSONDict | None = None,
    ) -> Tenant | None:
        """Update tenant properties.

        Args:
            tenant_id: Tenant identifier.
            name: New tenant name.
            metadata: New metadata (merged with existing).

        Returns:
            Updated tenant if found, None otherwise.
        """
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return None

        # Update fields
        if name:
            tenant.name = name
        if metadata:
            tenant.metadata.update(metadata)
        tenant.updated_at = datetime.now(UTC)

        # Update cache
        self._cache_tenant(tenant)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated tenant: {tenant_id}")
        return tenant

    async def delete_tenant(self, tenant_id: str, force: bool = False) -> bool:
        """Delete a tenant.

        Args:
            tenant_id: Tenant identifier.
            force: Force delete even if tenant has children.

        Returns:
            True if deleted, False if not found.

        Raises:
            TenantValidationError: If tenant has children and force=False.
        """
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return False

        # Check for child tenants
        children = await self.get_child_tenants(tenant_id)
        if children and not force:
            raise TenantValidationError(
                f"Cannot delete tenant with {len(children)} child tenants. Use force=True.",
                tenant_id=tenant_id,
            )

        # Delete children first if forcing
        if children and force:
            for child in children:
                await self.delete_tenant(child.tenant_id, force=True)

        # Publish event before deletion
        await self._publish_event(TenantEvent.DEACTIVATED, tenant)

        # Remove from cache
        self._invalidate_cache(tenant_id)
        if tenant.slug in self._slug_to_id:
            del self._slug_to_id[tenant.slug]

        # Remove usage tracking
        if tenant_id in self._usage:
            del self._usage[tenant_id]

        # Delete from repository
        result = await self.repository.delete_tenant(tenant_id)

        logger.warning(f"[{CONSTITUTIONAL_HASH}] Deleted tenant: {tenant_id}")
        return result

    # ========================================================================
    # Lifecycle Operations
    # ========================================================================

    async def activate_tenant(self, tenant_id: str) -> Tenant | None:
        """Activate a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Activated tenant if found, None otherwise.

        Raises:
            TenantValidationError: If tenant cannot be activated.
        """
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return None

        if tenant.status == TenantStatus.ACTIVE:
            return tenant

        if tenant.status == TenantStatus.DEACTIVATED:
            raise TenantValidationError(
                f"Cannot activate deactivated tenant: {tenant_id}",
                tenant_id=tenant_id,
            )

        # Activate
        tenant = await self.repository.activate_tenant(tenant_id)
        if tenant:
            self._cache_tenant(tenant)
            await self._publish_event(TenantEvent.ACTIVATED, tenant)

        return tenant

    async def suspend_tenant(
        self,
        tenant_id: str,
        reason: str | None = None,
        suspend_children: bool = True,
    ) -> Tenant | None:
        """Suspend a tenant.

        Args:
            tenant_id: Tenant identifier.
            reason: Suspension reason.
            suspend_children: Whether to also suspend child tenants.

        Returns:
            Suspended tenant if found, None otherwise.
        """
        tenant = await self.repository.suspend_tenant(tenant_id, reason)
        if not tenant:
            return None

        self._cache_tenant(tenant)
        await self._publish_event(TenantEvent.SUSPENDED, tenant)

        # Suspend children if requested
        if suspend_children:
            children = await self.get_child_tenants(tenant_id)
            for child in children:
                await self.suspend_tenant(
                    child.tenant_id,
                    reason=f"Parent tenant suspended: {reason}",
                    suspend_children=True,
                )

        return tenant

    async def reactivate_tenant(self, tenant_id: str) -> Tenant | None:
        """Reactivate a suspended tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Reactivated tenant if found, None otherwise.

        Raises:
            TenantValidationError: If tenant cannot be reactivated.
        """
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return None

        if tenant.status != TenantStatus.SUSPENDED:
            raise TenantValidationError(
                f"Can only reactivate suspended tenants. Current status: {tenant.status}",
                tenant_id=tenant_id,
            )

        return await self.activate_tenant(tenant_id)

    # ========================================================================
    # Configuration Operations
    # ========================================================================

    async def update_config(
        self,
        tenant_id: str,
        config: TenantConfig,
    ) -> Tenant | None:
        """Update tenant configuration.

        Args:
            tenant_id: Tenant identifier.
            config: New configuration.

        Returns:
            Updated tenant if found, None otherwise.
        """
        tenant = await self.repository.update_tenant_config(tenant_id, config)
        if tenant:
            self._cache_tenant(tenant)
            await self._publish_event(TenantEvent.CONFIG_UPDATED, tenant)

        return tenant

    async def update_quota(
        self,
        tenant_id: str,
        quota: TenantQuota,
    ) -> Tenant | None:
        """Update tenant quota.

        Args:
            tenant_id: Tenant identifier.
            quota: New quota.

        Returns:
            Updated tenant if found, None otherwise.
        """
        tenant = await self.repository.update_tenant_quota(tenant_id, quota)
        if tenant:
            self._cache_tenant(tenant)
            await self._publish_event(TenantEvent.QUOTA_UPDATED, tenant)

        return tenant

    # ========================================================================
    # Quota Management
    # ========================================================================

    async def check_quota(
        self,
        tenant_id: str,
        resource: str,
        requested_amount: int = 1,
    ) -> bool:
        """Check if a tenant has quota for a resource.

        Args:
            tenant_id: Tenant identifier.
            resource: Resource type (agents, policies, messages, storage, sessions).
            requested_amount: Amount of resource being requested.

        Returns:
            True if quota is available, False otherwise.

        Raises:
            TenantNotFoundError: If tenant not found.
            TenantQuotaExceededError: If quota exceeded and raise_on_exceed=True.
        """
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant not found: {tenant_id}", tenant_id)

        quota = tenant.get_quota()
        usage = self._usage.get(tenant_id, TenantUsage())

        # Map resource to quota/usage fields
        resource_map = {
            "agents": ("max_agents", "agent_count"),
            "policies": ("max_policies", "policy_count"),
            "messages": ("max_messages_per_minute", "message_count_minute"),
            "storage": ("max_storage_mb", "storage_used_mb"),
            "sessions": ("max_concurrent_sessions", "concurrent_sessions"),
        }

        if resource not in resource_map:
            logger.warning(f"Unknown resource type: {resource}")
            return True

        quota_field, usage_field = resource_map[resource]
        limit = getattr(quota, quota_field)
        current = getattr(usage, usage_field)

        # Check if quota exceeded
        if current + requested_amount > limit:
            await self._publish_event(
                TenantEvent.QUOTA_EXCEEDED,
                tenant,
                extra={"resource": resource, "current": current, "limit": limit},
            )
            return False

        # Check for warning threshold
        usage_ratio = (current + requested_amount) / limit if limit > 0 else 0
        if usage_ratio >= self._quota_warning_threshold:
            await self._publish_event(
                TenantEvent.QUOTA_WARNING,
                tenant,
                extra={"resource": resource, "usage_ratio": usage_ratio},
            )

        return True

    async def increment_usage(
        self,
        tenant_id: str,
        resource: str,
        amount: int = 1,
    ) -> TenantUsage:
        """Increment resource usage for a tenant.

        Args:
            tenant_id: Tenant identifier.
            resource: Resource type.
            amount: Amount to increment.

        Returns:
            Updated usage.

        Raises:
            TenantQuotaExceededError: If quota would be exceeded.
        """
        # Check quota first
        if not await self.check_quota(tenant_id, resource, amount):
            tenant = await self.get_tenant(tenant_id)
            quota = tenant.get_quota() if tenant else TenantQuota()
            usage = self._usage.get(tenant_id, TenantUsage())

            resource_map = {
                "agents": ("max_agents", "agent_count"),
                "policies": ("max_policies", "policy_count"),
                "messages": ("max_messages_per_minute", "message_count_minute"),
                "storage": ("max_storage_mb", "storage_used_mb"),
                "sessions": ("max_concurrent_sessions", "concurrent_sessions"),
            }

            if resource in resource_map:
                quota_field, usage_field = resource_map[resource]
                raise TenantQuotaExceededError(
                    f"Quota exceeded for {resource}",
                    tenant_id=tenant_id,
                    resource=resource,
                    current=int(getattr(usage, usage_field)),
                    limit=getattr(quota, quota_field),
                )

        # Increment usage
        if tenant_id not in self._usage:
            self._usage[tenant_id] = TenantUsage()

        usage = self._usage[tenant_id]
        if resource == "agents":
            usage.agent_count += amount
        elif resource == "policies":
            usage.policy_count += amount
        elif resource == "messages":
            usage.message_count_minute += amount
        elif resource == "storage":
            usage.storage_used_mb += amount
        elif resource == "sessions":
            usage.concurrent_sessions += amount

        usage.last_updated = datetime.now(UTC)
        return usage

    async def decrement_usage(
        self,
        tenant_id: str,
        resource: str,
        amount: int = 1,
    ) -> TenantUsage:
        """Decrement resource usage for a tenant.

        Args:
            tenant_id: Tenant identifier.
            resource: Resource type.
            amount: Amount to decrement.

        Returns:
            Updated usage.
        """
        if tenant_id not in self._usage:
            self._usage[tenant_id] = TenantUsage()

        usage = self._usage[tenant_id]
        if resource == "agents":
            usage.agent_count = max(0, usage.agent_count - amount)
        elif resource == "policies":
            usage.policy_count = max(0, usage.policy_count - amount)
        elif resource == "messages":
            usage.message_count_minute = max(0, usage.message_count_minute - amount)
        elif resource == "storage":
            usage.storage_used_mb = max(0, usage.storage_used_mb - amount)
        elif resource == "sessions":
            usage.concurrent_sessions = max(0, usage.concurrent_sessions - amount)

        usage.last_updated = datetime.now(UTC)
        return usage

    async def get_usage(self, tenant_id: str) -> TenantUsage:
        """Get current resource usage for a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Current usage.
        """
        return self._usage.get(tenant_id, TenantUsage())

    async def reset_message_usage(self) -> None:
        """Reset message counters for rate limiting (call periodically)."""
        for usage in self._usage.values():
            usage.message_count_minute = 0
            usage.last_updated = datetime.now(UTC)

    # ========================================================================
    # Hierarchical Operations
    # ========================================================================

    async def get_child_tenants(self, parent_id: str) -> list[Tenant]:
        """Get all direct child tenants.

        Args:
            parent_id: Parent tenant identifier.

        Returns:
            List of child tenants.
        """
        return await self.list_tenants(parent_id=parent_id)

    async def get_tenant_hierarchy(self, tenant_id: str) -> list[Tenant]:
        """Get full hierarchy path from root to tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            List of tenants from root to specified tenant.
        """
        hierarchy: JSONList = []
        current_id = tenant_id

        while current_id:
            tenant = await self.get_tenant(current_id)
            if not tenant:
                break
            hierarchy.insert(0, tenant)
            current_id = tenant.parent_tenant_id

        return hierarchy  # type: ignore[no-any-return]

    async def get_all_descendants(self, tenant_id: str) -> list[Tenant]:
        """Get all descendant tenants (children, grandchildren, etc.).

        Args:
            tenant_id: Tenant identifier.

        Returns:
            List of all descendant tenants.
        """
        descendants = []
        to_process = [tenant_id]

        while to_process:
            current_id = to_process.pop(0)
            children = await self.get_child_tenants(current_id)
            for child in children:
                descendants.append(child)
                to_process.append(child.tenant_id)

        return descendants

    # ========================================================================
    # Context Management
    # ========================================================================

    def get_context(
        self,
        tenant_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        is_admin: bool = False,
    ) -> TenantContext:
        """Create a tenant context for operations.

        Args:
            tenant_id: Tenant identifier.
            user_id: User identifier.
            session_id: Session identifier.
            is_admin: Whether user is admin.

        Returns:
            TenantContext for use in operations.
        """
        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            is_admin=is_admin,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    def context(
        self,
        tenant_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        is_admin: bool = False,
    ) -> tenant_context:
        """Get a context manager for tenant operations.

        Args:
            tenant_id: Tenant identifier.
            user_id: User identifier.
            session_id: Session identifier.
            is_admin: Whether user is admin.

        Returns:
            Context manager for tenant-scoped operations.
        """
        return tenant_context(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            is_admin=is_admin,
        )

    # ========================================================================
    # Event Subscription
    # ========================================================================

    def subscribe(
        self,
        event: TenantEvent,
        handler: Callable[[Tenant, JSONDict], None],
    ) -> None:
        """Subscribe to tenant events.

        Args:
            event: Event type to subscribe to.
            handler: Handler function (receives tenant and extra data).
        """
        self._subscribers[event].append(handler)
        logger.debug(f"[{CONSTITUTIONAL_HASH}] Subscribed to {event.value}")

    def unsubscribe(
        self,
        event: TenantEvent,
        handler: Callable[[Tenant, JSONDict], None],
    ) -> None:
        """Unsubscribe from tenant events.

        Args:
            event: Event type.
            handler: Handler to remove.
        """
        if handler in self._subscribers[event]:
            self._subscribers[event].remove(handler)
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Unsubscribed from {event.value}")

    async def _publish_event(
        self,
        event: TenantEvent,
        tenant: Tenant,
        extra: JSONDict | None = None,
    ) -> None:
        """Publish a tenant event to all subscribers.

        Args:
            event: Event type.
            tenant: Affected tenant.
            extra: Additional event data.
        """
        extra = extra or {}
        extra["constitutional_hash"] = CONSTITUTIONAL_HASH
        extra["timestamp"] = datetime.now(UTC).isoformat()

        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Publishing event: {event.value} for tenant {tenant.tenant_id}"
        )

        for handler in self._subscribers[event]:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(tenant, extra)
                else:
                    handler(tenant, extra)
            except TENANT_EVENT_HANDLER_ERRORS as e:
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] Event handler error: {e}",
                    exc_info=True,
                )

    # ========================================================================
    # Cache Management
    # ========================================================================

    def _cache_tenant(self, tenant: Tenant) -> None:
        """Add tenant to cache."""
        self._cache[tenant.tenant_id] = (tenant, datetime.now(UTC))
        self._slug_to_id[tenant.slug] = tenant.tenant_id

    def _get_cached_tenant(self, tenant_id: str) -> Tenant | None:
        """Get tenant from cache if valid."""
        if tenant_id not in self._cache:
            return None

        tenant, cached_at = self._cache[tenant_id]
        if datetime.now(UTC) - cached_at > timedelta(seconds=self._cache_ttl):
            self._invalidate_cache(tenant_id)
            return None

        return tenant

    def _invalidate_cache(self, tenant_id: str) -> None:
        """Invalidate cache for a tenant."""
        if tenant_id in self._cache:
            del self._cache[tenant_id]

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._slug_to_id.clear()
        logger.debug(f"[{CONSTITUTIONAL_HASH}] Cache cleared")

    # ========================================================================
    # Validation
    # ========================================================================

    def _validate_slug(self, slug: str) -> bool:
        """Validate tenant slug format."""
        import re

        # Must be 2-63 characters, lowercase alphanumeric with hyphens
        # Cannot start or end with hyphen
        pattern = r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$|^[a-z0-9]$"
        return bool(re.match(pattern, slug))

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self) -> JSONDict:
        """Get tenant manager statistics.

        Returns:
            Dictionary of statistics.
        """
        return {
            "total_tenants": self.repository.get_tenant_count(),
            "active_tenants": self.repository.get_active_tenant_count(),
            "cached_tenants": len(self._cache),
            "tracked_usage": len(self._usage),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# Singleton instance for convenience
_default_manager: TenantManager | None = None


def get_tenant_manager() -> TenantManager:
    """Get the default TenantManager instance.

    Returns:
        Default TenantManager.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = TenantManager()
    return _default_manager


def set_tenant_manager(manager: TenantManager) -> None:
    """Set the default TenantManager instance.

    Args:
        manager: TenantManager to use as default.
    """
    global _default_manager
    _default_manager = manager


__all__ = [
    "TenantEvent",
    "TenantManager",
    "TenantManagerError",
    "TenantNotFoundError",
    "TenantQuotaExceededError",
    "TenantValidationError",
    "get_tenant_manager",
    "set_tenant_manager",
]
