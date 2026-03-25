"""
ACGS-2 Enhanced Agent Bus - Redis Connection Pool
Constitutional Hash: 608508a9bd224290

High-performance Redis connection pooling for batch operations.
Implements Phase 4-Task 1 acceptance criteria:
- Reuse Redis connections across batch
- Configurable pool size
- Connection health monitoring

Performance Optimizations:
- Connection pool pre-warming to reduce startup latency
- Pre-established connections avoid cold-start penalties
"""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _RedisPoolMetrics(TypedDict, total=False):
    """Type definition for Redis pool metrics."""

    total_connections: int
    active_connections: int
    total_operations: int
    failed_operations: int
    total_latency_ms: float
    created_at: str
    warmed_connections: int
    avg_latency_ms: float


try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

try:
    import redis.asyncio as aioredis
    from redis.exceptions import (
        ConnectionError as RedisConnectionError,
    )
    from redis.exceptions import (
        RedisError,
    )
    from redis.exceptions import (
        TimeoutError as RedisTimeoutError,
    )

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False
    # Fallback exception types for type checking
    RedisError = Exception  # type: ignore[misc, assignment]
    RedisConnectionError = Exception  # type: ignore[misc, assignment]
    RedisTimeoutError = Exception  # type: ignore[misc, assignment]

logger = get_logger(__name__)
_REDIS_POOL_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

# Default pool configuration
DEFAULT_POOL_SIZE = 20
DEFAULT_MIN_CONNECTIONS = 5
DEFAULT_SOCKET_TIMEOUT = 5.0
DEFAULT_SOCKET_CONNECT_TIMEOUT = 5.0
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 0.1


