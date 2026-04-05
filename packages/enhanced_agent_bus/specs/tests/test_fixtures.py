"""
ACGS-2 Fixture Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for all executable specification fixtures.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from ..fixtures.architecture import (
    ArchitecturalLayer,
    ComponentState,
    SpecArchitectureContext,
    SpecLayerContext,
)

# Import all fixture modules using relative imports
from ..fixtures.constitutional import CONSTITUTIONAL_HASH, ConstitutionalHashValidator
from ..fixtures.governance import (
    ConsensusType,
    PolicyEnforcement,
    SpecConsensusChecker,
    SpecPolicyVerifier,
    VoteType,
)
from ..fixtures.observability import (
    Layer,
    SpecMetricsRegistry,
    SpecTimeoutBudgetManager,
)
from ..fixtures.resilience import (
    CircuitState,
    FailureType,
    SpecChaosController,
    SpecCircuitBreaker,
    SpecSagaManager,
)
from ..fixtures.temporal import (
    CausalValidator,
    SpecTimeline,
    TemporalViolation,
    TemporalViolationType,
)
from ..fixtures.verification import (
    MACIAgent,
    MACIFramework,
    MACIRole,
    RoleViolationError,
    SelfValidationError,
    SpecZ3SolverContext,
    Z3Result,
)

# =============================================================================
# Constitutional Hash Fixture Tests
# =============================================================================


class TestConstitutionalHashValidator:
    """Tests for ConstitutionalHashValidator fixture."""

    def test_valid_hash(self):
        """Test validation of correct constitutional hash."""
        validator = ConstitutionalHashValidator()
        result = validator.validate(CONSTITUTIONAL_HASH)
        assert result.is_valid
        assert result.actual == CONSTITUTIONAL_HASH
        assert result.expected == CONSTITUTIONAL_HASH

    def test_invalid_hash(self):
        """Test validation of incorrect hash."""
        validator = ConstitutionalHashValidator()
        result = validator.validate("wrong_hash")
        assert not result.is_valid
        assert "mismatch" in result.message.lower()

    def test_none_hash(self):
        """Test validation of None hash."""
        validator = ConstitutionalHashValidator()
        result = validator.validate(None)
        assert not result.is_valid
        assert result.actual is None

    def test_layer_tracking(self):
        """Test validation with layer tracking."""
        validator = ConstitutionalHashValidator()
        result = validator.validate(CONSTITUTIONAL_HASH, layer="L1")
        assert result.layer == "L1"
        assert result.is_valid

    def test_propagation_validation(self):
        """Test validation across multiple layers."""
        validator = ConstitutionalHashValidator()
        layer_hashes = {
            "L1": CONSTITUTIONAL_HASH,
            "L2": CONSTITUTIONAL_HASH,
            "L3": "wrong_hash",
        }
        results = validator.validate_propagation(layer_hashes)
        assert len(results) == 3
        assert results[0].is_valid
        assert results[1].is_valid
        assert not results[2].is_valid

    def test_all_valid_check(self):
        """Test all_valid method."""
        validator = ConstitutionalHashValidator()
        validator.validate(CONSTITUTIONAL_HASH)
        assert validator.all_valid()

        validator.validate("wrong")
        assert not validator.all_valid()

    def test_get_failures(self):
        """Test getting failed validations."""
        validator = ConstitutionalHashValidator()
        validator.validate(CONSTITUTIONAL_HASH)
        validator.validate("wrong1")
        validator.validate("wrong2")

        failures = validator.get_failures()
        assert len(failures) == 2

    def test_reset(self):
        """Test resetting validation history."""
        validator = ConstitutionalHashValidator()
        validator.validate("wrong")
        validator.reset()
        assert validator.all_valid()
        assert len(validator.get_failures()) == 0


# =============================================================================
# Temporal Fixture Tests
# =============================================================================


class TestSpecTimeline:
    """Tests for SpecTimeline fixture."""

    def test_record_event(self):
        """Test recording events."""
        timeline = SpecTimeline()
        event = timeline.record("A")
        assert event.id == "A"
        assert event in timeline.events.values()

    def test_happened_before(self):
        """Test temporal ordering."""
        timeline = SpecTimeline()
        timeline.record("A")
        import time

        time.sleep(0.001)  # Ensure different timestamps
        timeline.record("B")
        assert timeline.happened_before("A", "B")
        assert not timeline.happened_before("B", "A")

    def test_causal_relationships(self):
        """Test cause-effect tracking."""
        timeline = SpecTimeline()
        timeline.record("cause")
        timeline.record("effect", causes={"cause"})

        assert "effect" in timeline.events["cause"].effects
        assert "cause" in timeline.events["effect"].causes

    def test_get_sorted_events(self):
        """Test getting events sorted by time."""
        timeline = SpecTimeline()
        timeline.record("A")
        import time

        time.sleep(0.001)
        timeline.record("B")

        sorted_events = timeline.get_sorted_events()
        assert sorted_events[0].id == "A"
        assert sorted_events[1].id == "B"

    def test_clear(self):
        """Test clearing timeline."""
        timeline = SpecTimeline()
        timeline.record("A")
        timeline.clear()
        assert len(timeline.events) == 0
        assert len(timeline.order) == 0


class TestCausalValidator:
    """Tests for CausalValidator fixture."""

    def test_validate_causality(self):
        """Test causality validation."""
        timeline = SpecTimeline()
        timeline.record("cause")
        import time

        time.sleep(0.001)
        timeline.record("effect")

        validator = CausalValidator(timeline)
        assert validator.validate_causality("cause", "effect")

    def test_invalid_causality(self):
        """Test detection of causality violations."""
        timeline = SpecTimeline()
        effect_time = datetime.now(UTC)
        cause_time = effect_time + timedelta(seconds=1)

        timeline.record("effect", timestamp=effect_time)
        timeline.record("cause", timestamp=cause_time)

        validator = CausalValidator(timeline)
        assert not validator.validate_causality("cause", "effect")
        assert len(validator.violations) == 1
        assert validator.violations[0].violation_type == TemporalViolationType.CAUSALITY

    def test_validate_chain(self):
        """Test causal chain validation."""
        timeline = SpecTimeline()
        for _i, name in enumerate(["A", "B", "C"]):
            import time

            time.sleep(0.001)
            timeline.record(name)

        validator = CausalValidator(timeline)
        is_valid, violations = validator.validate_chain(["A", "B", "C"])
        assert is_valid
        assert len(violations) == 0

    def test_check_ordering(self):
        """Test event ordering validation."""
        timeline = SpecTimeline()
        for name in ["first", "second", "third"]:
            import time

            time.sleep(0.001)
            timeline.record(name)

        validator = CausalValidator(timeline)
        assert validator.check_ordering(["first", "second", "third"])

    def test_reset(self):
        """Test validator reset."""
        timeline = SpecTimeline()
        validator = CausalValidator(timeline)
        validator.violations.append(
            TemporalViolation(
                violation_type=TemporalViolationType.CAUSALITY,
                event_a="a",
                event_b="b",
                message="test",
            )
        )
        validator.reset()
        assert validator.is_valid()


# =============================================================================
# Governance Fixture Tests
# =============================================================================


class TestSpecConsensusChecker:
    """Tests for SpecConsensusChecker fixture."""

    def test_majority_consensus(self):
        """Test majority consensus."""
        checker = SpecConsensusChecker(consensus_type=ConsensusType.MAJORITY)
        checker.register_voter("A")
        checker.register_voter("B")
        checker.register_voter("C")

        checker.cast_vote("A", VoteType.APPROVE)
        checker.cast_vote("B", VoteType.APPROVE)
        checker.cast_vote("C", VoteType.REJECT)

        result = checker.check_consensus()
        assert result.reached
        assert result.approval_ratio == 2 / 3

    def test_supermajority_consensus(self):
        """Test supermajority (2/3) consensus."""
        checker = SpecConsensusChecker(consensus_type=ConsensusType.SUPERMAJORITY)
        checker.register_voter("A")
        checker.register_voter("B")
        checker.register_voter("C")

        checker.cast_vote("A", VoteType.APPROVE)
        checker.cast_vote("B", VoteType.APPROVE)
        checker.cast_vote("C", VoteType.REJECT)

        result = checker.check_consensus()
        assert result.reached  # 2/3 exactly meets threshold

    def test_unanimous_consensus(self):
        """Test unanimous consensus."""
        checker = SpecConsensusChecker(consensus_type=ConsensusType.UNANIMOUS)
        checker.register_voter("A")
        checker.register_voter("B")

        checker.cast_vote("A", VoteType.APPROVE)
        checker.cast_vote("B", VoteType.APPROVE)

        result = checker.check_consensus()
        assert result.reached

    def test_quorum_not_met(self):
        """Test quorum check."""
        checker = SpecConsensusChecker(quorum_threshold=0.5)
        checker.register_voter("A")
        checker.register_voter("B")
        checker.register_voter("C")
        checker.register_voter("D")

        checker.cast_vote("A", VoteType.APPROVE)  # Only 25% participation

        result = checker.check_consensus()
        assert not result.quorum_met
        assert not result.reached

    def test_weighted_voting(self):
        """Test weighted voting."""
        checker = SpecConsensusChecker()
        checker.register_voter("major", weight=3.0)
        checker.register_voter("minor", weight=1.0)

        checker.cast_vote("major", VoteType.REJECT)
        checker.cast_vote("minor", VoteType.APPROVE)

        result = checker.check_consensus()
        assert not result.reached
        assert result.reject_weight == 3.0
        assert result.approve_weight == 1.0


class TestSpecPolicyVerifier:
    """Tests for SpecPolicyVerifier fixture."""

    def test_rule_creation(self):
        """Test creating policy rules."""
        verifier = SpecPolicyVerifier()
        rule = verifier.create_rule(
            "r1",
            "Test Rule",
            lambda x: x > 0,
        )
        assert rule.rule_id == "r1"
        assert "r1" in verifier.rules

    def test_rule_verification_pass(self):
        """Test passing rule verification."""
        verifier = SpecPolicyVerifier()
        verifier.create_rule("pos", "Positive", lambda x: x > 0)
        result = verifier.verify("pos", {"x": 5})
        assert result.passed

    def test_rule_verification_fail(self):
        """Test failing rule verification."""
        verifier = SpecPolicyVerifier()
        verifier.create_rule("pos", "Positive", lambda x: x > 0)
        result = verifier.verify("pos", {"x": -1})
        assert not result.passed
        assert len(result.violations) == 1

    def test_enforcement_levels(self):
        """Test different enforcement levels."""
        verifier = SpecPolicyVerifier()
        verifier.create_rule(
            "strict",
            "Strict Rule",
            lambda: False,
            enforcement=PolicyEnforcement.STRICT,
        )
        verifier.create_rule(
            "advisory",
            "Advisory Rule",
            lambda: False,
            enforcement=PolicyEnforcement.ADVISORY,
        )

        verifier.verify("strict")
        verifier.verify("advisory")

        strict_violations = verifier.get_violations(PolicyEnforcement.STRICT)
        assert len(strict_violations) == 1

    def test_verify_all(self):
        """Test verifying all rules."""
        verifier = SpecPolicyVerifier()
        verifier.create_rule("r1", "Rule 1", lambda: True)
        verifier.create_rule("r2", "Rule 2", lambda: True)

        results = verifier.verify_all()
        assert len(results) == 2
        assert all(r.passed for r in results)


# =============================================================================
# Architecture Fixture Tests
# =============================================================================


class TestSpecArchitectureContext:
    """Tests for SpecArchitectureContext fixture."""

    def test_enter_layer(self):
        """Test entering a layer."""
        ctx = SpecArchitectureContext()
        layer_ctx = ctx.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)

        assert layer_ctx.is_active
        assert ctx.current_layer == ArchitecturalLayer.LAYER1_VALIDATION

    def test_layer_transition(self):
        """Test transitioning between layers."""
        ctx = SpecArchitectureContext()
        ctx.enter_layer(ArchitecturalLayer.LAYER1_VALIDATION)
        transition = ctx.transition_to(ArchitecturalLayer.LAYER2_DELIBERATION)

        assert transition.from_layer == ArchitecturalLayer.LAYER1_VALIDATION
        assert transition.to_layer == ArchitecturalLayer.LAYER2_DELIBERATION
        assert ctx.current_layer == ArchitecturalLayer.LAYER2_DELIBERATION

    def test_component_registration(self):
        """Test registering components."""
        ctx = SpecArchitectureContext()
        comp = ctx.register_component(
            ArchitecturalLayer.LAYER1_VALIDATION,
            "validator",
            version="1.0.0",
        )

        assert comp.name == "validator"
        assert comp.layer == ArchitecturalLayer.LAYER1_VALIDATION

    def test_health_report(self):
        """Test health report generation."""
        ctx = SpecArchitectureContext()
        ctx.register_component(ArchitecturalLayer.LAYER1_VALIDATION, "comp1")
        ctx.layers[ArchitecturalLayer.LAYER1_VALIDATION].update_component_state(
            "comp1", ComponentState.READY
        )

        report = ctx.get_health_report()
        assert report["healthy"]
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_constitutional_compliance(self):
        """Test constitutional compliance validation."""
        ctx = SpecArchitectureContext()
        assert ctx.validate_constitutional_compliance()


class TestSpecLayerContext:
    """Tests for SpecLayerContext fixture."""

    def test_layer_budget(self):
        """Test default timeout budget."""
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        assert ctx.config.timeout_budget_ms == 5.0

    def test_component_state_updates(self):
        """Test updating component state."""
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        ctx.register_component("comp")
        ctx.update_component_state("comp", ComponentState.READY)

        comp = ctx.get_component("comp")
        assert comp.state == ComponentState.READY

    def test_health_check(self):
        """Test layer health check."""
        ctx = SpecLayerContext(ArchitecturalLayer.LAYER1_VALIDATION)
        ctx.register_component("comp")
        ctx.update_component_state("comp", ComponentState.READY)

        assert ctx.is_healthy()

        ctx.update_component_state("comp", ComponentState.FAILED)
        assert not ctx.is_healthy()


# =============================================================================
# MACI Framework Tests
# =============================================================================


class TestMACIFramework:
    """Tests for MACI role separation enforcement."""

    def test_executive_propose(self):
        """Test Executive role can propose."""
        maci = MACIFramework()
        output = maci.executive_agent.propose("decision")
        assert output is not None
        assert output in maci.executive_agent.outputs

    def test_executive_cannot_validate(self):
        """Test Executive cannot validate."""
        maci = MACIFramework()
        with pytest.raises(RoleViolationError) as exc_info:
            maci.executive_agent.validate("output:0")
        assert exc_info.value.role == "executive"

    def test_judicial_validate(self):
        """Test Judicial role can validate."""
        maci = MACIFramework()
        assert maci.judicial_agent.validate("executive:0")

    def test_self_validation_blocked(self):
        """Test self-validation is blocked (Gödel bypass prevention)."""
        maci = MACIFramework()
        judicial = maci.judicial_agent

        # Create a fake output from the judicial agent
        judicial.outputs.append("judicial:self")

        with pytest.raises(SelfValidationError) as exc_info:
            judicial.validate("judicial:self")
        assert exc_info.value.agent == "judicial"

    def test_legislative_extract_rules(self):
        """Test Legislative role can extract rules."""
        maci = MACIFramework()
        rules = maci.legislative_agent.extract_rules("content")
        assert len(rules) == 3

    def test_legislative_cannot_propose(self):
        """Test Legislative cannot propose."""
        maci = MACIFramework()
        with pytest.raises(RoleViolationError):
            maci.legislative_agent.propose("content")

    def test_judicial_cannot_validate_judicial(self):
        """Test Judicial cannot validate other judicial outputs."""
        maci = MACIFramework()
        other_judicial = MACIAgent("other_judicial", MACIRole.JUDICIAL)

        with pytest.raises(RoleViolationError):
            maci.judicial_agent.validate("output:0", target_agent=other_judicial)


class TestSpecZ3SolverContext:
    """Tests for Z3 solver specification context."""

    def test_satisfiable_constraint(self):
        """Test satisfiable constraint."""
        solver = SpecZ3SolverContext()
        result = solver.verify("x > 0 AND x < 10")
        assert result.sat
        assert result.result == Z3Result.SAT

    def test_unsatisfiable_constraint(self):
        """Test unsatisfiable constraint."""
        solver = SpecZ3SolverContext()
        result = solver.verify("x > 10 AND x < 5")
        assert not result.sat
        assert result.result == Z3Result.UNSAT

    def test_contradiction(self):
        """Test logical contradiction."""
        solver = SpecZ3SolverContext()
        result = solver.verify("x = x + 1")
        assert not result.sat

    def test_true_constraint(self):
        """Test explicit true constraint."""
        solver = SpecZ3SolverContext()
        result = solver.verify("true")
        assert result.sat

    def test_false_constraint(self):
        """Test explicit false constraint."""
        solver = SpecZ3SolverContext()
        result = solver.verify("false")
        assert not result.sat


# =============================================================================
# Resilience Fixture Tests
# =============================================================================


class TestSpecCircuitBreaker:
    """Tests for SpecCircuitBreaker fixture."""

    def test_initial_state(self):
        """Test initial closed state."""
        cb = SpecCircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_opens_on_failures(self):
        """Test circuit opens after failure threshold."""
        cb = SpecCircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_transition(self):
        """Test transition to half-open state."""
        cb = SpecCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.trigger_timer_expiry()
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success(self):
        """Test half-open to closed on success."""
        cb = SpecCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb.trigger_timer_expiry()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure(self):
        """Test half-open to open on failure."""
        cb = SpecCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb.trigger_timer_expiry()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestSpecChaosController:
    """Tests for SpecChaosController fixture."""

    async def test_inject_failure(self):
        """Test failure injection."""
        controller = SpecChaosController()
        injection = await controller.fail("component", FailureType.ERROR)

        assert controller.is_failed("component")
        assert injection.component == "component"

    async def test_recover_component(self):
        """Test component recovery."""
        controller = SpecChaosController()
        await controller.fail("component")

        injection = await controller.recover("component")

        assert not controller.is_failed("component")
        assert injection.recovered

    async def test_reset_all(self):
        """Test resetting all failures."""
        controller = SpecChaosController()
        await controller.fail("comp1")
        await controller.fail("comp2")

        await controller.reset()

        assert not controller.is_failed("comp1")
        assert not controller.is_failed("comp2")


class TestSpecSagaManager:
    """Tests for SpecSagaManager fixture."""

    async def test_saga_execution(self):
        """Test saga step execution."""
        manager = SpecSagaManager()
        async with manager.transaction() as saga:
            await saga.execute_step("A")
            await saga.execute_step("B")

        assert len(manager.steps) == 2
        assert manager.steps[0].executed
        assert manager.steps[1].executed

    async def test_lifo_compensation(self):
        """Test LIFO compensation order."""
        manager = SpecSagaManager()
        async with manager.transaction() as saga:
            await saga.execute_step("A")
            await saga.execute_step("B")
            await saga.execute_step("C")

            order = await saga.compensate()

        assert order == ["C", "B", "A"]

    async def test_compensation_callback(self):
        """Test compensation with callbacks."""
        compensated = []
        manager = SpecSagaManager()

        async with manager.transaction() as saga:
            await saga.execute_step("step1")
            saga.on_compensate("step1", lambda: compensated.append("step1"))

            await saga.compensate()

        assert "step1" in compensated


# =============================================================================
# Observability Fixture Tests
# =============================================================================


class TestSpecTimeoutBudgetManager:
    """Tests for SpecTimeoutBudgetManager fixture."""

    def test_record_measurement(self):
        """Test recording latency measurement."""
        manager = SpecTimeoutBudgetManager()
        measurement = manager.record_measurement(
            Layer.LAYER1_VALIDATION,
            "test_op",
            3.5,
        )

        assert measurement.latency_ms == 3.5
        assert measurement.within_budget  # 3.5 < 5.0

    def test_budget_violation(self):
        """Test detecting budget violation."""
        manager = SpecTimeoutBudgetManager()
        measurement = manager.record_measurement(
            Layer.LAYER1_VALIDATION,
            "slow_op",
            10.0,  # Exceeds 5ms budget
        )

        assert not measurement.within_budget

    def test_get_violations(self):
        """Test getting budget violations."""
        manager = SpecTimeoutBudgetManager()
        manager.record_measurement(Layer.LAYER1_VALIDATION, "fast", 2.0)
        manager.record_measurement(Layer.LAYER1_VALIDATION, "slow", 10.0)

        violations = manager.get_budget_violations()
        assert len(violations) == 1
        assert violations[0].operation == "slow"

    def test_compliance_report(self):
        """Test budget compliance report."""
        manager = SpecTimeoutBudgetManager()
        manager.record_measurement(Layer.LAYER1_VALIDATION, "op1", 3.0)
        manager.record_measurement(Layer.LAYER1_VALIDATION, "op2", 4.0)

        report = manager.verify_budget_compliance()
        assert report["compliant"]
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSpecMetricsRegistry:
    """Tests for SpecMetricsRegistry fixture."""

    def test_counter_increment(self):
        """Test counter increment."""
        registry = SpecMetricsRegistry()
        registry.increment_counter("requests")

        assert registry.get_counter_total("requests") == 1

    def test_latency_recording(self):
        """Test latency recording."""
        registry = SpecMetricsRegistry()
        registry.record_latency("response_time", 5.5)

        events = registry.get_events_by_name("response_time")
        assert len(events) == 1
        assert events[0]["value"] == 5.5

    def test_event_attributes(self):
        """Test metric event attributes."""
        registry = SpecMetricsRegistry()
        registry.increment_counter("requests", attributes={"path": "/api"})

        events = registry.get_events_by_name("requests")
        assert events[0]["attributes"]["path"] == "/api"

    def test_clear_events(self):
        """Test clearing events."""
        registry = SpecMetricsRegistry()
        registry.increment_counter("counter")
        registry.clear_events()

        assert len(registry.metric_events) == 0
