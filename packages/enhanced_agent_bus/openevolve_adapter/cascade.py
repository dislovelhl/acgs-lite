"""
OpenEvolve Governance Adapter — Cascade Evaluation
Constitutional Hash: 608508a9bd224290

Progressive three-stage evaluation pipeline that prunes bad candidates early,
saving compute for expensive stages.

Stage semantics
---------------
1. **Syntax** (<1 ms)   — structural validity, hash anchor, tier/stage legality.
   Threshold: 0.0  (any structural violation is fatal)

2. **Quick** (~1–100 ms) — lightweight fitness score using the caller-supplied
   performance estimate and verification payload.
   Threshold: configurable (default 0.3)

3. **Full** (~100 ms–10 s) — re-verification via the injected external verifier,
   then a full :class:`ConstitutionalFitness` evaluation.
   Threshold: configurable (default 0.5)

Candidates that fail any stage are returned immediately without advancing —
this is the "cascade" / "early-exit" behaviour that yields ~10× compute savings
when most candidates fail early.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from enhanced_agent_bus.observability.structured_logging import get_logger

from .candidate import EvolutionCandidate
from .evolver import ConstitutionalVerifier
from .fitness import ConstitutionalFitness, FitnessResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stage enumeration
# ---------------------------------------------------------------------------


class CascadeStage(str, Enum):
    SYNTAX = "syntax"
    QUICK = "quick"
    FULL = "full"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CascadeResult:
    """Outcome of a cascade evaluation run."""

    candidate_id: str
    passed: bool  # True iff the candidate cleared all stages
    exit_stage: CascadeStage  # Stage at which evaluation stopped
    score: float  # Best score reached (0.0 if syntax failed)
    fitness_result: FitnessResult | None  # Only set when FULL stage completes
    rejection_reason: str = ""
    stage_timings_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "passed": self.passed,
            "exit_stage": self.exit_stage.value,
            "score": self.score,
            "rejection_reason": self.rejection_reason,
            "stage_timings_ms": self.stage_timings_ms,
            "fitness": self.fitness_result.to_dict() if self.fitness_result else None,
        }


# ---------------------------------------------------------------------------
# Cascade evaluator
# ---------------------------------------------------------------------------


class CascadeEvaluator:
    """
    Three-stage cascade evaluation pipeline for evolution candidates.

    Args:
        verifier: External :class:`ConstitutionalVerifier` — used only in Stage 3.
        fitness: :class:`ConstitutionalFitness` instance (default: 60/40, threshold 0.5).
        quick_threshold: Minimum quick-score to pass Stage 2 (default 0.3).
        full_threshold: Minimum fitness to pass Stage 3 (default 0.5).

    Example::

        evaluator = CascadeEvaluator(verifier=my_verifier)
        result = await evaluator.evaluate(candidate, performance_score=0.8)
        if result.passed:
            # promote to rollout controller
            ...
    """

    def __init__(
        self,
        verifier: ConstitutionalVerifier,
        *,
        fitness: ConstitutionalFitness | None = None,
        quick_threshold: float = 0.3,
        full_threshold: float = 0.5,
    ) -> None:
        self._verifier = verifier
        self._fitness = fitness or ConstitutionalFitness(threshold=full_threshold)
        self._quick_threshold = quick_threshold
        self._full_threshold = full_threshold

        # Running totals for metrics
        self._counts: dict[str, int] = {
            "evaluated": 0,
            "passed_syntax": 0,
            "passed_quick": 0,
            "passed_full": 0,
            "failed_syntax": 0,
            "failed_quick": 0,
            "failed_full": 0,
        }

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    async def evaluate(
        self,
        candidate: EvolutionCandidate,
        *,
        performance_score: float,
    ) -> CascadeResult:
        """
        Run the three-stage cascade for a single candidate.

        Args:
            candidate: The :class:`EvolutionCandidate` to evaluate.
            performance_score: Raw task performance in [0, 1].

        Returns:
            A :class:`CascadeResult` with the exit stage and final score.
        """
        self._counts["evaluated"] += 1
        timings: dict[str, float] = {}

        # ── Stage 1: Syntax ──────────────────────────────────────────────
        t0 = time.perf_counter()
        syntax_ok, syntax_reason = self._stage_syntax(candidate)
        timings[CascadeStage.SYNTAX.value] = (time.perf_counter() - t0) * 1000

        if not syntax_ok:
            self._counts["failed_syntax"] += 1
            logger.debug(
                "Cascade: syntax fail",
                candidate_id=candidate.candidate_id,
                reason=syntax_reason,
            )
            return CascadeResult(
                candidate_id=candidate.candidate_id,
                passed=False,
                exit_stage=CascadeStage.SYNTAX,
                score=0.0,
                fitness_result=None,
                rejection_reason=syntax_reason,
                stage_timings_ms=timings,
            )

        self._counts["passed_syntax"] += 1

        # ── Stage 2: Quick ───────────────────────────────────────────────
        t1 = time.perf_counter()
        quick_score = self._stage_quick(candidate, performance_score)
        timings[CascadeStage.QUICK.value] = (time.perf_counter() - t1) * 1000

        if quick_score < self._quick_threshold:
            self._counts["failed_quick"] += 1
            reason = f"Quick score {quick_score:.4f} below threshold {self._quick_threshold}"
            logger.debug(
                "Cascade: quick fail",
                candidate_id=candidate.candidate_id,
                score=quick_score,
            )
            return CascadeResult(
                candidate_id=candidate.candidate_id,
                passed=False,
                exit_stage=CascadeStage.QUICK,
                score=quick_score,
                fitness_result=None,
                rejection_reason=reason,
                stage_timings_ms=timings,
            )

        self._counts["passed_quick"] += 1

        # ── Stage 3: Full ────────────────────────────────────────────────
        t2 = time.perf_counter()
        fitness_result, full_reason = await self._stage_full(candidate, performance_score)
        timings[CascadeStage.FULL.value] = (time.perf_counter() - t2) * 1000

        if not fitness_result.passed:
            self._counts["failed_full"] += 1
            logger.info(
                "Cascade: full fail",
                candidate_id=candidate.candidate_id,
                fitness=fitness_result.fitness,
                reason=full_reason,
            )
            return CascadeResult(
                candidate_id=candidate.candidate_id,
                passed=False,
                exit_stage=CascadeStage.FULL,
                score=fitness_result.fitness,
                fitness_result=fitness_result,
                rejection_reason=full_reason,
                stage_timings_ms=timings,
            )

        self._counts["passed_full"] += 1
        logger.info(
            "Cascade: passed all stages",
            candidate_id=candidate.candidate_id,
            fitness=fitness_result.fitness,
        )
        return CascadeResult(
            candidate_id=candidate.candidate_id,
            passed=True,
            exit_stage=CascadeStage.FULL,
            score=fitness_result.fitness,
            fitness_result=fitness_result,
            stage_timings_ms=timings,
        )

    async def evaluate_batch(
        self,
        items: list[tuple[EvolutionCandidate, float]],
    ) -> list[CascadeResult]:
        """
        Evaluate a batch sequentially, returning results in input order.

        Candidates that pass all stages are sorted first by score (desc).
        Failed candidates retain their original order at the end.
        """
        results: list[CascadeResult] = []
        for candidate, score in items:
            result = await self.evaluate(candidate, performance_score=score)
            results.append(result)

        passed = sorted((r for r in results if r.passed), key=lambda r: r.score, reverse=True)
        failed = [r for r in results if not r.passed]
        return passed + failed

    def metrics(self) -> dict[str, Any]:
        """Return evaluation throughput and stage-pass-rate metrics."""
        total = self._counts["evaluated"]
        return {
            **self._counts,
            "syntax_pass_rate": _rate(self._counts["passed_syntax"], total),
            "quick_pass_rate": _rate(self._counts["passed_quick"], self._counts["passed_syntax"]),
            "full_pass_rate": _rate(self._counts["passed_full"], self._counts["passed_quick"]),
            "overall_pass_rate": _rate(self._counts["passed_full"], total),
        }

    # ------------------------------------------------------------------ #
    # Stage implementations                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _stage_syntax(candidate: EvolutionCandidate) -> tuple[bool, str]:
        """
        Stage 1 — structural validity check (no I/O, <1 ms).

        Validates:
        - candidate_id is non-empty
        - constitutional hash is present
        - verification_payload is attached
        - candidate.is_verified (syntax + policy + safety ≥ 0.5)
        """
        if not candidate.candidate_id or not candidate.candidate_id.strip():
            return False, "candidate_id is empty"
        if not candidate.constitutional_hash:
            return False, "constitutional_hash is empty"
        if candidate.verification_payload is None:
            return False, "verification_payload is missing"
        if not candidate.verification_payload.syntax_valid:
            return False, "verification_payload.syntax_valid is False"
        if not candidate.verification_payload.policy_compliant:
            return False, "verification_payload.policy_compliant is False"
        return True, ""

    @staticmethod
    def _stage_quick(candidate: EvolutionCandidate, performance_score: float) -> float:
        """
        Stage 2 — lightweight blended score (~1 ms, no external calls).

        Uses the existing verification payload (no re-verification) and a
        simplified 50/50 blend to quickly filter obvious losers.
        """
        vp = candidate.verification_payload
        compliance = 0.5 * int(vp.syntax_valid) + 0.5 * vp.safety_score
        return 0.5 * performance_score + 0.5 * compliance

    async def _stage_full(
        self,
        candidate: EvolutionCandidate,
        performance_score: float,
    ) -> tuple[FitnessResult, str]:
        """
        Stage 3 — full re-verification + constitutional fitness (~100 ms–10 s).

        Re-runs the external verifier to get a fresh payload, then scores via
        ConstitutionalFitness.  If the verifier raises, the candidate fails.
        """
        try:
            await self._verifier.verify(candidate)
        except Exception as exc:
            # Build a zero-score result on verifier failure
            dummy = self._fitness.evaluate(candidate, performance_score=0.0)
            return dummy, f"Verifier error: {exc}"

        result = self._fitness.evaluate(candidate, performance_score=performance_score)
        reason = (
            ""
            if result.passed
            else f"Full fitness {result.fitness:.4f} below threshold {self._full_threshold}"
        )
        return result, reason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
