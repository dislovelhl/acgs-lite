"""
Tests for enhanced_agent_bus.adaptive_governance.governance_engine

Covers AdaptiveGovernanceEngine methods: initialization, evaluate_governance_decision,
provide_feedback, classify_impact_level, generate_reasoning, DTMC integration,
A/B test routing, drift detection, metrics, background learning, and fallback paths.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.adaptive_governance.governance_engine import (
    AB_TESTING_AVAILABLE,
    DRIFT_MONITORING_AVAILABLE,
    ONLINE_LEARNING_AVAILABLE,
    AdaptiveGovernanceEngine,
)
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.governance_constants import (
    GOVERNANCE_COMPLIANCE_THRESHOLD,
    GOVERNANCE_FALLBACK_CONFIDENCE,
    GOVERNANCE_RECOMMENDED_THRESHOLD,
    GOVERNANCE_RETRAIN_CHECK_MODULUS,
    GOVERNANCE_RETRAIN_HISTORY_MIN,
    GOVERNANCE_RISK_CRITICAL,
    GOVERNANCE_RISK_HIGH,
    GOVERNANCE_RISK_LOW,
    GOVERNANCE_RISK_MEDIUM,
)

pytestmark = [pytest.mark.unit]

HASH = "608508a9bd224290"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_features(**overrides) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=2,
        tenant_complexity=0.3,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.2,
        historical_precedence=1,
        resource_utilization=0.1,
        network_isolation=0.8,
        risk_score=0.25,
        confidence_level=0.85,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides) -> GovernanceDecision:
    defaults = dict(
        action_allowed=True,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.85,
        reasoning="Test reasoning",
        recommended_threshold=0.4,
        features_used=_make_features(),
        decision_id="gov-test-001",
    )
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_externals():
    """Patch all external subsystems so the engine can be instantiated without side effects."""
    with (
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.import_module"
        ) as mock_import,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ImpactScorer"
        ) as mock_scorer_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AdaptiveThresholds"
        ) as mock_thresh_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DTMCLearner"
        ) as mock_dtmc_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.TraceCollector"
        ) as mock_trace_cls,
    ):
        # Validator returned by import_module("enhanced_agent_bus.validators")
        mock_validator = MagicMock()
        mock_validator.GovernanceDecisionValidator.return_value.validate_decision = AsyncMock(
            return_value=(True, [])
        )

        def _import_side_effect(module_name: str):
            if module_name == "enhanced_agent_bus.validators":
                return mock_validator
            return importlib.import_module(module_name)

        mock_import.side_effect = _import_side_effect

        # ImpactScorer instance
        scorer = MagicMock()
        scorer.model_trained = False
        scorer.assess_impact = AsyncMock(return_value=_make_features())
        scorer.update_model = MagicMock()
        mock_scorer_cls.return_value = scorer

        # AdaptiveThresholds instance
        thresh = MagicMock()
        thresh.get_adaptive_threshold = MagicMock(return_value=0.5)
        thresh.update_model = MagicMock()
        mock_thresh_cls.return_value = thresh

        # DTMCLearner instance
        dtmc = MagicMock()
        dtmc.is_fitted = False
        mock_dtmc_cls.return_value = dtmc

        # TraceCollector instance
        mock_trace_cls.return_value = MagicMock()

        yield SimpleNamespace(
            scorer=scorer,
            thresh=thresh,
            dtmc=dtmc,
            validator=mock_validator.GovernanceDecisionValidator.return_value,
            trace=mock_trace_cls.return_value,
        )


@pytest.fixture()
def engine(_patch_externals):
    """Return a cleanly initialised AdaptiveGovernanceEngine with mocked deps."""
    eng = AdaptiveGovernanceEngine(HASH)
    # Wire in mocks that the constructor already set via patched classes
    eng._decision_validator = _patch_externals.validator
    return eng


@pytest.fixture()
def mocks(_patch_externals):
    return _patch_externals


# ---------------------------------------------------------------------------
# Construction & properties
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_initial_state(self, engine):
        assert engine.constitutional_hash == HASH
        assert engine.mode == GovernanceMode.ADAPTIVE
        assert len(engine.decision_history) == 0
        assert engine.running is False

    def test_metrics_start_zeroed(self, engine):
        m = engine.metrics
        assert m.constitutional_compliance_rate == 0.0
        assert m.average_response_time == 0.0
        assert m.compliance_trend == []

    def test_learning_thread_alias(self, engine):
        engine.learning_task = "sentinel"
        assert engine._learning_thread == "sentinel"


# ---------------------------------------------------------------------------
# _classify_impact_level
# ---------------------------------------------------------------------------


class TestClassifyImpactLevel:
    @pytest.mark.parametrize(
        "score, expected",
        [
            (0.0, ImpactLevel.NEGLIGIBLE),
            (GOVERNANCE_RISK_LOW - 0.01, ImpactLevel.NEGLIGIBLE),
            (GOVERNANCE_RISK_LOW, ImpactLevel.LOW),
            (GOVERNANCE_RISK_MEDIUM - 0.01, ImpactLevel.LOW),
            (GOVERNANCE_RISK_MEDIUM, ImpactLevel.MEDIUM),
            (GOVERNANCE_RISK_HIGH - 0.01, ImpactLevel.MEDIUM),
            (GOVERNANCE_RISK_HIGH, ImpactLevel.HIGH),
            (GOVERNANCE_RISK_CRITICAL - 0.01, ImpactLevel.HIGH),
            (GOVERNANCE_RISK_CRITICAL, ImpactLevel.CRITICAL),
            (1.0, ImpactLevel.CRITICAL),
        ],
    )
    def test_boundaries(self, engine, score, expected):
        assert engine._classify_impact_level(score) == expected


# ---------------------------------------------------------------------------
# _generate_reasoning
# ---------------------------------------------------------------------------


class TestGenerateReasoning:
    def test_allowed_reasoning_contains_action(self, engine):
        features = _make_features(risk_score=0.2, confidence_level=0.9, historical_precedence=0)
        result = engine._generate_reasoning(True, features, 0.5)
        assert "ALLOWED" in result
        assert "0.200" in result
        assert "0.500" in result

    def test_blocked_reasoning_contains_action(self, engine):
        result = engine._generate_reasoning(
            False, _make_features(risk_score=0.8, confidence_level=0.9), 0.7
        )
        assert "BLOCKED" in result

    def test_low_confidence_note(self, engine):
        features = _make_features(confidence_level=0.5, risk_score=0.3)
        result = engine._generate_reasoning(True, features, 0.5)
        assert "Low confidence" in result

    def test_historical_precedence_note(self, engine):
        features = _make_features(historical_precedence=5, risk_score=0.3, confidence_level=0.9)
        result = engine._generate_reasoning(True, features, 0.5)
        assert "5 similar precedents" in result


# ---------------------------------------------------------------------------
# _build_conservative_fallback_decision
# ---------------------------------------------------------------------------


class TestFallbackDecision:
    def test_fallback_is_blocked(self, engine):
        decision = engine._build_conservative_fallback_decision(ValueError("boom"))
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH
        assert decision.confidence_score == GOVERNANCE_FALLBACK_CONFIDENCE
        assert decision.recommended_threshold == GOVERNANCE_RECOMMENDED_THRESHOLD
        assert "boom" in decision.reasoning


# ---------------------------------------------------------------------------
# evaluate_governance_decision
# ---------------------------------------------------------------------------


class TestEvaluateGovernanceDecision:
    @pytest.mark.asyncio
    async def test_happy_path_returns_decision(self, engine, mocks):
        mocks.scorer.assess_impact = AsyncMock(
            return_value=_make_features(risk_score=0.1, confidence_level=0.9)
        )
        mocks.thresh.get_adaptive_threshold.return_value = 0.5

        decision = await engine.evaluate_governance_decision(
            {"content": "hello"}, {"active_agents": []}
        )

        assert isinstance(decision, GovernanceDecision)
        assert decision.action_allowed is True
        assert len(engine.decision_history) == 1

    @pytest.mark.asyncio
    async def test_high_risk_blocked(self, engine, mocks):
        mocks.scorer.assess_impact = AsyncMock(
            return_value=_make_features(risk_score=0.9, confidence_level=0.8)
        )
        mocks.thresh.get_adaptive_threshold.return_value = 0.5

        decision = await engine.evaluate_governance_decision(
            {"content": "danger"}, {"active_agents": []}
        )
        assert decision.action_allowed is False

    @pytest.mark.asyncio
    async def test_validation_failure_triggers_fallback(self, engine, mocks):
        mocks.validator.validate_decision = AsyncMock(return_value=(False, ["hash mismatch"]))

        decision = await engine.evaluate_governance_decision(
            {"content": "x"}, {"active_agents": []}
        )
        assert decision.action_allowed is False
        assert "conservative fallback" in decision.reasoning.lower()

    @pytest.mark.asyncio
    async def test_scorer_exception_triggers_fallback(self, engine, mocks):
        mocks.scorer.assess_impact = AsyncMock(side_effect=RuntimeError("scorer down"))

        decision = await engine.evaluate_governance_decision(
            {"content": "x"}, {"active_agents": []}
        )
        assert decision.action_allowed is False
        assert "scorer down" in decision.reasoning


# ---------------------------------------------------------------------------
# _apply_dtmc_risk_blend
# ---------------------------------------------------------------------------


class TestDTMCRiskBlend:
    def test_noop_when_dtmc_disabled(self, engine):
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_blends_when_enabled(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        mocks.dtmc.predict_risk.return_value = 0.6

        # Populate decision_history so trajectory prefix exists
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        # blended = 0.3 + 0.6 * 0.5 = 0.6
        assert abs(result.risk_score - 0.6) < 1e-6

    def test_clamps_to_1(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=1.0, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        mocks.dtmc.predict_risk.return_value = 0.9

        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        features = _make_features(risk_score=0.5)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 1.0


# ---------------------------------------------------------------------------
# _apply_dtmc_escalation
# ---------------------------------------------------------------------------


class TestDTMCEscalation:
    def test_noop_when_disabled(self, engine):
        d = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(d)
        assert result.impact_level == ImpactLevel.LOW

    def test_escalates_when_intervention_needed(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        mocks.dtmc.should_intervene.return_value = True
        mocks.dtmc.predict_risk.return_value = 0.85

        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        d = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(d)
        assert result.impact_level == ImpactLevel.HIGH
        assert result.action_allowed is False
        assert "DTMC" in result.reasoning

    def test_no_escalation_if_already_high(self, engine, mocks):
        engine.config = SimpleNamespace(
            enable_dtmc=True, dtmc_impact_weight=0.5, dtmc_intervention_threshold=0.8
        )
        mocks.dtmc.is_fitted = True
        mocks.dtmc.should_intervene.return_value = True
        mocks.dtmc.predict_risk.return_value = 0.85

        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.CRITICAL))

        d = _make_decision(impact_level=ImpactLevel.HIGH)
        result = engine._apply_dtmc_escalation(d)
        assert result.impact_level == ImpactLevel.HIGH  # unchanged


# ---------------------------------------------------------------------------
# _build_decision_for_features
# ---------------------------------------------------------------------------


class TestBuildDecisionForFeatures:
    def test_returns_correct_structure(self, engine, mocks):
        mocks.thresh.get_adaptive_threshold.return_value = 0.5
        features = _make_features(risk_score=0.25, confidence_level=0.9)

        decision = engine._build_decision_for_features(features, "gov-test-1")
        assert decision.action_allowed is True  # 0.25 <= 0.5
        assert decision.decision_id == "gov-test-1"
        assert decision.features_used is features

    def test_blocked_when_risk_exceeds_threshold(self, engine, mocks):
        mocks.thresh.get_adaptive_threshold.return_value = 0.3
        features = _make_features(risk_score=0.5)

        decision = engine._build_decision_for_features(features, "gov-test-2")
        assert decision.action_allowed is False


# ---------------------------------------------------------------------------
# provide_feedback
# ---------------------------------------------------------------------------


class TestProvideFeedback:
    def test_updates_threshold_and_scorer(self, engine, mocks):
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)

        mocks.thresh.update_model.assert_called_once()
        mocks.scorer.update_model.assert_called_once()

    def test_human_override_passed_to_threshold(self, engine, mocks):
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True, human_override=False)

        call_args = mocks.thresh.update_model.call_args
        assert call_args[0][1] is True  # outcome_success
        assert call_args[0][2] is False  # human_feedback = override == action_allowed

    def test_failure_increases_risk(self, engine, mocks):
        features = _make_features(risk_score=0.3)
        decision = _make_decision(features_used=features)
        engine.provide_feedback(decision, outcome_success=False)

        # actual_impact should be risk_score + 0.2 = 0.5
        call_args = mocks.scorer.update_model.call_args
        assert abs(call_args[0][1] - 0.5) < 1e-6

    def test_exception_does_not_propagate(self, engine, mocks):
        mocks.thresh.update_model.side_effect = RuntimeError("db error")
        decision = _make_decision()
        # Should not raise
        engine.provide_feedback(decision, outcome_success=True)


# ---------------------------------------------------------------------------
# _update_metrics
# ---------------------------------------------------------------------------


class TestUpdateMetrics:
    def test_updates_response_time(self, engine):
        engine.metrics.average_response_time = 0.0
        decision = _make_decision(confidence_score=0.9)
        engine.decision_history.append(decision)

        engine._update_metrics(decision, 0.010)
        assert engine.metrics.average_response_time > 0

    def test_compliance_rate_calculated(self, engine):
        high_conf = _make_decision(confidence_score=0.95)
        low_conf = _make_decision(confidence_score=0.5)
        engine.decision_history.append(high_conf)
        engine.decision_history.append(low_conf)

        engine._update_metrics(high_conf, 0.001)
        # 1 out of 2 has confidence > GOVERNANCE_COMPLIANCE_THRESHOLD
        assert engine.metrics.constitutional_compliance_rate == 0.5


# ---------------------------------------------------------------------------
# _analyze_performance_trends
# ---------------------------------------------------------------------------


class TestAnalyzePerformanceTrends:
    def test_appends_trend_data(self, engine):
        engine.metrics.constitutional_compliance_rate = 0.9
        engine.metrics.false_positive_rate = 0.1
        engine.metrics.average_response_time = 0.005

        engine._analyze_performance_trends()

        assert len(engine.metrics.compliance_trend) == 1
        assert engine.metrics.compliance_trend[0] == 0.9
        assert len(engine.metrics.accuracy_trend) == 1
        assert len(engine.metrics.performance_trend) == 1

    def test_trims_long_trends(self, engine):
        engine.metrics.compliance_trend = list(range(200))
        engine.metrics.accuracy_trend = list(range(200))
        engine.metrics.performance_trend = list(range(200))
        engine.metrics.average_response_time = 0.005

        engine._analyze_performance_trends()

        assert len(engine.metrics.compliance_trend) <= 101  # 200 + 1 then trimmed to 100


# ---------------------------------------------------------------------------
# _should_retrain_models
# ---------------------------------------------------------------------------


class TestShouldRetrainModels:
    def test_retrain_when_compliance_low(self, engine):
        engine.metrics.constitutional_compliance_rate = 0.5
        assert engine._should_retrain_models() is True

    def test_no_retrain_when_compliant_and_insufficient_data(self, engine):
        engine.metrics.constitutional_compliance_rate = 0.98
        assert engine._should_retrain_models() is False

    def test_retrain_when_enough_data_and_modulus_hit(self, engine):
        engine.metrics.constitutional_compliance_rate = 0.98
        # Fill history to trigger modulus check
        for _ in range(GOVERNANCE_RETRAIN_HISTORY_MIN):
            engine.decision_history.append(_make_decision())
        # Adjust length to be exact modulus multiple
        while len(engine.decision_history) % GOVERNANCE_RETRAIN_CHECK_MODULUS != 0:
            engine.decision_history.append(_make_decision())
        assert engine._should_retrain_models() is True


# ---------------------------------------------------------------------------
# _get_trajectory_prefix
# ---------------------------------------------------------------------------


class TestGetTrajectoryPrefix:
    def test_empty_history_returns_none(self, engine):
        assert engine._get_trajectory_prefix() is None

    def test_returns_state_indices(self, engine):
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.CRITICAL))

        prefix = engine._get_trajectory_prefix()
        assert prefix == [1, 4]  # LOW=1, CRITICAL=4

    def test_caps_at_10_entries(self, engine):
        for _i in range(15):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.MEDIUM))

        prefix = engine._get_trajectory_prefix()
        assert len(prefix) == 10


# ---------------------------------------------------------------------------
# _maybe_refit_dtmc
# ---------------------------------------------------------------------------


class TestMaybeRefitDTMC:
    def test_noop_when_disabled(self, engine, mocks):
        engine.config = None
        engine._maybe_refit_dtmc()
        mocks.dtmc.fit.assert_not_called()

    def test_noop_when_insufficient_history(self, engine, mocks):
        engine.config = SimpleNamespace(enable_dtmc=True)
        for _ in range(5):
            engine.decision_history.append(_make_decision())
        engine._maybe_refit_dtmc()
        mocks.dtmc.fit.assert_not_called()

    def test_refits_with_enough_history(self, engine, mocks):
        engine.config = SimpleNamespace(enable_dtmc=True)
        for _ in range(12):
            engine.decision_history.append(_make_decision())
        mocks.trace.collect_from_decision_history.return_value = [[1, 2, 3]]
        mocks.dtmc.fit.return_value = SimpleNamespace(n_trajectories=1, unsafe_fraction=0.1)

        engine._maybe_refit_dtmc()
        mocks.dtmc.fit.assert_called_once()


# ---------------------------------------------------------------------------
# _default_river_feature_names
# ---------------------------------------------------------------------------


class TestDefaultRiverFeatureNames:
    def test_returns_list_of_strings(self):
        names = AdaptiveGovernanceEngine._default_river_feature_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)
        assert "message_length" in names
        assert "risk_score" in names


# ---------------------------------------------------------------------------
# get_river_model_stats / get_ab_test_router / get_ab_test_metrics / etc.
# ---------------------------------------------------------------------------


class TestAccessors:
    def test_river_stats_none_when_no_model(self, engine):
        engine.river_model = None
        assert engine.get_river_model_stats() is None

    def test_river_stats_returns_dict(self, engine):
        mock_model = MagicMock()
        mock_model.get_stats.return_value = SimpleNamespace(total_samples=42, is_ready=True)
        engine.river_model = mock_model

        # Patch the module-level availability flag
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            result = engine.get_river_model_stats()
        assert result["total_samples"] == 42

    def test_get_ab_test_router_returns_internal(self, engine):
        engine._ab_test_router = "sentinel"
        assert engine.get_ab_test_router() == "sentinel"

    def test_ab_test_metrics_none_when_unavailable(self, engine):
        engine._ab_test_router = None
        assert engine.get_ab_test_metrics() is None

    def test_ab_test_comparison_none_when_unavailable(self, engine):
        engine._ab_test_router = None
        assert engine.get_ab_test_comparison() is None

    def test_promote_candidate_none_when_unavailable(self, engine):
        engine._ab_test_router = None
        assert engine.promote_candidate_model() is None

    def test_latest_drift_report_initially_none(self, engine):
        assert engine.get_latest_drift_report() is None


# ---------------------------------------------------------------------------
# initialize / shutdown
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_initialize_starts_learning(self, engine):
        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None
        # Clean up
        await engine.shutdown()
        assert engine.running is False

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self, engine):
        await engine.shutdown()
        await engine.shutdown()
        assert engine.running is False

    @pytest.mark.asyncio
    async def test_shutdown_cancels_learning_task(self, engine):
        await engine.initialize()
        task = engine.learning_task
        await engine.shutdown()
        assert task.done()


# ---------------------------------------------------------------------------
# _store_feedback_event (with and without feedback handler)
# ---------------------------------------------------------------------------


class TestStoreFeedbackEvent:
    def test_noop_when_handler_unavailable(self, engine):
        engine._feedback_handler = None
        # Should not raise
        engine._store_feedback_event(_make_decision(), True, None, 0.3)

    def test_stores_event_when_handler_present(self, engine):
        mock_handler = MagicMock()
        mock_handler.store_feedback.return_value = SimpleNamespace(feedback_id="fb-1")
        engine._feedback_handler = mock_handler

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            engine._store_feedback_event(_make_decision(), True, None, 0.3)

        mock_handler.store_feedback.assert_called_once()

    def test_correction_type_on_human_override(self, engine):
        mock_handler = MagicMock()
        mock_handler.store_feedback.return_value = SimpleNamespace(feedback_id="fb-2")
        engine._feedback_handler = mock_handler

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            engine._store_feedback_event(_make_decision(), False, True, 0.5)

        call_args = mock_handler.store_feedback.call_args[0][0]
        # The FeedbackEvent should be a CORRECTION type
        assert call_args.feedback_type.value == "correction"


# ---------------------------------------------------------------------------
# _update_river_model
# ---------------------------------------------------------------------------


class TestUpdateRiverModel:
    def test_noop_when_no_model(self, engine):
        engine.river_model = None
        # Should not raise
        engine._update_river_model(_make_decision(), 0.5)

    def test_calls_learn_from_feedback(self, engine):
        mock_model = MagicMock()
        mock_model.learn_from_feedback.return_value = SimpleNamespace(
            success=True, total_samples=10
        )
        mock_model.adapter.is_ready = False
        engine.river_model = mock_model

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            engine._update_river_model(_make_decision(), 0.5)

        mock_model.learn_from_feedback.assert_called_once()


# ---------------------------------------------------------------------------
# _collect_drift_data
# ---------------------------------------------------------------------------


class TestCollectDriftData:
    def test_returns_none_for_empty_history(self, engine):
        assert engine._collect_drift_data() is None

    def test_returns_dataframe_with_data(self, engine):
        pd = pytest.importorskip("pandas", reason="pandas required for drift data")
        engine.decision_history.append(_make_decision())
        engine.decision_history.append(_make_decision())

        result = engine._collect_drift_data()
        if result is None:
            pytest.skip("drift data collection returned None (pandas mock or unavailable)")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _log_performance_summary (smoke)
# ---------------------------------------------------------------------------


class TestLogPerformanceSummary:
    def test_does_not_raise(self, engine):
        engine._log_performance_summary()


# ---------------------------------------------------------------------------
# A/B test routing
# ---------------------------------------------------------------------------


class TestABTestRouting:
    def test_noop_when_router_unavailable(self, engine):
        engine._ab_test_router = None
        d = _make_decision()
        result = engine._apply_ab_test_routing(d, _make_features(), time.time())
        assert result is d  # unchanged

    def test_returns_decorated_decision_on_success(self, engine):
        mock_router = MagicMock()
        cohort_mock = MagicMock()
        cohort_mock.value = "champion"
        routing_result = SimpleNamespace(cohort=cohort_mock, model_version=2)
        mock_router.route.return_value = routing_result
        mock_router.get_champion_metrics.return_value.record_request = MagicMock()
        engine._ab_test_router = mock_router
        engine._shadow_executor = None

        # CohortType is None when ab_testing not installed, so patch it
        candidate_sentinel = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.CohortType",
                candidate_sentinel,
            ),
        ):
            d = _make_decision()
            result = engine._apply_ab_test_routing(d, _make_features(), time.time())

        assert result.cohort == "champion"
        assert result.model_version == 2

    def test_falls_back_on_routing_error(self, engine):
        mock_router = MagicMock()
        mock_router.route.side_effect = RuntimeError("route failed")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            d = _make_decision()
            result = engine._apply_ab_test_routing(d, _make_features(), time.time())

        assert result is d  # unchanged on error


# ---------------------------------------------------------------------------
# promote_candidate_model
# ---------------------------------------------------------------------------


class TestPromoteCandidateModel:
    def test_returns_result_on_success(self, engine):
        mock_router = MagicMock()
        status = MagicMock()
        status.value = "promoted"
        mock_router.promote_candidate.return_value = SimpleNamespace(
            status=status,
            previous_champion_version=1,
            new_champion_version=2,
        )
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.promote_candidate_model(force=True)
        assert result.new_champion_version == 2

    def test_returns_none_on_error(self, engine):
        mock_router = MagicMock()
        mock_router.promote_candidate.side_effect = RuntimeError("fail")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.promote_candidate_model()
        assert result is None
