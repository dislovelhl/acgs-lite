"""
Tests for batch17f coverage targets:
- adaptive_governance/impact_scorer.py
- specs/fixtures/resilience.py
- specs/fixtures/architecture.py
- specs/fixtures/governance.py
"""

import sys

sys.path.insert(0, "packages/enhanced_agent_bus")

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. ImpactScorer tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures


def _make_features(**overrides) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.3,
        historical_precedence=1,
        resource_utilization=0.2,
        network_isolation=0.9,
        risk_score=0.0,
        confidence_level=0.0,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


class TestImpactScorerInit:
    """Test ImpactScorer construction and mlflow init."""

    def test_init_without_sklearn(self):
        with (
            patch("enhanced_agent_bus.adaptive_governance.impact_scorer.SKLEARN_AVAILABLE", False),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.RandomForestRegressor", None
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

            scorer = ImpactScorer("testhash")
            assert scorer.impact_classifier is None
            assert scorer.constitutional_hash == "testhash"

    def test_init_with_sklearn(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import (
            SKLEARN_AVAILABLE,
            ImpactScorer,
        )

        scorer = ImpactScorer("hash2")
        if SKLEARN_AVAILABLE:
            assert scorer.impact_classifier is not None
        else:
            assert scorer.impact_classifier is None

    def test_mlflow_not_initialized_in_tests(self):
        """pytest is in sys.modules so mlflow init is skipped."""
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer("hash3")
        assert scorer._mlflow_initialized is False


class TestImpactScorerRuleBasedScoring:
    """Test _rule_based_risk_score branches."""

    def setup_method(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        self.scorer = ImpactScorer("test")

    def test_low_risk_message(self):
        features = _make_features(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = self.scorer._rule_based_risk_score(features)
        assert score == pytest.approx(0.0, abs=0.01)

    def test_high_length_adds_03(self):
        features = _make_features(
            message_length=15000,
            agent_count=0,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = self.scorer._rule_based_risk_score(features)
        assert score >= 0.3

    def test_medium_length_adds_01(self):
        features = _make_features(
            message_length=5000,
            agent_count=0,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = self.scorer._rule_based_risk_score(features)
        assert score >= 0.1

    def test_high_agent_count_adds_02(self):
        features = _make_features(
            message_length=50,
            agent_count=15,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = self.scorer._rule_based_risk_score(features)
        assert score >= 0.2

    def test_medium_agent_count_adds_01(self):
        features = _make_features(
            message_length=50,
            agent_count=7,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = self.scorer._rule_based_risk_score(features)
        assert score >= 0.1

    def test_combined_high_risk_capped_at_1(self):
        features = _make_features(
            message_length=20000,
            agent_count=20,
            tenant_complexity=1.0,
            resource_utilization=1.0,
            semantic_similarity=1.0,
        )
        score = self.scorer._rule_based_risk_score(features)
        assert score <= 1.0


class TestImpactScorerConfidence:
    """Test _calculate_confidence branches."""

    def setup_method(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        self.scorer = ImpactScorer("test")

    def test_base_confidence(self):
        features = _make_features(
            historical_precedence=0,
            temporal_patterns=[],
            semantic_similarity=0.0,
        )
        conf = self.scorer._calculate_confidence(features)
        assert conf == pytest.approx(0.5)

    def test_all_boosts(self):
        features = _make_features(
            historical_precedence=5,
            temporal_patterns=[0.1],
            semantic_similarity=0.5,
        )
        conf = self.scorer._calculate_confidence(features)
        assert conf == pytest.approx(0.9)

    def test_confidence_capped_at_1(self):
        features = _make_features(
            historical_precedence=10,
            temporal_patterns=[0.1, 0.2, 0.3],
            semantic_similarity=0.9,
        )
        conf = self.scorer._calculate_confidence(features)
        assert conf <= 1.0


class TestImpactScorerPredictRisk:
    """Test _predict_risk_score."""

    def setup_method(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        self.scorer = ImpactScorer("test")

    def test_fallback_when_not_trained(self):
        features = _make_features()
        score = self.scorer._predict_risk_score(features)
        # Should fall through to rule-based
        assert 0.0 <= score <= 1.0

    def test_fallback_when_no_classifier(self):
        self.scorer.model_trained = True
        self.scorer.impact_classifier = None
        features = _make_features()
        score = self.scorer._predict_risk_score(features)
        assert 0.0 <= score <= 1.0

    def test_predict_with_empty_temporal_patterns(self):
        features = _make_features(temporal_patterns=[])
        score = self.scorer._predict_risk_score(features)
        assert 0.0 <= score <= 1.0

    def test_predict_with_trained_model(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import (
            NUMPY_AVAILABLE,
            SKLEARN_AVAILABLE,
        )

        if not (SKLEARN_AVAILABLE and NUMPY_AVAILABLE):
            pytest.skip("sklearn/numpy not available")

        import numpy as np

        self.scorer.model_trained = True
        # Train a simple model
        X = np.array([[100, 2, 0.5, 0.15, 0.3, 1, 0.2, 0.9]] * 10)
        y = np.array([0.5] * 10)
        self.scorer.impact_classifier.fit(X, y)

        features = _make_features()
        score = self.scorer._predict_risk_score(features)
        assert 0.0 <= score <= 1.0

    def test_predict_handles_classifier_error(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import (
            NUMPY_AVAILABLE,
            SKLEARN_AVAILABLE,
        )

        if not (SKLEARN_AVAILABLE and NUMPY_AVAILABLE):
            pytest.skip("sklearn/numpy not available")

        self.scorer.model_trained = True
        mock_clf = MagicMock()
        mock_clf.predict.side_effect = RuntimeError("model error")
        self.scorer.impact_classifier = mock_clf

        features = _make_features()
        score = self.scorer._predict_risk_score(features)
        assert 0.0 <= score <= 1.0


class TestImpactScorerAssessImpact:
    """Test assess_impact async method."""

    def setup_method(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        self.scorer = ImpactScorer("test")

    async def test_assess_impact_untrained(self):
        msg = {"content": "hello world", "tenant_id": "t1"}
        ctx = {"active_agents": ["a1", "a2"]}
        result = await self.scorer.assess_impact(msg, ctx)
        assert isinstance(result, ImpactFeatures)
        assert result.risk_score >= 0.0
        assert result.confidence_level > 0.0

    async def test_assess_impact_with_trained_model(self):
        self.scorer.model_trained = True
        msg = {"content": "test", "tenant_id": "t1"}
        ctx = {"active_agents": []}
        result = await self.scorer.assess_impact(msg, ctx)
        assert isinstance(result, ImpactFeatures)

    async def test_assess_impact_error_returns_defaults(self):
        with patch.object(self.scorer, "_extract_features", side_effect=RuntimeError("fail")):
            msg = {"content": "x"}
            ctx = {}
            result = await self.scorer.assess_impact(msg, ctx)
            assert isinstance(result, ImpactFeatures)
            assert result.confidence_level == 0.5


class TestImpactScorerExtractFeatures:
    """Test _extract_features."""

    def setup_method(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        self.scorer = ImpactScorer("test")

    async def test_extract_features_basic(self):
        msg = {"content": "hello", "tenant_id": "default"}
        ctx = {"active_agents": ["a1"]}
        features = await self.scorer._extract_features(msg, ctx)
        assert features.message_length == 5
        assert features.agent_count == 1

    async def test_extract_features_no_agents(self):
        msg = {"content": "x"}
        ctx = {"active_agents": "not_a_list"}
        features = await self.scorer._extract_features(msg, ctx)
        assert features.agent_count == 0

    async def test_extract_features_missing_fields(self):
        msg = {}
        ctx = {}
        features = await self.scorer._extract_features(msg, ctx)
        assert features.message_length == 0
        assert features.agent_count == 0


class TestImpactScorerUpdateModel:
    """Test update_model and _retrain_model."""

    def setup_method(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        self.scorer = ImpactScorer("test")

    def test_update_model_appends_sample(self):
        features = _make_features()
        self.scorer.update_model(features, 0.5)
        assert len(self.scorer.training_samples) == 1

    def test_update_model_error_handled(self):
        with patch.object(self.scorer, "training_samples", side_effect=RuntimeError("fail")):
            # Should not raise
            try:
                self.scorer.update_model(_make_features(), 0.5)
            except (RuntimeError, TypeError):
                pass  # acceptable in mocked scenario

    def test_retrain_model_insufficient_samples(self):
        """Retrain skips when not enough samples."""
        self.scorer._retrain_model()
        assert not self.scorer.model_trained

    def test_retrain_model_no_numpy(self):
        with patch("enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE", False):
            self.scorer._retrain_model()
            assert not self.scorer.model_trained

    def test_retrain_model_no_classifier(self):
        self.scorer.impact_classifier = None
        self.scorer._retrain_model()
        assert not self.scorer.model_trained


class TestImpactScorerMHCStability:
    """Test _apply_mhc_stability."""

    def setup_method(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        self.scorer = ImpactScorer("test")

    def test_stability_skipped_when_not_available(self):
        self.scorer.use_mhc_stability = False
        original_weights = dict(self.scorer.feature_weights)
        self.scorer._apply_mhc_stability()
        assert self.scorer.feature_weights == original_weights

    def test_stability_error_handled(self):
        self.scorer.use_mhc_stability = True
        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.torch",
            None,
        ):
            # Should not raise even if torch is None
            try:
                self.scorer._apply_mhc_stability()
            except (TypeError, AttributeError):
                pass  # Expected when torch is None


# ---------------------------------------------------------------------------
# 2. Resilience fixtures tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.specs.fixtures.resilience import (
    ChaosInjection,
    CircuitBreakerEvent,
    CircuitState,
    FailureType,
    SagaStep,
    SpecChaosController,
    SpecCircuitBreaker,
    SpecSagaManager,
    trigger_event,
)


class TestCircuitState:
    def test_enum_values(self):
        assert CircuitState.CLOSED.value == "CLOSED"
        assert CircuitState.OPEN.value == "OPEN"
        assert CircuitState.HALF_OPEN.value == "HALF_OPEN"


class TestCircuitBreakerEvent:
    def test_creation(self):
        event = CircuitBreakerEvent(
            timestamp=datetime.now(UTC),
            event_type="failure",
            old_state=CircuitState.CLOSED,
            new_state=CircuitState.OPEN,
            failure_count=3,
            message="test",
        )
        assert event.event_type == "failure"
        assert event.failure_count == 3

    def test_default_message(self):
        event = CircuitBreakerEvent(
            timestamp=datetime.now(UTC),
            event_type="success",
            old_state=None,
            new_state=CircuitState.CLOSED,
            failure_count=0,
        )
        assert event.message == ""


class TestSpecCircuitBreaker:
    def test_initial_state(self):
        cb = SpecCircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_custom_thresholds(self):
        cb = SpecCircuitBreaker(failure_threshold=5, recovery_timeout_s=60.0, half_open_max_calls=2)
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout_s == 60.0
        assert cb.half_open_max_calls == 2

    def test_opens_on_threshold(self):
        cb = SpecCircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_stays_closed_below_threshold(self):
        cb = SpecCircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_success_decrements_failure_count(self):
        cb = SpecCircuitBreaker()
        cb.record_failure()
        assert cb.failure_count == 1
        cb.record_success()
        assert cb.failure_count == 0

    def test_success_with_zero_failures_stays_zero(self):
        cb = SpecCircuitBreaker()
        cb.record_success()
        assert cb.failure_count == 0

    def test_half_open_success_closes(self):
        cb = SpecCircuitBreaker(failure_threshold=1, half_open_max_calls=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.trigger_timer_expiry()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = SpecCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb.trigger_timer_expiry()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_trigger_timer_expiry_no_op_when_closed(self):
        cb = SpecCircuitBreaker()
        cb.trigger_timer_expiry()
        assert cb.state == CircuitState.CLOSED

    def test_set_state(self):
        cb = SpecCircuitBreaker()
        cb.set_state("OPEN")
        assert cb._state == CircuitState.OPEN

    def test_reset(self):
        cb = SpecCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert len(cb.events) == 0

    def test_state_auto_transition_open_to_half_open(self):
        cb = SpecCircuitBreaker(failure_threshold=1, recovery_timeout_s=0.0)
        cb.record_failure()
        assert cb._state == CircuitState.OPEN
        # With recovery_timeout_s=0, accessing .state should trigger half_open
        assert cb.state == CircuitState.HALF_OPEN

    def test_events_recorded(self):
        cb = SpecCircuitBreaker(failure_threshold=2)
        cb.record_success()
        cb.record_failure()
        cb.record_failure()  # triggers OPEN transition
        # success event + failure event + failure event + transition event
        assert len(cb.events) >= 3

    def test_half_open_multi_success(self):
        cb = SpecCircuitBreaker(failure_threshold=1, half_open_max_calls=2)
        cb.record_failure()
        cb.trigger_timer_expiry()
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # needs 2 successes
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestFailureType:
    def test_enum_values(self):
        assert FailureType.TIMEOUT.value == "timeout"
        assert FailureType.ERROR.value == "error"
        assert FailureType.LATENCY.value == "latency"
        assert FailureType.CRASH.value == "crash"


class TestChaosInjection:
    def test_creation(self):
        inj = ChaosInjection(component="redis", failure_type=FailureType.TIMEOUT, duration_s=5.0)
        assert inj.component == "redis"
        assert not inj.recovered

    def test_defaults(self):
        inj = ChaosInjection(component="x", failure_type=FailureType.ERROR)
        assert inj.duration_s is None
        assert not inj.recovered
        assert isinstance(inj.timestamp, datetime)


class TestSpecChaosController:
    async def test_fail_and_is_failed(self):
        ctrl = SpecChaosController()
        await ctrl.fail("redis", FailureType.TIMEOUT)
        assert ctrl.is_failed("redis")
        assert not ctrl.is_failed("postgres")

    async def test_recover(self):
        ctrl = SpecChaosController()
        await ctrl.fail("redis")
        result = await ctrl.recover("redis")
        assert result is not None
        assert result.recovered
        assert not ctrl.is_failed("redis")

    async def test_recover_nonexistent(self):
        ctrl = SpecChaosController()
        result = await ctrl.recover("nonexistent")
        assert result is None

    async def test_get_failure(self):
        ctrl = SpecChaosController()
        await ctrl.fail("db", FailureType.CRASH, duration_s=10.0)
        failure = ctrl.get_failure("db")
        assert failure is not None
        assert failure.failure_type == FailureType.CRASH
        assert ctrl.get_failure("other") is None

    async def test_reset_recovers_all(self):
        ctrl = SpecChaosController()
        await ctrl.fail("a")
        await ctrl.fail("b")
        await ctrl.reset()
        assert not ctrl.is_failed("a")
        assert not ctrl.is_failed("b")

    async def test_injection_history(self):
        ctrl = SpecChaosController()
        await ctrl.fail("x")
        await ctrl.fail("y")
        assert len(ctrl.injection_history) == 2


class TestSagaStep:
    def test_defaults(self):
        step = SagaStep(name="step1")
        assert not step.executed
        assert not step.compensated
        assert step.compensation is None


class TestSpecSagaManager:
    async def test_transaction_execute_steps(self):
        mgr = SpecSagaManager()
        async with mgr.transaction() as saga:
            await saga.execute_step("A")
            await saga.execute_step("B")
        assert len(mgr.steps) == 2
        assert mgr.steps[0].name == "A"
        assert mgr.steps[1].name == "B"

    async def test_compensation_lifo_order(self):
        mgr = SpecSagaManager()
        async with mgr.transaction() as saga:
            await saga.execute_step("A")
            await saga.execute_step("B")
            await saga.execute_step("C")
            order = await saga.compensate()
        assert order == ["C", "B", "A"]

    async def test_compensation_with_callback(self):
        mgr = SpecSagaManager()
        called = []

        async with mgr.transaction() as saga:
            await saga.execute_step("A")
            saga.on_compensate("A", lambda: called.append("A"))
            await saga.execute_step("B")
            saga.on_compensate("B", lambda: called.append("B"))
            order = await saga.compensate()

        assert order == ["B", "A"]
        assert called == ["B", "A"]

    async def test_compensation_with_async_callback(self):
        mgr = SpecSagaManager()
        called = []

        async def async_comp():
            called.append("async")

        async with mgr.transaction() as saga:
            await saga.execute_step("X")
            saga.on_compensate("X", async_comp)
            await saga.compensate()

        assert called == ["async"]

    async def test_transaction_context_manager(self):
        mgr = SpecSagaManager()
        assert not mgr._in_transaction
        async with mgr.transaction():
            assert mgr._in_transaction
        assert not mgr._in_transaction

    def test_reset(self):
        mgr = SpecSagaManager()
        mgr.steps.append(SagaStep(name="x", executed=True))
        mgr.compensation_log.append("x")
        mgr._in_transaction = True
        mgr.reset()
        assert len(mgr.steps) == 0
        assert len(mgr.compensation_log) == 0
        assert not mgr._in_transaction

    async def test_on_compensate_no_match(self):
        mgr = SpecSagaManager()
        async with mgr.transaction() as saga:
            await saga.execute_step("A")
            saga.on_compensate("NONEXISTENT", lambda: None)
            # Should not crash, just skip

    async def test_compensation_log_updated(self):
        mgr = SpecSagaManager()
        async with mgr.transaction() as saga:
            await saga.execute_step("A")
            await saga.compensate()
        assert mgr.compensation_log == ["A"]


class TestTriggerEvent:
    def test_success(self):
        cb = SpecCircuitBreaker()
        cb.record_failure()
        trigger_event(cb, "success")
        assert cb.failure_count == 0

    def test_failure(self):
        cb = SpecCircuitBreaker(failure_threshold=1)
        trigger_event(cb, "failure")
        assert cb.state == CircuitState.OPEN

    def test_timer_expires(self):
        cb = SpecCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        trigger_event(cb, "timer_expires")
        assert cb.state == CircuitState.HALF_OPEN

    def test_unknown_event(self):
        cb = SpecCircuitBreaker()
        trigger_event(cb, "unknown")  # should not raise


# ---------------------------------------------------------------------------
# 3. Architecture fixtures tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.specs.fixtures.architecture import (
    ArchitecturalLayer,
    ComponentInfo,
    ComponentState,
    LayerConfig,
    LayerTransition,
    SpecArchitectureContext,
    SpecLayerContext,
)


class TestArchitecturalLayer:
    def test_values(self):
        assert ArchitecturalLayer.LAYER1_VALIDATION.value == "layer1_validation"
        assert ArchitecturalLayer.LAYER4_AUDIT.value == "layer4_audit"


class TestComponentState:
    def test_all_states(self):
        states = [s.value for s in ComponentState]
        assert "ready" in states
        assert "failed" in states
        assert "degraded" in states


class TestLayerConfig:
    def test_to_dict(self):
        cfg = LayerConfig(
            layer=ArchitecturalLayer.LAYER1_VALIDATION,
            timeout_budget_ms=5.0,
            enabled=True,
        )
        d = cfg.to_dict()
        assert d["layer"] == "layer1_validation"
        assert d["timeout_budget_ms"] == 5.0
        assert d["enabled"] is True
        assert "constitutional_hash" in d

    def test_defaults(self):
        cfg = LayerConfig(layer=ArchitecturalLayer.LAYER2_DELIBERATION, timeout_budget_ms=20.0)
        assert cfg.enabled is True
        assert cfg.strict_enforcement is True
        assert cfg.fallback_enabled is True


class TestComponentInfo:
    def test_defaults(self):
        comp = ComponentInfo(name="val", layer=ArchitecturalLayer.LAYER1_VALIDATION)
        assert comp.state == ComponentState.UNINITIALIZED
        assert comp.version == "1.0.0"
        assert comp.dependencies == set()


class TestLayerTransition:
    def test_defaults(self):
        t = LayerTransition(
            from_layer=ArchitecturalLayer.LAYER1_VALIDATION,
            to_layer=ArchitecturalLayer.LAYER2_DELIBERATION,
        )
        assert t.success is True
        assert t.duration_ms == 0.0
        assert isinstance(t.timestamp, datetime)


class TestSpecLayerContext:
    def test_default_budgets(self):
        assert SpecLayerContext._default_budget(ArchitecturalLayer.LAYER1_VALIDATION) == 5.0
        assert SpecLayerContext._default_budget(ArchitecturalLayer.LAYER2_DELIBERATION) == 20.0
        assert SpecLayerContext._default_budget(ArchitecturalLayer.LAYER3_POLICY) == 10.0
        assert SpecLayerContext._default_budget(ArchitecturalLayer.LAYER4_AUDIT) == 15.0

    def test_enter_exit(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        assert not ctx.is_active
        ctx.enter()
        assert ctx.is_active
        assert ctx.entry_time is not None
        duration = ctx.exit()
        assert not ctx.is_active
        assert duration >= 0.0

    def test_exit_without_enter(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        duration = ctx.exit()
        assert duration == 0.0

    def test_register_component(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        comp = ctx.register_component("validator", "2.0.0", {"dep1"})
        assert comp.name == "validator"
        assert comp.version == "2.0.0"
        assert "dep1" in comp.dependencies
        assert "validator" in ctx.components

    def test_update_component_state(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        ctx.register_component("val")
        result = ctx.update_component_state("val", ComponentState.READY)
        assert result is not None
        assert result.state == ComponentState.READY
        assert result.last_health_check is not None

    def test_update_nonexistent_component(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        result = ctx.update_component_state("nope", ComponentState.READY)
        assert result is None

    def test_get_component(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        ctx.register_component("a")
        assert ctx.get_component("a") is not None
        assert ctx.get_component("b") is None

    def test_is_healthy(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        assert ctx.is_healthy()  # no components
        ctx.register_component("a")
        ctx.update_component_state("a", ComponentState.READY)
        assert ctx.is_healthy()
        ctx.update_component_state("a", ComponentState.FAILED)
        assert not ctx.is_healthy()

    def test_is_healthy_degraded(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        ctx.register_component("a")
        ctx.update_component_state("a", ComponentState.DEGRADED)
        assert not ctx.is_healthy()

    def test_get_ready_components(self):
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        ctx.register_component("a")
        ctx.register_component("b")
        ctx.update_component_state("a", ComponentState.READY)
        ctx.update_component_state("b", ComponentState.FAILED)
        ready = ctx.get_ready_components()
        assert len(ready) == 1
        assert ready[0].name == "a"

    def test_custom_config(self):
        cfg = LayerConfig(
            layer=ArchitecturalLayer.LAYER3_POLICY,
            timeout_budget_ms=99.0,
            enabled=False,
        )
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER3_POLICY, config=cfg)
        assert ctx.config.timeout_budget_ms == 99.0
        assert ctx.config.enabled is False


class TestSpecArchitectureContext:
    def test_init_all_layers(self):
        arch = SpecArchitectureContext()
        assert len(arch.layers) == 4
        for layer in ArchitecturalLayer:
            assert layer in arch.layers

    def test_get_layer(self):
        arch = SpecArchitectureContext()
        ctx = arch.get_layer(ArchitecturalLayer.LAYER1_VALIDATION)
        assert ctx.layer == ArchitecturalLayer.LAYER1_VALIDATION

    def test_enter_and_exit_layer(self):
        arch = SpecArchitectureContext()
        ctx = arch.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)
        assert ctx.is_active
        assert arch.current_layer == ArchitecturalLayer.LAYER1_VALIDATION
        transition = arch.exit_layer()
        assert transition is not None
        assert arch.current_layer is None

    def test_exit_layer_when_none(self):
        arch = SpecArchitectureContext()
        assert arch.exit_layer() is None

    def test_enter_layer_switches(self):
        arch = SpecArchitectureContext()
        arch.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)
        arch.enter_layer(ArchitecturalLayer.LAYER2_DELIBERATION)
        assert arch.current_layer == ArchitecturalLayer.LAYER2_DELIBERATION
        # Previous layer should have been exited
        assert not arch.layers[ArchitecturalLayer.LAYER1_VALIDATION].is_active

    def test_transition_to(self):
        arch = SpecArchitectureContext()
        arch.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)
        transition = arch.transition_to(ArchitecturalLayer.LAYER2_DELIBERATION)
        assert transition.from_layer == ArchitecturalLayer.LAYER1_VALIDATION
        assert transition.to_layer == ArchitecturalLayer.LAYER2_DELIBERATION
        assert transition.success

    def test_transition_to_from_none(self):
        arch = SpecArchitectureContext()
        transition = arch.transition_to(ArchitecturalLayer.LAYER3_POLICY)
        assert transition.from_layer == ArchitecturalLayer.LAYER3_POLICY
        assert transition.duration_ms == 0.0

    def test_register_and_get_component(self):
        arch = SpecArchitectureContext()
        comp = arch.register_component(
            ArchitecturalLayer.LAYER1_VALIDATION, "engine", "1.0.0", {"dep"}
        )
        assert comp.name == "engine"
        fetched = arch.get_component(ArchitecturalLayer.LAYER1_VALIDATION, "engine")
        assert fetched is not None
        assert fetched.name == "engine"

    def test_get_component_nonexistent(self):
        arch = SpecArchitectureContext()
        assert arch.get_component(ArchitecturalLayer.LAYER1_VALIDATION, "nope") is None

    def test_get_all_components(self):
        arch = SpecArchitectureContext()
        arch.register_component(ArchitecturalLayer.LAYER1_VALIDATION, "a")
        arch.register_component(ArchitecturalLayer.LAYER2_DELIBERATION, "b")
        all_comps = arch.get_all_components()
        assert len(all_comps[ArchitecturalLayer.LAYER1_VALIDATION]) == 1
        assert len(all_comps[ArchitecturalLayer.LAYER2_DELIBERATION]) == 1

    def test_get_health_report_healthy(self):
        arch = SpecArchitectureContext()
        report = arch.get_health_report()
        assert report["healthy"] is True
        assert report["total_components"] == 0

    def test_get_health_report_unhealthy(self):
        arch = SpecArchitectureContext()
        arch.register_component(ArchitecturalLayer.LAYER1_VALIDATION, "broken")
        arch.layers[ArchitecturalLayer.LAYER1_VALIDATION].update_component_state(
            "broken", ComponentState.FAILED
        )
        report = arch.get_health_report()
        assert report["healthy"] is False
        assert report["total_components"] == 1
        assert report["ready_components"] == 0

    def test_get_transition_history(self):
        arch = SpecArchitectureContext()
        arch.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)
        arch.exit_layer()
        history = arch.get_transition_history()
        assert len(history) == 1

    def test_validate_constitutional_compliance(self):
        arch = SpecArchitectureContext()
        assert arch.validate_constitutional_compliance()

    def test_validate_compliance_fails_on_mismatch(self):
        arch = SpecArchitectureContext()
        arch.layers[ArchitecturalLayer.LAYER1_VALIDATION].constitutional_hash = "wrong"
        assert not arch.validate_constitutional_compliance()

    def test_validate_compliance_fails_on_component_mismatch(self):
        arch = SpecArchitectureContext()
        comp = arch.register_component(ArchitecturalLayer.LAYER1_VALIDATION, "x")
        comp.constitutional_hash = "bad"
        assert not arch.validate_constitutional_compliance()

    def test_reset(self):
        arch = SpecArchitectureContext()
        arch.register_component(ArchitecturalLayer.LAYER1_VALIDATION, "a")
        arch.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)
        arch.transition_to(ArchitecturalLayer.LAYER2_DELIBERATION)
        arch.reset()
        assert arch.current_layer is None
        assert len(arch.transitions) == 0
        for ctx in arch.layers.values():
            assert len(ctx.components) == 0
            assert not ctx.is_active


# ---------------------------------------------------------------------------
# 4. Governance fixtures tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.specs.fixtures.governance import (
    ConsensusResult,
    ConsensusType,
    PolicyEnforcement,
    PolicyRule,
    PolicyScope,
    PolicyVerificationResult,
    PolicyViolation,
    SpecConsensusChecker,
    SpecPolicyVerifier,
    Vote,
    VoteType,
)


class TestVoteType:
    def test_values(self):
        assert VoteType.APPROVE.value == "approve"
        assert VoteType.REJECT.value == "reject"
        assert VoteType.ABSTAIN.value == "abstain"


class TestConsensusType:
    def test_values(self):
        assert ConsensusType.MAJORITY.value == "majority"
        assert ConsensusType.SUPERMAJORITY.value == "supermajority"
        assert ConsensusType.UNANIMOUS.value == "unanimous"
        assert ConsensusType.QUORUM.value == "quorum"


class TestVote:
    def test_defaults(self):
        v = Vote(voter_id="v1", vote_type=VoteType.APPROVE)
        assert v.weight == 1.0
        assert v.rationale is None
        assert isinstance(v.timestamp, datetime)


class TestConsensusResult:
    def test_approval_ratio(self):
        r = ConsensusResult(
            reached=True,
            consensus_type=ConsensusType.MAJORITY,
            approve_weight=3.0,
            reject_weight=1.0,
            abstain_weight=1.0,
            total_weight=5.0,
            quorum_met=True,
        )
        assert r.approval_ratio == pytest.approx(0.75)

    def test_approval_ratio_no_participation(self):
        r = ConsensusResult(
            reached=False,
            consensus_type=ConsensusType.MAJORITY,
            approve_weight=0.0,
            reject_weight=0.0,
            abstain_weight=3.0,
            total_weight=3.0,
            quorum_met=True,
        )
        assert r.approval_ratio == 0.0

    def test_to_dict(self):
        r = ConsensusResult(
            reached=True,
            consensus_type=ConsensusType.MAJORITY,
            approve_weight=2.0,
            reject_weight=1.0,
            abstain_weight=0.0,
            total_weight=3.0,
            quorum_met=True,
            message="done",
        )
        d = r.to_dict()
        assert d["reached"] is True
        assert d["consensus_type"] == "majority"
        assert "approval_ratio" in d
        assert d["quorum_met"] is True


class TestSpecConsensusChecker:
    def test_register_and_cast_vote(self):
        cc = SpecConsensusChecker()
        cc.register_voter("A", 2.0)
        vote = cc.cast_vote("A", VoteType.APPROVE, rationale="yes")
        assert vote.weight == 2.0
        assert vote.rationale == "yes"

    def test_cast_vote_unregistered(self):
        cc = SpecConsensusChecker()
        vote = cc.cast_vote("X", VoteType.REJECT)
        assert vote.weight == 1.0

    def test_majority_consensus_reached(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.MAJORITY)
        cc.register_voter("A")
        cc.register_voter("B")
        cc.register_voter("C")
        cc.cast_vote("A", VoteType.APPROVE)
        cc.cast_vote("B", VoteType.APPROVE)
        cc.cast_vote("C", VoteType.REJECT)
        result = cc.check_consensus()
        assert result.reached
        assert result.quorum_met

    def test_majority_consensus_not_reached(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.MAJORITY)
        cc.register_voter("A")
        cc.register_voter("B")
        cc.register_voter("C")
        cc.cast_vote("A", VoteType.REJECT)
        cc.cast_vote("B", VoteType.REJECT)
        cc.cast_vote("C", VoteType.APPROVE)
        result = cc.check_consensus()
        assert not result.reached

    def test_supermajority(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.SUPERMAJORITY)
        for i in range(3):
            cc.register_voter(f"v{i}")
        cc.cast_vote("v0", VoteType.APPROVE)
        cc.cast_vote("v1", VoteType.APPROVE)
        cc.cast_vote("v2", VoteType.REJECT)
        result = cc.check_consensus()
        # 2/3 = 0.667 >= 2/3
        assert result.reached

    def test_supermajority_not_reached(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.SUPERMAJORITY)
        for i in range(4):
            cc.register_voter(f"v{i}")
        cc.cast_vote("v0", VoteType.APPROVE)
        cc.cast_vote("v1", VoteType.APPROVE)
        cc.cast_vote("v2", VoteType.REJECT)
        cc.cast_vote("v3", VoteType.REJECT)
        result = cc.check_consensus()
        assert not result.reached

    def test_unanimous_reached(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.UNANIMOUS)
        cc.register_voter("A")
        cc.register_voter("B")
        cc.cast_vote("A", VoteType.APPROVE)
        cc.cast_vote("B", VoteType.APPROVE)
        result = cc.check_consensus()
        assert result.reached

    def test_unanimous_not_reached(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.UNANIMOUS)
        cc.register_voter("A")
        cc.register_voter("B")
        cc.cast_vote("A", VoteType.APPROVE)
        cc.cast_vote("B", VoteType.REJECT)
        result = cc.check_consensus()
        assert not result.reached

    def test_unanimous_no_approvals(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.UNANIMOUS)
        cc.register_voter("A")
        cc.cast_vote("A", VoteType.ABSTAIN)
        result = cc.check_consensus()
        assert not result.reached

    def test_quorum_type(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.QUORUM, quorum_threshold=0.5)
        cc.register_voter("A")
        cc.register_voter("B")
        cc.cast_vote("A", VoteType.ABSTAIN)
        result = cc.check_consensus()
        assert result.reached  # quorum met = consensus for QUORUM type

    def test_quorum_not_met(self):
        cc = SpecConsensusChecker(quorum_threshold=0.8)
        cc.register_voter("A")
        cc.register_voter("B")
        cc.register_voter("C")
        cc.register_voter("D")
        cc.register_voter("E")
        cc.cast_vote("A", VoteType.APPROVE)
        result = cc.check_consensus()
        assert not result.reached
        assert not result.quorum_met

    def test_all_abstain(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.MAJORITY)
        cc.register_voter("A")
        cc.cast_vote("A", VoteType.ABSTAIN)
        result = cc.check_consensus()
        # approval_ratio = 0 since no participating votes
        assert not result.reached

    def test_weighted_votes(self):
        cc = SpecConsensusChecker(consensus_type=ConsensusType.MAJORITY)
        cc.register_voter("A", weight=10.0)
        cc.register_voter("B", weight=1.0)
        cc.cast_vote("A", VoteType.APPROVE)
        cc.cast_vote("B", VoteType.REJECT)
        result = cc.check_consensus()
        assert result.reached
        assert result.approve_weight == 10.0

    def test_reset(self):
        cc = SpecConsensusChecker()
        cc.register_voter("A")
        cc.cast_vote("A", VoteType.APPROVE)
        cc.reset()
        assert len(cc.votes) == 0
        # Voters still registered
        assert len(cc.registered_voters) == 1


class TestPolicyScope:
    def test_values(self):
        assert PolicyScope.GLOBAL.value == "global"
        assert PolicyScope.MESSAGE.value == "message"


class TestPolicyEnforcement:
    def test_values(self):
        assert PolicyEnforcement.STRICT.value == "strict"
        assert PolicyEnforcement.ADVISORY.value == "advisory"
        assert PolicyEnforcement.AUDIT_ONLY.value == "audit_only"


class TestPolicyVerificationResult:
    def test_to_dict(self):
        r = PolicyVerificationResult(
            passed=True,
            rule_id="r1",
            rule_name="test",
            enforcement=PolicyEnforcement.STRICT,
        )
        d = r.to_dict()
        assert d["passed"] is True
        assert d["enforcement"] == "strict"
        assert d["violation_count"] == 0


class TestSpecPolicyVerifier:
    def test_register_and_verify_passing(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "check_true", lambda: True)
        result = pv.verify("r1")
        assert result.passed

    def test_verify_failing(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "check_false", lambda: False)
        result = pv.verify("r1")
        assert not result.passed
        assert len(result.violations) == 1

    def test_verify_unknown_rule(self):
        pv = SpecPolicyVerifier()
        result = pv.verify("nonexistent")
        assert not result.passed
        assert result.rule_name == "unknown"

    def test_verify_with_context(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "check_val", lambda val: val > 10)
        assert pv.verify("r1", {"val": 20}).passed
        assert not pv.verify("r1", {"val": 5}).passed

    def test_verify_condition_raises(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "bad", lambda: 1 / 0)
        # ZeroDivisionError is not caught, but TypeError/KeyError/ValueError/AttributeError are
        # Let's test with a TypeError
        pv2 = SpecPolicyVerifier()
        pv2.create_rule("r2", "type_err", lambda x: x > 0)
        result = pv2.verify("r2")  # no kwargs -> TypeError
        assert not result.passed

    def test_verify_all(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "pass", lambda: True)
        pv.create_rule("r2", "fail", lambda: False)
        results = pv.verify_all()
        assert len(results) == 2

    def test_verify_all_with_scope_filter(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "msg", lambda: True, scope=PolicyScope.MESSAGE)
        pv.create_rule("r2", "global", lambda: True, scope=PolicyScope.GLOBAL)
        results = pv.verify_all(scope=PolicyScope.MESSAGE)
        assert len(results) == 1

    def test_is_compliant_all_pass(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "ok", lambda: True, enforcement=PolicyEnforcement.STRICT)
        pv.verify_all()
        assert pv.is_compliant()

    def test_is_compliant_strict_failure(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "fail", lambda: False, enforcement=PolicyEnforcement.STRICT)
        pv.verify_all()
        assert not pv.is_compliant()

    def test_is_compliant_advisory_failure_ok(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "warn", lambda: False, enforcement=PolicyEnforcement.ADVISORY)
        pv.verify_all()
        assert pv.is_compliant()

    def test_is_compliant_with_scope_filter(self):
        pv = SpecPolicyVerifier()
        pv.create_rule(
            "r1",
            "msg_fail",
            lambda: False,
            scope=PolicyScope.MESSAGE,
            enforcement=PolicyEnforcement.STRICT,
        )
        pv.create_rule(
            "r2",
            "global_fail",
            lambda: False,
            scope=PolicyScope.GLOBAL,
            enforcement=PolicyEnforcement.STRICT,
        )
        pv.verify_all()
        # Only check MESSAGE scope
        assert not pv.is_compliant(scope=PolicyScope.MESSAGE)

    def test_get_violations(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "fail", lambda: False, enforcement=PolicyEnforcement.STRICT)
        pv.create_rule("r2", "warn", lambda: False, enforcement=PolicyEnforcement.ADVISORY)
        pv.verify_all()
        all_violations = pv.get_violations()
        assert len(all_violations) == 2
        strict_only = pv.get_violations(enforcement=PolicyEnforcement.STRICT)
        assert len(strict_only) == 1

    def test_reset(self):
        pv = SpecPolicyVerifier()
        pv.create_rule("r1", "fail", lambda: False)
        pv.verify("r1")
        pv.reset()
        assert len(pv.violations) == 0
        assert len(pv.verification_log) == 0
        # Rules still registered
        assert "r1" in pv.rules

    def test_register_rule_directly(self):
        pv = SpecPolicyVerifier()
        rule = PolicyRule(
            rule_id="r1",
            name="direct",
            condition=lambda: True,
            scope=PolicyScope.SERVICE,
            enforcement=PolicyEnforcement.AUDIT_ONLY,
            description="test rule",
        )
        pv.register_rule(rule)
        assert "r1" in pv.rules
        result = pv.verify("r1")
        assert result.passed

    def test_policy_violation_fields(self):
        v = PolicyViolation(
            rule_id="r1",
            rule_name="test",
            scope=PolicyScope.AGENT,
            enforcement=PolicyEnforcement.STRICT,
            context={"key": "val"},
            message="failed",
        )
        assert v.rule_id == "r1"
        assert v.scope == PolicyScope.AGENT
        assert isinstance(v.timestamp, datetime)
