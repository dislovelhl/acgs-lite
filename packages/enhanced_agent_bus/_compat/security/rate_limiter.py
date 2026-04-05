"""Shim for src.core.shared.security.rate_limiter."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.security.rate_limiter import *  # noqa: F403
except ImportError:

    class RateLimiter:
        """No-op rate limiter for standalone mode."""

        def __init__(self, **kwargs: Any) -> None:
            self.max_requests: int = kwargs.get("max_requests", 100)
            self.window_seconds: int = kwargs.get("window_seconds", 60)

        async def check(self, key: str) -> bool:
            """Always permits the request."""
            return True

        async def is_allowed(self, key: str) -> bool:
            return True

        async def reset(self, key: str) -> None:
            pass

    class RateLimitMiddleware:
        """No-op middleware stub."""

        def __init__(self, app: Any = None, **kwargs: Any) -> None:
            self.app = app

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if self.app is not None:
                await self.app(scope, receive, send)

    def get_rate_limiter(**kwargs: Any) -> RateLimiter:
        return RateLimiter(**kwargs)
