"""
ACGS-2 Enhanced Agent Bus - Batch Circuit Breaker
Constitutional Hash: cdd01ef066bc6cf2

Implements rate-based circuit breaker pattern for batch processing resilience.
Relocated from ``batch_circuit_breaker.py`` to ``circuit_breaker/batch.py``.
"""

import asyncio
import time

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import CircuitState

logger = get_logger(__name__)


class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    def __init__(
        self,
        failure_threshold: float = 0.5,
        minimum_requests: int = 10,
        cooldown_period: float = 30.0,
        success_threshold: float = 0.5,
    ):
        """
        Initialize circuit breaker configuration.

        Args:
            failure_threshold: Failure rate threshold (0.0 to 1.0)
            minimum_requests: Minimum requests before evaluating circuit state
            cooldown_period: Cooldown period in seconds when circuit is open
            success_threshold: Success threshold for half-open state
        """
        self.failure_threshold = failure_threshold
        self.minimum_requests = minimum_requests
        self.cooldown_period = cooldown_period
        self.success_threshold = success_threshold


class CircuitBreaker:
    """
    Circuit breaker implementation for batch processing.

    .. deprecated::
        Use ``src.core.shared.errors.circuit_breaker.SimpleCircuitBreaker`` (or the
        ``@circuit_breaker`` decorator) instead.
        This local implementation in the batch processing layer exists for
        historical reasons and is not maintained as the canonical version.

    Prevents cascading failures by blocking requests when failure rate exceeds threshold.
    """

    def __init__(self, config: CircuitBreakerConfig):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.total_requests = 0
        self.last_failure_time: float | None = None
        self.half_open_success_count = 0
        self._lock = asyncio.Lock()

    async def allow_request(self) -> bool:
        """
        Check if a request should be allowed through the circuit breaker.

        Returns:
            True if request should be allowed, False otherwise
        """
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            elif self.state == CircuitState.OPEN:
                # Check if cooldown period has passed
                if (
                    self.last_failure_time
                    and (time.time() - self.last_failure_time) >= self.config.cooldown_period
                ):
                    # Move to half-open state
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_success_count = 0
                    logger.info("Circuit breaker moving to HALF-OPEN state")
                    return True
                return False

            elif self.state == CircuitState.HALF_OPEN:
                # Allow requests to test if system has recovered
                return True

            return False

    async def record_success(self) -> None:
        """
        Record a successful operation.

        Updates circuit breaker state based on success rate.
        """
        async with self._lock:
            self.total_requests += 1
            self.success_count += 1

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_success_count += 1

                # Check if we have enough samples to determine recovery
                total_half_open_requests = self.half_open_success_count
                success_rate = (
                    self.half_open_success_count / total_half_open_requests
                    if total_half_open_requests > 0
                    else 0.0
                )

                if success_rate >= self.config.success_threshold:
                    # System has recovered, close the circuit
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.total_requests = 0
                    logger.info("Circuit breaker moving to CLOSED state")

    async def record_failure(self) -> None:
        """
        Record a failed operation.

        Updates circuit breaker state based on failure rate.
        """
        async with self._lock:
            self.total_requests += 1
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # System still failing, open the circuit
                self.state = CircuitState.OPEN
                logger.warning("Circuit breaker moving to OPEN state (half-open test failed)")

            elif self.state == CircuitState.CLOSED:
                # Check if we should open the circuit
                if self.total_requests >= self.config.minimum_requests:
                    failure_rate = self.failure_count / self.total_requests
                    if failure_rate >= self.config.failure_threshold:
                        self.state = CircuitState.OPEN
                        logger.warning(
                            f"Circuit breaker moving to OPEN state "
                            f"(failure rate: {failure_rate:.2%})"
                        )

    def get_state(self) -> CircuitState:
        """
        Get current circuit breaker state.

        Returns:
            Current circuit state
        """
        return self.state

    def get_statistics(self) -> JSONDict:
        """
        Get circuit breaker statistics.

        Returns:
            Dictionary with circuit breaker statistics
        """
        failure_rate = self.failure_count / self.total_requests if self.total_requests > 0 else 0.0

        return {
            "state": self.state.value,
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "failure_rate": failure_rate,
            "last_failure_time": self.last_failure_time,
            "half_open_success_count": self.half_open_success_count,
        }

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.total_requests = 0
        self.last_failure_time = None
        self.half_open_success_count = 0
        logger.info("Circuit breaker reset to CLOSED state")
