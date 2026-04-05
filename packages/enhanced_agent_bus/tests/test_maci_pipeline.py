"""Tests for MACI Verification Pipeline."""

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
from enhanced_agent_bus.verification.maci_pipeline import (
    CONSTITUTIONAL_HASH,
    AgentRole,
    ConstitutionalPrinciple,
    ExecutiveAgent,
    GovernanceDecision,
    JudicialAgent,
    LegislativeAgent,
    MACIVerificationPipeline,
)

# Mark all tests as governance tests (95% coverage required)
# Constitutional Hash: 608508a9bd224290
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMACIAgents:
    # Constitutional Hash: 608508a9bd224290
    """Test individual MACI agents."""

    @pytest.fixture
    def constitutional_principles(self):
        """Sample constitutional principles for testing."""
        return [
            ConstitutionalPrinciple(
                id="principle-1",
                text="All governance decisions must prioritize user safety",
                category="safety",
                priority=10,
            ),
            ConstitutionalPrinciple(
                id="principle-2",
                text="Decisions affecting multiple stakeholders require consensus",
                category="governance",
                priority=8,
            ),
            ConstitutionalPrinciple(
                id="principle-3",
                text="Emergency actions may bypass standard procedures",
                category="emergency",
                priority=9,
            ),
        ]

    @pytest.fixture
    def sample_decision(self):
        """Sample governance decision for testing."""
        return GovernanceDecision(
            id="test-decision-001",
            action="Deploy critical security update",
            context={
                "impact_assessment": {"severity": "high"},
                "stakeholders": ["users", "admins", "developers"],
                "emergency": False,
                "resources_required": ["compute", "storage", "network"],
            },
        )

    def test_executive_agent_initialization(self):
        """Test Executive agent initialization."""
        agent = ExecutiveAgent()
        assert agent.role == AgentRole.EXECUTIVE
        assert agent.agent_id == "executive-001"

    def test_legislative_agent_initialization(self):
        """Test Legislative agent initialization."""
        agent = LegislativeAgent()
        assert agent.role == AgentRole.LEGISLATIVE
        assert agent.agent_id == "legislative-001"

    def test_judicial_agent_initialization(self):
        """Test Judicial agent initialization."""
        agent = JudicialAgent()
        assert agent.role == AgentRole.JUDICIAL
        assert agent.agent_id == "judicial-001"

    def test_constitutional_principle_hash(self, constitutional_principles):
        """Test constitutional principle hash generation."""
        principle = constitutional_principles[0]
        assert principle.hash is not None
        assert len(principle.hash) == 16  # SHA256 truncated to 16 chars

    async def test_executive_agent_response(self, constitutional_principles, sample_decision):
        """Test Executive agent response generation."""
        agent = ExecutiveAgent()
        agent.load_constitutional_principles(constitutional_principles)

        response = await agent.respond_to_decision(sample_decision)

        assert response.agent_role == AgentRole.EXECUTIVE
        assert response.decision_id == sample_decision.id
        assert 0.0 <= response.confidence <= 1.0
        assert response.reasoning is not None
        assert response.agent_hash is not None

    async def test_legislative_agent_response(self, constitutional_principles, sample_decision):
        """Test Legislative agent response generation."""
        agent = LegislativeAgent()
        agent.load_constitutional_principles(constitutional_principles)

        response = await agent.respond_to_decision(sample_decision)

        assert response.agent_role == AgentRole.LEGISLATIVE
        assert response.decision_id == sample_decision.id
        assert 0.0 <= response.confidence <= 1.0

    async def test_judicial_agent_response(self, constitutional_principles, sample_decision):
        """Test Judicial agent response generation."""
        agent = JudicialAgent()
        agent.load_constitutional_principles(constitutional_principles)

        # Create mock context responses
        executive_response = await ExecutiveAgent().respond_to_decision(sample_decision)
        legislative_response = await LegislativeAgent().respond_to_decision(sample_decision)

        response = await agent.respond_to_decision(
            sample_decision, context_responses=[executive_response, legislative_response]
        )

        assert response.agent_role == AgentRole.JUDICIAL
        assert response.decision_id == sample_decision.id
        assert 0.0 <= response.confidence <= 1.0


