# mypy: ignore-errors
# Mixin class: all methods reference self.* attrs provided by OPAClientCore.
# Cannot statically verify mixin composition without Protocol-based injection.
"""
ACGS-2 OPA Client — Cache Mixin
Constitutional Hash: 608508a9bd224290

Provides all cache-related methods for OPAClient:
Redis cache, memory cache, cache key generation, cache clearing.
"""

import heapq
import json
import time

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import centralized Redis config for caching
try:
    from enhanced_agent_bus._compat.redis_config import get_redis_url

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

    def get_redis_url(db: int = 0) -> str:
        """Mock redis url."""
        return f"redis://localhost:6379/{db}"


# Optional Redis client for caching
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

    REDIS_CLIENT_AVAILABLE = True
except ImportError:
    REDIS_CLIENT_AVAILABLE = False
    aioredis = None
    # Fallback types for type checking
    RedisError = Exception  # type: ignore[misc, assignment]
    RedisConnectionError = Exception  # type: ignore[misc, assignment]
    RedisTimeoutError = Exception  # type: ignore[misc, assignment]

DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

logger = get_logger(__name__)


def _redis_client_available() -> bool:
    """Look up REDIS_CLIENT_AVAILABLE through the package namespace for patchability."""
    import sys

    pkg = sys.modules.get(__name__.rsplit(".", 1)[0])  # enhanced_agent_bus.opa_client
    if pkg is not None and hasattr(pkg, "REDIS_CLIENT_AVAILABLE"):
        return pkg.REDIS_CLIENT_AVAILABLE  # type: ignore[return-value]
    return REDIS_CLIENT_AVAILABLE


def _get_aioredis():
    """Look up aioredis through the package namespace for patchability."""
    import sys

    pkg = sys.modules.get(__name__.rsplit(".", 1)[0])
    if pkg is not None and hasattr(pkg, "aioredis"):
        return pkg.aioredis
    return aioredis


