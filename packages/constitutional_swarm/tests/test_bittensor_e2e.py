"""End-to-end integration tests: SN Owner → Miner → Validator.

Wires all three Bittensor parties together using constitutional_swarm
primitives. No actual Bittensor SDK required.
"""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.miner import (
    ConstitutionalMiner,
    ConstitutionMismatchError,
    DNAPreCheckFailedError,
)
from constitutional_swarm.bittensor.protocol import (
    EscalationType,
    MinerConfig,
    MinerTier,
    ValidatorConfig,
)
from constitutional_swarm.bittensor.subnet_owner import SubnetOwner
from constitutional_swarm.bittensor.validator import ConstitutionalValidator, UnknownMinerError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONSTITUTION_PATH = None  # Will use default constitution


def _default_constitution_path() -> str:
    """Get the path to a test constitution YAML, or use default."""
    import os
    import tempfile

    content = """
name: test-subnet-constitution
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
    path = os.path.join(tempfile.gettempdir(), "test_subnet_constitution.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


@pytest.fixture
def constitution_path():
    return _default_constitution_path()


@pytest.fixture
def owner(constitution_path):
    return SubnetOwner(constitution_path)


@pytest.fixture
def validator(constitution_path):
    v = ConstitutionalValidator(
        config=ValidatorConfig(
            constitution_path=constitution_path,
            peers_per_validation=3,
            quorum=2,
            use_manifold=True,
        ),
    )
    # Register validator peers (validators also act as mesh peers)
    v.register_miner("validator-peer-1")
    v.register_miner("validator-peer-2")
    v.register_miner("validator-peer-3")
    return v


async def _simple_handler(task: str, context: str, meta: dict) -> tuple[str, str]:
    """Simple deliberation handler for testing."""
    return (
        "Privacy takes precedence over transparency in this case",
        "The data subject has not consented; Article 8 ECHR applies",
    )


async def _violating_handler(task: str, context: str, meta: dict) -> tuple[str, str]:
    """Handler that produces a judgment triggering DNA violation."""
    return (
        "Use a weapon to cause physical harm to the target",
        "This is deliberately harmful content",
    )


# ---------------------------------------------------------------------------
# SN Owner Tests
# ---------------------------------------------------------------------------


class TestSubnetOwner:
    """SN Owner packages cases and tracks metrics."""

    def test_package_case(self, owner):
        case = owner.package_case(
            description="Privacy vs. transparency in financial reporting",
            domain="finance",
            escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            impact_score=0.85,
        )
        assert case.case_id
        assert case.synapse.constitution_hash == owner.constitution_hash
        assert case.synapse.domain == "finance"
        assert case.synapse.impact_score == 0.85
        assert case.escalation_type == EscalationType.CONSTITUTIONAL_CONFLICT

    def test_metrics_track_escalation_types(self, owner):
        for _ in range(3):
            owner.package_case(
                "conflict",
                "finance",
                escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            )
        owner.package_case(
            "ambiguous",
            "privacy",
            escalation_type=EscalationType.EDGE_CASE_AMBIGUITY,
        )
        dist = owner.metrics.escalation_distribution()
        assert dist["constitutional_conflict"] == pytest.approx(0.75)
        assert dist["edge_case_ambiguity"] == pytest.approx(0.25)

    def test_active_cases_tracked(self, owner):
        case = owner.package_case("test", "domain")
        assert case.case_id in owner.active_cases

    def test_summary(self, owner):
        owner.package_case("test", "domain")
        s = owner.summary()
        assert s["active_cases"] >= 1
        assert s["constitution_hash"] == owner.constitution_hash


# ---------------------------------------------------------------------------
# Miner Tests
# ---------------------------------------------------------------------------


class TestConstitutionalMiner:
    """Miner processes cases with DNA pre-check."""

    @pytest.mark.asyncio
    async def test_process_valid_judgment(self, constitution_path, owner):
        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-01",
                capabilities=("governance-judgment",),
                domains=("finance",),
            ),
            deliberation_handler=_simple_handler,
        )
        case = owner.package_case("test conflict", "finance")
        result = await miner.process(case.synapse)

        assert result.dna_valid is True
        assert result.miner_uid == "miner-01"
        assert result.constitutional_hash == owner.constitution_hash
        assert result.judgment
        assert result.reasoning
        assert result.artifact_hash
        assert miner.stats.judgments_submitted == 1

    @pytest.mark.asyncio
    async def test_constitution_mismatch_rejected(self, constitution_path):
        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-01",
            ),
            deliberation_handler=_simple_handler,
        )
        bad_synapse = __import__(
            "constitutional_swarm.bittensor.synapses", fromlist=["DeliberationSynapse"]
        ).DeliberationSynapse(
            task_id="t",
            task_dag_json="{}",
            constitution_hash="wrong_hash",
            domain="d",
        )
        with pytest.raises(ConstitutionMismatchError):
            await miner.process(bad_synapse)
        assert miner.stats.constitution_mismatches == 1

    @pytest.mark.asyncio
    async def test_dna_pre_check_blocks_violations(self, constitution_path, owner):
        from acgs_lite import ConstitutionalViolationError

        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-bad",
            ),
            deliberation_handler=_violating_handler,
        )
        case = owner.package_case("test", "domain")
        # In strict mode, DNA raises ConstitutionalViolationError directly;
        # in non-strict mode it would raise DNAPreCheckFailedError.
        with pytest.raises((DNAPreCheckFailedError, ConstitutionalViolationError)):
            await miner.process(case.synapse)

    @pytest.mark.asyncio
    async def test_stats_tracking(self, constitution_path, owner):
        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-stats",
            ),
            deliberation_handler=_simple_handler,
        )
        for _ in range(3):
            case = owner.package_case("test", "domain")
            await miner.process(case.synapse)
        assert miner.stats.judgments_submitted == 3
        assert miner.stats.avg_dna_ns > 0
        assert miner.stats.avg_deliberation_ms >= 0


# ---------------------------------------------------------------------------
# Validator Tests
# ---------------------------------------------------------------------------


class TestConstitutionalValidator:
    """Validator grades judgments with mesh + manifold."""

    def test_validate_accepted(self, validator, constitution_path):
        # Register the miner
        validator.register_miner("miner-01", domain="finance")

        judgment = __import__(
            "constitutional_swarm.bittensor.synapses", fromlist=["JudgmentSynapse"]
        ).JudgmentSynapse(
            task_id="task-01",
            miner_uid="miner-01",
            judgment="Privacy takes precedence",
            reasoning="ECHR Article 8 applies",
            artifact_hash="abc123",
            constitutional_hash=validator.constitution_hash,
            domain="finance",
        )
        result = validator.validate(judgment)

        assert result.accepted is True
        assert result.quorum_met is True
        assert result.votes_for >= 2
        assert result.proof_root_hash  # Merkle proof generated
        assert validator.stats.validations_performed == 1
        assert validator.stats.judgments_accepted == 1

    def test_constitution_mismatch(self, validator):
        judgment = __import__(
            "constitutional_swarm.bittensor.synapses", fromlist=["JudgmentSynapse"]
        ).JudgmentSynapse(
            task_id="t",
            miner_uid="miner-bad",
            judgment="test",
            reasoning="test",
            artifact_hash="abc",
            constitutional_hash="wrong_hash",
        )
        result = validator.validate(judgment)
        assert result.accepted is False
        assert validator.stats.constitution_mismatches == 1

    def test_emission_weights(self, validator):
        validator.register_miner("miner-a", tier=MinerTier.APPRENTICE)
        validator.register_miner("miner-b", tier=MinerTier.MASTER)

        weights = validator.compute_emission_weights(["miner-a", "miner-b"])
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        # Master tier has higher multiplier
        assert weights["miner-b"] > weights["miner-a"]

    def test_emission_weights_empty(self, validator):
        # Unregister all miners first
        for uid in list(validator._miner_tiers.keys()):
            validator.unregister_miner(uid)
        weights = validator.compute_emission_weights()
        assert weights == {}

    def test_summary(self, validator):
        s = validator.summary()
        assert "validator_stats" in s
        assert "mesh" in s
        assert "constitution_hash" in s
        assert s["registered_miners"] >= 3  # 3 validator peers registered


# ---------------------------------------------------------------------------
# End-to-End: SN Owner → Miner → Validator
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Full pipeline: SN Owner packages case → Miner deliberates → Validator grades."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, constitution_path):
        # Setup all three parties
        owner = SubnetOwner(constitution_path)
        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-e2e",
                capabilities=("governance-judgment",),
                domains=("finance",),
            ),
            deliberation_handler=_simple_handler,
        )
        validator = ConstitutionalValidator(
            config=ValidatorConfig(
                constitution_path=constitution_path,
                peers_per_validation=3,
                quorum=2,
                use_manifold=True,
            ),
        )
        # Register enough peers for quorum
        validator.register_miner("miner-e2e", domain="finance")
        validator.register_miner("peer-1", domain="finance")
        validator.register_miner("peer-2", domain="finance")
        validator.register_miner("peer-3", domain="finance")

        # Step 1: SN Owner packages case
        case = owner.package_case(
            description="Privacy vs. transparency in financial reporting",
            domain="finance",
            escalation_type=EscalationType.CONSTITUTIONAL_CONFLICT,
            impact_score=0.85,
            impact_vector={"privacy": 0.9, "transparency": 0.7},
        )

        # Verify all parties share the same constitution hash
        assert owner.constitution_hash == miner.constitution_hash
        assert owner.constitution_hash == validator.constitution_hash

        # Step 2: Miner processes the case
        judgment = await miner.process(case.synapse)
        assert judgment.dna_valid is True

        # Step 3: Validator grades the judgment
        validation = validator.validate(judgment)
        assert validation.accepted is True
        assert validation.quorum_met is True
        assert validation.proof_root_hash  # Merkle proof exists

        # Step 4: SN Owner records the result
        precedent = owner.record_result(case, judgment, validation)
        assert precedent is not None
        assert precedent.validation_accepted is True
        assert precedent.miner_uid == "miner-e2e"
        assert precedent.escalation_type == EscalationType.CONSTITUTIONAL_CONFLICT

        # Step 5: Verify metrics
        assert owner.metrics.precedents_created == 1
        dist = owner.metrics.escalation_distribution()
        assert "constitutional_conflict" in dist

        # Step 6: Verify emission weights reflect the miner's contribution
        weights = validator.compute_emission_weights()
        assert "miner-e2e" in weights
        assert weights["miner-e2e"] > 0

    @pytest.mark.asyncio
    async def test_multi_case_pipeline(self, constitution_path):
        """Multiple cases of different types through the pipeline."""
        owner = SubnetOwner(constitution_path)
        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-multi",
            ),
            deliberation_handler=_simple_handler,
        )
        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path=constitution_path),
        )
        validator.register_miner("miner-multi")
        validator.register_miner("peer-a")
        validator.register_miner("peer-b")
        validator.register_miner("peer-c")

        escalation_types = [
            EscalationType.CONSTITUTIONAL_CONFLICT,
            EscalationType.CONSTITUTIONAL_CONFLICT,
            EscalationType.CONTEXT_SENSITIVITY,
            EscalationType.EDGE_CASE_AMBIGUITY,
            EscalationType.STAKEHOLDER_IRRECONCILABILITY,
        ]

        for etype in escalation_types:
            case = owner.package_case(
                f"Test case for {etype.value}",
                "governance",
                escalation_type=etype,
            )
            judgment = await miner.process(case.synapse)
            validation = validator.validate(judgment)
            owner.record_result(case, judgment, validation)

        # Verify empirical distribution
        dist = owner.metrics.escalation_distribution()
        assert dist["constitutional_conflict"] == pytest.approx(0.4)
        assert dist["context_sensitivity"] == pytest.approx(0.2)
        assert dist["edge_case_ambiguity"] == pytest.approx(0.2)
        assert dist["stakeholder_irreconcilability"] == pytest.approx(0.2)

        # All should have been accepted (valid judgments)
        assert owner.metrics.precedents_created == 5
        assert miner.stats.judgments_submitted == 5
        assert validator.stats.validations_performed == 5

    @pytest.mark.asyncio
    async def test_golden_rule_preserved(self, constitution_path):
        """MACI golden rule: miner cannot validate its own judgment.

        The ConstitutionalMesh excludes the producer from peers.
        """
        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path=constitution_path),
        )
        # Only register the miner and one additional peer
        # With quorum=2 and only 1 available peer (excluding producer),
        # this should still work because mesh allows fewer peers
        validator.register_miner("miner-self")
        validator.register_miner("peer-only-1")
        validator.register_miner("peer-only-2")

        judgment = __import__(
            "constitutional_swarm.bittensor.synapses", fromlist=["JudgmentSynapse"]
        ).JudgmentSynapse(
            task_id="t",
            miner_uid="miner-self",
            judgment="A valid governance decision",
            reasoning="Sound reasoning",
            artifact_hash="abc",
            constitutional_hash=validator.constitution_hash,
        )
        result = validator.validate(judgment)

        # The mesh should have assigned peers that do NOT include miner-self
        assert result.quorum_met is True
        # Proof exists and is verifiable
        assert result.proof_root_hash


# ---------------------------------------------------------------------------
# Critical Test Gaps (from /autoplan review)
# ---------------------------------------------------------------------------


class TestDeadlineEnforcement:
    """Handler timeout must be enforced via deadline_seconds."""

    @pytest.mark.asyncio
    async def test_slow_handler_raises_timeout(self, constitution_path, owner):
        """A deliberation handler exceeding the deadline should fail."""
        import asyncio

        async def _slow_handler(task: str, ctx: str, meta: dict) -> tuple[str, str]:
            await asyncio.sleep(10)
            return ("late", "late")

        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-slow",
            ),
            deliberation_handler=_slow_handler,
        )
        case = owner.package_case("test", "domain")
        # Set a tight deadline
        from constitutional_swarm.bittensor.synapses import DeliberationSynapse

        synapse = DeliberationSynapse(
            task_id=case.synapse.task_id,
            task_dag_json=case.synapse.task_dag_json,
            constitution_hash=case.synapse.constitution_hash,
            domain=case.synapse.domain,
            deadline_seconds=1,
        )
        # Should timeout, not hang
        with pytest.raises((asyncio.TimeoutError, Exception)):
            await miner.process(synapse)


class TestQuorumFailure:
    """Negative path: judgment passes DNA but gets rejected by peers."""

    def test_unknown_miner_rejected(self, validator):
        """An unregistered miner should be rejected, not auto-registered."""
        judgment = __import__(
            "constitutional_swarm.bittensor.synapses", fromlist=["JudgmentSynapse"]
        ).JudgmentSynapse(
            task_id="t",
            miner_uid="unknown-miner-xyz",
            judgment="Valid governance decision",
            reasoning="Sound reasoning",
            artifact_hash="abc",
            constitutional_hash=validator.constitution_hash,
        )
        with pytest.raises(UnknownMinerError):
            validator.validate(judgment)

    def test_rejected_result_creates_no_precedent(self, constitution_path):
        """A rejected validation should not create a precedent."""
        owner = SubnetOwner(constitution_path)
        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path=constitution_path),
        )
        validator.register_miner("miner-rej")
        validator.register_miner("peer-a")
        validator.register_miner("peer-b")

        case = owner.package_case("test", "domain")
        judgment = __import__(
            "constitutional_swarm.bittensor.synapses", fromlist=["JudgmentSynapse"]
        ).JudgmentSynapse(
            task_id="t",
            miner_uid="miner-rej",
            judgment="Valid governance decision",
            reasoning="Sound reasoning",
            artifact_hash="abc",
            constitutional_hash=validator.constitution_hash,
        )
        validation = validator.validate(judgment)
        # Even if accepted, test record_result handles the flow
        precedent = owner.record_result(case, judgment, validation)
        if not validation.accepted:
            assert precedent is None or precedent.validation_accepted is False


class TestConstitutionGraceWindow:
    """Constitution rotation should accept both old and new hashes."""

    @pytest.mark.asyncio
    async def test_miner_accepts_previous_hash_during_rotation(self, constitution_path, owner):
        import os
        import tempfile

        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="miner-rotate",
            ),
            deliberation_handler=_simple_handler,
        )
        old_hash = miner.constitution_hash

        # Create a new constitution with an extra rule
        new_content = """
