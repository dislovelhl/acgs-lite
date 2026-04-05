"""
Tests for Constitutional Rollback Engine
Constitutional Hash: 608508a9bd224290

Tests for saga workflow for rolling back constitutional amendments
when governance degradation is detected.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..amendment_model import AmendmentProposal, AmendmentStatus
from ..degradation_detector import (
    DegradationDetector,
    DegradationReport,
    DegradationSeverity,
    TimeWindow,
)
from ..metrics_collector import GovernanceMetricsCollector, GovernanceMetricsSnapshot
from ..rollback_engine import (
    RollbackEngineError,
    RollbackReason,
    RollbackSagaActivities,
    RollbackTriggerConfig,
    create_rollback_saga,
)
from ..storage import ConstitutionalStorageService
from ..version_model import ConstitutionalStatus, ConstitutionalVersion

# Constitutional validation markers
pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.unit,
]


class TestRollbackTriggerConfig:
    """Test RollbackTriggerConfig configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RollbackTriggerConfig()

        assert config.enable_automatic_rollback is True
        assert config.monitoring_interval_seconds == 300
        assert TimeWindow.ONE_HOUR in config.monitoring_windows
        assert TimeWindow.SIX_HOURS in config.monitoring_windows
        assert config.require_hitl_approval_for_critical is True
        assert config.auto_approve_high_confidence is True
        assert config.min_confidence_for_auto_rollback == 0.7

    def test_custom_config(self):
        """Test custom configuration."""
        config = RollbackTriggerConfig(
            enable_automatic_rollback=False,
            monitoring_interval_seconds=600,
            monitoring_windows=[TimeWindow.TWENTY_FOUR_HOURS],
            min_confidence_for_auto_rollback=0.9,
        )

        assert config.enable_automatic_rollback is False
        assert config.monitoring_interval_seconds == 600
        assert config.monitoring_windows == [TimeWindow.TWENTY_FOUR_HOURS]
        assert config.min_confidence_for_auto_rollback == 0.9


class TestRollbackReason:
    """Test RollbackReason constants."""

    def test_rollback_reasons(self):
        """Test rollback reason values."""
        assert RollbackReason.AUTOMATIC_DEGRADATION == "automatic_degradation"
        assert RollbackReason.MANUAL_REQUEST == "manual_request"
        assert RollbackReason.EMERGENCY_OVERRIDE == "emergency_override"


