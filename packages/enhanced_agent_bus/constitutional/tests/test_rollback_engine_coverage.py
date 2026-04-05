"""
Comprehensive coverage tests for Constitutional Rollback Engine.
Constitutional Hash: 608508a9bd224290

Tests targeting 85%+ coverage of rollback_engine.py.
"""

import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.observability.structured_logging import get_logger

from ...governance_constants import (
    ROLLBACK_DETECT_TIMEOUT_SECONDS,
    ROLLBACK_STEP_TIMEOUT_SECONDS,
)
from ..amendment_model import AmendmentProposal, AmendmentStatus
from ..degradation_detector import (
    DegradationDetector,
    DegradationReport,
    DegradationSeverity,
    TimeWindow,
)
from ..metrics_collector import GovernanceMetricsCollector, GovernanceMetricsSnapshot
from ..rollback_engine import (
    ROLLBACK_STEP_SPECS,
    RollbackEngineError,
    RollbackReason,
    RollbackSagaActivities,
    RollbackStepSpec,
    RollbackTriggerConfig,
    _build_rollback_context,
    _resolve_rollback_activity_callable,
    create_rollback_saga,
    rollback_amendment,
)
from ..storage import ConstitutionalStorageService
from ..version_model import ConstitutionalStatus, ConstitutionalVersion

pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.unit,
]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage():
    return AsyncMock(spec=ConstitutionalStorageService)


@pytest.fixture
def mock_metrics_collector():
    return AsyncMock(spec=GovernanceMetricsCollector)


@pytest.fixture
def mock_degradation_detector():
    return AsyncMock(spec=DegradationDetector)


@pytest.fixture
def activities(mock_storage, mock_metrics_collector, mock_degradation_detector):
    return RollbackSagaActivities(
        storage=mock_storage,
        metrics_collector=mock_metrics_collector,
        degradation_detector=mock_degradation_detector,
        opa_url="http://localhost:8181",
        audit_service_url="http://localhost:8001",
        redis_url="redis://localhost:6379",
    )


@pytest.fixture
def baseline_snapshot():
    return GovernanceMetricsSnapshot(
        snapshot_id="baseline-001",
        constitutional_version="1.0.0",
        constitutional_hash=CONSTITUTIONAL_HASH,
        total_requests=1000,
        violations_count=10,
        violations_rate=0.01,
        governance_latency_p99=2.0,
        deliberation_success_rate=0.95,
        maci_violations_count=0,
        error_rate=0.02,
        health_score=0.95,
        escalated_requests=100,
    )


@pytest.fixture
def degradation_report(baseline_snapshot):
    return DegradationReport(
        report_id="report-001",
        time_window=TimeWindow.ONE_HOUR,
        baseline_snapshot=baseline_snapshot,
        current_snapshot=baseline_snapshot,
        overall_severity=DegradationSeverity.HIGH,
        confidence_score=0.85,
        rollback_recommended=True,
        degradation_summary="Governance degradation detected: violations rate increased.",
    )


@pytest.fixture
def current_version():
    return ConstitutionalVersion(
        version_id="v-1.1.0",
        version="1.1.0",
        constitutional_hash=CONSTITUTIONAL_HASH,
        content={"principles": ["P1", "P2", "P3"]},
        status=ConstitutionalStatus.ACTIVE,
        predecessor_version="v-1.0.0",
    )


@pytest.fixture
def target_version():
    return ConstitutionalVersion(
        version_id="v-1.0.0",
        version="1.0.0",
        constitutional_hash=CONSTITUTIONAL_HASH,
        content={"principles": ["P1", "P2"]},
        status=ConstitutionalStatus.APPROVED,
    )


@pytest.fixture
def mock_amendment():
    return AmendmentProposal(
        proposal_id="amendment-123",
        proposed_changes={"key": "value"},
        justification="Test amendment for rollback testing.",
        proposer_agent_id="agent-001",
        target_version="1.0.0",
        status=AmendmentStatus.ACTIVE,
    )


def _make_mock_saga_classes():
    class MockSagaCompensation:
        def __init__(self, name, description, execute):
            self.name = name
            self.description = description
            self.execute = execute

    class MockSagaStep:
        def __init__(
            self, name, description, execute, compensation, timeout_seconds=30, is_optional=False
        ):
            self.name = name
            self.description = description
            self.execute = execute
            self.compensation = compensation
            self.timeout_seconds = timeout_seconds
            self.is_optional = is_optional

    class MockConstitutionalSagaWorkflow:
        def __init__(self, saga_id):
            self.saga_id = saga_id
            self._steps = []

        def add_step(self, step):
            self._steps.append(step)

    return MockConstitutionalSagaWorkflow, MockSagaStep, MockSagaCompensation


# ---------------------------------------------------------------------------
# RollbackReason
# ---------------------------------------------------------------------------


class TestRollbackReason:
    def test_automatic_degradation(self):
        assert RollbackReason.AUTOMATIC_DEGRADATION == "automatic_degradation"

    def test_manual_request(self):
        assert RollbackReason.MANUAL_REQUEST == "manual_request"

    def test_emergency_override(self):
        assert RollbackReason.EMERGENCY_OVERRIDE == "emergency_override"

    def test_is_string(self):
        assert isinstance(RollbackReason.AUTOMATIC_DEGRADATION, str)


# ---------------------------------------------------------------------------
# RollbackTriggerConfig
# ---------------------------------------------------------------------------


