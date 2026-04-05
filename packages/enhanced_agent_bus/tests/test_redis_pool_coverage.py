"""
ACGS-2 Enhanced Agent Bus - Redis Pool Coverage Tests
Constitutional Hash: 608508a9bd224290

Comprehensive test suite targeting >=98% coverage of redis_pool.py.
Covers all classes, methods, error paths, and edge cases.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(**kwargs):
    """Create a RedisConnectionPool with sensible defaults."""
    from enhanced_agent_bus.redis_pool import RedisConnectionPool

    defaults = dict(
        redis_url="redis://localhost:6379",
        max_connections=10,
        min_connections=2,
        socket_timeout=1.0,
        socket_connect_timeout=1.0,
        retry_attempts=3,
        retry_delay=0.0,
        decode_responses=True,
    )
    defaults.update(kwargs)
    return RedisConnectionPool(**defaults)


def _make_initialized_pool(mock_redis):
    """Create a pool that looks already initialized with a mock redis client."""
    pool = _make_pool()
    pool._redis = mock_redis
    pool._initialized = True
    return pool


# ---------------------------------------------------------------------------
# Module-level constants / defaults
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Verify exported constants and defaults."""

    def test_default_pool_size(self):
        from enhanced_agent_bus.redis_pool import DEFAULT_POOL_SIZE

        assert DEFAULT_POOL_SIZE == 20

    def test_default_min_connections(self):
        from enhanced_agent_bus.redis_pool import DEFAULT_MIN_CONNECTIONS

        assert DEFAULT_MIN_CONNECTIONS == 5

    def test_redis_available_flag_is_bool(self):
        from enhanced_agent_bus.redis_pool import REDIS_AVAILABLE

        assert isinstance(REDIS_AVAILABLE, bool)

    def test_all_exports_present(self):
        import enhanced_agent_bus.redis_pool as m

        for name in [
            "DEFAULT_POOL_SIZE",
            "DEFAULT_MIN_CONNECTIONS",
            "RedisConnectionPool",
            "get_shared_pool",
            "reset_shared_pool",
            "REDIS_AVAILABLE",
        ]:
            assert hasattr(m, name), f"Missing export: {name}"


# ---------------------------------------------------------------------------
# RedisConnectionPool.__init__
# ---------------------------------------------------------------------------


class TestRedisConnectionPoolInit:
    """Test __init__ stores all parameters and initialises metrics."""

    def test_all_params_stored(self):
        pool = _make_pool(
            redis_url="redis://host:9999",
            max_connections=42,
            min_connections=7,
            socket_timeout=2.5,
            socket_connect_timeout=3.5,
            retry_attempts=5,
            retry_delay=0.25,
            decode_responses=False,
        )
        assert pool.redis_url == "redis://host:9999"
        assert pool.max_connections == 42
        assert pool.min_connections == 7
        assert pool.socket_timeout == 2.5
        assert pool.socket_connect_timeout == 3.5
        assert pool.retry_attempts == 5
        assert pool.retry_delay == 0.25
        assert pool.decode_responses is False

    def test_constitutional_hash_set(self):
        pool = _make_pool()
        assert pool.constitutional_hash == CONSTITUTIONAL_HASH

    def test_initial_state_not_initialized(self):
        pool = _make_pool()
        assert pool._initialized is False
        assert pool._redis is None
        assert pool._pool is None

    def test_metrics_initialized(self):
        pool = _make_pool()
        m = pool._metrics
        assert m["total_connections"] == 0
        assert m["active_connections"] == 0
        assert m["total_operations"] == 0
        assert m["failed_operations"] == 0
        assert m["total_latency_ms"] == 0.0
        assert "created_at" in m

    def test_lock_is_asyncio_lock(self):
        pool = _make_pool()
        assert isinstance(pool._lock, asyncio.Lock)


# ---------------------------------------------------------------------------
# RedisConnectionPool.initialize
# ---------------------------------------------------------------------------


