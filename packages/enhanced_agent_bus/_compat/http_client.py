"""Shim for src.core.shared.http_client."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.http_client import *  # noqa: F403
except ImportError:

    class HttpClient:
        """Stub HTTP client that raises on use."""

        def __init__(self, base_url: str = "", **kwargs: Any) -> None:
            self.base_url = base_url
            self.timeout: float = kwargs.get("timeout", 30.0)
            self.headers: dict[str, str] = kwargs.get("headers", {})

        async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
            raise NotImplementedError("HttpClient not available in standalone mode")

        async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
            raise NotImplementedError("HttpClient not available in standalone mode")

        async def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
            raise NotImplementedError("HttpClient not available in standalone mode")

        async def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
            raise NotImplementedError("HttpClient not available in standalone mode")

        async def close(self) -> None:
            pass

        async def __aenter__(self) -> "HttpClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            await self.close()
