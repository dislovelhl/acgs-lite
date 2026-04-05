from __future__ import annotations

import asyncio
import dataclasses
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as CONST_HASH
from enhanced_agent_bus.adaptive_governance.governance_engine import (
    AdaptiveGovernanceEngine,
)
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.adaptive_governance.tests.engine.helpers import (
    _make_decision,
    _make_features,
)

_MLFLOW_PATCH = "mlflow.set_tracking_uri"
_IMPACT_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.impact_scorer.ImpactScorer._initialize_mlflow"
)
_THRESH_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.threshold_manager.AdaptiveThresholds._initialize_mlflow"  # noqa: E501
)


class TestClassifyImpactLevel:
    def test_critical(self, engine):

        assert engine._classify_impact_level(0.95) == ImpactLevel.CRITICAL

    def test_high(self, engine):

        assert engine._classify_impact_level(0.75) == ImpactLevel.HIGH

    def test_medium(self, engine):

        assert engine._classify_impact_level(0.5) == ImpactLevel.MEDIUM

    def test_low(self, engine):

        assert engine._classify_impact_level(0.25) == ImpactLevel.LOW

    def test_negligible(self, engine):

        assert engine._classify_impact_level(0.1) == ImpactLevel.NEGLIGIBLE

    def test_boundary_critical(self, engine):

        assert engine._classify_impact_level(0.9) == ImpactLevel.CRITICAL

    def test_boundary_high(self, engine):

        assert engine._classify_impact_level(0.7) == ImpactLevel.HIGH


# ---------------------------------------------------------------------------
# 4. _generate_reasoning
# ---------------------------------------------------------------------------


class TestGenerateReasoning:
    def test_allowed_high_confidence(self, engine):
        features = _make_features(risk_score=0.3, confidence=0.9)
        result = engine._generate_reasoning(True, features, threshold=0.5)
        assert "ALLOWED" in result
        assert "0.300" in result

    def test_blocked_high_confidence(self, engine):
        features = _make_features(risk_score=0.8, confidence=0.85)
        result = engine._generate_reasoning(False, features, threshold=0.5)
        assert "BLOCKED" in result

    def test_low_confidence_appended(self, engine):
        features = _make_features(risk_score=0.3, confidence=0.5)
        result = engine._generate_reasoning(True, features, threshold=0.5)
        assert "Low confidence" in result

    def test_historical_precedence_appended(self, engine):
        features = _make_features(risk_score=0.3, confidence=0.9)
        features = dataclasses.replace(features, historical_precedence=5)
        result = engine._generate_reasoning(True, features, threshold=0.5)
        assert "5 similar precedents" in result

    def test_zero_historical_precedence_not_appended(self, engine):
        features = _make_features(risk_score=0.3, confidence=0.9)
        features = dataclasses.replace(features, historical_precedence=0)
        result = engine._generate_reasoning(True, features, threshold=0.5)
        assert "precedents" not in result


# ---------------------------------------------------------------------------
# 5. evaluate_governance_decision (happy path + fallback)
# ---------------------------------------------------------------------------