class OPAClientCacheMixin:
    """Mixin providing cache-related methods for OPAClient.

    All methods reference ``self`` attributes that are initialized
    by ``OPAClientCore.__init__``.
    """

    async def _initialize_redis_cache(self) -> None:
        """Initialize Redis cache connection for distributed policy caching."""
        try:
            redis_mod = _get_aioredis()
            self._redis_client = await redis_mod.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self._redis_client.ping()
            logger.info("Redis cache initialized for OPA client")
        except RedisConnectionError as e:
            logger.warning("Redis connection failed: %s, using memory cache", e)
            self._redis_client = None
        except RedisTimeoutError as e:
            logger.warning("Redis timeout: %s, using memory cache", e)
            self._redis_client = None
        except RedisError as e:
            logger.warning("Redis error: %s, using memory cache", e)
            self._redis_client = None

    def _generate_cache_key(self, policy_path: str, input_data: JSONDict) -> str:
        """Generate cache key."""
        import hashlib

        input_str = json.dumps(input_data, sort_keys=True)
        if self.cache_hash_mode == "fast" and FAST_HASH_AVAILABLE:
            input_hash = f"{fast_hash(input_str):016x}"
        else:
            input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:16]
        return f"opa:{policy_path}:{input_hash}"

    async def _get_from_cache(self, cache_key: str) -> JSONDict | None:
        """Get result from cache."""
        if not self.enable_cache:
            return None

        redis_cached = await self._read_redis_cache(cache_key)
        if redis_cached is not None:
            return redis_cached

        return self._read_memory_cache(cache_key)

    async def _read_redis_cache(self, cache_key: str) -> JSONDict | None:
        """Read cache entry from Redis if available."""
        if not self._redis_client:
            return None

        try:
            cached = await self._redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except RedisConnectionError:
            logger.debug("Redis connection error on cache read")
        except (RedisTimeoutError, RedisError) as e:
            logger.warning("Redis cache read error: %s", e)
        except json.JSONDecodeError as e:
            logger.warning("Cache value decode error: %s", e)

        return None

    def _read_memory_cache(self, cache_key: str) -> JSONDict | None:
        """Read cache entry from in-memory store with TTL enforcement."""
        cached_entry = self._memory_cache.get(cache_key)
        if cached_entry is None:
            return None

        timestamp = self._resolve_memory_cache_timestamp(cache_key, cached_entry)
        if time.time() - timestamp >= self.cache_ttl:
            self._memory_cache.pop(cache_key, None)
            self._memory_cache_timestamps.pop(cache_key, None)
            return None

        return self._normalize_memory_cache_entry(cached_entry)

    def _resolve_memory_cache_timestamp(self, cache_key: str, cached_entry: JSONDict) -> float:
        """Resolve and persist timestamp for memory cache entries."""
        timestamp = self._memory_cache_timestamps.get(cache_key)
        if timestamp is not None:
            return timestamp

        embedded_timestamp = cached_entry.get("timestamp")
        if isinstance(embedded_timestamp, (int, float)):
            timestamp = float(embedded_timestamp)
        else:
            timestamp = time.time()

        self._memory_cache_timestamps[cache_key] = timestamp
        return timestamp

    def _normalize_memory_cache_entry(self, cached_entry: JSONDict) -> JSONDict:
        """Support legacy and current memory cache entry formats."""
        if "allowed" in cached_entry:
            return cached_entry

        nested_result = cached_entry.get("result")
        if isinstance(nested_result, dict):
            return nested_result

        return cached_entry

    async def _set_to_cache(self, cache_key: str, result: JSONDict) -> None:
        """Set result in cache."""
        if not self.enable_cache:
            return

        if self._redis_client:
            try:
                await self._redis_client.setex(cache_key, self.cache_ttl, json.dumps(result))
                # Phase 4: Track keys by policy path for smart invalidation
                policy_path = cache_key.split(":")[1]
                path_set_key = f"opa:path_keys:{policy_path}"
                await self._redis_client.sadd(path_set_key, cache_key)
                await self._redis_client.expire(path_set_key, self.cache_ttl * 2)
                return
            except RedisConnectionError:
                logger.debug("Redis connection error on cache write")
            except (RedisTimeoutError, RedisError) as e:
                logger.warning("Redis cache write error: %s", e)

        # Evict oldest 25% of entries when cache exceeds maxsize
        if len(self._memory_cache) >= self._memory_cache_maxsize:
            evict_count = max(1, len(self._memory_cache) // 4)
            # Use nsmallest for O(n log k) instead of full sort O(n log n)
            oldest_keys = heapq.nsmallest(
                evict_count,
                self._memory_cache_timestamps,
                key=self._memory_cache_timestamps.__getitem__,
            )
            for k in oldest_keys:
                self._memory_cache.pop(k, None)
                self._memory_cache_timestamps.pop(k, None)

        timestamp = time.time()
        self._memory_cache[cache_key] = {"result": result, "timestamp": timestamp}
        self._memory_cache_timestamps[cache_key] = timestamp

    async def clear_cache(self, policy_path: str | None = None) -> None:
        """
        Clear the policy evaluation cache.

        Args:
            policy_path: If provided, only clear cache for this specific policy path.
                         If None, clear the entire cache.
        """
        if not self.enable_cache:
            return

        logger.info("Clearing OPA cache (path=%s)", policy_path or "ALL")

        if self._redis_client:
            await self._clear_redis_cache(policy_path)

        self._clear_memory_cache(policy_path)

    async def _clear_redis_cache(self, policy_path: str | None) -> None:
        """Clear Redis-backed cache entries."""
        try:
            if policy_path:
                await self._clear_redis_policy_path(policy_path)
                return
            await self._clear_all_redis_opa_keys()
        except RedisConnectionError as e:
            logger.error("Redis connection failed during cache clear: %s", e)
        except (RedisTimeoutError, RedisError) as e:
            logger.error("Failed to clear Redis cache: %s", e)

    async def _clear_redis_policy_path(self, policy_path: str) -> None:
        """Clear Redis cache entries for a single policy path."""
        path_set_key = f"opa:path_keys:{policy_path}"
        keys = await self._redis_client.smembers(path_set_key)
        await self._delete_redis_keys(keys)
        await self._redis_client.delete(path_set_key)

    async def _clear_all_redis_opa_keys(self) -> None:
        """Clear all Redis OPA cache keys via bounded SCAN iterations."""
        cursor: int | str = 0
        max_scan_iterations = 10_000
        pattern = "opa:*"

        for _ in range(max_scan_iterations):
            cursor, keys = await self._redis_client.scan(cursor, match=pattern)
            await self._delete_redis_keys(keys)
            if cursor in (0, "0"):
                break

    async def _delete_redis_keys(self, keys: list[str] | set[str] | tuple[str, ...]) -> None:
        """Delete Redis keys in batches to avoid oversized command payloads."""
        if not keys:
            return

        key_list = list(keys)
        batch_size = 500
        for idx in range(0, len(key_list), batch_size):
            await self._redis_client.delete(*key_list[idx : idx + batch_size])

    def _clear_memory_cache(self, policy_path: str | None) -> None:
        """Clear memory-backed cache entries."""
        if policy_path is None:
            self._memory_cache.clear()
            self._memory_cache_timestamps.clear()
            return

        prefix = f"opa:{policy_path}:"
        keys_to_delete = [key for key in self._memory_cache if key.startswith(prefix)]
        for key in keys_to_delete:
            self._memory_cache.pop(key, None)
            self._memory_cache_timestamps.pop(key, None)
