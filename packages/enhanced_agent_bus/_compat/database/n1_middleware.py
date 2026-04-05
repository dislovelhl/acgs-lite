"""Shim for src.core.shared.database.n1_middleware."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.database.n1_middleware import *  # noqa: F403
except ImportError:

    class N1Detector:
        """No-op N+1 query detector for standalone mode."""

        def __init__(self, **kwargs: Any) -> None:
            self.enabled: bool = False
            self.threshold: int = kwargs.get("threshold", 5)

        def start_tracking(self) -> None:
            pass

        def stop_tracking(self) -> None:
            pass

        def report(self) -> dict[str, Any]:
            return {"enabled": False, "violations": []}

    class N1DetectorMiddleware:
        """No-op middleware stub."""

        def __init__(self, app: Any = None, **kwargs: Any) -> None:
            self.app = app

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if self.app is not None:
                await self.app(scope, receive, send)