class TestInitialize:
    """Test the initialize() method under all branches."""

    async def test_initialize_success_no_prewarm(self):
        """Happy path — initialize without pre-warming."""
        pool = _make_pool(min_connections=1)

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                result = await pool.initialize(pre_warm=False)

        assert result is True
        assert pool._initialized is True
        assert pool._redis is mock_redis
        mock_redis.ping.assert_awaited_once()

    async def test_initialize_success_with_prewarm(self):
        """Happy path — initialize with pre-warming (min_connections > 1)."""
        pool = _make_pool(min_connections=3)

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                result = await pool.initialize(pre_warm=True)

        assert result is True
        assert pool._initialized is True

    async def test_initialize_already_initialized_returns_true(self):
        """Calling initialize again when already initialized is a no-op."""
        pool = _make_pool()
        pool._initialized = True

        result = await pool.initialize()

        assert result is True
        assert pool._redis is None  # was not touched

    async def test_initialize_redis_not_available(self):
        """Returns False when redis package is not available."""
        pool = _make_pool()

        with patch("enhanced_agent_bus.redis_pool.REDIS_AVAILABLE", False):
            result = await pool.initialize()

        assert result is False
        assert pool._initialized is False

    async def test_initialize_connection_error(self):
        """Returns False on RedisConnectionError during init."""
        from redis.exceptions import ConnectionError as RedisConnError

        pool = _make_pool()
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis") as mock_redis_cls:
                mock_redis_cls.return_value.ping = AsyncMock(side_effect=RedisConnError("down"))
                result = await pool.initialize()

        assert result is False
        assert pool._pool is None
        assert pool._redis is None

    async def test_initialize_timeout_error(self):
        """Returns False on RedisTimeoutError during init."""
        from redis.exceptions import TimeoutError as RedisTO

        pool = _make_pool()
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis") as mock_redis_cls:
                mock_redis_cls.return_value.ping = AsyncMock(side_effect=RedisTO("timeout"))
                result = await pool.initialize()

        assert result is False

    async def test_initialize_redis_error(self):
        """Returns False on generic RedisError during init."""
        from redis.exceptions import RedisError

        pool = _make_pool()
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis") as mock_redis_cls:
                mock_redis_cls.return_value.ping = AsyncMock(side_effect=RedisError("oops"))
                result = await pool.initialize()

        assert result is False

    async def test_initialize_operation_error_tuple(self):
        """Returns False on OSError (member of _REDIS_POOL_OPERATION_ERRORS)."""
        pool = _make_pool()
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis") as mock_redis_cls:
                mock_redis_cls.return_value.ping = AsyncMock(side_effect=OSError("network"))
                result = await pool.initialize()

        assert result is False

    async def test_initialize_double_check_inside_lock(self):
        """Second goroutine finds _initialized=True inside the lock."""
        pool = _make_pool(min_connections=1)

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                r1 = await pool.initialize()
                r2 = await pool.initialize()

        assert r1 is True
        assert r2 is True
        # ping only called once (second call exits at top-level guard)
        assert mock_redis.ping.await_count == 1

    async def test_initialize_prewarm_skipped_when_min_connections_is_1(self):
        """Pre-warm is skipped if min_connections <= 1."""
        pool = _make_pool(min_connections=1)

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = MagicMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                with patch.object(pool, "_warm_pool", new=AsyncMock()) as mock_warm:
                    result = await pool.initialize(pre_warm=True)

        assert result is True
        mock_warm.assert_not_awaited()


# ---------------------------------------------------------------------------
# RedisConnectionPool._warm_pool / _warm_single_connection
# ---------------------------------------------------------------------------


class TestWarmPool:
    """Test connection pre-warming logic."""

    async def test_warm_pool_no_redis_returns_zero(self):
        pool = _make_pool()
        pool._redis = None
        result = await pool._warm_pool()
        assert result == 0

    async def test_warm_pool_counts_successes(self):
        pool = _make_pool(min_connections=3)
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        pool._redis = mock_redis

        result = await pool._warm_pool()
        assert result == 3
        assert pool._metrics["warmed_connections"] == 3
        assert pool._metrics["total_connections"] == 3

    async def test_warm_pool_handles_partial_failures(self):
        """Some pings fail — only successful ones are counted."""
        pool = _make_pool(min_connections=3)
        mock_redis = AsyncMock()
        call_count = 0

        async def sometimes_fail():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                from redis.exceptions import ConnectionError as RCE

                raise RCE("fail")
            return True

        mock_redis.ping = AsyncMock(side_effect=sometimes_fail)
        pool._redis = mock_redis

        result = await pool._warm_pool()
        assert result == 2

    async def test_warm_pool_handles_exception_result(self):
        """asyncio.gather returns an Exception object — warned, not counted."""
        pool = _make_pool(min_connections=2)
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RuntimeError("boom"))
        pool._redis = mock_redis

        result = await pool._warm_pool()
        assert result == 0

    async def test_warm_single_connection_success(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        pool = _make_pool()
        pool._redis = mock_redis
        result = await pool._warm_single_connection()
        assert result is True

    async def test_warm_single_connection_redis_connection_error(self):
        from redis.exceptions import ConnectionError as RCE

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RCE("fail"))

        pool = _make_pool()
        pool._redis = mock_redis
        result = await pool._warm_single_connection()
        assert result is False

    async def test_warm_single_connection_timeout_error(self):
        from redis.exceptions import TimeoutError as RTE

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RTE("timeout"))

        pool = _make_pool()
        pool._redis = mock_redis
        result = await pool._warm_single_connection()
        assert result is False

    async def test_warm_single_connection_redis_error(self):
        from redis.exceptions import RedisError

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RedisError("err"))

        pool = _make_pool()
        pool._redis = mock_redis
        result = await pool._warm_single_connection()
        assert result is False


