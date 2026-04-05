# pyright: reportAssignmentType=false, reportMissingImports=false
"""
Transaction Coordinator Metrics Module

Constitutional Hash: 608508a9bd224290

Comprehensive metrics collection for TransactionCoordinator with:
- Transaction count tracking (total, success, failure)
- Latency percentiles (p50, p95, p99)
- Compensation metrics
- Checkpoint operations
- Concurrent transaction gauge
- Consistency ratio monitoring
- Prometheus integration with no-op fallbacks
- Health check endpoints

Supports 99.9% consistency target with detailed observability.
"""

import time
from collections import deque
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, cast

# Constitutional compliance
try:
    from enhanced_agent_bus._compat.types import (
        CONSTITUTIONAL_HASH,
        JSONDict,
    )
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"  # type: ignore[misc,assignment]
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from acgs2_perf import compute_percentiles_floor_index

    PERF_KERNELS_AVAILABLE = True
except ImportError:
    PERF_KERNELS_AVAILABLE = False

logger = get_logger(__name__)
_TRANSACTION_METRICS_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class CounterLike(Protocol):
    def labels(self, **kwargs: object) -> "CounterLike": ...

    def inc(self, amount: float = 1) -> None: ...


class GaugeLike(Protocol):
    def labels(self, **kwargs: object) -> "GaugeLike": ...

    def set(self, value: float) -> None: ...

    def inc(self, amount: float = 1) -> None: ...

    def dec(self, amount: float = 1) -> None: ...


class HistogramLike(Protocol):
    def labels(self, **kwargs: object) -> "HistogramLike": ...

    def observe(self, value: float) -> None: ...


class InfoLike(Protocol):
    def info(self, value: dict[str, str]) -> None: ...


# =============================================================================
# Prometheus Client Handling
# =============================================================================

_prometheus_available = False
_registry = None
_pc: object = None
try:
    import prometheus_client as _pc  # type: ignore[no-redef]
    from prometheus_client import Counter, Gauge, Histogram, Info

    _prometheus_available = True
    logger.info(f"[{CONSTITUTIONAL_HASH}] Prometheus client available for transaction metrics")
except ImportError:
    logger.warning(f"[{CONSTITUTIONAL_HASH}] Prometheus client not available, using no-op metrics")

    # No-op implementations
    class Counter:  # type: ignore[no-redef]
        """No-op counter when prometheus_client is not available."""

        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self  # type: ignore[return-value]

        def inc(self, amount: float = 1) -> None:
            pass

    class Gauge:  # type: ignore[no-redef]
        """No-op gauge when prometheus_client is not available."""

        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self  # type: ignore[return-value]

        def set(self, value: float) -> None:
            pass

        def inc(self, amount: float = 1) -> None:
            pass

        def dec(self, amount: float = 1) -> None:
            pass

    class Histogram:  # type: ignore[no-redef]
        """No-op histogram when prometheus_client is not available."""

        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self  # type: ignore[return-value]

        def observe(self, value: float) -> None:
            pass

        def time(self) -> "_NoOpTimer":
            return _NoOpTimer()

    class Info:  # type: ignore[no-redef]
        """No-op info metric when prometheus_client is not available."""

        def __init__(self, *args, **kwargs):
            pass

        def info(self, value: dict[str, str]) -> None:
            pass

    class _NoOpTimer:
        """No-op timer context manager."""

        def __enter__(self) -> "_NoOpTimer":
            return self

        def __exit__(self, *args):
            pass

    _registry = None

PROMETHEUS_AVAILABLE = _prometheus_available
REGISTRY = _pc.REGISTRY if _pc is not None else _registry  # type: ignore[attr-defined]

# =============================================================================
# No-Op Classes for Duplicate Metric Handling
# =============================================================================


