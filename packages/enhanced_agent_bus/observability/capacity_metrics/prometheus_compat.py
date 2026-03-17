"""
ACGS-2 Prometheus Compatibility Layer
Constitutional Hash: cdd01ef066bc6cf2

Re-exports from shared metrics/noop module for backward compatibility.
"""

from src.core.shared.metrics.noop import (
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
