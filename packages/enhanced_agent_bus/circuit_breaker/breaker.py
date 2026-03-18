"""
ACGS-2 Circuit Breaker Core Implementation

Constitutional Hash: cdd01ef066bc6cf2

This module implements the core ServiceCircuitBreaker class with state management,
metrics tracking, and fallback strategy support.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit tripped, requests use fallback strategy
- HALF_OPEN: Testing if service recovered

Transitions:
- CLOSED -> OPEN: When consecutive failures >= threshold
- OPEN -> HALF_OPEN: After timeout expires
- HALF_OPEN -> CLOSED: When half_open_requests succeed
- HALF_OPEN -> OPEN: On any failure during half-open
"""

import asyncio
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.circuit_breaker.models import CircuitBreakerMetrics, QueuedRequest
from enhanced_agent_bus.observability.structured_logging import get_logger

from .config import ServiceCircuitConfig
from .enums import CircuitState
from .metrics import (
    acgs_circuit_breaker_failures_total,
    acgs_circuit_breaker_queue_size,
    acgs_circuit_breaker_rejections_total,
    acgs_circuit_breaker_state,
    acgs_circuit_breaker_state_changes_total,
    acgs_circuit_breaker_successes_total,
)

logger = get_logger(__name__)
CIRCUIT_RETRY_HANDLER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class ServiceCircuitBreaker:
    """
    Service-specific circuit breaker with fallback strategies.

    Constitutional Hash: cdd01ef066bc6cf2

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit tripped, requests use fallback strategy
    - HALF_OPEN: Testing if service recovered

    Transitions:
    - CLOSED -> OPEN: When consecutive failures >= threshold
    - OPEN -> HALF_OPEN: After timeout expires
    - HALF_OPEN -> CLOSED: When half_open_requests succeed
    - HALF_OPEN -> OPEN: On any failure during half-open
    """

    def __init__(self, config: ServiceCircuitConfig):
        self.config = config
        self.constitutional_hash = CONSTITUTIONAL_HASH

        # State tracking
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float | None = None
        self._last_state_change: float = time.time()
        self._half_open_successes = 0

        # Metrics
        self.metrics = CircuitBreakerMetrics()

        # Fallback cache for CACHED_VALUE strategy
        self._fallback_cache: JSONDict = {}
        self._cache_timestamps: dict[str, float] = {}

        # Retry queue for QUEUE_FOR_RETRY strategy
        self._retry_queue: deque[QueuedRequest] = deque(maxlen=config.fallback_max_queue_size)
        self._retry_task: asyncio.Task | None = None

        # Async lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Created circuit breaker '{config.name}' "
            f"(threshold={config.failure_threshold}, timeout={config.timeout_seconds}s, "
            f"fallback={config.fallback_strategy.value}, severity={config.severity.value})"
        )

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with metrics and logging."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()
        self.metrics.state_changes += 1
        self.metrics.last_state_change_time = self._last_state_change

        # Reset half-open successes when entering half-open
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_successes = 0

        # Reset consecutive failures when closing
        if new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0

        # Update Prometheus metrics
        state_value = {"closed": 0, "half_open": 1, "open": 2}[new_state.value]
        acgs_circuit_breaker_state.labels(
            service=self.config.name,
            severity=self.config.severity.value,
        ).set(state_value)

        acgs_circuit_breaker_state_changes_total.labels(
            service=self.config.name,
            from_state=old_state.value,
            to_state=new_state.value,
        ).inc()

        logger.warning(
            f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' "
            f"state change: {old_state.value} -> {new_state.value} "
            f"(severity={self.config.severity.value})"
        )

    async def _check_timeout_expiry(self) -> bool:
        """Check if timeout has expired for open circuit."""
        if self._state != CircuitState.OPEN:
            return False
        elapsed = time.time() - self._last_state_change
        return elapsed >= self.config.timeout_seconds

    async def can_execute(self) -> bool:
        """Check if a request can be executed."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if await self._check_timeout_expiry():
                    await self._transition_to(CircuitState.HALF_OPEN)
                    return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                return self._half_open_successes < self.config.half_open_requests

            return False

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self.metrics.total_calls += 1
            self.metrics.successful_calls += 1
            self.metrics.last_success_time = time.time()

            acgs_circuit_breaker_successes_total.labels(service=self.config.name).inc()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.config.half_open_requests:
                    await self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    async def record_failure(
        self, error: Exception | None = None, error_type: str = "unknown"
    ) -> None:
        """Record a failed call."""
        async with self._lock:
            self.metrics.total_calls += 1
            self.metrics.failed_calls += 1
            self._consecutive_failures += 1
            self._last_failure_time = time.time()
            self.metrics.last_failure_time = self._last_failure_time

            acgs_circuit_breaker_failures_total.labels(
                service=self.config.name,
                error_type=error_type,
            ).inc()

            if self._state == CircuitState.HALF_OPEN:
                await self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:  # noqa: SIM102
                if self._consecutive_failures >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)

    async def record_rejection(self) -> None:
        """Record a rejected call (when circuit is open)."""
        async with self._lock:
            self.metrics.total_calls += 1
            self.metrics.rejected_calls += 1

            acgs_circuit_breaker_rejections_total.labels(
                service=self.config.name,
                fallback_strategy=self.config.fallback_strategy.value,
            ).inc()

    # =========================================================================
    # Fallback Strategies
    # =========================================================================

    def set_cached_fallback(self, key: str, value: object) -> None:
        """Set a cached fallback value for CACHED_VALUE strategy."""
        self._fallback_cache[key] = value
        self._cache_timestamps[key] = time.time()

    def get_cached_fallback(self, key: str) -> object | None:
        """Get a cached fallback value if still valid."""
        if key not in self._fallback_cache:
            return None

        timestamp = self._cache_timestamps.get(key, 0)
        if time.time() - timestamp > self.config.fallback_ttl_seconds:
            # Cache expired
            del self._fallback_cache[key]
            del self._cache_timestamps[key]
            return None

        self.metrics.fallback_used_count += 1
        return self._fallback_cache[key]  # type: ignore[no-any-return]

    async def queue_for_retry(self, request_id: str, args: tuple, kwargs: dict) -> bool:
        """Queue a request for retry (QUEUE_FOR_RETRY strategy)."""
        if len(self._retry_queue) >= self.config.fallback_max_queue_size:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' "
                f"retry queue full ({self.config.fallback_max_queue_size})"
            )
            return False

        queued_request = QueuedRequest(
            id=request_id,
            args=args,
            kwargs=kwargs,
            queued_at=time.time(),
        )
        self._retry_queue.append(queued_request)
        self.metrics.queue_size = len(self._retry_queue)

        acgs_circuit_breaker_queue_size.labels(service=self.config.name).set(
            self.metrics.queue_size
        )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' "
            f"queued request {request_id} for retry (queue_size={self.metrics.queue_size})"
        )
        return True

    def get_queue_size(self) -> int:
        """Get current retry queue size."""
        return len(self._retry_queue)

    async def process_retry_queue(self, handler: Callable[..., object]) -> dict[str, bool]:
        """Process queued requests (call when circuit closes)."""
        results: dict[str, bool] = {}
        processed = []

        while self._retry_queue:
            request = self._retry_queue.popleft()

            if request.retry_count >= request.max_retries:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' "
                    f"request {request.id} exceeded max retries"
                )
                results[request.id] = False
                continue

            try:
                await handler(*request.args, **request.kwargs)
                results[request.id] = True
                processed.append(request.id)
            except Exception as e:
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' "
                    f"retry failed for {request.id}: {e}"
                )
                request.retry_count += 1
                # Re-queue only if there is room — do NOT rely on deque(maxlen)
                # silently evicting the oldest item, which would lose a queued
                # request that hasn't been attempted yet.
                if request.retry_count < request.max_retries:
                    if len(self._retry_queue) < self.config.fallback_max_queue_size:
                        self._retry_queue.append(request)
                    else:
                        logger.warning(
                            f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' "
                            f"dropped retry for {request.id}: queue full"
                        )
                results[request.id] = False

        self.metrics.queue_size = len(self._retry_queue)
        acgs_circuit_breaker_queue_size.labels(service=self.config.name).set(
            self.metrics.queue_size
        )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' "
            f"processed {len(processed)} queued requests"
        )
        return results

    # =========================================================================
    # Status and Metrics
    # =========================================================================

    def get_status(self) -> JSONDict:
        """Get circuit breaker status."""
        return {
            "name": self.config.name,
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.config.failure_threshold,
            "timeout_seconds": self.config.timeout_seconds,
            "half_open_requests": self.config.half_open_requests,
            "half_open_successes": self._half_open_successes,
            "fallback_strategy": self.config.fallback_strategy.value,
            "severity": self.config.severity.value,
            "metrics": {
                "total_calls": self.metrics.total_calls,
                "successful_calls": self.metrics.successful_calls,
                "failed_calls": self.metrics.failed_calls,
                "rejected_calls": self.metrics.rejected_calls,
                "state_changes": self.metrics.state_changes,
                "fallback_used_count": self.metrics.fallback_used_count,
                "queue_size": self.metrics.queue_size,
            },
            "last_failure_time": (
                datetime.fromtimestamp(self.metrics.last_failure_time, tz=UTC).isoformat()
                if self.metrics.last_failure_time
                else None
            ),
            "last_state_change_time": (
                datetime.fromtimestamp(self._last_state_change, tz=UTC).isoformat()
            ),
            "description": self.config.description,
            "constitutional_hash": self.constitutional_hash,
        }

    async def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._last_failure_time = None
            self._last_state_change = time.time()
            self._half_open_successes = 0
            self.metrics = CircuitBreakerMetrics()

            # Update Prometheus metrics
            acgs_circuit_breaker_state.labels(
                service=self.config.name,
                severity=self.config.severity.value,
            ).set(0)  # closed

            logger.info(f"[{CONSTITUTIONAL_HASH}] Circuit '{self.config.name}' reset to CLOSED")


__all__ = [
    "ServiceCircuitBreaker",
]
