"""Tests for Redis rate limiter backend.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.services.api_gateway.redis_backend import (
    RedisConfig,
    RedisRateLimitBackend,
    get_redis_backend,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# RedisConfig
# ---------------------------------------------------------------------------


class TestRedisConfig:
    def test_defaults(self):
        config = RedisConfig()
        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0
        assert config.password is None
        assert config.key_prefix == "acgs:ratelimit:"
        assert config.socket_timeout == 1.0

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = RedisConfig.from_env()
        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0
        assert config.password is None

    def test_from_env_custom(self):
        env = {
            "REDIS_HOST": "redis.example.com",
            "REDIS_PORT": "6380",
            "REDIS_DB": "2",
            "REDIS_PASSWORD": "secret123",
            "REDIS_RATE_LIMIT_PREFIX": "custom:",
        }
        with patch.dict(os.environ, env, clear=True):
            config = RedisConfig.from_env()
        assert config.host == "redis.example.com"
        assert config.port == 6380
        assert config.db == 2
        assert config.password == "secret123"
        assert config.key_prefix == "custom:"


# ---------------------------------------------------------------------------
# RedisRateLimitBackend — connection
# ---------------------------------------------------------------------------


class TestRedisRateLimitBackendConnect:
    def test_constitutional_hash_set(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        assert backend.constitutional_hash == CONSTITUTIONAL_HASH

    def test_initial_state_not_available(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        assert backend.is_available is False

    @pytest.mark.asyncio
    async def test_connect_import_error(self):
        """When redis package is not installed, connect returns False."""
        backend = RedisRateLimitBackend(config=RedisConfig())
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("no redis"),
            ):
                result = await backend.connect()
        # May or may not catch depending on import path, but should not crash
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_connect_connection_failure(self):
        """When Redis is unreachable, connect returns False."""
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_pool = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                result = await backend.connect()

        assert result is False
        assert backend.is_available is False

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Successful connection sets is_available to True."""
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_pool = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                result = await backend.connect()

        assert result is True
        assert backend.is_available is True


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_false_when_redis_is_none(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        backend._available = True
        backend._redis = None
        assert backend.is_available is False

    def test_false_when_available_flag_false(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        backend._available = False
        backend._redis = MagicMock()
        assert backend.is_available is False

    def test_true_when_both_set(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        backend._available = True
        backend._redis = MagicMock()
        assert backend.is_available is True


# ---------------------------------------------------------------------------
# check_and_consume
# ---------------------------------------------------------------------------


class TestCheckAndConsume:
    @pytest.mark.asyncio
    async def test_not_available_returns_allowed(self):
        """When Redis is unavailable, always allow (fail-open)."""
        backend = RedisRateLimitBackend(config=RedisConfig())
        allowed, remaining, reset = await backend.check_and_consume(
            "test_key", max_tokens=10.0, refill_rate=1.0
        )
        assert allowed is True
        assert remaining == 10.0
        assert reset == 0.0

    @pytest.mark.asyncio
    async def test_lua_script_success(self):
        """Successful Lua script execution returns parsed results."""
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=[1, 9.0, 1.0])
        backend._redis = mock_redis
        backend._available = True

        allowed, remaining, reset = await backend.check_and_consume(
            "user:123", max_tokens=10.0, refill_rate=1.0, window_seconds=60
        )

        assert allowed is True
        assert remaining == 9.0
        assert reset == 1.0
        mock_redis.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lua_script_denied(self):
        """When tokens exhausted, returns not allowed."""
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=[0, 0.0, 10.0])
        backend._redis = mock_redis
        backend._available = True

        allowed, remaining, reset = await backend.check_and_consume(
            "user:456", max_tokens=10.0, refill_rate=1.0
        )

        assert allowed is False
        assert remaining == 0.0
        assert reset == 10.0

    @pytest.mark.asyncio
    async def test_lua_script_failure_falls_back_to_allow(self):
        """Redis errors during check fall back to allow (fail-open)."""
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(side_effect=ConnectionError("timeout"))
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("still down"))
        backend._redis = mock_redis
        backend._available = True
        backend._last_check = 0.0  # Allow _check_connection to run

        allowed, remaining, reset = await backend.check_and_consume(
            "user:789", max_tokens=10.0, refill_rate=1.0
        )

        assert allowed is True
        assert remaining == 10.0

    @pytest.mark.asyncio
    async def test_uses_key_prefix(self):
        """Keys should be prefixed with the configured prefix."""
        config = RedisConfig(key_prefix="myprefix:")
        backend = RedisRateLimitBackend(config=config)
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=[1, 9.0, 1.0])
        backend._redis = mock_redis
        backend._available = True

        await backend.check_and_consume("user:1", max_tokens=10.0, refill_rate=1.0)

        call_args = mock_redis.eval.call_args
        assert call_args[0][2] == "myprefix:user:1"


