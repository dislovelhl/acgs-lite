"""
ACGS-2 Enhanced Agent Bus - Performance Optimization
Constitutional Hash: cdd01ef066bc6cf2

Phase 6 implementation providing:
- AsyncPipelineOptimizer: Parallel task execution with semaphore-limited concurrency
- ResourcePool: Generic object pooling for expensive resources
- MemoryOptimizer: Lazy loading and cache management for memory efficiency
- LatencyReducer: Connection pooling and batch operations for reduced latency

Part of Agent Orchestration Improvements Phases 4-7.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import (
    Any,
    Generic,
    TypeVar,
)

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")

# Feature flag for performance optimization
PERFORMANCE_OPTIMIZATION_AVAILABLE = True


# =============================================================================
# Task 6.1: Async Pipeline Optimizer
# =============================================================================


@dataclass
class PipelineStage:
    """Single stage in an async processing pipeline.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    name: str
    handler: Callable[..., Coroutine[Any, Any, Any]]
    timeout: float = 30.0
    parallel: bool = False
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


@dataclass
class PipelineResult:
    """Result from a pipeline execution.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    stage_name: str
    output: Any
    duration_ms: float
    success: bool
    error: str | None = None
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


class AsyncPipelineOptimizer:
    """
    Execute pipeline stages with semaphore-limited concurrency.

    Stages marked ``parallel=True`` are gathered concurrently within
    their group.  Sequential stages run in order.  A shared semaphore
    caps overall in-flight coroutines to avoid resource exhaustion.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        max_concurrency: int = 16,
        default_timeout: float = 30.0,
    ) -> None:
        self._stages: list[PipelineStage] = []
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._default_timeout = default_timeout
        self._stats: dict[str, int | float] = {
            "runs": 0,
            "stage_successes": 0,
            "stage_failures": 0,
            "total_duration_ms": 0.0,
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def add_stage(self, stage: PipelineStage) -> None:
        """Append a stage to the pipeline."""
        self._stages.append(stage)

    async def _run_stage(self, stage: PipelineStage, input_data: Any) -> PipelineResult:
        """Run a single stage with timeout and semaphore control."""
        start = time.monotonic()
        async with self._semaphore:
            try:
                timeout = stage.timeout or self._default_timeout
                output = await asyncio.wait_for(stage.handler(input_data), timeout=timeout)
                duration_ms = (time.monotonic() - start) * 1000.0
                self._stats["stage_successes"] = int(self._stats["stage_successes"]) + 1
                self._stats["total_duration_ms"] = (
                    float(self._stats["total_duration_ms"]) + duration_ms
                )
                return PipelineResult(
                    stage_name=stage.name,
                    output=output,
                    duration_ms=duration_ms,
                    success=True,
                )
            except TimeoutError:
                duration_ms = (time.monotonic() - start) * 1000.0
                self._stats["stage_failures"] = int(self._stats["stage_failures"]) + 1
                logger.warning(
                    "[%s] Stage '%s' timed out after %.1fms",
                    CONSTITUTIONAL_HASH,
                    stage.name,
                    duration_ms,
                )
                return PipelineResult(
                    stage_name=stage.name,
                    output=None,
                    duration_ms=duration_ms,
                    success=False,
                    error=f"Timeout after {stage.timeout}s",
                )
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                self._stats["stage_failures"] = int(self._stats["stage_failures"]) + 1
                logger.error(
                    "[%s] Stage '%s' failed: %s",
                    CONSTITUTIONAL_HASH,
                    stage.name,
                    exc,
                )
                return PipelineResult(
                    stage_name=stage.name,
                    output=None,
                    duration_ms=duration_ms,
                    success=False,
                    error=str(exc),
                )

    async def run(self, input_data: Any) -> list[PipelineResult]:
        """
        Execute all pipeline stages in order.

        Consecutive parallel stages are batched and gathered concurrently.
        Sequential (non-parallel) stages block until the previous group
        completes, feeding the last successful output forward.

        Returns a flat list of PipelineResult for every stage.
        """
        self._stats["runs"] = int(self._stats["runs"]) + 1
        results: list[PipelineResult] = []
        current_input: Any = input_data

        # Group consecutive parallel stages; sequential stages form solo groups.
        groups: list[list[PipelineStage]] = []
        buf: list[PipelineStage] = []
        for stage in self._stages:
            if stage.parallel:
                buf.append(stage)
            else:
                if buf:
                    groups.append(buf)
                    buf = []
                groups.append([stage])
        if buf:
            groups.append(buf)

        for group in groups:
            if len(group) == 1:
                result = await self._run_stage(group[0], current_input)
                results.append(result)
                if result.success:
                    current_input = result.output
            else:
                group_results = await asyncio.gather(
                    *[self._run_stage(s, current_input) for s in group],
                    return_exceptions=False,
                )
                results.extend(group_results)
                # Pass last successful output from the group forward
                for gr in reversed(group_results):
                    if gr.success:
                        current_input = gr.output
                        break

        return results

    def get_stats(self) -> JSONDict:
        """Return pipeline execution statistics."""
        runs = int(self._stats["runs"])
        return {
            **self._stats,
            "stages_registered": len(self._stages),
            "avg_duration_ms": (float(self._stats["total_duration_ms"]) / max(1, runs)),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# Task 6.2: Resource Pool (Generic Object Pooling)
# =============================================================================


@dataclass
class PooledResource(Generic[T]):
    """Wrapper around a poolable resource.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    resource: T
    resource_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    use_count: int = 0
    in_use: bool = False
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def mark_acquired(self) -> None:
        """Mark resource as acquired."""
        self.in_use = True
        self.last_used = datetime.now()
        self.use_count += 1

    def mark_released(self) -> None:
        """Mark resource as released back to pool."""
        self.in_use = False
        self.last_used = datetime.now()


ResourceFactory = Callable[[], Coroutine[Any, Any, T]]


class ResourcePool(Generic[T]):
    """
    Generic async resource pool with configurable size limits.

    Provides acquire/release semantics and an async context manager
    for safe resource lifecycle management.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        factory: ResourceFactory[T],
        max_size: int = 10,
        min_size: int = 1,
        max_idle_seconds: int = 300,
    ) -> None:
        self._factory = factory
        self._max_size = max_size
        self._min_size = min_size
        self._max_idle = timedelta(seconds=max_idle_seconds)

        self._available: list[PooledResource[T]] = []
        self._all: list[PooledResource[T]] = []
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)
        self._stats: dict[str, int] = {
            "acquired": 0,
            "released": 0,
            "created": 0,
            "evicted": 0,
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def _create_resource(self) -> PooledResource[T]:
        """Create a new pooled resource."""
        resource = await self._factory()
        resource_id = hashlib.sha256(f"{id(resource)}{time.time_ns()}".encode()).hexdigest()[:12]
        pooled = PooledResource(resource=resource, resource_id=resource_id)
        self._all.append(pooled)
        self._stats["created"] += 1
        logger.debug(
            "[%s] ResourcePool created resource %s (%d/%d)",
            CONSTITUTIONAL_HASH,
            resource_id,
            len(self._all),
            self._max_size,
        )
        return pooled

    async def acquire(self) -> PooledResource[T]:
        """
        Acquire a resource from the pool.

        Blocks if the pool is exhausted until one is released.
        Creates new resources up to *max_size*.
        """
        async with self._not_empty:
            while True:
                # Evict idle resources first to keep pool fresh
                await self._evict_idle()

                if self._available:
                    pooled = self._available.pop()
                    pooled.mark_acquired()
                    self._stats["acquired"] += 1
                    return pooled

                # Can we create a new one?
                in_use_count = sum(1 for r in self._all if r.in_use)
                if in_use_count < self._max_size:
                    pooled = await self._create_resource()
                    pooled.mark_acquired()
                    self._stats["acquired"] += 1
                    return pooled

                # Pool exhausted — wait for a release
                logger.debug(
                    "[%s] ResourcePool exhausted (%d/%d), waiting…",
                    CONSTITUTIONAL_HASH,
                    in_use_count,
                    self._max_size,
                )
                await self._not_empty.wait()

    async def release(self, pooled: PooledResource[T]) -> None:
        """Return a resource to the pool."""
        async with self._not_empty:
            pooled.mark_released()
            self._available.append(pooled)
            self._stats["released"] += 1
            self._not_empty.notify_all()

    @contextlib.asynccontextmanager
    async def resource(self):  # type: ignore[return]
        """Async context manager for safe resource acquisition."""
        pooled = await self.acquire()
        try:
            yield pooled
        finally:
            await self.release(pooled)

    async def _evict_idle(self) -> None:
        """Remove resources that have been idle past the TTL."""
        now = datetime.now()
        keep = []
        for pooled in self._available:
            if (
                now - pooled.last_used > self._max_idle
                and len(self._all) - len([r for r in self._all if r.in_use]) > self._min_size
            ):
                self._all.remove(pooled)
                self._stats["evicted"] += 1
            else:
                keep.append(pooled)
        self._available = keep

    async def close(self) -> None:
        """Release all resources and clear the pool."""
        async with self._lock:
            self._available.clear()
            self._all.clear()

    def get_stats(self) -> JSONDict:
        """Return pool statistics."""
        in_use = sum(1 for r in self._all if r.in_use)
        return {
            **self._stats,
            "pool_size": len(self._all),
            "available": len(self._available),
            "in_use": in_use,
            "max_size": self._max_size,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# Task 6.3: Memory Optimizer (Lazy Loading + LRU Cache)
# =============================================================================


@dataclass
class CacheEntry:
    """An entry in the MemoryOptimizer LRU cache.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    key: str
    value: Any
    size_bytes: int
    cached_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def touch(self) -> None:
        """Update access metadata."""
        self.last_accessed = datetime.now()
        self.access_count += 1


class MemoryOptimizer:
    """
    Lazy-loading LRU cache with memory-pressure-aware eviction.

    Loaders are registered per key prefix or exact key.  On first
    access the loader is invoked; subsequent accesses are served from
    cache until TTL expiry or memory pressure triggers eviction.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        max_entries: int = 1000,
        max_memory_bytes: int = 256 * 1024 * 1024,  # 256 MB
        default_ttl_seconds: int = 600,
    ) -> None:
        self._max_entries = max_entries
        self._max_memory_bytes = max_memory_bytes
        self._default_ttl = timedelta(seconds=default_ttl_seconds)

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._loaders: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self._lock = asyncio.Lock()
        self._stats: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "loads": 0,
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def register_loader(
        self,
        key: str,
        loader: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Register an async loader for a key or key prefix."""
        self._loaders[key] = loader
        logger.debug(
            "[%s] MemoryOptimizer: registered loader for '%s'",
            CONSTITUTIONAL_HASH,
            key,
        )

    def _find_loader(self, key: str) -> Callable[..., Coroutine[Any, Any, Any]] | None:
        """Find loader by exact key or longest matching prefix."""
        if key in self._loaders:
            return self._loaders[key]
        # Prefix match (longest wins)
        matches = [p for p in self._loaders if key.startswith(p)]
        if matches:
            return self._loaders[max(matches, key=len)]
        return None

    async def get(self, key: str, *loader_args: Any, **loader_kwargs: Any) -> Any:
        """
        Retrieve a value, loading lazily if not cached.

        Returns ``None`` if no loader is registered and the key is absent.
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                # Check TTL
                if datetime.now() - entry.cached_at <= self._default_ttl:
                    entry.touch()
                    self._cache.move_to_end(key)
                    self._stats["hits"] += 1
                    return entry.value
                # Expired
                del self._cache[key]

            self._stats["misses"] += 1

        # Load outside lock to avoid blocking other cache accesses
        loader = self._find_loader(key)
        if loader is None:
            return None

        self._stats["loads"] += 1
        value = await loader(*loader_args, **loader_kwargs)

        async with self._lock:
            await self._maybe_evict()
            size_bytes = len(str(value).encode())
            entry = CacheEntry(key=key, value=value, size_bytes=size_bytes)
            entry.touch()
            self._cache[key] = entry
            self._cache.move_to_end(key)

        return value

    async def put(self, key: str, value: Any) -> None:
        """Explicitly cache a value under *key*."""
        async with self._lock:
            await self._maybe_evict()
            size_bytes = len(str(value).encode())
            entry = CacheEntry(key=key, value=value, size_bytes=size_bytes)
            self._cache[key] = entry
            self._cache.move_to_end(key)

    async def evict(self, key: str) -> bool:
        """Remove a single key from the cache. Returns True if it existed."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["evictions"] += 1
                return True
            return False

    async def clear(self) -> int:
        """Clear the entire cache. Returns number of evicted entries."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats["evictions"] += count
            return count

    async def _maybe_evict(self) -> None:
        """Evict LRU entries if at capacity or memory limit."""
        total_bytes = sum(e.size_bytes for e in self._cache.values())

        while (
            len(self._cache) >= self._max_entries or total_bytes > self._max_memory_bytes
        ) and self._cache:
            _key, evicted = self._cache.popitem(last=False)
            total_bytes -= evicted.size_bytes
            self._stats["evictions"] += 1

    def get_stats(self) -> JSONDict:
        """Return cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        total_bytes = sum(e.size_bytes for e in self._cache.values())
        return {
            **self._stats,
            "cache_entries": len(self._cache),
            "cache_bytes": total_bytes,
            "hit_rate": self._stats["hits"] / max(1, total),
            "loaders_registered": len(self._loaders),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# Task 6.4: Latency Reducer (Connection Pooling + Batch Operations)
# =============================================================================


@dataclass
class BatchConfig:
    """Configuration for batch processing operations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    max_batch_size: int = 100
    max_wait_seconds: float = 0.05  # 50 ms
    max_concurrent_batches: int = 10
    enable_auto_tuning: bool = True
    target_latency_ms: float = 100.0
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


@dataclass
class BatchFlushResult:
    """Result from flushing a batch.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    topic: str
    items_flushed: int
    duration_ms: float
    success: bool
    error: str | None = None
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


class _BatchBuffer:
    """Internal buffer for a single topic."""

    def __init__(self, topic: str, config: BatchConfig) -> None:
        self.topic = topic
        self.config = config
        self._items: list[Any] = []
        self._created_at: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def add(self, item: Any) -> bool:
        """Add item. Returns True if buffer is now full."""
        async with self._lock:
            self._items.append(item)
            return len(self._items) >= self.config.max_batch_size

    async def flush(self) -> list[Any]:
        """Drain and return current batch."""
        async with self._lock:
            items = list(self._items)
            self._items.clear()
            self._created_at = time.monotonic()
            return items

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self._created_at

    def __len__(self) -> int:
        return len(self._items)


BatchProcessor = Callable[[str, list[Any]], Coroutine[Any, Any, None]]


class LatencyReducer:
    """
    Reduce tail latency via connection pooling and micro-batching.

    Items submitted to a topic are accumulated in a buffer and
    flushed either when the batch reaches ``max_batch_size`` or
    after ``max_wait_seconds``, whichever comes first.  A semaphore
    limits concurrent flush coroutines to prevent overload.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        batch_config: BatchConfig | None = None,
        processor: BatchProcessor | None = None,
    ) -> None:
        self._config = batch_config or BatchConfig()
        self._processor = processor
        self._buffers: dict[str, _BatchBuffer] = {}
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_batches)
        self._flush_tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._stats: dict[str, int | float] = {
            "items_submitted": 0,
            "batches_flushed": 0,
            "items_flushed": 0,
            "flush_errors": 0,
            "total_flush_ms": 0.0,
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def _get_or_create_buffer(self, topic: str) -> _BatchBuffer:
        """Return the buffer for *topic*, creating it if absent."""
        async with self._lock:
            if topic not in self._buffers:
                self._buffers[topic] = _BatchBuffer(topic, self._config)
            return self._buffers[topic]

    async def submit(self, topic: str, item: Any) -> None:
        """
        Submit an item to the batch buffer for *topic*.

        Triggers an immediate flush if the buffer reaches capacity.
        Otherwise a background timer-flush is scheduled.
        """
        buf = await self._get_or_create_buffer(topic)
        is_full = await buf.add(item)
        self._stats["items_submitted"] = int(self._stats["items_submitted"]) + 1

        if is_full:
            await self.flush(topic)
        else:
            # Ensure a timer-based flush task is running
            async with self._lock:
                if topic not in self._flush_tasks or self._flush_tasks[topic].done():
                    self._flush_tasks[topic] = asyncio.create_task(self._timed_flush(topic))

    async def _timed_flush(self, topic: str) -> None:
        """Wait for the batch window, then flush."""
        await asyncio.sleep(self._config.max_wait_seconds)
        await self.flush(topic)

    async def flush(self, topic: str) -> BatchFlushResult:
        """
        Flush the current batch for *topic* synchronously.

        If a processor is registered, it is called with the batch.
        Returns a BatchFlushResult describing the outcome.
        """
        buf = await self._get_or_create_buffer(topic)
        items = await buf.flush()

        if not items:
            return BatchFlushResult(
                topic=topic,
                items_flushed=0,
                duration_ms=0.0,
                success=True,
            )

        start = time.monotonic()
        async with self._semaphore:
            try:
                if self._processor is not None:
                    await self._processor(topic, items)

                duration_ms = (time.monotonic() - start) * 1000.0
                self._stats["batches_flushed"] = int(self._stats["batches_flushed"]) + 1
                self._stats["items_flushed"] = int(self._stats["items_flushed"]) + len(items)
                self._stats["total_flush_ms"] = float(self._stats["total_flush_ms"]) + duration_ms
                logger.debug(
                    "[%s] LatencyReducer flushed %d items for topic '%s' in %.1fms",
                    CONSTITUTIONAL_HASH,
                    len(items),
                    topic,
                    duration_ms,
                )
                return BatchFlushResult(
                    topic=topic,
                    items_flushed=len(items),
                    duration_ms=duration_ms,
                    success=True,
                )
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000.0
                self._stats["flush_errors"] = int(self._stats["flush_errors"]) + 1
                logger.error(
                    "[%s] LatencyReducer flush error for topic '%s': %s",
                    CONSTITUTIONAL_HASH,
                    topic,
                    exc,
                )
                return BatchFlushResult(
                    topic=topic,
                    items_flushed=0,
                    duration_ms=duration_ms,
                    success=False,
                    error=str(exc),
                )

    async def flush_all(self) -> list[BatchFlushResult]:
        """Flush all pending topic buffers."""
        async with self._lock:
            topics = list(self._buffers.keys())
        return await asyncio.gather(*[self.flush(t) for t in topics])

    async def close(self) -> None:
        """Flush all pending batches and cancel background tasks."""
        # Cancel pending timer tasks
        async with self._lock:
            for task in self._flush_tasks.values():
                if not task.done():
                    task.cancel()
            self._flush_tasks.clear()

        await self.flush_all()

    def get_stats(self) -> JSONDict:
        """Return latency reducer statistics."""
        batches = int(self._stats["batches_flushed"])
        return {
            **self._stats,
            "topics_tracked": len(self._buffers),
            "avg_flush_ms": (float(self._stats["total_flush_ms"]) / max(1, batches)),
            "pending_items": sum(len(b) for b in self._buffers.values()),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# Factory Functions
# =============================================================================


def create_async_pipeline(
    max_concurrency: int = 16,
    default_timeout: float = 30.0,
) -> AsyncPipelineOptimizer:
    """
    Create a configured AsyncPipelineOptimizer.

    Constitutional Hash: cdd01ef066bc6cf2
    """
    return AsyncPipelineOptimizer(
        max_concurrency=max_concurrency,
        default_timeout=default_timeout,
    )


def create_resource_pool(
    factory: ResourceFactory[T],
    max_size: int = 10,
    min_size: int = 1,
    max_idle_seconds: int = 300,
) -> ResourcePool[T]:
    """
    Create a configured ResourcePool.

    Constitutional Hash: cdd01ef066bc6cf2
    """
    return ResourcePool(
        factory=factory,
        max_size=max_size,
        min_size=min_size,
        max_idle_seconds=max_idle_seconds,
    )


def create_latency_reducer(
    batch_config: BatchConfig | None = None,
    processor: BatchProcessor | None = None,
) -> LatencyReducer:
    """
    Create a configured LatencyReducer.

    Constitutional Hash: cdd01ef066bc6cf2
    """
    return LatencyReducer(batch_config=batch_config, processor=processor)


def create_memory_optimizer(
    max_entries: int = 1000,
    max_memory_bytes: int = 256 * 1024 * 1024,
    default_ttl_seconds: int = 600,
) -> MemoryOptimizer:
    """
    Create a configured MemoryOptimizer.

    Constitutional Hash: cdd01ef066bc6cf2
    """
    return MemoryOptimizer(
        max_entries=max_entries,
        max_memory_bytes=max_memory_bytes,
        default_ttl_seconds=default_ttl_seconds,
    )


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Feature flag
    "PERFORMANCE_OPTIMIZATION_AVAILABLE",
    "AsyncPipelineOptimizer",
    # Task 6.4: Latency Reducer
    "BatchConfig",
    "BatchFlushResult",
    "BatchProcessor",
    # Task 6.3: Memory Optimizer
    "CacheEntry",
    "LatencyReducer",
    "MemoryOptimizer",
    "PipelineResult",
    # Task 6.1: Async Pipeline Optimizer
    "PipelineStage",
    # Task 6.2: Resource Pool
    "PooledResource",
    "ResourceFactory",
    "ResourcePool",
    "create_async_pipeline",
    "create_latency_reducer",
    "create_memory_optimizer",
    "create_resource_pool",
]
