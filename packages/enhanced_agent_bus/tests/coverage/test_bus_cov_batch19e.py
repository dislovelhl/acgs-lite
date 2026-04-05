"""
Coverage tests for:
1. enhanced_agent_bus.multi_tenancy.db_repository_optimized (DatabaseTenantRepository)
2. enhanced_agent_bus.opa_client.core (OPAClientCore, OPAClient, singleton helpers)
3. enhanced_agent_bus.deliberation_layer.impact_scorer (ImpactScorer)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. DatabaseTenantRepository tests
# ---------------------------------------------------------------------------


class TestDatabaseTenantRepository:
    """Tests for multi_tenancy.db_repository_optimized.DatabaseTenantRepository."""

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture()
    def repo(self, mock_session: AsyncMock) -> Any:
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            DatabaseTenantRepository,
        )

        return DatabaseTenantRepository(session=mock_session, enable_caching=False)

    @pytest.fixture()
    def repo_cached(self, mock_session: AsyncMock) -> Any:
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            DatabaseTenantRepository,
        )

        return DatabaseTenantRepository(session=mock_session, enable_caching=True)

    # -- Init / lifecycle ---------------------------------------------------

    def test_init_no_cache(self, repo: Any) -> None:
        assert repo._tenant_cache is None
        assert repo._enable_caching is False

    def test_init_with_cache(self, repo_cached: Any) -> None:
        assert repo_cached._tenant_cache is not None
        assert repo_cached._enable_caching is True

    async def test_initialize_no_cache(self, repo: Any) -> None:
        result = await repo.initialize()
        assert result is True

    async def test_initialize_with_cache(self, repo_cached: Any) -> None:
        repo_cached._tenant_cache.initialize = AsyncMock(return_value=True)
        result = await repo_cached.initialize()
        assert result is True

    async def test_close_no_cache(self, repo: Any) -> None:
        await repo.close()  # should not raise

    async def test_close_with_cache(self, repo_cached: Any) -> None:
        repo_cached._tenant_cache.close = AsyncMock()
        await repo_cached.close()
        repo_cached._tenant_cache.close.assert_awaited_once()

    # -- Cache key generation -----------------------------------------------

    def test_generate_tenant_cache_key(self, repo: Any) -> None:
        from enhanced_agent_bus.multi_tenancy.context import CONSTITUTIONAL_HASH

        key = repo._generate_tenant_cache_key("t1")
        combined = f"tenant:t1:{CONSTITUTIONAL_HASH}"
        expected = f"tenant:id:{hashlib.sha256(combined.encode()).hexdigest()}"
        assert key == expected

    def test_generate_slug_cache_key(self, repo: Any) -> None:
        from enhanced_agent_bus.multi_tenancy.context import CONSTITUTIONAL_HASH

        key = repo._generate_slug_cache_key("my-slug")
        combined = f"slug:my-slug:{CONSTITUTIONAL_HASH}"
        expected = f"tenant:slug:{hashlib.sha256(combined.encode()).hexdigest()}"
        assert key == expected

    # -- Cache invalidation -------------------------------------------------

    async def test_invalidate_tenant_cache_noop_without_cache(self, repo: Any) -> None:
        await repo._invalidate_tenant_cache("t1", "slug1")  # no error

    async def test_invalidate_tenant_cache_with_slug(self, repo_cached: Any) -> None:
        repo_cached._tenant_cache.delete = AsyncMock()
        await repo_cached._invalidate_tenant_cache("t1", "slug1")
        assert repo_cached._tenant_cache.delete.await_count == 2

    async def test_invalidate_tenant_cache_without_slug(self, repo_cached: Any) -> None:
        repo_cached._tenant_cache.delete = AsyncMock()
        await repo_cached._invalidate_tenant_cache("t1")
        assert repo_cached._tenant_cache.delete.await_count == 1

    # -- ORM conversions ----------------------------------------------------

    def test_orm_to_pydantic_full(self, repo: Any) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        now = datetime.now(UTC)
        orm = SimpleNamespace(
            tenant_id="t1",
            name="Test",
            slug="test",
            status=TenantStatusEnum.ACTIVE,
            config={"enable_batch_processing": True},
            quota={"max_agents": 50},
            metadata_={"key": "val"},
            parent_tenant_id="p1",
            created_at=now,
            updated_at=now,
            activated_at=now,
            suspended_at=None,
        )
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.tenant_id == "t1"
        assert tenant.name == "Test"
        assert tenant.slug == "test"
        assert tenant.parent_tenant_id == "p1"

    def test_orm_to_pydantic_no_status(self, repo: Any) -> None:
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        orm = SimpleNamespace(
            tenant_id="t2",
            name="NoStatus",
            slug="no-status",
            status=None,
            config=None,
            quota=None,
            metadata_=None,
            parent_tenant_id=None,
            created_at="not-a-datetime",
            updated_at="not-a-datetime",
            activated_at="not-a-datetime",
            suspended_at="not-a-datetime",
        )
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.status == TenantStatus.PENDING
        assert isinstance(tenant.created_at, datetime)

    def test_pydantic_to_orm(self, repo: Any) -> None:
        from enhanced_agent_bus.multi_tenancy.models import Tenant

        tenant = Tenant(name="Org", slug="or-gg")
        orm = repo._pydantic_to_orm(tenant)
        assert orm.name == "Org"

    def test_status_to_orm_unknown(self, repo: Any) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        result = repo._status_to_orm("nonexistent")
        assert result == TenantStatusEnum.PENDING

    def test_dump_config_none(self, repo: Any) -> None:
        assert repo._dump_config(None) == {}

    def test_dump_config_dict(self, repo: Any) -> None:
        assert repo._dump_config({"a": 1}) == {"a": 1}

    def test_dump_config_pydantic(self, repo: Any) -> None:
        from enhanced_agent_bus.multi_tenancy.models import TenantConfig

        cfg = TenantConfig()
        result = repo._dump_config(cfg)
        assert isinstance(result, dict)
        assert "enable_batch_processing" in result

    def test_dump_quota_none(self, repo: Any) -> None:
        assert repo._dump_quota(None) == {}

    def test_dump_quota_dict(self, repo: Any) -> None:
        assert repo._dump_quota({"max_agents": 5}) == {"max_agents": 5}

    def test_dump_quota_with_model_dump(self, repo: Any) -> None:
        obj = SimpleNamespace(model_dump=lambda: {"x": 1})
        assert repo._dump_quota(obj) == {"x": 1}

    def test_dump_quota_no_model_dump(self, repo: Any) -> None:
        obj = SimpleNamespace()
        assert repo._dump_quota(obj) == {}

    def test_normalize_metadata(self, repo: Any) -> None:
        assert repo._normalize_metadata(None) == {}
        assert repo._normalize_metadata({"k": "v"}) == {"k": "v"}

    # -- CRUD: create_tenant ------------------------------------------------

    async def test_create_tenant_duplicate_slug(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = SimpleNamespace(slug="dup")
        mock_session.execute.return_value = result_mock

        with pytest.raises(ValueError, match="already exists"):
            await repo.create_tenant(name="Dup", slug="dup")

    async def test_create_tenant_success(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        # First call: check slug -> no existing
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None

        now = datetime.now(UTC)
        created_orm = SimpleNamespace(
            tenant_id="new-id",
            name="New",
            slug="new-slug",
            status=TenantStatusEnum.ACTIVE,
            config={},
            quota={},
            metadata_={},
            parent_tenant_id=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            suspended_at=None,
        )
        mock_session.execute.return_value = no_existing
        mock_session.refresh = AsyncMock(return_value=None)

        # After refresh, the ORM returned is the one added via session.add
        # We patch refresh to populate the ORM returned
        async def fake_refresh(orm: Any) -> None:
            orm.tenant_id = created_orm.tenant_id
            orm.name = created_orm.name
            orm.slug = created_orm.slug
            orm.status = created_orm.status
            orm.config = created_orm.config
            orm.quota = created_orm.quota
            orm.metadata_ = created_orm.metadata_
            orm.parent_tenant_id = created_orm.parent_tenant_id
            orm.created_at = created_orm.created_at
            orm.updated_at = created_orm.updated_at
            orm.activated_at = created_orm.activated_at
            orm.suspended_at = created_orm.suspended_at

        mock_session.refresh.side_effect = fake_refresh

        tenant = await repo.create_tenant(name="New", slug="new-slug")
        assert tenant.name == "New"
        mock_session.commit.assert_awaited()

    # -- CRUD: get_tenant ---------------------------------------------------

    async def test_get_tenant_found(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        now = datetime.now(UTC)
        orm = SimpleNamespace(
            tenant_id="t1",
            name="Found",
            slug="found",
            status=TenantStatusEnum.ACTIVE,
            config={},
            quota={},
            metadata_={},
            parent_tenant_id=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            suspended_at=None,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = result_mock

        tenant = await repo.get_tenant("t1")
        assert tenant is not None
        assert tenant.tenant_id == "t1"

    async def test_get_tenant_not_found(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        tenant = await repo.get_tenant("missing")
        assert tenant is None

    async def test_get_tenant_cache_hit(self, repo_cached: Any, mock_session: AsyncMock) -> None:
        repo_cached._tenant_cache.get_async = AsyncMock(
            return_value={"tenant_id": "c1", "name": "Cached", "slug": "ca-ch"}
        )
        tenant = await repo_cached.get_tenant("c1")
        assert tenant is not None
        assert tenant.name == "Cached"
        mock_session.execute.assert_not_awaited()

    # -- CRUD: get_tenant_by_slug -------------------------------------------

    async def test_get_tenant_by_slug_found(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        now = datetime.now(UTC)
        orm = SimpleNamespace(
            tenant_id="t2",
            name="BySlug",
            slug="by-slug",
            status=TenantStatusEnum.ACTIVE,
            config={},
            quota={},
            metadata_={},
            parent_tenant_id=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            suspended_at=None,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = result_mock

        tenant = await repo.get_tenant_by_slug("by-slug")
        assert tenant is not None
        assert tenant.slug == "by-slug"

    async def test_get_tenant_by_slug_not_found(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        tenant = await repo.get_tenant_by_slug("nope")
        assert tenant is None

    async def test_get_tenant_by_slug_cache_hit(
        self, repo_cached: Any, mock_session: AsyncMock
    ) -> None:
        repo_cached._tenant_cache.get_async = AsyncMock(
            return_value={"tenant_id": "cs", "name": "CachedSlug", "slug": "cs-sl"}
        )
        tenant = await repo_cached.get_tenant_by_slug("cs-sl")
        assert tenant is not None
        assert tenant.name == "CachedSlug"

    # -- list_tenants -------------------------------------------------------

    async def test_list_tenants_no_status(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        now = datetime.now(UTC)
        orm1 = SimpleNamespace(
            tenant_id="l1",
            name="List1",
            slug="list-one",
            status=TenantStatusEnum.ACTIVE,
            config={},
            quota={},
            metadata_={},
            parent_tenant_id=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            suspended_at=None,
        )
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [orm1]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute.return_value = result_mock

        tenants = await repo.list_tenants()
        assert len(tenants) == 1
        assert tenants[0].name == "List1"

    async def test_list_tenants_with_status(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute.return_value = result_mock

        tenants = await repo.list_tenants(status=TenantStatus.ACTIVE)
        assert tenants == []

    async def test_list_tenants_offset(self, repo: Any, mock_session: AsyncMock) -> None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute.return_value = result_mock

        tenants = await repo.list_tenants(offset=5)
        assert tenants == []

    # -- activate_tenant ----------------------------------------------------

    async def test_activate_tenant_found(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        now = datetime.now(UTC)
        orm = SimpleNamespace(
            tenant_id="a1",
            name="Activate",
            slug="activate",
            status=TenantStatusEnum.PENDING,
            config={},
            quota={},
            metadata_={},
            parent_tenant_id=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            suspended_at=None,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = result_mock

        tenant = await repo.activate_tenant("a1")
        assert tenant is not None
        assert orm.status == TenantStatusEnum.ACTIVE

    async def test_activate_tenant_not_found(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await repo.activate_tenant("missing")
        assert result is None

    # -- suspend_tenant -----------------------------------------------------

    async def test_suspend_tenant_found(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        now = datetime.now(UTC)
        orm = SimpleNamespace(
            tenant_id="s1",
            name="Suspend",
            slug="suspend",
            status=TenantStatusEnum.ACTIVE,
            config={},
            quota={},
            metadata_={},
            parent_tenant_id=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            suspended_at=None,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = result_mock

        tenant = await repo.suspend_tenant("s1", reason="bad behavior")
        assert tenant is not None
        assert orm.status == TenantStatusEnum.SUSPENDED

    async def test_suspend_tenant_not_found(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await repo.suspend_tenant("missing")
        assert result is None

    # -- delete_tenant ------------------------------------------------------

    async def test_delete_tenant_found(self, repo: Any, mock_session: AsyncMock) -> None:
        orm = SimpleNamespace(tenant_id="d1", slug="del-one")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm
        mock_session.execute.return_value = result_mock

        deleted = await repo.delete_tenant("d1")
        assert deleted is True
        mock_session.delete.assert_awaited()

    async def test_delete_tenant_not_found(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        deleted = await repo.delete_tenant("missing")
        assert deleted is False

    # -- bulk operations (mocked BulkOperations) ----------------------------

    @patch(
        "enhanced_agent_bus.multi_tenancy.db_repository_optimized.BulkOperations.bulk_insert",
        new_callable=AsyncMock,
    )
    async def test_create_tenants_bulk_optimized(
        self, mock_bulk_insert: AsyncMock, repo: Any, mock_session: AsyncMock
    ) -> None:
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        now = datetime.now(UTC)
        orm1 = SimpleNamespace(
            tenant_id="b1",
            name="Bulk1",
            slug="bulk-one",
            status=TenantStatusEnum.ACTIVE,
            config={},
            quota={},
            metadata_={},
            parent_tenant_id=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            suspended_at=None,
        )
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [orm1]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute.return_value = result_mock

        tenants = await repo.create_tenants_bulk_optimized([{"name": "Bulk1", "slug": "bulk-one"}])
        assert len(tenants) == 1
        mock_bulk_insert.assert_awaited_once()

    @patch(
        "enhanced_agent_bus.multi_tenancy.db_repository_optimized.BulkOperations.bulk_update",
        new_callable=AsyncMock,
        return_value=3,
    )
    async def test_update_tenants_bulk(self, mock_bulk_update: AsyncMock, repo: Any) -> None:
        count = await repo.update_tenants_bulk([{"tenant_id": "t1", "status": "active"}])
        assert count == 3
        mock_bulk_update.assert_awaited_once()

    @patch(
        "enhanced_agent_bus.multi_tenancy.db_repository_optimized.BulkOperations.bulk_delete",
        new_callable=AsyncMock,
        return_value=2,
    )
    async def test_delete_tenants_bulk(self, mock_bulk_delete: AsyncMock, repo: Any) -> None:
        count = await repo.delete_tenants_bulk(["t1", "t2"])
        assert count == 2
        mock_bulk_delete.assert_awaited_once()

    @patch(
        "enhanced_agent_bus.multi_tenancy.db_repository_optimized.BulkOperations.bulk_delete",
        new_callable=AsyncMock,
        return_value=1,
    )
    async def test_delete_tenants_bulk_with_cache(
        self, mock_bulk_delete: AsyncMock, repo_cached: Any
    ) -> None:
        repo_cached._tenant_cache.delete = AsyncMock()
        count = await repo_cached.delete_tenants_bulk(["t1"])
        assert count == 1

    # -- count_tenants ------------------------------------------------------

    async def test_count_tenants_all(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar.return_value = 42
        mock_session.execute.return_value = result_mock

        count = await repo.count_tenants()
        assert count == 42

    async def test_count_tenants_by_status(self, repo: Any, mock_session: AsyncMock) -> None:
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        result_mock = MagicMock()
        result_mock.scalar.return_value = 5
        mock_session.execute.return_value = result_mock

        count = await repo.count_tenants(status=TenantStatus.SUSPENDED)
        assert count == 5

    async def test_count_tenants_none_result(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        mock_session.execute.return_value = result_mock

        count = await repo.count_tenants()
        assert count == 0

    # -- count_tenants_by_parent --------------------------------------------

    async def test_count_tenants_by_parent_with_id(
        self, repo: Any, mock_session: AsyncMock
    ) -> None:
        result_mock = MagicMock()
        result_mock.scalar.return_value = 3
        mock_session.execute.return_value = result_mock

        count = await repo.count_tenants_by_parent("p1")
        assert count == 3

    async def test_count_tenants_by_parent_root(self, repo: Any, mock_session: AsyncMock) -> None:
        result_mock = MagicMock()
        result_mock.scalar.return_value = 10
        mock_session.execute.return_value = result_mock

        count = await repo.count_tenants_by_parent(None)
        assert count == 10

    # -- TenantSummary / TenantHierarchyNode dataclasses --------------------

    def test_tenant_summary_frozen(self) -> None:
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            TenantSummary,
        )

        now = datetime.now(UTC)
        s = TenantSummary(tenant_id="t1", name="S", slug="ss", status="active", created_at=now)
        assert s.tenant_id == "t1"
        with pytest.raises(AttributeError):
            s.name = "changed"  # type: ignore[misc]

    def test_tenant_hierarchy_node_frozen(self) -> None:
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            TenantHierarchyNode,
        )

        now = datetime.now(UTC)
        h = TenantHierarchyNode(
            tenant_id="t1",
            name="H",
            slug="hh",
            status="active",
            parent_tenant_id=None,
            child_count=0,
            created_at=now,
        )
        assert h.child_count == 0


# ---------------------------------------------------------------------------
# 2. OPA Client Core tests
# ---------------------------------------------------------------------------


class TestOPAClientCore:
    """Tests for opa_client.core.OPAClientCore and helpers."""

    @pytest.fixture()
    def client(self) -> Any:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        return OPAClientCore(
            opa_url="http://localhost:8181",
            mode="fallback",
            enable_cache=False,
        )

    @pytest.fixture()
    def http_client(self) -> Any:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        return OPAClientCore(
            opa_url="http://localhost:8181",
            mode="http",
            enable_cache=False,
        )

    # -- Init ---------------------------------------------------------------

    def test_init_defaults(self, client: Any) -> None:
        assert client.mode == "fallback"
        assert client.fail_closed is True
        assert client.enable_cache is False

    def test_init_invalid_cache_hash_mode(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            OPAClientCore(cache_hash_mode="invalid")  # type: ignore[arg-type]

    def test_init_embedded_without_sdk(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch("enhanced_agent_bus.opa_client.core._opa_sdk_available", return_value=False):
            c = OPAClientCore(mode="embedded", enable_cache=False)
            assert c.mode == "http"  # falls back

    # -- get_stats ----------------------------------------------------------

    def test_get_stats_disabled_cache(self, client: Any) -> None:
        stats = client.get_stats()
        assert stats["cache_backend"] == "disabled"
        assert stats["mode"] == "fallback"
        assert stats["fail_closed"] is True

    def test_get_stats_memory_cache(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        c = OPAClientCore(
            opa_url="http://localhost:8181",
            mode="http",
            enable_cache=True,
        )
        c._redis_client = None
        stats = c.get_stats()
        assert stats["cache_backend"] == "memory"

    def test_get_stats_redis_cache(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        c = OPAClientCore(
            opa_url="http://localhost:8181",
            mode="http",
            enable_cache=True,
        )
        c._redis_client = MagicMock()
        stats = c.get_stats()
        assert stats["cache_backend"] == "redis"

    # -- Context manager ----------------------------------------------------

    async def test_context_manager(self, client: Any) -> None:
        client.initialize = AsyncMock()
        client.close = AsyncMock()
        async with client as c:
            assert c is client
        client.initialize.assert_awaited_once()
        client.close.assert_awaited_once()

    # -- SSL context --------------------------------------------------------

    def test_ssl_context_no_https(self, client: Any) -> None:
        result = client._build_ssl_context_if_needed()
        assert result is None

    def test_ssl_context_https_no_verify_dev(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            c = OPAClientCore(
                opa_url="https://opa.local:8181",
                mode="http",
                ssl_verify=False,
                enable_cache=False,
            )
            ctx = c._build_ssl_context_if_needed()
            assert ctx is not None

    def test_ssl_context_https_no_verify_production_raises(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClientCore

        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            c = OPAClientCore(
                opa_url="https://opa.prod:8181",
                mode="http",
                ssl_verify=False,
                enable_cache=False,
            )
            with pytest.raises(Exception, match="SSL verification cannot be disabled"):
                c._build_ssl_context_if_needed()

    # -- Validate policy path -----------------------------------------------

    def test_validate_policy_path_valid(self, client: Any) -> None:
        client._validate_policy_path("data.acgs.allow")  # no error

    def test_validate_policy_path_invalid_chars(self, client: Any) -> None:
        with pytest.raises(Exception, match="Invalid policy path"):
            client._validate_policy_path("data/../../etc/passwd")

    def test_validate_policy_path_traversal(self, client: Any) -> None:
        with pytest.raises(Exception, match="Path traversal"):
            client._validate_policy_path("data..acgs..allow")

    # -- Validate input data ------------------------------------------------

    def test_validate_input_data_ok(self, client: Any) -> None:
        client._validate_input_data({"key": "value"})  # no error

    def test_validate_input_data_too_large(self, client: Any) -> None:
        with patch.object(client, "_estimate_input_size_bytes", return_value=1024 * 1024):
            with pytest.raises(Exception, match="exceeds maximum"):
                client._validate_input_data({"big": "data"})

    # -- _estimate_input_size_bytes -----------------------------------------

    def test_estimate_input_size_empty(self, client: Any) -> None:
        size = client._estimate_input_size_bytes({})
        assert size > 0

    def test_estimate_input_size_nested(self, client: Any) -> None:
        data: dict[str, Any] = {"a": [1, 2, {"b": "c"}], "d": (1, 2)}
        size = client._estimate_input_size_bytes(data)
        assert size > 0

    def test_estimate_input_size_circular(self, client: Any) -> None:
        data: dict[str, Any] = {"self": None}
        # Simulate circular via seen set — just verify it handles already-seen ids
        size = client._estimate_input_size_bytes(data, seen={id(data)})
        assert size == 0

    # -- _format_evaluation_result ------------------------------------------

    def test_format_result_bool_true(self, client: Any) -> None:
        r = client._format_evaluation_result(True, "http", "data.acgs.allow")
        assert r["allowed"] is True
        assert r["result"] is True

    def test_format_result_bool_false(self, client: Any) -> None:
        r = client._format_evaluation_result(False, "http", "data.acgs.allow")
        assert r["allowed"] is False

    def test_format_result_dict(self, client: Any) -> None:
        r = client._format_evaluation_result(
            {"allow": True, "reason": "ok", "metadata": {"x": 1}}, "http", "p"
        )
        assert r["allowed"] is True
        assert r["metadata"]["x"] == 1

    def test_format_result_unexpected_type(self, client: Any) -> None:
        r = client._format_evaluation_result(42, "http", "p")
        assert r["allowed"] is False
        assert "Unexpected" in r["reason"]

    # -- _handle_evaluation_error -------------------------------------------

    def test_handle_evaluation_error_fail_closed(self, client: Any) -> None:
        with patch.object(client, "_sanitize_error", return_value="safe msg"):
            r = client._handle_evaluation_error(ValueError("test"), "data.acgs.allow")
            assert r["allowed"] is False
            assert r["metadata"]["security"] == "fail-closed"

    # -- _dispatch_evaluation -----------------------------------------------

    async def test_dispatch_http(self, http_client: Any) -> None:
        http_client._evaluate_http = AsyncMock(return_value={"result": True})
        r = await http_client._dispatch_evaluation({}, "p")
        assert r["result"] is True

    async def test_dispatch_embedded(self, client: Any) -> None:
        client.mode = "embedded"
        client._evaluate_embedded = AsyncMock(return_value={"result": True})
        r = await client._dispatch_evaluation({}, "p")
        assert r["result"] is True

    async def test_dispatch_fallback(self, client: Any) -> None:
        client.mode = "fallback"
        r = await client._dispatch_evaluation({}, "data.acgs.allow")
        assert r["allowed"] is False  # fail-closed

    # -- _evaluate_fallback -------------------------------------------------

    async def test_evaluate_fallback_wrong_hash(self, client: Any) -> None:
        r = await client._evaluate_fallback({"constitutional_hash": "wrong"}, "data.acgs.allow")
        assert r["allowed"] is False
        assert "Invalid constitutional hash" in r["reason"]

    async def test_evaluate_fallback_correct_hash(self, client: Any) -> None:
        from enhanced_agent_bus.models import CONSTITUTIONAL_HASH

        r = await client._evaluate_fallback(
            {"constitutional_hash": CONSTITUTIONAL_HASH}, "data.acgs.allow"
        )
        assert r["allowed"] is False
        assert "fail-closed" in r["reason"]

    # -- _evaluate_http not initialized -------------------------------------

    async def test_evaluate_http_no_client(self, http_client: Any) -> None:
        http_client._http_client = None
        with pytest.raises(Exception, match="not.*[Ii]nitiali"):
            await http_client._evaluate_http({}, "data.acgs.allow")

    # -- _evaluate_embedded not initialized ---------------------------------

    async def test_evaluate_embedded_no_opa(self, client: Any) -> None:
        client._embedded_opa = None
        with pytest.raises(Exception, match="not.*[Ii]nitiali"):
            await client._evaluate_embedded({}, "data.acgs.allow")

    # -- evaluate_policy (happy path via fallback) --------------------------

    async def test_evaluate_policy_fallback(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClient

        c = OPAClient(
            opa_url="http://localhost:8181",
            mode="fallback",
            enable_cache=False,
        )
        r = await c.evaluate_policy({"constitutional_hash": "wrong"}, "data.acgs.allow")
        assert r["allowed"] is False

    async def test_evaluate_policy_validation_error(self) -> None:
        from enhanced_agent_bus.opa_client.core import OPAClient

        c = OPAClient(
            opa_url="http://localhost:8181",
            mode="fallback",
            enable_cache=False,
        )
        r = await c.evaluate_policy({}, "bad/path!")
        assert r["allowed"] is False

    # -- load_policy --------------------------------------------------------

    async def test_load_policy_not_http_mode(self, client: Any) -> None:
        result = await client.load_policy("p1", "package test")
        assert result is False

    async def test_load_policy_success(self, http_client: Any) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_http = AsyncMock()
        mock_http.put = AsyncMock(return_value=mock_resp)
        http_client._http_client = mock_http
        http_client.clear_cache = AsyncMock()

        result = await http_client.load_policy("p1", "package test")
        assert result is True

    async def test_load_policy_connection_error(self, http_client: Any) -> None:
        from httpx import ConnectError as HTTPConnectError

        mock_http = AsyncMock()
        mock_http.put = AsyncMock(side_effect=HTTPConnectError("conn refused"))
        http_client._http_client = mock_http

        result = await http_client.load_policy("p1", "package test")
        assert result is False

    # -- close --------------------------------------------------------------

    async def test_close_http_client(self, http_client: Any) -> None:
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock()
        http_client._http_client = mock_http
        http_client._redis_client = None

        await http_client.close()
        assert http_client._http_client is None

    async def test_close_event_loop_closed(self, http_client: Any) -> None:
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
        http_client._http_client = mock_http
        http_client._redis_client = None

        await http_client.close()
        assert http_client._http_client is None

    async def test_close_redis_event_loop_closed(self, client: Any) -> None:
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
        client._http_client = None
        client._redis_client = mock_redis

        await client.close()
        assert client._redis_client is None

    async def test_close_redis_other_runtime_error(self, client: Any) -> None:
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock(side_effect=RuntimeError("other error"))
        client._http_client = None
        client._redis_client = mock_redis

        with pytest.raises(RuntimeError, match="other error"):
            await client.close()

    # -- _rollback_to_lkg ---------------------------------------------------

    async def test_rollback_lkg_exists(self, client: Any) -> None:
        with patch("os.path.exists", return_value=True):
            result = await client._rollback_to_lkg()
            assert result is True

    async def test_rollback_lkg_missing(self, client: Any) -> None:
        with patch("os.path.exists", return_value=False):
            result = await client._rollback_to_lkg()
            assert result is False

    # -- _initialize_embedded_opa -------------------------------------------

    async def test_initialize_embedded_opa_success(self, client: Any) -> None:
        mock_cls = MagicMock(return_value=MagicMock())
        with patch(
            "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
            return_value=mock_cls,
        ):
            await client._initialize_embedded_opa()
            assert client._embedded_opa is not None

    async def test_initialize_embedded_opa_failure(self, client: Any) -> None:
        mock_cls = MagicMock(side_effect=RuntimeError("no wasm"))
        with patch(
            "enhanced_agent_bus.opa_client.core._get_embedded_opa_class",
            return_value=mock_cls,
        ):
            client._ensure_http_client = AsyncMock()
            await client._initialize_embedded_opa()
            assert client.mode == "http"

    # -- Singleton helpers --------------------------------------------------

    async def test_singleton_lifecycle(self) -> None:
        import enhanced_agent_bus.opa_client.core as core_mod

        # Reset state
        core_mod._opa_client = None

        with patch.object(core_mod.OPAClient, "initialize", new_callable=AsyncMock):
            c = await core_mod.initialize_opa_client(
                opa_url="http://localhost:8181",
                mode="fallback",
                enable_cache=False,
            )
            assert c is not None

            # Second call reuses
            c2 = await core_mod.initialize_opa_client()
            assert c2 is c

            # get_opa_client returns same
            c3 = core_mod.get_opa_client()
            assert c3 is c

            # close
            with patch.object(c, "close", new_callable=AsyncMock) as mock_close:
                await core_mod.close_opa_client()
                mock_close.assert_awaited_once()
            assert core_mod._opa_client is None

    def test_get_opa_client_not_initialized(self) -> None:
        import enhanced_agent_bus.opa_client.core as core_mod

        core_mod._opa_client = None
        with pytest.raises(Exception, match="not.*[Ii]nitiali"):
            core_mod.get_opa_client()

    # -- _opa_sdk_available / _get_embedded_opa_class -----------------------

    def test_opa_sdk_available_from_module(self) -> None:
        from enhanced_agent_bus.opa_client.core import _opa_sdk_available

        result = _opa_sdk_available()
        assert isinstance(result, bool)

    def test_get_embedded_opa_class(self) -> None:
        from enhanced_agent_bus.opa_client.core import _get_embedded_opa_class

        result = _get_embedded_opa_class()
        # May be None if opa SDK not installed
        assert result is None or callable(result)

    # -- validate_constitutional --------------------------------------------

    async def test_validate_constitutional_success(self, client: Any) -> None:
        client.evaluate_policy = AsyncMock(
            return_value={
                "allowed": True,
                "reason": "ok",
                "metadata": {"mode": "fallback"},
            }
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)
        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is True

    async def test_validate_constitutional_denied(self, client: Any) -> None:
        client.evaluate_policy = AsyncMock(
            return_value={
                "allowed": False,
                "reason": "denied",
                "metadata": {},
            }
        )
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)
        result = await client.validate_constitutional({"content": "bad"})
        assert result.is_valid is False
        assert len(result.errors) > 0

    async def test_validate_constitutional_opa_error(self, client: Any) -> None:
        from enhanced_agent_bus.exceptions import OPAConnectionError

        client.evaluate_policy = AsyncMock(side_effect=OPAConnectionError("localhost", "down"))
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)
        result = await client.validate_constitutional({"content": "test"})
        assert result.is_valid is False

    # -- check_agent_authorization ------------------------------------------

    async def test_check_authorization_success(self, client: Any) -> None:
        client.evaluate_policy = AsyncMock(return_value={"allowed": True})
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)
        result = await client.check_agent_authorization("a1", "read", "res1")
        assert result is True

    async def test_check_authorization_wrong_hash(self, client: Any) -> None:
        result = await client.check_agent_authorization(
            "a1", "read", "res1", context={"constitutional_hash": "wrong"}
        )
        assert result is False

    async def test_check_authorization_opa_error(self, client: Any) -> None:
        from enhanced_agent_bus.exceptions import OPAConnectionError

        client.evaluate_policy = AsyncMock(side_effect=OPAConnectionError("localhost", "down"))
        client._is_multi_path_candidate_generation_enabled = MagicMock(return_value=False)
        result = await client.check_agent_authorization("a1", "read", "res1")
        assert result is False


# ---------------------------------------------------------------------------
# 3. ImpactScorer tests
# ---------------------------------------------------------------------------


class TestImpactScorer:
    """Tests for deliberation_layer.impact_scorer.ImpactScorer."""

    @pytest.fixture()
    def scorer(self) -> Any:
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        return ImpactScorer(enable_caching=False, enable_minicpm=False)

    # -- Init / lifecycle ---------------------------------------------------

    def test_init_defaults(self, scorer: Any) -> None:
        assert scorer._enable_minicpm is False
        assert scorer._embedding_cache is None
        assert scorer._onnx_enabled is False
        assert scorer._total_evaluations == 0
        assert scorer._overrides == 0

    def test_init_with_caching(self) -> None:
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        s = ImpactScorer(enable_caching=True, enable_minicpm=False)
        assert s._embedding_cache is not None

    async def test_initialize_no_cache(self, scorer: Any) -> None:
        result = await scorer.initialize()
        assert result is True

    async def test_initialize_with_cache(self) -> None:
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        s = ImpactScorer(enable_caching=True, enable_minicpm=False)
        s._embedding_cache.initialize = AsyncMock(return_value=True)
        result = await s.initialize()
        assert result is True

    async def test_close_no_cache(self, scorer: Any) -> None:
        await scorer.close()  # no error

    async def test_close_with_cache(self) -> None:
        from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer

        s = ImpactScorer(enable_caching=True, enable_minicpm=False)
        s._embedding_cache.close = AsyncMock()
        await s.close()
        s._embedding_cache.close.assert_awaited_once()

    # -- Cache key ----------------------------------------------------------

    def test_generate_cache_key(self, scorer: Any) -> None:
        key = scorer._generate_cache_key("hello")
        assert key.startswith("impact:embedding:")

    # -- Class cache reset --------------------------------------------------

    def test_reset_class_cache(self, scorer: Any) -> None:
        scorer.reset_class_cache()  # no-op, just covers

    # -- Clear tokenization cache -------------------------------------------

    def test_clear_tokenization_cache(self, scorer: Any) -> None:
        scorer._tokenization_cache["x"] = 1
        scorer.clear_tokenization_cache()
        assert len(scorer._tokenization_cache) == 0

    # -- Properties ---------------------------------------------------------

    def test_minicpm_enabled(self, scorer: Any) -> None:
        assert scorer.minicpm_enabled is False

    def test_loco_operator_available_none(self, scorer: Any) -> None:
        assert scorer.loco_operator_available is False

    def test_loco_operator_available_with_client(self, scorer: Any) -> None:
        scorer._loco_client = SimpleNamespace(is_available=True)
        assert scorer.loco_operator_available is True

    # -- _score_with_loco_operator ------------------------------------------

    async def test_score_with_loco_not_available(self, scorer: Any) -> None:
        result = await scorer._score_with_loco_operator("action", {})
        assert result is None

    async def test_score_with_loco_available(self, scorer: Any) -> None:
        mock_client = AsyncMock()
        mock_client.score_governance_action = AsyncMock(return_value={"score": 0.8})
        scorer._loco_client = mock_client
        # Need loco_operator_available to return True
        scorer._loco_client.is_available = True

        # Patch the property
        with patch.object(
            type(scorer),
            "loco_operator_available",
            new_callable=lambda: property(lambda self: True),
        ):
            result = await scorer._score_with_loco_operator("action", {})
            assert result == {"score": 0.8}

    # -- calculate_impact_score --------------------------------------------

    def test_calculate_impact_score_basic(self, scorer: Any) -> None:
        score = scorer.calculate_impact_score({"content": "hello"})
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_none_message(self, scorer: Any) -> None:
        score = scorer.calculate_impact_score(None)
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_high_impact_keyword(self, scorer: Any) -> None:
        score = scorer.calculate_impact_score({"content": "critical security breach"})
        assert score > 0.3

    def test_calculate_impact_score_critical_priority(self, scorer: Any) -> None:
        score = scorer.calculate_impact_score({"content": "test", "priority": "critical"})
        from enhanced_agent_bus.governance_constants import IMPACT_CRITICAL_FLOOR

        assert score >= IMPACT_CRITICAL_FLOOR

    def test_calculate_impact_score_with_context_priority(self, scorer: Any) -> None:
        score = scorer.calculate_impact_score({"content": "test"}, {"priority": "high"})
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_with_priority_enum(self, scorer: Any) -> None:
        priority = SimpleNamespace(name="CRITICAL")
        score = scorer.calculate_impact_score({"content": "test", "priority": priority})
        from enhanced_agent_bus.governance_constants import IMPACT_CRITICAL_FLOOR

        assert score >= IMPACT_CRITICAL_FLOOR

    def test_calculate_impact_score_semantic_override(self, scorer: Any) -> None:
        score = scorer.calculate_impact_score({"content": "test"}, {"semantic_override": 0.95})
        # semantic_override >= 0.9 triggers high-semantic floor
        from enhanced_agent_bus.governance_constants import IMPACT_HIGH_SEMANTIC_FLOOR

        assert score >= IMPACT_HIGH_SEMANTIC_FLOOR

    def test_calculate_impact_score_governance_type(self, scorer: Any) -> None:
        score1 = scorer.calculate_impact_score({"content": "test", "message_type": "governance"})
        score2 = scorer.calculate_impact_score({"content": "test", "message_type": "info"})
        # governance type has higher type_factor
        assert score1 >= score2

    def test_calculate_impact_score_object_message(self, scorer: Any) -> None:
        msg = SimpleNamespace(
            from_agent="agent1",
            priority="normal",
            content="hello",
            tools=None,
            payload={},
            message_type="",
        )
        score = scorer.calculate_impact_score(msg)
        assert 0.0 <= score <= 1.0

    def test_increments_total_evaluations(self, scorer: Any) -> None:
        scorer.calculate_impact_score({"content": "a"})
        scorer.calculate_impact_score({"content": "b"})
        assert scorer._total_evaluations == 2

    # -- record_override / spec_to_artifact_score ---------------------------

    def test_record_override(self, scorer: Any) -> None:
        scorer.record_override()
        assert scorer._overrides == 1

    def test_spec_to_artifact_score_no_evals(self, scorer: Any) -> None:
        assert scorer.spec_to_artifact_score == 1.0

    def test_spec_to_artifact_score_with_overrides(self, scorer: Any) -> None:
        scorer._total_evaluations = 10
        scorer._overrides = 2
        assert scorer.spec_to_artifact_score == pytest.approx(0.8)

    def test_get_spec_to_artifact_metrics(self, scorer: Any) -> None:
        scorer._total_evaluations = 5
        scorer._overrides = 1
        m = scorer.get_spec_to_artifact_metrics()
        assert m["total_evaluations"] == 5
        assert m["overrides"] == 1
        assert m["override_rate"] == pytest.approx(0.2)
        assert m["spec_to_artifact_score"] == pytest.approx(0.8)

    def test_get_spec_to_artifact_metrics_no_evals(self, scorer: Any) -> None:
        m = scorer.get_spec_to_artifact_metrics()
        assert m["override_rate"] == 0.0
        assert m["spec_to_artifact_score"] == 1.0

    # -- _calculate_permission_score ----------------------------------------

    def test_permission_score_no_tools(self, scorer: Any) -> None:
        assert scorer._calculate_permission_score({}) == 0.1

    def test_permission_score_high_risk_tool(self, scorer: Any) -> None:
        msg = {"tools": [{"name": "execute_command"}]}
        assert scorer._calculate_permission_score(msg) >= 0.7

    def test_permission_score_read_tool(self, scorer: Any) -> None:
        msg = {"tools": [{"name": "read_file"}]}
        assert scorer._calculate_permission_score(msg) >= 0.2

    def test_permission_score_unknown_tool(self, scorer: Any) -> None:
        msg = {"tools": [{"name": "custom_thing"}]}
        assert scorer._calculate_permission_score(msg) >= 0.3

    def test_permission_score_string_tools(self, scorer: Any) -> None:
        msg = {"tools": ["execute_shell", "read_data"]}
        assert scorer._calculate_permission_score(msg) >= 0.7

    def test_permission_score_object_message(self, scorer: Any) -> None:
        msg = SimpleNamespace(tools=[{"name": "delete_record"}])
        assert scorer._calculate_permission_score(msg) >= 0.7

    # -- _calculate_volume_score --------------------------------------------

    def test_volume_score_new_agent(self, scorer: Any) -> None:
        assert scorer._calculate_volume_score("new-agent") == 0.1

    def test_volume_score_escalation(self, scorer: Any) -> None:
        for _ in range(11):
            scorer._calculate_volume_score("agent-x")
        assert scorer._calculate_volume_score("agent-x") == 0.2

    def test_volume_score_high(self, scorer: Any) -> None:
        for _ in range(101):
            scorer._calculate_volume_score("heavy")
        assert scorer._calculate_volume_score("heavy") == 1.0

    # -- _calculate_context_score -------------------------------------------

    def test_context_score_no_amount(self, scorer: Any) -> None:
        assert scorer._calculate_context_score({}, {}) == 0.1

    def test_context_score_high_amount(self, scorer: Any) -> None:
        msg = {"payload": {"amount": 50000}}
        assert scorer._calculate_context_score(msg, {}) == 0.5

    def test_context_score_object_message(self, scorer: Any) -> None:
        msg = SimpleNamespace(payload={"amount": 50000}, content={})
        assert scorer._calculate_context_score(msg, {}) == 0.5

    def test_context_score_object_non_dict_payload(self, scorer: Any) -> None:
        msg = SimpleNamespace(payload="string", content={})
        assert scorer._calculate_context_score(msg, {}) == 0.1

    # -- _calculate_drift_score ---------------------------------------------

    def test_drift_score_first_call(self, scorer: Any) -> None:
        assert scorer._calculate_drift_score("a1", 0.4) == 0.0

    def test_drift_score_no_deviation(self, scorer: Any) -> None:
        scorer._calculate_drift_score("a2", 0.4)
        scorer._calculate_drift_score("a2", 0.4)
        assert scorer._calculate_drift_score("a2", 0.4) == 0.0

    def test_drift_score_high_deviation(self, scorer: Any) -> None:
        scorer._calculate_drift_score("a3", 0.1)
        scorer._calculate_drift_score("a3", 0.1)
        # Now pass a very different value — deviation > 0.3
        result = scorer._calculate_drift_score("a3", 0.9)
        assert result > 0.0

    # -- _calculate_semantic_score ------------------------------------------

    def test_semantic_score_empty(self, scorer: Any) -> None:
        assert scorer._calculate_semantic_score({}) == 0.0

    def test_semantic_score_high_keyword(self, scorer: Any) -> None:
        assert scorer._calculate_semantic_score({"content": "security breach"}) == 0.95

    def test_semantic_score_normal(self, scorer: Any) -> None:
        assert scorer._calculate_semantic_score({"content": "hello world"}) == 0.1

    # -- _get_keyword_score -------------------------------------------------

    def test_keyword_score_none(self, scorer: Any) -> None:
        assert scorer._get_keyword_score("nothing here") == 0.1

    def test_keyword_score_one(self, scorer: Any) -> None:
        assert scorer._get_keyword_score("security concern") == 0.5

    def test_keyword_score_two(self, scorer: Any) -> None:
        assert scorer._get_keyword_score("security breach") == 0.75

    def test_keyword_score_many(self, scorer: Any) -> None:
        score = scorer._get_keyword_score("security breach exploit vulnerability attack threat")
        assert score >= 0.75

    # -- _calculate_priority_factor -----------------------------------------

    def test_priority_factor_critical(self, scorer: Any) -> None:
        assert scorer._calculate_priority_factor({"priority": "critical"}) == 1.0

    def test_priority_factor_high(self, scorer: Any) -> None:
        assert scorer._calculate_priority_factor({"priority": "high"}) == 0.8

    def test_priority_factor_normal(self, scorer: Any) -> None:
        assert scorer._calculate_priority_factor({"priority": "normal"}) == 0.5

    def test_priority_factor_low(self, scorer: Any) -> None:
        assert scorer._calculate_priority_factor({"priority": "low"}) == 0.2

    def test_priority_factor_unknown(self, scorer: Any) -> None:
        assert scorer._calculate_priority_factor({"priority": "weird"}) == 0.5

    def test_priority_factor_context_override(self, scorer: Any) -> None:
        assert scorer._calculate_priority_factor({}, {"priority": "critical"}) == 1.0

    def test_priority_factor_enum_value(self, scorer: Any) -> None:
        p = SimpleNamespace(value="high", name="HIGH")
        assert scorer._calculate_priority_factor({"priority": p}) == 0.8

    def test_priority_factor_numeric(self, scorer: Any) -> None:
        assert scorer._calculate_priority_factor({"priority": "3"}) == 1.0
        assert scorer._calculate_priority_factor({"priority": "0"}) == 0.2

    # -- _calculate_type_factor ---------------------------------------------

    def test_type_factor_governance(self, scorer: Any) -> None:
        assert scorer._calculate_type_factor({"message_type": "governance"}) == 1.5

    def test_type_factor_security(self, scorer: Any) -> None:
        assert scorer._calculate_type_factor({"message_type": "security"}) == 1.4

    def test_type_factor_financial(self, scorer: Any) -> None:
        assert scorer._calculate_type_factor({"message_type": "financial"}) == 1.3

    def test_type_factor_default(self, scorer: Any) -> None:
        assert scorer._calculate_type_factor({"message_type": "other"}) == 1.0

    def test_type_factor_object_message(self, scorer: Any) -> None:
        msg = SimpleNamespace(message_type="governance")
        assert scorer._calculate_type_factor(msg) == 1.5

    # -- _extract_text_content / helpers ------------------------------------

    def test_extract_text_content_dict(self, scorer: Any) -> None:
        text = scorer._extract_text_content(
            {"content": "hello", "action": "do_thing", "tools": [{"name": "cmd"}]}
        )
        assert "hello" in text
        assert "do_thing" in text
        assert "cmd" in text

    def test_extract_text_content_object(self, scorer: Any) -> None:
        msg = SimpleNamespace(content="obj content", tools=["tool1"])
        text = scorer._extract_text_content(msg)
        assert "obj content" in text
        assert "tool1" in text

    def test_extract_payload_content(self, scorer: Any) -> None:
        parts = scorer._extract_payload_content(
            {"payload": {"message": "pay msg"}, "description": "desc"}
        )
        assert "pay msg" in parts
        assert "desc" in parts

    def test_extract_basic_content_no_content(self, scorer: Any) -> None:
        parts = scorer._extract_basic_content({"no_content": True})
        assert parts == []

    def test_extract_tool_content_object_no_tools(self, scorer: Any) -> None:
        msg = SimpleNamespace()
        parts = scorer._extract_tool_content(msg)
        assert parts == []

    # -- batch scoring ------------------------------------------------------

    def test_batch_score_impact(self, scorer: Any) -> None:
        messages = [{"content": "a"}, {"content": "critical breach"}]
        scores = scorer.batch_score_impact(messages)
        assert len(scores) == 2

    def test_batch_score_impact_with_contexts(self, scorer: Any) -> None:
        messages = [{"content": "a"}, {"content": "b"}]
        contexts = [{"priority": "high"}, {"priority": "low"}]
        scores = scorer.batch_score_impact(messages, contexts)
        assert len(scores) == 2

    def test_batch_score_impact_mismatched_contexts(self, scorer: Any) -> None:
        with pytest.raises(ValueError, match="must match"):
            scorer.batch_score_impact([{"content": "a"}], [{}, {}])

    def test_score_messages_batch_no_onnx(self, scorer: Any) -> None:
        scores = scorer.score_messages_batch([{"content": "hello"}, {"content": "security"}])
        assert len(scores) == 2

    # -- reset_history ------------------------------------------------------

    def test_reset_history(self, scorer: Any) -> None:
        scorer._calculate_volume_score("agent1")
        scorer._calculate_drift_score("agent1", 0.5)
        scorer.reset_history()
        assert len(scorer._volume_counts) == 0
        assert len(scorer._drift_history) == 0

    # -- get_governance_vector / get_minicpm_score --------------------------

    def test_get_governance_vector(self, scorer: Any) -> None:
        scorer.service.get_governance_vector = MagicMock(return_value=None)
        result = scorer.get_governance_vector({})
        assert result is None

    def test_get_minicpm_score(self, scorer: Any) -> None:
        scorer.service.get_minicpm_score = MagicMock(return_value=None)
        result = scorer.get_minicpm_score({})
        assert result is None

    def test_score_impact_delegates(self, scorer: Any) -> None:
        from enhanced_agent_bus.impact_scorer_infra.models import ScoringResult

        mock_result = MagicMock(spec=ScoringResult)
        scorer.service.get_impact_score = MagicMock(return_value=mock_result)
        result = scorer.score_impact({})
        assert result is mock_result
