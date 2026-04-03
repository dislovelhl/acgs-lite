"""Tests for the bt.Synapse adapter layer.

Covers:
  - GovernanceDeliberation creation and field access
  - Dataclass <-> bt synapse conversions (round-trip)
  - MinerAxonServer handler wiring
  - ValidatorDendriteClient query/response
  - Error paths: constitution mismatch, timeout, unknown miner
  - Fallback behavior when bittensor is not installed
"""

from __future__ import annotations

import pytest
from constitutional_swarm.bittensor.synapse_adapter import (
    HAS_BITTENSOR,
    GovernanceDeliberation,
    bt_to_deliberation,
    bt_to_judgment,
    deliberation_to_bt,
    judgment_to_bt,
)
from constitutional_swarm.bittensor.synapses import (
    DeliberationSynapse,
    JudgmentSynapse,
)

# ---------------------------------------------------------------------------
# GovernanceDeliberation creation
# ---------------------------------------------------------------------------


class TestGovernanceDeliberation:
    """The bt.Synapse-compatible synapse holds both request and response fields."""

    def test_create_request_only(self):
        syn = GovernanceDeliberation(
            task_id="task-01",
            task_dag_json='{"goal": "test"}',
            constitution_hash="608508a9bd224290",
            domain="finance",
        )
        assert syn.task_id == "task-01"
        assert syn.constitution_hash == "608508a9bd224290"
        assert syn.domain == "finance"
        # Response fields should be None/empty
        assert syn.judgment is None
        assert syn.reasoning is None
        assert syn.artifact_hash is None

    def test_fill_response_fields(self):
        syn = GovernanceDeliberation(
            task_id="task-01",
            task_dag_json="{}",
            constitution_hash="hash",
            domain="d",
        )
        # Miner fills response fields (mutable, not frozen)
        syn.judgment = "Privacy takes precedence"
        syn.reasoning = "ECHR Article 8"
        syn.artifact_hash = "abc123"
        syn.dna_valid = True
        syn.miner_uid = "miner-01"

        assert syn.judgment == "Privacy takes precedence"
        assert syn.dna_valid is True

    def test_request_hash_deterministic(self):
        args = dict(
            task_id="t",
            task_dag_json='{"goal": "x"}',
            constitution_hash="h",
            domain="d",
        )
        s1 = GovernanceDeliberation(**args)
        s2 = GovernanceDeliberation(**args)
        assert s1.request_content_hash == s2.request_content_hash
        assert len(s1.request_content_hash) == 32

    def test_default_values(self):
        syn = GovernanceDeliberation(
            task_id="t",
            task_dag_json="{}",
            constitution_hash="h",
            domain="d",
        )
        assert syn.deadline_seconds == 3600
        assert syn.impact_score == 0.0
        assert syn.escalation_type == ""
        assert syn.required_capabilities == []
        assert syn.impact_vector == {}

    def test_deserialize_returns_self(self):
        syn = GovernanceDeliberation(
            task_id="t",
            task_dag_json="{}",
            constitution_hash="h",
            domain="d",
        )
        assert syn.deserialize() is syn


# ---------------------------------------------------------------------------
# Conversion: DeliberationSynapse <-> GovernanceDeliberation
# ---------------------------------------------------------------------------


