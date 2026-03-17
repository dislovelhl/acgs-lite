"""
ACGS-2 API Gateway Prometheus Metrics Module
Constitutional Hash: cdd01ef066bc6cf2

Provides Prometheus metrics instrumentation for the API Gateway service,
including automatic HTTP request tracking middleware and cache metrics.
"""

import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Constitutional Hash for governance validation
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)

# Check prometheus_client availability with graceful fallback
PROMETHEUS_AVAILABLE = False

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
    logger.info(f"[{CONSTITUTIONAL_HASH}] Prometheus client available")
except ImportError:
    logger.warning(
        f"[{CONSTITUTIONAL_HASH}] prometheus_client not available, using no-op implementations"
    )

# ============================================================================
# No-Op Implementations for Graceful Degradation
# ============================================================================


class NoOpMetric:
    """No-op metric for when Prometheus is not available."""

    def labels(self, **kwargs) -> "NoOpMetric":
        return self

    def inc(self, amount: float = 1) -> None:
        pass

    def dec(self, amount: float = 1) -> None:
        pass

    def observe(self, value: float) -> None:
        pass

    def set(self, value: float) -> None:
        pass


# ============================================================================
# Metric Registration Helpers (handle duplicate registration gracefully)
# ============================================================================

_METRICS_CACHE: JSONDict = {}


def _find_existing_metric(name: str):
    """Find an existing metric by name in the registry."""
    if not PROMETHEUS_AVAILABLE:
        return None
    try:
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]
        for collector in REGISTRY._names_to_collectors.values():
            if hasattr(collector, "_name") and collector._name == name:
                return collector
    except (RuntimeError, ValueError, TypeError):
        pass
    return None


def _get_or_create_histogram(
    name: str, description: str, labels: list, buckets: list | None = None
):
    """Get existing or create new histogram metric."""
    if not PROMETHEUS_AVAILABLE:
        return NoOpMetric()

    global _METRICS_CACHE
    if name in _METRICS_CACHE:
        return _METRICS_CACHE[name]

    existing = _find_existing_metric(name)
    if existing:
        _METRICS_CACHE[name] = existing
        return existing

    kwargs = {"labelnames": labels}
    if buckets:
        kwargs["buckets"] = buckets

    try:
        metric = Histogram(name, description, **kwargs)
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError:
        existing = _find_existing_metric(name)
        if existing:
            _METRICS_CACHE[name] = existing
            return existing
        return NoOpMetric()


def _get_or_create_counter(name: str, description: str, labels: list):
    """Get existing or create new counter metric."""
    if not PROMETHEUS_AVAILABLE:
        return NoOpMetric()

    global _METRICS_CACHE
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
        return NoOpMetric()


def _get_or_create_gauge(name: str, description: str, labels: list):
    """Get existing or create new gauge metric."""
    if not PROMETHEUS_AVAILABLE:
        return NoOpMetric()

    global _METRICS_CACHE
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
        return NoOpMetric()


# ============================================================================
# API Gateway Specific Metrics
# ============================================================================

# HTTP request metrics with sub-millisecond precision buckets for P99 tracking
HTTP_REQUEST_DURATION = _get_or_create_histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "service", "status_code"],
    # Buckets optimized for P99 < 1ms target
    buckets=[
        0.0001,  # 0.1ms
        0.00025,  # 0.25ms
        0.0005,  # 0.5ms
        0.00075,  # 0.75ms
        0.001,  # 1ms (target P99)
        0.0025,  # 2.5ms
        0.005,  # 5ms
        0.01,  # 10ms
        0.025,  # 25ms
        0.05,  # 50ms
        0.1,  # 100ms
        0.25,  # 250ms
        0.5,  # 500ms
        1.0,  # 1s
    ],
)

HTTP_REQUESTS_TOTAL = _get_or_create_counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "service", "status_code"],
)

HTTP_REQUESTS_IN_PROGRESS = _get_or_create_gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method", "service"],
)

# Cache metrics for >98% hit rate tracking
CACHE_HITS_TOTAL = _get_or_create_counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type", "service"],
)

CACHE_MISSES_TOTAL = _get_or_create_counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type", "service"],
)

