"""Tests for acgs_lite.maci — MACI separation of powers enforcement.

Covers: MACIRole, ActionRiskTier, EscalationTier, recommend_escalation,
MACIEnforcer, DomainScopedRole, DomainRoleRegistry, DerivedRole,
DelegationGrant, DelegationRegistry.
"""

from __future__ import annotations

import pytest

from acgs_lite.errors import MACIViolationError
from acgs_lite.maci import (
    ActionRiskTier,
    DelegationGrant,
    DelegationRegistry,
    DerivedRole,
    DomainRoleRegistry,
    DomainScopedRole,
    EscalationTier,
    MACIEnforcer,
    MACIRole,
    recommend_escalation,
)


# ---------------------------------------------------------------------------
# MACIRole enum
# ---------------------------------------------------------------------------
class TestMACIRole:
    def test_values(self):
        assert MACIRole.PROPOSER.value == "proposer"
        assert MACIRole.VALIDATOR.value == "validator"
        assert MACIRole.EXECUTOR.value == "executor"
        assert MACIRole.OBSERVER.value == "observer"

    def test_is_str_enum(self):
        assert isinstance(MACIRole.PROPOSER, str)


# ---------------------------------------------------------------------------
# ActionRiskTier
# ---------------------------------------------------------------------------
class TestActionRiskTier:
    def test_values(self):
        assert ActionRiskTier.LOW.value == "low"
        assert ActionRiskTier.CRITICAL.value == "critical"

    def test_escalation_path_property(self):
        assert ActionRiskTier.LOW.escalation_path == "auto_approve"
        assert ActionRiskTier.MEDIUM.escalation_path == "supervisor_notify"
        assert ActionRiskTier.HIGH.escalation_path == "human_review_queue"
        assert ActionRiskTier.CRITICAL.escalation_path == "governance_lead_immediate"


# ---------------------------------------------------------------------------
# recommend_escalation
# ---------------------------------------------------------------------------
class TestRecommendEscalation:
    def test_low_everything(self):
        result = recommend_escalation("low", 0.0, "low")
        assert result["tier"] == EscalationTier.TIER_0_AUTO.value
        assert result["requires_human"] is False

    def test_critical_severity_high_action(self):
        result = recommend_escalation("critical", 0.5, "critical")
        assert result["tier"] == EscalationTier.TIER_4_BLOCK.value
        assert result["requires_human"] is True
        assert result["sla"] == "immediate"

    def test_medium_severity_medium_action(self):
        result = recommend_escalation("medium", 0.3, "medium")
        # combined = 1 + 1 + 0.9 = 2.9 => tier_1
        assert result["tier"] == EscalationTier.TIER_1_NOTIFY.value

    def test_high_severity_zero_context(self):
        result = recommend_escalation("high", 0.0, "high")
        # combined = 2 + 2 + 0 = 4 => tier_2
        assert result["tier"] == EscalationTier.TIER_2_REVIEW.value
        assert result["requires_human"] is True

    def test_critical_severity_full_context(self):
        result = recommend_escalation("critical", 1.0, "high")
        # combined = 3 + 2 + 3 = 8 => tier_4
        assert result["tier"] == EscalationTier.TIER_4_BLOCK.value

    def test_unknown_severity_defaults_zero(self):
        result = recommend_escalation("unknown", 0.0, "low")
        # combined = 0 + 0 + 0 = 0 => tier_0
        assert result["tier"] == EscalationTier.TIER_0_AUTO.value


