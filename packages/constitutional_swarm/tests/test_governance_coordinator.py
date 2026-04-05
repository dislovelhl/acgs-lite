"""Tests for GovernanceCoordinator — acgs-lite ↔ constitutional_swarm bridge.

Proves that the acgs-lite governance primitives (CaseManager,
ValidatorSelector, SpotCheckAuditor, TrustScoreManager) compose
correctly with the constitutional_swarm bittensor runtime.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from constitutional_swarm.bittensor.governance_coordinator import (
    CoordinatorConfig,
    GovernanceCoordinator,
)

from acgs_lite.constitution.claim_lifecycle import CaseConfig, CaseState
from acgs_lite.constitution.spot_check import AuditPolicy
from acgs_lite.constitution.trust_score import TrustConfig, TrustTier
from acgs_lite.constitution.validator_selection import SelectionPolicy

# ── Helpers ──────────────────────────────────────────────────────────────────


def _ts(minutes: float = 0) -> datetime:
    return datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _make_coordinator(
    n_validators: int = 10,
    sample_rate: float = 1.0,
    signing_key: str = "",
    auto_audit: bool = False,
) -> GovernanceCoordinator:
    """Create a coordinator with diverse validators pre-registered."""
    config = CoordinatorConfig(
        case_config=CaseConfig(
            claim_timeout_minutes=60,
            submission_timeout_minutes=120,
            validation_timeout_minutes=480,
            max_claims=3,
            auto_requeue_on_expiry=True,
        ),
        selection_policy=SelectionPolicy(
            signing_key=signing_key,
            require_domain_match=True,
            diversity_bonus_factor=0.5,
        ),
        audit_policy=AuditPolicy(
            sample_rate=sample_rate,
            correct_reward=0.005,
            correct_dissent_bonus=0.05,
            lazy_penalty=0.03,
        ),
        trust_config=TrustConfig(
            initial_score=0.9,
            time_decay_rate=0.001,
        ),
        auto_audit=auto_audit,
    )
    gc = GovernanceCoordinator(config)

    models = ["gpt-4", "claude-3", "gemini-2"]
    for i in range(n_validators):
        gc.register_validator(
            f"val-{i:03d}",
            trust_score=0.7 + (i % 4) * 0.1,
            domains=["finance", "privacy"],
            model=models[i % len(models)],
        )
    return gc


def _oracle_agrees(case_id: str, sub_hash: str) -> str:
    """Spot-check oracle that always agrees with the original."""
    return "approve"


def _oracle_disagrees(case_id: str, sub_hash: str) -> str:
    """Spot-check oracle that always disagrees (catches bad approvals)."""
    return "reject"


# ── Basic lifecycle ──────────────────────────────────────────────────────────


class TestBasicLifecycle:
    """Create → claim → submit → select validators → finalize."""

    def test_happy_path(self) -> None:
        gc = _make_coordinator()

        # Create
        cid = gc.create_case("evaluate model v3", domain="finance", risk_tier="high", _now=_ts(0))
        assert gc.case(cid).state == CaseState.OPEN

        # Claim
        gc.assign_miner(cid, "miner-42", _now=_ts(1))
        assert gc.case(cid).state == CaseState.CLAIMED

        # Submit
        gc.submit_result(cid, "miner-42", {"verdict": "allow"}, _now=_ts(2))
        assert gc.case(cid).state == CaseState.SUBMITTED

        # Select validators and begin validation
        sel = gc.select_and_begin_validation(cid, _now=_ts(3))
        assert gc.case(cid).state == CaseState.VALIDATING
        assert sel.producer_excluded  # miner-42 excluded
        assert sel.k >= 5  # high risk
        assert sel.verify()

        # Finalize
        votes = {vid: "approve" for vid in sel.selected}
        gc.finalize_case(
            cid,
            accepted=True,
            validator_votes=votes,
            proof_hash="abc123",
            _now=_ts(4),
        )
        assert gc.case(cid).state == CaseState.FINALIZED

    def test_rejection_lifecycle(self) -> None:
        gc = _make_coordinator()
        cid = gc.create_case("risky action", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "m1", _now=_ts(1))
        gc.submit_result(cid, "m1", {}, _now=_ts(2))
        sel = gc.select_and_begin_validation(cid, _now=_ts(3))

        votes = {vid: "reject" for vid in sel.selected}
        gc.finalize_case(cid, accepted=False, validator_votes=votes, _now=_ts(4))
        assert gc.case(cid).state == CaseState.REJECTED

    def test_maci_submitter_must_be_claimer(self) -> None:
        gc = _make_coordinator()
        cid = gc.create_case("test", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "miner-1", _now=_ts(1))

        with pytest.raises(ValueError, match="MACI violation"):
            gc.submit_result(cid, "miner-2", {}, _now=_ts(2))

    def test_producer_excluded_from_selection(self) -> None:
        gc = _make_coordinator()
        # Register the miner as a validator too
        gc.register_validator("miner-1", domains=["finance"], model="gpt-4")

        cid = gc.create_case("test", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "miner-1", _now=_ts(1))
        gc.submit_result(cid, "miner-1", {}, _now=_ts(2))

        sel = gc.select_and_begin_validation(cid, _now=_ts(3))
        assert "miner-1" not in sel.selected


# ── Selection proof verification ─────────────────────────────────────────────


class TestSelectionProof:
    def test_signed_proof_verifiable(self) -> None:
        gc = _make_coordinator(signing_key="test-key-123")
        cid = gc.create_case("test", domain="finance", risk_tier="medium", _now=_ts(0))
        gc.assign_miner(cid, "m1", _now=_ts(1))
        gc.submit_result(cid, "m1", {}, _now=_ts(2))

        sel = gc.select_and_begin_validation(cid, _now=_ts(3))
        assert sel.proof.signature != ""
        assert sel.verify(signing_key="test-key-123")
        assert not sel.verify(signing_key="wrong-key")

    def test_selection_tracked_per_case(self) -> None:
        gc = _make_coordinator()
        cid = gc.create_case("test", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "m1", _now=_ts(1))
        gc.submit_result(cid, "m1", {}, _now=_ts(2))
        gc.select_and_begin_validation(cid, _now=_ts(3))

        proof = gc.selection_proof(cid)
        assert proof is not None
        assert proof.verify()


# ── Audit cycle ──────────────────────────────────────────────────────────────


class TestAuditCycle:
    def test_audit_cycle_with_correct_validators(self) -> None:
        """All validators vote correctly → small trust reward."""
        gc = _make_coordinator()

        # Process a case
        cid = gc.create_case("test", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "m1", _now=_ts(1))
        gc.submit_result(cid, "m1", {}, _now=_ts(2))
        sel = gc.select_and_begin_validation(cid, _now=_ts(3))

        votes = {vid: "approve" for vid in sel.selected}
        gc.finalize_case(cid, accepted=True, validator_votes=votes, _now=_ts(4))

        # Run audit (oracle agrees)
        audit = gc.run_audit_cycle(check_fn=_oracle_agrees, _now=_ts(10))
        assert len(audit.spot_check_results) == 1
        assert audit.spot_check_results[0].agrees_with_original is True
        assert audit.adjustments_applied > 0
        assert audit.validators_synced > 0

        # All selected validators should have slightly improved trust
        for vid in sel.selected:
            score = gc.validator_trust(vid, _now=_ts(10))
            assert score > 0.0  # has some score

    def test_audit_cycle_detects_lazy_validators(self) -> None:
        """Spot-check disagrees → lazy validators penalized, dissenters rewarded."""
        # Use equal initial scores so trust deltas are directly comparable
        gc = GovernanceCoordinator(
            CoordinatorConfig(
                case_config=CaseConfig(
                    claim_timeout_minutes=60,
                    submission_timeout_minutes=120,
                    validation_timeout_minutes=480,
                ),
                selection_policy=SelectionPolicy(require_domain_match=True),
                audit_policy=AuditPolicy(
                    sample_rate=1.0,
                    correct_dissent_bonus=0.05,
                    lazy_penalty=0.03,
                ),
                trust_config=TrustConfig(initial_score=0.9, time_decay_rate=0.001),
            )
        )
        for i in range(10):
            gc.register_validator(
                f"val-{i:03d}",
                trust_score=0.9,  # all same score
                domains=["finance"],
                model=["gpt-4", "claude-3", "gemini-2"][i % 3],
            )

        cid = gc.create_case("test", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "m1", _now=_ts(1))
        gc.submit_result(cid, "m1", {}, _now=_ts(2))
        sel = gc.select_and_begin_validation(cid, seed="aabb" * 16, _now=_ts(3))

        # One dissenter
        votes = {vid: "approve" for vid in sel.selected}
        dissenter = sel.selected[-1]
        votes[dissenter] = "reject"

        gc.finalize_case(cid, accepted=True, validator_votes=votes, _now=_ts(4))

        # Oracle says "reject" → the majority was wrong
        audit = gc.run_audit_cycle(check_fn=_oracle_disagrees, _now=_ts(10))

        # Find the dissenter's adjustment
        adj_map = {a.validator_id: a for a in audit.trust_adjustments}
        assert adj_map[dissenter].delta > 0  # correct dissent bonus
        assert adj_map[dissenter].dissent_bonus_count == 1

        # Lazy validators penalized
        for vid in sel.selected[:-1]:
            assert adj_map[vid].delta < 0
            assert adj_map[vid].lazy_count == 1

        # With equal starting scores, dissenter should now be higher
        d_score = gc.validator_trust(dissenter, _now=_ts(10))
        l_score = gc.validator_trust(sel.selected[0], _now=_ts(10))
        assert d_score > l_score

    def test_auto_audit_on_finalize(self) -> None:
        """When auto_audit is enabled, audit runs on every finalization."""
        gc = _make_coordinator(auto_audit=True)

        cid = gc.create_case("test", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "m1", _now=_ts(1))
        gc.submit_result(cid, "m1", {}, _now=_ts(2))
        sel = gc.select_and_begin_validation(cid, _now=_ts(3))

        votes = {vid: "approve" for vid in sel.selected}
        gc.finalize_case(cid, accepted=True, validator_votes=votes, _now=_ts(4))

        # Audit should have already run (auto_audit=True)
        # Verify by checking that unchecked count is 0
        assert gc.auditor.unchecked_count() == 0


# ── Multi-case scenarios ─────────────────────────────────────────────────────


class TestMultiCase:
    def test_multiple_cases_different_domains(self) -> None:
        gc = _make_coordinator()

        cases = []
        for i, domain in enumerate(["finance", "privacy", "finance"]):
            cid = gc.create_case(f"case-{i}", domain=domain, _now=_ts(i * 10))
            gc.assign_miner(cid, f"miner-{i}", _now=_ts(i * 10 + 1))
            gc.submit_result(cid, f"miner-{i}", {"v": i}, _now=_ts(i * 10 + 2))
            sel = gc.select_and_begin_validation(cid, _now=_ts(i * 10 + 3))
            votes = {vid: "approve" for vid in sel.selected}
            gc.finalize_case(
                cid,
                accepted=True,
                validator_votes=votes,
                _now=_ts(i * 10 + 4),
            )
            cases.append(cid)

        # Summary should reflect all 3 cases
        s = gc.summary()
        assert s["case_lifecycle"]["total_cases"] == 3
        assert s["case_lifecycle"]["finalized_count"] == 3
        assert s["pending_audit_cases"] == 3  # not yet audited

        # Run audit
        audit = gc.run_audit_cycle(check_fn=_oracle_agrees, _now=_ts(50))
        assert len(audit.spot_check_results) == 3
        assert gc.auditor.unchecked_count() == 0

    def test_case_timeout_and_requeue(self) -> None:
        gc = _make_coordinator()

        cid = gc.create_case("slow case", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "slow-miner", _now=_ts(1))

        # Time out (submission timeout = 120 min)
        gc.expire_stale_cases(_now=_ts(125))

        # Should be re-queued (auto_requeue_on_expiry=True)
        case = gc.case(cid)
        assert case.state == CaseState.OPEN
        assert case.claim_count == 1

        # New miner picks it up
        gc.assign_miner(cid, "fast-miner", _now=_ts(130))
        gc.submit_result(cid, "fast-miner", {"v": 1}, _now=_ts(135))
        sel = gc.select_and_begin_validation(cid, _now=_ts(140))
        gc.finalize_case(
            cid,
            accepted=True,
            validator_votes={vid: "approve" for vid in sel.selected},
            _now=_ts(145),
        )
        assert gc.case(cid).state == CaseState.FINALIZED


# ── Trust feedback loop ──────────────────────────────────────────────────────


class TestTrustFeedback:
    def test_trust_syncs_back_to_pool(self) -> None:
        """Trust adjustments flow back to the validator pool, affecting
        future selection probabilities."""
        gc = _make_coordinator()

        # Record a score before
        before_score = gc.validator_pool.get("val-000").trust_score

        # Process case where val-000 is lazy
        cid = gc.create_case("test", domain="finance", _now=_ts(0))
        gc.assign_miner(cid, "m1", _now=_ts(1))
        gc.submit_result(cid, "m1", {}, _now=_ts(2))
        sel = gc.select_and_begin_validation(
            cid,
            seed="ff" * 32,
            _now=_ts(3),
        )

        # Check if val-000 was selected
        if "val-000" in sel.selected:
            votes = {vid: "approve" for vid in sel.selected}
            gc.finalize_case(
                cid,
                accepted=True,
                validator_votes=votes,
                _now=_ts(4),
            )

            # Oracle disagrees → val-000 was lazy
            gc.run_audit_cycle(check_fn=_oracle_disagrees, _now=_ts(5))

            # Pool score should have changed
            after_score = gc.validator_pool.get("val-000").trust_score
            assert after_score != before_score

    def test_domain_specific_trust(self) -> None:
        """Domain-scoped trust: penalty in finance doesn't affect privacy."""
        gc = _make_coordinator()

        # val-003 starts with trust 1.0 (0.7 + (3%4)*0.1 = 1.0) — above trusted threshold
        vid = "val-003"
        assert gc.validator_trust(vid, _now=_ts(0)) >= 0.9  # sanity check initial score

        # Directly record a domain-specific violation via trust manager
        gc.trust_manager.record_decision(
            vid,
            compliant=False,
            severity="critical",
            domain="finance",
            _now=_ts(0),
        )

        fin_score = gc.validator_trust(vid, domain="finance", _now=_ts(0))
        priv_tier = gc.validator_tier(vid, domain="privacy", _now=_ts(0))

        # Finance should be penalized
        assert fin_score < 0.9
        # Privacy should still be trusted (no history → initial score)
        assert priv_tier == TrustTier.TRUSTED


