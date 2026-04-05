"""
ACGS-2 Enhanced Agent Bus - Circuit Breaker Redis Client Coverage Tests
Constitutional Hash: 608508a9bd224290

Targets >=90% coverage on cb_redis_client.py by exercising all branches
and edge cases in CircuitBreakerRedisClient.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cb(can_execute: bool = True):
    """Create a mock ServiceCircuitBreaker."""
    cb = MagicMock()
    cb.can_execute = AsyncMock(return_value=can_execute)
    cb.record_success = AsyncMock()
    cb.record_failure = AsyncMock()
    cb.record_rejection = AsyncMock()
    cb.get_status = MagicMock(
        return_value={
            "state": "closed",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
    )
    cb.state = MagicMock()
    cb.state.value = "closed"
    cb.metrics = MagicMock()
    cb.metrics.__dict__ = {"total_calls": 0, "successful_calls": 0, "failed_calls": 0}
    return cb


def _make_redis():
    """Create a mock aioredis client."""
    r = AsyncMock()
    r.ping = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.setex = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    pipe = AsyncMock()
    pipe.get = MagicMock()
    pipe.setex = MagicMock()
    pipe.execute = AsyncMock(return_value=[])
    r.pipeline = MagicMock(return_value=pipe)
    r.close = AsyncMock()
    return r


async def _make_client(redis_mock=None, cb_mock=None, *, connect_fail=False):
    """
    Build an initialized CircuitBreakerRedisClient with all externals mocked.
    """
    from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

    client = CircuitBreakerRedisClient()

    if connect_fail:
        # Simulate Redis connection failure during initialize
        with (
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb_mock or _make_cb()),
            ),
            patch("redis.asyncio.from_url", side_effect=ConnectionError("refused")),
        ):
            await client.initialize()
    else:
        r = redis_mock or _make_redis()
        with (
            patch("redis.asyncio.from_url", return_value=r),
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb_mock or _make_cb()),
            ),
        ):
            await client.initialize()
    return client


# ---------------------------------------------------------------------------
# __init__ / initialize
# ---------------------------------------------------------------------------


class TestInitialize:
    async def test_default_attributes(self):
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        client = CircuitBreakerRedisClient()
        assert client.redis_url == "redis://localhost:6379"
        assert client.max_connections == 20
        assert client.socket_timeout == 1.0
        assert client.decode_responses is True
        assert client.constitutional_hash == CONSTITUTIONAL_HASH
        assert client._redis is None
        assert client._circuit_breaker is None
        assert not client._initialized
        assert client._degraded_operations == 0
        assert client._bypass_count == 0

    async def test_custom_attributes(self):
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        client = CircuitBreakerRedisClient(
            redis_url="redis://custom:6380",
            max_connections=10,
            socket_timeout=2.5,
            decode_responses=False,
        )
        assert client.redis_url == "redis://custom:6380"
        assert client.max_connections == 10
        assert client.socket_timeout == 2.5
        assert client.decode_responses is False

    async def test_initialize_success(self):
        client = await _make_client()
        assert client._initialized is True
        assert client._redis is not None
        assert client._circuit_breaker is not None

    async def test_initialize_idempotent(self):
        """Calling initialize a second time is a no-op."""
        client = await _make_client()
        first_redis = client._redis
        # Second call should return early without reassigning _redis
        await client.initialize()
        assert client._redis is first_redis

    async def test_initialize_connection_failure_degraded_mode(self):
        """If Redis connection fails, client enters degraded mode."""
        client = await _make_client(connect_fail=True)
        assert client._initialized is True
        assert client._redis is None

    async def test_initialize_import_error_raises(self):
        """If redis package is unavailable, ImportError is re-raised."""
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        client = CircuitBreakerRedisClient()
        with (
            patch.dict(
                "sys.modules",
                {"redis": None, "redis.asyncio": None},
            ),
            pytest.raises(ImportError),
        ):
            # We patch the import inside initialize by patching builtins import
            # Easier: patch redis.asyncio directly to raise ImportError
            with patch(
                "redis.asyncio.from_url",
                side_effect=ImportError("no redis"),
            ):
                await client.initialize()


# ---------------------------------------------------------------------------
# close / context manager
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close_with_awaitable_close(self):
        """close() awaits redis.close() when it returns a coroutine."""
        client = await _make_client()
        r = client._redis
        await client.close()
        r.close.assert_called_once()
        assert client._redis is None
        assert client._initialized is False

    async def test_close_without_redis(self):
        """close() is safe when _redis is None."""
        client = await _make_client(connect_fail=True)
        await client.close()  # Should not raise
        assert client._initialized is False

    async def test_close_non_awaitable_close(self):
        """close() handles TypeError/AttributeError from redis.close()."""
        client = await _make_client()
        # Replace close() with something that raises TypeError when called
        client._redis.close = MagicMock(side_effect=TypeError("not awaitable"))
        # Should not raise; TypeError is caught in the except branch (lines 111-113)
        await client.close()
        assert client._redis is None

    async def test_close_attribute_error_from_close(self):
        """close() handles AttributeError from redis.close()."""
        client = await _make_client()
        client._redis.close = MagicMock(side_effect=AttributeError("no close"))
        await client.close()
        assert client._redis is None

    async def test_close_returns_non_awaitable_skips_await(self):
        """close() skips await when close() returns a non-awaitable (branch 109->115)."""
        client = await _make_client()
        # close() returns a plain string — no __await__, so the if branch is False
        client._redis.close = MagicMock(return_value="not_a_coro")
        await client.close()
        assert client._redis is None

    async def test_context_manager(self):
        """async context manager initializes and closes."""
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        r = _make_redis()
        cb = _make_cb()
        with (
            patch("redis.asyncio.from_url", return_value=r),
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb),
            ),
        ):
            async with CircuitBreakerRedisClient() as client:
                assert client._initialized is True
        # After exit, initialized is False
        assert client._initialized is False


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestGet:
    async def test_get_success(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        r.get = AsyncMock(return_value="hello")
        client = await _make_client(r, cb)

        result = await client.get("mykey")
        assert result == "hello"
        cb.record_success.assert_called_once()

    async def test_get_no_redis_bypasses(self):
        """Returns None and increments bypass_count when no redis connection."""
        client = await _make_client(connect_fail=True)
        # Ensure circuit breaker exists so we can call can_execute safely
        result = await client.get("key")
        assert result is None
        assert client._bypass_count == 1

    async def test_get_circuit_open_bypasses(self):
        """Returns None (fail-open) when circuit is open."""
        cb = _make_cb(can_execute=False)
        r = _make_redis()
        client = await _make_client(r, cb)

        result = await client.get("key")
        assert result is None
        assert client._bypass_count == 1
        cb.record_rejection.assert_called_once()

    async def test_get_operation_failure(self):
        """On redis error, records failure and returns None."""
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        r.get = AsyncMock(side_effect=RuntimeError("redis down"))
        client = await _make_client(r, cb)

        result = await client.get("key")
        assert result is None
        assert client._degraded_operations == 1
        cb.record_failure.assert_called_once()

    async def test_get_auto_initializes(self):
        """get() calls initialize() if not yet initialized."""
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        r = _make_redis()
        r.get = AsyncMock(return_value="auto_init_value")
        cb = _make_cb(can_execute=True)

        client = CircuitBreakerRedisClient()
        assert not client._initialized

        with (
            patch("redis.asyncio.from_url", return_value=r),
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb),
            ),
        ):
            result = await client.get("key")

        assert result == "auto_init_value"
        assert client._initialized is True


# ---------------------------------------------------------------------------
# set()
# ---------------------------------------------------------------------------


class TestSet:
    async def test_set_with_expiry(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        client = await _make_client(r, cb)

        result = await client.set("k", "v", ex=60)
        assert result is True
        r.setex.assert_called_once_with("k", 60, "v")
        cb.record_success.assert_called_once()

    async def test_set_without_expiry(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        client = await _make_client(r, cb)

        result = await client.set("k", "v")
        assert result is True
        r.set.assert_called_once_with("k", "v")
        cb.record_success.assert_called_once()

    async def test_set_no_redis_bypasses(self):
        client = await _make_client(connect_fail=True)
        result = await client.set("k", "v")
        assert result is False
        assert client._bypass_count == 1

    async def test_set_circuit_open_bypasses(self):
        cb = _make_cb(can_execute=False)
        r = _make_redis()
        client = await _make_client(r, cb)

        result = await client.set("k", "v")
        assert result is False
        assert client._bypass_count == 1
        cb.record_rejection.assert_called_once()

    async def test_set_operation_failure(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        r.set = AsyncMock(side_effect=ConnectionError("broken pipe"))
        client = await _make_client(r, cb)

        result = await client.set("k", "v")
        assert result is False
        assert client._degraded_operations == 1
        cb.record_failure.assert_called_once()

    async def test_set_auto_initializes(self):
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        r = _make_redis()
        cb = _make_cb(can_execute=True)
        client = CircuitBreakerRedisClient()

        with (
            patch("redis.asyncio.from_url", return_value=r),
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb),
            ),
        ):
            result = await client.set("k", "v", ex=10)

        assert result is True


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_delete_success(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        r.delete = AsyncMock(return_value=2)
        client = await _make_client(r, cb)

        result = await client.delete("k1", "k2")
        assert result == 2
        cb.record_success.assert_called_once()

    async def test_delete_no_keys(self):
        """Calling delete() with no keys returns 0 immediately."""
        client = await _make_client()
        result = await client.delete()
        assert result == 0

    async def test_delete_no_redis_returns_zero(self):
        client = await _make_client(connect_fail=True)
        result = await client.delete("k")
        assert result == 0

    async def test_delete_circuit_open_bypasses(self):
        cb = _make_cb(can_execute=False)
        r = _make_redis()
        client = await _make_client(r, cb)

        result = await client.delete("k")
        assert result == 0
        assert client._bypass_count == 1
        cb.record_rejection.assert_called_once()

    async def test_delete_operation_failure(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        r.delete = AsyncMock(side_effect=TimeoutError("timeout"))
        client = await _make_client(r, cb)

        result = await client.delete("k")
        assert result == 0
        assert client._degraded_operations == 1
        cb.record_failure.assert_called_once()

    async def test_delete_auto_initializes(self):
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        r = _make_redis()
        r.delete = AsyncMock(return_value=1)
        cb = _make_cb(can_execute=True)
        client = CircuitBreakerRedisClient()

        with (
            patch("redis.asyncio.from_url", return_value=r),
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb),
            ),
        ):
            result = await client.delete("mykey")

        assert result == 1


# ---------------------------------------------------------------------------
# batch_get()
# ---------------------------------------------------------------------------


class TestBatchGet:
    async def test_batch_get_empty_list(self):
        client = await _make_client()
        result = await client.batch_get([])
        assert result == []

    async def test_batch_get_success(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        pipe = r.pipeline.return_value
        pipe.execute = AsyncMock(return_value=["v1", "v2"])
        client = await _make_client(r, cb)

        result = await client.batch_get(["k1", "k2"])
        assert result == ["v1", "v2"]
        cb.record_success.assert_called_once()

    async def test_batch_get_no_redis_bypasses(self):
        client = await _make_client(connect_fail=True)
        result = await client.batch_get(["k1", "k2"])
        assert result == [None, None]
        assert client._bypass_count == 1

    async def test_batch_get_circuit_open_bypasses(self):
        cb = _make_cb(can_execute=False)
        r = _make_redis()
        client = await _make_client(r, cb)

        result = await client.batch_get(["k1", "k2", "k3"])
        assert result == [None, None, None]
        assert client._bypass_count == 1
        cb.record_rejection.assert_called_once()

    async def test_batch_get_operation_failure(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        pipe = r.pipeline.return_value
        pipe.execute = AsyncMock(side_effect=OSError("pipe broken"))
        client = await _make_client(r, cb)

        result = await client.batch_get(["k1", "k2"])
        assert result == [None, None]
        assert client._degraded_operations == 1
        cb.record_failure.assert_called_once()

    async def test_batch_get_auto_initializes(self):
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        r = _make_redis()
        pipe = r.pipeline.return_value
        pipe.execute = AsyncMock(return_value=["val"])
        cb = _make_cb(can_execute=True)
        client = CircuitBreakerRedisClient()

        with (
            patch("redis.asyncio.from_url", return_value=r),
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb),
            ),
        ):
            result = await client.batch_get(["k"])

        assert result == ["val"]


# ---------------------------------------------------------------------------
# batch_set()
# ---------------------------------------------------------------------------


class TestBatchSet:
    async def test_batch_set_empty_list(self):
        client = await _make_client()
        result = await client.batch_set([])
        assert result == []

    async def test_batch_set_success(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        pipe = r.pipeline.return_value
        pipe.execute = AsyncMock(return_value=[True, True])
        client = await _make_client(r, cb)

        result = await client.batch_set([("k1", "v1", 60), ("k2", "v2", 120)])
        assert result == [True, True]
        cb.record_success.assert_called_once()

    async def test_batch_set_no_redis_bypasses(self):
        client = await _make_client(connect_fail=True)
        result = await client.batch_set([("k1", "v1", 60)])
        assert result == [False]
        assert client._bypass_count == 1

    async def test_batch_set_circuit_open_bypasses(self):
        cb = _make_cb(can_execute=False)
        r = _make_redis()
        client = await _make_client(r, cb)

        result = await client.batch_set([("k1", "v1", 60), ("k2", "v2", 60)])
        assert result == [False, False]
        assert client._bypass_count == 1
        cb.record_rejection.assert_called_once()

    async def test_batch_set_operation_failure(self):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        pipe = r.pipeline.return_value
        pipe.execute = AsyncMock(side_effect=ValueError("bad value"))
        client = await _make_client(r, cb)

        result = await client.batch_set([("k1", "v1", 60)])
        assert result == [False]
        assert client._degraded_operations == 1
        cb.record_failure.assert_called_once()

    async def test_batch_set_auto_initializes(self):
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        r = _make_redis()
        pipe = r.pipeline.return_value
        pipe.execute = AsyncMock(return_value=[True])
        cb = _make_cb(can_execute=True)
        client = CircuitBreakerRedisClient()

        with (
            patch("redis.asyncio.from_url", return_value=r),
            patch(
                "enhanced_agent_bus.cb_redis_client.get_service_circuit_breaker",
                new=AsyncMock(return_value=cb),
            ),
        ):
            result = await client.batch_set([("k", "v", 30)])

        assert result == [True]

    async def test_batch_set_falsy_results_become_false(self):
        """0 / None in pipeline results should become False."""
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        pipe = r.pipeline.return_value
        pipe.execute = AsyncMock(return_value=[0, None, 1])
        client = await _make_client(r, cb)

        result = await client.batch_set([("k1", "v1", 1), ("k2", "v2", 1), ("k3", "v3", 1)])
        assert result == [False, False, True]


# ---------------------------------------------------------------------------
# health_check()
# ---------------------------------------------------------------------------


class TestHealthCheck:
    async def test_health_check_healthy_redis(self):
        cb = _make_cb()
        r = _make_redis()
        client = await _make_client(r, cb)

        health = await client.health_check()

        assert health["service"] == "redis_cache"
        assert health["healthy"] is True
        assert health["redis_status"] == "healthy"
        assert health["fallback_strategy"] == "bypass"
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "circuit_state" in health
        assert "circuit_metrics" in health
        assert "client_metrics" in health
        assert "timestamp" in health

    async def test_health_check_degraded_mode(self):
        """Health check when no Redis connection."""
        client = await _make_client(connect_fail=True)
        # _circuit_breaker is still set even in degraded mode
        health = await client.health_check()

        assert health["healthy"] is False
        assert health["redis_status"] == "not_connected"
        assert health["degraded_mode"] is True

    async def test_health_check_redis_ping_failure(self):
        """Health check when Redis exists but ping fails with a _REDIS_OPERATION_ERRORS member."""
        cb = _make_cb()
        r = _make_redis()
        # Initialize succeeds (first ping passes), then health_check ping fails
        ping_calls = [None]  # first call returns None (success), second raises

        async def ping_side_effect():
            if ping_calls:
                ping_calls.pop()
                return True
            raise ConnectionError("ping failed")

        r.ping = ping_side_effect
        client = await _make_client(r, cb)

        # Now override _redis.ping to fail on the health_check call
        client._redis.ping = AsyncMock(side_effect=ConnectionError("health ping failed"))

        health = await client.health_check()

        assert health["healthy"] is False
        assert health["redis_status"] == "unhealthy"
        assert "error" in health

    async def test_health_check_no_circuit_breaker(self):
        """health_check when circuit_breaker not yet set — circuit_state defaults to 'unknown'."""
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        client = CircuitBreakerRedisClient()
        # Do not initialize — _circuit_breaker is None
        health = await client.health_check()

        # circuit_state defaults to "unknown" (always present in the dict)
        assert health["circuit_state"] == "unknown"
        # circuit_metrics is NOT set when _circuit_breaker is None
        assert "circuit_metrics" not in health
        assert health["healthy"] is False


# ---------------------------------------------------------------------------
# get_circuit_status()
# ---------------------------------------------------------------------------


class TestGetCircuitStatus:
    async def test_get_circuit_status_initialized(self):
        cb = _make_cb()
        client = await _make_client(cb_mock=cb)

        status = client.get_circuit_status()
        assert isinstance(status, dict)

    async def test_get_circuit_status_not_initialized(self):
        """Returns error dict when circuit breaker is None."""
        from enhanced_agent_bus.cb_redis_client import CircuitBreakerRedisClient

        client = CircuitBreakerRedisClient()
        status = client.get_circuit_status()
        assert "error" in status
        assert status["error"] == "Circuit breaker not initialized"


# ---------------------------------------------------------------------------
# Error-type coverage: each member of _REDIS_OPERATION_ERRORS
# ---------------------------------------------------------------------------


class TestErrorTypes:
    @pytest.mark.parametrize(
        "exc_class",
        [
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            OSError,
            TimeoutError,
            ConnectionError,
        ],
    )
    async def test_get_various_error_types(self, exc_class):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        r.get = AsyncMock(side_effect=exc_class("error"))
        client = await _make_client(r, cb)

        result = await client.get("key")
        assert result is None
        assert client._degraded_operations == 1

    @pytest.mark.parametrize(
        "exc_class",
        [
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            OSError,
            TimeoutError,
            ConnectionError,
        ],
    )
    async def test_set_various_error_types(self, exc_class):
        cb = _make_cb(can_execute=True)
        r = _make_redis()
        r.set = AsyncMock(side_effect=exc_class("error"))
        client = await _make_client(r, cb)

        result = await client.set("key", "value")
        assert result is False
        assert client._degraded_operations == 1


# ---------------------------------------------------------------------------
# __all__ export
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports(self):
        import enhanced_agent_bus.cb_redis_client as mod

        assert "CircuitBreakerRedisClient" in mod.__all__
