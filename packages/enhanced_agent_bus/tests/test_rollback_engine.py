"""
Tests for enhanced_agent_bus.constitutional.rollback_engine

Targets the uncovered activity methods on RollbackSagaActivities:
  - initialize / close
  - detect_degradation / log_detection_failure
  - prepare_rollback / cancel_preparation
  - notify_hitl / cancel_hitl_notification
  - update_opa_to_previous / revert_opa_to_current
  - restore_previous_version / revert_version_restoration
  - invalidate_cache / restore_cache
  - audit_rollback / mark_rollback_audit_failed
  - _build_rollback_step / _resolve_rollback_activity_callable / _add_rollback_saga_steps
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from enhanced_agent_bus.constitutional.degradation_detector import (
    DegradationReport,
    DegradationSeverity,
    MetricDegradationAnalysis,
    SignificanceLevel,
    TimeWindow,
)
from enhanced_agent_bus.constitutional.rollback_engine import (
    ROLLBACK_STEP_SPECS,
    RollbackEngineError,
    RollbackReason,
    RollbackSagaActivities,
    RollbackTriggerConfig,
    _add_rollback_saga_steps,
    _build_rollback_step,
    _resolve_rollback_activity_callable,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_activities(
    hitl_integration: Any = None,
    redis_url: str | None = None,
) -> RollbackSagaActivities:
    """Create RollbackSagaActivities with mock dependencies."""
    storage = MagicMock()
    metrics_collector = MagicMock()
    degradation_detector = MagicMock()

    return RollbackSagaActivities(
        storage=storage,
        metrics_collector=metrics_collector,
        degradation_detector=degradation_detector,
        opa_url="http://localhost:8181",
        audit_service_url="http://localhost:8001",
        redis_url=redis_url or "redis://localhost:6379",
        hitl_integration=hitl_integration,
    )


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


# ---------------------------------------------------------------------------
# RollbackSagaActivities.initialize
# ---------------------------------------------------------------------------


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_creates_http_client(self) -> None:
        act = _make_activities()
        assert act._http_client is None

        with (
            patch("enhanced_agent_bus.constitutional.rollback_engine.REDIS_AVAILABLE", False),
            patch("enhanced_agent_bus.constitutional.rollback_engine.OPAClient", None),
            patch("enhanced_agent_bus.constitutional.rollback_engine.AuditClient", None),
        ):
            await act.initialize()

        assert act._http_client is not None
        await act._http_client.aclose()

    @pytest.mark.asyncio
    async def test_initialize_redis_failure_sets_none(self) -> None:
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = AsyncMock(side_effect=RuntimeError("conn refused"))

        act = _make_activities()
        with (
            patch("enhanced_agent_bus.constitutional.rollback_engine.REDIS_AVAILABLE", True),
            patch("enhanced_agent_bus.constitutional.rollback_engine.aioredis", mock_aioredis),
            patch("enhanced_agent_bus.constitutional.rollback_engine.OPAClient", None),
            patch("enhanced_agent_bus.constitutional.rollback_engine.AuditClient", None),
        ):
            await act.initialize()

        assert act._redis_client is None
        await act._http_client.aclose()

    @pytest.mark.asyncio
    async def test_initialize_opa_client_failure_sets_none(self) -> None:
        mock_opa_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.initialize = AsyncMock(side_effect=RuntimeError("opa err"))
        mock_opa_cls.return_value = mock_instance

        act = _make_activities()
        with (
            patch("enhanced_agent_bus.constitutional.rollback_engine.REDIS_AVAILABLE", False),
            patch("enhanced_agent_bus.constitutional.rollback_engine.OPAClient", mock_opa_cls),
            patch("enhanced_agent_bus.constitutional.rollback_engine.AuditClient", None),
        ):
            await act.initialize()

        assert act._opa_client is None
        await act._http_client.aclose()

    @pytest.mark.asyncio
    async def test_initialize_audit_client_failure_sets_none(self) -> None:
        mock_audit_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.start = AsyncMock(side_effect=ValueError("audit err"))
        mock_audit_cls.return_value = mock_instance

        act = _make_activities()
        with (
            patch("enhanced_agent_bus.constitutional.rollback_engine.REDIS_AVAILABLE", False),
            patch("enhanced_agent_bus.constitutional.rollback_engine.OPAClient", None),
            patch("enhanced_agent_bus.constitutional.rollback_engine.AuditClient", mock_audit_cls),
        ):
            await act.initialize()

        assert act._audit_client is None
        await act._http_client.aclose()

    @pytest.mark.asyncio
    async def test_initialize_redis_success(self) -> None:
        mock_redis_client = MagicMock()
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = AsyncMock(return_value=mock_redis_client)

        act = _make_activities()
        with (
            patch("enhanced_agent_bus.constitutional.rollback_engine.REDIS_AVAILABLE", True),
            patch("enhanced_agent_bus.constitutional.rollback_engine.aioredis", mock_aioredis),
            patch("enhanced_agent_bus.constitutional.rollback_engine.OPAClient", None),
            patch("enhanced_agent_bus.constitutional.rollback_engine.AuditClient", None),
        ):
            await act.initialize()

        assert act._redis_client is mock_redis_client
        await act._http_client.aclose()


# ---------------------------------------------------------------------------
# RollbackSagaActivities.close
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_close_all_clients(self) -> None:
        act = _make_activities()
        act._http_client = MagicMock()
        act._http_client.aclose = AsyncMock()
        act._redis_client = MagicMock()
        act._redis_client.aclose = AsyncMock()
        act._opa_client = MagicMock()
        act._opa_client.close = AsyncMock()
        act._audit_client = MagicMock()
        act._audit_client.stop = AsyncMock()

        await act.close()

        act._http_client.aclose.assert_awaited_once()
        act._redis_client.aclose.assert_awaited_once()
        act._opa_client.close.assert_awaited_once()
        act._audit_client.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_with_no_clients(self) -> None:
        act = _make_activities()
        # All clients are None by default
        await act.close()  # Should not raise


# ---------------------------------------------------------------------------
# detect_degradation
# ---------------------------------------------------------------------------


class TestDetectDegradation:
    @pytest.mark.asyncio
    async def test_detect_degradation_with_baseline(self) -> None:
        act = _make_activities()
        report = _make_degradation_report(
            severity=DegradationSeverity.HIGH,
            confidence=0.85,
            rollback_recommended=True,
        )

        baseline_snapshot = MagicMock()
        current_snapshot = MagicMock()

        act.metrics_collector.get_baseline_snapshot = AsyncMock(return_value=baseline_snapshot)
        act.metrics_collector.collect_snapshot = AsyncMock(return_value=current_snapshot)
        act.degradation_detector.analyze_degradation = AsyncMock(return_value=report)

        inp = _make_saga_input()
        result = await act.detect_degradation(inp)

        assert result["severity"] == "high"
        assert result["confidence_score"] == 0.85
        assert result["rollback_recommended"] is True
        assert "detection_id" in result
        assert "timestamp" in result
        act.metrics_collector.get_baseline_snapshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_detect_degradation_no_baseline_falls_back(self) -> None:
        act = _make_activities()
        report = _make_degradation_report()

        current_snapshot = MagicMock()

        act.metrics_collector.get_baseline_snapshot = AsyncMock(return_value=None)
        act.metrics_collector.collect_snapshot = AsyncMock(return_value=current_snapshot)
        act.degradation_detector.analyze_degradation = AsyncMock(return_value=report)

        inp = _make_saga_input()
        result = await act.detect_degradation(inp)

        # collect_snapshot called twice: once for synthetic baseline, once for current
        assert act.metrics_collector.collect_snapshot.await_count == 2
        assert "severity" in result


# ---------------------------------------------------------------------------
# log_detection_failure (compensation)
# ---------------------------------------------------------------------------


class TestLogDetectionFailure:
    @pytest.mark.asyncio
    async def test_returns_true(self) -> None:
        act = _make_activities()
        inp = _make_saga_input()
        result = await act.log_detection_failure(inp)
        assert result is True


# ---------------------------------------------------------------------------
# prepare_rollback
# ---------------------------------------------------------------------------


class TestPrepareRollback:
    @pytest.mark.asyncio
    async def test_prepare_rollback_success(self) -> None:
        act = _make_activities()

        current_version = MagicMock()
        current_version.predecessor_version = "pred-v1"
        current_version.version_id = "version-abc123"
        current_version.version = "1.0.0"

        target_version = MagicMock()
        target_version.version_id = "pred-v1"
        target_version.version = "0.9.0"
        target_version.constitutional_hash = "hash-prev"

        act.storage.get_version = AsyncMock(side_effect=[current_version, target_version])
        act.storage.get_amendment = AsyncMock(return_value=MagicMock())

        inp = _make_saga_input()
        result = await act.prepare_rollback(inp)

        assert result["is_valid"] is True
        assert result["target_version_id"] == "pred-v1"
        assert result["target_hash"] == "hash-prev"

    @pytest.mark.asyncio
    async def test_prepare_rollback_current_not_found(self) -> None:
        act = _make_activities()
        act.storage.get_version = AsyncMock(return_value=None)

        inp = _make_saga_input()
        with pytest.raises(RollbackEngineError, match="not found"):
            await act.prepare_rollback(inp)

    @pytest.mark.asyncio
    async def test_prepare_rollback_no_predecessor(self) -> None:
        act = _make_activities()
        current_version = MagicMock()
        current_version.predecessor_version = None

        act.storage.get_version = AsyncMock(return_value=current_version)

        inp = _make_saga_input()
        with pytest.raises(RollbackEngineError, match="no predecessor"):
            await act.prepare_rollback(inp)

    @pytest.mark.asyncio
    async def test_prepare_rollback_predecessor_not_found(self) -> None:
        act = _make_activities()
        current_version = MagicMock()
        current_version.predecessor_version = "pred-v1"

        act.storage.get_version = AsyncMock(side_effect=[current_version, None])

        inp = _make_saga_input()
        with pytest.raises(RollbackEngineError, match="Predecessor version.*not found"):
            await act.prepare_rollback(inp)

    @pytest.mark.asyncio
    async def test_prepare_rollback_no_amendment_id(self) -> None:
        act = _make_activities()

        current_version = MagicMock()
        current_version.predecessor_version = "pred-v1"
        current_version.version_id = "version-abc123"
        current_version.version = "1.0.0"

        target_version = MagicMock()
        target_version.version_id = "pred-v1"
        target_version.version = "0.9.0"
        target_version.constitutional_hash = "hash-prev"

        act.storage.get_version = AsyncMock(side_effect=[current_version, target_version])

        inp = _make_saga_input(amendment_id=None)
        result = await act.prepare_rollback(inp)

        assert result["amendment_id"] is None
        act.storage.get_amendment.assert_not_called()


# ---------------------------------------------------------------------------
# cancel_preparation (compensation)
# ---------------------------------------------------------------------------


class TestCancelPreparation:
    @pytest.mark.asyncio
    async def test_returns_true(self) -> None:
        act = _make_activities()
        result = await act.cancel_preparation(_make_saga_input())
        assert result is True


# ---------------------------------------------------------------------------
# notify_hitl
# ---------------------------------------------------------------------------


class TestNotifyHITL:
    @pytest.mark.asyncio
    async def test_no_notification_for_low_severity(self) -> None:
        act = _make_activities()
        inp = _make_saga_input(
            detect_degradation={"severity": "low"},
            prepare_rollback={"current_version": "1.0"},
        )
        result = await act.notify_hitl(inp)
        assert result["notifications_sent"] == []

    @pytest.mark.asyncio
    async def test_slack_notification_for_high_severity(self) -> None:
        hitl = MagicMock()
        hitl._send_slack_notification = AsyncMock()
        act = _make_activities(hitl_integration=hitl)

        inp = _make_saga_input(
            detect_degradation={"severity": "high", "degradation_summary": "bad"},
            prepare_rollback={"current_version": "1.0", "target_version": "0.9"},
        )
        result = await act.notify_hitl(inp)

        assert "slack" in result["notifications_sent"]
        hitl._send_slack_notification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pagerduty_for_critical_severity(self) -> None:
        hitl = MagicMock()
        hitl._send_slack_notification = AsyncMock()
        hitl._send_pagerduty_notification = AsyncMock()
        act = _make_activities(hitl_integration=hitl)

        inp = _make_saga_input(
            detect_degradation={"severity": "critical", "degradation_summary": "very bad"},
            prepare_rollback={"current_version": "1.0", "target_version": "0.9"},
        )
        result = await act.notify_hitl(inp)

        assert "slack" in result["notifications_sent"]
        assert "pagerduty" in result["notifications_sent"]

    @pytest.mark.asyncio
    async def test_slack_failure_handled_gracefully(self) -> None:
        hitl = MagicMock()
        hitl._send_slack_notification = AsyncMock(side_effect=RuntimeError("slack down"))
        hitl._send_pagerduty_notification = AsyncMock()
        act = _make_activities(hitl_integration=hitl)

        inp = _make_saga_input(
            detect_degradation={"severity": "critical"},
            prepare_rollback={"current_version": "1.0"},
        )
        result = await act.notify_hitl(inp)

        assert "slack" not in result["notifications_sent"]
        # PagerDuty should still be attempted
        assert "pagerduty" in result["notifications_sent"]

    @pytest.mark.asyncio
    async def test_pagerduty_failure_handled_gracefully(self) -> None:
        hitl = MagicMock()
        hitl._send_slack_notification = AsyncMock()
        hitl._send_pagerduty_notification = AsyncMock(side_effect=ValueError("pd err"))
        act = _make_activities(hitl_integration=hitl)

        inp = _make_saga_input(
            detect_degradation={"severity": "critical"},
            prepare_rollback={"current_version": "1.0"},
        )
        result = await act.notify_hitl(inp)

        assert "slack" in result["notifications_sent"]
        assert "pagerduty" not in result["notifications_sent"]

    @pytest.mark.asyncio
    async def test_no_hitl_integration_skips_notifications(self) -> None:
        act = _make_activities(hitl_integration=None)
        inp = _make_saga_input(
            detect_degradation={"severity": "critical"},
            prepare_rollback={},
        )
        result = await act.notify_hitl(inp)
        assert result["notifications_sent"] == []


# ---------------------------------------------------------------------------
# cancel_hitl_notification (compensation)
# ---------------------------------------------------------------------------


class TestCancelHITLNotification:
    @pytest.mark.asyncio
    async def test_returns_true(self) -> None:
        act = _make_activities()
        result = await act.cancel_hitl_notification(_make_saga_input())
        assert result is True


# ---------------------------------------------------------------------------
# update_opa_to_previous
# ---------------------------------------------------------------------------


class TestUpdateOPAToPrevious:
    @pytest.mark.asyncio
    async def test_success_with_http_client(self) -> None:
        act = _make_activities()
        mock_response = MagicMock()
        mock_response.status_code = 204
        act._http_client = MagicMock()
        act._http_client.put = AsyncMock(return_value=mock_response)

        inp = _make_saga_input(prepare_rollback={"target_hash": "newhash", "target_version": "0.9"})
        result = await act.update_opa_to_previous(inp)

        assert result["updated"] is True
        assert result["previous_hash"] == "newhash"
        act._http_client.put.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_warning_on_non_success_status(self) -> None:
        act = _make_activities()
        mock_response = MagicMock()
        mock_response.status_code = 500
        act._http_client = MagicMock()
        act._http_client.put = AsyncMock(return_value=mock_response)

        inp = _make_saga_input(prepare_rollback={"target_hash": "h", "target_version": "v"})
        result = await act.update_opa_to_previous(inp)

        # Should still return updated=True (non-critical)
        assert result["updated"] is True

    @pytest.mark.asyncio
    async def test_http_error_handled_gracefully(self) -> None:
        act = _make_activities()
        act._http_client = MagicMock()
        act._http_client.put = AsyncMock(side_effect=RuntimeError("timeout"))

        inp = _make_saga_input(prepare_rollback={})
        result = await act.update_opa_to_previous(inp)

        assert result["updated"] is True  # Continues despite error

    @pytest.mark.asyncio
    async def test_no_http_client_skips_update(self) -> None:
        act = _make_activities()
        act._http_client = None

        inp = _make_saga_input(prepare_rollback={})
        result = await act.update_opa_to_previous(inp)

        assert result["updated"] is True


# ---------------------------------------------------------------------------
# revert_opa_to_current (compensation)
# ---------------------------------------------------------------------------


class TestRevertOPAToCurrent:
    @pytest.mark.asyncio
    async def test_no_http_client_returns_true(self) -> None:
        act = _make_activities()
        act._http_client = None

        result = await act.revert_opa_to_current(_make_saga_input())
        assert result is True

    @pytest.mark.asyncio
    async def test_success_status_200(self) -> None:
        act = _make_activities()
        mock_response = MagicMock()
        mock_response.status_code = 200
        act._http_client = MagicMock()
        act._http_client.put = AsyncMock(return_value=mock_response)

        result = await act.revert_opa_to_current(_make_saga_input())
        assert result is True

    @pytest.mark.asyncio
    async def test_failure_status_500(self) -> None:
        act = _make_activities()
        mock_response = MagicMock()
        mock_response.status_code = 500
        act._http_client = MagicMock()
        act._http_client.put = AsyncMock(return_value=mock_response)

        result = await act.revert_opa_to_current(_make_saga_input())
        assert result is False

    @pytest.mark.asyncio
    async def test_http_exception_returns_false(self) -> None:
        act = _make_activities()
        act._http_client = MagicMock()
        act._http_client.put = AsyncMock(side_effect=RuntimeError("err"))

        result = await act.revert_opa_to_current(_make_saga_input())
        assert result is False


# ---------------------------------------------------------------------------
# restore_previous_version
# ---------------------------------------------------------------------------


class TestRestorePreviousVersion:
    @pytest.mark.asyncio
    async def test_restore_with_amendment(self) -> None:
        act = _make_activities()
        act.storage.activate_version = AsyncMock()

        amendment = MagicMock()
        amendment.metadata = {}
        act.storage.get_amendment = AsyncMock(return_value=amendment)
        act.storage.save_amendment = AsyncMock()

        inp = _make_saga_input(
            prepare_rollback={
                "target_version_id": "pred-v1",
                "target_version": "0.9",
                "current_version_id": "version-abc123",
            },
        )
        result = await act.restore_previous_version(inp)

        assert result["restored"] is True
        assert result["amendment_rolled_back"] is True
        act.storage.activate_version.assert_awaited_once_with("pred-v1")
        act.storage.save_amendment.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restore_without_amendment(self) -> None:
        act = _make_activities()
        act.storage.activate_version = AsyncMock()

        inp = _make_saga_input(
            amendment_id=None,
            prepare_rollback={
                "target_version_id": "pred-v1",
                "target_version": "0.9",
                "current_version_id": "version-abc123",
            },
        )
        result = await act.restore_previous_version(inp)

        assert result["restored"] is True
        assert result["amendment_rolled_back"] is False
        act.storage.get_amendment.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_amendment_not_found(self) -> None:
        act = _make_activities()
        act.storage.activate_version = AsyncMock()
        act.storage.get_amendment = AsyncMock(return_value=None)

        inp = _make_saga_input(
            prepare_rollback={
                "target_version_id": "pred-v1",
                "target_version": "0.9",
                "current_version_id": "version-abc123",
            },
        )
        result = await act.restore_previous_version(inp)

        assert result["restored"] is True
        # save_amendment should NOT be called when amendment is None
        act.storage.save_amendment.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_amendment_with_none_metadata(self) -> None:
        act = _make_activities()
        act.storage.activate_version = AsyncMock()

        amendment = MagicMock()
        amendment.metadata = None
        act.storage.get_amendment = AsyncMock(return_value=amendment)
        act.storage.save_amendment = AsyncMock()

        inp = _make_saga_input(
            prepare_rollback={
                "target_version_id": "pred-v1",
                "target_version": "0.9",
                "current_version_id": "version-abc123",
            },
        )
        result = await act.restore_previous_version(inp)

        assert result["restored"] is True
        # metadata should have been set to a dict
        assert amendment.metadata is not None


# ---------------------------------------------------------------------------
# revert_version_restoration (compensation)
# ---------------------------------------------------------------------------


class TestRevertVersionRestoration:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        act = _make_activities()
        act.storage.activate_version = AsyncMock()

        inp = _make_saga_input(prepare_rollback={"current_version_id": "version-abc123"})
        result = await act.revert_version_restoration(inp)

        assert result is True
        act.storage.activate_version.assert_awaited_once_with("version-abc123")

    @pytest.mark.asyncio
    async def test_failure_returns_false(self) -> None:
        act = _make_activities()
        act.storage.activate_version = AsyncMock(side_effect=RuntimeError("db err"))

        inp = _make_saga_input(prepare_rollback={"current_version_id": "version-abc123"})
        result = await act.revert_version_restoration(inp)

        assert result is False


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------


class TestInvalidateCache:
    @pytest.mark.asyncio
    async def test_invalidate_with_redis(self) -> None:
        act = _make_activities()
        act._redis_client = MagicMock()
        act._redis_client.delete = AsyncMock(return_value=1)

        result = await act.invalidate_cache(_make_saga_input())

        assert result["cache_invalidated"] is True
        act._redis_client.delete.assert_awaited_once_with("constitutional:active_version")

    @pytest.mark.asyncio
    async def test_invalidate_without_redis(self) -> None:
        act = _make_activities()
        act._redis_client = None

        result = await act.invalidate_cache(_make_saga_input())

        assert result["cache_invalidated"] is False

    @pytest.mark.asyncio
    async def test_invalidate_redis_error(self) -> None:
        act = _make_activities()
        act._redis_client = MagicMock()
        act._redis_client.delete = AsyncMock(side_effect=RuntimeError("redis err"))

        result = await act.invalidate_cache(_make_saga_input())

        assert result["cache_invalidated"] is False


# ---------------------------------------------------------------------------
# restore_cache (compensation)
# ---------------------------------------------------------------------------


class TestRestoreCache:
    @pytest.mark.asyncio
    async def test_no_redis_returns_true(self) -> None:
        act = _make_activities()
        act._redis_client = None

        result = await act.restore_cache(_make_saga_input())
        assert result is True

    @pytest.mark.asyncio
    async def test_success_returns_true(self) -> None:
        act = _make_activities()
        act._redis_client = MagicMock()
        act._redis_client.delete = AsyncMock(return_value=1)

        result = await act.restore_cache(_make_saga_input())
        assert result is True

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        act = _make_activities()
        act._redis_client = MagicMock()
        act._redis_client.delete = AsyncMock(side_effect=RuntimeError("err"))

        result = await act.restore_cache(_make_saga_input())
        assert result is False


# ---------------------------------------------------------------------------
# audit_rollback
# ---------------------------------------------------------------------------


class TestAuditRollback:
    @pytest.mark.asyncio
    async def test_audit_with_client(self) -> None:
        act = _make_activities()
        act._audit_client = MagicMock()
        act._audit_client.log = AsyncMock()

        inp = _make_saga_input(
            detect_degradation={"severity": "high", "confidence_score": 0.9},
            prepare_rollback={"current_version": "1.0"},
            restore_previous_version={"restored_version": "0.9"},
            notify_hitl={"notifications_sent": ["slack"]},
        )
        result = await act.audit_rollback(inp)

        assert result["event_type"] == "constitutional_version_rolled_back"
        assert "audit_id" in result
        act._audit_client.log.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audit_without_client(self) -> None:
        act = _make_activities()
        act._audit_client = None

        inp = _make_saga_input()
        result = await act.audit_rollback(inp)

        assert result["event_type"] == "constitutional_version_rolled_back"

    @pytest.mark.asyncio
    async def test_audit_client_error_handled(self) -> None:
        act = _make_activities()
        act._audit_client = MagicMock()
        act._audit_client.log = AsyncMock(side_effect=RuntimeError("audit err"))

        inp = _make_saga_input()
        result = await act.audit_rollback(inp)

        # Should not raise, just log warning
        assert result["event_type"] == "constitutional_version_rolled_back"


# ---------------------------------------------------------------------------
# mark_rollback_audit_failed (compensation)
# ---------------------------------------------------------------------------


class TestMarkRollbackAuditFailed:
    @pytest.mark.asyncio
    async def test_with_audit_client(self) -> None:
        act = _make_activities()
        act._audit_client = MagicMock()
        act._audit_client.log = AsyncMock()

        inp = _make_saga_input(audit_rollback={"audit_id": "aud-123"})
        result = await act.mark_rollback_audit_failed(inp)

        assert result is True
        act._audit_client.log.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_without_audit_client(self) -> None:
        act = _make_activities()
        act._audit_client = None

        result = await act.mark_rollback_audit_failed(_make_saga_input())
        assert result is True

    @pytest.mark.asyncio
    async def test_audit_client_error_still_returns_true(self) -> None:
        act = _make_activities()
        act._audit_client = MagicMock()
        act._audit_client.log = AsyncMock(side_effect=ValueError("err"))

        result = await act.mark_rollback_audit_failed(_make_saga_input())
        assert result is True


# ---------------------------------------------------------------------------
# _build_rollback_step
# ---------------------------------------------------------------------------


class TestBuildRollbackStep:
    def test_raises_when_saga_types_unavailable(self) -> None:
        with patch("enhanced_agent_bus.constitutional.rollback_engine.SagaStep", None):
            with pytest.raises(ImportError, match="saga step types not available"):
                _build_rollback_step(
                    name="test",
                    description="test step",
                    execute=AsyncMock(),
                    compensation_name="comp",
                    compensation_description="comp desc",
                    compensation_execute=AsyncMock(),
                    timeout_seconds=30,
                )

    def test_builds_step_when_types_available(self) -> None:
        mock_step = MagicMock()
        mock_comp = MagicMock()

        with (
            patch("enhanced_agent_bus.constitutional.rollback_engine.SagaStep", mock_step),
            patch("enhanced_agent_bus.constitutional.rollback_engine.SagaCompensation", mock_comp),
        ):
            _build_rollback_step(
                name="test",
                description="test step",
                execute=AsyncMock(),
                compensation_name="comp",
                compensation_description="comp desc",
                compensation_execute=AsyncMock(),
                timeout_seconds=30,
                is_optional=True,
            )

        mock_step.assert_called_once()
        mock_comp.assert_called_once()
        call_kwargs = mock_step.call_args[1]
        assert call_kwargs["name"] == "test"
        assert call_kwargs["is_optional"] is True


# ---------------------------------------------------------------------------
# _resolve_rollback_activity_callable
# ---------------------------------------------------------------------------


class TestResolveRollbackActivityCallable:
    def test_resolves_valid_async_method(self) -> None:
        act = _make_activities()
        spec = ROLLBACK_STEP_SPECS[0]  # detect_degradation
        result = _resolve_rollback_activity_callable(act, spec, "detect_degradation")
        assert callable(result)

    def test_raises_for_missing_attr(self) -> None:
        act = _make_activities()
        spec = ROLLBACK_STEP_SPECS[0]
        with pytest.raises(RollbackEngineError, match="missing activity"):
            _resolve_rollback_activity_callable(act, spec, "nonexistent_method")

    def test_raises_for_non_async_callable(self) -> None:
        act = _make_activities()
        act.bad_method = lambda x: x  # sync, not async
        spec = ROLLBACK_STEP_SPECS[0]
        with pytest.raises(RollbackEngineError, match="must be async callable"):
            _resolve_rollback_activity_callable(act, spec, "bad_method")


# ---------------------------------------------------------------------------
# _add_rollback_saga_steps
# ---------------------------------------------------------------------------


class TestAddRollbackSagaSteps:
    def test_adds_all_seven_steps(self) -> None:
        mock_saga = MagicMock()
        mock_saga.add_step = MagicMock()
        act = _make_activities()

        mock_step_cls = MagicMock()
        mock_comp_cls = MagicMock()

        with (
            patch("enhanced_agent_bus.constitutional.rollback_engine.SagaStep", mock_step_cls),
            patch(
                "enhanced_agent_bus.constitutional.rollback_engine.SagaCompensation", mock_comp_cls
            ),
        ):
            _add_rollback_saga_steps(mock_saga, act)

        assert mock_saga.add_step.call_count == 7
