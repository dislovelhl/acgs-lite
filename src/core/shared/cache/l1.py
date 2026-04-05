"""
ACGS-2 L1 In-Process Cache Module
Constitutional Hash: 608508a9bd224290

Provides thread-safe in-memory caching using cachetools.TTLCache for ultra-hot data
with sub-millisecond latency (<0.1ms target).

Usage:
    from src.core.shared.l1_cache import L1Cache, get_l1_cache

    # Direct usage
    cache = L1Cache(maxsize=1024, ttl=600)
    cache.set('key', 'value')
    value = cache.get('key')

    # Singleton pattern
    cache = get_l1_cache()

Example:
    cache = L1Cache(maxsize=100, ttl=300)
    cache.set('user:123', {'name': 'Alice'})
    user = cache.get('user:123')  # Returns {'name': 'Alice'}
"""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from src.core.shared.structured_logging import get_logger

try:
    from src.core.shared.types import JSONDict, JSONValue
except ImportError:
    JSONDict = dict[str, object]  # type: ignore[misc, assignment]
    JSONValue = object  # type: ignore[misc]

try:
    from cachetools import TTLCache
except ImportError:
    TTLCache = None

# Constitutional Hash for governance validation
from src.core.shared.constants import CONSTITUTIONAL_HASH

logger = get_logger(__name__)
T = TypeVar("T")


@dataclass
class L1CacheConfig:
    """Configuration for L1 in-process cache."""

    maxsize: int = 1024  # Maximum number of items in cache
    ttl: int = 600  # Time-to-live in seconds (default: 10 minutes)
    serialize: bool = False  # Whether to JSON serialize values for type consistency


