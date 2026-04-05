"""
ACGS-2 Performance Metrics Registry
Constitutional Hash: 608508a9bd224290

Extended Prometheus instrumentation for ACGS-2 performance metrics.
Provides specialized metrics for:
- Z3 constraint solver operations
- Adaptive governance threshold decisions
- Cache miss tracking by layer and reason
- Batch processing overhead
- MACI enforcement latency
- Constitutional validation rates
- OPA policy evaluation
- Deliberation layer processing

All metrics include the constitutional hash for compliance tracking.

Expert Reference: Michael Nygard (Release It!)
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from threading import Lock

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from ..structured_logging import get_logger
from .prometheus_compat import (
    Counter,
    Gauge,
    Histogram,
    _safe_create_metric,
)

logger = get_logger(__name__)
# =============================================================================
# Latency Bucket Definitions
# =============================================================================

Z3_SOLVER_LATENCY_BUCKETS = (1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0)
ADAPTIVE_THRESHOLD_BUCKETS = (0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0)
BATCH_OVERHEAD_BUCKETS = (10.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0)
OPA_POLICY_LATENCY_BUCKETS = (1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0)
DELIBERATION_LAYER_BUCKETS = (5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0)


# =============================================================================
# Z3 Solver Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_z3_solver_latency_ms: Histogram | None = None


def _get_z3_solver_latency() -> Histogram:
    """Get or create Z3 solver latency histogram."""
    global _z3_solver_latency_ms
    if _z3_solver_latency_ms is None:
        _z3_solver_latency_ms = _safe_create_metric(  # type: ignore[assignment]
            Histogram,
            "acgs2_z3_solver_latency_ms",
            "Z3 constraint solver execution latency in milliseconds",
            labels=["operation", "constitutional_hash"],
            buckets=Z3_SOLVER_LATENCY_BUCKETS,
        )
    return _z3_solver_latency_ms


def record_z3_solver_latency(latency_ms: float, operation: str = "solve") -> None:
    """
    Record Z3 solver execution latency.

    Args:
        latency_ms: Latency in milliseconds
        operation: Type of Z3 operation (solve, check, optimize)
    """
    metric = _get_z3_solver_latency()
    metric.labels(operation=operation, constitutional_hash=CONSTITUTIONAL_HASH).observe(latency_ms)


@contextmanager
def z3_solver_timer(operation: str = "solve") -> Generator[None, None, None]:
    """
    Context manager for timing Z3 solver operations.

    Args:
        operation: Type of Z3 operation

    Yields:
        None
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        record_z3_solver_latency(latency_ms, operation)


# =============================================================================
# Adaptive Threshold Decision Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_adaptive_threshold_decision_ms: Histogram | None = None


def _get_adaptive_threshold_decision() -> Histogram:
    """Get or create adaptive threshold decision histogram."""
    global _adaptive_threshold_decision_ms
    if _adaptive_threshold_decision_ms is None:
        _adaptive_threshold_decision_ms = _safe_create_metric(  # type: ignore[assignment]
            Histogram,
            "acgs2_adaptive_threshold_decision_ms",
            "Adaptive governance threshold decision latency in milliseconds",
            labels=["decision_type", "constitutional_hash"],
            buckets=ADAPTIVE_THRESHOLD_BUCKETS,
        )
    return _adaptive_threshold_decision_ms


def record_adaptive_threshold_decision(
    latency_ms: float,
    decision_type: str = "threshold_update",
) -> None:
    """
    Record adaptive threshold decision latency.

    Args:
        latency_ms: Latency in milliseconds
        decision_type: Type of decision (threshold_update, calibration, adjustment)
    """
    metric = _get_adaptive_threshold_decision()
    metric.labels(
        decision_type=decision_type,
        constitutional_hash=CONSTITUTIONAL_HASH,
    ).observe(latency_ms)


@contextmanager
def adaptive_threshold_timer(
    decision_type: str = "threshold_update",
) -> Generator[None, None, None]:
    """
    Context manager for timing adaptive threshold decisions.

    Args:
        decision_type: Type of decision

    Yields:
        None
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        record_adaptive_threshold_decision(latency_ms, decision_type)


# =============================================================================
# Cache Miss Reason Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_cache_miss_reasons: Counter | None = None


def _get_cache_miss_reasons() -> Counter:
    """Get or create cache miss reasons counter."""
    global _cache_miss_reasons
    if _cache_miss_reasons is None:
        _cache_miss_reasons = _safe_create_metric(  # type: ignore[assignment]
            Counter,
            "acgs2_cache_miss_reasons_total",
            "Cache miss counts by layer and reason",
            labels=["layer", "reason", "constitutional_hash"],
        )
    return _cache_miss_reasons


class CacheLayer(str, Enum):
    """Cache layer identifiers."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class CacheMissReason(str, Enum):
    """Cache miss reason types."""

    EXPIRED = "expired"
    EVICTED = "evicted"
    NOT_FOUND = "not_found"


