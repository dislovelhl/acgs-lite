"""
ACGS-2 Enhanced Agent Bus - Circuit Breaker Redis Client
Constitutional Hash: cdd01ef066bc6cf2

Redis Client with circuit breaker protection implementing FAIL-OPEN (BYPASS) strategy.
When the circuit is open, cache operations are bypassed and the system continues
to function without caching.
Split from circuit_breaker_clients.py for improved maintainability.
"""

from datetime import UTC, datetime

# Import centralized constitutional hash
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import circuit breaker components
from .circuit_breaker import (
    ServiceCircuitBreaker,
    get_service_circuit_breaker,
)

logger = get_logger(__name__)
_REDIS_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class CircuitBreakerRedisClient:
    """
    Redis Client with circuit breaker protection.

    Implements FAIL-OPEN (BYPASS) strategy for graceful degradation.
    When the circuit is open, cache operations are bypassed and
    the system continues to function without caching.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_connections: int = 20,
        socket_timeout: float = 1.0,
        decode_responses: bool = True,
    ):
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.decode_responses = decode_responses
        self.constitutional_hash = CONSTITUTIONAL_HASH

        self._redis: object | None = None
        self._circuit_breaker: ServiceCircuitBreaker | None = None
        self._initialized = False

        # Degraded mode metrics
        self._degraded_operations = 0
        self._bypass_count = 0

    async def initialize(self) -> None:
        """Initialize the Redis client with circuit breaker."""
        if self._initialized:
            return

        try:
            import redis.asyncio as aioredis

            # from_url is synchronous, returns a client that has async methods
            self._redis = aioredis.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                socket_timeout=self.socket_timeout,
                decode_responses=self.decode_responses,
            )
            await self._redis.ping()
        except ImportError:
            logger.error(f"[{CONSTITUTIONAL_HASH}] redis package not available")
            raise
        except _REDIS_OPERATION_ERRORS as e:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Redis connection failed, operating in degraded mode: {e}"
            )
            self._redis = None

        # Get or create the circuit breaker for Redis
        self._circuit_breaker = await get_service_circuit_breaker("redis_cache")
        self._initialized = True

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Circuit-protected Redis client initialized "
            f"(url={self.redis_url}, fail_open=True)"
        )

    async def close(self) -> None:
        """Close the Redis client."""
        if self._redis:
            try:
                # Handle both real redis clients and mocks
                close_coro = self._redis.close()
                if hasattr(close_coro, "__await__"):
                    await close_coro
            except (TypeError, AttributeError):
                # Handle mocked clients that aren't awaitable
                pass
            finally:
                self._redis = None
        self._initialized = False

    async def __aenter__(self) -> "CircuitBreakerRedisClient":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def get(self, key: str) -> str | None:
        """
        Get a value from Redis with circuit breaker protection.

        FAIL-OPEN: Returns None if circuit is open or operation fails.

        Args:
            key: Redis key to retrieve

        Returns:
            Value if found and circuit is closed, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        if not self._redis:
            # No Redis connection, bypass
            self._bypass_count += 1
            return None

        # Check circuit breaker
        if not await self._circuit_breaker.can_execute():
            # FAIL-OPEN: Bypass cache when circuit is open
            await self._circuit_breaker.record_rejection()
            self._bypass_count += 1
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Redis circuit breaker OPEN - bypassing GET for {key}"
            )
            return None

        try:
            result = await self._redis.get(key)
            await self._circuit_breaker.record_success()
            return str(result) if result is not None else None
        except _REDIS_OPERATION_ERRORS as e:
            await self._circuit_breaker.record_failure(e, type(e).__name__)
            self._degraded_operations += 1
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis GET failed for {key}: {e}")
            return None

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """
        Set a value in Redis with circuit breaker protection.

        FAIL-OPEN: Returns False if circuit is open or operation fails.
        The caller should continue without caching.

        Args:
            key: Redis key
            value: Value to set
            ex: Expiry time in seconds

        Returns:
            True if successful, False if bypassed or failed
        """
        if not self._initialized:
            await self.initialize()

        if not self._redis:
            self._bypass_count += 1
            return False

        if not await self._circuit_breaker.can_execute():
            await self._circuit_breaker.record_rejection()
            self._bypass_count += 1
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Redis circuit breaker OPEN - bypassing SET for {key}"
            )
            return False

        try:
            if ex:
                await self._redis.setex(key, ex, value)
            else:
                await self._redis.set(key, value)
            await self._circuit_breaker.record_success()
            return True
        except _REDIS_OPERATION_ERRORS as e:
            await self._circuit_breaker.record_failure(e, type(e).__name__)
            self._degraded_operations += 1
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis SET failed for {key}: {e}")
            return False

    async def delete(self, *keys: str) -> int:
        """
        Delete keys from Redis with circuit breaker protection.

        FAIL-OPEN: Returns 0 if circuit is open or operation fails.

        Args:
            keys: Redis keys to delete

        Returns:
            Number of keys deleted, 0 if bypassed or failed
        """
        if not self._initialized:
            await self.initialize()

        if not self._redis or not keys:
            return 0

        if not await self._circuit_breaker.can_execute():
            await self._circuit_breaker.record_rejection()
            self._bypass_count += 1
            return 0

        try:
            result = await self._redis.delete(*keys)
            await self._circuit_breaker.record_success()
            return int(result)
        except _REDIS_OPERATION_ERRORS as e:
            await self._circuit_breaker.record_failure(e, type(e).__name__)
            self._degraded_operations += 1
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis DELETE failed: {e}")
            return 0

    async def batch_get(self, keys: list[str]) -> list[str | None]:
        """
        Batch get multiple keys with circuit breaker protection.

        FAIL-OPEN: Returns list of None values if circuit is open.

        Args:
            keys: List of Redis keys

        Returns:
            List of values (None for missing or failed keys)
        """
        if not self._initialized:
            await self.initialize()

        if not keys:
            return []

        if not self._redis:
            self._bypass_count += 1
            return [None] * len(keys)

        if not await self._circuit_breaker.can_execute():
            await self._circuit_breaker.record_rejection()
            self._bypass_count += 1
            return [None] * len(keys)

        try:
            pipe = self._redis.pipeline()
            for key in keys:
                pipe.get(key)
            results = await pipe.execute()
            await self._circuit_breaker.record_success()
            return list(results)  # type: ignore[return-value]
        except _REDIS_OPERATION_ERRORS as e:
            await self._circuit_breaker.record_failure(e, type(e).__name__)
            self._degraded_operations += 1
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis batch_get failed: {e}")
            return [None] * len(keys)

    async def batch_set(self, items: list[tuple[str, str, int]]) -> list[bool]:
        """
        Batch set multiple key-value pairs with circuit breaker protection.

        FAIL-OPEN: Returns list of False values if circuit is open.

        Args:
            items: List of (key, value, ttl_seconds) tuples

        Returns:
            List of success booleans
        """
        if not self._initialized:
            await self.initialize()

        if not items:
            return []

        if not self._redis:
            self._bypass_count += 1
            return [False] * len(items)

        if not await self._circuit_breaker.can_execute():
            await self._circuit_breaker.record_rejection()
            self._bypass_count += 1
            return [False] * len(items)

        try:
            pipe = self._redis.pipeline()
            for key, value, ttl in items:
                pipe.setex(key, ttl, value)
            results = await pipe.execute()
            await self._circuit_breaker.record_success()
            return [bool(r) for r in results]
        except _REDIS_OPERATION_ERRORS as e:
            await self._circuit_breaker.record_failure(e, type(e).__name__)
            self._degraded_operations += 1
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis batch_set failed: {e}")
            return [False] * len(items)

    async def health_check(self) -> JSONDict:
        """Check Redis service health with circuit breaker status."""
        health = {
            "service": "redis_cache",
            "healthy": False,
            "circuit_state": "unknown",
            "fallback_strategy": "bypass",
            "degraded_mode": self._redis is None,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if self._circuit_breaker:
            health["circuit_state"] = self._circuit_breaker.state.value
            health["circuit_metrics"] = self._circuit_breaker.metrics.__dict__

        health["client_metrics"] = {
            "degraded_operations": self._degraded_operations,
            "bypass_count": self._bypass_count,
        }

        if self._redis:
            try:
                await self._redis.ping()
                health["healthy"] = True
                health["redis_status"] = "healthy"
            except _REDIS_OPERATION_ERRORS as e:
                health["error"] = str(e)
                health["redis_status"] = "unhealthy"
        else:
            health["redis_status"] = "not_connected"

        return health

    def get_circuit_status(self) -> JSONDict:
        """Get circuit breaker status."""
        if not self._circuit_breaker:
            return {"error": "Circuit breaker not initialized"}
        return self._circuit_breaker.get_status()


__all__ = [
    "CircuitBreakerRedisClient",
]
