"""Shim for src.core.shared.database.n1_middleware."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, List

# ContextVars defined before the try/except so the stub class can reference them
# directly at method call time (no circular import needed).
_n1_detection_enabled: ContextVar[bool] = ContextVar("_n1_detection_enabled", default=False)
_queries_executed: ContextVar[List[str] | None] = ContextVar("_queries_executed", default=None)
_query_count: ContextVar[int] = ContextVar("_query_count", default=0)


def setup_n1_detection(**kwargs: Any) -> None:
    """No-op setup function used by tests."""


try:
    from src.core.shared.database.n1_middleware import *  # noqa: F403

    # If the real module has its own ContextVars, re-export them so they
    # stay consistent with what N1Detector.record_query internally uses.
    try:
        from src.core.shared.database.n1_middleware import (  # noqa: F401
            _n1_detection_enabled,
            _queries_executed,
            _query_count,
        )
    except ImportError:
        pass  # stubs defined above are already in scope
except ImportError:

    class N1Detector:
        """Stub N+1 query detector for standalone mode."""

        def __init__(self, **kwargs: Any) -> None:
            self.enabled: bool = False
            self.threshold: int = kwargs.get("threshold", 5)

        def start_tracking(self) -> None:
            pass

        def stop_tracking(self) -> None:
            pass

        def report(self) -> dict[str, Any]:
            return {"enabled": False, "violations": []}

        @classmethod
        def record_query(cls, sql: str, duration: float) -> None:
            """Record a query into context-local storage when detection is on."""
            if not _n1_detection_enabled.get():
                return
            _query_count.set(_query_count.get() + 1)
            existing = _queries_executed.get()
            if existing is None:
                existing = []
            existing.append(sql)
            _queries_executed.set(existing)

    class N1DetectorMiddleware:
        """No-op middleware stub."""

        def __init__(self, app: Any = None, **kwargs: Any) -> None:
            self.app = app

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if self.app is not None:
                await self.app(scope, receive, send)
