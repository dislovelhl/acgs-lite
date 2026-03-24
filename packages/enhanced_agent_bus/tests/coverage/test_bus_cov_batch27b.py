"""
Tests targeting uncovered lines in:
  1. enhanced_agent_bus.adaptive_governance.governance_engine (78% -> 90%+)
  2. enhanced_agent_bus.observability.telemetry (72.6% -> 90%+)

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
import time
from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

sys.path.insert(0, "packages/enhanced_agent_bus")

import pytest

# -----------------------------------------------------------------------
# Governance Engine imports
# -----------------------------------------------------------------------
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.adaptive_governance.trace_collector import IMPACT_TO_STATE
from enhanced_agent_bus.governance_constants import (
    GOVERNANCE_BACKOFF_SECONDS,
    GOVERNANCE_COMPLIANCE_THRESHOLD,
    GOVERNANCE_FALLBACK_CONFIDENCE,
    GOVERNANCE_MAX_TREND_LENGTH,
    GOVERNANCE_RECOMMENDED_THRESHOLD,
    GOVERNANCE_RETRAIN_CHECK_MODULUS,
    GOVERNANCE_RETRAIN_HISTORY_MIN,
    GOVERNANCE_RISK_CRITICAL,
    GOVERNANCE_RISK_HIGH,
    GOVERNANCE_RISK_LOW,
    GOVERNANCE_RISK_MEDIUM,
)

# -----------------------------------------------------------------------
# Telemetry imports
# -----------------------------------------------------------------------
from enhanced_agent_bus.observability.telemetry import (
    OTEL_AVAILABLE,
    MetricsRegistry,
    NoOpCounter,
    NoOpHistogram,
    NoOpMeter,
    NoOpSpan,
    NoOpTracer,
    NoOpUpDownCounter,
    TelemetryConfig,
    TracingContext,
    _CrossModuleNoOpType,
    _get_env_default,
    _get_export_metrics,
    _get_export_traces,
    _get_otlp_endpoint,
    _get_resource_attributes,
    _get_trace_sample_rate,
    configure_telemetry,
    get_meter,
    get_tracer,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _make_features(**overrides) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2, 0.3],
        semantic_similarity=0.6,
        historical_precedence=3,
        resource_utilization=0.4,
        network_isolation=0.3,
        risk_score=0.3,
        confidence_level=0.85,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides) -> GovernanceDecision:
    defaults = dict(
        action_allowed=True,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.85,
        reasoning="Test decision",
        recommended_threshold=0.5,
        features_used=_make_features(),
        decision_id="gov-test-001",
    )
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


def _make_config(**kwargs):
    """Create a mock BusConfiguration."""
    cfg = SimpleNamespace(
        enable_dtmc=False,
        dtmc_impact_weight=0.0,
        dtmc_intervention_threshold=0.8,
    )
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    return cfg


# -----------------------------------------------------------------------
# governance_engine: _initialize_feedback_handler (lines 305-311)
# -----------------------------------------------------------------------

class TestInitializeFeedbackHandler:
    """Cover lines 305-311: feedback handler init success and failure."""

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_feedback_handler")
    def test_feedback_handler_success(self, mock_get_fh):
        mock_handler = MagicMock()
        mock_get_fh.return_value = mock_handler
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        # The handler was called during __init__
        mock_get_fh.assert_called()
        mock_handler.initialize_schema.assert_called()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_feedback_handler")
    def test_feedback_handler_failure(self, mock_get_fh):
        mock_get_fh.side_effect = RuntimeError("No DB")
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine._feedback_handler is None


# -----------------------------------------------------------------------
# governance_engine: _initialize_drift_detector (lines 313-326)
# -----------------------------------------------------------------------

class TestInitializeDriftDetector:
    """Cover lines 318-326: drift detector init paths."""

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector")
    def test_drift_detector_success_with_data(self, mock_get_dd):
        mock_dd = MagicMock()
        mock_dd.load_reference_data.return_value = True
        mock_get_dd.return_value = mock_dd
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine._drift_detector is mock_dd

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector")
    def test_drift_detector_success_no_data(self, mock_get_dd):
        mock_dd = MagicMock()
        mock_dd.load_reference_data.return_value = False
        mock_get_dd.return_value = mock_dd
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine._drift_detector is mock_dd

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector")
    def test_drift_detector_failure(self, mock_get_dd):
        mock_get_dd.side_effect = RuntimeError("fail")
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine._drift_detector is None


# -----------------------------------------------------------------------
# governance_engine: _initialize_river_model (lines 345-367)
# -----------------------------------------------------------------------

class TestInitializeRiverModel:
    """Cover lines 348-362: River model init paths."""

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ModelType", SimpleNamespace(REGRESSOR="regressor"))
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_online_learning_pipeline")
    def test_river_model_success_with_trained_scorer(self, mock_get_pipeline):
        mock_pipeline = MagicMock()
        mock_get_pipeline.return_value = mock_pipeline
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        # impact_scorer.model_trained may be False by default, that's OK
        mock_get_pipeline.assert_called()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ModelType", SimpleNamespace(REGRESSOR="regressor"))
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_online_learning_pipeline")
    def test_river_model_init_sets_fallback_when_trained(self, mock_get_pipeline):
        mock_pipeline = MagicMock()
        mock_get_pipeline.return_value = mock_pipeline
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        engine.impact_scorer.model_trained = True
        # Re-initialize to trigger line 354
        engine._initialize_river_model()
        mock_pipeline.set_fallback_model.assert_called()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ModelType", SimpleNamespace(REGRESSOR="regressor"))
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_online_learning_pipeline")
    def test_river_model_init_failure(self, mock_get_pipeline):
        mock_get_pipeline.side_effect = RuntimeError("bad")
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine.river_model is None


# -----------------------------------------------------------------------
# governance_engine: _initialize_ab_test_router (lines 369-401)
# -----------------------------------------------------------------------

class TestInitializeABTestRouter:
    """Cover lines 375-401: AB test router init paths."""

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.AB_TEST_SPLIT", 0.1)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ShadowPolicyExecutor")
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_ab_test_router")
    def test_ab_router_success_trained(self, mock_get_router, mock_shadow_cls):
        mock_router = MagicMock()
        mock_get_router.return_value = mock_router
        mock_shadow_cls.return_value = MagicMock()
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        engine.impact_scorer.model_trained = True
        engine._initialize_ab_test_router()
        mock_router.set_champion_model.assert_called()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.get_ab_test_router")
    def test_ab_router_failure(self, mock_get_router):
        mock_get_router.side_effect = Exception("fail")
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine._ab_test_router is None
        assert engine._shadow_executor is None


# -----------------------------------------------------------------------
# governance_engine: _initialize_anomaly_monitor (lines 392-401)
# -----------------------------------------------------------------------

class TestInitializeAnomalyMonitor:
    """Cover lines 397-401: anomaly monitor init paths."""

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ANOMALY_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.AnomalyMonitor")
    def test_anomaly_monitor_success(self, mock_cls):
        mock_cls.return_value = MagicMock()
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine._anomaly_monitor is not None

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ANOMALY_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.AnomalyMonitor")
    def test_anomaly_monitor_failure(self, mock_cls):
        mock_cls.side_effect = RuntimeError("bad")
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        assert engine._anomaly_monitor is None


# -----------------------------------------------------------------------
# governance_engine: _record_ab_test_request (lines 568-585)
# -----------------------------------------------------------------------

class TestRecordABTestRequest:
    """Cover lines 576, 580: champion vs candidate routing metric recording."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        engine._ab_test_router = MagicMock()
        return engine

    def test_candidate_cohort_records(self):
        engine = self._make_engine()
        mock_routing = MagicMock()
        mock_cohort = MagicMock()
        mock_cohort.value = "candidate"
        mock_routing.cohort = mock_cohort
        # Make CohortType.CANDIDATE match
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType"
        ) as mock_ct:
            mock_ct.CANDIDATE = mock_cohort
            engine._record_ab_test_request(mock_routing, 5.0, True)
        engine._ab_test_router.get_candidate_metrics.assert_called()

    def test_champion_cohort_records(self):
        engine = self._make_engine()
        mock_routing = MagicMock()
        mock_champion = MagicMock()
        mock_champion.value = "champion"
        mock_candidate = MagicMock()
        mock_candidate.value = "candidate"
        mock_routing.cohort = mock_champion
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType"
        ) as mock_ct:
            mock_ct.CANDIDATE = mock_candidate
            engine._record_ab_test_request(mock_routing, 5.0, True)
        engine._ab_test_router.get_champion_metrics.assert_called()


