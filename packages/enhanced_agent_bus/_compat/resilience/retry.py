"""Shim for src.core.shared.resilience.retry."""
from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

try:
    from src.core.shared.resilience.retry import *  # noqa: F403
except ImportError:
    F = TypeVar("F", bound=Callable[..., Any])

    class RetryConfig:
        max_retries: int = 3
        base_delay: float = 1.0
        max_delay: float = 60.0
        exponential_base: float = 2.0
        retry_on: tuple[type[BaseException], ...] = (Exception,)

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def retry(
        max_retries: int = 3,
        delay: float = 1.0,
        retry_on: tuple[type[BaseException], ...] = (Exception,),
        **kwargs: Any,
    ) -> Callable[[F], F]:
        """No-op retry decorator — calls the function once without retries."""

        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kw: Any) -> Any:
                return fn(*args, **kw)

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kw: Any) -> Any:
                return await fn(*args, **kw)

            import asyncio

            if asyncio.iscoroutinefunction(fn):
                return async_wrapper  # type: ignore[return-value]
            return wrapper  # type: ignore[return-value]

        return decorator

    async def retry_async(
        fn: Callable[..., Any],
        *args: Any,
        config: RetryConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        """Stub: calls fn once without retries."""
        return await fn(*args, **kwargs)
