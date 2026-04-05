"""
Coverage tests for:
  1. enhanced_agent_bus.adaptive_governance.governance_engine
  2. enhanced_agent_bus.pqc_validators

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections import deque
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.security.pqc import UnsupportedPQCAlgorithmError

# ---------------------------------------------------------------------------
# Governance engine imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)

CONSTITUTIONAL_HASH = "608508a9bd224290"


def _make_impact_features(**overrides) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.8,
        historical_precedence=3,
        resource_utilization=0.4,
        network_isolation=0.6,
        risk_score=0.3,
        confidence_level=0.85,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides) -> GovernanceDecision:
    defaults = dict(
        action_allowed=True,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.9,
        reasoning="test",
        recommended_threshold=0.7,
        features_used=_make_impact_features(),
        decision_id="gov-test-001",
    )
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


# ---------------------------------------------------------------------------
# Helper: build a patched AdaptiveGovernanceEngine
# ---------------------------------------------------------------------------
def _build_engine(config=None):
    """Build engine with all optional subsystems mocked away."""
    with (
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

        engine = AdaptiveGovernanceEngine(constitutional_hash=CONSTITUTIONAL_HASH, config=config)
    return engine


# ===========================================================================
# AdaptiveGovernanceEngine tests
# ===========================================================================


class TestAdaptiveGovernanceEngineInit:
    def test_default_mode_is_adaptive(self):
        engine = _build_engine()
        assert engine.mode == GovernanceMode.ADAPTIVE

    def test_constitutional_hash_stored(self):
        engine = _build_engine()
        assert engine.constitutional_hash == CONSTITUTIONAL_HASH

    def test_metrics_initialized(self):
        engine = _build_engine()
        assert isinstance(engine.metrics, GovernanceMetrics)
        assert engine.metrics.constitutional_compliance_rate == 0.0

    def test_decision_history_is_deque(self):
        engine = _build_engine()
        assert isinstance(engine.decision_history, deque)
        assert len(engine.decision_history) == 0


class TestClassifyImpactLevel:
    def test_critical(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.95) == ImpactLevel.CRITICAL

    def test_high(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.75) == ImpactLevel.HIGH

    def test_medium(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.5) == ImpactLevel.MEDIUM

    def test_low(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.25) == ImpactLevel.LOW

    def test_negligible(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.1) == ImpactLevel.NEGLIGIBLE

    def test_boundary_critical(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.9) == ImpactLevel.CRITICAL

    def test_boundary_high(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.7) == ImpactLevel.HIGH

    def test_boundary_medium(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.4) == ImpactLevel.MEDIUM

    def test_boundary_low(self):
        engine = _build_engine()
        assert engine._classify_impact_level(0.2) == ImpactLevel.LOW


class TestGenerateReasoning:
    def test_allowed_action(self):
        engine = _build_engine()
        features = _make_impact_features(risk_score=0.3, confidence_level=0.9)
        result = engine._generate_reasoning(True, features, 0.7)
        assert "ALLOWED" in result
        assert "0.300" in result

    def test_blocked_action(self):
        engine = _build_engine()
        features = _make_impact_features(risk_score=0.8, confidence_level=0.9)
        result = engine._generate_reasoning(False, features, 0.7)
        assert "BLOCKED" in result

    def test_low_confidence_note(self):
        engine = _build_engine()
        features = _make_impact_features(confidence_level=0.5)
        result = engine._generate_reasoning(True, features, 0.7)
        assert "Low confidence" in result

    def test_historical_precedence_note(self):
        engine = _build_engine()
        features = _make_impact_features(historical_precedence=5)
        result = engine._generate_reasoning(True, features, 0.7)
        assert "5 similar precedents" in result


class TestBuildConservativeFallbackDecision:
    def test_fallback_blocks_action(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        err = RuntimeError("test failure")
        decision = AdaptiveGovernanceEngine._build_conservative_fallback_decision(err)
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH
        assert "test failure" in decision.reasoning

    def test_fallback_has_zero_features(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        decision = AdaptiveGovernanceEngine._build_conservative_fallback_decision(ValueError("x"))
        assert decision.features_used.message_length == 0
        assert decision.features_used.agent_count == 0


class TestUpdateMetrics:
    def test_updates_response_time(self):
        engine = _build_engine()
        decision = _make_decision()
        engine.decision_history.append(decision)
        engine._update_metrics(decision, 0.05)
        assert engine.metrics.average_response_time > 0

    def test_compliance_rate_updated(self):
        engine = _build_engine()
        # Add decisions with high confidence
        for _ in range(5):
            d = _make_decision(confidence_score=0.99)
            engine.decision_history.append(d)
        engine._update_metrics(engine.decision_history[-1], 0.01)
        assert engine.metrics.constitutional_compliance_rate > 0


class TestAnalyzePerformanceTrends:
    def test_appends_trends(self):
        engine = _build_engine()
        engine.metrics.constitutional_compliance_rate = 0.9
        engine.metrics.false_positive_rate = 0.1
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) == 1
        assert len(engine.metrics.accuracy_trend) == 1
        assert len(engine.metrics.performance_trend) == 1


class TestShouldRetrainModels:
    def test_retrain_when_compliance_low(self):
        engine = _build_engine()
        engine.metrics.constitutional_compliance_rate = 0.5
        engine.performance_target = 0.9
        assert engine._should_retrain_models() is True

    def test_no_retrain_when_compliance_high_and_insufficient_data(self):
        engine = _build_engine()
        engine.metrics.constitutional_compliance_rate = 0.99
        engine.performance_target = 0.9
        assert engine._should_retrain_models() is False


class TestLogPerformanceSummary:
    def test_does_not_raise(self):
        engine = _build_engine()
        engine._log_performance_summary()


class TestGetTrajectoryPrefix:
    def test_returns_none_when_empty(self):
        engine = _build_engine()
        assert engine._get_trajectory_prefix() is None

    def test_returns_state_indices(self):
        engine = _build_engine()
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.HIGH))
        prefix = engine._get_trajectory_prefix()
        assert prefix is not None
        assert len(prefix) == 2


class TestApplyDtmcRiskBlend:
    def test_no_blend_when_dtmc_disabled(self):
        engine = _build_engine()
        features = _make_impact_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_blend_applied_when_enabled(self):
        config = SimpleNamespace(
            enable_dtmc=True,
            dtmc_impact_weight=0.5,
            dtmc_intervention_threshold=0.8,
        )
        engine = _build_engine(config=config)
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.predict_risk = MagicMock(return_value=0.6)
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        features = _make_impact_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == pytest.approx(0.3 + 0.6 * 0.5)


class TestApplyDtmcEscalation:
    def test_no_escalation_when_disabled(self):
        engine = _build_engine()
        decision = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.LOW

    def test_escalation_when_dtmc_intervenes(self):
        config = SimpleNamespace(
            enable_dtmc=True,
            dtmc_impact_weight=0.5,
            dtmc_intervention_threshold=0.5,
        )
        engine = _build_engine(config=config)
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene = MagicMock(return_value=True)
        engine._dtmc_learner.predict_risk = MagicMock(return_value=0.9)
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        decision = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH
        assert result.action_allowed is False

    def test_no_escalation_when_already_high(self):
        config = SimpleNamespace(
            enable_dtmc=True,
            dtmc_impact_weight=0.5,
            dtmc_intervention_threshold=0.5,
        )
        engine = _build_engine(config=config)
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene = MagicMock(return_value=True)
        engine._dtmc_learner.predict_risk = MagicMock(return_value=0.9)
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.HIGH))
        decision = _make_decision(impact_level=ImpactLevel.HIGH)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH


class TestMaybeRefitDtmc:
    def test_no_refit_when_disabled(self):
        engine = _build_engine()
        engine._maybe_refit_dtmc()  # should not raise

    def test_no_refit_insufficient_data(self):
        config = SimpleNamespace(enable_dtmc=True, dtmc_intervention_threshold=0.8)
        engine = _build_engine(config=config)
        for _ in range(5):
            engine.decision_history.append(_make_decision())
        engine._maybe_refit_dtmc()  # not enough data (< 10)

    def test_refit_with_enough_data(self):
        config = SimpleNamespace(enable_dtmc=True, dtmc_intervention_threshold=0.8)
        engine = _build_engine(config=config)
        for _ in range(15):
            engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        engine._maybe_refit_dtmc()


class TestEvaluateGovernanceDecision:
    async def test_returns_decision(self):
        engine = _build_engine()
        engine.impact_scorer.assess_impact = AsyncMock(
            return_value=_make_impact_features(risk_score=0.3)
        )
        engine._decision_validator.validate_decision = AsyncMock(return_value=(True, []))
        result = await engine.evaluate_governance_decision(
            message={"content": "test"}, context={"tenant": "t1"}
        )
        assert isinstance(result, GovernanceDecision)
        assert result.action_allowed is True

    async def test_fallback_on_error(self):
        engine = _build_engine()
        engine.impact_scorer.assess_impact = AsyncMock(side_effect=RuntimeError("boom"))
        result = await engine.evaluate_governance_decision(message={"content": "test"}, context={})
        assert result.action_allowed is False
        assert "boom" in result.reasoning


class TestProvideFeedback:
    def test_basic_feedback(self):
        engine = _build_engine()
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)

    def test_feedback_with_human_override(self):
        engine = _build_engine()
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=False, human_override=True)

    def test_feedback_error_handled(self):
        engine = _build_engine()
        decision = _make_decision()
        engine.threshold_manager.update_model = MagicMock(side_effect=RuntimeError("fail"))
        engine.provide_feedback(decision, outcome_success=True)


class TestInitializeAndShutdown:
    async def test_initialize_sets_running(self):
        engine = _build_engine()
        await engine.initialize()
        assert engine.running is True
        await engine.shutdown()
        assert engine.running is False

    async def test_shutdown_cancels_task(self):
        engine = _build_engine()
        await engine.initialize()
        assert engine.learning_task is not None
        await engine.shutdown()


class TestDefaultRiverFeatureNames:
    def test_returns_list(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        names = AdaptiveGovernanceEngine._default_river_feature_names()
        assert isinstance(names, list)
        assert "risk_score" in names
        assert "confidence_level" in names


class TestLearningThread:
    def test_learning_thread_alias(self):
        engine = _build_engine()
        assert engine._learning_thread is engine.learning_task


class TestGetRiverModelStats:
    def test_returns_none_when_unavailable(self):
        engine = _build_engine()
        assert engine.get_river_model_stats() is None


class TestGetAbTestRouter:
    def test_returns_none_when_unavailable(self):
        engine = _build_engine()
        assert engine.get_ab_test_router() is None


class TestGetAbTestMetrics:
    def test_returns_none_when_unavailable(self):
        engine = _build_engine()
        assert engine.get_ab_test_metrics() is None


class TestGetAbTestComparison:
    def test_returns_none_when_unavailable(self):
        engine = _build_engine()
        assert engine.get_ab_test_comparison() is None


class TestPromoteCandidateModel:
    def test_returns_none_when_unavailable(self):
        engine = _build_engine()
        assert engine.promote_candidate_model() is None


class TestRecordDecisionMetrics:
    def test_appends_decision(self):
        engine = _build_engine()
        decision = _make_decision()
        engine._record_decision_metrics(decision, time.time() - 0.01)
        assert len(engine.decision_history) == 1


class TestBuildDecisionForFeatures:
    def test_builds_allowed_decision(self):
        engine = _build_engine()
        features = _make_impact_features(risk_score=0.1)
        decision = engine._build_decision_for_features(features, "test-id")
        assert decision.action_allowed is True
        assert decision.decision_id == "test-id"

    def test_builds_blocked_decision(self):
        engine = _build_engine()
        features = _make_impact_features(risk_score=0.99)
        decision = engine._build_decision_for_features(features, "test-id")
        assert decision.action_allowed is False


class TestRunScheduledDriftDetection:
    def test_no_op_when_unavailable(self):
        engine = _build_engine()
        engine._run_scheduled_drift_detection()  # should not raise

    def test_no_op_when_interval_not_elapsed(self):
        engine = _build_engine()
        engine._drift_detector = MagicMock()
        engine._last_drift_check = time.time()  # just checked
        engine._run_scheduled_drift_detection()
        engine._drift_detector.detect_drift.assert_not_called()


class TestCollectDriftData:
    def test_returns_none_when_no_history(self):
        engine = _build_engine()
        assert engine._collect_drift_data() is None

    def test_returns_dataframe_with_history(self):
        pytest.importorskip("pandas")
        engine = _build_engine()
        engine.decision_history.append(_make_decision())
        result = engine._collect_drift_data()
        assert result is not None
        assert len(result) == 1


class TestGetLatestDriftReport:
    def test_returns_none_initially(self):
        engine = _build_engine()
        assert engine.get_latest_drift_report() is None


# ===========================================================================
# pqc_validators tests
# ===========================================================================


class TestPqcValidatorsHelper:
    def test_process_returns_string(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process("hello") == "hello"

    def test_process_returns_none_for_none(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process(None) is None

    def test_process_returns_none_for_non_string(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process(123) is None  # type: ignore[arg-type]

    def test_custom_hash(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators(constitutional_hash="abc123")
        assert v._constitutional_hash == "abc123"


class TestGetModeSafe:
    async def test_returns_mode_from_config(self):
        from enhanced_agent_bus.pqc_validators import _get_mode_safe

        config = AsyncMock()
        config.get_mode.return_value = "permissive"
        result = await _get_mode_safe(config)
        assert result == "permissive"

    async def test_fails_safe_to_strict(self):
        from enhanced_agent_bus.pqc_validators import _get_mode_safe

        config = AsyncMock()
        config.get_mode.side_effect = RuntimeError("boom")
        result = await _get_mode_safe(config)
        assert result == "strict"


class TestCheckEnforcementForCreate:
    async def test_migration_context_bypasses(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        await check_enforcement_for_create(
            key_type="classical",
            key_algorithm="Ed25519",
            enforcement_config=config,
            migration_context=True,
        )

    async def test_non_strict_mode_allows(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode.return_value = "permissive"
        await check_enforcement_for_create(
            key_type="classical",
            key_algorithm="Ed25519",
            enforcement_config=config,
        )

    async def test_strict_no_key_raises(self):
        from enhanced_agent_bus.pqc_validators import (
            PQCKeyRequiredError,
            check_enforcement_for_create,
        )

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        with pytest.raises(PQCKeyRequiredError):
            await check_enforcement_for_create(
                key_type=None,
                key_algorithm=None,
                enforcement_config=config,
            )

    async def test_strict_classical_key_rejected(self):
        from enhanced_agent_bus.pqc_validators import (
            ClassicalKeyRejectedError,
            check_enforcement_for_create,
        )

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        with pytest.raises(ClassicalKeyRejectedError):
            await check_enforcement_for_create(
                key_type="classical",
                key_algorithm="Ed25519",
                enforcement_config=config,
            )

    async def test_strict_pqc_valid_algorithm(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        await check_enforcement_for_create(
            key_type="pqc",
            key_algorithm="ML-DSA-65",
            enforcement_config=config,
        )

    async def test_strict_pqc_invalid_algorithm(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        with pytest.raises(UnsupportedPQCAlgorithmError):
            await check_enforcement_for_create(
                key_type="pqc",
                key_algorithm="INVALID-ALG",
                enforcement_config=config,
            )


class TestCheckEnforcementForUpdate:
    async def test_migration_context_bypasses(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        await check_enforcement_for_update(
            existing_key_type="classical",
            enforcement_config=config,
            migration_context=True,
        )

    async def test_non_strict_allows(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode.return_value = "permissive"
        await check_enforcement_for_update(
            existing_key_type="classical",
            enforcement_config=config,
        )

    async def test_strict_classical_raises_migration(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        with pytest.raises(Exception, match="migrated"):
            await check_enforcement_for_update(
                existing_key_type="classical",
                enforcement_config=config,
            )

    async def test_strict_pqc_key_allows(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode.return_value = "strict"
        await check_enforcement_for_update(
            existing_key_type="pqc",
            enforcement_config=config,
        )


class TestValidateConstitutionalHashPqc:
    async def test_missing_hash_returns_invalid(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(data={})
        assert result.valid is False
        assert any("Missing" in e for e in result.errors)

    async def test_hash_mismatch_returns_invalid(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(
            data={"constitutional_hash": "wrong_hash_value"}
        )
        assert result.valid is False
        assert any("mismatch" in e for e in result.errors)

    async def test_short_mismatched_hash(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(data={"constitutional_hash": "short"})
        assert result.valid is False

    async def test_valid_hash_no_signature(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(
            data={"constitutional_hash": CONSTITUTIONAL_HASH}
        )
        assert result.valid is True
        assert result.validation_duration_ms is not None

    async def test_valid_hash_with_signature_pqc_disabled(self):
        """When PQC is disabled and signature has 'signature' key, classical path is used.

        The production ValidationResult stub lacks classical_verification_ms,
        so we patch ValidationResult to accept arbitrary kwargs.
        """
        from dataclasses import dataclass
        from dataclasses import field as dc_field

        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        @dataclass
        class _VR:
            valid: bool = False
            constitutional_hash: str = ""
            errors: list = dc_field(default_factory=list)
            warnings: list = dc_field(default_factory=list)
            pqc_metadata: object = None
            validation_duration_ms: float | None = None
            classical_verification_ms: float | None = None
            pqc_verification_ms: float | None = None
            hybrid_signature: object = None

        with patch("enhanced_agent_bus.pqc_validators.ValidationResult", _VR):
            result = await validate_constitutional_hash_pqc(
                data={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "signature": {"signature": "abc123"},
                },
                pqc_config=None,
            )
            assert result.valid is True
            assert result.pqc_metadata is not None

    async def test_valid_hash_signature_dict_no_sig_key(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "signature": {"other": "data"},
            },
            pqc_config=None,
        )
        assert result.valid is True

    async def test_signature_not_dict(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "signature": "raw-string-sig",
            },
            pqc_config=None,
        )
        assert result.valid is True

    async def test_pqc_enabled_v1_classical(self):
        from dataclasses import dataclass
        from dataclasses import field as dc_field

        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        @dataclass
        class _VR:
            valid: bool = False
            constitutional_hash: str = ""
            errors: list = dc_field(default_factory=list)
            warnings: list = dc_field(default_factory=list)
            pqc_metadata: object = None
            validation_duration_ms: float | None = None
            classical_verification_ms: float | None = None
            pqc_verification_ms: float | None = None
            hybrid_signature: object = None

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")
        config.migration_phase = "phase_3"
        config.enforce_content_hash = False

        with (
            patch("enhanced_agent_bus.pqc_validators.PQCCryptoService") as mock_svc_cls,
            patch("enhanced_agent_bus.pqc_validators.ValidationResult", _VR),
        ):
            mock_svc = MagicMock()
            mock_svc.config = config
            mock_svc_cls.return_value = mock_svc

            result = await validate_constitutional_hash_pqc(
                data={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "signature": {"version": "v1", "signature": "abc"},
                },
                pqc_config=config,
            )
            assert result.valid is True
            assert result.pqc_metadata is not None

    async def test_pqc_enabled_v1_phase5_warning(self):
        from dataclasses import dataclass
        from dataclasses import field as dc_field

        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        @dataclass
        class _VR:
            valid: bool = False
            constitutional_hash: str = ""
            errors: list = dc_field(default_factory=list)
            warnings: list = dc_field(default_factory=list)
            pqc_metadata: object = None
            validation_duration_ms: float | None = None
            classical_verification_ms: float | None = None
            pqc_verification_ms: float | None = None
            hybrid_signature: object = None

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")
        config.migration_phase = "phase_5"
        config.enforce_content_hash = False

        with (
            patch("enhanced_agent_bus.pqc_validators.PQCCryptoService") as mock_svc_cls,
            patch("enhanced_agent_bus.pqc_validators.ValidationResult", _VR),
        ):
            mock_svc = MagicMock()
            mock_svc.config = config
            mock_svc_cls.return_value = mock_svc

            result = await validate_constitutional_hash_pqc(
                data={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "signature": {"version": "v1", "signature": "abc"},
                },
                pqc_config=config,
            )
            assert result.valid is True
            assert any("deprecated" in w for w in result.warnings)

    async def test_constitutional_hash_mismatch_error_caught(self):
        from enhanced_agent_bus._compat.security.pqc import ConstitutionalHashMismatchError
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")

        with patch("enhanced_agent_bus.pqc_validators.PQCCryptoService") as mock_svc_cls:
            mock_svc_cls.side_effect = ConstitutionalHashMismatchError("bad hash")

            result = await validate_constitutional_hash_pqc(
                data={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "signature": {"version": "v2"},
                },
                pqc_config=config,
            )
            assert result.valid is False

    async def test_pqc_verification_error_caught(self):
        from enhanced_agent_bus._compat.security.pqc import PQCVerificationError
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")

        with patch("enhanced_agent_bus.pqc_validators.PQCCryptoService") as mock_svc_cls:
            mock_svc_cls.side_effect = PQCVerificationError("bad sig")

            result = await validate_constitutional_hash_pqc(
                data={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "signature": {"version": "v2"},
                },
                pqc_config=config,
            )
            assert result.valid is False
            assert any("PQC verification" in e for e in result.errors)

    async def test_unexpected_error_caught(self):
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")

        with patch("enhanced_agent_bus.pqc_validators.PQCCryptoService") as mock_svc_cls:
            mock_svc_cls.side_effect = ValueError("unexpected")

            result = await validate_constitutional_hash_pqc(
                data={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "signature": {"version": "v2"},
                },
                pqc_config=config,
            )
            assert result.valid is False


class TestValidateMaciRecordPqc:
    async def test_missing_required_fields(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(record={})
        assert result.valid is False
        assert any("agent_id" in e for e in result.errors)

    async def test_hash_mismatch(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "a1",
                "action": "validate",
                "timestamp": "2024-01-01",
                "constitutional_hash": "wrong_hash",
            }
        )
        assert result.valid is False
        assert any("mismatch" in e for e in result.errors)

    async def test_self_validation_detected(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01",
                "target_output_id": "output-agent-1-001",
                "output_author": "agent-1",
            }
        )
        assert result.valid is False
        assert any("Self-validation" in e for e in result.errors)

    async def test_valid_record_classical(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01",
            }
        )
        assert result.valid is True

    async def test_valid_record_with_pqc_config_no_signature(self):
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")
        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01",
            },
            pqc_config=config,
        )
        assert result.valid is True

    async def test_self_validation_via_target_id(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2024-01-01",
                "target_output_id": "agent-1-output-xyz",
            }
        )
        assert result.valid is False


class TestIsSelfValidation:
    def test_output_author_matches(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-123", {"output_author": "agent-1"}) is True

    def test_output_author_no_match(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-123", {"output_author": "agent-2"}) is False

    def test_agent_id_in_target(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "agent-1-output-xyz", {}) is True

    def test_no_match(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-for-agent-2", {}) is False


class TestExtractMessageContent:
    def test_excludes_signature(self):
        from enhanced_agent_bus.pqc_validators import _extract_message_content

        data = {"a": 1, "b": 2, "signature": "sig"}
        content = _extract_message_content(data)
        assert b"signature" not in content
        assert b'"a"' in content

    def test_canonical_json(self):
        from enhanced_agent_bus.pqc_validators import _extract_message_content

        data = {"z": 1, "a": 2}
        content = _extract_message_content(data)
        assert content.index(b'"a"') < content.index(b'"z"')


class TestValidateSignature:
    async def test_classical_in_hybrid_mode(self):
        from enhanced_agent_bus.pqc_validators import validate_signature

        mock_reg = MagicMock()
        mock_reg.key_registry_client._registry = None

        with patch("importlib.import_module", return_value=mock_reg):
            result = await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="Ed25519",
                hybrid_mode=True,
            )
            assert result["valid"] is True
            assert result["key_type"] == "classical"
            assert result["algorithm"] == "Ed25519"

    async def test_pqc_algorithm(self):
        from enhanced_agent_bus.pqc_validators import validate_signature

        mock_reg = MagicMock()
        mock_reg.key_registry_client._registry = None

        with patch("importlib.import_module", return_value=mock_reg):
            result = await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-2",
                algorithm="ML-DSA-65",
                hybrid_mode=True,
            )
            assert result["valid"] is True
            assert result["key_type"] == "pqc"

    async def test_classical_rejected_in_pqc_only_mode(self):
        from enhanced_agent_bus.pqc_validators import (
            ClassicalKeyRejectedError,
            validate_signature,
        )

        with pytest.raises(ClassicalKeyRejectedError):
            await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="Ed25519",
                hybrid_mode=False,
            )

    async def test_unsupported_algorithm(self):
        from enhanced_agent_bus._compat.security.pqc import UnsupportedAlgorithmError
        from enhanced_agent_bus.pqc_validators import validate_signature

        with pytest.raises(UnsupportedAlgorithmError):
            await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="TOTALLY-FAKE",
                hybrid_mode=True,
            )

    async def test_key_registry_error_raises(self):
        from enhanced_agent_bus.pqc_validators import (
            KeyRegistryUnavailableError,
            validate_signature,
        )

        with patch("importlib.import_module", side_effect=RuntimeError("registry down")):
            with pytest.raises(KeyRegistryUnavailableError):
                await validate_signature(
                    payload=b"test",
                    signature=b"sig",
                    key_id="key-1",
                    algorithm="ML-DSA-65",
                    hybrid_mode=True,
                )


class TestCheckKeyRegistryStatus:
    async def test_returns_active_on_error(self):
        from enhanced_agent_bus.pqc_validators import _check_key_registry_status

        with patch("importlib.import_module", side_effect=RuntimeError("unavailable")):
            result = await _check_key_registry_status("key-1")
            assert result == "active"

    async def test_returns_active_when_no_registry(self):
        from enhanced_agent_bus.pqc_validators import _check_key_registry_status

        mock_reg = MagicMock()
        mock_reg.key_registry_client._registry = None
        with patch("importlib.import_module", return_value=mock_reg):
            result = await _check_key_registry_status("key-1")
            assert result == "active"


class TestVerifyClassicalComponent:
    def test_no_classical_key_returns_true(self):
        from enhanced_agent_bus.pqc_validators import _verify_classical_component

        result = _verify_classical_component({}, MagicMock(), b"msg")
        assert result is True

    def test_no_classical_attr_returns_true(self):
        from enhanced_agent_bus.pqc_validators import _verify_classical_component

        sig = SimpleNamespace()  # no .classical attr
        result = _verify_classical_component({"classical": b"key"}, sig, b"msg")
        assert result is True


class TestVerifyPqcComponent:
    def test_no_pqc_key_returns_true(self):
        from enhanced_agent_bus.pqc_validators import _verify_pqc_component

        result = _verify_pqc_component({}, MagicMock(), b"msg")
        assert result is True

    def test_no_pqc_attr_returns_true(self):
        from enhanced_agent_bus.pqc_validators import _verify_pqc_component

        sig = SimpleNamespace()  # no .pqc attr
        result = _verify_pqc_component({"pqc": b"key"}, sig, b"msg")
        assert result is True


class TestCheckKeyStatusForValidation:
    async def test_no_key_id_returns_none(self):
        from enhanced_agent_bus.pqc_validators import (
            _check_key_status_for_validation,
        )

        result = await _check_key_status_for_validation(
            data={},
            signature_data={},
            errors=[],
            warnings=[],
            expected_hash=CONSTITUTIONAL_HASH,
            start_time=time.perf_counter(),
        )
        assert result is None

    async def test_revoked_key_returns_result(self):
        from enhanced_agent_bus.pqc_validators import (
            _check_key_status_for_validation,
        )

        with patch(
            "enhanced_agent_bus.pqc_validators._check_key_registry_status",
            new_callable=AsyncMock,
            return_value="revoked",
        ):
            errors: list[str] = []
            result = await _check_key_status_for_validation(
                data={"key_id": "k1"},
                signature_data={},
                errors=errors,
                warnings=[],
                expected_hash=CONSTITUTIONAL_HASH,
                start_time=time.perf_counter(),
            )
            assert result is not None
            assert result.valid is False

    async def test_superseded_key_adds_warning(self):
        from enhanced_agent_bus.pqc_validators import (
            _check_key_status_for_validation,
        )

        with patch(
            "enhanced_agent_bus.pqc_validators._check_key_registry_status",
            new_callable=AsyncMock,
            return_value="superseded",
        ):
            warnings: list[str] = []
            result = await _check_key_status_for_validation(
                data={},
                signature_data={"key_id": "k2"},
                errors=[],
                warnings=warnings,
                expected_hash=CONSTITUTIONAL_HASH,
                start_time=time.perf_counter(),
            )
            assert result is None
            assert any("superseded" in w for w in warnings)


class TestSupportedPqcAlgorithms:
    def test_has_algorithms(self):
        from enhanced_agent_bus.pqc_validators import SUPPORTED_PQC_ALGORITHMS

        assert len(SUPPORTED_PQC_ALGORITHMS) > 0
        assert "ML-DSA-65" in SUPPORTED_PQC_ALGORITHMS


class TestValidateMaciRecordWithPqcSignature:
    async def test_pqc_signature_validation_delegated(self):
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")

        with patch(
            "enhanced_agent_bus.pqc_validators.validate_constitutional_hash_pqc",
            new_callable=AsyncMock,
        ) as mock_validate:
            from enhanced_agent_bus._compat.security.pqc_crypto import ValidationResult

            mock_validate.return_value = ValidationResult(
                valid=True,
                constitutional_hash=CONSTITUTIONAL_HASH,
                errors=[],
                warnings=[],
            )
            result = await validate_maci_record_pqc(
                record={
                    "agent_id": "a1",
                    "action": "propose",
                    "timestamp": "2024-01-01",
                    "signature": {"version": "v2"},
                },
                pqc_config=config,
            )
            assert result.valid is True
            mock_validate.assert_awaited_once()

    async def test_pqc_signature_validation_failure_adds_error(self):
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        config = PQCConfig(pqc_enabled=True, verification_mode="strict")

        with patch(
            "enhanced_agent_bus.pqc_validators.validate_constitutional_hash_pqc",
            new_callable=AsyncMock,
        ) as mock_validate:
            from enhanced_agent_bus._compat.security.pqc_crypto import ValidationResult

            mock_validate.return_value = ValidationResult(
                valid=False,
                constitutional_hash=CONSTITUTIONAL_HASH,
                errors=["sig invalid"],
                warnings=[],
            )
            result = await validate_maci_record_pqc(
                record={
                    "agent_id": "a1",
                    "action": "propose",
                    "timestamp": "2024-01-01",
                    "signature": {"version": "v2"},
                },
                pqc_config=config,
            )
            assert result.valid is False
            assert any("MACI" in e for e in result.errors)


class TestValidateMaciRecordClassicalWithPqcConfig:
    async def test_classical_with_pqc_config_returns_metadata(self):
        from enhanced_agent_bus._compat.security.pqc_crypto import PQCConfig
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        config = PQCConfig(pqc_enabled=False, verification_mode="classical_only")
        result = await validate_maci_record_pqc(
            record={
                "agent_id": "a1",
                "action": "propose",
                "timestamp": "2024-01-01",
            },
            pqc_config=config,
        )
        assert result.valid is True
        assert result.pqc_metadata is not None
        assert result.pqc_metadata.pqc_enabled is False

    async def test_classical_no_config_no_metadata(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "a1",
                "action": "propose",
                "timestamp": "2024-01-01",
            },
            pqc_config=None,
        )
        assert result.valid is True
        assert result.pqc_metadata is None
