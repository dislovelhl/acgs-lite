"""Shim for src.core.shared.types.protocol_types."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

try:
    from src.core.shared.types.protocol_types import *  # noqa: F403
except ImportError:

    @runtime_checkable
    class Identifiable(Protocol):
        @property
        def id(self) -> str: ...

    @runtime_checkable
    class Timestamped(Protocol):
        @property
        def created_at(self) -> str: ...

        @property
        def updated_at(self) -> str: ...

    @runtime_checkable
    class Serializable(Protocol):
        def to_dict(self) -> dict[str, Any]: ...

    @runtime_checkable
    class Validatable(Protocol):
        def validate(self) -> bool: ...

    @runtime_checkable
    class HasMetadata(Protocol):
        @property
        def metadata(self) -> dict[str, Any]: ...

    @runtime_checkable
    class Configurable(Protocol):
        def configure(self, config: dict[str, Any]) -> None: ...

    @runtime_checkable
    class Closeable(Protocol):
        async def close(self) -> None: ...

    @runtime_checkable
    class HealthCheckable(Protocol):
        async def health_check(self) -> dict[str, Any]: ...