class RedisConnectionPool:
    """
    High-performance Redis connection pool for batch operations.

    Features:
    - Connection reuse across batch operations
    - Configurable pool size (min/max connections)
    - Health monitoring with retry logic
    - Batch operations with pipelining
    - Metrics collection for observability

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_connections: int = DEFAULT_POOL_SIZE,
        min_connections: int = DEFAULT_MIN_CONNECTIONS,
        socket_timeout: float = DEFAULT_SOCKET_TIMEOUT,
        socket_connect_timeout: float = DEFAULT_SOCKET_CONNECT_TIMEOUT,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        decode_responses: bool = True,
    ):
        """
        Initialize Redis connection pool.

        Args:
            redis_url: Redis connection URL
            max_connections: Maximum connections in pool
            min_connections: Minimum connections to maintain
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
            retry_attempts: Number of retry attempts for failed operations
            retry_delay: Delay between retries in seconds
            decode_responses: Whether to decode responses to strings
        """
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.min_connections = min_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.decode_responses = decode_responses
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # Pool and client state
        self._pool: object | None = None
        self._redis: object | None = None
        self._initialized = False
        self._lock = asyncio.Lock()

        # Metrics tracking
        self._metrics: _RedisPoolMetrics = {
            "total_connections": 0,
            "active_connections": 0,
            "total_operations": 0,
            "failed_operations": 0,
            "total_latency_ms": 0.0,
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def initialize(self, pre_warm: bool = True) -> bool:
        """
        Initialize the connection pool.

        Args:
            pre_warm: If True, pre-warm the pool with min_connections to reduce startup latency

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            return True

        if not REDIS_AVAILABLE:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis package not available")
            return False

        async with self._lock:
            if self._initialized:
                return True

            try:
                self._pool = aioredis.ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=self.max_connections,
                    socket_timeout=self.socket_timeout,
                    socket_connect_timeout=self.socket_connect_timeout,
                    decode_responses=self.decode_responses,
                )
                self._redis = aioredis.Redis(connection_pool=self._pool)

                # Verify connection
                await self._redis.ping()  # type: ignore[misc]

                self._initialized = True
                self._metrics["total_connections"] = 1

                # Pre-warm connections to reduce startup latency
                if pre_warm and self.min_connections > 1:
                    warm_count = await self._warm_pool()
                    logger.info(
                        f"[{CONSTITUTIONAL_HASH}] Redis pool pre-warmed: "
                        f"{warm_count} connections established"
                    )

                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] Redis pool initialized: "
                    f"{self.redis_url} (max={self.max_connections}, min={self.min_connections})"
                )
                return True

            except RedisConnectionError as e:
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] Redis connection failed during pool init: {e}"
                )
                self._pool = None
                self._redis = None
                return False
            except RedisTimeoutError as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Redis timeout during pool init: {e}")
                self._pool = None
                self._redis = None
                return False
            except RedisError as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Redis error during pool init: {e}")
                self._pool = None
                self._redis = None
                return False
            except _REDIS_POOL_OPERATION_ERRORS as e:
                # Catch-all for any connection errors (including stdlib ConnectionError)
                logger.error(f"[{CONSTITUTIONAL_HASH}] Unexpected error during pool init: {e}")
                self._pool = None
                self._redis = None
                return False

    async def _warm_pool(self) -> int:
        """
        Pre-warm the connection pool by establishing min_connections.

        This reduces cold-start latency by ensuring connections are ready
        before the first actual request comes in.

        Returns:
            Number of connections successfully warmed
        """
        if not self._redis:
            return 0

        warmed = 0
        tasks = []

        # Create concurrent PING tasks to warm up connections
        for _ in range(self.min_connections):
            tasks.append(self._warm_single_connection())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if result is True:
                warmed += 1
            elif isinstance(result, Exception):
                logger.warning(f"[{CONSTITUTIONAL_HASH}] Connection warm-up warning: {result}")

        self._metrics["total_connections"] = warmed
        self._metrics["warmed_connections"] = warmed
        return warmed

    async def _warm_single_connection(self) -> bool:
        """Warm a single connection by executing a PING."""
        try:
            await self._redis.ping()
            return True
        except RedisConnectionError as e:
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Warm-up connection failed: {e}")
            return False
        except RedisTimeoutError as e:
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Warm-up ping timeout: {e}")
            return False
        except RedisError as e:
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Warm-up ping failed: {e}")
            return False

    async def close(self) -> None:
        """Close the connection pool and release all connections."""
        async with self._lock:
            if self._redis:
                await self._redis.close()
                self._redis = None

            if self._pool:
                await self._pool.disconnect()
                self._pool = None

            self._initialized = False
            logger.info(f"[{CONSTITUTIONAL_HASH}] Redis pool closed")

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the pool.

        Usage:
            async with pool.acquire() as conn:
                await conn.get("key")

        Yields:
            Redis client connection
        """
        if not self._initialized:
            await self.initialize()

        if not self._redis:
            raise ConnectionError("Redis pool not initialized")

        start_time = time.perf_counter()
        self._metrics["active_connections"] += 1

        try:
            yield self._redis
        finally:
            self._metrics["active_connections"] -= 1
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics["total_latency_ms"] += elapsed_ms
            self._metrics["total_operations"] += 1

    async def _ensure_initialized(self) -> str | None:
        """Attempt lazy initialization if the pool has not yet been set up.

        Returns:
            None on success, or an error string describing the failure.
        """
        if self._initialized:
            return None
        try:
            init_success = await self.initialize()
            if not init_success:
                return "Failed to initialize pool"
            return None
        except RedisConnectionError as e:
            return f"Connection failed during init: {e}"
        except RedisTimeoutError as e:
            return f"Timeout during init: {e}"
        except RedisError as e:
            return f"Redis error during init: {e}"
        except _REDIS_POOL_OPERATION_ERRORS as e:
            return f"Unexpected error during init: {e}"

    async def _ping_once(self) -> str | None:
        """Attempt a single Redis PING.

        Returns:
            None on success, or an error string describing the failure.
        """
        try:
            await self._redis.ping()
            return None
        except RedisConnectionError as e:
            return f"Connection failed: {e}"
        except RedisTimeoutError as e:
            return f"Timeout: {e}"
        except RedisError as e:
            return f"Redis error: {e}"
        except _REDIS_POOL_OPERATION_ERRORS as e:
            return f"Unexpected error: {e}"

    async def health_check(self) -> JSONDict:
        """
        Check health of the Redis connection pool.

        Returns:
            Health status dictionary with:
            - healthy: bool
            - constitutional_hash: str
            - pool_stats: dict
            - error: str (if unhealthy)
        """
        health = {
            "healthy": False,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": datetime.now(UTC).isoformat(),
            "pool_stats": {
                "max_connections": self.max_connections,
                "min_connections": self.min_connections,
            },
        }

        init_error = await self._ensure_initialized()
        if init_error is not None:
            health["error"] = init_error
            return health

        if not self._redis:
            health["error"] = "Redis client not available"
            return health

        last_error: str | None = None
        for attempt in range(self.retry_attempts):
            last_error = await self._ping_once()
            if last_error is None:
                health["healthy"] = True
                health["pool_stats"].update(self._get_pool_stats())  # type: ignore[attr-defined]
                return health
            if attempt < self.retry_attempts - 1:
                await asyncio.sleep(self.retry_delay)

        health["error"] = last_error
        return health

    def _get_pool_stats(self) -> JSONDict:
        """Get internal pool statistics."""
        stats = {
            "initialized": self._initialized,
            "max_connections": self.max_connections,
        }

        if self._pool:
            try:
                # Try to get pool info if available
                stats["pool_class"] = self._pool.__class__.__name__
            except AttributeError:
                # Pool class doesn't have expected attributes
                pass

        return stats

    async def batch_get(self, keys: list[str]) -> list[str | None]:
        """
        Batch get multiple keys using pipeline for efficiency.

        Args:
            keys: List of keys to retrieve

        Returns:
            List of values (None for missing keys)
        """
        if not keys:
            return []

        if not self._initialized:
            await self.initialize()

        if not self._redis:
            raise ConnectionError("Redis pool not initialized")

        start_time = time.perf_counter()

        try:
            pipe = self._redis.pipeline()
            for key in keys:
                pipe.get(key)
            results = await pipe.execute()

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics["total_latency_ms"] += elapsed_ms
            self._metrics["total_operations"] += 1

            return list(results)  # type: ignore[arg-type]

        except RedisConnectionError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch get connection failed: {e}")
            raise
        except RedisTimeoutError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch get timeout: {e}")
            raise
        except RedisError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch get failed: {e}")
            raise

    async def batch_set(self, items: list[tuple[str, str, int]]) -> list[bool]:
        """
        Batch set multiple key-value pairs with TTL using pipeline.

        Args:
            items: List of (key, value, ttl_seconds) tuples

        Returns:
            List of success booleans for each operation
        """
        if not items:
            return []

        if not self._initialized:
            await self.initialize()

        if not self._redis:
            raise ConnectionError("Redis pool not initialized")

        start_time = time.perf_counter()

        try:
            pipe = self._redis.pipeline()
            for key, value, ttl in items:
                pipe.setex(key, ttl, value)
            results = await pipe.execute()

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics["total_latency_ms"] += elapsed_ms
            self._metrics["total_operations"] += 1

            return [bool(r) for r in results]

        except RedisConnectionError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch set connection failed: {e}")
            raise
        except RedisTimeoutError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch set timeout: {e}")
            raise
        except RedisError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch set failed: {e}")
            raise

    async def batch_delete(self, keys: list[str]) -> int:
        """
        Batch delete multiple keys.

        Args:
            keys: List of keys to delete

        Returns:
            Number of keys deleted
        """
        if not keys:
            return 0

        if not self._initialized:
            await self.initialize()

        if not self._redis:
            raise ConnectionError("Redis pool not initialized")

        try:
            result = await self._redis.delete(*keys)
            self._metrics["total_operations"] += 1
            return int(result)

        except RedisConnectionError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch delete connection failed: {e}")
            raise
        except RedisTimeoutError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch delete timeout: {e}")
            raise
        except RedisError as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Batch delete failed: {e}")
            raise

    def get_metrics(self) -> JSONDict:
        """
        Get connection pool metrics.

        Returns:
            Dictionary with pool metrics including:
            - total_connections
            - active_connections
            - total_operations
            - failed_operations
            - avg_latency_ms
        """
        metrics: JSONDict = dict(self._metrics)

        if metrics["total_operations"] > 0:
            metrics["avg_latency_ms"] = metrics["total_latency_ms"] / metrics["total_operations"]
        else:
            metrics["avg_latency_ms"] = 0.0

        return metrics

    async def __aenter__(self) -> "RedisConnectionPool":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Singleton instance for shared pool
_shared_pool: RedisConnectionPool | None = None
_shared_pool_lock = asyncio.Lock()


async def get_shared_pool(
    redis_url: str = "redis://localhost:6379",
    max_connections: int = DEFAULT_POOL_SIZE,
) -> RedisConnectionPool:
    """
    Get or create shared Redis connection pool singleton.

    Args:
        redis_url: Redis connection URL (only used for first call)
        max_connections: Max pool size (only used for first call)

    Returns:
        Shared RedisConnectionPool instance
    """
    global _shared_pool

    if _shared_pool is not None and _shared_pool._initialized:
        return _shared_pool

    async with _shared_pool_lock:
        if _shared_pool is None or not _shared_pool._initialized:
            _shared_pool = RedisConnectionPool(
                redis_url=redis_url,
                max_connections=max_connections,
            )
            await _shared_pool.initialize()

        return _shared_pool


async def reset_shared_pool() -> None:
    """Reset the shared pool singleton (for testing)."""
    global _shared_pool

    async with _shared_pool_lock:
        if _shared_pool is not None:
            try:
                await _shared_pool.close()
            except (RedisConnectionError, RedisTimeoutError, RedisError):
                # Suppress Redis errors during cleanup
                pass
            _shared_pool = None


__all__ = [
    "DEFAULT_MIN_CONNECTIONS",
    "DEFAULT_POOL_SIZE",
    "REDIS_AVAILABLE",
    "RedisConnectionPool",
    "get_shared_pool",
    "reset_shared_pool",
]
