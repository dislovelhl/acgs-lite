"""
Tests for Tenant Manager.

Constitutional Hash: 608508a9bd224290

Covers:
- TenantManager CRUD (create, get, get_by_slug, list, update, delete)
- Lifecycle (activate, suspend, reactivate)
- Configuration and quota updates
- Quota checking and usage tracking
- Hierarchical tenant operations
- Context management
- Event subscription and publishing
- Cache management
- Validation
- Error classes
- Module-level helpers (get_tenant_manager, set_tenant_manager)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.multi_tenancy.manager import (
    TenantEvent,
    TenantManager,
    TenantManagerError,
    TenantNotFoundError,
    TenantQuotaExceededError,
    TenantValidationError,
    get_tenant_manager,
    set_tenant_manager,
)
from enhanced_agent_bus.multi_tenancy.models import (
    Tenant,
    TenantConfig,
    TenantQuota,
    TenantStatus,
    TenantUsage,
)
from enhanced_agent_bus.multi_tenancy.repository import TenantRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager():
    """Create a fresh TenantManager."""
    return TenantManager()


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


class TestCreateTenant:
    async def test_create_basic(self, manager):
        tenant = await manager.create_tenant(name="Acme Corp", slug="acme-corp")
        assert tenant.name == "Acme Corp"
        assert tenant.slug == "acme-corp"
        assert tenant.status == TenantStatus.PENDING

    async def test_create_with_auto_activate(self, manager):
        tenant = await manager.create_tenant(
            name="Active Corp", slug="active-corp", auto_activate=True
        )
        assert tenant.status == TenantStatus.ACTIVE

    async def test_create_invalid_slug_raises(self, manager):
        with pytest.raises(TenantValidationError):
            await manager.create_tenant(name="Bad", slug="-bad-slug-")

    async def test_create_invalid_slug_uppercase(self, manager):
        with pytest.raises(TenantValidationError):
            await manager.create_tenant(name="Bad", slug="BAD")

    async def test_create_with_parent(self, manager):
        parent = await manager.create_tenant(name="Parent", slug="parent-org", auto_activate=True)
        child = await manager.create_tenant(
            name="Child", slug="child-org", parent_tenant_id=parent.tenant_id
        )
        assert child.parent_tenant_id == parent.tenant_id

    async def test_create_with_nonexistent_parent_raises(self, manager):
        with pytest.raises(TenantNotFoundError):
            await manager.create_tenant(
                name="Orphan", slug="orphan", parent_tenant_id="nonexistent"
            )

    async def test_create_with_inactive_parent_raises(self, manager):
        parent = await manager.create_tenant(name="Inactive Parent", slug="inactive-parent")
        # Parent is PENDING, not ACTIVE
        with pytest.raises(TenantValidationError):
            await manager.create_tenant(
                name="Child", slug="child-of-inactive", parent_tenant_id=parent.tenant_id
            )

    async def test_create_inherits_parent_config(self, manager):
        parent = await manager.create_tenant(name="Parent", slug="parent-cfg", auto_activate=True)
        child = await manager.create_tenant(
            name="Child", slug="child-cfg", parent_tenant_id=parent.tenant_id
        )
        # Should inherit parent's config since none was specified
        assert child.config is not None


class TestGetTenant:
    async def test_get_existing(self, manager):
        tenant = await manager.create_tenant(name="Test", slug="test-get")
        found = await manager.get_tenant(tenant.tenant_id)
        assert found is not None
        assert found.tenant_id == tenant.tenant_id

    async def test_get_nonexistent(self, manager):
        found = await manager.get_tenant("nonexistent-id")
        assert found is None

    async def test_get_by_slug(self, manager):
        tenant = await manager.create_tenant(name="Test", slug="test-slug")
        found = await manager.get_tenant_by_slug("test-slug")
        assert found is not None
        assert found.slug == "test-slug"

    async def test_get_by_slug_nonexistent(self, manager):
        found = await manager.get_tenant_by_slug("nonexistent-slug")
        assert found is None

    async def test_get_cached(self, manager):
        tenant = await manager.create_tenant(name="Cached", slug="cached-t")
        # Second call should use cache
        found = await manager.get_tenant(tenant.tenant_id)
        assert found is not None


class TestListTenants:
    async def test_list_all(self, manager):
        await manager.create_tenant(name="A", slug="aa")
        await manager.create_tenant(name="B", slug="bb")
        tenants = await manager.list_tenants()
        assert len(tenants) == 2

    async def test_list_with_pagination(self, manager):
        for i in range(5):
            await manager.create_tenant(name=f"T{i}", slug=f"t{i}")
        page = await manager.list_tenants(skip=2, limit=2)
        assert len(page) == 2

    async def test_list_by_parent(self, manager):
        parent = await manager.create_tenant(name="Parent", slug="parent-list", auto_activate=True)
        await manager.create_tenant(name="C1", slug="c1-list", parent_tenant_id=parent.tenant_id)
        await manager.create_tenant(name="C2", slug="c2-list", parent_tenant_id=parent.tenant_id)
        await manager.create_tenant(name="Other", slug="other-list")

        children = await manager.list_tenants(parent_id=parent.tenant_id)
        assert len(children) == 2


class TestUpdateTenant:
    async def test_update_name(self, manager):
        tenant = await manager.create_tenant(name="Old", slug="update-t")
        updated = await manager.update_tenant(tenant.tenant_id, name="New")
        assert updated.name == "New"

    async def test_update_metadata(self, manager):
        tenant = await manager.create_tenant(name="Meta", slug="meta-t")
        updated = await manager.update_tenant(tenant.tenant_id, metadata={"key": "value"})
        assert updated.metadata["key"] == "value"

    async def test_update_nonexistent(self, manager):
        result = await manager.update_tenant("nonexistent", name="X")
        assert result is None


class TestDeleteTenant:
    async def test_delete_existing(self, manager):
        tenant = await manager.create_tenant(name="Del", slug="del-t")
        result = await manager.delete_tenant(tenant.tenant_id)
        assert result is True
        found = await manager.get_tenant(tenant.tenant_id)
        assert found is None

    async def test_delete_nonexistent(self, manager):
        result = await manager.delete_tenant("nonexistent")
        assert result is False

    async def test_delete_with_children_raises(self, manager):
        parent = await manager.create_tenant(name="Parent", slug="parent-del", auto_activate=True)
        await manager.create_tenant(
            name="Child", slug="child-del", parent_tenant_id=parent.tenant_id
        )
        with pytest.raises(TenantValidationError):
            await manager.delete_tenant(parent.tenant_id)

    async def test_delete_with_children_force(self, manager):
        parent = await manager.create_tenant(name="Parent", slug="parent-force", auto_activate=True)
        await manager.create_tenant(
            name="Child", slug="child-force", parent_tenant_id=parent.tenant_id
        )
        result = await manager.delete_tenant(parent.tenant_id, force=True)
        assert result is True


# ---------------------------------------------------------------------------
# Lifecycle Tests
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_activate(self, manager):
        tenant = await manager.create_tenant(name="Act", slug="act-t")
        activated = await manager.activate_tenant(tenant.tenant_id)
        assert activated.status == TenantStatus.ACTIVE

    async def test_activate_already_active(self, manager):
        tenant = await manager.create_tenant(name="AA", slug="aa-t", auto_activate=True)
        # Should return same tenant without error
        result = await manager.activate_tenant(tenant.tenant_id)
        assert result.status == TenantStatus.ACTIVE

    async def test_activate_nonexistent(self, manager):
        result = await manager.activate_tenant("nonexistent")
        assert result is None

    async def test_activate_deactivated_raises(self, manager):
        tenant = await manager.create_tenant(name="Deact", slug="deact-t")
        # Manually set to deactivated
        t = await manager.get_tenant(tenant.tenant_id)
        t.status = TenantStatus.DEACTIVATED
        with pytest.raises(TenantValidationError):
            await manager.activate_tenant(tenant.tenant_id)

    async def test_suspend(self, manager):
        tenant = await manager.create_tenant(name="Sus", slug="sus-t", auto_activate=True)
        suspended = await manager.suspend_tenant(tenant.tenant_id, reason="Test")
        assert suspended.status == TenantStatus.SUSPENDED

    async def test_suspend_nonexistent(self, manager):
        result = await manager.suspend_tenant("nonexistent")
        assert result is None

    async def test_suspend_with_children(self, manager):
        parent = await manager.create_tenant(name="P", slug="p-sus", auto_activate=True)
        child = await manager.create_tenant(
            name="C", slug="c-sus", parent_tenant_id=parent.tenant_id, auto_activate=True
        )
        await manager.suspend_tenant(parent.tenant_id, reason="Test", suspend_children=True)
        child_updated = await manager.get_tenant(child.tenant_id)
        assert child_updated.status == TenantStatus.SUSPENDED

    async def test_reactivate(self, manager):
        tenant = await manager.create_tenant(name="React", slug="react-t", auto_activate=True)
        await manager.suspend_tenant(tenant.tenant_id)
        reactivated = await manager.reactivate_tenant(tenant.tenant_id)
        assert reactivated.status == TenantStatus.ACTIVE

    async def test_reactivate_not_suspended_raises(self, manager):
        tenant = await manager.create_tenant(name="NotSus", slug="notsus-t")
        with pytest.raises(TenantValidationError):
            await manager.reactivate_tenant(tenant.tenant_id)

    async def test_reactivate_nonexistent(self, manager):
        result = await manager.reactivate_tenant("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Config and Quota Updates
# ---------------------------------------------------------------------------


class TestConfigQuotaUpdates:
    async def test_update_config(self, manager):
        tenant = await manager.create_tenant(name="Cfg", slug="cfg-t", auto_activate=True)
        new_config = TenantConfig(cache_ttl_seconds=600)
        updated = await manager.update_config(tenant.tenant_id, new_config)
        assert updated.config.cache_ttl_seconds == 600

    async def test_update_config_nonexistent(self, manager):
        result = await manager.update_config("nonexistent", TenantConfig())
        assert result is None

    async def test_update_quota(self, manager):
        tenant = await manager.create_tenant(name="Qta", slug="qta-t", auto_activate=True)
        new_quota = TenantQuota(max_agents=50)
        updated = await manager.update_quota(tenant.tenant_id, new_quota)
        assert updated.quota["max_agents"] == 50

    async def test_update_quota_nonexistent(self, manager):
        result = await manager.update_quota("nonexistent", TenantQuota())
        assert result is None


# ---------------------------------------------------------------------------
# Quota Management
# ---------------------------------------------------------------------------


class TestQuotaManagement:
    async def test_check_quota_within_limits(self, manager):
        tenant = await manager.create_tenant(name="Q", slug="q-check", auto_activate=True)
        result = await manager.check_quota(tenant.tenant_id, "agents", 1)
        assert result is True

    async def test_check_quota_exceeded(self, manager):
        tenant = await manager.create_tenant(name="Q", slug="q-exceed", auto_activate=True)
        # Default max_agents is 100, request 101
        result = await manager.check_quota(tenant.tenant_id, "agents", 101)
        assert result is False

    async def test_check_quota_unknown_resource(self, manager):
        tenant = await manager.create_tenant(name="Q", slug="q-unknown", auto_activate=True)
        result = await manager.check_quota(tenant.tenant_id, "unknown_resource")
        assert result is True

    async def test_check_quota_nonexistent_tenant_raises(self, manager):
        with pytest.raises(TenantNotFoundError):
            await manager.check_quota("nonexistent", "agents")

    async def test_increment_usage(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-inc", auto_activate=True)
        usage = await manager.increment_usage(tenant.tenant_id, "agents", 5)
        assert usage.agent_count == 5

    async def test_increment_usage_exceeds_quota(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-exc", auto_activate=True)
        with pytest.raises(TenantQuotaExceededError):
            await manager.increment_usage(tenant.tenant_id, "agents", 101)

    async def test_decrement_usage(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-dec", auto_activate=True)
        await manager.increment_usage(tenant.tenant_id, "agents", 10)
        usage = await manager.decrement_usage(tenant.tenant_id, "agents", 3)
        assert usage.agent_count == 7

    async def test_decrement_below_zero(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-zero", auto_activate=True)
        usage = await manager.decrement_usage(tenant.tenant_id, "agents", 5)
        assert usage.agent_count == 0

    async def test_get_usage(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-get", auto_activate=True)
        usage = await manager.get_usage(tenant.tenant_id)
        assert isinstance(usage, TenantUsage)

    async def test_reset_message_usage(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-reset", auto_activate=True)
        await manager.increment_usage(tenant.tenant_id, "messages", 50)
        await manager.reset_message_usage()
        usage = await manager.get_usage(tenant.tenant_id)
        assert usage.message_count_minute == 0

    async def test_all_resource_types_increment(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-all", auto_activate=True)
        for resource in ["agents", "policies", "messages", "storage", "sessions"]:
            usage = await manager.increment_usage(tenant.tenant_id, resource, 1)
            assert usage is not None

    async def test_all_resource_types_decrement(self, manager):
        tenant = await manager.create_tenant(name="U", slug="u-all-dec", auto_activate=True)
        for resource in ["agents", "policies", "messages", "storage", "sessions"]:
            await manager.increment_usage(tenant.tenant_id, resource, 5)
        for resource in ["agents", "policies", "messages", "storage", "sessions"]:
            usage = await manager.decrement_usage(tenant.tenant_id, resource, 2)
            assert usage is not None

    async def test_quota_warning_event(self, manager):
        """Test quota warning event is published when threshold exceeded."""
        events_received = []

        def handler(tenant, extra):
            events_received.append(extra)

        manager.subscribe(TenantEvent.QUOTA_WARNING, handler)
        tenant = await manager.create_tenant(name="W", slug="w-warn", auto_activate=True)
        # Bring usage close to the limit
        manager._usage[tenant.tenant_id] = TenantUsage(agent_count=85)
        await manager.check_quota(tenant.tenant_id, "agents", 5)
        assert len(events_received) >= 1


# ---------------------------------------------------------------------------
# Hierarchical Operations
# ---------------------------------------------------------------------------


class TestHierarchy:
    async def test_get_child_tenants(self, manager):
        parent = await manager.create_tenant(name="P", slug="p-hier", auto_activate=True)
        await manager.create_tenant(name="C1", slug="c1-hier", parent_tenant_id=parent.tenant_id)
        await manager.create_tenant(name="C2", slug="c2-hier", parent_tenant_id=parent.tenant_id)
        children = await manager.get_child_tenants(parent.tenant_id)
        assert len(children) == 2

    async def test_get_tenant_hierarchy(self, manager):
        root = await manager.create_tenant(name="Root", slug="root-hier", auto_activate=True)
        child = await manager.create_tenant(
            name="Child", slug="child-hier", parent_tenant_id=root.tenant_id
        )
        hierarchy = await manager.get_tenant_hierarchy(child.tenant_id)
        assert len(hierarchy) == 2
        assert hierarchy[0].tenant_id == root.tenant_id
        assert hierarchy[1].tenant_id == child.tenant_id

    async def test_get_all_descendants(self, manager):
        root = await manager.create_tenant(name="Root", slug="root-desc", auto_activate=True)
        child = await manager.create_tenant(
            name="Child",
            slug="child-desc",
            parent_tenant_id=root.tenant_id,
            auto_activate=True,
        )
        grandchild = await manager.create_tenant(
            name="Grandchild", slug="gc-desc", parent_tenant_id=child.tenant_id
        )
        descendants = await manager.get_all_descendants(root.tenant_id)
        ids = {d.tenant_id for d in descendants}
        assert child.tenant_id in ids
        assert grandchild.tenant_id in ids


# ---------------------------------------------------------------------------
# Context Management
# ---------------------------------------------------------------------------


class TestContextManagement:
    def test_get_context(self, manager):
        ctx = manager.get_context("tenant-1", user_id="user-1", is_admin=True)
        assert ctx.tenant_id == "tenant-1"
        assert ctx.user_id == "user-1"
        assert ctx.is_admin is True

    def test_context_manager(self, manager):
        cm = manager.context("tenant-2", user_id="user-2")
        with cm as ctx:
            assert ctx.tenant_id == "tenant-2"


# ---------------------------------------------------------------------------
# Event Subscription
# ---------------------------------------------------------------------------


class TestEventSubscription:
    async def test_subscribe_and_publish(self, manager):
        events = []

        def handler(tenant, extra):
            events.append({"tenant": tenant, "extra": extra})

        manager.subscribe(TenantEvent.CREATED, handler)
        await manager.create_tenant(name="Evt", slug="evt-t")
        assert len(events) == 1

    async def test_unsubscribe(self, manager):
        events = []

        def handler(tenant, extra):
            events.append(True)

        manager.subscribe(TenantEvent.CREATED, handler)
        manager.unsubscribe(TenantEvent.CREATED, handler)
        await manager.create_tenant(name="NoEvt", slug="noevt-t")
        assert len(events) == 0

    async def test_async_handler(self, manager):
        events = []

        async def handler(tenant, extra):
            events.append(True)

        manager.subscribe(TenantEvent.CREATED, handler)
        await manager.create_tenant(name="Async", slug="async-t")
        assert len(events) == 1

    async def test_handler_error_does_not_propagate(self, manager):
        def bad_handler(tenant, extra):
            raise RuntimeError("handler boom")

        manager.subscribe(TenantEvent.CREATED, bad_handler)
        # Should not raise
        tenant = await manager.create_tenant(name="Safe", slug="safe-t")
        assert tenant is not None


# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------


class TestCacheManagement:
    def test_clear_cache(self, manager):
        manager._cache["test"] = ("obj", None)
        manager._slug_to_id["test-slug"] = "test"
        manager.clear_cache()
        assert len(manager._cache) == 0
        assert len(manager._slug_to_id) == 0

    async def test_cache_expiry(self, manager):
        tenant = await manager.create_tenant(name="Exp", slug="exp-t")
        # Manually expire cache
        from datetime import UTC, datetime, timedelta

        manager._cache[tenant.tenant_id] = (
            tenant,
            datetime.now(UTC) - timedelta(seconds=manager._cache_ttl + 1),
        )
        result = manager._get_cached_tenant(tenant.tenant_id)
        assert result is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_slug(self, manager):
        assert manager._validate_slug("valid-slug") is True
        assert manager._validate_slug("a") is True
        assert manager._validate_slug("abc123") is True

    def test_invalid_slug(self, manager):
        assert manager._validate_slug("-starts-with-dash") is False
        assert manager._validate_slug("UPPERCASE") is False
        assert manager._validate_slug("") is False


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    async def test_get_stats(self, manager):
        await manager.create_tenant(name="S1", slug="s1-stat")
        stats = manager.get_stats()
        assert stats["total_tenants"] == 1
        assert "constitutional_hash" in stats


# ---------------------------------------------------------------------------
# Error Classes
# ---------------------------------------------------------------------------


class TestErrorClasses:
    def test_tenant_manager_error(self):
        err = TenantManagerError("test error", tenant_id="t1")
        assert err.tenant_id == "t1"

    def test_tenant_not_found_error(self):
        err = TenantNotFoundError("not found", tenant_id="t2")
        assert err.http_status_code == 404

    def test_tenant_quota_exceeded_error(self):
        err = TenantQuotaExceededError(
            "quota exceeded",
            tenant_id="t3",
            resource="agents",
            current=100,
            limit=100,
        )
        assert err.resource == "agents"
        assert err.http_status_code == 429

    def test_tenant_validation_error(self):
        err = TenantValidationError("invalid")
        assert err.http_status_code == 400


# ---------------------------------------------------------------------------
# Module Helpers
# ---------------------------------------------------------------------------


class TestModuleHelpers:
    def test_get_tenant_manager_singleton(self):
        import enhanced_agent_bus.multi_tenancy.manager as mod

        mod._default_manager = None
        m1 = get_tenant_manager()
        m2 = get_tenant_manager()
        assert m1 is m2
        mod._default_manager = None  # cleanup

    def test_set_tenant_manager(self):
        import enhanced_agent_bus.multi_tenancy.manager as mod

        original = mod._default_manager
        custom = TenantManager()
        set_tenant_manager(custom)
        assert get_tenant_manager() is custom
        mod._default_manager = original  # cleanup