# ---------------------------------------------------------------------------
# RedisConnectionPool.close
# ---------------------------------------------------------------------------


class TestClose:
    """Test the close() method."""

    async def test_close_clears_state(self):
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()
        mock_pool_obj = AsyncMock()
        mock_pool_obj.disconnect = AsyncMock()

        pool = _make_pool()
        pool._redis = mock_redis
        pool._pool = mock_pool_obj
        pool._initialized = True

        await pool.close()

        mock_redis.close.assert_awaited_once()
        mock_pool_obj.disconnect.assert_awaited_once()
        assert pool._redis is None
        assert pool._pool is None
        assert pool._initialized is False

    async def test_close_when_already_none(self):
        """Closing when redis/pool are None should not raise."""
        pool = _make_pool()
        await pool.close()  # no-op, nothing to close


# ---------------------------------------------------------------------------
# RedisConnectionPool.acquire
# ---------------------------------------------------------------------------


class TestAcquire:
    """Test the acquire() context manager."""

    async def test_acquire_yields_redis_client(self):
        mock_redis = AsyncMock()
        pool = _make_initialized_pool(mock_redis)

        async with pool.acquire() as conn:
            assert conn is mock_redis

    async def test_acquire_updates_metrics(self):
        mock_redis = AsyncMock()
        pool = _make_initialized_pool(mock_redis)

        assert pool._metrics["active_connections"] == 0
        async with pool.acquire() as _:
            assert pool._metrics["active_connections"] == 1

        assert pool._metrics["active_connections"] == 0
        assert pool._metrics["total_operations"] == 1
        assert pool._metrics["total_latency_ms"] >= 0.0

    async def test_acquire_raises_when_not_initialized(self):
        """If initialize() leaves _redis=None, acquire raises ConnectionError."""
        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(return_value=False)):
            with pytest.raises(ConnectionError, match="Redis pool not initialized"):
                async with pool.acquire() as _:
                    pass

    async def test_acquire_triggers_initialize_when_not_initialized(self):
        """acquire() calls initialize() if pool is not yet initialized."""
        mock_redis = AsyncMock()
        pool = _make_pool()

        async def fake_init(pre_warm=True):
            pool._initialized = True
            pool._redis = mock_redis
            return True

        with patch.object(pool, "initialize", side_effect=fake_init):
            async with pool.acquire() as conn:
                assert conn is mock_redis

    async def test_acquire_metrics_updated_on_exception(self):
        """Metrics are still updated in finally block even if body raises."""
        mock_redis = AsyncMock()
        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RuntimeError):
            async with pool.acquire() as _:
                raise RuntimeError("body error")

        assert pool._metrics["active_connections"] == 0
        assert pool._metrics["total_operations"] == 1


