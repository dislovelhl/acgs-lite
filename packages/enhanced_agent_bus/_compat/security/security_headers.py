"""Shim for src.core.shared.security.security_headers."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.security.security_headers import *  # noqa: F403
except ImportError:

    class SecurityHeadersMiddleware:
        """No-op security headers middleware stub."""

        def __init__(self, app: Any = None, **kwargs: Any) -> None:
            self.app = app

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if self.app is not None:
                await self.app(scope, receive, send)

    def get_security_headers() -> dict[str, str]:
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
        }

    def apply_security_headers(app: Any) -> None:
        """No-op stub."""
