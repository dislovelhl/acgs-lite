"""Lightweight dependency-injection container for agent scope isolation.

Provides AgentScope (a context-manager-aware scoped registry) and DIContainer
(a global factory for child scopes).  Designed for fail-closed semantics:
AgentScope.__exit__ always resets the scope, even on exception.
"""

from __future__ import annotations

import threading
from types import TracebackType
from typing import Any, TypeVar

T = TypeVar("T")


class AgentScope:
    """An isolated service registry for one agent / conversation scope.

    Usage::

        scope = DIContainer.child_scope("my-agent")
        scope.register(MyService, MyService())
        svc = scope.get(MyService)

        # As a context manager — always cleans up on exit (fail-closed)
        with scope:
            ...
    """

    def __init__(self, scope_id: str) -> None:
        self.scope_id = scope_id
        self._registry: dict[type[Any], Any] = {}

    def register(self, service_type: type[T], instance: T) -> None:
        """Bind *instance* to *service_type* within this scope."""
        self._registry[service_type] = instance

    def get(self, service_type: type[T]) -> T:
        """Resolve *service_type* from this scope.

        Raises:
            KeyError: if the type has not been registered.
        """
        if service_type not in self._registry:
            raise KeyError(service_type)
        return self._registry[service_type]  # type: ignore[return-value]

    def reset(self) -> None:
        """Remove all registrations from this scope."""
        self._registry.clear()

    # ------------------------------------------------------------------
    # Context-manager support (fail-closed)
    # ------------------------------------------------------------------

    def __enter__(self) -> AgentScope:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.reset()


class DIContainer:
    """Global factory and registry for AgentScope instances.

    All state is class-level so there is a single container per process.
    Thread-safe via a reentrant lock.
    """

    _lock: threading.RLock = threading.RLock()
    _scopes: dict[str, AgentScope] = {}

    @classmethod
    def child_scope(cls, scope_id: str) -> AgentScope:
        """Return a new (or existing) AgentScope for *scope_id*."""
        with cls._lock:
            if scope_id not in cls._scopes:
                cls._scopes[scope_id] = AgentScope(scope_id)
            return cls._scopes[scope_id]

    @classmethod
    def reset(cls) -> None:
        """Destroy all scopes — intended for test isolation."""
        with cls._lock:
            cls._scopes.clear()
