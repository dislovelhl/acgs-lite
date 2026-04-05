# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for constitutional/storage.py (facade layer).

Target: ≥95% line coverage of constitutional/storage.py (57 stmts).
"""

from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.constitutional.amendment_model import AmendmentProposal
from enhanced_agent_bus.constitutional.storage import (
    ConstitutionalStorageService,
    StorageConfig,
)
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret


def _make_version(**kwargs) -> ConstitutionalVersion:
    defaults = dict(
        version="1.0.0",
        content={"rule": "value"},
    )
    defaults.update(kwargs)
    return ConstitutionalVersion(**defaults)


def _make_amendment(**kwargs) -> AmendmentProposal:
    defaults = dict(
        proposed_changes={"key": "value"},
        justification="This is a valid justification.",
        proposer_agent_id="agent-001",
        target_version="1.0.0",
    )
    defaults.update(kwargs)
    return AmendmentProposal(**defaults)


def _make_mock_service():
    """Return a fully-mocked ModularStorageService instance."""
    svc = MagicMock()
    svc.connect = AsyncMock(return_value=True)
    svc.disconnect = AsyncMock(return_value=None)
    svc.save_version = AsyncMock(return_value=True)
    svc.get_version = AsyncMock(return_value=None)
    svc.get_active_version = AsyncMock(return_value=None)
    svc.activate_version = AsyncMock(return_value=True)
    svc.save_amendment = AsyncMock(return_value=True)
    svc.get_amendment = AsyncMock(return_value=None)
    svc.list_versions = AsyncMock(return_value=[])
    svc.list_amendments = AsyncMock(return_value=([], 0))
    # For property access (.persistence.engine, .cache.redis_client)
    svc.persistence = MagicMock()
    svc.persistence.engine = MagicMock(name="engine")
    svc.cache = MagicMock()
    svc.cache.redis_client = MagicMock(name="redis_client")
    return svc


def _make_facade(**init_kwargs) -> tuple["ConstitutionalStorageService", MagicMock]:
    """Return (facade, mock_modular_service)."""
    mock_svc = _make_mock_service()
    with patch(
        "enhanced_agent_bus.constitutional.storage.ModularStorageService",
        return_value=mock_svc,
    ):
        facade = ConstitutionalStorageService(**init_kwargs)
    return facade, mock_svc


# ---------------------------------------------------------------------------
# __init__ / construction
# ---------------------------------------------------------------------------


class TestConstitutionalStorageServiceInit:
    def test_default_construction(self):
        facade, _mock_svc = _make_facade()
        assert facade is not None
        assert facade.enable_multi_tenancy is True
        assert facade.default_tenant_id == "system"

    def test_custom_redis_and_db_url(self):
        facade, _ = _make_facade(
            redis_url="redis://custom:6380",
            database_url="postgresql+asyncpg://custom/db",
        )
        assert facade is not None

    def test_custom_cache_ttl_and_lock_timeout(self):
        facade, _ = _make_facade(cache_ttl=7200, lock_timeout=60)
        assert facade is not None

    def test_multi_tenancy_disabled(self):
        facade, _ = _make_facade(enable_multi_tenancy=False)
        assert facade.enable_multi_tenancy is False

    def test_custom_default_tenant_id(self):
        facade, _ = _make_facade(default_tenant_id="tenant-x")
        assert facade.default_tenant_id == "tenant-x"

    def test_none_redis_url_uses_default(self):
        """None redis_url should fall back to the default URL inside __init__."""
        facade, _ = _make_facade(redis_url=None)
        assert facade is not None

    def test_none_database_url_uses_default(self):
        facade, _ = _make_facade(database_url=None)
        assert facade is not None


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_engine_property(self):
        facade, mock_svc = _make_facade()
        engine = facade.engine
        assert engine is mock_svc.persistence.engine

    def test_redis_client_property(self):
        facade, mock_svc = _make_facade()
        client = facade.redis_client
        assert client is mock_svc.cache.redis_client


# ---------------------------------------------------------------------------
# _get_tenant_id
# ---------------------------------------------------------------------------


class TestGetTenantId:
    def test_multi_tenancy_enabled_with_context(self):
        facade, _ = _make_facade(enable_multi_tenancy=True, default_tenant_id="system")
        with patch(
            "enhanced_agent_bus.constitutional.storage.ConstitutionalStorageService._get_tenant_id"
        ):
            pass  # We test via the module import path below

        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value="ctx-tenant",
        ):
            tid = facade._get_tenant_id()
        assert tid == "ctx-tenant"

    def test_multi_tenancy_enabled_no_context_falls_back(self):
        facade, _ = _make_facade(enable_multi_tenancy=True, default_tenant_id="fallback")
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            tid = facade._get_tenant_id()
        assert tid == "fallback"

    def test_multi_tenancy_disabled_returns_default(self):
        facade, _ = _make_facade(enable_multi_tenancy=False, default_tenant_id="fixed")
        # Even if a context tenant exists, it should NOT be used
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value="ctx-tenant",
        ):
            tid = facade._get_tenant_id()
        assert tid == "fixed"


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


class TestConnectDisconnect:
    async def test_connect_delegates(self):
        facade, mock_svc = _make_facade()
        result = await facade.connect()
        assert result is True
        mock_svc.connect.assert_awaited_once()

    async def test_connect_returns_false_when_service_fails(self):
        facade, mock_svc = _make_facade()
        mock_svc.connect.return_value = False
        result = await facade.connect()
        assert result is False

    async def test_disconnect_delegates(self):
        facade, mock_svc = _make_facade()
        await facade.disconnect()
        mock_svc.disconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# save_version
# ---------------------------------------------------------------------------


class TestSaveVersion:
    async def test_save_version_with_explicit_tenant(self):
        facade, mock_svc = _make_facade()
        version = _make_version()
        result = await facade.save_version(version, tenant_id="tenant-a")
        mock_svc.save_version.assert_awaited_once_with(version, "tenant-a")
        assert result is True

    async def test_save_version_uses_get_tenant_id_when_none(self):
        facade, mock_svc = _make_facade(default_tenant_id="default-t")
        version = _make_version()
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            result = await facade.save_version(version)
        mock_svc.save_version.assert_awaited_once_with(version, "default-t")
        assert result is True

    async def test_save_version_returns_false_on_failure(self):
        facade, mock_svc = _make_facade()
        mock_svc.save_version.return_value = False
        version = _make_version()
        result = await facade.save_version(version, tenant_id="t1")
        assert result is False


# ---------------------------------------------------------------------------
# get_version
# ---------------------------------------------------------------------------


class TestGetVersion:
    async def test_get_version_found(self):
        facade, mock_svc = _make_facade()
        version = _make_version()
        mock_svc.get_version.return_value = version
        result = await facade.get_version("vid-1", tenant_id="t1")
        assert result is version
        mock_svc.get_version.assert_awaited_once_with("vid-1", "t1")

    async def test_get_version_not_found(self):
        facade, mock_svc = _make_facade()
        mock_svc.get_version.return_value = None
        result = await facade.get_version("vid-missing", tenant_id="t1")
        assert result is None

    async def test_get_version_uses_default_tenant_when_none(self):
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        mock_svc.get_version.return_value = None
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            await facade.get_version("vid-x")
        mock_svc.get_version.assert_awaited_once_with("vid-x", "sys")


# ---------------------------------------------------------------------------
# get_active_version
# ---------------------------------------------------------------------------


class TestGetActiveVersion:
    async def test_get_active_version_found(self):
        facade, mock_svc = _make_facade()
        version = _make_version()
        mock_svc.get_active_version.return_value = version
        result = await facade.get_active_version(tenant_id="t1")
        assert result is version

    async def test_get_active_version_none(self):
        facade, _mock_svc = _make_facade()
        result = await facade.get_active_version(tenant_id="t1")
        assert result is None

    async def test_get_active_version_uses_default_tenant(self):
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            await facade.get_active_version()
        mock_svc.get_active_version.assert_awaited_once_with("sys")


# ---------------------------------------------------------------------------
# activate_version
# ---------------------------------------------------------------------------


class TestActivateVersion:
    async def test_activate_version_success(self):
        facade, mock_svc = _make_facade()
        result = await facade.activate_version("vid-1", tenant_id="t1")
        assert result is True
        mock_svc.activate_version.assert_awaited_once_with("vid-1", "t1")

    async def test_activate_version_ignores_deactivate_current_flag(self):
        """_deactivate_current param is accepted but not passed to inner service."""
        facade, mock_svc = _make_facade()
        result = await facade.activate_version("vid-1", _deactivate_current=False, tenant_id="t1")
        assert result is True
        mock_svc.activate_version.assert_awaited_once_with("vid-1", "t1")

    async def test_activate_version_failure(self):
        facade, mock_svc = _make_facade()
        mock_svc.activate_version.return_value = False
        result = await facade.activate_version("vid-x", tenant_id="t1")
        assert result is False

    async def test_activate_version_uses_default_tenant(self):
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            await facade.activate_version("vid-1")
        mock_svc.activate_version.assert_awaited_once_with("vid-1", "sys")


# ---------------------------------------------------------------------------
# save_amendment
# ---------------------------------------------------------------------------


class TestSaveAmendment:
    async def test_save_amendment_explicit_tenant(self):
        facade, mock_svc = _make_facade()
        amendment = _make_amendment()
        result = await facade.save_amendment(amendment, tenant_id="t1")
        assert result is True
        mock_svc.save_amendment.assert_awaited_once_with(amendment, "t1")

    async def test_save_amendment_uses_default_tenant(self):
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        amendment = _make_amendment()
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            await facade.save_amendment(amendment)
        mock_svc.save_amendment.assert_awaited_once_with(amendment, "sys")

    async def test_save_amendment_returns_false_on_failure(self):
        facade, mock_svc = _make_facade()
        mock_svc.save_amendment.return_value = False
        amendment = _make_amendment()
        result = await facade.save_amendment(amendment, tenant_id="t1")
        assert result is False


# ---------------------------------------------------------------------------
# get_amendment
# ---------------------------------------------------------------------------


class TestGetAmendment:
    async def test_get_amendment_found(self):
        facade, mock_svc = _make_facade()
        amendment = _make_amendment()
        mock_svc.get_amendment.return_value = amendment
        result = await facade.get_amendment("pid-1", tenant_id="t1")
        assert result is amendment

    async def test_get_amendment_not_found(self):
        facade, _mock_svc = _make_facade()
        result = await facade.get_amendment("pid-missing", tenant_id="t1")
        assert result is None

    async def test_get_amendment_uses_default_tenant(self):
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            await facade.get_amendment("pid-1")
        mock_svc.get_amendment.assert_awaited_once_with("pid-1", "sys")


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    async def test_list_versions_default_params(self):
        facade, mock_svc = _make_facade()
        result = await facade.list_versions(tenant_id="t1")
        mock_svc.list_versions.assert_awaited_once_with("t1", 50, 0, None)
        assert result == []

    async def test_list_versions_with_status(self):
        facade, mock_svc = _make_facade()
        await facade.list_versions(status=ConstitutionalStatus.ACTIVE, tenant_id="t1")
        mock_svc.list_versions.assert_awaited_once_with("t1", 50, 0, "active")

    async def test_list_versions_with_limit_offset(self):
        facade, mock_svc = _make_facade()
        await facade.list_versions(limit=10, offset=5, tenant_id="t1")
        mock_svc.list_versions.assert_awaited_once_with("t1", 10, 5, None)

    async def test_list_versions_uses_default_tenant(self):
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            await facade.list_versions()
        mock_svc.list_versions.assert_awaited_once_with("sys", 50, 0, None)

    async def test_list_versions_with_status_none(self):
        facade, mock_svc = _make_facade()
        await facade.list_versions(status=None, tenant_id="t1")
        mock_svc.list_versions.assert_awaited_once_with("t1", 50, 0, None)

    async def test_list_versions_returns_items(self):
        facade, mock_svc = _make_facade()
        versions = [_make_version(), _make_version(version="1.0.1")]
        mock_svc.list_versions.return_value = versions
        result = await facade.list_versions(tenant_id="t1")
        assert result is versions

    async def test_list_versions_status_draft(self):
        facade, mock_svc = _make_facade()
        await facade.list_versions(status=ConstitutionalStatus.DRAFT, tenant_id="t1")
        mock_svc.list_versions.assert_awaited_once_with("t1", 50, 0, "draft")

    async def test_list_versions_status_superseded(self):
        facade, mock_svc = _make_facade()
        await facade.list_versions(status=ConstitutionalStatus.SUPERSEDED, tenant_id="t1")
        mock_svc.list_versions.assert_awaited_once_with("t1", 50, 0, "superseded")


# ---------------------------------------------------------------------------
# list_amendments
# ---------------------------------------------------------------------------


class TestListAmendments:
    async def test_list_amendments_defaults(self):
        facade, mock_svc = _make_facade()
        result = await facade.list_amendments(tenant_id="t1")
        mock_svc.list_amendments.assert_awaited_once_with("t1", 50, 0, None, None)
        assert result == ([], 0)

    async def test_list_amendments_with_all_params(self):
        facade, mock_svc = _make_facade()
        mock_svc.list_amendments.return_value = ([_make_amendment()], 1)
        _amendments, total = await facade.list_amendments(
            limit=5,
            offset=2,
            status="proposed",
            proposer_agent_id="agent-1",
            tenant_id="t1",
        )
        mock_svc.list_amendments.assert_awaited_once_with("t1", 5, 2, "proposed", "agent-1")
        assert total == 1

    async def test_list_amendments_uses_default_tenant(self):
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            await facade.list_amendments()
        mock_svc.list_amendments.assert_awaited_once_with("sys", 50, 0, None, None)

    async def test_list_amendments_status_filter(self):
        facade, mock_svc = _make_facade()
        await facade.list_amendments(status="approved", tenant_id="t1")
        mock_svc.list_amendments.assert_awaited_once_with("t1", 50, 0, "approved", None)


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    async def test_compute_diff_both_versions_missing(self):
        facade, mock_svc = _make_facade()
        # Both get_version calls return None
        mock_svc.get_version.return_value = None
        result = await facade.compute_diff("v1", "v2")
        assert result is None

    async def test_compute_diff_from_version_missing(self):
        facade, mock_svc = _make_facade()
        to_version = _make_version(version="1.0.1", content={"a": 1})
        # First call returns None (from), second returns to_version
        mock_svc.get_version.side_effect = [None, to_version]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result is None

    async def test_compute_diff_to_version_missing(self):
        facade, mock_svc = _make_facade()
        from_version = _make_version(version="1.0.0", content={"a": 1})
        mock_svc.get_version.side_effect = [from_version, None]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result is None

    async def test_compute_diff_identical_content(self):
        facade, mock_svc = _make_facade()
        content = {"rule_a": "allow", "rule_b": "deny"}
        from_v = _make_version(version="1.0.0", content=content)
        to_v = _make_version(version="1.0.1", content=content)
        mock_svc.get_version.side_effect = [from_v, to_v]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result is not None
        assert result["content_diff"]["added"] == {}
        assert result["content_diff"]["removed"] == {}
        assert result["content_diff"]["modified"] == {}

    async def test_compute_diff_added_keys(self):
        facade, mock_svc = _make_facade()
        from_v = _make_version(version="1.0.0", content={"rule_a": "allow"})
        to_v = _make_version(version="1.0.1", content={"rule_a": "allow", "rule_b": "deny"})
        mock_svc.get_version.side_effect = [from_v, to_v]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result is not None
        assert result["content_diff"]["added"] == {"rule_b": "deny"}
        assert result["content_diff"]["removed"] == {}
        assert result["content_diff"]["modified"] == {}

    async def test_compute_diff_removed_keys(self):
        facade, mock_svc = _make_facade()
        from_v = _make_version(version="1.0.0", content={"rule_a": "allow", "rule_b": "deny"})
        to_v = _make_version(version="1.0.1", content={"rule_a": "allow"})
        mock_svc.get_version.side_effect = [from_v, to_v]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result is not None
        assert result["content_diff"]["removed"] == {"rule_b": "deny"}
        assert result["content_diff"]["added"] == {}

    async def test_compute_diff_modified_keys(self):
        facade, mock_svc = _make_facade()
        from_v = _make_version(version="1.0.0", content={"rule_a": "old_value"})
        to_v = _make_version(version="1.0.1", content={"rule_a": "new_value"})
        mock_svc.get_version.side_effect = [from_v, to_v]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result is not None
        modified = result["content_diff"]["modified"]
        assert "rule_a" in modified
        assert modified["rule_a"]["from"] == "old_value"
        assert modified["rule_a"]["to"] == "new_value"

    async def test_compute_diff_returns_version_numbers(self):
        facade, mock_svc = _make_facade()
        from_v = _make_version(version="1.0.0", content={"a": 1})
        to_v = _make_version(version="2.0.0", content={"a": 1, "b": 2})
        mock_svc.get_version.side_effect = [from_v, to_v]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result["from_version"] == "1.0.0"
        assert result["to_version"] == "2.0.0"

    async def test_compute_diff_mixed_changes(self):
        """Test diff with additions, removals, and modifications simultaneously."""
        facade, mock_svc = _make_facade()
        from_v = _make_version(
            version="1.0.0",
            content={"a": "old", "b": "keep", "c": "removed"},
        )
        to_v = _make_version(
            version="1.1.0",
            content={"a": "new", "b": "keep", "d": "added"},
        )
        mock_svc.get_version.side_effect = [from_v, to_v]
        result = await facade.compute_diff("vid-from", "vid-to")
        assert result["content_diff"]["added"] == {"d": "added"}
        assert result["content_diff"]["removed"] == {"c": "removed"}
        assert result["content_diff"]["modified"]["a"] == {"from": "old", "to": "new"}
        assert "b" not in result["content_diff"]["modified"]

    async def test_compute_diff_calls_get_version_twice(self):
        """compute_diff must call get_version for both from and to IDs."""
        facade, mock_svc = _make_facade()
        mock_svc.get_version.return_value = None
        await facade.compute_diff("from-id", "to-id")
        assert mock_svc.get_version.await_count == 2

    async def test_compute_diff_uses_tenant_context_via_get_version(self):
        """compute_diff delegates through get_version which uses _get_tenant_id."""
        facade, mock_svc = _make_facade(default_tenant_id="sys")
        from_v = _make_version(version="1.0.0", content={"x": 1})
        to_v = _make_version(version="1.0.1", content={"x": 2})
        mock_svc.get_version.side_effect = [from_v, to_v]
        with patch(
            "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
            return_value=None,
        ):
            result = await facade.compute_diff("vid-from", "vid-to")
        assert result is not None


# ---------------------------------------------------------------------------
# StorageConfig export
# ---------------------------------------------------------------------------


class TestStorageConfigExport:
    def test_storage_config_importable_from_storage(self):
        from enhanced_agent_bus.constitutional.storage import StorageConfig as SC

        assert SC is StorageConfig

    def test_storage_config_defaults(self):
        cfg = StorageConfig()
        assert cfg.redis_url == "redis://localhost:6379"
        assert cfg.database_url == "postgresql+asyncpg://localhost/acgs2"
        assert cfg.cache_ttl == 3600
        assert cfg.lock_timeout == 30
        assert cfg.enable_multi_tenancy is True
        assert cfg.default_tenant_id == "system"

    def test_storage_config_custom(self):
        cfg = StorageConfig(
            redis_url="redis://x:6380",
            database_url="postgresql+asyncpg://x/db",
            cache_ttl=600,
            lock_timeout=10,
            enable_multi_tenancy=False,
            default_tenant_id="custom",
        )
        assert cfg.redis_url == "redis://x:6380"
        assert cfg.cache_ttl == 600
        assert cfg.enable_multi_tenancy is False


# ---------------------------------------------------------------------------
# __all__ export check
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports(self):
        from enhanced_agent_bus.constitutional import storage

        assert "ConstitutionalStorageService" in storage.__all__
        assert "StorageConfig" in storage.__all__


# ---------------------------------------------------------------------------
# Integration: multi-tenancy context propagation
# ---------------------------------------------------------------------------


class TestMultiTenancyContextPropagation:
    async def test_tenant_context_propagates_to_save_version(self):
        from enhanced_agent_bus.multi_tenancy.context import tenant_context

        facade, mock_svc = _make_facade(enable_multi_tenancy=True, default_tenant_id="system")
        version = _make_version()

        with tenant_context(tenant_id="ctx-tenant"):
            await facade.save_version(version)

        mock_svc.save_version.assert_awaited_once_with(version, "ctx-tenant")

    async def test_tenant_context_propagates_to_get_active_version(self):
        from enhanced_agent_bus.multi_tenancy.context import tenant_context

        facade, mock_svc = _make_facade(enable_multi_tenancy=True, default_tenant_id="system")

        with tenant_context(tenant_id="active-tenant"):
            await facade.get_active_version()

        mock_svc.get_active_version.assert_awaited_once_with("active-tenant")

    async def test_disabled_multi_tenancy_ignores_context(self):
        from enhanced_agent_bus.multi_tenancy.context import tenant_context

        facade, mock_svc = _make_facade(enable_multi_tenancy=False, default_tenant_id="fixed")
        version = _make_version()

        with tenant_context(tenant_id="ctx-tenant"):
            await facade.save_version(version)

        # Should use "fixed", not "ctx-tenant"
        mock_svc.save_version.assert_awaited_once_with(version, "fixed")