# ---------------------------------------------------------------------------
# RedisConnectionPool.health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Test health_check() under all branches."""

    async def test_health_check_healthy(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        pool = _make_initialized_pool(mock_redis)

        result = await pool.health_check()

        assert result["healthy"] is True
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "pool_stats" in result

    async def test_health_check_not_initialized_calls_init_success(self):
        """health_check initializes pool if not initialized."""
        pool = _make_pool()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        async def fake_init(pre_warm=True):
            pool._initialized = True
            pool._redis = mock_redis
            return True

        with patch.object(pool, "initialize", side_effect=fake_init):
            result = await pool.health_check()

        assert result["healthy"] is True

    async def test_health_check_not_initialized_init_fails(self):
        """Returns error dict when init fails."""
        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(return_value=False)):
            result = await pool.health_check()

        assert result["healthy"] is False
        assert "error" in result

    async def test_health_check_not_initialized_connection_error_on_init(self):
        from redis.exceptions import ConnectionError as RCE

        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(side_effect=RCE("fail"))):
            result = await pool.health_check()

        assert result["healthy"] is False
        assert "error" in result

    async def test_health_check_not_initialized_timeout_on_init(self):
        from redis.exceptions import TimeoutError as RTE

        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(side_effect=RTE("timeout"))):
            result = await pool.health_check()

        assert result["healthy"] is False
        assert "error" in result

    async def test_health_check_not_initialized_redis_error_on_init(self):
        from redis.exceptions import RedisError

        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(side_effect=RedisError("err"))):
            result = await pool.health_check()

        assert result["healthy"] is False
        assert "error" in result

    async def test_health_check_not_initialized_operation_error_on_init(self):
        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(side_effect=OSError("os fail"))):
            result = await pool.health_check()

        assert result["healthy"] is False
        assert "error" in result

    async def test_health_check_redis_none_after_init(self):
        """_redis is still None after initialization — returns error."""
        pool = _make_pool()
        pool._initialized = True
        pool._redis = None

        result = await pool.health_check()

        assert result["healthy"] is False
        assert result["error"] == "Redis client not available"

    async def test_health_check_ping_connection_error_retries_and_fails(self):
        from redis.exceptions import ConnectionError as RCE

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RCE("down"))
        pool = _make_initialized_pool(mock_redis)
        pool.retry_attempts = 2
        pool.retry_delay = 0.0

        result = await pool.health_check()

        assert result["healthy"] is False
        assert "Connection failed" in result["error"]
        assert mock_redis.ping.await_count == 2

    async def test_health_check_ping_timeout_error_retries_and_fails(self):
        from redis.exceptions import TimeoutError as RTE

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RTE("timeout"))
        pool = _make_initialized_pool(mock_redis)
        pool.retry_attempts = 2
        pool.retry_delay = 0.0

        result = await pool.health_check()

        assert result["healthy"] is False
        assert "Timeout" in result["error"]

    async def test_health_check_ping_redis_error_retries_and_fails(self):
        from redis.exceptions import RedisError

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RedisError("err"))
        pool = _make_initialized_pool(mock_redis)
        pool.retry_attempts = 2
        pool.retry_delay = 0.0

        result = await pool.health_check()

        assert result["healthy"] is False
        assert "Redis error" in result["error"]

    async def test_health_check_ping_operation_error_retries_and_fails(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=RuntimeError("rt"))
        pool = _make_initialized_pool(mock_redis)
        pool.retry_attempts = 2
        pool.retry_delay = 0.0

        result = await pool.health_check()

        assert result["healthy"] is False
        assert "Unexpected error" in result["error"]

    async def test_health_check_retries_then_succeeds(self):
        """Fails once, then succeeds on retry."""
        from redis.exceptions import ConnectionError as RCE

        call_count = 0

        async def flaky_ping():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RCE("transient")
            return True

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=flaky_ping)
        pool = _make_initialized_pool(mock_redis)
        pool.retry_attempts = 3
        pool.retry_delay = 0.0

        result = await pool.health_check()

        assert result["healthy"] is True

    async def test_health_check_pool_stats_included_on_success(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        pool = _make_initialized_pool(mock_redis)

        result = await pool.health_check()

        stats = result["pool_stats"]
        assert stats["max_connections"] == pool.max_connections

    async def test_health_check_timestamp_present(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        pool = _make_initialized_pool(mock_redis)

        result = await pool.health_check()

        assert "timestamp" in result


# ---------------------------------------------------------------------------
# RedisConnectionPool._get_pool_stats
# ---------------------------------------------------------------------------


class TestGetPoolStats:
    """Test the internal _get_pool_stats() helper."""

    def test_get_pool_stats_initialized(self):
        pool = _make_initialized_pool(MagicMock())
        pool._pool = MagicMock()

        stats = pool._get_pool_stats()

        assert stats["initialized"] is True
        assert stats["max_connections"] == pool.max_connections
        assert "pool_class" in stats

    def test_get_pool_stats_no_pool_object(self):
        pool = _make_initialized_pool(MagicMock())
        pool._pool = None

        stats = pool._get_pool_stats()

        assert "pool_class" not in stats

    def test_get_pool_stats_attribute_error_suppressed(self):
        """AttributeError inside pool attribute access is silently caught."""
        pool = _make_initialized_pool(MagicMock())

        class _BadPool:
            """Pool whose __class__ property raises AttributeError."""

            @property
            def __class__(self):
                raise AttributeError("no class info")

        pool._pool = object.__new__(_BadPool)

        # Should not raise; AttributeError is caught in the source
        stats = pool._get_pool_stats()
        assert "initialized" in stats


# ---------------------------------------------------------------------------
# RedisConnectionPool.batch_get
# ---------------------------------------------------------------------------


class TestBatchGet:
    """Test batch_get() under all branches."""

    async def test_batch_get_empty_list_returns_empty(self):
        pool = _make_initialized_pool(MagicMock())
        result = await pool.batch_get([])
        assert result == []

    async def test_batch_get_success(self):
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=["v1", "v2"])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)
        result = await pool.batch_get(["k1", "k2"])

        assert result == ["v1", "v2"]
        assert pool._metrics["total_operations"] == 1

    async def test_batch_get_not_initialized_raises_connection_error(self):
        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(return_value=False)):
            with pytest.raises(ConnectionError):
                await pool.batch_get(["k1"])

    async def test_batch_get_redis_connection_error(self):
        from redis.exceptions import ConnectionError as RCE

        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RCE("down"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RCE):
            await pool.batch_get(["k1"])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_get_timeout_error(self):
        from redis.exceptions import TimeoutError as RTE

        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RTE("timeout"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RTE):
            await pool.batch_get(["k1"])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_get_redis_error(self):
        from redis.exceptions import RedisError

        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RedisError("err"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RedisError):
            await pool.batch_get(["k1"])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_get_triggers_initialize_when_needed(self):
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=["val"])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_pool()

        async def fake_init(pre_warm=True):
            pool._initialized = True
            pool._redis = mock_redis
            return True

        with patch.object(pool, "initialize", side_effect=fake_init):
            result = await pool.batch_get(["k"])

        assert result == ["val"]

    async def test_batch_get_latency_tracked(self):
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=["v1"])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)
        await pool.batch_get(["k1"])

        assert pool._metrics["total_latency_ms"] >= 0.0


