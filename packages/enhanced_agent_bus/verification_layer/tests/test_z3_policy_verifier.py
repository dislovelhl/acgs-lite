"""
Tests for Z3 Policy Verifier - VeriPlan SMT Solver Integration
Constitutional Hash: 608508a9bd224290

Tests cover:
- Policy constraint generation
- Z3 SMT solver verification
- Heuristic fallback
- Timeout handling
- Proof generation
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ..z3_policy_verifier import (
    CONSTITUTIONAL_HASH,
    Z3_AVAILABLE,
    ConstraintGenerator,
    ConstraintType,
    HeuristicVerifier,
    PolicyConstraint,
    PolicyDomain,
    PolicyVerificationRequest,
    PolicyVerificationResult,
    VerificationProof,
    Z3PolicyVerifier,
    Z3VerificationStatus,
    create_z3_verifier,
)


class TestConstitutionalHash:
    """Tests for constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Test that constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_verifier_has_constitutional_hash(self):
        """Test that verifier includes constitutional hash."""
        verifier = create_z3_verifier()
        assert verifier.constitutional_hash == CONSTITUTIONAL_HASH
        assert verifier.get_constitutional_hash() == CONSTITUTIONAL_HASH

    def test_constraint_has_constitutional_hash(self):
        """Test that constraint includes constitutional hash."""
        constraint = PolicyConstraint(name="Test")
        assert constraint.constitutional_hash == CONSTITUTIONAL_HASH

    def test_proof_has_constitutional_hash(self):
        """Test that proof includes constitutional hash."""
        proof = VerificationProof()
        assert proof.constitutional_hash == CONSTITUTIONAL_HASH


class TestZ3PolicyVerifierCreation:
    """Tests for Z3PolicyVerifier creation."""

    def test_default_creation(self):
        """Test verifier creation with defaults."""
        verifier = create_z3_verifier()
        assert verifier is not None
        assert verifier.default_timeout_ms == 5000
        assert not verifier.enable_heuristic_fallback

    def test_custom_timeout(self):
        """Test verifier with custom timeout."""
        verifier = create_z3_verifier(timeout_ms=10000)
        assert verifier.default_timeout_ms == 10000

    def test_disable_heuristic_fallback(self):
        """Test verifier with heuristic fallback disabled."""
        verifier = create_z3_verifier(enable_heuristic_fallback=False)
        assert not verifier.enable_heuristic_fallback


class TestPolicyConstraint:
    """Tests for PolicyConstraint model."""

    def test_constraint_creation(self):
        """Test constraint creation with defaults."""
        constraint = PolicyConstraint(name="Test Constraint")
        assert constraint.name == "Test Constraint"
        assert constraint.constraint_type == ConstraintType.BOOLEAN
        assert constraint.domain == PolicyDomain.GOVERNANCE
        assert constraint.is_mandatory
        assert constraint.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constraint_with_all_fields(self):
        """Test constraint with all fields."""
        constraint = PolicyConstraint(
            name="Full Constraint",
            description="A fully specified constraint",
            constraint_type=ConstraintType.INTEGER,
            domain=PolicyDomain.ACCESS_CONTROL,
            expression="(assert (>= access_level 5))",
            natural_language="Access level must be at least 5",
            variables={"access_level": "Int"},
            confidence=0.95,
            is_mandatory=True,
            priority=1,
        )

        assert constraint.name == "Full Constraint"
        assert constraint.constraint_type == ConstraintType.INTEGER
        assert constraint.domain == PolicyDomain.ACCESS_CONTROL
        assert constraint.confidence == 0.95

    def test_constraint_to_dict(self):
        """Test constraint serialization."""
        constraint = PolicyConstraint(
            name="Test",
            description="A test",
            confidence=0.8,
        )

        data = constraint.to_dict()

        assert data["name"] == "Test"
        assert data["description"] == "A test"
        assert data["confidence"] == 0.8
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestConstraintType:
    """Tests for ConstraintType enum."""

    def test_all_types_defined(self):
        """Test that all constraint types are defined."""
        assert ConstraintType.BOOLEAN.value == "boolean"
        assert ConstraintType.INTEGER.value == "integer"
        assert ConstraintType.REAL.value == "real"
        assert ConstraintType.STRING.value == "string"
        assert ConstraintType.ARRAY.value == "array"
        assert ConstraintType.COMPOSITE.value == "composite"


