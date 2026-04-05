"""
Tests for enhanced_agent_bus.security.redis_rate_limiter

Covers: InMemoryWindow, InMemoryRateLimiter, RedisRateLimiter (fallback paths),
        MultiTierRateLimiter, RateLimitResult dataclass.
All Redis interactions are avoided; tests exercise the in-memory fallback path.
"""

import time

import pytest

from enhanced_agent_bus.security.redis_rate_limiter import (
    InMemoryRateLimiter,
    InMemoryWindow,
    MultiTierRateLimiter,
    RateLimitResult,
    RedisRateLimiter,
)

# ---------------------------------------------------------------------------
# RateLimitResult dataclass
# ---------------------------------------------------------------------------


class TestRateLimitResult:
    def test_defaults(self):
        r = RateLimitResult(
            allowed=True,
            current_count=1,
            limit=10,
            window_seconds=60,
            remaining=9,
        )
        assert r.retry_after_seconds is None
        assert r.using_fallback is False


# ---------------------------------------------------------------------------
# InMemoryWindow
# ---------------------------------------------------------------------------


class TestInMemoryWindow:
    def test_add_request_returns_count(self):
        w = InMemoryWindow()
        now = time.monotonic()
        count = w.add_request(now, 60)
        assert count == 1
        count = w.add_request(now + 0.1, 60)
        assert count == 2

    def test_expired_entries_removed(self):
        w = InMemoryWindow()
        old = time.monotonic() - 100
        w.timestamps = [old]
        count = w.add_request(time.monotonic(), 60)
        assert count == 1  # old entry evicted


# ---------------------------------------------------------------------------
# InMemoryRateLimiter
# ---------------------------------------------------------------------------


class TestInMemoryRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        limiter = InMemoryRateLimiter()
        result = await limiter.is_allowed("user1", 5, 60)
        assert result.allowed is True
        assert result.remaining == 4
        assert result.using_fallback is True

    @pytest.mark.asyncio
    async def test_denies_over_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            await limiter.is_allowed("user1", 5, 60)
        result = await limiter.is_allowed("user1", 5, 60)
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after_seconds is not None

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            await limiter.is_allowed("a", 5, 60)
        # Key "b" should still be allowed
        result = await limiter.is_allowed("b", 5, 60)
        assert result.allowed is True

    def test_cleanup_removes_expired_windows(self):
        limiter = InMemoryRateLimiter()
        limiter._windows["old_key"].timestamps = []
        limiter._windows["stale_key"].timestamps = [time.monotonic() - 7200]
        limiter._last_cleanup = time.monotonic() - 120  # Force cleanup
        limiter._maybe_cleanup()
        assert "old_key" not in limiter._windows
        assert "stale_key" not in limiter._windows

    def test_cleanup_skips_if_recent(self):
        limiter = InMemoryRateLimiter()
        limiter._windows["k"].timestamps = []
        limiter._last_cleanup = time.monotonic()  # Very recent
        limiter._maybe_cleanup()
        # Should not have cleaned up (interval not elapsed)
        assert "k" in limiter._windows


# ---------------------------------------------------------------------------
# RedisRateLimiter — fallback mode (no real Redis)
# ---------------------------------------------------------------------------


class TestRedisRateLimiterFallback:
    @pytest.fixture()
    def limiter(self):
        return RedisRateLimiter(
            redis_url="redis://localhost:9999",
            fallback_enabled=True,
        )

    def test_initial_state(self, limiter):
        assert limiter.is_connected is False
        assert limiter.using_fallback is False

    @pytest.mark.asyncio
    async def test_connect_activates_fallback_on_failure(self, limiter):
        await limiter.connect()
        # Should fall back since Redis is not reachable
        assert limiter.using_fallback is True
        assert limiter.is_connected is False

    @pytest.mark.asyncio
    async def test_is_allowed_uses_fallback(self, limiter):
        await limiter.connect()
        result = await limiter.is_allowed("key1", 10, 60)
        assert result.allowed is True
        assert result.using_fallback is True

    @pytest.mark.asyncio
    async def test_get_current_count_fallback(self, limiter):
        await limiter.connect()
        await limiter.is_allowed("key1", 10, 60)
        count = await limiter.get_current_count("key1", 60)
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_current_count_no_window(self, limiter):
        await limiter.connect()
        count = await limiter.get_current_count("nonexistent", 60)
        assert count == 0

    @pytest.mark.asyncio
    async def test_reset_fallback(self, limiter):
        await limiter.connect()
        await limiter.is_allowed("key1", 10, 60)
        ok = await limiter.reset("key1")
        assert ok is True
        count = await limiter.get_current_count("key1", 60)
        assert count == 0

    @pytest.mark.asyncio
    async def test_reset_nonexistent_key(self, limiter):
        await limiter.connect()
        ok = await limiter.reset("nope")
        assert ok is True

    @pytest.mark.asyncio
    async def test_close_is_safe(self, limiter):
        await limiter.connect()
        await limiter.close()
        assert limiter.is_connected is False

    def test_make_key(self, limiter):
        assert limiter._make_key("user:1") == "acgs:ratelimit:user:1"


class TestRedisRateLimiterFallbackDisabled:
    @pytest.mark.asyncio
    async def test_connect_raises_when_fallback_disabled(self):
        limiter = RedisRateLimiter(
            redis_url="redis://localhost:9999",
            fallback_enabled=False,
        )
        with pytest.raises(RuntimeError, match="fallback disabled"):
            await limiter.connect()

    @pytest.mark.asyncio
    async def test_is_allowed_raises_when_not_connected(self):
        limiter = RedisRateLimiter(fallback_enabled=False)
        with pytest.raises(RuntimeError, match="not connected"):
            await limiter.is_allowed("k", 10, 60)


class TestRedisRateLimiterNotConnected:
    @pytest.mark.asyncio
    async def test_get_current_count_returns_zero(self):
        limiter = RedisRateLimiter(fallback_enabled=False)
        count = await limiter.get_current_count("k", 60)
        assert count == 0

    @pytest.mark.asyncio
    async def test_reset_returns_false(self):
        limiter = RedisRateLimiter(fallback_enabled=False)
        ok = await limiter.reset("k")
        assert ok is False

    @pytest.mark.asyncio
    async def test_is_allowed_activates_fallback_if_enabled(self):
        limiter = RedisRateLimiter(fallback_enabled=True)
        # Not connected, not in fallback mode yet
        result = await limiter.is_allowed("k", 10, 60)
        assert result.using_fallback is True


# ---------------------------------------------------------------------------
# MultiTierRateLimiter
# ---------------------------------------------------------------------------


class TestMultiTierRateLimiter:
    @pytest.fixture()
    async def tier_limiter(self):
        mt = MultiTierRateLimiter(
            redis_url="redis://localhost:9999",
            fallback_enabled=True,
        )
        await mt.connect()
        mt.configure_tiers("default", [(5, 1), (20, 60)])
        return mt

    @pytest.mark.asyncio
    async def test_configure_and_check(self, tier_limiter):
        allowed, results = await tier_limiter.is_allowed("user1", "default")
        assert allowed is True
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_unknown_tier_raises(self, tier_limiter):
        with pytest.raises(ValueError, match="Unknown tier"):
            await tier_limiter.is_allowed("user1", "premium")

    @pytest.mark.asyncio
    async def test_close(self, tier_limiter):
        await tier_limiter.close()
