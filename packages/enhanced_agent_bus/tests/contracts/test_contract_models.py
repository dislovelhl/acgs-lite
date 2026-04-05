"""
Tests for Agent Behavioral Contract Pydantic models.
Constitutional Hash: 608508a9bd224290

Covers:
- Default construction and field values
- Serialization / deserialization round-trips
- Field constraint enforcement (bounds on impact_score, autonomy_level)
- Constitutional hash propagation
- Full C=(P,I,G,R) composition
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.contracts.models import (
    AgentBehavioralContract,
    ContractGoals,
    ContractInstructions,
    ContractPermissions,
    ContractRestrictions,
)
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH

# ── ContractPermissions ──────────────────────────────────────────────


@pytest.mark.unit
class TestContractPermissions:
    """Tests for the Permissions (P) component."""

    def test_defaults(self) -> None:
        p = ContractPermissions()
        assert p.allowed_actions == []
        assert p.allowed_resources == []
        assert p.max_impact_score == 1.0

    def test_with_values(self) -> None:
        p = ContractPermissions(
            allowed_actions=["read", "write"],
            allowed_resources=["db:users"],
            max_impact_score=0.5,
        )
        assert p.allowed_actions == ["read", "write"]
        assert p.allowed_resources == ["db:users"]
        assert p.max_impact_score == 0.5

    def test_max_impact_score_lower_bound(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            ContractPermissions(max_impact_score=-0.1)

    def test_max_impact_score_upper_bound(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            ContractPermissions(max_impact_score=1.1)

    def test_max_impact_score_boundary_values(self) -> None:
        assert ContractPermissions(max_impact_score=0.0).max_impact_score == 0.0
        assert ContractPermissions(max_impact_score=1.0).max_impact_score == 1.0

    def test_serialization_round_trip(self) -> None:
        p = ContractPermissions(
            allowed_actions=["send_message"],
            max_impact_score=0.8,
        )
        data = p.model_dump()
        restored = ContractPermissions.model_validate(data)
        assert restored == p

    def test_json_round_trip(self) -> None:
        p = ContractPermissions(allowed_resources=["topic:alerts"])
        blob = p.model_dump_json()
        restored = ContractPermissions.model_validate_json(blob)
        assert restored == p


# ── ContractInstructions ─────────────────────────────────────────────


@pytest.mark.unit
class TestContractInstructions:
    """Tests for the Instructions (I) component."""

    def test_defaults(self) -> None:
        i = ContractInstructions()
        assert i.directives == []
        assert i.priority_order == []

    def test_with_values(self) -> None:
        i = ContractInstructions(
            directives=["always explain reasoning", "cite sources"],
            priority_order=["safety", "accuracy", "speed"],
        )
        assert len(i.directives) == 2
        assert i.priority_order[0] == "safety"

    def test_serialization_round_trip(self) -> None:
        i = ContractInstructions(
            directives=["be concise"],
            priority_order=["clarity"],
        )
        data = i.model_dump()
        restored = ContractInstructions.model_validate(data)
        assert restored == i


# ── ContractGoals ────────────────────────────────────────────────────


@pytest.mark.unit
class TestContractGoals:
    """Tests for the Goals (G) component."""

    def test_defaults(self) -> None:
        g = ContractGoals()
        assert g.objectives == []
        assert g.success_criteria == []

    def test_with_values(self) -> None:
        g = ContractGoals(
            objectives=["reduce response time"],
            success_criteria=["p99 < 5ms"],
        )
        assert g.objectives == ["reduce response time"]
        assert g.success_criteria == ["p99 < 5ms"]

    def test_serialization_round_trip(self) -> None:
        g = ContractGoals(
            objectives=["maximize accuracy"],
            success_criteria=["accuracy > 0.95"],
        )
        restored = ContractGoals.model_validate(g.model_dump())
        assert restored == g


# ── ContractRestrictions ─────────────────────────────────────────────


@pytest.mark.unit
class TestContractRestrictions:
    """Tests for the Restrictions (R) component."""

    def test_defaults(self) -> None:
        r = ContractRestrictions()
        assert r.prohibited_actions == []
        assert r.prohibited_resources == []
        assert r.max_autonomy_level == 3

    def test_with_values(self) -> None:
        r = ContractRestrictions(
            prohibited_actions=["delete_all"],
            prohibited_resources=["db:production"],
            max_autonomy_level=1,
        )
        assert r.prohibited_actions == ["delete_all"]
        assert r.prohibited_resources == ["db:production"]
        assert r.max_autonomy_level == 1

    def test_max_autonomy_level_lower_bound(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            ContractRestrictions(max_autonomy_level=-1)

    def test_max_autonomy_level_upper_bound(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 5"):
            ContractRestrictions(max_autonomy_level=6)

    def test_max_autonomy_level_boundary_values(self) -> None:
        assert ContractRestrictions(max_autonomy_level=0).max_autonomy_level == 0
        assert ContractRestrictions(max_autonomy_level=5).max_autonomy_level == 5

    def test_serialization_round_trip(self) -> None:
        r = ContractRestrictions(
            prohibited_actions=["drop_table"],
            max_autonomy_level=2,
        )
        restored = ContractRestrictions.model_validate(r.model_dump())
        assert restored == r


# ── AgentBehavioralContract ──────────────────────────────────────────


@pytest.mark.unit
class TestAgentBehavioralContract:
    """Tests for the composite C=(P,I,G,R) contract model."""

    def test_minimal_construction(self) -> None:
        c = AgentBehavioralContract(agent_id="agent-1")
        assert c.agent_id == "agent-1"
        assert c.constitutional_hash == CONSTITUTIONAL_HASH
        assert c.version == "1.0.0"
        assert c.effective_from is None
        assert c.created_at is not None

    def test_full_construction(self) -> None:
        c = AgentBehavioralContract(
            agent_id="agent-2",
            permissions=ContractPermissions(
                allowed_actions=["read"],
                max_impact_score=0.7,
            ),
            instructions=ContractInstructions(
                directives=["be helpful"],
            ),
            goals=ContractGoals(
                objectives=["assist user"],
            ),
            restrictions=ContractRestrictions(
                prohibited_actions=["self-modify"],
                max_autonomy_level=2,
            ),
            version="2.0.0",
            effective_from="2026-03-08T00:00:00Z",
        )
        assert c.permissions.allowed_actions == ["read"]
        assert c.instructions.directives == ["be helpful"]
        assert c.goals.objectives == ["assist user"]
        assert c.restrictions.prohibited_actions == ["self-modify"]
        assert c.version == "2.0.0"
        assert c.effective_from == "2026-03-08T00:00:00Z"

    def test_constitutional_hash_default_matches_system(self) -> None:
        c = AgentBehavioralContract(agent_id="agent-x")
        assert c.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_custom(self) -> None:
        custom_hash = "deadbeef12345678"  # pragma: allowlist secret
        c = AgentBehavioralContract(
            agent_id="agent-x",
            constitutional_hash=custom_hash,
        )
        assert c.constitutional_hash == custom_hash

    def test_serialization_round_trip(self) -> None:
        original = AgentBehavioralContract(
            agent_id="agent-rt",
            permissions=ContractPermissions(allowed_actions=["read", "write"]),
            restrictions=ContractRestrictions(prohibited_resources=["secret-vault"]),
        )
        data = original.model_dump()
        restored = AgentBehavioralContract.model_validate(data)
        assert restored.agent_id == original.agent_id
        assert restored.permissions == original.permissions
        assert restored.restrictions == original.restrictions
        assert restored.constitutional_hash == original.constitutional_hash

    def test_json_round_trip(self) -> None:
        original = AgentBehavioralContract(
            agent_id="agent-json",
            goals=ContractGoals(objectives=["test"]),
        )
        blob = original.model_dump_json()
        parsed = json.loads(blob)
        assert parsed["agent_id"] == "agent-json"
        assert parsed["goals"]["objectives"] == ["test"]
        restored = AgentBehavioralContract.model_validate_json(blob)
        assert restored == original

    def test_default_sub_models_are_independent(self) -> None:
        """Ensure default factories create separate instances."""
        c1 = AgentBehavioralContract(agent_id="a1")
        c2 = AgentBehavioralContract(agent_id="a2")
        c1.permissions.allowed_actions.append("write")
        assert "write" not in c2.permissions.allowed_actions

    def test_created_at_is_populated(self) -> None:
        c = AgentBehavioralContract(agent_id="agent-ts")
        assert c.created_at is not None
        assert len(c.created_at) > 0