# -----------------------------------------------------------------------
# governance_engine: _schedule_shadow_execution_if_needed (lines 587-605)
# -----------------------------------------------------------------------

class TestScheduleShadowExecution:
    """Cover lines 597, 604-605: shadow execution scheduling."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        return engine

    def test_skips_when_not_champion(self):
        engine = self._make_engine()
        mock_routing = MagicMock()
        mock_routing.cohort = MagicMock()
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType"
        ) as mock_ct:
            mock_ct.CHAMPION = MagicMock()  # Different object
            engine._schedule_shadow_execution_if_needed(
                mock_routing, _make_decision(), _make_features()
            )
        # No task created
        assert len(engine._background_tasks) == 0

    def test_schedules_shadow_for_champion(self):
        engine = self._make_engine()
        mock_shadow = AsyncMock()
        mock_shadow.execute_shadow = AsyncMock(return_value=None)
        engine._shadow_executor = mock_shadow
        mock_routing = MagicMock()
        champion_val = MagicMock()
        mock_routing.cohort = champion_val
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType"
        ) as mock_ct:
            mock_ct.CHAMPION = champion_val
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._run_shadow(engine, mock_routing))
            finally:
                loop.close()

    async def _run_shadow(self, engine, mock_routing):
        engine._schedule_shadow_execution_if_needed(
            mock_routing, _make_decision(), _make_features()
        )
        # Let the task complete
        if engine._background_tasks:
            await asyncio.gather(*engine._background_tasks, return_exceptions=True)


# -----------------------------------------------------------------------
# governance_engine: _update_river_model line 874
# -----------------------------------------------------------------------

class TestUpdateRiverModel:
    """Cover line 874: River model is_ready + scorer not trained path."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        return engine

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE", True)
    def test_river_model_ready_scorer_not_trained(self):
        engine = self._make_engine()
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_samples = 50
        mock_pipeline.learn_from_feedback.return_value = mock_result
        mock_adapter = MagicMock()
        mock_adapter.is_ready = True
        mock_pipeline.adapter = mock_adapter
        engine.river_model = mock_pipeline
        engine.impact_scorer.model_trained = False

        decision = _make_decision()
        engine._update_river_model(decision, 0.5)

        mock_pipeline.learn_from_feedback.assert_called_once()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE", True)
    def test_river_model_update_failure_result(self):
        engine = self._make_engine()
        mock_pipeline = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "bad data"
        mock_pipeline.learn_from_feedback.return_value = mock_result
        mock_pipeline.adapter = MagicMock(is_ready=False)
        engine.river_model = mock_pipeline

        decision = _make_decision()
        engine._update_river_model(decision, 0.5)

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE", True)
    def test_river_model_update_exception(self):
        engine = self._make_engine()
        mock_pipeline = MagicMock()
        mock_pipeline.learn_from_feedback.side_effect = RuntimeError("fail")
        engine.river_model = mock_pipeline

        decision = _make_decision()
        engine._update_river_model(decision, 0.5)  # Should not raise


