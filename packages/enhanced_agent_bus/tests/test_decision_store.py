"""Tests for enhanced_agent_bus.decision_store module.

Covers DecisionStore CRUD operations, memory fallback, metrics,
health checks, key generation, singleton management, and error paths.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.decision_store import (
    DEFAULT_KEY_PREFIX,
    DEFAULT_TTL_SECONDS,
    DecisionStore,
    get_decision_store,
    reset_decision_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_explanation(
    decision_id: str = "dec-001",
    tenant_id: str | None = "tenant-a",
    message_id: str | None = "msg-001",
    verdict: str = "ALLOW",
    confidence: float = 0.9,
) -> MagicMock:
    """Create a mock DecisionExplanationV1-like object."""
    exp = MagicMock()
    exp.decision_id = decision_id
    exp.tenant_id = tenant_id
    exp.message_id = message_id
    exp.verdict = verdict
    exp.confidence_score = confidence
    exp.model_dump_json.return_value = json.dumps(
        {
            "decision_id": decision_id,
            "tenant_id": tenant_id,
            "message_id": message_id,
            "verdict": verdict,
            "confidence_score": confidence,
        }
    )
    return exp


def _memory_store(**overrides) -> DecisionStore:
    """Create a DecisionStore pre-configured for memory fallback."""
    store = DecisionStore(**overrides)
    store._initialized = True
    store._use_memory_fallback = True
    return store


# ---------------------------------------------------------------------------
# Key Generation
# ---------------------------------------------------------------------------


class TestKeyGeneration:
    def test_make_key_normal(self):
        store = DecisionStore()
        key = store._make_key("tenant-a", "dec-001")
        assert key == f"{DEFAULT_KEY_PREFIX}:tenant-a:dec-001"

    def test_make_key_colon_in_tenant(self):
        store = DecisionStore()
        key = store._make_key("ns:tenant", "dec-001")
        assert ":" not in key.split(":", 2)[2].rsplit(":", 1)[0]
        assert "ns_tenant" in key

    def test_make_key_empty_tenant(self):
        store = DecisionStore()
        key = store._make_key("", "dec-001")
        assert "default" in key

    def test_make_key_none_tenant(self):
        store = DecisionStore()
        key = store._make_key(None, "dec-001")
        assert "default" in key

    def test_make_message_index_key(self):
        store = DecisionStore()
        key = store._make_message_index_key("t1", "msg-1")
        assert key.startswith(store._index_prefix)
        assert "msg" in key
        assert "msg-1" in key

    def test_make_time_index_key(self):
        store = DecisionStore()
        key = store._make_time_index_key("t1", "2024-01-01")
        assert "time" in key
        assert "2024-01-01" in key


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        store = _memory_store()
        result = await store.initialize()
        assert result is True

    @pytest.mark.asyncio
    async def test_initialize_redis_not_available(self):
        store = DecisionStore()
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            result = await store.initialize()
        assert result is True
        assert store._use_memory_fallback is True
        assert store._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_redis_healthy(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": True}
        store = DecisionStore(redis_pool=mock_pool)
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True):
            result = await store.initialize()
        assert result is True
        assert store._use_memory_fallback is False

    @pytest.mark.asyncio
    async def test_initialize_redis_unhealthy_falls_back(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": False, "error": "down"}
        store = DecisionStore(redis_pool=mock_pool)
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True):
            result = await store.initialize()
        assert result is True
        assert store._use_memory_fallback is True

    @pytest.mark.asyncio
    async def test_initialize_creates_pool_when_none(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": True}
        with (
            patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.decision_store.get_shared_pool",
                return_value=mock_pool,
            ) as mock_get,
        ):
            store = DecisionStore()
            result = await store.initialize()
        assert result is True
        mock_get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_connection_error_falls_back(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.side_effect = ConnectionError("refused")
        store = DecisionStore(redis_pool=mock_pool)
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True):
            result = await store.initialize()
        assert result is True
        assert store._use_memory_fallback is True


# ---------------------------------------------------------------------------
# Store (memory fallback)
# ---------------------------------------------------------------------------


class TestStoreMemory:
    @pytest.mark.asyncio
    async def test_store_success(self):
        store = _memory_store()
        exp = _make_explanation()
        result = await store.store(exp)
        assert result is True
        assert store._metrics["total_stores"] == 1

    @pytest.mark.asyncio
    async def test_store_creates_message_index(self):
        store = _memory_store()
        exp = _make_explanation(message_id="msg-42")
        await store.store(exp)
        msg_key = store._make_message_index_key("tenant-a", "msg-42")
        assert msg_key in store._memory_indexes
        assert store._memory_indexes[msg_key] == "dec-001"

    @pytest.mark.asyncio
    async def test_store_no_message_id_skips_index(self):
        store = _memory_store()
        exp = _make_explanation(message_id=None)
        await store.store(exp)
        assert len(store._memory_indexes) == 0

    @pytest.mark.asyncio
    async def test_store_with_custom_ttl(self):
        store = _memory_store()
        exp = _make_explanation()
        result = await store.store(exp, ttl_seconds=60)
        assert result is True

    @pytest.mark.asyncio
    async def test_store_serialization_error(self):
        store = _memory_store()
        exp = _make_explanation()
        exp.model_dump_json.side_effect = TypeError("not serializable")
        result = await store.store(exp)
        assert result is False
        assert store._metrics["failed_operations"] == 1

    @pytest.mark.asyncio
    async def test_store_auto_initializes(self):
        """Store should call initialize if not yet initialized."""
        store = DecisionStore()
        store._use_memory_fallback = True
        with patch.object(
            store, "initialize", new_callable=AsyncMock, return_value=True
        ) as mock_init:
            # After initialize, we need the store to be marked initialized
            async def init_side_effect():
                store._initialized = True
                return True

            mock_init.side_effect = init_side_effect
            exp = _make_explanation()
            result = await store.store(exp)
        assert result is True
        mock_init.assert_awaited_once()


# ---------------------------------------------------------------------------
# Get (memory fallback)
# ---------------------------------------------------------------------------


class TestGetMemory:
    @pytest.mark.asyncio
    async def test_get_existing(self):
        store = _memory_store()
        exp = _make_explanation()
        await store.store(exp)

        # DecisionExplanationV1 may be None in test env, so it returns parsed dict
        result = await store.get("dec-001", "tenant-a")
        assert result is not None
        assert store._metrics["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_get_missing(self):
        store = _memory_store()
        result = await store.get("nonexistent", "tenant-a")
        assert result is None
        assert store._metrics["cache_misses"] == 1

    @pytest.mark.asyncio
    async def test_get_tracks_latency(self):
        store = _memory_store()
        await store.get("any", "tenant-a")
        assert store._metrics["total_retrievals"] == 1
        assert store._metrics["total_latency_ms"] > 0.0


# ---------------------------------------------------------------------------
# Get by message ID (memory fallback)
# ---------------------------------------------------------------------------


class TestGetByMessageId:
    @pytest.mark.asyncio
    async def test_found(self):
        store = _memory_store()
        exp = _make_explanation(decision_id="d1", message_id="m1", tenant_id="t1")
        await store.store(exp)
        result = await store.get_by_message_id("m1", "t1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_not_found(self):
        store = _memory_store()
        result = await store.get_by_message_id("no-such-msg")
        assert result is None

    @pytest.mark.asyncio
    async def test_error_path(self):
        store = _memory_store()
        # Force an error by making the index lookup raise
        with patch.object(store, "_make_message_index_key", side_effect=ValueError("bad")):
            result = await store.get_by_message_id("m1")
        assert result is None
        assert store._metrics["failed_operations"] == 1


# ---------------------------------------------------------------------------
# Delete (memory fallback)
# ---------------------------------------------------------------------------


class TestDeleteMemory:
    @pytest.mark.asyncio
    async def test_delete_existing(self):
        store = _memory_store()
        exp = _make_explanation(decision_id="d1", message_id="m1", tenant_id="t1")
        await store.store(exp)
        result = await store.delete("d1", "t1")
        assert result is True
        assert store._metrics["total_deletes"] == 1
        # Verify key removed
        key = store._make_key("t1", "d1")
        assert key not in store._memory_store

    @pytest.mark.asyncio
    async def test_delete_removes_message_index(self):
        store = _memory_store()
        exp = _make_explanation(decision_id="d1", message_id="m1", tenant_id="t1")
        await store.store(exp)
        msg_key = store._make_message_index_key("t1", "m1")
        assert msg_key in store._memory_indexes
        await store.delete("d1", "t1")
        assert msg_key not in store._memory_indexes

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        store = _memory_store()
        result = await store.delete("nope", "t1")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_error_path(self):
        store = _memory_store()
        # Put a value so the key exists and delete enters cleanup logic
        key = store._make_key("default", "d1")
        store._memory_store[key] = "data"
        # Replace _memory_indexes with a mock that raises during iteration
        mock_idx = MagicMock()
        mock_idx.items.side_effect = RuntimeError("fail")
        store._memory_indexes = mock_idx
        result = await store.delete("d1")
        assert result is False
        assert store._metrics["failed_operations"] == 1


# ---------------------------------------------------------------------------
# List decisions (memory fallback)
# ---------------------------------------------------------------------------


class TestListDecisions:
    @pytest.mark.asyncio
    async def test_list_empty(self):
        store = _memory_store()
        result = await store.list_decisions("t1")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_returns_decision_ids(self):
        store = _memory_store()
        for i in range(5):
            exp = _make_explanation(decision_id=f"d{i}", tenant_id="t1")
            await store.store(exp)
        result = await store.list_decisions("t1")
        assert len(result) == 5
        for r in result:
            assert r.startswith("d")

    @pytest.mark.asyncio
    async def test_list_respects_limit(self):
        store = _memory_store()
        for i in range(10):
            exp = _make_explanation(decision_id=f"d{i}", tenant_id="t1")
            await store.store(exp)
        result = await store.list_decisions("t1", limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_respects_offset(self):
        store = _memory_store()
        for i in range(5):
            exp = _make_explanation(decision_id=f"d{i}", tenant_id="t1")
            await store.store(exp)
        all_ids = await store.list_decisions("t1")
        offset_ids = await store.list_decisions("t1", offset=2)
        assert len(offset_ids) == 3
        assert offset_ids == all_ids[2:]

    @pytest.mark.asyncio
    async def test_list_error_path(self):
        store = _memory_store()
        with patch.object(store, "_make_key", side_effect=RuntimeError("fail")):
            result = await store.list_decisions("t1")
        assert result == []


# ---------------------------------------------------------------------------
# Exists (memory fallback)
# ---------------------------------------------------------------------------


class TestExists:
    @pytest.mark.asyncio
    async def test_exists_true(self):
        store = _memory_store()
        exp = _make_explanation(decision_id="d1", tenant_id="t1")
        await store.store(exp)
        assert await store.exists("d1", "t1") is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        store = _memory_store()
        assert await store.exists("nope", "t1") is False

    @pytest.mark.asyncio
    async def test_exists_error_path(self):
        store = _memory_store()
        # Patch _memory_store.__contains__ to raise inside try block
        orig_store = store._memory_store
        store._memory_store = MagicMock()
        store._memory_store.__contains__ = MagicMock(side_effect=OSError("disk"))
        result = await store.exists("d1")
        assert result is False
        assert store._metrics["failed_operations"] == 1
        store._memory_store = orig_store


# ---------------------------------------------------------------------------
# TTL operations (memory fallback)
# ---------------------------------------------------------------------------


class TestTTL:
    @pytest.mark.asyncio
    async def test_get_ttl_existing(self):
        store = _memory_store()
        exp = _make_explanation(decision_id="d1", tenant_id="t1")
        await store.store(exp)
        ttl = await store.get_ttl("d1", "t1")
        assert ttl == DEFAULT_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_get_ttl_nonexistent(self):
        store = _memory_store()
        ttl = await store.get_ttl("nope", "t1")
        assert ttl == -2

    @pytest.mark.asyncio
    async def test_get_ttl_error_path(self):
        store = _memory_store()
        store._memory_store = MagicMock()
        store._memory_store.__contains__ = MagicMock(side_effect=ValueError("bad"))
        ttl = await store.get_ttl("d1")
        assert ttl == -2

    @pytest.mark.asyncio
    async def test_extend_ttl_existing(self):
        store = _memory_store()
        exp = _make_explanation(decision_id="d1", tenant_id="t1")
        await store.store(exp)
        result = await store.extend_ttl("d1", "t1")
        assert result is True

    @pytest.mark.asyncio
    async def test_extend_ttl_nonexistent(self):
        store = _memory_store()
        result = await store.extend_ttl("nope", "t1")
        assert result is False

    @pytest.mark.asyncio
    async def test_extend_ttl_error_path(self):
        store = _memory_store()
        store._memory_store = MagicMock()
        store._memory_store.__contains__ = MagicMock(side_effect=RuntimeError("fail"))
        result = await store.extend_ttl("d1")
        assert result is False


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_initial_metrics(self):
        store = DecisionStore()
        m = store.get_metrics()
        assert m["total_stores"] == 0
        assert m["cache_hit_rate"] == 0.0
        assert m["avg_latency_ms"] == 0.0
        assert "constitutional_hash" in m

    @pytest.mark.asyncio
    async def test_metrics_after_operations(self):
        store = _memory_store()
        exp = _make_explanation()
        await store.store(exp)
        await store.get("dec-001", "tenant-a")

        m = store.get_metrics()
        assert m["total_stores"] == 1
        assert m["total_retrievals"] == 1
        assert m["cache_hits"] == 1
        assert m["cache_hit_rate"] == 100.0
        assert m["avg_latency_ms"] > 0.0

    @pytest.mark.asyncio
    async def test_metrics_cache_miss(self):
        store = _memory_store()
        await store.get("missing", "t1")
        m = store.get_metrics()
        assert m["cache_misses"] == 1
        assert m["cache_hit_rate"] == 0.0


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_memory_fallback(self):
        store = _memory_store()
        h = await store.health_check()
        assert h["healthy"] is True
        assert h["using_memory_fallback"] is True
        assert "constitutional_hash" in h
        assert "timestamp" in h

    @pytest.mark.asyncio
    async def test_health_with_redis_pool(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": True}
        store = DecisionStore(redis_pool=mock_pool)
        store._initialized = True
        store._use_memory_fallback = False
        h = await store.health_check()
        assert h["redis_healthy"] is True

    @pytest.mark.asyncio
    async def test_health_redis_unhealthy(self):
        mock_pool = AsyncMock()
        mock_pool.health_check.return_value = {"healthy": False, "error": "timeout"}
        store = DecisionStore(redis_pool=mock_pool)
        store._initialized = True
        store._use_memory_fallback = False
        h = await store.health_check()
        assert h["redis_healthy"] is False
        assert h["redis_error"] == "timeout"


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_close_clears_state(self):
        store = _memory_store()
        exp = _make_explanation()
        await store.store(exp)
        assert len(store._memory_store) > 0

        await store.close()
        assert store._initialized is False
        assert len(store._memory_store) == 0
        assert len(store._memory_indexes) == 0


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_defaults(self):
        store = DecisionStore()
        assert store._ttl_seconds == DEFAULT_TTL_SECONDS
        assert store._key_prefix == DEFAULT_KEY_PREFIX
        assert store._initialized is False
        assert store._use_memory_fallback is False

    def test_custom_params(self):
        store = DecisionStore(
            redis_url="redis://custom:1234",
            ttl_seconds=60,
            key_prefix="custom:key",
            index_prefix="custom:idx",
            enable_metrics=False,
        )
        assert store._ttl_seconds == 60
        assert store._key_prefix == "custom:key"
        assert store._index_prefix == "custom:idx"
        assert store._enable_metrics is False


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------


class TestSingleton:
    @pytest.mark.asyncio
    async def test_get_decision_store_creates_singleton(self):
        await reset_decision_store()
        with (
            patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False),
        ):
            store = await get_decision_store()
            assert store._initialized is True
            # Second call returns same instance
            store2 = await get_decision_store()
            assert store is store2
        await reset_decision_store()

    @pytest.mark.asyncio
    async def test_reset_decision_store(self):
        await reset_decision_store()
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            store = await get_decision_store()
            assert store._initialized is True
        await reset_decision_store()
        # After reset, the global should be None -- verify by getting a new one
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            store2 = await get_decision_store()
            assert store2 is not store
        await reset_decision_store()