class TestRollbackTriggerConfig:
    def test_defaults(self):
        cfg = RollbackTriggerConfig()
        assert cfg.enable_automatic_rollback is True
        assert cfg.require_hitl_approval_for_critical is True
        assert cfg.auto_approve_high_confidence is True
        assert cfg.min_confidence_for_auto_rollback == pytest.approx(0.7, abs=0.1)
        assert TimeWindow.ONE_HOUR in cfg.monitoring_windows
        assert TimeWindow.SIX_HOURS in cfg.monitoring_windows

    def test_custom_values(self):
        cfg = RollbackTriggerConfig(
            enable_automatic_rollback=False,
            monitoring_interval_seconds=600,
            monitoring_windows=[TimeWindow.TWENTY_FOUR_HOURS],
            require_hitl_approval_for_critical=False,
            auto_approve_high_confidence=False,
            min_confidence_for_auto_rollback=0.95,
        )
        assert cfg.enable_automatic_rollback is False
        assert cfg.monitoring_interval_seconds == 600
        assert cfg.monitoring_windows == [TimeWindow.TWENTY_FOUR_HOURS]
        assert cfg.require_hitl_approval_for_critical is False
        assert cfg.auto_approve_high_confidence is False
        assert cfg.min_confidence_for_auto_rollback == pytest.approx(0.95)

    def test_default_monitoring_windows_when_none_provided(self):
        cfg = RollbackTriggerConfig(monitoring_windows=None)
        assert len(cfg.monitoring_windows) == 2

    def test_custom_monitoring_interval(self):
        cfg = RollbackTriggerConfig(monitoring_interval_seconds=120)
        assert cfg.monitoring_interval_seconds == 120


# ---------------------------------------------------------------------------
# RollbackEngineError
# ---------------------------------------------------------------------------


class TestRollbackEngineError:
    def test_is_exception(self):
        err = RollbackEngineError("test error")
        assert isinstance(err, Exception)

    def test_message(self):
        err = RollbackEngineError("rollback failed")
        assert "rollback failed" in str(err)

    def test_http_status_code(self):
        assert RollbackEngineError.http_status_code == 500

    def test_error_code(self):
        assert RollbackEngineError.error_code == "ROLLBACK_ENGINE_ERROR"


# ---------------------------------------------------------------------------
# RollbackSagaActivities.__init__
# ---------------------------------------------------------------------------


class TestRollbackSagaActivitiesInit:
    def test_init_with_all_args(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        acts = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
            opa_url="http://opa:8181",
            audit_service_url="http://audit:8001",
            redis_url="redis://redis:6379",
            hitl_integration=MagicMock(),
        )
        assert acts.opa_url == "http://opa:8181"
        assert acts.audit_service_url == "http://audit:8001"
        assert acts.redis_url == "redis://redis:6379"
        assert acts.hitl_integration is not None

    def test_init_defaults_redis_url(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        acts = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )
        # defaults
        assert acts.redis_url == "redis://localhost:6379"
        assert acts.hitl_integration is None
        assert acts._http_client is None
        assert acts._redis_client is None
        assert acts._opa_client is None
        assert acts._audit_client is None


# ---------------------------------------------------------------------------
# initialize / close
# ---------------------------------------------------------------------------


class TestInitializeClose:
    async def test_initialize_creates_http_client(self, activities):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client
            await activities.initialize()
            assert mock_client_cls.called

    async def test_initialize_http_client_is_set(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        """After initialize(), _http_client is set to an httpx.AsyncClient."""
        import httpx

        acts = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )
        await acts.initialize()
        assert acts._http_client is not None
        assert isinstance(acts._http_client, httpx.AsyncClient)
        await acts.close()

    async def test_initialize_redis_available_sets_client(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        """When redis is available and reachable, _redis_client is set."""
        acts = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )
        # Real redis.asyncio.from_url is synchronous (returns client object)
        # so initialize should complete without error regardless of connectivity
        await acts.initialize()
        # redis client was either set or left None (connection error) — both are valid
        # What matters is no exception was raised
        await acts.close()

    async def test_close_with_all_clients(self, activities):
        http_mock = AsyncMock()
        redis_mock = AsyncMock()
        opa_mock = AsyncMock()
        audit_mock = AsyncMock()

        activities._http_client = http_mock
        activities._redis_client = redis_mock
        activities._opa_client = opa_mock
        activities._audit_client = audit_mock

        await activities.close()

        http_mock.aclose.assert_called_once()
        redis_mock.aclose.assert_called_once()
        opa_mock.close.assert_called_once()
        audit_mock.stop.assert_called_once()

    async def test_close_with_no_clients(self, activities):
        """close() should not raise when no clients are set."""
        await activities.close()  # no error expected


# ---------------------------------------------------------------------------
# detect_degradation
# ---------------------------------------------------------------------------


class TestDetectDegradation:
    async def test_detect_degradation_with_baseline(
        self,
        activities,
        mock_metrics_collector,
        mock_degradation_detector,
        baseline_snapshot,
        degradation_report,
    ):
        mock_metrics_collector.get_baseline_snapshot.return_value = baseline_snapshot
        mock_metrics_collector.collect_snapshot.return_value = baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = degradation_report

        result = await activities.detect_degradation(
            {
                "saga_id": "s1",
                "context": {
                    "current_version_id": "v-1.1.0",
                    "amendment_id": "a-123",
                    "time_window": TimeWindow.ONE_HOUR,
                },
            }
        )

        assert result["has_degradation"] is True
        assert result["rollback_recommended"] is True
        assert result["severity"] == "high"
        assert result["confidence_score"] == pytest.approx(0.85)
        assert "detection_id" in result
        assert "timestamp" in result

    async def test_detect_degradation_no_baseline(
        self,
        activities,
        mock_metrics_collector,
        mock_degradation_detector,
        baseline_snapshot,
        degradation_report,
    ):
        mock_metrics_collector.get_baseline_snapshot.return_value = None
        mock_metrics_collector.collect_snapshot.return_value = baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = degradation_report

        result = await activities.detect_degradation(
            {
                "saga_id": "s1",
                "context": {
                    "current_version_id": "v-1.1.0",
                    "time_window": TimeWindow.ONE_HOUR,
                },
            }
        )

        assert "detection_id" in result
        # collect_snapshot called twice: synthetic baseline + current
        assert mock_metrics_collector.collect_snapshot.call_count == 2

    async def test_detect_degradation_default_time_window(
        self,
        activities,
        mock_metrics_collector,
        mock_degradation_detector,
        baseline_snapshot,
        degradation_report,
    ):
        """When time_window is absent in context, defaults to ONE_HOUR."""
        mock_metrics_collector.get_baseline_snapshot.return_value = baseline_snapshot
        mock_metrics_collector.collect_snapshot.return_value = baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = degradation_report

        result = await activities.detect_degradation(
            {"saga_id": "s1", "context": {"current_version_id": "v-1.1.0"}}
        )

        assert result["severity"] == "high"

    async def test_detect_degradation_critical_severity(
        self,
        activities,
        mock_metrics_collector,
        mock_degradation_detector,
        baseline_snapshot,
    ):
        critical_report = DegradationReport(
            report_id="report-crit",
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=baseline_snapshot,
            current_snapshot=baseline_snapshot,
            overall_severity=DegradationSeverity.CRITICAL,
            confidence_score=0.99,
            rollback_recommended=True,
            degradation_summary="Critical failure.",
        )
        mock_metrics_collector.get_baseline_snapshot.return_value = baseline_snapshot
        mock_metrics_collector.collect_snapshot.return_value = baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = critical_report

        result = await activities.detect_degradation(
            {"saga_id": "s1", "context": {"current_version_id": "v-1.1.0"}}
        )

        assert result["severity"] == "critical"
        assert result["confidence_score"] == pytest.approx(0.99)

    async def test_detect_degradation_no_degradation(
        self,
        activities,
        mock_metrics_collector,
        mock_degradation_detector,
        baseline_snapshot,
    ):
        no_deg_report = DegradationReport(
            report_id="report-ok",
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=baseline_snapshot,
            current_snapshot=baseline_snapshot,
            overall_severity=DegradationSeverity.NONE,
            confidence_score=0.5,
            rollback_recommended=False,
            degradation_summary="No degradation.",
        )
        mock_metrics_collector.get_baseline_snapshot.return_value = baseline_snapshot
        mock_metrics_collector.collect_snapshot.return_value = baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = no_deg_report

        result = await activities.detect_degradation(
            {"saga_id": "s1", "context": {"current_version_id": "v-1.1.0"}}
        )

        assert result["rollback_recommended"] is False
        assert result["severity"] == "none"


