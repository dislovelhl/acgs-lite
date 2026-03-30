"""Tests for Bittensor protocol types and subnet integration scaffolding."""

from __future__ import annotations

from constitutional_swarm.bittensor.protocol import (
    EscalationType,
    MinerConfig,
    MinerTier,
    SubnetMetrics,
    TIER_TAO_MULTIPLIER,
    TIER_REQUIREMENTS,
    ValidatorConfig,
)
from constitutional_swarm.bittensor.synapses import (
    DeliberationSynapse,
    JudgmentSynapse,
    ValidationSynapse,
)


class TestEscalationType:
    """Escalation type enum covers the working taxonomy."""

    def test_four_categories_plus_unknown(self):
        assert len(EscalationType) == 5
        assert EscalationType.CONSTITUTIONAL_CONFLICT.value == "constitutional_conflict"
        assert EscalationType.CONTEXT_SENSITIVITY.value == "context_sensitivity"
        assert EscalationType.STAKEHOLDER_IRRECONCILABILITY.value == "stakeholder_irreconcilability"
        assert EscalationType.EDGE_CASE_AMBIGUITY.value == "edge_case_ambiguity"
        assert EscalationType.UNKNOWN.value == "unknown"


class TestMinerTier:
    """Miner qualification tiers with TAO multipliers."""

    def test_four_tiers(self):
        assert len(MinerTier) == 4

    def test_multipliers_increase_with_tier(self):
        assert TIER_TAO_MULTIPLIER[MinerTier.APPRENTICE] < TIER_TAO_MULTIPLIER[MinerTier.JOURNEYMAN]
        assert TIER_TAO_MULTIPLIER[MinerTier.JOURNEYMAN] < TIER_TAO_MULTIPLIER[MinerTier.MASTER]
        assert TIER_TAO_MULTIPLIER[MinerTier.MASTER] < TIER_TAO_MULTIPLIER[MinerTier.ELDER]

    def test_requirements_increase_with_tier(self):
        apprentice = TIER_REQUIREMENTS[MinerTier.APPRENTICE]
        master = TIER_REQUIREMENTS[MinerTier.MASTER]
        assert apprentice["min_validated"] < master["min_validated"]
        assert apprentice["min_reputation"] < master["min_reputation"]


class TestSubnetMetrics:
    """SubnetMetrics tracks escalation data for empirical distribution."""

    def test_empty_metrics(self):
        metrics = SubnetMetrics()
        assert metrics.total_escalations == 0
        assert metrics.escalation_distribution() == {}

    def test_record_escalation(self):
        metrics = SubnetMetrics()
        metrics.record_escalation(EscalationType.CONSTITUTIONAL_CONFLICT)
        metrics.record_escalation(EscalationType.CONSTITUTIONAL_CONFLICT)
        metrics.record_escalation(EscalationType.CONTEXT_SENSITIVITY)
        assert metrics.total_escalations == 3
        assert metrics.escalation_type_counts["constitutional_conflict"] == 2
        assert metrics.escalation_type_counts["context_sensitivity"] == 1

    def test_escalation_distribution(self):
        metrics = SubnetMetrics()
        for _ in range(7):
            metrics.record_escalation(EscalationType.CONSTITUTIONAL_CONFLICT)
        for _ in range(3):
            metrics.record_escalation(EscalationType.CONTEXT_SENSITIVITY)
        dist = metrics.escalation_distribution()
        assert abs(dist["constitutional_conflict"] - 0.7) < 1e-9
        assert abs(dist["context_sensitivity"] - 0.3) < 1e-9


class TestDeliberationSynapse:
    """SN Owner → Miner synapse."""

    def test_create_and_hash(self):
        synapse = DeliberationSynapse(
            task_id="task-001",
            task_dag_json='{"goal": "resolve privacy conflict"}',
            constitution_hash="608508a9bd224290",
            domain="privacy",
            required_capabilities=("tier:master", "privacy"),
            impact_score=0.85,
        )
        assert synapse.task_id == "task-001"
        assert synapse.constitution_hash == "608508a9bd224290"
        assert synapse.content_hash  # deterministic, non-empty
        assert len(synapse.content_hash) == 32

    def test_immutable(self):
        synapse = DeliberationSynapse(
            task_id="t",
            task_dag_json="{}",
            constitution_hash="hash",
            domain="d",
        )
        try:
            synapse.task_id = "changed"  # type: ignore[misc]
            assert False, "Should be immutable"
        except AttributeError:
            pass

    def test_to_dict(self):
        synapse = DeliberationSynapse(
            task_id="t",
            task_dag_json="{}",
            constitution_hash="h",
            domain="d",
        )
        d = synapse.to_dict()
        assert d["task_id"] == "t"
        assert d["constitution_hash"] == "h"


class TestJudgmentSynapse:
    """Miner → Validator synapse."""

    def test_create_with_dna_result(self):
        synapse = JudgmentSynapse(
            task_id="task-001",
            miner_uid="miner-42",
            judgment="Privacy takes precedence in this context",
            reasoning="Article 8 ECHR applies; the data subject has not consented",
            artifact_hash="abc123",
            constitutional_hash="608508a9bd224290",
            dna_valid=True,
            dna_latency_ns=443,
            domain="privacy",
        )
        assert synapse.dna_valid is True
        assert synapse.dna_latency_ns == 443
        assert synapse.content_hash
        assert len(synapse.content_hash) == 32

    def test_content_hash_deterministic(self):
        args = dict(
            task_id="t",
            miner_uid="m",
            judgment="j",
            reasoning="r",
            artifact_hash="a",
            constitutional_hash="h",
        )
        s1 = JudgmentSynapse(**args)
        s2 = JudgmentSynapse(**args)
        assert s1.content_hash == s2.content_hash


class TestValidationSynapse:
    """Validator → SN Owner synapse."""

    def test_create_with_proof(self):
        synapse = ValidationSynapse(
            task_id="task-001",
            assignment_id="assign-01",
            accepted=True,
            votes_for=2,
            votes_against=1,
            quorum_met=True,
            proof_root_hash="deadbeef" * 4,
            proof_vote_hashes=("hash1", "hash2", "hash3"),
            constitutional_hash="608508a9bd224290",
        )
        assert synapse.accepted is True
        assert synapse.is_verified is True
        assert synapse.quorum_met is True

    def test_not_verified_without_proof(self):
        synapse = ValidationSynapse(
            task_id="t",
            assignment_id="a",
            accepted=False,
            votes_for=0,
            votes_against=2,
            quorum_met=True,
        )
        assert synapse.is_verified is False


class TestMinerConfig:
    """Miner configuration is immutable."""

    def test_defaults(self):
        config = MinerConfig(constitution_path="/path/to/constitution.yaml")
        assert config.tier == MinerTier.APPRENTICE
        assert config.strict_dna is True
        assert config.validate_output is True

    def test_custom(self):
        config = MinerConfig(
            constitution_path="/path",
            agent_id="miner-01",
            capabilities=("governance-judgment",),
            domains=("finance", "privacy"),
            tier=MinerTier.MASTER,
        )
        assert config.tier == MinerTier.MASTER
        assert "finance" in config.domains


class TestValidatorConfig:
    """Validator configuration."""

    def test_defaults(self):
        config = ValidatorConfig(constitution_path="/path")
        assert config.peers_per_validation == 3
        assert config.quorum == 2
        assert config.use_manifold is True
