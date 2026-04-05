"""Precedent Cascade — Four-Stage Evolutionary Filter for Constitution Amendment.

New precedents are candidate mutations to the effective constitution.
A four-stage cascade filters them from cheapest (443ns DNA check) to most
expensive (multi-miner consensus + compatibility verification).

Stage 1: DNA Pre-check       → 443ns, catches obvious violations
Stage 2: Mesh Validation     → 3-peer quorum, quality filter
Stage 3: Multi-Miner Consensus → N-miner stability check
Stage 4: Constitutional Compatibility → contradiction detection

Evolutionary pattern: Cascade evaluation with ceiling detection.
Only precedents surviving all four stages amend the living constitution.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from acgs_lite import Constitution, ConstitutionalViolationError
from constitutional_swarm.dna import AgentDNA
from constitutional_swarm.mesh import ConstitutionalMesh


class CascadeStage(Enum):
    """The four progressive evaluation stages."""

    DNA_PRECHECK = "dna_precheck"
    MESH_VALIDATION = "mesh_validation"
    MULTI_MINER_CONSENSUS = "consensus"
    CONSTITUTIONAL_COMPATIBILITY = "compat"


STAGE_ORDER = [
    CascadeStage.DNA_PRECHECK,
    CascadeStage.MESH_VALIDATION,
    CascadeStage.MULTI_MINER_CONSENSUS,
    CascadeStage.CONSTITUTIONAL_COMPATIBILITY,
]


@dataclass(frozen=True, slots=True)
class CascadeResult:
    """Result of a single cascade stage."""

    stage: CascadeStage
    passed: bool
    latency_ns: int
    detail: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class PrecedentCandidate:
    """A proposed precedent moving through the cascade."""

    candidate_id: str
    judgment_text: str
    reasoning_text: str
    domain: str
    miner_uid: str
    constitutional_hash: str
    stage_results: tuple[CascadeResult, ...]
    current_stage: CascadeStage
    alive: bool

    @property
    def stages_passed(self) -> int:
        return sum(1 for r in self.stage_results if r.passed)

    def with_result(self, result: CascadeResult) -> PrecedentCandidate:
        """Return new candidate with the result appended."""
        next_idx = STAGE_ORDER.index(result.stage) + 1
        next_stage = STAGE_ORDER[next_idx] if next_idx < len(STAGE_ORDER) else result.stage
        return PrecedentCandidate(
            candidate_id=self.candidate_id,
            judgment_text=self.judgment_text,
            reasoning_text=self.reasoning_text,
            domain=self.domain,
            miner_uid=self.miner_uid,
            constitutional_hash=self.constitutional_hash,
            stage_results=(*self.stage_results, result),
            current_stage=next_stage,
            alive=self.alive and result.passed,
        )


@dataclass(frozen=True, slots=True)
class ConstitutionDelta:
    """A successfully cascaded precedent, ready for constitution integration."""

    candidate_id: str
    rule_text: str
    domain: str
    source_miner: str
    consensus_strength: float
    compatibility_verified: bool
    constitutional_hash: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class CascadeMetrics:
    """Funnel conversion tracking."""

    submitted: int = 0
    passed_dna: int = 0
    passed_mesh: int = 0
    passed_consensus: int = 0
    passed_compatibility: int = 0
    _improvement_window: list[float] = field(default_factory=list)
    window_size: int = 50

    def record_improvement(self, delta: float) -> None:
        self._improvement_window.append(delta)
        if len(self._improvement_window) > self.window_size:
            self._improvement_window = self._improvement_window[-self.window_size :]

    @property
    def ceiling_detected(self) -> bool:
        """No improvement above epsilon for the full window."""
        if len(self._improvement_window) < self.window_size:
            return False
        epsilon = 0.001
        return all(d < epsilon for d in self._improvement_window)

    def funnel_report(self) -> dict[str, Any]:
        return {
            "submitted": self.submitted,
            "passed_dna": self.passed_dna,
            "passed_mesh": self.passed_mesh,
            "passed_consensus": self.passed_consensus,
            "passed_compatibility": self.passed_compatibility,
            "conversion_rate": (self.passed_compatibility / max(self.submitted, 1)),
            "ceiling_detected": self.ceiling_detected,
        }


class PrecedentCascade:
    """Four-stage evolutionary cascade for constitution amendment.

    Usage:
        cascade = PrecedentCascade(constitution, mesh)
        candidate = cascade.run_full_cascade(
            judgment="Privacy takes precedence",
            reasoning="Article 8 ECHR applies",
            domain="privacy",
            miner_uid="miner-01",
        )
        if candidate.alive:
            delta = cascade.accept(candidate)
    """

    def __init__(
        self,
        constitution: Constitution,
        mesh: ConstitutionalMesh | None = None,
        *,
        consensus_threshold: float = 0.8,
        seed: int | None = None,
    ) -> None:
        self._constitution = constitution
        self._dna = AgentDNA(constitution=constitution, agent_id="cascade-validator", strict=False)
        self._mesh = mesh
        self._consensus_threshold = consensus_threshold
        self._metrics = CascadeMetrics()
        self._accepted: list[ConstitutionDelta] = []
        self._seed = seed

    @property
    def metrics(self) -> CascadeMetrics:
        return self._metrics

    @property
    def accepted_deltas(self) -> list[ConstitutionDelta]:
        return list(self._accepted)

    def submit(
        self,
        judgment: str,
        reasoning: str,
        domain: str,
        miner_uid: str,
    ) -> PrecedentCandidate:
        """Create a new candidate at Stage 1."""
        self._metrics.submitted += 1
        return PrecedentCandidate(
            candidate_id=uuid.uuid4().hex[:12],
            judgment_text=judgment,
            reasoning_text=reasoning,
            domain=domain,
            miner_uid=miner_uid,
            constitutional_hash=self._constitution.hash,
            stage_results=(),
            current_stage=CascadeStage.DNA_PRECHECK,
            alive=True,
        )

    def advance(self, candidate: PrecedentCandidate) -> PrecedentCandidate:
        """Advance a candidate through its current stage."""
        if not candidate.alive:
            return candidate

        stage = candidate.current_stage
        if stage == CascadeStage.DNA_PRECHECK:
            result = self._stage_dna(candidate)
        elif stage == CascadeStage.MESH_VALIDATION:
            result = self._stage_mesh(candidate)
        elif stage == CascadeStage.MULTI_MINER_CONSENSUS:
            result = self._stage_consensus(candidate)
        elif stage == CascadeStage.CONSTITUTIONAL_COMPATIBILITY:
            result = self._stage_compatibility(candidate)
        else:
            return candidate

        updated = candidate.with_result(result)

        # Track funnel
        if result.passed:
            if stage == CascadeStage.DNA_PRECHECK:
                self._metrics.passed_dna += 1
            elif stage == CascadeStage.MESH_VALIDATION:
                self._metrics.passed_mesh += 1
            elif stage == CascadeStage.MULTI_MINER_CONSENSUS:
                self._metrics.passed_consensus += 1
            elif stage == CascadeStage.CONSTITUTIONAL_COMPATIBILITY:
                self._metrics.passed_compatibility += 1

        return updated

    def run_full_cascade(
        self,
        judgment: str,
        reasoning: str,
        domain: str,
        miner_uid: str,
    ) -> PrecedentCandidate:
        """Run all four stages, short-circuiting on rejection."""
        candidate = self.submit(judgment, reasoning, domain, miner_uid)
        for _ in STAGE_ORDER:
            candidate = self.advance(candidate)
            if not candidate.alive:
                break
        return candidate

    def accept(self, candidate: PrecedentCandidate) -> ConstitutionDelta | None:
        """Accept a fully-cascaded candidate as a constitution delta.

        Returns None if the candidate didn't pass all stages.
        """
        if not candidate.alive or candidate.stages_passed < len(STAGE_ORDER):
            return None

        delta = ConstitutionDelta(
            candidate_id=candidate.candidate_id,
            rule_text=candidate.judgment_text,
            domain=candidate.domain,
            source_miner=candidate.miner_uid,
            consensus_strength=self._consensus_threshold,
            compatibility_verified=True,
            constitutional_hash=candidate.constitutional_hash,
        )
        self._accepted.append(delta)
        self._metrics.record_improvement(1.0)
        return delta

    def ceiling_detected(self) -> bool:
        """True when the constitution has converged."""
        return self._metrics.ceiling_detected

    # -- Stage Implementations -----------------------------------------------

    def _stage_dna(self, candidate: PrecedentCandidate) -> CascadeResult:
        """Stage 1: DNA pre-check (443ns target)."""
        start = time.perf_counter_ns()
        result = self._dna.validate(candidate.judgment_text)
        elapsed = time.perf_counter_ns() - start
        return CascadeResult(
            stage=CascadeStage.DNA_PRECHECK,
            passed=result.valid,
            latency_ns=elapsed,
            detail="pass" if result.valid else "; ".join(result.violations),
        )

    def _stage_mesh(self, candidate: PrecedentCandidate) -> CascadeResult:
        """Stage 2: Mesh validation (3-peer quorum)."""
        start = time.perf_counter_ns()
        if self._mesh is None:
            # No mesh available — pass through
            elapsed = time.perf_counter_ns() - start
            return CascadeResult(
                stage=CascadeStage.MESH_VALIDATION,
                passed=True,
                latency_ns=elapsed,
                detail="no mesh configured — pass through",
            )

        try:
            result = self._mesh.full_validation(
                producer_id=candidate.miner_uid,
                content=candidate.judgment_text,
                artifact_id=candidate.candidate_id,
            )
            elapsed = time.perf_counter_ns() - start
            return CascadeResult(
                stage=CascadeStage.MESH_VALIDATION,
                passed=result.accepted,
                latency_ns=elapsed,
                detail=f"votes: {result.votes_for}/{result.votes_for + result.votes_against}",
            )
        except (KeyError, ValueError) as exc:
            elapsed = time.perf_counter_ns() - start
            return CascadeResult(
                stage=CascadeStage.MESH_VALIDATION,
                passed=False,
                latency_ns=elapsed,
                detail=f"mesh error: {type(exc).__name__}",
            )

    def _stage_consensus(self, candidate: PrecedentCandidate) -> CascadeResult:
        """Stage 3: Multi-miner consensus.

        In production, this would re-broadcast the case to N miners and
        check for semantic agreement. For now, we check if the judgment
        passes DNA validation from multiple perspectives (strict + non-strict).
        """
        start = time.perf_counter_ns()
        # Simulate multi-perspective validation
        strict_dna = AgentDNA(
            constitution=self._constitution,
            agent_id="consensus-strict",
            strict=True,
        )
        nonstrict_dna = AgentDNA(
            constitution=self._constitution,
            agent_id="consensus-nonstrict",
            strict=False,
        )

        try:
            strict_dna.validate(candidate.judgment_text)
            strict_pass = True
        except ConstitutionalViolationError:
            strict_pass = False

        nonstrict_result = nonstrict_dna.validate(candidate.judgment_text)
        elapsed = time.perf_counter_ns() - start

        passed = strict_pass and nonstrict_result.valid
        return CascadeResult(
            stage=CascadeStage.MULTI_MINER_CONSENSUS,
            passed=passed,
            latency_ns=elapsed,
            detail=f"strict={strict_pass}, nonstrict={nonstrict_result.valid}",
        )

    def _stage_compatibility(self, candidate: PrecedentCandidate) -> CascadeResult:
        """Stage 4: Constitutional compatibility.

        Verify the precedent doesn't contradict existing rules.
        Cross-validates by checking if existing rules would be
        violated by the new precedent's text.
        """
        start = time.perf_counter_ns()
        # The judgment must pass DNA validation (already checked in Stage 1,
        # but here we also check the reasoning text)
        reasoning_result = self._dna.validate(candidate.reasoning_text)
        elapsed = time.perf_counter_ns() - start

        return CascadeResult(
            stage=CascadeStage.CONSTITUTIONAL_COMPATIBILITY,
            passed=reasoning_result.valid,
            latency_ns=elapsed,
            detail="compatible"
            if reasoning_result.valid
            else "; ".join(reasoning_result.violations),
        )
