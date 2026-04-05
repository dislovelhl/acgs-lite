"""Shim for src.core.shared.security.execution_time_limit."""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

try:
    from src.core.shared.security.execution_time_limit import *  # noqa: F403
except ImportError:
    F = TypeVar("F", bound=Callable[..., Any])

    def execution_time_limit(seconds: float = 30.0) -> Callable[[F], F]:
        """No-op decorator — does not enforce time limits in standalone mode."""

        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return fn(*args, **kwargs)

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await fn(*args, **kwargs)

            import asyncio

            if asyncio.iscoroutinefunction(fn):
                return async_wrapper  # type: ignore[return-value]
            return wrapper  # type: ignore[return-value]

        return decorator
