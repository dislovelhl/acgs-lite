"""
ACGS-2 Circuit Breaker Wrapper — [CANONICAL]
Constitutional Hash: 608508a9bd224290

This is the **canonical** circuit breaker module for ACGS-2.
New code should import from here (``src.core.shared.errors.circuit_breaker``).

Landscape — other implementations that exist for historical/local reasons
(all are deprecated in favour of this module):

- ``src.core.services.api_gateway.circuit_breaker.CircuitBreaker``
- ``packages.enhanced_agent_bus.batch_circuit_breaker.CircuitBreaker``
- ``packages.enhanced_agent_bus.llm_adapters.registry.CircuitBreaker``
- ``src.core.cognitive.actors.circuit_breaker.CircuitBreaker``
- ``src.core.shared.http_client.CircuitBreaker``
- ``src.core.services.integration.search_platform.client.CircuitBreaker``
- ``src.governance_adapter.utils.CircuitBreaker``

Provides a unified circuit breaker interface that wraps existing implementations
from src.core.shared.circuit_breaker and packages.enhanced_agent_bus.circuit_breaker.

This module offers:
- Simple decorator for wrapping functions with circuit breaker protection
- Integration with existing ACGS-2 circuit breaker infrastructure
- Fallback strategies for graceful degradation
- Prometheus metrics integration
- Structured logging with constitutional hash context

Usage:
    from src.core.shared.errors.circuit_breaker import circuit_breaker

    @circuit_breaker("policy_registry")
    async def fetch_policies() -> list[dict]:
        return await policy_client.list()

    # With custom configuration
    from src.core.shared.errors import CircuitBreakerConfig

    @circuit_breaker("opa_evaluator", config=CircuitBreakerConfig(
        failure_threshold=5,
        reset_timeout=30,
    ))
    async def evaluate_policy(input_data: dict) -> dict:
        return await opa_client.evaluate(input_data)
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeVar, cast

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)
T = TypeVar("T")


class CircuitBreakerState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit tripped, requests are rejected/use fallback
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerOpenError(ACGSBaseError):
    """
    Raised when circuit breaker is open and fallback not available (Q-H4 migration).

    Attributes:
        service_name: Name of the service with open circuit.
        state: Current circuit breaker state.
        retry_after: Suggested retry delay in seconds.
        constitutional_hash: Constitutional hash for governance tracking.
    """

    http_status_code = 503
    error_code = "CIRCUIT_BREAKER_OPEN"

    def __init__(
        self,
        message: str,
        *,
        service_name: str,
        state: CircuitBreakerState = CircuitBreakerState.OPEN,
        retry_after: float | None = None,
        **kwargs: object,
    ) -> None:
        # Preserve backward-compatible attributes
        self.service_name = service_name
        self.state = state
        self.retry_after = retry_after

        # Build details dict for ACGSBaseError
        details = kwargs.pop("details", {}) or {}
        details.update(
            {
                "service_name": service_name,
                "state": state.value,
                "retry_after": retry_after,
            }
        )

        super().__init__(message, details=details, **kwargs)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for API responses."""
        return {
            "error": "CIRCUIT_BREAKER_OPEN",
            "message": str(self),
            "service_name": self.service_name,
            "state": self.state.value,
            "retry_after": self.retry_after,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for circuit breaker behavior.

    Constitutional Hash: 608508a9bd224290

    Attributes:
        failure_threshold: Number of failures before opening circuit.
        reset_timeout: Seconds before attempting to close circuit.
        half_open_max_calls: Maximum calls allowed in half-open state.
        success_threshold: Successes required in half-open to close.
        fallback: Optional fallback function when circuit is open.
        exclude_exceptions: Exception types that don't count as failures.
    """

    failure_threshold: int = 5
    reset_timeout: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2
    fallback: Callable[..., object] | None = None
    exclude_exceptions: tuple[type[BaseException], ...] = field(default_factory=tuple)

    def to_dict(self) -> JSONDict:
        """Convert configuration to dictionary."""
        return {
            "failure_threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
            "half_open_max_calls": self.half_open_max_calls,
            "success_threshold": self.success_threshold,
            "has_fallback": self.fallback is not None,
            "exclude_exceptions": [e.__name__ for e in self.exclude_exceptions],
        }


class SimpleCircuitBreaker:
    """
    Simple circuit breaker implementation for standalone usage.

    This is used when the more complex circuit breaker infrastructure
    is not available or not needed.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, service_name: str, config: CircuitBreakerConfig) -> None:
        self.service_name = service_name
        self.config = config
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit state, potentially transitioning from OPEN to HALF_OPEN."""
        if self._state == CircuitBreakerState.OPEN and self._should_attempt_reset():
            self._transition_to(CircuitBreakerState.HALF_OPEN)
        return self._state

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.config.reset_timeout

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state with logging."""
        old_state = self._state
        self._state = new_state

        if new_state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0

        if new_state == CircuitBreakerState.CLOSED:
            self._failure_count = 0
            self._success_count = 0

        logger.warning(
            f"[{CONSTITUTIONAL_HASH}] Circuit breaker '{self.service_name}' "
            f"state change: {old_state.value} -> {new_state.value}"
        )

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        state = self.state  # This may trigger OPEN -> HALF_OPEN

        if state == CircuitBreakerState.CLOSED:
            return True

        if state == CircuitBreakerState.OPEN:
            return False

        if state == CircuitBreakerState.HALF_OPEN:
            return self._half_open_calls < self.config.half_open_max_calls

        return False

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._transition_to(CircuitBreakerState.CLOSED)
        elif self._state == CircuitBreakerState.CLOSED:
            # Reset failure count on success in closed state
            self._failure_count = 0

    def record_failure(self, exception: BaseException) -> None:
        """Record a failed call."""
        # Check if exception should be excluded
        if isinstance(exception, self.config.exclude_exceptions):
            return

        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitBreakerState.HALF_OPEN:
            # object failure in half-open immediately opens circuit
            self._transition_to(CircuitBreakerState.OPEN)
        elif self._state == CircuitBreakerState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitBreakerState.OPEN)

    def before_call(self) -> None:
        """Called before executing a call."""
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls += 1

    def get_status(self) -> JSONDict:
        """Get circuit breaker status."""
        return {
            "service_name": self.service_name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "config": self.config.to_dict(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._transition_to(CircuitBreakerState.CLOSED)
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0
        logger.info(f"[{CONSTITUTIONAL_HASH}] Circuit breaker '{self.service_name}' reset")


# Global registry of circuit breakers
_circuit_breakers: dict[str, SimpleCircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(
    service_name: str,
    config: CircuitBreakerConfig | None = None,
) -> SimpleCircuitBreaker:
    """
    Get or create a circuit breaker for a service.

    Constitutional Hash: 608508a9bd224290

    Args:
        service_name: Name of the service.
        config: Optional configuration (uses defaults if not provided).

    Returns:
        Circuit breaker instance for the service.
    """
    with _registry_lock:
        if service_name not in _circuit_breakers:
            config = config or CircuitBreakerConfig()
            _circuit_breakers[service_name] = SimpleCircuitBreaker(service_name, config)
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Created circuit breaker for '{service_name}' "
                f"(threshold={config.failure_threshold}, timeout={config.reset_timeout}s)"
            )

    return _circuit_breakers[service_name]


def circuit_breaker(
    service_name: str,
    *,
    fallback: Callable[..., object] | None = None,
    config: CircuitBreakerConfig | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to wrap a function with circuit breaker protection.

    Constitutional Hash: 608508a9bd224290

    Args:
        service_name: Name of the service for the circuit breaker.
        fallback: Optional fallback function when circuit is open.
        config: Optional circuit breaker configuration.

    Returns:
        Decorated function with circuit breaker protection.

    Usage:
        @circuit_breaker("policy_registry")
        async def get_policies():
            return await policy_client.list()

        @circuit_breaker("audit_service", fallback=lambda: {"status": "unavailable"})
        async def log_audit_event(event: dict):
            return await audit_client.log(event)
    """
    if config is None:
        config = CircuitBreakerConfig(fallback=fallback)
    elif fallback is not None:
        # Create new config with fallback
        config = CircuitBreakerConfig(
            failure_threshold=config.failure_threshold,
            reset_timeout=config.reset_timeout,
            half_open_max_calls=config.half_open_max_calls,
            success_threshold=config.success_threshold,
            fallback=fallback,
            exclude_exceptions=config.exclude_exceptions,
        )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            return cast(Callable[..., T], _create_async_cb_wrapper(func, service_name, config))
        else:
            return cast(Callable[..., T], _create_sync_cb_wrapper(func, service_name, config))

    return decorator


def _create_async_cb_wrapper(
    func: Callable[..., T],
    service_name: str,
    config: CircuitBreakerConfig,
) -> Callable[..., T]:
    """Create async wrapper with circuit breaker logic."""

    @functools.wraps(func)
    async def wrapper(*args: object, **kwargs: object) -> T:
        cb = get_circuit_breaker(service_name, config)

        if not cb.can_execute():
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Circuit breaker '{service_name}' is "
                f"{cb.state.value}, rejecting call to {func.__name__}"
            )

            # Use fallback if available
            if config.fallback is not None:
                result = config.fallback(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result

            raise CircuitBreakerOpenError(
                f"Circuit breaker open for service '{service_name}'",
                service_name=service_name,
                state=cb.state,
                retry_after=config.reset_timeout,
            )

        cb.before_call()

        try:
            result = await func(*args, **kwargs)  # type: ignore[misc]
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure(e)
            raise

    return cast(Callable[..., T], wrapper)


def _create_sync_cb_wrapper(
    func: Callable[..., T],
    service_name: str,
    config: CircuitBreakerConfig,
) -> Callable[..., T]:
    """Create sync wrapper with circuit breaker logic."""

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> T:
        cb = get_circuit_breaker(service_name, config)

        if not cb.can_execute():
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Circuit breaker '{service_name}' is "
                f"{cb.state.value}, rejecting call to {func.__name__}"
            )

            if config.fallback is not None:
                return config.fallback(*args, **kwargs)

            raise CircuitBreakerOpenError(
                f"Circuit breaker open for service '{service_name}'",
                service_name=service_name,
                state=cb.state,
                retry_after=config.reset_timeout,
            )

        cb.before_call()

        try:
            result = func(*args, **kwargs)
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure(e)
            raise

    return cast(Callable[..., T], wrapper)


def reset_circuit_breaker(service_name: str) -> bool:
    """
    Reset a specific circuit breaker to closed state.

    Args:
        service_name: Name of the service.

    Returns:
        True if circuit breaker was reset, False if not found.
    """
    if service_name in _circuit_breakers:
        _circuit_breakers[service_name].reset()
        return True
    return False


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state."""
    for cb in _circuit_breakers.values():
        cb.reset()


def get_all_circuit_breaker_states() -> dict[str, JSONDict]:
    """Get status of all circuit breakers."""
    return {name: cb.get_status() for name, cb in _circuit_breakers.items()}


__all__ = [
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "SimpleCircuitBreaker",
    "circuit_breaker",
    "get_all_circuit_breaker_states",
    "get_circuit_breaker",
    "reset_all_circuit_breakers",
    "reset_circuit_breaker",
]