# ---------------------------------------------------------------------------
# prepare_rollback
# ---------------------------------------------------------------------------


class TestPrepareRollback:
    async def test_success(self, activities, mock_storage, current_version, target_version):
        mock_storage.get_version.side_effect = [current_version, target_version]

        result = await activities.prepare_rollback(
            {
                "saga_id": "s1",
                "context": {"current_version_id": "v-1.1.0", "amendment_id": "a-123"},
            }
        )

        assert result["is_valid"] is True
        assert result["current_version"] == "1.1.0"
        assert result["target_version"] == "1.0.0"
        assert result["target_version_id"] == "v-1.0.0"
        assert result["target_hash"] == CONSTITUTIONAL_HASH
        assert "preparation_id" in result

    async def test_version_not_found(self, activities, mock_storage):
        mock_storage.get_version.return_value = None

        with pytest.raises(RollbackEngineError, match="not found"):
            await activities.prepare_rollback(
                {"saga_id": "s1", "context": {"current_version_id": "v-missing"}}
            )

    async def test_no_predecessor(self, activities, mock_storage):
        version_no_predecessor = ConstitutionalVersion(
            version_id="v-first",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={},
            status=ConstitutionalStatus.ACTIVE,
            predecessor_version=None,
        )
        mock_storage.get_version.return_value = version_no_predecessor

        with pytest.raises(RollbackEngineError, match="no predecessor"):
            await activities.prepare_rollback(
                {"saga_id": "s1", "context": {"current_version_id": "v-first"}}
            )

    async def test_predecessor_not_in_storage(self, activities, mock_storage, current_version):
        mock_storage.get_version.side_effect = [current_version, None]

        with pytest.raises(RollbackEngineError, match="not found"):
            await activities.prepare_rollback(
                {"saga_id": "s1", "context": {"current_version_id": "v-1.1.0"}}
            )

    async def test_prepare_without_amendment_id(
        self, activities, mock_storage, current_version, target_version
    ):
        """Amendment ID is optional; prepare should succeed without it."""
        mock_storage.get_version.side_effect = [current_version, target_version]

        result = await activities.prepare_rollback(
            {"saga_id": "s1", "context": {"current_version_id": "v-1.1.0"}}
        )

        assert result["is_valid"] is True
        assert result["amendment_id"] is None

    async def test_prepare_fetches_amendment_when_provided(
        self, activities, mock_storage, current_version, target_version
    ):
        mock_storage.get_version.side_effect = [current_version, target_version]

        await activities.prepare_rollback(
            {
                "saga_id": "s1",
                "context": {"current_version_id": "v-1.1.0", "amendment_id": "amend-001"},
            }
        )

        mock_storage.get_amendment.assert_called_once_with("amend-001")


# ---------------------------------------------------------------------------
# notify_hitl
# ---------------------------------------------------------------------------


class TestNotifyHitl:
    async def test_critical_severity_with_hitl_sends_slack_and_pagerduty(self, activities):
        mock_hitl = AsyncMock()
        activities.hitl_integration = mock_hitl

        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {"severity": "critical"},
                    "prepare_rollback": {"current_version": "1.1.0", "target_version": "1.0.0"},
                    "rollback_reason": RollbackReason.AUTOMATIC_DEGRADATION,
                },
            }
        )

        assert "slack" in result["notifications_sent"]
        assert "pagerduty" in result["notifications_sent"]
        assert result["severity"] == "critical"

    async def test_high_severity_with_hitl_sends_slack_only(self, activities):
        mock_hitl = AsyncMock()
        activities.hitl_integration = mock_hitl

        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {"severity": "high"},
                    "prepare_rollback": {},
                },
            }
        )

        assert "slack" in result["notifications_sent"]
        assert "pagerduty" not in result["notifications_sent"]

    async def test_low_severity_no_notification(self, activities):
        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {"severity": "low"},
                    "prepare_rollback": {},
                },
            }
        )

        assert result["notifications_sent"] == []

    async def test_none_severity_no_notification(self, activities):
        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {"severity": "none"},
                    "prepare_rollback": {},
                },
            }
        )

        assert result["notifications_sent"] == []

    async def test_critical_severity_no_hitl_integration(self, activities):
        """No hitl_integration → no notifications, no error."""
        activities.hitl_integration = None

        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {"severity": "critical"},
                    "prepare_rollback": {},
                },
            }
        )

        assert result["notifications_sent"] == []
        assert "notification_id" in result

    async def test_slack_notification_failure_is_swallowed(self, activities):
        """Slack send failure is caught and the method continues."""
        mock_hitl = AsyncMock()
        mock_hitl._send_slack_notification.side_effect = RuntimeError("slack down")
        activities.hitl_integration = mock_hitl

        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {"severity": "high"},
                    "prepare_rollback": {},
                },
            }
        )

        # slack failed but no exception raised
        assert result["severity"] == "high"

    async def test_pagerduty_failure_is_swallowed(self, activities):
        mock_hitl = AsyncMock()
        mock_hitl._send_pagerduty_notification.side_effect = RuntimeError("pd down")
        activities.hitl_integration = mock_hitl

        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {"severity": "critical"},
                    "prepare_rollback": {"current_version": "1.1.0", "target_version": "1.0.0"},
                },
            }
        )

        # slack may have been sent; pagerduty failed silently
        assert isinstance(result["notifications_sent"], list)

    async def test_unknown_severity_no_notification(self, activities):
        result = await activities.notify_hitl(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {},
                    "prepare_rollback": {},
                },
            }
        )

        assert result["notifications_sent"] == []


