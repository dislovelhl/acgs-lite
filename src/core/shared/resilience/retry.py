"""
ACGS-2 Retry Utilities
Constitutional Hash: 608508a9bd224290

Canonical location: src.core.shared.resilience.retry

Provides retry decorators and utilities with exponential backoff for
resilient service communication across ACGS-2 components.

Features:
- Configurable retry behavior via RetryConfig dataclass
- Exponential backoff with jitter to prevent thundering herd
- Configurable retry conditions (retry on specific exceptions)
- Async and sync support
- Integration with circuit breaker pattern
- Structured logging with correlation ID

Usage:
    from src.core.shared.errors.retry import retry, RetryConfig

    # Simple decorator usage
    @retry(max_retries=3, base_delay=1.0)
    async def fetch_policy(policy_id: str) -> dict:
        return await policy_client.get(policy_id)

    # With custom configuration
    config = RetryConfig(
        max_retries=5,
        base_delay=0.5,
        max_delay=30.0,
        jitter=True,
        retryable_exceptions=(ConnectionError, TimeoutError),
    )

    @retry(config=config)
    async def call_external_service():
        ...
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import secrets
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TypeVar, cast

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ACGSBaseError, ServiceUnavailableError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

_secure_rng = secrets.SystemRandom()

logger = get_logger(__name__)
T = TypeVar("T")

# Default exceptions that are considered retryable
DEFAULT_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,  # Covers network-related OS errors
)


class RetryExhaustedError(ACGSBaseError):
    """
    Raised when all retry attempts have been exhausted (Q-H4 migration).

    Attributes:
        attempts: Number of attempts made.
        last_exception: The last exception that caused the failure.
        operation: Name of the operation that failed.
        constitutional_hash: Constitutional hash for governance tracking.
    """

    http_status_code = 503
    error_code = "RETRY_EXHAUSTED"

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_exception: BaseException | None = None,
        operation: str = "",
        **kwargs: object,
    ) -> None:
        # Preserve backward-compatible attributes
        self.attempts = attempts
        self.last_exception = last_exception
        self.operation = operation

        # Build details dict for ACGSBaseError
        details = kwargs.pop("details", {}) or {}
        details.update(
            {
                "attempts": attempts,
                "operation": operation,
            }
        )

        super().__init__(
            message,
            details=details,
            cause=last_exception,
            **kwargs,
        )

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for logging."""
        return {
            "error": "RETRY_EXHAUSTED",
            "message": str(self),
            "attempts": self.attempts,
            "operation": self.operation,
            "last_exception_type": (
                type(self.last_exception).__name__ if self.last_exception else None
            ),
            "last_exception_message": str(self.last_exception) if self.last_exception else None,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.

    Constitutional Hash: 608508a9bd224290

    Attributes:
        max_retries: Maximum number of retry attempts (not including initial).
        max_attempts: Alias for max_retries + 1 (total attempts).
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay cap in seconds.
        multiplier: Factor to multiply delay by each attempt.
        jitter: If True, adds random jitter to prevent thundering herd.
        jitter_factor: Maximum jitter as a fraction of delay (0.0 to 1.0).
        retryable_exceptions: Tuple of exception types to retry on.
        on_retry: Optional callback called before each retry.
        raise_on_exhausted: If True, raises RetryExhaustedError when exhausted.
    """

    max_retries: int = 3
    max_attempts: int | None = None
    base_delay: float = 1.0
    max_delay: float = 60.0
    multiplier: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.25
    retryable_exceptions: tuple[type[BaseException], ...] = field(
        default_factory=lambda: DEFAULT_RETRYABLE_EXCEPTIONS
    )
    on_retry: Callable[[int, BaseException], None] | None = None
    raise_on_exhausted: bool = True

    def __post_init__(self):
        """Normalize max_retries and max_attempts."""
        if self.max_attempts is not None:
            # max_attempts includes the initial try, so max_retries is attempts - 1
            self.max_retries = max(0, self.max_attempts - 1)
        else:
            self.max_attempts = self.max_retries + 1

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt number.

        Args:
            attempt: The attempt number (1-indexed).

        Returns:
            Delay in seconds with optional jitter applied.
        """
        # Exponential backoff: base * multiplier^(attempt-1)
        delay = self.base_delay * (self.multiplier ** (attempt - 1))

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Apply jitter if enabled
        if self.jitter:
            jitter_range = delay * self.jitter_factor
            delay = delay + _secure_rng.uniform(-jitter_range, jitter_range)
            delay = max(0.0, delay)  # Ensure non-negative

        return delay

    def to_dict(self) -> JSONDict:
        """Convert configuration to dictionary."""
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "multiplier": self.multiplier,
            "jitter": self.jitter,
            "jitter_factor": self.jitter_factor,
            "retryable_exceptions": [e.__name__ for e in self.retryable_exceptions],
            "raise_on_exhausted": self.raise_on_exhausted,
        }


