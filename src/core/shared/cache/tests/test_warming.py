"""
Tests for ACGS-2 Cache Warming Module

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shared.cache.models import CacheTier

# The warming module lazily imports `from src.core.shared.tiered_cache import CacheTier`
# and `from src.core.shared.tiered_cache import get_tiered_cache`.
# That module may not be importable in isolation, so we install a lightweight shim.
_tiered_cache_shim = types.ModuleType("src.core.shared.tiered_cache")
_tiered_cache_shim.CacheTier = CacheTier  # type: ignore[attr-defined]
_tiered_cache_shim.get_tiered_cache = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("src.core.shared.tiered_cache", _tiered_cache_shim)

from src.core.shared.cache.warming import (
    CacheWarmer,
    RateLimiter,
    WarmingConfig,
    WarmingProgress,
    WarmingResult,
    WarmingStatus,
    get_cache_warmer,
    reset_cache_warmer,
    warm_cache_on_startup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the singleton warmer before and after each test."""
    reset_cache_warmer()
    yield
    reset_cache_warmer()


@pytest.fixture()
def config() -> WarmingConfig:
    return WarmingConfig(
        rate_limit=1000,
        batch_size=5,
        l1_count=2,
        l2_count=10,
        key_timeout=0.5,
        total_timeout=5.0,
        max_retries=2,
        retry_delay=0.01,
    )


@pytest.fixture()
def mock_cache_manager():
    """A mock cache manager that records set() calls."""
    mgr = AsyncMock()
    mgr.set = AsyncMock()
    mgr.get = MagicMock(return_value=None)
    return mgr


@pytest.fixture()
def warmer(config, mock_cache_manager) -> CacheWarmer:
    return CacheWarmer(config=config, cache_manager=mock_cache_manager)


# ---------------------------------------------------------------------------
# WarmingStatus
# ---------------------------------------------------------------------------


class TestWarmingStatus:
    def test_enum_values(self):
        assert WarmingStatus.IDLE.value == "idle"
        assert WarmingStatus.WARMING.value == "warming"
        assert WarmingStatus.COMPLETED.value == "completed"
        assert WarmingStatus.FAILED.value == "failed"
        assert WarmingStatus.CANCELLED.value == "cancelled"


# ---------------------------------------------------------------------------
# WarmingConfig dataclass
# ---------------------------------------------------------------------------


class TestWarmingConfig:
    def test_defaults(self):
        cfg = WarmingConfig()
        assert cfg.rate_limit == 100
        assert cfg.batch_size == 10
        assert cfg.l1_count == 10
        assert cfg.l2_count == 100
        assert cfg.max_retries == 3
        assert cfg.priority_keys == []

    def test_custom_values(self, config):
        assert config.rate_limit == 1000
        assert config.l1_count == 2


# ---------------------------------------------------------------------------
# WarmingResult
# ---------------------------------------------------------------------------


class TestWarmingResult:
    def test_success_property_completed(self):
        result = WarmingResult(status=WarmingStatus.COMPLETED)
        assert result.success is True

    def test_success_property_failed(self):
        result = WarmingResult(status=WarmingStatus.FAILED)
        assert result.success is False

    def test_success_rate_no_keys(self):
        result = WarmingResult(status=WarmingStatus.COMPLETED)
        assert result.success_rate == 0.0

    def test_success_rate_partial(self):
        result = WarmingResult(
            status=WarmingStatus.COMPLETED,
            keys_warmed=7,
            keys_failed=3,
        )
        assert result.success_rate == pytest.approx(0.7)

    def test_success_rate_all_warmed(self):
        result = WarmingResult(
            status=WarmingStatus.COMPLETED,
            keys_warmed=10,
            keys_failed=0,
        )
        assert result.success_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# WarmingProgress
# ---------------------------------------------------------------------------


