"""
Tests for ContractValidator and ContractRegistry.
Constitutional Hash: 608508a9bd224290

Covers:
- Permission violation detection (action not allowed, impact exceeded)
- Restriction violation detection (prohibited action/resource)
- Constitutional hash mismatch
- Valid message with matching contract passes
- Empty / unset allowed_actions means "permit all actions"
- ContractRegistry singleton lifecycle (register, get, list, unregister, clear)
- Feature flag advisory mode
"""

from __future__ import annotations

import os

import pytest

from enhanced_agent_bus.contracts.models import (
    AgentBehavioralContract,
    ContractPermissions,
    ContractRestrictions,
)
from enhanced_agent_bus.contracts.validator import (
    ContractRegistry,
    ContractValidationResult,
    ContractValidator,
    _is_abc_enabled,
)
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def validator() -> ContractValidator:
    return ContractValidator()


@pytest.fixture()
def basic_contract() -> AgentBehavioralContract:
    return AgentBehavioralContract(
        agent_id="agent-test",
        permissions=ContractPermissions(
            allowed_actions=["read", "write", "send_message"],
            allowed_resources=["db:users", "topic:alerts"],
            max_impact_score=0.8,
        ),
        restrictions=ContractRestrictions(
            prohibited_actions=["delete_all", "self_destruct"],
            prohibited_resources=["db:production_secrets"],
            max_autonomy_level=3,
        ),
    )


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """Ensure each test gets a fresh singleton."""
    ContractRegistry._reset_singleton()
    yield  # type: ignore[misc]
    ContractRegistry._reset_singleton()


# ── ContractValidationResult ─────────────────────────────────────────


@pytest.mark.unit
class TestContractValidationResult:
    """Sanity checks on the result model itself."""

    def test_default_is_valid(self) -> None:
        r = ContractValidationResult()
        assert r.valid is True
        assert r.violations == []
        assert r.warnings == []

    def test_with_violations(self) -> None:
        r = ContractValidationResult(valid=False, violations=["bad action"])
        assert r.valid is False
        assert len(r.violations) == 1


# ── ContractValidator — permission checks ────────────────────────────


