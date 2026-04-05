"""Shim package for src.core.shared.cache."""

from __future__ import annotations

try:
    from src.core.shared.cache import *  # noqa: F403
    from src.core.shared.cache import workflow_cache
except ImportError:
    from functools import lru_cache as _lru

    def workflow_cache(func=None, *, maxsize=128, ttl=None):  # type: ignore[assignment]
        """No-op workflow cache for standalone mode."""
        if func is None:
            return lambda f: _lru(maxsize=maxsize)(f)
        return _lru(maxsize=maxsize)(func)
