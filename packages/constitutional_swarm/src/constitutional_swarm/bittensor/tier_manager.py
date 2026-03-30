"""Tier Manager — Phase 5: miner qualification tiers + task routing.

Tracks per-miner performance history, evaluates tier eligibility based on
TIER_REQUIREMENTS, promotes/demotes automatically, and routes governance
tasks to miners whose tier is sufficient for the task complexity.

Tier structure (from roadmap Phase 5.1):
  APPRENTICE  < 10 validated, any reputation       LOW tasks only     1.0x TAO
  JOURNEYMAN  ≥ 10 validated, reputation ≥ 1.2     LOW + MEDIUM       1.5x TAO
  MASTER      ≥ 50 validated, reputation ≥ 1.5     ALL tiers          2.5x TAO
  ELDER       ≥ 200 validated, reputation ≥ 1.8    Constitutional     4.0x TAO

Task complexity mapping (from MEDIUM/HIGH impact routing):
  LOW     → any tier
  MEDIUM  → Journeyman+
  HIGH    → Master+
  CONSTITUTIONAL → Elder only

Integration:
  • CapabilityRegistry: tier tags ("tier:master") registered per miner
  • ConstitutionalValidator.compute_emission_weights(): reads tier via MinerTier
  • PrecedentStore: precedent_contribution feeds Elder promotion criteria

Roadmap: 08-subnet-implementation-roadmap.md § Phase 5
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from constitutional_swarm.bittensor.protocol import (
    MinerTier,
    TIER_REQUIREMENTS,
    TIER_TAO_MULTIPLIER,
)
from constitutional_swarm.capability import Capability, CapabilityRegistry


# ---------------------------------------------------------------------------
# Task complexity
# ---------------------------------------------------------------------------


class TaskComplexity(Enum):
    """Complexity level of a governance task.

    Maps onto the ACGS-2 escalation tiers (LOW/MEDIUM/HIGH) plus
    the Elder-only CONSTITUTIONAL tier for amendment proposals.
    """

    LOW            = "low"             # fully automated, any tier can deliberate
    MEDIUM         = "medium"          # 15-min human window, Journeyman+
    HIGH           = "high"            # blocks until approval, Master+
    CONSTITUTIONAL = "constitutional"  # amendment proposals, Elder only


# Minimum tier required to handle each complexity level
_COMPLEXITY_MIN_TIER: dict[TaskComplexity, MinerTier] = {
    TaskComplexity.LOW:            MinerTier.APPRENTICE,
    TaskComplexity.MEDIUM:         MinerTier.JOURNEYMAN,
    TaskComplexity.HIGH:           MinerTier.MASTER,
    TaskComplexity.CONSTITUTIONAL: MinerTier.ELDER,
}

# Tier ordering for comparison
_TIER_ORDER: dict[MinerTier, int] = {
    MinerTier.APPRENTICE: 0,
    MinerTier.JOURNEYMAN: 1,
    MinerTier.MASTER:     2,
    MinerTier.ELDER:      3,
}


# ---------------------------------------------------------------------------
# Miner performance record
# ---------------------------------------------------------------------------


@dataclass
class MinerPerformance:
    """Cumulative performance record for a single miner.

    Updated after each judgment validated (accepted or rejected).
    Precedent contributions are set when a validated judgment is
    recorded in the PrecedentStore.
    """

    miner_uid: str
    current_tier: MinerTier = MinerTier.APPRENTICE
    judgments_validated: int = 0       # accepted by validators
    judgments_rejected: int = 0        # rejected by validators
    precedents_contributed: int = 0    # stored in PrecedentStore
    reputation: float = 1.0            # from ConstitutionalMesh (default 1.0)
    domains: set[str] = field(default_factory=set)
    avg_authenticity: float = 0.0      # rolling average from AuthenticityDetector
    first_seen_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)

    @property
    def acceptance_rate(self) -> float:
        total = self.judgments_validated + self.judgments_rejected
        if total == 0:
            return 0.0
        return self.judgments_validated / total

    @property
    def is_domain_specialist(self) -> bool:
        """Master requires specialization in ≥ 1 domain."""
        return len(self.domains) >= 1

    def summary(self) -> dict[str, Any]:
        return {
            "miner_uid": self.miner_uid,
            "current_tier": self.current_tier.value,
            "tao_multiplier": TIER_TAO_MULTIPLIER[self.current_tier],
            "judgments_validated": self.judgments_validated,
            "judgments_rejected": self.judgments_rejected,
            "acceptance_rate": round(self.acceptance_rate, 3),
            "precedents_contributed": self.precedents_contributed,
            "reputation": round(self.reputation, 3),
            "domains": sorted(self.domains),
            "avg_authenticity": round(self.avg_authenticity, 3),
        }


# ---------------------------------------------------------------------------
# Promotion event
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TierPromotion:
    """Immutable record of a tier change event."""

    event_id: str
    miner_uid: str
    from_tier: MinerTier
    to_tier: MinerTier
    reason: str
    occurred_at: float

    @property
    def is_promotion(self) -> bool:
        return _TIER_ORDER[self.to_tier] > _TIER_ORDER[self.from_tier]

    @property
    def is_demotion(self) -> bool:
        return _TIER_ORDER[self.to_tier] < _TIER_ORDER[self.from_tier]


# ---------------------------------------------------------------------------
# Routing result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """Result of routing a task to a qualified miner."""

    task_id: str
    complexity: TaskComplexity
    min_tier_required: MinerTier
    eligible_miners: tuple[str, ...]
    selected_miner: str | None
    selection_reason: str


# ---------------------------------------------------------------------------
# Tier Manager
# ---------------------------------------------------------------------------


class TierManager:
    """Manages miner tiers and routes governance tasks by complexity.

    Usage::

        registry = CapabilityRegistry()
        manager = TierManager(registry)

        # Register a new miner (starts as APPRENTICE)
        manager.register_miner("miner-01", domains={"finance"})

        # After a validated judgment
        manager.record_judgment("miner-01", accepted=True,
                                domain="finance", authenticity=0.72)

        # Check current tier
        perf = manager.get_performance("miner-01")
        print(perf.current_tier)  # APPRENTICE until 10 validated

        # Route a task
        result = manager.route_task("task-42", TaskComplexity.MEDIUM)
        print(result.selected_miner)   # picks a Journeyman+ miner

        # Force tier re-evaluation (called periodically by SN Owner)
        promotions = manager.evaluate_all_tiers()
        for p in promotions:
            print(f"{p.miner_uid}: {p.from_tier.value} → {p.to_tier.value}")
    """

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry or CapabilityRegistry()
        self._miners: dict[str, MinerPerformance] = {}
        self._promotion_log: list[TierPromotion] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_miner(
        self,
        miner_uid: str,
        domains: set[str] | None = None,
        initial_tier: MinerTier = MinerTier.APPRENTICE,
    ) -> MinerPerformance:
        """Register a new miner. Idempotent — re-registration is a no-op."""
        if miner_uid in self._miners:
            return self._miners[miner_uid]

        perf = MinerPerformance(
            miner_uid=miner_uid,
            current_tier=initial_tier,
            domains=set(domains or []),
        )
        self._miners[miner_uid] = perf
        self._sync_registry(perf)
        return perf

    def unregister_miner(self, miner_uid: str) -> None:
        """Remove a miner from tracking and the CapabilityRegistry."""
        self._miners.pop(miner_uid, None)
        self._registry.unregister(miner_uid)

    # ------------------------------------------------------------------
    # Performance recording
    # ------------------------------------------------------------------

    def record_judgment(
        self,
        miner_uid: str,
        accepted: bool,
        domain: str = "",
        authenticity: float = 0.0,
        reputation: float | None = None,
    ) -> TierPromotion | None:
        """Record a judgment outcome and optionally promote the miner.

        Args:
            miner_uid:    the miner's ID
            accepted:     True if validator accepted the judgment
            domain:       domain of the task (e.g. "finance", "healthcare")
            authenticity: AuthenticityDetector score for this judgment
            reputation:   current mesh reputation score (updates rolling value)

        Returns:
            TierPromotion if a tier change occurred, else None.
        """
        if miner_uid not in self._miners:
            self.register_miner(miner_uid, domains={domain} if domain else None)

        perf = self._miners[miner_uid]
        if accepted:
            perf.judgments_validated += 1
        else:
            perf.judgments_rejected += 1

        if domain:
            perf.domains.add(domain)

        if authenticity > 0:
            # Exponential moving average
            alpha = 0.2
            perf.avg_authenticity = (
                alpha * authenticity + (1 - alpha) * perf.avg_authenticity
            )

        if reputation is not None:
            perf.reputation = reputation

        perf.last_active_at = time.time()

        # Re-evaluate tier
        return self._evaluate_tier(perf)

    def record_precedent(self, miner_uid: str) -> TierPromotion | None:
        """Record that a miner's judgment was stored as precedent.

        Precedent contributions feed the Elder promotion criteria.
        """
        if miner_uid not in self._miners:
            self.register_miner(miner_uid)
        perf = self._miners[miner_uid]
        perf.precedents_contributed += 1
        return self._evaluate_tier(perf)

    # ------------------------------------------------------------------
    # Task routing
    # ------------------------------------------------------------------

    def route_task(
        self,
        task_id: str,
        complexity: TaskComplexity,
        domain: str = "",
        prefer_specialist: bool = True,
    ) -> RoutingResult:
        """Route a task to the most qualified eligible miner.

        Eligibility: miner's tier ≥ minimum required for complexity.
        Selection priority:
          1. Domain specialist (if prefer_specialist and domain set)
          2. Higher tier (more experienced)
          3. Higher acceptance rate

        Returns RoutingResult with selected_miner=None if no eligible miner.
        """
        min_tier = _COMPLEXITY_MIN_TIER[complexity]
        min_order = _TIER_ORDER[min_tier]

        eligible = [
            perf for perf in self._miners.values()
            if _TIER_ORDER[perf.current_tier] >= min_order
        ]

        if not eligible:
            return RoutingResult(
                task_id=task_id,
                complexity=complexity,
                min_tier_required=min_tier,
                eligible_miners=(),
                selected_miner=None,
                selection_reason=f"No miners at {min_tier.value}+ tier",
            )

        # Score candidates
        def _score(p: MinerPerformance) -> tuple:
            specialist = domain in p.domains if domain else False
            return (
                1 if (prefer_specialist and specialist) else 0,
                _TIER_ORDER[p.current_tier],
                p.acceptance_rate,
                p.avg_authenticity,
            )

        best = max(eligible, key=_score)
        reason_parts = [f"tier:{best.current_tier.value}"]
        if domain and domain in best.domains:
            reason_parts.append(f"specialist:{domain}")
        reason_parts.append(f"acceptance:{best.acceptance_rate:.2f}")

        return RoutingResult(
            task_id=task_id,
            complexity=complexity,
            min_tier_required=min_tier,
            eligible_miners=tuple(p.miner_uid for p in eligible),
            selected_miner=best.miner_uid,
            selection_reason=", ".join(reason_parts),
        )

    def eligible_miners(
        self,
        complexity: TaskComplexity,
    ) -> list[MinerPerformance]:
        """Return all miners eligible for a given task complexity."""
        min_order = _TIER_ORDER[_COMPLEXITY_MIN_TIER[complexity]]
        return [
            p for p in self._miners.values()
            if _TIER_ORDER[p.current_tier] >= min_order
        ]

    # ------------------------------------------------------------------
    # Tier evaluation
    # ------------------------------------------------------------------

    def evaluate_all_tiers(self) -> list[TierPromotion]:
        """Re-evaluate every miner's tier. Returns all promotions/demotions."""
        return [
            p for p in (self._evaluate_tier(perf) for perf in self._miners.values())
            if p is not None
        ]

    def get_performance(self, miner_uid: str) -> MinerPerformance | None:
        return self._miners.get(miner_uid)

    @property
    def all_miners(self) -> list[MinerPerformance]:
        return list(self._miners.values())

    @property
    def promotion_log(self) -> list[TierPromotion]:
        return list(self._promotion_log)

    def tier_distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {t.value: 0 for t in MinerTier}
        for p in self._miners.values():
            counts[p.current_tier.value] += 1
        return counts

    def summary(self) -> dict[str, Any]:
        return {
            "total_miners": len(self._miners),
            "tier_distribution": self.tier_distribution(),
            "total_promotions": sum(1 for p in self._promotion_log if p.is_promotion),
            "total_demotions": sum(1 for p in self._promotion_log if p.is_demotion),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evaluate_tier(self, perf: MinerPerformance) -> TierPromotion | None:
        """Compute the correct tier for a miner and promote/demote if needed."""
        target = self._compute_tier(perf)
        if target == perf.current_tier:
            return None

        old_tier = perf.current_tier
        perf.current_tier = target
        self._sync_registry(perf)

        event = TierPromotion(
            event_id=uuid.uuid4().hex[:8],
            miner_uid=perf.miner_uid,
            from_tier=old_tier,
            to_tier=target,
            reason=self._tier_reason(perf, target),
            occurred_at=time.time(),
        )
        self._promotion_log.append(event)
        return event

    def _compute_tier(self, perf: MinerPerformance) -> MinerTier:
        """Determine the highest tier the miner qualifies for."""
        reqs = TIER_REQUIREMENTS

        # Check from highest to lowest
        if (
            perf.judgments_validated >= reqs[MinerTier.ELDER]["min_validated"]
            and perf.reputation >= reqs[MinerTier.ELDER]["min_reputation"]
        ):
            return MinerTier.ELDER

        if (
            perf.judgments_validated >= reqs[MinerTier.MASTER]["min_validated"]
            and perf.reputation >= reqs[MinerTier.MASTER]["min_reputation"]
            and perf.is_domain_specialist
        ):
            return MinerTier.MASTER

        if (
            perf.judgments_validated >= reqs[MinerTier.JOURNEYMAN]["min_validated"]
            and perf.reputation >= reqs[MinerTier.JOURNEYMAN]["min_reputation"]
        ):
            return MinerTier.JOURNEYMAN

        return MinerTier.APPRENTICE

    def _tier_reason(self, perf: MinerPerformance, tier: MinerTier) -> str:
        return (
            f"validated={perf.judgments_validated}, "
            f"reputation={perf.reputation:.2f}, "
            f"domains={sorted(perf.domains)}"
        )

    def _sync_registry(self, perf: MinerPerformance) -> None:
        """Update CapabilityRegistry with tier-tagged capabilities."""
        self._registry.unregister(perf.miner_uid)
        tier_tag = f"tier:{perf.current_tier.value}"
        caps = [
            Capability(
                name="governance-judgment",
                domain=domain,
                tags=(tier_tag, f"specialization:{domain}"),
            )
            for domain in (perf.domains or {"general"})
        ]
        # Always include a generic capability
        caps.append(Capability(
            name="governance-judgment",
            domain="general",
            tags=(tier_tag,),
        ))
        self._registry.register(perf.miner_uid, caps)
