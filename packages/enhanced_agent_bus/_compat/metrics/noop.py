"""Shim for src.core.shared.metrics.noop."""
from __future__ import annotations

from typing import Any

try:
    from src.core.shared.metrics.noop import *  # noqa: F403
except ImportError:

    class NoOpCounter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def inc(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "NoOpCounter":
            return self

    class NoOpHistogram:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self, value: float = 0.0, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "NoOpHistogram":
            return self

        def time(self) -> "_Timer":
            return _Timer()

    class NoOpGauge:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def set(self, value: float = 0.0, **kwargs: Any) -> None:
            pass

        def inc(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def dec(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "NoOpGauge":
            return self

    class _Timer:
        def __enter__(self) -> "_Timer":
            return self

        def __exit__(self, *args: Any) -> None:
            pass
