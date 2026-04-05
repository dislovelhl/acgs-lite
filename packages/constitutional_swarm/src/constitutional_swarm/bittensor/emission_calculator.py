"""Emission Calculator — TAO emission weight formula.

Implements the full emission formula from the roadmap economic model,
combining all five signal sources into a single normalized weight per miner:

  emission_weight(miner_i) = f(
      manifold_trust[i],          GovernanceManifold projected column sum
      reputation[i],              ConstitutionalMesh reputation score
      tier_multiplier[i],         MinerTier TAO bonus (1.0x - 4.0x)
      precedent_contribution[i],  PrecedentStore contribution count
      authenticity_score[i],      Average AuthenticityDetector score
  )

Formula (configurable weights, defaults sum to 1.0):
  raw_score = (
      w_trust         x normalize(manifold_trust)
    + w_reputation    x normalize(reputation)
    + w_tier          x normalize(tier_multiplier)
    + w_precedent     x normalize(precedent_contributions)
    + w_authenticity  x authenticity_score
  )
  emission_weight = normalize(raw_score) over all miners

Safeguards (matching GovernanceManifold guarantees):
  • Bounded influence: no miner exceeds max_weight_fraction (default 0.40)
  • Conservation: weights sum to exactly 1.0
  • Minimum floor: every registered miner gets at least min_weight_fraction
  • Tier hard gate: miners below minimum_tier get zero weight

Roadmap: 08-subnet-implementation-roadmap.md § Economic Model Integration
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constitutional_swarm.bittensor.protocol import TIER_TAO_MULTIPLIER, MinerTier

# ---------------------------------------------------------------------------
# Formula weights (configurable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmissionWeights:
    """Relative importance of each signal in the emission formula."""

    manifold_trust: float = 0.30
    reputation: float = 0.25
    tier: float = 0.20
    precedent: float = 0.15
    authenticity: float = 0.10

    def __post_init__(self) -> None:
        total = (
            self.manifold_trust + self.reputation + self.tier + self.precedent + self.authenticity
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"EmissionWeights must sum to 1.0, got {total:.6f}")


DEFAULT_EMISSION_WEIGHTS = EmissionWeights()


# ---------------------------------------------------------------------------
# Per-miner input snapshot
# ---------------------------------------------------------------------------


@dataclass
class MinerEmissionInput:
    """All signal inputs for one miner in one emission cycle."""

    miner_uid: str
    tier: MinerTier = MinerTier.APPRENTICE
    manifold_trust: float = 0.0  # from GovernanceManifold column sum
    reputation: float = 1.0  # from ConstitutionalMesh
    precedent_contributions: int = 0  # from PrecedentStore
    avg_authenticity: float = 0.0  # from AuthenticityDetector rolling avg
    is_active: bool = True  # inactive miners get zero weight


# ---------------------------------------------------------------------------
# Emission result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MinerEmission:
    """Computed emission for one miner."""

    miner_uid: str
    raw_score: float  # before normalization + clamping
    emission_weight: float  # final normalized weight (0.0 - 1.0)
    tier_multiplier: float
    was_floor_applied: bool
    was_cap_applied: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "miner_uid": self.miner_uid,
            "raw_score": round(self.raw_score, 6),
            "emission_weight": round(self.emission_weight, 6),
            "tier_multiplier": self.tier_multiplier,
            "was_floor_applied": self.was_floor_applied,
            "was_cap_applied": self.was_cap_applied,
        }


@dataclass
class EmissionCycle:
    """Full emission cycle result for all miners."""

    emissions: list[MinerEmission]
    total_miners: int
    active_miners: int
    weights: EmissionWeights

    @property
    def weight_sum(self) -> float:
        return sum(e.emission_weight for e in self.emissions)

    @property
    def max_weight(self) -> float:
        if not self.emissions:
            return 0.0
        return max(e.emission_weight for e in self.emissions)

    def top_k(self, k: int) -> list[MinerEmission]:
        return sorted(self.emissions, key=lambda e: e.emission_weight, reverse=True)[:k]

    def as_weight_dict(self) -> dict[str, float]:
        return {e.miner_uid: e.emission_weight for e in self.emissions}

    def summary(self) -> dict[str, Any]:
        return {
            "total_miners": self.total_miners,
            "active_miners": self.active_miners,
            "weight_sum": round(self.weight_sum, 9),
            "max_weight": round(self.max_weight, 6),
            "top_3": [
                {"miner": e.miner_uid, "weight": round(e.emission_weight, 6)} for e in self.top_k(3)
            ],
        }


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------


class EmissionCalculator:
    """Computes TAO emission weights for all subnet miners.

    Usage::

        calc = EmissionCalculator(
            weights=DEFAULT_EMISSION_WEIGHTS,
            min_weight_fraction=0.01,    # floor: 1% per active miner
            max_weight_fraction=0.40,    # cap:  40% per miner
            minimum_tier=MinerTier.APPRENTICE,
        )

        inputs = [
            MinerEmissionInput("miner-01", tier=MinerTier.MASTER,
                               manifold_trust=0.8, reputation=1.5,
                               precedent_contributions=12, avg_authenticity=0.73),
            MinerEmissionInput("miner-02", tier=MinerTier.JOURNEYMAN,
                               manifold_trust=0.5, reputation=1.2,
                               precedent_contributions=3, avg_authenticity=0.61),
        ]
        cycle = calc.compute(inputs)
        print(cycle.as_weight_dict())
        # {"miner-01": 0.65, "miner-02": 0.35} (normalized, sum=1.0)
    """

    def __init__(
        self,
        weights: EmissionWeights = DEFAULT_EMISSION_WEIGHTS,
        min_weight_fraction: float = 0.01,
        max_weight_fraction: float = 0.40,
        minimum_tier: MinerTier = MinerTier.APPRENTICE,
    ) -> None:
        self._weights = weights
        self._min_frac = min_weight_fraction
        self._max_frac = max_weight_fraction
        self._min_tier = minimum_tier
        self._min_tier_order = _TIER_ORDER[minimum_tier]

    def compute(self, inputs: list[MinerEmissionInput]) -> EmissionCycle:
        """Compute emission weights for all miners.

        Steps:
          1. Filter inactive + below-minimum-tier miners → zero weight
          2. Normalize each signal dimension to [0, 1]
          3. Apply formula weights → raw_score per miner
          4. Apply tier multiplier
          5. Normalize raw_scores → weights summing to 1.0
          6. Apply floor (min_weight_fraction x count) and cap (max_weight_fraction)
          7. Re-normalize after floor/cap adjustments

        Returns EmissionCycle with all MinerEmission records.
        """
        active = [
            inp for inp in inputs if inp.is_active and _TIER_ORDER[inp.tier] >= self._min_tier_order
        ]

        if not active:
            return EmissionCycle(
                emissions=[
                    MinerEmission(
                        miner_uid=inp.miner_uid,
                        raw_score=0.0,
                        emission_weight=0.0,
                        tier_multiplier=TIER_TAO_MULTIPLIER[inp.tier],
                        was_floor_applied=False,
                        was_cap_applied=False,
                    )
                    for inp in inputs
                ],
                total_miners=len(inputs),
                active_miners=0,
                weights=self._weights,
            )

        # --- Step 2: normalize each signal across active miners ---
        trust_vals = [inp.manifold_trust for inp in active]
        rep_vals = [inp.reputation for inp in active]
        prec_vals = [float(inp.precedent_contributions) for inp in active]
        auth_vals = [inp.avg_authenticity for inp in active]
        tier_vals = [TIER_TAO_MULTIPLIER[inp.tier] for inp in active]

        n_trust = _normalize_vec(trust_vals)
        n_rep = _normalize_vec(rep_vals)
        n_prec = _normalize_vec(prec_vals)
        n_auth = _normalize_vec(auth_vals)
        n_tier = _normalize_vec(tier_vals)

        # --- Step 3+4: raw score ---
        w = self._weights
        raw: list[float] = []
        for i, inp in enumerate(active):
            score = (
                w.manifold_trust * n_trust[i]
                + w.reputation * n_rep[i]
                + w.tier * n_tier[i]
                + w.precedent * n_prec[i]
                + w.authenticity * n_auth[i]
            )
            # Tier multiplier boosts relative score
            score *= TIER_TAO_MULTIPLIER[inp.tier]
            raw.append(score)

        # --- Step 5: normalize to sum 1.0 ---
        raw_weights = _safe_normalize(raw)

        # --- Step 6: floor and cap (iterative until stable) ---
        n = len(active)
        floor = self._min_frac / n if n > 0 else 0.0
        cap = self._max_frac
        final = _apply_floor_cap(raw_weights, floor, cap)

        # --- Build results ---
        emissions_active = []
        for i, inp in enumerate(active):
            emissions_active.append(
                MinerEmission(
                    miner_uid=inp.miner_uid,
                    raw_score=raw[i],
                    emission_weight=final[i],
                    tier_multiplier=TIER_TAO_MULTIPLIER[inp.tier],
                    was_floor_applied=(final[i] > raw_weights[i] and raw_weights[i] < floor + 1e-9),
                    was_cap_applied=(final[i] < raw_weights[i] - 1e-9),
                )
            )

        # Zero weight for inactive / below-tier miners
        active_uids = {inp.miner_uid for inp in active}
        inactive_emissions = [
            MinerEmission(
                miner_uid=inp.miner_uid,
                raw_score=0.0,
                emission_weight=0.0,
                tier_multiplier=TIER_TAO_MULTIPLIER[inp.tier],
                was_floor_applied=False,
                was_cap_applied=False,
            )
            for inp in inputs
            if inp.miner_uid not in active_uids
        ]

        return EmissionCycle(
            emissions=emissions_active + inactive_emissions,
            total_miners=len(inputs),
            active_miners=len(active),
            weights=self._weights,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TIER_ORDER: dict[MinerTier, int] = {
    MinerTier.APPRENTICE: 0,
    MinerTier.JOURNEYMAN: 1,
    MinerTier.MASTER: 2,
    MinerTier.ELDER: 3,
}


def _apply_floor_cap(
    weights: list[float],
    floor: float,
    cap: float,
    max_iter: int = 50,
) -> list[float]:
    """Apply floor and cap iteratively until all weights are within bounds.

    Algorithm:
      1. Clamp all weights to [floor, cap]
      2. Normalize to sum 1.0
      3. Repeat until no weights violate cap (bounded by max_iter)

    With iterative redistribution, the dominant miner's share is capped
    and the remainder is redistributed proportionally to other miners.
    """
    w = list(weights)
    for _ in range(max_iter):
        # Apply floor
        w = [max(floor, v) for v in w]
        total = sum(w)
        if total > 0:
            w = [v / total for v in w]

        # Check if anyone exceeds cap
        if not any(v > cap + 1e-9 for v in w):
            break

        # Cap and redistribute: locked miners stay at cap,
        # remaining budget flows to uncapped miners
        excess = sum(max(0.0, v - cap) for v in w)
        locked = [min(cap, v) for v in w]
        uncapped_sum = sum(v for v in locked if v < cap - 1e-9)

        if uncapped_sum <= 0:
            # All miners at cap — just clamp and normalize
            w = locked
            break

        # Redistribute excess proportionally to uncapped miners
        w = [v + excess * (v / uncapped_sum) if v < cap - 1e-9 else v for v in locked]

    # Final normalize
    return _safe_normalize(w)


def _normalize_vec(values: list[float]) -> list[float]:
    """Min-max normalize a list to [0, 1]. All-equal → uniform 0.5."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _safe_normalize(weights: list[float]) -> list[float]:
    """Normalize weights to sum 1.0. All-zero → uniform."""
    total = sum(weights)
    if total == 0:
        n = len(weights)
        return [1.0 / n] * n if n > 0 else []
    return [w / total for w in weights]