class TestEvaluateGovernanceDecision:
    async def test_basic_evaluation(self, engine, sample_message, sample_context):

        features = _make_features(risk_score=0.3)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        decision = await engine.evaluate_governance_decision(sample_message, sample_context)
        assert isinstance(decision, GovernanceDecision)
        assert decision.action_allowed is True
        assert len(engine.decision_history) == 1

    async def test_blocked_decision(self, engine, sample_message, sample_context):
        features = _make_features(risk_score=0.9)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        decision = await engine.evaluate_governance_decision(sample_message, sample_context)
        assert decision.action_allowed is False

    async def test_fallback_on_exception(self, engine, sample_message, sample_context):

        engine.impact_scorer.assess_impact = AsyncMock(side_effect=RuntimeError("boom"))

        decision = await engine.evaluate_governance_decision(sample_message, sample_context)
        # Conservative fallback: action_allowed=False
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH

    async def test_anomaly_monitor_record_metrics(self, engine, sample_message, sample_context):
        mock_monitor = MagicMock()
        mock_monitor.record_metrics = MagicMock()
        engine._anomaly_monitor = mock_monitor

        features = _make_features(risk_score=0.3)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        await engine.evaluate_governance_decision(sample_message, sample_context)
        mock_monitor.record_metrics.assert_called_once()

    async def test_ab_test_routing_champion(self, engine, sample_message, sample_context):
        """AB routing branch — champion cohort + shadow execution."""

        # Simulate AB_TESTING_AVAILABLE=True with mocked router
        mock_cohort = MagicMock()
        mock_cohort.value = "champion"

        mock_routing_result = MagicMock()
        mock_routing_result.cohort = mock_cohort
        mock_routing_result.model_version = 1

        mock_champion_metrics = MagicMock()
        mock_champion_metrics.record_request = MagicMock()

        mock_router = MagicMock()
        mock_router.route = MagicMock(return_value=mock_routing_result)
        mock_router.get_champion_metrics = MagicMock(return_value=mock_champion_metrics)

        mock_shadow = MagicMock()
        mock_shadow.execute_shadow = AsyncMock()

        engine._ab_test_router = mock_router
        engine._shadow_executor = mock_shadow

        features = _make_features(risk_score=0.3)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        # Patch AB_TESTING_AVAILABLE and CohortType.CHAMPION in module scope
        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_ab = ge_mod.AB_TESTING_AVAILABLE
        orig_cohort_type = ge_mod.CohortType
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            # Create a fake CohortType where CHAMPION matches
            fake_cohort = MagicMock()
            fake_cohort.CHAMPION = mock_cohort
            fake_cohort.CANDIDATE = MagicMock()
            # Make the comparison mock_cohort == CHAMPION succeed
            mock_cohort.__eq__ = lambda self, other: other is mock_cohort
            ge_mod.CohortType = fake_cohort

            decision = await engine.evaluate_governance_decision(sample_message, sample_context)
            assert isinstance(decision, GovernanceDecision)
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig_ab
            ge_mod.CohortType = orig_cohort_type

    async def test_ab_test_routing_error(self, engine, sample_message, sample_context):
        """AB routing that raises should be swallowed and execution continues."""
        mock_router = MagicMock()
        mock_router.route = MagicMock(side_effect=RuntimeError("route fail"))
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_ab = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            features = _make_features(risk_score=0.3)
            engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
            engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

            decision = await engine.evaluate_governance_decision(sample_message, sample_context)
            assert decision is not None
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig_ab

    async def test_dtmc_blending_when_fitted(self, engine, sample_message, sample_context):
        """DTMC risk blending path when enable_dtmc=True and learner is fitted."""
        cfg = MagicMock()
        cfg.enable_dtmc = True
        cfg.dtmc_impact_weight = 0.5
        cfg.dtmc_intervention_threshold = 0.8
        engine.config = cfg

        # Make learner appear fitted
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.predict_risk = MagicMock(return_value=0.3)
        engine._dtmc_learner.should_intervene = MagicMock(return_value=False)

        # Provide decision history so _get_trajectory_prefix returns a value
        engine.decision_history = [_make_decision(risk_score=0.3) for _ in range(3)]

        features = _make_features(risk_score=0.3)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        decision = await engine.evaluate_governance_decision(sample_message, sample_context)
        assert decision is not None

    async def test_dtmc_escalation_when_should_intervene(
        self, engine, sample_message, sample_context
    ):
        """DTMC intervention escalates decision to HIGH / blocks action."""

        cfg = MagicMock()
        cfg.enable_dtmc = True
        cfg.dtmc_impact_weight = 0.0
        cfg.dtmc_intervention_threshold = 0.8
        engine.config = cfg

        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene = MagicMock(return_value=True)
        engine._dtmc_learner.predict_risk = MagicMock(return_value=0.9)

        # Populate history so prefix is available
        engine.decision_history = [_make_decision(risk_score=0.3) for _ in range(3)]

        features = _make_features(risk_score=0.3)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        decision = await engine.evaluate_governance_decision(sample_message, sample_context)
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH
        assert "DTMC trajectory" in decision.reasoning

    async def test_dtmc_no_escalation_when_already_high(
        self, engine, sample_message, sample_context
    ):
        """If decision is already HIGH, DTMC escalation path does not change it."""

        cfg = MagicMock()
        cfg.enable_dtmc = True
        cfg.dtmc_impact_weight = 0.0
        cfg.dtmc_intervention_threshold = 0.8
        engine.config = cfg

        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene = MagicMock(return_value=True)
        engine._dtmc_learner.predict_risk = MagicMock(return_value=0.9)

        engine.decision_history = [_make_decision(risk_score=0.3) for _ in range(3)]

        # risk_score=0.75 → HIGH impact level already
        features = _make_features(risk_score=0.75)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold = MagicMock(return_value=0.5)

        decision = await engine.evaluate_governance_decision(sample_message, sample_context)
        # Impact should already be HIGH or CRITICAL — no extra "DTMC trajectory" annotation
        # (the branch guard prevents re-escalating)
        assert decision.impact_level in (ImpactLevel.HIGH, ImpactLevel.CRITICAL)


# ---------------------------------------------------------------------------
# 6. _update_metrics
# ---------------------------------------------------------------------------
