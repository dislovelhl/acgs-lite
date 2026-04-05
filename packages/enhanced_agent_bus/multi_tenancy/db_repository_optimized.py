"""
ACGS-2 Database-Backed Tenant Repository (Optimized)
Constitutional Hash: 608508a9bd224290

Provides SQLAlchemy async database operations for tenant management.
Optimized with:
- Bulk operations for batch processing
- N+1-safe eager loading
- Unified pagination framework
- Projection support for lightweight queries

Replaces in-memory storage with persistent PostgreSQL/SQLite backend.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enhanced_agent_bus._compat.cache.manager import TieredCacheConfig, TieredCacheManager
from enhanced_agent_bus._compat.database.utils import (
    BulkOperations,
    Page,
    Pageable,
    paginate,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import CONSTITUTIONAL_HASH
from .models import Tenant, TenantConfig, TenantQuota, TenantStatus
from .orm_models import TenantORM, TenantStatusEnum

logger = get_logger(__name__)

# =============================================================================
# Status mapping constants (ORM ↔ Pydantic)
# =============================================================================

_ORM_TO_PYDANTIC_STATUS: dict[TenantStatusEnum, TenantStatus] = {
    TenantStatusEnum.PENDING: TenantStatus.PENDING,
    TenantStatusEnum.ACTIVE: TenantStatus.ACTIVE,
    TenantStatusEnum.SUSPENDED: TenantStatus.SUSPENDED,
    TenantStatusEnum.DEACTIVATED: TenantStatus.DEACTIVATED,
    TenantStatusEnum.MIGRATING: TenantStatus.MIGRATING,
}

_PYDANTIC_TO_ORM_STATUS: dict[TenantStatus | str, TenantStatusEnum] = {
    TenantStatus.PENDING: TenantStatusEnum.PENDING,
    TenantStatus.ACTIVE: TenantStatusEnum.ACTIVE,
    TenantStatus.SUSPENDED: TenantStatusEnum.SUSPENDED,
    TenantStatus.DEACTIVATED: TenantStatusEnum.DEACTIVATED,
    TenantStatus.MIGRATING: TenantStatusEnum.MIGRATING,
}

# =============================================================================
# Projection DTOs
# =============================================================================


@dataclass(frozen=True)
class TenantSummary:
    """Lightweight projection for tenant list views.

    Reduces memory usage by selecting only needed columns.
    """

    tenant_id: str
    name: str
    slug: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class TenantHierarchyNode:
    """Projection for hierarchical tenant views with child count."""

    tenant_id: str
    name: str
    slug: str
    status: str
    parent_tenant_id: str | None
    child_count: int
    created_at: datetime


# =============================================================================
# Optimized Tenant Repository
# =============================================================================


class DatabaseTenantRepository:
    """Database-backed repository for tenant management operations.

    Constitutional Hash: 608508a9bd224290

    This repository handles tenant lifecycle operations with persistent storage:
    - Tenant creation and registration (with bulk support)
    - Tenant activation and suspension
    - Tenant configuration management
    - Tenant deletion and cleanup
    - Hierarchical tenant queries

    Uses SQLAlchemy 2.0 async for database operations with PostgreSQL/SQLite support.
    Optimized for high-performance batch operations and N+1-safe loading.
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
            return bool(await self._tenant_cache.initialize())
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

    # ==========================================================================
    # ORM Conversions
    # ==========================================================================

    def _orm_to_pydantic(self, orm: TenantORM) -> Tenant:
        """Convert ORM model to Pydantic model."""
        orm_status = str(orm.status) if orm.status else None
        return Tenant(
            tenant_id=str(orm.tenant_id),
            name=str(orm.name),
            slug=str(orm.slug),
            status=_ORM_TO_PYDANTIC_STATUS.get(orm_status, TenantStatus.PENDING)
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
        """Convert Pydantic model to ORM model."""
        return TenantORM(**self._tenantorm_kwargs(tenant))

    def _status_to_orm(self, status: TenantStatus | str | None) -> TenantStatusEnum:
        return _PYDANTIC_TO_ORM_STATUS.get(status, TenantStatusEnum.PENDING)

    def _dump_config(self, config: TenantConfig | JSONDict | None) -> JSONDict:
        if config is None:
            return {}
        if isinstance(config, dict):
            return config
        return config.model_dump()

    def _dump_quota(self, quota: TenantQuota | JSONDict | None) -> JSONDict:
        if quota is None:
            return {}
        if isinstance(quota, dict):
            return quota
        if hasattr(quota, "model_dump"):
            return quota.model_dump()
        return {}

    def _normalize_metadata(self, metadata: JSONDict | None) -> JSONDict:
        return metadata or {}

    def _tenantorm_kwargs(self, tenant: Tenant) -> JSONDict:
        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "slug": tenant.slug,
            "status": self._status_to_orm(tenant.status),
            "config": self._dump_config(tenant.config),
            "quota": self._dump_quota(tenant.quota),
            "metadata_": self._normalize_metadata(tenant.metadata),
            "parent_tenant_id": tenant.parent_tenant_id,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
            "activated_at": tenant.activated_at,
            "suspended_at": tenant.suspended_at,
        }

    # ==========================================================================
    # CRUD Operations
    # ==========================================================================

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
        """Create a new tenant in the database."""
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

    # ==========================================================================
    # Bulk Operations (NEW - 10-50x faster)
    # ==========================================================================

    async def create_tenants_bulk_optimized(
        self,
        tenants_data: list[dict],
        batch_size: int = 1000,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Tenant]:
        """Create multiple tenants using optimized bulk insert.
        Uses SQLAlchemy Core for maximum performance.
        Args:
            tenants_data: List of tenant dictionaries with keys:
                - name (required)
                - slug (required)
                - config (optional)
                - quota (optional)
                - metadata (optional)
                - parent_tenant_id (optional)
                - tenant_id (optional, auto-generated if not provided)
            batch_size: Number of records per batch (default 1000)
            limit: Maximum records to return (pagination).
            offset: Number of records to skip (pagination).
        Returns:
            List of created Tenant objects
            ValueError: If duplicate slug exists (constraint violation)
            tenants = [
                {"name": "Tenant A", "slug": "tenant-a"},
                {"name": "Tenant B", "slug": "tenant-b", "config": {"theme": "dark"}},
            ]
            created = await repo.create_tenants_bulk_optimized(tenants)
        """
        now = datetime.now(UTC)
        values = []
        for data in tenants_data:
            values.append(
                {
                    "tenant_id": data.get("tenant_id", str(uuid4())),
                    "name": data["name"],
                    "slug": data["slug"],
                    "status": TenantStatusEnum.ACTIVE,
                    "config": data.get("config", {}),
                    "quota": data.get("quota", {}),
                    "metadata_": data.get("metadata", {}),
                    "parent_tenant_id": data.get("parent_tenant_id"),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        # Use bulk insert (10-50x faster)
        await BulkOperations.bulk_insert(
            self.session,
            TenantORM.__table__,
            values,
            batch_size=batch_size,
            return_defaults=False,
        )
        # Fetch created tenants (using slugs for lookup)
        slugs = [data["slug"] for data in tenants_data]
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.slug.in_(slugs)).offset(offset).limit(limit)
        )
        orms = result.scalars().all()

        tenants = [self._orm_to_pydantic(orm) for orm in orms]

        # Update cache
        if self._tenant_cache:
            for tenant in tenants:
                await self._tenant_cache.set(
                    self._generate_tenant_cache_key(tenant.tenant_id),
                    tenant.model_dump(),
                    ttl=3600,
                )
                await self._tenant_cache.set(
                    self._generate_slug_cache_key(tenant.slug),
                    tenant.model_dump(),
                    ttl=3600,
                )

        logger.info(f"[{CONSTITUTIONAL_HASH}] Bulk created {len(tenants)} tenants")
        return tenants

    async def update_tenants_bulk(
        self,
        updates: list[dict],
        batch_size: int = 1000,
    ) -> int:
        """Update multiple tenants using optimized bulk update.

        10-50x faster than individual updates.

        Args:
            updates: List of dictionaries with keys:
                - tenant_id (required): The ID of tenant to update
                - object other columns to update
            batch_size: Number of records per batch

        Returns:
            Number of rows updated

        Example:
            updates = [
                {"tenant_id": "id1", "status": "active", "updated_at": now},
                {"tenant_id": "id2", "status": "suspended", "updated_at": now},
            ]
            count = await repo.update_tenants_bulk(updates)
        """
        count = await BulkOperations.bulk_update(
            self.session,
            TenantORM.__table__,
            updates,
            id_column="tenant_id",
            batch_size=batch_size,
        )

        # Invalidate cache for updated tenants
        if self._tenant_cache:
            for update in updates:
                tenant_id = update.get("tenant_id")
                if tenant_id:
                    await self._invalidate_tenant_cache(tenant_id)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Bulk updated {count} tenants")
        return int(count)

    # ==========================================================================
    # Read Operations with N+1-Safe Loading
    # ==========================================================================

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID from the database."""
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
        """Get a tenant by slug from the database."""
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

    # ==========================================================================
    # Optimized List with Pagination (N+1 Safe)
    # ==========================================================================

    async def list_tenants(
        self,
        status: TenantStatus | None = None,
        skip: int = 0,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Tenant]:
        """List all tenants from the database.

        DEPRECATED: Use list_tenants_paginated for better performance.
        """
        query = select(TenantORM).order_by(TenantORM.created_at.desc())

        if status:
            orm_status = _PYDANTIC_TO_ORM_STATUS.get(status)
            if orm_status:
                query = query.where(TenantORM.status == orm_status)

        query = query.offset(offset if offset > 0 else skip).limit(limit)

        result = await self.session.execute(query)
        orms = result.scalars().all()

        return [self._orm_to_pydantic(orm) for orm in orms]

    async def list_tenants_paginated(
        self,
        pageable: Pageable,
        status: TenantStatus | None = None,
    ) -> Page[Tenant]:
        """List tenants with pagination and sorting support.

        N+1-safe with optimized count query.

        Args:
            pageable: Pagination and sorting parameters
            status: Optional status filter

        Returns:
            Page with tenants and metadata

        Example:
            pageable = Pageable(page=0, size=20, sort=[("created_at", "desc")])
            page = await repo.list_tenants_paginated(pageable, status=TenantStatus.ACTIVE)

            for tenant in page.content:
                logger.debug("Tenant: %s", tenant.name)
            logger.info("Total: %d, Pages: %d", page.total_elements, page.total_pages)
        """
        # Base query
        stmt = select(TenantORM)

        # Apply status filter if provided
        if status:
            orm_status = _PYDANTIC_TO_ORM_STATUS.get(status)
            if orm_status:
                stmt = stmt.where(TenantORM.status == orm_status)

        # Use optimized pagination
        page = await paginate(self.session, stmt, pageable)

        # Convert to Pydantic models
        tenants = [self._orm_to_pydantic(orm) for orm in page.content]

        return Page(
            content=tenants,
            total_elements=page.total_elements,
            page_number=page.page_number,
            page_size=page.page_size,
        )

    # ==========================================================================
    # Projection Queries (Lightweight DTOs)
    # ==========================================================================

    async def list_tenant_summaries(
        self,
        pageable: Pageable,
        status: TenantStatus | None = None,
    ) -> Page[TenantSummary]:
        """List tenant summaries with projection (faster than full entities).

        Selects only needed columns for list views, reducing memory usage.

        Args:
            pageable: Pagination parameters
            status: Optional status filter

        Returns:
            Page of TenantSummary projections
        """
        # Select only needed columns (projection)
        stmt = select(
            TenantORM.tenant_id,
            TenantORM.name,
            TenantORM.slug,
            TenantORM.status,
            TenantORM.created_at,
        )

        if status:
            orm_status = _PYDANTIC_TO_ORM_STATUS.get(status)
            if orm_status:
                stmt = stmt.where(TenantORM.status == orm_status)

        # Get total count
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(TenantORM)
        if status:
            orm_status = _PYDANTIC_TO_ORM_STATUS.get(status)
            if orm_status:
                count_stmt = count_stmt.where(TenantORM.status == orm_status)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Apply sorting
        for field, direction in pageable.sort:
            column = getattr(TenantORM, field, None)
            if column is not None:
                if direction.lower() == "desc":
                    stmt = stmt.order_by(column.desc())
                else:
                    stmt = stmt.order_by(column.asc())

        # Apply pagination
        stmt = stmt.offset(pageable.offset).limit(pageable.limit)

        result = await self.session.execute(stmt)
        rows = result.all()

        summaries = [
            TenantSummary(
                tenant_id=str(row.tenant_id),
                name=str(row.name),
                slug=str(row.slug),
                status=str(row.status),
                created_at=row.created_at,
            )
            for row in rows
        ]

        return Page(
            content=summaries,
            total_elements=total,
            page_number=pageable.page,
            page_size=pageable.size,
        )

    async def get_tenant_hierarchy(
        self,
        parent_tenant_id: str | None = None,
    ) -> list[TenantHierarchyNode]:
        """Get tenant hierarchy with child counts.

        Uses efficient aggregation query instead of N+1 relationship loading.

        Args:
            parent_tenant_id: Filter by parent tenant (None for root tenants)

        Returns:
            List of hierarchy nodes with child counts
        """
        from sqlalchemy import func

        # Build subquery for child counts
        child_count_subq = (
            select(
                TenantORM.parent_tenant_id,
                func.count(TenantORM.tenant_id).label("child_count"),
            )
            .where(TenantORM.parent_tenant_id.isnot(None))
            .group_by(TenantORM.parent_tenant_id)
            .subquery()
        )

        # Main query with left join to child counts
        stmt = select(
            TenantORM.tenant_id,
            TenantORM.name,
            TenantORM.slug,
            TenantORM.status,
            TenantORM.parent_tenant_id,
            TenantORM.created_at,
            func.coalesce(child_count_subq.c.child_count, 0).label("child_count"),
        ).outerjoin(
            child_count_subq,
            TenantORM.tenant_id == child_count_subq.c.parent_tenant_id,
        )

        if parent_tenant_id:
            stmt = stmt.where(TenantORM.parent_tenant_id == parent_tenant_id)
        else:
            stmt = stmt.where(TenantORM.parent_tenant_id.is_(None))

        stmt = stmt.order_by(TenantORM.created_at.desc())

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            TenantHierarchyNode(
                tenant_id=str(row.tenant_id),
                name=str(row.name),
                slug=str(row.slug),
                status=str(row.status),
                parent_tenant_id=str(row.parent_tenant_id) if row.parent_tenant_id else None,
                child_count=row.child_count,
                created_at=row.created_at,
            )
            for row in rows
        ]

    # ==========================================================================
    # Lifecycle Operations
    # ==========================================================================

    async def activate_tenant(self, tenant_id: str) -> Tenant | None:
        """Activate a tenant in the database."""
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
        """Suspend a tenant in the database."""
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

        await self.session.commit()
        await self.session.refresh(orm)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Suspended tenant: {tenant_id}")
        tenant = self._orm_to_pydantic(orm)

        await self._invalidate_tenant_cache(tenant_id, str(orm.slug) if orm.slug else None)

        return tenant

    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant from the database."""
        result = await self.session.execute(
            select(TenantORM).where(TenantORM.tenant_id == tenant_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return False

        slug = str(orm.slug) if orm.slug else None

        await self.session.delete(orm)
        await self.session.commit()

        logger.info(f"[{CONSTITUTIONAL_HASH}] Deleted tenant: {tenant_id}")

        await self._invalidate_tenant_cache(tenant_id, slug)

        return True

    async def delete_tenants_bulk(self, tenant_ids: list[str], batch_size: int = 1000) -> int:
        """Delete multiple tenants using optimized bulk delete.

        10-50x faster than individual deletes.

        Args:
            tenant_ids: List of tenant IDs to delete
            batch_size: Batch size for processing

        Returns:
            Number of tenants deleted
        """
        count = await BulkOperations.bulk_delete(
            self.session,
            TenantORM.__table__,
            tenant_ids,
            id_column="tenant_id",
            batch_size=batch_size,
        )

        # Invalidate cache
        if self._tenant_cache:
            for tenant_id in tenant_ids:
                await self._invalidate_tenant_cache(tenant_id)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Bulk deleted {count} tenants")
        return int(count)

    # ==========================================================================
    # Statistics
    # ==========================================================================

    async def count_tenants(self, status: TenantStatus | None = None) -> int:
        """Count tenants with optional status filter."""
        from sqlalchemy import func

        stmt = select(func.count(TenantORM.tenant_id))

        if status:
            orm_status = _PYDANTIC_TO_ORM_STATUS.get(status)
            if orm_status:
                stmt = stmt.where(TenantORM.status == orm_status)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_tenants_by_parent(self, parent_tenant_id: str | None = None) -> int:
        """Count child tenants for a parent tenant."""
        from sqlalchemy import func

        stmt = select(func.count(TenantORM.tenant_id))

        if parent_tenant_id:
            stmt = stmt.where(TenantORM.parent_tenant_id == parent_tenant_id)
        else:
            stmt = stmt.where(TenantORM.parent_tenant_id.is_(None))

        result = await self.session.execute(stmt)
        return result.scalar() or 0