class _NoOpCounter:
    """No-op counter for duplicate registration fallback."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def labels(self, **kwargs: object) -> "_NoOpCounter":
        return self

    def inc(self, amount: float = 1) -> None:
        pass


class _NoOpGauge:
    """No-op gauge for duplicate registration fallback."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def labels(self, **kwargs: object) -> "_NoOpGauge":
        return self

    def set(self, value: float) -> None:
        pass

    def inc(self, amount: float = 1) -> None:
        pass

    def dec(self, amount: float = 1) -> None:
        pass


class _NoOpHistogram:
    """No-op histogram for duplicate registration fallback."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def labels(self, **kwargs: object) -> "_NoOpHistogram":
        return self

    def observe(self, value: float) -> None:
        pass


# =============================================================================
# Metric Registration Helper
# =============================================================================

_METRICS_CACHE: JSONDict = {}


def _get_or_create_metric(
    metric_class: type,
    name: str,
    documentation: str,
    labels: list[str] | None = None,
    buckets: list[float] | None = None,
) -> object:
    """
    Get existing metric from cache or create new one.

    Handles duplicate registration gracefully by returning existing metrics
    from the Prometheus registry.

    Args:
        metric_class: The metric class (Counter, Gauge, Histogram)
        name: Metric name
        documentation: Metric description
        labels: List of label names for the metric
        buckets: Histogram buckets (only for Histogram)

    Returns:
        The metric instance
    """
    cache_key = f"{metric_class.__name__}:{name}"
    if cache_key in _METRICS_CACHE:
        return _METRICS_CACHE[cache_key]

    try:
        if not PROMETHEUS_AVAILABLE:
            # Return no-op implementation
            _metric: _NoOpCounter | _NoOpGauge | _NoOpHistogram
            if metric_class == Counter:
                _metric = _NoOpCounter()
            elif metric_class == Gauge:
                _metric = _NoOpGauge()
            elif metric_class == Histogram:
                _metric = _NoOpHistogram()
            else:
                _metric = _NoOpCounter()
            _METRICS_CACHE[cache_key] = _metric
            return _metric

        # Create actual Prometheus metric
        if metric_class == Histogram:
            if buckets:
                metric = metric_class(name, documentation, labelnames=labels or [], buckets=buckets)
            else:
                metric = metric_class(name, documentation, labelnames=labels or [])
        elif metric_class == Info:
            metric = metric_class(name, documentation)
        else:
            metric = metric_class(name, documentation, labelnames=labels or [])

        _METRICS_CACHE[cache_key] = metric
        return metric

    except ValueError as e:
        if "Duplicated timeseries" in str(e) or "already registered" in str(e):
            # Try to retrieve from registry
            if REGISTRY is not None:
                try:
                    for collector in REGISTRY._names_to_collectors.values():
                        if getattr(collector, "_name", None) == name:
                            _METRICS_CACHE[cache_key] = collector
                            return collector
                except (AttributeError, TypeError):
                    pass

        # Return no-op as fallback
        logger.warning(f"Failed to create metric {name}: {e}, using no-op")
        if metric_class == Histogram:
            return _NoOpHistogram()
        elif metric_class == Gauge:
            return _NoOpGauge()
        else:
            return _NoOpCounter()


def reset_metrics_cache() -> None:
    """Clear the metrics cache. Useful for testing."""
    _METRICS_CACHE.clear()


# =============================================================================
# Enums and Types
# =============================================================================


class TransactionStatus(str, Enum):
    """Transaction status for metric labels."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    COMPENSATED = "compensated"


class CompensationStatus(str, Enum):
    """Compensation status for metric labels."""

    SUCCESS = "success"
    FAILURE = "failure"


class CheckpointOperation(str, Enum):
    """Checkpoint operation type for metric labels."""

    SAVE = "save"
    RESTORE = "restore"


