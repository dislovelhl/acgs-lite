"""
OpenEvolve Governance Adapter — Rollout Controller
Constitutional Hash: 608508a9bd224290

Bridges EvolutionCandidate risk tiers to concrete rollout constraints:

| Risk Tier | Allowed Stages              | Min Canary   | Human Approval |
|-----------|----------------------------|--------------|----------------|
| LOW       | any                        | 1 h          | no             |
| MEDIUM    | any (shadow validation)    | 1 h          | no             |
| HIGH      | canary, shadow only        | 24 h         | yes            |
| CRITICAL  | canary, shadow, partial    | 72 h         | yes (mandatory)|

The controller enforces these constraints and records a decision audit trail.
It does NOT execute rollouts — that is the Executor's responsibility (MACI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from enhanced_agent_bus.observability.structured_logging import get_logger

from .candidate import EvolutionCandidate, RiskTier, RolloutStage

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Rollout constraints per risk tier
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TierConstraints:
    allowed_stages: frozenset[RolloutStage]
    min_canary_hours: float
    requires_human_approval: bool
    shadow_validation_required: bool = False


_TIER_CONSTRAINTS: dict[RiskTier, TierConstraints] = {
    RiskTier.LOW: TierConstraints(
        allowed_stages=frozenset(RolloutStage),
        min_canary_hours=1.0,
        requires_human_approval=False,
    ),
    RiskTier.MEDIUM: TierConstraints(
        allowed_stages=frozenset(RolloutStage),
        min_canary_hours=1.0,
        requires_human_approval=False,
        shadow_validation_required=True,
    ),
    RiskTier.HIGH: TierConstraints(
        allowed_stages=frozenset({RolloutStage.CANARY, RolloutStage.SHADOW}),
        min_canary_hours=24.0,
        requires_human_approval=True,
    ),
    RiskTier.CRITICAL: TierConstraints(
        allowed_stages=frozenset({RolloutStage.CANARY, RolloutStage.SHADOW, RolloutStage.PARTIAL}),
        min_canary_hours=72.0,
        requires_human_approval=True,
    ),
}


# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RolloutDecision:
    """Immutable record of a single rollout gate decision."""

    candidate_id: str
    risk_tier: str
    proposed_stage: str
    allowed: bool
    reason: str
    constraints: dict[str, Any]
    decided_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "risk_tier": self.risk_tier,
            "proposed_stage": self.proposed_stage,
            "allowed": self.allowed,
            "reason": self.reason,
            "constraints": self.constraints,
            "decided_at": self.decided_at,
        }


# ---------------------------------------------------------------------------
# Rollout Controller
# ---------------------------------------------------------------------------


class RolloutController:
    """
    Constitutional rollout gate — enforces tier-based stage constraints.

    Responsibilities (Proposer-side only):
    - Validate that a candidate's proposed_rollout_stage is permitted for
      its risk_tier.
    - Surface human-approval requirements before any executor acts.
    - Maintain an immutable audit trail of every gate decision.

    The controller decides but never executes.  Execution is the Executor's
    responsibility under MACI separation of powers.
    """

    def __init__(self) -> None:
        self._decisions: list[RolloutDecision] = []

    # ------------------------------------------------------------------ #
    # Gate API                                                              #
    # ------------------------------------------------------------------ #

    def gate(self, candidate: EvolutionCandidate) -> RolloutDecision:
        """
        Evaluate whether *candidate* may proceed to its proposed rollout stage.

        Args:
            candidate: A fully constructed :class:`EvolutionCandidate`.

        Returns:
            A :class:`RolloutDecision` — always returned (never raises).
            Callers must inspect ``decision.allowed`` before proceeding.
        """
        constraints = _TIER_CONSTRAINTS[candidate.risk_tier]
        proposed = candidate.proposed_rollout_stage

        if proposed not in constraints.allowed_stages:
            reason = (
                f"RiskTier.{candidate.risk_tier.value.upper()} forbids "
                f"RolloutStage.{proposed.value.upper()}. "
                f"Allowed: {sorted(s.value for s in constraints.allowed_stages)}"
            )
            decision = self._record(
                candidate, allowed=False, reason=reason, constraints=constraints
            )
            logger.warning("Rollout gate DENIED", **_log_fields(decision))
            return decision

        if not candidate.is_verified:
            reason = "Candidate is_verified=False — verification payload incomplete or failing"
            decision = self._record(
                candidate, allowed=False, reason=reason, constraints=constraints
            )
            logger.warning("Rollout gate DENIED (unverified)", **_log_fields(decision))
            return decision

        notes: list[str] = []
        if constraints.requires_human_approval:
            notes.append(
                f"Human approval required before execution "
                f"(min canary: {constraints.min_canary_hours}h)"
            )
        if constraints.shadow_validation_required:
            notes.append("Shadow validation pass required before canary promotion")

        reason = "Approved" + (f" — {'; '.join(notes)}" if notes else "")
        decision = self._record(candidate, allowed=True, reason=reason, constraints=constraints)
        logger.info("Rollout gate APPROVED", **_log_fields(decision))
        return decision

    def gate_batch(self, candidates: list[EvolutionCandidate]) -> list[RolloutDecision]:
        """Gate multiple candidates; returns decisions in the same order."""
        return [self.gate(c) for c in candidates]

    # ------------------------------------------------------------------ #
    # Audit                                                                 #
    # ------------------------------------------------------------------ #

    def audit_trail(self) -> list[dict[str, Any]]:
        """Return the full immutable audit trail as a list of dicts."""
        return [d.to_dict() for d in self._decisions]

    def metrics(self) -> dict[str, Any]:
        total = len(self._decisions)
        approved = sum(1 for d in self._decisions if d.allowed)
        return {
            "total_decisions": total,
            "approved": approved,
            "denied": total - approved,
            "approval_rate": round(approved / total, 4) if total else 0.0,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _record(
        self,
        candidate: EvolutionCandidate,
        *,
        allowed: bool,
        reason: str,
        constraints: TierConstraints,
    ) -> RolloutDecision:
        decision = RolloutDecision(
            candidate_id=candidate.candidate_id,
            risk_tier=candidate.risk_tier.value,
            proposed_stage=candidate.proposed_rollout_stage.value,
            allowed=allowed,
            reason=reason,
            constraints={
                "allowed_stages": sorted(s.value for s in constraints.allowed_stages),
                "min_canary_hours": constraints.min_canary_hours,
                "requires_human_approval": constraints.requires_human_approval,
                "shadow_validation_required": constraints.shadow_validation_required,
            },
        )
        self._decisions.append(decision)
        return decision


def _log_fields(decision: RolloutDecision) -> dict[str, Any]:
    return {
        "candidate_id": decision.candidate_id,
        "risk_tier": decision.risk_tier,
        "proposed_stage": decision.proposed_stage,
        "allowed": decision.allowed,
    }