class TestDeliberationConversion:
    """Round-trip conversion between frozen dataclass and bt synapse."""

    def test_deliberation_to_bt(self):
        delib = DeliberationSynapse(
            task_id="task-42",
            task_dag_json='{"goal": "resolve conflict"}',
            constitution_hash="608508a9bd224290",
            domain="privacy",
            required_capabilities=("tier:master", "privacy"),
            deadline_seconds=1800,
            escalation_type="constitutional_conflict",
            impact_score=0.85,
            impact_vector={"privacy": 0.9, "transparency": 0.7},
            context="Test context",
        )
        bt_syn = deliberation_to_bt(delib)

        assert isinstance(bt_syn, GovernanceDeliberation)
        assert bt_syn.task_id == "task-42"
        assert bt_syn.constitution_hash == "608508a9bd224290"
        assert bt_syn.domain == "privacy"
        assert bt_syn.required_capabilities == ["tier:master", "privacy"]
        assert bt_syn.deadline_seconds == 1800
        assert bt_syn.impact_score == 0.85
        assert bt_syn.impact_vector == {"privacy": 0.9, "transparency": 0.7}
        assert bt_syn.context == "Test context"
        # Response fields still empty
        assert bt_syn.judgment is None

    def test_bt_to_deliberation(self):
        bt_syn = GovernanceDeliberation(
            task_id="task-42",
            task_dag_json='{"goal": "test"}',
            constitution_hash="608508a9bd224290",
            domain="finance",
            required_capabilities=["tier:master"],
            deadline_seconds=900,
            escalation_type="edge_case_ambiguity",
            impact_score=0.5,
            impact_vector={"fairness": 0.8},
            context="Finance context",
        )
        delib = bt_to_deliberation(bt_syn)

        assert isinstance(delib, DeliberationSynapse)
        assert delib.task_id == "task-42"
        assert delib.constitution_hash == "608508a9bd224290"
        assert delib.required_capabilities == ("tier:master",)
        assert delib.deadline_seconds == 900
        assert delib.impact_vector == {"fairness": 0.8}

    def test_deliberation_round_trip(self):
        original = DeliberationSynapse(
            task_id="round-trip",
            task_dag_json='{"nodes": {}}',
            constitution_hash="abc123",
            domain="governance",
            required_capabilities=("cap-a", "cap-b"),
            deadline_seconds=600,
            escalation_type="context_sensitivity",
            impact_score=0.42,
        )
        bt_syn = deliberation_to_bt(original)
        restored = bt_to_deliberation(bt_syn)

        assert restored.task_id == original.task_id
        assert restored.constitution_hash == original.constitution_hash
        assert restored.domain == original.domain
        assert restored.required_capabilities == original.required_capabilities
        assert restored.deadline_seconds == original.deadline_seconds
        assert restored.escalation_type == original.escalation_type
        assert restored.impact_score == original.impact_score


# ---------------------------------------------------------------------------
# Conversion: JudgmentSynapse <-> GovernanceDeliberation response
# ---------------------------------------------------------------------------


class TestJudgmentConversion:
    """Extract JudgmentSynapse from a completed GovernanceDeliberation."""

    def test_bt_to_judgment(self):
        bt_syn = GovernanceDeliberation(
            task_id="task-01",
            task_dag_json="{}",
            constitution_hash="hash-a",
            domain="privacy",
        )
        # Simulate miner filling response
        bt_syn.judgment = "Privacy wins"
        bt_syn.reasoning = "ECHR applies"
        bt_syn.artifact_hash = "art-hash-01"
        bt_syn.dna_valid = True
        bt_syn.dna_violations = ["none"]
        bt_syn.dna_latency_ns = 443
        bt_syn.miner_uid = "miner-42"
        bt_syn.miner_constitution_hash = "hash-a"

        judgment = bt_to_judgment(bt_syn)

        assert isinstance(judgment, JudgmentSynapse)
        assert judgment.task_id == "task-01"
        assert judgment.miner_uid == "miner-42"
        assert judgment.judgment == "Privacy wins"
        assert judgment.reasoning == "ECHR applies"
        assert judgment.artifact_hash == "art-hash-01"
        assert judgment.constitutional_hash == "hash-a"
        assert judgment.dna_valid is True
        assert judgment.dna_violations == ("none",)
        assert judgment.dna_latency_ns == 443
        assert judgment.domain == "privacy"

    def test_bt_to_judgment_no_response_raises(self):
        bt_syn = GovernanceDeliberation(
            task_id="t",
            task_dag_json="{}",
            constitution_hash="h",
            domain="d",
        )
        # No response fields filled
        with pytest.raises(ValueError, match="no judgment"):
            bt_to_judgment(bt_syn)

    def test_judgment_to_bt(self):
        bt_syn = GovernanceDeliberation(
            task_id="task-01",
            task_dag_json="{}",
            constitution_hash="hash-a",
            domain="privacy",
        )
        judgment = JudgmentSynapse(
            task_id="task-01",
            miner_uid="miner-01",
            judgment="Decision X",
            reasoning="Because Y",
            artifact_hash="art-01",
            constitutional_hash="hash-a",
            dna_valid=True,
            dna_violations=(),
            dna_latency_ns=500,
            domain="privacy",
        )
        filled = judgment_to_bt(judgment, bt_syn)

        assert filled.judgment == "Decision X"
        assert filled.reasoning == "Because Y"
        assert filled.miner_uid == "miner-01"
        assert filled.dna_valid is True
        assert filled.artifact_hash == "art-01"

    def test_judgment_round_trip(self):
        original_judgment = JudgmentSynapse(
            task_id="rt-task",
            miner_uid="rt-miner",
            judgment="Original judgment",
            reasoning="Original reasoning",
            artifact_hash="orig-hash",
            constitutional_hash="const-hash",
            dna_valid=True,
            dna_violations=("warn-1",),
            dna_latency_ns=123,
            domain="test",
        )
        bt_syn = GovernanceDeliberation(
            task_id="rt-task",
            task_dag_json="{}",
            constitution_hash="const-hash",
            domain="test",
        )
        filled = judgment_to_bt(original_judgment, bt_syn)
        restored = bt_to_judgment(filled)

        assert restored.task_id == original_judgment.task_id
        assert restored.miner_uid == original_judgment.miner_uid
        assert restored.judgment == original_judgment.judgment
        assert restored.reasoning == original_judgment.reasoning
        assert restored.artifact_hash == original_judgment.artifact_hash
        assert restored.dna_valid == original_judgment.dna_valid
        assert restored.dna_violations == original_judgment.dna_violations
        assert restored.dna_latency_ns == original_judgment.dna_latency_ns


