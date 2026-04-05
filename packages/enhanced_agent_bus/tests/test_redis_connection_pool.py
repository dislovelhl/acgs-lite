"""
ACGS-2 Enhanced Agent Bus - Redis Connection Pool Tests
Constitutional Hash: 608508a9bd224290

TDD tests for Redis connection pooling in batch operations.
Tests Phase 4-Task 1 acceptance criteria:
- Reuse Redis connections across batch
- Configurable pool size
- Connection health monitoring
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Import centralized constitutional hash
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


class TestRedisConnectionPoolConfig:
    """Test Redis connection pool configuration."""

    async def test_default_pool_size(self):
        """Test default connection pool size is reasonable."""
        from enhanced_agent_bus.redis_pool import DEFAULT_POOL_SIZE, RedisConnectionPool

        assert DEFAULT_POOL_SIZE >= 10
        assert DEFAULT_POOL_SIZE <= 100

    async def test_configurable_pool_size(self):
        """Test pool size can be configured."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        pool = RedisConnectionPool(
            redis_url="redis://localhost:6379",
            max_connections=50,
        )
        assert pool.max_connections == 50

    async def test_configurable_min_connections(self):
        """Test minimum pool connections can be configured."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        pool = RedisConnectionPool(
            redis_url="redis://localhost:6379",
            min_connections=5,
            max_connections=50,
        )
        assert pool.min_connections == 5

    async def test_pool_has_constitutional_hash(self):
        """Test pool tracks constitutional hash for compliance."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        pool = RedisConnectionPool(redis_url="redis://localhost:6379")
        assert pool.constitutional_hash == CONSTITUTIONAL_HASH


class TestRedisConnectionPoolAcquisition:
    """Test Redis connection acquisition and release."""

    async def test_acquire_connection(self):
        """Test acquiring a connection from pool."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url") as mock_pool:
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                async with pool.acquire() as conn:
                    assert conn is not None

    async def test_connection_reuse_across_batch(self):
        """Test connections are reused across batch operations."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value = mock_pool

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    max_connections=5,
                )
                await pool.initialize()

                # Multiple acquisitions should reuse the same underlying pool
                connections_used = []
                for _ in range(10):
                    async with pool.acquire() as conn:
                        connections_used.append(id(conn))

                # Should only create pool once
                mock_pool_cls.assert_called_once()

    async def test_concurrent_connection_acquisition(self):
        """Test multiple concurrent connections from pool."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value = mock_pool

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.get = AsyncMock(return_value="test_value")

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    max_connections=10,
                )
                await pool.initialize()

                async def use_connection(i: int):
                    async with pool.acquire() as conn:
                        result = await conn.get(f"key_{i}")
                        return result

                # Run 20 concurrent operations
                results = await asyncio.gather(*[use_connection(i) for i in range(20)])
                assert len(results) == 20


class TestRedisConnectionPoolHealthMonitoring:
    """Test Redis connection health monitoring."""

    async def test_health_check_healthy(self):
        """Test health check returns healthy for good connection."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                health = await pool.health_check()
                assert health["healthy"] is True
                assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_health_check_unhealthy(self):
        """Test health check returns unhealthy for failed connection."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                health = await pool.health_check()
                assert health["healthy"] is False
                assert "error" in health

    async def test_health_check_includes_pool_stats(self):
        """Test health check includes pool statistics."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    max_connections=20,
                )
                await pool.initialize()

                health = await pool.health_check()
                assert "pool_stats" in health
                assert "max_connections" in health["pool_stats"]
                assert health["pool_stats"]["max_connections"] == 20

    async def test_connection_retry_on_failure(self):
        """Test connection is retried on transient failure."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        call_count = 0

        async def flaky_ping():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Transient failure")
            return True

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = flaky_ping

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    retry_attempts=3,
                )
                await pool.initialize()

                # Should succeed after retry
                health = await pool.health_check()
                assert health["healthy"] is True


class TestRedisConnectionPoolBatchOperations:
    """Test Redis connection pool for batch operations."""

    async def test_batch_get_uses_pipeline(self):
        """Test batch get operations use Redis pipeline for efficiency."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            mock_pipeline = AsyncMock()
            mock_pipeline.get = MagicMock(return_value=mock_pipeline)
            mock_pipeline.execute = AsyncMock(return_value=["value1", "value2", "value3"])
            mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                keys = ["key1", "key2", "key3"]
                results = await pool.batch_get(keys)

                assert len(results) == 3
                mock_redis.pipeline.assert_called()

    async def test_batch_set_uses_pipeline(self):
        """Test batch set operations use Redis pipeline for efficiency."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            mock_pipeline = AsyncMock()
            mock_pipeline.setex = MagicMock(return_value=mock_pipeline)
            mock_pipeline.execute = AsyncMock(return_value=[True, True, True])
            mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                items = [
                    ("key1", "value1", 3600),
                    ("key2", "value2", 3600),
                    ("key3", "value3", 3600),
                ]
                results = await pool.batch_set(items)

                assert all(results)
                mock_redis.pipeline.assert_called()

    async def test_batch_operation_with_connection_pool_reuse(self):
        """Test batch operations reuse connection pool."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value = mock_pool

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            mock_pipeline = AsyncMock()
            mock_pipeline.get = MagicMock(return_value=mock_pipeline)
            mock_pipeline.execute = AsyncMock(return_value=["v1", "v2"])
            mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                # Multiple batch operations
                await pool.batch_get(["k1", "k2"])
                await pool.batch_get(["k3", "k4"])
                await pool.batch_get(["k5", "k6"])

                # Pool should be created only once
                mock_pool_cls.assert_called_once()