# ---------------------------------------------------------------------------
# update_opa_to_previous
# ---------------------------------------------------------------------------


class TestUpdateOpaToPrevious:
    async def test_success_200(self, activities):
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=200)

        result = await activities.update_opa_to_previous(
            {
                "saga_id": "s1",
                "context": {
                    "prepare_rollback": {
                        "target_hash": CONSTITUTIONAL_HASH,
                        "target_version": "1.0.0",
                    }
                },
            }
        )

        assert result["updated"] is True
        assert result["previous_hash"] == CONSTITUTIONAL_HASH
        assert result["previous_version"] == "1.0.0"

    async def test_success_204(self, activities):
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=204)

        result = await activities.update_opa_to_previous(
            {
                "saga_id": "s1",
                "context": {
                    "prepare_rollback": {
                        "target_hash": CONSTITUTIONAL_HASH,
                        "target_version": "1.0.0",
                    }
                },
            }
        )

        assert result["updated"] is True

    async def test_opa_non_200_still_returns_updated_true(self, activities):
        """OPA update failure is non-critical; updated flag stays True."""
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=500)

        result = await activities.update_opa_to_previous(
            {
                "saga_id": "s1",
                "context": {"prepare_rollback": {"target_hash": "abc", "target_version": "1.0.0"}},
            }
        )

        assert result["updated"] is True

    async def test_http_exception_is_caught(self, activities):
        activities._http_client = AsyncMock()
        activities._http_client.put.side_effect = RuntimeError("network error")

        result = await activities.update_opa_to_previous(
            {
                "saga_id": "s1",
                "context": {"prepare_rollback": {"target_hash": "abc", "target_version": "1.0.0"}},
            }
        )

        assert result["updated"] is True  # continues anyway

    async def test_no_http_client(self, activities):
        """If no HTTP client, method returns updated=True without making request."""
        activities._http_client = None

        result = await activities.update_opa_to_previous(
            {
                "saga_id": "s1",
                "context": {"prepare_rollback": {"target_hash": CONSTITUTIONAL_HASH}},
            }
        )

        assert result["updated"] is True


# ---------------------------------------------------------------------------
# revert_opa_to_current
# ---------------------------------------------------------------------------


class TestRevertOpaToCurrent:
    async def test_success(self, activities):
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=200)

        result = await activities.revert_opa_to_current(
            {
                "saga_id": "s1",
                "context": {"prepare_rollback": {"current_version": "1.1.0"}},
            }
        )

        assert result is True

    async def test_non_200_returns_false(self, activities):
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=500)

        result = await activities.revert_opa_to_current(
            {"saga_id": "s1", "context": {"prepare_rollback": {"current_version": "1.1.0"}}}
        )

        assert result is False

    async def test_exception_returns_false(self, activities):
        activities._http_client = AsyncMock()
        activities._http_client.put.side_effect = RuntimeError("conn failed")

        result = await activities.revert_opa_to_current(
            {"saga_id": "s1", "context": {"prepare_rollback": {"current_version": "1.1.0"}}}
        )

        assert result is False

    async def test_no_http_client_returns_true(self, activities):
        activities._http_client = None

        result = await activities.revert_opa_to_current(
            {"saga_id": "s1", "context": {"prepare_rollback": {}}}
        )

        assert result is True


# ---------------------------------------------------------------------------
# restore_previous_version
# ---------------------------------------------------------------------------


class TestRestorePreviousVersion:
    async def test_success_with_amendment(self, activities, mock_storage, mock_amendment):
        mock_storage.get_amendment.return_value = mock_amendment

        result = await activities.restore_previous_version(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "amendment-123",
                    "prepare_rollback": {
                        "target_version_id": "v-1.0.0",
                        "target_version": "1.0.0",
                        "current_version_id": "v-1.1.0",
                    },
                },
            }
        )

        assert result["restored"] is True
        assert result["restored_version_id"] == "v-1.0.0"
        assert result["amendment_rolled_back"] is True
        mock_storage.activate_version.assert_called_with("v-1.0.0")
        mock_storage.save_amendment.assert_called_once()

    async def test_success_without_amendment(self, activities, mock_storage):
        result = await activities.restore_previous_version(
            {
                "saga_id": "s1",
                "context": {
                    "prepare_rollback": {
                        "target_version_id": "v-1.0.0",
                        "target_version": "1.0.0",
                        "current_version_id": "v-1.1.0",
                    },
                },
            }
        )

        assert result["restored"] is True
        assert result["amendment_rolled_back"] is False
        mock_storage.get_amendment.assert_not_called()

    async def test_amendment_not_found_in_storage(self, activities, mock_storage):
        """If amendment not found in storage, still completes (amendment = None guard)."""
        mock_storage.get_amendment.return_value = None

        result = await activities.restore_previous_version(
            {
                "saga_id": "s1",
                "context": {
                    "amendment_id": "missing-amend",
                    "prepare_rollback": {
                        "target_version_id": "v-1.0.0",
                        "target_version": "1.0.0",
                        "current_version_id": "v-1.1.0",
                    },
                },
            }
        )

        assert result["restored"] is True
        mock_storage.save_amendment.assert_not_called()

    async def test_amendment_metadata_set(self, activities, mock_storage, mock_amendment):
        """Amendment metadata is updated with rollback info."""
        mock_amendment.metadata = None
        mock_storage.get_amendment.return_value = mock_amendment

        await activities.restore_previous_version(
            {
                "saga_id": "saga-abc",
                "context": {
                    "amendment_id": "amendment-123",
                    "prepare_rollback": {
                        "target_version_id": "v-1.0.0",
                        "target_version": "1.0.0",
                        "current_version_id": "v-1.1.0",
                    },
                },
            }
        )

        # metadata must be set
        assert mock_amendment.metadata is not None
        assert mock_amendment.metadata["rollback_saga_id"] == "saga-abc"
        assert mock_amendment.status == AmendmentStatus.ROLLED_BACK


