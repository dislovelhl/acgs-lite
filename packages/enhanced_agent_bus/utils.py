"""
ACGS-2 Enhanced Agent Bus - Utilities
Constitutional Hash: 608508a9bd224290
"""

import re
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Generic, TypeVar

import cachetools

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

K = TypeVar("K")
V = TypeVar("V")


def redact_error_message(error: Exception) -> str:
    """Redact sensitive information from error messages (VULN-008)."""
    error_msg = str(error)
    # Redact potential URLs/URIs
    redacted = re.sub(r'[a-zA-Z0-9+.-]+://[^\s<>"]+', "[REDACTED_URI]", error_msg)
    # Redact common credential patterns
    redacted = re.sub(
        r"(?i)(key|secret|token|password|auth|pwd)=[^ \b\n\r\t,;]+", r"\1=[REDACTED]", redacted
    )
    # Redact absolute file paths (Unix-style)
    redacted = re.sub(r"/(?:[a-zA-Z0-9._-]+/)+[a-zA-Z0-9._-]+", "[REDACTED_PATH]", redacted)
    return redacted


def get_iso_timestamp() -> str:
    """Get current timezone.utc timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


class LRUCache(Generic[K, V]):
    """LRU cache for validation results backed by cachetools.LRUCache.

    Provides a .get()/.set()/.clear() API while delegating core LRU logic to
    cachetools.LRUCache. The internal ._cache attribute is an OrderedDict-like
    view maintained for backward compatibility with callers that inspect it.
    """

    def __init__(self, maxsize: int = 1000):
        self._maxsize = maxsize
        self._backing: cachetools.LRUCache[K, V] = cachetools.LRUCache(maxsize=maxsize)
        # Expose an OrderedDict view so tests that access cache._cache.keys()
        # continue to work. We keep it in sync with every mutation.
        self._cache: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        """Return cached value for key, or None if missing."""
        try:
            value: V = self._backing[key]  # type: ignore[assignment]
        except KeyError:
            return None
        # Sync the view: move accessed key to end (most recently used).
        if key in self._cache:
            self._cache.move_to_end(key)
        return value

    def set(self, key: K, value: V) -> None:
        """Store value under key, evicting the LRU entry when full."""
        will_evict = key not in self._backing and len(self._backing) >= self._maxsize
        self._backing[key] = value
        # Prune any entry cachetools evicted from the OrderedDict view.
        if will_evict:
            stale = [k for k in self._cache if k not in self._backing]
            for k in stale:
                del self._cache[k]
        # Keep the OrderedDict view in sync (value and recency order).
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._backing.clear()
        self._cache.clear()


class TTLCache(Generic[K, V]):
    """
    LRU cache with TTL (Time-To-Live) expiration for high-read, low-write operations.

    Optimized for:
    - Policy evaluation results (TTL: 300-900s)
    - Impact scoring embeddings (TTL: 3600s)
    - Governance KPI calculations (TTL: 300-3600s)
    - MACI role verification (TTL: 600s)

    Performance targets:
    - Cache hit rate: >95%
    - Lookup time: <0.1ms
    - Memory efficient with automatic expiration
    """

    def __init__(self, maxsize: int = 10000, ttl_seconds: float = 300.0):
        """
        Initialize TTL cache.

        Args:
            maxsize: Maximum number of entries (default: 10000 for enterprise scale)
            ttl_seconds: Time-to-live in seconds (default: 300s = 5 minutes)
        """
        from collections import OrderedDict

        self._cache: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> V | None:
        """Get value if exists and not expired."""
        if key not in self._cache:
            self._misses += 1
            return None

        value, expiry = self._cache[key]
        current_time = time.monotonic()

        if current_time > expiry:
            # Entry expired, remove it
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (LRU) and return
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: K, value: V, ttl: float | None = None) -> None:
        """Set value with optional custom TTL."""
        ttl_seconds = ttl if ttl is not None else self._ttl
        expiry = time.monotonic() + ttl_seconds

        if key in self._cache:
            self._cache.move_to_end(key)

        self._cache[key] = (value, expiry)

        # Evict oldest if over capacity
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all entries and reset stats."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        current_time = time.monotonic()
        expired_keys = [k for k, (_, expiry) in self._cache.items() if current_time > expiry]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def get_stats(self) -> JSONDict:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, key: K) -> bool:
        """Check if key exists and is not expired."""
        if key not in self._cache:
            return False
        _, expiry = self._cache[key]
        return time.monotonic() <= expiry