def retry(
    max_retries: int | None = None,
    max_attempts: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    retryable_exceptions: tuple[type[BaseException], ...] | None = None,
    on_retry: Callable[[int, BaseException], None] | None = None,
    config: RetryConfig | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Universal retry decorator supporting both async and sync functions.

    Constitutional Hash: 608508a9bd224290

    Args:
        max_retries: Maximum number of retry attempts.
        max_attempts: Alias for max_retries + 1 (total attempts).
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay cap in seconds.
        retryable_exceptions: Tuple of exception types to retry on.
        on_retry: Optional callback called before each retry.
        config: RetryConfig instance (overrides individual parameters).

    Returns:
        Decorated function with retry logic.

    Usage:
        @retry(max_retries=3, base_delay=1.0)
        async def fetch_data(url: str) -> dict:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                return response.json()
    """
    # Build configuration
    if config is None:
        config = RetryConfig(
            max_retries=max_retries if max_retries is not None else 3,
            max_attempts=max_attempts,
            base_delay=base_delay if base_delay is not None else 1.0,
            max_delay=max_delay if max_delay is not None else 60.0,
            retryable_exceptions=retryable_exceptions or DEFAULT_RETRYABLE_EXCEPTIONS,
            on_retry=on_retry,
        )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Determine if function is async
        is_async = inspect.iscoroutinefunction(func)

        if is_async:
            return cast(Callable[..., T], _create_async_wrapper(func, config))
        else:
            return cast(Callable[..., T], _create_sync_wrapper(func, config))

    return decorator


def _create_async_wrapper(
    func: Callable[..., T],
    config: RetryConfig,
) -> Callable[..., T]:
    """Create async wrapper for retry logic."""

    @functools.wraps(func)
    async def wrapper(*args: object, **kwargs: object) -> T:
        last_exception: BaseException | None = None

        for attempt in range(1, config.max_retries + 2):  # +2 for initial + max_retries
            try:
                return await cast(object, func)(*args, **kwargs)
            except config.retryable_exceptions as e:
                last_exception = e

                # Check if this was the last attempt
                if attempt > config.max_retries:
                    break

                # Calculate delay
                delay = config.calculate_delay(attempt)

                # Log retry attempt
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Retry {attempt}/{config.max_retries} for "
                    f"{func.__name__}: {type(e).__name__}: {e}. Waiting {delay:.2f}s"
                )

                # Call on_retry callback if provided
                if config.on_retry:
                    config.on_retry(attempt, e)

                # Wait before retry
                await asyncio.sleep(delay)

        # All retries exhausted
        if config.raise_on_exhausted:
            raise RetryExhaustedError(
                f"All {config.max_retries} retries exhausted for {func.__name__}",
                attempts=config.max_retries + 1,
                last_exception=last_exception,
                operation=func.__name__,
            )

        # Re-raise last exception if not raising RetryExhaustedError
        if last_exception:
            raise last_exception

        # Should not reach here
        raise ServiceUnavailableError(
            f"Retry logic error in {func.__name__}",
            error_code="RETRY_LOGIC_ERROR",
        )

    return cast(Callable[..., T], wrapper)


def _create_sync_wrapper(
    func: Callable[..., T],
    config: RetryConfig,
) -> Callable[..., T]:
    """Create sync wrapper for retry logic."""

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> T:
        last_exception: BaseException | None = None

        for attempt in range(1, config.max_retries + 2):
            try:
                return func(*args, **kwargs)
            except config.retryable_exceptions as e:
                last_exception = e

                if attempt > config.max_retries:
                    break

                delay = config.calculate_delay(attempt)

                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Retry {attempt}/{config.max_retries} for "
                    f"{func.__name__}: {type(e).__name__}: {e}. Waiting {delay:.2f}s"
                )

                if config.on_retry:
                    config.on_retry(attempt, e)

                # WARNING: This sleep implementation blocks the event loop when called
                # from async context. The code below detects running event loops and
                # raises an error to prevent blocking. For async callers, use retry_async
                # which uses asyncio.sleep() instead. This function is designed for
                # synchronous retry loops only.
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(asyncio.sleep(delay))
                else:
                    logger.debug(
                        "retry_sync detected running event loop during retry of %s",
                        func.__name__,
                        exc_info=True,
                    )
                    raise ServiceUnavailableError(
                        "retry_sync cannot block inside a running event loop; "
                        "use retry_async for async contexts",
                        error_code="RETRY_EVENT_LOOP_CONFLICT",
                    ) from None

        if config.raise_on_exhausted:
            raise RetryExhaustedError(
                f"All {config.max_retries} retries exhausted for {func.__name__}",
                attempts=config.max_retries + 1,
                last_exception=last_exception,
                operation=func.__name__,
            )

        if last_exception:
            raise last_exception

        raise ServiceUnavailableError(
            f"Retry logic error in {func.__name__}",
            error_code="RETRY_LOGIC_ERROR",
        )

    return cast(Callable[..., T], wrapper)


# retry_async / retry_sync are pure aliases of retry() — kept for backward
# compatibility and semantic clarity. retry() already auto-detects async/sync.
retry_async = retry
retry_sync = retry


async def exponential_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    multiplier: float = 2.0,
) -> AsyncIterator[float]:
    """
    Async generator yielding delay values for exponential backoff.

    Constitutional Hash: 608508a9bd224290

    Args:
        max_attempts: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        jitter: If True, adds random jitter to prevent thundering herd.
        multiplier: Factor to multiply delay by each attempt.

    Yields:
        Delay value in seconds for each attempt.

    Example:
        async for delay in exponential_backoff(max_attempts=5):
            try:
                result = await external_api_call()
                break
            except TransientError:
                logger.warning("Retrying in %.2fs...", delay)
                await asyncio.sleep(delay)
    """
    delay = base_delay
    for _attempt in range(max_attempts):
        if jitter:
            jitter_factor = 1.0 + _secure_rng.uniform(-0.25, 0.25)
            yield min(delay * jitter_factor, max_delay)
        else:
            yield min(delay, max_delay)
        delay *= multiplier


class RetryBudget:
    """
    Token-bucket style retry budget to prevent retry storms.

    Constitutional Hash: 608508a9bd224290

    Limits total retries across all operations within a time window.

    Example:
        budget = RetryBudget(max_retries=10, window_seconds=60.0)

        async def fetch_with_budget():
            if not await budget.can_retry():
                raise ServiceUnavailableError(
                    "Retry budget exhausted",
                    error_code="RETRY_BUDGET_EXHAUSTED",
                )
            await budget.record_retry()
            ...
    """

    def __init__(self, max_retries: int = 10, window_seconds: float = 60.0) -> None:
        self.max_retries = max_retries
        self.window_seconds = window_seconds
        self._retries: list[float] = []
        self._lock = asyncio.Lock()

    @staticmethod
    def _now() -> float:
        """Return monotonic time from event loop or process clock."""
        try:
            return asyncio.get_running_loop().time()
        except RuntimeError:
            return time.monotonic()

    async def can_retry(self) -> bool:
        """Check if a retry is allowed within budget."""
        async with self._lock:
            self._cleanup_old_retries()
            return len(self._retries) < self.max_retries

    async def record_retry(self) -> None:
        """Record that a retry was attempted."""
        async with self._lock:
            self._retries.append(self._now())
            self._cleanup_old_retries()

    def _cleanup_old_retries(self) -> None:
        """Remove retries outside the time window."""
        now = self._now()
        cutoff = now - self.window_seconds
        self._retries = [t for t in self._retries if t > cutoff]

    def get_retry_count(self) -> int:
        """Get current retry count in window."""
        self._cleanup_old_retries()
        return len(self._retries)


__all__ = [
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    "RetryBudget",
    "RetryConfig",
    "RetryExhaustedError",
    "exponential_backoff",
    "retry",
    "retry_async",
    "retry_sync",
]
