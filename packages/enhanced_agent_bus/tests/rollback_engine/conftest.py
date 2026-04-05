# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test coverage for constitutional/rollback_engine.py.

Targets ≥95% coverage of all classes, methods, and code paths.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Minimal stub imports before importing the module under test so that all
# optional dependencies resolve without network / real service access.
# ---------------------------------------------------------------------------
# Patch heavy optional deps before module import so try/except blocks pick up
# the stubs at import time.
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


# ── Stub: redis.asyncio ──────────────────────────────────────────────────────
class _FakeRedisClient:
    async def delete(self, key: str) -> int:
        return 1

    async def close(self) -> None:
        pass


class _FakeAioRedis:
    @staticmethod
    async def from_url(*args: Any, **kwargs: Any) -> _FakeRedisClient:
        return _FakeRedisClient()


_redis_asyncio_mod = MagicMock()
_redis_asyncio_mod.from_url = AsyncMock(return_value=_FakeRedisClient())
_redis_mod = MagicMock()
_redis_mod.asyncio = _redis_asyncio_mod
sys.modules.setdefault("redis", _redis_mod)
sys.modules.setdefault("redis.asyncio", _redis_asyncio_mod)

# ── Stub: httpx ──────────────────────────────────────────────────────────────
import httpx

from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.degradation_detector import (
    DegradationReport,
    DegradationSeverity,
    MetricDegradationAnalysis,
    SignificanceLevel,
    TimeWindow,
)
from enhanced_agent_bus.constitutional.rollback_engine import (
    RollbackEngineError,
    RollbackReason,
    RollbackSagaActivities,
    RollbackTriggerConfig,
    create_rollback_saga,
    rollback_amendment,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

# ── Import the module under test ─────────────────────────────────────────────

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_degradation_report(
    severity: DegradationSeverity = DegradationSeverity.NONE,
    confidence: float = 0.5,
    rollback_recommended: bool = False,
) -> DegradationReport:
    """Build a minimal DegradationReport for testing."""
    from enhanced_agent_bus.constitutional.metrics_collector import (
        GovernanceMetricsSnapshot,
    )

    snapshot = GovernanceMetricsSnapshot(
        constitutional_version="1.0.0",
        window_seconds=3600,
        approval_rate=0.9,
        avg_decision_latency_ms=10.0,
        compliance_score=1.0,
        total_messages=100,
        approved_messages=90,
        blocked_messages=10,
        pending_messages=0,
        violation_rate=0.0,
        hitl_trigger_rate=0.0,
        constitutional_hash_validated=True,
    )

    return DegradationReport(
        time_window=TimeWindow.ONE_HOUR,
        baseline_snapshot=snapshot,
        current_snapshot=snapshot,
        overall_severity=severity,
        confidence_score=confidence,
        rollback_recommended=rollback_recommended,
        degradation_summary="test summary",
        statistical_significance=SignificanceLevel.NONE,
    )


def _make_activities(
    hitl_integration: Any = None,
    redis_url: str | None = None,
) -> RollbackSagaActivities:
    """Create a RollbackSagaActivities with mock dependencies."""
    storage = MagicMock()
    metrics_collector = MagicMock()
    degradation_detector = MagicMock()

    activities = RollbackSagaActivities(
        storage=storage,
        metrics_collector=metrics_collector,
        degradation_detector=degradation_detector,
        opa_url="http://localhost:8181",
        audit_service_url="http://localhost:8001",
        redis_url=redis_url or "redis://localhost:6379",
        hitl_integration=hitl_integration,
    )
    return activities


def _make_saga_input(saga_id: str = "saga-001", **context_kwargs: Any) -> dict:
    """Build a minimal saga step input dict."""
    context: dict[str, Any] = {
        "current_version_id": "version-abc123",
        "amendment_id": "amendment-001",
        "time_window": TimeWindow.ONE_HOUR,
        "rollback_reason": RollbackReason.AUTOMATIC_DEGRADATION,
    }
    context.update(context_kwargs)
    return {"saga_id": saga_id, "context": context}


# ---------------------------------------------------------------------------
# RollbackEngineError
# ---------------------------------------------------------------------------