# ---------------------------------------------------------------------------
# MACIEnforcer
# ---------------------------------------------------------------------------
class TestMACIEnforcer:
    def test_assign_and_get_role(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("a1", MACIRole.PROPOSER)
        assert enforcer.get_role("a1") == MACIRole.PROPOSER

    def test_get_role_unassigned(self):
        enforcer = MACIEnforcer()
        assert enforcer.get_role("unknown") is None

    def test_check_allowed_action(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("a1", MACIRole.PROPOSER)
        assert enforcer.check("a1", "propose") is True

    def test_check_denied_action_raises(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("a1", MACIRole.PROPOSER)
        with pytest.raises(MACIViolationError) as exc_info:
            enforcer.check("a1", "validate")
        assert exc_info.value.actor_role == "proposer"
        assert exc_info.value.attempted_action == "validate"

    def test_validator_cannot_execute(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("v1", MACIRole.VALIDATOR)
        with pytest.raises(MACIViolationError):
            enforcer.check("v1", "execute")

    def test_executor_cannot_validate(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("e1", MACIRole.EXECUTOR)
        with pytest.raises(MACIViolationError):
            enforcer.check("e1", "validate")

    def test_observer_cannot_propose(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("o1", MACIRole.OBSERVER)
        with pytest.raises(MACIViolationError):
            enforcer.check("o1", "propose")

    def test_unassigned_agent_treated_as_observer(self):
        enforcer = MACIEnforcer()
        assert enforcer.check("unregistered", "read") is True
        with pytest.raises(MACIViolationError):
            enforcer.check("unregistered", "execute")

    def test_query_literal_is_allowed_but_query_phrase_is_denied(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("a1", MACIRole.PROPOSER)
        assert enforcer.check("a1", "query") is True
        with pytest.raises(MACIViolationError):
            enforcer.check("a1", "query secrets")

    def test_check_no_self_validation_different_agents(self):
        enforcer = MACIEnforcer()
        assert enforcer.check_no_self_validation("a1", "a2") is True

    def test_check_no_self_validation_same_agent_raises(self):
        enforcer = MACIEnforcer()
        with pytest.raises(MACIViolationError) as exc_info:
            enforcer.check_no_self_validation("a1", "a1")
        assert "self-validate" in exc_info.value.attempted_action

    def test_role_assignments_property(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("a1", MACIRole.PROPOSER)
        enforcer.assign_role("a2", MACIRole.VALIDATOR)
        assignments = enforcer.role_assignments
        assert assignments == {"a1": "proposer", "a2": "validator"}

    def test_summary(self):
        enforcer = MACIEnforcer()
        enforcer.assign_role("a1", MACIRole.PROPOSER)
        enforcer.check("a1", "propose")
        summary = enforcer.summary()
        assert summary["agents"] == 1
        assert summary["checks_total"] >= 1

    def test_classify_action_risk_critical(self):
        enforcer = MACIEnforcer()
        result = enforcer.classify_action_risk("self-validate the output")
        assert result["risk_tier"] == "critical"

    def test_classify_action_risk_high(self):
        enforcer = MACIEnforcer()
        result = enforcer.classify_action_risk("deploy to production cluster")
        assert result["risk_tier"] == "high"

    def test_classify_action_risk_medium(self):
        enforcer = MACIEnforcer()
        result = enforcer.classify_action_risk("modify config settings")
        assert result["risk_tier"] == "medium"

    def test_classify_action_risk_low(self):
        enforcer = MACIEnforcer()
        result = enforcer.classify_action_risk("read the document")
        assert result["risk_tier"] == "low"
        assert result["matched_signal"] == ""

    def test_classify_action_risk_bypass_governance(self):
        enforcer = MACIEnforcer()
        result = enforcer.classify_action_risk("bypass validation checks")
        assert result["risk_tier"] == "critical"

    def test_classify_action_risk_password(self):
        enforcer = MACIEnforcer()
        result = enforcer.classify_action_risk("expose password in logs")
        assert result["risk_tier"] == "critical"


# ---------------------------------------------------------------------------
# DomainScopedRole
# ---------------------------------------------------------------------------
class TestDomainScopedRole:
    def test_can_act_in_assigned_domain(self):
        scoped = DomainScopedRole("a1", MACIRole.PROPOSER, ["finance"])
        assert scoped.can_act_in("finance") is True

    def test_cannot_act_in_other_domain(self):
        scoped = DomainScopedRole("a1", MACIRole.PROPOSER, ["finance"])
        assert scoped.can_act_in("healthcare") is False

    def test_empty_domains_means_unrestricted(self):
        scoped = DomainScopedRole("a1", MACIRole.PROPOSER, [])
        assert scoped.can_act_in("anything") is True

    def test_case_insensitive(self):
        scoped = DomainScopedRole("a1", MACIRole.PROPOSER, ["Finance"])
        assert scoped.can_act_in("finance") is True

    def test_to_dict(self):
        scoped = DomainScopedRole("a1", MACIRole.PROPOSER, ["finance"])
        d = scoped.to_dict()
        assert d["agent_id"] == "a1"
        assert d["role"] == "proposer"
        assert d["domains"] == ["finance"]

    def test_repr(self):
        scoped = DomainScopedRole("a1", MACIRole.PROPOSER, ["finance"])
        assert "a1" in repr(scoped)


# ---------------------------------------------------------------------------
# DomainRoleRegistry
# ---------------------------------------------------------------------------
class TestDomainRoleRegistry:
    def test_assign_and_get(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        scoped = reg.get("a1")
        assert scoped is not None
        assert scoped.role == MACIRole.PROPOSER

    def test_check_allowed(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        result = reg.check("a1", "propose", domain="finance")
        assert result["allowed"] is True

    def test_check_cross_domain_violation(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        result = reg.check("a1", "propose", domain="healthcare")
        assert result["allowed"] is False
        assert "cross-domain" in result["reason"]

    def test_check_role_violation(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        result = reg.check("a1", "validate", domain="finance")
        assert result["allowed"] is False
        assert "role violation" in result["reason"]

    def test_check_unknown_action_is_denied(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        result = reg.check("a1", "delete", domain="finance")
        assert result["allowed"] is False
        assert "role violation" in result["reason"]

    def test_check_query_phrase_is_denied(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        result = reg.check("a1", "query secrets", domain="finance")
        assert result["allowed"] is False
        assert "role violation" in result["reason"]

    def test_check_unregistered_agent(self):
        reg = DomainRoleRegistry()
        result = reg.check("unknown", "read", domain="finance")
        assert result["allowed"] is False
        assert "not registered" in result["reason"]

    def test_check_no_domain_constraint(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        result = reg.check("a1", "propose", domain="")
        assert result["allowed"] is True

    def test_isolation_report(self):
        reg = DomainRoleRegistry()
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        reg.assign("a2", MACIRole.VALIDATOR, domains=["healthcare"])
        reg.assign("a3", MACIRole.EXECUTOR, domains=[])
        report = reg.isolation_report()
        assert report["total_agents"] == 3
        assert "finance" in report["domains"]
        assert "healthcare" in report["domains"]
        assert "a3" in report["cross_domain_risk"]

    def test_len_and_repr(self):
        reg = DomainRoleRegistry()
        assert len(reg) == 0
        reg.assign("a1", MACIRole.PROPOSER, domains=["finance"])
        assert len(reg) == 1
        assert "1 agents" in repr(reg)


# ---------------------------------------------------------------------------
# DerivedRole
# ---------------------------------------------------------------------------
class TestDerivedRole:
    def test_single_base_role_permissions(self):
        derived = DerivedRole("test", [MACIRole.PROPOSER])
        assert derived.can_perform("propose") is True
        assert derived.can_perform("validate") is False

    def test_composed_permissions(self):
        derived = DerivedRole("senior", [MACIRole.PROPOSER, MACIRole.VALIDATOR])
        assert derived.can_perform("propose") is True
        assert derived.can_perform("validate") is True

    def test_deny_override(self):
        derived = DerivedRole(
            "restricted",
            [MACIRole.PROPOSER, MACIRole.VALIDATOR],
            deny_override={"execute", "deploy"},
        )
        assert derived.can_perform("execute") is False

    def test_allow_override(self):
        derived = DerivedRole(
            "special",
            [MACIRole.OBSERVER],
            allow_override={"execute"},
        )
        assert derived.can_perform("execute") is True

    def test_denials_win_over_permissions(self):
        # execute is denied by shared denials of proposer+validator (no, actually
        # both deny execute so shared_denials includes execute)
        derived = DerivedRole("combo", [MACIRole.PROPOSER, MACIRole.VALIDATOR])
        assert derived.can_perform("execute") is False

    def test_check_returns_structured_verdict(self):
        derived = DerivedRole("test", [MACIRole.PROPOSER])
        result = derived.check("propose")
        assert result["allowed"] is True
        assert result["derived_role"] == "test"
        assert "inherited:proposer" in result["source"]

    def test_check_denied_action(self):
        derived = DerivedRole("test", [MACIRole.PROPOSER], deny_override={"draft"})
        result = derived.check("draft")
        assert result["allowed"] is False
        assert "denied:override" in result["source"]

    def test_check_not_found(self):
        derived = DerivedRole("test", [MACIRole.PROPOSER])
        result = derived.check("completely_unknown_action")
        assert result["allowed"] is False
        assert result["source"] == "not_found"

    def test_check_query_phrase_is_not_treated_as_query_permission(self):
        derived = DerivedRole("test", [MACIRole.PROPOSER])
        result = derived.check("query secrets")
        assert result["allowed"] is False
        assert result["source"] == "not_found"

    def test_to_dict(self):
        derived = DerivedRole("test", [MACIRole.PROPOSER])
        d = derived.to_dict()
        assert d["name"] == "test"
        assert "proposer" in d["base_roles"]
        assert isinstance(d["permissions"], list)
        assert isinstance(d["denials"], list)

    def test_repr(self):
        derived = DerivedRole("test", [MACIRole.PROPOSER])
        assert "test" in repr(derived)

    def test_empty_base_roles(self):
        derived = DerivedRole("empty", [])
        assert derived.can_perform("propose") is False
        assert len(derived.permissions) == 0


# ---------------------------------------------------------------------------
# DelegationGrant
# ---------------------------------------------------------------------------
class TestDelegationGrant:
    def test_is_active_default(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["SAFE-*"],
        )
        assert grant.is_active() is True
        assert grant.revoked is False

    def test_is_expired_no_expiry(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["*"],
        )
        assert grant.is_expired() is False

    def test_is_expired_past_expiry(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["*"],
            expires_at="2020-01-01T00:00:00+00:00",
        )
        assert grant.is_expired() is True
        assert grant.is_active() is False

    def test_covers_scope_exact(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["SAFE-001"],
        )
        assert grant.covers_scope("SAFE-001") is True
        assert grant.covers_scope("SAFE-002") is False

    def test_covers_scope_wildcard(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["SAFE-*"],
        )
        assert grant.covers_scope("SAFE-001") is True
        assert grant.covers_scope("PII-001") is False

    def test_covers_scope_global(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["*"],
        )
        assert grant.covers_scope("anything") is True

    def test_can_redelegate(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["*"],
            max_depth=1,
            depth=0,
        )
        assert grant.can_redelegate() is True

    def test_cannot_redelegate_at_max(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["*"],
            max_depth=1,
            depth=1,
        )
        assert grant.can_redelegate() is False

    def test_to_dict(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["SAFE-*"],
        )
        d = grant.to_dict()
        assert d["grant_id"] == "DLG-1"
        assert d["is_active"] is True
        assert d["can_redelegate"] is False

    def test_repr(self):
        grant = DelegationGrant(
            grant_id="DLG-1",
            grantor_id="admin",
            grantee_id="user1",
            scopes=["*"],
        )
        assert "DLG-1" in repr(grant)
        assert "active" in repr(grant)


# ---------------------------------------------------------------------------
# DelegationRegistry
# ---------------------------------------------------------------------------
class TestDelegationRegistry:
    def test_delegate_creates_grant(self):
        reg = DelegationRegistry()
        grant = reg.delegate(
            grantor_id="admin",
            grantee_id="user1",
            scopes=["SAFE-*"],
        )
        assert grant.grant_id == "DLG-00001"
        assert grant.grantor_id == "admin"
        assert grant.grantee_id == "user1"

    def test_delegate_self_raises(self):
        reg = DelegationRegistry()
        with pytest.raises(ValueError, match="Cannot delegate authority to self"):
            reg.delegate(grantor_id="admin", grantee_id="admin", scopes=["*"])

    def test_delegate_empty_scopes_raises(self):
        reg = DelegationRegistry()
        with pytest.raises(ValueError, match="at least one scope"):
            reg.delegate(grantor_id="admin", grantee_id="user1", scopes=[])

    def test_check_authority_authorized(self):
        reg = DelegationRegistry()
        reg.delegate(grantor_id="admin", grantee_id="user1", scopes=["SAFE-*"])
        result = reg.check_authority("user1", scope="SAFE-001")
        assert result["authorized"] is True

    def test_check_authority_not_authorized(self):
        reg = DelegationRegistry()
        result = reg.check_authority("nobody", scope="SAFE-001")
        assert result["authorized"] is False

    def test_redelegate(self):
        reg = DelegationRegistry()
        parent = reg.delegate(
            grantor_id="admin",
            grantee_id="lead",
            scopes=["SAFE-*"],
            max_depth=1,
        )
        child = reg.redelegate(
            parent_grant_id=parent.grant_id,
            grantee_id="analyst",
            scopes=["SAFE-*"],
        )
        assert child.depth == 1
        assert child.parent_grant_id == parent.grant_id
        result = reg.check_authority("analyst", scope="SAFE-001")
        assert result["authorized"] is True

    def test_redelegate_exceeds_depth_raises(self):
        reg = DelegationRegistry()
        parent = reg.delegate(
            grantor_id="admin",
            grantee_id="lead",
            scopes=["*"],
            max_depth=0,
        )
        with pytest.raises(ValueError, match="cannot re-delegate"):
            reg.redelegate(
                parent_grant_id=parent.grant_id,
                grantee_id="analyst",
            )

    def test_redelegate_same_grantee_raises(self):
        reg = DelegationRegistry()
        parent = reg.delegate(
            grantor_id="admin",
            grantee_id="lead",
            scopes=["*"],
            max_depth=1,
        )
        with pytest.raises(ValueError, match="same grantee"):
            reg.redelegate(
                parent_grant_id=parent.grant_id,
                grantee_id="lead",
            )

    def test_redelegate_scope_violation_raises(self):
        reg = DelegationRegistry()
        parent = reg.delegate(
            grantor_id="admin",
            grantee_id="lead",
            scopes=["SAFE-*"],
            max_depth=1,
        )
        with pytest.raises(ValueError, match="not covered"):
            reg.redelegate(
                parent_grant_id=parent.grant_id,
                grantee_id="analyst",
                scopes=["PII-*"],
            )

    def test_revoke_single(self):
        reg = DelegationRegistry()
        grant = reg.delegate(grantor_id="admin", grantee_id="user1", scopes=["*"])
        count = reg.revoke(grant.grant_id, reason="test")
        assert count == 1
        assert grant.revoked is True

    def test_revoke_cascade(self):
        reg = DelegationRegistry()
        parent = reg.delegate(
            grantor_id="admin",
            grantee_id="lead",
            scopes=["*"],
            max_depth=1,
        )
        child = reg.redelegate(
            parent_grant_id=parent.grant_id,
            grantee_id="analyst",
        )
        count = reg.revoke(parent.grant_id, reason="cascade test", cascade=True)
        assert count == 2
        assert parent.revoked is True
        assert child.revoked is True

    def test_revoke_already_revoked_returns_zero(self):
        reg = DelegationRegistry()
        grant = reg.delegate(grantor_id="admin", grantee_id="user1", scopes=["*"])
        reg.revoke(grant.grant_id)
        count = reg.revoke(grant.grant_id)
        assert count == 0

    def test_revoke_unknown_raises(self):
        reg = DelegationRegistry()
        with pytest.raises(KeyError):
            reg.revoke("DLG-99999")

    def test_grants_for_and_by(self):
        reg = DelegationRegistry()
        reg.delegate(grantor_id="admin", grantee_id="user1", scopes=["*"])
        assert len(reg.grants_for("user1")) == 1
        assert len(reg.grants_by("admin")) == 1
        assert len(reg.grants_for("admin")) == 0

    def test_delegation_tree(self):
        reg = DelegationRegistry()
        parent = reg.delegate(
            grantor_id="admin",
            grantee_id="lead",
            scopes=["*"],
            max_depth=1,
        )
        reg.redelegate(
            parent_grant_id=parent.grant_id,
            grantee_id="analyst",
        )
        tree = reg.delegation_tree()
        assert len(tree["roots"]) == 1
        assert tree["summary"]["total_grants"] == 2
        assert tree["summary"]["max_depth"] == 1

    def test_summary(self):
        reg = DelegationRegistry()
        reg.delegate(grantor_id="admin", grantee_id="user1", scopes=["SAFE-*"])
        summary = reg.summary()
        assert summary["total"] == 1
        assert summary["active"] == 1
        assert summary["revoked"] == 0

    def test_history(self):
        reg = DelegationRegistry()
        reg.delegate(grantor_id="admin", grantee_id="user1", scopes=["*"])
        history = reg.history()
        assert len(history) == 1
        assert history[0]["action"] == "delegate"

    def test_len_and_repr(self):
        reg = DelegationRegistry()
        assert len(reg) == 0
        reg.delegate(grantor_id="admin", grantee_id="user1", scopes=["*"])
        assert len(reg) == 1
        assert "1 grants" in repr(reg)
