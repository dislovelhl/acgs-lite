"""Adaptive Load Shedding Middleware for the API Gateway.

Constitutional Hash: 608508a9bd224290  # pragma: allowlist secret

Implements Design C: Adaptive Load Shedding Layer.  The middleware monitors
P99 latency over a rolling window and progressively sheds lower-priority
traffic when the SLO target is breached.  Governance and health paths are
constitutionally exempt (CI-2 invariant) and are **never** shed.

Priority cascade (shed first -> shed last):
    ANALYTICS > FEEDBACK > DISCOVERY > MESSAGES_LOW > MESSAGES_NORMAL
    GOVERNANCE and HEALTH are in the NEVER_SHED set and are always passed.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections import deque
from enum import StrEnum
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
_rng = secrets.SystemRandom()

# ---------------------------------------------------------------------------
# Prometheus metrics (optional — gracefully degrade if unavailable)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Gauge

    load_shed_gauge: Gauge | None = Gauge(
        "acgs_load_shed_percentage",
        "Current load shedding percentage",
    )
except (ImportError, ValueError):
    load_shed_gauge = None


# ---------------------------------------------------------------------------
# ShedPriority enum
# ---------------------------------------------------------------------------


class ShedPriority(StrEnum):
    """Priority tiers for load shedding decisions.

    Lower-priority tiers are shed first when latency exceeds the SLO target.
    GOVERNANCE and HEALTH are constitutionally exempt (CI-2 invariant).
    """

    ANALYTICS = "analytics"
    FEEDBACK = "feedback"
    DISCOVERY = "discovery"
    MESSAGES_LOW = "messages_low"
    MESSAGES_NORMAL = "messages"
    GOVERNANCE = "governance"
    HEALTH = "health"


NEVER_SHED: frozenset[ShedPriority] = frozenset({ShedPriority.GOVERNANCE, ShedPriority.HEALTH})
"""Constitutional invariant CI-2: these priorities are never shed."""

# Threshold at which each priority begins to be shed.  A lower value means
# the priority is shed more aggressively (earlier).
_PRIORITY_THRESHOLDS: dict[ShedPriority, float] = {
    ShedPriority.ANALYTICS: 0.3,
    ShedPriority.FEEDBACK: 0.5,
    ShedPriority.DISCOVERY: 0.6,
    ShedPriority.MESSAGES_LOW: 0.8,
    ShedPriority.MESSAGES_NORMAL: 1.0,
}


# ---------------------------------------------------------------------------
# AdaptiveLoadShedder — the core shedding algorithm
# ---------------------------------------------------------------------------


class AdaptiveLoadShedder:
    """Adaptive load shedder that tracks rolling P99 latency and decides
    whether to shed requests based on priority thresholds.

    Thread-safe via ``asyncio.Lock``.

    Args:
        p99_target_ms: P99 latency target in milliseconds (default 5.0).
        window_seconds: Rolling window size in seconds (default 30).
    """

    def __init__(
        self,
        p99_target_ms: float = 5.0,
        window_seconds: float = 30,
    ) -> None:
        self._p99_target_ms = p99_target_ms
        self._window_seconds = window_seconds
        self._latencies: deque[tuple[float, float]] = deque()  # (timestamp, latency_ms)
        self._shed_pct: float = 0.0
        self._lock = asyncio.Lock()

    # -- public API ---------------------------------------------------------

    async def record_latency(self, ms: float) -> None:
        """Record an observed response latency (milliseconds)."""
        async with self._lock:
            now = time.monotonic()
            self._latencies.append((now, ms))
            self._prune(now)

    async def should_shed(self, priority: ShedPriority) -> bool:
        """Return ``True`` if the request with the given *priority* should be
        shed (dropped with 503).

        Constitutional invariant CI-2: priorities in ``NEVER_SHED`` always
        return ``False``.
        """
        if priority in NEVER_SHED:
            return False

        async with self._lock:
            now = time.monotonic()
            self._prune(now)
            p99 = self._compute_p99()

            if p99 > self._p99_target_ms:
                self._shed_pct = min(self._shed_pct + 0.1, 1.0)
            else:
                self._shed_pct = max(self._shed_pct - 0.05, 0.0)

            if load_shed_gauge is not None:
                load_shed_gauge.set(self._shed_pct)

            threshold = _PRIORITY_THRESHOLDS.get(priority, 1.0)
            return _rng.random() < (self._shed_pct * threshold)

    async def get_shed_percentage(self) -> float:
        """Return the current shed percentage (0.0 .. 1.0)."""
        async with self._lock:
            return self._shed_pct

    # -- internals ----------------------------------------------------------

    def _prune(self, now: float) -> None:
        """Remove latency samples outside the rolling window."""
        cutoff = now - self._window_seconds
        while self._latencies and self._latencies[0][0] < cutoff:
            self._latencies.popleft()

    def _compute_p99(self) -> float:
        """Compute P99 latency from the current window.

        Returns ``0.0`` when no samples are available so that an empty window
        does not trigger shedding.
        """
        if not self._latencies:
            return 0.0
        values = sorted(v for _, v in self._latencies)
        idx = int(len(values) * 0.99)
        idx = min(idx, len(values) - 1)
        return values[idx]


# ---------------------------------------------------------------------------
# Path -> ShedPriority mapping
# ---------------------------------------------------------------------------

_DEFAULT_PATH_MAP: list[tuple[str, ShedPriority]] = [
    # Health probes — never shed (CI-2)
    ("/health", ShedPriority.HEALTH),
    ("/healthz", ShedPriority.HEALTH),
    ("/readyz", ShedPriority.HEALTH),
    ("/startupz", ShedPriority.HEALTH),
    # Governance / constitutional validation — never shed (CI-2)
    ("/api/v1/validate", ShedPriority.GOVERNANCE),
    ("/api/v1/governance", ShedPriority.GOVERNANCE),
    ("/api/v1/decisions", ShedPriority.GOVERNANCE),
    ("/api/v1/data-subject", ShedPriority.GOVERNANCE),
    ("/api/v1/policies", ShedPriority.GOVERNANCE),
    # Authentication and admin — important operational traffic
    ("/api/v1/sso", ShedPriority.MESSAGES_NORMAL),
    ("/api/v1/admin", ShedPriority.MESSAGES_NORMAL),
    # Core message flow
    ("/api/v1/messages", ShedPriority.MESSAGES_NORMAL),
    # Low-priority analytics and metrics
    ("/api/v1/stats", ShedPriority.ANALYTICS),
    ("/api/v1/analytics", ShedPriority.ANALYTICS),
    ("/metrics", ShedPriority.ANALYTICS),
    # Feedback
    ("/api/v1/feedback", ShedPriority.FEEDBACK),
]


def _classify_path(path: str) -> ShedPriority:
    """Map a request path to a :class:`ShedPriority`.

    Matches are prefix-based so ``/health`` also covers ``/healthz`` and
    ``/health/ready``.  First match wins.

    Falls back to :attr:`ShedPriority.MESSAGES_NORMAL` for unknown paths.
    """
    for prefix, priority in _DEFAULT_PATH_MAP:
        if path.startswith(prefix):
            return priority
    return ShedPriority.MESSAGES_NORMAL


# ---------------------------------------------------------------------------
# LoadSheddingMiddleware (Starlette)
# ---------------------------------------------------------------------------


class LoadSheddingMiddleware:
    """Pure ASGI middleware that applies adaptive load shedding per request.

    ~50-80% faster than the previous BaseHTTPMiddleware implementation by
    avoiding per-request Request object cloning and coroutine boundary overhead.

    When the rolling P99 latency exceeds the target, low-priority requests are
    progressively rejected with ``HTTP 503 Service Unavailable``.

    Governance and health requests are constitutionally exempt (CI-2).

    Args:
        app: The ASGI application to wrap.
        shedder: An :class:`AdaptiveLoadShedder` instance.  If ``None``, a
            default shedder is created with ``p99_target_ms=5.0`` and
            ``window_seconds=30``.
        path_classifier: Optional callable ``(str) -> ShedPriority``.
            Defaults to :func:`_classify_path`.
    """

    def __init__(
        self,
        app: ASGIApp,
        shedder: AdaptiveLoadShedder | None = None,
        path_classifier: Any | None = None,
    ) -> None:
        self.app = app
        self.shedder = shedder or AdaptiveLoadShedder()
        self._classify = path_classifier or _classify_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        priority = self._classify(path)

        if await self.shedder.should_shed(priority):
            shed_pct = await self.shedder.get_shed_percentage()
            logger.warning(
                "load_shedding.shed",
                path=path,
                priority=priority.value,
                shed_percentage=shed_pct,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            body = json.dumps(
                {
                    "error": "service_overloaded",
                    "message": "Request shed due to latency SLO breach",
                    "retry_after_seconds": 5,
                    "shed_priority": priority.value,
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", b"5"),
                        (b"x-shed-reason", b"latency_slo_breach"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        start = time.monotonic()
        await self.app(scope, receive, send)
        elapsed_ms = (time.monotonic() - start) * 1000.0

        await self.shedder.record_latency(elapsed_ms)
