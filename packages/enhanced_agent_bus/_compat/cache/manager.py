"""Shim for src.core.shared.cache.manager."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.cache.manager import *  # noqa: F403
except ImportError:

    class TieredCacheManager:
        """Minimal in-memory cache stub (no Redis/external tiers)."""

        def __init__(self, **kwargs: Any) -> None:
            self._local: dict[str, Any] = {}
            self.default_ttl: int = kwargs.get("default_ttl", 300)

        async def get(self, key: str) -> Any | None:
            return self._local.get(key)

        async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
            self._local[key] = value

        async def delete(self, key: str) -> None:
            self._local.pop(key, None)

        async def clear(self) -> None:
            self._local.clear()

        async def has(self, key: str) -> bool:
            return key in self._local

    def get_cache_manager(**kwargs: Any) -> TieredCacheManager:
        return TieredCacheManager(**kwargs)
