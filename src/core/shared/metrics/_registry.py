"""
ACGS-2 Metric Registration Helpers (shared)
Constitutional Hash: cdd01ef066bc6cf2

Consolidated metric registration utilities used by both
``src.core.shared.metrics`` and ``src.core.shared.cache_metrics``.

Handles duplicate Prometheus registration gracefully (common in pytest
and multi-import scenarios).
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info

# Shared cache for registered metrics to avoid re-registration
_METRICS_CACHE: dict[str, object] = {}


def _find_existing_metric(name: str) -> object | None:
    """Find an existing metric by name in the Prometheus registry."""
    try:
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]

        for collector in REGISTRY._names_to_collectors.values():
            collector_name = getattr(collector, "_name", None)
            if collector_name == name:
                return collector
    except (RuntimeError, AttributeError, TypeError, ValueError):
        pass
    return None


def _get_or_create_histogram(
    name: str, description: str, labels: list[str], buckets: list[float] | None = None
) -> object:
    """Get existing or create new histogram metric."""
    if name in _METRICS_CACHE:
        return _METRICS_CACHE[name]

    existing = _find_existing_metric(name)
    if existing:
        _METRICS_CACHE[name] = existing
        return existing

    try:
        if buckets:
            metric = Histogram(name, description, labelnames=labels, buckets=buckets)
        else:
            metric = Histogram(name, description, labelnames=labels)
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError:
        existing = _find_existing_metric(name)
        if existing:
            _METRICS_CACHE[name] = existing
            return existing
        raise


def _get_or_create_counter(name: str, description: str, labels: list[str]) -> object:
    """Get existing or create new counter metric."""
    if name in _METRICS_CACHE:
        return _METRICS_CACHE[name]

    existing = _find_existing_metric(name)
    if existing:
        _METRICS_CACHE[name] = existing
        return existing

    try:
        metric = Counter(name, description, labelnames=labels)
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError:
        existing = _find_existing_metric(name)
        if existing:
            _METRICS_CACHE[name] = existing
            return existing
        raise


def _get_or_create_gauge(name: str, description: str, labels: list[str]) -> object:
    """Get existing or create new gauge metric."""
    if name in _METRICS_CACHE:
        return _METRICS_CACHE[name]

    existing = _find_existing_metric(name)
    if existing:
        _METRICS_CACHE[name] = existing
        return existing

    try:
        metric = Gauge(name, description, labelnames=labels)
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError:
        existing = _find_existing_metric(name)
        if existing:
            _METRICS_CACHE[name] = existing
            return existing
        raise


def _get_or_create_info(name: str, description: str) -> object:
    """Get existing or create new info metric."""
    if name in _METRICS_CACHE:
        return _METRICS_CACHE[name]

    existing = _find_existing_metric(name)
    if existing:
        _METRICS_CACHE[name] = existing
        return existing

    try:
        metric = Info(name, description)
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError:
        existing = _find_existing_metric(name)
        if existing:
            _METRICS_CACHE[name] = existing
            return existing
        raise


__all__ = [
    "_METRICS_CACHE",
    "_find_existing_metric",
    "_get_or_create_counter",
    "_get_or_create_gauge",
    "_get_or_create_histogram",
    "_get_or_create_info",
]
