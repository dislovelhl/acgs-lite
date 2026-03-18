"""
ACGS-2 Context & Memory - Constitutional Context Cache
Constitutional Hash: cdd01ef066bc6cf2

Fast caching layer for constitutional context with sub-5ms P99 latency.
Ensures constitutional principles are always readily available.

Key Features:
- Multi-tier caching (L1 memory, L2 Redis)
- Sub-5ms P99 latency for context retrieval
- Constitutional hash validation on all operations
- Automatic cache warming for critical context
"""

import asyncio
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Generic, TypeVar

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.json_utils import dumps as json_dumps
from src.core.shared.json_utils import loads as json_loads

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import ContextChunk, ContextPriority, ContextType

logger = get_logger(__name__)
T = TypeVar("T")

L2_CACHE_OPERATION_ERRORS = (
    AttributeError,
    ConnectionError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class CacheTier(str, Enum):  # noqa: UP042
    """Cache storage tiers."""

    L1_MEMORY = "l1_memory"  # In-process memory
    L2_REDIS = "l2_redis"  # Redis cluster
    L3_DATABASE = "l3_database"  # Persistent database


@dataclass
class CacheConfig:
    """Configuration for constitutional context cache.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    l1_max_entries: int = 1000
    l1_ttl_seconds: int = 300
    l2_enabled: bool = False
    l2_ttl_seconds: int = 3600
    l3_enabled: bool = False
    p99_latency_target_ms: float = 5.0
    enable_warming: bool = True
    warming_batch_size: int = 100
    enable_compression: bool = False
    enable_metrics: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {self.constitutional_hash}")


@dataclass
class CacheEntry(Generic[T]):
    """A cached entry with metadata.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    key: str
    value: T
    created_at: datetime
    expires_at: datetime
    tier: CacheTier
    access_count: int = 0
    last_accessed: datetime | None = None
    size_bytes: int = 0
    content_hash: str = ""
    is_constitutional: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return datetime.now(UTC) > self.expires_at

    def record_access(self) -> None:
        """Record an access to this entry."""
        self.access_count += 1
        self.last_accessed = datetime.now(UTC)


@dataclass
class CacheStats:
    """Statistics for cache operations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    total_requests: int = 0
    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    l3_hits: int = 0
    l3_misses: int = 0
    evictions: int = 0
    writes: int = 0
    deletes: int = 0
    p99_latency_ms: float = 0.0
    average_latency_ms: float = 0.0
    constitutional_context_hits: int = 0
    warming_operations: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def hit_rate(self) -> float:
        """Calculate overall cache hit rate."""
        if self.total_requests == 0:
            return 0.0
        total_hits = self.l1_hits + self.l2_hits + self.l3_hits
        return total_hits / self.total_requests

    @property
    def l1_hit_rate(self) -> float:
        """Calculate L1 cache hit rate."""
        l1_total = self.l1_hits + self.l1_misses
        if l1_total == 0:
            return 0.0
        return self.l1_hits / l1_total


class ConstitutionalContextCache:
    """Fast cache for constitutional context with sub-5ms P99 latency.

    Provides multi-tier caching with constitutional compliance validation.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        config: CacheConfig | None = None,
        redis_client: object | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.config = config or CacheConfig()
        self.constitutional_hash = constitutional_hash
        self._redis_client = redis_client

        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {constitutional_hash}")

        # L1 cache (in-memory LRU)
        self._l1_cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # Constitutional context (always cached)
        self._constitutional_context: dict[str, ContextChunk] = {}

        # Statistics
        self._stats = CacheStats(constitutional_hash=constitutional_hash)

        # Latency tracking
        self._latencies: list[float] = []
        self._latency_window_size = 1000

        # Cache key prefix
        self._key_prefix = "acgs2:ctx:"

        # Background task tracking (prevent GC before completion)
        self._background_tasks: set[asyncio.Task] = set()

        logger.info(f"Initialized ConstitutionalContextCache (L1 max={self.config.l1_max_entries})")

    async def get(
        self,
        key: str,
        default: T | None = None,
    ) -> T | None:
        """Get a value from the cache.

        Args:
            key: Cache key
            default: Default value if not found

        Returns:
            Cached value or default
        """
        start_time = time.perf_counter()
        self._stats.total_requests += 1

        # Check L1 cache
        entry = self._l1_cache.get(key)
        if entry and not entry.is_expired():
            entry.record_access()
            self._l1_cache.move_to_end(key)
            self._stats.l1_hits += 1
            if entry.is_constitutional:
                self._stats.constitutional_context_hits += 1
            self._record_latency(start_time)
            return entry.value  # type: ignore[no-any-return]

        self._stats.l1_misses += 1

        # Check L2 cache (Redis) if enabled
        if self.config.l2_enabled and self._redis_client:
            value = await self._get_from_l2(key)
            if value is not None:
                self._stats.l2_hits += 1
                # Promote to L1
                await self.set(key, value)
                self._record_latency(start_time)
                return value
            self._stats.l2_misses += 1

        self._record_latency(start_time)
        return default

    async def set(
        self,
        key: str,
        value: T,
        ttl_seconds: int | None = None,
        is_constitutional: bool = False,
    ) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live (defaults to config)
            is_constitutional: Whether this is constitutional context

        Returns:
            True if successfully cached
        """
        start_time = time.perf_counter()
        ttl = ttl_seconds or self.config.l1_ttl_seconds

        # Calculate expiration
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl)

        # Calculate content hash for validation
        content_hash = hashlib.sha256(str(value).encode()).hexdigest()[:16]

        # Create entry
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=expires_at,
            tier=CacheTier.L1_MEMORY,
            content_hash=content_hash,
            is_constitutional=is_constitutional,
            constitutional_hash=self.constitutional_hash,
        )

        # Evict if necessary
        while len(self._l1_cache) >= self.config.l1_max_entries:
            self._evict_one()

        # Store in L1
        self._l1_cache[key] = entry
        self._l1_cache.move_to_end(key)
        self._stats.writes += 1

        # Store in L2 if enabled
        if self.config.l2_enabled and self._redis_client:
            await self._set_to_l2(key, value, ttl)

        self._record_latency(start_time)
        return True

    async def get_constitutional_context(
        self,
        context_type: ContextType | None = None,
    ) -> list[ContextChunk]:
        """Get cached constitutional context.

        Args:
            context_type: Filter by context type

        Returns:
            List of constitutional context chunks
        """
        self._stats.constitutional_context_hits += 1

        if context_type:
            return [
                c for c in self._constitutional_context.values() if c.context_type == context_type
            ]
        return list(self._constitutional_context.values())

    async def set_constitutional_context(
        self,
        chunks: list[ContextChunk],
    ) -> None:
        """Set the constitutional context that is always cached.

        Args:
            chunks: List of constitutional context chunks
        """
        self._constitutional_context.clear()

        for chunk in chunks:
            # Ensure constitutional type
            chunk.context_type = ContextType.CONSTITUTIONAL
            chunk.priority = ContextPriority.CRITICAL
            chunk.is_critical = True

            self._constitutional_context[chunk.chunk_id] = chunk

            # Also add to L1 cache
            await self.set(
                f"constitutional:{chunk.chunk_id}",
                chunk,
                ttl_seconds=self.config.l1_ttl_seconds * 10,  # Longer TTL
                is_constitutional=True,
            )

        logger.info(f"Set {len(chunks)} constitutional context chunks")

    async def warm_cache(
        self,
        chunks: list[ContextChunk],
        priority_types: list[ContextType] | None = None,
    ) -> int:
        """Warm the cache with frequently accessed context.

        Args:
            chunks: Chunks to cache
            priority_types: Types to prioritize

        Returns:
            Number of chunks warmed
        """
        if not self.config.enable_warming:
            return 0

        warmed = 0
        priority_types = priority_types or [
            ContextType.CONSTITUTIONAL,
            ContextType.POLICY,
            ContextType.GOVERNANCE,
        ]

        # Sort by priority
        sorted_chunks = sorted(
            chunks,
            key=lambda c: (
                c.context_type in priority_types,
                c.priority.value,
            ),
            reverse=True,
        )

        # Warm in batches
        for i in range(0, len(sorted_chunks), self.config.warming_batch_size):
            batch = sorted_chunks[i : i + self.config.warming_batch_size]
            for chunk in batch:
                key = f"chunk:{chunk.chunk_id}"
                await self.set(
                    key,
                    chunk,
                    is_constitutional=chunk.context_type == ContextType.CONSTITUTIONAL,
                )
                warmed += 1

        self._stats.warming_operations += 1
        logger.info(f"Warmed cache with {warmed} chunks")
        return warmed

    async def invalidate(self, key: str) -> bool:
        """Invalidate a cache entry.

        Args:
            key: Cache key

        Returns:
            True if entry was found and removed
        """
        found = False

        # Remove from L1
        if key in self._l1_cache:
            del self._l1_cache[key]
            found = True
            self._stats.deletes += 1

        # Remove from L2 if enabled
        if self.config.l2_enabled and self._redis_client:
            await self._delete_from_l2(key)

        return found

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all entries matching a pattern.

        Args:
            pattern: Pattern to match (substring)

        Returns:
            Number of entries invalidated
        """
        keys_to_remove = [k for k in self._l1_cache.keys() if pattern in k]

        for key in keys_to_remove:
            await self.invalidate(key)

        return len(keys_to_remove)

    def _evict_one(self) -> None:
        """Evict one entry from L1 cache (LRU)."""
        if not self._l1_cache:
            return

        # Don't evict constitutional context if possible
        for key, entry in self._l1_cache.items():
            if not entry.is_constitutional:
                del self._l1_cache[key]
                self._stats.evictions += 1
                return

        # If all are constitutional, evict oldest
        oldest_key = next(iter(self._l1_cache))
        del self._l1_cache[oldest_key]
        self._stats.evictions += 1

    async def _get_from_l2(self, key: str) -> object | None:
        """Get value from L2 Redis cache."""
        if not self._redis_client:
            return None

        try:
            prefixed_key = f"{self._key_prefix}{key}"
            value = await self._redis_client.get(prefixed_key)
            if value:
                return json_loads(value)  # type: ignore[no-any-return]
            return None
        except L2_CACHE_OPERATION_ERRORS as e:
            logger.warning(f"L2 cache get failed: {e}")
            return None

    async def _set_to_l2(self, key: str, value: object, ttl: int) -> bool:
        """Set value in L2 Redis cache."""
        if not self._redis_client:
            return False

        try:
            prefixed_key = f"{self._key_prefix}{key}"
            await self._redis_client.setex(
                prefixed_key,
                ttl,
                json_dumps(value, default=str),
            )
            return True
        except L2_CACHE_OPERATION_ERRORS as e:
            logger.warning(f"L2 cache set failed: {e}")
            return False

    async def _delete_from_l2(self, key: str) -> bool:
        """Delete value from L2 Redis cache."""
        if not self._redis_client:
            return False

        try:
            prefixed_key = f"{self._key_prefix}{key}"
            await self._redis_client.delete(prefixed_key)
            return True
        except L2_CACHE_OPERATION_ERRORS as e:
            logger.warning(f"L2 cache delete failed: {e}")
            return False

    def _record_latency(self, start_time: float) -> None:
        """Record latency for P99 calculation."""
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._latencies.append(latency_ms)

        # Keep window bounded
        if len(self._latencies) > self._latency_window_size:
            self._latencies = self._latencies[-self._latency_window_size :]

        # Update stats
        if self._latencies:
            sorted_latencies = sorted(self._latencies)
            p99_idx = int(len(sorted_latencies) * 0.99)
            self._stats.p99_latency_ms = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]
            self._stats.average_latency_ms = sum(self._latencies) / len(self._latencies)

    def clear(self) -> int:
        """Clear all caches.

        Returns:
            Number of entries cleared
        """
        count = len(self._l1_cache)
        self._l1_cache.clear()

        # Restore constitutional context
        for chunk_id, chunk in self._constitutional_context.items():
            task = asyncio.create_task(
                self.set(
                    f"constitutional:{chunk_id}",
                    chunk,
                    is_constitutional=True,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        return count

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    def get_metrics(self) -> JSONDict:
        """Get cache metrics as dict."""
        return {
            "total_requests": self._stats.total_requests,
            "l1_hits": self._stats.l1_hits,
            "l1_misses": self._stats.l1_misses,
            "l2_hits": self._stats.l2_hits,
            "l2_misses": self._stats.l2_misses,
            "hit_rate": self._stats.hit_rate,
            "l1_hit_rate": self._stats.l1_hit_rate,
            "p99_latency_ms": self._stats.p99_latency_ms,
            "average_latency_ms": self._stats.average_latency_ms,
            "evictions": self._stats.evictions,
            "writes": self._stats.writes,
            "l1_size": len(self._l1_cache),
            "constitutional_context_count": len(self._constitutional_context),
            "constitutional_context_hits": self._stats.constitutional_context_hits,
            "p99_target_ms": self.config.p99_latency_target_ms,
            "p99_within_target": self._stats.p99_latency_ms <= self.config.p99_latency_target_ms,
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "CONSTITUTIONAL_HASH",
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "CacheTier",
    "ConstitutionalContextCache",
]
