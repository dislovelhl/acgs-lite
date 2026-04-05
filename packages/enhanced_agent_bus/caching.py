"""
ACGS-2 Enhanced Agent Bus - Caching Utilities
Constitutional Hash: 608508a9bd224290

High-performance caching layer for API responses and batch processing.
"""

import asyncio
import hashlib
import inspect
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import Redis exceptions for specific error handling
try:
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import RedisError

    REDIS_EXCEPTIONS_AVAILABLE = True
except ImportError:
    # Fallback if redis not installed
    RedisError = Exception  # type: ignore[misc, assignment]
    RedisConnectionError = Exception  # type: ignore[misc, assignment]
    REDIS_EXCEPTIONS_AVAILABLE = False

logger = get_logger(__name__)
T = TypeVar("T")
DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}
CACHE_HASH_MODE = DEFAULT_CACHE_HASH_MODE

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

# Thread-safe global cache with lock
_local_cache: OrderedDict[str, tuple[object, float]] = OrderedDict()
_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
_cache_lock_sync = threading.Lock()  # Protects _local_cache and _cache_stats (sync functions)
_cache_lock_async = asyncio.Lock()  # Protects _local_cache and _cache_stats (async functions)


def _reset_cache_state() -> None:
    """Reset module-level cache state. Used by test fixtures."""
    with _cache_lock_sync:
        _local_cache.clear()
        _cache_stats.update(hits=0, misses=0, evictions=0)


def set_cache_hash_mode(mode: str) -> None:
    """Set cache hash mode for cache_key generation."""
    if mode not in _CACHE_HASH_MODES:
        raise ValueError(f"Invalid cache hash mode: {mode}")
    global CACHE_HASH_MODE
    CACHE_HASH_MODE = mode
    if mode == "fast" and not FAST_HASH_AVAILABLE:
        logger.warning(
            "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
            "falling back to sha256"
        )


def cache_key(*args: object, **kwargs: object) -> str:
    key_data = f"{args}:{sorted(kwargs.items())}"
    if CACHE_HASH_MODE == "fast" and FAST_HASH_AVAILABLE:
        return f"fast:{fast_hash(key_data):016x}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:16]


def _make_cache_key(func_name: str, args: tuple[object, ...], kwargs: dict[str, object]) -> str:
    """Build deterministic cache key for a function invocation."""
    return f"{func_name}:{cache_key(*args, **kwargs)}"


async def _async_lookup_cache(key: str, now: float) -> tuple[bool, object | None]:
    """Lookup cache value under async lock."""
    async with _cache_lock_async:
        cached_entry = _local_cache.get(key)
        if cached_entry is None:
            return False, None

        value, expires = cached_entry
        if now < expires:
            _cache_stats["hits"] += 1
            _local_cache.move_to_end(key)
            return True, value

        _local_cache.pop(key, None)
        return False, None


def _sync_lookup_cache(key: str, now: float) -> tuple[bool, object | None]:
    """Lookup cache value under thread lock."""
    with _cache_lock_sync:
        cached_entry = _local_cache.get(key)
        if cached_entry is None:
            return False, None

        value, expires = cached_entry
        if now < expires:
            _cache_stats["hits"] += 1
            _local_cache.move_to_end(key)
            return True, value

        _local_cache.pop(key, None)
        return False, None


async def _async_store_cache(key: str, value: object, expires_at: float, max_size: int) -> None:
    """Store cache value under async lock with eviction."""
    async with _cache_lock_async:
        if len(_local_cache) >= max_size:
            _local_cache.popitem(last=False)
            _cache_stats["evictions"] += 1
        _local_cache[key] = (value, expires_at)


def _sync_store_cache(key: str, value: object, expires_at: float, max_size: int) -> None:
    """Store cache value under thread lock with eviction."""
    with _cache_lock_sync:
        if len(_local_cache) >= max_size:
            _local_cache.popitem(last=False)
            _cache_stats["evictions"] += 1
        _local_cache[key] = (value, expires_at)


def _record_cache_miss() -> None:
    """Increment cache miss counter in a lock-safe way."""
    with _cache_lock_sync:
        _cache_stats["misses"] += 1


def cached(ttl_seconds: float = 300.0, max_size: int = 1000):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> T:
            key = _make_cache_key(func.__name__, args, kwargs)
            now = time.time()

            hit, cached_value = await _async_lookup_cache(key, now)
            if hit:
                return cached_value  # type: ignore[return-value]

            _record_cache_miss()
            result = await func(*args, **kwargs)  # type: ignore[misc]
            await _async_store_cache(key, result, now + ttl_seconds, max_size)
            return result  # type: ignore[no-any-return]

        @wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> T:
            key = _make_cache_key(func.__name__, args, kwargs)
            now = time.time()

            hit, cached_value = _sync_lookup_cache(key, now)
            if hit:
                return cached_value  # type: ignore[return-value]

            _record_cache_miss()
            result = func(*args, **kwargs)
            _sync_store_cache(key, result, now + ttl_seconds, max_size)
            return result

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper

    return decorator


def get_cache_stats() -> dict[str, int]:
    """Get cache statistics (thread-safe)."""
    with _cache_lock_sync:
        return _cache_stats.copy()


def clear_cache() -> int:
    """Clear all cache entries (thread-safe)."""
    with _cache_lock_sync:
        count = len(_local_cache)
        _local_cache.clear()
        return count


def invalidate_pattern(pattern: str) -> int:
    """Invalidate cache entries matching pattern (thread-safe)."""
    with _cache_lock_sync:
        keys_to_delete = [k for k in _local_cache if pattern in k]
        for key in keys_to_delete:
            del _local_cache[key]
        return len(keys_to_delete)


class RedisCacheClient:
    """Redis cache client with graceful error handling.

    Uses specific Redis exceptions for targeted error handling while
    maintaining fail-safe behavior for cache operations.
    """

    def __init__(self, redis_pool: object):
        self._pool = redis_pool
        self._prefix = "acgs2:cache:"

    async def get(self, key: str) -> str | None:
        """Get value from cache, returns None on any Redis error."""
        try:
            async with self._pool.connection() as conn:
                result = await conn.get(f"{self._prefix}{key}")
                return str(result) if result is not None else None
        except RedisConnectionError:
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Redis connection error on cache get")
            return None
        except RedisError as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis error on cache get: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int = 300) -> bool:
        """Set value in cache, returns False on any Redis error."""
        try:
            async with self._pool.connection() as conn:
                await conn.setex(f"{self._prefix}{key}", ttl, value)
                return True
        except RedisConnectionError:
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Redis connection error on cache set")
            return False
        except RedisError as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis error on cache set: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache, returns False on any Redis error."""
        try:
            async with self._pool.connection() as conn:
                await conn.delete(f"{self._prefix}{key}")
                return True
        except RedisConnectionError:
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Redis connection error on cache delete")
            return False
        except RedisError as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis error on cache delete: {e}")
            return False

    async def mget(self, keys: list[str]) -> list[str | None]:
        """Get multiple values from cache, returns list of None on any Redis error."""
        try:
            async with self._pool.connection() as conn:
                prefixed = [f"{self._prefix}{k}" for k in keys]
                return list(await conn.mget(prefixed))  # type: ignore[arg-type]
        except RedisConnectionError:
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Redis connection error on cache mget")
            return [None] * len(keys)
        except RedisError as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis error on cache mget: {e}")
            return [None] * len(keys)