class HealthStatus(str, Enum):
    """Health status for the coordinator."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# =============================================================================
# Latency Buckets
# =============================================================================

# Transaction latency buckets (targeting p99 < 5s)
TRANSACTION_LATENCY_BUCKETS = [
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
]

# Compensation latency buckets (typically faster)
COMPENSATION_LATENCY_BUCKETS = [
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
]

# Checkpoint latency buckets
CHECKPOINT_LATENCY_BUCKETS = [
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
]

# =============================================================================
# TransactionMetrics Class
# =============================================================================


@dataclass
class TransactionMetrics:
    """
    Comprehensive metrics collection for TransactionCoordinator.

    Tracks:
    - Transaction counts (total, success, failed)
    - Transaction latency percentiles (p50, p95, p99)
    - Compensation counts and latency
    - Checkpoint save/restore operations
    - Concurrent transaction gauge
    - Consistency ratio

    Constitutional Hash: 608508a9bd224290
    """

    # Internal state for tracking when Prometheus is not available
    _initialized: bool = field(default=False, repr=False)
    # PERF FIX (2026-03): Use bounded deque instead of list+slice.  The previous
    # implementation appended to a list and sliced when it exceeded _max_samples,
    # which is O(n) per trim and causes memory churn.  deque(maxlen=N) is O(1)
    # append with automatic eviction — no manual trimming needed.
    _duration_samples: deque[float] = field(
        default_factory=lambda: deque(maxlen=10_000), repr=False
    )
    _compensation_samples: deque[float] = field(
        default_factory=lambda: deque(maxlen=10_000), repr=False
    )
    _max_samples: int = field(default=10_000, repr=False)

    # Internal counters for accurate tracking (especially in tests)
    _internal_total: int = field(default=0, repr=False)
    _internal_success: int = field(default=0, repr=False)
    _internal_failed: int = field(default=0, repr=False)
    _internal_compensations: int = field(default=0, repr=False)
    _internal_concurrent: int = field(default=0, repr=False)

    # Prometheus metrics (initialized in __post_init__)
    transactions_total: CounterLike = field(init=False)
    transactions_success: CounterLike = field(init=False)
    transactions_failed: CounterLike = field(init=False)
    transaction_latency: HistogramLike = field(init=False)
    compensations_total: CounterLike = field(init=False)
    compensation_latency: HistogramLike = field(init=False)
    checkpoint_saves: CounterLike = field(init=False)
    checkpoint_restores: CounterLike = field(init=False)
    checkpoint_latency: HistogramLike = field(init=False)
    concurrent_transactions: GaugeLike = field(init=False)
    consistency_ratio: GaugeLike = field(init=False)
    health_status: GaugeLike = field(init=False)
    transaction_info: InfoLike = field(init=False)

    def __post_init__(self) -> None:
        """Initialize all Prometheus metrics."""
        if self._initialized:
            return

        # Transaction counters
        self.transactions_total = cast(
            CounterLike,
            _get_or_create_metric(
                Counter,
                "acgs_transactions_total",
                "Total number of transactions started",
                ["status"],
            ),
        )

        self.transactions_success = cast(
            CounterLike,
            _get_or_create_metric(
                Counter,
                "acgs_transactions_success_total",
                "Total number of successful transactions",
            ),
        )

        self.transactions_failed = cast(
            CounterLike,
            _get_or_create_metric(
                Counter,
                "acgs_transactions_failed_total",
                "Total number of failed transactions",
                ["reason"],
            ),
        )

        # Transaction latency histogram
        self.transaction_latency = cast(
            HistogramLike,
            _get_or_create_metric(
                Histogram,
                "acgs_transaction_latency_seconds",
                "Transaction execution latency in seconds",
                ["status"],
                buckets=TRANSACTION_LATENCY_BUCKETS,
            ),
        )

        # Compensation metrics
        self.compensations_total = cast(
            CounterLike,
            _get_or_create_metric(
                Counter,
                "acgs_compensations_total",
                "Total number of compensation operations executed",
                ["status"],
            ),
        )

        self.compensation_latency = cast(
            HistogramLike,
            _get_or_create_metric(
                Histogram,
                "acgs_compensation_latency_seconds",
                "Compensation operation latency in seconds",
                buckets=COMPENSATION_LATENCY_BUCKETS,
            ),
        )

        # Checkpoint metrics
        self.checkpoint_saves = cast(
            CounterLike,
            _get_or_create_metric(
                Counter,
                "acgs_checkpoint_saves_total",
                "Total number of checkpoint save operations",
                ["status"],
            ),
        )

        self.checkpoint_restores = cast(
            CounterLike,
            _get_or_create_metric(
                Counter,
                "acgs_checkpoint_restores_total",
                "Total number of checkpoint restore operations",
                ["status"],
            ),
        )

        self.checkpoint_latency = cast(
            HistogramLike,
            _get_or_create_metric(
                Histogram,
                "acgs_checkpoint_latency_seconds",
                "Checkpoint operation latency in seconds",
                ["operation"],
                buckets=CHECKPOINT_LATENCY_BUCKETS,
            ),
        )

        # Gauges
        self.concurrent_transactions = cast(
            GaugeLike,
            _get_or_create_metric(
                Gauge,
                "acgs_concurrent_transactions",
                "Number of currently executing transactions",
            ),
        )

        self.consistency_ratio = cast(
            GaugeLike,
            _get_or_create_metric(
                Gauge,
                "acgs_consistency_ratio",
                "Transaction consistency ratio (0.0-1.0)",
            ),
        )

        self.health_status = cast(
            GaugeLike,
            _get_or_create_metric(
                Gauge,
                "acgs_transaction_coordinator_health",
                "Health status of transaction coordinator (0=unhealthy, 1=degraded, 2=healthy)",
            ),
        )

        # Info metric
        self.transaction_info = cast(
            InfoLike,
            _get_or_create_metric(
                Info,
                "acgs_transaction_coordinator_info",
                "Transaction coordinator metadata",
            ),
        )

        # Set info
        try:
            self.transaction_info.info(
                {
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "version": "2.0.0",
                    "consistency_target": "99.9",
                }
            )
        except _TRANSACTION_METRICS_OPERATION_ERRORS as e:
            logger.debug(f"Failed to set transaction info: {e}")

        self._initialized = True

    # ==========================================================================
    # Transaction Metrics Recording
    # ==========================================================================

    def record_transaction_start(self) -> None:
        """Record the start of a transaction."""
        self._internal_total += 1
        self._internal_concurrent += 1
        self.transactions_total.labels(status="started").inc()
        self.concurrent_transactions.inc()

    def record_transaction_success(self, duration_seconds: float) -> None:
        """
        Record a successful transaction.

        Args:
            duration_seconds: Transaction duration in seconds
        """
        self._internal_success += 1
        self._internal_concurrent = max(0, self._internal_concurrent - 1)
        self.transactions_total.labels(status=TransactionStatus.SUCCESS).inc()
        self.transactions_success.inc()
        self.transaction_latency.labels(status=TransactionStatus.SUCCESS).observe(duration_seconds)
        self.concurrent_transactions.dec()
        self._record_duration(duration_seconds)
        self._update_consistency_ratio()

    def record_transaction_failure(self, duration_seconds: float, reason: str = "unknown") -> None:
        """
        Record a failed transaction.

        Args:
            duration_seconds: Transaction duration in seconds
            reason: Failure reason (e.g., 'timeout', 'error', 'compensated')
        """
        self._internal_failed += 1
        self._internal_concurrent = max(0, self._internal_concurrent - 1)
        self.transactions_total.labels(status=TransactionStatus.FAILURE).inc()
        self.transactions_failed.labels(reason=reason).inc()
        self.transaction_latency.labels(status=TransactionStatus.FAILURE).observe(duration_seconds)
        self.concurrent_transactions.dec()
        self._record_duration(duration_seconds)
        self._update_consistency_ratio()

    def record_transaction_timeout(self, duration_seconds: float) -> None:
        """
        Record a transaction that timed out.

        Args:
            duration_seconds: Time until timeout in seconds
        """
        self._internal_failed += 1
        self._internal_concurrent = max(0, self._internal_concurrent - 1)
        self.transactions_total.labels(status=TransactionStatus.TIMEOUT).inc()
        self.transactions_failed.labels(reason="timeout").inc()
        self.transaction_latency.labels(status=TransactionStatus.TIMEOUT).observe(duration_seconds)
        self.concurrent_transactions.dec()
        self._record_duration(duration_seconds)
        self._update_consistency_ratio()

    def record_transaction_compensated(self) -> None:
        """Record that a transaction was fully compensated."""
        self.transactions_total.labels(status=TransactionStatus.COMPENSATED).inc()
        self._update_consistency_ratio()

    # ==========================================================================
    # Compensation Metrics Recording
    # ==========================================================================

    def record_compensation_start(self) -> None:
        """Record the start of a compensation operation."""
        pass  # Compensations are recorded on completion

    def record_compensation_success(self, duration_seconds: float) -> None:
        """
        Record a successful compensation.

        Args:
            duration_seconds: Compensation duration in seconds
        """
        self._internal_compensations += 1
        self.compensations_total.labels(status=CompensationStatus.SUCCESS).inc()
        self.compensation_latency.observe(duration_seconds)
        self._record_compensation_duration(duration_seconds)

    def record_compensation_failure(self, duration_seconds: float) -> None:
        """
        Record a failed compensation.

        Args:
            duration_seconds: Time until failure in seconds
        """
        self.compensations_total.labels(status=CompensationStatus.FAILURE).inc()
        self.compensation_latency.observe(duration_seconds)

    # ==========================================================================
    # Checkpoint Metrics Recording
    # ==========================================================================

    def record_checkpoint_save(self, duration_seconds: float, success: bool = True) -> None:
        """
        Record a checkpoint save operation.

        Args:
            duration_seconds: Save operation duration in seconds
            success: Whether the save was successful
        """
        status = CompensationStatus.SUCCESS if success else CompensationStatus.FAILURE
        self.checkpoint_saves.labels(status=status).inc()
        self.checkpoint_latency.labels(operation=CheckpointOperation.SAVE).observe(duration_seconds)

    def record_checkpoint_restore(self, duration_seconds: float, success: bool = True) -> None:
        """
        Record a checkpoint restore operation.

        Args:
            duration_seconds: Restore operation duration in seconds
            success: Whether the restore was successful
        """
        status = CompensationStatus.SUCCESS if success else CompensationStatus.FAILURE
        self.checkpoint_restores.labels(status=status).inc()
        self.checkpoint_latency.labels(operation=CheckpointOperation.RESTORE).observe(
            duration_seconds
        )

    # ==========================================================================
    # Internal Tracking
    # ==========================================================================

    def _record_duration(self, duration_seconds: float) -> None:
        """
        Record duration for percentile calculations.

        Args:
            duration_seconds: Duration in seconds
        """
        self._duration_samples.append(duration_seconds * 1000)

    def _record_compensation_duration(self, duration_seconds: float) -> None:
        """
        Record compensation duration for percentile calculations.

        Args:
            duration_seconds: Duration in seconds
        """
        self._compensation_samples.append(duration_seconds * 1000)

    def _update_consistency_ratio(self) -> None:
        """Update the consistency ratio gauge based on current metrics."""
        ratio = self.get_consistency_ratio()
        self.consistency_ratio.set(ratio)

    # ==========================================================================
    # Metrics Queries
    # ==========================================================================

    def get_consistency_ratio(self) -> float:
        """
        Calculate the current consistency ratio.

        Returns:
            Ratio of successful transactions to total (0.0-1.0)
        """
        # Use internal counters for accurate tracking
        total = self._internal_total
        success = self._internal_success

        if total == 0:
            return 1.0  # No transactions = perfect consistency
        return success / total

    def _get_counter_value(self, counter: CounterLike, **labels: str) -> float:
        """Get counter value, handling both Prometheus and no-op counters."""
        try:
            counter_value_obj = getattr(
                counter.labels(**labels) if labels else counter, "_value", None
            )
            getter = getattr(counter_value_obj, "get", None)
            if callable(getter):
                value = getter()
                return float(value) if isinstance(value, (int, float)) else 0.0
            if labels:
                return 0.0
            return 0.0
        except _TRANSACTION_METRICS_OPERATION_ERRORS:
            return 0.0

    @staticmethod
    def _compute_percentiles_from_samples(samples: Sequence[float]) -> dict[str, float]:
        """Compute p50/p95/p99 using floor-index semantics."""
        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_samples = sorted(samples)
        if PERF_KERNELS_AVAILABLE:
            p50, p95, p99 = compute_percentiles_floor_index(sorted_samples, [50.0, 95.0, 99.0])
            return {"p50": p50, "p95": p95, "p99": p99}

        n = len(sorted_samples)

        def percentile(p: float) -> float:
            idx = int(n * p / 100)
            return sorted_samples[min(idx, n - 1)]

        return {"p50": percentile(50), "p95": percentile(95), "p99": percentile(99)}

    def get_latency_percentiles(self) -> dict[str, float]:
        """
        Calculate latency percentiles from samples.

        Returns:
            Dictionary with p50, p95, p99 latency in milliseconds
        """
        return self._compute_percentiles_from_samples(self._duration_samples)

    def get_compensation_percentiles(self) -> dict[str, float]:
        """
        Calculate compensation latency percentiles.

        Returns:
            Dictionary with p50, p95, p99 compensation latency in milliseconds
        """
        return self._compute_percentiles_from_samples(self._compensation_samples)

    def get_health_status_enum(self) -> HealthStatus:
        """
        Determine health status based on consistency ratio.

        Returns:
            HealthStatus: HEALTHY (>=99.9%), DEGRADED (>=99%), UNHEALTHY (<99%)
        """
        ratio = self.get_consistency_ratio()

        if ratio >= 0.999:
            return HealthStatus.HEALTHY
        elif ratio >= 0.99:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.UNHEALTHY

    def update_health_gauge(self) -> None:
        """Update the health status gauge."""
        status = self.get_health_status_enum()
        value = {"healthy": 2, "degraded": 1, "unhealthy": 0}.get(status.value, 0)
        self.health_status.set(value)

    def get_metrics_summary(self) -> JSONDict:
        """
        Get a comprehensive metrics summary.

        Returns:
            Dictionary with all key metrics
        """
        latency_percentiles = self.get_latency_percentiles()
        compensation_percentiles = self.get_compensation_percentiles()
        health = self.get_health_status_enum()

        return {
            "consistency_ratio": self.get_consistency_ratio(),
            "health_status": health.value,
            "latency_ms": latency_percentiles,
            "compensation_latency_ms": compensation_percentiles,
            "concurrent_transactions": self._get_gauge_value(self.concurrent_transactions),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def _get_gauge_value(self, gauge: GaugeLike) -> float:
        """Get gauge value, handling both Prometheus and no-op gauges."""
        # Return internal counter for concurrent transactions
        if gauge is self.concurrent_transactions:
            return float(self._internal_concurrent)
        try:
            gauge_value_obj = getattr(gauge, "_value", None)
            getter = getattr(gauge_value_obj, "get", None)
            if callable(getter):
                value = getter()
                return float(value) if isinstance(value, (int, float)) else 0.0
            return 0.0
        except (AttributeError, Exception):
            return 0.0

    # ==========================================================================
    # Context Managers for Timing
    # ==========================================================================

    @contextmanager
    def transaction_timer(self, expected_success: bool = True) -> Generator[JSONDict, None, None]:
        """
        Context manager for timing transactions.

        Usage:
            with metrics.transaction_timer() as timer:
                # Execute transaction
                pass
            # Metrics automatically recorded

        Args:
            expected_success: Whether the transaction is expected to succeed

        Yields:
            Dictionary with start time and status
        """
        context: JSONDict = {
            "start_time": time.perf_counter(),
            "success": expected_success,
            "recorded": False,
        }

        self.record_transaction_start()

        try:
            yield context
        except _TRANSACTION_METRICS_OPERATION_ERRORS:
            context["success"] = False
            raise
        finally:
            if not context["recorded"]:
                duration = time.perf_counter() - context["start_time"]
                if context["success"]:
                    self.record_transaction_success(duration)
                else:
                    self.record_transaction_failure(duration, reason="error")
                context["recorded"] = True

    @contextmanager
    def compensation_timer(self) -> Generator[JSONDict, None, None]:
        """
        Context manager for timing compensation operations.

        Yields:
            Dictionary with start time and status
        """
        context: JSONDict = {
            "start_time": time.perf_counter(),
            "success": True,
            "recorded": False,
        }

        try:
            yield context
        except _TRANSACTION_METRICS_OPERATION_ERRORS:
            context["success"] = False
            raise
        finally:
            if not context["recorded"]:
                duration = time.perf_counter() - context["start_time"]
                if context["success"]:
                    self.record_compensation_success(duration)
                else:
                    self.record_compensation_failure(duration)
                context["recorded"] = True

    @contextmanager
    def checkpoint_timer(self, operation: CheckpointOperation) -> Generator[JSONDict, None, None]:
        """
        Context manager for timing checkpoint operations.

        Args:
            operation: The checkpoint operation type (save or restore)

        Yields:
            Dictionary with start time and status
        """
        context: JSONDict = {
            "start_time": time.perf_counter(),
            "success": True,
            "operation": operation,
            "recorded": False,
        }

        try:
            yield context
        except _TRANSACTION_METRICS_OPERATION_ERRORS:
            context["success"] = False
            raise
        finally:
            if not context["recorded"]:
                duration = time.perf_counter() - context["start_time"]
                if operation == CheckpointOperation.SAVE:
                    self.record_checkpoint_save(duration, context["success"])
                else:
                    self.record_checkpoint_restore(duration, context["success"])
                context["recorded"] = True


# =============================================================================
# Health, Dashboard, and Alerting (extracted to dedicated modules)
# =============================================================================

# Re-export for backward compatibility
from .transaction_coordinator_alerts import (
    ALERT_RULES,
    AlertRule,
    generate_alert_rules_yaml,
)
from .transaction_coordinator_health import (
    DashboardQueries,
    HealthChecker,
    HealthCheckResult,
)

# =============================================================================
# Global Instance
# =============================================================================


def get_transaction_metrics() -> TransactionMetrics:
    """Get or create the global TransactionMetrics instance via DI container.

    Returns:
        TransactionMetrics singleton instance
    """
    from enhanced_agent_bus._compat.di_container import DIContainer

    try:
        result: TransactionMetrics = DIContainer.get(TransactionMetrics)  # type: ignore[no-any-return]
        return result
    except KeyError:
        instance = TransactionMetrics()
        DIContainer.register(TransactionMetrics, instance)
        return instance


def reset_transaction_metrics() -> None:
    """Reset the global metrics instance. Useful for testing."""
    from enhanced_agent_bus._compat.di_container import DIContainer

    DIContainer.register(TransactionMetrics, TransactionMetrics())
    reset_metrics_cache()

    # Export public API


__all__ = [
    "ALERT_RULES",
    "CHECKPOINT_LATENCY_BUCKETS",
    "COMPENSATION_LATENCY_BUCKETS",
    "PROMETHEUS_AVAILABLE",
    "TRANSACTION_LATENCY_BUCKETS",
    "AlertRule",
    "CheckpointOperation",
    "CompensationStatus",
    "DashboardQueries",
    "HealthCheckResult",
    "HealthChecker",
    "HealthStatus",
    "TransactionMetrics",
    "TransactionStatus",
    "generate_alert_rules_yaml",
    "get_transaction_metrics",
    "reset_transaction_metrics",
]