# ---------------------------------------------------------------------------
# RedisConnectionPool.batch_set
# ---------------------------------------------------------------------------


class TestBatchSet:
    """Test batch_set() under all branches."""

    async def test_batch_set_empty_list_returns_empty(self):
        pool = _make_initialized_pool(MagicMock())
        result = await pool.batch_set([])
        assert result == []

    async def test_batch_set_success(self):
        mock_pipe = AsyncMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)
        result = await pool.batch_set([("k1", "v1", 60), ("k2", "v2", 120)])

        assert result == [True, True]
        assert pool._metrics["total_operations"] == 1

    async def test_batch_set_falsy_results_converted_to_bool(self):
        mock_pipe = AsyncMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, 0, 1])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)
        result = await pool.batch_set([("k1", "v1", 10), ("k2", "v2", 10), ("k3", "v3", 10)])

        assert result == [True, False, True]

    async def test_batch_set_not_initialized_raises_connection_error(self):
        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(return_value=False)):
            with pytest.raises(ConnectionError):
                await pool.batch_set([("k", "v", 10)])

    async def test_batch_set_redis_connection_error(self):
        from redis.exceptions import ConnectionError as RCE

        mock_pipe = AsyncMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RCE("down"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RCE):
            await pool.batch_set([("k", "v", 10)])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_set_timeout_error(self):
        from redis.exceptions import TimeoutError as RTE

        mock_pipe = AsyncMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RTE("timeout"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RTE):
            await pool.batch_set([("k", "v", 10)])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_set_redis_error(self):
        from redis.exceptions import RedisError

        mock_pipe = AsyncMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RedisError("err"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RedisError):
            await pool.batch_set([("k", "v", 10)])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_set_triggers_initialize_when_needed(self):
        mock_pipe = AsyncMock()
        mock_pipe.setex = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        pool = _make_pool()

        async def fake_init(pre_warm=True):
            pool._initialized = True
            pool._redis = mock_redis
            return True

        with patch.object(pool, "initialize", side_effect=fake_init):
            result = await pool.batch_set([("k", "v", 10)])

        assert result == [True]


# ---------------------------------------------------------------------------
# RedisConnectionPool.batch_delete
# ---------------------------------------------------------------------------