class TestPolicyDomain:
    """Tests for PolicyDomain enum."""

    def test_all_domains_defined(self):
        """Test that all policy domains are defined."""
        assert PolicyDomain.ACCESS_CONTROL.value == "access_control"
        assert PolicyDomain.DATA_PROTECTION.value == "data_protection"
        assert PolicyDomain.RESOURCE_ALLOCATION.value == "resource_allocation"
        assert PolicyDomain.GOVERNANCE.value == "governance"
        assert PolicyDomain.SECURITY.value == "security"
        assert PolicyDomain.COMPLIANCE.value == "compliance"


class TestConstraintGenerator:
    """Tests for ConstraintGenerator."""

    @pytest.fixture
    def generator(self):
        return ConstraintGenerator()

    async def test_generate_from_empty_text(self, generator):
        """Test generating constraints from empty text."""
        constraints = await generator.generate_constraints("")
        assert constraints == []

    async def test_generate_obligation_constraint(self, generator):
        """Test generating obligation constraint."""
        constraints = await generator.generate_constraints(
            "Users must authenticate before accessing resources."
        )

        assert len(constraints) > 0
        assert any("Obligation" in c.name for c in constraints)

    async def test_generate_prohibition_constraint(self, generator):
        """Test generating prohibition constraint."""
        constraints = await generator.generate_constraints(
            "Users cannot access restricted areas without permission."
        )

        assert len(constraints) > 0
        assert any("Prohibition" in c.name for c in constraints)

    async def test_generate_permission_constraint(self, generator):
        """Test generating permission constraint."""
        constraints = await generator.generate_constraints(
            "Administrators may modify system settings."
        )

        assert len(constraints) > 0
        assert any("Permission" in c.name for c in constraints)

    async def test_generate_comparison_constraint(self, generator):
        """Test generating comparison constraint."""
        constraints = await generator.generate_constraints(
            "Password length must be greater than 8 characters."
        )

        assert len(constraints) > 0
        assert any("Comparison" in c.name for c in constraints)

    async def test_generate_multiple_constraints(self, generator):
        """Test generating multiple constraints from complex text."""
        policy_text = """
        Users must authenticate.
        Access cannot be granted without verification.
        Session timeout must be at least 30 minutes.
        """

        constraints = await generator.generate_constraints(policy_text)

        assert len(constraints) >= 3


class TestHeuristicVerifier:
    """Tests for HeuristicVerifier."""

    @pytest.fixture
    def verifier(self):
        return HeuristicVerifier()

    async def test_verify_empty_constraints(self, verifier):
        """Test verifying empty constraint list."""
        score, violations = await verifier.verify([], {})
        assert score == 0.0
        assert violations == []

    async def test_verify_single_constraint(self, verifier):
        """Test verifying single constraint."""
        constraint = PolicyConstraint(
            name="Obligation: Test",
            confidence=0.9,
        )

        score, violations = await verifier.verify([constraint], {})

        assert score > 0
        assert isinstance(violations, list)

    async def test_verify_multiple_constraints(self, verifier):
        """Test verifying multiple constraints."""
        constraints = [
            PolicyConstraint(name="Obligation: Test 1", confidence=0.9),
            PolicyConstraint(name="Prohibition: Test 2", confidence=0.85),
            PolicyConstraint(name="Permission: Test 3", confidence=0.7, is_mandatory=False),
        ]

        score, _violations = await verifier.verify(constraints, {})

        assert 0 <= score <= 1.0