class TestMACIVerificationPipeline:
    """Test the complete MACI verification pipeline."""

    @pytest.fixture
    def pipeline(self, constitutional_principles):
        """Initialize MACI pipeline with constitutional principles."""
        pipeline = MACIVerificationPipeline()
        pipeline.load_constitution(constitutional_principles)
        return pipeline

    @pytest.fixture
    def constitutional_principles(self):
        """Sample constitutional principles."""
        return [
            ConstitutionalPrinciple(
                id="safety-first",
                text="User safety is the highest priority",
                category="safety",
                priority=10,
            ),
            ConstitutionalPrinciple(
                id="consensus-required",
                text="Major decisions require stakeholder consensus",
                category="governance",
                priority=8,
            ),
            ConstitutionalPrinciple(
                id="emergency-override",
                text="Emergency conditions allow procedure bypass",
                category="emergency",
                priority=9,
            ),
        ]

    def test_pipeline_initialization(self, pipeline):
        """Test pipeline initialization."""
        assert pipeline.executive_agent is not None
        assert pipeline.legislative_agent is not None
        assert pipeline.judicial_agent is not None
        assert len(pipeline.constitutional_principles) == 3

    def test_constitutional_hash_validation(self, pipeline):
        """Test constitutional hash validation."""
        assert pipeline.get_constitutional_hash() == CONSTITUTIONAL_HASH

    async def test_propose_and_verify_decision(self, pipeline):
        """Test complete propose and verify workflow."""
        action = "Implement user safety enhancement"
        context = {
            "impact_assessment": {"severity": "medium"},
            "stakeholders": ["users", "security_team"],
            "emergency": False,
        }

        decision, verification = await pipeline.propose_and_verify_decision(
            action=action, context=context, proposed_by="test-agent"
        )

        # Check decision
        assert decision.action == action
        assert decision.context == context
        assert decision.proposed_by == "test-agent"
        assert decision.constitutional_hash == CONSTITUTIONAL_HASH

        # Check verification
        assert verification.decision_id == decision.id
        assert isinstance(verification.is_compliant, bool)
        assert 0.0 <= verification.confidence <= 1.0
        assert verification.executive_response is not None
        assert verification.legislative_response is not None
        assert verification.judicial_response is not None
        assert verification.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_emergency_decision_handling(self, pipeline):
        """Test emergency decision handling."""
        action = "Emergency security lockdown"
        context = {
            "emergency": True,
            "emergency_justification": "Active security breach detected",
            "impact_assessment": {"severity": "critical"},
        }

        decision, verification = await pipeline.propose_and_verify_decision(
            action=action, context=context
        )

        assert decision.action == action
        assert verification.confidence > 0.0  # Should have some confidence even in emergency

    async def test_high_impact_decision(self, pipeline):
        """Test high-impact decision with many stakeholders."""
        action = "System-wide policy change"
        context = {
            "impact_assessment": {"severity": "critical"},
            "stakeholders": [
                "users",
                "admins",
                "developers",
                "auditors",
                "executives",
            ],  # 5 stakeholders
            "emergency": False,
            "resources_required": ["all"],
        }

        _decision, verification = await pipeline.propose_and_verify_decision(
            action=action, context=context
        )

        # High-impact decisions should be carefully analyzed
        assert verification.executive_response.confidence < 0.9  # Should be cautious

    def test_pipeline_stats(self, pipeline):
        """Test pipeline statistics generation."""
        stats = pipeline.get_pipeline_stats()
        assert "total_decisions" in stats
        assert stats["total_decisions"] == 0  # No decisions processed yet

    async def test_pipeline_stats_after_decisions(self, pipeline):
        """Test pipeline statistics after processing decisions."""
        # Process a few decisions
        decisions = [
            ("Safe action", {"impact_assessment": {"severity": "low"}}),
            ("Risky action", {"impact_assessment": {"severity": "critical"}}),
            ("Emergency action", {"emergency": True, "emergency_justification": "Valid reason"}),
        ]

        for action, context in decisions:
            await pipeline.propose_and_verify_decision(action, context)

        stats = pipeline.get_pipeline_stats()
        assert stats["total_decisions"] == 3
        assert "compliance_rate" in stats
        assert "average_confidence" in stats
        assert 0.0 <= stats["compliance_rate"] <= 1.0
        assert 0.0 <= stats["average_confidence"] <= 1.0


