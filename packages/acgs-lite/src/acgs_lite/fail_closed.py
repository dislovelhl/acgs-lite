"""Unified fail-closed decorator for governance operations.

Constitutional Hash: 608508a9bd224290

Usage:
    @fail_closed(deny_value=False)
    def check_policy(action: str) -> bool:
        ...  # If anything throws, returns False

    @fail_closed(deny_value=ValidationResult.denied())
    async def validate(msg: Message) -> ValidationResult:
        ...  # If anything throws, returns denied result
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FailClosedError(Exception):
    """Raised when a fail-closed operation encounters an error."""


def fail_closed(
    deny_value: Any = None,
    *,
    log_level: int = logging.WARNING,
    message: str = "fail_closed: operation failed, returning deny value",
    reraise: tuple[type[BaseException], ...] = (KeyboardInterrupt, SystemExit),
) -> Callable:
    """Decorator: wraps sync or async functions in fail-closed error handling.

    On any exception (except those in ``reraise``), logs the error and returns
    ``deny_value`` instead of propagating. This ensures governance operations
    always deny on failure rather than silently passing.

    Args:
        deny_value: The value to return on failure. Use the most restrictive
            safe default for your return type (False, empty list, denied result).
        log_level: Logging level for the failure message.
        message: Log message prefix.
        reraise: Exception types that should propagate (never swallowed).
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await fn(*args, **kwargs)
                except reraise:
                    raise
                except Exception as exc:
                    logger.log(
                        log_level,
                        "%s: %s.%s: %s",
                        message,
                        fn.__module__,
                        fn.__qualname__,
                        type(exc).__name__,
                    )
                    return deny_value

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return fn(*args, **kwargs)
                except reraise:
                    raise
                except Exception as exc:
                    logger.log(
                        log_level,
                        "%s: %s.%s: %s",
                        message,
                        fn.__module__,
                        fn.__qualname__,
                        type(exc).__name__,
                    )
                    return deny_value

            return sync_wrapper  # type: ignore[return-value]

    return decorator