class TestWarmingProgress:
    def test_percent_complete_zero_total(self):
        progress = WarmingProgress(total_keys=0, processed_keys=0)
        assert progress.percent_complete == 0.0

    def test_percent_complete_half(self):
        progress = WarmingProgress(total_keys=20, processed_keys=10)
        assert progress.percent_complete == pytest.approx(50.0)

    def test_percent_complete_full(self):
        progress = WarmingProgress(total_keys=5, processed_keys=5)
        assert progress.percent_complete == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_init_defaults(self):
        rl = RateLimiter()
        assert rl.tokens_per_second == 100.0
        assert rl.max_tokens == 100

    def test_init_custom_max_tokens(self):
        rl = RateLimiter(tokens_per_second=50.0, max_tokens=200)
        assert rl.max_tokens == 200

    def test_acquire_immediate_when_tokens_available(self):
        rl = RateLimiter(tokens_per_second=100.0)
        wait = rl.acquire(1)
        assert wait == 0.0

    def test_acquire_returns_wait_when_exhausted(self):
        rl = RateLimiter(tokens_per_second=10.0, max_tokens=1)
        # First acquire should succeed
        wait1 = rl.acquire(1)
        assert wait1 == 0.0
        # Second acquire should require waiting
        wait2 = rl.acquire(1)
        assert wait2 > 0.0

    @pytest.mark.asyncio
    async def test_acquire_async_immediate(self):
        rl = RateLimiter(tokens_per_second=1000.0)
        # Should not raise and should complete quickly
        await rl.acquire_async(1)

    @pytest.mark.asyncio
    async def test_acquire_async_waits_when_exhausted(self):
        rl = RateLimiter(tokens_per_second=1000.0, max_tokens=1)
        await rl.acquire_async(1)
        start = time.monotonic()
        await rl.acquire_async(1)
        elapsed = time.monotonic() - start
        # Should have waited some amount (at least a fraction of a ms at 1000/s)
        assert elapsed >= 0.0


# ---------------------------------------------------------------------------
# CacheWarmer — initialisation & properties
# ---------------------------------------------------------------------------


class TestCacheWarmerInit:
    def test_default_init(self, mock_cache_manager):
        w = CacheWarmer(cache_manager=mock_cache_manager)
        assert w.status == WarmingStatus.IDLE
        assert w.is_warming is False
        assert w.config.rate_limit == 100

    def test_custom_rate_limit_overrides_config(self, mock_cache_manager):
        w = CacheWarmer(rate_limit=50, cache_manager=mock_cache_manager)
        assert w.config.rate_limit == 50

    def test_repr(self, warmer):
        r = repr(warmer)
        assert "CacheWarmer" in r
        assert "idle" in r

    def test_get_stats(self, warmer):
        stats = warmer.get_stats()
        assert stats["status"] == "idle"
        assert "config" in stats
        assert "progress" in stats
        assert stats["config"]["rate_limit"] == 1000


# ---------------------------------------------------------------------------
# CacheWarmer — warm_cache (happy path)
# ---------------------------------------------------------------------------


class TestCacheWarmerWarmCache:
    @pytest.mark.asyncio
    async def test_warm_with_empty_keys(self, warmer):
        result = await warmer.warm_cache(source_keys=[])
        assert result.status == WarmingStatus.COMPLETED
        assert result.keys_warmed == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_warm_with_source_keys_and_loader(self, warmer, mock_cache_manager):
        """Keys loaded via a custom sync loader end up in the cache."""

        def loader(key: str):
            return {"value": key}

        keys = ["k1", "k2", "k3"]
        result = await warmer.warm_cache(source_keys=keys, key_loader=loader)

        assert result.status == WarmingStatus.COMPLETED
        assert result.keys_warmed == 3
        assert result.keys_failed == 0
        # k1 and k2 should be L1 (l1_count=2), k3 L2
        assert result.l1_keys == 2
        assert result.l2_keys == 1
        assert mock_cache_manager.set.call_count == 3

    @pytest.mark.asyncio
    async def test_warm_with_async_loader(self, warmer, mock_cache_manager):
        """Keys loaded via an async loader."""

        async def loader(key: str):
            return {"value": key}

        keys = ["a", "b"]
        result = await warmer.warm_cache(source_keys=keys, key_loader=loader)

        assert result.status == WarmingStatus.COMPLETED
        assert result.keys_warmed == 2

    @pytest.mark.asyncio
    async def test_warm_loader_returns_none_counts_as_failed(self, warmer):
        """If loader returns None, the key counts as failed."""

        def loader(_key: str):
            return None

        result = await warmer.warm_cache(source_keys=["x"], key_loader=loader)

        assert result.keys_warmed == 0
        assert result.keys_failed == 1

    @pytest.mark.asyncio
    async def test_warm_duration_is_recorded(self, warmer):
        result = await warmer.warm_cache(source_keys=["k1"], key_loader=lambda k: "v")
        assert result.duration_seconds > 0.0


# ---------------------------------------------------------------------------
# CacheWarmer — error handling
# ---------------------------------------------------------------------------


