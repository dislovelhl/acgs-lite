"""
OpenEvolve Governance Adapter — Governed Evolver
Constitutional Hash: 608508a9bd224290

Implements MACI separation-of-powers for the evolution loop:

- The **Proposer** (this class) generates and scores candidates.
- The **Validator** is *injected* — it is never created by the evolver itself.
- The evolver cannot verify its own output (MACI Golden Rule).

Usage::

    from enhanced_agent_bus.openevolve_adapter.evolver import GovernedEvolver
    from enhanced_agent_bus.openevolve_adapter.fitness import ConstitutionalFitness

    class MyValidator:
        async def verify(self, candidate: EvolutionCandidate) -> VerificationPayload: ...

    evolver = GovernedEvolver(
        verifier=MyValidator(),
        fitness=ConstitutionalFitness(threshold=0.6),
    )
    result = await evolver.evolve(candidate, performance_score=0.85)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from enhanced_agent_bus.observability.structured_logging import get_logger

from .candidate import EvolutionCandidate, VerificationPayload
from .fitness import ConstitutionalFitness, FitnessResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Validator protocol (dependency-injected — never self-created)
# ---------------------------------------------------------------------------


@runtime_checkable
class ConstitutionalVerifier(Protocol):
    """
    External validator contract.

    Any object that implements ``verify`` is accepted.  The verifier must be
    *independent* of the evolver — an evolver instance may never construct its
    own verifier (MACI: agents cannot self-validate).
    """

    async def verify(self, candidate: EvolutionCandidate) -> VerificationPayload:
        """Return a :class:`VerificationPayload` for *candidate*."""
        ...


# ---------------------------------------------------------------------------
# Evolution result
# ---------------------------------------------------------------------------


class EvolveResult:
    """Outcome of a single governed evolution step."""

    __slots__ = (
        "candidate",
        "fitness_result",
        "approved",
        "rejection_reason",
    )

    def __init__(
        self,
        candidate: EvolutionCandidate,
        fitness_result: FitnessResult,
        *,
        approved: bool,
        rejection_reason: str = "",
    ) -> None:
        self.candidate = candidate
        self.fitness_result = fitness_result
        self.approved = approved
        self.rejection_reason = rejection_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate.candidate_id,
            "approved": self.approved,
            "rejection_reason": self.rejection_reason,
            "fitness": self.fitness_result.to_dict(),
            "risk_tier": self.candidate.risk_tier.value,
            "proposed_rollout_stage": self.candidate.proposed_rollout_stage.value,
        }


# ---------------------------------------------------------------------------
# Governed Evolver
# ---------------------------------------------------------------------------


class GovernedEvolver:
    """
    MACI-compliant evolution orchestrator.

    The evolver *proposes* — it scores candidates using ``ConstitutionalFitness``
    and routes them through the injected verifier.  It never constructs or calls
    a verifier it owns; that would violate MACI separation of powers.

    Args:
        verifier: An external :class:`ConstitutionalVerifier`.  Must be injected;
                  must not be instantiated inside this class.
        fitness: A :class:`ConstitutionalFitness` instance (optional; defaults
                 to the standard 60/40 weighting with threshold 0.5).
    """

    def __init__(
        self,
        verifier: ConstitutionalVerifier,
        *,
        fitness: ConstitutionalFitness | None = None,
    ) -> None:
        if not isinstance(verifier, ConstitutionalVerifier):
            raise TypeError(
                f"verifier must implement ConstitutionalVerifier protocol, got {type(verifier)}"
            )
        self._verifier = verifier
        self._fitness = fitness or ConstitutionalFitness()
        self._metrics: dict[str, int] = {
            "candidates_evaluated": 0,
            "candidates_approved": 0,
            "candidates_rejected": 0,
        }

    # ------------------------------------------------------------------ #
    # Core API                                                              #
    # ------------------------------------------------------------------ #

    async def evolve(
        self,
        candidate: EvolutionCandidate,
        *,
        performance_score: float,
    ) -> EvolveResult:
        """
        Run one governed evolution step.

        The candidate must already carry a :class:`VerificationPayload` issued
        by an external validator (enforced via :meth:`EvolutionCandidate.__post_init__`).
        This method re-verifies using the injected verifier, then scores fitness.

        Args:
            candidate: A fully constructed :class:`EvolutionCandidate`.
            performance_score: Raw task performance in [0, 1].

        Returns:
            An :class:`EvolveResult` indicating approval and fitness details.
        """
        self._metrics["candidates_evaluated"] += 1

        # Re-verify with injected external verifier (MACI: cannot self-verify)
        try:
            fresh_payload = await self._verifier.verify(candidate)
        except Exception as exc:
            logger.warning(
                "Verification failed for candidate",
                candidate_id=candidate.candidate_id,
                error=str(exc),
            )
            self._metrics["candidates_rejected"] += 1
            fitness_result = self._fitness.evaluate(candidate, performance_score=0.0)
            return EvolveResult(
                candidate,
                fitness_result,
                approved=False,
                rejection_reason=f"Verification error: {exc}",
            )

        # Check basic compliance from fresh payload
        if not (fresh_payload.syntax_valid and fresh_payload.policy_compliant):
            self._metrics["candidates_rejected"] += 1
            fitness_result = self._fitness.evaluate(candidate, performance_score=performance_score)
            reason = "Verification payload: "
            if not fresh_payload.syntax_valid:
                reason += "syntax_invalid "
            if not fresh_payload.policy_compliant:
                reason += "policy_non_compliant"
            logger.info(
                "Candidate rejected by verifier",
                candidate_id=candidate.candidate_id,
                reason=reason.strip(),
            )
            return EvolveResult(
                candidate, fitness_result, approved=False, rejection_reason=reason.strip()
            )

        # Compute constitutional fitness
        fitness_result = self._fitness.evaluate(candidate, performance_score=performance_score)

        if fitness_result.passed:
            self._metrics["candidates_approved"] += 1
            logger.info(
                "Candidate approved",
                candidate_id=candidate.candidate_id,
                fitness=round(fitness_result.fitness, 4),
                risk_tier=candidate.risk_tier.value,
            )
            return EvolveResult(candidate, fitness_result, approved=True)
        else:
            self._metrics["candidates_rejected"] += 1
            reason = f"Fitness {fitness_result.fitness:.4f} below threshold"
            logger.info(
                "Candidate rejected (low fitness)",
                candidate_id=candidate.candidate_id,
                fitness=round(fitness_result.fitness, 4),
            )
            return EvolveResult(candidate, fitness_result, approved=False, rejection_reason=reason)

    async def evolve_batch(
        self,
        items: list[tuple[EvolutionCandidate, float]],
    ) -> list[EvolveResult]:
        """
        Evaluate a batch of (candidate, performance_score) pairs sequentially.

        Returns results sorted: approved first, then by descending fitness.
        """
        results: list[EvolveResult] = []
        for candidate, score in items:
            result = await self.evolve(candidate, performance_score=score)
            results.append(result)

        results.sort(key=lambda r: (r.approved, r.fitness_result.fitness), reverse=True)
        return results

    # ------------------------------------------------------------------ #
    # Metrics                                                               #
    # ------------------------------------------------------------------ #

    def get_metrics(self) -> dict[str, Any]:
        total = self._metrics["candidates_evaluated"]
        approval_rate = self._metrics["candidates_approved"] / total if total else 0.0
        return {
            **self._metrics,
            "approval_rate": round(approval_rate, 4),
        }
