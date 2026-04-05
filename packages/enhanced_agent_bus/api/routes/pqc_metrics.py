"""
ACGS-2 Enhanced Agent Bus - PQC Adoption Metrics Route
Constitutional Hash: 608508a9bd224290

GET /api/v1/metrics/pqc-adoption — returns rolling PQC adoption rate
metrics for 1h, 24h, and 7d windows.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from enhanced_agent_bus.api.api_key_auth import require_api_key
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["pqc-metrics"])

# Redis key patterns (must match pqc_audit.py)
_METRICS_KEY_PREFIX = "pqc:metrics"
_WINDOWS: list[Literal["1h", "24h", "7d"]] = ["1h", "24h", "7d"]
_WINDOW_SECONDS = {"1h": 3600, "24h": 86400, "7d": 604800}


def _bucket_id(window: str) -> str:
    """Compute the current time-bucket identifier for a window."""
    now = int(time.time())
    return str(now // _WINDOW_SECONDS[window])


def _compute_adoption_rate(pqc_count: int, classical_count: int) -> float:
    """Compute PQC adoption rate, returning 0.0 when total is 0."""
    total = pqc_count + classical_count
    if total == 0:
        return 0.0
    return pqc_count / total


async def _read_window_counters(
    redis_client: Any,
    window: str,
) -> tuple[int, int]:
    """Read pqc and classical counters from Redis for a window.

    Returns (pqc_count, classical_count). Defaults to (0, 0) on failure.
    """
    bucket = _bucket_id(window)
    redis_key = f"{_METRICS_KEY_PREFIX}:{window}:{bucket}"
    try:
        raw_pqc = await redis_client.hget(redis_key, "pqc_verified_count")
        raw_classical = await redis_client.hget(redis_key, "classical_verified_count")
        pqc_count = int(raw_pqc) if raw_pqc else 0
        classical_count = int(raw_classical) if raw_classical else 0
        return pqc_count, classical_count
    except Exception as exc:
        logger.warning(
            "Failed to read PQC adoption counters from Redis",
            window=window,
            error=str(exc),
        )
        return 0, 0


def _get_redis_client() -> Any:
    """Dependency stub for Redis client injection.

    In production, this is overridden via app.dependency_overrides.
    """
    return None  # pragma: no cover


@router.get("/metrics/pqc-adoption")
async def get_pqc_adoption_metrics(
    window: str | None = Query(None, description="Filter to a single window: 1h, 24h, or 7d"),
    redis_client: Any = Depends(_get_redis_client),
    _api_key: str = Depends(require_api_key),
) -> dict[str, Any]:
    """Return PQC adoption metrics for rolling time windows."""
    windows_to_query = [window] if window and window in _WINDOWS else list(_WINDOWS)

    results = []
    for w in windows_to_query:
        if redis_client is not None:
            pqc_count, classical_count = await _read_window_counters(redis_client, w)
        else:
            pqc_count, classical_count = 0, 0

        results.append(
            {
                "window": w,
                "pqc_verified_count": pqc_count,
                "classical_verified_count": classical_count,
                "pqc_adoption_rate": _compute_adoption_rate(pqc_count, classical_count),
            }
        )

    return {
        "windows": results,
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


__all__ = [
    "_compute_adoption_rate",
    "_read_window_counters",
    "router",
]
