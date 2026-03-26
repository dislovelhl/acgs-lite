"""
ACGS-2 Performance Monitor
Constitutional Hash: 608508a9bd224290

Performance monitoring and timing for the Enhanced Agent Bus.
Provides @timed decorator for automatic latency tracking and metrics aggregation.
Designed for minimal overhead (<1μs) using lock-free operations where possible.
"""

import asyncio
import functools
import inspect
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from acgs2_perf import compute_percentiles_nearest_rank

    PERF_KERNELS_AVAILABLE = True
except ImportError:
    PERF_KERNELS_AVAILABLE = False

logger = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., object])
MONITOR_WRAPPER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.CancelledError,
)


class MetricType(Enum):
    """Types of performance metrics."""

    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    CUSTOM = "custom"


@dataclass
class TimingRecord:
    """A single timing measurement."""

    operation: str
    duration_ms: float
    timestamp: float
    success: bool
    trace_id: str | None = None
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "operation": self.operation,
            "duration_ms": round(self.duration_ms, 3),
            "timestamp": self.timestamp,
            "success": self.success,
            "trace_id": self.trace_id,
            "metadata": self.metadata,
        }


@dataclass
class OperationMetrics:
    """Aggregated metrics for an operation."""

    operation: str
    count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    durations: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    error_count: int = 0
    last_updated: float = field(default_factory=time.time)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def add_record(self, record: TimingRecord) -> None:
        """Add a timing record to the metrics."""
        self.count += 1
        self.total_duration_ms += record.duration_ms
        self.min_duration_ms = min(self.min_duration_ms, record.duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, record.duration_ms)
        self.durations.append(record.duration_ms)
        if not record.success:
            self.error_count += 1
        self.last_updated = time.time()

    @property
    def mean_duration_ms(self) -> float:
        """Calculate mean duration."""
        if self.count == 0:
            return 0.0
        return self.total_duration_ms / self.count

    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage."""
        if self.count == 0:
            return 0.0
        return (self.error_count / self.count) * 100

    def get_percentile(self, percentile: float) -> float:
        """Calculate percentile latency (0-100)."""
        return self._compute_percentiles([percentile])[0]

    def _compute_percentiles(self, percentiles: list[float]) -> list[float]:
        """Compute nearest-rank percentiles with optional Rust acceleration."""
        if not self.durations:
            return [0.0 for _ in percentiles]

        sorted_durations = sorted(self.durations)

        if PERF_KERNELS_AVAILABLE:
            return compute_percentiles_nearest_rank(sorted_durations, percentiles)  # type: ignore[no-any-return]

        n = len(sorted_durations)
        results = []
        for percentile in percentiles:
            rank = math.ceil(n * percentile / 100)
            index = max(rank - 1, 0)
            results.append(sorted_durations[min(index, n - 1)])
        return results

    @property
    def p50_ms(self) -> float:
        """50th percentile (median) latency."""
        return self.get_percentile(50)

    @property
    def p95_ms(self) -> float:
        """95th percentile latency."""
        return self.get_percentile(95)

    @property
    def p99_ms(self) -> float:
        """99th percentile latency."""
        return self.get_percentile(99)

    def to_dict(self) -> JSONDict:
        p50, p95, p99 = self._compute_percentiles([50.0, 95.0, 99.0])
        return {
            "operation": self.operation,
            "count": self.count,
            "mean_ms": round(self.mean_duration_ms, 3),
            "min_ms": round(self.min_duration_ms, 3) if self.min_duration_ms != float("inf") else 0,
            "max_ms": round(self.max_duration_ms, 3),
            "p50_ms": round(p50, 3),
            "p95_ms": round(p95, 3),
            "p99_ms": round(p99, 3),
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 2),
            "last_updated": self.last_updated,
        }


class PerformanceMonitor:
    """
    Central performance monitoring system for Enhanced Agent Bus.

    Features:
    - Decorator-based timing (@timed)
    - Automatic metric aggregation
    - Percentile calculations (p50, p95, p99)
    - Thread-safe async operations
    - Configurable retention windows

    Usage:
        monitor = PerformanceMonitor()

        @monitor.timed("process_message")
        async def process_message(msg):
            # ... processing logic
            pass

        # Get metrics
        metrics = monitor.get_metrics()
    """

    def __init__(self, max_records_per_operation: int = 10000):
        self._metrics: dict[str, OperationMetrics] = {}
        self._records: deque[TimingRecord] = deque(maxlen=max_records_per_operation)
        self._max_records_per_operation = max_records_per_operation
        self._lock = asyncio.Lock()
        self._enabled = True
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._background_tasks: set[asyncio.Task[object]] = set()

    def _create_timing_record(
        self, operation_name: str, start_time: float, success: bool, trace_id: str | None
    ) -> TimingRecord:
        """Create a timing record from execution data."""
        duration_ms = (time.perf_counter() - start_time) * 1000
        return TimingRecord(
            operation=operation_name,
            duration_ms=duration_ms,
            timestamp=time.time(),
            success=success,
            trace_id=trace_id,
        )

    def _store_record_safely(self, record: TimingRecord) -> None:
        """Store record using appropriate method based on event loop context."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                _t = asyncio.create_task(self._add_record(record))
                self._background_tasks.add(_t)
                _t.add_done_callback(self._background_tasks.discard)
                return
        except RuntimeError:
            pass
        # No event loop available, store directly
        self._store_record_sync(record)

    def _create_async_timed_wrapper(self, func: F, operation_name: str) -> Callable[..., object]:
        """Create async wrapper for timed function."""

        @functools.wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            if not self._enabled:
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            success = True
            trace_id = kwargs.get("trace_id")

            try:
                result = await func(*args, **kwargs)
                return result
            except MONITOR_WRAPPER_ERRORS:
                success = False
                raise
            finally:
                record = self._create_timing_record(operation_name, start_time, success, trace_id)
                _t = asyncio.create_task(self._add_record(record))
                self._background_tasks.add(_t)
                _t.add_done_callback(self._background_tasks.discard)

        return async_wrapper

    def _create_sync_timed_wrapper(self, func: F, operation_name: str) -> Callable[..., object]:
        """Create sync wrapper for timed function."""

        @functools.wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            if not self._enabled:
                return func(*args, **kwargs)

            start_time = time.perf_counter()
            success = True
            trace_id = kwargs.get("trace_id")

            try:
                result = func(*args, **kwargs)
                return result
            except MONITOR_WRAPPER_ERRORS:
                success = False
                raise
            finally:
                record = self._create_timing_record(operation_name, start_time, success, trace_id)
                self._store_record_safely(record)

        return sync_wrapper

    def timed(self, operation_name: str) -> Callable[[F], F]:
        """
        Decorator to time function execution.

        Args:
            operation_name: Name of the operation being timed

        Returns:
            Decorator function that wraps the target

        Usage:
            @monitor.timed("process_message")
            async def process_message(msg):
                pass
        """

        def decorator(func: F) -> F:
            if inspect.iscoroutinefunction(func):
                wrapper = self._create_async_timed_wrapper(func, operation_name)
            else:
                wrapper = self._create_sync_timed_wrapper(func, operation_name)

            return wrapper  # type: ignore[return-value]

        return decorator

    async def _add_record(self, record: TimingRecord) -> None:
        """Add a timing record asynchronously."""
        async with self._lock:
            self._store_record_sync(record)

    def _store_record_sync(self, record: TimingRecord) -> None:
        """Store record synchronously (internal use with lock held)."""
        self._records.append(record)

        if record.operation not in self._metrics:
            self._metrics[record.operation] = OperationMetrics(operation=record.operation)

        self._metrics[record.operation].add_record(record)

    def record_timing(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        trace_id: str | None = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Manually record a timing measurement.

        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
            success: Whether the operation succeeded
            trace_id: Optional trace ID for correlation
            metadata: Optional additional metadata
        """
        if not self._enabled:
            return

        record = TimingRecord(
            operation=operation,
            duration_ms=duration_ms,
            timestamp=time.time(),
            success=success,
            trace_id=trace_id,
            metadata=metadata or {},
        )

        # Use appropriate storage method based on context
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._add_record(record))
        except RuntimeError:
            # No event loop available
            self._store_record_sync(record)

    def get_metrics(self, operation: str | None = None) -> JSONDict:
        """
        Get performance metrics.

        Args:
            operation: Optional operation name to filter by

        Returns:
            Dict containing metrics summary
        """
        if operation:
            if operation in self._metrics:
                return {
                    "operation": operation,
                    "metrics": self._metrics[operation].to_dict(),
                    "constitutional_hash": self.constitutional_hash,
                }
            return {"error": f"Operation '{operation}' not found"}

        all_metrics = {op: metrics.to_dict() for op, metrics in self._metrics.items()}

        # Calculate global statistics
        total_count = sum(m.count for m in self._metrics.values())
        total_errors = sum(m.error_count for m in self._metrics.values())
        global_error_rate = (total_errors / total_count * 100) if total_count > 0 else 0

        return {
            "operations": all_metrics,
            "summary": {
                "total_operations": len(self._metrics),
                "total_records": len(self._records),
                "total_count": total_count,
                "total_errors": total_errors,
                "global_error_rate": round(global_error_rate, 2),
            },
            "constitutional_hash": self.constitutional_hash,
            "timestamp": time.time(),
        }

    def get_operation_names(self) -> list[str]:
        """Get list of all tracked operation names."""
        return list(self._metrics.keys())

    def clear_metrics(self, operation: str | None = None) -> None:
        """
        Clear metrics for a specific operation or all operations.

        Args:
            operation: Optional operation name to clear
        """
        if operation:
            if operation in self._metrics:
                del self._metrics[operation]
                # Also clear records for this operation
                self._records = deque(
                    [r for r in self._records if r.operation != operation],
                    maxlen=self._max_records_per_operation,
                )
        else:
            self._metrics.clear()
            self._records.clear()

    def enable(self) -> None:
        """Enable performance monitoring."""
        self._enabled = True
        logger.info("Performance monitoring enabled")

    def disable(self) -> None:
        """Disable performance monitoring."""
        self._enabled = False
        logger.info("Performance monitoring disabled")

    @property
    def is_enabled(self) -> bool:
        """Check if monitoring is enabled."""
        return self._enabled


# Global instance for shared use
_global_monitor: PerformanceMonitor | None = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get or create the global performance monitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


def set_performance_monitor(monitor: PerformanceMonitor) -> None:
    """Set the global performance monitor instance."""
    global _global_monitor
    _global_monitor = monitor


# Convenience decorator using global monitor
def timed(operation_name: str) -> Callable[[F], F]:
    """
    Convenience decorator using global performance monitor.

    Args:
        operation_name: Name of the operation being timed

    Usage:
        @timed("process_message")
        async def process_message(msg):
            pass
    """
    monitor = get_performance_monitor()
    return monitor.timed(operation_name)
