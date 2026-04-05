"""
ACGS-2 Prometheus Compatibility Layer
Constitutional Hash: 608508a9bd224290

Re-exports from shared metrics/noop module for backward compatibility.
"""

from enhanced_agent_bus._compat.metrics.noop import (
    PROMETHEUS_AVAILABLE,
    Counter,
    Gauge,
    Histogram,
    Info,
    _safe_create_metric,
)

__all__ = [
    "PROMETHEUS_AVAILABLE",
    "Counter",
    "Gauge",
    "Histogram",
    "Info",
    "_safe_create_metric",
]
