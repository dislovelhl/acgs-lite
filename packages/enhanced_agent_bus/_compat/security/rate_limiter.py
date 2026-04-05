"""Shim for src.core.shared.security.rate_limiter."""

from __future__ import annotations

import importlib.util
import sys
from typing import Any, Callable

try:
    from src.core.shared.security.rate_limiter import *  # noqa: F403
    from src.core.shared.security.rate_limiter import (  # noqa: F401
        _extract_request_from_call,
        _module_available,
        _parse_bool_env,
        _resolve_rate_limit_identifier,
        add_rate_limit_headers,
        configure_rate_limits,
        rate_limit,
        update_rate_limit_metrics,
    )
except ImportError:

    def _parse_bool_env(value: str | None) -> bool | None:
        """Parse a boolean-ish environment variable string."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return None

    def _module_available(module_name: str) -> bool:
        """Return whether a module is available without crashing on stub modules."""
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ModuleNotFoundError, ValueError):
            return sys.modules.get(module_name) is not None

    def _extract_request_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        """Extract FastAPI Request from decorated endpoint call."""
        try:
            from fastapi import Request
        except ImportError:
            return None
        for arg in args:
            if isinstance(arg, Request):
                return arg
        request_candidate = kwargs.get("request")
        if isinstance(request_candidate, Request):
            return request_candidate
        return None

    def _resolve_rate_limit_identifier(
        request: Any, limit_type: str, key_func: Callable[..., str] | None
    ) -> str:
        """Resolve the identifier used for scoped rate limiting."""
        if key_func:
            return key_func(request)
        client_ip = request.client.host if request.client else "unknown"
        if limit_type == "user":
            user_id: str | None = getattr(request.state, "user_id", None)
            return str(user_id) if user_id is not None else client_ip
        if limit_type == "ip":
            return client_ip
        if limit_type == "endpoint":
            return str(request.url.path)
        return "global"

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

    def rate_limit(
        max_requests: int = 100,
        window_seconds: int = 60,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        """No-op rate limit decorator for standalone mode."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return decorator

    def update_rate_limit_metrics(**kwargs: Any) -> None:
        """No-op metrics update."""

    def configure_rate_limits(**kwargs: Any) -> None:
        """No-op rate limit configuration."""

    def add_rate_limit_headers(response: Any, **kwargs: Any) -> Any:
        """No-op header injection."""
        return response

    def create_rate_limit_middleware(app: Any = None, **kwargs: Any) -> RateLimitMiddleware:
        """Factory for no-op middleware."""
        return RateLimitMiddleware(app=app, **kwargs)
