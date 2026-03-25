"""
ACGS-2 Tenant-Aware Repository
Constitutional Hash: 608508a9bd224290

Provides tenant-aware database operations with automatic RLS context management.
Implements the repository pattern for multi-tenant data access.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import (
    CONSTITUTIONAL_HASH,
    TenantContext,
    require_tenant_context,
)
from .models import Tenant, TenantConfig, TenantQuota, TenantStatus

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class TenantAwareRepository(ABC, Generic[T]):
    """Base class for tenant-aware repositories.

    Constitutional Hash: 608508a9bd224290

    This abstract class provides:
    - Automatic tenant context injection
    - RLS parameter management
    - Common CRUD operations with tenant isolation

    Subclasses implement database-specific operations.
    """

    def __init__(
        self,
        model_class: type[T],
        table_name: str,
        tenant_column: str = "tenant_id",
    ) -> None:
        """Initialize the repository.

        Args:
            model_class: Pydantic model class for entities.
            table_name: Database table name.
            tenant_column: Column containing tenant ID.
        """
        self.model_class = model_class
        self.table_name = table_name
        self.tenant_column = tenant_column
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def _get_tenant_context(self) -> TenantContext:
        """Get the current tenant context.

        Returns:
            Current TenantContext.

        Raises:
            RuntimeError: If no tenant context is set.
        """
        return require_tenant_context()

    def _get_tenant_id(self) -> str:
        """Get the current tenant ID.

        Returns:
            Current tenant ID.

        Raises:
            RuntimeError: If no tenant context is set.
        """
        return self._get_tenant_context().tenant_id

    @abstractmethod
    async def _execute_query(
        self,
        query: str,
        params: JSONDict | None = None,
    ) -> list[JSONDict]:
        """Execute a database query.

        Args:
            query: SQL query string.
            params: Query parameters.

        Returns:
            List of result rows as dictionaries.
        """
        pass

    @abstractmethod
    async def _execute_command(
        self,
        command: str,
        params: JSONDict | None = None,
    ) -> int:
        """Execute a database command (INSERT/UPDATE/DELETE).

        Args:
            command: SQL command string.
            params: Command parameters.

        Returns:
            Number of affected rows.
        """
        pass

    @abstractmethod
    async def _set_rls_context(self) -> None:
        """Set RLS context parameters for the current connection."""
        pass

    async def create(self, entity: T) -> T:
        """Create a new entity.

        Args:
            entity: Entity to create.

        Returns:
            Created entity with generated ID.
        """
        ctx = self._get_tenant_context()
        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Creating {self.model_class.__name__} "
            f"in tenant {ctx.tenant_id}"
        )
        # Implementation by subclass
        raise NotImplementedError

    async def get_by_id(self, entity_id: str) -> T | None:
        """Get an entity by ID.

        Args:
            entity_id: Entity identifier.

        Returns:
            Entity if found, None otherwise.
        """
        ctx = self._get_tenant_context()
        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Getting {self.model_class.__name__} "
            f"{entity_id} in tenant {ctx.tenant_id}"
        )
        # Implementation by subclass
        raise NotImplementedError

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> list[T]:
        """List all entities for the current tenant.

        Args:
            skip: Number of records to skip.
            limit: Maximum records to return.
            order_by: Column to order by.
            order_desc: Whether to order descending.

        Returns:
            List of entities.
        """
        ctx = self._get_tenant_context()
        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Listing {self.model_class.__name__} in tenant {ctx.tenant_id}"
        )
        # Implementation by subclass
        raise NotImplementedError

    async def update(self, entity_id: str, updates: JSONDict) -> T | None:
        """Update an entity.

        Args:
            entity_id: Entity identifier.
            updates: Dictionary of fields to update.

        Returns:
            Updated entity if found, None otherwise.
        """
        ctx = self._get_tenant_context()
        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Updating {self.model_class.__name__} "
            f"{entity_id} in tenant {ctx.tenant_id}"
        )
        # Implementation by subclass
        raise NotImplementedError

    async def delete(self, entity_id: str) -> bool:
        """Delete an entity.

        Args:
            entity_id: Entity identifier.

        Returns:
            True if deleted, False if not found.
        """
        ctx = self._get_tenant_context()
        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Deleting {self.model_class.__name__} "
            f"{entity_id} in tenant {ctx.tenant_id}"
        )
        # Implementation by subclass
        raise NotImplementedError


class TenantRepository:
    """Repository for tenant management operations.

    Constitutional Hash: 608508a9bd224290

    This repository handles tenant lifecycle operations:
    - Tenant creation and registration
    - Tenant activation and suspension
    - Tenant configuration management
    - Tenant deletion and cleanup

    Note: Tenant operations bypass RLS as they manage tenants themselves.
    """

    def __init__(self) -> None:
        """Initialize the tenant repository."""
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._tenants: dict[str, Tenant] = {}

    async def create_tenant(
        self,
        name: str,
        slug: str,
        config: TenantConfig | None = None,
        quota: TenantQuota | None = None,
        metadata: JSONDict | None = None,
        parent_tenant_id: str | None = None,
    ) -> Tenant:
        """Create a new tenant.

        Args:
            name: Human-readable tenant name.
            slug: URL-safe tenant slug.
            config: Tenant configuration.
            quota: Resource quota.
            metadata: Additional metadata.
            parent_tenant_id: Parent tenant for hierarchical tenancy.

        Returns:
            Created tenant.

        Raises:
            ValueError: If slug already exists.
        """
        # Check for duplicate slug
        for existing in self._tenants.values():
            if existing.slug == slug:
                raise ValueError(f"Tenant slug '{slug}' already exists")

        tenant = Tenant(
            tenant_id=str(uuid4()),
            name=name,
            slug=slug,
            status=TenantStatus.PENDING,
            config=config or TenantConfig(),
            quota=(quota or TenantQuota()).to_dict(),
            metadata=metadata or {},
            parent_tenant_id=parent_tenant_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        self._tenants[tenant.tenant_id] = tenant
        logger.info(f"[{CONSTITUTIONAL_HASH}] Created tenant: {tenant.tenant_id} ({tenant.slug})")

        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Tenant if found, None otherwise.
        """
        return self._tenants.get(tenant_id)

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        """Get a tenant by slug.

        Args:
            slug: Tenant slug.

        Returns:
            Tenant if found, None otherwise.
        """
        for tenant in self._tenants.values():
            if tenant.slug == slug:
                return tenant
        return None

    async def list_tenants(
        self,
        status: TenantStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Tenant]:
        """List all tenants.

        Args:
            status: Filter by status.
            skip: Number of records to skip.
            limit: Maximum records to return.

        Returns:
            List of tenants.
        """
        tenants = list(self._tenants.values())

        if status:
            tenants = [t for t in tenants if t.status == status]

        tenants.sort(key=lambda t: t.created_at, reverse=True)
        return tenants[skip : skip + limit]

    async def activate_tenant(self, tenant_id: str) -> Tenant | None:
        """Activate a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Activated tenant if found, None otherwise.
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        tenant.status = TenantStatus.ACTIVE
        tenant.activated_at = datetime.now(UTC)
        tenant.updated_at = datetime.now(UTC)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Activated tenant: {tenant_id}")
        return tenant

    async def suspend_tenant(
        self,
        tenant_id: str,
        reason: str | None = None,
    ) -> Tenant | None:
        """Suspend a tenant.

        Args:
            tenant_id: Tenant identifier.
            reason: Suspension reason.

        Returns:
            Suspended tenant if found, None otherwise.
        """
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        tenant.status = TenantStatus.SUSPENDED
        tenant.suspended_at = datetime.now(UTC)
        tenant.updated_at = datetime.now(UTC)
        if reason:
            tenant.metadata["suspension_reason"] = reason

        logger.warning(f"[{CONSTITUTIONAL_HASH}] Suspended tenant: {tenant_id} - {reason}")
        return tenant

    async def update_tenant_config(
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
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        tenant.config = config
        tenant.updated_at = datetime.now(UTC)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated config for tenant: {tenant_id}")
        return tenant

    async def update_tenant_quota(
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
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None

        tenant.quota = quota.to_dict()
        tenant.updated_at = datetime.now(UTC)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated quota for tenant: {tenant_id}")
        return tenant

    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            True if deleted, False if not found.
        """
        if tenant_id not in self._tenants:
            return False

        # Mark as deactivated first
        tenant = self._tenants[tenant_id]
        tenant.status = TenantStatus.DEACTIVATED
        tenant.updated_at = datetime.now(UTC)

        # Remove from in-memory store
        del self._tenants[tenant_id]

        logger.warning(f"[{CONSTITUTIONAL_HASH}] Deleted tenant: {tenant_id}")
        return True

    def get_tenant_count(self) -> int:
        """Get total number of tenants."""
        return len(self._tenants)

    def get_active_tenant_count(self) -> int:
        """Get number of active tenants."""
        return len([t for t in self._tenants.values() if t.is_active()])
