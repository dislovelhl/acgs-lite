"""
Tests for Constitutional Invariant System
Constitutional Hash: 608508a9bd224290

Tests for invariant models, predicate functions, hash determinism,
and the default manifest factory.
"""

from __future__ import annotations

import pytest

from ..invariants import (
    ChangeClassification,
    EnforcementMode,
    InvariantCheckResult,
    InvariantDefinition,
    InvariantManifest,
    InvariantScope,
    check_append_only_audit,
    check_constitutional_hash_required,
    check_fail_closed,
    check_human_approval_for_activation,
    check_maci_separation,
    check_tenant_isolation,
    get_default_manifest,
)

pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.unit,
]


# ---------------------------------------------------------------------------
# Model serialization / deserialization
# ---------------------------------------------------------------------------


class TestInvariantScope:
    """Test InvariantScope enum."""

    def test_values(self):
        assert InvariantScope.HARD == "hard"
        assert InvariantScope.META == "meta"
        assert InvariantScope.SOFT == "soft"

    def test_from_string(self):
        assert InvariantScope("hard") is InvariantScope.HARD


class TestEnforcementMode:
    """Test EnforcementMode enum."""

    def test_values(self):
        assert EnforcementMode.PRE_PROPOSAL == "pre_proposal"
        assert EnforcementMode.PRE_ACTIVATION == "pre_activation"
        assert EnforcementMode.RUNTIME == "runtime"


class TestInvariantCheckResult:
    """Test InvariantCheckResult model."""

    def test_create_passing(self):
        result = InvariantCheckResult(passed=True, invariant_id="INV-001", message="ok")
        assert result.passed is True
        assert result.invariant_id == "INV-001"
        assert result.message == "ok"

    def test_create_failing(self):
        result = InvariantCheckResult(passed=False, invariant_id="INV-002", message="violation")
        assert result.passed is False

    def test_default_message(self):
        result = InvariantCheckResult(passed=True, invariant_id="INV-001")
        assert result.message == ""

    def test_roundtrip(self):
        original = InvariantCheckResult(passed=True, invariant_id="INV-003", message="verified")
        data = original.model_dump()
        restored = InvariantCheckResult.model_validate(data)
        assert restored == original


class TestInvariantDefinition:
    """Test InvariantDefinition model."""

    def test_create(self):
        defn = InvariantDefinition(
            invariant_id="INV-001",
            name="Test Invariant",
            scope=InvariantScope.HARD,
            description="A test invariant",
            enforcement_modes=[EnforcementMode.RUNTIME],
            predicate_module="some.module.check",
        )
        assert defn.invariant_id == "INV-001"
        assert defn.scope is InvariantScope.HARD
        assert defn.protected_paths == []

    def test_with_protected_paths(self):
        defn = InvariantDefinition(
            invariant_id="INV-002",
            name="Test",
            scope=InvariantScope.SOFT,
            description="desc",
            protected_paths=["path/a.py", "path/b.py"],
            enforcement_modes=[EnforcementMode.PRE_PROPOSAL],
            predicate_module="mod.check",
        )
        assert len(defn.protected_paths) == 2

    def test_roundtrip(self):
        original = InvariantDefinition(
            invariant_id="INV-001",
            name="Test",
            scope=InvariantScope.META,
            description="desc",
            protected_paths=["a.py"],
            enforcement_modes=[
                EnforcementMode.PRE_PROPOSAL,
                EnforcementMode.RUNTIME,
            ],
            predicate_module="mod.fn",
        )
        data = original.model_dump()
        restored = InvariantDefinition.model_validate(data)
        assert restored == original


class TestChangeClassification:
    """Test ChangeClassification model."""

    def test_not_touching(self):
        cc = ChangeClassification(
            touches_invariants=False,
            blocked=False,
        )
        assert cc.touches_invariants is False
        assert cc.touched_invariant_ids == []
        assert cc.requires_refoundation is False
        assert cc.reason is None

    def test_blocked_hard_invariant(self):
        cc = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=["INV-001", "INV-002"],
            blocked=True,
            requires_refoundation=True,
            reason="Change modifies HARD invariant boundaries",
        )
        assert cc.blocked is True
        assert cc.requires_refoundation is True
        assert len(cc.touched_invariant_ids) == 2

    def test_roundtrip(self):
        original = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=["INV-005"],
            blocked=False,
            reason="SOFT invariant, extra review required",
        )
        data = original.model_dump()
        restored = ChangeClassification.model_validate(data)
        assert restored == original


