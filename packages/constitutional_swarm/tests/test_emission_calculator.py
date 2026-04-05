"""Tests for EmissionCalculator — TAO emission weight formula."""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.emission_calculator import (
    DEFAULT_EMISSION_WEIGHTS,
    EmissionCalculator,
    EmissionCycle,
    EmissionWeights,
    MinerEmissionInput,
    _normalize_vec,
    _safe_normalize,
)
from constitutional_swarm.bittensor.protocol import MinerTier

# ---------------------------------------------------------------------------
# EmissionWeights
# ---------------------------------------------------------------------------


class TestEmissionWeights:
    def test_default_sums_to_one(self):
        w = DEFAULT_EMISSION_WEIGHTS
        total = w.manifold_trust + w.reputation + w.tier + w.precedent + w.authenticity
        assert abs(total - 1.0) < 1e-9

    def test_invalid_weights_raise(self):
        with pytest.raises(ValueError, match=r"sum to 1\.0"):
            EmissionWeights(
                manifold_trust=0.5, reputation=0.5, tier=0.5,
                precedent=0.5, authenticity=0.5,
            )

    def test_custom_valid_weights(self):
        w = EmissionWeights(0.40, 0.30, 0.15, 0.10, 0.05)
        total = w.manifold_trust + w.reputation + w.tier + w.precedent + w.authenticity
        assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_normalize_vec_range(self):
        result = _normalize_vec([1.0, 2.0, 3.0])
        assert result[0] == pytest.approx(0.0)
        assert result[2] == pytest.approx(1.0)

    def test_normalize_vec_all_equal(self):
        result = _normalize_vec([5.0, 5.0, 5.0])
        assert all(v == pytest.approx(0.5) for v in result)

    def test_normalize_vec_empty(self):
        assert _normalize_vec([]) == []

    def test_safe_normalize_sums_to_one(self):
        result = _safe_normalize([1.0, 2.0, 3.0])
        assert abs(sum(result) - 1.0) < 1e-9

    def test_safe_normalize_all_zero(self):
        result = _safe_normalize([0.0, 0.0, 0.0])
        assert all(v == pytest.approx(1 / 3) for v in result)

    def test_safe_normalize_empty(self):
        assert _safe_normalize([]) == []


# ---------------------------------------------------------------------------
# EmissionCalculator — basic cases
# ---------------------------------------------------------------------------


class TestEmissionCalculatorBasic:
    def test_empty_inputs_returns_empty_active(self):
        calc = EmissionCalculator()
        cycle = calc.compute([])
        assert cycle.active_miners == 0

    def test_single_miner_gets_full_weight(self):
        calc = EmissionCalculator()
        inputs = [MinerEmissionInput("m1", tier=MinerTier.MASTER,
                                    manifold_trust=0.8, reputation=1.5,
                                    avg_authenticity=0.7)]
        cycle = calc.compute(inputs)
        assert len(cycle.emissions) == 1
        assert cycle.emissions[0].emission_weight == pytest.approx(1.0)

    def test_weights_sum_to_one(self):
        calc = EmissionCalculator()
        inputs = [
            MinerEmissionInput(f"m{i}", tier=MinerTier.JOURNEYMAN,
                               manifold_trust=float(i) * 0.1,
                               reputation=1.2 + i * 0.1)
            for i in range(5)
        ]
        cycle = calc.compute(inputs)
        active_weights = sum(
            e.emission_weight for e in cycle.emissions if e.miner_uid.startswith("m")
        )
        # Should sum to 1.0 (all are active)
        assert abs(active_weights - 1.0) < 1e-6

    def test_inactive_miner_gets_zero_weight(self):
        calc = EmissionCalculator()
        inputs = [
            MinerEmissionInput("active", tier=MinerTier.JOURNEYMAN,
                               manifold_trust=0.8, is_active=True),
            MinerEmissionInput("inactive", tier=MinerTier.MASTER,
                               manifold_trust=0.9, is_active=False),
        ]
        cycle = calc.compute(inputs)
        inactive = next(e for e in cycle.emissions if e.miner_uid == "inactive")
        assert inactive.emission_weight == 0.0

    def test_below_min_tier_gets_zero_weight(self):
        calc = EmissionCalculator(minimum_tier=MinerTier.JOURNEYMAN)
        inputs = [
            MinerEmissionInput("apprentice", tier=MinerTier.APPRENTICE,
                               manifold_trust=0.9),
            MinerEmissionInput("journeyman", tier=MinerTier.JOURNEYMAN,
                               manifold_trust=0.5),
        ]
        cycle = calc.compute(inputs)
        appr = next(e for e in cycle.emissions if e.miner_uid == "apprentice")
        jour = next(e for e in cycle.emissions if e.miner_uid == "journeyman")
        assert appr.emission_weight == 0.0
        assert jour.emission_weight == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# EmissionCalculator — ordering and tier multiplier
# ---------------------------------------------------------------------------