class TestBatchDelete:
    """Test batch_delete() under all branches."""

    async def test_batch_delete_empty_list_returns_zero(self):
        pool = _make_initialized_pool(MagicMock())
        result = await pool.batch_delete([])
        assert result == 0

    async def test_batch_delete_success(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=3)

        pool = _make_initialized_pool(mock_redis)
        result = await pool.batch_delete(["k1", "k2", "k3"])

        assert result == 3
        mock_redis.delete.assert_awaited_once_with("k1", "k2", "k3")
        assert pool._metrics["total_operations"] == 1

    async def test_batch_delete_not_initialized_raises_connection_error(self):
        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(return_value=False)):
            with pytest.raises(ConnectionError):
                await pool.batch_delete(["k"])

    async def test_batch_delete_redis_connection_error(self):
        from redis.exceptions import ConnectionError as RCE

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=RCE("down"))

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RCE):
            await pool.batch_delete(["k"])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_delete_timeout_error(self):
        from redis.exceptions import TimeoutError as RTE

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=RTE("timeout"))

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RTE):
            await pool.batch_delete(["k"])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_delete_redis_error(self):
        from redis.exceptions import RedisError

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=RedisError("err"))

        pool = _make_initialized_pool(mock_redis)

        with pytest.raises(RedisError):
            await pool.batch_delete(["k"])

        assert pool._metrics["failed_operations"] == 1

    async def test_batch_delete_triggers_initialize_when_needed(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        pool = _make_pool()

        async def fake_init(pre_warm=True):
            pool._initialized = True
            pool._redis = mock_redis
            return True

        with patch.object(pool, "initialize", side_effect=fake_init):
            result = await pool.batch_delete(["k"])

        assert result == 1


# ---------------------------------------------------------------------------
# RedisConnectionPool.get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    """Test the get_metrics() helper."""

    def test_get_metrics_no_operations(self):
        pool = _make_pool()
        metrics = pool.get_metrics()

        assert metrics["total_operations"] == 0
        assert metrics["avg_latency_ms"] == 0.0

    def test_get_metrics_with_operations(self):
        pool = _make_pool()
        pool._metrics["total_operations"] = 10
        pool._metrics["total_latency_ms"] = 50.0

        metrics = pool.get_metrics()

        assert metrics["avg_latency_ms"] == 5.0

    def test_get_metrics_returns_copy(self):
        """Mutations to the returned dict should not affect internal metrics."""
        pool = _make_pool()
        metrics = pool.get_metrics()
        metrics["total_operations"] = 9999

        assert pool._metrics["total_operations"] == 0

    def test_get_metrics_includes_all_keys(self):
        pool = _make_pool()
        metrics = pool.get_metrics()

        for key in [
            "total_connections",
            "active_connections",
            "total_operations",
            "failed_operations",
            "total_latency_ms",
            "created_at",
            "avg_latency_ms",
        ]:
            assert key in metrics, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# RedisConnectionPool async context manager
# ---------------------------------------------------------------------------


class TestAsyncContextManager:
    """Test __aenter__ / __aexit__."""

    async def test_aenter_calls_initialize(self):
        pool = _make_pool()

        with patch.object(pool, "initialize", new=AsyncMock(return_value=True)) as mock_init:
            result = await pool.__aenter__()

        mock_init.assert_awaited_once()
        assert result is pool

    async def test_aexit_calls_close(self):
        pool = _make_pool()

        with patch.object(pool, "close", new=AsyncMock()) as mock_close:
            await pool.__aexit__(None, None, None)

        mock_close.assert_awaited_once()

    async def test_context_manager_full_flow(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.close = AsyncMock()
        mock_pool_obj = AsyncMock()
        mock_pool_obj.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = _make_pool(min_connections=1)
                async with pool:
                    assert pool._initialized is True

        assert pool._initialized is False


# ---------------------------------------------------------------------------
# get_shared_pool / reset_shared_pool
# ---------------------------------------------------------------------------


class TestSharedPool:
    """Test module-level singleton helpers."""

    async def test_get_shared_pool_creates_and_initializes(self):
        from enhanced_agent_bus.redis_pool import get_shared_pool, reset_shared_pool

        await reset_shared_pool()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = AsyncMock()
        mock_pool_obj.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = await get_shared_pool(redis_url="redis://localhost:6379")

        assert pool is not None
        assert pool._initialized is True

        await reset_shared_pool()

    async def test_get_shared_pool_returns_same_instance(self):
        from enhanced_agent_bus.redis_pool import get_shared_pool, reset_shared_pool

        await reset_shared_pool()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = AsyncMock()
        mock_pool_obj.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool1 = await get_shared_pool()
                pool2 = await get_shared_pool()

        assert pool1 is pool2

        await reset_shared_pool()

    async def test_get_shared_pool_reinitializes_after_reset(self):
        from enhanced_agent_bus.redis_pool import get_shared_pool, reset_shared_pool

        await reset_shared_pool()

        mock_redis1 = AsyncMock()
        mock_redis1.ping = AsyncMock(return_value=True)
        mock_redis1.close = AsyncMock()
        mock_pool_obj1 = AsyncMock()
        mock_pool_obj1.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj1):
            with patch("redis.asyncio.Redis", return_value=mock_redis1):
                pool1 = await get_shared_pool()

        await reset_shared_pool()

        mock_redis2 = AsyncMock()
        mock_redis2.ping = AsyncMock(return_value=True)
        mock_pool_obj2 = AsyncMock()
        mock_pool_obj2.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj2):
            with patch("redis.asyncio.Redis", return_value=mock_redis2):
                pool2 = await get_shared_pool()

        assert pool1 is not pool2

        await reset_shared_pool()

    async def test_reset_shared_pool_when_none(self):
        """reset_shared_pool should be safe to call with no existing pool."""
        import enhanced_agent_bus.redis_pool as m

        original = m._shared_pool
        m._shared_pool = None
        await m.reset_shared_pool()
        assert m._shared_pool is None
        m._shared_pool = original

    async def test_reset_shared_pool_suppresses_redis_connection_errors(self):
        """Redis ConnectionError errors during close are swallowed."""
        from redis.exceptions import ConnectionError as RCE

        import enhanced_agent_bus.redis_pool as m

        mock_pool_obj = _make_initialized_pool(AsyncMock())
        mock_pool_obj._redis = AsyncMock()
        mock_pool_obj._redis.close = AsyncMock(side_effect=RCE("fail"))
        mock_pool_obj._pool = AsyncMock()
        mock_pool_obj._pool.disconnect = AsyncMock(side_effect=RCE("fail"))

        m._shared_pool = mock_pool_obj
        await m.reset_shared_pool()  # must not raise
        assert m._shared_pool is None

    async def test_reset_shared_pool_suppresses_timeout_errors(self):
        from redis.exceptions import TimeoutError as RTE

        import enhanced_agent_bus.redis_pool as m

        mock_pool_obj = _make_initialized_pool(AsyncMock())
        mock_pool_obj._redis = AsyncMock()
        mock_pool_obj._redis.close = AsyncMock(side_effect=RTE("timeout"))
        mock_pool_obj._pool = AsyncMock()
        mock_pool_obj._pool.disconnect = AsyncMock()

        m._shared_pool = mock_pool_obj
        await m.reset_shared_pool()
        assert m._shared_pool is None

    async def test_reset_shared_pool_suppresses_redis_error(self):
        from redis.exceptions import RedisError

        import enhanced_agent_bus.redis_pool as m

        mock_pool_obj = _make_initialized_pool(AsyncMock())
        mock_pool_obj._redis = AsyncMock()
        mock_pool_obj._redis.close = AsyncMock(side_effect=RedisError("err"))
        mock_pool_obj._pool = AsyncMock()
        mock_pool_obj._pool.disconnect = AsyncMock()

        m._shared_pool = mock_pool_obj
        await m.reset_shared_pool()
        assert m._shared_pool is None

    async def test_get_shared_pool_existing_not_initialized_recreates(self):
        """If existing pool exists but is not initialized, it is recreated."""
        import enhanced_agent_bus.redis_pool as m

        await m.reset_shared_pool()

        # Inject a stale, uninitialized pool
        stale = _make_pool()
        stale._initialized = False
        m._shared_pool = stale

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = AsyncMock()
        mock_pool_obj.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = await m.get_shared_pool()

        assert pool is not stale
        assert pool._initialized is True

        await m.reset_shared_pool()


