"""Tests for TieredCacheManager.

Covers initialization, sync get, async get/set/delete/exists,
L1/L2/L3 tier logic, degraded mode, serialization, stats, and cleanup.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shared.cache.models import CacheTier, TieredCacheConfig, TieredCacheStats


# ---------------------------------------------------------------------------
# Patch heavy externals before importing the module under test
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _patch_metrics():
    """Stub out all Prometheus metric helpers so tests don't need a registry."""
    noop = lambda *a, **kw: None  # noqa: E731
    patches = [
        patch("src.core.shared.cache.manager.record_cache_hit", noop),
        patch("src.core.shared.cache.manager.record_cache_miss", noop),
        patch("src.core.shared.cache.manager.record_cache_latency", noop),
        patch("src.core.shared.cache.manager.record_fallback", noop),
        patch("src.core.shared.cache.manager.record_promotion", noop),
        patch("src.core.shared.cache.manager.set_tier_health", noop),
        patch("src.core.shared.cache.manager.update_cache_size", noop),
        patch("src.core.shared.cache.manager.TIERED_CACHE_REDIS_FAILURES", MagicMock()),
        patch("src.core.shared.cache.manager.TIERED_CACHE_DEGRADED", MagicMock()),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


from src.core.shared.cache.manager import TieredCacheManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> TieredCacheConfig:
    defaults = {
        "l1_maxsize": 64,
        "l1_ttl": 60,
        "l2_ttl": 300,
        "l3_ttl": 600,
        "l3_enabled": True,
        "promotion_threshold": 10,
        "serialize": True,
    }
    defaults.update(overrides)
    return TieredCacheConfig(**defaults)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_config(self):
        mgr = TieredCacheManager(name="t1")
        assert mgr.name == "t1"
        assert mgr.config is not None

    def test_l1_ttl_clamped_to_l2(self):
        cfg = _make_config(l1_ttl=9999, l2_ttl=100)
        mgr = TieredCacheManager(config=cfg, name="clamp")
        assert mgr.config.l1_ttl <= mgr.config.l2_ttl

    def test_custom_name(self):
        mgr = TieredCacheManager(name="custom")
        assert mgr.name == "custom"


# ---------------------------------------------------------------------------
# Synchronous get (L1 + L3 only)
# ---------------------------------------------------------------------------


class TestSyncGet:
    def test_get_returns_default_on_miss(self):
        mgr = TieredCacheManager(config=_make_config(), name="sync")
        assert mgr.get("missing") is None
        assert mgr.get("missing", default="fallback") == "fallback"

    def test_get_from_l1(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="sync-l1")
        mgr._l1_cache.set("k1", "hello")
        assert mgr.get("k1") == "hello"

    def test_get_from_l3(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="sync-l3")
        mgr._l3_cache["k2"] = {"data": "world", "timestamp": time.time()}
        assert mgr.get("k2") == "world"

    def test_get_l3_expired(self):
        mgr = TieredCacheManager(config=_make_config(l3_ttl=1, serialize=False), name="exp")
        mgr._l3_cache["k3"] = {"data": "old", "timestamp": time.time() - 100}
        assert mgr.get("k3") is None

    def test_get_l3_disabled(self):
        mgr = TieredCacheManager(config=_make_config(l3_enabled=False, serialize=False), name="no3")
        assert mgr.get("nope") is None


# ---------------------------------------------------------------------------
# Async get
# ---------------------------------------------------------------------------


class TestAsyncGet:
    @pytest.mark.asyncio
    async def test_get_async_l1_hit(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="ag")
        mgr._l1_cache.set("a", 42)
        result = await mgr.get_async("a")
        assert result == 42

    @pytest.mark.asyncio
    async def test_get_async_l2_hit(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="ag2")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(
            return_value=json.dumps({"data": "from-redis", "timestamp": time.time()})
        )
        mgr._l2_client = mock_redis
        mgr._l2_degraded = False

        result = await mgr.get_async("b")
        assert result == "from-redis"

    @pytest.mark.asyncio
    async def test_get_async_l2_degraded_skips(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="ag3")
        mgr._l2_client = AsyncMock()
        mgr._l2_degraded = True
        mgr._last_l2_failure = time.time()  # recent failure

        result = await mgr.get_async("c")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_async_falls_to_l3(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="ag4")
        mgr._l3_cache["d"] = {"data": "l3val", "timestamp": time.time()}
        result = await mgr.get_async("d")
        assert result == "l3val"

    @pytest.mark.asyncio
    async def test_get_async_default(self):
        mgr = TieredCacheManager(config=_make_config(), name="ag5")
        result = await mgr.get_async("none", default="def")
        assert result == "def"


# ---------------------------------------------------------------------------
# Async set
# ---------------------------------------------------------------------------


class TestAsyncSet:
    @pytest.mark.asyncio
    async def test_set_to_l1(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="s1")
        await mgr.set("k", "v", tier=CacheTier.L1)
        assert mgr._l1_cache.get("k") == "v"

    @pytest.mark.asyncio
    async def test_set_to_l3(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="s3")
        await mgr.set("k", "v", tier=CacheTier.L3)
        assert "k" in mgr._l3_cache

    @pytest.mark.asyncio
    async def test_set_to_l2_with_redis(self):
        mgr = TieredCacheManager(config=_make_config(), name="s2")
        mock_redis = AsyncMock()
        mgr._l2_client = mock_redis
        mgr._l2_degraded = False
        await mgr.set("k", "v", tier=CacheTier.L2)
        mock_redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_default_falls_to_l3_when_no_redis(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="s4")
        # No L2 client, so default set should fall through to L3
        await mgr.set("k", "v")
        assert "k" in mgr._l3_cache

    @pytest.mark.asyncio
    async def test_set_l2_failure_falls_to_l3(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="s5")
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=ConnectionError("gone"))
        mgr._l2_client = mock_redis
        mgr._l2_degraded = False
        await mgr.set("k", "v", tier=CacheTier.L2)
        assert "k" in mgr._l3_cache
        assert mgr._l2_degraded is True