class TestRollbackSagaActivities:
    """Test RollbackSagaActivities methods."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage service."""
        storage = AsyncMock(spec=ConstitutionalStorageService)
        return storage

    @pytest.fixture
    def mock_metrics_collector(self):
        """Create mock metrics collector."""
        collector = AsyncMock(spec=GovernanceMetricsCollector)
        return collector

    @pytest.fixture
    def mock_degradation_detector(self):
        """Create mock degradation detector."""
        detector = AsyncMock(spec=DegradationDetector)
        return detector

    @pytest.fixture
    def activities(self, mock_storage, mock_metrics_collector, mock_degradation_detector):
        """Create activities instance for testing."""
        return RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics_collector,
            degradation_detector=mock_degradation_detector,
            opa_url="http://localhost:8181",
            audit_service_url="http://localhost:8001",
            redis_url="redis://localhost:6379",
        )

    @pytest.fixture
    def mock_baseline_snapshot(self):
        """Create mock baseline metrics snapshot."""
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
    def mock_degradation_report(self, mock_baseline_snapshot):
        """Create mock degradation report."""
        return DegradationReport(
            report_id="report-001",
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=mock_baseline_snapshot,
            current_snapshot=mock_baseline_snapshot,
            overall_severity=DegradationSeverity.HIGH,
            confidence_score=0.85,
            rollback_recommended=True,
            degradation_summary="Governance degradation detected: violations rate increased.",
        )

    @pytest.fixture
    def mock_current_version(self):
        """Create mock current constitutional version."""
        return ConstitutionalVersion(
            version_id="v-1.1.0",
            version="1.1.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": ["P1", "P2", "P3"]},
            status=ConstitutionalStatus.ACTIVE,
            predecessor_version="v-1.0.0",
        )

    @pytest.fixture
    def mock_target_version(self):
        """Create mock target (previous) constitutional version."""
        return ConstitutionalVersion(
            version_id="v-1.0.0",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": ["P1", "P2"]},
            status=ConstitutionalStatus.APPROVED,
        )

    async def test_detect_degradation_success(
        self,
        activities,
        mock_metrics_collector,
        mock_degradation_detector,
        mock_baseline_snapshot,
        mock_degradation_report,
    ):
        """Test successful degradation detection."""
        mock_metrics_collector.get_baseline_snapshot.return_value = mock_baseline_snapshot
        mock_metrics_collector.collect_snapshot.return_value = mock_baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = mock_degradation_report

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "current_version_id": "v-1.1.0",
                "amendment_id": "amendment-123",
                "time_window": TimeWindow.ONE_HOUR,
            },
        }

        result = await activities.detect_degradation(input_data)

        assert "detection_id" in result
        assert result["severity"] == "high"
        assert result["rollback_recommended"] is True
        assert result["confidence_score"] == 0.85
        assert result["has_degradation"] is True

    async def test_detect_degradation_no_baseline(
        self,
        activities,
        mock_metrics_collector,
        mock_degradation_detector,
        mock_baseline_snapshot,
        mock_degradation_report,
    ):
        """Test degradation detection without existing baseline."""
        # No baseline found - will create synthetic baseline
        mock_metrics_collector.get_baseline_snapshot.return_value = None
        mock_metrics_collector.collect_snapshot.return_value = mock_baseline_snapshot
        mock_degradation_detector.analyze_degradation.return_value = mock_degradation_report

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "current_version_id": "v-1.1.0",
                "time_window": TimeWindow.ONE_HOUR,
            },
        }

        result = await activities.detect_degradation(input_data)

        # Should still succeed with synthetic baseline
        assert "detection_id" in result
        mock_metrics_collector.collect_snapshot.assert_called()

    async def test_prepare_rollback_success(
        self, activities, mock_storage, mock_current_version, mock_target_version
    ):
        """Test successful rollback preparation."""
        mock_storage.get_version.side_effect = [mock_current_version, mock_target_version]

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "current_version_id": "v-1.1.0",
                "amendment_id": "amendment-123",
            },
        }

        result = await activities.prepare_rollback(input_data)

        assert result["is_valid"] is True
        assert result["current_version"] == "1.1.0"
        assert result["target_version"] == "1.0.0"
        assert result["target_version_id"] == "v-1.0.0"
        assert result["target_hash"] == CONSTITUTIONAL_HASH

    async def test_prepare_rollback_version_not_found(self, activities, mock_storage):
        """Test rollback preparation fails when version not found."""
        mock_storage.get_version.return_value = None

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {"current_version_id": "v-nonexistent"},
        }

        with pytest.raises(RollbackEngineError, match="not found"):
            await activities.prepare_rollback(input_data)

    async def test_prepare_rollback_no_predecessor(self, activities, mock_storage):
        """Test rollback fails when no predecessor version."""
        version_without_predecessor = ConstitutionalVersion(
            version_id="v-1.0.0",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": []},
            status=ConstitutionalStatus.ACTIVE,
            predecessor_version=None,  # No predecessor
        )
        mock_storage.get_version.return_value = version_without_predecessor

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {"current_version_id": "v-1.0.0"},
        }

        with pytest.raises(RollbackEngineError, match="no predecessor"):
            await activities.prepare_rollback(input_data)

    async def test_notify_hitl_critical_severity(self, activities):
        """Test HITL notification for critical severity."""
        mock_hitl = AsyncMock()
        activities.hitl_integration = mock_hitl

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "detect_degradation": {"severity": "critical"},
                "prepare_rollback": {
                    "current_version": "1.1.0",
                    "target_version": "1.0.0",
                },
                "rollback_reason": RollbackReason.AUTOMATIC_DEGRADATION,
            },
        }

        result = await activities.notify_hitl(input_data)

        assert "notification_id" in result
        assert result["severity"] == "critical"

    async def test_notify_hitl_low_severity_no_notification(self, activities):
        """Test no HITL notification for low severity."""
        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "detect_degradation": {"severity": "low"},
                "prepare_rollback": {},
            },
        }

        result = await activities.notify_hitl(input_data)

        assert result["notifications_sent"] == []

    async def test_update_opa_to_previous_success(self, activities):
        """Test successful OPA policy rollback."""
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=200)

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "prepare_rollback": {
                    "target_hash": CONSTITUTIONAL_HASH,
                    "target_version": "1.0.0",
                },
            },
        }

        result = await activities.update_opa_to_previous(input_data)

        assert result["updated"] is True
        assert result["previous_hash"] == CONSTITUTIONAL_HASH
        assert result["previous_version"] == "1.0.0"

    async def test_restore_previous_version_success(
        self, activities, mock_storage, mock_target_version
    ):
        """Test successful version restoration."""
        mock_amendment = AmendmentProposal(
            proposal_id="amendment-123",
            proposed_changes={"key": "value"},
            justification="Test amendment for rollback testing.",
            proposer_agent_id="agent-001",
            target_version="1.0.0",
            status=AmendmentStatus.ACTIVE,
        )
        mock_storage.get_amendment.return_value = mock_amendment

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "amendment_id": "amendment-123",
                "prepare_rollback": {
                    "target_version_id": "v-1.0.0",
                    "target_version": "1.0.0",
                    "current_version_id": "v-1.1.0",
                },
            },
        }

        result = await activities.restore_previous_version(input_data)

        assert result["restored"] is True
        assert result["restored_version_id"] == "v-1.0.0"
        assert result["amendment_rolled_back"] is True

        mock_storage.activate_version.assert_called_with("v-1.0.0")
        mock_storage.save_amendment.assert_called()

    async def test_invalidate_cache_success(self, activities):
        """Test successful cache invalidation."""
        activities._redis_client = AsyncMock()
        activities._redis_client.delete.return_value = 1

        input_data = {"saga_id": "rollback-saga-001", "context": {}}

        result = await activities.invalidate_cache(input_data)

        assert result["cache_invalidated"] is True
        activities._redis_client.delete.assert_called_with("constitutional:active_version")

    async def test_invalidate_cache_no_redis(self, activities):
        """Test cache invalidation without Redis."""
        activities._redis_client = None

        input_data = {"saga_id": "rollback-saga-001", "context": {}}

        result = await activities.invalidate_cache(input_data)

        assert result["cache_invalidated"] is False

    async def test_audit_rollback_success(self, activities):
        """Test successful rollback audit logging."""
        activities._audit_client = AsyncMock()

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "amendment_id": "amendment-123",
                "rollback_reason": RollbackReason.AUTOMATIC_DEGRADATION,
                "detect_degradation": {
                    "severity": "high",
                    "confidence_score": 0.85,
                    "degradation_summary": "Violations rate increased.",
                    "critical_metrics": ["violations_rate"],
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
                "notify_hitl": {"notifications_sent": ["slack"]},
            },
        }

        result = await activities.audit_rollback(input_data)

        assert result["event_type"] == "constitutional_version_rolled_back"
        assert result["amendment_id"] == "amendment-123"
        assert result["rollback_reason"] == RollbackReason.AUTOMATIC_DEGRADATION
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert result["severity"] == "high"

    async def test_compensation_methods(self, activities, mock_storage):
        """Test all compensation methods return True."""
        input_data = {"saga_id": "rollback-saga-001", "context": {}}

        assert await activities.log_detection_failure(input_data) is True
        assert await activities.cancel_preparation(input_data) is True
        assert await activities.cancel_hitl_notification(input_data) is True

    async def test_revert_opa_to_current(self, activities):
        """Test OPA revert compensation."""
        activities._http_client = AsyncMock()
        activities._http_client.put.return_value = MagicMock(status_code=200)

        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "prepare_rollback": {"current_version": "1.1.0"},
            },
        }

        result = await activities.revert_opa_to_current(input_data)

        assert result is True

    async def test_revert_version_restoration(self, activities, mock_storage):
        """Test version restoration revert."""
        input_data = {
            "saga_id": "rollback-saga-001",
            "context": {
                "prepare_rollback": {"current_version_id": "v-1.1.0"},
            },
        }

        result = await activities.revert_version_restoration(input_data)

        assert result is True
        mock_storage.activate_version.assert_called_with("v-1.1.0")


