"""Shim for src.core.shared.di_container."""

from __future__ import annotations

from typing import Any, TypeVar

try:
    from src.core.shared.di_container import *  # noqa: F403
except ImportError:
    T = TypeVar("T")

    class DIContainer:
        """Minimal dependency injection container stub."""

        def __init__(self) -> None:
            self._registry: dict[str, Any] = {}

        def register(self, key: str | type, instance: Any) -> None:
            k = key if isinstance(key, str) else key.__qualname__
            self._registry[k] = instance

        def resolve(self, key: str | type) -> Any:
            k = key if isinstance(key, str) else key.__qualname__
            return self._registry.get(k)

        def has(self, key: str | type) -> bool:
            k = key if isinstance(key, str) else key.__qualname__
            return k in self._registry

        def clear(self) -> None:
            self._registry.clear()

    _container: DIContainer | None = None

    def get_container() -> DIContainer:
        global _container  # noqa: PLW0603
        if _container is None:
            _container = DIContainer()
        return _container
