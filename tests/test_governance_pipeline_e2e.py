"""End-to-end integration test for the governance validation pipeline.

Exercises the **full lifecycle** of a governance case through all four
acgs-lite validation primitives:

    CaseManager  →  ValidatorSelector  →  Lifecycle finalization
        ↓                                        ↓
    SpotCheckAuditor  ←────────────────── finalized cases
        ↓
    TrustScoreManager  →  sync_to_validator_pool  →  ValidatorPool

This proves the modules compose correctly into a working governance
system before wiring into the constitutional_swarm bittensor layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from acgs_lite.constitution.claim_lifecycle import (
    CaseConfig,
    CaseManager,
    CaseState,
)
from acgs_lite.constitution.spot_check import (
    AuditPolicy,
    SpotCheckAuditor,
)
from acgs_lite.constitution.trust_score import (
    TrustConfig,
    TrustScoreManager,
    TrustTier,
)
from acgs_lite.constitution.validator_selection import (
    SelectionPolicy,
    ValidatorPool,
    ValidatorSelector,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _ts(minutes: float = 0) -> datetime:
    """Base timestamp with optional minute offset."""
    return datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def _setup_pool(n_validators: int = 10) -> ValidatorPool:
    """Create a pool with diverse validators across 3 model types."""
    pool = ValidatorPool()
    models = ["gpt-5.5", "claude-sonnet-4-6", "gemini-2.5-flash"]
    for i in range(n_validators):
        pool.register(
            f"val-{i:03d}",
            trust_score=0.7 + (i % 4) * 0.1,
            domains=["finance", "privacy"],
            model=models[i % len(models)],
        )
    return pool


def _setup_trust_manager(validator_ids: list[str]) -> TrustScoreManager:
    """Create a TrustScoreManager tracking the given validators."""
    mgr = TrustScoreManager()
    for vid in validator_ids:
        mgr.register(
            vid,
            TrustConfig(
                initial_score=0.9,
                time_decay_rate=0.001,
            ),
        )
    return mgr


def _revalidation_fn(oracle_outcomes: dict[str, str]):
    """Factory: returns a spot-check function that uses a fixed oracle."""

    def check_fn(case_id: str, submission_hash: str) -> str:
        return oracle_outcomes.get(case_id, "approve")

    return check_fn


# ── Full Pipeline E2E ────────────────────────────────────────────────────────


class TestGovernancePipelineE2E:
    """Full end-to-end: create case → select validators → process lifecycle
    → spot-check → trust adjustment → sync back to validator pool."""

    def test_single_case_happy_path(self) -> None:
        """One case, accepted by validators, spot-checked as correct."""
        t = _ts(0)

        # ── 1. Setup infrastructure ──
        pool = _setup_pool(10)
        selector = ValidatorSelector(
            pool,
            SelectionPolicy(
                signing_key="e2e-test-key",
                require_domain_match=True,
            ),
        )
        case_mgr = CaseManager(
            CaseConfig(
                claim_timeout_minutes=60,
                submission_timeout_minutes=120,
                validation_timeout_minutes=480,
            )
        )
        validator_ids = pool.list_validators()
        trust_mgr = _setup_trust_manager(validator_ids)
        auditor = SpotCheckAuditor(
            AuditPolicy(
                sample_rate=1.0,  # check everything in tests
                correct_reward=0.005,
                correct_dissent_bonus=0.05,
                lazy_penalty=0.03,
            )
        )

        # ── 2. Create governance case ──
        case_id = case_mgr.create(
            action="Evaluate financial model v3 for privacy compliance",
            domain="finance",
            risk_tier="high",
            _now=t,
        )
        case = case_mgr.get(case_id)
        assert case is not None
        assert case.state == CaseState.OPEN

        # ── 3. Miner claims and submits ──
        miner_id = "miner-42"
        case_mgr.claim(case_id, miner_id, _now=_ts(5))
        case_mgr.submit(
            case_id,
            miner_id,
            result={"verdict": "compliant", "confidence": 0.92},
            _now=_ts(10),
        )
        assert case_mgr.get(case_id).state == CaseState.SUBMITTED

        # ── 4. Select validator quorum ──
        selection = selector.select(
            case_id=case_id,
            producer_id=miner_id,
            risk_tier="high",
            domain="finance",
            seed="deadbeef" * 8,
        )
        assert selection.producer_excluded
        assert selection.k >= 5  # high risk → k=7 if enough validators
        assert selection.verify(signing_key="e2e-test-key")

        # ── 5. Begin validation ──
        case_mgr.begin_validation(
            case_id,
            selection.selected,
            _now=_ts(15),
        )
        assert case_mgr.get(case_id).state == CaseState.VALIDATING

        # ── 6. Finalize (approved) ──
        case_mgr.finalize(
            case_id,
            outcome="approved",
            proof_hash="abc123",
            _now=_ts(20),
        )
        final_case = case_mgr.get(case_id)
        assert final_case.state == CaseState.FINALIZED
        assert final_case.outcome == "approved"

        # ── 7. Register for spot-check ──
        # Simulate validator votes: all selected voted "approve"
        votes = {vid: "approve" for vid in selection.selected}
        auditor.register_completed(
            case_id=case_id,
            domain="finance",
            original_outcome="approved",
            validator_votes=votes,
            submission_hash="abc123",
            producer_id=miner_id,
            _now=_ts(25),
        )

        # ── 8. Run spot-check (oracle agrees → correct) ──
        oracle = _revalidation_fn({case_id: "approve"})
        results = auditor.run_spot_check(oracle, case_ids=[case_id], _now=_ts(30))
        assert len(results) == 1
        assert results[0].agrees_with_original is True

        # All validators voted correctly
        for va in results[0].validator_assessments:
            assert va.assessment == "correct"
            assert va.trust_delta > 0

        # ── 9. Compute and apply trust adjustments ──
        adjustments = auditor.compute_adjustments(results)
        applied = auditor.apply_adjustments(trust_mgr, adjustments, _now=_ts(35))
        assert applied > 0

        # All validators should have slightly improved trust
        for vid in selection.selected:
            score = trust_mgr.score(vid, _now=_ts(35))
            assert score > 0.9  # started at 0.9, got a small reward

        # ── 10. Sync trust back to validator pool ──
        updated = trust_mgr.sync_to_validator_pool(pool, _now=_ts(35))
        assert updated == len(validator_ids)

        # Verify pool reflects updated scores
        for vid in selection.selected:
            pool_info = pool.get(vid)
            assert pool_info is not None
            # Pool score should now match trust manager
            expected = trust_mgr.score(vid, _now=_ts(35))
            assert abs(pool_info.trust_score - expected) < 1e-4

    def test_lazy_validators_detected_and_penalized(self) -> None:
        """Case where spot-check disagrees with majority: lazy validators
        are penalized and correct dissenters are rewarded."""
        t = _ts(0)

        pool = _setup_pool(10)
        selector = ValidatorSelector(pool)
        case_mgr = CaseManager()
        validator_ids = pool.list_validators()
        trust_mgr = _setup_trust_manager(validator_ids)
        auditor = SpotCheckAuditor(
            AuditPolicy(
                sample_rate=1.0,
                correct_dissent_bonus=0.05,
                lazy_penalty=0.03,
            )
        )

        # Create and process case
        case_id = case_mgr.create("evaluate deployment risk", domain="finance", _now=t)
        case_mgr.claim(case_id, "miner-1", _now=_ts(1))
        case_mgr.submit(case_id, "miner-1", {"verdict": "safe"}, _now=_ts(2))

        selection = selector.select(
            case_id=case_id,
            producer_id="miner-1",
            risk_tier="medium",
            domain="finance",
            seed="aabb" * 16,
        )

        case_mgr.begin_validation(case_id, selection.selected, _now=_ts(3))
        case_mgr.finalize(case_id, "approved", _now=_ts(4))

        # Simulate: all but one validator voted "approve", one dissented
        votes = {vid: "approve" for vid in selection.selected}
        dissenter = selection.selected[-1]
        votes[dissenter] = "reject"

        auditor.register_completed(
            case_id=case_id,
            domain="finance",
            original_outcome="approved",
            validator_votes=votes,
            submission_hash="hash-1",
            _now=_ts(5),
        )

        # Spot-check DISAGREES with original → original approval was wrong
        oracle = _revalidation_fn({case_id: "reject"})
        results = auditor.run_spot_check(oracle, case_ids=[case_id], _now=_ts(6))
        assert results[0].agrees_with_original is False

        # The dissenter should be assessed as "correct_dissent"
        assessments = {a.validator_id: a for a in results[0].validator_assessments}
        assert assessments[dissenter].assessment == "correct_dissent"
        assert assessments[dissenter].trust_delta > 0

        # All majority voters should be "lazy_agree"
        for vid in selection.selected[:-1]:
            assert assessments[vid].assessment == "lazy_agree"
            assert assessments[vid].trust_delta < 0

        # Apply adjustments
        adjustments = auditor.compute_adjustments(results)
        auditor.apply_adjustments(trust_mgr, adjustments, _now=_ts(7))

        # Dissenter should now have higher trust than lazy validators
        dissenter_score = trust_mgr.score(dissenter, _now=_ts(7))
        lazy_score = trust_mgr.score(selection.selected[0], _now=_ts(7))
        assert dissenter_score > lazy_score

        # Sync to pool and verify
        trust_mgr.sync_to_validator_pool(pool, _now=_ts(7))
        assert pool.get(dissenter).trust_score > pool.get(selection.selected[0]).trust_score

    def test_multi_case_pipeline_with_domain_scoping(self) -> None:
        """Multiple cases across domains, demonstrating domain-isolated
        trust scoring and cross-domain aggregate effects."""
        pool = _setup_pool(10)
        selector = ValidatorSelector(pool, SelectionPolicy(require_domain_match=False))
        case_mgr = CaseManager()
        trust_mgr = _setup_trust_manager(pool.list_validators())
        auditor = SpotCheckAuditor(AuditPolicy(sample_rate=1.0))

        processed_cases: list[str] = []

        for i, (domain, outcome, _spot_agrees) in enumerate(
            [
                ("finance", "approved", True),
                ("privacy", "approved", False),  # spot-check catches bad approval
                ("finance", "rejected", True),
            ]
        ):
            cid = case_mgr.create(
                f"case-{i}",
                domain=domain,
                risk_tier="medium",
                _now=_ts(i * 10),
            )
            case_mgr.claim(cid, f"miner-{i}", _now=_ts(i * 10 + 1))
            case_mgr.submit(cid, f"miner-{i}", {"v": i}, _now=_ts(i * 10 + 2))

            sel = selector.select(
                case_id=cid,
                producer_id=f"miner-{i}",
                risk_tier="medium",
                domain=domain,
                seed=f"{i:064x}",
            )
            case_mgr.begin_validation(cid, sel.selected, _now=_ts(i * 10 + 3))
            case_mgr.finalize(cid, outcome, _now=_ts(i * 10 + 4))

            # All validators vote with the outcome
            vote_val = "approve" if outcome == "approved" else "reject"
            votes = {vid: vote_val for vid in sel.selected}

            auditor.register_completed(
                case_id=cid,
                domain=domain,
                original_outcome=outcome,
                validator_votes=votes,
                submission_hash=f"hash-{i}",
                _now=_ts(i * 10 + 5),
            )
            processed_cases.append(cid)

        # Run spot-checks with oracle
        oracle_outcomes = {
            processed_cases[0]: "approve",  # agrees
            processed_cases[1]: "reject",  # disagrees (catches bad approval)
            processed_cases[2]: "reject",  # agrees with rejection
        }
        oracle = _revalidation_fn(oracle_outcomes)
        results = auditor.run_spot_check(oracle, _now=_ts(50))
        assert len(results) == 3

        # Case 1: agreement
        assert results[0].agrees_with_original is True
        # Case 2: disagreement (privacy domain validators were lazy)
        assert results[1].agrees_with_original is False
        # Case 3: agreement
        assert results[2].agrees_with_original is True

        # Apply all adjustments
        adjustments = auditor.compute_adjustments(results)
        auditor.apply_adjustments(trust_mgr, adjustments, _now=_ts(55))

        # Sync back to pool
        trust_mgr.sync_to_validator_pool(pool, _now=_ts(55))

        # Verify summary
        summary = auditor.summary()
        assert summary["total_spot_checks"] == 3
        assert summary["agreements"] == 2
        assert summary["disagreements"] == 1
        assert summary["lazy_validations_detected"] > 0

        # Case manager summary
        cm_summary = case_mgr.summary()
        assert cm_summary["total_cases"] == 3
        assert cm_summary["finalized_count"] == 2  # 1 approved + 1 rejected (via finalize)

    def test_case_timeout_and_requeue_pipeline(self) -> None:
        """Case times out, gets requeued, then successfully processed
        on second attempt with fresh validator selection."""
        config = CaseConfig(
            claim_timeout_minutes=10,
            submission_timeout_minutes=30,
            auto_requeue_on_expiry=True,
            max_claims=3,
        )
        pool = _setup_pool(8)
        selector = ValidatorSelector(pool)
        case_mgr = CaseManager(config)

        # Create case
        cid = case_mgr.create("review model", domain="finance", _now=_ts(0))

        # First claim — miner abandons (timeout)
        case_mgr.claim(cid, "miner-slow", _now=_ts(1))
        case_mgr.expire_stale(_now=_ts(35))  # past submission deadline

        # Case should be auto-requeued
        case = case_mgr.get(cid)
        assert case.state == CaseState.OPEN
        assert case.claim_count == 1

        # Second claim — successful this time
        case_mgr.claim(cid, "miner-fast", _now=_ts(36))
        case_mgr.submit(cid, "miner-fast", {"verdict": "ok"}, _now=_ts(40))

        sel = selector.select(
            case_id=cid,
            producer_id="miner-fast",
            risk_tier="medium",
            domain="finance",
            seed="cc" * 32,
        )
        case_mgr.begin_validation(cid, sel.selected, _now=_ts(42))
        case_mgr.finalize(cid, "approved", _now=_ts(45))

        assert case_mgr.get(cid).state == CaseState.FINALIZED
        assert case_mgr.get(cid).claim_count == 2

        # Audit trail should show the full history
        trail = case_mgr.transitions(cid)
        states = [t.to_state for t in trail]
        assert "open" in states
        assert "claimed" in states
        assert "expired" in states
        assert "finalized" in states

    def test_maci_constraints_enforced_through_pipeline(self) -> None:
        """MACI separation of powers is enforced at every layer:
        - Claimer must be submitter
        - Producer excluded from validator selection
        - Producer excluded from validation quorum
        """
        pool = _setup_pool(10)
        # Add the miner as a validator too
        pool.register("miner-1", trust_score=0.95, domains=["finance"], model="gpt-5.5")
        selector = ValidatorSelector(pool)
        case_mgr = CaseManager()

        cid = case_mgr.create("test MACI", domain="finance", _now=_ts(0))
        case_mgr.claim(cid, "miner-1", _now=_ts(1))

        # MACI: different agent can't submit
        with pytest.raises(ValueError, match="MACI violation"):
            case_mgr.submit(cid, "miner-2", {}, _now=_ts(2))

        # Correct submitter
        case_mgr.submit(cid, "miner-1", {"v": 1}, _now=_ts(2))

        # Validator selection excludes producer
        sel = selector.select(
            case_id=cid,
            producer_id="miner-1",
            risk_tier="medium",
            domain="finance",
        )
        assert "miner-1" not in sel.selected
        assert sel.producer_excluded

        # MACI: producer can't be in validation quorum
        with pytest.raises(ValueError, match="MACI violation"):
            case_mgr.begin_validation(cid, ["miner-1", "val-001", "val-002"], _now=_ts(3))

        # Correct: use selected validators (producer excluded)
        case_mgr.begin_validation(cid, sel.selected, _now=_ts(3))
        case_mgr.finalize(cid, "approved", _now=_ts(4))

    def test_trust_decay_and_recovery_over_time(self) -> None:
        """Demonstrates time-based forgiveness: a penalized validator
        gradually recovers trust and regains selection likelihood."""
        config = TrustConfig(
            initial_score=1.0,
            time_decay_rate=0.01,  # recover 0.01/hour passively
        )
        trust_mgr = TrustScoreManager()
        trust_mgr.register("val-target", config)
        trust_mgr.register("val-clean", config)

        # Heavy penalty on val-target (4 × critical = -0.80, score = 0.20)
        for _ in range(4):
            trust_mgr.record_decision(
                "val-target",
                compliant=False,
                severity="critical",
                domain="finance",
                _now=_ts(0),
            )

        # Immediately: val-target is restricted
        assert trust_mgr.tier("val-target", domain="finance", _now=_ts(0)) == TrustTier.RESTRICTED
        assert trust_mgr.tier("val-clean", _now=_ts(0)) == TrustTier.TRUSTED

        # After 50 hours: 0.20 + 0.01*50 = 0.70 → monitored
        assert (
            trust_mgr.tier("val-target", domain="finance", _now=_ts(50 * 60)) == TrustTier.MONITORED
        )

        # After 80 hours: 0.20 + 0.01*80 = 1.00 → trusted (capped at 1.0)
        assert (
            trust_mgr.tier("val-target", domain="finance", _now=_ts(80 * 60)) == TrustTier.TRUSTED
        )

        # Sync recovered trust to pool
        pool = ValidatorPool()
        pool.register("val-target", trust_score=0.2, domains=["finance"])
        pool.register("val-clean", trust_score=1.0, domains=["finance"])

        trust_mgr.sync_to_validator_pool(pool, domain="finance", _now=_ts(80 * 60))
        assert pool.get("val-target").trust_score >= 0.99  # recovered

    def test_validator_pool_diversity_affects_selection(self) -> None:
        """Low-diversity pools get flagged; diversity bonus influences selection."""
        # Monoculture pool
        mono_pool = ValidatorPool()
        for i in range(6):
            mono_pool.register(f"v{i}", trust_score=0.9, domains=["fin"], model="gpt-5.5")

        report = mono_pool.monoculture_report()
        assert report["monoculture_risk"] is True
        assert report["diversity_score"] == 0.0

        # Diverse pool
        diverse_pool = ValidatorPool()
        models = [
            "gpt-5.5",
            "claude-sonnet-4-6",
            "gemini-2.5-flash",
            "llama-3",
            "mistral-2",
            "qwen-2",
        ]
        for i, m in enumerate(models):
            diverse_pool.register(f"v{i}", trust_score=0.9, domains=["fin"], model=m)

        report = diverse_pool.monoculture_report()
        assert report["monoculture_risk"] is False
        assert report["diversity_score"] > 0.99

        # Selection from diverse pool should have high diversity
        selector = ValidatorSelector(diverse_pool, SelectionPolicy(diversity_bonus_factor=1.0))
        result = selector.select(
            case_id="c1",
            producer_id="producer-x",
            risk_tier="low",
            domain="fin",
        )
        assert result.diversity_score > 0.0

    def test_bias_detection_across_many_cases(self) -> None:
        """Validator who always votes the same way gets flagged for bias."""
        auditor = SpotCheckAuditor(
            AuditPolicy(
                sample_rate=1.0,
                min_cases_for_bias=5,
                bias_threshold=0.90,
            )
        )

        # Register 10 cases — val-rubber always approves
        for i in range(10):
            auditor.register_completed(
                case_id=f"c{i}",
                domain="finance",
                original_outcome="approved",
                validator_votes={
                    "val-rubber": "approve",  # always same
                    "val-varied": "approve" if i % 2 == 0 else "reject",
                },
                submission_hash=f"h{i}",
                _now=_ts(i),
            )

        biased = auditor.biased_validators()
        assert len(biased) == 1
        assert biased[0]["validator_id"] == "val-rubber"
        assert biased[0]["bias_direction"] == "approve"

        # val-varied should NOT be flagged
        varied_ids = [b["validator_id"] for b in biased]
        assert "val-varied" not in varied_ids

    def test_complete_system_summary(self) -> None:
        """All four subsystems produce coherent summaries after a pipeline run."""
        pool = _setup_pool(8)
        selector = ValidatorSelector(pool)
        case_mgr = CaseManager()
        trust_mgr = _setup_trust_manager(pool.list_validators())
        auditor = SpotCheckAuditor(AuditPolicy(sample_rate=1.0))

        # Process one case end-to-end
        cid = case_mgr.create("summary test", domain="finance", _now=_ts(0))
        case_mgr.claim(cid, "m1", _now=_ts(1))
        case_mgr.submit(cid, "m1", {}, _now=_ts(2))
        sel = selector.select(cid, "m1", "medium", "finance", seed="dd" * 32)
        case_mgr.begin_validation(cid, sel.selected, _now=_ts(3))
        case_mgr.finalize(cid, "approved", _now=_ts(4))

        votes = {vid: "approve" for vid in sel.selected}
        auditor.register_completed(
            cid,
            "finance",
            "approved",
            votes,
            "hash",
            _now=_ts(5),
        )
        results = auditor.run_spot_check(
            _revalidation_fn({cid: "approve"}),
            _now=_ts(6),
        )
        adjustments = auditor.compute_adjustments(results)
        auditor.apply_adjustments(trust_mgr, adjustments, _now=_ts(7))
        trust_mgr.sync_to_validator_pool(pool, _now=_ts(7))

        # Verify all summaries are populated
        cm = case_mgr.summary()
        assert cm["total_cases"] == 1
        assert cm["finalized_count"] == 1

        ts = trust_mgr.summary()
        assert ts["agent_count"] == 8

        sp = auditor.summary()
        assert sp["total_spot_checks"] == 1
        assert sp["agreement_rate"] == 1.0

        pr = pool.monoculture_report(domain="finance")
        assert pr["total_validators"] == 8

        # Selection result is independently verifiable
        assert sel.verify()