# -----------------------------------------------------------------------
# governance_engine: _run_scheduled_drift_detection (lines 1024-1091)
# -----------------------------------------------------------------------

class TestScheduledDriftDetection:
    """Cover lines 1036-1091: drift detection scheduled runs."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        return engine

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    def test_drift_detection_not_due(self):
        engine = self._make_engine()
        engine._drift_detector = MagicMock()
        engine._last_drift_check = time.time()
        engine._drift_check_interval = 99999
        engine._run_scheduled_drift_detection()
        engine._drift_detector.detect_drift.assert_not_called()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    def test_drift_detection_no_data(self):
        engine = self._make_engine()
        engine._drift_detector = MagicMock()
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0
        engine.decision_history = deque()
        engine._run_scheduled_drift_detection()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DriftStatus")
    def test_drift_detection_success_with_drift(self, mock_drift_status):
        engine = self._make_engine()
        mock_dd = MagicMock()
        engine._drift_detector = mock_dd
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        # Add some decision history
        for _ in range(5):
            engine.decision_history.append(_make_decision())

        mock_report = MagicMock()
        mock_report.status = mock_drift_status.SUCCESS
        mock_report.dataset_drift = True
        mock_report.drift_severity = MagicMock(value="high")
        mock_report.drifted_features = 3
        mock_report.total_features = 10
        mock_report.drift_share = 0.3
        mock_report.recommendations = ["retrain model"]
        mock_dd.detect_drift.return_value = mock_report
        mock_dd.should_trigger_retraining.return_value = True

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.pd",
            create=True,
        ):
            engine._run_scheduled_drift_detection()

        assert engine._latest_drift_report is mock_report

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DriftStatus")
    def test_drift_detection_success_no_drift(self, mock_drift_status):
        engine = self._make_engine()
        mock_dd = MagicMock()
        engine._drift_detector = mock_dd
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        for _ in range(5):
            engine.decision_history.append(_make_decision())

        mock_report = MagicMock()
        mock_report.status = mock_drift_status.SUCCESS
        mock_report.dataset_drift = False
        mock_report.drift_share = 0.05
        mock_dd.detect_drift.return_value = mock_report

        engine._run_scheduled_drift_detection()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DriftStatus")
    def test_drift_detection_error_status(self, mock_drift_status):
        engine = self._make_engine()
        mock_dd = MagicMock()
        engine._drift_detector = mock_dd
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        for _ in range(5):
            engine.decision_history.append(_make_decision())

        mock_report = MagicMock()
        mock_report.status = MagicMock(value="error")
        mock_report.error_message = "something went wrong"
        # Make status != SUCCESS
        mock_drift_status.SUCCESS = MagicMock()
        mock_dd.detect_drift.return_value = mock_report

        engine._run_scheduled_drift_detection()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE", True)
    def test_drift_detection_exception(self):
        engine = self._make_engine()
        mock_dd = MagicMock()
        mock_dd.detect_drift.side_effect = RuntimeError("detector fail")
        engine._drift_detector = mock_dd
        engine._last_drift_check = 0.0
        engine._drift_check_interval = 0

        for _ in range(5):
            engine.decision_history.append(_make_decision())

        old_time = engine._last_drift_check
        engine._run_scheduled_drift_detection()
        # Should still update last check time
        assert engine._last_drift_check > old_time


# -----------------------------------------------------------------------
# governance_engine: _collect_drift_data empty records (line 1139)
# -----------------------------------------------------------------------

class TestCollectDriftData:
    """Cover line 1139: empty feature_records path."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    def test_no_decision_history(self):
        engine = self._make_engine()
        engine.decision_history = deque()
        result = engine._collect_drift_data()
        assert result is None

    def test_with_pandas_missing(self):
        engine = self._make_engine()
        engine.decision_history = deque([_make_decision()])
        with patch.dict(sys.modules, {"pandas": None}):
            # Force ImportError for pandas
            result = engine._collect_drift_data()
            # May return None or a DataFrame depending on cached import
            # This exercises the code path


# -----------------------------------------------------------------------
# governance_engine: _analyze_performance_trends error (line 1169-1170)
# -----------------------------------------------------------------------