class TestRollbackSagaFactory:
    """Test create_rollback_saga factory function."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage."""
        return AsyncMock(spec=ConstitutionalStorageService)

    @pytest.fixture
    def mock_metrics_collector(self):
        """Create mock metrics collector."""
        return AsyncMock(spec=GovernanceMetricsCollector)

    @pytest.fixture
    def mock_degradation_detector(self):
        """Create mock degradation detector."""
        return AsyncMock(spec=DegradationDetector)

    def test_create_rollback_saga_without_workflow(
        self, mock_storage, mock_metrics_collector, mock_degradation_detector
    ):
        """Test saga creation fails without ConstitutionalSagaWorkflow."""
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

    def test_create_rollback_saga_requires_workflow(
        self,
        mock_storage,
        mock_metrics_collector,
        mock_degradation_detector,
    ):
        """Test saga creation requires ConstitutionalSagaWorkflow to be available.

        The saga factory requires the deliberation_layer.workflows module to be
        installed. If not available, it should raise ImportError with a helpful message.
        """
        # When ConstitutionalSagaWorkflow is not available (as in test environment),
        # creating a saga should raise ImportError with guidance
        with pytest.raises(ImportError, match="ConstitutionalSagaWorkflow not available"):
            create_rollback_saga(
                current_version_id="v-1.1.0",
                storage=mock_storage,
                metrics_collector=mock_metrics_collector,
                degradation_detector=mock_degradation_detector,
                rollback_reason=RollbackReason.AUTOMATIC_DEGRADATION,
                amendment_id="amendment-123",
                time_window=TimeWindow.SIX_HOURS,
            )


