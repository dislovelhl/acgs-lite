"""
ACGS-2 Memory Profiler Integration
Constitutional Hash: 608508a9bd224290

Memory profiling for message processing using tracemalloc.
Designed for minimal latency impact (<5μs) using fire-and-forget async patterns.
"""

import asyncio
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_MEMORY_PROFILER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class ProfilingLevel(Enum):
    """Profiling detail level."""

    DISABLED = "disabled"
    SUMMARY = "summary"  # Just peak/current memory
    DETAILED = "detailed"  # Top allocations by file/line
    FULL = "full"  # Complete allocation traces


@dataclass
class MemorySnapshot:
    """A point-in-time memory snapshot."""

    timestamp: float
    current_bytes: int
    peak_bytes: int
    trace_id: str | None = None
    operation: str | None = None
    top_allocations: list[JSONDict] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def current_mb(self) -> float:
        return self.current_bytes / (1024 * 1024)

    @property
    def peak_mb(self) -> float:
        return self.peak_bytes / (1024 * 1024)

    def to_dict(self) -> JSONDict:
        return {
            "timestamp": self.timestamp,
            "current_bytes": self.current_bytes,
            "current_mb": round(self.current_mb, 2),
            "peak_bytes": self.peak_bytes,
            "peak_mb": round(self.peak_mb, 2),
            "trace_id": self.trace_id,
            "operation": self.operation,
            "top_allocations": self.top_allocations,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class MemoryDelta:
    """Memory change between two snapshots."""

    start_bytes: int
    end_bytes: int
    delta_bytes: int
    peak_bytes: int
    duration_ms: float
    operation: str
    trace_id: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def delta_mb(self) -> float:
        return self.delta_bytes / (1024 * 1024)

    @property
    def is_leak_candidate(self) -> bool:
        """Flags potential memory leaks (>10MB retained after operation)."""
        return self.delta_bytes > 10 * 1024 * 1024

    def to_dict(self) -> JSONDict:
        return {
            "start_bytes": self.start_bytes,
            "end_bytes": self.end_bytes,
            "delta_bytes": self.delta_bytes,
            "delta_mb": round(self.delta_mb, 2),
            "peak_bytes": self.peak_bytes,
            "duration_ms": round(self.duration_ms, 2),
            "operation": self.operation,
            "trace_id": self.trace_id,
            "is_leak_candidate": self.is_leak_candidate,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class MemoryProfilingConfig:
    """Configuration for memory profiling."""

    enabled: bool = False
    level: ProfilingLevel = ProfilingLevel.SUMMARY
    top_n_allocations: int = 10
    leak_threshold_bytes: int = 10 * 1024 * 1024  # 10MB
    queue_size: int = 1000
    flush_interval_s: float = 60.0
    trace_depth: int = 10  # tracemalloc frame depth


class AsyncMemoryQueue:
    """
    Fire-and-forget async queue for memory snapshots.

    Designed for <5μs latency impact on message processing.
    Snapshots are enqueued and processed asynchronously.
    """

    def __init__(
        self,
        config: MemoryProfilingConfig,
        callback: Callable[[MemorySnapshot], None] | None = None,
    ):
        self.config = config
        self.callback = callback
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=config.queue_size)
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._snapshots: list[MemorySnapshot] = []
        self._deltas: list[MemoryDelta] = []

    async def start(self) -> None:
        """Start the background worker."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"[{CONSTITUTIONAL_HASH}] Memory profiling queue started")

    async def stop(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info(f"[{CONSTITUTIONAL_HASH}] Memory profiling queue stopped")

    async def enqueue(self, snapshot: MemorySnapshot) -> bool:
        """
        Enqueue a memory snapshot (fire-and-forget).

        Returns False if queue is full (snapshot dropped).
        """
        if not self._running:
            return False

        try:
            self._queue.put_nowait(snapshot)
            return True
        except asyncio.QueueFull:
            return False

    async def _worker(self) -> None:
        """Background worker to process queued snapshots."""
        while self._running:
            try:
                snapshot = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=self.config.flush_interval_s,
                )
                self._snapshots.append(snapshot)

                if self.callback:
                    try:
                        self.callback(snapshot)
                    except _MEMORY_PROFILER_OPERATION_ERRORS as e:
                        logger.warning(f"[{CONSTITUTIONAL_HASH}] Callback error: {e}")

                # Trim old snapshots to prevent memory growth
                if len(self._snapshots) > self.config.queue_size:
                    self._snapshots = self._snapshots[-self.config.queue_size :]

            except TimeoutError:
                # Periodic flush/maintenance
                pass
            except asyncio.CancelledError:
                break
            except _MEMORY_PROFILER_OPERATION_ERRORS as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Memory queue worker error: {e}")

    def get_recent_snapshots(self, n: int = 100) -> list[MemorySnapshot]:
        """Get the most recent n snapshots."""
        return self._snapshots[-n:]

    def get_memory_stats(self) -> JSONDict:
        """Get aggregated memory statistics."""
        if not self._snapshots:
            return {
                "total_snapshots": 0,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        currents = [s.current_bytes for s in self._snapshots]
        peaks = [s.peak_bytes for s in self._snapshots]

        return {
            "total_snapshots": len(self._snapshots),
            "avg_current_mb": round(sum(currents) / len(currents) / (1024 * 1024), 2),
            "max_current_mb": round(max(currents) / (1024 * 1024), 2),
            "min_current_mb": round(min(currents) / (1024 * 1024), 2),
            "avg_peak_mb": round(sum(peaks) / len(peaks) / (1024 * 1024), 2),
            "max_peak_mb": round(max(peaks) / (1024 * 1024), 2),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


class MemoryProfiler:
    """
    Memory profiler with tracemalloc integration.

    Provides:
    - Point-in-time snapshots
    - Delta tracking between operations
    - Top allocation analysis
    - Async queue for fire-and-forget profiling
    """

    def __init__(self, config: MemoryProfilingConfig | None = None):
        self.config = config or MemoryProfilingConfig()
        self._started = False
        self._queue: AsyncMemoryQueue | None = None
        self._baseline: tracemalloc.Snapshot | None = None

    def start(self) -> None:
        """Start tracemalloc profiling."""
        if self._started or not self.config.enabled:
            return

        if self.config.level == ProfilingLevel.DISABLED:
            return

        try:
            tracemalloc.start(self.config.trace_depth)
            self._started = True
            self._baseline = tracemalloc.take_snapshot()
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Memory profiler started (level={self.config.level.value})"
            )
        except _MEMORY_PROFILER_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Failed to start tracemalloc: {e}")

    def stop(self) -> None:
        """Stop tracemalloc profiling."""
        if not self._started:
            return

        try:
            tracemalloc.stop()
            self._started = False
            logger.info(f"[{CONSTITUTIONAL_HASH}] Memory profiler stopped")
        except _MEMORY_PROFILER_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Failed to stop tracemalloc: {e}")

    def take_snapshot(
        self,
        operation: str | None = None,
        trace_id: str | None = None,
    ) -> MemorySnapshot:
        """Take a memory snapshot."""
        current, peak = tracemalloc.get_traced_memory()

        top_allocations = []
        if self._started and self.config.level in (ProfilingLevel.DETAILED, ProfilingLevel.FULL):
            snapshot = tracemalloc.take_snapshot()
            stats = snapshot.statistics("lineno")[: self.config.top_n_allocations]
            top_allocations = [
                {
                    "file": str(stat.traceback),
                    "size_bytes": stat.size,
                    "count": stat.count,
                }
                for stat in stats
            ]

        return MemorySnapshot(
            timestamp=time.monotonic(),
            current_bytes=current,
            peak_bytes=peak,
            trace_id=trace_id,
            operation=operation,
            top_allocations=top_allocations,
        )

    def reset_peak(self) -> None:
        """Reset the peak memory counter."""
        if self._started:
            tracemalloc.reset_peak()

    def compare_to_baseline(self) -> list[JSONDict] | None:
        """Compare current allocations to baseline."""
        if not self._started or not self._baseline:
            return None

        current = tracemalloc.take_snapshot()
        top_stats = current.compare_to(self._baseline, "lineno")

        return [
            {
                "file": str(stat.traceback),
                "size_diff": stat.size_diff,
                "count_diff": stat.count_diff,
            }
            for stat in top_stats[: self.config.top_n_allocations]
        ]

    def profile_async(
        self,
        operation: str,
        trace_id: str | None = None,
    ) -> "MemoryProfilingContext":
        """
        Return an async context manager for profiling a code block.

        Usage:
            async with profiler.profile_async("process_message", trace_id="abc") as ctx:
                result = await process(message)
            delta = ctx.delta  # Memory change during operation

        Args:
            operation: Name of the operation being profiled
            trace_id: Optional trace ID for correlation

        Returns:
            MemoryProfilingContext async context manager
        """
        return MemoryProfilingContext(
            profiler=self,
            operation=operation,
            trace_id=trace_id,
            queue=self._queue,
        )


class MemoryProfilingContext:
    """
    Context manager for profiling a code block's memory usage.

    Usage:
        async with MemoryProfilingContext(profiler, "process_message") as ctx:
            result = await process(message)

        delta = ctx.delta  # Memory change during operation
    """

    def __init__(
        self,
        profiler: MemoryProfiler,
        operation: str,
        trace_id: str | None = None,
        queue: AsyncMemoryQueue | None = None,
    ):
        self.profiler = profiler
        self.operation = operation
        self.trace_id = trace_id
        self.queue = queue
        self._start_snapshot: MemorySnapshot | None = None
        self._end_snapshot: MemorySnapshot | None = None
        self._start_time: float = 0
        self.delta: MemoryDelta | None = None

    async def __aenter__(self) -> "MemoryProfilingContext":
        if self.profiler.config.enabled:
            self.profiler.reset_peak()
            self._start_time = time.perf_counter()
            self._start_snapshot = self.profiler.take_snapshot(
                operation=f"{self.operation}_start",
                trace_id=self.trace_id,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self.profiler.config.enabled or not self._start_snapshot:
            return

        self._end_snapshot = self.profiler.take_snapshot(
            operation=f"{self.operation}_end",
            trace_id=self.trace_id,
        )

        duration_ms = (time.perf_counter() - self._start_time) * 1000

        self.delta = MemoryDelta(
            start_bytes=self._start_snapshot.current_bytes,
            end_bytes=self._end_snapshot.current_bytes,
            delta_bytes=self._end_snapshot.current_bytes - self._start_snapshot.current_bytes,
            peak_bytes=self._end_snapshot.peak_bytes,
            duration_ms=duration_ms,
            operation=self.operation,
            trace_id=self.trace_id,
        )

        # Fire-and-forget enqueue if queue is available
        if self.queue:
            await self.queue.enqueue(self._end_snapshot)

        # Log potential leaks
        if self.delta.is_leak_candidate:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Potential memory leak in {self.operation}: "
                f"+{self.delta.delta_mb:.2f}MB retained"
            )


# Global profiler instance (lazy initialization)
_profiler: MemoryProfiler | None = None
_queue: AsyncMemoryQueue | None = None


def get_memory_profiler(config: MemoryProfilingConfig | None = None) -> MemoryProfiler:
    """Get or create the global memory profiler."""
    global _profiler
    if _profiler is None:
        _profiler = MemoryProfiler(config or MemoryProfilingConfig())
    return _profiler


async def get_memory_queue(
    config: MemoryProfilingConfig | None = None,
) -> AsyncMemoryQueue:
    """Get or create the global memory queue."""
    global _queue
    if _queue is None:
        cfg = config or MemoryProfilingConfig()
        _queue = AsyncMemoryQueue(cfg)
        if cfg.enabled:
            await _queue.start()
    return _queue


def profile_memory(operation: str):
    """
    Decorator for profiling async function memory usage.

    Usage:
        @profile_memory("process_message")
        async def process_message(msg):
            ...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            profiler = get_memory_profiler()
            if not profiler.config.enabled:
                return await func(*args, **kwargs)

            trace_id = kwargs.get("trace_id") or (
                getattr(args[0], "trace_id", None) if args else None
            )

            async with MemoryProfilingContext(
                profiler=profiler,
                operation=operation,
                trace_id=trace_id,
            ):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


# Memory profiling availability flag
MEMORY_PROFILING_AVAILABLE = True
