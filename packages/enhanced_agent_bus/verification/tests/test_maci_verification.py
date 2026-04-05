"""
Tests for MACI Verification Module
Constitutional Hash: 608508a9bd224290

Tests for the MACI Constitutional Verification Pipeline including:
- Agent roles (Executive, Legislative, Judicial)
- Governance decisions
- Rule extraction and validation
- Role separation for formal verification guarantees
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.verification.maci_verification import (
    AgentCapabilities,
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

# Constitutional validation markers
pytestmark = [
    pytest.mark.constitutional,
    pytest.mark.unit,
]


class TestAgentRole:
    """Test AgentRole enum."""

    def test_role_values(self):
        """Test agent role enum values."""
        assert AgentRole.EXECUTIVE.value == "executive"
        assert AgentRole.LEGISLATIVE.value == "legislative"
        assert AgentRole.JUDICIAL.value == "judicial"

    def test_role_count(self):
        """Test that we have exactly 3 MACI roles."""
        assert len(AgentRole) == 3


class TestGovernanceDecisionType:
    """Test GovernanceDecisionType enum."""

    def test_decision_type_values(self):
        """Test governance decision type enum values."""
        assert GovernanceDecisionType.POLICY_ENFORCEMENT.value == "policy_enforcement"
        assert GovernanceDecisionType.RESOURCE_ALLOCATION.value == "resource_allocation"
        assert GovernanceDecisionType.ACCESS_CONTROL.value == "access_control"
        assert GovernanceDecisionType.AUDIT_TRIGGER.value == "audit_trigger"
        assert GovernanceDecisionType.CONSTITUTIONAL_AMENDMENT.value == "constitutional_amendment"
        assert GovernanceDecisionType.SYSTEM_MAINTENANCE.value == "system_maintenance"


class TestGovernanceDecision:
    """Test GovernanceDecision dataclass."""

    def test_create_decision(self):
        """Test creating a governance decision."""
        decision = GovernanceDecision(
            decision_id="test-001",
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="Test policy enforcement decision",
            context={"key": "value"},
            proposed_action={"action": "enforce"},
        )

        assert decision.decision_id == "test-001"
        assert decision.decision_type == GovernanceDecisionType.POLICY_ENFORCEMENT
        assert decision.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(decision.timestamp, datetime)

    def test_decision_to_dict(self):
        """Test converting decision to dictionary."""
        decision = GovernanceDecision(
            decision_id="test-002",
            decision_type=GovernanceDecisionType.ACCESS_CONTROL,
            description="Grant access request",
            context={"user": "admin"},
            proposed_action={"grant": True},
        )

        data = decision.to_dict()

        assert data["decision_id"] == "test-002"
        assert data["decision_type"] == "access_control"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestConstitutionalRules:
    """Test ConstitutionalRules dataclass."""

    def test_create_rules(self):
        """Test creating constitutional rules."""
        rules = ConstitutionalRules(
            rules=[{"rule_id": "r1", "description": "Test rule"}],
            principles=["Principle 1", "Principle 2"],
            constraints=["Constraint 1"],
            precedence_order=["r1"],
        )

        assert len(rules.rules) == 1
        assert len(rules.principles) == 2
        assert rules.constitutional_hash == CONSTITUTIONAL_HASH

    def test_rules_to_dict(self):
        """Test converting rules to dictionary."""
        rules = ConstitutionalRules(
            rules=[{"rule_id": "r1"}],
            principles=["P1"],
            constraints=["C1"],
            precedence_order=["r1"],
        )

        data = rules.to_dict()
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_create_valid_result(self):
        """Test creating a valid validation result."""
        result = ValidationResult(
            decision_id="decision-001",
            is_valid=True,
            confidence_score=0.95,
            violations=[],
            justifications=["Decision complies with all rules"],
            validated_by=AgentRole.JUDICIAL,
        )

        assert result.is_valid is True
        assert result.confidence_score == 0.95
        assert result.validated_by == AgentRole.JUDICIAL
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_invalid_result(self):
        """Test creating an invalid validation result."""
        result = ValidationResult(
            decision_id="decision-002",
            is_valid=False,
            confidence_score=0.3,
            violations=[{"rule_id": "r1", "severity": "critical"}],
            justifications=[],
            validated_by=AgentRole.JUDICIAL,
        )

        assert result.is_valid is False
        assert len(result.violations) == 1


class TestExecutiveAgent:
    """Test ExecutiveAgent class."""

    @pytest.fixture
    def executive(self):
        """Create an executive agent."""
        return ExecutiveAgent()

    def test_initialization(self, executive):
        """Test executive agent initialization."""
        assert executive.capabilities.role == AgentRole.EXECUTIVE
        assert executive.constitutional_hash == CONSTITUTIONAL_HASH

    def test_capabilities_include_limitations(self, executive):
        """Test that executive has documented limitations."""
        limitations = executive.capabilities.limitations
        assert "Cannot validate own decisions" in limitations

    async def test_propose_decision(self, executive):
        """Test proposing a governance decision."""
        context = {"involves_sensitive_data": True}

        decision = await executive.propose_decision(
            context=context,
            decision_type=GovernanceDecisionType.ACCESS_CONTROL,
            description="Grant admin access",
        )

        assert decision.decision_id.startswith("exec_")
        assert "risk_assessment" in decision.proposed_action

    async def test_risk_assessment_sensitive_data(self, executive):
        """Test risk assessment increases for sensitive data."""
        context_normal = {}
        context_sensitive = {"involves_sensitive_data": True}

        risk_normal = await executive._assess_risks(context_normal)
        risk_sensitive = await executive._assess_risks(context_sensitive)

        assert (
            risk_sensitive["risk_factors"]["security_risk"]
            > risk_normal["risk_factors"]["security_risk"]
        )


class TestLegislativeAgent:
    """Test LegislativeAgent class."""

    @pytest.fixture
    def legislative(self):
        """Create a legislative agent."""
        return LegislativeAgent()

    def test_initialization(self, legislative):
        """Test legislative agent initialization."""
        assert legislative.capabilities.role == AgentRole.LEGISLATIVE
        assert legislative.constitutional_hash == CONSTITUTIONAL_HASH

    def test_capabilities_include_limitations(self, legislative):
        """Test that legislative has documented limitations."""
        limitations = legislative.capabilities.limitations
        assert "Cannot propose decisions" in limitations

    def test_core_principles_defined(self, legislative):
        """Test that core constitutional principles are defined."""
        assert len(legislative.core_principles) >= 5

    async def test_extract_rules(self, legislative):
        """Test extracting constitutional rules."""
        decision = GovernanceDecision(
            decision_id="test-001",
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="Enforce policy",
            context={},
            proposed_action={},
        )

        rules = await legislative.extract_rules(decision)

        assert isinstance(rules, ConstitutionalRules)
        assert len(rules.rules) > 0
        assert rules.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_extract_rules_for_access_control(self, legislative):
        """Test rule extraction for access control decisions."""
        decision = GovernanceDecision(
            decision_id="test-access",
            decision_type=GovernanceDecisionType.ACCESS_CONTROL,
            description="Grant access",
            context={},
            proposed_action={},
        )

        rules = await legislative.extract_rules(decision)
        rule_ids = [r["rule_id"] for r in rules.rules]
        assert "principle_of_least_privilege" in rule_ids


class TestJudicialAgent:
    """Test JudicialAgent class."""

    @pytest.fixture
    def judicial(self):
        """Create a judicial agent."""
        return JudicialAgent()

    def test_initialization(self, judicial):
        """Test judicial agent initialization."""
        assert judicial.capabilities.role == AgentRole.JUDICIAL
        assert judicial.constitutional_hash == CONSTITUTIONAL_HASH

    def test_capabilities_include_limitations(self, judicial):
        """Test that judicial has documented limitations."""
        limitations = judicial.capabilities.limitations
        assert "Cannot propose decisions" in limitations

    async def test_validate_compliant_decision(self, judicial):
        """Test validating a compliant decision."""
        decision = GovernanceDecision(
            decision_id="test-valid",
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="Valid decision",
            context={"policy_compliant": True},
            proposed_action={"impact_evaluation": {"severity": 0.5}},
        )

        rules = ConstitutionalRules(
            rules=[
                {
                    "rule_id": "policy_integrity",
                    "description": "Policy must comply",
                    "severity": "critical",
                },
            ],
            principles=["Ensure transparency"],
            constraints=[],
            precedence_order=["policy_integrity"],
        )

        result = await judicial.validate_decision(decision, rules)

        assert result.is_valid is True
        assert result.validated_by == AgentRole.JUDICIAL

    async def test_validate_non_compliant_decision(self, judicial):
        """Test validating a non-compliant decision."""
        decision = GovernanceDecision(
            decision_id="test-invalid",
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="Invalid decision",
            context={"policy_compliant": False},
            proposed_action={},
        )

        rules = ConstitutionalRules(
            rules=[
                {
                    "rule_id": "policy_integrity",
                    "description": "Policy must comply",
                    "severity": "critical",
                },
            ],
            principles=[],
            constraints=[],
            precedence_order=["policy_integrity"],
        )

        result = await judicial.validate_decision(decision, rules)

        assert result.is_valid is False
        assert len(result.violations) > 0


class TestConstitutionalVerificationPipeline:
    """Test ConstitutionalVerificationPipeline class."""

    @pytest.fixture
    def pipeline(self):
        """Create a verification pipeline."""
        return ConstitutionalVerificationPipeline()

    def test_initialization(self, pipeline):
        """Test pipeline initialization."""
        assert pipeline.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(pipeline.executive, ExecutiveAgent)
        assert isinstance(pipeline.legislative, LegislativeAgent)
        assert isinstance(pipeline.judicial, JudicialAgent)

    async def test_get_pipeline_status(self, pipeline):
        """Test getting pipeline status."""
        status = await pipeline.get_pipeline_status()

        assert status["status"] == "operational"
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "executive" in status["agents"]

    async def test_verify_governance_decision(self, pipeline):
        """Test full verification pipeline."""
        context = {
            "policy_compliant": True,
            "technically_feasible": True,
            "auditable": True,
        }

        result = await pipeline.verify_governance_decision(
            context=context,
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="Test governance decision",
        )

        assert isinstance(result, ValidationResult)
        assert result.validated_by == AgentRole.JUDICIAL

    async def test_pipeline_handles_errors(self, pipeline):
        """Test that pipeline handles errors gracefully."""
        pipeline.executive.propose_decision = AsyncMock(side_effect=RuntimeError("Test error"))

        result = await pipeline.verify_governance_decision(
            context={},
            decision_type=GovernanceDecisionType.AUDIT_TRIGGER,
            description="Error test",
        )

        assert result.is_valid is False


class TestMACIConvenienceFunctions:
    """Test convenience functions."""

    def test_get_maci_pipeline(self):
        """Test getting the global MACI pipeline."""
        pipeline = get_maci_pipeline()
        assert isinstance(pipeline, ConstitutionalVerificationPipeline)

    async def test_verify_decision_maci(self):
        """Test the verify_decision_maci convenience function."""
        result = await verify_decision_maci(
            context={"policy_compliant": True},
            decision_type="policy_enforcement",
            description="Test decision",
        )

        assert isinstance(result, dict)
        assert "is_valid" in result

    async def test_verify_decision_maci_invalid_type(self):
        """Test verify_decision_maci with invalid decision type."""
        result = await verify_decision_maci(
            context={},
            decision_type="invalid_type",
            description="Invalid test",
        )

        assert result["is_valid"] is False


class TestRoleSeparation:
    """Test role separation ensures formal verification guarantees."""

    @pytest.fixture
    def pipeline(self):
        """Create a verification pipeline."""
        return ConstitutionalVerificationPipeline()

    def test_executive_cannot_validate(self, pipeline):
        """Test that executive agent cannot validate decisions."""
        limitations = pipeline.executive.capabilities.limitations
        assert "Cannot validate own decisions" in limitations

    def test_legislative_cannot_validate(self, pipeline):
        """Test that legislative agent cannot validate decisions."""
        limitations = pipeline.legislative.capabilities.limitations
        assert "No validation authority" in limitations

    def test_judicial_cannot_propose(self, pipeline):
        """Test that judicial agent cannot propose decisions."""
        limitations = pipeline.judicial.capabilities.limitations
        assert "Cannot propose decisions" in limitations

    async def test_role_separation_enforced(self, pipeline):
        """Test that role separation is enforced in pipeline."""
        context = {"policy_compliant": True}

        # Executive proposes (Phase 1)
        decision = await pipeline.executive.propose_decision(
            context=context,
            decision_type=GovernanceDecisionType.POLICY_ENFORCEMENT,
            description="Test",
        )
        assert decision.decision_id.startswith("exec_")

        # Legislative extracts rules (Phase 2)
        rules = await pipeline.legislative.extract_rules(decision)
        assert rules.constitutional_hash == CONSTITUTIONAL_HASH

        # Judicial validates (Phase 3)
        result = await pipeline.judicial.validate_decision(decision, rules)
        assert result.validated_by == AgentRole.JUDICIAL


class TestConstitutionalHashEnforcement:
    """Test constitutional hash enforcement throughout MACI."""

    def test_decision_has_hash(self):
        """Test that decisions include constitutional hash."""
        decision = GovernanceDecision(
            decision_id="test",
            decision_type=GovernanceDecisionType.AUDIT_TRIGGER,
            description="Test",
            context={},
            proposed_action={},
        )
        assert decision.constitutional_hash == CONSTITUTIONAL_HASH

    def test_rules_have_hash(self):
        """Test that rules include constitutional hash."""
        rules = ConstitutionalRules(
            rules=[],
            principles=[],
            constraints=[],
            precedence_order=[],
        )
        assert rules.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_has_hash(self):
        """Test that validation results include constitutional hash."""
        result = ValidationResult(
            decision_id="test",
            is_valid=True,
            confidence_score=1.0,
            violations=[],
            justifications=[],
            validated_by=AgentRole.JUDICIAL,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_agents_have_hash(self):
        """Test that all agents have constitutional hash."""
        executive = ExecutiveAgent()
        legislative = LegislativeAgent()
        judicial = JudicialAgent()

        assert executive.constitutional_hash == CONSTITUTIONAL_HASH
        assert legislative.constitutional_hash == CONSTITUTIONAL_HASH
        assert judicial.constitutional_hash == CONSTITUTIONAL_HASH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