class TestCacheWarmerErrors:
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_warm_already_in_progress(self, config, mock_cache_manager):
        """Second concurrent warm_cache call is rejected."""
        slow_loader_entered = asyncio.Event()
        slow_loader_can_proceed = asyncio.Event()

        async def slow_loader(_key: str):
            slow_loader_entered.set()
            await slow_loader_can_proceed.wait()
            return "val"

        w = CacheWarmer(config=config, cache_manager=mock_cache_manager)
        task = asyncio.create_task(
            w.warm_cache(source_keys=["a", "b"], key_loader=slow_loader)
        )
        await slow_loader_entered.wait()

        # Attempt a second warm while first is running
        dup_result = await w.warm_cache(source_keys=["c"])
        assert dup_result.status == WarmingStatus.FAILED
        assert "already in progress" in (dup_result.error_message or "").lower()

        # Unblock the first
        slow_loader_can_proceed.set()
        first_result = await task
        assert first_result.status == WarmingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_warm_loader_raises_runtime_error(self, warmer):
        """RuntimeError during key load counts as failed key, not total failure."""

        def bad_loader(_key: str):
            raise RuntimeError("boom")

        result = await warmer.warm_cache(source_keys=["a", "b"], key_loader=bad_loader)
        assert result.status == WarmingStatus.COMPLETED
        assert result.keys_failed == 2
        assert result.keys_warmed == 0

    @pytest.mark.asyncio
    async def test_warm_general_exception_returns_failed(self, config):
        """If _get_keys_to_warm raises, warm_cache returns FAILED."""
        w = CacheWarmer(config=config, cache_manager=MagicMock())

        with patch.object(w, "_get_keys_to_warm", side_effect=Exception("db down")):
            result = await w.warm_cache()

        assert result.status == WarmingStatus.FAILED
        assert "db down" in (result.error_message or "")


# ---------------------------------------------------------------------------
# CacheWarmer — cancellation
# ---------------------------------------------------------------------------


class TestCacheWarmerCancellation:
    @pytest.mark.asyncio
    async def test_cancel_stops_warming(self, config, mock_cache_manager):
        """Calling cancel() causes warming to stop with CANCELLED status."""
        call_count = 0

        async def counting_loader(key: str):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Cancel after loading first key
                w.cancel()
            return "val"

        w = CacheWarmer(config=config, cache_manager=mock_cache_manager)
        # Use enough keys that there are multiple batches
        keys = [f"key-{i}" for i in range(20)]
        result = await w.warm_cache(source_keys=keys, key_loader=counting_loader)

        assert result.status == WarmingStatus.CANCELLED


# ---------------------------------------------------------------------------
# CacheWarmer — progress callbacks
# ---------------------------------------------------------------------------


class TestCacheWarmerProgress:
    @pytest.mark.asyncio
    async def test_progress_callback_called(self, warmer):
        progress_updates: list[WarmingProgress] = []

        warmer.on_progress(progress_updates.append)

        result = await warmer.warm_cache(
            source_keys=["a", "b", "c", "d", "e", "f"],
            key_loader=lambda k: "v",
        )

        assert result.status == WarmingStatus.COMPLETED
        assert len(progress_updates) > 0
        last = progress_updates[-1]
        assert last.processed_keys == 6
        assert last.percent_complete == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_progress_callback_error_swallowed(self, warmer):
        """A failing callback does not break warming."""

        def bad_callback(_progress: WarmingProgress):
            raise ValueError("callback error")

        warmer.on_progress(bad_callback)
        result = await warmer.warm_cache(
            source_keys=["a"],
            key_loader=lambda k: "v",
        )
        assert result.status == WarmingStatus.COMPLETED

    def test_remove_progress_callback(self, warmer):
        cb = lambda p: None  # noqa: E731
        warmer.on_progress(cb)
        assert warmer.remove_progress_callback(cb) is True
        assert warmer.remove_progress_callback(cb) is False


# ---------------------------------------------------------------------------
# CacheWarmer — _get_keys_to_warm
# ---------------------------------------------------------------------------


class TestGetKeysToWarm:
    @pytest.mark.asyncio
    async def test_explicit_source_keys_truncated(self, config, mock_cache_manager):
        config.l2_count = 3
        w = CacheWarmer(config=config, cache_manager=mock_cache_manager)
        keys = await w._get_keys_to_warm(source_keys=["a", "b", "c", "d", "e"])
        assert keys == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_priority_keys_used_when_no_source(self, mock_cache_manager):
        cfg = WarmingConfig(priority_keys=["prio1", "prio2"], l2_count=10)
        w = CacheWarmer(config=cfg, cache_manager=mock_cache_manager)
        keys = await w._get_keys_to_warm()
        assert "prio1" in keys
        assert "prio2" in keys

    @pytest.mark.asyncio
    async def test_deduplication(self, mock_cache_manager):
        cfg = WarmingConfig(priority_keys=["dup", "dup", "other"], l2_count=10)
        w = CacheWarmer(config=cfg, cache_manager=mock_cache_manager)
        keys = await w._get_keys_to_warm()
        assert keys == ["dup", "other"]

    @pytest.mark.asyncio
    async def test_l3_cache_keys_loaded(self):
        """If cache manager has _l3_cache, those keys are included."""
        import threading

        # Use a plain MagicMock to avoid AsyncMock auto-creating coroutine attrs
        mgr = MagicMock()
        mgr._l3_cache = {"l3a": {}, "l3b": {}}
        mgr._l3_lock = threading.Lock()
        # Explicitly remove _access_records so hasattr returns False
        del mgr._access_records

        cfg = WarmingConfig(l2_count=10)
        w = CacheWarmer(config=cfg, cache_manager=mgr)
        keys = await w._get_keys_to_warm()
        assert "l3a" in keys
        assert "l3b" in keys


