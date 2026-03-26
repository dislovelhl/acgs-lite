"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- decision_store.py (Redis-backed decision explanation storage)
- routes/tenants.py (Tenant management API endpoints)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# decision_store imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.decision_store import (
    DEFAULT_KEY_PREFIX,
    DEFAULT_TTL_SECONDS,
    DecisionStore,
    get_decision_store,
    reset_decision_store,
)
from enhanced_agent_bus.multi_tenancy import (
    Tenant,
    TenantConfig,
    TenantNotFoundError,
    TenantQuota,
    TenantQuotaExceededError,
    TenantStatus,
    TenantValidationError,
)
from enhanced_agent_bus.routes.models.tenant_models import (
    CreateTenantRequest,
    QuotaCheckRequest,
    TenantResponse,
)

# ---------------------------------------------------------------------------
# tenants route imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.routes.tenants import (
    _build_quota_check_response,
    _build_tenant_config_and_quota,
    _build_tenant_hierarchy_response,
    _build_tenant_list_response,
    _build_usage_response,
    _calculate_utilization,
    _check_tenant_scope,
    _extract_usage_and_quota_dicts,
    _is_uuid,
    _parse_status_filter,
    _quota_resource_keys,
    _raise_internal_tenant_error,
    _raise_tenant_not_found,
    _raise_value_http_error,
    _to_dict_safe,
    _validate_admin_api_key,
    get_manager,
    router,
)

# ============================================================================
# Helpers / Fixtures
# ============================================================================


def _make_mock_explanation(
    *,
    decision_id: str = "dec-001",
    tenant_id: str = "tenant-a",
    message_id: str | None = "msg-001",
) -> MagicMock:
    """Build a mock DecisionExplanationV1 for store tests."""
    m = MagicMock()
    m.decision_id = decision_id
    m.tenant_id = tenant_id
    m.message_id = message_id
    m.model_dump_json.return_value = json.dumps(
        {
            "decision_id": decision_id,
            "tenant_id": tenant_id,
            "message_id": message_id,
            "outcome": "approved",
        }
    )
    return m


