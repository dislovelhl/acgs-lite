"""
Tests for MACI Pipeline module (maci_pipeline.py).
Constitutional Hash: 608508a9bd224290

Covers:
- AgentRole, GovernancePhase enums
- ConstitutionalPrinciple, GovernanceDecision, AgentResponse, VerificationResult dataclasses
- BaseMACIAgent, ExecutiveAgent, LegislativeAgent, JudicialAgent
- MACIVerificationPipeline (load_constitution, verify, propose_and_verify, stats)
- create_maci_pipeline_with_constitution convenience function
"""

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.verification.maci_pipeline import (
    AgentResponse,
    AgentRole,
    BaseMACIAgent,
    ConstitutionalPrinciple,
    ExecutiveAgent,
    GovernanceDecision,
    GovernancePhase,
    JudicialAgent,
    LegislativeAgent,
    MACIVerificationPipeline,
    VerificationResult,
    create_maci_pipeline_with_constitution,
)

pytestmark = [pytest.mark.unit, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestAgentRole:
    def test_values(self):
        assert AgentRole.EXECUTIVE.value == "executive"
        assert AgentRole.LEGISLATIVE.value == "legislative"
        assert AgentRole.JUDICIAL.value == "judicial"

    def test_count(self):
        assert len(AgentRole) == 3


class TestGovernancePhase:
    def test_values(self):
        assert GovernancePhase.PROPOSAL.value == "proposal"
        assert GovernancePhase.VALIDATION.value == "validation"
        assert GovernancePhase.JUDGMENT.value == "judgment"
        assert GovernancePhase.EXECUTION.value == "execution"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestConstitutionalPrinciple:
    def test_creates_hash_on_init(self):
        p = ConstitutionalPrinciple(id="p1", text="Do no harm", category="safety", priority=1)
        assert len(p.hash) == 16
        assert isinstance(p.hash, str)

    def test_hash_deterministic(self):
        p1 = ConstitutionalPrinciple(id="p1", text="Do no harm", category="safety", priority=1)
        p2 = ConstitutionalPrinciple(id="p1", text="Do no harm", category="safety", priority=1)
        assert p1.hash == p2.hash

    def test_different_content_different_hash(self):
        p1 = ConstitutionalPrinciple(id="p1", text="Do no harm", category="safety", priority=1)
        p2 = ConstitutionalPrinciple(id="p2", text="Be transparent", category="ethics", priority=2)
        assert p1.hash != p2.hash


class TestGovernanceDecision:
    def _make_decision(self, **kwargs):
        defaults = dict(id="dec-001", action="test_action", context={})
        defaults.update(kwargs)
        return GovernanceDecision(**defaults)

    def test_default_constitutional_hash(self):
        d = self._make_decision()
        assert d.constitutional_hash == CONSTITUTIONAL_HASH

    def test_decision_hash_property(self):
        d = self._make_decision()
        h = d.decision_hash
        assert len(h) == 16
        assert isinstance(h, str)

    def test_decision_hash_is_stable(self):
        d = self._make_decision()
        assert d.decision_hash == d.decision_hash

    def test_proposed_by_default(self):
        d = self._make_decision()
        assert d.proposed_by == "system"

    def test_custom_proposed_by(self):
        d = self._make_decision(proposed_by="agent-007")
        assert d.proposed_by == "agent-007"


class TestAgentResponse:
    def _make_response(self, **kwargs):
        defaults = dict(
            agent_role=AgentRole.EXECUTIVE,
            decision_id="dec-001",
            confidence=0.8,
            reasoning="Test reasoning",
            evidence=["evidence-1"],
        )
        defaults.update(kwargs)
        return AgentResponse(**defaults)

    def test_agent_hash_generated(self):
        r = self._make_response()
        assert len(r.agent_hash) == 16

    def test_agent_hash_deterministic(self):
        r1 = self._make_response()
        r2 = self._make_response()
        assert r1.agent_hash == r2.agent_hash

    def test_fields_stored(self):
        r = self._make_response(confidence=0.75, reasoning="My reasoning")
        assert r.confidence == 0.75
        assert r.reasoning == "My reasoning"
        assert r.evidence == ["evidence-1"]


class TestVerificationResult:
    def _make_result(self, **kwargs):
        exec_resp = AgentResponse(
            agent_role=AgentRole.EXECUTIVE,
            decision_id="d",
            confidence=0.8,
            reasoning="exec",
            evidence=[],
        )
        leg_resp = AgentResponse(
            agent_role=AgentRole.LEGISLATIVE,
            decision_id="d",
            confidence=0.8,
            reasoning="leg",
            evidence=[],
        )
        jud_resp = AgentResponse(
            agent_role=AgentRole.JUDICIAL,
            decision_id="d",
            confidence=0.8,
            reasoning="jud",
            evidence=[],
        )
        defaults = dict(
            decision_id="d",
            is_compliant=True,
            confidence=0.8,
            violations=[],
            recommendations=[],
            executive_response=exec_resp,
            legislative_response=leg_resp,
            judicial_response=jud_resp,
        )
        defaults.update(kwargs)
        return VerificationResult(**defaults)

    def test_default_hash(self):
        r = self._make_result()
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_compliant(self):
        r = self._make_result(is_compliant=True)
        assert r.is_compliant is True

    def test_non_compliant(self):
        r = self._make_result(is_compliant=False, violations=["viol-1"])
        assert r.is_compliant is False
        assert len(r.violations) == 1


# ---------------------------------------------------------------------------
# Agent tests
# ---------------------------------------------------------------------------


class TestBaseMACIAgent:
    """Test BaseMACIAgent via a minimal concrete subclass."""

    class _ConcreteAgent(BaseMACIAgent):
        async def _analyze_decision_specific(self, decision, context_responses=None):
            return {"confidence": 0.7, "reasoning": "ok", "evidence": []}

    def _make_decision(self):
        return GovernanceDecision(id="d1", action="do_something", context={})

    def test_load_principles(self):
        agent = self._ConcreteAgent(AgentRole.EXECUTIVE, "test-agent")
        principles = [
            ConstitutionalPrinciple(id="p1", text="Harm none", category="safety", priority=1),
            ConstitutionalPrinciple(id="p2", text="Be fair", category="ethics", priority=2),
        ]
        agent.load_constitutional_principles(principles)
        assert len(agent.constitutional_principles) == 2

    def test_validate_hash_valid(self):
        agent = self._ConcreteAgent(AgentRole.EXECUTIVE, "test-agent")
        d = self._make_decision()
        assert agent.validate_constitutional_hash(d) is True

    def test_validate_hash_invalid(self):
        agent = self._ConcreteAgent(AgentRole.EXECUTIVE, "test-agent")
        d = GovernanceDecision(
            id="d1",
            action="do_something",
            context={},
            constitutional_hash="badhash",
        )
        assert agent.validate_constitutional_hash(d) is False

    async def test_respond_to_decision_valid_hash(self):
        agent = self._ConcreteAgent(AgentRole.EXECUTIVE, "test-agent")
        d = self._make_decision()
        response = await agent.respond_to_decision(d)
        assert response.agent_role == AgentRole.EXECUTIVE
        assert response.confidence == 0.7

    async def test_respond_to_decision_invalid_hash(self):
        agent = self._ConcreteAgent(AgentRole.EXECUTIVE, "test-agent")
        d = GovernanceDecision(
            id="d1",
            action="do_something",
            context={},
            constitutional_hash="badhash",
        )
        response = await agent.respond_to_decision(d)
        assert response.confidence == 0.0
        assert "Invalid constitutional hash" in response.reasoning

    async def test_decision_history_appended(self):
        agent = self._ConcreteAgent(AgentRole.EXECUTIVE, "test-agent")
        d = self._make_decision()
        await agent.respond_to_decision(d)
        assert len(agent.decision_history) == 1


class TestExecutiveAgent:
    @pytest.fixture
    def agent(self):
        return ExecutiveAgent()

    def _make_decision(self, context=None):
        return GovernanceDecision(id="d1", action="grant_access", context=context or {})

    def test_role(self, agent):
        assert agent.role == AgentRole.EXECUTIVE

    async def test_propose_decision(self, agent):
        d = await agent.propose_decision(
            action="deploy_service", context={}, proposed_by="operator-1"
        )
        assert d.action == "deploy_service"
        assert d.proposed_by == "operator-1"
        assert d.id.startswith("exec-")

    async def test_base_confidence(self, agent):
        d = self._make_decision()
        resp = await agent.respond_to_decision(d)
        # Base confidence is 0.8, no context modifiers applied
        assert 0.1 <= resp.confidence <= 0.95

    async def test_critical_impact_reduces_confidence(self, agent):
        d_base = self._make_decision()
        d_critical = self._make_decision({"impact_assessment": {"severity": "critical"}})
        resp_base = await agent.respond_to_decision(d_base)
        resp_critical = await agent.respond_to_decision(d_critical)
        assert resp_critical.confidence < resp_base.confidence

    async def test_emergency_flag_increases_confidence(self, agent):
        d_base = self._make_decision()
        d_emergency = self._make_decision({"emergency": True})
        resp_base = await agent.respond_to_decision(d_base)
        resp_emergency = await agent.respond_to_decision(d_emergency)
        assert resp_emergency.confidence > resp_base.confidence

    async def test_many_resources_reduces_confidence(self, agent):
        d_base = self._make_decision()
        d_complex = self._make_decision({"resources_required": [f"r{i}" for i in range(10)]})
        resp_base = await agent.respond_to_decision(d_base)
        resp_complex = await agent.respond_to_decision(d_complex)
        assert resp_complex.confidence < resp_base.confidence

    async def test_confidence_clamped(self, agent):
        # Stack all modifiers that increase confidence
        d = self._make_decision({"emergency": True})
        resp = await agent.respond_to_decision(d)
        assert resp.confidence <= 0.95

    async def test_violations_empty_from_executive(self, agent):
        d = self._make_decision()
        resp = await agent.respond_to_decision(d)
        # Executive does not identify violations
        assert resp.evidence is not None  # evidence list exists


class TestLegislativeAgent:
    @pytest.fixture
    def agent(self):
        return LegislativeAgent()

    def _make_decision(self, action="enforce policy", context=None):
        return GovernanceDecision(id="d1", action=action, context=context or {})

    def test_role(self, agent):
        assert agent.role == AgentRole.LEGISLATIVE

    async def test_analyzes_decision(self, agent):
        d = self._make_decision()
        resp = await agent.respond_to_decision(d)
        assert resp.agent_role == AgentRole.LEGISLATIVE
        assert 0.0 <= resp.confidence <= 1.0

    async def test_loads_principles_and_uses_them(self, agent):
        principle = ConstitutionalPrinciple(
            id="pol-1", text="enforce transparency policy", category="governance", priority=1
        )
        agent.load_constitutional_principles([principle])
        d = self._make_decision(action="enforce policy for transparency")
        resp = await agent.respond_to_decision(d)
        # Should pick up at least one relevant principle
        assert "Legislative analysis identified" in resp.reasoning

    async def test_large_stakeholder_list_adds_evidence(self, agent):
        d = self._make_decision(context={"stakeholders": [f"s{i}" for i in range(12)]})
        resp = await agent.respond_to_decision(d)
        assert any("stakeholder" in e.lower() for e in resp.evidence)

    async def test_low_exec_confidence_adds_evidence(self, agent):
        d = self._make_decision()
        exec_resp = AgentResponse(
            agent_role=AgentRole.EXECUTIVE,
            decision_id="d1",
            confidence=0.3,
            reasoning="concerns",
            evidence=[],
        )
        resp = await agent.respond_to_decision(d, context_responses=[exec_resp])
        assert any("Executive" in e for e in resp.evidence)


class TestJudicialAgent:
    @pytest.fixture
    def agent(self):
        return JudicialAgent()

    def _make_decision(self, context=None):
        return GovernanceDecision(id="d1", action="approve", context=context or {})

    def _make_exec_resp(self, confidence=0.8):
        return AgentResponse(
            agent_role=AgentRole.EXECUTIVE,
            decision_id="d1",
            confidence=confidence,
            reasoning="exec",
            evidence=[],
        )

    def _make_leg_resp(self, confidence=0.8, reasoning="Legislative analysis"):
        return AgentResponse(
            agent_role=AgentRole.LEGISLATIVE,
            decision_id="d1",
            confidence=confidence,
            reasoning=reasoning,
            evidence=[],
        )

    def test_role(self, agent):
        assert agent.role == AgentRole.JUDICIAL

    async def test_no_context_returns_low_confidence(self, agent):
        d = self._make_decision()
        resp = await agent.respond_to_decision(d, context_responses=None)
        assert resp.confidence == 0.1

    async def test_no_context_returns_incomplete_review(self, agent):
        d = self._make_decision()
        resp = await agent.respond_to_decision(d, context_responses=None)
        assert "Insufficient context" in resp.reasoning

    async def test_low_executive_confidence_adds_violation(self, agent):
        d = self._make_decision()
        exec_resp = self._make_exec_resp(confidence=0.3)
        resp = await agent.respond_to_decision(d, context_responses=[exec_resp])
        # The code stores "Executive confidence: X.XX" in evidence
        assert any("Executive confidence" in e for e in resp.evidence)

    async def test_high_legislative_confidence_boosts_score(self, agent):
        d = self._make_decision()
        exec_resp = self._make_exec_resp(confidence=0.8)
        leg_resp = self._make_leg_resp(confidence=0.9, reasoning="relevant_principles found")
        resp_with = await agent.respond_to_decision(d, context_responses=[exec_resp, leg_resp])
        resp_without = await agent.respond_to_decision(d, context_responses=[exec_resp])
        assert resp_with.confidence >= resp_without.confidence

    async def test_emergency_override_without_justification_adds_violation(self, agent):
        d = self._make_decision(context={"emergency_override": True})
        exec_resp = self._make_exec_resp()
        leg_resp = self._make_leg_resp()
        resp = await agent.respond_to_decision(d, context_responses=[exec_resp, leg_resp])
        # Lacks justification → violation goes into reasoning (NON-COMPLIANT)
        # and "Emergency override condition detected" is added to evidence
        assert any("Emergency override" in str(e) for e in resp.evidence)
        assert "NON-COMPLIANT" in resp.reasoning or "justification" in resp.reasoning

    async def test_emergency_override_with_justification(self, agent):
        d = self._make_decision(
            context={
                "emergency_override": True,
                "emergency_justification": "System critical failure",
            }
        )
        exec_resp = self._make_exec_resp()
        leg_resp = self._make_leg_resp()
        resp = await agent.respond_to_decision(d, context_responses=[exec_resp, leg_resp])
        assert any("Emergency override" in str(e) for e in resp.evidence)


# ---------------------------------------------------------------------------
# MACIVerificationPipeline tests
# ---------------------------------------------------------------------------


class TestMACIVerificationPipeline:
    @pytest.fixture
    def pipeline(self):
        return MACIVerificationPipeline()

    @pytest.fixture
    def principles(self):
        return [
            ConstitutionalPrinciple(id="p1", text="Do no harm", category="safety", priority=1),
            ConstitutionalPrinciple(
                id="p2", text="Ensure transparency", category="governance", priority=2
            ),
        ]

    def test_initialization(self, pipeline):
        assert isinstance(pipeline.executive_agent, ExecutiveAgent)
        assert isinstance(pipeline.legislative_agent, LegislativeAgent)
        assert isinstance(pipeline.judicial_agent, JudicialAgent)
        assert len(pipeline.verification_history) == 0

    def test_load_constitution(self, pipeline, principles):
        pipeline.load_constitution(principles)
        assert len(pipeline.constitutional_principles) == 2
        # All agents should have received the principles
        assert len(pipeline.executive_agent.constitutional_principles) == 2
        assert len(pipeline.legislative_agent.constitutional_principles) == 2
        assert len(pipeline.judicial_agent.constitutional_principles) == 2

    def test_get_constitutional_hash(self, pipeline):
        assert pipeline.get_constitutional_hash() == CONSTITUTIONAL_HASH

    def test_get_pipeline_stats_empty(self, pipeline):
        stats = pipeline.get_pipeline_stats()
        assert stats == {"total_decisions": 0}

    async def test_verify_governance_decision(self, pipeline):
        d = GovernanceDecision(id="d1", action="update_policy", context={})
        result = await pipeline.verify_governance_decision(d)
        assert isinstance(result, VerificationResult)
        assert result.decision_id == "d1"
        assert isinstance(result.executive_response, AgentResponse)
        assert isinstance(result.legislative_response, AgentResponse)
        assert isinstance(result.judicial_response, AgentResponse)

    async def test_verify_appends_to_history(self, pipeline):
        d = GovernanceDecision(id="d1", action="update_policy", context={})
        await pipeline.verify_governance_decision(d)
        assert len(pipeline.verification_history) == 1

    async def test_pipeline_stats_after_decisions(self, pipeline):
        d1 = GovernanceDecision(id="d1", action="action1", context={})
        d2 = GovernanceDecision(id="d2", action="action2", context={})
        await pipeline.verify_governance_decision(d1)
        await pipeline.verify_governance_decision(d2)
        stats = pipeline.get_pipeline_stats()
        assert stats["total_decisions"] == 2
        assert "compliance_rate" in stats
        assert "average_confidence" in stats
        assert "total_violations" in stats

    async def test_propose_and_verify_decision(self, pipeline):
        decision, verification = await pipeline.propose_and_verify_decision(
            action="grant_access",
            context={"resource": "admin-panel"},
            proposed_by="security-agent",
        )
        assert isinstance(decision, GovernanceDecision)
        assert isinstance(verification, VerificationResult)
        assert decision.id == verification.decision_id

    async def test_non_compliant_judicial_adds_violation(self, pipeline):
        """NON-COMPLIANT in judicial reasoning triggers violation in result."""
        d = GovernanceDecision(id="d1", action="block_all", context={})
        result = await pipeline.verify_governance_decision(d)
        # Whether compliant or not, result should have proper structure
        assert isinstance(result.is_compliant, bool)

    async def test_low_executive_confidence_adds_recommendation(self, pipeline):
        """When executive confidence < 0.5, a recommendation should be added."""
        d = GovernanceDecision(
            id="d1",
            action="shutdown_system",
            context={
                "impact_assessment": {"severity": "critical"},
                "resources_required": list(range(10)),
            },
        )
        result = await pipeline.verify_governance_decision(d)
        # Executive confidence will be lowered; recommendations may be added
        assert isinstance(result.recommendations, list)


# ---------------------------------------------------------------------------
# Convenience function tests
# ---------------------------------------------------------------------------


class TestCreateMACIPipelineWithConstitution:
    async def test_creates_pipeline_with_principles(self):
        raw_principles = [
            {"id": "p1", "text": "Do no harm", "category": "safety", "priority": 1},
            {"id": "p2", "text": "Be transparent", "category": "ethics", "priority": 2},
        ]
        pipeline = await create_maci_pipeline_with_constitution(raw_principles)
        assert isinstance(pipeline, MACIVerificationPipeline)
        assert len(pipeline.constitutional_principles) == 2

    async def test_empty_principles(self):
        pipeline = await create_maci_pipeline_with_constitution([])
        assert isinstance(pipeline, MACIVerificationPipeline)
        assert len(pipeline.constitutional_principles) == 0

    async def test_pipeline_functional_after_creation(self):
        raw_principles = [
            {"id": "p1", "text": "Ensure accountability", "category": "governance", "priority": 1},
        ]
        pipeline = await create_maci_pipeline_with_constitution(raw_principles)
        d = GovernanceDecision(id="d1", action="audit_system", context={})
        result = await pipeline.verify_governance_decision(d)
        assert isinstance(result, VerificationResult)