@dataclass
class L1CacheStats:
    """Statistics for L1 cache operations."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0

    @property
    def hit_ratio(self) -> float:
        """Calculate hit ratio."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class L1Cache:
    """
    Thread-safe in-process cache using cachetools.TTLCache.

    Provides ultra-fast local caching with configurable TTL and size limits.
    Thread safety is ensured via threading.Lock for all cache operations.

    Attributes:
        maxsize: Maximum number of items the cache can hold
        ttl: Time-to-live for cache entries in seconds
    """

    def __init__(
        self,
        maxsize: int = 1024,
        ttl: int = 600,
        serialize: bool = False,
        on_evict: Callable[[str, JSONValue], None] | None = None,
    ):
        """
        Initialize L1 cache.

        Args:
            maxsize: Maximum number of items in cache (default: 1024)
            ttl: Time-to-live in seconds (default: 600 = 10 minutes)
            serialize: Whether to JSON serialize values for type consistency
            on_evict: Optional callback when items are evicted
        """
        if TTLCache is None:
            raise ImportError(
                "cachetools is required for L1Cache. Install with: pip install cachetools"
            )

        self.maxsize = maxsize
        self.ttl = ttl
        self.serialize = serialize
        self.on_evict = on_evict

        # Core cache with TTL support
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

        # Thread safety lock - CRITICAL for concurrent FastAPI access
        self._lock = threading.Lock()

        # Statistics tracking
        self._stats = L1CacheStats()

        # Access tracking for promotion decisions (frequency per key)
        self._access_counts: dict[str, int] = {}
        self._access_window_start: float = time.time()
        self._access_window_seconds: int = 60  # Track access per minute

    def get(self, key: str, default: JSONValue | None = None) -> JSONValue | None:
        """
        Get a value from the cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        with self._lock:
            self._track_access(key)
            try:
                value = self._cache[key]
                self._stats.hits += 1

                # Deserialize if needed
                if self.serialize and value is not None:
                    value = json.loads(value)

                return cast(JSONValue, value)
            except KeyError:
                self._stats.misses += 1
                return default

    def set(self, key: str, value: JSONValue, ttl: int | None = None) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional per-item TTL override (not supported by TTLCache, ignored)
        """
        with self._lock:
            # Serialize if configured
            if self.serialize:
                value = json.dumps(value)

            # Track evictions - check if cache is at capacity before insert
            was_at_capacity = len(self._cache) >= self._cache.maxsize
            key_existed = key in self._cache
            self._cache[key] = value

            # Eviction occurred if cache was full and we added a new key
            if was_at_capacity and not key_existed:
                self._stats.evictions += 1

            self._stats.sets += 1
            self._track_access(key)

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            try:
                # Call eviction callback if set
                if self.on_evict and key in self._cache:
                    self.on_evict(key, cast(JSONValue, self._cache[key]))

                del self._cache[key]
                self._stats.deletes += 1
                return True
            except KeyError:
                return False

    def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: Cache key

        Returns:
            True if key exists and not expired
        """
        with self._lock:
            return key in self._cache

    def clear(self) -> None:
        """Clear all items from the cache."""
        with self._lock:
            self._cache.clear()
            self._access_counts.clear()

    def get_many(self, keys: list[str]) -> JSONDict:
        """
        Get multiple values from the cache.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of found key-value pairs
        """
        result = {}
        with self._lock:
            for key in keys:
                self._track_access(key)
                try:
                    value = self._cache[key]
                    self._stats.hits += 1

                    if self.serialize and value is not None:
                        value = json.loads(value)

                    result[key] = value
                except KeyError:
                    self._stats.misses += 1

        return result

    def set_many(self, items: JSONDict) -> None:
        """
        Set multiple values in the cache.

        Args:
            items: Dictionary of key-value pairs to cache
        """
        with self._lock:
            for key, value in items.items():
                if self.serialize:
                    value = json.dumps(value)

                self._cache[key] = value
                self._stats.sets += 1
                self._track_access(key)

    def _track_access(self, key: str) -> None:
        """
        Track access frequency for promotion decisions.
        Called within lock context.

        Args:
            key: Cache key being accessed
        """
        current_time = time.time()

        # Reset window if expired
        if current_time - self._access_window_start >= self._access_window_seconds:
            self._access_counts.clear()
            self._access_window_start = current_time

        # Increment access count
        self._access_counts[key] = self._access_counts.get(key, 0) + 1

    def get_access_frequency(self, key: str) -> int:
        """
        Get access frequency for a key in the current window.

        Args:
            key: Cache key

        Returns:
            Number of accesses in current minute window
        """
        with self._lock:
            current_time = time.time()

            # Check if window expired
            if current_time - self._access_window_start >= self._access_window_seconds:
                return 0

            return self._access_counts.get(key, 0)

    def get_hot_keys(self, threshold: int = 10) -> list[str]:
        """
        Get keys with access frequency above threshold.

        Args:
            threshold: Minimum access count to be considered "hot"

        Returns:
            List of hot keys
        """
        with self._lock:
            current_time = time.time()

            # Check if window expired
            if current_time - self._access_window_start >= self._access_window_seconds:
                return []

            return [key for key, count in self._access_counts.items() if count >= threshold]

    @property
    def stats(self) -> L1CacheStats:
        """Get cache statistics."""
        return self._stats

    @property
    def size(self) -> int:
        """Get current number of items in cache."""
        with self._lock:
            return len(self._cache)

    @property
    def currsize(self) -> int:
        """Alias for size property (cachetools compatibility)."""
        return self.size

    def get_stats(self) -> JSONDict:
        """
        Get comprehensive cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            return {
                "tier": "L1",
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "maxsize": self.maxsize,
                "ttl": self.ttl,
                "current_size": len(self._cache),
                "hits": self._stats.hits,
                "misses": self._stats.misses,
                "sets": self._stats.sets,
                "deletes": self._stats.deletes,
                "evictions": self._stats.evictions,
                "hit_ratio": self._stats.hit_ratio,
                "hot_keys_count": len([k for k, v in self._access_counts.items() if v >= 10]),
            }

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator."""
        return self.exists(key)

    def __len__(self) -> int:
        """Support len() function."""
        return self.size

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"L1Cache(maxsize={self.maxsize}, ttl={self.ttl}, "
            f"size={self.size}, hit_ratio={self._stats.hit_ratio:.2%})"
        )


# Singleton instance for shared usage
_default_cache: L1Cache | None = None
_singleton_lock = threading.Lock()


def get_l1_cache(
    maxsize: int = 1024,
    ttl: int = 600,
    serialize: bool = False,
) -> L1Cache:
    """
    Get or create the singleton L1 cache instance.

    Thread-safe singleton pattern for shared cache access across the application.

    Args:
        maxsize: Maximum number of items (used only on first call)
        ttl: Time-to-live in seconds (used only on first call)
        serialize: Whether to JSON serialize values (used only on first call)

    Returns:
        L1Cache singleton instance
    """
    global _default_cache

    if _default_cache is None:
        with _singleton_lock:
            if _default_cache is None:
                _default_cache = L1Cache(maxsize=maxsize, ttl=ttl, serialize=serialize)
                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] L1Cache singleton created: "
                    f"maxsize={maxsize}, ttl={ttl}"
                )

    return _default_cache


def reset_l1_cache() -> None:
    """
    Reset the singleton L1 cache instance.

    Useful for testing or when cache configuration needs to change.
    """
    global _default_cache

    with _singleton_lock:
        if _default_cache is not None:
            _default_cache.clear()
            _default_cache = None
            logger.info(f"[{CONSTITUTIONAL_HASH}] L1Cache singleton reset")


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Classes
    "L1Cache",
    "L1CacheConfig",
    "L1CacheStats",
    # Functions
    "get_l1_cache",
    "reset_l1_cache",
]
