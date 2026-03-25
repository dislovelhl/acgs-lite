"""
Coverage tests for adaptive_governance/governance_engine.py and
adaptive_governance/impact_scorer.py.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import dataclasses
from collections import deque
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONSTITUTIONAL_HASH = "608508a9bd224290"


def _make_features(**overrides) -> ImpactFeatures:
    defaults = {
        "message_length": 100,
        "agent_count": 2,
        "tenant_complexity": 0.5,
        "temporal_patterns": [0.1, 0.2],
        "semantic_similarity": 0.3,
        "historical_precedence": 1,
        "resource_utilization": 0.2,
        "network_isolation": 0.9,
        "risk_score": 0.3,
        "confidence_level": 0.8,
    }
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides) -> GovernanceDecision:
    defaults = {
        "action_allowed": True,
        "impact_level": ImpactLevel.LOW,
        "confidence_score": 0.85,
        "reasoning": "test reasoning",
        "recommended_threshold": 0.5,
        "features_used": _make_features(),
        "decision_id": "gov-test-001",
    }
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


# ---------------------------------------------------------------------------
# ImpactScorer tests
# ---------------------------------------------------------------------------


class TestImpactScorer:
    """Tests for ImpactScorer covering rule-based scoring, ML prediction,
    confidence calculation, feature extraction, model updates, and error paths."""

    @pytest.fixture
    def scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer(CONSTITUTIONAL_HASH)

    # -- rule_based_risk_score --

    def test_rule_based_short_message_low_agents(self, scorer):
        """Short message with few agents should produce low risk."""
        features = _make_features(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.0, abs=0.01)

    def test_rule_based_medium_message(self, scorer):
        """Message above low threshold but below high should add 0.1."""
        features = _make_features(
            message_length=5000,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.1, abs=0.01)

    def test_rule_based_long_message(self, scorer):
        """Message above high threshold should add 0.3."""
        features = _make_features(
            message_length=15000,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.3, abs=0.01)

    def test_rule_based_high_agent_count(self, scorer):
        """Agent count above high threshold should add 0.2."""
        features = _make_features(
            message_length=50,
            agent_count=15,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.2, abs=0.01)

    def test_rule_based_medium_agent_count(self, scorer):
        """Agent count above low threshold but below high should add 0.1."""
        features = _make_features(
            message_length=50,
            agent_count=7,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.1, abs=0.01)

    def test_rule_based_combined_high_risk(self, scorer):
        """All risk factors high should cap at 1.0."""
        features = _make_features(
            message_length=20000,
            agent_count=20,
            tenant_complexity=1.0,
            resource_utilization=1.0,
            semantic_similarity=1.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_rule_based_tenant_complexity_contribution(self, scorer):
        """Tenant complexity multiplied by 0.2 contributes to score."""
        features = _make_features(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.5,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.1, abs=0.01)

    def test_rule_based_resource_utilization_contribution(self, scorer):
        """Resource utilization multiplied by 0.3 contributes to score."""
        features = _make_features(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.5,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.15, abs=0.01)

    # -- _calculate_confidence --

    def test_confidence_all_signals_present(self, scorer):
        """Full feature data should yield higher confidence."""
        features = _make_features(
            historical_precedence=5,
            temporal_patterns=[0.1, 0.2],
            semantic_similarity=0.5,
        )
        conf = scorer._calculate_confidence(features)
        assert conf == pytest.approx(0.9, abs=0.01)

    def test_confidence_no_history(self, scorer):
        """No historical precedence yields lower confidence."""
        features = _make_features(
            historical_precedence=0,
            temporal_patterns=[],
            semantic_similarity=0.0,
        )
        conf = scorer._calculate_confidence(features)
        assert conf == pytest.approx(0.5, abs=0.01)

    def test_confidence_capped_at_one(self, scorer):
        """Confidence should not exceed 1.0."""
        features = _make_features(
            historical_precedence=100,
            temporal_patterns=[0.1, 0.2, 0.3, 0.4],
            semantic_similarity=0.99,
        )
        conf = scorer._calculate_confidence(features)
        assert conf <= 1.0

    # -- assess_impact --

    async def test_assess_impact_untrained_model(self, scorer):
        """Untrained model falls back to rule-based scoring."""
        message = {"content": "test message", "tenant_id": "t1"}
        context = {"active_agents": ["a1", "a2"]}

        result = await scorer.assess_impact(message, context)

        assert isinstance(result, ImpactFeatures)
        assert result.confidence_level == pytest.approx(0.7, abs=0.01)
        assert 0.0 <= result.risk_score <= 1.0

    async def test_assess_impact_trained_model(self, scorer):
        """Trained model uses ML prediction path."""
        scorer.model_trained = True
        scorer._predict_risk_score = MagicMock(return_value=0.42)
        scorer._calculate_confidence = MagicMock(return_value=0.88)

        message = {"content": "test message", "tenant_id": "t1"}
        context = {"active_agents": ["a1"]}

        result = await scorer.assess_impact(message, context)

        assert result.risk_score == pytest.approx(0.42, abs=0.01)
        assert result.confidence_level == pytest.approx(0.88, abs=0.01)

    async def test_assess_impact_error_returns_safe_defaults(self, scorer):
        """Error during feature extraction returns conservative defaults."""
        scorer._extract_features = AsyncMock(side_effect=RuntimeError("boom"))

        message = {"content": "x"}
        context = {}

        result = await scorer.assess_impact(message, context)

        assert isinstance(result, ImpactFeatures)
        assert result.risk_score == pytest.approx(0.1, abs=0.01)
        assert result.confidence_level == 0.5

    # -- _extract_features --

    async def test_extract_features_basic(self, scorer):
        """Feature extraction populates all fields."""
        message = {"content": "hello world", "tenant_id": "tenant-1"}
        context = {"active_agents": ["a1", "a2", "a3"]}

        features = await scorer._extract_features(message, context)

        assert features.message_length == 11
        assert features.agent_count == 3
        assert isinstance(features.tenant_complexity, float)
        assert isinstance(features.temporal_patterns, list)

    async def test_extract_features_empty_content(self, scorer):
        """Missing content key should produce zero-length."""
        message = {}
        context = {}

        features = await scorer._extract_features(message, context)

        assert features.message_length == 0
        assert features.agent_count == 0

    async def test_extract_features_active_agents_not_list(self, scorer):
        """Non-list active_agents should yield agent_count=0."""
        message = {"content": "x"}
        context = {"active_agents": "not-a-list"}

        features = await scorer._extract_features(message, context)

        assert features.agent_count == 0

    # -- _predict_risk_score --

    def test_predict_risk_score_untrained_fallback(self, scorer):
        """Untrained classifier falls back to rule-based scoring."""
        scorer.model_trained = False
        features = _make_features()
        score = scorer._predict_risk_score(features)
        rule_score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(rule_score, abs=0.01)

    def test_predict_risk_score_no_classifier(self, scorer):
        """None classifier falls back to rule-based scoring."""
        scorer.model_trained = True
        scorer.impact_classifier = None
        features = _make_features()
        score = scorer._predict_risk_score(features)
        rule_score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(rule_score, abs=0.01)

    def test_predict_risk_score_ml_error_fallback(self, scorer):
        """ML prediction error falls back to rule-based scoring."""
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.side_effect = RuntimeError("model error")
        scorer.impact_classifier = mock_clf
        features = _make_features()
        score = scorer._predict_risk_score(features)
        rule_score = scorer._rule_based_risk_score(features)
        assert score == pytest.approx(rule_score, abs=0.01)

    def test_predict_risk_score_clamped(self, scorer):
        """ML prediction is clamped between 0.0 and 1.0."""
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.return_value = [1.5]
        scorer.impact_classifier = mock_clf
        features = _make_features()
        score = scorer._predict_risk_score(features)
        assert score <= 1.0

    def test_predict_risk_score_clamped_negative(self, scorer):
        """Negative ML prediction is clamped to 0.0."""
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.return_value = [-0.5]
        scorer.impact_classifier = mock_clf
        features = _make_features()
        score = scorer._predict_risk_score(features)
        assert score >= 0.0

    def test_predict_risk_score_empty_temporal(self, scorer):
        """Empty temporal patterns default to 0 in feature vector."""
        scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.return_value = [0.5]
        scorer.impact_classifier = mock_clf
        features = _make_features(temporal_patterns=[])
        score = scorer._predict_risk_score(features)
        assert score == pytest.approx(0.5, abs=0.01)

    # -- update_model --

    def test_update_model_appends_sample(self, scorer):
        """update_model appends training sample."""
        features = _make_features()
        scorer.update_model(features, 0.5)
        assert len(scorer.training_samples) == 1
        assert scorer.training_samples[0] == (features, 0.5)

    def test_update_model_error_handled(self, scorer):
        """Error in update_model is caught and logged."""
        scorer.training_samples = MagicMock()
        scorer.training_samples.append.side_effect = RuntimeError("boom")
        # Should not raise
        scorer.update_model(_make_features(), 0.5)

    # -- _retrain_model --

    def test_retrain_model_insufficient_samples(self, scorer):
        """Retrain with too few samples does nothing."""
        scorer.training_samples = deque([((_make_features(), 0.5))], maxlen=5000)
        scorer._retrain_model()
        assert not scorer.model_trained

    def test_retrain_model_no_classifier(self, scorer):
        """Retrain with no classifier returns early."""
        scorer.impact_classifier = None
        scorer._retrain_model()
        assert not scorer.model_trained

    def test_retrain_model_success(self, scorer):
        """Retrain with sufficient samples trains the model."""
        try:
            import numpy as np
            from sklearn.ensemble import RandomForestRegressor
        except ImportError:
            pytest.skip("sklearn/numpy required")

        if scorer.impact_classifier is None:
            pytest.skip("sklearn not available")

        # Fill training samples above threshold (500)
        for i in range(600):
            features = _make_features(message_length=i * 10, risk_score=i / 600.0)
            scorer.training_samples.append((features, i / 600.0))

        scorer._retrain_model()
        assert scorer.model_trained is True

    def test_retrain_model_error_handled(self, scorer):
        """Error during retrain is caught."""
        if scorer.impact_classifier is None:
            pytest.skip("sklearn not available")

        for _i in range(600):
            scorer.training_samples.append((_make_features(), 0.5))

        scorer.impact_classifier.fit = MagicMock(side_effect=RuntimeError("fit error"))
        scorer._retrain_model()
        # Should not raise, model_trained stays False
        assert not scorer.model_trained

    # -- _apply_mhc_stability --

    def test_mhc_stability_skipped_when_disabled(self, scorer):
        """When use_mhc_stability is False, weights are unchanged."""
        original = dict(scorer.feature_weights)
        scorer.use_mhc_stability = False
        scorer._apply_mhc_stability()
        assert scorer.feature_weights == original

    def test_mhc_stability_error_handled(self, scorer):
        """Error in mHC stabilization is caught."""
        scorer.use_mhc_stability = True
        # Force torch error by patching
        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.torch",
            None,
        ):
            scorer._apply_mhc_stability()
        # Should not raise

    # -- _initialize_mlflow --

    def test_mlflow_not_initialized_in_tests(self, scorer):
        """MLflow should not be initialized when pytest is in sys.modules."""
        assert not scorer._mlflow_initialized


# ---------------------------------------------------------------------------
# AdaptiveGovernanceEngine tests
# ---------------------------------------------------------------------------


class TestAdaptiveGovernanceEngine:
    """Tests for AdaptiveGovernanceEngine covering evaluation, feedback,
    classification, reasoning, metrics, DTMC, A/B testing, and drift detection."""

    @pytest.fixture
    def engine(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        return AdaptiveGovernanceEngine(CONSTITUTIONAL_HASH)

    # -- _classify_impact_level --

    @pytest.mark.parametrize(
        "risk_score,expected_level",
        [
            (0.95, ImpactLevel.CRITICAL),
            (0.9, ImpactLevel.CRITICAL),
            (0.75, ImpactLevel.HIGH),
            (0.7, ImpactLevel.HIGH),
            (0.5, ImpactLevel.MEDIUM),
            (0.4, ImpactLevel.MEDIUM),
            (0.25, ImpactLevel.LOW),
            (0.2, ImpactLevel.LOW),
            (0.1, ImpactLevel.NEGLIGIBLE),
            (0.0, ImpactLevel.NEGLIGIBLE),
        ],
    )
    def test_classify_impact_level(self, engine, risk_score, expected_level):
        result = engine._classify_impact_level(risk_score)
        assert result == expected_level

    # -- _generate_reasoning --

    def test_reasoning_allowed_high_confidence(self, engine):
        features = _make_features(risk_score=0.2, confidence_level=0.9, historical_precedence=3)
        reasoning = engine._generate_reasoning(True, features, 0.5)
        assert "ALLOWED" in reasoning
        assert "0.200" in reasoning
        assert "3 similar precedents" in reasoning
        assert "Low confidence" not in reasoning

    def test_reasoning_blocked_low_confidence(self, engine):
        features = _make_features(risk_score=0.8, confidence_level=0.5, historical_precedence=0)
        reasoning = engine._generate_reasoning(False, features, 0.5)
        assert "BLOCKED" in reasoning
        assert "Low confidence" in reasoning
        assert "precedents" not in reasoning

    # -- _build_conservative_fallback_decision --

    def test_fallback_decision(self, engine):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        error = ValueError("test error")
        decision = AdaptiveGovernanceEngine._build_conservative_fallback_decision(error)
        assert not decision.action_allowed
        assert decision.impact_level == ImpactLevel.HIGH
        assert "test error" in decision.reasoning
        assert "conservative fallback" in decision.reasoning
        assert decision.confidence_score == pytest.approx(0.9, abs=0.01)

    # -- _build_decision_for_features --

    def test_build_decision_low_risk(self, engine):
        features = _make_features(risk_score=0.1, confidence_level=0.9)
        decision = engine._build_decision_for_features(features, "gov-001")
        assert decision.action_allowed is True
        assert decision.decision_id == "gov-001"
        assert decision.confidence_score == pytest.approx(0.9, abs=0.01)

    def test_build_decision_high_risk(self, engine):
        features = _make_features(risk_score=0.99, confidence_level=0.8)
        decision = engine._build_decision_for_features(features, "gov-002")
        assert decision.impact_level == ImpactLevel.CRITICAL
        # action_allowed depends on threshold_manager; verify decision is built
        assert decision.decision_id == "gov-002"
        assert decision.confidence_score == pytest.approx(0.8, abs=0.01)

    # -- evaluate_governance_decision --

    async def test_evaluate_governance_decision_success(self, engine):
        """Full evaluation pipeline returning a valid decision."""
        mock_features = _make_features(risk_score=0.05, confidence_level=0.85)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=mock_features)
        engine._decision_validator.validate_decision = AsyncMock(return_value=(True, []))

        message = {"content": "safe message"}
        context = {"active_agents": []}

        decision = await engine.evaluate_governance_decision(message, context)

        assert isinstance(decision, GovernanceDecision)
        # Low risk score should be allowed (below any threshold)
        assert decision.confidence_score == pytest.approx(0.85, abs=0.01)

    async def test_evaluate_governance_decision_validation_failure(self, engine):
        """Validation failure triggers conservative fallback."""
        mock_features = _make_features(risk_score=0.15, confidence_level=0.85)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=mock_features)
        engine._decision_validator.validate_decision = AsyncMock(
            return_value=(False, ["hash mismatch"])
        )

        message = {"content": "test"}
        context = {}

        decision = await engine.evaluate_governance_decision(message, context)

        # Should fall back to conservative decision
        assert not decision.action_allowed
        assert decision.impact_level == ImpactLevel.HIGH

    async def test_evaluate_governance_decision_error(self, engine):
        """Runtime error during evaluation returns conservative fallback."""
        engine.impact_scorer.assess_impact = AsyncMock(side_effect=RuntimeError("scorer down"))

        message = {"content": "test"}
        context = {}

        decision = await engine.evaluate_governance_decision(message, context)

        assert not decision.action_allowed
        assert "scorer down" in decision.reasoning

    # -- _apply_dtmc_risk_blend --

    def test_dtmc_risk_blend_disabled(self, engine):
        """DTMC blend returns unchanged features when disabled."""
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == pytest.approx(0.3, abs=0.001)

    def test_dtmc_risk_blend_enabled_unfitted(self, engine):
        """DTMC blend returns unchanged features when learner is not fitted."""
        engine.config = MagicMock(enable_dtmc=True, dtmc_impact_weight=0.3)
        engine._dtmc_learner.is_fitted = False
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == pytest.approx(0.3, abs=0.001)

    def test_dtmc_risk_blend_enabled_no_history(self, engine):
        """DTMC blend returns unchanged features when no trajectory history."""
        engine.config = MagicMock(enable_dtmc=True, dtmc_impact_weight=0.3)
        engine._dtmc_learner = MagicMock(is_fitted=True)
        engine.decision_history.clear()
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == pytest.approx(0.3, abs=0.001)

    def test_dtmc_risk_blend_enabled_with_history(self, engine):
        """DTMC blend adjusts risk score when all conditions met."""
        engine.config = MagicMock(enable_dtmc=True, dtmc_impact_weight=0.5)
        engine._dtmc_learner = MagicMock(is_fitted=True, predict_risk=MagicMock(return_value=0.6))
        # Add some decisions to history
        for _ in range(3):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)

        # blended = min(1.0, 0.3 + 0.6 * 0.5) = 0.6
        assert result.risk_score == pytest.approx(0.6, abs=0.01)
        assert result is not features  # immutable replacement

    def test_dtmc_risk_blend_capped_at_one(self, engine):
        """DTMC blend caps blended score at 1.0."""
        engine.config = MagicMock(enable_dtmc=True, dtmc_impact_weight=1.0)
        engine._dtmc_learner = MagicMock(is_fitted=True, predict_risk=MagicMock(return_value=0.9))
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        features = _make_features(risk_score=0.8)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == pytest.approx(1.0, abs=0.01)

    # -- _apply_dtmc_escalation --

    def test_dtmc_escalation_disabled(self, engine):
        """Escalation returns unchanged decision when DTMC disabled."""
        decision = _make_decision(impact_level=ImpactLevel.LOW, action_allowed=True)
        result = engine._apply_dtmc_escalation(decision)
        assert result.action_allowed is True
        assert result.impact_level == ImpactLevel.LOW

    def test_dtmc_escalation_already_high(self, engine):
        """No escalation when already HIGH or CRITICAL."""
        engine.config = MagicMock(enable_dtmc=True)
        engine._dtmc_learner = MagicMock(
            is_fitted=True,
            should_intervene=MagicMock(return_value=True),
            predict_risk=MagicMock(return_value=0.95),
        )
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.HIGH))

        decision = _make_decision(impact_level=ImpactLevel.HIGH, action_allowed=True)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH
        assert result.action_allowed is True  # unchanged

    def test_dtmc_escalation_triggers(self, engine):
        """Escalation changes LOW to HIGH and blocks action."""
        engine.config = MagicMock(enable_dtmc=True)
        engine._dtmc_learner = MagicMock(
            is_fitted=True,
            should_intervene=MagicMock(return_value=True),
            predict_risk=MagicMock(return_value=0.9),
        )
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        decision = _make_decision(impact_level=ImpactLevel.LOW, action_allowed=True)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH
        assert result.action_allowed is False
        assert "DTMC trajectory risk" in result.reasoning

    def test_dtmc_escalation_no_intervention_needed(self, engine):
        """No escalation when should_intervene returns False."""
        engine.config = MagicMock(enable_dtmc=True)
        engine._dtmc_learner = MagicMock(
            is_fitted=True,
            should_intervene=MagicMock(return_value=False),
        )
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        decision = _make_decision(impact_level=ImpactLevel.LOW, action_allowed=True)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.LOW

    # -- _apply_ab_test_routing --

    def test_ab_test_routing_unavailable(self, engine):
        """Returns unmodified decision when A/B testing is unavailable."""
        engine._ab_test_router = None
        decision = _make_decision()
        features = _make_features()
        result = engine._apply_ab_test_routing(decision, features, 1.0)
        assert result is decision

    # -- _record_decision_metrics --

    def test_record_decision_metrics(self, engine):
        """Metrics recording appends to history and updates response time."""
        decision = _make_decision(confidence_score=0.95)
        engine._record_decision_metrics(decision, 0.5)
        assert len(engine.decision_history) == 1
        assert engine.metrics.average_response_time > 0

    # -- _update_metrics --

    def test_update_metrics_compliance_rate(self, engine):
        """Compliance rate calculated from recent decisions."""
        for i in range(10):
            engine.decision_history.append(_make_decision(confidence_score=0.9 if i < 8 else 0.5))
        decision = _make_decision(confidence_score=0.9)
        engine._update_metrics(decision, 0.01)
        assert engine.metrics.constitutional_compliance_rate > 0.5

    # -- provide_feedback --

    def test_provide_feedback_success(self, engine):
        """Feedback updates models without error."""
        decision = _make_decision()
        engine.threshold_manager.update_model = MagicMock()
        engine.impact_scorer.update_model = MagicMock()
        engine._update_river_model = MagicMock()
        engine._store_feedback_event = MagicMock()

        engine.provide_feedback(decision, outcome_success=True)

        engine.threshold_manager.update_model.assert_called_once()
        engine.impact_scorer.update_model.assert_called_once()

    def test_provide_feedback_with_human_override(self, engine):
        """Feedback with human override passes correction info."""
        decision = _make_decision(action_allowed=True)
        engine.threshold_manager.update_model = MagicMock()
        engine.impact_scorer.update_model = MagicMock()
        engine._update_river_model = MagicMock()
        engine._store_feedback_event = MagicMock()

        engine.provide_feedback(decision, outcome_success=False, human_override=False)

        engine.threshold_manager.update_model.assert_called_once()
        # actual_impact should be increased by 0.2 since outcome_success=False
        call_args = engine.impact_scorer.update_model.call_args
        actual_impact = call_args[0][1]
        assert actual_impact == pytest.approx(0.5, abs=0.01)  # 0.3 + 0.2

    def test_provide_feedback_error_handled(self, engine):
        """Error during feedback processing is caught."""
        decision = _make_decision()
        engine.threshold_manager.update_model = MagicMock(side_effect=RuntimeError("db error"))
        # Should not raise
        engine.provide_feedback(decision, outcome_success=True)

    def test_provide_feedback_dtmc_update(self, engine):
        """DTMC online update triggered when enable_dtmc is True."""
        engine.config = MagicMock(enable_dtmc=True)
        engine._dtmc_learner = MagicMock(is_fitted=True)
        engine.threshold_manager.update_model = MagicMock()
        engine.impact_scorer.update_model = MagicMock()
        engine._update_river_model = MagicMock()
        engine._store_feedback_event = MagicMock()
        engine._trace_collector = MagicMock()
        engine._trace_collector.collect_from_decision_history.return_value = [
            MagicMock(states=[0, 1], terminal_unsafe=False)
        ]

        # Add decisions to history
        for _ in range(5):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))

        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)

        # Check dtmc update was called for new decisions
        engine._dtmc_learner.update_online.assert_called()

    # -- _store_feedback_event --

    def test_store_feedback_event_no_handler(self, engine):
        """No-op when feedback handler is not available."""
        engine._feedback_handler = None
        # Should not raise
        engine._store_feedback_event(_make_decision(), True, None, 0.3)

    # -- _update_river_model --

    def test_update_river_model_unavailable(self, engine):
        """No-op when river model is None."""
        engine.river_model = None
        # Should not raise
        engine._update_river_model(_make_decision(), 0.5)

    # -- get_river_model_stats --

    def test_get_river_model_stats_unavailable(self, engine):
        """Returns None when river model is unavailable."""
        engine.river_model = None
        assert engine.get_river_model_stats() is None

    def test_get_river_model_stats_error(self, engine):
        """Returns None on error."""
        engine.river_model = MagicMock()
        engine.river_model.get_stats.side_effect = RuntimeError("stats error")
        result = engine.get_river_model_stats()
        assert result is None

    # -- get_ab_test_router --

    def test_get_ab_test_router(self, engine):
        """Returns the A/B test router instance."""
        assert engine.get_ab_test_router() is engine._ab_test_router

    # -- get_ab_test_metrics --

    def test_get_ab_test_metrics_unavailable(self, engine):
        """Returns None when A/B testing unavailable."""
        engine._ab_test_router = None
        assert engine.get_ab_test_metrics() is None

    def test_get_ab_test_metrics_error(self, engine):
        """Returns None on error."""
        engine._ab_test_router = MagicMock()
        engine._ab_test_router.get_metrics_summary.side_effect = RuntimeError("err")
        result = engine.get_ab_test_metrics()
        assert result is None

    # -- get_ab_test_comparison --

    def test_get_ab_test_comparison_unavailable(self, engine):
        """Returns None when A/B testing unavailable."""
        engine._ab_test_router = None
        assert engine.get_ab_test_comparison() is None

    def test_get_ab_test_comparison_error(self, engine):
        """Returns None on error."""
        engine._ab_test_router = MagicMock()
        engine._ab_test_router.compare_metrics.side_effect = RuntimeError("err")
        result = engine.get_ab_test_comparison()
        assert result is None

    # -- promote_candidate_model --

    def test_promote_candidate_unavailable(self, engine):
        """Returns None when A/B testing unavailable."""
        engine._ab_test_router = None
        assert engine.promote_candidate_model() is None

    def test_promote_candidate_error(self, engine):
        """Returns None on error."""
        engine._ab_test_router = MagicMock()
        engine._ab_test_router.promote_candidate.side_effect = RuntimeError("err")
        result = engine.promote_candidate_model()
        assert result is None

    # -- _analyze_performance_trends --

    def test_analyze_performance_trends(self, engine):
        """Appends to trend lists."""
        engine.metrics.constitutional_compliance_rate = 0.95
        engine.metrics.false_positive_rate = 0.05
        engine.metrics.average_response_time = 0.01

        engine._analyze_performance_trends()

        assert len(engine.metrics.compliance_trend) == 1
        assert len(engine.metrics.accuracy_trend) == 1
        assert len(engine.metrics.performance_trend) == 1

    def test_analyze_performance_trends_trimming(self, engine):
        """Trends are trimmed when they exceed max length."""
        engine.metrics.compliance_trend = list(range(150))
        engine.metrics.accuracy_trend = list(range(150))
        engine.metrics.performance_trend = list(range(150))

        engine._analyze_performance_trends()

        assert len(engine.metrics.compliance_trend) <= 100
        assert len(engine.metrics.accuracy_trend) <= 100
        assert len(engine.metrics.performance_trend) <= 100

    # -- _should_retrain_models --

    def test_should_retrain_low_compliance(self, engine):
        """Retrain triggered when compliance below target."""
        engine.metrics.constitutional_compliance_rate = 0.5
        assert engine._should_retrain_models() is True

    def test_should_retrain_sufficient_data(self, engine):
        """Retrain triggered with sufficient history at modulus boundary."""
        engine.metrics.constitutional_compliance_rate = 0.99
        # Need >= 1000 decisions at modulus 500
        for _ in range(1000):
            engine.decision_history.append(_make_decision())
        assert engine._should_retrain_models() is True

    def test_should_not_retrain(self, engine):
        """No retrain when compliance is high and insufficient data."""
        engine.metrics.constitutional_compliance_rate = 0.99
        for _ in range(50):
            engine.decision_history.append(_make_decision())
        assert engine._should_retrain_models() is False

    # -- _log_performance_summary --

    def test_log_performance_summary(self, engine):
        """Performance summary logs without error."""
        engine.metrics.constitutional_compliance_rate = 0.95
        engine.metrics.average_response_time = 0.01
        # Should not raise
        engine._log_performance_summary()

    # -- _get_trajectory_prefix --

    def test_get_trajectory_prefix_empty(self, engine):
        """Returns None when no decision history."""
        assert engine._get_trajectory_prefix() is None

    def test_get_trajectory_prefix_with_history(self, engine):
        """Returns list of state indices from recent decisions."""
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.NEGLIGIBLE))
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.HIGH))

        prefix = engine._get_trajectory_prefix()
        assert prefix == [0, 1, 3]

    # -- _maybe_refit_dtmc --

    def test_maybe_refit_dtmc_disabled(self, engine):
        """No-op when DTMC disabled."""
        engine.config = None
        engine._maybe_refit_dtmc()  # Should not raise

    def test_maybe_refit_dtmc_insufficient_history(self, engine):
        """No refit with fewer than 10 decisions."""
        engine.config = MagicMock(enable_dtmc=True)
        for _ in range(5):
            engine.decision_history.append(_make_decision())
        engine._dtmc_learner = MagicMock()
        engine._maybe_refit_dtmc()
        engine._dtmc_learner.fit.assert_not_called()

    def test_maybe_refit_dtmc_with_data(self, engine):
        """Refit called with sufficient decision history."""
        engine.config = MagicMock(enable_dtmc=True)
        for _ in range(15):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        engine._dtmc_learner = MagicMock()
        engine._trace_collector = MagicMock()
        mock_traj = MagicMock()
        engine._trace_collector.collect_from_decision_history.return_value = [mock_traj]
        engine._dtmc_learner.fit.return_value = MagicMock(n_trajectories=1, unsafe_fraction=0.1)

        engine._maybe_refit_dtmc()

        engine._dtmc_learner.fit.assert_called_once()

    def test_maybe_refit_dtmc_no_trajectories(self, engine):
        """No refit when trace collector returns empty."""
        engine.config = MagicMock(enable_dtmc=True)
        for _ in range(15):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        engine._dtmc_learner = MagicMock()
        engine._trace_collector = MagicMock()
        engine._trace_collector.collect_from_decision_history.return_value = []

        engine._maybe_refit_dtmc()

        engine._dtmc_learner.fit.assert_not_called()

    # -- _run_scheduled_drift_detection --

    def test_run_scheduled_drift_not_due(self, engine):
        """No drift detection if interval has not elapsed."""
        import time as _time

        engine._drift_detector = MagicMock()
        engine._last_drift_check = _time.time()
        engine._drift_check_interval = 99999
        engine._run_scheduled_drift_detection()
        engine._drift_detector.detect_drift.assert_not_called()

    def test_run_scheduled_drift_no_detector(self, engine):
        """No-op when drift detector is None."""
        engine._drift_detector = None
        engine._run_scheduled_drift_detection()  # Should not raise

    # -- _collect_drift_data --

    def test_collect_drift_data_empty_history(self, engine):
        """Returns None when no decision history."""
        result = engine._collect_drift_data()
        assert result is None

    def test_collect_drift_data_with_history(self, engine):
        """Returns DataFrame when history is present."""
        try:
            import pandas
        except ImportError:
            pytest.skip("pandas required for drift data collection")

        for _ in range(5):
            engine.decision_history.append(_make_decision())

        result = engine._collect_drift_data()
        assert result is not None
        assert len(result) == 5

    # -- get_latest_drift_report --

    def test_get_latest_drift_report_none(self, engine):
        """Returns None when no drift check has been run."""
        assert engine.get_latest_drift_report() is None

    # -- initialize / shutdown --

    async def test_initialize_and_shutdown(self, engine):
        """Initialize starts background tasks, shutdown cancels them."""
        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None

        await engine.shutdown()
        assert engine.running is False

    async def test_shutdown_without_initialize(self, engine):
        """Shutdown is safe even without prior initialization."""
        await engine.shutdown()
        assert engine.running is False

    # -- _learning_thread property --

    def test_learning_thread_property(self, engine):
        """_learning_thread is an alias for learning_task."""
        engine.learning_task = MagicMock()
        assert engine._learning_thread is engine.learning_task

    # -- mode initialization --

    def test_mode_defaults_to_adaptive(self, engine):
        """Engine initializes in ADAPTIVE mode."""
        assert engine.mode == GovernanceMode.ADAPTIVE

    # -- _default_river_feature_names --

    def test_default_river_feature_names(self, engine):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        names = AdaptiveGovernanceEngine._default_river_feature_names()
        assert "message_length" in names
        assert "risk_score" in names
        assert len(names) == 11
