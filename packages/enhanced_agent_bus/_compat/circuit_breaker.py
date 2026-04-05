"""Shim for src.core.shared.circuit_breaker."""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

try:
    from src.core.shared.circuit_breaker import *  # noqa: F403
    from src.core.shared.circuit_breaker import _registry  # noqa: F401
except ImportError:
    F = TypeVar("F", bound=Callable[..., Any])

    class _CircuitBreakerRegistry:
        """Lightweight registry stub for standalone mode."""

        def __init__(self) -> None:
            self._breakers: dict[str, Any] = {}

    _registry = _CircuitBreakerRegistry()

    class CircuitBreakerConfig:
        failure_threshold: int = 5
        success_threshold: int = 2
        timeout_seconds: float = 30.0
        half_open_max_calls: int = 1

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class CircuitBreaker:
        """No-op circuit breaker — always closed."""

        def __init__(self, config: CircuitBreakerConfig | None = None, **kwargs: Any) -> None:
            self.config = config or CircuitBreakerConfig()
            self.state: str = "closed"

        def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        async def async_call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            return await fn(*args, **kwargs)

        def reset(self) -> None:
            self.state = "closed"

    def get_circuit_breaker(
        service_name: str = "",
        config: CircuitBreakerConfig | None = None,
        **kwargs: Any,
    ) -> CircuitBreaker:
        return CircuitBreaker(config=config, **kwargs)

    def circuit_breaker(name: str = "", **kwargs: Any) -> Callable[[F], F]:
        """No-op decorator."""

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
