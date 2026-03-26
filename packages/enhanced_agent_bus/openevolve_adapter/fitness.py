"""
OpenEvolve Governance Adapter — Constitutional Fitness
Constitutional Hash: 608508a9bd224290

Computes a blended fitness score that weights raw performance against
constitutional compliance.  A risk multiplier further penalises high-risk
candidates, ensuring that governance constraints are never drowned out by
pure performance optimisation.

Fitness formula::

    fitness = (0.6 * performance_score + 0.4 * compliance_score) * risk_multiplier

Risk multipliers:
    LOW      → 1.0   (no penalty)
    MEDIUM   → 0.9   (10 % penalty)
    HIGH     → 0.75  (25 % penalty)
    CRITICAL → 0.5   (50 % penalty)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .candidate import EvolutionCandidate, RiskTier

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PERFORMANCE_WEIGHT: float = 0.6
COMPLIANCE_WEIGHT: float = 0.4

_RISK_MULTIPLIERS: dict[RiskTier, float] = {
    RiskTier.LOW: 1.0,
    RiskTier.MEDIUM: 0.9,
    RiskTier.HIGH: 0.75,
    RiskTier.CRITICAL: 0.5,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FitnessResult:
    """Output of a single fitness evaluation."""

    candidate_id: str
    performance_score: float  # 0.0 – 1.0 — raw task performance
    compliance_score: float  # 0.0 – 1.0 — constitutional compliance
    risk_multiplier: float
    fitness: float  # blended, risk-adjusted score
    passed: bool  # True when fitness ≥ threshold
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "performance_score": self.performance_score,
            "compliance_score": self.compliance_score,
            "risk_multiplier": self.risk_multiplier,
            "fitness": self.fitness,
            "passed": self.passed,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Fitness evaluator
# ---------------------------------------------------------------------------


class ConstitutionalFitness:
    """
    Multi-objective fitness evaluator with constitutional compliance weighting.

    Args:
        threshold: Minimum blended fitness for a candidate to pass (default 0.5).
        performance_weight: Weight given to raw performance (default 0.6).
        compliance_weight: Weight given to constitutional compliance (default 0.4).

    The two weights must sum to 1.0.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        performance_weight: float = PERFORMANCE_WEIGHT,
        compliance_weight: float = COMPLIANCE_WEIGHT,
    ) -> None:
        if abs(performance_weight + compliance_weight - 1.0) > 1e-9:
            raise ValueError(
                f"performance_weight + compliance_weight must equal 1.0, "
                f"got {performance_weight + compliance_weight}"
            )
        self._threshold = threshold
        self._pw = performance_weight
        self._cw = compliance_weight

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def evaluate(
        self,
        candidate: EvolutionCandidate,
        *,
        performance_score: float,
    ) -> FitnessResult:
        """
        Evaluate a candidate's constitutional fitness.

        Args:
            candidate: The :class:`EvolutionCandidate` to score.
            performance_score: Raw task performance in [0, 1].  Callers are
                responsible for computing this via domain-specific metrics.

        Returns:
            A :class:`FitnessResult` capturing all scoring components.

        Raises:
            ValueError: If *performance_score* is outside [0, 1].
        """
        if not (0.0 <= performance_score <= 1.0):
            raise ValueError(f"performance_score must be in [0, 1], got {performance_score}")

        compliance_score = self._compliance_from_payload(candidate)
        risk_multiplier = _RISK_MULTIPLIERS[candidate.risk_tier]

        blended = (self._pw * performance_score + self._cw * compliance_score) * risk_multiplier
        # Clamp to [0, 1] — risk multiplier can theoretically exceed it via float arithmetic
        fitness = min(max(blended, 0.0), 1.0)

        return FitnessResult(
            candidate_id=candidate.candidate_id,
            performance_score=performance_score,
            compliance_score=compliance_score,
            risk_multiplier=risk_multiplier,
            fitness=fitness,
            passed=fitness >= self._threshold,
            detail={
                "performance_weight": self._pw,
                "compliance_weight": self._cw,
                "threshold": self._threshold,
                "risk_tier": candidate.risk_tier.value,
                "syntax_valid": candidate.verification_payload.syntax_valid,
                "policy_compliant": candidate.verification_payload.policy_compliant,
            },
        )

    def rank(
        self,
        candidates: list[tuple[EvolutionCandidate, float]],
    ) -> list[FitnessResult]:
        """
        Evaluate and rank a list of (candidate, performance_score) pairs.

        Returns results sorted descending by fitness, passing candidates first.
        """
        results = [self.evaluate(c, performance_score=s) for c, s in candidates]
        return sorted(results, key=lambda r: (r.passed, r.fitness), reverse=True)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compliance_from_payload(candidate: EvolutionCandidate) -> float:
        """Derive a [0, 1] compliance score from the verification payload."""
        vp = candidate.verification_payload
        # Each boolean component contributes ⅓; safety_score contributes the rest
        bool_score = 0.333 * int(vp.syntax_valid) + 0.333 * int(vp.policy_compliant)
        return min(bool_score + 0.334 * vp.safety_score, 1.0)
