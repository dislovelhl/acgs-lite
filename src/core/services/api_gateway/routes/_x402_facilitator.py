"""x402 facilitator failover pool with circuit-breaker health tracking.

Provides automatic failover across multiple x402 payment facilitators so that
paid endpoints remain available when any single facilitator is unreachable.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["x402-facilitator"])

# ---------------------------------------------------------------------------
# Circuit-breaker constants
# ---------------------------------------------------------------------------

_FAILURE_THRESHOLD: Final[int] = 3
_COOLDOWN_SECONDS: Final[float] = 60.0


# ---------------------------------------------------------------------------
# Per-facilitator health state (immutable snapshots via replace)
# ---------------------------------------------------------------------------


class _FacilitatorState:
    """Snapshot of a single facilitator's health metrics."""

    __slots__ = (
        "consecutive_failures",
        "last_failure",
        "last_success",
        "url",
    )

    def __init__(
        self,
        url: str,
        *,
        last_success: float = 0.0,
        last_failure: float = 0.0,
        consecutive_failures: int = 0,
    ) -> None:
        self.url = url
        self.last_success = last_success
        self.last_failure = last_failure
        self.consecutive_failures = consecutive_failures

    def with_success(self, ts: float) -> _FacilitatorState:
        return _FacilitatorState(
            self.url,
            last_success=ts,
            last_failure=self.last_failure,
            consecutive_failures=0,
        )

    def with_failure(self, ts: float) -> _FacilitatorState:
        return _FacilitatorState(
            self.url,
            last_success=self.last_success,
            last_failure=ts,
            consecutive_failures=self.consecutive_failures + 1,
        )

    @property
    def is_healthy(self) -> bool:
        if self.consecutive_failures < _FAILURE_THRESHOLD:
            return True
        elapsed = time.monotonic() - self.last_failure
        return elapsed >= _COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FacilitatorStatus(BaseModel):
    url: str
    healthy: bool
    consecutive_failures: int
    last_success_ago_s: float | None
    last_failure_ago_s: float | None
    circuit_state: str


class FacilitatorHealthResponse(BaseModel):
    constitutional_hash: str
    facilitators: list[FacilitatorStatus]
    active_facilitator: str | None


# ---------------------------------------------------------------------------
# FacilitatorPool
# ---------------------------------------------------------------------------


def _parse_urls() -> list[str]:
    """Read facilitator URLs from environment, dedup while preserving order."""
    raw = os.getenv("X402_FACILITATOR_URLS")
    if not raw:
        raw = os.getenv("FACILITATOR_URL", "https://facilitator.xpay.sh")
    urls: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        url = part.strip().rstrip("/")
        if url and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


class FacilitatorPool:
    """Thread-safe facilitator pool with circuit-breaker failover.

    After ``_FAILURE_THRESHOLD`` consecutive failures a facilitator enters
    *open* state for ``_COOLDOWN_SECONDS``.  If **all** facilitators are
    unhealthy the pool returns the one whose cooldown is closest to expiry,
    ensuring requests are never silently dropped.
    """

    def __init__(self, urls: list[str] | None = None) -> None:
        resolved = urls if urls is not None else _parse_urls()
        if not resolved:
            resolved = ["https://facilitator.xpay.sh"]
        self._states: dict[str, _FacilitatorState] = {
            url: _FacilitatorState(url) for url in resolved
        }
        self._order: list[str] = list(resolved)
        self._lock = asyncio.Lock()

    # -- mutations (immutable replace under lock) ---------------------------

    async def report_success(self, url: str) -> None:
        async with self._lock:
            state = self._states.get(url)
            if state is None:
                return
            self._states = {
                **self._states,
                url: state.with_success(time.monotonic()),
            }
        logger.debug("facilitator.success", url=url)

    async def report_failure(self, url: str) -> None:
        async with self._lock:
            state = self._states.get(url)
            if state is None:
                return
            new_state = state.with_failure(time.monotonic())
            self._states = {
                **self._states,
                url: new_state,
            }
        logger.warning(
            "facilitator.failure",
            url=url,
            consecutive_failures=new_state.consecutive_failures,
        )

    # -- selection ----------------------------------------------------------

    async def get_healthy_facilitator(self) -> str:
        """Return the best available facilitator URL.

        Preference order:
        1. First healthy facilitator in configured order.
        2. If all are unhealthy, the one closest to cooldown expiry.
        """
        async with self._lock:
            snapshot = {url: self._states[url] for url in self._order}

        for url in self._order:
            if snapshot[url].is_healthy:
                return url

        # All unhealthy -- pick the one whose cooldown expires soonest.
        logger.warning("facilitator.all_unhealthy", count=len(self._order))
        best_url = self._order[0]
        best_remaining = float("inf")
        now = time.monotonic()
        for url in self._order:
            st = snapshot[url]
            remaining = max(0.0, _COOLDOWN_SECONDS - (now - st.last_failure))
            if remaining < best_remaining:
                best_remaining = remaining
                best_url = url
        return best_url

    # -- introspection ------------------------------------------------------

    async def health_snapshot(self) -> list[FacilitatorStatus]:
        now = time.monotonic()
        async with self._lock:
            states = [self._states[url] for url in self._order]

        result: list[FacilitatorStatus] = []
        for st in states:
            if st.consecutive_failures >= _FAILURE_THRESHOLD:
                elapsed = now - st.last_failure
                circuit = "open" if elapsed < _COOLDOWN_SECONDS else "half-open"
            else:
                circuit = "closed"

            result.append(
                FacilitatorStatus(
                    url=st.url,
                    healthy=st.is_healthy,
                    consecutive_failures=st.consecutive_failures,
                    last_success_ago_s=round(now - st.last_success, 2) if st.last_success else None,
                    last_failure_ago_s=round(now - st.last_failure, 2) if st.last_failure else None,
                    circuit_state=circuit,
                )
            )
        return result

    @property
    def urls(self) -> list[str]:
        return list(self._order)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_pool: FacilitatorPool | None = None
_pool_lock = asyncio.Lock()


async def get_facilitator_pool() -> FacilitatorPool:
    """Return (or create) the process-wide ``FacilitatorPool`` singleton."""
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is not None:
            return _pool
        _pool = FacilitatorPool()
        logger.info(
            "facilitator_pool.initialized",
            urls=_pool.urls,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return _pool


# ---------------------------------------------------------------------------
# Health endpoint (free -- no x402 payment required)
# ---------------------------------------------------------------------------


@router.get("/x402/facilitator-health", response_model=FacilitatorHealthResponse)
async def facilitator_health() -> FacilitatorHealthResponse:
    """Return the health status of all configured x402 facilitators."""
    pool = await get_facilitator_pool()
    statuses = await pool.health_snapshot()
    active: str | None = None
    for s in statuses:
        if s.healthy:
            active = s.url
            break
    return FacilitatorHealthResponse(
        constitutional_hash=CONSTITUTIONAL_HASH,
        facilitators=statuses,
        active_facilitator=active,
    )
