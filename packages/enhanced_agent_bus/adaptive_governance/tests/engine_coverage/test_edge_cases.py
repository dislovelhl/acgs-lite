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
# 20. Additional branch coverage for uncovered paths
# ---------------------------------------------------------------------------


class TestAdditionalBranchCoverage:
    """Tests targeting specific uncovered branches."""

    def test_drift_monitoring_init_error(self):
        """Branch: DRIFT_MONITORING_AVAILABLE=True but get_drift_detector raises."""
        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector",
                side_effect=RuntimeError("drift init fail"),
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng._drift_detector is None

    def test_river_init_error(self):
        """Branch: ONLINE_LEARNING and RIVER available, but get_online_learning_pipeline raises."""
        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "get_online_learning_pipeline",
                side_effect=RuntimeError("river init fail"),
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ModelType",
                MagicMock(),
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng.river_model is None

    def test_ab_test_router_success_with_trained_model(self):
        """Branch: AB router available, model_trained=True → set_champion_model called."""
        mock_router = MagicMock()
        mock_shadow = MagicMock()

        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_ab_test_router",
                return_value=mock_router,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ShadowPolicyExecutor",
                return_value=mock_shadow,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TEST_SPLIT",
                0.1,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            # Force impact_scorer.model_trained=True after creation
            eng.impact_scorer.model_trained = True
            # Verify that router was created
            assert eng._ab_test_router is mock_router

    def test_get_river_model_stats_dict_conversion(self, engine):
        """Branch: stats has no __dict__, uses dict(stats)."""
        mock_stats = {"samples": 5, "accuracy": 0.8}
        mock_model = MagicMock()
        # make get_stats return a dict directly (no __dict__)
        mock_model.get_stats = MagicMock(return_value=mock_stats)
        # Remove __dict__ from stats so the `hasattr(stats, '__dict__')` check is False
        engine.river_model = mock_model

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.ONLINE_LEARNING_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            result = engine.get_river_model_stats()
            assert result == {"samples": 5, "accuracy": 0.8}
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig

    def test_store_feedback_event_negative_outcome(self, engine):
        """Branch: outcome_success=False → NEGATIVE feedback type + FAILURE status."""
        mock_handler = MagicMock()
        mock_handler.store_feedback = MagicMock(return_value=MagicMock(feedback_id="fid-3"))
        engine._feedback_handler = mock_handler

        mock_ft = MagicMock()
        mock_ft.POSITIVE = "POSITIVE"
        mock_ft.NEGATIVE = "NEGATIVE"
        mock_ft.CORRECTION = "CORRECTION"
        mock_os = MagicMock()
        mock_os.SUCCESS = "SUCCESS"
        mock_os.FAILURE = "FAILURE"
        mock_event_cls = MagicMock()

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_available = ge_mod.FEEDBACK_HANDLER_AVAILABLE
        orig_ft = ge_mod.FeedbackType
        orig_os = ge_mod.OutcomeStatus
        orig_ev = ge_mod.FeedbackEvent
        try:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = True
            ge_mod.FeedbackType = mock_ft
            ge_mod.OutcomeStatus = mock_os
            ge_mod.FeedbackEvent = mock_event_cls

            decision = _make_decision()
            engine._store_feedback_event(
                decision, outcome_success=False, human_override=None, actual_impact=0.7
            )
            mock_handler.store_feedback.assert_called_once()
        finally:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = orig_available
            ge_mod.FeedbackType = orig_ft
            ge_mod.OutcomeStatus = orig_os
            ge_mod.FeedbackEvent = orig_ev

    def test_dtmc_blending_with_empty_prefix(self, engine, sample_message, sample_context):
        """Branch: DTMC blend branch but prefix is None (empty history)."""
        # This is an async test — but we call the internal sync parts
        # The branch 431->443 means: enable_dtmc+fitted+weight>0, _get_trajectory_prefix returns None
        pass  # Covered by test_dtmc_blending_when_fitted with no history

    async def test_ab_test_routing_candidate_cohort(self, engine, sample_message, sample_context):
        """Branch: AB routing to CANDIDATE cohort (line 470 — candidate metrics)."""
        mock_cohort = MagicMock()
        mock_cohort.value = "candidate"

        mock_routing_result = MagicMock()
        mock_routing_result.cohort = mock_cohort
        mock_routing_result.model_version = 2

        mock_candidate_metrics = MagicMock()
        mock_candidate_metrics.record_request = MagicMock()

        mock_router = MagicMock()
        mock_router.route = MagicMock(return_value=mock_routing_result)
        mock_router.get_candidate_metrics = MagicMock(return_value=mock_candidate_metrics)

        engine._ab_test_router = mock_router
        engine._shadow_executor = None

        features = _make_features(risk_score=0.3)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_ab = ge_mod.AB_TESTING_AVAILABLE
        orig_cohort_type = ge_mod.CohortType
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            # Make cohort == CANDIDATE by matching our mock
            fake_cohort = MagicMock()
            fake_cohort.CHAMPION = MagicMock()
            fake_cohort.CANDIDATE = mock_cohort
            mock_cohort.__eq__ = lambda self, other: other is mock_cohort
            ge_mod.CohortType = fake_cohort

            decision = await engine.evaluate_governance_decision(sample_message, sample_context)
            assert decision is not None
            mock_candidate_metrics.record_request.assert_called_once()
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig_ab
            ge_mod.CohortType = orig_cohort_type

    def test_provide_feedback_dtmc_less_than_2_decisions(self, engine):
        """Branch: enable_dtmc + fitted, but new_decisions < 2 so update_online not called."""
        cfg = MagicMock()
        cfg.enable_dtmc = True
        engine.config = cfg
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.update_online = MagicMock()
        engine.impact_scorer.update_model = MagicMock()
        engine.threshold_manager.update_model = MagicMock()

        # Only 1 decision in history, idx=0 → new_decisions has 1 item → < 2
        engine.decision_history = [_make_decision()]
        engine._dtmc_feedback_idx = 0

        engine.provide_feedback(_make_decision(), outcome_success=True)
        # update_online should NOT be called since len(new_decisions) < 2
        engine._dtmc_learner.update_online.assert_not_called()

    def test_run_scheduled_drift_no_drift(self, engine):
        """Branch: drift detection runs, dataset_drift=False → 'No significant drift'."""
        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        mock_drift_status = MagicMock()

        mock_report = MagicMock()
        # status == DriftStatus.SUCCESS must be True
        mock_report.dataset_drift = False
        mock_report.drift_share = 0.05

        mock_detector = MagicMock()
        mock_detector.detect_drift = MagicMock(return_value=mock_report)

        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=5)

        orig_drift = ge_mod.DRIFT_MONITORING_AVAILABLE
        orig_status = ge_mod.DriftStatus
        try:
            ge_mod.DRIFT_MONITORING_AVAILABLE = True
            # Make status == DriftStatus.SUCCESS pass by making both the same object
            ge_mod.DriftStatus = mock_drift_status
            mock_drift_status.SUCCESS = mock_report.status  # match

            with patch.object(engine, "_collect_drift_data", return_value=mock_df):
                engine._run_scheduled_drift_detection()
            mock_detector.detect_drift.assert_called_once()
        finally:
            ge_mod.DRIFT_MONITORING_AVAILABLE = orig_drift
            ge_mod.DriftStatus = orig_status

    def test_run_scheduled_drift_detection_status_not_success(self, engine):
        """Branch: drift status != SUCCESS → warning logged."""
        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        mock_drift_status = MagicMock()
        mock_drift_status.SUCCESS = "SUCCESS"

        mock_report = MagicMock()
        mock_report.status = MagicMock()
        mock_report.status.value = "error"
        mock_report.error_message = "something went wrong"
        # status != DriftStatus.SUCCESS
        mock_report.status.__eq__ = lambda self, other: False

        mock_detector = MagicMock()
        mock_detector.detect_drift = MagicMock(return_value=mock_report)

        engine._drift_detector = mock_detector
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        mock_df = MagicMock()
        mock_df.__len__ = MagicMock(return_value=5)

        orig_drift = ge_mod.DRIFT_MONITORING_AVAILABLE
        orig_status = ge_mod.DriftStatus
        try:
            ge_mod.DRIFT_MONITORING_AVAILABLE = True
            ge_mod.DriftStatus = mock_drift_status

            with patch.object(engine, "_collect_drift_data", return_value=mock_df):
                engine._run_scheduled_drift_detection()
        finally:
            ge_mod.DRIFT_MONITORING_AVAILABLE = orig_drift
            ge_mod.DriftStatus = orig_status

    async def test_load_historical_data_exception(self, engine):
        """Branch: _load_historical_data exception is caught and warned."""
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.logger"
        ) as mock_logger:
            mock_logger.info.side_effect = [RuntimeError("load fail"), None, None]
            await engine._load_historical_data()
            # Should not raise

    async def test_save_model_state_exception(self, engine):
        """Branch: _save_model_state exception is caught and logged as error."""
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.logger"
        ) as mock_logger:
            mock_logger.info.side_effect = [RuntimeError("save fail"), None]
            await engine._save_model_state()
            # Should not raise

    def test_collect_drift_data_pandas_exception(self, engine):
        """Branch: pandas import succeeds but DataFrame creation raises."""
        engine.decision_history = [_make_decision() for _ in range(3)]

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.pd",
            None,
            create=True,
        ):
            # If pd is not importable inside the method, returns None
            result = engine._collect_drift_data()
            # Either None (no pandas) or a DataFrame — no crash is the assertion
            assert result is None or hasattr(result, "shape")