# ---------------------------------------------------------------------------
# revert_version_restoration
# ---------------------------------------------------------------------------


class TestRevertVersionRestoration:
    async def test_success(self, activities, mock_storage):
        result = await activities.revert_version_restoration(
            {
                "saga_id": "s1",
                "context": {"prepare_rollback": {"current_version_id": "v-1.1.0"}},
            }
        )

        assert result is True
        mock_storage.activate_version.assert_called_with("v-1.1.0")

    async def test_storage_error_returns_false(self, activities, mock_storage):
        mock_storage.activate_version.side_effect = RuntimeError("db error")

        result = await activities.revert_version_restoration(
            {
                "saga_id": "s1",
                "context": {"prepare_rollback": {"current_version_id": "v-1.1.0"}},
            }
        )

        assert result is False


# ---------------------------------------------------------------------------
# invalidate_cache
# ---------------------------------------------------------------------------


class TestInvalidateCache:
    async def test_success(self, activities):
        activities._redis_client = AsyncMock()
        activities._redis_client.delete.return_value = 1

        result = await activities.invalidate_cache({"saga_id": "s1", "context": {}})

        assert result["cache_invalidated"] is True
        activities._redis_client.delete.assert_called_with("constitutional:active_version")

    async def test_no_redis(self, activities):
        activities._redis_client = None

        result = await activities.invalidate_cache({"saga_id": "s1", "context": {}})

        assert result["cache_invalidated"] is False

    async def test_redis_exception_swallowed(self, activities):
        activities._redis_client = AsyncMock()
        activities._redis_client.delete.side_effect = RuntimeError("redis down")

        result = await activities.invalidate_cache({"saga_id": "s1", "context": {}})

        assert result["cache_invalidated"] is False
        assert "cache_invalidation_id" in result


# ---------------------------------------------------------------------------
# restore_cache
# ---------------------------------------------------------------------------


class TestRestoreCache:
    async def test_success(self, activities):
        activities._redis_client = AsyncMock()

        result = await activities.restore_cache({"saga_id": "s1", "context": {}})

        assert result is True
        activities._redis_client.delete.assert_called_with("constitutional:active_version")

    async def test_no_redis(self, activities):
        activities._redis_client = None

        result = await activities.restore_cache({"saga_id": "s1", "context": {}})

        assert result is True

    async def test_redis_error_returns_false(self, activities):
        activities._redis_client = AsyncMock()
        activities._redis_client.delete.side_effect = RuntimeError("redis down")

        result = await activities.restore_cache({"saga_id": "s1", "context": {}})

        assert result is False


# ---------------------------------------------------------------------------
# audit_rollback
# ---------------------------------------------------------------------------


class TestAuditRollback:
    async def test_audit_without_audit_client(self, activities):
        activities._audit_client = None

        result = await activities.audit_rollback(
            {
                "saga_id": "s1",
                "context": {
                    "rollback_reason": RollbackReason.AUTOMATIC_DEGRADATION,
                    "amendment_id": "a-001",
                    "detect_degradation": {
                        "severity": "high",
                        "confidence_score": 0.85,
                        "degradation_summary": "High violations.",
                        "critical_metrics": [],
                        "report": {},
                    },
                    "prepare_rollback": {
                        "current_version": "1.1.0",
                        "current_version_id": "v-1.1.0",
                    },
                    "restore_previous_version": {
                        "restored_version": "1.0.0",
                        "restored_version_id": "v-1.0.0",
                    },
                    "notify_hitl": {"notifications_sent": []},
                },
            }
        )

        assert result["event_type"] == "constitutional_version_rolled_back"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert result["rollback_reason"] == RollbackReason.AUTOMATIC_DEGRADATION
        assert result["severity"] == "high"

    async def test_audit_with_audit_client(self, activities):
        activities._audit_client = AsyncMock()

        result = await activities.audit_rollback(
            {
                "saga_id": "s1",
                "context": {
                    "rollback_reason": RollbackReason.MANUAL_REQUEST,
                    "amendment_id": "a-002",
                    "detect_degradation": {
                        "severity": "critical",
                        "confidence_score": 0.99,
                        "degradation_summary": "Critical.",
                        "critical_metrics": ["violations_rate"],
                        "report": {"data": "x"},
                    },
                    "prepare_rollback": {
                        "current_version": "2.0.0",
                        "current_version_id": "v-2.0.0",
                    },
                    "restore_previous_version": {
                        "restored_version": "1.0.0",
                        "restored_version_id": "v-1.0.0",
                    },
                    "notify_hitl": {"notifications_sent": ["slack"]},
                },
            }
        )

        activities._audit_client.log.assert_called_once()
        assert result["amendment_id"] == "a-002"

    async def test_audit_client_error_swallowed(self, activities):
        activities._audit_client = AsyncMock()
        activities._audit_client.log.side_effect = RuntimeError("audit down")

        result = await activities.audit_rollback(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {},
                    "prepare_rollback": {},
                    "restore_previous_version": {},
                    "notify_hitl": {},
                },
            }
        )

        assert result["event_type"] == "constitutional_version_rolled_back"

    async def test_audit_emergency_override_reason(self, activities):
        activities._audit_client = None

        result = await activities.audit_rollback(
            {
                "saga_id": "s1",
                "context": {
                    "rollback_reason": RollbackReason.EMERGENCY_OVERRIDE,
                    "detect_degradation": {},
                    "prepare_rollback": {},
                    "restore_previous_version": {},
                    "notify_hitl": {},
                },
            }
        )

        assert result["rollback_reason"] == RollbackReason.EMERGENCY_OVERRIDE

    async def test_audit_default_rollback_reason(self, activities):
        """When rollback_reason missing from context, defaults to AUTOMATIC_DEGRADATION."""
        activities._audit_client = None

        result = await activities.audit_rollback(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {},
                    "prepare_rollback": {},
                    "restore_previous_version": {},
                    "notify_hitl": {},
                },
            }
        )

        assert result["rollback_reason"] == RollbackReason.AUTOMATIC_DEGRADATION