def record_cache_miss(
    layer: CacheLayer | str,
    reason: CacheMissReason | str,
) -> None:
    """
    Record a cache miss with reason.

    Args:
        layer: Cache layer (L1, L2, L3)
        reason: Reason for miss (expired, evicted, not_found)
    """
    layer_val = layer.value if isinstance(layer, CacheLayer) else layer
    reason_val = reason.value if isinstance(reason, CacheMissReason) else reason

    metric = _get_cache_miss_reasons()
    metric.labels(
        layer=layer_val,
        reason=reason_val,
        constitutional_hash=CONSTITUTIONAL_HASH,
    ).inc()


# =============================================================================
# Batch Processing Overhead Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_batch_processing_overhead_us: Histogram | None = None


def _get_batch_processing_overhead() -> Histogram:
    """Get or create batch processing overhead histogram."""
    global _batch_processing_overhead_us
    if _batch_processing_overhead_us is None:
        _batch_processing_overhead_us = _safe_create_metric(  # type: ignore[assignment]
            Histogram,
            "acgs2_batch_processing_overhead_us",
            "Batch processing overhead in microseconds",
            labels=["batch_size_bucket", "constitutional_hash"],
            buckets=BATCH_OVERHEAD_BUCKETS,
        )
    return _batch_processing_overhead_us


def record_batch_processing_overhead(
    overhead_us: float,
    batch_size: int,
) -> None:
    """
    Record batch processing overhead.

    Args:
        overhead_us: Overhead in microseconds
        batch_size: Size of the batch being processed
    """
    # Bucket batch sizes for better cardinality control
    if batch_size <= 10:
        size_bucket = "1-10"
    elif batch_size <= 50:
        size_bucket = "11-50"
    elif batch_size <= 100:
        size_bucket = "51-100"
    elif batch_size <= 500:
        size_bucket = "101-500"
    else:
        size_bucket = "500+"

    metric = _get_batch_processing_overhead()
    metric.labels(
        batch_size_bucket=size_bucket,
        constitutional_hash=CONSTITUTIONAL_HASH,
    ).observe(overhead_us)


@contextmanager
def batch_overhead_timer(batch_size: int) -> Generator[None, None, None]:
    """
    Context manager for timing batch processing overhead.

    Args:
        batch_size: Size of the batch

    Yields:
        None
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        overhead_us = (time.perf_counter() - start) * 1_000_000
        record_batch_processing_overhead(overhead_us, batch_size)


# =============================================================================
# MACI Enforcement Latency Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_maci_enforcement_latency_p99: Gauge | None = None
_maci_latency_samples: deque[float] = deque(maxlen=1000)
_maci_latency_lock = Lock()


def _get_maci_enforcement_latency_p99() -> Gauge:
    """Get or create MACI enforcement P99 latency gauge."""
    global _maci_enforcement_latency_p99
    if _maci_enforcement_latency_p99 is None:
        _maci_enforcement_latency_p99 = _safe_create_metric(  # type: ignore[assignment]
            Gauge,
            "acgs2_maci_enforcement_latency_p99_ms",
            "P99 MACI enforcement latency in milliseconds",
            labels=["maci_role", "constitutional_hash"],
        )
    return _maci_enforcement_latency_p99


def record_maci_enforcement_latency(
    latency_ms: float,
    maci_role: str = "unknown",
) -> None:
    """
    Record MACI enforcement latency and update P99 gauge.

    Args:
        latency_ms: Latency in milliseconds
        maci_role: MACI role (EXECUTIVE, LEGISLATIVE, JUDICIAL, etc.)
    """
    with _maci_latency_lock:
        _maci_latency_samples.append(latency_ms)

        # Calculate P99 from samples
        if len(_maci_latency_samples) >= 10:
            sorted_samples = sorted(_maci_latency_samples)
            p99_index = int(len(sorted_samples) * 0.99)
            p99_value = sorted_samples[min(p99_index, len(sorted_samples) - 1)]

            metric = _get_maci_enforcement_latency_p99()
            metric.labels(
                maci_role=maci_role,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ).set(p99_value)


@contextmanager
def maci_enforcement_timer(maci_role: str = "unknown") -> Generator[None, None, None]:
    """
    Context manager for timing MACI enforcement operations.

    Args:
        maci_role: MACI role performing the enforcement

    Yields:
        None
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        record_maci_enforcement_latency(latency_ms, maci_role)


# =============================================================================
# Constitutional Validation Rate Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_constitutional_validation_rate: Counter | None = None