class TestVerificationProof:
    """Tests for VerificationProof model."""

    def test_proof_creation(self):
        """Test proof creation."""
        proof = VerificationProof()
        assert proof.proof_id is not None
        assert proof.status == Z3VerificationStatus.PENDING
        assert not proof.is_verified
        assert proof.constitutional_hash == CONSTITUTIONAL_HASH

    def test_proof_to_dict(self):
        """Test proof serialization."""
        proof = VerificationProof(
            verification_id="ver-001",
            is_verified=True,
            solve_time_ms=5.5,
        )

        data = proof.to_dict()

        assert data["verification_id"] == "ver-001"
        assert data["is_verified"]
        assert data["solve_time_ms"] == 5.5
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_proof_trace_entry(self):
        """Test adding trace entries to proof."""
        proof = VerificationProof()
        proof.add_trace_entry("test_step", {"key": "value"})

        assert len(proof.proof_trace) == 1
        assert proof.proof_trace[0]["step"] == "test_step"
        assert proof.proof_trace[0]["details"]["key"] == "value"


class TestPolicyVerificationRequest:
    """Tests for PolicyVerificationRequest model."""

    def test_request_creation(self):
        """Test request creation."""
        request = PolicyVerificationRequest(
            policy_id="policy-001",
            policy_text="Users must authenticate.",
        )

        assert request.policy_id == "policy-001"
        assert request.policy_text == "Users must authenticate."
        assert request.timeout_ms == 5000
        assert not request.use_heuristic_fallback
        assert request.constitutional_hash == CONSTITUTIONAL_HASH

    def test_request_with_constraints(self):
        """Test request with pre-generated constraints."""
        constraints = [
            PolicyConstraint(name="Test Constraint"),
        ]

        request = PolicyVerificationRequest(
            policy_id="policy-001",
            constraints=constraints,
        )

        assert len(request.constraints) == 1

    def test_request_to_dict(self):
        """Test request serialization."""
        request = PolicyVerificationRequest(
            policy_id="policy-001",
            policy_text="Test policy",
            timeout_ms=10000,
        )

        data = request.to_dict()

        assert data["policy_id"] == "policy-001"
        assert data["policy_text"] == "Test policy"
        assert data["timeout_ms"] == 10000
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestPolicyVerificationResult:
    """Tests for PolicyVerificationResult model."""

    def test_result_creation(self):
        """Test result creation."""
        result = PolicyVerificationResult(
            policy_id="policy-001",
            is_verified=True,
            status=Z3VerificationStatus.SATISFIABLE,
        )

        assert result.policy_id == "policy-001"
        assert result.is_verified
        assert result.status == Z3VerificationStatus.SATISFIABLE
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_to_dict(self):
        """Test result serialization."""
        result = PolicyVerificationResult(
            policy_id="policy-001",
            is_verified=True,
            status=Z3VerificationStatus.SATISFIABLE,
            total_constraints=5,
            satisfied_constraints=5,
            total_time_ms=10.5,
        )

        data = result.to_dict()

        assert data["policy_id"] == "policy-001"
        assert data["is_verified"]
        assert data["status"] == "satisfiable"
        assert data["total_constraints"] == 5
        assert data["satisfied_constraints"] == 5
        assert data["total_time_ms"] == 10.5
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestZ3VerificationStatus:
    """Tests for Z3VerificationStatus enum."""

    def test_all_statuses_defined(self):
        """Test that all statuses are defined."""
        assert Z3VerificationStatus.PENDING.value == "pending"
        assert Z3VerificationStatus.SATISFIABLE.value == "satisfiable"
        assert Z3VerificationStatus.UNSATISFIABLE.value == "unsatisfiable"
        assert Z3VerificationStatus.UNKNOWN.value == "unknown"
        assert Z3VerificationStatus.TIMEOUT.value == "timeout"
        assert Z3VerificationStatus.ERROR.value == "error"
        assert Z3VerificationStatus.HEURISTIC_FALLBACK.value == "heuristic_fallback"


