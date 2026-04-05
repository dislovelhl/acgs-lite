"""Shim for src.core.shared.metrics._registry."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.metrics._registry import *  # noqa: F403
except ImportError:

    class _NoOpCounter:
        def inc(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "_NoOpCounter":
            return self

    class _NoOpHistogram:
        def observe(self, value: float = 0.0, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "_NoOpHistogram":
            return self

        def time(self) -> "_Timer":
            return _Timer()

    class _NoOpGauge:
        def set(self, value: float = 0.0, **kwargs: Any) -> None:
            pass

        def inc(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def dec(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "_NoOpGauge":
            return self

    class _Timer:
        def __enter__(self) -> "_Timer":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    def _get_or_create_counter(
        name: str, description: str = "", labelnames: Any = None, **kwargs: Any
    ) -> _NoOpCounter:
        return _NoOpCounter()

    def _get_or_create_histogram(
        name: str, description: str = "", labelnames: Any = None, buckets: Any = None, **kwargs: Any
    ) -> _NoOpHistogram:
        return _NoOpHistogram()

    def _get_or_create_gauge(
        name: str, description: str = "", labelnames: Any = None, **kwargs: Any
    ) -> _NoOpGauge:
        return _NoOpGauge()