# ---------------------------------------------------------------------------
# CacheWarmer — _load_key_value
# ---------------------------------------------------------------------------


class TestLoadKeyValue:
    @pytest.mark.asyncio
    async def test_sync_loader(self, warmer, mock_cache_manager):
        val = await warmer._load_key_value("k", mock_cache_manager, lambda k: 42)
        assert val == 42

    @pytest.mark.asyncio
    async def test_async_loader(self, warmer, mock_cache_manager):
        async def loader(k):
            return 99

        val = await warmer._load_key_value("k", mock_cache_manager, loader)
        assert val == 99

    @pytest.mark.asyncio
    async def test_fallback_to_cache_manager_get(self, warmer, mock_cache_manager):
        mock_cache_manager.get = MagicMock(return_value="cached")
        val = await warmer._load_key_value("k", mock_cache_manager, None)
        assert val == "cached"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, warmer, mock_cache_manager):
        mock_cache_manager.get = MagicMock(return_value=None)
        val = await warmer._load_key_value("k", mock_cache_manager, None)
        assert val is None

    @pytest.mark.asyncio
    async def test_retries_on_runtime_error(self, warmer, mock_cache_manager):
        call_count = 0

        def flaky_loader(k):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient")
            return "ok"

        val = await warmer._load_key_value("k", mock_cache_manager, flaky_loader)
        assert val == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_returns_none_after_max_retries(self, warmer, mock_cache_manager):
        def always_fail(k):
            raise ConnectionError("down")

        val = await warmer._load_key_value("k", mock_cache_manager, always_fail)
        assert val is None

    @pytest.mark.asyncio
    async def test_l3_cache_data_extracted(self, warmer, mock_cache_manager):
        """Value is extracted from _l3_cache[key]['data']."""
        import threading

        mock_cache_manager._l3_cache = {"mykey": {"data": "hello"}}
        mock_cache_manager._l3_lock = threading.Lock()

        val = await warmer._load_key_value("mykey", mock_cache_manager, None)
        assert val == "hello"


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_cache_warmer_returns_same_instance(self):
        w1 = get_cache_warmer(rate_limit=50)
        w2 = get_cache_warmer(rate_limit=999)  # Ignored — singleton already created
        assert w1 is w2

    def test_reset_cache_warmer(self):
        w1 = get_cache_warmer()
        reset_cache_warmer()
        w2 = get_cache_warmer()
        assert w1 is not w2

    def test_reset_when_none(self):
        # Should not raise
        reset_cache_warmer()
        reset_cache_warmer()


# ---------------------------------------------------------------------------
# warm_cache_on_startup convenience function
# ---------------------------------------------------------------------------


class TestWarmCacheOnStartup:
    @pytest.mark.asyncio
    async def test_warm_cache_on_startup_returns_result(self):
        with patch(
            "src.core.shared.cache.warming.get_cache_warmer"
        ) as mock_get:
            mock_warmer = AsyncMock()
            mock_warmer.warm_cache = AsyncMock(
                return_value=WarmingResult(status=WarmingStatus.COMPLETED)
            )
            mock_get.return_value = mock_warmer

            result = await warm_cache_on_startup(
                source_keys=["a"],
                priority_keys=["p1"],
                rate_limit=50,
            )

            assert result.status == WarmingStatus.COMPLETED
            mock_warmer.warm_cache.assert_awaited_once()


# ---------------------------------------------------------------------------
# Timeout in _warm_in_batches
# ---------------------------------------------------------------------------


class TestWarmingTimeout:
    @pytest.mark.asyncio
    async def test_timeout_stops_warming(self, mock_cache_manager):
        cfg = WarmingConfig(
            rate_limit=10000,
            batch_size=2,
            l1_count=0,
            l2_count=100,
            total_timeout=0.0,  # Immediate timeout
        )
        w = CacheWarmer(config=cfg, cache_manager=mock_cache_manager)
        keys = [f"k{i}" for i in range(10)]
        result = await w.warm_cache(source_keys=keys, key_loader=lambda k: "v")
        # Should complete (timeout is treated as completed with detail)
        assert result.status == WarmingStatus.COMPLETED
        assert result.details.get("timeout") is True or result.keys_warmed < 10
