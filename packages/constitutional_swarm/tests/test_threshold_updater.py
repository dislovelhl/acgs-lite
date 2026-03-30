"""Tests for BayesianThresholdUpdater — Phase 3.2."""

from __future__ import annotations

import pytest

from constitutional_swarm.bittensor.threshold_updater import (
    DEFAULT_WEIGHTS,
    BayesianThresholdUpdater,
    DimensionEvidence,
    WeightUpdate,
    _fill_defaults,
    _normalize,
)
from constitutional_swarm.bittensor.precedent_store import PrecedentRecord
from constitutional_swarm.bittensor.protocol import EscalationType


CONST_HASH = "608508a9bd224290"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    judgment: str = "Privacy takes precedence",
    impact_vector: dict | None = None,
    ambiguous: tuple[str, ...] = ("security",),
    grade: float = 0.91,
    case_id: str = "c1",
) -> PrecedentRecord:
    return PrecedentRecord.create(
        case_id=case_id,
        task_id="t1",
        miner_uid="miner-01",
        judgment=judgment,
        reasoning="Rationale",
        votes_for=3,
        votes_against=0,
        proof_root_hash="abc",
        escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
        impact_vector=impact_vector or {
            "safety": 0.1, "security": 0.8, "privacy": 0.2,
            "fairness": 0.1, "reliability": 0.1, "transparency": 0.1, "efficiency": 0.1,
        },
        constitutional_hash=CONST_HASH,
        ambiguous_dimensions=ambiguous,
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


class TestUtils:
    def test_normalize_sums_to_one(self):
        w = {"a": 2.0, "b": 3.0, "c": 5.0}
        n = _normalize(w)
        assert abs(sum(n.values()) - 1.0) < 1e-9

    def test_normalize_preserves_ratios(self):
        w = {"a": 1.0, "b": 2.0}
        n = _normalize(w)
        assert abs(n["b"] / n["a"] - 2.0) < 1e-9

    def test_normalize_zero_gives_uniform(self):
        w = {"a": 0.0, "b": 0.0}
        n = _normalize(w)
        assert abs(n["a"] - 0.5) < 1e-9

    def test_fill_defaults_fills_missing(self):
        w = {"safety": 0.50}
        filled = _fill_defaults(w)
        assert filled["security"] == DEFAULT_WEIGHTS["security"]
        assert filled["safety"] == 0.50

    def test_fill_defaults_all_present(self):
        filled = _fill_defaults({})
        assert set(filled.keys()) == set(DEFAULT_WEIGHTS.keys())


# ---------------------------------------------------------------------------
# DimensionEvidence
# ---------------------------------------------------------------------------


class TestDimensionEvidence:
    def test_observation_rate_empty(self):
        ev = DimensionEvidence("security", "", 0, 0.0, 0.0)
        assert ev.observation_rate == 0.5

    def test_observation_rate_all_confirmed(self):
        ev = DimensionEvidence("security", "", 10, 10.0, 0.0)
        assert ev.observation_rate == pytest.approx(1.0)

    def test_observation_rate_mixed(self):
        ev = DimensionEvidence("security", "", 10, 8.0, 2.0)
        assert ev.observation_rate == pytest.approx(0.8)

    def test_is_sufficient(self):
        ev = DimensionEvidence("security", "", 5, 3.0, 2.0)
        assert ev.is_sufficient is True

    def test_is_not_sufficient(self):
        ev = DimensionEvidence("security", "", 0, 0.0, 0.0)
        assert not ev.is_sufficient


# ---------------------------------------------------------------------------
# BayesianThresholdUpdater — evidence collection
# ---------------------------------------------------------------------------


class TestEvidenceCollection:
    def test_collect_empty_precedents(self):
        updater = BayesianThresholdUpdater()
        evidence = updater.collect_evidence([])
        assert len(evidence) == 7  # one per dimension
        for ev in evidence:
            assert ev.total_cases == 0

    def test_collect_single_precedent(self):
        updater = BayesianThresholdUpdater()
        rec = _make_record(
            impact_vector={
                "safety": 0.1, "security": 0.8, "privacy": 0.2,
                "fairness": 0.1, "reliability": 0.1,
                "transparency": 0.1, "efficiency": 0.1,
            },
            ambiguous=("security",),
            grade=0.9,
        )
        evidence = updater.collect_evidence([rec])
        sec = next(e for e in evidence if e.dimension == "security")
        assert sec.total_cases == 1
        # impact_vector["security"] = 0.8 >= 0.5 → confirmed
        # grade = votes_for/total = 3/3 = 1.0 (votes_for=3, votes_against=0)
        assert sec.confirmed_count == pytest.approx(1.0)
        assert sec.overblown_count == pytest.approx(0.0)

    def test_collect_confirmed_vs_overblown(self):
        updater = BayesianThresholdUpdater(confirmation_threshold=0.5)
        # Confirmed: security score = 0.8
        r1 = _make_record(
            case_id="c1",
            impact_vector={"security": 0.8, "safety": 0.1, "privacy": 0.1,
                           "fairness": 0.1, "reliability": 0.1,
                           "transparency": 0.1, "efficiency": 0.1},
            ambiguous=("security",), grade=1.0,
        )
        # Overblown: security score = 0.2
        r2 = _make_record(
            case_id="c2",
            impact_vector={"security": 0.2, "safety": 0.1, "privacy": 0.1,
                           "fairness": 0.1, "reliability": 0.1,
                           "transparency": 0.1, "efficiency": 0.1},
            ambiguous=("security",), grade=1.0,
        )
        evidence = updater.collect_evidence([r1, r2])
        sec = next(e for e in evidence if e.dimension == "security")
        assert sec.total_cases == 2
        assert sec.confirmed_count == pytest.approx(1.0)
        assert sec.overblown_count == pytest.approx(1.0)
        assert sec.observation_rate == pytest.approx(0.5)

    def test_collect_only_ambiguous_dims_counted(self):
        updater = BayesianThresholdUpdater()
        # security is ambiguous, but safety is NOT in ambiguous_dimensions
        rec = _make_record(
            impact_vector={"safety": 0.9, "security": 0.8, "privacy": 0.1,
                           "fairness": 0.1, "reliability": 0.1,
                           "transparency": 0.1, "efficiency": 0.1},
            ambiguous=("security",),  # safety NOT in ambiguous
        )
        evidence = updater.collect_evidence([rec])
        safety = next(e for e in evidence if e.dimension == "safety")
        assert safety.total_cases == 0  # not counted even though score is high


# ---------------------------------------------------------------------------
# BayesianThresholdUpdater — update cycle
# ---------------------------------------------------------------------------


class TestUpdateCycle:
    def test_update_no_evidence_unchanged(self):
        updater = BayesianThresholdUpdater(min_evidence_count=5)
        evidence = [DimensionEvidence(d, "", 0, 0.0, 0.0) for d in
                    ("safety", "security", "privacy", "fairness",
                     "reliability", "transparency", "efficiency")]
        cycle = updater.update(evidence, domain="test")
        # All zero evidence → no shifts
        for u in cycle.updates:
            assert abs(u.shift) < 1e-9

    def test_update_high_confirmation_increases_weight(self):
        """Q&A example: security 87% confirmed → weight increases."""
        updater = BayesianThresholdUpdater(
            max_shift_per_cycle=0.08,
            min_evidence_count=1,
        )
        # 87% observation rate for security
        evidence = []
        for dim in ("safety", "security", "privacy", "fairness",
                    "reliability", "transparency", "efficiency"):
            if dim == "security":
                evidence.append(DimensionEvidence(dim, "", 47, 41.0, 6.0))
            else:
                evidence.append(DimensionEvidence(dim, "", 0, 0.0, 0.0))

        cycle = updater.update(evidence, domain="healthcare")
        sec = next(u for u in cycle.updates if u.dimension == "security")

        # Expected shift: (0.872 - 0.5) × 0.08 ≈ 0.030
        assert sec.shift == pytest.approx(0.030, abs=0.005)
        assert sec.direction == "increased"
        assert sec.posterior > sec.prior

    def test_update_low_confirmation_decreases_weight(self):
        updater = BayesianThresholdUpdater(
            max_shift_per_cycle=0.08, min_evidence_count=1
        )
        evidence = []
        for dim in ("safety", "security", "privacy", "fairness",
                    "reliability", "transparency", "efficiency"):
            if dim == "privacy":
                # 20% confirmed → concern overblown
                evidence.append(DimensionEvidence(dim, "", 10, 2.0, 8.0))
            else:
                evidence.append(DimensionEvidence(dim, "", 0, 0.0, 0.0))

        cycle = updater.update(evidence, domain="")
        priv = next(u for u in cycle.updates if u.dimension == "privacy")
        assert priv.shift < 0
        assert priv.posterior < priv.prior

    def test_weights_normalized_after_update(self):
        updater = BayesianThresholdUpdater(min_evidence_count=1)
        evidence = [DimensionEvidence(d, "", 10, 8.0, 2.0)
                    for d in ("safety", "security", "privacy", "fairness",
                              "reliability", "transparency", "efficiency")]
        cycle = updater.update(evidence)
        total = sum(cycle.posterior_weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_max_shift_capped(self):
        updater = BayesianThresholdUpdater(
            max_shift_per_cycle=0.01, min_evidence_count=1
        )
        # 100% confirmed → raw_shift = (1.0 - 0.5) × 0.01 = 0.005 (not capped)
        # But if max_shift is very small, bigger obs rates get capped
        evidence = [DimensionEvidence("safety", "", 100, 100.0, 0.0)]
        for dim in ("security", "privacy", "fairness", "reliability",
                    "transparency", "efficiency"):
            evidence.append(DimensionEvidence(dim, "", 0, 0.0, 0.0))
        cycle = updater.update(evidence)
        safety = next(u for u in cycle.updates if u.dimension == "safety")
        assert abs(safety.shift) <= 0.01 + 1e-9

    def test_min_weight_floor_enforced(self):
        """Weight should never fall below _MIN_WEIGHT."""
        updater = BayesianThresholdUpdater(
            max_shift_per_cycle=1.0,  # huge shift
            min_evidence_count=1,
        )
        # 0% confirmed → drive weight to floor
        evidence = [DimensionEvidence("safety", "", 100, 0.0, 100.0)]
        for dim in ("security", "privacy", "fairness", "reliability",
                    "transparency", "efficiency"):
            evidence.append(DimensionEvidence(dim, "", 0, 0.0, 0.0))
        cycle = updater.update(evidence)
        safety = next(u for u in cycle.updates if u.dimension == "safety")
        from constitutional_swarm.bittensor.threshold_updater import _MIN_WEIGHT
        assert safety.posterior >= _MIN_WEIGHT

    def test_domain_isolated_weights(self):
        updater = BayesianThresholdUpdater(min_evidence_count=1)
        ev_high = [DimensionEvidence("security", "", 20, 18.0, 2.0)]
        ev_high += [DimensionEvidence(d, "", 0, 0.0, 0.0)
                    for d in ("safety", "privacy", "fairness", "reliability",
                              "transparency", "efficiency")]

        updater.update(ev_high, domain="healthcare")
        updater.update(
            [DimensionEvidence(d, "", 0, 0.0, 0.0)
             for d in ("safety", "security", "privacy", "fairness",
                       "reliability", "transparency", "efficiency")],
            domain="finance",
        )
        hc = updater.weights("healthcare")
        fi = updater.weights("finance")
        assert hc["security"] != fi["security"]

    def test_rollback(self):
        updater = BayesianThresholdUpdater(min_evidence_count=1)
        original = updater.weights("")
        ev = [DimensionEvidence("security", "", 20, 18.0, 2.0)]
        ev += [DimensionEvidence(d, "", 0, 0.0, 0.0)
               for d in ("safety", "privacy", "fairness", "reliability",
                         "transparency", "efficiency")]
        updater.update(ev)
        updater.rollback()
        after_rollback = updater.weights("")
        assert after_rollback == original

    def test_rollback_no_history_returns_false(self):
        updater = BayesianThresholdUpdater()
        assert updater.rollback("nonexistent-domain") is False

    def test_update_from_precedents_convenience(self):
        updater = BayesianThresholdUpdater(min_evidence_count=1)
        recs = [_make_record(case_id=f"c{i}") for i in range(5)]
        cycle = updater.update_from_precedents(recs)
        assert cycle is not None
        assert cycle.total_precedents_used >= 0

    def test_explanation_text_included(self):
        updater = BayesianThresholdUpdater(min_evidence_count=1)
        ev = [DimensionEvidence("security", "", 10, 8.0, 2.0)]
        ev += [DimensionEvidence(d, "", 0, 0.0, 0.0)
               for d in ("safety", "privacy", "fairness", "reliability",
                         "transparency", "efficiency")]
        cycle = updater.update(ev)
        sec = next(u for u in cycle.updates if u.dimension == "security")
        assert "security" in sec.explanation
        assert len(sec.explanation) > 10

    def test_summary(self):
        updater = BayesianThresholdUpdater()
        s = updater.summary()
        assert "cycles_run" in s
        assert "max_shift_per_cycle" in s
