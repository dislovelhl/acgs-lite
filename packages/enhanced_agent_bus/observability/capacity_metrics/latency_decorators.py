"""
ACGS-2 Capacity Metrics Latency Decorators
Constitutional Hash: 608508a9bd224290

Decorators for tracking request latency in the Enhanced Agent Bus.
These decorators automatically record request latency to the capacity metrics
collector for both synchronous and asynchronous functions.

Note: This module is named latency_decorators.py to avoid conflict with
the existing observability/decorators.py module which contains OpenTelemetry
tracing decorators.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


def track_request_latency(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to track request latency for synchronous functions.

    Records the execution time of the decorated function to the capacity
    metrics collector, along with success/failure status.

    Args:
        func: The synchronous function to wrap

    Returns:
        Wrapped function that records latency metrics

    Example:
        @track_request_latency
        def process_request(data: dict) -> Response:
            # ... processing logic
            return response
    """
    # Import here to avoid circular imports
    from .collector import get_capacity_metrics

    def wrapper(*args: object, **kwargs: object) -> T:
        metrics = get_capacity_metrics()
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            metrics.record_request(latency_ms, success=True)
            return result
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            # Record failed request metrics before re-raising
            latency_ms = (time.perf_counter() - start) * 1000
            metrics.record_request(latency_ms, success=False)
            raise e

    return wrapper


def track_async_request_latency(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """
    Decorator to track request latency for asynchronous functions.

    Records the execution time of the decorated async function to the capacity
    metrics collector, along with success/failure status.

    Args:
        func: The asynchronous function to wrap

    Returns:
        Wrapped async function that records latency metrics

    Example:
        @track_async_request_latency
        async def process_request(data: dict) -> Response:
            # ... async processing logic
            return response
    """
    # Import here to avoid circular imports
    from .collector import get_capacity_metrics

    async def wrapper(*args: object, **kwargs: object) -> T:
        metrics = get_capacity_metrics()
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            latency_ms = (time.perf_counter() - start) * 1000
            metrics.record_request(latency_ms, success=True)
            return result
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            # Record failed request metrics before re-raising
            latency_ms = (time.perf_counter() - start) * 1000
            metrics.record_request(latency_ms, success=False)
            raise e

    return wrapper


__all__ = [
    "track_async_request_latency",
    "track_request_latency",
]
