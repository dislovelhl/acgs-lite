"""
ACGS-2 Circuit Breaker Prometheus Metrics

Constitutional Hash: 608508a9bd224290

This module defines Prometheus metrics for circuit breaker observability,
with no-op fallbacks when prometheus_client is not available.
"""

from enhanced_agent_bus._compat.metrics.noop import (
    PROMETHEUS_AVAILABLE,
    Counter,
    Gauge,
    _safe_create_metric,
)
from enhanced_agent_bus._compat.metrics.noop import (
    NoOpCounter as _NoOpCounter,
)
from enhanced_agent_bus._compat.metrics.noop import (
    NoOpGauge as _NoOpGauge,
)
from enhanced_agent_bus._compat.metrics.noop import (
    NoOpHistogram as _NoOpHistogram,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Circuit breaker state metric
acgs_circuit_breaker_state = _safe_create_metric(
    Gauge,
    "acgs_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["service", "severity"],
)

# Circuit breaker state changes counter
acgs_circuit_breaker_state_changes_total = _safe_create_metric(
    Counter,
    "acgs_circuit_breaker_state_changes_total",
    "Total circuit breaker state changes",
    ["service", "from_state", "to_state"],
)

# Circuit breaker failures counter
acgs_circuit_breaker_failures_total = _safe_create_metric(
    Counter,
    "acgs_circuit_breaker_failures_total",
    "Total failures recorded by circuit breakers",
    ["service", "error_type"],
)

# Circuit breaker successes counter
acgs_circuit_breaker_successes_total = _safe_create_metric(
    Counter,
    "acgs_circuit_breaker_successes_total",
    "Total successes recorded by circuit breakers",
    ["service"],
)

# Circuit breaker rejected requests counter
acgs_circuit_breaker_rejections_total = _safe_create_metric(
    Counter,
    "acgs_circuit_breaker_rejections_total",
    "Total requests rejected by circuit breakers",
    ["service", "fallback_strategy"],
)

# Fallback queue size gauge
acgs_circuit_breaker_queue_size = _safe_create_metric(
    Gauge,
    "acgs_circuit_breaker_queue_size",
    "Current size of retry queue for circuit breaker",
    ["service"],
)


__all__ = [
    "PROMETHEUS_AVAILABLE",
    "_NoOpCounter",
    "_NoOpGauge",
    "_NoOpHistogram",
    "_safe_create_metric",
    "acgs_circuit_breaker_failures_total",
    "acgs_circuit_breaker_queue_size",
    "acgs_circuit_breaker_rejections_total",
    "acgs_circuit_breaker_state",
    "acgs_circuit_breaker_state_changes_total",
    "acgs_circuit_breaker_successes_total",
]
