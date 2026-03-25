"""
ACGS-2 Enhanced Agent Bus - PQC Adoption Metrics Tests
Constitutional Hash: 608508a9bd224290

Tests for GET /api/v1/metrics/pqc-adoption endpoint.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

try:
    from enhanced_agent_bus.api.routes.pqc_metrics import (
        _compute_adoption_rate,
        _read_window_counters,
    )
except ImportError:
    from api.routes.pqc_metrics import (  # type: ignore[no-redef]
        _compute_adoption_rate,
        _read_window_counters,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redis_with_counters(pqc: int = 0, classical: int = 0) -> AsyncMock:
    """Build Redis mock returning given counter values for hget."""
    redis = AsyncMock()

    async def _hget(key: str, field: str) -> bytes | None:
        if field == "pqc_verified_count":
            return str(pqc).encode() if pqc else None
        if field == "classical_verified_count":
            return str(classical).encode() if classical else None
        return None

    redis.hget = AsyncMock(side_effect=_hget)
    return redis


# ---------------------------------------------------------------------------
# _compute_adoption_rate tests
# ---------------------------------------------------------------------------


def test_adoption_rate_normal():
    """Normal case: rate = pqc / (pqc + classical)."""
    assert _compute_adoption_rate(80, 20) == pytest.approx(0.8)


def test_adoption_rate_zero_total():
    """No division by zero: returns 0.0 when total is 0."""
    assert _compute_adoption_rate(0, 0) == 0.0


def test_adoption_rate_all_pqc():
    """100% PQC adoption."""
    assert _compute_adoption_rate(100, 0) == 1.0


def test_adoption_rate_all_classical():
    """0% PQC adoption."""
    assert _compute_adoption_rate(0, 50) == 0.0


# ---------------------------------------------------------------------------
# _read_window_counters tests
# ---------------------------------------------------------------------------


async def test_read_window_counters_returns_counts():
    """Reads pqc and classical counters from Redis for a window."""
    redis = _redis_with_counters(pqc=42, classical=8)
    pqc_count, classical_count = await _read_window_counters(redis, "1h")
    assert pqc_count == 42
    assert classical_count == 8


async def test_read_window_counters_missing_keys_default_zero():
    """Missing Redis keys default to 0."""
    redis = _redis_with_counters(pqc=0, classical=0)
    pqc_count, classical_count = await _read_window_counters(redis, "24h")
    assert pqc_count == 0
    assert classical_count == 0


async def test_read_window_counters_redis_failure_returns_zero():
    """Redis failure returns (0, 0) gracefully."""
    redis = AsyncMock()
    redis.hget = AsyncMock(side_effect=ConnectionError("Redis down"))
    pqc_count, classical_count = await _read_window_counters(redis, "7d")
    assert pqc_count == 0
    assert classical_count == 0