# ---------------------------------------------------------------------------
# MinerAxonServer
# ---------------------------------------------------------------------------


class TestMinerAxonServer:
    """Axon handler wrapping ConstitutionalMiner."""

    @pytest.fixture
    def constitution_path(self, tmp_path):
        content = """
name: test-adapter-constitution
rules:
  - id: safety-01
    text: Do not cause physical harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
      - danger
"""
        path = tmp_path / "constitution.yaml"
        path.write_text(content)
        return str(path)

    @pytest.fixture
    def axon_server(self, constitution_path):
        from constitutional_swarm.bittensor.axon_server import MinerAxonServer
        from constitutional_swarm.bittensor.miner import ConstitutionalMiner
        from constitutional_swarm.bittensor.protocol import MinerConfig

        async def handler(task, ctx, meta):
            return ("Governance decision made", "Sound reasoning applies")

        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="test-miner",
            ),
            deliberation_handler=handler,
        )
        return MinerAxonServer(miner)

    @pytest.mark.asyncio
    async def test_forward_fn_fills_response(self, axon_server):
        syn = GovernanceDeliberation(
            task_id="ax-task",
            task_dag_json="{}",
            constitution_hash=axon_server.miner.constitution_hash,
            domain="governance",
        )
        result = await axon_server.forward(syn)

        assert result.judgment is not None
        assert result.reasoning is not None
        assert result.artifact_hash is not None
        assert result.dna_valid is True
        assert result.miner_uid == "test-miner"

    @pytest.mark.asyncio
    async def test_forward_constitution_mismatch(self, axon_server):
        syn = GovernanceDeliberation(
            task_id="bad-task",
            task_dag_json="{}",
            constitution_hash="wrong-hash",
            domain="d",
        )
        result = await axon_server.forward(syn)

        # On mismatch, response fields stay empty and error is recorded
        assert result.judgment is None
        assert result.error_message is not None
        assert "constitution" in result.error_message.lower()

    def test_blacklist_fn_allows_known(self, axon_server):
        syn = GovernanceDeliberation(
            task_id="t",
            task_dag_json="{}",
            constitution_hash=axon_server.miner.constitution_hash,
            domain="d",
        )
        assert axon_server.blacklist(syn) is False

    def test_verify_fn_checks_required_fields(self, axon_server):
        # Missing task_id should fail verify
        syn = GovernanceDeliberation(
            task_id="",
            task_dag_json="{}",
            constitution_hash="h",
            domain="d",
        )
        with pytest.raises(ValueError, match="task_id"):
            axon_server.verify(syn)

    def test_priority_fn_uses_impact_score(self, axon_server):
        low = GovernanceDeliberation(
            task_id="low",
            task_dag_json="{}",
            constitution_hash="h",
            domain="d",
            impact_score=0.1,
        )
        high = GovernanceDeliberation(
            task_id="high",
            task_dag_json="{}",
            constitution_hash="h",
            domain="d",
            impact_score=0.9,
        )
        assert axon_server.priority(high) > axon_server.priority(low)


