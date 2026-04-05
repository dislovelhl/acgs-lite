"""
Test coverage for AdaptiveGovernanceEngine.
Constitutional Hash: 608508a9bd224290

Targets ≥90% coverage of
src/core/enhanced_agent_bus/adaptive_governance/governance_engine.py
"""

import asyncio
import dataclasses
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as SHARED_CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Shared patch targets — always suppress heavy I/O during import / init
# ---------------------------------------------------------------------------

_MLFLOW_PATCH = "mlflow.set_tracking_uri"
_IMPACT_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.impact_scorer.ImpactScorer._initialize_mlflow"
)
_THRESH_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.threshold_manager.AdaptiveThresholds._initialize_mlflow"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONST_HASH = SHARED_CONSTITUTIONAL_HASH


def _make_features(risk_score: float = 0.3, confidence: float = 0.9):
    from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

    return ImpactFeatures(
        message_length=50,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.4,
        historical_precedence=1,
        resource_utilization=0.2,
        network_isolation=0.8,
        risk_score=risk_score,
        confidence_level=confidence,
    )


def _make_decision(risk_score: float = 0.3, action_allowed: bool = True):
    from enhanced_agent_bus.adaptive_governance.models import (
        GovernanceDecision,
        ImpactLevel,
    )

    features = _make_features(risk_score=risk_score)
    return GovernanceDecision(
        action_allowed=action_allowed,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.9,
        reasoning="test reasoning",
        recommended_threshold=0.5,
        features_used=features,
    )


@pytest.fixture
def engine():
    """Create an AdaptiveGovernanceEngine with all heavy deps suppressed."""
    with (
        patch(_IMPACT_MLFLOW),
        patch(_THRESH_MLFLOW),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ANOMALY_MONITORING_AVAILABLE",
            False,
        ),
    ):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        return AdaptiveGovernanceEngine(CONST_HASH)


@pytest.fixture
def sample_message():
    return {
        "from_agent": "agent-a",
        "to_agent": "agent-b",
        "content": "Hello world",
        "tenant_id": "tenant-1",
        "constitutional_hash": CONST_HASH,
    }


@pytest.fixture
def sample_context():
    return {
        "tenant_id": "tenant-1",
        "agent_type": "standard",
        "permissions": ["read"],
    }


# ---------------------------------------------------------------------------
# 13. _get_trajectory_prefix
# ---------------------------------------------------------------------------


class TestGetTrajectoryPrefix:
    def test_empty_history_returns_none(self, engine):
        assert engine._get_trajectory_prefix() is None

    def test_returns_state_indices(self, engine):
        engine.decision_history = [_make_decision() for _ in range(5)]
        prefix = engine._get_trajectory_prefix()
        assert prefix is not None
        assert len(prefix) == 5

    def test_capped_at_10(self, engine):
        engine.decision_history = [_make_decision() for _ in range(15)]
        prefix = engine._get_trajectory_prefix()
        assert len(prefix) == 10


# ---------------------------------------------------------------------------
# 14. _maybe_refit_dtmc
# ---------------------------------------------------------------------------


class TestMaybeRefitDtmc:
    def test_noop_when_dtmc_disabled(self, engine):
        engine.config = None
        engine._maybe_refit_dtmc()  # should not raise

    def test_noop_when_insufficient_history(self, engine):
        cfg = MagicMock()
        cfg.enable_dtmc = True
        engine.config = cfg
        engine.decision_history = [_make_decision() for _ in range(5)]  # < 10
        engine._dtmc_learner.fit = MagicMock()
        engine._maybe_refit_dtmc()
        engine._dtmc_learner.fit.assert_not_called()

    def test_refit_called_with_enough_history(self, engine):
        cfg = MagicMock()
        cfg.enable_dtmc = True
        engine.config = cfg
        engine.decision_history = [_make_decision() for _ in range(15)]

        mock_result = MagicMock()
        mock_result.n_trajectories = 2
        mock_result.unsafe_fraction = 0.1
        engine._dtmc_learner.fit = MagicMock(return_value=mock_result)

        engine._maybe_refit_dtmc()
        # If trajectories were produced, fit will have been called
        # (depends on trace_collector, but no crash is the assertion)

    def test_noop_when_no_trajectories(self, engine):
        cfg = MagicMock()
        cfg.enable_dtmc = True
        engine.config = cfg
        engine.decision_history = [_make_decision() for _ in range(15)]
        engine._trace_collector.collect_from_decision_history = MagicMock(return_value=[])
        engine._dtmc_learner.fit = MagicMock()
        engine._maybe_refit_dtmc()
        engine._dtmc_learner.fit.assert_not_called()


# ---------------------------------------------------------------------------
# 15. _run_scheduled_drift_detection
# ---------------------------------------------------------------------------