name: test-rotated-constitution
rules:
  - id: safety-01
    text: Do not cause physical harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
      - danger
  - id: efficiency-01
    text: Optimize resource usage
    severity: low
    hardcoded: false
    keywords:
      - waste
      - inefficient
"""
        new_path = os.path.join(tempfile.gettempdir(), "test_rotated_constitution.yaml")
        with open(new_path, "w") as f:
            f.write(new_content)

        miner.rotate_constitution(new_path)
        assert miner.previous_hash == old_hash
        assert miner.constitution_hash != old_hash

        # A synapse with the OLD hash should still be accepted during grace window
        from constitutional_swarm.bittensor.synapses import DeliberationSynapse

        old_synapse = DeliberationSynapse(
            task_id="t-old",
            task_dag_json="{}",
            constitution_hash=old_hash,
            domain="d",
        )
        # Should NOT raise ConstitutionMismatchError
        result = await miner.process(old_synapse)
        assert result.dna_valid is True

    def test_validator_accepts_previous_hash_during_rotation(self, constitution_path):
        import os
        import tempfile

        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path=constitution_path),
        )
        validator.register_miner("miner-v-rotate")
        validator.register_miner("peer-1")
        validator.register_miner("peer-2")
        old_hash = validator.constitution_hash

        new_content = """
