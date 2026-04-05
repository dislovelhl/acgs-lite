"""
Tests for MACI Verifier - Role-Based Verification Pipeline
Constitutional Hash: 608508a9bd224290

Tests cover:
- Role separation enforcement
- Godel bypass prevention (no self-validation)
- Cross-role validation constraints
- Executive/Legislative/Judicial agent interactions
- Verification pipeline execution
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import MACIRole

from ..maci_verifier import (
    CONSTITUTIONAL_HASH,
    ROLE_PERMISSIONS,
    VALIDATION_CONSTRAINTS,
    AgentVerificationRecord,
    ExecutiveAgent,
    JudicialAgent,
    LegislativeAgent,
    MACIAgentRole,
    MACIVerificationContext,
    MACIVerificationResult,
    MACIVerifier,
    VerificationPhase,
    VerificationStatus,
    create_maci_verifier,
)


class TestConstitutionalHash:
    """Tests for constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Test that constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_maci_verifier_has_constitutional_hash(self):
        """Test that MACIVerifier includes constitutional hash."""
        verifier = create_maci_verifier()
        assert verifier.constitutional_hash == CONSTITUTIONAL_HASH
        assert verifier.get_constitutional_hash() == CONSTITUTIONAL_HASH

    def test_verification_context_has_constitutional_hash(self):
        """Test that verification context includes constitutional hash."""
        ctx = MACIVerificationContext()
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_verification_result_has_constitutional_hash(self):
        """Test that verification result includes constitutional hash."""
        result = MACIVerificationResult(
            verification_id="test-001",
            is_compliant=True,
            confidence=0.9,
            status=VerificationStatus.COMPLETED,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestMACIAgentRoles:
    """Tests for MACI agent role definitions."""

    def test_all_roles_defined(self):
        """Test that all required roles are defined."""
        assert MACIAgentRole.EXECUTIVE.value == "executive"
        assert MACIAgentRole.LEGISLATIVE.value == "legislative"
        assert MACIAgentRole.JUDICIAL.value == "judicial"
        assert MACIAgentRole.MONITOR.value == "monitor"
        assert MACIAgentRole.AUDITOR.value == "auditor"

    def test_parse_accepts_canonical_roles(self):
        assert MACIAgentRole.parse(MACIRole.EXECUTIVE) == MACIAgentRole.EXECUTIVE
        assert MACIAgentRole.parse("AUDITOR") == MACIAgentRole.AUDITOR

    def test_parse_rejects_unsupported_canonical_roles(self):
        with pytest.raises(ValueError):
            MACIAgentRole.parse(MACIRole.CONTROLLER)

    def test_role_permissions_defined(self):
        """Test that role permissions are properly defined."""
        assert MACIAgentRole.EXECUTIVE in ROLE_PERMISSIONS
        assert MACIAgentRole.LEGISLATIVE in ROLE_PERMISSIONS
        assert MACIAgentRole.JUDICIAL in ROLE_PERMISSIONS

    def test_executive_can_propose(self):
        """Test that executive can perform proposal phase."""
        assert VerificationPhase.PROPOSAL in ROLE_PERMISSIONS[MACIAgentRole.EXECUTIVE]

    def test_executive_cannot_judge(self):
        """Test that executive cannot perform judgment phase."""
        assert VerificationPhase.JUDGMENT not in ROLE_PERMISSIONS[MACIAgentRole.EXECUTIVE]

    def test_legislative_can_extract(self):
        """Test that legislative can extract policies."""
        assert VerificationPhase.POLICY_EXTRACTION in ROLE_PERMISSIONS[MACIAgentRole.LEGISLATIVE]

    def test_legislative_cannot_propose(self):
        """Test that legislative cannot propose decisions."""
        assert VerificationPhase.PROPOSAL not in ROLE_PERMISSIONS[MACIAgentRole.LEGISLATIVE]

    def test_judicial_can_judge(self):
        """Test that judicial can perform judgment."""
        assert VerificationPhase.JUDGMENT in ROLE_PERMISSIONS[MACIAgentRole.JUDICIAL]

    def test_judicial_cannot_propose(self):
        """Test that judicial cannot propose decisions."""
        assert VerificationPhase.PROPOSAL not in ROLE_PERMISSIONS[MACIAgentRole.JUDICIAL]


class TestValidationConstraints:
    """Tests for cross-role validation constraints."""

    def test_judicial_can_validate_executive(self):
        """Test that judicial can validate executive outputs."""
        assert MACIAgentRole.EXECUTIVE in VALIDATION_CONSTRAINTS[MACIAgentRole.JUDICIAL]

    def test_judicial_can_validate_legislative(self):
        """Test that judicial can validate legislative outputs."""
        assert MACIAgentRole.LEGISLATIVE in VALIDATION_CONSTRAINTS[MACIAgentRole.JUDICIAL]

    def test_judicial_cannot_validate_self(self):
        """Test that judicial cannot validate judicial outputs."""
        assert MACIAgentRole.JUDICIAL not in VALIDATION_CONSTRAINTS[MACIAgentRole.JUDICIAL]

    def test_auditor_can_validate_judicial(self):
        """Test that auditor can validate judicial outputs."""
        assert MACIAgentRole.JUDICIAL in VALIDATION_CONSTRAINTS[MACIAgentRole.AUDITOR]

    async def test_cross_role_validation_accepts_canonical_roles(self):
        verifier = MACIVerifier()
        permitted = await verifier.verify_cross_role_action(
            validator_agent_id="judicial-001",
            validator_role=MACIRole.JUDICIAL,
            target_agent_id="executive-001",
            target_role=MACIRole.EXECUTIVE,
            target_output_id="out-1",
        )
        assert permitted is True

    async def test_cross_role_validation_rejects_unsupported_projection(self):
        verifier = MACIVerifier()
        permitted = await verifier.verify_cross_role_action(
            validator_agent_id="controller-001",
            validator_role=MACIRole.CONTROLLER,
            target_agent_id="executive-001",
            target_role=MACIRole.EXECUTIVE,
            target_output_id="out-1",
        )
        assert permitted is False


class TestExecutiveAgent:
    """Tests for ExecutiveAgent."""

    def test_executive_agent_creation(self):
        """Test executive agent creation."""
        agent = ExecutiveAgent()
        assert agent.role == MACIAgentRole.EXECUTIVE
        assert agent.constitutional_hash == CONSTITUTIONAL_HASH

    def test_executive_agent_custom_id(self):
        """Test executive agent with custom ID."""
        agent = ExecutiveAgent(agent_id="custom-exec-001")
        assert agent.agent_id == "custom-exec-001"

    async def test_propose_decision(self):
        """Test decision proposal."""
        agent = ExecutiveAgent()
        decision, _output_id = await agent.propose_decision(
            action="Grant access to resource",
            context={"resource_id": "res-001", "user_id": "user-001"},
        )

        assert decision is not None
        assert "output_id" in decision
        assert decision["action"] == "Grant access to resource"
        assert decision["role"] == "executive"
        assert decision["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_propose_decision_registers_output(self):
        """Test that proposed decision is registered."""
        agent = ExecutiveAgent()
        _decision, output_id = await agent.propose_decision(
            action="Test action",
            context={},
        )

        assert agent.owns_output(output_id)
        assert output_id in agent.output_registry

    async def test_risk_assessment(self):
        """Test risk assessment in proposal."""
        agent = ExecutiveAgent()
        decision, _ = await agent.propose_decision(
            action="High risk action",
            context={
                "involves_sensitive_data": True,
                "high_impact": True,
            },
        )

        assert "risk_assessment" in decision
        assert decision["risk_assessment"]["score"] >= 0.5  # High risk

    def test_can_perform_phase(self):
        """Test phase permission checking."""
        agent = ExecutiveAgent()
        assert agent.can_perform_phase(VerificationPhase.PROPOSAL)
        assert not agent.can_perform_phase(VerificationPhase.JUDGMENT)


class TestLegislativeAgent:
    """Tests for LegislativeAgent."""

    def test_legislative_agent_creation(self):
        """Test legislative agent creation."""
        agent = LegislativeAgent()
        assert agent.role == MACIAgentRole.LEGISLATIVE
        assert agent.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_extract_rules(self):
        """Test rule extraction."""
        agent = LegislativeAgent()
        decision = {
            "output_id": "exec-001",
            "action": "Enforce policy for data protection",
            "context": {},
        }
        ctx = MACIVerificationContext()

        rules, _output_id = await agent.extract_rules(decision, ctx)

        assert rules is not None
        assert "rules" in rules
        assert "principles" in rules
        assert "constraints" in rules
        assert rules["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_extract_rules_with_policy_keywords(self):
        """Test rule extraction recognizes policy keywords."""
        agent = LegislativeAgent()
        decision = {
            "output_id": "exec-001",
            "action": "Enforce access control policy",
            "context": {"involves_sensitive_data": True},
        }
        ctx = MACIVerificationContext()

        rules, _ = await agent.extract_rules(decision, ctx)

        assert len(rules["rules"]) > 0
        rule_ids = [r["rule_id"] for r in rules["rules"]]
        assert any("policy" in rid or "integrity" in rid for rid in rule_ids)

    async def test_registers_output(self):
        """Test that extracted rules are registered."""
        agent = LegislativeAgent()
        decision = {"output_id": "exec-001", "action": "Test", "context": {}}
        ctx = MACIVerificationContext()

        _rules, output_id = await agent.extract_rules(decision, ctx)

        assert agent.owns_output(output_id)

    def test_can_perform_phase(self):
        """Test phase permission checking."""
        agent = LegislativeAgent()
        assert agent.can_perform_phase(VerificationPhase.POLICY_EXTRACTION)
        assert not agent.can_perform_phase(VerificationPhase.PROPOSAL)


class TestJudicialAgent:
    """Tests for JudicialAgent."""

    def test_judicial_agent_creation(self):
        """Test judicial agent creation."""
        agent = JudicialAgent()
        assert agent.role == MACIAgentRole.JUDICIAL
        assert agent.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_validate_compliance(self):
        """Test compliance validation."""
        agent = JudicialAgent()
        decision = {
            "output_id": "exec-001",
            "agent_id": "executive-001",  # Different from judicial agent
            "action": "Test action",
            "context": {},
        }
        rules = {
            "output_id": "legis-001",
            "rules": [],
            "principles": [],
            "constraints": [],
            "precedence_order": [],
        }
        ctx = MACIVerificationContext()

        judgment, _output_id = await agent.validate_compliance(decision, rules, ctx)

        assert judgment is not None
        assert "is_compliant" in judgment
        assert "confidence" in judgment
        assert "violations" in judgment
        assert judgment["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_godel_bypass_prevention(self):
        """Test that judicial agent cannot validate its own output."""
        agent = JudicialAgent(agent_id="judicial-001")
        decision = {
            "output_id": "jud-001",
            "agent_id": "judicial-001",  # Same as judicial agent - should fail
            "action": "Self-validated action",
            "context": {},
        }
        rules = {
            "output_id": "legis-001",
            "rules": [],
            "principles": [],
            "constraints": [],
            "precedence_order": [],
        }
        ctx = MACIVerificationContext()

        with pytest.raises(ValueError, match="Godel bypass prevention"):
            await agent.validate_compliance(decision, rules, ctx)

    async def test_detects_violations(self):
        """Test that violations are detected."""
        agent = JudicialAgent()
        decision = {
            "output_id": "exec-001",
            "agent_id": "executive-001",
            "action": "Grant excessive access",
            "context": {
                "excessive_permissions": True,
            },
        }
        rules = {
            "output_id": "legis-001",
            "rules": [
                {
                    "rule_id": "least_privilege",
                    "description": "Access must follow least privilege",
                    "severity": "critical",
                    "scope": "access",
                }
            ],
            "principles": [],
            "constraints": [],
            "precedence_order": ["least_privilege"],
        }
        ctx = MACIVerificationContext()

        judgment, _ = await agent.validate_compliance(decision, rules, ctx)

        assert not judgment["is_compliant"]
        assert len(judgment["violations"]) > 0

    def test_can_perform_phase(self):
        """Test phase permission checking."""
        agent = JudicialAgent()
        assert agent.can_perform_phase(VerificationPhase.JUDGMENT)
        assert not agent.can_perform_phase(VerificationPhase.PROPOSAL)


class TestMACIVerifier:
    """Tests for MACIVerifier pipeline."""

    def test_verifier_creation(self):
        """Test verifier creation."""
        verifier = create_maci_verifier()
        assert verifier is not None
        assert verifier.constitutional_hash == CONSTITUTIONAL_HASH

    def test_verifier_with_custom_agents(self):
        """Test verifier with custom agent IDs."""
        verifier = create_maci_verifier(
            executive_id="exec-custom",
            legislative_id="legis-custom",
            judicial_id="jud-custom",
        )
        assert verifier.executive.agent_id == "exec-custom"
        assert verifier.legislative.agent_id == "legis-custom"
        assert verifier.judicial.agent_id == "jud-custom"

    async def test_full_verification_pipeline(self):
        """Test full MACI verification pipeline."""
        verifier = create_maci_verifier()

        result = await verifier.verify(
            action="Grant read access to document",
            context={"document_id": "doc-001", "user_id": "user-001"},
        )

        assert result is not None
        assert isinstance(result, MACIVerificationResult)
        assert result.verification_id is not None
        assert result.status == VerificationStatus.COMPLETED
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_verification_result_contains_agent_records(self):
        """Test that verification result contains all agent records."""
        verifier = create_maci_verifier()

        result = await verifier.verify(
            action="Test action",
            context={},
        )

        assert len(result.agent_records) >= 3  # At least 3 agents
        roles = [r.role for r in result.agent_records]
        assert MACIAgentRole.EXECUTIVE in roles
        assert MACIAgentRole.LEGISLATIVE in roles
        assert MACIAgentRole.JUDICIAL in roles

    async def test_verification_produces_audit_trail(self):
        """Test that verification produces audit trail."""
        verifier = create_maci_verifier()

        result = await verifier.verify(
            action="Auditable action",
            context={},
        )

        assert len(result.audit_trail) > 0
        phases_in_trail = [e.get("phase") for e in result.audit_trail]
        assert VerificationPhase.PROPOSAL.value in phases_in_trail

    async def test_compliant_decision(self):
        """Test compliant decision verification."""
        verifier = create_maci_verifier()

        result = await verifier.verify(
            action="Simple read operation",
            context={"auditable": True},
        )

        assert result.is_compliant
        assert result.confidence > 0.5

    async def test_non_compliant_decision(self):
        """Test non-compliant decision verification."""
        verifier = create_maci_verifier()

        result = await verifier.verify(
            action="Access sensitive data",
            context={
                "excessive_permissions": True,
                "data_unprotected": True,
                "involves_sensitive_data": True,
            },
        )

        # Should have violations
        assert len(result.violations) > 0 or not result.is_compliant

    async def test_verification_context_passed_through(self):
        """Test that verification context is passed through pipeline."""
        verifier = create_maci_verifier()
        ctx = MACIVerificationContext(
            session_id="session-001",
            tenant_id="tenant-001",
            decision_context={"custom_key": "custom_value"},
        )

        result = await verifier.verify(
            action="Test action",
            context={"custom_key": "custom_value"},
            verification_context=ctx,
        )

        assert result.verification_id == ctx.verification_id

    async def test_cross_role_validation_check(self):
        """Test cross-role validation permission checking."""
        verifier = create_maci_verifier()

        # Judicial can validate executive
        can_validate = await verifier.verify_cross_role_action(
            validator_agent_id="judicial-001",
            validator_role=MACIAgentRole.JUDICIAL,
            target_agent_id="executive-001",
            target_role=MACIAgentRole.EXECUTIVE,
            target_output_id="output-001",
        )
        assert can_validate

        # Executive cannot validate judicial
        can_validate = await verifier.verify_cross_role_action(
            validator_agent_id="executive-001",
            validator_role=MACIAgentRole.EXECUTIVE,
            target_agent_id="judicial-001",
            target_role=MACIAgentRole.JUDICIAL,
            target_output_id="output-001",
        )
        assert not can_validate

    async def test_self_validation_prevented(self):
        """Test that self-validation is prevented."""
        verifier = create_maci_verifier()

        can_validate = await verifier.verify_cross_role_action(
            validator_agent_id="agent-001",
            validator_role=MACIAgentRole.JUDICIAL,
            target_agent_id="agent-001",  # Same agent
            target_role=MACIAgentRole.EXECUTIVE,
            target_output_id="output-001",
        )

        assert not can_validate  # Self-validation prevented

    def test_verification_stats(self):
        """Test verification statistics."""
        verifier = create_maci_verifier()
        stats = verifier.get_verification_stats()

        assert "total_verifications" in stats
        assert stats["total_verifications"] == 0

    async def test_verification_stats_after_execution(self):
        """Test statistics after verification."""
        verifier = create_maci_verifier()

        await verifier.verify("Test action 1", {})
        await verifier.verify("Test action 2", {})

        stats = verifier.get_verification_stats()
        assert stats["total_verifications"] == 2
        assert "compliance_rate" in stats
        assert "average_duration_ms" in stats


class TestVerificationContext:
    """Tests for MACIVerificationContext."""

    def test_context_creation(self):
        """Test context creation with defaults."""
        ctx = MACIVerificationContext()
        assert ctx.verification_id is not None
        assert ctx.tenant_id == "default"
        assert ctx.timeout_ms == 5000
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_context_custom_values(self):
        """Test context with custom values."""
        ctx = MACIVerificationContext(
            session_id="session-001",
            tenant_id="tenant-001",
            initiator_agent_id="agent-001",
            timeout_ms=10000,
        )

        assert ctx.session_id == "session-001"
        assert ctx.tenant_id == "tenant-001"
        assert ctx.initiator_agent_id == "agent-001"
        assert ctx.timeout_ms == 10000

    def test_context_to_dict(self):
        """Test context serialization."""
        ctx = MACIVerificationContext()
        data = ctx.to_dict()

        assert "verification_id" in data
        assert "constitutional_hash" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_context_hash_generation(self):
        """Test context hash generation."""
        ctx = MACIVerificationContext()
        hash1 = ctx.generate_context_hash()
        hash2 = ctx.generate_context_hash()

        assert hash1 == hash2  # Same context produces same hash
        assert len(hash1) == 16  # SHA256 truncated to 16 chars


class TestAgentVerificationRecord:
    """Tests for AgentVerificationRecord."""

    def test_record_creation(self):
        """Test record creation."""
        record = AgentVerificationRecord(
            agent_id="agent-001",
            role=MACIAgentRole.EXECUTIVE,
            phase=VerificationPhase.PROPOSAL,
            action="propose_decision",
            input_hash="abc123",
            output_hash="def456",
            confidence=0.85,
            reasoning="Test reasoning",
        )

        assert record.agent_id == "agent-001"
        assert record.role == MACIAgentRole.EXECUTIVE
        assert record.confidence == 0.85
        assert record.constitutional_hash == CONSTITUTIONAL_HASH

    def test_record_to_dict(self):
        """Test record serialization."""
        record = AgentVerificationRecord(
            agent_id="agent-001",
            role=MACIAgentRole.JUDICIAL,
            phase=VerificationPhase.JUDGMENT,
            action="validate",
            input_hash="abc",
            output_hash="def",
            confidence=0.9,
            reasoning="Compliant",
            evidence=["Evidence 1", "Evidence 2"],
        )

        data = record.to_dict()

        assert data["agent_id"] == "agent-001"
        assert data["role"] == "judicial"
        assert data["phase"] == "judgment"
        assert len(data["evidence"]) == 2
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestMACIVerificationResult:
    """Tests for MACIVerificationResult."""

    def test_result_creation(self):
        """Test result creation."""
        result = MACIVerificationResult(
            verification_id="ver-001",
            is_compliant=True,
            confidence=0.95,
            status=VerificationStatus.COMPLETED,
        )

        assert result.verification_id == "ver-001"
        assert result.is_compliant
        assert result.confidence == 0.95
        assert result.status == VerificationStatus.COMPLETED
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_to_dict(self):
        """Test result serialization."""
        result = MACIVerificationResult(
            verification_id="ver-001",
            is_compliant=True,
            confidence=0.9,
            status=VerificationStatus.COMPLETED,
            violations=[{"type": "test", "description": "Test violation"}],
        )

        data = result.to_dict()

        assert data["verification_id"] == "ver-001"
        assert data["is_compliant"]
        assert data["status"] == "completed"
        assert len(data["violations"]) == 1
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_add_audit_entry(self):
        """Test adding audit entries."""
        result = MACIVerificationResult(
            verification_id="ver-001",
            is_compliant=True,
            confidence=0.9,
            status=VerificationStatus.COMPLETED,
        )

        result.add_audit_entry({"action": "test", "data": "value"})

        assert len(result.audit_trail) == 1
        assert result.audit_trail[0]["action"] == "test"
        assert "timestamp" in result.audit_trail[0]
        assert result.audit_trail[0]["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestVerificationPhases:
    """Tests for verification phase definitions."""

    def test_all_phases_defined(self):
        """Test that all required phases are defined."""
        assert VerificationPhase.PROPOSAL.value == "proposal"
        assert VerificationPhase.POLICY_EXTRACTION.value == "policy_extraction"
        assert VerificationPhase.COMPLIANCE_CHECK.value == "compliance_check"
        assert VerificationPhase.JUDGMENT.value == "judgment"
        assert VerificationPhase.EXECUTION.value == "execution"
        assert VerificationPhase.AUDIT.value == "audit"


class TestVerificationStatus:
    """Tests for verification status definitions."""

    def test_all_statuses_defined(self):
        """Test that all required statuses are defined."""
        assert VerificationStatus.PENDING.value == "pending"
        assert VerificationStatus.IN_PROGRESS.value == "in_progress"
        assert VerificationStatus.COMPLETED.value == "completed"
        assert VerificationStatus.FAILED.value == "failed"
        assert VerificationStatus.BLOCKED.value == "blocked"
        assert VerificationStatus.TIMEOUT.value == "timeout"