CACHE_OPERATION_DURATION = _get_or_create_histogram(
    "cache_operation_duration_seconds",
    "Cache operation latency in seconds",
    ["operation", "cache_type", "service"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
)

# Connection pool metrics
CONNECTION_POOL_SIZE = _get_or_create_gauge(
    "connection_pool_size",
    "Current connection pool size",
    ["pool_type", "service"],
)

CONNECTION_POOL_AVAILABLE = _get_or_create_gauge(
    "connection_pool_available",
    "Available connections in pool",
    ["pool_type", "service"],
)

# Proxy metrics for API Gateway
PROXY_REQUESTS_TOTAL = _get_or_create_counter(
    "proxy_requests_total",
    "Total requests proxied to backend services",
    ["target_service", "status_code"],
)

PROXY_DURATION = _get_or_create_histogram(
    "proxy_duration_seconds",
    "Time spent proxying requests to backend services",
    ["target_service"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

FEEDBACK_SUBMISSIONS_TOTAL = _get_or_create_counter(
    "feedback_submissions_total",
    "Total feedback submissions accepted by the API gateway",
    ["auth_mode", "category", "user_id_verified"],
)

FEEDBACK_REJECTIONS_TOTAL = _get_or_create_counter(
    "feedback_rejections_total",
    "Total feedback submissions rejected by the API gateway",
    ["reason", "auth_mode"],
)

# ============================================================================
# Metrics Middleware for Automatic HTTP Request Tracking
# ============================================================================


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware for automatic HTTP request metrics collection.

    Tracks request duration, total requests, and in-progress requests with
    labels for method, endpoint, and status code.
    """

    def __init__(self, app, service_name: str = "api_gateway"):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        # Normalize endpoint path to avoid high cardinality
        endpoint = self._normalize_endpoint(request.url.path)

        # Track in-progress requests
        HTTP_REQUESTS_IN_PROGRESS.labels(
            method=method,
            service=self.service_name,
        ).inc()

        start_time = time.perf_counter()
        status_code = "500"  # Default to error

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except (RuntimeError, ValueError, TypeError):
            status_code = "500"
            raise
        finally:
            duration = time.perf_counter() - start_time

            # Record request duration
            HTTP_REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint,
                service=self.service_name,
                status_code=status_code,
            ).observe(duration)

            # Increment total requests counter
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                service=self.service_name,
                status_code=status_code,
            ).inc()

            # Decrement in-progress counter
            HTTP_REQUESTS_IN_PROGRESS.labels(
                method=method,
                service=self.service_name,
            ).dec()

    def _normalize_endpoint(self, path: str) -> str:
        """
        Normalize endpoint path to reduce cardinality.

        Replaces dynamic path segments (UUIDs, IDs) with placeholders.
        """
        import re

        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{uuid}",
            path,
            flags=re.IGNORECASE,
        )
        # Replace numeric IDs
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
        return path


# ============================================================================
# Cache Metrics Helper Functions
# ============================================================================


def record_cache_hit(cache_type: str = "redis", service: str = "api_gateway") -> None:
    """Record a cache hit."""
    CACHE_HITS_TOTAL.labels(cache_type=cache_type, service=service).inc()


def record_cache_miss(cache_type: str = "redis", service: str = "api_gateway") -> None:
    """Record a cache miss."""
    CACHE_MISSES_TOTAL.labels(cache_type=cache_type, service=service).inc()


def record_cache_operation(
    operation: str,
    duration: float,
    cache_type: str = "redis",
    service: str = "api_gateway",
) -> None:
    """Record cache operation duration."""
    CACHE_OPERATION_DURATION.labels(
        operation=operation,
        cache_type=cache_type,
        service=service,
    ).observe(duration)


def record_proxy_request(
    target_service: str,
    status_code: int,
    duration: float,
) -> None:
    """Record a proxy request to a backend service."""
    PROXY_REQUESTS_TOTAL.labels(
        target_service=target_service,
        status_code=str(status_code),
    ).inc()
    PROXY_DURATION.labels(target_service=target_service).observe(duration)


def record_feedback_submission(
    auth_mode: str,
    category: str,
    user_id_verified: bool,
) -> None:
    """Record an accepted gateway feedback submission."""
    FEEDBACK_SUBMISSIONS_TOTAL.labels(
        auth_mode=auth_mode,
        category=category,
        user_id_verified=str(user_id_verified).lower(),
    ).inc()


def record_feedback_rejection(reason: str, auth_mode: str) -> None:
    """Record a rejected gateway feedback submission."""
    FEEDBACK_REJECTIONS_TOTAL.labels(reason=reason, auth_mode=auth_mode).inc()


def update_connection_pool_metrics(
    pool_type: str,
    size: int,
    available: int,
    service: str = "api_gateway",
) -> None:
    """Update connection pool metrics."""
    CONNECTION_POOL_SIZE.labels(pool_type=pool_type, service=service).set(size)
    CONNECTION_POOL_AVAILABLE.labels(pool_type=pool_type, service=service).set(available)


# ============================================================================
# Metrics Endpoint
# ============================================================================


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not available\n"
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics."""
    if not PROMETHEUS_AVAILABLE:
        return "text/plain; charset=utf-8"
    return CONTENT_TYPE_LATEST


def create_metrics_endpoint():
    """
    Create a FastAPI metrics endpoint.

    Usage:
        from metrics import create_metrics_endpoint
        app.add_api_route('/metrics', create_metrics_endpoint())
    """
    from fastapi import Response

    async def metrics_endpoint():
        return Response(
            content=get_metrics(),
            media_type=get_metrics_content_type(),
        )

    return metrics_endpoint


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    "CACHE_HITS_TOTAL",
    "CACHE_MISSES_TOTAL",
    "CACHE_OPERATION_DURATION",
    "CONNECTION_POOL_AVAILABLE",
    "CONNECTION_POOL_SIZE",
    # Constants
    "CONSTITUTIONAL_HASH",
    "FEEDBACK_REJECTIONS_TOTAL",
    "FEEDBACK_SUBMISSIONS_TOTAL",
    "HTTP_REQUESTS_IN_PROGRESS",
    "HTTP_REQUESTS_TOTAL",
    # Metrics
    "HTTP_REQUEST_DURATION",
    "PROMETHEUS_AVAILABLE",
    "PROXY_DURATION",
    "PROXY_REQUESTS_TOTAL",
    # Middleware
    "MetricsMiddleware",
    "create_metrics_endpoint",
    # Endpoint
    "get_metrics",
    "get_metrics_content_type",
    # Helper Functions
    "record_cache_hit",
    "record_cache_miss",
    "record_cache_operation",
    "record_feedback_rejection",
    "record_feedback_submission",
    "record_proxy_request",
    "update_connection_pool_metrics",
]
