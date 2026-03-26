"""Tests for enhanced_agent_bus.multi_tenancy.db_repository_optimized — coverage boost.

Constitutional Hash: 608508a9bd224290

Tests DatabaseTenantRepository including ORM conversions, cache key generation,
helper methods, and CRUD operation logic. All database and cache calls are mocked.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
    _ORM_TO_PYDANTIC_STATUS,
    _PYDANTIC_TO_ORM_STATUS,
    DatabaseTenantRepository,
    TenantHierarchyNode,
    TenantSummary,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_cache():
    """Create a mock TieredCacheManager."""
    cache = AsyncMock()
    cache.initialize = AsyncMock(return_value=True)
    cache.close = AsyncMock()
    cache.get_async = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


def _make_repo(session, enable_caching=False, cache=None):
    """Create a DatabaseTenantRepository with optional cache override."""
    repo = DatabaseTenantRepository(session, enable_caching=enable_caching)
    if cache is not None:
        repo._tenant_cache = cache
    return repo


def _make_orm(**overrides):
    """Create a mock TenantORM."""
    from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

    now = datetime.now(UTC)
    defaults = {
        "tenant_id": "tid-001",
        "name": "Test Tenant",
        "slug": "test-tenant",
        "status": TenantStatusEnum.ACTIVE,
        "config": {},
        "quota": {},
        "metadata_": {},
        "parent_tenant_id": None,
        "constitutional_hash": "608508a9bd224290",
        "created_at": now,
        "updated_at": now,
        "activated_at": now,
        "suspended_at": None,
    }
    defaults.update(overrides)
    orm = MagicMock()
    for k, v in defaults.items():
        setattr(orm, k, v)
    return orm


# ---------------------------------------------------------------------------
# TenantSummary / TenantHierarchyNode
# ---------------------------------------------------------------------------


class TestProjectionDTOs:
    def test_tenant_summary_creation(self):
        now = datetime.now(UTC)
        s = TenantSummary(tenant_id="t1", name="Test", slug="test", status="active", created_at=now)
        assert s.tenant_id == "t1"
        assert s.status == "active"

    def test_tenant_summary_is_frozen(self):
        now = datetime.now(UTC)
        s = TenantSummary(tenant_id="t1", name="Test", slug="test", status="active", created_at=now)
        with pytest.raises(AttributeError):
            s.name = "Changed"  # type: ignore[misc]

    def test_hierarchy_node_creation(self):
        now = datetime.now(UTC)
        h = TenantHierarchyNode(
            tenant_id="t1",
            name="Parent",
            slug="parent",
            status="active",
            parent_tenant_id=None,
            child_count=3,
            created_at=now,
        )
        assert h.child_count == 3
        assert h.parent_tenant_id is None


# ---------------------------------------------------------------------------
# Status mapping constants
# ---------------------------------------------------------------------------


class TestStatusMapping:
    def test_orm_to_pydantic_mapping_complete(self):
        assert len(_ORM_TO_PYDANTIC_STATUS) == 5

    def test_pydantic_to_orm_mapping_complete(self):
        assert len(_PYDANTIC_TO_ORM_STATUS) == 5


# ---------------------------------------------------------------------------
# Cache key generation
# ---------------------------------------------------------------------------


class TestCacheKeyGeneration:
    def test_tenant_cache_key_deterministic(self, mock_session):
        repo = _make_repo(mock_session)
        k1 = repo._generate_tenant_cache_key("tid-001")
        k2 = repo._generate_tenant_cache_key("tid-001")
        assert k1 == k2
        assert k1.startswith("tenant:id:")

    def test_tenant_cache_key_varies_by_id(self, mock_session):
        repo = _make_repo(mock_session)
        k1 = repo._generate_tenant_cache_key("tid-001")
        k2 = repo._generate_tenant_cache_key("tid-002")
        assert k1 != k2

    def test_slug_cache_key_deterministic(self, mock_session):
        repo = _make_repo(mock_session)
        k1 = repo._generate_slug_cache_key("my-slug")
        k2 = repo._generate_slug_cache_key("my-slug")
        assert k1 == k2
        assert k1.startswith("tenant:slug:")

    def test_slug_cache_key_varies(self, mock_session):
        repo = _make_repo(mock_session)
        k1 = repo._generate_slug_cache_key("slug-a")
        k2 = repo._generate_slug_cache_key("slug-b")
        assert k1 != k2


# ---------------------------------------------------------------------------
# _invalidate_tenant_cache
# ---------------------------------------------------------------------------


class TestInvalidateTenantCache:
    @pytest.mark.asyncio
    async def test_no_cache_is_noop(self, mock_session):
        repo = _make_repo(mock_session, enable_caching=False)
        await repo._invalidate_tenant_cache("tid-001")  # Should not raise

    @pytest.mark.asyncio
    async def test_invalidates_by_id(self, mock_session, mock_cache):
        repo = _make_repo(mock_session, cache=mock_cache)
        await repo._invalidate_tenant_cache("tid-001")
        mock_cache.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidates_by_slug(self, mock_session, mock_cache):
        repo = _make_repo(mock_session, cache=mock_cache)
        await repo._invalidate_tenant_cache("tid-001", slug="my-slug")
        assert mock_cache.delete.await_count == 2


# ---------------------------------------------------------------------------
# ORM conversions
# ---------------------------------------------------------------------------


class TestOrmConversions:
    def test_orm_to_pydantic(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm()
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.tenant_id == "tid-001"
        assert tenant.name == "Test Tenant"
        assert tenant.slug == "test-tenant"

    def test_orm_to_pydantic_no_status(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm(status=None)
        tenant = repo._orm_to_pydantic(orm)
        # Should default to PENDING
        assert tenant.status is not None

    def test_orm_to_pydantic_no_dates(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm(created_at="not-a-datetime", updated_at="not-a-datetime")
        tenant = repo._orm_to_pydantic(orm)
        # Should fall back to datetime.now(UTC)
        assert isinstance(tenant.created_at, datetime)

    def test_status_to_orm(self, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        repo = _make_repo(mock_session)
        assert repo._status_to_orm(TenantStatus.ACTIVE) == TenantStatusEnum.ACTIVE
        assert repo._status_to_orm(None) == TenantStatusEnum.PENDING


# ---------------------------------------------------------------------------
# Helper methods
# ---------------------------------------------------------------------------


class TestHelperMethods:
    def test_dump_config_none(self, mock_session):
        repo = _make_repo(mock_session)
        assert repo._dump_config(None) == {}

    def test_dump_config_dict(self, mock_session):
        repo = _make_repo(mock_session)
        assert repo._dump_config({"theme": "dark"}) == {"theme": "dark"}

    def test_dump_config_pydantic(self, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantConfig

        repo = _make_repo(mock_session)
        config = TenantConfig()
        result = repo._dump_config(config)
        assert isinstance(result, dict)

    def test_dump_quota_none(self, mock_session):
        repo = _make_repo(mock_session)
        assert repo._dump_quota(None) == {}

    def test_dump_quota_dict(self, mock_session):
        repo = _make_repo(mock_session)
        assert repo._dump_quota({"limit": 100}) == {"limit": 100}

    def test_dump_quota_object_with_model_dump(self, mock_session):
        repo = _make_repo(mock_session)
        obj = MagicMock()
        obj.model_dump.return_value = {"max_agents": 10}
        assert repo._dump_quota(obj) == {"max_agents": 10}

    def test_dump_quota_object_without_model_dump(self, mock_session):
        repo = _make_repo(mock_session)
        obj = object()
        assert repo._dump_quota(obj) == {}

    def test_normalize_metadata_none(self, mock_session):
        repo = _make_repo(mock_session)
        assert repo._normalize_metadata(None) == {}

    def test_normalize_metadata_dict(self, mock_session):
        repo = _make_repo(mock_session)
        assert repo._normalize_metadata({"k": "v"}) == {"k": "v"}


# ---------------------------------------------------------------------------
# initialize / close
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_initialize_no_cache(self, mock_session):
        repo = _make_repo(mock_session, enable_caching=False)
        result = await repo.initialize()
        assert result is True

    @pytest.mark.asyncio
    async def test_initialize_with_cache(self, mock_session, mock_cache):
        repo = _make_repo(mock_session, cache=mock_cache)
        result = await repo.initialize()
        assert result is True
        mock_cache.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_no_cache(self, mock_session):
        repo = _make_repo(mock_session, enable_caching=False)
        await repo.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_with_cache(self, mock_session, mock_cache):
        repo = _make_repo(mock_session, cache=mock_cache)
        await repo.close()
        mock_cache.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_tenant
# ---------------------------------------------------------------------------


class TestGetTenant:
    @pytest.mark.asyncio
    async def test_get_tenant_found(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant("tid-001")
        assert tenant is not None
        assert tenant.tenant_id == "tid-001"

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant("nonexistent")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_get_tenant_cache_hit(self, mock_session, mock_cache):
        from enhanced_agent_bus.multi_tenancy.models import TenantConfig, TenantStatus

        now = datetime.now(UTC)
        cached_data = {
            "tenant_id": "tid-001",
            "name": "Cached",
            "slug": "cached",
            "status": TenantStatus.ACTIVE,
            "config": TenantConfig(),
            "quota": {},
            "metadata": {},
            "parent_tenant_id": "",
            "created_at": now,
            "updated_at": now,
            "activated_at": now,
            "suspended_at": None,
        }
        mock_cache.get_async.return_value = cached_data
        repo = _make_repo(mock_session, cache=mock_cache)

        tenant = await repo.get_tenant("tid-001")
        assert tenant is not None
        assert tenant.name == "Cached"
        # DB should not be called
        mock_session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_tenant_by_slug
# ---------------------------------------------------------------------------


class TestGetTenantBySlug:
    @pytest.mark.asyncio
    async def test_found(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm(slug="my-slug")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant_by_slug("my-slug")
        assert tenant is not None
        assert tenant.slug == "my-slug"

    @pytest.mark.asyncio
    async def test_not_found(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant_by_slug("nope")
        assert tenant is None


# ---------------------------------------------------------------------------
# list_tenants
# ---------------------------------------------------------------------------


class TestListTenants:
    @pytest.mark.asyncio
    async def test_list_all(self, mock_session):
        repo = _make_repo(mock_session)
        orm1 = _make_orm(tenant_id="t1", slug="s1")
        orm2 = _make_orm(tenant_id="t2", slug="s2")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [orm1, orm2]
        mock_session.execute.return_value = mock_result

        tenants = await repo.list_tenants()
        assert len(tenants) == 2

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        tenants = await repo.list_tenants(status=TenantStatus.ACTIVE)
        assert tenants == []


# ---------------------------------------------------------------------------
# activate_tenant / suspend_tenant
# ---------------------------------------------------------------------------


class TestLifecycleOps:
    @pytest.mark.asyncio
    async def test_activate_found(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.activate_tenant("tid-001")
        assert tenant is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_activate_not_found(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.activate_tenant("nonexistent")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_suspend_found(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.suspend_tenant("tid-001", reason="policy violation")
        assert tenant is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_suspend_not_found(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.suspend_tenant("nonexistent")
        assert tenant is None


# ---------------------------------------------------------------------------
# delete_tenant
# ---------------------------------------------------------------------------


class TestDeleteTenant:
    @pytest.mark.asyncio
    async def test_delete_found(self, mock_session):
        repo = _make_repo(mock_session)
        orm = _make_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = mock_result

        ok = await repo.delete_tenant("tid-001")
        assert ok is True
        mock_session.delete.assert_awaited_once_with(orm)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        ok = await repo.delete_tenant("nonexistent")
        assert ok is False


# ---------------------------------------------------------------------------
# count_tenants
# ---------------------------------------------------------------------------


class TestCountTenants:
    @pytest.mark.asyncio
    async def test_count_all(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute.return_value = mock_result

        count = await repo.count_tenants()
        assert count == 42

    @pytest.mark.asyncio
    async def test_count_with_status(self, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_session.execute.return_value = mock_result

        count = await repo.count_tenants(status=TenantStatus.ACTIVE)
        assert count == 10

    @pytest.mark.asyncio
    async def test_count_returns_zero_on_none(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        count = await repo.count_tenants()
        assert count == 0


# ---------------------------------------------------------------------------
# count_tenants_by_parent
# ---------------------------------------------------------------------------


class TestCountTenantsByParent:
    @pytest.mark.asyncio
    async def test_count_with_parent(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_session.execute.return_value = mock_result

        count = await repo.count_tenants_by_parent("parent-id")
        assert count == 5

    @pytest.mark.asyncio
    async def test_count_root_tenants(self, mock_session):
        repo = _make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        mock_session.execute.return_value = mock_result

        count = await repo.count_tenants_by_parent(None)
        assert count == 3


# ---------------------------------------------------------------------------
# _tenantorm_kwargs
# ---------------------------------------------------------------------------


class TestTenantOrmKwargs:
    def test_builds_correct_dict(self, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import Tenant, TenantConfig, TenantStatus

        repo = _make_repo(mock_session)
        now = datetime.now(UTC)
        tenant = MagicMock(spec=Tenant)
        tenant.tenant_id = "t1"
        tenant.name = "Test"
        tenant.slug = "test"
        tenant.status = TenantStatus.ACTIVE
        tenant.config = TenantConfig()
        tenant.quota = {}
        tenant.metadata = {}
        tenant.parent_tenant_id = None
        tenant.created_at = now
        tenant.updated_at = now
        tenant.activated_at = None
        tenant.suspended_at = None

        kwargs = repo._tenantorm_kwargs(tenant)
        assert kwargs["tenant_id"] == "t1"
        assert kwargs["name"] == "Test"
        assert "constitutional_hash" in kwargs
