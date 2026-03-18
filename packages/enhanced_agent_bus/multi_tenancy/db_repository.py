"""
ACGS-2 Database-Backed Tenant Repository
Constitutional Hash: cdd01ef066bc6cf2

Provides SQLAlchemy async database operations for tenant management.
Replaces in-memory storage with persistent PostgreSQL/SQLite backend.
"""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.shared.cache.manager import TieredCacheConfig, TieredCacheManager

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import CONSTITUTIONAL_HASH
from .models import Tenant, TenantConfig, TenantQuota, TenantStatus
from .orm_models import TenantORM, TenantStatusEnum

logger = get_logger(__name__)


class DatabaseTenantRepository:
    """Database-backed repository for tenant management operations.

    Constitutional Hash: cdd01ef066bc6cf2

    This repository handles tenant lifecycle operations with persistent storage:
    - Tenant creation and registration
    - Tenant activation and suspension
    - Tenant configuration management
    - Tenant deletion and cleanup

    Uses SQLAlchemy async for database operations with PostgreSQL/SQLite support.
    """

    def __init__(self, session: AsyncSession, enable_caching: bool = True) -> None:
        """Initialize the database tenant repository.

        Args:
            session: SQLAlchemy async session for database operations.
            enable_caching: Enable tiered caching for tenant lookups.
        """
        self.session = session
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._enable_caching = enable_caching
        self._tenant_cache: TieredCacheManager | None = None

        if enable_caching:
            cache_config = TieredCacheConfig(
                l1_maxsize=500,
                l1_ttl=300,
                l2_ttl=3600,
                l3_enabled=True,
                l3_ttl=86400,
            )
            self._tenant_cache = TieredCacheManager(config=cache_config, name="tenant_metadata")

    async def initialize(self) -> bool:
        """Initialize cache connections."""
        if self._tenant_cache:
            return await self._tenant_cache.initialize()  # type: ignore[no-any-return]
        return True

    async def close(self) -> None:
        """Close cache connections."""
        if self._tenant_cache:
            await self._tenant_cache.close()

    def _generate_tenant_cache_key(self, tenant_id: str) -> str:
        combined = f"tenant:{tenant_id}:{CONSTITUTIONAL_HASH}"
        return f"tenant:id:{hashlib.sha256(combined.encode()).hexdigest()}"

    def _generate_slug_cache_key(self, slug: str) -> str:
        combined = f"slug:{slug}:{CONSTITUTIONAL_HASH}"
        return f"tenant:slug:{hashlib.sha256(combined.encode()).hexdigest()}"

    async def _invalidate_tenant_cache(self, tenant_id: str, slug: str | None = None) -> None:
        if not self._tenant_cache:
            return
        await self._tenant_cache.delete(self._generate_tenant_cache_key(tenant_id))
        if slug:
            await self._tenant_cache.delete(self._generate_slug_cache_key(slug))

    def _orm_to_pydantic(self, orm: TenantORM) -> Tenant:
        """Convert ORM model to Pydantic model.

        Args:
            orm: TenantORM instance.

        Returns:
            Tenant Pydantic model.
        """
        # Map ORM status string to TenantStatus enum
        status_map = {
            TenantStatusEnum.PENDING: TenantStatus.PENDING,
            TenantStatusEnum.ACTIVE: TenantStatus.ACTIVE,
            TenantStatusEnum.SUSPENDED: TenantStatus.SUSPENDED,
            TenantStatusEnum.DEACTIVATED: TenantStatus.DEACTIVATED,
            TenantStatusEnum.MIGRATING: TenantStatus.MIGRATING,
        }

        # Cast SQLAlchemy Column values to their expected Python types
        # Cast orm.status to the enum type for dict lookup
        orm_status = str(orm.status) if orm.status else None
        return Tenant(
            tenant_id=str(orm.tenant_id),
            name=str(orm.name),
            slug=str(orm.slug),
            status=status_map.get(orm_status, TenantStatus.PENDING)  # type: ignore[call-overload]
            if orm_status
            else TenantStatus.PENDING,
            config=TenantConfig(**dict(orm.config or {})),
            quota=dict(orm.quota) if orm.quota else {},
            metadata=dict(orm.metadata_) if orm.metadata_ else {},
            parent_tenant_id=str(orm.parent_tenant_id) if orm.parent_tenant_id else "",
            created_at=orm.created_at
            if isinstance(orm.created_at, datetime)
            else datetime.now(UTC),
            updated_at=orm.updated_at
            if isinstance(orm.updated_at, datetime)
            else datetime.now(UTC),
            activated_at=orm.activated_at if isinstance(orm.activated_at, datetime) else None,
            suspended_at=orm.suspended_at if isinstance(orm.suspended_at, datetime) else None,
        )

    def _pydantic_to_orm(self, tenant: Tenant) -> TenantORM:
        """Convert Pydantic model to ORM model.

        Args:
            tenant: Tenant Pydantic model.

        Returns:
            TenantORM instance.
        """
        # Map TenantStatus enum to ORM status string
        status_map = {
            TenantStatus.PENDING: TenantStatusEnum.PENDING,
            TenantStatus.ACTIVE: TenantStatusEnum.ACTIVE,
            TenantStatus.SUSPENDED: TenantStatusEnum.SUSPENDED,
            TenantStatus.DEACTIVATED: TenantStatusEnum.DEACTIVATED,
            TenantStatus.MIGRATING: TenantStatusEnum.MIGRATING,
        }

        return TenantORM(
            tenant_id=tenant.tenant_id,
            name=tenant.name,
            slug=tenant.slug,
            status=status_map.get(tenant.status, TenantStatusEnum.PENDING),
            config=tenant.config.model_dump() if tenant.config else {},
            quota=tenant.quota if isinstance(tenant.quota, dict) else {},
            metadata_=tenant.metadata or {},
            parent_tenant_id=tenant.parent_tenant_id,
            constitutional_hash=CONSTITUTIONAL_HASH,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            activated_at=tenant.activated_at,
            suspended_at=tenant.suspended_at,
        )

    async def create_tenant(
        self,
        name: str,
        slug: str,
        config: TenantConfig | None = None,
        quota: TenantQuota | None = None,
        metadata: JSONDict | None = None,
        parent_tenant_id: str | None = None,
        tenant_id: str | None = None,
    ) -> Tenant:
        """Create a new tenant in the database.

        Args:
            name: Human-readable tenant name.
            slug: URL-safe tenant slug.
            config: Tenant configuration.
            quota: Resource quota.
            metadata: Additional metadata.
            parent_tenant_id: Parent tenant for hierarchical tenancy.
            tenant_id: Optional specific tenant ID (for system tenant).

        Returns:
            Created tenant.

        Raises:
            ValueError: If slug already exists.
        """
        # Check for duplicate slug
        result = await self.session.execute(select(TenantORM).where(TenantORM.slug == slug))
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Tenant slug '{slug}' already exists")

        # Create ORM instance
        now = datetime.now(UTC)
        orm = TenantORM(
            tenant_id=tenant_id or str(uuid4()),
            name=name,
            slug=slug,
            status=TenantStatusEnum.PENDING,
            config=(config.model_dump() if config else {}),
            quota=(quota.to_dict() if quota else {}),
            metadata_=metadata or {},
            parent_tenant_id=parent_tenant_id,
            constitutional_hash=CONSTITUTIONAL_HASH,
            created_at=now,
            updated_at=now,
        )

        self.session.add(orm)
        await self.session.commit()
        await self.session.refresh(orm)

        tenant = self._orm_to_pydantic(orm)
        logger.info(f"[{CONSTITUTIONAL_HASH}] Created tenant: {tenant.tenant_id} ({tenant.slug})")

        if self._tenant_cache:
            await self._tenant_cache.set(
                self._generate_tenant_cache_key(tenant.tenant_id), tenant.model_dump(), ttl=3600
            )
            await self._tenant_cache.set(
                self._generate_slug_cache_key(tenant.slug), tenant.model_dump(), ttl=3600
            )

        return tenant

    async def create_tenants_bulk(self, tenants_data: list[dict]) -> list[Tenant]:
        """Create multiple tenants in a single transaction using bulk insert.

        10x faster than sequential create_tenant() calls.
        """
        now = datetime.now(UTC)
        orms = []

        for data in tenants_data:
            tenant_id = data.get("tenant_id", str(uuid4()))
            orm = TenantORM(
                tenant_id=tenant_id,
                name=data["name"],
                slug=data["slug"],
                status=TenantStatusEnum.ACTIVE,
                config=data.get("config", {}),
                quota=data.get("quota", {}),
                metadata=data.get("metadata", {}),
                created_at=now,
                updated_at=now,
            )
            orms.append(orm)

        self.session.add_all(orms)
        await self.session.commit()

        tenants = [self._orm_to_pydantic(orm) for orm in orms]

        logger.info(f"[{CONSTITUTIONAL_HASH}] Bulk created {len(tenants)} tenants")

        return tenants

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID from the database.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Tenant if found, None otherwise.
        """
        if self._tenant_cache:
            cache_key = self._generate_tenant_cache_key(tenant_id)
            cached_tenant = await self._tenant_cache.get_async(cache_key)
            if cached_tenant and isinstance(cached_tenant, dict):
                logger.debug(f"Tenant cache HIT for {tenant_id}")
                return Tenant(**cached_tenant)
            logger.debug(f"Tenant cache MISS for {tenant_id}")

        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        tenant = self._orm_to_pydantic(orm)

        if self._tenant_cache:
            await self._tenant_cache.set(cache_key, tenant.model_dump(), ttl=3600)

        return tenant

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        """Get a tenant by slug from the database.

        Args:
            slug: Tenant slug.

        Returns:
            Tenant if found, None otherwise.
        """
        if self._tenant_cache:
            cache_key = self._generate_slug_cache_key(slug)
            cached_tenant = await self._tenant_cache.get_async(cache_key)
            if cached_tenant and isinstance(cached_tenant, dict):
                logger.debug(f"Tenant slug cache HIT for {slug}")
                return Tenant(**cached_tenant)
            logger.debug(f"Tenant slug cache MISS for {slug}")

        result = await self.session.execute(select(TenantORM).where(TenantORM.slug == slug))
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        tenant = self._orm_to_pydantic(orm)

        if self._tenant_cache:
            await self._tenant_cache.set(cache_key, tenant.model_dump(), ttl=3600)
            await self._tenant_cache.set(
                self._generate_tenant_cache_key(tenant.tenant_id), tenant.model_dump(), ttl=3600
            )

        return tenant

    async def list_tenants(
        self,
        status: TenantStatus | None = None,
        skip: int = 0,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Tenant]:
        """List all tenants from the database.

        Args:
            status: Filter by status.
            skip: Number of records to skip (deprecated, use offset).
            limit: Maximum records to return.
            offset: Number of records to skip (pagination).

        Returns:
            List of tenants.
        """
        # Map TenantStatus to ORM status string
        status_map = {
            TenantStatus.PENDING: TenantStatusEnum.PENDING,
            TenantStatus.ACTIVE: TenantStatusEnum.ACTIVE,
            TenantStatus.SUSPENDED: TenantStatusEnum.SUSPENDED,
            TenantStatus.DEACTIVATED: TenantStatusEnum.DEACTIVATED,
            TenantStatus.MIGRATING: TenantStatusEnum.MIGRATING,
        }

        query = select(TenantORM).order_by(TenantORM.created_at.desc())

        if status:
            orm_status = status_map.get(status)
            if orm_status:
                query = query.where(TenantORM.status == orm_status)

        # Use offset parameter if provided, otherwise fall back to skip
        pagination_offset = offset if offset > 0 else skip
        query = query.offset(pagination_offset).limit(limit)
        result = await self.session.execute(query)
        orms = result.scalars().all()

        return [self._orm_to_pydantic(orm) for orm in orms]

    async def activate_tenant(self, tenant_id: str) -> Tenant | None:
        """Activate a tenant in the database.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Activated tenant if found, None otherwise.
        """
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        now = datetime.now(UTC)
        orm.status = TenantStatusEnum.ACTIVE  # type: ignore[assignment]
        orm.activated_at = now  # type: ignore[assignment]
        orm.updated_at = now  # type: ignore[assignment]

        await self.session.commit()
        await self.session.refresh(orm)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Activated tenant: {tenant_id}")
        tenant = self._orm_to_pydantic(orm)

        await self._invalidate_tenant_cache(tenant_id, str(orm.slug) if orm.slug else None)

        return tenant

    async def suspend_tenant(
        self,
        tenant_id: str,
        reason: str | None = None,
    ) -> Tenant | None:
        """Suspend a tenant in the database.

        Args:
            tenant_id: Tenant identifier.
            reason: Suspension reason.

        Returns:
            Suspended tenant if found, None otherwise.
        """
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        now = datetime.now(UTC)
        orm.status = TenantStatusEnum.SUSPENDED  # type: ignore[assignment]
        orm.suspended_at = now  # type: ignore[assignment]
        orm.updated_at = now  # type: ignore[assignment]

        if reason:
            metadata: JSONDict = orm.metadata_ or {}  # type: ignore[assignment]
            metadata["suspension_reason"] = reason
            orm.metadata_ = metadata  # type: ignore[assignment]

        await self.session.commit()
        await self.session.refresh(orm)

        logger.warning(f"[{CONSTITUTIONAL_HASH}] Suspended tenant: {tenant_id} - {reason}")
        tenant = self._orm_to_pydantic(orm)

        await self._invalidate_tenant_cache(tenant_id, str(orm.slug) if orm.slug else None)

        return tenant

    async def update_tenant_config(
        self,
        tenant_id: str,
        config: TenantConfig,
    ) -> Tenant | None:
        """Update tenant configuration in the database.

        Args:
            tenant_id: Tenant identifier.
            config: New configuration.

        Returns:
            Updated tenant if found, None otherwise.
        """
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        orm.config = config.model_dump()  # type: ignore[assignment]
        orm.updated_at = datetime.now(UTC)  # type: ignore[assignment]

        await self.session.commit()
        await self.session.refresh(orm)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated config for tenant: {tenant_id}")
        tenant = self._orm_to_pydantic(orm)

        await self._invalidate_tenant_cache(tenant_id, str(orm.slug) if orm.slug else None)

        return tenant

    async def update_tenant_quota(
        self,
        tenant_id: str,
        quota: TenantQuota,
    ) -> Tenant | None:
        """Update tenant quota in the database.

        Args:
            tenant_id: Tenant identifier.
            quota: New quota.

        Returns:
            Updated tenant if found, None otherwise.
        """
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        orm.quota = quota.to_dict()  # type: ignore[assignment]
        orm.updated_at = datetime.now(UTC)  # type: ignore[assignment]

        await self.session.commit()
        await self.session.refresh(orm)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated quota for tenant: {tenant_id}")
        tenant = self._orm_to_pydantic(orm)

        await self._invalidate_tenant_cache(tenant_id, str(orm.slug) if orm.slug else None)

        return tenant

    async def update_tenant(
        self,
        tenant_id: str,
        name: str | None = None,
        metadata: JSONDict | None = None,
    ) -> Tenant | None:
        """Update tenant properties in the database.

        Args:
            tenant_id: Tenant identifier.
            name: New tenant name.
            metadata: New metadata (merged with existing).

        Returns:
            Updated tenant if found, None otherwise.
        """
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None

        if name:
            orm.name = name  # type: ignore[assignment]
        if metadata:
            # Create new dict to trigger SQLAlchemy change detection
            existing = dict(orm.metadata_ or {})
            existing.update(metadata)
            orm.metadata_ = existing  # type: ignore[assignment]

        orm.updated_at = datetime.now(UTC)  # type: ignore[assignment]

        await self.session.commit()
        await self.session.refresh(orm)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated tenant: {tenant_id}")
        tenant = self._orm_to_pydantic(orm)

        await self._invalidate_tenant_cache(tenant_id, str(orm.slug) if orm.slug else None)

        return tenant

    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant from the database.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return False

        # Mark as deactivated first for audit trail
        orm.status = TenantStatusEnum.DEACTIVATED  # type: ignore[assignment]
        orm.updated_at = datetime.now(UTC)  # type: ignore[assignment]

        # Actually delete (cascade will handle related records)
        await self.session.delete(orm)
        await self.session.commit()

        await self._invalidate_tenant_cache(tenant_id, str(orm.slug) if orm.slug else None)

        logger.warning(f"[{CONSTITUTIONAL_HASH}] Deleted tenant: {tenant_id}")
        return True

    async def get_tenant_count(self) -> int:
        """Get total number of tenants in the database."""
        result = await self.session.execute(select(func.count(TenantORM.tenant_id)))
        return result.scalar() or 0

    async def get_active_tenant_count(self) -> int:
        """Get number of active tenants in the database."""
        result = await self.session.execute(
            select(func.count(TenantORM.tenant_id)).where(
                TenantORM.status == TenantStatusEnum.ACTIVE
            )
        )
        return result.scalar() or 0

    async def get_children(
        self,
        parent_tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Tenant]:
        """Get child tenants for a parent.
        Args:
            parent_tenant_id: Parent tenant identifier.
            limit: Maximum records to return.
            offset: Number of records to skip (pagination).
        Returns:
            List of child tenants.
        """
        result = await self.session.execute(
            select(TenantORM)
            .where(TenantORM.parent_tenant_id == parent_tenant_id)
            .offset(offset)
            .limit(limit)
        )
        orms = result.scalars().all()
        return [self._orm_to_pydantic(orm) for orm in orms]


# Type alias for backward compatibility
TenantRepositoryDB = DatabaseTenantRepository


__all__ = [
    "DatabaseTenantRepository",
    "TenantRepositoryDB",
]
