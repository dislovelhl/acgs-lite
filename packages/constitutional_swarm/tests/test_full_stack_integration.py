"""Full-stack integration: GovernanceCoordinator + Miner + Validator.

Exercises the complete loop:
  1. GovernanceCoordinator creates a case
  2. ConstitutionalMiner processes the escalated case (DNA pre-check)
  3. GovernanceCoordinator selects validator quorum
  4. ConstitutionalValidator grades the judgment (mesh + Merkle proof)
  5. GovernanceCoordinator finalizes and registers for audit
  6. SpotCheckAuditor runs audit, adjusts trust
  7. Trust syncs back to ValidatorPool for next selection

This proves the full pipeline from acgs-lite governance primitives
through constitutional_swarm bittensor runtime to audited feedback loop.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from constitutional_swarm.bittensor.governance_coordinator import (
    CoordinatorConfig,
    GovernanceCoordinator,
)
from constitutional_swarm.bittensor.miner import (
    ConstitutionalMiner,
    MinerConfig,
)
from constitutional_swarm.bittensor.protocol import (
    EscalationType,
    MinerTier,
    ValidatorConfig,
)
from constitutional_swarm.bittensor.subnet_owner import SubnetOwner
from constitutional_swarm.bittensor.validator import ConstitutionalValidator

from acgs_lite.constitution.claim_lifecycle import CaseConfig, CaseState
from acgs_lite.constitution.spot_check import AuditPolicy
from acgs_lite.constitution.trust_score import TrustConfig
from acgs_lite.constitution.validator_selection import SelectionPolicy

# ── Fixtures ─────────────────────────────────────────────────────────────────

_CONSTITUTION_YAML = """\
name: full-stack-test-constitution
rules:
  - id: safety-01
    text: Do not cause physical harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
      - danger
      - kill
      - weapon
  - id: privacy-01
    text: Protect personal information
    severity: high
    hardcoded: true
    keywords:
      - personal data
      - PII
      - private
  - id: fairness-01
    text: Avoid discriminatory outcomes
    severity: high
    hardcoded: false
    keywords:
      - discriminat
      - bias
      - unfair
