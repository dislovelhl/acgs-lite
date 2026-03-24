"""
Tests for enhanced_agent_bus.verification.maci_verification

Covers: ExecutiveAgent, LegislativeAgent, JudicialAgent,
        ConstitutionalVerificationPipeline, verify_decision_maci,
        dataclass serialization, and error handling paths.
"""

import pytest

from enhanced_agent_bus.verification.maci_verification import (
    AgentRole,
    ConstitutionalRules,
    ConstitutionalVerificationPipeline,
    ExecutiveAgent,
    GovernanceDecision,
    GovernanceDecisionType,
    JudicialAgent,
    LegislativeAgent,
    ValidationResult,
    get_maci_pipeline,
    verify_decision_maci,
)

# ---------------------------------------------------------------------------
# Dataclass serialization
# ---------------------------------------------------------------------------


class TestGovernanceDecisionToDict:
    def test_to_dict_contains_all_fields(self):
        decision = GovernanceDecision(
            decision_id="d1",
            decision_type=GovernanceDecisionType.ACCESS_CONTROL,
            description="grant access",
            context={"key": "val"},
            proposed_action={"action": "grant"},
        )
        d = decision.to_dict()
        assert d["decision_id"] == "d1"
        assert d["decision_type"] == "access_control"
        assert d["description"] == "grant access"
        assert "timestamp" in d
        assert "constitutional_hash" in d


class TestConstitutionalRulesToDict:
    def test_to_dict(self):
        rules = ConstitutionalRules(
            rules=[{"rule_id": "r1"}],
            principles=["p1"],
            constraints=["c1"],
            precedence_order=["r1"],
        )
        d = rules.to_dict()
        assert d["rules"] == [{"rule_id": "r1"}]
        assert d["principles"] == ["p1"]
        assert "extracted_at" in d


class TestValidationResultToDict:
    def test_to_dict(self):
        vr = ValidationResult(
            decision_id="d1",
            is_valid=True,
            confidence_score=0.95,
            violations=[],
            justifications=["ok"],
            validated_by=AgentRole.JUDICIAL,
        )
        d = vr.to_dict()
        assert d["is_valid"] is True
        assert d["validated_by"] == "judicial"


# ---------------------------------------------------------------------------
# ExecutiveAgent
# ---------------------------------------------------------------------------


class TestExecutiveAgent:
    @pytest.fixture()
    def agent(self):
        return ExecutiveAgent()

    @pytest.mark.asyncio
    async def test_propose_decision_returns_governance_decision(self, agent):
        result = await agent.propose_decision(
            context={"some": "ctx"},
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="test proposal",
        )
        assert isinstance(result, GovernanceDecision)
        assert result.decision_id.startswith("exec_")
        assert result.decision_type == GovernanceDecisionType.POLICY_ENFORCEMENT

    @pytest.mark.asyncio
    async def test_risk_assessment_sensitive_data(self, agent):
        risk = await agent._assess_risks({"involves_sensitive_data": True})
        assert risk["risk_factors"]["security_risk"] > 0.5
        assert risk["mitigation_required"] is True

    @pytest.mark.asyncio
    async def test_risk_assessment_cross_jurisdictions(self, agent):
        risk = await agent._assess_risks({"crosses_jurisdictions": True})
        assert risk["risk_factors"]["compliance_risk"] > 0.3

    @pytest.mark.asyncio
    async def test_impact_evaluation_types(self, agent):
        for dt in GovernanceDecisionType:
            impact = await agent._evaluate_impact({}, dt)
            assert "impact_areas" in impact
            assert "requires_oversight" in impact

    @pytest.mark.asyncio
    async def test_implementation_plan(self, agent):
        plan = await agent._create_implementation_plan({}, GovernanceDecisionType.AUDIT_TRIGGER)
        assert "steps" in plan
        assert len(plan["steps"]) > 0


# ---------------------------------------------------------------------------
# LegislativeAgent
# ---------------------------------------------------------------------------


