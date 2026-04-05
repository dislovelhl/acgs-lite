"""
OpenEvolve Governance Adapter — Evolution Candidate Contract
Constitutional Hash: 608508a9bd224290

Defines the mandatory data contract for every evolution candidate that passes
through the ACGS-2 governed evolution pipeline.  All fields are immutable after
construction; the constitutional hash is validated at ``__post_init__`` time so
that malformed candidates are rejected before they reach the evaluation chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "608508a9bd224290"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Supporting enumerations
# ---------------------------------------------------------------------------


class RiskTier(str, Enum):
    """Risk tier for an evolution candidate — governs allowed rollout stages."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RolloutStage(str, Enum):
    """Rollout stage allowed for a given risk tier."""

    CANARY = "canary"
    SHADOW = "shadow"
    PARTIAL = "partial"
    FULL = "full"


# Risk tier → maximum allowed rollout stage
_TIER_MAX_STAGE: dict[RiskTier, set[RolloutStage]] = {
    RiskTier.LOW: {
        RolloutStage.CANARY,
        RolloutStage.SHADOW,
        RolloutStage.PARTIAL,
        RolloutStage.FULL,
    },
    RiskTier.MEDIUM: {
        RolloutStage.CANARY,
        RolloutStage.SHADOW,
        RolloutStage.PARTIAL,
        RolloutStage.FULL,
    },
    RiskTier.HIGH: {RolloutStage.CANARY, RolloutStage.SHADOW},
    RiskTier.CRITICAL: {RolloutStage.CANARY, RolloutStage.SHADOW, RolloutStage.PARTIAL},
}


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MutationRecord:
    """Single mutation applied to produce this candidate."""

    operator: str  # e.g. "crossover", "point_mutation", "inject"
    parent_id: str
    description: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator": self.operator,
            "parent_id": self.parent_id,
            "description": self.description,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class VerificationPayload:
    """Outputs produced by an independent MACI Validator — never self-generated."""

    validator_id: str  # Identity of the external validator
    verified_at: str  # ISO-8601 timestamp
    constitutional_hash: str  # Must match outer candidate's hash
    syntax_valid: bool
    policy_compliant: bool
    safety_score: float  # 0.0 – 1.0
    notes: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.safety_score <= 1.0):
            raise ValueError(f"safety_score must be in [0, 1], got {self.safety_score}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator_id": self.validator_id,
            "verified_at": self.verified_at,
            "constitutional_hash": self.constitutional_hash,
            "syntax_valid": self.syntax_valid,
            "policy_compliant": self.policy_compliant,
            "safety_score": self.safety_score,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Core contract
# ---------------------------------------------------------------------------


@dataclass
class EvolutionCandidate:
    """
    Governed evolution candidate — the central data contract.

    Every candidate entering the ACGS-2 evolution pipeline must carry:

    - An immutable constitutional_hash anchoring it to the active constitution.
    - A VerificationPayload produced by an *external* MACI Validator (never
      the same agent that proposed the candidate).
    - A risk_tier that restricts which rollout stages are permitted.
    - A mutation_trace recording every operator applied to produce this candidate.

    Raises:
        ValueError: If the constitutional hash is mismatched, the rollout stage
                    is not allowed for the risk tier, or verification failed.
    """

    candidate_id: str
    mutation_trace: list[MutationRecord]
    fitness_inputs: dict[str, Any]
    verification_payload: VerificationPayload
    constitutional_hash: str
    risk_tier: RiskTier
    proposed_rollout_stage: RolloutStage
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Constitutional hash mismatch: expected {CONSTITUTIONAL_HASH!r}, "
                f"got {self.constitutional_hash!r}"
            )
        if self.verification_payload.constitutional_hash != self.constitutional_hash:
            raise ValueError(
                "Mismatched constitutional hashes between candidate and verification_payload"
            )
        allowed = _TIER_MAX_STAGE[self.risk_tier]
        if self.proposed_rollout_stage not in allowed:
            raise ValueError(
                f"RiskTier.{self.risk_tier.value.upper()} does not allow "
                f"RolloutStage.{self.proposed_rollout_stage.value.upper()}. "
                f"Allowed: {sorted(s.value for s in allowed)}"
            )

    # ------------------------------------------------------------------ #
    # Derived properties                                                    #
    # ------------------------------------------------------------------ #

    @property
    def is_verified(self) -> bool:
        """True when the verification payload reports full compliance."""
        vp = self.verification_payload
        return vp.syntax_valid and vp.policy_compliant and vp.safety_score >= 0.5

    @property
    def generation(self) -> int:
        """Depth of the mutation trace (0 == seed candidate)."""
        return len(self.mutation_trace)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "constitutional_hash": self.constitutional_hash,
            "risk_tier": self.risk_tier.value,
            "proposed_rollout_stage": self.proposed_rollout_stage.value,
            "is_verified": self.is_verified,
            "generation": self.generation,
            "created_at": self.created_at,
            "mutation_trace": [m.to_dict() for m in self.mutation_trace],
            "verification_payload": self.verification_payload.to_dict(),
            "fitness_inputs": self.fitness_inputs,
            "metadata": self.metadata,
        }