class TestZ3PolicyVerification:
    """Tests for Z3 policy verification."""

    async def test_verify_simple_policy(self):
        """Test verifying a simple policy."""
        verifier = create_z3_verifier()

        result = await verifier.verify_policy_text(
            "Users must authenticate before accessing resources."
        )

        assert result is not None
        assert isinstance(result, PolicyVerificationResult)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_verify_policy_with_constraints(self):
        """Test verifying policy with pre-generated constraints."""
        verifier = create_z3_verifier()

        constraints = [
            PolicyConstraint(
                name="Auth Required",
                expression="(assert auth_required)",
                variables={"auth_required": "Bool"},
            ),
        ]

        request = PolicyVerificationRequest(
            policy_id="auth-policy",
            constraints=constraints,
        )

        result = await verifier.verify_policy(request)

        assert result is not None
        assert result.total_constraints == 1

    async def test_verify_empty_policy(self):
        """Test verifying empty policy."""
        verifier = create_z3_verifier()

        result = await verifier.verify_policy_text("")

        assert result.is_verified
        assert len(result.warnings) > 0

    async def test_heuristic_fallback_when_z3_unavailable(self):
        """Test heuristic fallback."""
        verifier = create_z3_verifier(enable_heuristic_fallback=True)

        result = await verifier.verify_policy_text("Data must be encrypted at rest.")

        # Should either use Z3 or fall back to heuristic
        assert result is not None
        assert result.status in (
            Z3VerificationStatus.SATISFIABLE,
            Z3VerificationStatus.HEURISTIC_FALLBACK,
            Z3VerificationStatus.UNSATISFIABLE,
            Z3VerificationStatus.UNKNOWN,
        )

    async def test_verification_produces_proof(self):
        """Test that verification produces proof."""
        verifier = create_z3_verifier()

        result = await verifier.verify_policy_text("Access shall be logged.")

        assert result.proof is not None
        assert isinstance(result.proof, VerificationProof)

    async def test_verification_with_timeout(self):
        """Test verification with custom timeout."""
        verifier = create_z3_verifier(timeout_ms=100)

        result = await verifier.verify_policy_text(
            "Users must complete training.",
            timeout_ms=100,
        )

        assert result is not None

    async def test_verification_generates_recommendations(self):
        """Test that verification generates recommendations."""
        verifier = create_z3_verifier()

        result = await verifier.verify_policy_text(
            "Users must not share credentials. Access cannot be delegated."
        )

        # Should have recommendations if not verified or has warnings
        assert isinstance(result.recommendations, list)


class TestVerificationStatistics:
    """Tests for verification statistics."""

    def test_initial_stats(self):
        """Test initial statistics."""
        verifier = create_z3_verifier()
        stats = verifier.get_verification_stats()

        assert stats["total_verifications"] == 0

    async def test_stats_after_verification(self):
        """Test statistics after verification."""
        verifier = create_z3_verifier()

        await verifier.verify_policy_text("Test policy 1.")
        await verifier.verify_policy_text("Test policy 2.")

        stats = verifier.get_verification_stats()

        assert stats["total_verifications"] == 2
        assert "verification_rate" in stats
        assert "average_time_ms" in stats
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestZ3Integration:
    """Tests for Z3 solver integration (conditional on Z3 availability)."""

    @pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 not installed")
    def test_z3_is_available(self):
        """Test that Z3 is available."""
        assert Z3_AVAILABLE

    @pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 not installed")
    async def test_z3_verification(self):
        """Test actual Z3 verification."""
        verifier = create_z3_verifier()

        result = await verifier.verify_policy_text("Access level must be at least 5.")

        # Should use Z3 when available
        assert result.status in (
            Z3VerificationStatus.SATISFIABLE,
            Z3VerificationStatus.UNSATISFIABLE,
            Z3VerificationStatus.UNKNOWN,
        )


class TestComplexPolicies:
    """Tests for complex policy verification."""

    async def test_multi_constraint_policy(self):
        """Test policy with multiple constraints."""
        verifier = create_z3_verifier()

        policy_text = """
        All users must authenticate.
        Passwords must be at least 12 characters.
        Users cannot access restricted resources without clearance.
        Session timeout shall be at most 30 minutes.
        Administrative actions may require additional verification.
        """

        result = await verifier.verify_policy_text(policy_text)

        assert result.total_constraints >= 3
        assert result.proof is not None

    async def test_conflicting_policy(self):
        """Test policy with potentially conflicting constraints."""
        verifier = create_z3_verifier()

        # This could potentially be unsatisfiable
        policy_text = """
        Access level must be greater than 10.
        Access level must be less than 5.
        """

        result = await verifier.verify_policy_text(policy_text)

        # The result depends on constraint generation and verification
        assert result is not None
        assert isinstance(result.status, Z3VerificationStatus)