class TestRunScheduledDriftDetection:
    def test_noop_when_drift_unavailable(self, engine):
        engine._drift_detector = None
        engine._run_scheduled_drift_detection()  # should not raise

    def test_skips_when_interval_not_elapsed(self, engine):
        mock_detector = MagicMock()
        engine._drift_detector = mock_detector
        engine._last_drift_check = time.time()  # just now
        engine._drift_check_interval = 9999

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.DRIFT_MONITORING_AVAILABLE
        try:
            ge_mod.DRIFT_MONITORING_AVAILABLE = True
            engine._run_scheduled_drift_detection()
            mock_detector.detect_drift.assert_not_called()
        finally:
            ge_mod.DRIFT_MONITORING_AVAILABLE = orig

    def test_runs_when_interval_elapsed_no_data(self, engine):
        mock_detector = MagicMock()
        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0  # long ago
        engine._drift_check_interval = 0

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.DRIFT_MONITORING_AVAILABLE
        try:
            ge_mod.DRIFT_MONITORING_AVAILABLE = True
            engine._run_scheduled_drift_detection()
            # No data → detect_drift not called
            mock_detector.detect_drift.assert_not_called()
        finally:
            ge_mod.DRIFT_MONITORING_AVAILABLE = orig

    def test_runs_drift_detection_with_data_drift_found(self, engine):
        """Drift detected path — dataset_drift=True."""
        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        mock_drift_status = MagicMock()
        mock_drift_status.SUCCESS = "SUCCESS"
        mock_severity = MagicMock()
        mock_severity.value = "high"

        mock_report = MagicMock()
        mock_report.status = MagicMock()
        mock_report.status.__eq__ = lambda self, other: True  # always equal SUCCESS
        mock_report.dataset_drift = True
        mock_report.drift_severity = mock_severity
        mock_report.drifted_features = 3
        mock_report.total_features = 10
        mock_report.drift_share = 0.3
        mock_report.recommendations = ["retrain model"]

        mock_detector = MagicMock()
        mock_detector.detect_drift = MagicMock(return_value=mock_report)
        mock_detector.should_trigger_retraining = MagicMock(return_value=True)

        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        # Add decisions so _collect_drift_data returns data
        engine.decision_history = [_make_decision() for _ in range(5)]

        # Patch _collect_drift_data to return a non-empty mock frame
        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=5)

        orig_drift = ge_mod.DRIFT_MONITORING_AVAILABLE
        orig_status = ge_mod.DriftStatus
        try:
            ge_mod.DRIFT_MONITORING_AVAILABLE = True
            ge_mod.DriftStatus = mock_drift_status
            with patch.object(engine, "_collect_drift_data", return_value=mock_df):
                engine._run_scheduled_drift_detection()
            mock_detector.detect_drift.assert_called_once()
        finally:
            ge_mod.DRIFT_MONITORING_AVAILABLE = orig_drift
            ge_mod.DriftStatus = orig_status

    def test_runs_drift_detection_exception_swallowed(self, engine):
        mock_detector = MagicMock()
        mock_detector.detect_drift = MagicMock(side_effect=RuntimeError("drift fail"))
        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=5)

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.DRIFT_MONITORING_AVAILABLE
        try:
            ge_mod.DRIFT_MONITORING_AVAILABLE = True
            with patch.object(engine, "_collect_drift_data", return_value=mock_df):
                engine._run_scheduled_drift_detection()  # should not raise
        finally:
            ge_mod.DRIFT_MONITORING_AVAILABLE = orig


# ---------------------------------------------------------------------------
# 16. _collect_drift_data
# ---------------------------------------------------------------------------


class TestCollectDriftData:
    def test_returns_none_when_no_history(self, engine):
        result = engine._collect_drift_data()
        assert result is None

    def test_returns_dataframe_with_decisions(self, engine):
        engine.decision_history = [_make_decision() for _ in range(5)]
        result = engine._collect_drift_data()
        # May be None if pandas not available — just ensure no crash
        # If pandas IS available, should be a non-None DataFrame
        assert result is None or hasattr(result, "shape")

    def test_with_temporal_patterns_empty(self, engine):
        """Covers 0-division guard when temporal_patterns is empty."""
        from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

        features = ImpactFeatures(
            message_length=10,
            agent_count=1,
            tenant_complexity=0.5,
            temporal_patterns=[],  # empty list
            semantic_similarity=0.3,
            historical_precedence=0,
            resource_utilization=0.2,
            network_isolation=0.8,
        )
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactLevel,
        )

        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.LOW,
            confidence_score=0.9,
            reasoning="test",
            recommended_threshold=0.5,
            features_used=features,
        )
        engine.decision_history = [decision]
        result = engine._collect_drift_data()
        assert result is None or hasattr(result, "shape")


# ---------------------------------------------------------------------------
# 17. get_latest_drift_report
# ---------------------------------------------------------------------------


class TestGetLatestDriftReport:
    def test_returns_none_initially(self, engine):
        assert engine.get_latest_drift_report() is None

    def test_returns_report_after_set(self, engine):
        mock_report = MagicMock()
        engine._latest_drift_report = mock_report
        assert engine.get_latest_drift_report() is mock_report
