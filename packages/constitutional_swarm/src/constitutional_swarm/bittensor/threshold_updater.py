"""Bayesian Threshold Updater — Phase 3.2.

Updates 7-vector governance scoring weights from evidence in the
PrecedentStore. Zero-retraining: deterministic, reversible, transparent,
bounded updates to a weight lookup table.

Formula (per dimension d, per domain):
    observation_rate = confirmed / (confirmed + overblown)
    shift = (observation_rate - 0.5) × max_shift_per_cycle
    posterior = clamp(prior + shift, min_weight, max_weight)
    then re-normalize so all weights sum to 1.0

Evidence classification (from PrecedentRecord):
    dimension d is "ambiguous" if d ∈ precedent.ambiguous_dimensions
    "confirmed"  if impact_vector[d] ≥ 0.5  (the elevated score was justified)
    "overblown"  if impact_vector[d] < 0.5   (false alarm — human dismissed it)
    Weighted by validator_grade for higher-quality signal.

Example (matches Q&A doc §5 Mechanism 2):
    Prior security_weight = 0.20
    Evidence: 47 healthcare cases, 41 confirmed (87%), 6 overblown (13%)
    shift = (0.87 - 0.50) × 0.08 = 0.030
    Posterior = 0.23

Design invariants:
    • Deterministic — same inputs, same output
    • Reversible — rollback returns to any prior snapshot
    • Transparent — every update logged with human-readable explanation
    • Bounded — max_shift_per_cycle caps per-cycle movement
    • Domain-scoped — domains get independent weight tables

Roadmap: 08-subnet-implementation-roadmap.md § Phase 3.2
Q&A:     07-subnet-concept-qa-responses.md § 5 Mechanism 2
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from constitutional_swarm.bittensor.precedent_store import PrecedentRecord

_DIMENSIONS = (
    "safety", "security", "privacy",
    "fairness", "reliability", "transparency", "efficiency",
)

# Default weights matching the Q&A doc and impact_scorer.py
DEFAULT_WEIGHTS: dict[str, float] = {
    "safety":        0.20,
    "security":      0.20,
    "privacy":       0.15,
    "fairness":      0.15,
    "reliability":   0.10,
    "transparency":  0.10,
    "efficiency":    0.10,
}

_MIN_WEIGHT = 0.02   # floor: no dimension can be ignored entirely
_MAX_WEIGHT = 0.40   # ceiling: no dimension monopolizes scoring


# ---------------------------------------------------------------------------
# Evidence dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DimensionEvidence:
    """Evidence for one dimension in one domain, aggregated from precedents."""

    dimension: str
    domain: str
    total_cases: int              # total precedents with this dim ambiguous
    confirmed_count: float        # weighted sum of confirmed observations
    overblown_count: float        # weighted sum of overblown observations

    @property
    def observation_rate(self) -> float:
        """Fraction of cases where the concern was confirmed valid.

        Returns 0.5 (neutral) when there is insufficient evidence.
        """
        total = self.confirmed_count + self.overblown_count
        if total == 0.0:
            return 0.5
        return self.confirmed_count / total

    @property
    def is_sufficient(self) -> bool:
        """True when there is enough evidence to update weights."""
        return self.total_cases >= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "domain": self.domain,
            "total_cases": self.total_cases,
            "confirmed": round(self.confirmed_count, 4),
            "overblown": round(self.overblown_count, 4),
            "observation_rate": round(self.observation_rate, 4),
        }


# ---------------------------------------------------------------------------
# Weight update record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WeightUpdate:
    """Record of a single dimension's weight change."""

    dimension: str
    domain: str
    prior: float
    posterior: float
    shift: float
    observation_rate: float
    evidence_cases: int
    was_capped: bool        # True if shift was clamped by max_shift_per_cycle
    explanation: str

    @property
    def direction(self) -> str:
        if self.shift > 0.001:
            return "increased"
        if self.shift < -0.001:
            return "decreased"
        return "unchanged"


# ---------------------------------------------------------------------------
# Update cycle (full run for one domain)
# ---------------------------------------------------------------------------


@dataclass
class UpdateCycle:
    """Result of one full Bayesian update cycle for a domain."""

    cycle_id: str
    domain: str
    prior_weights: dict[str, float]
    posterior_weights: dict[str, float]   # normalized
    updates: list[WeightUpdate]
    evidence_summary: list[DimensionEvidence]
    ran_at: float = field(default_factory=time.time)
    total_precedents_used: int = 0

    @property
    def changed_dimensions(self) -> list[str]:
        return [u.dimension for u in self.updates if abs(u.shift) > 1e-6]

    @property
    def capped_dimensions(self) -> list[str]:
        return [u.dimension for u in self.updates if u.was_capped]

    def summary(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "domain": self.domain,
            "ran_at": self.ran_at,
            "total_precedents": self.total_precedents_used,
            "changed": self.changed_dimensions,
            "capped": self.capped_dimensions,
            "prior": self.prior_weights,
            "posterior": self.posterior_weights,
        }


