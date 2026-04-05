"""
ACGS-2 Prometheus Metrics Configuration
Constitutional Hash: 608508a9bd224290

Implements the required metrics from SPEC_ACGS2_ENHANCED.md Section 6.1.
Per Expert Panel Review (Kelsey Hightower - Cloud Native Expert).

Metric Categories:
- Constitutional Validation metrics
- Caching metrics
- Policy metrics
- System metrics
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.metrics.noop import (
    CONTENT_TYPE_LATEST,
    PROMETHEUS_AVAILABLE,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    Info,
    _safe_create_metric,
    generate_latest,
)
from enhanced_agent_bus._compat.metrics.noop import (
    NoOpCounter as _NoOpCounter,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .structured_logging import get_logger

logger = get_logger(__name__)
PROMETHEUS_SYSTEM_INFO_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


# =============================================================================
# Metric Definitions per SPEC_ACGS2_ENHANCED.md Section 6.1
# =============================================================================

# Latency buckets for validation (targeting <5ms P99)
VALIDATION_LATENCY_BUCKETS = (0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)

# Confidence score buckets
CONFIDENCE_BUCKETS = (0.5, 0.7, 0.8, 0.9, 0.95, 0.99)

# Policy evaluation latency buckets
POLICY_LATENCY_BUCKETS = (0.001, 0.005, 0.01, 0.05)


# -----------------------------------------------------------------------------
# Constitutional Validation Metrics
# -----------------------------------------------------------------------------

# Lazy initialization to avoid duplicate metric registration
_acgs_constitutional_validations_total = None


def _get_constitutional_validations_counter() -> object:
    global _acgs_constitutional_validations_total
    if _acgs_constitutional_validations_total is None:
        if PROMETHEUS_AVAILABLE:
            try:
                _acgs_constitutional_validations_total = Counter(
                    "acgs_constitutional_validations_total",
                    "Total constitutional validations",
                    ["result", "principle_category", "agent_id"],
                )
            except ValueError as e:
                if "Duplicated timeseries" in str(e):
                    # Metric already exists, create a no-op wrapper
                    _acgs_constitutional_validations_total = _NoOpCounter()
                else:
                    raise
        else:
            _acgs_constitutional_validations_total = _NoOpCounter()
    return _acgs_constitutional_validations_total


acgs_constitutional_validations_total = _get_constitutional_validations_counter()

acgs_validation_latency_seconds = _safe_create_metric(
    Histogram,
    "acgs_validation_latency_seconds",
    "Validation request latency",
    ["endpoint", "result"],
    buckets=VALIDATION_LATENCY_BUCKETS,
)

acgs_validation_confidence = _safe_create_metric(
    Histogram,
    "acgs_validation_confidence",
    "Validation confidence scores",
    ["principle_category"],
    buckets=CONFIDENCE_BUCKETS,
)


# -----------------------------------------------------------------------------
# Caching Metrics
# -----------------------------------------------------------------------------

acgs_cache_operations_total = _safe_create_metric(
    Counter,
    "acgs_cache_operations_total",
    "Total cache operations",
    ["cache_tier", "operation", "result"],
)

acgs_cache_hit_ratio = _safe_create_metric(
    Gauge,
    "acgs_cache_hit_ratio",
    "Cache hit ratio",
    ["cache_tier"],
)

acgs_cache_size_bytes = _safe_create_metric(
    Gauge,
    "acgs_cache_size_bytes",
    "Cache size in bytes",
    ["cache_tier"],
)


# -----------------------------------------------------------------------------
# Policy Metrics
# -----------------------------------------------------------------------------

acgs_policy_evaluations_total = _safe_create_metric(
    Counter,
    "acgs_policy_evaluations_total",
    "Total policy evaluations",
    ["policy_id", "decision"],
)

acgs_policy_evaluation_latency_seconds = _safe_create_metric(
    Histogram,
    "acgs_policy_evaluation_latency_seconds",
    "Policy evaluation latency",
    buckets=POLICY_LATENCY_BUCKETS,
)


# -----------------------------------------------------------------------------
# System Metrics
# -----------------------------------------------------------------------------

acgs_active_connections = _safe_create_metric(
    Gauge,
    "acgs_active_connections",
    "Active connections",
    ["service", "connection_type"],
)

acgs_request_queue_size = _safe_create_metric(
    Gauge,
    "acgs_request_queue_size",
    "Request queue size",
    ["service"],
)

# Constitutional hash info metric
acgs_system_info = _safe_create_metric(
    Info,
    "acgs_system",
    "ACGS-2 system information",
)


# =============================================================================
# Helper Classes and Functions
# =============================================================================


class ValidationResult(str, Enum):
    """Validation result types for metric labels."""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    HASH_MISMATCH = "hash_mismatch"
    TIMEOUT = "timeout"


class CacheTier(str, Enum):
    """Cache tier types for metric labels."""

    L1 = "l1"
    L2 = "l2"
    L3 = "l3"


class CacheOperation(str, Enum):
    """Cache operation types for metric labels."""

    GET = "get"
    SET = "set"
    DELETE = "delete"
    EXPIRE = "expire"


class PolicyDecision(str, Enum):
    """Policy decision types for metric labels."""

    ALLOW = "allow"
    DENY = "deny"
    DEFER = "defer"


@dataclass
class MetricsCollector:
    """
    Centralized metrics collector for ACGS-2.

    Constitutional Hash: 608508a9bd224290

    Provides methods to record metrics following the spec in Section 6.1.
    """

    service_name: str = "acgs2-enhanced-agent-bus"
    constitutional_hash: str = CONSTITUTIONAL_HASH
    _initialized: bool = field(default=False, repr=False)

    def __post_init__(self):
        """Initialize system info metric."""
        if PROMETHEUS_AVAILABLE and not self._initialized:
            try:
                acgs_system_info.info(
                    {
                        "service": self.service_name,
                        "constitutional_hash": self.constitutional_hash,
                        "version": "3.0.0",
                    }
                )
                self._initialized = True
            except PROMETHEUS_SYSTEM_INFO_ERRORS as e:
                logger.warning(f"[{CONSTITUTIONAL_HASH}] Failed to set system info: {e}")

    # -------------------------------------------------------------------------
    # Constitutional Validation Metrics
    # -------------------------------------------------------------------------

    def record_validation(
        self,
        result: ValidationResult,
        principle_category: str,
        agent_id: str,
        latency_seconds: float,
        confidence: float | None = None,
        endpoint: str = "/api/v1/validate",
    ) -> None:
        """Record a constitutional validation event."""
        # Increment validation counter
        acgs_constitutional_validations_total.labels(
            result=result.value,
            principle_category=principle_category,
            agent_id=agent_id,
        ).inc()

        # Record latency
        acgs_validation_latency_seconds.labels(
            endpoint=endpoint,
            result=result.value,
        ).observe(latency_seconds)

        # Record confidence if provided
        if confidence is not None:
            acgs_validation_confidence.labels(
                principle_category=principle_category,
            ).observe(confidence)

    @contextmanager
    def validation_timer(
        self,
        endpoint: str = "/api/v1/validate",
    ) -> Generator[JSONDict, None, None]:
        """Context manager for timing validation operations."""
        start_time = time.perf_counter()
        context = {"start_time": start_time, "result": ValidationResult.SUCCESS}

        try:
            yield context
        except (RuntimeError, ValueError, TypeError, OSError):
            context["result"] = ValidationResult.ERROR
            raise
        finally:
            latency = time.perf_counter() - start_time
            acgs_validation_latency_seconds.labels(
                endpoint=endpoint,
                result=context["result"].value,  # type: ignore[attr-defined]
            ).observe(latency)

    # -------------------------------------------------------------------------
    # Cache Metrics
    # -------------------------------------------------------------------------

    def record_cache_operation(
        self,
        tier: CacheTier,
        operation: CacheOperation,
        hit: bool,
    ) -> None:
        """Record a cache operation."""
        result = "hit" if hit else "miss"
        acgs_cache_operations_total.labels(
            cache_tier=tier.value,
            operation=operation.value,
            result=result,
        ).inc()

    def update_cache_hit_ratio(self, tier: CacheTier, ratio: float) -> None:
        """Update cache hit ratio gauge."""
        acgs_cache_hit_ratio.labels(cache_tier=tier.value).set(ratio)

    def update_cache_size(self, tier: CacheTier, size_bytes: int) -> None:
        """Update cache size gauge."""
        acgs_cache_size_bytes.labels(cache_tier=tier.value).set(size_bytes)

    # -------------------------------------------------------------------------
    # Policy Metrics
    # -------------------------------------------------------------------------

    def record_policy_evaluation(
        self,
        policy_id: str,
        decision: PolicyDecision,
        latency_seconds: float,
    ) -> None:
        """Record a policy evaluation event."""
        acgs_policy_evaluations_total.labels(
            policy_id=policy_id,
            decision=decision.value,
        ).inc()

        acgs_policy_evaluation_latency_seconds.observe(latency_seconds)

    @contextmanager
    def policy_timer(self) -> Generator[None, None, None]:
        """Context manager for timing policy evaluations."""
        start_time = time.perf_counter()
        try:
            yield
        finally:
            latency = time.perf_counter() - start_time
            acgs_policy_evaluation_latency_seconds.observe(latency)

    # -------------------------------------------------------------------------
    # System Metrics
    # -------------------------------------------------------------------------

    def update_active_connections(
        self,
        service: str,
        connection_type: str,
        count: int,
    ) -> None:
        """Update active connections gauge."""
        acgs_active_connections.labels(
            service=service,
            connection_type=connection_type,
        ).set(count)

    def update_request_queue_size(self, service: str, size: int) -> None:
        """Update request queue size gauge."""
        acgs_request_queue_size.labels(service=service).set(size)

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format."""
        if PROMETHEUS_AVAILABLE:
            return bytes(generate_latest(REGISTRY))  # type: ignore[arg-type]
        return b""

    def get_content_type(self) -> str:
        """Get content type for metrics response."""
        return CONTENT_TYPE_LATEST if PROMETHEUS_AVAILABLE else "text/plain"