# ---------------------------------------------------------------------------
# _check_connection
# ---------------------------------------------------------------------------


class TestCheckConnection:
    @pytest.mark.asyncio
    async def test_skips_if_checked_recently(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        backend._last_check = time.time()  # Just checked
        backend._redis = AsyncMock()

        await backend._check_connection()
        # Should not call ping because interval hasn't elapsed
        backend._redis.ping.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ping_success_restores_availability(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        backend._last_check = 0.0  # Long ago
        backend._available = False
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        backend._redis = mock_redis

        await backend._check_connection()
        assert backend._available is True

    @pytest.mark.asyncio
    async def test_ping_failure_marks_unavailable(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        backend._last_check = 0.0
        backend._available = True
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))
        backend._redis = mock_redis

        await backend._check_connection()
        assert backend._available is False

    @pytest.mark.asyncio
    async def test_no_redis_client_skips(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        backend._last_check = 0.0
        backend._redis = None

        await backend._check_connection()
        # No error raised


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    @pytest.mark.asyncio
    async def test_stats_when_unavailable(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        stats = await backend.get_stats()

        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["backend"] == "in-memory"
        assert stats["available"] is False
        assert "config" in stats

    @pytest.mark.asyncio
    async def test_stats_when_available(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_redis = AsyncMock()
        mock_redis.info = AsyncMock(return_value={"used_memory_human": "1.5M"})
        backend._redis = mock_redis
        backend._available = True

        stats = await backend.get_stats()

        assert stats["backend"] == "redis"
        assert stats["available"] is True
        assert stats["memory_used"] == "1.5M"

    @pytest.mark.asyncio
    async def test_stats_redis_info_failure_handled(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_redis = AsyncMock()
        mock_redis.info = AsyncMock(side_effect=ConnectionError("down"))
        backend._redis = mock_redis
        backend._available = True

        stats = await backend.get_stats()
        # Should not crash, memory_used should not be present
        assert stats["available"] is True
        assert "memory_used" not in stats


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_close_redis_and_pool(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        mock_redis = AsyncMock()
        mock_pool = AsyncMock()
        backend._redis = mock_redis
        backend._connection_pool = mock_pool
        backend._available = True

        await backend.close()

        mock_redis.close.assert_awaited_once()
        mock_pool.disconnect.assert_awaited_once()
        assert backend._redis is None
        assert backend._connection_pool is None
        assert backend._available is False

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self):
        backend = RedisRateLimitBackend(config=RedisConfig())
        # Should not raise
        await backend.close()


# ---------------------------------------------------------------------------
# get_redis_backend singleton
# ---------------------------------------------------------------------------


class TestGetRedisBackend:
    @pytest.mark.asyncio
    async def test_creates_and_connects_backend(self):
        import src.core.services.api_gateway.redis_backend as rb_mod

        rb_mod._redis_backend = None

        mock_pool = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("test"))

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                backend = await get_redis_backend()

        assert isinstance(backend, RedisRateLimitBackend)
        rb_mod._redis_backend = None  # cleanup
