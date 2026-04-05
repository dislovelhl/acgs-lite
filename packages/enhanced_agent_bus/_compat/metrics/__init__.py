"""Shim for src.core.shared.metrics."""
from __future__ import annotations

from typing import Any

from ._registry import *  # noqa: F403
from ._registry import _get_or_create_counter, _get_or_create_gauge, _get_or_create_histogram

try:
    from src.core.shared.metrics import *  # noqa: F403
except ImportError:

    class _NoOpMetric:
        """Metric that silently discards all observations."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self, value: float = 0.0, **kwargs: Any) -> None:
            pass

        def inc(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def dec(self, value: float = 1.0, **kwargs: Any) -> None:
            pass

        def set(self, value: float = 0.0, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "_NoOpMetric":
            return self

        def time(self) -> "_NoOpContextManager":
            return _NoOpContextManager()

    class _NoOpContextManager:
        def __enter__(self) -> "_NoOpContextManager":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    HTTP_REQUEST_DURATION = _NoOpMetric()
    HTTP_REQUESTS_TOTAL = _NoOpMetric()
    MESSAGE_PROCESSING_DURATION = _NoOpMetric()
    MESSAGES_PROCESSED_TOTAL = _NoOpMetric()
    ACTIVE_CONNECTIONS = _NoOpMetric()
