"""Tests for enhanced_agent_bus.verification_layer.maci_verifier module.

Covers: enums, dataclasses, agent base, executive/legislative/judicial agents,
MACIVerifier pipeline, cross-role validation, stats, and factory function.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.verification_layer.maci_verifier import (
    ROLE_PERMISSIONS,
    VALIDATION_CONSTRAINTS,
    AgentVerificationRecord,
    ExecutiveAgent,
    JudicialAgent,
    LegislativeAgent,
    MACIAgentBase,
    MACIAgentRole,
    MACIVerificationContext,
    MACIVerificationResult,
    MACIVerifier,
    VerificationPhase,
    VerificationStatus,
    create_maci_verifier,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestMACIAgentRole:
    def test_values(self):
        assert MACIAgentRole.EXECUTIVE.value == "executive"
        assert MACIAgentRole.LEGISLATIVE.value == "legislative"
        assert MACIAgentRole.JUDICIAL.value == "judicial"
        assert MACIAgentRole.MONITOR.value == "monitor"
        assert MACIAgentRole.AUDITOR.value == "auditor"


class TestVerificationPhase:
    def test_values(self):
        assert VerificationPhase.PROPOSAL.value == "proposal"
        assert VerificationPhase.POLICY_EXTRACTION.value == "policy_extraction"
        assert VerificationPhase.COMPLIANCE_CHECK.value == "compliance_check"
        assert VerificationPhase.JUDGMENT.value == "judgment"
        assert VerificationPhase.EXECUTION.value == "execution"
        assert VerificationPhase.AUDIT.value == "audit"


class TestVerificationStatus:
    def test_values(self):
        assert VerificationStatus.PENDING.value == "pending"
        assert VerificationStatus.COMPLETED.value == "completed"
        assert VerificationStatus.FAILED.value == "failed"
        assert VerificationStatus.BLOCKED.value == "blocked"
        assert VerificationStatus.TIMEOUT.value == "timeout"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestMACIVerificationContext:
    def test_defaults(self):
        ctx = MACIVerificationContext()
        assert ctx.tenant_id == "default"
        assert ctx.initiator_agent_id == ""
        assert ctx.session_id is None
        assert ctx.timeout_ms == 5000
        assert isinstance(ctx.created_at, datetime)

    def test_to_dict_round_trip(self):
        ctx = MACIVerificationContext(
            session_id="sess-1",
            tenant_id="t1",
            initiator_agent_id="agent-x",
        )
        d = ctx.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["tenant_id"] == "t1"
        assert d["initiator_agent_id"] == "agent-x"
        assert "verification_id" in d
        assert "created_at" in d

    def test_generate_context_hash_deterministic(self):
        ctx = MACIVerificationContext(
            verification_id="fixed-id",
            session_id="sess",
            tenant_id="t",
        )
        h1 = ctx.generate_context_hash()
        h2 = ctx.generate_context_hash()
        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) >= 16

    def test_generate_context_hash_differs_for_different_inputs(self):
        ctx_a = MACIVerificationContext(verification_id="a", session_id="s", tenant_id="t")
        ctx_b = MACIVerificationContext(verification_id="b", session_id="s", tenant_id="t")
        assert ctx_a.generate_context_hash() != ctx_b.generate_context_hash()


class TestAgentVerificationRecord:
    def test_to_dict(self):
        rec = AgentVerificationRecord(
            agent_id="ag-1",
            role=MACIAgentRole.EXECUTIVE,
            phase=VerificationPhase.PROPOSAL,
            action="propose",
            input_hash="aaa",
            output_hash="bbb",
            confidence=0.9,
            reasoning="ok",
            evidence=["ev1"],
        )
        d = rec.to_dict()
        assert d["agent_id"] == "ag-1"
        assert d["role"] == "executive"
        assert d["phase"] == "proposal"
        assert d["confidence"] == 0.9
        assert d["evidence"] == ["ev1"]


class TestMACIVerificationResult:
    def test_to_dict(self):
        result = MACIVerificationResult(
            verification_id="v-1",
            is_compliant=True,
            confidence=0.95,
            status=VerificationStatus.COMPLETED,
        )
        d = result.to_dict()
        assert d["verification_id"] == "v-1"
        assert d["is_compliant"] is True
        assert d["status"] == "completed"

    def test_add_audit_entry(self):
        result = MACIVerificationResult(
            verification_id="v-2",
            is_compliant=False,
            confidence=0.0,
            status=VerificationStatus.PENDING,
        )
        result.add_audit_entry({"phase": "test", "info": "something"})
        assert len(result.audit_trail) == 1
        entry = result.audit_trail[0]
        assert entry["phase"] == "test"
        assert "timestamp" in entry
        assert "constitutional_hash" in entry


# ---------------------------------------------------------------------------
# Role permissions matrix tests
# ---------------------------------------------------------------------------


class TestRolePermissions:
    def test_executive_can_propose_and_execute(self):
        perms = ROLE_PERMISSIONS[MACIAgentRole.EXECUTIVE]
        assert VerificationPhase.PROPOSAL in perms
        assert VerificationPhase.EXECUTION in perms
        assert VerificationPhase.JUDGMENT not in perms

    def test_legislative_can_only_extract(self):
        perms = ROLE_PERMISSIONS[MACIAgentRole.LEGISLATIVE]
        assert VerificationPhase.POLICY_EXTRACTION in perms
        assert len(perms) == 1

    def test_judicial_can_check_and_judge(self):
        perms = ROLE_PERMISSIONS[MACIAgentRole.JUDICIAL]
        assert VerificationPhase.COMPLIANCE_CHECK in perms
        assert VerificationPhase.JUDGMENT in perms
        assert VerificationPhase.PROPOSAL not in perms

    def test_validation_constraints(self):
        assert MACIAgentRole.EXECUTIVE in VALIDATION_CONSTRAINTS[MACIAgentRole.JUDICIAL]
        assert MACIAgentRole.LEGISLATIVE in VALIDATION_CONSTRAINTS[MACIAgentRole.JUDICIAL]
        assert MACIAgentRole.MONITOR in VALIDATION_CONSTRAINTS[MACIAgentRole.AUDITOR]


# ---------------------------------------------------------------------------
# MACIAgentBase tests
# ---------------------------------------------------------------------------


class TestMACIAgentBase:
    def test_register_and_owns_output(self):
        agent = MACIAgentBase("a1", MACIAgentRole.EXECUTIVE)
        h = agent.register_output("out-1", {"data": "test"})
        assert isinstance(h, str)
        assert agent.owns_output("out-1")
        assert not agent.owns_output("nonexistent")

    def test_can_perform_phase(self):
        exec_agent = MACIAgentBase("a1", MACIAgentRole.EXECUTIVE)
        assert exec_agent.can_perform_phase(VerificationPhase.PROPOSAL)
        assert not exec_agent.can_perform_phase(VerificationPhase.JUDGMENT)

    def test_can_validate_role(self):
        judicial = MACIAgentBase("j1", MACIAgentRole.JUDICIAL)
        assert judicial.can_validate_role(MACIAgentRole.EXECUTIVE)
        assert not judicial.can_validate_role(MACIAgentRole.JUDICIAL)

        exec_agent = MACIAgentBase("e1", MACIAgentRole.EXECUTIVE)
        assert not exec_agent.can_validate_role(MACIAgentRole.LEGISLATIVE)


# ---------------------------------------------------------------------------
# ExecutiveAgent tests
# ---------------------------------------------------------------------------


class TestExecutiveAgent:
    @pytest.fixture
    def agent(self):
        return ExecutiveAgent("exec-test")

    @pytest.mark.asyncio
    async def test_propose_decision_returns_tuple(self, agent):
        decision, output_id = await agent.propose_decision(
            action="test action",
            context={"scope": "local"},
        )
        assert output_id.startswith("exec-")
        assert decision["agent_id"] == "exec-test"
        assert decision["role"] == "executive"
        assert decision["action"] == "test action"
        assert "risk_assessment" in decision
        assert "impact_evaluation" in decision
        assert agent.owns_output(output_id)

    @pytest.mark.asyncio
    async def test_risk_assessment_sensitive_data(self, agent):
        decision, _ = await agent.propose_decision(
            action="handle data",
            context={"involves_sensitive_data": True, "high_impact": True},
        )
        score = decision["risk_assessment"]["score"]
        # base 0.2 + sensitive 0.3 + high_impact 0.2 = 0.7
        assert score == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio
    async def test_risk_assessment_capped_at_1(self, agent):
        decision, _ = await agent.propose_decision(
            action="everything risky",
            context={
                "involves_sensitive_data": True,
                "crosses_jurisdictions": True,
                "high_impact": True,
                "requires_human_approval": True,
            },
        )
        score = decision["risk_assessment"]["score"]
        assert score <= 1.0

    @pytest.mark.asyncio
    async def test_risk_factors_extraction(self, agent):
        decision, _ = await agent.propose_decision(
            action="test",
            context={"involves_sensitive_data": True, "emergency": True},
        )
        factors = decision["risk_assessment"]["factors"]
        assert "sensitive_data_involved" in factors
        assert "emergency_condition" in factors

    @pytest.mark.asyncio
    async def test_custom_impact_assessment(self, agent):
        custom_impact = {"scope": "global", "custom": True}
        decision, _ = await agent.propose_decision(
            action="test",
            context={},
            impact_assessment=custom_impact,
        )
        assert decision["impact_evaluation"]["custom"] is True


# ---------------------------------------------------------------------------
# LegislativeAgent tests
# ---------------------------------------------------------------------------


class TestLegislativeAgent:
    @pytest.fixture
    def agent(self):
        return LegislativeAgent("legis-test")

    @pytest.mark.asyncio
    async def test_extract_rules_policy_action(self, agent):
        decision = {"action": "enforce policy", "output_id": "d-1"}
        ctx = MACIVerificationContext()
        rules, rules_id = await agent.extract_rules(decision, ctx)

        assert rules_id.startswith("legis-")
        assert rules["agent_id"] == "legis-test"
        assert rules["role"] == "legislative"
        rule_ids = [r["rule_id"] for r in rules["rules"]]
        assert "policy_integrity" in rule_ids
        assert "impact_assessment_required" in rule_ids

    @pytest.mark.asyncio
    async def test_extract_rules_access_action(self, agent):
        decision = {"action": "grant access", "output_id": "d-2"}
        ctx = MACIVerificationContext()
        rules, _ = await agent.extract_rules(decision, ctx)

        rule_ids = [r["rule_id"] for r in rules["rules"]]
        assert "least_privilege" in rule_ids
        assert "audit_trail_required" in rule_ids

    @pytest.mark.asyncio
    async def test_extract_rules_sensitive_data_context(self, agent):
        decision = {"action": "store data", "output_id": "d-3"}
        ctx = MACIVerificationContext(decision_context={"involves_sensitive_data": True})
        rules, _ = await agent.extract_rules(decision, ctx)

        rule_ids = [r["rule_id"] for r in rules["rules"]]
        assert "data_protection" in rule_ids

    @pytest.mark.asyncio
    async def test_extract_rules_no_matching_action(self, agent):
        decision = {"action": "do something generic", "output_id": "d-4"}
        ctx = MACIVerificationContext()
        rules, _ = await agent.extract_rules(decision, ctx)
        assert rules["rules"] == []

    @pytest.mark.asyncio
    async def test_amendment_principles(self, agent):
        decision = {"action": "constitutional amendment", "output_id": "d-5"}
        ctx = MACIVerificationContext()
        rules, _ = await agent.extract_rules(decision, ctx)
        principles = rules["principles"]
        assert any("amendments require broad consensus" in p.lower() for p in principles)

    @pytest.mark.asyncio
    async def test_constraints_with_human_approval(self, agent):
        decision = {"action": "test", "output_id": "d-6"}
        ctx = MACIVerificationContext(decision_context={"requires_human_approval": True})
        rules, _ = await agent.extract_rules(decision, ctx)
        assert any("Human approval" in c for c in rules["constraints"])

    @pytest.mark.asyncio
    async def test_precedence_order_critical_first(self, agent):
        decision = {"action": "enforce policy with access permissions", "output_id": "d-7"}
        ctx = MACIVerificationContext()
        rules, _ = await agent.extract_rules(decision, ctx)
        precedence = rules["precedence_order"]
        # critical rules should come before high rules
        if "policy_integrity" in precedence and "impact_assessment_required" in precedence:
            assert precedence.index("policy_integrity") < precedence.index(
                "impact_assessment_required"
            )


# ---------------------------------------------------------------------------
# JudicialAgent tests
# ---------------------------------------------------------------------------


class TestJudicialAgent:
    @pytest.fixture
    def agent(self):
        return JudicialAgent("jud-test")

    def _make_compliant_decision(self):
        return {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "action": "test",
            "context": {},
            "impact_evaluation": {"scope": "local"},
        }

    def _make_rules(self, rule_ids=None):
        rules_list = []
        all_rules = {
            "policy_integrity": {
                "rule_id": "policy_integrity",
                "severity": "critical",
                "description": "Policy integrity",
                "scope": "all",
            },
            "impact_assessment_required": {
                "rule_id": "impact_assessment_required",
                "severity": "high",
                "description": "Impact",
                "scope": "changes",
            },
            "least_privilege": {
                "rule_id": "least_privilege",
                "severity": "critical",
                "description": "Least privilege",
                "scope": "access",
            },
            "audit_trail_required": {
                "rule_id": "audit_trail_required",
                "severity": "high",
                "description": "Audit trail",
                "scope": "ops",
            },
            "data_protection": {
                "rule_id": "data_protection",
                "severity": "critical",
                "description": "Data protection",
                "scope": "data",
            },
        }
        for rid in rule_ids or []:
            if rid in all_rules:
                rules_list.append(all_rules[rid])
        return {
            "output_id": "r-1",
            "agent_id": "legis-001",
            "rules": rules_list,
            "precedence_order": [r["rule_id"] for r in rules_list],
            "principles": ["Maximize beneficial impact while minimizing harm"],
            "constraints": [],
        }

    @pytest.mark.asyncio
    async def test_compliant_decision(self, agent):
        decision = self._make_compliant_decision()
        rules = self._make_rules(["policy_integrity"])
        ctx = MACIVerificationContext()
        judgment, jid = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is True
        assert judgment["confidence"] == 1.0
        assert len(judgment["violations"]) == 0
        assert agent.owns_output(jid)

    @pytest.mark.asyncio
    async def test_godel_bypass_prevention(self, agent):
        decision = {"output_id": "d-self", "agent_id": "jud-test"}
        rules = self._make_rules()
        ctx = MACIVerificationContext()

        with pytest.raises(ValueError, match="Godel bypass prevention"):
            await agent.validate_compliance(decision, rules, ctx)

    @pytest.mark.asyncio
    async def test_policy_integrity_violation(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"policy_compliant": False},
            "impact_evaluation": {},
        }
        rules = self._make_rules(["policy_integrity"])
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False
        assert judgment["confidence"] == pytest.approx(0.3)
        assert any(v["rule_id"] == "policy_integrity" for v in judgment["violations"])

    @pytest.mark.asyncio
    async def test_missing_impact_assessment_violation(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {},
            # no impact_evaluation
        }
        rules = self._make_rules(["impact_assessment_required"])
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False
        assert any(v["rule_id"] == "impact_assessment_required" for v in judgment["violations"])

    @pytest.mark.asyncio
    async def test_least_privilege_violation(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"excessive_permissions": True},
            "impact_evaluation": {},
        }
        rules = self._make_rules(["least_privilege"])
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False
        assert judgment["confidence"] == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_audit_trail_violation(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"auditable": False},
            "impact_evaluation": {},
        }
        rules = self._make_rules(["audit_trail_required"])
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False
        assert judgment["confidence"] == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_data_protection_violation(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"data_unprotected": True},
            "impact_evaluation": {},
        }
        rules = self._make_rules(["data_protection"])
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False
        assert judgment["confidence"] == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_potential_harm_principle_violation(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"potential_harm": True},
            "impact_evaluation": {},
        }
        rules = self._make_rules()
        # Add the harm principle
        rules["principles"] = ["Maximize beneficial impact while minimizing harm"]
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False
        assert any("harm" in str(v).lower() for v in judgment["violations"])

    @pytest.mark.asyncio
    async def test_constraint_technically_not_feasible(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"technically_feasible": False},
            "impact_evaluation": {},
        }
        rules = self._make_rules()
        rules["constraints"] = ["Implementation must be technically feasible"]
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False

    @pytest.mark.asyncio
    async def test_constraint_human_approval_required_not_obtained(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"requires_human_approval": True, "human_approved": False},
            "impact_evaluation": {},
        }
        rules = self._make_rules()
        rules["constraints"] = ["Human approval required before execution"]
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert judgment["is_compliant"] is False

    @pytest.mark.asyncio
    async def test_reasoning_compliant(self, agent):
        decision = self._make_compliant_decision()
        rules = self._make_rules()
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert "COMPLIANT" in judgment["judgment_reasoning"]

    @pytest.mark.asyncio
    async def test_reasoning_non_compliant(self, agent):
        decision = {
            "output_id": "d-1",
            "agent_id": "exec-001",
            "context": {"policy_compliant": False},
            "impact_evaluation": {},
        }
        rules = self._make_rules(["policy_integrity"])
        ctx = MACIVerificationContext()
        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert "NON-COMPLIANT" in judgment["judgment_reasoning"]
        assert "1 violation" in judgment["judgment_reasoning"]


# ---------------------------------------------------------------------------
# MACIVerifier pipeline tests
# ---------------------------------------------------------------------------


class TestMACIVerifier:
    @pytest.fixture
    def mock_planner(self):
        planner = MagicMock()
        planner.generate_recommendations.return_value = ["recommendation-1"]
        return planner

    @pytest.fixture
    def verifier(self, mock_planner):
        return MACIVerifier(
            executive_agent=ExecutiveAgent("exec-v"),
            legislative_agent=LegislativeAgent("legis-v"),
            judicial_agent=JudicialAgent("jud-v"),
            recommendation_planner=mock_planner,
        )

    @pytest.mark.asyncio
    async def test_verify_compliant_action(self, verifier):
        result = await verifier.verify(
            action="generic action",
            context={"scope": "local"},
        )
        assert isinstance(result, MACIVerificationResult)
        assert result.status == VerificationStatus.COMPLETED
        assert result.is_compliant is True
        assert result.confidence > 0
        assert result.total_duration_ms >= 0
        assert len(result.agent_records) == 3
        assert result.executive_decision is not None
        assert result.legislative_rules is not None
        assert result.judicial_judgment is not None

    @pytest.mark.asyncio
    async def test_verify_non_compliant_action(self, verifier):
        result = await verifier.verify(
            action="enforce policy",
            context={"policy_compliant": False},
        )
        assert result.status == VerificationStatus.COMPLETED
        assert result.is_compliant is False
        assert len(result.violations) > 0

    @pytest.mark.asyncio
    async def test_verify_with_custom_context(self, verifier):
        ctx = MACIVerificationContext(
            session_id="s1",
            tenant_id="tenant-x",
            decision_context={"involves_sensitive_data": True},
        )
        result = await verifier.verify(
            action="store data",
            context={"involves_sensitive_data": True},
            verification_context=ctx,
        )
        assert result.verification_id == ctx.verification_id
        assert result.status == VerificationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_verify_stores_history(self, verifier):
        assert len(verifier.verification_history) == 0
        await verifier.verify(action="test", context={})
        assert len(verifier.verification_history) == 1
        await verifier.verify(action="test2", context={})
        assert len(verifier.verification_history) == 2

    @pytest.mark.asyncio
    async def test_verify_handles_error_gracefully(self, verifier):
        # Force judicial agent to raise by making it try self-validation
        verifier.judicial.agent_id = verifier.executive.agent_id
        result = await verifier.verify(action="test", context={})
        assert result.status == VerificationStatus.FAILED
        assert any(v["type"] == "verification_error" for v in result.violations)

    @pytest.mark.asyncio
    async def test_verify_audit_trail_populated(self, verifier):
        result = await verifier.verify(action="test", context={})
        # Should have at least: proposal start/end, extraction start/end, judgment start/end
        assert len(result.audit_trail) >= 6

    @pytest.mark.asyncio
    async def test_recommendations_called(self, verifier, mock_planner):
        result = await verifier.verify(action="test", context={})
        mock_planner.generate_recommendations.assert_called_once()
        assert result.recommendations == ["recommendation-1"]


# ---------------------------------------------------------------------------
# Cross-role validation tests
# ---------------------------------------------------------------------------


class TestVerifyCrossRoleAction:
    @pytest.fixture
    def verifier(self):
        planner = MagicMock()
        planner.generate_recommendations.return_value = []
        return MACIVerifier(
            executive_agent=ExecutiveAgent("exec-cr"),
            legislative_agent=LegislativeAgent("legis-cr"),
            judicial_agent=JudicialAgent("jud-cr"),
            recommendation_planner=planner,
        )

    @pytest.mark.asyncio
    async def test_self_validation_blocked(self, verifier):
        allowed = await verifier.verify_cross_role_action(
            validator_agent_id="agent-1",
            validator_role=MACIAgentRole.JUDICIAL,
            target_agent_id="agent-1",
            target_role=MACIAgentRole.EXECUTIVE,
            target_output_id="out-1",
        )
        assert allowed is False

    @pytest.mark.asyncio
    async def test_judicial_can_validate_executive(self, verifier):
        allowed = await verifier.verify_cross_role_action(
            validator_agent_id="jud-1",
            validator_role=MACIAgentRole.JUDICIAL,
            target_agent_id="exec-1",
            target_role=MACIAgentRole.EXECUTIVE,
            target_output_id="out-1",
        )
        assert allowed is True

    @pytest.mark.asyncio
    async def test_executive_cannot_validate_legislative(self, verifier):
        allowed = await verifier.verify_cross_role_action(
            validator_agent_id="exec-1",
            validator_role=MACIAgentRole.EXECUTIVE,
            target_agent_id="legis-1",
            target_role=MACIAgentRole.LEGISLATIVE,
            target_output_id="out-1",
        )
        assert allowed is False

    @pytest.mark.asyncio
    async def test_auditor_can_validate_monitor(self, verifier):
        allowed = await verifier.verify_cross_role_action(
            validator_agent_id="aud-1",
            validator_role=MACIAgentRole.AUDITOR,
            target_agent_id="mon-1",
            target_role=MACIAgentRole.MONITOR,
            target_output_id="out-1",
        )
        assert allowed is True


# ---------------------------------------------------------------------------
# Stats and factory tests
# ---------------------------------------------------------------------------


class TestGetVerificationStats:
    @pytest.fixture
    def verifier(self):
        planner = MagicMock()
        planner.generate_recommendations.return_value = []
        return MACIVerifier(
            executive_agent=ExecutiveAgent("exec-s"),
            legislative_agent=LegislativeAgent("legis-s"),
            judicial_agent=JudicialAgent("jud-s"),
            recommendation_planner=planner,
        )

    def test_empty_stats(self, verifier):
        stats = verifier.get_verification_stats()
        assert stats == {"total_verifications": 0}

    @pytest.mark.asyncio
    async def test_stats_after_verifications(self, verifier):
        await verifier.verify(action="test", context={})
        await verifier.verify(action="enforce policy", context={"policy_compliant": False})

        stats = verifier.get_verification_stats()
        assert stats["total_verifications"] == 2
        assert stats["compliant_count"] >= 0
        assert 0 <= stats["compliance_rate"] <= 1.0
        assert stats["average_confidence"] > 0
        assert stats["average_duration_ms"] >= 0
        assert "constitutional_hash" in stats


class TestGetConstitutionalHash:
    def test_returns_hash(self):
        planner = MagicMock()
        planner.generate_recommendations.return_value = []
        v = MACIVerifier(recommendation_planner=planner)
        h = v.get_constitutional_hash()
        assert isinstance(h, str)
        assert len(h) > 0


class TestCreateMACIVerifier:
    def test_factory_default_ids(self):
        v = create_maci_verifier()
        assert v.executive.agent_id == "executive-001"
        assert v.legislative.agent_id == "legislative-001"
        assert v.judicial.agent_id == "judicial-001"

    def test_factory_custom_ids(self):
        v = create_maci_verifier(
            executive_id="e-custom",
            legislative_id="l-custom",
            judicial_id="j-custom",
        )
        assert v.executive.agent_id == "e-custom"
        assert v.legislative.agent_id == "l-custom"
        assert v.judicial.agent_id == "j-custom"