class TestRedisConnectionPoolCleanup:
    """Test Redis connection pool cleanup."""

    async def test_pool_close(self):
        """Test pool closes all connections on shutdown."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url") as mock_pool_cls:
            mock_pool = AsyncMock()
            mock_pool.disconnect = AsyncMock()
            mock_pool_cls.return_value = mock_pool

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()
                await pool.close()

                mock_redis.close.assert_called_once()
                mock_pool.disconnect.assert_called_once()

    async def test_context_manager_cleanup(self):
        """Test pool cleans up when used as context manager."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url") as mock_pool_cls:
            mock_pool = AsyncMock()
            mock_pool.disconnect = AsyncMock()
            mock_pool_cls.return_value = mock_pool

            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                async with RedisConnectionPool(redis_url="redis://localhost:6379") as pool:
                    assert pool is not None

                mock_redis.close.assert_called_once()


class TestRedisConnectionPoolSingleton:
    """Test Redis connection pool singleton pattern."""

    async def test_get_shared_pool_returns_singleton(self):
        """Test get_shared_pool returns singleton instance."""
        from enhanced_agent_bus.redis_pool import (
            get_shared_pool,
            reset_shared_pool,
        )

        # Reset to ensure clean state (use try/except to handle any errors)
        try:
            await reset_shared_pool()
        except (RuntimeError, ConnectionError, OSError):
            pass

        mock_pool = MagicMock()
        mock_pool.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool1 = await get_shared_pool()
                pool2 = await get_shared_pool()

                assert pool1 is pool2

        # Cleanup
        try:
            await reset_shared_pool()
        except (RuntimeError, ConnectionError, OSError):
            pass

    async def test_reset_shared_pool(self):
        """Test reset_shared_pool clears singleton."""
        from enhanced_agent_bus.redis_pool import (
            get_shared_pool,
            reset_shared_pool,
        )

        # Reset to ensure clean state
        try:
            await reset_shared_pool()
        except (RuntimeError, ConnectionError, OSError):
            pass

        mock_pool = MagicMock()
        mock_pool.disconnect = AsyncMock()

        with patch("redis.asyncio.ConnectionPool.from_url", return_value=mock_pool):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.close = AsyncMock()

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool1 = await get_shared_pool()
                await reset_shared_pool()
                pool2 = await get_shared_pool()

                assert pool1 is not pool2

        # Cleanup
        try:
            await reset_shared_pool()
        except (RuntimeError, ConnectionError, OSError):
            pass