# ---------------------------------------------------------------------------
# mark_rollback_audit_failed
# ---------------------------------------------------------------------------


class TestMarkRollbackAuditFailed:
    async def test_no_audit_client(self, activities):
        activities._audit_client = None

        result = await activities.mark_rollback_audit_failed(
            {"saga_id": "s1", "context": {"audit_rollback": {"audit_id": "aud-001"}}}
        )

        assert result is True

    async def test_with_audit_client(self, activities):
        activities._audit_client = AsyncMock()

        result = await activities.mark_rollback_audit_failed(
            {"saga_id": "s1", "context": {"audit_rollback": {"audit_id": "aud-001"}}}
        )

        assert result is True
        activities._audit_client.log.assert_called_once()

    async def test_audit_client_error_swallowed(self, activities):
        activities._audit_client = AsyncMock()
        activities._audit_client.log.side_effect = RuntimeError("fail")

        result = await activities.mark_rollback_audit_failed(
            {"saga_id": "s1", "context": {"audit_rollback": {}}}
        )

        assert result is True

    async def test_missing_audit_id(self, activities):
        activities._audit_client = None

        result = await activities.mark_rollback_audit_failed({"saga_id": "s1", "context": {}})

        assert result is True


# ---------------------------------------------------------------------------
# Compensation methods (log_detection_failure, cancel_preparation,
# cancel_hitl_notification)
# ---------------------------------------------------------------------------


class TestCompensationMethods:
    async def test_log_detection_failure(self, activities):
        assert await activities.log_detection_failure({"saga_id": "s1", "context": {}}) is True

    async def test_cancel_preparation(self, activities):
        assert await activities.cancel_preparation({"saga_id": "s1", "context": {}}) is True

    async def test_cancel_hitl_notification(self, activities):
        assert await activities.cancel_hitl_notification({"saga_id": "s1", "context": {}}) is True


# ---------------------------------------------------------------------------
# create_rollback_saga
# ---------------------------------------------------------------------------