class TestLegislativeAgent:
    @pytest.fixture()
    def agent(self):
        return LegislativeAgent()

    def _make_decision(self, dt, context=None):
        return GovernanceDecision(
            decision_id="leg_test",
            decision_type=dt,
            description="test",
            context=context or {},
            proposed_action={},
        )

    @pytest.mark.asyncio
    async def test_extract_rules_policy_enforcement(self, agent):
        decision = self._make_decision(GovernanceDecisionType.POLICY_ENFORCEMENT)
        rules = await agent.extract_rules(decision)
        assert isinstance(rules, ConstitutionalRules)
        rule_ids = [r["rule_id"] for r in rules.rules]
        assert "policy_integrity" in rule_ids

    @pytest.mark.asyncio
    async def test_extract_rules_access_control(self, agent):
        decision = self._make_decision(GovernanceDecisionType.ACCESS_CONTROL)
        rules = await agent.extract_rules(decision)
        rule_ids = [r["rule_id"] for r in rules.rules]
        assert "principle_of_least_privilege" in rule_ids

    @pytest.mark.asyncio
    async def test_personal_data_adds_rule(self, agent):
        decision = self._make_decision(
            GovernanceDecisionType.RESOURCE_ALLOCATION,
            context={"involves_personal_data": True},
        )
        rules = await agent.extract_rules(decision)
        rule_ids = [r["rule_id"] for r in rules.rules]
        assert "data_protection" in rule_ids

    @pytest.mark.asyncio
    async def test_constitutional_amendment_adds_principles(self, agent):
        decision = self._make_decision(GovernanceDecisionType.CONSTITUTIONAL_AMENDMENT)
        rules = await agent.extract_rules(decision)
        assert any("consensus" in p for p in rules.principles)

    @pytest.mark.asyncio
    async def test_resource_allocation_adds_constraints(self, agent):
        decision = self._make_decision(GovernanceDecisionType.RESOURCE_ALLOCATION)
        rules = await agent.extract_rules(decision)
        assert any("single points of failure" in c for c in rules.constraints)

    @pytest.mark.asyncio
    async def test_precedence_order_by_severity(self, agent):
        rules = [
            {"rule_id": "low_rule", "severity": "low"},
            {"rule_id": "crit_rule", "severity": "critical"},
        ]
        precedence = await agent._determine_precedence(rules)
        assert precedence[0] == "crit_rule"


# ---------------------------------------------------------------------------
# JudicialAgent
# ---------------------------------------------------------------------------


class TestJudicialAgent:
    @pytest.fixture()
    def agent(self):
        return JudicialAgent()

    def _make_decision(self, context=None, proposed_action=None):
        return GovernanceDecision(
            decision_id="jud_test",
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="test",
            context=context or {},
            proposed_action=proposed_action or {"impact_evaluation": {}},
        )

    @pytest.mark.asyncio
    async def test_valid_decision_passes(self, agent):
        decision = self._make_decision(context={"policy_compliant": True})
        rules = ConstitutionalRules(
            rules=[
                {"rule_id": "policy_integrity", "severity": "critical", "description": "pol"},
            ],
            principles=["Ensure transparency and accountability"],
            constraints=[],
            precedence_order=["policy_integrity"],
        )
        result = await agent.validate_decision(decision, rules)
        assert result.is_valid is True
        assert result.confidence_score >= agent.capabilities.confidence_threshold

    @pytest.mark.asyncio
    async def test_policy_violation(self, agent):
        decision = self._make_decision(context={"policy_compliant": False})
        rules = ConstitutionalRules(
            rules=[
                {"rule_id": "policy_integrity", "severity": "critical", "description": "pol"},
            ],
            principles=[],
            constraints=[],
            precedence_order=["policy_integrity"],
        )
        result = await agent.validate_decision(decision, rules)
        assert result.is_valid is False
        assert len(result.violations) > 0

    @pytest.mark.asyncio
    async def test_missing_impact_assessment(self, agent):
        decision = self._make_decision(proposed_action={})
        rules = ConstitutionalRules(
            rules=[
                {"rule_id": "impact_assessment_required", "severity": "high", "description": "imp"},
            ],
            principles=[],
            constraints=[],
            precedence_order=["impact_assessment_required"],
        )
        result = await agent.validate_decision(decision, rules)
        assert any(v["rule_id"] == "impact_assessment_required" for v in result.violations)

    @pytest.mark.asyncio
    async def test_excessive_permissions_violation(self, agent):
        decision = self._make_decision(context={"excessive_permissions": True})
        rules = ConstitutionalRules(
            rules=[
                {
                    "rule_id": "principle_of_least_privilege",
                    "severity": "critical",
                    "description": "priv",
                },
            ],
            principles=[],
            constraints=[],
            precedence_order=["principle_of_least_privilege"],
        )
        result = await agent.validate_decision(decision, rules)
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_audit_trail_violation(self, agent):
        decision = self._make_decision(context={"auditable": False})
        rules = ConstitutionalRules(
            rules=[
                {"rule_id": "audit_trail_required", "severity": "high", "description": "aud"},
            ],
            principles=[],
            constraints=[],
            precedence_order=["audit_trail_required"],
        )
        result = await agent.validate_decision(decision, rules)
        assert any(v["rule_id"] == "audit_trail_required" for v in result.violations)

    @pytest.mark.asyncio
    async def test_principle_violation_potential_harm(self, agent):
        decision = self._make_decision(context={"potential_harm": True})
        rules = ConstitutionalRules(
            rules=[],
            principles=["Maximize beneficial impact while minimizing harm"],
            constraints=[],
            precedence_order=[],
        )
        result = await agent.validate_decision(decision, rules)
        assert len(result.violations) > 0

    @pytest.mark.asyncio
    async def test_constraint_violates_principles(self, agent):
        decision = self._make_decision(context={"violates_principles": True})
        rules = ConstitutionalRules(
            rules=[],
            principles=[],
            constraints=["Decision must not violate constitutional principles"],
            precedence_order=[],
        )
        result = await agent.validate_decision(decision, rules)
        assert len(result.violations) > 0

    @pytest.mark.asyncio
    async def test_constraint_not_feasible(self, agent):
        decision = self._make_decision(context={"technically_feasible": False})
        rules = ConstitutionalRules(
            rules=[],
            principles=[],
            constraints=["Implementation must be technically feasible"],
            precedence_order=[],
        )
        result = await agent.validate_decision(decision, rules)
        assert len(result.violations) > 0

    @pytest.mark.asyncio
    async def test_unknown_rule_id_skipped(self, agent):
        decision = self._make_decision()
        rules = ConstitutionalRules(
            rules=[{"rule_id": "known", "severity": "low", "description": "d"}],
            principles=[],
            constraints=[],
            precedence_order=["unknown_rule", "known"],
        )
        result = await agent.validate_decision(decision, rules)
        assert isinstance(result, ValidationResult)