def _get_constitutional_validation_rate() -> Counter:
    """Get or create constitutional validation rate counter."""
    global _constitutional_validation_rate
    if _constitutional_validation_rate is None:
        _constitutional_validation_rate = _safe_create_metric(  # type: ignore[assignment]
            Counter,
            "acgs2_constitutional_validation_total",
            "Constitutional validation counts by result",
            labels=["result", "validation_type", "constitutional_hash"],
        )
    return _constitutional_validation_rate


class ValidationResult(str, Enum):
    """Constitutional validation result types."""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    HASH_MISMATCH = "hash_mismatch"
    TIMEOUT = "timeout"


def record_constitutional_validation(
    result: ValidationResult | str,
    validation_type: str = "standard",
) -> None:
    """
    Record a constitutional validation result.

    Args:
        result: Validation result (success, failure, error, hash_mismatch, timeout)
        validation_type: Type of validation performed
    """
    result_val = result.value if isinstance(result, ValidationResult) else result

    metric = _get_constitutional_validation_rate()
    metric.labels(
        result=result_val,
        validation_type=validation_type,
        constitutional_hash=CONSTITUTIONAL_HASH,
    ).inc()


# =============================================================================
# OPA Policy Evaluation Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_opa_policy_evaluation_ms: Histogram | None = None


def _get_opa_policy_evaluation() -> Histogram:
    """Get or create OPA policy evaluation histogram."""
    global _opa_policy_evaluation_ms
    if _opa_policy_evaluation_ms is None:
        _opa_policy_evaluation_ms = _safe_create_metric(  # type: ignore[assignment]
            Histogram,
            "acgs2_opa_policy_evaluation_ms",
            "OPA policy evaluation latency in milliseconds",
            labels=["policy_name", "decision", "constitutional_hash"],
            buckets=OPA_POLICY_LATENCY_BUCKETS,
        )
    return _opa_policy_evaluation_ms


def record_opa_policy_evaluation(
    latency_ms: float,
    policy_name: str = "default",
    decision: str = "allow",
) -> None:
    """
    Record OPA policy evaluation latency.

    Args:
        latency_ms: Latency in milliseconds
        policy_name: Name of the evaluated policy
        decision: Policy decision result (allow, deny, defer)
    """
    metric = _get_opa_policy_evaluation()
    metric.labels(
        policy_name=policy_name,
        decision=decision,
        constitutional_hash=CONSTITUTIONAL_HASH,
    ).observe(latency_ms)


@contextmanager
def opa_policy_timer(
    policy_name: str = "default",
) -> Generator[dict[str, str], None, None]:
    """
    Context manager for timing OPA policy evaluations.

    Args:
        policy_name: Name of the policy being evaluated

    Yields:
        Context dict to set decision result
    """
    start = time.perf_counter()
    context: dict[str, str] = {"decision": "allow"}
    try:
        yield context
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        record_opa_policy_evaluation(latency_ms, policy_name, context.get("decision", "allow"))


# =============================================================================
# Deliberation Layer Duration Metrics
# Constitutional Hash: 608508a9bd224290
# =============================================================================

_deliberation_layer_duration_ms: Histogram | None = None


def _get_deliberation_layer_duration() -> Histogram:
    """Get or create deliberation layer duration histogram."""
    global _deliberation_layer_duration_ms
    if _deliberation_layer_duration_ms is None:
        _deliberation_layer_duration_ms = _safe_create_metric(  # type: ignore[assignment]
            Histogram,
            "acgs2_deliberation_layer_duration_ms",
            "Deliberation layer processing duration in milliseconds",
            labels=["layer_type", "impact_score_bucket", "constitutional_hash"],
            buckets=DELIBERATION_LAYER_BUCKETS,
        )
    return _deliberation_layer_duration_ms


def record_deliberation_layer_duration(
    duration_ms: float,
    layer_type: str = "consensus",
    impact_score: float | None = None,
) -> None:
    """
    Record deliberation layer processing duration.

    Args:
        duration_ms: Duration in milliseconds
        layer_type: Type of deliberation (consensus, hitl, impact_scoring)
        impact_score: Optional impact score for bucketing
    """
    # Bucket impact scores for cardinality control
    if impact_score is None:
        score_bucket = "unknown"
    elif impact_score < 0.3:
        score_bucket = "low"
    elif impact_score < 0.6:
        score_bucket = "medium"
    elif impact_score < 0.8:
        score_bucket = "high"
    else:
        score_bucket = "critical"

    metric = _get_deliberation_layer_duration()
    metric.labels(
        layer_type=layer_type,
        impact_score_bucket=score_bucket,
        constitutional_hash=CONSTITUTIONAL_HASH,
    ).observe(duration_ms)