# ---------------------------------------------------------------------------
# InvariantManifest and hash determinism
# ---------------------------------------------------------------------------


class TestInvariantManifest:
    """Test InvariantManifest model and hash computation."""

    def _make_invariant(self, inv_id: str = "INV-T01") -> InvariantDefinition:
        return InvariantDefinition(
            invariant_id=inv_id,
            name=f"Test {inv_id}",
            scope=InvariantScope.HARD,
            description="test",
            enforcement_modes=[EnforcementMode.RUNTIME],
            predicate_module="mod.check",
        )

    def test_create_empty(self):
        manifest = InvariantManifest(constitutional_hash="608508a9bd224290")
        assert manifest.manifest_version == "1.0.0"
        assert manifest.constitutional_hash == "608508a9bd224290"
        assert manifest.invariant_hash != ""

    def test_hash_deterministic(self):
        """Same invariants must produce the same hash."""
        inv = self._make_invariant()
        m1 = InvariantManifest(
            constitutional_hash="abc",
            invariants=[inv],
        )
        m2 = InvariantManifest(
            constitutional_hash="abc",
            invariants=[inv],
        )
        assert m1.invariant_hash == m2.invariant_hash

    def test_hash_changes_on_different_invariants(self):
        """Different invariants must produce different hashes."""
        inv_a = self._make_invariant("INV-A")
        inv_b = self._make_invariant("INV-B")
        m1 = InvariantManifest(
            constitutional_hash="abc",
            invariants=[inv_a],
        )
        m2 = InvariantManifest(
            constitutional_hash="abc",
            invariants=[inv_b],
        )
        assert m1.invariant_hash != m2.invariant_hash

    def test_hash_order_independent(self):
        """Invariant order should not affect the hash (sorted internally)."""
        inv_a = self._make_invariant("INV-A")
        inv_b = self._make_invariant("INV-B")
        m1 = InvariantManifest(
            constitutional_hash="abc",
            invariants=[inv_a, inv_b],
        )
        m2 = InvariantManifest(
            constitutional_hash="abc",
            invariants=[inv_b, inv_a],
        )
        assert m1.invariant_hash == m2.invariant_hash

    def test_roundtrip(self):
        inv = self._make_invariant()
        original = InvariantManifest(
            constitutional_hash="608508a9bd224290",
            invariants=[inv],
        )
        data = original.model_dump()
        restored = InvariantManifest.model_validate(data)
        assert restored.invariant_hash == original.invariant_hash
        assert len(restored.invariants) == 1

    def test_explicit_hash_mismatch_raises(self):
        """If invariant_hash is provided but doesn't match content, raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Invariant hash mismatch"):
            InvariantManifest(
                constitutional_hash="abc",
                invariant_hash="wrong_hash_value",
                invariants=[],
            )

    def test_explicit_hash_correct_accepted(self):
        """If invariant_hash matches computed hash, it is accepted."""
        # First compute the correct hash for empty invariants
        m = InvariantManifest(constitutional_hash="abc", invariants=[])
        correct_hash = m.invariant_hash
        # Now create with explicit matching hash
        m2 = InvariantManifest(
            constitutional_hash="abc",
            invariant_hash=correct_hash,
            invariants=[],
        )
        assert m2.invariant_hash == correct_hash


# ---------------------------------------------------------------------------
# Predicate functions — passing cases
# ---------------------------------------------------------------------------


class TestMACISeparation:
    """Test check_maci_separation predicate."""

    def test_pass_distinct_roles(self):
        result = check_maci_separation(
            state={},
            change={
                "proposer_id": "agent-A",
                "validator_id": "agent-B",
                "executor_id": "agent-C",
            },
        )
        assert result.passed is True
        assert result.invariant_id == "INV-001"

    def test_fail_empty_roles(self):
        """Empty/missing roles must fail — all three required for MACI verification."""
        result = check_maci_separation(state={}, change={})
        assert result.passed is False
        assert "all three roles" in result.message.lower()

    def test_fail_proposer_equals_validator(self):
        result = check_maci_separation(
            state={},
            change={
                "proposer_id": "agent-A",
                "validator_id": "agent-A",
                "executor_id": "agent-C",
            },
        )
        assert result.passed is False
        assert "MACI separation violated" in result.message

    def test_fail_validator_equals_executor(self):
        result = check_maci_separation(
            state={},
            change={
                "proposer_id": "agent-A",
                "validator_id": "agent-B",
                "executor_id": "agent-B",
            },
        )
        assert result.passed is False

    def test_fail_all_same(self):
        result = check_maci_separation(
            state={},
            change={
                "proposer_id": "agent-X",
                "validator_id": "agent-X",
                "executor_id": "agent-X",
            },
        )
        assert result.passed is False


class TestFailClosed:
    """Test check_fail_closed predicate."""

    def test_pass_default(self):
        result = check_fail_closed(state={}, change={})
        assert result.passed is True

    def test_pass_on_error_deny(self):
        result = check_fail_closed(state={}, change={"on_error": "deny"})
        assert result.passed is True

    def test_fail_on_error_allow(self):
        result = check_fail_closed(state={}, change={"on_error": "allow"})
        assert result.passed is False
        assert "on_error is 'allow'" in result.message

    def test_fail_governance_bypass(self):
        result = check_fail_closed(state={}, change={"governance_bypass": True})
        assert result.passed is False
        assert "governance_bypass" in result.message


class TestAppendOnlyAudit:
    """Test check_append_only_audit predicate."""

    def test_pass_no_audit_op(self):
        result = check_append_only_audit(state={}, change={})
        assert result.passed is True

    def test_pass_append(self):
        result = check_append_only_audit(state={}, change={"audit_operation": "append"})
        assert result.passed is True

    def test_fail_delete(self):
        result = check_append_only_audit(state={}, change={"audit_operation": "delete"})
        assert result.passed is False

    def test_fail_update(self):
        result = check_append_only_audit(state={}, change={"audit_operation": "update"})
        assert result.passed is False

    def test_fail_truncate(self):
        result = check_append_only_audit(state={}, change={"audit_operation": "truncate"})
        assert result.passed is False

    def test_fail_drop(self):
        result = check_append_only_audit(state={}, change={"audit_operation": "drop"})
        assert result.passed is False


class TestConstitutionalHashRequired:
    """Test check_constitutional_hash_required predicate."""

    def test_pass_matching_hash(self):
        result = check_constitutional_hash_required(
            state={"constitutional_hash": "608508a9bd224290"},
            change={"constitutional_hash": "608508a9bd224290"},
        )
        assert result.passed is True

    def test_pass_no_expected_hash(self):
        """When state has no hash, any provided hash passes."""
        result = check_constitutional_hash_required(
            state={},
            change={"constitutional_hash": "some_hash"},
        )
        assert result.passed is True

    def test_fail_missing_hash(self):
        result = check_constitutional_hash_required(
            state={"constitutional_hash": "608508a9bd224290"},
            change={},
        )
        assert result.passed is False
        assert "missing" in result.message.lower()

    def test_fail_mismatched_hash(self):
        result = check_constitutional_hash_required(
            state={"constitutional_hash": "608508a9bd224290"},
            change={"constitutional_hash": "wrong_hash"},
        )
        assert result.passed is False
        assert "mismatch" in result.message.lower()


class TestTenantIsolation:
    """Test check_tenant_isolation predicate."""

    def test_pass_same_tenant(self):
        result = check_tenant_isolation(
            state={},
            change={
                "source_tenant_id": "tenant-1",
                "target_tenant_id": "tenant-1",
            },
        )
        assert result.passed is True

    def test_pass_no_tenants(self):
        result = check_tenant_isolation(state={}, change={})
        assert result.passed is True

    def test_pass_only_source(self):
        result = check_tenant_isolation(state={}, change={"source_tenant_id": "tenant-1"})
        assert result.passed is True

    def test_fail_cross_tenant(self):
        result = check_tenant_isolation(
            state={},
            change={
                "source_tenant_id": "tenant-1",
                "target_tenant_id": "tenant-2",
            },
        )
        assert result.passed is False
        assert "tenant-1" in result.message
        assert "tenant-2" in result.message


class TestHumanApproval:
    """Test check_human_approval_for_activation predicate."""

    def test_pass_not_activation(self):
        result = check_human_approval_for_activation(state={}, change={})
        assert result.passed is True

    def test_pass_activation_with_approval(self):
        result = check_human_approval_for_activation(
            state={},
            change={"is_activation": True, "human_approved": True},
        )
        assert result.passed is True

    def test_fail_activation_without_approval(self):
        result = check_human_approval_for_activation(
            state={},
            change={"is_activation": True, "human_approved": False},
        )
        assert result.passed is False
        assert "human approval" in result.message.lower()

    def test_fail_activation_missing_approval(self):
        result = check_human_approval_for_activation(
            state={},
            change={"is_activation": True},
        )
        assert result.passed is False


# ---------------------------------------------------------------------------
# Default manifest factory
# ---------------------------------------------------------------------------


class TestGetDefaultManifest:
    """Test get_default_manifest factory."""

    def test_returns_six_invariants(self):
        manifest = get_default_manifest()
        assert len(manifest.invariants) == 6

    def test_constitutional_hash(self):
        manifest = get_default_manifest()
        assert manifest.constitutional_hash == "608508a9bd224290"

    def test_invariant_ids(self):
        manifest = get_default_manifest()
        ids = {inv.invariant_id for inv in manifest.invariants}
        expected = {f"INV-00{i}" for i in range(1, 7)}
        assert ids == expected

    def test_all_have_enforcement_modes(self):
        manifest = get_default_manifest()
        for inv in manifest.invariants:
            assert len(inv.enforcement_modes) >= 1

    def test_all_have_predicate_modules(self):
        manifest = get_default_manifest()
        for inv in manifest.invariants:
            assert inv.predicate_module.startswith("enhanced_agent_bus.constitutional.invariants.")

    def test_hard_and_meta_scopes(self):
        manifest = get_default_manifest()
        scopes = {inv.scope for inv in manifest.invariants}
        assert InvariantScope.HARD in scopes
        assert InvariantScope.META in scopes

    def test_hash_is_stable(self):
        """Two calls must produce the same invariant hash."""
        m1 = get_default_manifest()
        m2 = get_default_manifest()
        assert m1.invariant_hash == m2.invariant_hash

    def test_manifest_version(self):
        manifest = get_default_manifest()
        assert manifest.manifest_version == "1.0.0"


# ---------------------------------------------------------------------------
# Integration: ChangeClassification with invariants
# ---------------------------------------------------------------------------


class TestChangeClassificationBlocking:
    """Test ChangeClassification blocked behavior with HARD invariants."""

    def test_blocked_when_hard_invariant_touched(self):
        cc = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=["INV-001"],
            blocked=True,
            requires_refoundation=True,
            reason="Modifies MACI separation — HARD invariant",
        )
        assert cc.blocked is True
        assert cc.requires_refoundation is True
        assert "INV-001" in cc.touched_invariant_ids

    def test_not_blocked_when_no_invariants_touched(self):
        cc = ChangeClassification(
            touches_invariants=False,
            blocked=False,
        )
        assert cc.blocked is False
        assert cc.requires_refoundation is False

    def test_soft_invariant_not_blocked(self):
        cc = ChangeClassification(
            touches_invariants=True,
            touched_invariant_ids=["INV-SOFT-001"],
            blocked=False,
            requires_refoundation=False,
            reason="SOFT invariant — extra review required but not blocked",
        )
        assert cc.blocked is False
        assert cc.touches_invariants is True
