"""Tests for claim_lifecycle module.

Covers: full lifecycle, MACI constraints, timeouts, re-queuing,
release, max claims, queries, and audit trail.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from acgs_lite.constitution.claim_lifecycle import (
    CaseConfig,
    CaseManager,
    CaseRecord,
    CaseState,
)


def _ts(minutes_offset: float = 0) -> datetime:
    """Helper: return a UTC datetime with optional minute offset."""
    return datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes_offset)


# ── Happy path ───────────────────────────────────────────────────────────────


class TestHappyPath:
    def test_full_lifecycle(self) -> None:
        mgr = CaseManager()
        t0 = _ts(0)

        cid = mgr.create("evaluate model", domain="finance", risk_tier="high", _now=t0)
        case = mgr.get(cid)
        assert case is not None
        assert case.state == CaseState.OPEN

        mgr.claim(cid, "miner-1", _now=_ts(5))
        assert mgr.get(cid).state == CaseState.CLAIMED  # type: ignore[union-attr]

        mgr.submit(cid, "miner-1", {"verdict": "safe"}, _now=_ts(10))
        assert mgr.get(cid).state == CaseState.SUBMITTED  # type: ignore[union-attr]

        mgr.begin_validation(cid, ["val-1", "val-2", "val-3"], _now=_ts(15))
        assert mgr.get(cid).state == CaseState.VALIDATING  # type: ignore[union-attr]

        mgr.finalize(cid, "approved", proof_hash="abc123", _now=_ts(20))
        case = mgr.get(cid)
        assert case.state == CaseState.FINALIZED  # type: ignore[union-attr]
        assert case.outcome == "approved"  # type: ignore[union-attr]
        assert case.proof_hash == "abc123"  # type: ignore[union-attr]

    def test_rejection_lifecycle(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("review action", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {"decision": "allow"}, _now=_ts(2))
        mgr.begin_validation(cid, ["v1", "v2", "v3"], _now=_ts(3))
        mgr.finalize(cid, "rejected", _now=_ts(4))
        assert mgr.get(cid).state == CaseState.REJECTED  # type: ignore[union-attr]

    def test_audit_trail(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))

        trail = mgr.transitions(cid)
        states = [(t.from_state, t.to_state) for t in trail]
        assert states == [
            ("", "open"),
            ("open", "claimed"),
            ("claimed", "submitted"),
        ]


# ── MACI constraints ────────────────────────────────────────────────────────


class TestMACIConstraints:
    def test_submitter_must_be_claimer(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "miner-1", _now=_ts(1))

        with pytest.raises(ValueError, match="MACI violation.*submitter.*not the claimer"):
            mgr.submit(cid, "miner-2", {"result": "x"}, _now=_ts(2))

    def test_producer_cannot_be_validator(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "miner-1", _now=_ts(1))
        mgr.submit(cid, "miner-1", {}, _now=_ts(2))

        with pytest.raises(ValueError, match="MACI violation.*producer.*cannot be"):
            mgr.begin_validation(cid, ["miner-1", "val-1", "val-2"], _now=_ts(3))

    def test_release_wrong_agent(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "miner-1", _now=_ts(1))

        with pytest.raises(ValueError, match="not the claimer"):
            mgr.release(cid, "miner-2", _now=_ts(2))


# ── Timeouts ─────────────────────────────────────────────────────────────────


class TestTimeouts:
    def test_claim_timeout_expires_case(self) -> None:
        config = CaseConfig(claim_timeout_minutes=10, auto_requeue_on_expiry=False)
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))

        # Try to claim after deadline
        with pytest.raises(ValueError, match="EXPIRED|OPEN"):
            mgr.claim(cid, "m1", _now=_ts(15))

    def test_submission_timeout(self) -> None:
        config = CaseConfig(
            submission_timeout_minutes=30,
            auto_requeue_on_expiry=False,
        )
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(5))

        # Submit after submission deadline
        with pytest.raises(ValueError, match="expired|CLAIMED"):
            mgr.submit(cid, "m1", {}, _now=_ts(40))

    def test_expire_stale_batch(self) -> None:
        config = CaseConfig(claim_timeout_minutes=10, auto_requeue_on_expiry=False)
        mgr = CaseManager(config)
        mgr.create("a", _now=_ts(0))
        mgr.create("b", _now=_ts(0))
        mgr.create("c", _now=_ts(5))

        expired = mgr.expire_stale(_now=_ts(12))
        # a and b should expire (created at t0, deadline t0+10)
        # c was created at t5, deadline t5+10 = t15, not yet expired
        assert len(expired) == 2

    def test_auto_requeue_on_expiry(self) -> None:
        config = CaseConfig(claim_timeout_minutes=10, auto_requeue_on_expiry=True)
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))

        mgr.expire_stale(_now=_ts(15))
        case = mgr.get(cid)
        # Should be back to OPEN after auto-requeue
        assert case.state == CaseState.OPEN  # type: ignore[union-attr]

    def test_validation_timeout(self) -> None:
        config = CaseConfig(
            validation_timeout_minutes=60,
            auto_requeue_on_expiry=True,
        )
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        mgr.begin_validation(cid, ["v1", "v2"], _now=_ts(3))

        mgr.expire_stale(_now=_ts(70))
        case = mgr.get(cid)
        # Expired and re-queued
        assert case.state == CaseState.OPEN  # type: ignore[union-attr]


# ── Max claims ───────────────────────────────────────────────────────────────


class TestMaxClaims:
    def test_max_claims_enforced(self) -> None:
        config = CaseConfig(max_claims=2, auto_requeue_on_expiry=False)
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))

        # Claim 1
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.release(cid, "m1", _now=_ts(2))

        # Claim 2
        mgr.claim(cid, "m2", _now=_ts(3))
        mgr.release(cid, "m2", _now=_ts(4))

        # Claim 3 should fail
        with pytest.raises(ValueError, match="max claims"):
            mgr.claim(cid, "m3", _now=_ts(5))

    def test_requeue_respects_max_claims(self) -> None:
        config = CaseConfig(max_claims=1, auto_requeue_on_expiry=False)
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        mgr.begin_validation(cid, ["v1"], _now=_ts(3))
        mgr.finalize(cid, "rejected", _now=_ts(4))

        with pytest.raises(ValueError, match="max claims"):
            mgr.requeue(cid, _now=_ts(5))


# ── Release ──────────────────────────────────────────────────────────────────


class TestRelease:
    def test_release_returns_to_open(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.release(cid, "m1", reason="Too complex", _now=_ts(2))

        case = mgr.get(cid)
        assert case.state == CaseState.OPEN  # type: ignore[union-attr]
        assert case.claimer_id == ""  # type: ignore[union-attr]

    def test_release_not_claimed_fails(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        with pytest.raises(ValueError, match="must be CLAIMED"):
            mgr.release(cid, "m1", _now=_ts(1))


# ── Requeue ──────────────────────────────────────────────────────────────────


class TestRequeue:
    def test_requeue_expired(self) -> None:
        config = CaseConfig(claim_timeout_minutes=10, auto_requeue_on_expiry=False)
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))
        mgr.expire_stale(_now=_ts(15))

        assert mgr.get(cid).state == CaseState.EXPIRED  # type: ignore[union-attr]
        mgr.requeue(cid, _now=_ts(16))
        assert mgr.get(cid).state == CaseState.OPEN  # type: ignore[union-attr]

    def test_requeue_rejected(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        mgr.begin_validation(cid, ["v1"], _now=_ts(3))
        mgr.finalize(cid, "rejected", _now=_ts(4))

        mgr.requeue(cid, _now=_ts(5))
        assert mgr.get(cid).state == CaseState.OPEN  # type: ignore[union-attr]

    def test_requeue_finalized_fails(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        mgr.begin_validation(cid, ["v1"], _now=_ts(3))
        mgr.finalize(cid, "approved", _now=_ts(4))

        with pytest.raises(ValueError, match="must be EXPIRED or REJECTED"):
            mgr.requeue(cid, _now=_ts(5))

    def test_auto_requeue_on_rejection(self) -> None:
        config = CaseConfig(auto_requeue_on_rejection=True)
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        mgr.begin_validation(cid, ["v1"], _now=_ts(3))
        mgr.finalize(cid, "rejected", _now=_ts(4))

        # Should auto-requeue
        assert mgr.get(cid).state == CaseState.OPEN  # type: ignore[union-attr]


# ── Invalid transitions ─────────────────────────────────────────────────────


class TestInvalidTransitions:
    def test_submit_without_claim(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        with pytest.raises(ValueError, match="must be CLAIMED"):
            mgr.submit(cid, "m1", {}, _now=_ts(1))

    def test_validate_without_submit(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        with pytest.raises(ValueError, match="must be SUBMITTED"):
            mgr.begin_validation(cid, ["v1"], _now=_ts(2))

    def test_finalize_without_validation(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        with pytest.raises(ValueError, match="must be VALIDATING"):
            mgr.finalize(cid, "approved", _now=_ts(3))

    def test_invalid_outcome(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        mgr.begin_validation(cid, ["v1"], _now=_ts(3))
        with pytest.raises(ValueError, match="must be 'approved' or 'rejected'"):
            mgr.finalize(cid, "maybe", _now=_ts(4))

    def test_empty_validators(self) -> None:
        mgr = CaseManager()
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.submit(cid, "m1", {}, _now=_ts(2))
        with pytest.raises(ValueError, match="(?i)at least one validator"):
            mgr.begin_validation(cid, [], _now=_ts(3))

    def test_case_not_found(self) -> None:
        mgr = CaseManager()
        with pytest.raises(KeyError, match="not found"):
            mgr.claim("nonexistent", "m1")

    def test_duplicate_case_id(self) -> None:
        mgr = CaseManager()
        mgr.create("test", case_id="dup-1", _now=_ts(0))
        with pytest.raises(ValueError, match="already exists"):
            mgr.create("test2", case_id="dup-1", _now=_ts(1))


# ── Queries ──────────────────────────────────────────────────────────────────


class TestQueries:
    def test_cases_by_state(self) -> None:
        mgr = CaseManager()
        mgr.create("a", _now=_ts(0))
        mgr.create("b", _now=_ts(0))
        cid_c = mgr.create("c", _now=_ts(0))
        mgr.claim(cid_c, "m1", _now=_ts(1))

        assert len(mgr.cases_by_state(CaseState.OPEN)) == 2
        assert len(mgr.cases_by_state(CaseState.CLAIMED)) == 1

    def test_open_cases_domain_filter(self) -> None:
        mgr = CaseManager()
        mgr.create("a", domain="finance", _now=_ts(0))
        mgr.create("b", domain="healthcare", _now=_ts(0))
        mgr.create("c", domain="finance", _now=_ts(0))

        assert len(mgr.open_cases(domain="finance")) == 2
        assert len(mgr.open_cases(domain="healthcare")) == 1

    def test_agent_active_cases(self) -> None:
        mgr = CaseManager()
        c1 = mgr.create("a", _now=_ts(0))
        c2 = mgr.create("b", _now=_ts(0))
        mgr.claim(c1, "m1", _now=_ts(1))
        mgr.claim(c2, "m1", _now=_ts(1))

        active = mgr.agent_active_cases("m1")
        assert len(active) == 2

    def test_claimable_excludes_max_claims(self) -> None:
        config = CaseConfig(max_claims=1, auto_requeue_on_expiry=False)
        mgr = CaseManager(config)
        cid = mgr.create("test", _now=_ts(0))
        mgr.claim(cid, "m1", _now=_ts(1))
        mgr.release(cid, "m1", _now=_ts(2))

        # Claim count is 1, max is 1 → not claimable
        assert cid not in mgr.claimable_cases("m2")

    def test_summary(self) -> None:
        mgr = CaseManager()
        mgr.create("a", domain="fin", _now=_ts(0))
        c2 = mgr.create("b", domain="fin", _now=_ts(0))
        mgr.claim(c2, "m1", _now=_ts(1))

        s = mgr.summary()
        assert s["total_cases"] == 2
        assert s["open_count"] == 1
        assert s["active_count"] == 1
        assert s["by_domain"]["fin"] == 2

    def test_repr(self) -> None:
        mgr = CaseManager()
        mgr.create("a", _now=_ts(0))
        r = repr(mgr)
        assert "1 cases" in r
        assert "1 open" in r