# =============================================================================
# Alerting Rule Definitions per Section 6.4
# =============================================================================


@dataclass
class AlertRule:
    """Prometheus alerting rule definition."""

    name: str
    condition: str
    severity: str
    channel: str
    description: str = ""


# Critical Alerts (P0, P1)
CRITICAL_ALERTS = [
    AlertRule(
        name="ConstitutionalHashViolation",
        condition='acgs_constitutional_validations_total{result="hash_mismatch"} > 0',
        severity="P0",
        channel="PagerDuty + Security",
        description="Constitutional hash mismatch detected - potential security violation",
    ),
    AlertRule(
        name="OPAUnavailable",
        condition='up{job="opa"} == 0 for 30s',
        severity="P1",
        channel="PagerDuty",
        description="OPA policy engine is unavailable",
    ),
]

# High Priority Alerts (P2)
HIGH_ALERTS = [
    AlertRule(
        name="HighErrorRate",
        condition='rate(acgs_constitutional_validations_total{result="error"}[5m]) '
        "/ rate(acgs_constitutional_validations_total[5m]) > 0.01",
        severity="P2",
        channel="PagerDuty",
        description="Error rate exceeds 1% threshold",
    ),
    AlertRule(
        name="HighLatency",
        condition="histogram_quantile(0.99, acgs_validation_latency_seconds) > 0.005",
        severity="P2",
        channel="Slack",
        description="P99 latency exceeds 5ms target",
    ),
]