# ---------------------------------------------------------------------------
# Delete / Exists
# ---------------------------------------------------------------------------


class TestDeleteExists:
    @pytest.mark.asyncio
    async def test_delete_from_l1(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="d1")
        mgr._l1_cache.set("x", 1)
        assert await mgr.delete("x") is True

    @pytest.mark.asyncio
    async def test_delete_from_l3(self):
        mgr = TieredCacheManager(config=_make_config(), name="d2")
        mgr._l3_cache["y"] = {"data": 1, "timestamp": time.time()}
        assert await mgr.delete("y") is True
        assert "y" not in mgr._l3_cache

    @pytest.mark.asyncio
    async def test_delete_missing_returns_false(self):
        mgr = TieredCacheManager(config=_make_config(), name="d3")
        assert await mgr.delete("ghost") is False

    @pytest.mark.asyncio
    async def test_exists_l1(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="e1")
        mgr._l1_cache.set("e", 1)
        assert await mgr.exists("e") is True

    @pytest.mark.asyncio
    async def test_exists_l3(self):
        mgr = TieredCacheManager(config=_make_config(), name="e2")
        mgr._l3_cache["f"] = {"data": 1, "timestamp": time.time()}
        assert await mgr.exists("f") is True

    @pytest.mark.asyncio
    async def test_exists_missing(self):
        mgr = TieredCacheManager(config=_make_config(), name="e3")
        assert await mgr.exists("nope") is False


# ---------------------------------------------------------------------------
# Degraded mode / health callback
# ---------------------------------------------------------------------------