# ---------------------------------------------------------------------------
# ValidatorDendriteClient
# ---------------------------------------------------------------------------


class TestValidatorDendriteClient:
    """Dendrite wrapper for sending cases to miners."""

    @pytest.fixture
    def constitution_path(self, tmp_path):
        content = """
name: test-dendrite-constitution
rules:
  - id: safety-01
    text: Do not cause physical harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
"""
        path = tmp_path / "constitution.yaml"
        path.write_text(content)
        return str(path)

    @pytest.fixture
    def dendrite_client(self, constitution_path):
        from constitutional_swarm.bittensor.dendrite_client import ValidatorDendriteClient

        return ValidatorDendriteClient(constitution_path=constitution_path)

    @pytest.mark.asyncio
    async def test_local_query_returns_judgments(self, dendrite_client, constitution_path):
        """In local mode (no bittensor), query routes to local miners."""
        from constitutional_swarm.bittensor.axon_server import MinerAxonServer
        from constitutional_swarm.bittensor.miner import ConstitutionalMiner
        from constitutional_swarm.bittensor.protocol import MinerConfig

        async def handler(task, ctx, meta):
            return ("Local judgment", "Local reasoning")

        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="local-miner",
            ),
            deliberation_handler=handler,
        )
        server = MinerAxonServer(miner)
        dendrite_client.register_local_miner(server)

        delib = DeliberationSynapse(
            task_id="dendrite-test",
            task_dag_json="{}",
            constitution_hash=dendrite_client.constitution_hash,
            domain="test",
        )
        judgments = await dendrite_client.query_miners(delib)

        assert len(judgments) == 1
        assert judgments[0].judgment == "Local judgment"
        assert judgments[0].miner_uid == "local-miner"

    @pytest.mark.asyncio
    async def test_query_multiple_miners(self, dendrite_client, constitution_path):
        from constitutional_swarm.bittensor.axon_server import MinerAxonServer
        from constitutional_swarm.bittensor.miner import ConstitutionalMiner
        from constitutional_swarm.bittensor.protocol import MinerConfig

        async def handler(task, ctx, meta):
            return ("Judgment", "Reasoning")

        for i in range(3):
            miner = ConstitutionalMiner(
                config=MinerConfig(
                    constitution_path=constitution_path,
                    agent_id=f"miner-{i}",
                ),
                deliberation_handler=handler,
            )
            dendrite_client.register_local_miner(MinerAxonServer(miner))

        delib = DeliberationSynapse(
            task_id="multi-test",
            task_dag_json="{}",
            constitution_hash=dendrite_client.constitution_hash,
            domain="test",
        )
        judgments = await dendrite_client.query_miners(delib)

        assert len(judgments) == 3
        miner_uids = {j.miner_uid for j in judgments}
        assert miner_uids == {"miner-0", "miner-1", "miner-2"}

    @pytest.mark.asyncio
    async def test_query_filters_failed_responses(self, dendrite_client, constitution_path):
        """Miners that fail (constitution mismatch, etc.) are filtered out."""
        from constitutional_swarm.bittensor.axon_server import MinerAxonServer
        from constitutional_swarm.bittensor.miner import ConstitutionalMiner
        from constitutional_swarm.bittensor.protocol import MinerConfig

        async def handler(task, ctx, meta):
            return ("Good judgment", "Good reasoning")

        miner = ConstitutionalMiner(
            config=MinerConfig(
                constitution_path=constitution_path,
                agent_id="good-miner",
            ),
            deliberation_handler=handler,
        )
        dendrite_client.register_local_miner(MinerAxonServer(miner))

        # Send with wrong hash — miner should fail, result filtered
        delib = DeliberationSynapse(
            task_id="filter-test",
            task_dag_json="{}",
            constitution_hash="wrong-hash-xxx",
            domain="test",
        )
        judgments = await dendrite_client.query_miners(delib)
        assert len(judgments) == 0

    @pytest.mark.asyncio
    async def test_empty_miners_returns_empty(self, dendrite_client):
        delib = DeliberationSynapse(
            task_id="empty-test",
            task_dag_json="{}",
            constitution_hash=dendrite_client.constitution_hash,
            domain="test",
        )
        judgments = await dendrite_client.query_miners(delib)
        assert judgments == []


