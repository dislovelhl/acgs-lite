"""Tests for spot_check auditing module.

Covers: sampling, re-validation, validator assessments, correct dissent,
lazy detection, bias detection, trust adjustments, and integration.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from acgs_lite.constitution.spot_check import (
    AuditPolicy,
    CompletedCase,
    SpotCheckAuditor,
    TrustAdjustment,
    ValidatorProfile,
)


def _ts() -> datetime:
    return datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)


def _make_auditor(sample_rate: float = 1.0) -> SpotCheckAuditor:
    """Create an auditor with 100% sample rate for deterministic testing."""
    return SpotCheckAuditor(AuditPolicy(sample_rate=sample_rate))


def _always_approve(case_id: str, sub_hash: str) -> str:
    return "approve"


def _always_reject(case_id: str, sub_hash: str) -> str:
    return "reject"


# ── Registration ─────────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_completed(self) -> None:
        auditor = _make_auditor()
        case = auditor.register_completed(
            case_id="c1",
            domain="finance",
            original_outcome="approved",
            validator_votes={"v1": "approve", "v2": "approve", "v3": "reject"},
            submission_hash="abc",
            _now=_ts(),
        )
        assert case.case_id == "c1"
        assert case.domain == "finance"
        assert not case.spot_checked

    def test_profiles_updated_on_registration(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "approve", "v3": "reject"},
            "abc", _now=_ts(),
        )

        p1 = auditor.profile("v1")
        assert p1 is not None
        assert p1.approve_count == 1
        assert p1.reject_count == 0

        p3 = auditor.profile("v3")
        assert p3 is not None
        assert p3.reject_count == 1


# ── Sampling ─────────────────────────────────────────────────────────────────


class TestSampling:
    def test_full_sample_rate(self) -> None:
        auditor = _make_auditor(sample_rate=1.0)
        auditor.register_completed("c1", "fin", "approved", {"v1": "approve"}, "a", _now=_ts())
        auditor.register_completed("c2", "fin", "approved", {"v1": "approve"}, "b", _now=_ts())

        sampled = auditor.sample_cases()
        assert len(sampled) == 2

    def test_zero_sample_rate(self) -> None:
        auditor = _make_auditor(sample_rate=0.0)
        auditor.register_completed("c1", "fin", "approved", {"v1": "approve"}, "a", _now=_ts())

        sampled = auditor.sample_cases()
        assert len(sampled) == 0

    def test_deterministic_sampling(self) -> None:
        auditor = _make_auditor(sample_rate=0.5)
        for i in range(20):
            auditor.register_completed(
                f"c{i}", "fin", "approved", {"v1": "approve"}, f"h{i}", _now=_ts()
            )

        s1 = auditor.sample_cases(_seed="test-seed-1")
        s2 = auditor.sample_cases(_seed="test-seed-1")
        assert s1 == s2

    def test_already_checked_excluded(self) -> None:
        auditor = _make_auditor(sample_rate=1.0)
        auditor.register_completed("c1", "fin", "approved", {"v1": "approve"}, "a", _now=_ts())

        # First sample
        s1 = auditor.sample_cases()
        assert "c1" in s1

        # Run the check
        auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())

        # Second sample should exclude already-checked
        s2 = auditor.sample_cases()
        assert "c1" not in s2


# ── Spot-check execution ────────────────────────────────────────────────────


class TestSpotCheck:
    def test_agreement(self) -> None:
        """Spot-check agrees with original: all majority validators are correct."""
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "approve", "v3": "reject"},
            "abc", _now=_ts(),
        )

        results = auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())
        assert len(results) == 1
        r = results[0]
        assert r.agrees_with_original is True
        assert r.spot_check_outcome == "approve"

        # v1, v2 should be "correct"; v3 should be "wrong_dissent"
        assessments = {a.validator_id: a for a in r.validator_assessments}
        assert assessments["v1"].assessment == "correct"
        assert assessments["v2"].assessment == "correct"
        assert assessments["v3"].assessment == "wrong_dissent"

    def test_disagreement_detects_lazy(self) -> None:
        """Spot-check disagrees: majority validators are flagged as lazy."""
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "approve", "v3": "reject"},
            "abc", _now=_ts(),
        )

        # Spot-check says reject → original approval was wrong
        results = auditor.run_spot_check(_always_reject, case_ids=["c1"], _now=_ts())
        r = results[0]
        assert r.agrees_with_original is False

        assessments = {a.validator_id: a for a in r.validator_assessments}
        # v1, v2 agreed with wrong majority → lazy
        assert assessments["v1"].assessment == "lazy_agree"
        assert assessments["v2"].assessment == "lazy_agree"
        # v3 disagreed with wrong majority → correct dissent!
        assert assessments["v3"].assessment == "correct_dissent"

    def test_correct_dissent_bonus(self) -> None:
        """Correct dissenters get the highest trust bonus."""
        policy = AuditPolicy(
            sample_rate=1.0,
            correct_reward=0.005,
            correct_dissent_bonus=0.05,
        )
        auditor = SpotCheckAuditor(policy)
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "approve", "v3": "reject"},
            "abc", _now=_ts(),
        )

        results = auditor.run_spot_check(_always_reject, case_ids=["c1"], _now=_ts())
        assessments = {a.validator_id: a for a in results[0].validator_assessments}

        # v3's correct dissent bonus should be much higher than v1's penalty
        assert assessments["v3"].trust_delta == 0.05
        assert assessments["v1"].trust_delta < 0  # lazy penalty

    def test_skip_already_checked(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed("c1", "fin", "approved", {"v1": "approve"}, "a", _now=_ts())

        auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())
        # Second run should skip
        results = auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())
        assert len(results) == 0

    def test_profiles_updated_after_check(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "reject"},
            "abc", _now=_ts(),
        )

        auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())

        p1 = auditor.profile("v1")
        assert p1.spot_check_correct == 1
        assert p1.spot_check_wrong == 0

        p2 = auditor.profile("v2")
        assert p2.spot_check_correct == 0
        assert p2.spot_check_wrong == 1


# ── Trust adjustments ────────────────────────────────────────────────────────


class TestTrustAdjustments:
    def test_compute_adjustments(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "approve", "v3": "reject"},
            "abc", _now=_ts(),
        )

        results = auditor.run_spot_check(_always_reject, case_ids=["c1"], _now=_ts())
        adjustments = auditor.compute_adjustments(results)

        adj_map = {a.validator_id: a for a in adjustments}
        assert adj_map["v1"].delta < 0  # lazy penalty
        assert adj_map["v3"].delta > 0  # correct dissent bonus
        assert adj_map["v3"].dissent_bonus_count == 1
        assert adj_map["v1"].lazy_count == 1

    def test_apply_adjustments_integration(self) -> None:
        from acgs_lite.constitution.trust_score import TrustConfig, TrustScoreManager

        trust_mgr = TrustScoreManager()
        trust_mgr.register("v1", TrustConfig(initial_score=0.9))
        trust_mgr.register("v2", TrustConfig(initial_score=0.9))
        trust_mgr.register("v3", TrustConfig(initial_score=0.9))

        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "approve", "v3": "reject"},
            "abc", _now=_ts(),
        )

        results = auditor.run_spot_check(_always_reject, case_ids=["c1"], _now=_ts())
        adjustments = auditor.compute_adjustments(results)
        applied = auditor.apply_adjustments(trust_mgr, adjustments, _now=_ts())

        assert applied > 0

        # v3 (correct dissent) should have higher score than v1 (lazy)
        s1 = trust_mgr.score("v1", _now=_ts())
        s3 = trust_mgr.score("v3", _now=_ts())
        assert s3 > s1

    def test_zero_delta_skipped(self) -> None:
        from acgs_lite.constitution.trust_score import TrustScoreManager

        trust_mgr = TrustScoreManager()

        # Create an adjustment with zero delta
        adjustments = [
            TrustAdjustment(
                validator_id="v1", domain="fin", delta=0.0,
                cases_checked=0, correct_count=0, lazy_count=0,
                dissent_bonus_count=0,
            )
        ]
        applied = SpotCheckAuditor().apply_adjustments(trust_mgr, adjustments, _now=_ts())
        assert applied == 0


# ── Bias detection ───────────────────────────────────────────────────────────


class TestBiasDetection:
    def test_no_bias_below_threshold(self) -> None:
        auditor = SpotCheckAuditor(AuditPolicy(min_cases_for_bias=5))

        # Only 3 cases → below threshold
        for i in range(3):
            auditor.register_completed(
                f"c{i}", "fin", "approved", {"v1": "approve"}, f"h{i}", _now=_ts()
            )

        assert len(auditor.biased_validators()) == 0

    def test_bias_detected(self) -> None:
        auditor = SpotCheckAuditor(AuditPolicy(
            min_cases_for_bias=5,
            bias_threshold=0.90,
        ))

        # v1 always approves across 10 cases
        for i in range(10):
            auditor.register_completed(
                f"c{i}", "fin", "approved", {"v1": "approve"}, f"h{i}", _now=_ts()
            )

        biased = auditor.biased_validators()
        assert len(biased) == 1
        assert biased[0]["validator_id"] == "v1"
        assert biased[0]["bias_direction"] == "approve"

    def test_mixed_votes_no_bias(self) -> None:
        auditor = SpotCheckAuditor(AuditPolicy(min_cases_for_bias=5, bias_threshold=0.90))

        for i in range(10):
            vote = "approve" if i % 2 == 0 else "reject"
            outcome = "approved" if i % 2 == 0 else "rejected"
            auditor.register_completed(
                f"c{i}", "fin", outcome, {"v1": vote}, f"h{i}", _now=_ts()
            )

        assert len(auditor.biased_validators()) == 0

    def test_profile_to_dict(self) -> None:
        p = ValidatorProfile(
            validator_id="v1",
            approve_count=8,
            reject_count=2,
        )
        d = p.to_dict()
        assert d["approve_rate"] == 0.8
        assert d["total_votes"] == 10


# ── Queries and summary ─────────────────────────────────────────────────────


class TestQueries:
    def test_unchecked_count(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed("c1", "fin", "approved", {"v1": "approve"}, "a", _now=_ts())
        auditor.register_completed("c2", "fin", "approved", {"v1": "approve"}, "b", _now=_ts())

        assert auditor.unchecked_count() == 2

        auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())
        assert auditor.unchecked_count() == 1

    def test_summary(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "reject"},
            "abc", _now=_ts(),
        )
        auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())

        s = auditor.summary()
        assert s["total_cases_registered"] == 1
        assert s["total_spot_checks"] == 1
        assert s["agreements"] == 1
        assert s["agreement_rate"] == 1.0

    def test_summary_with_disagreements(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve"},
            "abc", _now=_ts(),
        )
        auditor.run_spot_check(_always_reject, case_ids=["c1"], _now=_ts())

        s = auditor.summary()
        assert s["disagreements"] == 1
        assert s["lazy_validations_detected"] == 1

    def test_results_list(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed("c1", "fin", "approved", {"v1": "approve"}, "a", _now=_ts())
        auditor.run_spot_check(_always_approve, case_ids=["c1"], _now=_ts())

        assert len(auditor.results()) == 1

    def test_repr(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed("c1", "fin", "approved", {"v1": "approve"}, "a", _now=_ts())
        r = repr(auditor)
        assert "1 cases" in r
        assert "0 checked" in r


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_case_id_skipped(self) -> None:
        auditor = _make_auditor()
        results = auditor.run_spot_check(_always_approve, case_ids=["nonexistent"], _now=_ts())
        assert len(results) == 0

    def test_multiple_cases_multiple_validators(self) -> None:
        auditor = _make_auditor()
        auditor.register_completed(
            "c1", "fin", "approved",
            {"v1": "approve", "v2": "approve"},
            "a", _now=_ts(),
        )
        auditor.register_completed(
            "c2", "fin", "rejected",
            {"v1": "reject", "v3": "approve"},
            "b", _now=_ts(),
        )

        results = auditor.run_spot_check(_always_reject, case_ids=["c1", "c2"], _now=_ts())
        assert len(results) == 2

        adjustments = auditor.compute_adjustments(results)
        # v1 appears in both cases
        v1_adj = next(a for a in adjustments if a.validator_id == "v1")
        assert v1_adj.cases_checked == 2

    def test_empty_spot_check(self) -> None:
        auditor = _make_auditor()
        results = auditor.run_spot_check(_always_approve, _now=_ts())
        assert len(results) == 0

        adjustments = auditor.compute_adjustments(results)
        assert len(adjustments) == 0