class TestRedisConnectionPoolPreWarming:
    """Test Redis connection pool pre-warming for startup latency reduction."""

    async def test_pre_warming_enabled_by_default(self):
        """Test pool pre-warms connections on initialization by default."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    min_connections=5,
                )
                await pool.initialize(pre_warm=True)

                # With min_connections=5, should have called ping multiple times
                # Initial ping + pre-warming pings
                assert mock_redis.ping.call_count >= pool.min_connections

    async def test_pre_warming_can_be_disabled(self):
        """Test pool pre-warming can be disabled."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    min_connections=5,
                )
                await pool.initialize(pre_warm=False)

                # Should only call ping once for initial connection check
                assert mock_redis.ping.call_count == 1

    async def test_pre_warming_tracks_warmed_connections(self):
        """Test pre-warming tracks number of warmed connections in metrics."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    min_connections=5,
                )
                await pool.initialize(pre_warm=True)

                metrics = pool.get_metrics()
                assert "warmed_connections" in metrics
                assert metrics["warmed_connections"] >= 1

    async def test_pre_warming_handles_partial_failures(self):
        """Test pre-warming continues even if some connections fail."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        call_count = 0

        async def flaky_ping():
            nonlocal call_count
            call_count += 1
            # First call succeeds (init check), then alternate success/failure
            if call_count == 1:
                return True
            if call_count % 2 == 0:
                raise ConnectionError("Connection failed")
            return True

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = flaky_ping

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    min_connections=5,
                )
                # Should not raise even with partial failures
                await pool.initialize(pre_warm=True)

                metrics = pool.get_metrics()
                # Should have warmed at least some connections
                assert metrics.get("warmed_connections", 0) >= 1

    async def test_pre_warming_skipped_with_single_min_connection(self):
        """Test pre-warming is skipped when min_connections is 1."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(
                    redis_url="redis://localhost:6379",
                    min_connections=1,  # Skip pre-warming with min_connections <= 1
                )
                await pool.initialize(pre_warm=True)

                # Only initial connection check - pre-warming skipped
                assert mock_redis.ping.call_count == 1

    async def test_pre_warming_logs_status(self):
        """Test pre-warming logs the number of warmed connections."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                with patch("enhanced_agent_bus.redis_pool.logger") as mock_logger:
                    pool = RedisConnectionPool(
                        redis_url="redis://localhost:6379",
                        min_connections=3,
                    )
                    await pool.initialize(pre_warm=True)

                    # Should log pre-warming info
                    info_calls = [str(c) for c in mock_logger.info.call_args_list]
                    assert any("pre-warmed" in str(call).lower() for call in info_calls)


class TestRedisConnectionPoolMetrics:
    """Test Redis connection pool metrics collection."""

    async def test_pool_tracks_connection_count(self):
        """Test pool tracks active connection count."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                metrics = pool.get_metrics()
                assert "total_connections" in metrics
                assert "active_connections" in metrics

    async def test_pool_tracks_operation_latency(self):
        """Test pool tracks operation latency."""
        from enhanced_agent_bus.redis_pool import RedisConnectionPool

        with patch("redis.asyncio.ConnectionPool.from_url"):
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            mock_redis.get = AsyncMock(return_value="test_value")

            with patch("redis.asyncio.Redis", return_value=mock_redis):
                pool = RedisConnectionPool(redis_url="redis://localhost:6379")
                await pool.initialize()

                async with pool.acquire() as conn:
                    await conn.get("test_key")

                metrics = pool.get_metrics()
                assert "avg_latency_ms" in metrics