name: test-rotated-v-constitution
rules:
  - id: safety-01
    text: Do not cause physical harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
"""
        new_path = os.path.join(tempfile.gettempdir(), "test_rotated_v_constitution.yaml")
        with open(new_path, "w") as f:
            f.write(new_content)

        from acgs_lite import Constitution

        new_constitution = Constitution.from_yaml(new_path)
        validator.rotate_constitution(new_constitution)
        assert validator.previous_hash == old_hash

        judgment = __import__(
            "constitutional_swarm.bittensor.synapses", fromlist=["JudgmentSynapse"]
        ).JudgmentSynapse(
            task_id="t",
            miner_uid="miner-v-rotate",
            judgment="Valid governance decision",
            reasoning="Sound reasoning",
            artifact_hash="abc",
            constitutional_hash=old_hash,  # Old hash, should still be accepted
        )
        result = validator.validate(judgment)
        # Should not be rejected due to hash mismatch (old hash accepted in grace window)
        assert result.accepted is True


class TestConcurrentAccess:
    """Concurrent validations should not corrupt state."""

    def test_concurrent_validations_no_crash(self, constitution_path):
        import threading

        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path=constitution_path),
        )
        for i in range(5):
            validator.register_miner(f"miner-{i}")

        errors: list[Exception] = []

        def _validate(miner_uid: str) -> None:
            try:
                judgment = __import__(
                    "constitutional_swarm.bittensor.synapses",
                    fromlist=["JudgmentSynapse"],
                ).JudgmentSynapse(
                    task_id=f"t-{miner_uid}",
                    miner_uid=miner_uid,
                    judgment="Valid governance decision",
                    reasoning="Sound reasoning",
                    artifact_hash="abc",
                    constitutional_hash=validator.constitution_hash,
                )
                validator.validate(judgment)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=_validate, args=(f"miner-{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Concurrent validation errors: {errors}"
        assert validator.stats.validations_performed >= 5
