"""Shim for src.core.shared.database.session."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.database.session import *  # noqa: F403
except ImportError:
    Base: Any = None
    engine: Any = None
    SessionLocal: Any = None

    async def get_db() -> Any:
        """Stub: yields None (no real DB in standalone mode)."""
        yield None

    def init_db(**kwargs: Any) -> None:
        """No-op database initialization."""
