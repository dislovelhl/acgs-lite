"""
ACGS-2 Enhanced Agent Bus - Batch Validation Cache
Constitutional Hash: 608508a9bd224290

High-performance batch caching strategy for repeated validations.
Implements Phase 4-Task 2 acceptance criteria:
- Cache validation results within batch
- Deduplicate identical requests
- TTL-based cache invalidation

Performance Optimizations:
- msgpack serialization for 15-25% faster cache operations
- Fallback to JSON when msgpack unavailable
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Literal

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONList,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONList = list  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

# msgpack for faster serialization (15-25% improvement over JSON)
try:
    import msgpack

    MSGPACK_AVAILABLE = True
except ImportError:
    msgpack = None
    MSGPACK_AVAILABLE = False

logger = get_logger(__name__)
# Default cache configuration
DEFAULT_CACHE_TTL = 300  # 5 minutes
DEFAULT_MAX_SIZE = 10000  # Maximum cache entries
DEFAULT_CACHE_PREFIX = "acgs2:batch_cache:"
DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False


def _serialize_value(value: object) -> bytes:
    """
    Serialize value using msgpack (preferred) or JSON fallback.

    msgpack provides 15-25% faster serialization than JSON for typical
    cache payloads while maintaining compatibility.

    Args:
        value: Value to serialize

    Returns:
        Serialized bytes
    """
    if MSGPACK_AVAILABLE:
        return bytes(msgpack.packb(value, use_bin_type=True))  # type: ignore[arg-type]
    else:
        return json.dumps(value).encode("utf-8")


def _deserialize_value(data: bytes | str) -> object:
    """
    Deserialize value using msgpack (preferred) or JSON fallback.

    Args:
        data: Serialized bytes or string

    Returns:
        Deserialized value
    """
    if MSGPACK_AVAILABLE:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return msgpack.unpackb(data, raw=False)
    else:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)


class BatchValidationCache:
    """
    In-memory batch validation cache with TTL and LRU eviction.

    Features:
    - Cache validation results within batch operations
    - TTL-based cache invalidation
    - LRU eviction when max size reached
    - Metrics collection for observability
    - Constitutional hash tracking for compliance

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_CACHE_TTL,
        max_size: int = DEFAULT_MAX_SIZE,
        cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
    ):
        """
        Initialize batch validation cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
            max_size: Maximum number of entries in cache
        """
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        if cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self.cache_hash_mode = cache_hash_mode
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # LRU cache using OrderedDict
        self._cache: OrderedDict[str, tuple[object, float]] = OrderedDict()
        self._lock = asyncio.Lock()

        # Metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._created_at = datetime.now(UTC).isoformat()
        if self.cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

    def generate_cache_key(
        self,
        content: object,
        from_agent: str,
        to_agent: str,
        message_type: str,
        tenant_id: str | None = None,
    ) -> str:
        """
        Generate cache key from validation request parameters.

        Args:
            content: Message content (dict or string)
            from_agent: Source agent ID
            to_agent: Target agent ID
            message_type: Type of message
            tenant_id: Optional tenant ID for isolation

        Returns:
            SHA-256 hash as cache key
        """
        # Serialize content deterministically
        if isinstance(content, dict):
            content_str = json.dumps(content, sort_keys=True)
        else:
            content_str = str(content)

        # Build key components
        key_parts = [
            content_str,
            from_agent,
            to_agent,
            message_type,
            tenant_id or "",
        ]

        key_string = "|".join(key_parts)
        if self.cache_hash_mode == "fast" and FAST_HASH_AVAILABLE:
            return f"fast:{fast_hash(key_string):016x}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    async def get(self, key: str) -> JSONDict | None:
        """
        Get cached validation result.

        Args:
            key: Cache key

        Returns:
            Cached validation result or None if not found/expired
        """
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expires_at = self._cache[key]

            # Check TTL expiration
            if time.time() > expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end for LRU (most recently used)
            self._cache.move_to_end(key)

            self._hits += 1
            return value

    async def set(self, key: str, value: JSONDict) -> bool:
        """
        Set cached validation result.

        Args:
            key: Cache key
            value: Validation result to cache

        Returns:
            True if successfully cached
        """
        async with self._lock:
            expires_at = time.time() + self.ttl_seconds

            # If key exists, update and move to end
            if key in self._cache:
                self._cache[key] = (value, expires_at)
                self._cache.move_to_end(key)
                return True

            # Enforce max size - evict oldest if needed
            while len(self._cache) >= self.max_size:
                # Pop oldest (first) item
                self._cache.popitem(last=False)
                self._evictions += 1

            # Add new entry
            self._cache[key] = (value, expires_at)
            return True

    async def delete(self, key: str) -> bool:
        """
        Delete cached entry.

        Args:
            key: Cache key

        Returns:
            True if entry was deleted, False if not found
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()

    def get_stats(self) -> JSONDict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "constitutional_hash": self.constitutional_hash,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "evictions": self._evictions,
            "current_size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "created_at": self._created_at,
        }


class RedisBatchCache:
    """
    Redis-backed batch validation cache with TTL and batch operations.

    Features:
    - Distributed caching across instances
    - Batch get/set operations using pipelines
    - Automatic TTL-based expiration
    - Constitutional hash tracking

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl_seconds: int = DEFAULT_CACHE_TTL,
        key_prefix: str = DEFAULT_CACHE_PREFIX,
        max_connections: int = 20,
        cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
    ):
        """
        Initialize Redis batch cache.

        Args:
            redis_url: Redis connection URL
            ttl_seconds: Time-to-live for cache entries
            key_prefix: Prefix for cache keys
            max_connections: Maximum Redis connections
        """
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self.max_connections = max_connections
        if cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self.cache_hash_mode = cache_hash_mode
        self.constitutional_hash = CONSTITUTIONAL_HASH

        self._pool: object | None = None
        self._redis: object | None = None
        self._initialized = False
        self._lock = asyncio.Lock()

        # Metrics
        self._hits = 0
        self._misses = 0
        self._created_at = datetime.now(UTC).isoformat()
        if self.cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

    async def initialize(self) -> bool:
        """
        Initialize Redis connection pool.

        Returns:
            True if initialization successful
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
                # Note: decode_responses=False for msgpack binary support
                # When using JSON fallback, we handle string decoding in _deserialize_value
                self._pool = aioredis.ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=self.max_connections,
                    decode_responses=False,
                )
                self._redis = aioredis.Redis(connection_pool=self._pool)

                # Verify connection
                await self._redis.ping()  # type: ignore[misc]

                self._initialized = True
                logger.info(f"[{CONSTITUTIONAL_HASH}] Redis batch cache initialized")
                return True

            except (OSError, ConnectionError, ValueError, TypeError) as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to initialize Redis cache: {e}")
                return False

    async def close(self) -> None:
        """Close Redis connection."""
        async with self._lock:
            if self._redis:
                await self._redis.close()
                self._redis = None

            if self._pool:
                await self._pool.disconnect()
                self._pool = None

            self._initialized = False

    def _make_key(self, key: str) -> str:
        """Create prefixed Redis key."""
        return f"{self.key_prefix}{key}"

    def generate_cache_key(
        self,
        content: object,
        from_agent: str,
        to_agent: str,
        message_type: str,
        tenant_id: str | None = None,
    ) -> str:
        """
        Generate cache key from validation request parameters.

        Args:
            content: Message content (dict or string)
            from_agent: Source agent ID
            to_agent: Target agent ID
            message_type: Type of message
            tenant_id: Optional tenant ID for isolation

        Returns:
            SHA-256 hash as cache key
        """
        if isinstance(content, dict):
            content_str = json.dumps(content, sort_keys=True)
        else:
            content_str = str(content)

        key_parts = [
            content_str,
            from_agent,
            to_agent,
            message_type,
            tenant_id or "",
        ]

        key_string = "|".join(key_parts)
        if self.cache_hash_mode == "fast" and FAST_HASH_AVAILABLE:
            return f"fast:{fast_hash(key_string):016x}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    async def get(self, key: str) -> JSONDict | None:
        """
        Get cached validation result from Redis.

        Args:
            key: Cache key

        Returns:
            Cached validation result or None if not found
        """
        if not self._initialized:
            await self.initialize()

        if not self._redis:
            return None

        try:
            redis_key = self._make_key(key)
            value = await self._redis.get(redis_key)

            if value is None:
                self._misses += 1
                return None

            self._hits += 1
            return _deserialize_value(value)

        except (OSError, ConnectionError, ValueError, TypeError, KeyError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis get error: {e}")
            self._misses += 1
            return None

    async def set(self, key: str, value: JSONDict) -> bool:
        """
        Set cached validation result in Redis with TTL.

        Args:
            key: Cache key
            value: Validation result to cache

        Returns:
            True if successfully cached
        """
        if not self._initialized:
            await self.initialize()

        if not self._redis:
            return False

        try:
            redis_key = self._make_key(key)
            value_bytes = _serialize_value(value)
            await self._redis.setex(redis_key, self.ttl_seconds, value_bytes)
            return True

        except (OSError, ConnectionError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete cached entry from Redis.

        Args:
            key: Cache key

        Returns:
            True if entry was deleted
        """
        if not self._initialized:
            await self.initialize()

        if not self._redis:
            return False

        try:
            redis_key = self._make_key(key)
            result = await self._redis.delete(redis_key)
            return bool(result > 0)

        except (OSError, ConnectionError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis delete error: {e}")
            return False

    async def clear(self) -> None:
        """Clear all cached entries with prefix."""
        if not self._initialized:
            await self.initialize()

        if not self._redis:
            return

        try:
            # Find all keys with prefix
            pattern = f"{self.key_prefix}*"
            cursor = 0

            max_scan_iterations = 10_000
            for _ in range(max_scan_iterations):
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break

        except (OSError, ConnectionError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis clear error: {e}")

    async def batch_get(self, keys: list[str]) -> list[JSONDict | None]:
        """
        Batch get multiple cached values using pipeline.

        Args:
            keys: List of cache keys

        Returns:
            List of cached values (None for missing)
        """
        if not keys:
            return []

        if not self._initialized:
            await self.initialize()

        if not self._redis:
            return [None] * len(keys)

        try:
            pipe = self._redis.pipeline()
            for key in keys:
                redis_key = self._make_key(key)
                pipe.get(redis_key)

            results = await pipe.execute()

            parsed_results: JSONList = []
            for result in results:
                if result is None:
                    self._misses += 1
                    parsed_results.append(None)
                else:
                    self._hits += 1
                    parsed_results.append(_deserialize_value(result))

            return list(parsed_results)  # type: ignore[return-value]

        except (OSError, ConnectionError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis batch_get error: {e}")
            return [None] * len(keys)

    async def batch_set(self, items: list[tuple[str, JSONDict]]) -> list[bool]:
        """
        Batch set multiple cached values using pipeline.

        Args:
            items: List of (key, value) tuples

        Returns:
            List of success booleans
        """
        if not items:
            return []

        if not self._initialized:
            await self.initialize()

        if not self._redis:
            return [False] * len(items)

        try:
            pipe = self._redis.pipeline()
            for key, value in items:
                redis_key = self._make_key(key)
                value_bytes = _serialize_value(value)
                pipe.setex(redis_key, self.ttl_seconds, value_bytes)

            results = await pipe.execute()
            return [bool(r) for r in results]

        except (OSError, ConnectionError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Redis batch_set error: {e}")
            return [False] * len(items)

    def get_stats(self) -> JSONDict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "constitutional_hash": self.constitutional_hash,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "ttl_seconds": self.ttl_seconds,
            "initialized": self._initialized,
            "created_at": self._created_at,
            "backend": "redis",
            "serialization": "msgpack" if MSGPACK_AVAILABLE else "json",
        }


def create_batch_cache(
    backend: str = "memory",
    redis_url: str | None = None,
    ttl_seconds: int = DEFAULT_CACHE_TTL,
    max_size: int = DEFAULT_MAX_SIZE,
    key_prefix: str = DEFAULT_CACHE_PREFIX,
    cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
) -> BatchValidationCache | RedisBatchCache:
    """
    Factory function to create batch cache instance.

    Args:
        backend: Cache backend ("memory" or "redis")
        redis_url: Redis connection URL (required for redis backend)
        ttl_seconds: Time-to-live for cache entries
        max_size: Maximum size for memory cache
        key_prefix: Key prefix for Redis cache

    Returns:
        BatchValidationCache or RedisBatchCache instance
    """
    if backend == "redis":
        if not redis_url:
            redis_url = "redis://localhost:6379"
        return RedisBatchCache(
            redis_url=redis_url,
            ttl_seconds=ttl_seconds,
            key_prefix=key_prefix,
            cache_hash_mode=cache_hash_mode,
        )
    else:
        return BatchValidationCache(
            ttl_seconds=ttl_seconds,
            max_size=max_size,
            cache_hash_mode=cache_hash_mode,
        )


__all__ = [
    "DEFAULT_CACHE_HASH_MODE",
    "DEFAULT_CACHE_TTL",
    "DEFAULT_MAX_SIZE",
    "MSGPACK_AVAILABLE",
    "BatchValidationCache",
    "RedisBatchCache",
    "_deserialize_value",
    "_serialize_value",
    "create_batch_cache",
]
