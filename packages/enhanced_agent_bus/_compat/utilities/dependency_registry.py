"""Shim for src.core.shared.utilities.dependency_registry."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.utilities.dependency_registry import *  # noqa: F403
except ImportError:

    class DependencyRegistry:
        """Minimal service-locator stub."""

        def __init__(self) -> None:
            self._deps: dict[str, Any] = {}

        def register(self, name: str, dependency: Any) -> None:
            self._deps[name] = dependency

        def resolve(self, name: str) -> Any:
            return self._deps.get(name)

        def has(self, name: str) -> bool:
            return name in self._deps

        def clear(self) -> None:
            self._deps.clear()

        def all(self) -> dict[str, Any]:
            return dict(self._deps)

    _registry: DependencyRegistry | None = None

    def get_dependency_registry() -> DependencyRegistry:
        global _registry  # noqa: PLW0603
        if _registry is None:
            _registry = DependencyRegistry()
        return _registry
