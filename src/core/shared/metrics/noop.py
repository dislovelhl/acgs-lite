# pyright: reportAssignmentType=false
"""
ACGS-2 Prometheus No-Op Metrics
Constitutional Hash: 608508a9bd224290

Provides no-op metric implementations for graceful degradation when
prometheus_client is not installed. Also provides _safe_create_metric()
for handling duplicate metric registration.

Usage:
    from src.core.shared.metrics.noop import (
        PROMETHEUS_AVAILABLE, Counter, Gauge, Histogram, Info,
        _safe_create_metric,
    )
"""

from __future__ import annotations

from src.core.shared.structured_logging import get_logger

from ..types import JSONDict

logger = get_logger(__name__)
# ---------------------------------------------------------------------------
# Probe for prometheus_client
# ---------------------------------------------------------------------------

_prometheus_available = False
_registry = None
_content_type_latest = "text/plain"
_pc = None

try:
    import prometheus_client as _pc
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        Summary,
        generate_latest,
    )

    _prometheus_available = True
except ImportError:
    _registry = None
    _content_type_latest = "text/plain"

    def generate_latest(registry=None):  # type: ignore[misc]
        """Return empty bytes when prometheus_client is unavailable."""
        return b""

# ---------------------------------------------------------------------------
# No-Op metric classes (always importable)
# ---------------------------------------------------------------------------


class NoOpCounter:
    """No-op Counter when prometheus_client is unavailable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def labels(self, **kwargs: object) -> NoOpCounter:
        """Return self (no-op label filtering)."""
        return self

    def inc(self, amount: float = 1) -> None:
        """Increment counter (no-op)."""
        pass


class NoOpGauge:
    """No-op Gauge when prometheus_client is unavailable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def labels(self, **kwargs: object) -> NoOpGauge:
        """Return self (no-op label filtering)."""
        return self

    def set(self, value: float) -> None:
        """Set gauge value (no-op)."""
        pass

    def inc(self, amount: float = 1) -> None:
        """Increment gauge (no-op)."""
        pass

    def dec(self, amount: float = 1) -> None:
        """Decrement gauge (no-op)."""
        pass


class NoOpHistogram:
    """No-op Histogram when prometheus_client is unavailable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def labels(self, **kwargs: object) -> NoOpHistogram:
        """Return self (no-op label filtering)."""
        return self

    def observe(self, value: float) -> None:
        """Record an observation (no-op)."""
        pass

    def time(self) -> NoOpTimer:
        """Return a no-op context manager for timing."""
        return NoOpTimer()


class NoOpInfo:
    """No-op Info when prometheus_client is unavailable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def info(self, value: dict[str, str]) -> None:
        """Set info labels (no-op)."""
        pass

    def labels(self, **kwargs: object) -> NoOpInfo:
        """Return self (no-op label filtering)."""
        return self


class NoOpSummary:
    """No-op Summary when prometheus_client is unavailable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def labels(self, **kwargs: object) -> NoOpSummary:
        """Return self (no-op label filtering)."""
        return self

    def observe(self, value: float) -> None:
        """Record an observation (no-op)."""
        pass


class NoOpTimer:
    """No-op context manager for Histogram.time()."""

    def __enter__(self) -> NoOpTimer:
        return self

    def __exit__(self, *args: object) -> None:
        pass


# ---------------------------------------------------------------------------
# When prometheus_client is not installed, alias the real names to no-ops
# ---------------------------------------------------------------------------

if not _prometheus_available:
    Counter = NoOpCounter  # type: ignore[assignment, misc]
    Gauge = NoOpGauge  # type: ignore[assignment, misc]
    Histogram = NoOpHistogram  # type: ignore[assignment, misc]
    Info = NoOpInfo  # type: ignore[assignment, misc]
    Summary = NoOpSummary  # type: ignore[assignment, misc]

PROMETHEUS_AVAILABLE = _prometheus_available
REGISTRY = _pc.REGISTRY if _pc is not None else _registry
CONTENT_TYPE_LATEST = _pc.CONTENT_TYPE_LATEST if _pc is not None else _content_type_latest

# ---------------------------------------------------------------------------
# Safe metric creation helper
# ---------------------------------------------------------------------------


def _safe_create_metric(
    metric_class: type,
    name: str,
    documentation: str,
    labels: list[str] | None = None,
    buckets: tuple[float, ...] | None = None,
) -> object:
    """
    Safely create a Prometheus metric, handling duplicate registration gracefully.

    Returns no-op when prometheus_client is unavailable, and falls back to no-op
    on duplicate metric registration (common in pytest / multi-import scenarios).
    """
    if not PROMETHEUS_AVAILABLE:
        return metric_class()

    try:
        kwargs: JSONDict = {}
        if labels:
            kwargs["labelnames"] = labels
        if buckets is not None and metric_class is Histogram:
            kwargs["buckets"] = buckets
        return metric_class(name, documentation, **kwargs)
    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.debug("Metric %s already registered: %s", name, e)
            # Try to retrieve from registry
            try:
                if REGISTRY is not None:
                    for collector in REGISTRY._names_to_collectors.values():
                        if getattr(collector, "_name", None) == name:
                            return collector
            except (AttributeError, RuntimeError):
                pass
            # Fall back to no-op (NOT metric_class() — real classes need args)
            return NoOpCounter()
        raise


__all__ = [
    "CONTENT_TYPE_LATEST",
    "PROMETHEUS_AVAILABLE",
    "REGISTRY",
    "Counter",
    "Gauge",
    "Histogram",
    "Info",
    "NoOpCounter",
    "NoOpGauge",
    "NoOpHistogram",
    "NoOpInfo",
    "NoOpSummary",
    "NoOpTimer",
    "Summary",
    "_safe_create_metric",
    "generate_latest",
]
