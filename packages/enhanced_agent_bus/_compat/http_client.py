"""Shim for src.core.shared.http_client."""

from __future__ import annotations

import asyncio
import time
from typing import Any

try:
    from src.core.shared.http_client import *  # noqa: F403
    from src.core.shared.http_client import _AsyncCircuitBreaker  # noqa: F401
except ImportError:

    class _AsyncCircuitBreaker:
        """Async circuit breaker stub for standalone mode."""

        def __init__(
            self,
            failure_threshold: int = 5,
            recovery_timeout: float = 60.0,
            success_threshold: int = 2,
        ) -> None:
            self._failure_threshold = failure_threshold
            self._recovery_timeout = recovery_timeout
            self._success_threshold = success_threshold
            self._state = "closed"
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = 0.0
            self._lock = asyncio.Lock()

        @staticmethod
        def _now() -> float:
            try:
                return asyncio.get_running_loop().time()
            except RuntimeError:
                return time.monotonic()

        async def allow_request(self) -> bool:
            async with self._lock:
                if self._state == "closed":
                    return True
                elif self._state == "open":
                    if self._now() - self._last_failure_time >= self._recovery_timeout:
                        self._state = "half_open"
                        self._success_count = 0
                        return True
                    return False
                elif self._state == "half_open":
                    return True
                return True

        async def record_success(self) -> None:
            async with self._lock:
                if self._state == "half_open":
                    self._success_count += 1
                    if self._success_count >= self._success_threshold:
                        self._state = "closed"
                        self._failure_count = 0
                elif self._state == "closed":
                    self._failure_count = 0

        async def record_failure(self) -> None:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = self._now()
                if self._state == "half_open":
                    self._state = "open"
                elif self._state == "closed":
                    if self._failure_count >= self._failure_threshold:
                        self._state = "open"

        def get_state(self) -> str:
            return self._state

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
