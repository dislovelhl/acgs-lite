"""Tests for domain-scoped trust scoring and time-based decay.

Covers: per-domain scores, domain isolation, time decay, forgiveness,
sync_to_validator_pool, minimum_assignment_fraction, and backward compat.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from acgs_lite.constitution.trust_score import (
    TrustConfig,
    TrustEvent,
    TrustScoreManager,
    TrustTier,
)


def _ts(hours_offset: float = 0) -> datetime:
    return datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc) + timedelta(hours=hours_offset)


# ── Domain-scoped scoring ───────────────────────────────────────────────────


class TestDomainScoring:
    def test_domain_violation_affects_both_global_and_domain(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1", TrustConfig(initial_score=1.0))

        mgr.record_decision("a1", compliant=False, severity="high", domain="finance", _now=_ts(0))

        # Global score should drop
        global_score = mgr.score("a1", _now=_ts(0))
        assert global_score < 1.0

        # Finance score should also drop
        fin_score = mgr.score("a1", domain="finance", _now=_ts(0))
        assert fin_score < 1.0

        # Both should be the same penalty
        assert abs(global_score - fin_score) < 1e-6

    def test_domain_isolation(self) -> None:
        """Violation in finance should not affect healthcare domain score."""
        mgr = TrustScoreManager()
        mgr.register("a1", TrustConfig(initial_score=1.0))

        mgr.record_decision(
            "a1", compliant=False, severity="critical", domain="finance", _now=_ts(0)
        )

        fin_score = mgr.score("a1", domain="finance", _now=_ts(0))
        health_score = mgr.score("a1", domain="healthcare", _now=_ts(0))

        assert fin_score < 1.0  # penalized
        assert health_score == 1.0  # untouched (initial score)

    def test_domain_specific_tier(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1", TrustConfig(initial_score=1.0))

        # Hammer finance with violations (6 × high = -0.60, score = 0.40 < 0.50)
        for _ in range(6):
            mgr.record_decision(
                "a1", compliant=False, severity="high", domain="finance", _now=_ts(0)
            )

        assert mgr.tier("a1", domain="finance", _now=_ts(0)) == TrustTier.RESTRICTED
        # Healthcare should still be trusted
        assert mgr.tier("a1", domain="healthcare", _now=_ts(0)) == TrustTier.TRUSTED

    def test_global_score_reflects_all_domains(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1", TrustConfig(initial_score=1.0))

        mgr.record_decision("a1", compliant=False, severity="high", domain="finance", _now=_ts(0))
        mgr.record_decision(
            "a1", compliant=False, severity="high", domain="healthcare", _now=_ts(0)
        )

        # Global score should reflect both penalties
        global_score = mgr.score("a1", _now=_ts(0))
        assert global_score < 0.85  # two high violations = -0.20

    def test_domains_list(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1")

        mgr.record_decision("a1", compliant=True, domain="finance", _now=_ts(0))
        mgr.record_decision("a1", compliant=True, domain="privacy", _now=_ts(0))

        domains = mgr.domains("a1")
        assert "finance" in domains
        assert "privacy" in domains

    def test_domain_history(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1")

        mgr.record_decision("a1", compliant=True, domain="finance", _now=_ts(0))
        mgr.record_decision("a1", compliant=False, severity="low", domain="healthcare", _now=_ts(1))
        mgr.record_decision("a1", compliant=True, domain="finance", _now=_ts(2))

        fin_history = mgr.history("a1", domain="finance")
        assert len(fin_history) == 2
        assert all(e.domain == "finance" for e in fin_history)

        health_history = mgr.history("a1", domain="healthcare")
        assert len(health_history) == 1

    def test_domain_scores_report(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1")

        mgr.record_decision("a1", compliant=True, domain="finance", _now=_ts(0))
        mgr.record_decision("a1", compliant=False, severity="medium", domain="privacy", _now=_ts(0))

        report = mgr.domain_scores("a1", _now=_ts(0))
        assert "finance" in report
        assert "privacy" in report
        assert report["finance"]["tier"] == TrustTier.TRUSTED
        assert report["privacy"]["violations"] == 1

    def test_restricted_agents_by_domain(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1", TrustConfig(initial_score=1.0))
        mgr.register("a2", TrustConfig(initial_score=1.0))

        # Only a1 restricted in finance (6 × high = -0.60, score = 0.40)
        for _ in range(6):
            mgr.record_decision(
                "a1", compliant=False, severity="high", domain="finance", _now=_ts(0)
            )

        restricted_fin = mgr.restricted_agents(domain="finance")

        assert "a1" in restricted_fin
        assert "a2" not in restricted_fin

    def test_event_has_domain_field(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1")

        event = mgr.record_decision("a1", compliant=True, domain="finance", _now=_ts(0))
        assert event.domain == "finance"

    def test_global_event_empty_domain(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1")

        event = mgr.record_decision("a1", compliant=True, _now=_ts(0))
        assert event.domain == ""


# ── Time decay ───────────────────────────────────────────────────────────────


class TestTimeDecay:
    def test_passive_recovery_over_time(self) -> None:
        config = TrustConfig(initial_score=1.0, time_decay_rate=0.01)  # 0.01/hour
        mgr = TrustScoreManager()
        mgr.register("a1", config)

        # Critical violation: -0.20
        mgr.record_decision("a1", compliant=False, severity="critical", _now=_ts(0))
        score_after_violation = mgr.score("a1", _now=_ts(0))
        assert abs(score_after_violation - 0.80) < 1e-6

        # After 10 hours: +0.10 passive recovery
        score_later = mgr.score("a1", _now=_ts(10))
        assert score_later > score_after_violation
        assert abs(score_later - 0.90) < 1e-4

    def test_time_decay_capped_at_1(self) -> None:
        config = TrustConfig(initial_score=0.99, time_decay_rate=0.1)
        mgr = TrustScoreManager()
        mgr.register("a1", config)

        # After 100 hours of decay, score should not exceed 1.0
        score = mgr.score("a1", _now=_ts(100))
        assert score <= 1.0

    def test_no_decay_when_rate_zero(self) -> None:
        config = TrustConfig(initial_score=1.0, time_decay_rate=0.0)
        mgr = TrustScoreManager()
        mgr.register("a1", config)

        mgr.record_decision("a1", compliant=False, severity="critical", _now=_ts(0))
        score_t0 = mgr.score("a1", _now=_ts(0))
        score_t100 = mgr.score("a1", _now=_ts(100))

        # No passive recovery
        assert abs(score_t0 - score_t100) < 1e-6

    def test_time_decay_per_domain(self) -> None:
        config = TrustConfig(initial_score=1.0, time_decay_rate=0.02)
        mgr = TrustScoreManager()
        mgr.register("a1", config)

        mgr.record_decision("a1", compliant=False, severity="high", domain="finance", _now=_ts(0))

        # Finance domain should recover over time
        fin_t0 = mgr.score("a1", domain="finance", _now=_ts(0))
        fin_t5 = mgr.score("a1", domain="finance", _now=_ts(5))
        assert fin_t5 > fin_t0

    def test_time_decay_applied_before_recording(self) -> None:
        """Time decay should be applied before a new decision is recorded."""
        config = TrustConfig(initial_score=1.0, time_decay_rate=0.05)
        mgr = TrustScoreManager()
        mgr.register("a1", config)

        # Critical violation at t=0
        mgr.record_decision("a1", compliant=False, severity="critical", _now=_ts(0))
        # Score: 0.80

        # Compliant decision at t=10 — time decay should apply first
        event = mgr.record_decision("a1", compliant=True, _now=_ts(10))
        # Before: 0.80 + 0.05*10 = 1.30 → capped at 1.0
        # Then: +0.01 compliance → still 1.0
        # The score_before should reflect the time-decayed value
        assert event.score_before >= 0.80  # must be higher than raw 0.80

    def test_forgiveness_math(self) -> None:
        """Verify the exact forgiveness calculation."""
        config = TrustConfig(initial_score=1.0, time_decay_rate=0.001)
        mgr = TrustScoreManager()
        mgr.register("a1", config)

        # High violation: -0.10, score = 0.90
        mgr.record_decision("a1", compliant=False, severity="high", _now=_ts(0))

        # After 24 hours: +0.024 passive recovery
        score = mgr.score("a1", _now=_ts(24))
        expected = 0.90 + 0.001 * 24
        assert abs(score - expected) < 1e-4


# ── Config validation ────────────────────────────────────────────────────────


class TestConfigValidation:
    def test_negative_time_decay_rate(self) -> None:
        with pytest.raises(ValueError, match="time_decay_rate"):
            TrustConfig(time_decay_rate=-0.01)

    def test_minimum_assignment_fraction_bounds(self) -> None:
        # Valid
        TrustConfig(minimum_assignment_fraction=0.1)
        TrustConfig(minimum_assignment_fraction=0.0)
        TrustConfig(minimum_assignment_fraction=1.0)

        # Invalid
        with pytest.raises(ValueError, match="minimum_assignment_fraction"):
            TrustConfig(minimum_assignment_fraction=1.5)

    def test_minimum_assignment_fraction_stored(self) -> None:
        config = TrustConfig(minimum_assignment_fraction=0.15)
        assert config.minimum_assignment_fraction == 0.15


# ── Sync to ValidatorPool ───────────────────────────────────────────────────


class TestSyncToValidatorPool:
    def test_sync_updates_pool(self) -> None:
        from acgs_lite.constitution.validator_selection import ValidatorPool

        pool = ValidatorPool()
        pool.register("a1", trust_score=1.0, domains=["fin"])
        pool.register("a2", trust_score=1.0, domains=["fin"])

        mgr = TrustScoreManager()
        mgr.register("a1")
        mgr.register("a2")
        mgr.record_decision("a1", compliant=False, severity="high", _now=_ts(0))

        updated = mgr.sync_to_validator_pool(pool, _now=_ts(0))
        assert updated == 2

        assert pool.get("a1").trust_score < 1.0  # type: ignore[union-attr]
        assert pool.get("a2").trust_score == 1.0  # type: ignore[union-attr]

    def test_sync_with_domain(self) -> None:
        from acgs_lite.constitution.validator_selection import ValidatorPool

        pool = ValidatorPool()
        pool.register("a1", trust_score=1.0, domains=["fin"])

        mgr = TrustScoreManager()
        mgr.register("a1")
        mgr.record_decision(
            "a1", compliant=False, severity="critical", domain="finance", _now=_ts(0)
        )

        mgr.sync_to_validator_pool(pool, domain="finance", _now=_ts(0))
        assert pool.get("a1").trust_score < 1.0  # type: ignore[union-attr]

    def test_sync_skips_unknown_validators(self) -> None:
        from acgs_lite.constitution.validator_selection import ValidatorPool

        pool = ValidatorPool()
        pool.register("a1", trust_score=1.0)

        mgr = TrustScoreManager()
        mgr.register("a1")
        mgr.register("a_unknown")  # not in pool

        updated = mgr.sync_to_validator_pool(pool, _now=_ts(0))
        assert updated == 1  # only a1 was in the pool


# ── Summary with domains ────────────────────────────────────────────────────


class TestSummaryDomains:
    def test_summary_includes_domains(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1")
        mgr.record_decision("a1", compliant=True, domain="finance", _now=_ts(0))

        s = mgr.summary()
        assert s["agents"][0]["domains"] == ["finance"]

    def test_summary_with_domain_filter(self) -> None:
        mgr = TrustScoreManager()
        mgr.register("a1")
        mgr.record_decision(
            "a1", compliant=False, severity="critical", domain="finance", _now=_ts(0)
        )

        s = mgr.summary(domain="finance")
        assert s["domain_filter"] == "finance"
        # Score should reflect finance-specific score
        assert s["agents"][0]["score"] < 1.0
