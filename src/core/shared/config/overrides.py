"""
ACGS-2 Configuration Overrides
Constitutional Hash: 608508a9bd224290

Provides runtime configuration override mechanisms for testing
and environment-specific configuration adjustments.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from types import TracebackType

from src.core.shared.constants import CONSTITUTIONAL_HASH

_CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
_SENTINEL = object()
_override_lock = threading.Lock()
_overrides: dict[str, object] = {}


def set_override(key: str, value: object) -> None:
    with _override_lock:
        _overrides[key] = value


def get_override(key: str) -> object | None:
    with _override_lock:
        return _overrides.get(key)


def clear_overrides() -> None:
    with _override_lock:
        _overrides.clear()


def get_all_overrides() -> dict[str, object]:
    with _override_lock:
        return dict(_overrides)


@contextlib.contextmanager
def override_config(**overrides: object) -> Iterator[None]:
    previous: dict[str, object] = {}
    with _override_lock:
        for key, value in overrides.items():
            previous[key] = _overrides.get(key, _SENTINEL)
            _overrides[key] = value
    try:
        yield
    finally:
        with _override_lock:
            for key, previous_value in previous.items():
                if previous_value is _SENTINEL:
                    _ = _overrides.pop(key, None)
                else:
                    _overrides[key] = previous_value


class ConfigOverride:
    def __init__(self, **overrides: object) -> None:
        self._overrides: dict[str, object] = overrides
        self._previous: dict[str, object] = {}

    def __enter__(self) -> None:
        with _override_lock:
            for key, value in self._overrides.items():
                self._previous[key] = _overrides.get(key, _SENTINEL)
                _overrides[key] = value
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        with _override_lock:
            for key, previous_value in self._previous.items():
                if previous_value is _SENTINEL:
                    _ = _overrides.pop(key, None)
                else:
                    _overrides[key] = previous_value


__all__ = [
    "ConfigOverride",
    "clear_overrides",
    "get_all_overrides",
    "get_override",
    "override_config",
    "set_override",
]