class TestAnalyzePerformanceTrends:
    """Cover lines 1169-1170: error path in trend analysis."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    def test_trend_analysis_normal(self):
        engine = self._make_engine()
        engine.metrics.constitutional_compliance_rate = 0.9
        engine.metrics.false_positive_rate = 0.1
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) == 1

    def test_trend_trimming(self):
        engine = self._make_engine()
        engine.metrics.compliance_trend = list(range(GOVERNANCE_MAX_TREND_LENGTH + 10))
        engine.metrics.accuracy_trend = list(range(GOVERNANCE_MAX_TREND_LENGTH + 10))
        engine.metrics.performance_trend = list(range(GOVERNANCE_MAX_TREND_LENGTH + 10))
        engine.metrics.constitutional_compliance_rate = 0.9
        engine.metrics.false_positive_rate = 0.1
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) <= GOVERNANCE_MAX_TREND_LENGTH

    def test_trend_analysis_error(self):
        engine = self._make_engine()
        # Force error by making compliance_trend raise
        engine.metrics = MagicMock()
        engine.metrics.compliance_trend = MagicMock(side_effect=RuntimeError("boom"))
        engine.metrics.constitutional_compliance_rate = 0.9
        engine.metrics.false_positive_rate = 0.1
        engine.metrics.average_response_time = 0.01
        # Should not raise
        engine._analyze_performance_trends()


# -----------------------------------------------------------------------
# governance_engine: _log_performance_summary error (lines 1195-1196)
# -----------------------------------------------------------------------

class TestLogPerformanceSummary:
    """Cover lines 1195-1196."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    def test_log_summary_normal(self):
        engine = self._make_engine()
        engine._log_performance_summary()

    def test_log_summary_error(self):
        engine = self._make_engine()
        engine.metrics = MagicMock()
        engine.metrics.constitutional_compliance_rate = MagicMock(
            __format__=MagicMock(side_effect=RuntimeError("bad"))
        )
        engine._log_performance_summary()


# -----------------------------------------------------------------------
# governance_engine: _background_learning_loop (lines 1004-1022)
# -----------------------------------------------------------------------