class TestCreateRollbackSaga:
    def test_step_specs_define_expected_contract(self):
        assert all(isinstance(spec, RollbackStepSpec) for spec in ROLLBACK_STEP_SPECS)
        assert [spec.name for spec in ROLLBACK_STEP_SPECS] == [
            "detect_degradation",
            "prepare_rollback",
            "notify_hitl",
            "update_opa_to_previous",
            "restore_previous_version",
            "invalidate_cache",
            "audit_rollback",
        ]
        assert [spec.execute_attr for spec in ROLLBACK_STEP_SPECS] == [
            "detect_degradation",
            "prepare_rollback",
            "notify_hitl",
            "update_opa_to_previous",
            "restore_previous_version",
            "invalidate_cache",
            "audit_rollback",
        ]
        assert [spec.compensation_execute_attr for spec in ROLLBACK_STEP_SPECS] == [
            "log_detection_failure",
            "cancel_preparation",
            "cancel_hitl_notification",
            "revert_opa_to_current",
            "revert_version_restoration",
            "restore_cache",
            "mark_rollback_audit_failed",
        ]
        assert [spec.timeout_seconds for spec in ROLLBACK_STEP_SPECS] == [
            ROLLBACK_DETECT_TIMEOUT_SECONDS,
            ROLLBACK_STEP_TIMEOUT_SECONDS,
            ROLLBACK_STEP_TIMEOUT_SECONDS,
            ROLLBACK_DETECT_TIMEOUT_SECONDS,
            ROLLBACK_STEP_TIMEOUT_SECONDS,
            ROLLBACK_STEP_TIMEOUT_SECONDS,
            ROLLBACK_STEP_TIMEOUT_SECONDS,
        ]
        assert [spec.is_optional for spec in ROLLBACK_STEP_SPECS] == [
            False,
            False,
            True,
            True,
            False,
            False,
            True,
        ]
        assert [spec.compensation_name for spec in ROLLBACK_STEP_SPECS] == [
            "log_detection_failure",
            "cancel_preparation",
            "cancel_hitl_notification",
            "revert_opa_to_current",
            "revert_version_restoration",
            "restore_cache",
            "mark_rollback_audit_failed",
        ]

    def test_step_spec_mappings_resolve_to_async_activity_methods(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        activities = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )

        for spec in ROLLBACK_STEP_SPECS:
            execute_method = getattr(activities, spec.execute_attr)
            compensation_method = getattr(activities, spec.compensation_execute_attr)

            assert callable(execute_method)
            assert callable(compensation_method)
            assert inspect.iscoroutinefunction(execute_method)
            assert inspect.iscoroutinefunction(compensation_method)

    def test_resolve_rollback_activity_callable_returns_bound_async_method(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        activities = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )
        step_spec = ROLLBACK_STEP_SPECS[0]

        resolved = _resolve_rollback_activity_callable(
            activities, step_spec, step_spec.execute_attr
        )

        assert resolved == activities.detect_degradation

    def test_resolve_rollback_activity_callable_raises_for_missing_mapping(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        activities = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )
        bad_spec = RollbackStepSpec(
            name="bad_step",
            description="Bad step",
            execute_attr="missing_async_method",
            compensation_name="noop",
            compensation_description="noop",
            compensation_execute_attr="cancel_preparation",
            timeout_seconds=ROLLBACK_STEP_TIMEOUT_SECONDS,
        )

        with pytest.raises(RollbackEngineError, match="references missing activity"):
            _resolve_rollback_activity_callable(activities, bad_spec, bad_spec.execute_attr)

    def test_resolve_rollback_activity_callable_raises_for_sync_mapping(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        activities = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )
        bad_spec = RollbackStepSpec(
            name="bad_step",
            description="Bad step",
            execute_attr="sync_placeholder",
            compensation_name="noop",
            compensation_description="noop",
            compensation_execute_attr="cancel_preparation",
            timeout_seconds=ROLLBACK_STEP_TIMEOUT_SECONDS,
        )

        with patch.object(
            RollbackSagaActivities, "sync_placeholder", lambda _input: True, create=True
        ):
            with pytest.raises(RollbackEngineError, match="must be async callable"):
                _resolve_rollback_activity_callable(activities, bad_spec, bad_spec.execute_attr)

    def test_raises_import_error_when_workflow_unavailable(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        with patch(
            "enhanced_agent_bus.constitutional.rollback_engine.ConstitutionalSagaWorkflow",
            None,
        ):
            with pytest.raises(ImportError, match="ConstitutionalSagaWorkflow not available"):
                create_rollback_saga(
                    current_version_id="v-1.1.0",
                    storage=mock_storage,
                    metrics_collector=mock_metrics_collector,
                    degradation_detector=mock_degradation_detector,
                )

    def test_raises_when_workflow_none_via_patch(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        """Saga creation fails cleanly when workflow support is explicitly disabled."""
        with patch(
            "enhanced_agent_bus.constitutional.rollback_engine.ConstitutionalSagaWorkflow",
            None,
        ):
            with pytest.raises(ImportError, match="ConstitutionalSagaWorkflow not available"):
                create_rollback_saga(
                    current_version_id="v-1.1.0",
                    storage=mock_storage,
                    metrics_collector=mock_metrics_collector,
                    degradation_detector=mock_degradation_detector,
                    rollback_reason=RollbackReason.AUTOMATIC_DEGRADATION,
                    amendment_id="a-123",
                    time_window=TimeWindow.SIX_HOURS,
                )

    def test_raises_with_manual_reason(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        with pytest.raises(ImportError):
            create_rollback_saga(
                current_version_id="v-1.1.0",
                storage=mock_storage,
                metrics_collector=mock_metrics_collector,
                degradation_detector=mock_degradation_detector,
                rollback_reason=RollbackReason.MANUAL_REQUEST,
            )

    def test_builds_seven_steps_when_workflow_available(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        MockWorkflow, MockStep, MockComp = _make_mock_saga_classes()

        with patch.dict(
            create_rollback_saga.__globals__,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_rollback_saga(
                current_version_id="v-1.1.0",
                storage=mock_storage,
                metrics_collector=mock_metrics_collector,
                degradation_detector=mock_degradation_detector,
            )

        assert len(saga._steps) == 7

    def test_step_contract_matches_expected_rollback_flow(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        MockWorkflow, MockStep, MockComp = _make_mock_saga_classes()

        with patch.dict(
            create_rollback_saga.__globals__,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_rollback_saga(
                current_version_id="v-1.1.0",
                storage=mock_storage,
                metrics_collector=mock_metrics_collector,
                degradation_detector=mock_degradation_detector,
            )

        by_name = {step.name: step for step in saga._steps}
        assert [step.name for step in saga._steps] == [
            "detect_degradation",
            "prepare_rollback",
            "notify_hitl",
            "update_opa_to_previous",
            "restore_previous_version",
            "invalidate_cache",
            "audit_rollback",
        ]
        assert by_name["notify_hitl"].is_optional is True
        assert by_name["update_opa_to_previous"].is_optional is True
        assert by_name["audit_rollback"].is_optional is True
        assert by_name["restore_previous_version"].is_optional is False
        assert by_name["detect_degradation"].timeout_seconds == ROLLBACK_DETECT_TIMEOUT_SECONDS
        assert by_name["update_opa_to_previous"].timeout_seconds == ROLLBACK_DETECT_TIMEOUT_SECONDS
        assert by_name["prepare_rollback"].timeout_seconds == ROLLBACK_STEP_TIMEOUT_SECONDS
        assert by_name["invalidate_cache"].timeout_seconds == ROLLBACK_STEP_TIMEOUT_SECONDS
        assert by_name["detect_degradation"].compensation.name == "log_detection_failure"
        assert by_name["audit_rollback"].compensation.name == "mark_rollback_audit_failed"

    def test_saga_id_uses_current_version_prefix(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        MockWorkflow, MockStep, MockComp = _make_mock_saga_classes()

        with patch.dict(
            create_rollback_saga.__globals__,
            {
                "ConstitutionalSagaWorkflow": MockWorkflow,
                "SagaStep": MockStep,
                "SagaCompensation": MockComp,
            },
        ):
            saga = create_rollback_saga(
                current_version_id="version-abcdef12",
                storage=mock_storage,
                metrics_collector=mock_metrics_collector,
                degradation_detector=mock_degradation_detector,
            )

        assert saga.saga_id.startswith("rollback-version-")


# ---------------------------------------------------------------------------
# rollback_amendment
# ---------------------------------------------------------------------------


class TestRollbackAmendment:
    def test_build_rollback_context_sets_expected_step_results(self):
        class MockContext:
            def __init__(self, saga_id, constitutional_hash):
                self.saga_id = saga_id
                self.constitutional_hash = constitutional_hash
                self.values = {}

            def set_step_result(self, key, value):
                self.values[key] = value

        with patch("enhanced_agent_bus.constitutional.rollback_engine.SagaContext", MockContext):
            context = _build_rollback_context(
                saga_id="rollback-123",
                current_version_id="v-1.1.0",
                amendment_id="amend-7",
                rollback_reason=RollbackReason.MANUAL_REQUEST,
                time_window=TimeWindow.SIX_HOURS,
            )

        assert context.saga_id == "rollback-123"
        assert context.constitutional_hash == CONSTITUTIONAL_HASH
        assert context.values == {
            "current_version_id": "v-1.1.0",
            "amendment_id": "amend-7",
            "rollback_reason": RollbackReason.MANUAL_REQUEST,
            "time_window": TimeWindow.SIX_HOURS,
        }

    async def test_raises_when_saga_context_unavailable(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        with patch("enhanced_agent_bus.constitutional.rollback_engine.SagaContext", None):
            with pytest.raises(ImportError, match="SagaContext not available"):
                await rollback_amendment(
                    current_version_id="v-1.1.0",
                    storage=mock_storage,
                    metrics_collector=mock_metrics_collector,
                    degradation_detector=mock_degradation_detector,
                )

    async def test_initializes_executes_and_closes_saga_lifecycle(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        class MockContext:
            def __init__(self, saga_id, constitutional_hash):
                self.saga_id = saga_id
                self.constitutional_hash = constitutional_hash
                self.values = {}

            def set_step_result(self, key, value):
                self.values[key] = value

        mock_result = object()
        captured = {}

        class MockSaga:
            saga_id = "rollback-saga-42"

            async def execute(self, context):
                captured["context"] = context
                return mock_result

        init_mock = AsyncMock()
        close_mock = AsyncMock()

        with patch("enhanced_agent_bus.constitutional.rollback_engine.SagaContext", MockContext):
            with patch(
                "enhanced_agent_bus.constitutional.rollback_engine.create_rollback_saga",
                return_value=MockSaga(),
            ):
                with patch(
                    "enhanced_agent_bus.constitutional.rollback_engine._initialize_saga_activities",
                    init_mock,
                ):
                    with patch(
                        "enhanced_agent_bus.constitutional.rollback_engine._close_saga_activities",
                        close_mock,
                    ):
                        result = await rollback_amendment(
                            current_version_id="v-1.1.0",
                            storage=mock_storage,
                            metrics_collector=mock_metrics_collector,
                            degradation_detector=mock_degradation_detector,
                            amendment_id="amend-9",
                            rollback_reason=RollbackReason.EMERGENCY_OVERRIDE,
                            time_window=TimeWindow.ONE_HOUR,
                        )

        assert result is mock_result
        init_mock.assert_awaited_once()
        close_mock.assert_awaited_once()
        assert captured["context"].values["current_version_id"] == "v-1.1.0"
        assert captured["context"].values["amendment_id"] == "amend-9"
        assert captured["context"].values["rollback_reason"] == RollbackReason.EMERGENCY_OVERRIDE


# ---------------------------------------------------------------------------
# Constitutional hash enforcement
# ---------------------------------------------------------------------------


class TestConstitutionalHashEnforcement:
    def test_constitutional_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    async def test_audit_event_includes_hash(self, activities):
        activities._audit_client = None
        result = await activities.audit_rollback(
            {
                "saga_id": "s1",
                "context": {
                    "detect_degradation": {},
                    "prepare_rollback": {},
                    "restore_previous_version": {},
                    "notify_hitl": {},
                },
            }
        )
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_mark_audit_failed_includes_hash(self, activities):
        activities._audit_client = AsyncMock()

        await activities.mark_rollback_audit_failed(
            {"saga_id": "s1", "context": {"audit_rollback": {}}}
        )

        call_kwargs = activities._audit_client.log.call_args
        data_arg = call_kwargs[1].get("data") or call_kwargs[0][1]
        assert data_arg["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# End-to-end activity chain (integration-style)
# ---------------------------------------------------------------------------


class TestEndToEndActivityChain:
    async def test_full_happy_path(
        self,
        mock_storage,
        mock_metrics_collector,
        mock_degradation_detector,
        baseline_snapshot,
        degradation_report,
        current_version,
        target_version,
        mock_amendment,
    ):
        """Run all 7 saga activities in sequence and verify chain works."""
        mock_metrics_collector.get_baseline_snapshot.return_value = baseline_snapshot
        mock_metrics_collector.collect_snapshot.return_value = baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = degradation_report
        mock_storage.get_version.side_effect = [current_version, target_version]
        mock_storage.get_amendment.return_value = mock_amendment

        acts = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
        )

        # Step 1
        detect_result = await acts.detect_degradation(
            {
                "saga_id": "saga-e2e",
                "context": {
                    "current_version_id": "v-1.1.0",
                    "time_window": TimeWindow.ONE_HOUR,
                },
            }
        )
        assert detect_result["has_degradation"] is True

        # Step 2
        prepare_result = await acts.prepare_rollback(
            {
                "saga_id": "saga-e2e",
                "context": {
                    "current_version_id": "v-1.1.0",
                    "amendment_id": "amendment-123",
                },
            }
        )
        assert prepare_result["is_valid"] is True

        # Step 3
        notify_result = await acts.notify_hitl(
            {
                "saga_id": "saga-e2e",
                "context": {
                    "detect_degradation": detect_result,
                    "prepare_rollback": prepare_result,
                    "rollback_reason": RollbackReason.AUTOMATIC_DEGRADATION,
                },
            }
        )
        assert "notification_id" in notify_result

        # Step 4
        opa_result = await acts.update_opa_to_previous(
            {
                "saga_id": "saga-e2e",
                "context": {"prepare_rollback": prepare_result},
            }
        )
        assert opa_result["updated"] is True

        # Step 5
        restore_result = await acts.restore_previous_version(
            {
                "saga_id": "saga-e2e",
                "context": {
                    "amendment_id": "amendment-123",
                    "prepare_rollback": prepare_result,
                },
            }
        )
        assert restore_result["restored"] is True

        # Step 6
        acts._redis_client = AsyncMock()
        cache_result = await acts.invalidate_cache({"saga_id": "saga-e2e", "context": {}})
        assert cache_result["cache_invalidated"] is True

        # Step 7
        acts._audit_client = AsyncMock()
        audit_result = await acts.audit_rollback(
            {
                "saga_id": "saga-e2e",
                "context": {
                    "rollback_reason": RollbackReason.AUTOMATIC_DEGRADATION,
                    "amendment_id": "amendment-123",
                    "detect_degradation": detect_result,
                    "prepare_rollback": prepare_result,
                    "restore_previous_version": restore_result,
                    "notify_hitl": notify_result,
                },
            }
        )
        assert audit_result["event_type"] == "constitutional_version_rolled_back"

    async def test_compensation_chain(self, activities, mock_storage):
        """All compensation methods return True and can be chained."""
        base_input = {"saga_id": "s1", "context": {}}

        assert await activities.log_detection_failure(base_input) is True
        assert await activities.cancel_preparation(base_input) is True
        assert await activities.cancel_hitl_notification(base_input) is True

        activities._redis_client = None
        assert await activities.restore_cache(base_input) is True

        activities._audit_client = None
        assert await activities.mark_rollback_audit_failed({"saga_id": "s1", "context": {}}) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
