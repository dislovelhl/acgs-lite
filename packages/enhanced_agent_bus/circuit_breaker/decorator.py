"""
ACGS-2 Circuit Breaker Decorator

Constitutional Hash: 608508a9bd224290

This module provides the with_service_circuit_breaker decorator for wrapping
async functions with circuit breaker protection.
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

from .config import ServiceCircuitConfig
from .enums import FallbackStrategy, ServiceSeverity
from .exceptions import CircuitBreakerOpen
from .registry import get_service_circuit_breaker

logger = get_logger(__name__)
SERVICE_CIRCUIT_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

T = TypeVar("T")


def _fallback_cache_key(cache_key: str | None, service_name: str) -> str:
    """Resolve fallback cache key with service-level default."""
    return cache_key or service_name


def _raise_circuit_open(service_name: str, message: str, strategy: FallbackStrategy) -> None:
    """Raise canonical circuit-open exception."""
    raise CircuitBreakerOpen(service_name, message, strategy.value)


def _handle_cached_value_strategy(
    cb: object,
    service_name: str,
    cache_key: str | None,
) -> object:
    """Handle CACHED_VALUE fallback behavior."""
    cached = cb.get_cached_fallback(_fallback_cache_key(cache_key, service_name))
    if cached is not None:
        logger.info(f"[{CONSTITUTIONAL_HASH}] Using cached fallback for {service_name}")
        return cached
    _raise_circuit_open(service_name, "No cached fallback available", cb.config.fallback_strategy)


async def _handle_queue_for_retry_strategy(
    cb: object,
    service_name: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object | None:
    """Handle QUEUE_FOR_RETRY fallback behavior."""
    import uuid

    request_id = str(uuid.uuid4())
    queued = await cb.queue_for_retry(request_id, args, kwargs)
    if queued:
        logger.info(f"[{CONSTITUTIONAL_HASH}] Request queued for retry ({service_name})")

    if cb.config.severity == ServiceSeverity.CRITICAL:
        _raise_circuit_open(
            service_name,
            "Request queued but critical service unavailable",
            cb.config.fallback_strategy,
        )
    return None


async def _handle_open_circuit(
    cb: object,
    service_name: str,
    fallback_value: object | None,
    cache_key: str | None,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    """Apply configured fallback strategy when circuit is open."""
    strategy = cb.config.fallback_strategy

    if strategy == FallbackStrategy.FAIL_CLOSED:
        _raise_circuit_open(
            service_name, f"Service unavailable, circuit is {cb.state.value}", strategy
        )

    if strategy == FallbackStrategy.CACHED_VALUE:
        return _handle_cached_value_strategy(cb, service_name, cache_key)

    if strategy == FallbackStrategy.QUEUE_FOR_RETRY:
        return await _handle_queue_for_retry_strategy(cb, service_name, args, kwargs)

    if strategy == FallbackStrategy.BYPASS:
        logger.info(f"[{CONSTITUTIONAL_HASH}] Bypassing {service_name} (circuit open)")
        return fallback_value

    if strategy == FallbackStrategy.DEFAULT_VALUE:
        return fallback_value

    _raise_circuit_open(service_name, "Unsupported fallback strategy", strategy)


def _cache_successful_result(
    cb: object, cache_key: str | None, service_name: str, result: object
) -> None:
    """Cache successful result when CACHED_VALUE strategy is enabled."""
    if cb.config.fallback_strategy != FallbackStrategy.CACHED_VALUE or result is None:
        return
    cb.set_cached_fallback(_fallback_cache_key(cache_key, service_name), result)


def with_service_circuit_breaker(
    service_name: str,
    fallback_value: object | None = None,
    cache_key: str | None = None,
    config: ServiceCircuitConfig | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to wrap a function with service-specific circuit breaker.

    Args:
        service_name: Name of the service for the circuit breaker
        fallback_value: Value to return when using DEFAULT_VALUE strategy
        cache_key: Key for cached fallback (CACHED_VALUE strategy)
        config: Optional custom circuit breaker configuration

    Usage:
        @with_service_circuit_breaker('policy_registry', cache_key='policies')
        async def get_policies():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            cb = await get_service_circuit_breaker(service_name, config)

            if not await cb.can_execute():
                await cb.record_rejection()
                fallback_result = await _handle_open_circuit(
                    cb=cb,
                    service_name=service_name,
                    fallback_value=fallback_value,
                    cache_key=cache_key,
                    args=args,
                    kwargs=kwargs,
                )
                return fallback_result  # type: ignore[return-value]

            try:
                result = await func(*args, **kwargs)  # type: ignore[misc]
                await cb.record_success()
                _cache_successful_result(cb, cache_key, service_name, result)
                return result  # type: ignore[no-any-return]

            except Exception as e:
                # Circuit breaker MUST catch all exceptions from the wrapped
                # service — including domain-specific errors not in the named
                # tuple (e.g. OPAFailureError, KafkaProducerError). Narrowing
                # this catch causes those errors to bypass failure recording
                # so the circuit never opens for them.
                await cb.record_failure(e, type(e).__name__)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = [
    "with_service_circuit_breaker",
]