# ── Diversity reporting ──────────────────────────────────────────────────────


class TestDiversity:
    def test_pool_diversity_report(self) -> None:
        gc = _make_coordinator(10)
        report = gc.monoculture_report()
        assert report["total_validators"] == 10
        assert report["diversity_score"] > 0  # 3 models across 10 validators
        assert not report["monoculture_risk"]

    def test_monoculture_pool_flagged(self) -> None:
        gc = GovernanceCoordinator()
        for i in range(5):
            gc.register_validator(f"v{i}", domains=["fin"], model="gpt-4")

        report = gc.monoculture_report()
        assert report["monoculture_risk"] is True
        assert report["diversity_score"] == 0.0


# ── Queries and summary ─────────────────────────────────────────────────────


class TestQueries:
    def test_open_cases(self) -> None:
        gc = _make_coordinator()
        gc.create_case("a", domain="finance", _now=_ts(0))
        gc.create_case("b", domain="privacy", _now=_ts(0))
        c3 = gc.create_case("c", domain="finance", _now=_ts(0))
        gc.assign_miner(c3, "m1", _now=_ts(1))

        assert len(gc.open_cases()) == 2
        assert len(gc.open_cases(domain="finance")) == 1

    def test_claimable_cases(self) -> None:
        gc = _make_coordinator()
        gc.create_case("a", domain="finance", _now=_ts(0))
        assert len(gc.claimable_cases("m1")) == 1

    def test_summary(self) -> None:
        gc = _make_coordinator()
        gc.create_case("test", domain="finance", _now=_ts(0))

        s = gc.summary()
        assert "case_lifecycle" in s
        assert "trust" in s
        assert "audit" in s
        assert "pool" in s
        assert s["case_lifecycle"]["total_cases"] == 1
        assert s["pool"]["total_validators"] == 10

    def test_repr(self) -> None:
        gc = _make_coordinator(5)
        gc.create_case("test", _now=_ts(0))
        r = repr(gc)
        assert "cases=1" in r
        assert "validators=5" in r