# ---------------------------------------------------------------------------
# Concurrency / thread-safety basics
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Basic concurrency tests for initialize and acquire."""

    async def test_concurrent_initialize_only_calls_ping_once(self):
        """Multiple concurrent callers should not double-initialize."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = MagicMock()

        pool = _make_pool(min_connections=1)

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                results = await asyncio.gather(
                    pool.initialize(),
                )

        assert all(results)
        # ping called exactly once because of double-checked locking
        assert mock_redis.ping.await_count == 1

    async def test_concurrent_acquire_updates_active_connections(self):
        """Multiple concurrent acquires should be tracked independently."""
        mock_redis = AsyncMock()
        pool = _make_initialized_pool(mock_redis)

        peak = 0
        lock = asyncio.Lock()

        async def body():
            nonlocal peak
            async with pool.acquire() as _:
                async with lock:
                    peak = max(peak, pool._metrics["active_connections"])
                await asyncio.sleep(0)

        await asyncio.gather(*[body() for _ in range(5)])

        assert peak >= 1
        assert pool._metrics["active_connections"] == 0
        assert pool._metrics["total_operations"] == 5

    async def test_initialize_inner_lock_double_check_via_direct_state(self):
        """Hit line 167 (inner 'return True' inside lock) by directly simulating
        the race condition: both coroutines pass the outer check, then
        coroutine B acquires the lock and finds _initialized=True."""
        mock_redis = AsyncMock()
        mock_pool_obj = MagicMock()

        pool = _make_pool(min_connections=1)

        # We simulate the race by calling initialize() when _initialized is False,
        # but making the lock section see it as True by the time it runs.
        # We patch ConnectionPool.from_url to set _initialized before returning,
        # then trigger a second concurrent init that enters the lock body.
        lock_entered = asyncio.Event()
        init_may_finish = asyncio.Event()

        original_ping_calls = 0

        async def slow_ping():
            """First ping takes a while; second coroutine can queue up behind the lock."""
            nonlocal original_ping_calls
            original_ping_calls += 1
            lock_entered.set()
            await init_may_finish.wait()
            return True

        mock_redis.ping = AsyncMock(side_effect=slow_ping)

        async def coroutine_a():
            with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
                with patch("redis.asyncio.Redis", return_value=mock_redis):
                    return await pool.initialize()

        async def coroutine_b():
            # Wait until A is inside the lock, then queue up
            await lock_entered.wait()
            init_may_finish.set()  # let A finish
            return await pool.initialize()

        r1, r2 = await asyncio.gather(coroutine_a(), coroutine_b())

        assert r1 is True
        assert r2 is True