@contextmanager
def deliberation_layer_timer(
    layer_type: str = "consensus",
    impact_score: float | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for timing deliberation layer operations.

    Args:
        layer_type: Type of deliberation layer
        impact_score: Optional impact score

    Yields:
        None
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        record_deliberation_layer_duration(duration_ms, layer_type, impact_score)


# =============================================================================
# Performance Metrics Registry
# Constitutional Hash: 608508a9bd224290
# =============================================================================


@dataclass
class PerformanceMetricsRegistry:
    """
    Registry for all ACGS-2 performance metrics.

    Provides centralized access to all performance metrics with
    constitutional hash enforcement.

    Constitutional Hash: 608508a9bd224290
    """

    constitutional_hash: str = CONSTITUTIONAL_HASH

    def record_z3_latency(self, latency_ms: float, operation: str = "solve") -> None:
        """Record Z3 solver latency."""
        record_z3_solver_latency(latency_ms, operation)

    def record_adaptive_threshold(
        self,
        latency_ms: float,
        decision_type: str = "threshold_update",
    ) -> None:
        """Record adaptive threshold decision latency."""
        record_adaptive_threshold_decision(latency_ms, decision_type)

    def record_cache_miss(
        self,
        layer: CacheLayer | str,
        reason: CacheMissReason | str,
    ) -> None:
        """Record cache miss with reason."""
        record_cache_miss(layer, reason)

    def record_batch_overhead(self, overhead_us: float, batch_size: int) -> None:
        """Record batch processing overhead."""
        record_batch_processing_overhead(overhead_us, batch_size)

    def record_maci_latency(self, latency_ms: float, maci_role: str = "unknown") -> None:
        """Record MACI enforcement latency."""
        record_maci_enforcement_latency(latency_ms, maci_role)

    def record_validation(
        self,
        result: ValidationResult | str,
        validation_type: str = "standard",
    ) -> None:
        """Record constitutional validation result."""
        record_constitutional_validation(result, validation_type)

    def record_opa_evaluation(
        self,
        latency_ms: float,
        policy_name: str = "default",
        decision: str = "allow",
    ) -> None:
        """Record OPA policy evaluation latency."""
        record_opa_policy_evaluation(latency_ms, policy_name, decision)

    def record_deliberation(
        self,
        duration_ms: float,
        layer_type: str = "consensus",
        impact_score: float | None = None,
    ) -> None:
        """Record deliberation layer duration."""
        record_deliberation_layer_duration(duration_ms, layer_type, impact_score)


# =============================================================================
# Singleton Instance
# =============================================================================

_performance_metrics_registry: PerformanceMetricsRegistry | None = None


def get_performance_metrics() -> PerformanceMetricsRegistry:
    """Get or create the singleton performance metrics registry."""
    global _performance_metrics_registry
    if _performance_metrics_registry is None:
        _performance_metrics_registry = PerformanceMetricsRegistry()
    return _performance_metrics_registry


def reset_performance_metrics() -> None:
    """Reset the performance metrics registry (for testing)."""
    global _performance_metrics_registry
    global _z3_solver_latency_ms
    global _adaptive_threshold_decision_ms
    global _cache_miss_reasons
    global _batch_processing_overhead_us
    global _maci_enforcement_latency_p99
    global _constitutional_validation_rate
    global _opa_policy_evaluation_ms
    global _deliberation_layer_duration_ms

    _performance_metrics_registry = None
    _z3_solver_latency_ms = None
    _adaptive_threshold_decision_ms = None
    _cache_miss_reasons = None
    _batch_processing_overhead_us = None
    _maci_enforcement_latency_p99 = None
    _constitutional_validation_rate = None
    _opa_policy_evaluation_ms = None
    _deliberation_layer_duration_ms = None

    # Clear MACI latency samples
    with _maci_latency_lock:
        _maci_latency_samples.clear()


__all__ = [
    "ADAPTIVE_THRESHOLD_BUCKETS",
    "BATCH_OVERHEAD_BUCKETS",
    "DELIBERATION_LAYER_BUCKETS",
    "OPA_POLICY_LATENCY_BUCKETS",
    # Latency bucket definitions
    "Z3_SOLVER_LATENCY_BUCKETS",
    # Enums
    "CacheLayer",
    "CacheMissReason",
    # Registry
    "PerformanceMetricsRegistry",
    "ValidationResult",
    "adaptive_threshold_timer",
    "batch_overhead_timer",
    "deliberation_layer_timer",
    "get_performance_metrics",
    "maci_enforcement_timer",
    "opa_policy_timer",
    # Adaptive threshold metrics
    "record_adaptive_threshold_decision",
    # Batch metrics
    "record_batch_processing_overhead",
    # Cache metrics
    "record_cache_miss",
    # Constitutional validation metrics
    "record_constitutional_validation",
    # Deliberation metrics
    "record_deliberation_layer_duration",
    # MACI metrics
    "record_maci_enforcement_latency",
    # OPA metrics
    "record_opa_policy_evaluation",
    # Z3 metrics
    "record_z3_solver_latency",
    "reset_performance_metrics",
    "z3_solver_timer",
]