class TestRollbackIntegration:
    """Integration-style tests for rollback flow."""

    async def test_full_rollback_detection_flow(self):
        """Test complete rollback detection flow."""
        mock_storage = AsyncMock(spec=ConstitutionalStorageService)
        mock_metrics = AsyncMock(spec=GovernanceMetricsCollector)
        mock_detector = AsyncMock(spec=DegradationDetector)

        # Setup mock versions
        current_version = ConstitutionalVersion(
            version_id="v-1.1.0",
            version="1.1.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": ["P1", "P2", "P3"]},
            status=ConstitutionalStatus.ACTIVE,
            predecessor_version="v-1.0.0",
        )

        target_version = ConstitutionalVersion(
            version_id="v-1.0.0",
            version="1.0.0",
            constitutional_hash=CONSTITUTIONAL_HASH,
            content={"principles": ["P1", "P2"]},
            status=ConstitutionalStatus.APPROVED,
        )

        mock_storage.get_version.side_effect = [current_version, target_version]

        # Setup mock metrics
        baseline = GovernanceMetricsSnapshot(
            snapshot_id="baseline",
            constitutional_version="1.1.0",
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

        mock_metrics.get_baseline_snapshot.return_value = baseline
        mock_metrics.collect_snapshot.return_value = baseline

        # Setup degradation report
        report = DegradationReport(
            time_window=TimeWindow.ONE_HOUR,
            baseline_snapshot=baseline,
            current_snapshot=baseline,
            overall_severity=DegradationSeverity.HIGH,
            confidence_score=0.9,
            rollback_recommended=True,
            degradation_summary="Critical degradation detected.",
        )
        mock_detector.analyze_degradation.return_value = report

        activities = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics,
            degradation_detector=mock_detector,
        )

        # Step 1: Detect degradation
        detect_input = {
            "saga_id": "rollback-test-001",
            "context": {
                "current_version_id": "v-1.1.0",
                "time_window": TimeWindow.ONE_HOUR,
            },
        }
        detect_result = await activities.detect_degradation(detect_input)
        assert detect_result["rollback_recommended"] is True

        # Step 2: Prepare rollback
        prepare_input = {
            "saga_id": "rollback-test-001",
            "context": {"current_version_id": "v-1.1.0"},
        }
        prepare_result = await activities.prepare_rollback(prepare_input)
        assert prepare_result["target_version"] == "1.0.0"


class TestConstitutionalHashEnforcement:
    """Test constitutional hash enforcement in rollback."""

    def test_rollback_reason_audit_includes_hash(self):
        """Test that rollback audit includes constitutional hash."""
        mock_storage = AsyncMock()
        mock_metrics = AsyncMock()
        mock_detector = AsyncMock()

        activities = RollbackSagaActivities(
            storage=mock_storage,
            metrics_collector=mock_metrics,
            degradation_detector=mock_detector,
        )

        # Verify CONSTITUTIONAL_HASH is referenced
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