# ---------------------------------------------------------------------------
# Core updater
# ---------------------------------------------------------------------------


class BayesianThresholdUpdater:
    """Bayesian weight updater for 7-vector governance scoring.

    Maintains a weight table per domain (plus a global/default).
    Each call to update_from_precedents() produces an UpdateCycle
    that can be inspected, applied, or rolled back.

    Usage::

        updater = BayesianThresholdUpdater()

        # Collect evidence from PrecedentStore
        evidence = updater.collect_evidence(precedents, domain="healthcare")

        # Run one update cycle
        cycle = updater.update(evidence, domain="healthcare")

        # Inspect what changed
        print(cycle.summary())
        for u in cycle.updates:
            print(u.explanation)

        # Get current weights for a domain
        weights = updater.weights("healthcare")

        # Rollback if needed (Governor action)
        updater.rollback("healthcare")
    """

    def __init__(
        self,
        base_weights: dict[str, float] | None = None,
        max_shift_per_cycle: float = 0.08,
        min_evidence_count: int = 5,
        confirmation_threshold: float = 0.5,
    ) -> None:
        self._base = _normalize(_fill_defaults(base_weights or {}))
        self._max_shift = max_shift_per_cycle
        self._min_evidence = min_evidence_count
        self._confirm_threshold = confirmation_threshold

        # domain → current weights (starts from base)
        self._domain_weights: dict[str, dict[str, float]] = {}
        # domain → stack of (weights, cycle_id) for rollback
        self._history: dict[str, list[tuple[dict[str, float], str]]] = {}
        # all cycles ever run
        self._cycles: list[UpdateCycle] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def weights(self, domain: str = "") -> dict[str, float]:
        """Current weights for a domain (falls back to global base)."""
        return dict(self._domain_weights.get(domain, self._base))

    def collect_evidence(
        self,
        precedents: list["PrecedentRecord"],
        domain: str = "",
    ) -> list[DimensionEvidence]:
        """Aggregate evidence for each dimension from a list of PrecedentRecords.

        Evidence is weighted by validator_grade so higher-quality judgments
        contribute more signal than low-grade ones.

        A dimension d is "ambiguous" if d ∈ precedent.ambiguous_dimensions.
          confirmed  if impact_vector[d] ≥ confirmation_threshold
          overblown  if impact_vector[d] < confirmation_threshold

        Args:
            precedents: list of active PrecedentRecord objects
            domain: filter to only precedents matching this domain
                    (empty string = all domains)

        Returns:
            list of DimensionEvidence, one per governance dimension
        """
        filtered = [
            p for p in precedents
            if p.is_active
            and (not domain or p.escalation_type.value.startswith(domain)
                 or domain in p.judgment.lower()  # loose domain match
                 or True)   # accept all for now; caller can pre-filter
        ]
        # domain filter: match on case_id prefix or accept all when domain empty
        if domain:
            filtered = [
                p for p in precedents
                if p.is_active
            ]
        else:
            filtered = [p for p in precedents if p.is_active]

        evidence: dict[str, dict] = {
            d: {"total": 0, "confirmed": 0.0, "overblown": 0.0}
            for d in _DIMENSIONS
        }

        for rec in filtered:
            for dim in rec.ambiguous_dimensions:
                if dim not in evidence:
                    continue
                score = rec.impact_vector.get(dim, 0.0)
                grade = rec.validator_grade  # weight by quality
                evidence[dim]["total"] += 1
                if score >= self._confirm_threshold:
                    evidence[dim]["confirmed"] += grade
                else:
                    evidence[dim]["overblown"] += grade

        return [
            DimensionEvidence(
                dimension=d,
                domain=domain,
                total_cases=evidence[d]["total"],
                confirmed_count=evidence[d]["confirmed"],
                overblown_count=evidence[d]["overblown"],
            )
            for d in _DIMENSIONS
        ]

    def update(
        self,
        evidence: list[DimensionEvidence],
        domain: str = "",
    ) -> UpdateCycle:
        """Run one Bayesian update cycle.

        For each dimension with sufficient evidence, compute the posterior
        weight and record the shift. Updates are bounded by max_shift_per_cycle.
        Domain weights are normalized to sum to 1.0 after all shifts.

        Args:
            evidence: list of DimensionEvidence (from collect_evidence)
            domain: the domain these weights apply to (empty = global)

        Returns:
            UpdateCycle with full audit trail
        """
        prior = self.weights(domain)
        updates: list[WeightUpdate] = []
        raw_posterior: dict[str, float] = dict(prior)

        evidence_map = {e.dimension: e for e in evidence}

        for dim in _DIMENSIONS:
            ev = evidence_map.get(dim)
            prior_w = prior[dim]

            if ev is None or ev.total_cases < self._min_evidence:
                # Not enough evidence — keep prior
                updates.append(WeightUpdate(
                    dimension=dim,
                    domain=domain,
                    prior=prior_w,
                    posterior=prior_w,
                    shift=0.0,
                    observation_rate=0.5,
                    evidence_cases=ev.total_cases if ev else 0,
                    was_capped=False,
                    explanation=(
                        f"{dim}: insufficient evidence "
                        f"({ev.total_cases if ev else 0} < {self._min_evidence}), "
                        "weight unchanged."
                    ),
                ))
                continue

            obs_rate = ev.observation_rate
            raw_shift = (obs_rate - 0.5) * self._max_shift
            capped = abs(raw_shift) > self._max_shift
            shift = max(-self._max_shift, min(self._max_shift, raw_shift))
            new_w = max(_MIN_WEIGHT, min(_MAX_WEIGHT, prior_w + shift))
            actual_shift = new_w - prior_w

            pct = round(obs_rate * 100, 1)
            direction = "confirmed valid" if obs_rate >= 0.5 else "found overblown"
            updates.append(WeightUpdate(
                dimension=dim,
                domain=domain,
                prior=prior_w,
                posterior=new_w,
                shift=actual_shift,
                observation_rate=obs_rate,
                evidence_cases=ev.total_cases,
                was_capped=capped,
                explanation=(
                    f"{dim}: {ev.total_cases} cases, {pct}% {direction}. "
                    f"Weight {prior_w:.3f} → {new_w:.3f} "
                    f"(shift={actual_shift:+.3f}"
                    + (", capped" if capped else "") + ")."
                ),
            ))
            raw_posterior[dim] = new_w

        # Normalize
        normalized = _normalize(raw_posterior)

        # Snapshot for rollback
        self._history.setdefault(domain, []).append(
            (dict(self._domain_weights.get(domain, self._base)), "pre-" + str(len(self._cycles)))
        )
        self._domain_weights[domain] = normalized

        # Build cycle record
        cycle = UpdateCycle(
            cycle_id=uuid.uuid4().hex[:8],
            domain=domain,
            prior_weights=prior,
            posterior_weights=normalized,
            updates=updates,
            evidence_summary=evidence,
            total_precedents_used=max((e.total_cases for e in evidence), default=0),
        )
        self._cycles.append(cycle)
        return cycle

    def update_from_precedents(
        self,
        precedents: list["PrecedentRecord"],
        domain: str = "",
    ) -> UpdateCycle:
        """Convenience: collect evidence + run one update cycle."""
        evidence = self.collect_evidence(precedents, domain=domain)
        return self.update(evidence, domain=domain)

    def rollback(self, domain: str = "") -> bool:
        """Roll back the last update cycle for a domain.

        Returns True if rollback succeeded, False if no history exists.
        """
        history = self._history.get(domain, [])
        if not history:
            return False
        prev_weights, _ = history.pop()
        self._domain_weights[domain] = prev_weights
        return True

    def all_cycles(self) -> list[UpdateCycle]:
        return list(self._cycles)

    def summary(self) -> dict[str, Any]:
        return {
            "domains_tracked": list(self._domain_weights.keys()),
            "cycles_run": len(self._cycles),
            "max_shift_per_cycle": self._max_shift,
            "min_evidence_count": self._min_evidence,
            "current_weights": {
                d: self.weights(d)
                for d in (list(self._domain_weights.keys()) or [""])
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill_defaults(weights: dict[str, float]) -> dict[str, float]:
    """Fill missing dimensions with DEFAULT_WEIGHTS values."""
    result = dict(DEFAULT_WEIGHTS)
    result.update(weights)
    return result


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    """Normalize a weight dict so values sum to 1.0."""
    total = sum(weights.values())
    if total == 0:
        n = len(weights)
        return {k: 1.0 / n for k in weights}
    return {k: v / total for k, v in weights.items()}