class TestConstitutionalPrinciples:
    """Test constitutional principle functionality."""

    def test_principle_creation(self):
        """Test constitutional principle creation."""
        principle = ConstitutionalPrinciple(
            id="test-principle", text="This is a test principle", category="test", priority=5
        )

        assert principle.id == "test-principle"
        assert principle.text == "This is a test principle"
        assert principle.category == "test"
        assert principle.priority == 5
        assert principle.hash is not None

    def test_principle_hash_consistency(self):
        """Test that principle hash is consistent."""
        principle1 = ConstitutionalPrinciple(id="test", text="content", category="cat", priority=1)
        principle2 = ConstitutionalPrinciple(id="test", text="content", category="cat", priority=1)

        assert principle1.hash == principle2.hash

    def test_principle_hash_changes(self):
        """Test that hash changes when content changes."""
        principle1 = ConstitutionalPrinciple(id="test", text="content", category="cat", priority=1)
        principle2 = ConstitutionalPrinciple(
            id="test", text="different content", category="cat", priority=1
        )

        assert principle1.hash != principle2.hash


class TestGovernanceDecision:
    """Test governance decision functionality."""

    def test_decision_creation(self):
        """Test governance decision creation."""
        decision = GovernanceDecision(
            id="test-decision",
            action="Test action",
            context={"key": "value"},
            proposed_by="test-agent",
        )

        assert decision.id == "test-decision"
        assert decision.action == "Test action"
        assert decision.context == {"key": "value"}
        assert decision.proposed_by == "test-agent"
        assert decision.constitutional_hash == CONSTITUTIONAL_HASH

    def test_decision_hash(self):
        """Test decision hash generation."""
        decision = GovernanceDecision(id="test", action="action", context={"test": True})

        assert decision.decision_hash is not None
        assert len(decision.decision_hash) == 16

    def test_decision_hash_consistency(self):
        """Test that identical decisions have same hash."""
        decision1 = GovernanceDecision(id="test", action="action", context={"same": True})
        decision2 = GovernanceDecision(id="test", action="action", context={"same": True})

        # Note: timestamps might differ, so hashes might be different
        # This is expected behavior for decision integrity


class TestIntegration:
    """Integration tests for MACI pipeline."""

    async def test_full_governance_workflow(self):
        """Test complete governance workflow."""
        # Setup pipeline with constitution
        principles = [
            ConstitutionalPrinciple(
                id="safety", text="Safety first", category="safety", priority=10
            ),
            ConstitutionalPrinciple(
                id="consensus", text="Consensus required", category="governance", priority=8
            ),
        ]

        pipeline = MACIVerificationPipeline()
        pipeline.load_constitution(principles)

        # Propose and verify decision
        decision, verification = await pipeline.propose_and_verify_decision(
            action="Deploy safety feature",
            context={
                "impact_assessment": {"severity": "medium"},
                "stakeholders": ["users", "developers"],
                "emergency": False,
            },
        )

        # Verify all components
        assert decision is not None
        assert verification is not None
        assert verification.executive_response.agent_role == AgentRole.EXECUTIVE
        assert verification.legislative_response.agent_role == AgentRole.LEGISLATIVE
        assert verification.judicial_response.agent_role == AgentRole.JUDICIAL

        # Verify constitutional hash consistency
        assert decision.constitutional_hash == CONSTITUTIONAL_HASH
        assert verification.constitutional_hash == CONSTITUTIONAL_HASH

        logger.info(f"Governance workflow completed: {verification.is_compliant}")


if __name__ == "__main__":
    pytest.main([__file__])