"""


@pytest.fixture
def constitution_path():
    path = os.path.join(tempfile.gettempdir(), "test_full_stack_constitution.yaml")
    with open(path, "w") as f:
        f.write(_CONSTITUTION_YAML)
    return path


@pytest.fixture
def coordinator():
    config = CoordinatorConfig(
        case_config=CaseConfig(
            claim_timeout_minutes=60,
            submission_timeout_minutes=120,
            validation_timeout_minutes=480,
        ),
        selection_policy=SelectionPolicy(
            signing_key="full-stack-test-key",
            require_domain_match=False,  # test validators don't have domain lists
        ),
        audit_policy=AuditPolicy(
            sample_rate=1.0,
            correct_reward=0.005,
            correct_dissent_bonus=0.05,
            lazy_penalty=0.03,
        ),
        trust_config=TrustConfig(
            initial_score=0.9,
            time_decay_rate=0.001,
        ),
    )
    gc = GovernanceCoordinator(config)

    # Register validators matching the mesh peers
    models = ["gpt-4", "claude-3", "gemini-2"]
    for i in range(8):
        gc.register_validator(
            f"val-{i:03d}",
            trust_score=0.9,
            model=models[i % len(models)],
        )
    return gc


def _ts(minutes: float = 0) -> datetime:
    return datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC) + timedelta(minutes=minutes)


async def _valid_handler(task: str, context: str, meta: dict) -> tuple[str, str]:
    """Simple deliberation handler: produces a valid governance judgment."""
    return (
        "Privacy considerations outweigh transparency requirements in this case",
        "The data subjects have not provided explicit consent per GDPR Article 7",
    )


async def _violating_handler(task: str, context: str, meta: dict) -> tuple[str, str]:
    """Handler that triggers DNA violation."""
    return (
        "Use a weapon to cause harm and danger to the target",
        "Deliberately harmful",
    )


# ── Full-stack E2E ───────────────────────────────────────────────────────────


class TestFullStackIntegration:
    """GovernanceCoordinator + ConstitutionalMiner + ConstitutionalValidator."""

    @pytest.mark.asyncio
    async def test_complete_pipeline(self, constitution_path, coordinator):
        """Full loop: create → miner → validator → finalize → audit → trust sync."""

        # ── Setup miner and validator ──
        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-e2e",
                capabilities=("governance-judgment",),
            ),
            deliberation_handler=_valid_handler,
        )
        validator = ConstitutionalValidator(
            config=ValidatorConfig(
                constitution_path=constitution_path,
                peers_per_validation=3,
                quorum=2,
                use_manifold=True,
            ),
        )
        # Register mesh peers for the validator
        validator.register_miner("miner-e2e", domain="finance")
        for i in range(5):
            validator.register_miner(f"peer-{i}", domain="finance")

        # Create SN Owner for case packaging
        owner = SubnetOwner(constitution_path)

        # ── 1. Coordinator creates a case ──
        case_id = coordinator.create_case(
            action="Evaluate financial model privacy compliance",
            domain="finance",
            risk_tier="high",
            _now=_ts(0),
        )
        assert coordinator.case(case_id).state == CaseState.OPEN

        # ── 2. SN Owner packages the case as a synapse ──
        escalated = owner.package_case(
            description="Privacy vs transparency in financial reporting",
            domain="finance",
            escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            impact_score=0.85,
        )
        # All parties share the same constitution
        assert owner.constitution_hash == miner.constitution_hash
        assert owner.constitution_hash == validator.constitution_hash

        # ── 3. Coordinator assigns miner ──
        coordinator.assign_miner(case_id, "miner-e2e", _now=_ts(1))
        assert coordinator.case(case_id).state == CaseState.CLAIMED

        # ── 4. Miner processes the case ──
        judgment = await miner.process(escalated.synapse)
        assert judgment.dna_valid is True
        assert judgment.miner_uid == "miner-e2e"
        assert judgment.judgment  # non-empty
        assert judgment.reasoning  # non-empty

        # ── 5. Coordinator records miner's submission ──
        coordinator.submit_result(
            case_id,
            "miner-e2e",
            result={
                "judgment": judgment.judgment,
                "reasoning": judgment.reasoning,
                "artifact_hash": judgment.artifact_hash,
            },
            _now=_ts(2),
        )
        assert coordinator.case(case_id).state == CaseState.SUBMITTED

        # ── 6. Coordinator selects validator quorum ──
        selection = coordinator.select_and_begin_validation(
            case_id,
            seed="deadbeef" * 8,
            _now=_ts(3),
        )
        assert selection.producer_excluded
        assert "miner-e2e" not in selection.selected
        assert selection.verify(signing_key="full-stack-test-key")
        assert coordinator.case(case_id).state == CaseState.VALIDATING

        # ── 7. Validator grades the judgment ──
        validation = validator.validate(judgment)
        assert validation.accepted is True
        assert validation.quorum_met is True
        assert validation.proof_root_hash  # Merkle proof exists

        # ── 8. SN Owner records precedent ──
        precedent = owner.record_result(escalated, judgment, validation)
        assert precedent is not None
        assert precedent.validation_accepted is True

        # ── 9. Coordinator finalizes ──
        # Construct votes from the selected validators (all approve since validation accepted)
        votes = {vid: "approve" for vid in selection.selected}
        coordinator.finalize_case(
            case_id,
            accepted=True,
            validator_votes=votes,
            proof_hash=validation.proof_root_hash,
            _now=_ts(4),
        )
        assert coordinator.case(case_id).state == CaseState.FINALIZED

        # ── 10. Run audit cycle ──
        def _agrees_oracle(cid: str, sub_hash: str) -> str:
            return "approve"

        audit = coordinator.run_audit_cycle(check_fn=_agrees_oracle, _now=_ts(10))
        assert len(audit.spot_check_results) == 1
        assert audit.spot_check_results[0].agrees_with_original is True
        assert audit.adjustments_applied > 0
        assert audit.validators_synced > 0

        # ── 11. Verify trust is synced back ──
        for vid in selection.selected:
            pool_info = coordinator.validator_pool.get(vid)
            assert pool_info is not None
            trust_score = coordinator.validator_trust(vid, _now=_ts(10))
            assert abs(pool_info.trust_score - trust_score) < 1e-4

        # ── 12. Comprehensive summary ──
        summary = coordinator.summary()
        assert summary["case_lifecycle"]["total_cases"] == 1
        assert summary["case_lifecycle"]["finalized_count"] == 1
        assert summary["audit"]["total_spot_checks"] == 1
        assert summary["audit"]["agreement_rate"] == 1.0
        assert summary["pool"]["total_validators"] == 8

        # Miner stats
        assert miner.stats.judgments_submitted == 1
        assert validator.stats.validations_performed == 1
        assert owner.metrics.precedents_created == 1

    @pytest.mark.asyncio
    async def test_multi_case_with_audit_feedback(self, constitution_path, coordinator):
        """Multiple cases: audit detects lazy validators, trust adjusts
        for next round's selection."""

        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-multi",
            ),
            deliberation_handler=_valid_handler,
        )
        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path=constitution_path),
        )
        validator.register_miner("miner-multi")
        for i in range(6):
            validator.register_miner(f"peer-{i}")

        owner = SubnetOwner(constitution_path)

        # Process 3 cases
        for i in range(3):
            cid = coordinator.create_case(
                f"case-{i}",
                domain="governance",
                risk_tier="medium",
                _now=_ts(i * 10),
            )
            escalated = owner.package_case(f"case-{i} desc", "governance")

            coordinator.assign_miner(cid, "miner-multi", _now=_ts(i * 10 + 1))
            judgment = await miner.process(escalated.synapse)
            coordinator.submit_result(
                cid,
                "miner-multi",
                result={"judgment": judgment.judgment},
                _now=_ts(i * 10 + 2),
            )

            sel = coordinator.select_and_begin_validation(
                cid,
                seed=f"{i:064x}",
                _now=_ts(i * 10 + 3),
            )

            validation = validator.validate(judgment)
            votes = {vid: "approve" for vid in sel.selected}

            coordinator.finalize_case(
                cid,
                accepted=True,
                validator_votes=votes,
                proof_hash=validation.proof_root_hash or "proof",
                _now=_ts(i * 10 + 4),
            )

        # All 3 cases finalized
        assert coordinator.case_manager.summary()["finalized_count"] == 3

        # Run audit where oracle disagrees on case-1 (catches bad approval)
        def _selective_oracle(case_id: str, sub_hash: str) -> str:
            # Disagree with second case to simulate lazy detection
            if "CASE-000002" in case_id:
                return "reject"
            return "approve"

        audit = coordinator.run_audit_cycle(
            check_fn=_selective_oracle,
            _now=_ts(40),
        )
        assert len(audit.spot_check_results) == 3
        # 2 agreements, 1 disagreement
        agreements = sum(1 for r in audit.spot_check_results if r.agrees_with_original)
        assert agreements == 2
        assert audit.adjustments_applied > 0

    @pytest.mark.asyncio
    async def test_dna_violation_blocks_miner(self, constitution_path, coordinator):
        """Miner producing a harmful judgment is blocked by DNA pre-check."""
        from constitutional_swarm.bittensor.miner import DNAPreCheckFailedError

        from acgs_lite import ConstitutionalViolationError

        bad_miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-bad",
            ),
            deliberation_handler=_violating_handler,
        )
        owner = SubnetOwner(constitution_path)

        cid = coordinator.create_case("test", domain="safety", _now=_ts(0))
        coordinator.assign_miner(cid, "miner-bad", _now=_ts(1))

        escalated = owner.package_case("test safety", "safety")
        with pytest.raises((DNAPreCheckFailedError, ConstitutionalViolationError)):
            await bad_miner.process(escalated.synapse)

        # Case should still be claimed but not submitted
        assert coordinator.case(cid).state == CaseState.CLAIMED

    @pytest.mark.asyncio
    async def test_emission_weights_from_validated_judgments(
        self,
        constitution_path,
        coordinator,
    ):
        """Validator computes TAO emission weights from accumulated judgments."""
        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-w",
            ),
            deliberation_handler=_valid_handler,
        )
        validator = ConstitutionalValidator(
            config=ValidatorConfig(
                constitution_path=constitution_path,
                use_manifold=True,
            ),
        )
        validator.register_miner("miner-w", domain="finance", tier=MinerTier.JOURNEYMAN)
        validator.register_miner("peer-a", domain="finance", tier=MinerTier.APPRENTICE)
        validator.register_miner("peer-b")
        validator.register_miner("peer-c")

        owner = SubnetOwner(constitution_path)

        # Process case
        cid = coordinator.create_case("emission test", domain="finance", _now=_ts(0))
        escalated = owner.package_case("emission test", "finance")
        coordinator.assign_miner(cid, "miner-w", _now=_ts(1))
        judgment = await miner.process(escalated.synapse)
        coordinator.submit_result(
            cid,
            "miner-w",
            {"judgment": judgment.judgment},
            _now=_ts(2),
        )
        sel = coordinator.select_and_begin_validation(cid, _now=_ts(3))

        validation = validator.validate(judgment)
        assert validation.accepted

        votes = {vid: "approve" for vid in sel.selected}
        coordinator.finalize_case(
            cid,
            accepted=True,
            validator_votes=votes,
            _now=_ts(4),
        )

        # Compute emission weights
        weights = validator.compute_emission_weights(["miner-w", "peer-a"])
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        # Journeyman miner should get higher weight than apprentice
        assert weights["miner-w"] > weights["peer-a"]