class TestEmissionOrdering:
    def test_higher_tier_gets_more_weight(self):
        """Master should earn more than Apprentice with identical other signals.

        Need ≥3 miners so the 40% cap doesn't force equality between the two
        extreme tiers (master can hold ~40%, apprentice gets much less).
        """
        calc = EmissionCalculator()
        inputs = [
            MinerEmissionInput("master", tier=MinerTier.MASTER,
                               manifold_trust=0.5, reputation=1.5,
                               avg_authenticity=0.7),
            MinerEmissionInput("apprentice", tier=MinerTier.APPRENTICE,
                               manifold_trust=0.5, reputation=1.5,
                               avg_authenticity=0.7),
            # Filler miners absorb cap redistribution without swamping the result
            MinerEmissionInput("filler-a", tier=MinerTier.JOURNEYMAN,
                               manifold_trust=0.5, reputation=1.3, avg_authenticity=0.7),
            MinerEmissionInput("filler-b", tier=MinerTier.JOURNEYMAN,
                               manifold_trust=0.5, reputation=1.3, avg_authenticity=0.7),
        ]
        cycle = calc.compute(inputs)
        master_w = next(e.emission_weight for e in cycle.emissions if e.miner_uid == "master")
        appr_w   = next(e.emission_weight for e in cycle.emissions if e.miner_uid == "apprentice")
        assert master_w > appr_w

    def test_more_precedents_more_weight(self):
        """More precedents = higher weight (other signals equal)."""
        calc = EmissionCalculator()
        inputs = [
            MinerEmissionInput("high", tier=MinerTier.MASTER,
                               manifold_trust=0.6, reputation=1.5,
                               precedent_contributions=50, avg_authenticity=0.7),
            MinerEmissionInput("low", tier=MinerTier.MASTER,
                               manifold_trust=0.6, reputation=1.5,
                               precedent_contributions=0, avg_authenticity=0.7),
        ]
        cycle = calc.compute(inputs)
        high_w = next(e.emission_weight for e in cycle.emissions if e.miner_uid == "high")
        low_w  = next(e.emission_weight for e in cycle.emissions if e.miner_uid == "low")
        assert high_w >= low_w

    def test_tier_multiplier_recorded(self):
        calc = EmissionCalculator()
        inputs = [MinerEmissionInput("m", tier=MinerTier.ELDER)]
        cycle = calc.compute(inputs)
        assert cycle.emissions[0].tier_multiplier == 4.0


# ---------------------------------------------------------------------------
# EmissionCalculator — floor and cap
# ---------------------------------------------------------------------------


class TestFloorAndCap:
    def test_max_weight_cap_respected(self):
        calc = EmissionCalculator(max_weight_fraction=0.40)
        # One dominant miner with all signals maxed
        inputs = [
            MinerEmissionInput("dominant", tier=MinerTier.ELDER,
                               manifold_trust=1.0, reputation=2.0,
                               precedent_contributions=1000, avg_authenticity=1.0),
        ] + [
            MinerEmissionInput(f"weak-{i}", tier=MinerTier.APPRENTICE,
                               manifold_trust=0.01, reputation=1.0)
            for i in range(5)
        ]
        cycle = calc.compute(inputs)
        dominant = next(e for e in cycle.emissions if e.miner_uid == "dominant")
        assert dominant.emission_weight <= 0.40 + 1e-9

    def test_floor_applied_to_small_miners(self):
        calc = EmissionCalculator(min_weight_fraction=0.10)
        inputs = [
            MinerEmissionInput("big", tier=MinerTier.ELDER,
                               manifold_trust=1.0, reputation=2.0,
                               precedent_contributions=500),
            MinerEmissionInput("tiny", tier=MinerTier.APPRENTICE,
                               manifold_trust=0.001, reputation=1.0),
        ]
        cycle = calc.compute(inputs)
        tiny = next(e for e in cycle.emissions if e.miner_uid == "tiny")
        # Floor = 0.10 / 2 miners = 5%; tiny should get at least something above raw
        assert tiny.emission_weight > 0.0


# ---------------------------------------------------------------------------
# EmissionCycle helpers
# ---------------------------------------------------------------------------


class TestEmissionCycle:
    def _cycle(self) -> EmissionCycle:
        calc = EmissionCalculator()
        inputs = [
            MinerEmissionInput(f"m{i}", tier=MinerTier.JOURNEYMAN,
                               manifold_trust=float(i) * 0.2,
                               reputation=1.2)
            for i in range(5)
        ]
        return calc.compute(inputs)

    def test_top_k(self):
        cycle = self._cycle()
        top2 = cycle.top_k(2)
        assert len(top2) == 2
        assert top2[0].emission_weight >= top2[1].emission_weight

    def test_as_weight_dict(self):
        cycle = self._cycle()
        d = cycle.as_weight_dict()
        assert len(d) == 5
        assert abs(sum(d.values()) - 1.0) < 1e-6

    def test_summary_structure(self):
        cycle = self._cycle()
        s = cycle.summary()
        assert "active_miners" in s
        assert "weight_sum" in s
        assert "top_3" in s
        assert abs(s["weight_sum"] - 1.0) < 1e-6

    def test_max_weight(self):
        calc = EmissionCalculator()
        inputs = [MinerEmissionInput("m", tier=MinerTier.MASTER)]
        cycle = calc.compute(inputs)
        assert cycle.max_weight == pytest.approx(1.0)