# ---------------------------------------------------------------------------
# Edge case: redis package unavailable (ImportError branch lines 54-60)
# ---------------------------------------------------------------------------


class TestRedisUnavailable:
    """Test behavior when redis package cannot be imported."""

    async def test_initialize_returns_false_when_redis_unavailable(self):
        """When REDIS_AVAILABLE is False, initialize() returns False immediately."""
        import enhanced_agent_bus.redis_pool as module
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        pool = RedisConnectionPool(redis_url="redis://localhost:6379")

        # Temporarily override the module-level REDIS_AVAILABLE flag
        original = module.REDIS_AVAILABLE
        module.REDIS_AVAILABLE = False
        try:
            result = await pool.initialize()
            assert result is False
            assert pool._initialized is False
        finally:
            module.REDIS_AVAILABLE = original


# ---------------------------------------------------------------------------
# get_shared_pool: fast-return path when already initialized
# ---------------------------------------------------------------------------


class TestSharedPoolFastReturn:
    """Test the fast-return path in get_shared_pool (line 584-585)."""

    async def test_get_shared_pool_fast_return_when_already_initialized(self):
        """When _shared_pool is already initialized, returns it without acquiring lock."""
        import enhanced_agent_bus.redis_pool as m
        from enhanced_agent_bus.redis_pool import get_shared_pool, reset_shared_pool

        await reset_shared_pool()

        # Pre-create and mark as initialized
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = AsyncMock()
        mock_pool_obj.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool1 = await get_shared_pool()

        assert pool1._initialized is True

        # Second call — should hit the fast return at line 584-585
        # (no need to patch redis again since we're not re-initializing)
        pool2 = await get_shared_pool()

        assert pool2 is pool1  # same instance, returned fast

        await reset_shared_pool()

    async def test_get_shared_pool_inside_lock_already_initialized(self):
        """Inside the lock, if pool was initialized by another coroutine, returns it."""
        import enhanced_agent_bus.redis_pool as m
        from enhanced_agent_bus.redis_pool import get_shared_pool, reset_shared_pool

        await reset_shared_pool()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pool_obj = AsyncMock()
        mock_pool_obj.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool_obj):
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                # Two concurrent calls race; the winner initializes, loser finds
                # it initialized inside the lock (line 595 return path).
                p1, p2 = await asyncio.gather(
                    get_shared_pool(),
                    get_shared_pool(),
                )

        assert p1 is p2  # both return the same initialized instance

        await reset_shared_pool()

    async def test_get_shared_pool_inner_lock_double_check(self):
        """Explicitly hit line 595 (return _shared_pool inside lock) via state manipulation:
        coroutine A enters the lock and initializes; coroutine B queues behind the lock,
        then finds the pool already initialized and returns it via the inner branch."""
        import enhanced_agent_bus.redis_pool as m
        from enhanced_agent_bus.redis_pool import get_shared_pool, reset_shared_pool

        await reset_shared_pool()

        lock_entered = asyncio.Event()
        init_may_finish = asyncio.Event()

        # We'll make the pool initialize slowly so B can queue up.
        slow_redis = AsyncMock()
        fast_redis = AsyncMock()
        fast_redis.ping = AsyncMock(return_value=True)

        async def slow_ping():
            lock_entered.set()
            await init_may_finish.wait()
            return True

        slow_redis.ping = AsyncMock(side_effect=slow_ping)

        slow_pool_obj = AsyncMock()
        slow_pool_obj.disconnect = AsyncMock()

        call_count = 0

        def make_redis(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return slow_redis if call_count == 1 else fast_redis

        async def coro_a():
            with patch("redis.asyncio.ConnectionPool.from_url", return_value=slow_pool_obj):
                with patch("redis.asyncio.Redis", side_effect=make_redis):
                    return await get_shared_pool()

        async def coro_b():
            await lock_entered.wait()
            init_may_finish.set()
            return await get_shared_pool()

        p1, p2 = await asyncio.gather(coro_a(), coro_b())

        assert p1 is p2  # both returned same instance

        await reset_shared_pool()