def _make_tenant(
    *,
    tenant_id: str = "t-100",
    name: str = "Test Corp",
    slug: str = "test-corp",
    status: TenantStatus = TenantStatus.ACTIVE,
    parent_tenant_id: str | None = None,
) -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        status=status,
        parent_tenant_id=parent_tenant_id,
        config=TenantConfig(),
        quota=TenantQuota().to_dict(),
        usage={},
        metadata={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_app(mock_manager: MagicMock, admin_id: str = "system-admin") -> FastAPI:
    """Create a FastAPI app wired to mock manager and bypassed auth."""
    app = FastAPI()
    app.include_router(router)

    # Override auth dependency to return a static admin_id
    from enhanced_agent_bus.routes.tenants import get_admin_tenant_id
    from enhanced_agent_bus.routes.tenants import get_manager as _gm

    app.dependency_overrides[get_admin_tenant_id] = lambda: admin_id
    app.dependency_overrides[_gm] = lambda: mock_manager
    return app


# ============================================================================
# DecisionStore — memory fallback tests
# ============================================================================


class TestDecisionStoreInit:
    """Test DecisionStore construction and initialization."""

    async def test_default_construction(self):
        ds = DecisionStore()
        assert ds._ttl_seconds == DEFAULT_TTL_SECONDS
        assert ds._key_prefix == DEFAULT_KEY_PREFIX
        assert not ds._initialized

    async def test_custom_params(self):
        ds = DecisionStore(
            redis_url="redis://custom:1234",
            ttl_seconds=60,
            key_prefix="my:prefix",
            index_prefix="my:idx",
            enable_metrics=False,
        )
        assert ds._ttl_seconds == 60
        assert ds._key_prefix == "my:prefix"
        assert ds._index_prefix == "my:idx"

    @patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False)
    async def test_initialize_without_redis(self):
        ds = DecisionStore()
        result = await ds.initialize()
        assert result is True
        assert ds._use_memory_fallback is True
        assert ds._metrics["memory_fallback_active"] is True

    @patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False)
    async def test_double_initialize_is_idempotent(self):
        ds = DecisionStore()
        await ds.initialize()
        result = await ds.initialize()
        assert result is True

    @patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True)
    async def test_initialize_unhealthy_redis_falls_back(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": False, "error": "down"}
        ds = DecisionStore(redis_pool=mock_pool)
        result = await ds.initialize()
        assert result is True
        assert ds._use_memory_fallback is True

    @patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True)
    async def test_initialize_healthy_redis(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": True}
        ds = DecisionStore(redis_pool=mock_pool)
        result = await ds.initialize()
        assert result is True
        assert ds._use_memory_fallback is False

    @patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True)
    async def test_initialize_redis_exception_falls_back(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.side_effect = ConnectionError("refused")
        ds = DecisionStore(redis_pool=mock_pool)
        result = await ds.initialize()
        assert result is True
        assert ds._use_memory_fallback is True


class TestDecisionStoreKeyMaking:
    """Test key generation helpers."""

    def test_make_key_normal(self):
        ds = DecisionStore()
        assert ds._make_key("tenant-a", "dec-1") == "acgs:decision:tenant-a:dec-1"

    def test_make_key_colon_replacement(self):
        ds = DecisionStore()
        assert ds._make_key("a:b:c", "d") == "acgs:decision:a_b_c:d"

    def test_make_key_empty_tenant(self):
        ds = DecisionStore()
        assert ds._make_key("", "d") == "acgs:decision:default:d"

    def test_make_message_index_key(self):
        ds = DecisionStore()
        key = ds._make_message_index_key("t1", "msg-1")
        assert key == "acgs:decision:idx:msg:t1:msg-1"

    def test_make_time_index_key(self):
        ds = DecisionStore()
        key = ds._make_time_index_key("t1", "2026-01-01")
        assert key == "acgs:decision:idx:time:t1:2026-01-01"

    def test_make_message_index_key_empty_tenant(self):
        ds = DecisionStore()
        key = ds._make_message_index_key("", "msg-1")
        assert "default" in key

    def test_make_time_index_key_colon_tenant(self):
        ds = DecisionStore()
        key = ds._make_time_index_key("a:b", "ts")
        assert "a_b" in key


class TestDecisionStoreMemoryOps:
    """Test CRUD ops in memory-fallback mode."""

    async def _make_store(self) -> DecisionStore:
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        return ds

    async def test_store_and_get(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        with patch("enhanced_agent_bus.decision_store.DecisionExplanationV1", None):
            ok = await ds.store(expl)
            assert ok is True
            result = await ds.get("dec-001", "tenant-a")
        assert result is not None
        assert ds._metrics["total_stores"] == 1

    async def test_store_without_message_id(self):
        ds = await self._make_store()
        expl = _make_mock_explanation(message_id=None)
        ok = await ds.store(expl)
        assert ok is True
        assert len(ds._memory_indexes) == 0

    async def test_store_with_custom_ttl(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        ok = await ds.store(expl, ttl_seconds=30)
        assert ok is True

    async def test_get_missing_key_returns_none(self):
        ds = await self._make_store()
        result = await ds.get("nonexistent")
        assert result is None
        assert ds._metrics["cache_misses"] == 1

    async def test_get_by_message_id_found(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        with patch("enhanced_agent_bus.decision_store.DecisionExplanationV1", None):
            await ds.store(expl)
            result = await ds.get_by_message_id("msg-001", "tenant-a")
        assert result is not None

    async def test_get_by_message_id_not_found(self):
        ds = await self._make_store()
        result = await ds.get_by_message_id("missing-msg")
        assert result is None

    async def test_delete_existing_key(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        await ds.store(expl)
        deleted = await ds.delete("dec-001", "tenant-a")
        assert deleted is True
        assert ds._metrics["total_deletes"] == 1
        # Index should also be cleaned
        assert len(ds._memory_indexes) == 0

    async def test_delete_missing_key(self):
        ds = await self._make_store()
        deleted = await ds.delete("nope")
        assert deleted is False

    async def test_list_decisions_empty(self):
        ds = await self._make_store()
        ids = await ds.list_decisions("tenant-a")
        assert ids == []

    async def test_list_decisions_with_data(self):
        ds = await self._make_store()
        for i in range(3):
            expl = _make_mock_explanation(decision_id=f"d-{i}", tenant_id="t1")
            await ds.store(expl)
        ids = await ds.list_decisions("t1")
        assert len(ids) == 3

    async def test_list_decisions_with_offset_and_limit(self):
        ds = await self._make_store()
        for i in range(5):
            expl = _make_mock_explanation(decision_id=f"d-{i}", tenant_id="t1")
            await ds.store(expl)
        ids = await ds.list_decisions("t1", limit=2, offset=1)
        assert len(ids) == 2

    async def test_exists_true(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        await ds.store(expl)
        assert await ds.exists("dec-001", "tenant-a") is True

    async def test_exists_false(self):
        ds = await self._make_store()
        assert await ds.exists("nope") is False

    async def test_get_ttl_existing(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        await ds.store(expl)
        ttl = await ds.get_ttl("dec-001", "tenant-a")
        assert ttl == DEFAULT_TTL_SECONDS

    async def test_get_ttl_missing(self):
        ds = await self._make_store()
        ttl = await ds.get_ttl("nope")
        assert ttl == -2

    async def test_extend_ttl_existing(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        await ds.store(expl)
        result = await ds.extend_ttl("dec-001", "tenant-a")
        assert result is True

    async def test_extend_ttl_missing(self):
        ds = await self._make_store()
        result = await ds.extend_ttl("nope")
        assert result is False

    async def test_extend_ttl_custom_seconds(self):
        ds = await self._make_store()
        expl = _make_mock_explanation()
        await ds.store(expl)
        result = await ds.extend_ttl("dec-001", "tenant-a", ttl_seconds=999)
        assert result is True


class TestDecisionStoreMetrics:
    """Test metrics and health check."""

    async def test_get_metrics_initial(self):
        ds = DecisionStore()
        metrics = ds.get_metrics()
        assert metrics["cache_hit_rate"] == 0.0
        assert metrics["avg_latency_ms"] == 0.0
        assert "constitutional_hash" in metrics

    async def test_get_metrics_with_ops(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        expl = _make_mock_explanation()
        await ds.store(expl)
        with patch("enhanced_agent_bus.decision_store.DecisionExplanationV1", None):
            await ds.get("dec-001", "tenant-a")
        metrics = ds.get_metrics()
        assert metrics["total_stores"] == 1
        assert metrics["total_retrievals"] == 1
        assert metrics["cache_hits"] == 1
        assert metrics["cache_hit_rate"] == 100.0
        assert metrics["avg_latency_ms"] > 0

    async def test_health_check_memory_fallback(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        health = await ds.health_check()
        assert health["healthy"] is True
        assert health["using_memory_fallback"] is True

    @patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True)
    async def test_health_check_with_pool(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": True}
        ds = DecisionStore(redis_pool=mock_pool)
        await ds.initialize()
        health = await ds.health_check()
        assert health["redis_healthy"] is True

    @patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True)
    async def test_health_check_redis_unhealthy(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": False, "error": "timeout"}
        ds = DecisionStore(redis_pool=mock_pool)
        ds._initialized = True
        ds._use_memory_fallback = False
        ds._pool = mock_pool
        health = await ds.health_check()
        assert health["redis_healthy"] is False
        assert health.get("redis_error") == "timeout"


class TestDecisionStoreClose:
    """Test close behavior."""

    async def test_close_resets_state(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        expl = _make_mock_explanation()
        await ds.store(expl)
        await ds.close()
        assert ds._initialized is False
        assert len(ds._memory_store) == 0
        assert len(ds._memory_indexes) == 0


class TestDecisionStoreErrorPaths:
    """Test error handling in store/get/delete."""

    async def test_store_serialization_error(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        expl = MagicMock()
        expl.model_dump_json.side_effect = TypeError("cannot serialize")
        result = await ds.store(expl)
        assert result is False
        assert ds._metrics["failed_operations"] == 1

    async def test_get_error_path(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        # Corrupt memory_store to trigger error
        key = ds._make_key("default", "bad")
        ds._memory_store[key] = "not-valid-json"
        with patch("enhanced_agent_bus.decision_store.DecisionExplanationV1") as mock_cls:
            mock_cls.model_validate_json.side_effect = ValueError("invalid")
            result = await ds.get("bad")
        assert result is None
        assert ds._metrics["failed_operations"] == 1

    async def test_get_by_message_id_error_path(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        # Inject a bad index that causes a downstream error
        msg_key = ds._make_message_index_key("default", "m1")
        ds._memory_indexes[msg_key] = "bad-decision-id"
        # get() will work normally but let's verify the flow
        result = await ds.get_by_message_id("m1")
        # Should return None since the decision_id doesn't map to stored data
        assert result is None

    async def test_delete_error_path(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        # Patch memory_store to raise on del
        with patch.object(ds, "_memory_store", side_effect_map=None) as mock_store:
            # Simulate a RuntimeError during delete
            original = ds._memory_store
            ds._memory_store = MagicMock(spec=dict)
            ds._memory_store.__contains__ = MagicMock(side_effect=RuntimeError("boom"))
            result = await ds.delete("x")
        assert result is False

    async def test_list_decisions_error(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        ds._memory_store = MagicMock()
        ds._memory_store.keys.side_effect = RuntimeError("keys broken")
        result = await ds.list_decisions("t")
        assert result == []

    async def test_exists_error(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        ds._memory_store = MagicMock()
        ds._memory_store.__contains__ = MagicMock(side_effect=RuntimeError("oops"))
        result = await ds.exists("x")
        assert result is False

    async def test_get_ttl_error(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        ds._memory_store = MagicMock()
        ds._memory_store.__contains__ = MagicMock(side_effect=RuntimeError("oops"))
        result = await ds.get_ttl("x")
        assert result == -2

    async def test_extend_ttl_error(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        ds._memory_store = MagicMock()
        ds._memory_store.__contains__ = MagicMock(side_effect=OSError("disk"))
        result = await ds.extend_ttl("x")
        assert result is False

    async def test_get_by_message_id_exception(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        ds._memory_indexes = MagicMock()
        ds._memory_indexes.get = MagicMock(side_effect=ConnectionError("conn lost"))
        result = await ds.get_by_message_id("m1")
        assert result is None
        assert ds._metrics["failed_operations"] >= 1


class TestDecisionStoreSingleton:
    """Test singleton get/reset helpers."""

    async def test_get_and_reset(self):
        await reset_decision_store()
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            store = await get_decision_store()
            assert store._initialized is True
            # Second call returns same instance
            store2 = await get_decision_store()
            assert store is store2
        await reset_decision_store()

    async def test_reset_when_none(self):
        await reset_decision_store()
        # Should not raise
        await reset_decision_store()


class TestDecisionStoreGetRawDict:
    """Test get() path when DecisionExplanationV1 is None (returns raw dict)."""

    async def test_get_returns_raw_dict_when_no_schema(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            await ds.initialize()
        expl = _make_mock_explanation()
        await ds.store(expl)
        with patch("enhanced_agent_bus.decision_store.DecisionExplanationV1", None):
            result = await ds.get("dec-001", "tenant-a")
        assert isinstance(result, dict)
        assert result["decision_id"] == "dec-001"


class TestDecisionStoreAutoInit:
    """Test auto-initialization when calling ops before explicit init."""

    async def test_store_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            expl = _make_mock_explanation()
            ok = await ds.store(expl)
        assert ok is True
        assert ds._initialized is True

    async def test_get_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            result = await ds.get("x")
        assert result is None
        assert ds._initialized is True

    async def test_delete_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            result = await ds.delete("x")
        assert result is False
        assert ds._initialized is True

    async def test_list_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            result = await ds.list_decisions()
        assert result == []
        assert ds._initialized is True

    async def test_exists_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            result = await ds.exists("x")
        assert result is False

    async def test_get_ttl_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            result = await ds.get_ttl("x")
        assert result == -2

    async def test_extend_ttl_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            result = await ds.extend_ttl("x")
        assert result is False

    async def test_get_by_message_id_auto_inits(self):
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            ds = DecisionStore()
            result = await ds.get_by_message_id("m")
        assert result is None


# ============================================================================
# Tenants Route — Helper / Pure Function Tests
# ============================================================================


class TestToDictSafe:
    """Test _to_dict_safe helper."""

    def test_none_returns_empty(self):
        assert _to_dict_safe(None) == {}

    def test_dict_passthrough(self):
        d = {"a": 1}
        assert _to_dict_safe(d) is d

    def test_pydantic_model(self):
        class M(BaseModel):
            x: int = 1

        assert _to_dict_safe(M()) == {"x": 1}

    def test_to_dict_method(self):
        class Obj:
            def to_dict(self):
                return {"y": 2}

        assert _to_dict_safe(Obj()) == {"y": 2}

    def test_dataclass(self):
        @dataclass
        class DC:
            z: int = 3

        assert _to_dict_safe(DC()) == {"z": 3}

    def test_unconvertible_returns_empty(self):
        assert _to_dict_safe(42) == {}


class TestIsUuid:
    """Test UUID validation helper."""

    def test_valid_uuid(self):
        assert _is_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_invalid_uuid(self):
        assert _is_uuid("not-a-uuid") is False

    def test_system_admin_is_not_uuid(self):
        assert _is_uuid("system-admin") is False

    def test_uppercase_uuid(self):
        assert _is_uuid("550E8400-E29B-41D4-A716-446655440000") is True


class TestCheckTenantScope:
    """Test cross-tenant scope enforcement."""

    def test_same_tenant_allowed(self):
        _check_tenant_scope("t1", "t1")  # Should not raise

    def test_super_admin_allowed(self):
        _check_tenant_scope("550e8400-e29b-41d4-a716-446655440000", "other", is_super_admin=True)

    def test_non_uuid_admin_allowed(self):
        _check_tenant_scope("admin-key", "any-tenant")

    def test_cross_tenant_uuid_blocked(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _check_tenant_scope(
                "550e8400-e29b-41d4-a716-446655440000",
                "660e8400-e29b-41d4-a716-446655440000",
            )
        assert exc_info.value.status_code == 403


class TestParseStatusFilter:
    """Test status filter parsing."""

    def test_none_returns_none(self):
        assert _parse_status_filter(None) is None

    def test_empty_returns_none(self):
        assert _parse_status_filter("") is None

    def test_valid_active(self):
        assert _parse_status_filter("active") == TenantStatus.ACTIVE

    def test_valid_uppercase(self):
        assert _parse_status_filter("PENDING") == TenantStatus.PENDING

    def test_invalid_raises_400(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _parse_status_filter("bogus")
        assert exc_info.value.status_code == 400


class TestQuotaResourceKeys:
    """Test resource-to-key mapping."""

    def test_known_resource(self):
        assert _quota_resource_keys("agents") == ("agents_count", "max_agents")

    def test_unknown_resource_fallback(self):
        assert _quota_resource_keys("widgets") == ("widgets_count", "max_widgets")


class TestCalculateUtilization:
    """Test utilization percentage calculation."""

    def test_normal_utilization(self):
        usage = {"agents_count": 50, "policies_count": 200, "messages_this_minute": 5000}
        quota = {"max_agents": 100, "max_policies": 1000, "max_messages_per_minute": 10000}
        result = _calculate_utilization(usage, quota)
        assert result["agents_count"] == 50.0
        assert result["policies_count"] == 20.0

    def test_zero_quota_skipped(self):
        usage = {"agents_count": 50}
        quota = {"max_agents": 0}
        result = _calculate_utilization(usage, quota)
        assert "agents_count" not in result

    def test_non_numeric_skipped(self):
        usage = {"agents_count": "bad"}
        quota = {"max_agents": 100}
        result = _calculate_utilization(usage, quota)
        assert "agents_count" not in result


class TestBuildHelpers:
    """Test response builder helpers."""

    def test_build_tenant_config_and_quota_with_values(self):
        req = CreateTenantRequest(
            name="Test",
            slug="te-st",
            config={"enable_batch_processing": True},
            quota={"max_agents": 50},
        )
        config, quota = _build_tenant_config_and_quota(req)
        assert config is not None
        assert quota is not None

    def test_build_tenant_config_and_quota_none(self):
        req = CreateTenantRequest(name="T", slug="ab-cd", config=None, quota=None)
        config, quota = _build_tenant_config_and_quota(req)
        assert config is None
        assert quota is None

    def test_build_usage_response(self):
        resp = _build_usage_response("t1", usage_dict={"a": 1}, quota_dict={"b": 2})
        assert resp.tenant_id == "t1"

    def test_build_quota_check_response_non_int_values(self):
        req = QuotaCheckRequest(resource="agents", requested_amount=1)
        resp = _build_quota_check_response(
            "t1",
            req,
            available=True,
            usage_dict={"agents_count": "bad"},
            quota_dict={"max_agents": "bad"},
        )
        assert resp.current_usage == 0
        assert resp.quota_limit == 0

    def test_build_tenant_hierarchy_response_empty_ancestors(self):
        resp = _build_tenant_hierarchy_response("t1", ancestors=[], descendants=[])
        assert resp.depth == 0
        assert resp.ancestors == []

    def test_build_tenant_hierarchy_response_with_ancestors(self):
        t1 = _make_tenant(tenant_id="root", slug="ro-ot")
        t2 = _make_tenant(tenant_id="child", slug="ch-ld")
        resp = _build_tenant_hierarchy_response("child", ancestors=[t1, t2], descendants=[])
        assert resp.depth == 1
        assert len(resp.ancestors) == 1

    def test_build_tenant_list_response(self):
        t = _make_tenant()
        resp = _build_tenant_list_response([t], page=0, page_size=10, has_more=False)
        assert resp.total_count == 1


class TestExtractUsageAndQuota:
    """Test _extract_usage_and_quota_dicts."""

    def test_with_usage_override(self):
        t = _make_tenant()
        usage_dict, quota_dict = _extract_usage_and_quota_dicts(t, usage_override={"x": 1})
        assert usage_dict == {"x": 1}

    def test_without_usage_attr(self):
        t = _make_tenant()
        usage_dict, _ = _extract_usage_and_quota_dicts(t)
        # Tenant model has no usage attr, so _to_dict_safe(None) => {}
        assert usage_dict == {}


class TestRaiseHelpers:
    """Test error raise helpers."""

    def test_raise_tenant_not_found(self):
        from fastapi import HTTPException

        e = TenantNotFoundError("gone", tenant_id="t1")
        with pytest.raises(HTTPException) as exc_info:
            _raise_tenant_not_found(e)
        assert exc_info.value.status_code == 404

    def test_raise_internal_tenant_error(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _raise_internal_tenant_error(RuntimeError("boom"), "do thing", "do thing")
        assert exc_info.value.status_code == 500

    def test_raise_value_http_error_conflict(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _raise_value_http_error(ValueError("already exists"), action="create")
        assert exc_info.value.status_code == 409

    def test_raise_value_http_error_duplicate(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _raise_value_http_error(ValueError("duplicate key"), action="create")
        assert exc_info.value.status_code == 409

    def test_raise_value_http_error_bad_request(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _raise_value_http_error(ValueError("invalid input"), action="tenant operation")
        assert exc_info.value.status_code == 400

    def test_raise_value_http_error_conflict_markers(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _raise_value_http_error(
                ValueError("has children"),
                action="delete",
                conflict_markers=("children",),
            )
        assert exc_info.value.status_code == 409


class TestValidateAdminApiKey:
    """Test API key validation."""

    def test_empty_admin_key_returns_false(self):
        with patch("enhanced_agent_bus.routes.tenants.TENANT_ADMIN_KEY", ""):
            assert _validate_admin_api_key("anything") is False

    def test_valid_key(self):
        with patch("enhanced_agent_bus.routes.tenants.TENANT_ADMIN_KEY", "secret123"):
            assert _validate_admin_api_key("secret123") is True

    def test_invalid_key(self):
        with patch("enhanced_agent_bus.routes.tenants.TENANT_ADMIN_KEY", "secret123"):
            assert _validate_admin_api_key("wrong") is False


class TestGetManager:
    """Test get_manager dependency."""

    def test_success(self):
        with patch("enhanced_agent_bus.routes.tenants.get_tenant_manager") as mock_fn:
            mock_fn.return_value = MagicMock()
            manager = get_manager()
            assert manager is not None

    def test_runtime_error(self):
        from fastapi import HTTPException

        with patch(
            "enhanced_agent_bus.routes.tenants.get_tenant_manager",
            side_effect=RuntimeError("no manager"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_manager()
            assert exc_info.value.status_code == 503


# ============================================================================
# Tenants Route — API Endpoint Tests (via TestClient)
# ============================================================================


class TestCreateTenantEndpoint:
    """Test POST /api/v1/tenants."""

    def test_create_success(self):
        mock_mgr = AsyncMock()
        tenant = _make_tenant(tenant_id="new-1", slug="new-co")
        mock_mgr.create_tenant.return_value = tenant
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "New Co", "slug": "new-co"},
        )
        assert resp.status_code == 201
        assert resp.json()["tenant_id"] == "new-1"

    def test_create_validation_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.create_tenant.side_effect = TenantValidationError("bad slug")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "X", "slug": "ba-dx"},
        )
        assert resp.status_code == 400

    def test_create_duplicate_slug(self):
        mock_mgr = AsyncMock()
        mock_mgr.create_tenant.side_effect = ValueError("already exists")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "Dup", "slug": "du-px"},
        )
        assert resp.status_code == 409

    def test_create_value_error_bad_request(self):
        mock_mgr = AsyncMock()
        mock_mgr.create_tenant.side_effect = ValueError("bad input")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "Err", "slug": "er-rx"},
        )
        assert resp.status_code == 400

    def test_create_runtime_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.create_tenant.side_effect = RuntimeError("db down")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants",
            json={"name": "Fail", "slug": "fa-il"},
        )
        assert resp.status_code == 500


class TestGetTenantEndpoint:
    """Test GET /api/v1/tenants/{tenant_id}."""

    def test_get_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = _make_tenant()
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t-100")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "t-100"

    def test_get_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/missing")
        assert resp.status_code == 404

    def test_get_tenant_not_found_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.side_effect = TenantNotFoundError("nope", tenant_id="x")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/x")
        assert resp.status_code == 404

    def test_get_runtime_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.side_effect = RuntimeError("oops")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t1")
        assert resp.status_code == 500


class TestGetTenantBySlugEndpoint:
    """Test GET /api/v1/tenants/by-slug/{slug}."""

    def test_get_by_slug_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant_by_slug.return_value = _make_tenant()
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/by-slug/test-corp")
        assert resp.status_code == 200

    def test_get_by_slug_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant_by_slug.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/by-slug/nope")
        assert resp.status_code == 404

    def test_get_by_slug_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant_by_slug.side_effect = RuntimeError("db")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/by-slug/err")
        assert resp.status_code == 500


class TestListTenantsEndpoint:
    """Test GET /api/v1/tenants."""

    def test_list_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.list_tenants.return_value = [_make_tenant()]
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["has_more"] is False

    def test_list_with_has_more(self):
        mock_mgr = AsyncMock()
        # Return limit+1 items to trigger has_more
        mock_mgr.list_tenants.return_value = [
            _make_tenant(tenant_id=f"t-{i}", slug=f"t-{i}x") for i in range(21)
        ]
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants?limit=20")
        data = resp.json()
        assert data["has_more"] is True
        assert data["total_count"] == 20

    def test_list_with_status_filter(self):
        mock_mgr = AsyncMock()
        mock_mgr.list_tenants.return_value = []
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants?status=active")
        assert resp.status_code == 200

    def test_list_invalid_status(self):
        mock_mgr = AsyncMock()
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants?status=bogus")
        assert resp.status_code == 400

    def test_list_runtime_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.list_tenants.side_effect = RuntimeError("fail")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants")
        assert resp.status_code == 500


class TestUpdateTenantEndpoint:
    """Test PATCH /api/v1/tenants/{tenant_id}."""

    def test_update_name(self):
        mock_mgr = AsyncMock()
        tenant = _make_tenant()
        mock_mgr.get_tenant.return_value = tenant
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.patch("/api/v1/tenants/t-100", json={"name": "New Name"})
        assert resp.status_code == 200

    def test_update_config(self):
        mock_mgr = AsyncMock()
        tenant = _make_tenant()
        mock_mgr.get_tenant.return_value = tenant
        mock_mgr.update_config.return_value = tenant
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.patch("/api/v1/tenants/t-100", json={"config": {"key": "val"}})
        assert resp.status_code == 200

    def test_update_metadata(self):
        mock_mgr = AsyncMock()
        tenant = _make_tenant()
        mock_mgr.get_tenant.return_value = tenant
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.patch("/api/v1/tenants/t-100", json={"metadata": {"env": "prod"}})
        assert resp.status_code == 200

    def test_update_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.patch("/api/v1/tenants/missing", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_tenant_not_found_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.side_effect = TenantNotFoundError("nope", tenant_id="x")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.patch("/api/v1/tenants/x", json={"name": "Y"})
        assert resp.status_code == 404

    def test_update_runtime_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.side_effect = RuntimeError("boom")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.patch("/api/v1/tenants/t1", json={"name": "Z"})
        assert resp.status_code == 500


class TestDeleteTenantEndpoint:
    """Test DELETE /api/v1/tenants/{tenant_id}."""

    def test_delete_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.delete_tenant.return_value = True
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.delete("/api/v1/tenants/t-100")
        assert resp.status_code == 204

    def test_delete_not_found_false(self):
        mock_mgr = AsyncMock()
        mock_mgr.delete_tenant.return_value = False
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.delete("/api/v1/tenants/missing")
        assert resp.status_code == 404

    def test_delete_tenant_not_found_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.delete_tenant.side_effect = TenantNotFoundError("nope", tenant_id="x")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.delete("/api/v1/tenants/x")
        assert resp.status_code == 404

    def test_delete_has_children(self):
        mock_mgr = AsyncMock()
        mock_mgr.delete_tenant.side_effect = ValueError("has children")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.delete("/api/v1/tenants/t1")
        assert resp.status_code == 409

    def test_delete_runtime_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.delete_tenant.side_effect = RuntimeError("db")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.delete("/api/v1/tenants/t1")
        assert resp.status_code == 500

    def test_delete_force(self):
        mock_mgr = AsyncMock()
        mock_mgr.delete_tenant.return_value = True
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.delete("/api/v1/tenants/t-100?force=true")
        assert resp.status_code == 204


class TestActivateTenantEndpoint:
    """Test POST /api/v1/tenants/{tenant_id}/activate."""

    def test_activate_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.activate_tenant.return_value = _make_tenant()
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/t-100/activate")
        assert resp.status_code == 200

    def test_activate_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.activate_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/missing/activate")
        assert resp.status_code == 404

    def test_activate_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.activate_tenant.side_effect = RuntimeError("oops")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/t1/activate")
        assert resp.status_code == 500


class TestSuspendTenantEndpoint:
    """Test POST /api/v1/tenants/{tenant_id}/suspend."""

    def test_suspend_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.suspend_tenant.return_value = _make_tenant(status=TenantStatus.SUSPENDED)
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/t-100/suspend", json={"reason": "abuse"})
        assert resp.status_code == 200

    def test_suspend_no_body(self):
        mock_mgr = AsyncMock()
        mock_mgr.suspend_tenant.return_value = _make_tenant(status=TenantStatus.SUSPENDED)
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/t-100/suspend")
        assert resp.status_code == 200

    def test_suspend_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.suspend_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/missing/suspend")
        assert resp.status_code == 404

    def test_suspend_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.suspend_tenant.side_effect = RuntimeError("fail")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/t1/suspend")
        assert resp.status_code == 500


class TestDeactivateTenantEndpoint:
    """Test POST /api/v1/tenants/{tenant_id}/deactivate."""

    def test_deactivate_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.deactivate_tenant.return_value = _make_tenant(status=TenantStatus.DEACTIVATED)
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/t-100/deactivate")
        assert resp.status_code == 200

    def test_deactivate_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.deactivate_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/missing/deactivate")
        assert resp.status_code == 404

    def test_deactivate_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.deactivate_tenant.side_effect = ValueError("cannot deactivate")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/v1/tenants/t1/deactivate")
        assert resp.status_code == 500


class TestUpdateQuotaEndpoint:
    """Test PUT /api/v1/tenants/{tenant_id}/quota."""

    def test_update_quota_success(self):
        mock_mgr = AsyncMock()
        tenant = _make_tenant()
        mock_mgr.get_tenant.return_value = tenant
        mock_mgr.update_quota.return_value = tenant
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.put("/api/v1/tenants/t-100/quota", json={"max_agents": 200})
        assert resp.status_code == 200

    def test_update_quota_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.put("/api/v1/tenants/missing/quota", json={"max_agents": 200})
        assert resp.status_code == 404

    def test_update_quota_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.side_effect = RuntimeError("db")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.put("/api/v1/tenants/t1/quota", json={"max_agents": 200})
        assert resp.status_code == 500


class TestCheckQuotaEndpoint:
    """Test POST /api/v1/tenants/{tenant_id}/quota/check."""

    def test_check_quota_available(self):
        mock_mgr = AsyncMock()
        mock_mgr.check_quota.return_value = True
        mock_mgr.get_tenant.return_value = _make_tenant()
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants/t-100/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    def test_check_quota_tenant_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.check_quota.return_value = True
        mock_mgr.get_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants/missing/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 404

    def test_check_quota_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.check_quota.side_effect = RuntimeError("fail")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants/t1/quota/check",
            json={"resource": "agents", "requested_amount": 1},
        )
        assert resp.status_code == 500


class TestGetUsageEndpoint:
    """Test GET /api/v1/tenants/{tenant_id}/usage."""

    def test_get_usage_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = _make_tenant()
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t-100/usage")
        assert resp.status_code == 200

    def test_get_usage_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = None
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/missing/usage")
        assert resp.status_code == 404

    def test_get_usage_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.side_effect = RuntimeError("oops")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t1/usage")
        assert resp.status_code == 500


class TestIncrementUsageEndpoint:
    """Test POST /api/v1/tenants/{tenant_id}/usage/increment."""

    def test_increment_success(self):
        mock_mgr = AsyncMock()
        mock_mgr.increment_usage.return_value = {"agents_count": 5}
        mock_mgr.get_tenant.return_value = _make_tenant()
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants/t-100/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 200

    def test_increment_quota_exceeded(self):
        mock_mgr = AsyncMock()
        mock_mgr.increment_usage.side_effect = TenantQuotaExceededError(
            "exceeded", tenant_id="t1", resource="agents", current=100, limit=100
        )
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants/t1/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 429

    def test_increment_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.increment_usage.side_effect = TenantNotFoundError("nope", tenant_id="x")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants/x/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 404

    def test_increment_runtime_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.increment_usage.side_effect = RuntimeError("boom")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/tenants/t1/usage/increment",
            json={"resource": "agents", "amount": 1},
        )
        assert resp.status_code == 500


class TestHierarchyEndpoint:
    """Test GET /api/v1/tenants/{tenant_id}/hierarchy."""

    def test_hierarchy_success(self):
        mock_mgr = AsyncMock()
        t = _make_tenant()
        mock_mgr.get_tenant_hierarchy.return_value = [t]
        mock_mgr.get_all_descendants.return_value = []
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t-100/hierarchy")
        assert resp.status_code == 200

    def test_hierarchy_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant_hierarchy.side_effect = TenantNotFoundError("nope", tenant_id="x")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/x/hierarchy")
        assert resp.status_code == 404

    def test_hierarchy_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant_hierarchy.side_effect = RuntimeError("fail")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t1/hierarchy")
        assert resp.status_code == 500


class TestChildTenantsEndpoint:
    """Test GET /api/v1/tenants/{tenant_id}/children."""

    def test_children_success(self):
        mock_mgr = AsyncMock()
        child = _make_tenant(tenant_id="c1", slug="ch-1d")
        mock_mgr.get_child_tenants.return_value = [child]
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t-100/children")
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 1

    def test_children_not_found(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_child_tenants.side_effect = TenantNotFoundError("nope", tenant_id="x")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/x/children")
        assert resp.status_code == 404

    def test_children_error(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_child_tenants.side_effect = RuntimeError("db")
        app = _build_app(mock_mgr)
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/t1/children")
        assert resp.status_code == 500


class TestCrossTenantScopeEndpoint:
    """Test cross-tenant scope enforcement via API."""

    def test_uuid_admin_blocked_cross_tenant(self):
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = _make_tenant()
        app = _build_app(mock_mgr, admin_id="550e8400-e29b-41d4-a716-446655440000")
        client = TestClient(app)
        resp = client.get("/api/v1/tenants/different-tenant-id")
        assert resp.status_code == 403

    def test_uuid_admin_self_access_allowed(self):
        tid = "550e8400-e29b-41d4-a716-446655440000"
        mock_mgr = AsyncMock()
        mock_mgr.get_tenant.return_value = _make_tenant(tenant_id=tid, slug="se-lf")
        app = _build_app(mock_mgr, admin_id=tid)
        client = TestClient(app)
        resp = client.get(f"/api/v1/tenants/{tid}")
        assert resp.status_code == 200