@pytest.mark.unit
class TestContractValidatorPermissions:
    """Permission (P) component validation."""

    def test_allowed_action_passes(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"action": "read", "impact_score": 0.5},
            basic_contract,
        )
        assert result.valid is True
        assert result.violations == []

    def test_disallowed_action_fails(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"action": "execute_arbitrary_code"},
            basic_contract,
        )
        assert result.valid is False
        assert any("not in allowed_actions" in v for v in result.violations)

    def test_empty_allowed_actions_permits_all(
        self,
        validator: ContractValidator,
    ) -> None:
        """When allowed_actions is empty, any action is permitted."""
        contract = AgentBehavioralContract(
            agent_id="permissive",
            permissions=ContractPermissions(allowed_actions=[]),
        )
        result = validator.validate_message(
            {"action": "anything_goes"},
            contract,
        )
        assert result.valid is True

    def test_impact_score_within_limit(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"action": "read", "impact_score": 0.8},
            basic_contract,
        )
        assert result.valid is True

    def test_impact_score_exceeds_limit(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"action": "read", "impact_score": 0.9},
            basic_contract,
        )
        assert result.valid is False
        assert any("exceeds max" in v for v in result.violations)

    def test_no_impact_score_passes(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        """Missing impact_score should not trigger a violation."""
        result = validator.validate_message(
            {"action": "read"},
            basic_contract,
        )
        assert result.valid is True


# ── ContractValidator — restriction checks ───────────────────────────


@pytest.mark.unit
class TestContractValidatorRestrictions:
    """Restriction (R) component validation."""

    def test_prohibited_action_fails(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"action": "delete_all"},
            basic_contract,
        )
        assert result.valid is False
        assert any("prohibited" in v for v in result.violations)

    def test_prohibited_resource_fails(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"action": "read", "resource": "db:production_secrets"},
            basic_contract,
        )
        assert result.valid is False
        assert any("prohibited" in v for v in result.violations)

    def test_non_prohibited_resource_passes(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"action": "read", "resource": "db:public"},
            basic_contract,
        )
        assert result.valid is True

    def test_multiple_violations_collected(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        """A single message can trigger multiple violations."""
        result = validator.validate_message(
            {
                "action": "delete_all",
                "resource": "db:production_secrets",
                "impact_score": 0.95,
            },
            basic_contract,
        )
        assert result.valid is False
        assert len(result.violations) >= 2


# ── ContractValidator — constitutional hash ──────────────────────────


@pytest.mark.unit
class TestContractValidatorHash:
    """Constitutional hash validation."""

    def test_matching_hash_passes(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"constitutional_hash": CONSTITUTIONAL_HASH},
            basic_contract,
        )
        assert result.valid is True

    def test_mismatched_hash_fails(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message(
            {"constitutional_hash": "deadbeef00000000"},
            basic_contract,
        )
        assert result.valid is False
        assert any("hash mismatch" in v for v in result.violations)

    def test_absent_hash_passes(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        """No hash in message metadata means no hash check."""
        result = validator.validate_message({}, basic_contract)
        assert result.valid is True


# ── ContractValidator — edge cases ───────────────────────────────────


@pytest.mark.unit
class TestContractValidatorEdgeCases:
    """Boundary / edge-case scenarios."""

    def test_empty_metadata(
        self,
        validator: ContractValidator,
        basic_contract: AgentBehavioralContract,
    ) -> None:
        result = validator.validate_message({}, basic_contract)
        assert result.valid is True

    def test_minimal_contract_no_violations(
        self,
        validator: ContractValidator,
    ) -> None:
        """A contract with no permissions/restrictions should pass anything."""
        contract = AgentBehavioralContract(agent_id="minimal")
        result = validator.validate_message(
            {"action": "anything", "resource": "anywhere", "impact_score": 1.0},
            contract,
        )
        assert result.valid is True

    def test_action_both_allowed_and_prohibited(
        self,
        validator: ContractValidator,
    ) -> None:
        """If an action is in allowed_actions AND prohibited_actions,
        the restriction takes precedence (violation reported)."""
        contract = AgentBehavioralContract(
            agent_id="conflicting",
            permissions=ContractPermissions(allowed_actions=["dangerous_op"]),
            restrictions=ContractRestrictions(prohibited_actions=["dangerous_op"]),
        )
        result = validator.validate_message(
            {"action": "dangerous_op"},
            contract,
        )
        assert result.valid is False
        assert any("prohibited" in v for v in result.violations)


# ── ContractRegistry ─────────────────────────────────────────────────


@pytest.mark.unit
class TestContractRegistry:
    """Tests for the singleton contract registry."""

    def test_singleton_identity(self) -> None:
        r1 = ContractRegistry()
        r2 = ContractRegistry()
        assert r1 is r2

    def test_register_and_get(self) -> None:
        registry = ContractRegistry()
        contract = AgentBehavioralContract(agent_id="agent-a")
        registry.register("agent-a", contract)
        retrieved = registry.get("agent-a")
        assert retrieved is not None
        assert retrieved.agent_id == "agent-a"

    def test_get_unregistered_returns_none(self) -> None:
        registry = ContractRegistry()
        assert registry.get("nonexistent") is None

    def test_list_agents_sorted(self) -> None:
        registry = ContractRegistry()
        for name in ["charlie", "alice", "bob"]:
            registry.register(name, AgentBehavioralContract(agent_id=name))
        assert registry.list_agents() == ["alice", "bob", "charlie"]

    def test_unregister_existing(self) -> None:
        registry = ContractRegistry()
        registry.register("to-remove", AgentBehavioralContract(agent_id="to-remove"))
        assert registry.unregister("to-remove") is True
        assert registry.get("to-remove") is None

    def test_unregister_nonexistent(self) -> None:
        registry = ContractRegistry()
        assert registry.unregister("ghost") is False

    def test_register_overwrites(self) -> None:
        registry = ContractRegistry()
        v1 = AgentBehavioralContract(agent_id="agent-o", version="1.0.0")
        v2 = AgentBehavioralContract(agent_id="agent-o", version="2.0.0")
        registry.register("agent-o", v1)
        registry.register("agent-o", v2)
        assert registry.get("agent-o") is not None
        assert registry.get("agent-o").version == "2.0.0"  # type: ignore[union-attr]

    def test_clear(self) -> None:
        registry = ContractRegistry()
        registry.register("a", AgentBehavioralContract(agent_id="a"))
        registry.register("b", AgentBehavioralContract(agent_id="b"))
        registry.clear()
        assert registry.list_agents() == []

    def test_list_agents_empty(self) -> None:
        registry = ContractRegistry()
        assert registry.list_agents() == []


# ── Feature flag ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestFeatureFlag:
    """Verify the ACGS_ENABLE_ABC_CONTRACTS env var logic."""

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ACGS_ENABLE_ABC_CONTRACTS", raising=False)
        assert _is_abc_enabled() is False

    def test_enabled_with_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACGS_ENABLE_ABC_CONTRACTS", "true")
        assert _is_abc_enabled() is True

    def test_enabled_with_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACGS_ENABLE_ABC_CONTRACTS", "1")
        assert _is_abc_enabled() is True

    def test_enabled_with_yes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACGS_ENABLE_ABC_CONTRACTS", "yes")
        assert _is_abc_enabled() is True

    def test_disabled_with_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACGS_ENABLE_ABC_CONTRACTS", "false")
        assert _is_abc_enabled() is False

    def test_disabled_with_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ACGS_ENABLE_ABC_CONTRACTS", "")
        assert _is_abc_enabled() is False