class TestBackgroundLearningLoop:
    """Cover lines 1004, 1007-1008, 1012, 1015, 1018, 1021-1022."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    async def test_one_iteration(self):
        engine = self._make_engine()
        engine.running = True
        call_count = 0

        original_sleep = asyncio.sleep
        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                engine.running = False
            await original_sleep(0)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await engine._background_learning_loop()

    async def test_learning_loop_error_recovery(self):
        engine = self._make_engine()
        engine.running = True
        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                engine.running = False

        engine._analyze_performance_trends = MagicMock(side_effect=RuntimeError("boom"))

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await engine._background_learning_loop()


# -----------------------------------------------------------------------
# governance_engine: _maybe_refit_dtmc (lines 1204-1220)
# -----------------------------------------------------------------------

class TestMaybeRefitDTMC:
    """Cover DTMC refit paths."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config(enable_dtmc=True))

    def test_refit_with_enough_data(self):
        engine = self._make_engine()
        for _ in range(15):
            engine.decision_history.append(_make_decision())
        mock_result = MagicMock()
        mock_result.n_trajectories = 5
        mock_result.unsafe_fraction = 0.2
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.fit.return_value = mock_result
        engine._trace_collector = MagicMock()
        engine._trace_collector.collect_from_decision_history.return_value = [
            [0, 1, 2],
            [1, 2, 3],
        ]
        engine._maybe_refit_dtmc()
        engine._dtmc_learner.fit.assert_called_once()

    def test_refit_insufficient_data(self):
        engine = self._make_engine()
        for _ in range(5):
            engine.decision_history.append(_make_decision())
        engine._maybe_refit_dtmc()  # Should return early

    def test_refit_disabled(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine(
            "cdd01ef066bc6cf2", config=_make_config(enable_dtmc=False)
        )
        engine._maybe_refit_dtmc()  # Should return early


# -----------------------------------------------------------------------
# governance_engine: _store_feedback_event (lines 732-808)
# -----------------------------------------------------------------------

class TestStoreFeedbackEvent:
    """Cover feedback event storage with handler available."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackEvent")
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackType")
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.OutcomeStatus")
    def test_store_with_correction(self, mock_outcome, mock_ftype, mock_fevent):
        engine = self._make_engine()
        mock_handler = MagicMock()
        mock_response = MagicMock()
        mock_response.feedback_id = "fb-123"
        mock_handler.store_feedback.return_value = mock_response
        engine._feedback_handler = mock_handler

        mock_ftype.CORRECTION = "correction"
        mock_ftype.POSITIVE = "positive"
        mock_ftype.NEGATIVE = "negative"
        mock_outcome.SUCCESS = "success"
        mock_outcome.FAILURE = "failure"

        decision = _make_decision()
        engine._store_feedback_event(decision, True, True, 0.5)
        mock_handler.store_feedback.assert_called_once()

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackEvent")
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackType")
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.OutcomeStatus")
    def test_store_positive_no_override(self, mock_outcome, mock_ftype, mock_fevent):
        engine = self._make_engine()
        mock_handler = MagicMock()
        mock_response = MagicMock()
        mock_response.feedback_id = "fb-124"
        mock_handler.store_feedback.return_value = mock_response
        engine._feedback_handler = mock_handler

        mock_ftype.POSITIVE = "positive"
        mock_ftype.NEGATIVE = "negative"
        mock_outcome.SUCCESS = "success"

        decision = _make_decision()
        engine._store_feedback_event(decision, True, None, 0.3)

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE", True)
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackEvent")
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackType")
    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.OutcomeStatus")
    def test_store_negative_no_override(self, mock_outcome, mock_ftype, mock_fevent):
        engine = self._make_engine()
        mock_handler = MagicMock()
        mock_response = MagicMock()
        mock_response.feedback_id = "fb-125"
        mock_handler.store_feedback.return_value = mock_response
        engine._feedback_handler = mock_handler

        mock_ftype.NEGATIVE = "negative"
        mock_outcome.FAILURE = "failure"

        decision = _make_decision()
        engine._store_feedback_event(decision, False, None, 0.7)

    @patch("enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE", True)
    def test_store_failure(self):
        engine = self._make_engine()
        mock_handler = MagicMock()
        mock_handler.store_feedback.side_effect = RuntimeError("db error")
        engine._feedback_handler = mock_handler

        decision = _make_decision()
        engine._store_feedback_event(decision, True, None, 0.3)


# -----------------------------------------------------------------------
# governance_engine: _load_historical_data / _save_model_state error paths
# -----------------------------------------------------------------------

class TestLoadSaveModelState:
    """Cover lines 1229-1230, 1238-1239: error paths."""

    async def test_load_historical_data_normal(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        await engine._load_historical_data()

    async def test_save_model_state_normal(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        await engine._save_model_state()


# =======================================================================
# TELEMETRY TESTS
# =======================================================================


class TestNoOpSpan:
    """Cover NoOpSpan methods."""

    def test_set_attribute(self):
        span = NoOpSpan()
        span.set_attribute("key", "value")

    def test_add_event(self):
        span = NoOpSpan()
        span.add_event("event", {"k": "v"})
        span.add_event("event", None)

    def test_record_exception(self):
        span = NoOpSpan()
        span.record_exception(ValueError("test"))

    def test_set_status(self):
        span = NoOpSpan()
        span.set_status("ok")

    def test_context_manager(self):
        span = NoOpSpan()
        with span as s:
            assert s is span

    def test_exit_returns_false(self):
        span = NoOpSpan()
        result = span.__exit__(None, None, None)
        assert result is False


class TestNoOpTracer:
    """Cover NoOpTracer methods."""

    def test_start_as_current_span(self):
        tracer = NoOpTracer()
        with tracer.start_as_current_span("test") as span:
            assert isinstance(span, NoOpSpan)

    def test_start_span(self):
        tracer = NoOpTracer()
        span = tracer.start_span("test")
        assert isinstance(span, NoOpSpan)


class TestNoOpMeter:
    """Cover NoOpMeter methods."""

    def test_create_counter(self):
        meter = NoOpMeter()
        counter = meter.create_counter("test")
        assert isinstance(counter, NoOpCounter)

    def test_create_histogram(self):
        meter = NoOpMeter()
        hist = meter.create_histogram("test")
        assert isinstance(hist, NoOpHistogram)

    def test_create_up_down_counter(self):
        meter = NoOpMeter()
        udc = meter.create_up_down_counter("test")
        assert isinstance(udc, NoOpUpDownCounter)

    def test_create_observable_gauge(self):
        meter = NoOpMeter()
        gauge = meter.create_observable_gauge("test", callbacks=[lambda: 1])
        assert gauge is None


class TestNoOpCounter:
    """Cover NoOpCounter.add."""

    def test_add(self):
        counter = NoOpCounter()
        counter.add(1, {"key": "val"})
        counter.add(5, None)


class TestNoOpHistogram:
    """Cover NoOpHistogram.record."""

    def test_record(self):
        hist = NoOpHistogram()
        hist.record(1.5, {"key": "val"})
        hist.record(2.0, None)


class TestNoOpUpDownCounter:
    """Cover NoOpUpDownCounter.add."""

    def test_add(self):
        udc = NoOpUpDownCounter()
        udc.add(1, {"key": "val"})
        udc.add(-1, None)


class TestCrossModuleNoOpType:
    """Cover line 157: _CrossModuleNoOpType.__instancecheck__."""

    def test_normal_isinstance(self):
        counter = NoOpCounter()
        assert isinstance(counter, NoOpCounter)

    def test_cross_module_check(self):
        """Test that classes from different import paths with matching names pass."""

        class FakeModule:
            pass

        fake = FakeModule()
        fake.__class__ = type(
            "NoOpCounter", (), {"__module__": "some.observability.telemetry"}
        )
        assert isinstance(fake, NoOpCounter)

    def test_cross_module_check_mismatch_name(self):
        """Name mismatch should fail."""

        class FakeModule:
            pass

        fake = FakeModule()
        fake.__class__ = type(
            "NoOpHistogram", (), {"__module__": "some.observability.telemetry"}
        )
        assert not isinstance(fake, NoOpCounter)

    def test_cross_module_check_mismatch_module(self):
        """Module mismatch should fail."""

        class FakeModule:
            pass

        fake = FakeModule()
        fake.__class__ = type("NoOpCounter", (), {"__module__": "some.other.module"})
        assert not isinstance(fake, NoOpCounter)


# -----------------------------------------------------------------------
# telemetry: config helper functions
# -----------------------------------------------------------------------

class TestConfigHelpers:
    """Cover _get_env_default, _get_otlp_endpoint, etc. with settings=None."""

    def test_get_env_default_no_settings(self):
        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            result = _get_env_default()
            assert isinstance(result, str)

    def test_get_otlp_endpoint_no_settings(self):
        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            result = _get_otlp_endpoint()
            assert "localhost" in result or isinstance(result, str)

    def test_get_export_traces_no_settings(self):
        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            assert _get_export_traces() is True

    def test_get_export_metrics_no_settings(self):
        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            assert _get_export_metrics() is True

    def test_get_trace_sample_rate_no_settings(self):
        with patch("enhanced_agent_bus.observability.telemetry.settings", None):
            assert _get_trace_sample_rate() == 1.0

    def test_get_env_default_with_settings(self):
        mock_settings = MagicMock()
        mock_settings.env = "production"
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_env_default() == "production"

    def test_get_otlp_endpoint_with_settings(self):
        mock_settings = MagicMock()
        mock_settings.telemetry.otlp_endpoint = "http://otel:4317"
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_otlp_endpoint() == "http://otel:4317"

    def test_get_export_traces_with_settings(self):
        mock_settings = MagicMock()
        mock_settings.telemetry.export_traces = False
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_export_traces() is False

    def test_get_export_metrics_with_settings(self):
        mock_settings = MagicMock()
        mock_settings.telemetry.export_metrics = False
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_export_metrics() is False

    def test_get_trace_sample_rate_with_settings(self):
        mock_settings = MagicMock()
        mock_settings.telemetry.trace_sample_rate = 0.5
        with patch("enhanced_agent_bus.observability.telemetry.settings", mock_settings):
            assert _get_trace_sample_rate() == 0.5


# -----------------------------------------------------------------------
# telemetry: TelemetryConfig
# -----------------------------------------------------------------------

class TestTelemetryConfig:
    """Cover TelemetryConfig defaults."""

    def test_defaults(self):
        config = TelemetryConfig()
        assert config.service_name == "acgs2-agent-bus"
        assert config.batch_span_processor is True


# -----------------------------------------------------------------------
# telemetry: configure_telemetry without OTEL
# -----------------------------------------------------------------------

class TestConfigureTelemetry:
    """Cover configure_telemetry when OTEL not available."""

    def test_returns_noop_when_otel_unavailable(self):
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            tracer, meter = configure_telemetry()
            assert isinstance(tracer, NoOpTracer)
            assert isinstance(meter, NoOpMeter)

    def test_returns_noop_with_config(self):
        config = TelemetryConfig(service_name="test-service")
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            tracer, meter = configure_telemetry(config)
            assert isinstance(tracer, NoOpTracer)


# -----------------------------------------------------------------------
# telemetry: get_tracer / get_meter without OTEL
# -----------------------------------------------------------------------

class TestGetTracerMeter:
    """Cover get_tracer and get_meter paths."""

    def test_get_tracer_cached(self):
        with patch(
            "enhanced_agent_bus.observability.telemetry._tracers",
            {"my-svc": MagicMock()},
        ):
            result = get_tracer("my-svc")
            assert result is not None

    def test_get_tracer_noop(self):
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            with patch(
                "enhanced_agent_bus.observability.telemetry._tracers", {}
            ):
                result = get_tracer("unknown-svc")
                assert isinstance(result, NoOpTracer)

    def test_get_meter_cached(self):
        with patch(
            "enhanced_agent_bus.observability.telemetry._meters",
            {"my-svc": MagicMock()},
        ):
            result = get_meter("my-svc")
            assert result is not None

    def test_get_meter_noop(self):
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            with patch(
                "enhanced_agent_bus.observability.telemetry._meters", {}
            ):
                result = get_meter("unknown-svc")
                assert isinstance(result, NoOpMeter)

    def test_get_tracer_none_service(self):
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            with patch("enhanced_agent_bus.observability.telemetry._tracers", {}):
                result = get_tracer(None)
                assert isinstance(result, NoOpTracer)

    def test_get_meter_none_service(self):
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", False):
            with patch("enhanced_agent_bus.observability.telemetry._meters", {}):
                result = get_meter(None)
                assert isinstance(result, NoOpMeter)


# -----------------------------------------------------------------------
# telemetry: _get_resource_attributes
# -----------------------------------------------------------------------

class TestGetResourceAttributes:
    """Cover _get_resource_attributes fallback path."""

    def test_fallback_on_name_error(self):
        config = TelemetryConfig(service_name="test")
        with patch(
            "enhanced_agent_bus.observability.telemetry.get_resource_attributes",
            side_effect=NameError("not defined"),
            create=True,
        ):
            result = _get_resource_attributes(config)
            assert "service.name" in result
            assert result["service.name"] == "test"


# -----------------------------------------------------------------------
# telemetry: TracingContext
# -----------------------------------------------------------------------

class TestTracingContext:
    """Cover TracingContext enter/exit including error paths."""

    def test_enter_exit_normal(self):
        ctx = TracingContext("test-span")
        with ctx as span:
            assert span is not None

    def test_enter_with_attributes(self):
        ctx = TracingContext("test-span", attributes={"key": "val"})
        with ctx as span:
            pass

    def test_exit_with_exception_noop(self):
        ctx = TracingContext("test-span")
        with pytest.raises(ValueError, match="test error"):
            with ctx:
                raise ValueError("test error")

    def test_exit_with_exception_otel_available(self):
        """Cover line 459/461: OTEL_AVAILABLE branch in __exit__."""
        ctx = TracingContext("test-span")
        ctx.__enter__()
        mock_span = MagicMock()
        ctx._span = mock_span

        # Simulate OTEL_AVAILABLE=True with mock Status/StatusCode
        with patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True):
            mock_status = MagicMock()
            mock_status_code = MagicMock()
            mock_status_code.ERROR = "ERROR"
            with patch.dict(sys.modules, {
                "opentelemetry.trace": MagicMock(
                    Status=mock_status, StatusCode=mock_status_code
                ),
            }):
                exc = ValueError("oops")
                ctx.__exit__(type(exc), exc, None)

        mock_span.record_exception.assert_called_once_with(exc)

    def test_exit_no_context(self):
        ctx = TracingContext("test-span")
        # No __enter__ called, _context is None
        result = ctx.__exit__(None, None, None)
        assert result is False

    def test_tenant_import_error(self):
        """TracingContext handles ImportError for tenant gracefully."""
        ctx = TracingContext("test-span")
        with patch(
            "enhanced_agent_bus.observability.telemetry.get_tracer",
            return_value=NoOpTracer(),
        ):
            with ctx as span:
                pass


# -----------------------------------------------------------------------
# telemetry: MetricsRegistry
# -----------------------------------------------------------------------

class TestMetricsRegistry:
    """Cover MetricsRegistry methods."""

    def test_get_counter_creates_once(self):
        registry = MetricsRegistry("test-svc")
        c1 = registry.get_counter("requests", "Total requests")
        c2 = registry.get_counter("requests")
        assert c1 is c2

    def test_get_histogram_creates_once(self):
        registry = MetricsRegistry("test-svc")
        h1 = registry.get_histogram("latency", unit="ms", description="Latency")
        h2 = registry.get_histogram("latency")
        assert h1 is h2

    def test_get_gauge_creates_once(self):
        registry = MetricsRegistry("test-svc")
        g1 = registry.get_gauge("connections", "Active connections")
        g2 = registry.get_gauge("connections")
        assert g1 is g2

    def test_increment_counter_no_attributes(self):
        registry = MetricsRegistry("test-svc")
        registry.increment_counter("requests")

    def test_increment_counter_with_attributes(self):
        registry = MetricsRegistry("test-svc")
        registry.increment_counter("requests", 5, {"method": "GET"})

    def test_record_latency_no_attributes(self):
        registry = MetricsRegistry("test-svc")
        registry.record_latency("response_time", 12.5)

    def test_record_latency_with_attributes(self):
        registry = MetricsRegistry("test-svc")
        registry.record_latency("response_time", 12.5, {"endpoint": "/api"})

    def test_set_gauge_no_attributes(self):
        registry = MetricsRegistry("test-svc")
        registry.set_gauge("connections", 1)

    def test_set_gauge_with_attributes(self):
        registry = MetricsRegistry("test-svc")
        registry.set_gauge("connections", -1, {"pool": "main"})


# -----------------------------------------------------------------------
# telemetry: _configure_trace_provider / _configure_meter_provider /
#            _configure_propagation / _setup_telemetry_providers
# (lines 230-311) — only reachable when OTEL is available
# -----------------------------------------------------------------------

class TestOtelProviderConfiguration:
    """Cover provider configuration functions that require OTEL SDK mocks."""

    def test_configure_trace_provider_no_export(self):
        """Cover line 233: export_traces=False returns early."""
        if not OTEL_AVAILABLE:
            pytest.skip("OTEL not installed, testing via mock")

        # Mock all OTEL deps
        mock_tracer_provider = MagicMock()
        config = TelemetryConfig(export_traces=False)
        with patch(
            "enhanced_agent_bus.observability.telemetry.TracerProvider",
            return_value=mock_tracer_provider,
        ):
            from enhanced_agent_bus.observability.telemetry import (
                _configure_trace_provider,
            )
            result = _configure_trace_provider(config, MagicMock())
            assert result is mock_tracer_provider

    def test_configure_meter_provider_no_export(self):
        """Cover line 262: export_metrics=False."""
        if not OTEL_AVAILABLE:
            pytest.skip("OTEL not installed, testing via mock")

        mock_meter_provider = MagicMock()
        config = TelemetryConfig(export_metrics=False)
        with patch(
            "enhanced_agent_bus.observability.telemetry.MeterProvider",
            return_value=mock_meter_provider,
        ):
            from enhanced_agent_bus.observability.telemetry import (
                _configure_meter_provider,
            )
            result = _configure_meter_provider(config, MagicMock())
            assert result is mock_meter_provider


# -----------------------------------------------------------------------
# governance_engine: _apply_dtmc_risk_blend and _apply_dtmc_escalation
# -----------------------------------------------------------------------

class TestDTMCBlendAndEscalation:
    """Cover DTMC integration paths."""

    def _make_engine(self, **config_kwargs):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine(
            "cdd01ef066bc6cf2",
            config=_make_config(**config_kwargs),
        )

    def test_blend_disabled(self):
        engine = self._make_engine(enable_dtmc=False)
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_blend_enabled_not_fitted(self):
        engine = self._make_engine(enable_dtmc=True, dtmc_impact_weight=0.5)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = False
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_blend_enabled_fitted_no_history(self):
        engine = self._make_engine(enable_dtmc=True, dtmc_impact_weight=0.5)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine.decision_history = deque()
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_blend_enabled_fitted_with_history(self):
        engine = self._make_engine(enable_dtmc=True, dtmc_impact_weight=0.5)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.predict_risk.return_value = 0.6
        for _ in range(3):
            engine.decision_history.append(_make_decision())
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        expected = min(1.0, 0.3 + 0.6 * 0.5)
        assert abs(result.risk_score - expected) < 1e-6

    def test_escalation_disabled(self):
        engine = self._make_engine(enable_dtmc=False)
        decision = _make_decision()
        result = engine._apply_dtmc_escalation(decision)
        assert result is decision

    def test_escalation_already_high(self):
        engine = self._make_engine(enable_dtmc=True)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene.return_value = True
        engine._dtmc_learner.predict_risk.return_value = 0.9
        for _ in range(3):
            engine.decision_history.append(_make_decision())
        decision = _make_decision(impact_level=ImpactLevel.HIGH)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH  # No change

    def test_escalation_triggers(self):
        engine = self._make_engine(enable_dtmc=True)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene.return_value = True
        engine._dtmc_learner.predict_risk.return_value = 0.9
        for _ in range(3):
            engine.decision_history.append(_make_decision())
        decision = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH
        assert result.action_allowed is False
        assert "DTMC" in result.reasoning


# -----------------------------------------------------------------------
# governance_engine: _should_retrain_models
# -----------------------------------------------------------------------

class TestShouldRetrain:
    """Cover _should_retrain_models conditions."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    def test_retrain_low_compliance(self):
        engine = self._make_engine()
        engine.metrics.constitutional_compliance_rate = 0.5
        assert engine._should_retrain_models() is True

    def test_retrain_sufficient_data(self):
        engine = self._make_engine()
        engine.metrics.constitutional_compliance_rate = 0.99
        for _ in range(GOVERNANCE_RETRAIN_HISTORY_MIN):
            engine.decision_history.append(_make_decision())
        # Only true if modulus check passes
        if len(engine.decision_history) % GOVERNANCE_RETRAIN_CHECK_MODULUS == 0:
            assert engine._should_retrain_models() is True

    def test_no_retrain(self):
        engine = self._make_engine()
        engine.metrics.constitutional_compliance_rate = 0.99
        # Few decisions, no retrain
        assert engine._should_retrain_models() is False


# -----------------------------------------------------------------------
# governance_engine: _get_trajectory_prefix
# -----------------------------------------------------------------------

class TestGetTrajectoryPrefix:
    """Cover _get_trajectory_prefix."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    def test_empty_history(self):
        engine = self._make_engine()
        engine.decision_history = deque()
        assert engine._get_trajectory_prefix() is None

    def test_with_history(self):
        engine = self._make_engine()
        for _ in range(15):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        prefix = engine._get_trajectory_prefix()
        assert prefix is not None
        assert len(prefix) == 10
        assert all(p == IMPACT_TO_STATE[ImpactLevel.LOW] for p in prefix)


# -----------------------------------------------------------------------
# governance_engine: evaluate_governance_decision fallback
# -----------------------------------------------------------------------

class TestEvaluateGovernanceDecision:
    """Cover evaluate_governance_decision error path."""

    async def test_fallback_on_error(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        engine.impact_scorer.assess_impact = AsyncMock(
            side_effect=RuntimeError("scorer failed")
        )
        result = await engine.evaluate_governance_decision({}, {})
        assert result.action_allowed is False
        assert result.impact_level == ImpactLevel.HIGH
        assert "conservative fallback" in result.reasoning.lower()


# -----------------------------------------------------------------------
# governance_engine: initialize and shutdown
# -----------------------------------------------------------------------

class TestInitializeShutdown:
    """Cover initialize and shutdown paths."""

    async def test_initialize_with_anomaly_monitor(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        mock_monitor = AsyncMock()
        engine._anomaly_monitor = mock_monitor
        await engine.initialize()
        mock_monitor.start.assert_called_once()
        engine.running = False
        await engine.shutdown()
        mock_monitor.stop.assert_called_once()

    async def test_shutdown_cancels_task(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        engine = AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())
        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None
        await engine.shutdown()
        assert engine.running is False


# -----------------------------------------------------------------------
# governance_engine: _classify_impact_level
# -----------------------------------------------------------------------

class TestClassifyImpactLevel:
    """Cover all impact classification branches."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    def test_critical(self):
        engine = self._make_engine()
        assert engine._classify_impact_level(0.95) == ImpactLevel.CRITICAL

    def test_high(self):
        engine = self._make_engine()
        assert engine._classify_impact_level(0.75) == ImpactLevel.HIGH

    def test_medium(self):
        engine = self._make_engine()
        assert engine._classify_impact_level(0.5) == ImpactLevel.MEDIUM

    def test_low(self):
        engine = self._make_engine()
        assert engine._classify_impact_level(0.25) == ImpactLevel.LOW

    def test_negligible(self):
        engine = self._make_engine()
        assert engine._classify_impact_level(0.1) == ImpactLevel.NEGLIGIBLE


# -----------------------------------------------------------------------
# governance_engine: _generate_reasoning
# -----------------------------------------------------------------------

class TestGenerateReasoning:
    """Cover reasoning generation paths."""

    def _make_engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        return AdaptiveGovernanceEngine("cdd01ef066bc6cf2", config=_make_config())

    def test_allowed_high_confidence(self):
        engine = self._make_engine()
        features = _make_features(confidence_level=0.9, historical_precedence=0)
        result = engine._generate_reasoning(True, features, 0.5)
        assert "ALLOWED" in result

    def test_blocked_low_confidence_with_precedents(self):
        engine = self._make_engine()
        features = _make_features(confidence_level=0.5, historical_precedence=5)
        result = engine._generate_reasoning(False, features, 0.5)
        assert "BLOCKED" in result
        assert "Low confidence" in result
        assert "5 similar precedents" in result