# ---------------------------------------------------------------------------
# End-to-End: adapter layer integration
# ---------------------------------------------------------------------------


class TestAdapterE2E:
    """Full round-trip through the adapter layer."""

    @pytest.fixture
    def constitution_path(self, tmp_path):
        content = """
name: test-e2e-constitution
rules:
  - id: safety-01
    text: Do not cause physical harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
      - danger
  - id: privacy-01
    text: Protect personal information
    severity: high
    hardcoded: true
    keywords:
      - personal data
      - PII
"""
        path = tmp_path / "constitution.yaml"
        path.write_text(content)
        return str(path)

    @pytest.mark.asyncio
    async def test_full_adapter_pipeline(self, constitution_path):
        """SN Owner -> adapter -> miner axon -> adapter -> validator."""
        from constitutional_swarm.bittensor.axon_server import MinerAxonServer
        from constitutional_swarm.bittensor.dendrite_client import ValidatorDendriteClient
        from constitutional_swarm.bittensor.miner import ConstitutionalMiner
        from constitutional_swarm.bittensor.protocol import MinerConfig, ValidatorConfig
        from constitutional_swarm.bittensor.subnet_owner import SubnetOwner
        from constitutional_swarm.bittensor.validator import ConstitutionalValidator

        # Setup
        owner = SubnetOwner(constitution_path)
        client = ValidatorDendriteClient(constitution_path=constitution_path)

        async def deliberate(task, ctx, meta):
            return (
                "Privacy takes precedence over transparency",
                "Data subject has not consented",
            )

        for i in range(3):
            miner = ConstitutionalMiner(
                config=MinerConfig(
                    constitution_path=constitution_path,
                    agent_id=f"e2e-miner-{i}",
                ),
                deliberation_handler=deliberate,
            )
            client.register_local_miner(MinerAxonServer(miner))

        validator = ConstitutionalValidator(
            config=ValidatorConfig(constitution_path=constitution_path),
        )
        for i in range(3):
            validator.register_miner(f"e2e-miner-{i}", domain="privacy")
        validator.register_miner("extra-peer")

        # Step 1: Package case
        case = owner.package_case(
            "Privacy vs transparency conflict",
            "privacy",
            impact_score=0.85,
        )

        # Step 2: Query miners through adapter
        judgments = await client.query_miners(case.synapse)
        assert len(judgments) >= 1

        # Step 3: Validate first judgment
        validation = validator.validate(judgments[0])
        assert validation.accepted is True

        # Step 4: Record result
        precedent = owner.record_result(case, judgments[0], validation)
        assert precedent is not None
        assert precedent.validation_accepted is True


# ---------------------------------------------------------------------------
# Bittensor availability flag
# ---------------------------------------------------------------------------


class TestBittensorAvailability:
    """Adapter works regardless of bittensor installation."""

    def test_has_bittensor_flag_is_bool(self):
        assert isinstance(HAS_BITTENSOR, bool)

    def test_governance_deliberation_is_pydantic(self):
        """Regardless of bittensor availability, it's a Pydantic model."""
        from pydantic import BaseModel

        assert issubclass(GovernanceDeliberation, BaseModel)
