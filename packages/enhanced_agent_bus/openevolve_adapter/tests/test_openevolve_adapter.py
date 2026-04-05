"""
Tests for enhanced_agent_bus.openevolve_adapter
Constitutional Hash: 608508a9bd224290

Covers:
- candidate.py  (EvolutionCandidate contract & validation)
- fitness.py    (ConstitutionalFitness scoring)
- evolver.py    (GovernedEvolver MACI enforcement)
- rollout.py    (RolloutController gate logic)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from enhanced_agent_bus.openevolve_adapter import (
    CascadeEvaluator,
    CascadeResult,
    CascadeStage,
    ConstitutionalFitness,
    ConstitutionalVerifier,
    EvolutionCandidate,
    EvolutionMessageHandler,
    EvolveResult,
    FitnessResult,
    GovernedEvolver,
    MutationRecord,
    RiskTier,
    RolloutController,
    RolloutDecision,
    RolloutStage,
    VerificationPayload,
)

# ---------------------------------------------------------------------------
# Constants & shared helpers
# ---------------------------------------------------------------------------

HASH = "608508a9bd224290"  # pragma: allowlist secret


def _make_payload(
    *,
    syntax_valid: bool = True,
    policy_compliant: bool = True,
    safety_score: float = 0.9,
    validator_id: str = "validator-001",
    constitutional_hash: str = HASH,
) -> VerificationPayload:
    return VerificationPayload(
        validator_id=validator_id,
        verified_at=datetime.now(UTC).isoformat(),
        constitutional_hash=constitutional_hash,
        syntax_valid=syntax_valid,
        policy_compliant=policy_compliant,
        safety_score=safety_score,
    )


def _make_candidate(
    candidate_id: str = "cand-001",
    *,
    risk_tier: RiskTier = RiskTier.LOW,
    proposed_rollout_stage: RolloutStage = RolloutStage.CANARY,
    constitutional_hash: str = HASH,
    payload: VerificationPayload | None = None,
    fitness_inputs: dict[str, Any] | None = None,
    mutation_trace: list[MutationRecord] | None = None,
) -> EvolutionCandidate:
    return EvolutionCandidate(
        candidate_id=candidate_id,
        mutation_trace=mutation_trace or [],
        fitness_inputs=fitness_inputs or {"metric": 0.8},
        verification_payload=payload or _make_payload(constitutional_hash=constitutional_hash),
        constitutional_hash=constitutional_hash,
        risk_tier=risk_tier,
        proposed_rollout_stage=proposed_rollout_stage,
    )


# ---------------------------------------------------------------------------
# VerificationPayload
# ---------------------------------------------------------------------------


class TestVerificationPayload:
    def test_valid_construction(self):
        vp = _make_payload()
        assert vp.syntax_valid is True
        assert vp.safety_score == 0.9

    def test_to_dict(self):
        vp = _make_payload()
        d = vp.to_dict()
        assert d["validator_id"] == "validator-001"
        assert d["constitutional_hash"] == HASH
        assert "safety_score" in d

    def test_safety_score_out_of_range_raises(self):
        with pytest.raises(ValueError, match="safety_score"):
            _make_payload(safety_score=1.5)

    def test_safety_score_negative_raises(self):
        with pytest.raises(ValueError, match="safety_score"):
            _make_payload(safety_score=-0.1)

    def test_safety_score_boundary_zero(self):
        vp = _make_payload(safety_score=0.0)
        assert vp.safety_score == 0.0

    def test_safety_score_boundary_one(self):
        vp = _make_payload(safety_score=1.0)
        assert vp.safety_score == 1.0


# ---------------------------------------------------------------------------
# MutationRecord
# ---------------------------------------------------------------------------


class TestMutationRecord:
    def test_to_dict(self):
        m = MutationRecord(operator="crossover", parent_id="p-1", description="mix two parents")
        d = m.to_dict()
        assert d["operator"] == "crossover"
        assert "timestamp" in d

    def test_immutable(self):
        m = MutationRecord(operator="point_mutation", parent_id="p-2", description="swap token")
        with pytest.raises(AttributeError):
            m.operator = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EvolutionCandidate
# ---------------------------------------------------------------------------


class TestEvolutionCandidate:
    def test_valid_construction(self):
        c = _make_candidate()
        assert c.candidate_id == "cand-001"
        assert c.constitutional_hash == HASH

    def test_wrong_hash_raises(self):
        with pytest.raises(ValueError, match="Constitutional hash mismatch"):
            _make_candidate(constitutional_hash="deadbeef00000000")

    def test_payload_hash_mismatch_raises(self):
        payload = _make_payload(constitutional_hash="aaaa1111bbbb2222")
        with pytest.raises(ValueError, match="Mismatched constitutional hashes"):
            EvolutionCandidate(
                candidate_id="x",
                mutation_trace=[],
                fitness_inputs={},
                verification_payload=payload,
                constitutional_hash=HASH,
                risk_tier=RiskTier.LOW,
                proposed_rollout_stage=RolloutStage.CANARY,
            )

    def test_critical_full_stage_raises(self):
        """CRITICAL tier must not allow FULL rollout."""
        with pytest.raises(ValueError, match="does not allow"):
            _make_candidate(risk_tier=RiskTier.CRITICAL, proposed_rollout_stage=RolloutStage.FULL)

    def test_high_partial_stage_raises(self):
        with pytest.raises(ValueError, match="does not allow"):
            _make_candidate(risk_tier=RiskTier.HIGH, proposed_rollout_stage=RolloutStage.PARTIAL)

    def test_high_canary_allowed(self):
        c = _make_candidate(risk_tier=RiskTier.HIGH, proposed_rollout_stage=RolloutStage.CANARY)
        assert c.risk_tier == RiskTier.HIGH

    def test_is_verified_true(self):
        c = _make_candidate(payload=_make_payload(safety_score=0.7))
        assert c.is_verified is True

    def test_is_verified_false_low_safety(self):
        c = _make_candidate(payload=_make_payload(safety_score=0.2))
        assert c.is_verified is False

    def test_is_verified_false_syntax(self):
        c = _make_candidate(payload=_make_payload(syntax_valid=False))
        assert c.is_verified is False

    def test_generation_zero(self):
        c = _make_candidate(mutation_trace=[])
        assert c.generation == 0

    def test_generation_nonzero(self):
        trace = [
            MutationRecord("crossover", "p-0", "first"),
            MutationRecord("point_mutation", "p-1", "second"),
        ]
        c = _make_candidate(mutation_trace=trace)
        assert c.generation == 2

    def test_to_dict_keys(self):
        c = _make_candidate()
        d = c.to_dict()
        for key in (
            "candidate_id",
            "constitutional_hash",
            "risk_tier",
            "is_verified",
            "generation",
            "mutation_trace",
            "verification_payload",
            "fitness_inputs",
        ):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# ConstitutionalFitness
# ---------------------------------------------------------------------------


class TestConstitutionalFitness:
    def _perfect_candidate(self) -> EvolutionCandidate:
        return _make_candidate(payload=_make_payload(safety_score=1.0))

    def test_perfect_candidate_high_fitness(self):
        cf = ConstitutionalFitness(threshold=0.5)
        result = cf.evaluate(self._perfect_candidate(), performance_score=1.0)
        assert result.fitness > 0.9
        assert result.passed is True

    def test_zero_performance_still_passes_with_compliance(self):
        cf = ConstitutionalFitness(threshold=0.3)
        result = cf.evaluate(self._perfect_candidate(), performance_score=0.0)
        # 0.4 * compliance(~1.0) * 1.0 ≈ 0.4 → should pass threshold 0.3
        assert result.passed is True

    def test_low_performance_and_compliance_fails(self):
        cf = ConstitutionalFitness(threshold=0.5)
        bad_payload = _make_payload(syntax_valid=False, policy_compliant=False, safety_score=0.0)
        c = _make_candidate(payload=bad_payload)
        result = cf.evaluate(c, performance_score=0.0)
        assert result.passed is False
        assert result.fitness == 0.0

    def test_risk_multiplier_penalises_critical(self):
        cf = ConstitutionalFitness(threshold=0.0)
        low_c = _make_candidate(risk_tier=RiskTier.LOW, proposed_rollout_stage=RolloutStage.CANARY)
        crit_c = _make_candidate(
            risk_tier=RiskTier.CRITICAL, proposed_rollout_stage=RolloutStage.CANARY
        )
        low_r = cf.evaluate(low_c, performance_score=1.0)
        crit_r = cf.evaluate(crit_c, performance_score=1.0)
        assert low_r.fitness > crit_r.fitness

    def test_to_dict(self):
        cf = ConstitutionalFitness()
        r = cf.evaluate(self._perfect_candidate(), performance_score=0.8)
        d = r.to_dict()
        assert "fitness" in d
        assert "passed" in d
        assert "compliance_score" in d

    def test_invalid_weights_raises(self):
        with pytest.raises(ValueError, match="must equal 1.0"):
            ConstitutionalFitness(performance_weight=0.7, compliance_weight=0.7)

    def test_performance_score_out_of_range_raises(self):
        cf = ConstitutionalFitness()
        with pytest.raises(ValueError, match="performance_score"):
            cf.evaluate(self._perfect_candidate(), performance_score=1.5)

    def test_rank_sorts_by_fitness(self):
        cf = ConstitutionalFitness(threshold=0.5)
        c_high = _make_candidate("high", payload=_make_payload(safety_score=1.0))
        c_low = _make_candidate("low", payload=_make_payload(safety_score=0.1))
        ranked = cf.rank([(c_low, 0.1), (c_high, 0.9)])
        assert ranked[0].candidate_id == "high"

    def test_custom_weights(self):
        cf = ConstitutionalFitness(performance_weight=0.8, compliance_weight=0.2)
        c = _make_candidate(payload=_make_payload(safety_score=1.0))
        r = cf.evaluate(c, performance_score=1.0)
        assert r.performance_score == 1.0


# ---------------------------------------------------------------------------
# GovernedEvolver
# ---------------------------------------------------------------------------


class _GoodVerifier:
    """Stub verifier that always returns a clean payload."""

    async def verify(self, candidate: EvolutionCandidate) -> VerificationPayload:
        return _make_payload()


class _BadVerifier:
    """Stub verifier that always returns a failing payload."""

    async def verify(self, candidate: EvolutionCandidate) -> VerificationPayload:
        return _make_payload(syntax_valid=False, policy_compliant=False, safety_score=0.0)


class _RaisingVerifier:
    """Stub verifier that raises on every call."""

    async def verify(self, candidate: EvolutionCandidate) -> VerificationPayload:
        raise RuntimeError("External verifier unavailable")


class TestGovernedEvolver:
    def _evolver(self, verifier=None) -> GovernedEvolver:
        return GovernedEvolver(verifier=verifier or _GoodVerifier())

    @pytest.mark.asyncio
    async def test_approved_candidate(self):
        evolver = self._evolver()
        c = _make_candidate()
        result = await evolver.evolve(c, performance_score=0.9)
        assert result.approved is True
        assert result.fitness_result.fitness > 0.0

    @pytest.mark.asyncio
    async def test_rejected_by_verifier(self):
        evolver = self._evolver(_BadVerifier())
        c = _make_candidate()
        result = await evolver.evolve(c, performance_score=0.9)
        assert result.approved is False
        assert "non_compliant" in result.rejection_reason or "invalid" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_rejected_by_verifier_exception(self):
        evolver = self._evolver(_RaisingVerifier())
        c = _make_candidate()
        result = await evolver.evolve(c, performance_score=0.9)
        assert result.approved is False
        assert "Verification error" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_rejected_low_fitness(self):
        evolver = GovernedEvolver(
            verifier=_GoodVerifier(),
            fitness=ConstitutionalFitness(threshold=0.99),
        )
        # Even perfect compliance, very low performance → may fail threshold
        bad_payload = _make_payload(safety_score=0.01)
        c = _make_candidate(payload=bad_payload)
        result = await evolver.evolve(c, performance_score=0.0)
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_metrics_updated(self):
        evolver = self._evolver()
        c = _make_candidate()
        await evolver.evolve(c, performance_score=0.8)
        m = evolver.get_metrics()
        assert m["candidates_evaluated"] == 1
        assert m["candidates_approved"] == 1
        assert m["candidates_rejected"] == 0
        assert m["approval_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_batch_sorted_approved_first(self):
        evolver = GovernedEvolver(
            verifier=_GoodVerifier(),
            fitness=ConstitutionalFitness(threshold=0.5),
        )
        c_high = _make_candidate("high", payload=_make_payload(safety_score=1.0))
        c_low = _make_candidate("low", payload=_make_payload(safety_score=0.0))
        results = await evolver.evolve_batch([(c_low, 0.0), (c_high, 1.0)])
        assert results[0].candidate.candidate_id == "high"

    def test_non_verifier_raises(self):
        with pytest.raises(TypeError, match="ConstitutionalVerifier"):
            GovernedEvolver(verifier="not a verifier")  # type: ignore[arg-type]

    def test_verifier_protocol_satisfied(self):
        """Protocol check via runtime_checkable."""
        assert isinstance(_GoodVerifier(), ConstitutionalVerifier)

    @pytest.mark.asyncio
    async def test_to_dict(self):
        evolver = self._evolver()
        result = await evolver.evolve(_make_candidate(), performance_score=0.7)
        d = result.to_dict()
        assert "candidate_id" in d
        assert "approved" in d
        assert "fitness" in d


# ---------------------------------------------------------------------------
# RolloutController
# ---------------------------------------------------------------------------


class TestRolloutController:
    def test_low_canary_approved(self):
        ctrl = RolloutController()
        c = _make_candidate(risk_tier=RiskTier.LOW, proposed_rollout_stage=RolloutStage.CANARY)
        d = ctrl.gate(c)
        assert d.allowed is True

    def test_low_full_approved(self):
        ctrl = RolloutController()
        c = _make_candidate(risk_tier=RiskTier.LOW, proposed_rollout_stage=RolloutStage.FULL)
        d = ctrl.gate(c)
        assert d.allowed is True

    def test_high_canary_approved(self):
        ctrl = RolloutController()
        c = _make_candidate(risk_tier=RiskTier.HIGH, proposed_rollout_stage=RolloutStage.CANARY)
        d = ctrl.gate(c)
        assert d.allowed is True
        assert "Human approval required" in d.reason

    def test_high_full_denied(self):
        """HIGH tier must not reach FULL — EvolutionCandidate rejects at construction."""
        with pytest.raises(ValueError):
            _make_candidate(risk_tier=RiskTier.HIGH, proposed_rollout_stage=RolloutStage.FULL)

    def test_critical_partial_approved(self):
        ctrl = RolloutController()
        c = _make_candidate(
            risk_tier=RiskTier.CRITICAL, proposed_rollout_stage=RolloutStage.PARTIAL
        )
        d = ctrl.gate(c)
        assert d.allowed is True
        assert "Human approval required" in d.reason

    def test_unverified_candidate_denied(self):
        ctrl = RolloutController()
        bad_payload = _make_payload(syntax_valid=False, safety_score=0.0)
        c = _make_candidate(payload=bad_payload)
        d = ctrl.gate(c)
        assert d.allowed is False
        assert "is_verified=False" in d.reason

    def test_audit_trail_grows(self):
        ctrl = RolloutController()
        c1 = _make_candidate("c1")
        c2 = _make_candidate("c2")
        ctrl.gate(c1)
        ctrl.gate(c2)
        trail = ctrl.audit_trail()
        assert len(trail) == 2
        assert trail[0]["candidate_id"] == "c1"

    def test_metrics(self):
        ctrl = RolloutController()
        ctrl.gate(_make_candidate("ok"))
        bad_payload = _make_payload(syntax_valid=False, safety_score=0.0)
        ctrl.gate(_make_candidate("bad", payload=bad_payload))
        m = ctrl.metrics()
        assert m["total_decisions"] == 2
        assert m["approved"] == 1
        assert m["denied"] == 1
        assert m["approval_rate"] == 0.5

    def test_batch(self):
        ctrl = RolloutController()
        candidates = [_make_candidate(f"c{i}") for i in range(3)]
        decisions = ctrl.gate_batch(candidates)
        assert len(decisions) == 3
        assert all(d.allowed for d in decisions)

    def test_decision_to_dict(self):
        ctrl = RolloutController()
        c = _make_candidate()
        d = ctrl.gate(c)
        data = d.to_dict()
        for key in (
            "candidate_id",
            "risk_tier",
            "proposed_stage",
            "allowed",
            "reason",
            "constraints",
            "decided_at",
        ):
            assert key in data

    def test_medium_shadow_required_noted(self):
        ctrl = RolloutController()
        c = _make_candidate(risk_tier=RiskTier.MEDIUM, proposed_rollout_stage=RolloutStage.CANARY)
        d = ctrl.gate(c)
        assert d.allowed is True
        assert "Shadow validation" in d.reason

    def test_empty_metrics(self):
        ctrl = RolloutController()
        m = ctrl.metrics()
        assert m["total_decisions"] == 0
        assert m["approval_rate"] == 0.0


# ---------------------------------------------------------------------------
# CascadeEvaluator
# ---------------------------------------------------------------------------


class TestCascadeEvaluator:
    def _evaluator(self, *, quick_threshold=0.3, full_threshold=0.5) -> CascadeEvaluator:
        from enhanced_agent_bus.openevolve_adapter.cascade import CascadeEvaluator

        return CascadeEvaluator(
            _GoodVerifier(),
            quick_threshold=quick_threshold,
            full_threshold=full_threshold,
        )

    @pytest.mark.asyncio
    async def test_all_stages_pass(self):
        ev = self._evaluator()
        c = _make_candidate(payload=_make_payload(safety_score=1.0))
        result = await ev.evaluate(c, performance_score=0.9)
        assert result.passed is True
        assert result.exit_stage.value == "full"
        assert result.fitness_result is not None

    @pytest.mark.asyncio
    async def test_syntax_fail_empty_id(self):
        # Bypass __post_init__ to create a structurally broken candidate
        import dataclasses

        from enhanced_agent_bus.openevolve_adapter.cascade import CascadeEvaluator, CascadeStage

        c = _make_candidate()
        broken = dataclasses.replace(c, candidate_id="")
        ev = CascadeEvaluator(_GoodVerifier())
        result = await ev.evaluate(broken, performance_score=0.9)
        assert result.passed is False
        assert result.exit_stage == CascadeStage.SYNTAX
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_syntax_fail_syntax_invalid(self):
        from enhanced_agent_bus.openevolve_adapter.cascade import CascadeEvaluator, CascadeStage

        ev = CascadeEvaluator(_GoodVerifier())
        bad = _make_candidate(payload=_make_payload(syntax_valid=False))
        result = await ev.evaluate(bad, performance_score=0.9)
        assert result.exit_stage == CascadeStage.SYNTAX
        assert not result.passed

    @pytest.mark.asyncio
    async def test_quick_fail_low_score(self):
        from enhanced_agent_bus.openevolve_adapter.cascade import CascadeEvaluator, CascadeStage

        ev = CascadeEvaluator(_GoodVerifier(), quick_threshold=0.99)
        # Even perfect compliance: quick = 0.5*0.0 + 0.5*(0.5+0.5*0.9) = ~0.475 < 0.99
        c = _make_candidate(payload=_make_payload(safety_score=0.9))
        result = await ev.evaluate(c, performance_score=0.0)
        assert result.exit_stage == CascadeStage.QUICK
        assert not result.passed

    @pytest.mark.asyncio
    async def test_full_fail_low_fitness(self):
        from enhanced_agent_bus.openevolve_adapter.cascade import CascadeEvaluator, CascadeStage

        ev = CascadeEvaluator(_GoodVerifier(), quick_threshold=0.0, full_threshold=0.99)
        c = _make_candidate(payload=_make_payload(safety_score=0.1))
        result = await ev.evaluate(c, performance_score=0.1)
        assert result.exit_stage == CascadeStage.FULL
        assert not result.passed

    @pytest.mark.asyncio
    async def test_timings_recorded(self):
        ev = self._evaluator()
        c = _make_candidate(payload=_make_payload(safety_score=1.0))
        result = await ev.evaluate(c, performance_score=0.8)
        assert "syntax" in result.stage_timings_ms
        assert "full" in result.stage_timings_ms

    @pytest.mark.asyncio
    async def test_batch_passed_first(self):
        from enhanced_agent_bus.openevolve_adapter.cascade import CascadeEvaluator

        ev = CascadeEvaluator(_GoodVerifier(), quick_threshold=0.0, full_threshold=0.0)
        good = _make_candidate("good", payload=_make_payload(safety_score=1.0))
        bad = _make_candidate("bad", payload=_make_payload(syntax_valid=False))
        results = await ev.evaluate_batch([(bad, 0.1), (good, 0.9)])
        assert results[0].candidate_id == "good"
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_metrics_updated(self):
        ev = self._evaluator()
        good = _make_candidate(payload=_make_payload(safety_score=1.0))
        await ev.evaluate(good, performance_score=0.9)
        m = ev.metrics()
        assert m["evaluated"] == 1
        assert m["passed_full"] == 1

    def test_to_dict(self):
        from enhanced_agent_bus.openevolve_adapter.cascade import CascadeResult, CascadeStage

        r = CascadeResult(
            candidate_id="x",
            passed=True,
            exit_stage=CascadeStage.FULL,
            score=0.8,
            fitness_result=None,
        )
        d = r.to_dict()
        assert d["passed"] is True
        assert d["exit_stage"] == "full"


# ---------------------------------------------------------------------------
# EvolutionMessageHandler (integration)
# ---------------------------------------------------------------------------


def _make_meta(
    candidate_id: str = "cand-001",
    *,
    performance_score: float = 0.8,
    risk_tier: str = "low",
    stage: str = "canary",
    syntax_valid: bool = True,
    policy_compliant: bool = True,
    safety_score: float = 0.9,
    evolution_candidate: bool = True,
) -> dict[str, Any]:
    return {
        "evolution_candidate": evolution_candidate,
        "candidate_id": candidate_id,
        "constitutional_hash": HASH,
        "risk_tier": risk_tier,
        "proposed_rollout_stage": stage,
        "performance_score": performance_score,
        "verification_payload": {
            "validator_id": "test-validator",
            "verified_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": HASH,
            "syntax_valid": syntax_valid,
            "policy_compliant": policy_compliant,
            "safety_score": safety_score,
        },
    }


class _FakeMsg:
    """Minimal AgentMessage stub for handler tests."""

    def __init__(self, meta: dict[str, Any]) -> None:
        self.metadata = meta
        self.message_id = "msg-001"


class TestEvolutionMessageHandler:
    def _handler(self) -> EvolutionMessageHandler:
        from enhanced_agent_bus.openevolve_adapter.integration import EvolutionMessageHandler

        return EvolutionMessageHandler(_GoodVerifier())

    @pytest.mark.asyncio
    async def test_approved(self):
        h = self._handler()
        result = await h(_FakeMsg(_make_meta()))
        assert result.is_valid is True
        assert result.metadata["evolution_handler"] == "approved"

    @pytest.mark.asyncio
    async def test_skipped_non_evolution_message(self):
        h = self._handler()
        result = await h(_FakeMsg(_make_meta(evolution_candidate=False)))
        assert result.is_valid is True
        assert result.metadata["evolution_handler"] == "skipped_not_an_evolution_message"

    @pytest.mark.asyncio
    async def test_bad_payload_deserialise_error(self):
        h = self._handler()
        result = await h(_FakeMsg({"evolution_candidate": True, "candidate_id": "x"}))
        assert result.is_valid is False
        assert result.metadata["evolution_handler"] == "deserialise_error"

    @pytest.mark.asyncio
    async def test_cascade_rejection(self):
        h = self._handler()
        meta = _make_meta(syntax_valid=False)
        result = await h(_FakeMsg(meta))
        assert result.is_valid is False
        assert result.metadata["evolution_handler"] == "cascade_rejected"

    @pytest.mark.asyncio
    async def test_metrics_tracked(self):
        h = self._handler()
        await h(_FakeMsg(_make_meta()))
        m = h.metrics()
        assert m["received"] == 1
        assert m["gate_passed"] == 1

    @pytest.mark.asyncio
    async def test_gate_denied_critical_full(self):
        """CRITICAL tier attempting FULL is caught at candidate construction."""
        with pytest.raises(ValueError, match="does not allow"):
            _make_candidate(risk_tier=RiskTier.CRITICAL, proposed_rollout_stage=RolloutStage.FULL)

    @pytest.mark.asyncio
    async def test_mutation_trace_deserialised(self):
        from enhanced_agent_bus.openevolve_adapter.integration import (
            EvolutionMessageHandler,
            _deserialise_candidate,
        )

        meta = _make_meta()
        meta["mutation_trace"] = [
            {"operator": "crossover", "parent_id": "p-0", "description": "blend"}
        ]
        c = _deserialise_candidate(meta)
        assert c.generation == 1