# ---------------------------------------------------------------------------
# ConstitutionalVerificationPipeline
# ---------------------------------------------------------------------------


class TestConstitutionalVerificationPipeline:
    @pytest.fixture()
    def pipeline(self):
        return ConstitutionalVerificationPipeline()

    @pytest.mark.asyncio
    async def test_verify_governance_decision_happy_path(self, pipeline):
        result = await pipeline.verify_governance_decision(
            context={"policy_compliant": True, "auditable": True},
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="test decision",
        )
        assert isinstance(result, ValidationResult)
        assert result.validated_by == AgentRole.JUDICIAL

    @pytest.mark.asyncio
    async def test_verify_governance_decision_access_control(self, pipeline):
        result = await pipeline.verify_governance_decision(
            context={"excessive_permissions": True},
            decision_type=GovernanceDecisionType.ACCESS_CONTROL,
            description="excessive access",
        )
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_get_pipeline_status(self, pipeline):
        status = await pipeline.get_pipeline_status()
        assert status["status"] == "operational"
        assert status["godel_bypass_implemented"] is True
        assert "executive" in status["agents"]
        assert "legislative" in status["agents"]
        assert "judicial" in status["agents"]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestModuleFunctions:
    def test_get_maci_pipeline_returns_instance(self):
        p = get_maci_pipeline()
        assert isinstance(p, ConstitutionalVerificationPipeline)

    @pytest.mark.asyncio
    async def test_verify_decision_maci_happy(self):
        result = await verify_decision_maci(
            context={"policy_compliant": True},
            decision_type="policy_enforcement",
            description="test",
        )
        assert isinstance(result, dict)
        assert "is_valid" in result

    @pytest.mark.asyncio
    async def test_verify_decision_maci_invalid_type(self):
        result = await verify_decision_maci(
            context={},
            decision_type="not_a_real_type",
            description="bad",
        )
        assert result["is_valid"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


class TestEnums:
    def test_agent_role_values(self):
        assert AgentRole.EXECUTIVE.value == "executive"
        assert AgentRole.LEGISLATIVE.value == "legislative"
        assert AgentRole.JUDICIAL.value == "judicial"

    def test_governance_decision_type_values(self):
        assert GovernanceDecisionType.POLICY_ENFORCEMENT.value == "policy_enforcement"
        assert len(GovernanceDecisionType) == 6