class TestDegradedMode:
    def test_handle_l2_failure_sets_degraded(self):
        mgr = TieredCacheManager(config=_make_config(), name="deg")
        mgr._handle_l2_failure()
        assert mgr._l2_degraded is True
        assert mgr._stats.redis_failures == 1

    def test_on_redis_health_change_unhealthy(self):
        from src.core.shared.redis_config import RedisHealthState

        mgr = TieredCacheManager(config=_make_config(), name="hc")
        mgr._on_redis_health_change(RedisHealthState.HEALTHY, RedisHealthState.UNHEALTHY)
        assert mgr._l2_degraded is True

    def test_on_redis_health_change_recovery(self):
        from src.core.shared.redis_config import RedisHealthState

        mgr = TieredCacheManager(config=_make_config(), name="hc2")
        mgr._l2_degraded = True
        mgr._on_redis_health_change(RedisHealthState.UNHEALTHY, RedisHealthState.HEALTHY)
        assert mgr._l2_degraded is False


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_serialize_dict(self):
        mgr = TieredCacheManager(config=_make_config(serialize=True), name="ser")
        result = mgr._serialize({"a": 1})
        assert isinstance(result, str)
        assert json.loads(result) == {"a": 1}

    def test_serialize_string_passthrough(self):
        mgr = TieredCacheManager(config=_make_config(serialize=True), name="ser2")
        assert mgr._serialize("hello") == "hello"

    def test_deserialize_json_string(self):
        mgr = TieredCacheManager(config=_make_config(serialize=True), name="des")
        assert mgr._deserialize('{"a": 1}') == {"a": 1}

    def test_deserialize_non_json_string(self):
        mgr = TieredCacheManager(config=_make_config(serialize=True), name="des2")
        assert mgr._deserialize("not-json{") == "not-json{"

    def test_serialize_disabled(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="nos")
        data = {"x": 1}
        assert mgr._serialize(data) is data
        assert mgr._deserialize(data) is data


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_get_stats_structure(self):
        mgr = TieredCacheManager(config=_make_config(), name="stats")
        stats = mgr.get_stats()
        assert stats["name"] == "stats"
        assert "tiers" in stats
        assert "l1" in stats["tiers"]
        assert "l2" in stats["tiers"]
        assert "l3" in stats["tiers"]
        assert "aggregate" in stats

    def test_stats_track_hits(self):
        mgr = TieredCacheManager(config=_make_config(serialize=False), name="sh")
        mgr._l1_cache.set("h", "val")
        mgr.get("h")
        stats = mgr.get_stats()
        assert stats["tiers"]["l1"]["hits"] >= 1


# ---------------------------------------------------------------------------
# Initialize / Close
# ---------------------------------------------------------------------------


class TestInitializeClose:
    @pytest.mark.asyncio
    async def test_initialize_without_redis(self):
        mgr = TieredCacheManager(config=_make_config(), name="init")
        with patch("src.core.shared.cache.manager.aioredis", None):
            result = await mgr.initialize()
        # Without aioredis the L2 init returns False
        assert result is False
        assert mgr._l2_degraded is True

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        mgr = TieredCacheManager(config=_make_config(), name="cls")
        await mgr.close()  # should not raise

    @pytest.mark.asyncio
    async def test_close_with_client(self):
        mgr = TieredCacheManager(config=_make_config(), name="cls2")
        mock_client = AsyncMock()
        mgr._l2_client = mock_client
        await mgr.close()
        assert mgr._l2_client is None


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_old_records(self):
        mgr = TieredCacheManager(config=_make_config(), name="clean")
        from src.core.shared.cache.models import AccessRecord

        old = AccessRecord(key="old")
        old.last_access = time.time() - 7200  # 2 hours ago
        mgr._access_records["old"] = old
        mgr._cleanup_old_records()
        assert "old" not in mgr._access_records

    def test_cleanup_old_l3_entries(self):
        mgr = TieredCacheManager(config=_make_config(), name="clean2")
        mgr._l3_cache["stale"] = {"data": "x", "timestamp": time.time() - 7200}
        mgr._cleanup_old_records()
        assert "stale" not in mgr._l3_cache


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


class TestPromotion:
    def test_should_promote_returns_false_for_new_key(self):
        mgr = TieredCacheManager(config=_make_config(), name="promo")
        assert mgr._should_promote_to_l1("new") is False

    def test_check_and_promote_tier_only(self):
        mgr = TieredCacheManager(config=_make_config(promotion_threshold=1), name="promo2")
        from src.core.shared.cache.models import AccessRecord

        rec = AccessRecord(key="hot")
        rec.access_times = [time.time()] * 5
        rec.current_tier = CacheTier.L3
        mgr._access_records["hot"] = rec
        mgr._check_and_promote_tier_only("hot")
        assert mgr._access_records["hot"].current_tier == CacheTier.L1
        assert mgr._stats.promotions >= 1