# Warning Alerts (P3)
WARNING_ALERTS = [
    AlertRule(
        name="LowCacheHitRate",
        condition="acgs_cache_hit_ratio < 0.8",
        severity="P3",
        channel="Slack",
        description="Cache hit rate below 80% threshold",
    ),
]


def generate_prometheus_alert_rules() -> str:
    """Generate Prometheus alerting rules in YAML format."""
    rules = []

    for alert in CRITICAL_ALERTS + HIGH_ALERTS + WARNING_ALERTS:
        rules.append(f"""
  - alert: {alert.name}
    expr: {alert.condition}
    labels:
      severity: {alert.severity}
      constitutional_hash: {CONSTITUTIONAL_HASH}
    annotations:
      summary: "{alert.name}"
      description: "{alert.description}"
      channel: "{alert.channel}"
""")

    return f"""# ACGS-2 Prometheus Alerting Rules
# Constitutional Hash: {CONSTITUTIONAL_HASH}
# Generated at: {datetime.now(UTC).isoformat()}

groups:
  - name: acgs2_constitutional_governance
    rules:{"".join(rules)}
"""


# =============================================================================
# Global Metrics Collector Instance
# =============================================================================

_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics_collector() -> None:
    """Reset the global metrics collector (for testing)."""
    global _metrics_collector
    _metrics_collector = None


# =============================================================================
# FastAPI Integration
# =============================================================================


def create_metrics_endpoint() -> object | None:
    """Create a FastAPI metrics endpoint."""
    try:
        from fastapi import Response
        from fastapi.routing import APIRouter

        router = APIRouter()

        @router.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            collector = get_metrics_collector()
            return Response(
                content=collector.get_metrics(),
                media_type=collector.get_content_type(),
            )

        return router  # type: ignore[no-any-return]
    except ImportError:
        logger.warning(f"[{CONSTITUTIONAL_HASH}] FastAPI not available for metrics endpoint")
        return None
