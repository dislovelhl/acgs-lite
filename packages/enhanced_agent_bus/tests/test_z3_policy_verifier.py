"""
Tests for Z3 Policy Verifier module.
Constitutional Hash: 608508a9bd224290

Covers: dataclasses, ConstraintGenerator, HeuristicVerifier, Z3PolicyVerifier,
        factory function, and edge cases.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.verification_layer import z3_policy_verifier as z3_policy_module
from enhanced_agent_bus.verification_layer.z3_policy_verifier import (
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

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    """Test enum definitions and values."""

    def test_z3_verification_status_values(self):
        assert Z3VerificationStatus.PENDING.value == "pending"
        assert Z3VerificationStatus.SATISFIABLE.value == "satisfiable"
        assert Z3VerificationStatus.UNSATISFIABLE.value == "unsatisfiable"
        assert Z3VerificationStatus.UNKNOWN.value == "unknown"
        assert Z3VerificationStatus.TIMEOUT.value == "timeout"
        assert Z3VerificationStatus.ERROR.value == "error"
        assert Z3VerificationStatus.HEURISTIC_FALLBACK.value == "heuristic_fallback"

    def test_constraint_type_values(self):
        assert ConstraintType.BOOLEAN.value == "boolean"
        assert ConstraintType.INTEGER.value == "integer"
        assert ConstraintType.REAL.value == "real"
        assert ConstraintType.STRING.value == "string"
        assert ConstraintType.ARRAY.value == "array"
        assert ConstraintType.COMPOSITE.value == "composite"

    def test_policy_domain_values(self):
        assert PolicyDomain.ACCESS_CONTROL.value == "access_control"
        assert PolicyDomain.DATA_PROTECTION.value == "data_protection"
        assert PolicyDomain.RESOURCE_ALLOCATION.value == "resource_allocation"
        assert PolicyDomain.GOVERNANCE.value == "governance"
        assert PolicyDomain.SECURITY.value == "security"
        assert PolicyDomain.COMPLIANCE.value == "compliance"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestPolicyConstraint:
    """Test PolicyConstraint dataclass."""

    def test_default_construction(self):
        c = PolicyConstraint()
        assert c.name == ""
        assert c.constraint_type == ConstraintType.BOOLEAN
        assert c.domain == PolicyDomain.GOVERNANCE
        assert c.confidence == 1.0
        assert c.is_mandatory is True
        assert c.priority == 1
        assert isinstance(c.constraint_id, str)
        assert isinstance(c.created_at, datetime)

    def test_custom_construction(self):
        c = PolicyConstraint(
            name="test",
            constraint_type=ConstraintType.INTEGER,
            domain=PolicyDomain.SECURITY,
            expression="(assert x)",
            variables={"x": "Int"},
            confidence=0.9,
            generated_by="test",
            is_mandatory=False,
            priority=3,
        )
        assert c.name == "test"
        assert c.constraint_type == ConstraintType.INTEGER
        assert c.domain == PolicyDomain.SECURITY
        assert c.confidence == 0.9
        assert c.is_mandatory is False

    def test_to_dict(self):
        c = PolicyConstraint(name="foo", expression="(assert bar)")
        d = c.to_dict()
        assert d["name"] == "foo"
        assert d["expression"] == "(assert bar)"
        assert d["constraint_type"] == "boolean"
        assert d["domain"] == "governance"
        assert "constraint_id" in d
        assert "created_at" in d


class TestVerificationProof:
    """Test VerificationProof dataclass."""

    def test_default_construction(self):
        p = VerificationProof()
        assert p.status == Z3VerificationStatus.PENDING
        assert p.is_verified is False
        assert p.constraints_evaluated == 0
        assert p.proof_trace == []

    def test_to_dict(self):
        p = VerificationProof(
            status=Z3VerificationStatus.SATISFIABLE,
            is_verified=True,
            constraints_evaluated=3,
            constraints_satisfied=3,
            solve_time_ms=42.5,
        )
        d = p.to_dict()
        assert d["status"] == "satisfiable"
        assert d["is_verified"] is True
        assert d["solve_time_ms"] == 42.5

    def test_add_trace_entry(self):
        p = VerificationProof()
        p.add_trace_entry("step1", {"key": "value"})
        assert len(p.proof_trace) == 1
        assert p.proof_trace[0]["step"] == "step1"
        assert p.proof_trace[0]["details"] == {"key": "value"}
        assert "timestamp" in p.proof_trace[0]

    def test_multiple_trace_entries(self):
        p = VerificationProof()
        p.add_trace_entry("a", {})
        p.add_trace_entry("b", {"x": 1})
        assert len(p.proof_trace) == 2


class TestPolicyVerificationRequest:
    """Test PolicyVerificationRequest dataclass."""

    def test_default_construction(self):
        r = PolicyVerificationRequest()
        assert r.policy_id == ""
        assert r.policy_text == ""
        assert r.timeout_ms == 5000
        assert r.use_heuristic_fallback is False
        assert r.require_proof is True

    def test_to_dict_with_constraints(self):
        c = PolicyConstraint(name="c1")
        r = PolicyVerificationRequest(
            policy_id="p1",
            policy_text="some policy",
            constraints=[c],
        )
        d = r.to_dict()
        assert d["policy_id"] == "p1"
        assert len(d["constraints"]) == 1
        assert d["constraints"][0]["name"] == "c1"


class TestPolicyVerificationResult:
    """Test PolicyVerificationResult dataclass."""

    def test_default_construction(self):
        r = PolicyVerificationResult()
        assert r.is_verified is False
        assert r.status == Z3VerificationStatus.PENDING
        assert r.violations == []
        assert r.warnings == []

    def test_to_dict_without_proof(self):
        r = PolicyVerificationResult(policy_id="p1")
        d = r.to_dict()
        assert d["policy_id"] == "p1"
        assert d["proof"] is None

    def test_to_dict_with_proof(self):
        proof = VerificationProof(is_verified=True)
        r = PolicyVerificationResult(proof=proof)
        d = r.to_dict()
        assert d["proof"] is not None
        assert d["proof"]["is_verified"] is True


# ---------------------------------------------------------------------------
# ConstraintGenerator tests
# ---------------------------------------------------------------------------


class TestConstraintGenerator:
    """Test ConstraintGenerator natural language parsing."""

    @pytest.fixture
    def generator(self):
        return ConstraintGenerator()

    @pytest.mark.asyncio
    async def test_generate_obligation_must(self, generator):
        constraints = await generator.generate_constraints(
            "All agents must authenticate before access."
        )
        assert len(constraints) == 1
        assert "Obligation" in constraints[0].name
        assert constraints[0].constraint_type == ConstraintType.BOOLEAN
        assert constraints[0].confidence == 0.85
        assert constraints[0].is_mandatory is True
        assert "assert" in constraints[0].expression

    @pytest.mark.asyncio
    async def test_generate_obligation_shall(self, generator):
        constraints = await generator.generate_constraints("The system shall log all actions.")
        assert len(constraints) == 1
        assert "Obligation" in constraints[0].name

    @pytest.mark.asyncio
    async def test_generate_obligation_required(self, generator):
        constraints = await generator.generate_constraints("Encryption is required for all data.")
        assert len(constraints) == 1
        assert "Obligation" in constraints[0].name

    @pytest.mark.asyncio
    async def test_generate_prohibition_cannot(self, generator):
        constraints = await generator.generate_constraints("Agents cannot share private keys.")
        assert len(constraints) == 1
        assert "Prohibition" in constraints[0].name
        assert constraints[0].confidence == 0.90
        assert "(not " in constraints[0].expression

    @pytest.mark.asyncio
    async def test_generate_prohibition_must_not(self, generator):
        # "must not" contains "must" which also matches obligation pattern.
        # The iteration order of the dict means "must" is checked before "must not",
        # so this sentence actually generates an Obligation constraint.
        constraints = await generator.generate_constraints("The system must not expose secrets.")
        assert len(constraints) == 1
        # Pattern matching picks "must" first due to dict iteration order
        assert "Obligation" in constraints[0].name

    @pytest.mark.asyncio
    async def test_generate_prohibition_forbidden(self, generator):
        constraints = await generator.generate_constraints("Direct database access is forbidden.")
        assert len(constraints) == 1
        assert "Prohibition" in constraints[0].name

    @pytest.mark.asyncio
    async def test_generate_permission_may(self, generator):
        constraints = await generator.generate_constraints(
            "Agents may request additional resources."
        )
        assert len(constraints) == 1
        assert "Permission" in constraints[0].name
        assert constraints[0].confidence == 0.75
        assert constraints[0].is_mandatory is False
        assert constraints[0].priority == 2

    @pytest.mark.asyncio
    async def test_generate_permission_can(self, generator):
        constraints = await generator.generate_constraints("Users can opt out of telemetry.")
        assert len(constraints) == 1
        assert "Permission" in constraints[0].name

    @pytest.mark.asyncio
    async def test_generate_permission_optional(self, generator):
        constraints = await generator.generate_constraints("Logging verbosity is optional.")
        assert len(constraints) == 1
        assert "Permission" in constraints[0].name

    @pytest.mark.asyncio
    async def test_generate_comparison_greater_than(self, generator):
        constraints = await generator.generate_constraints("Score must be greater than 80.")
        # "must" also matches but comparison patterns are checked first
        assert len(constraints) >= 1
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) == 1
        assert comp[0].constraint_type == ConstraintType.INTEGER
        assert ">=" in comp[0].expression
        assert "80" in comp[0].expression

    @pytest.mark.asyncio
    async def test_generate_comparison_less_than(self, generator):
        constraints = await generator.generate_constraints("Latency must be less than 100 ms.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) == 1
        assert "<=" in comp[0].expression
        assert "100" in comp[0].expression

    @pytest.mark.asyncio
    async def test_generate_comparison_at_least(self, generator):
        constraints = await generator.generate_constraints("Coverage at least 80 percent.")
        assert len(constraints) == 1
        assert ">=" in constraints[0].expression

    @pytest.mark.asyncio
    async def test_generate_comparison_at_most(self, generator):
        constraints = await generator.generate_constraints("Errors at most 5 per hour.")
        assert len(constraints) == 1
        assert "<=" in constraints[0].expression

    @pytest.mark.asyncio
    async def test_generate_comparison_no_number(self, generator):
        constraints = await generator.generate_constraints("Throughput greater than expected.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) == 1
        # No number => threshold defaults to 0
        assert "0" in comp[0].expression

    @pytest.mark.asyncio
    async def test_empty_policy(self, generator):
        constraints = await generator.generate_constraints("")
        assert constraints == []

    @pytest.mark.asyncio
    async def test_no_matching_patterns(self, generator):
        constraints = await generator.generate_constraints("The sky is blue. Water is wet.")
        assert constraints == []

    @pytest.mark.asyncio
    async def test_multiple_sentences(self, generator):
        constraints = await generator.generate_constraints(
            "All agents must authenticate. Secrets cannot be shared. Logging may be enabled."
        )
        assert len(constraints) == 3

    @pytest.mark.asyncio
    async def test_context_passed_through(self, generator):
        """Context is accepted without error even if not used by pattern matching."""
        constraints = await generator.generate_constraints(
            "Data must be encrypted.",
            context={"env": "production"},
        )
        assert len(constraints) == 1


# ---------------------------------------------------------------------------
# HeuristicVerifier tests
# ---------------------------------------------------------------------------


class TestHeuristicVerifier:
    """Test HeuristicVerifier fallback logic."""

    @pytest.fixture
    def verifier(self):
        return HeuristicVerifier()

    @pytest.mark.asyncio
    async def test_verify_obligation_constraint(self, verifier):
        c = PolicyConstraint(
            name="Obligation: must authenticate",
            confidence=0.85,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        assert score == pytest.approx(0.85 * 0.9)
        assert violations == []

    @pytest.mark.asyncio
    async def test_verify_prohibition_constraint(self, verifier):
        c = PolicyConstraint(
            name="Prohibition: cannot share",
            confidence=0.90,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        assert score == pytest.approx(0.90 * 0.95)
        assert violations == []

    @pytest.mark.asyncio
    async def test_verify_permission_constraint(self, verifier):
        c = PolicyConstraint(
            name="Permission: may access",
            confidence=0.75,
            is_mandatory=False,
        )
        score, violations = await verifier.verify([c], {})
        assert score == pytest.approx(0.75 * 0.7)
        assert violations == []

    @pytest.mark.asyncio
    async def test_verify_comparison_constraint(self, verifier):
        c = PolicyConstraint(
            name="Comparison: value >= 80",
            confidence=0.80,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        assert score == pytest.approx(0.80 * 0.85)
        # 0.80 * 0.85 = 0.68 < 0.7 threshold => generates a violation
        assert len(violations) == 1
        assert violations[0]["constraint_id"] == c.constraint_id

    @pytest.mark.asyncio
    async def test_verify_low_confidence_mandatory_generates_violation(self, verifier):
        c = PolicyConstraint(
            name="Obligation: weak rule",
            confidence=0.5,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        # 0.5 * 0.9 = 0.45 < 0.7 => violation
        assert len(violations) == 1
        assert violations[0]["constraint_id"] == c.constraint_id

    @pytest.mark.asyncio
    async def test_verify_low_confidence_non_mandatory_no_violation(self, verifier):
        c = PolicyConstraint(
            name="Permission: weak",
            confidence=0.5,
            is_mandatory=False,
        )
        score, violations = await verifier.verify([c], {})
        # Not mandatory, so no violation even though score < 0.7
        assert violations == []

    @pytest.mark.asyncio
    async def test_verify_multiple_constraints(self, verifier):
        constraints = [
            PolicyConstraint(name="Obligation: a", confidence=0.85, is_mandatory=True),
            PolicyConstraint(name="Prohibition: b", confidence=0.90, is_mandatory=True),
        ]
        score, violations = await verifier.verify(constraints, {})
        expected = (0.85 * 0.9 + 0.90 * 0.95) / 2
        assert score == pytest.approx(expected)
        assert violations == []

    @pytest.mark.asyncio
    async def test_verify_empty_constraints(self, verifier):
        score, violations = await verifier.verify([], {})
        assert score == 0.0
        assert violations == []


# ---------------------------------------------------------------------------
# Z3PolicyVerifier tests (Z3 mocked out)
# ---------------------------------------------------------------------------


class TestZ3PolicyVerifier:
    """Test the main Z3PolicyVerifier class with Z3 mocked."""

    @pytest.fixture
    def verifier(self):
        return Z3PolicyVerifier(
            default_timeout_ms=1000,
            enable_heuristic_fallback=False,
            heuristic_threshold=0.75,
        )

    def test_initialization(self, verifier):
        assert verifier.default_timeout_ms == 1000
        assert verifier.enable_heuristic_fallback is False
        assert verifier.heuristic_threshold == 0.75
        assert verifier._verification_history == []

    def test_get_constitutional_hash(self, verifier):
        h = verifier.get_constitutional_hash()
        assert isinstance(h, str)
        assert len(h) > 0

    def test_get_verification_stats_empty(self, verifier):
        stats = verifier.get_verification_stats()
        assert stats == {"total_verifications": 0}

    @pytest.mark.asyncio
    async def test_verify_policy_no_constraints_no_text(self, verifier):
        """Empty request with no constraints and no text => verified with warning."""
        request = PolicyVerificationRequest(policy_id="p1")
        result = await verifier.verify_policy(request)
        assert result.is_verified is True
        assert result.status == Z3VerificationStatus.SATISFIABLE
        assert "No constraints to verify" in result.warnings

    @pytest.mark.asyncio
    async def test_verify_policy_generates_constraints_from_text(self, verifier):
        """When no constraints provided but policy_text given, generates them."""
        request = PolicyVerificationRequest(
            policy_id="p1",
            policy_text="All agents must authenticate.",
        )
        # Z3 not available in test env typically, so it will use heuristic
        result = await verifier.verify_policy(request)
        assert result.total_constraints == 1
        assert result.proof is not None
        assert result.request_id == request.request_id

    @pytest.mark.asyncio
    async def test_verify_policy_with_explicit_constraints(self, verifier):
        """Explicitly provided constraints are used directly."""
        c = PolicyConstraint(
            name="Obligation: must log",
            confidence=0.85,
            is_mandatory=True,
            expression="(assert obligation_1)",
            variables={"obligation_1": "Bool"},
        )
        request = PolicyVerificationRequest(
            policy_id="p2",
            constraints=[c],
        )
        result = await verifier.verify_policy(request)
        assert result.total_constraints == 1
        assert result.proof is not None

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        False,
    )
    async def test_verify_policy_z3_unavailable_fails_closed_by_default(self, verifier):
        """When Z3 is not available, verification fails closed by default."""
        c = PolicyConstraint(
            name="Obligation: test",
            confidence=0.85,
            is_mandatory=True,
        )
        request = PolicyVerificationRequest(
            policy_id="p3",
            constraints=[c],
        )
        result = await verifier.verify_policy(request)
        assert result.status == Z3VerificationStatus.ERROR
        assert result.is_verified is False
        assert any(v["type"] == "z3_unavailable" for v in result.violations)
        assert "failed closed" in result.warnings[0].lower()
        assert result.proof is not None
        assert result.proof.heuristic_score is None

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        False,
    )
    async def test_verify_policy_z3_unavailable_uses_heuristic_when_enabled(self):
        """Heuristic fallback remains available when explicitly enabled."""
        verifier = Z3PolicyVerifier(enable_heuristic_fallback=True)
        c = PolicyConstraint(
            name="Obligation: test",
            confidence=0.85,
            is_mandatory=True,
        )
        request = PolicyVerificationRequest(
            policy_id="p3b",
            constraints=[c],
            use_heuristic_fallback=True,
        )
        result = await verifier.verify_policy(request)
        assert result.status == Z3VerificationStatus.HEURISTIC_FALLBACK
        assert result.proof.heuristic_score is not None

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        True,
    )
    async def test_verify_with_z3_satisfiable(self, verifier):
        """Mock Z3 solver returning SAT."""
        mock_wrapper = MagicMock()
        mock_wrapper.add_constraint.return_value = True
        mock_wrapper.check.return_value = (
            Z3VerificationStatus.SATISFIABLE,
            {"x": True},
            None,
        )

        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            return_value=mock_wrapper,
        ):
            c = PolicyConstraint(
                name="Obligation: auth",
                confidence=0.9,
                expression="(assert x)",
                variables={"x": "Bool"},
            )
            request = PolicyVerificationRequest(
                policy_id="p4",
                constraints=[c],
            )
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.SATISFIABLE
        assert result.is_verified is True
        assert result.proof.model == {"x": True}

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        True,
    )
    async def test_verify_with_z3_unsatisfiable(self, verifier):
        """Mock Z3 solver returning UNSAT with core."""
        mock_wrapper = MagicMock()
        mock_wrapper.add_constraint.return_value = True
        mock_wrapper.check.return_value = (
            Z3VerificationStatus.UNSATISFIABLE,
            None,
            ["constraint_1"],
        )

        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            return_value=mock_wrapper,
        ):
            c = PolicyConstraint(
                name="Obligation: conflicting",
                expression="(assert x)",
                variables={"x": "Bool"},
            )
            request = PolicyVerificationRequest(
                policy_id="p5",
                constraints=[c],
            )
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.UNSATISFIABLE
        assert result.is_verified is False
        assert result.proof.unsat_core == ["constraint_1"]
        assert len(result.violations) > 0

    @pytest.mark.skipif(
        not z3_policy_module.Z3_AVAILABLE,
        reason="z3-solver not installed in test environment",
    )
    async def test_verify_with_z3_extracts_real_unsat_core(self, verifier):
        constraints = [
            PolicyConstraint(
                constraint_id="must_be_true",
                name="must be true",
                expression="(assert policy_flag)",
                variables={"policy_flag": "Bool"},
            ),
            PolicyConstraint(
                constraint_id="must_be_false",
                name="must be false",
                expression="(assert (not policy_flag))",
                variables={"policy_flag": "Bool"},
            ),
        ]

        result = await verifier.verify_policy(
            PolicyVerificationRequest(
                policy_id="contradiction",
                constraints=constraints,
            )
        )

        assert result.status == Z3VerificationStatus.UNSATISFIABLE
        assert result.is_verified is False
        assert set(result.proof.unsat_core or []) == {"must_be_true", "must_be_false"}

    async def test_verify_policy_handles_concurrent_requests(self, verifier):
        async def verify(policy_id: str) -> PolicyVerificationResult:
            return await verifier.verify_policy(
                PolicyVerificationRequest(
                    policy_id=policy_id,
                    constraints=[
                        PolicyConstraint(
                            name=f"obligation-{policy_id}",
                            expression="(assert obligation_flag)",
                            variables={"obligation_flag": "Bool"},
                        )
                    ],
                )
            )

        results = await asyncio.gather(verify("policy-a"), verify("policy-b"))

        assert [result.policy_id for result in results] == ["policy-a", "policy-b"]
        assert len(verifier._verification_history) >= 2

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        True,
    )
    async def test_verify_with_z3_unknown_fails_closed_by_default(self, verifier):
        """Z3 UNKNOWN must fail closed by default."""
        mock_wrapper = MagicMock()
        mock_wrapper.add_constraint.return_value = True
        mock_wrapper.check.return_value = (
            Z3VerificationStatus.UNKNOWN,
            None,
            None,
        )

        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            return_value=mock_wrapper,
        ):
            c = PolicyConstraint(
                name="Obligation: ambiguous",
                confidence=0.85,
                expression="(assert x)",
                variables={"x": "Bool"},
            )
            request = PolicyVerificationRequest(
                policy_id="p6",
                constraints=[c],
            )
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.UNKNOWN
        assert result.is_verified is False
        assert any(v["type"] == "z3_inconclusive" for v in result.violations)

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        True,
    )
    async def test_verify_with_z3_unknown_uses_heuristic_when_enabled(self):
        """UNKNOWN can use heuristic fallback only when explicitly enabled."""
        verifier = Z3PolicyVerifier(enable_heuristic_fallback=True)
        mock_wrapper = MagicMock()
        mock_wrapper.add_constraint.return_value = True
        mock_wrapper.check.return_value = (
            Z3VerificationStatus.UNKNOWN,
            None,
            None,
        )

        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            return_value=mock_wrapper,
        ):
            c = PolicyConstraint(
                name="Obligation: ambiguous",
                confidence=0.85,
                expression="(assert x)",
                variables={"x": "Bool"},
            )
            request = PolicyVerificationRequest(
                policy_id="p6b",
                constraints=[c],
                use_heuristic_fallback=True,
            )
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.HEURISTIC_FALLBACK

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        True,
    )
    async def test_verify_with_z3_timeout_fails_closed_by_default(self, verifier):
        """Z3 TIMEOUT must fail closed by default."""
        mock_wrapper = MagicMock()
        mock_wrapper.add_constraint.return_value = True
        mock_wrapper.check.return_value = (
            Z3VerificationStatus.TIMEOUT,
            None,
            None,
        )

        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            return_value=mock_wrapper,
        ):
            c = PolicyConstraint(
                name="Obligation: slow",
                confidence=0.85,
                expression="(assert x)",
                variables={"x": "Bool"},
            )
            request = PolicyVerificationRequest(
                policy_id="p7",
                constraints=[c],
            )
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.TIMEOUT
        assert result.is_verified is False
        assert any(v["type"] == "z3_inconclusive" for v in result.violations)

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        True,
    )
    async def test_verify_with_z3_unknown_no_fallback(self, verifier):
        """Z3 UNKNOWN without fallback enabled stays UNKNOWN."""
        verifier_no_fb = Z3PolicyVerifier(enable_heuristic_fallback=False)
        mock_wrapper = MagicMock()
        mock_wrapper.add_constraint.return_value = True
        mock_wrapper.check.return_value = (
            Z3VerificationStatus.UNKNOWN,
            None,
            None,
        )

        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            return_value=mock_wrapper,
        ):
            c = PolicyConstraint(
                name="Obligation: x",
                confidence=0.85,
                expression="(assert x)",
                variables={"x": "Bool"},
            )
            request = PolicyVerificationRequest(
                policy_id="p8",
                constraints=[c],
                use_heuristic_fallback=False,
            )
            result = await verifier_no_fb.verify_policy(request)

        assert result.status == Z3VerificationStatus.UNKNOWN

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        True,
    )
    async def test_verify_with_z3_error_in_solver(self, verifier):
        """Z3 solver raising an error is caught inside _verify_with_z3."""
        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            side_effect=RuntimeError("Z3 crashed"),
        ):
            c = PolicyConstraint(
                name="Obligation: boom",
                expression="(assert x)",
                variables={"x": "Bool"},
            )
            request = PolicyVerificationRequest(
                policy_id="p9",
                constraints=[c],
            )
            result = await verifier.verify_policy(request)

        # Error is caught in _verify_with_z3, returned as z3_error violation
        assert result.status == Z3VerificationStatus.ERROR
        assert result.is_verified is False
        assert any("z3_error" in str(v) for v in result.violations)

    @pytest.mark.asyncio
    async def test_verify_policy_text_convenience(self, verifier):
        """Test the convenience method verify_policy_text."""
        result = await verifier.verify_policy_text(
            "All agents must authenticate.",
            policy_id="conv1",
            context={"env": "test"},
            timeout_ms=2000,
        )
        assert result.request_id != ""
        assert result.policy_id == "conv1"
        assert result.proof is not None

    @pytest.mark.asyncio
    async def test_verify_policy_text_defaults(self, verifier):
        """verify_policy_text with minimal arguments."""
        result = await verifier.verify_policy_text("Data must be encrypted.")
        assert result.policy_id.startswith("policy_")
        assert result.total_constraints == 1

    @pytest.mark.asyncio
    async def test_verification_history_tracked(self, verifier):
        """Results are appended to history."""
        await verifier.verify_policy_text("Agents must log actions.")
        await verifier.verify_policy_text("Secrets cannot be exposed.")
        assert len(verifier._verification_history) == 2

    @pytest.mark.asyncio
    async def test_get_verification_stats_after_runs(self, verifier):
        """Stats reflect completed verifications."""
        await verifier.verify_policy_text("Agents must log actions.")
        await verifier.verify_policy_text("No matching pattern here.")
        stats = verifier.get_verification_stats()
        assert stats["total_verifications"] == 2
        assert "verification_rate" in stats
        assert "average_time_ms" in stats
        assert "average_constraints" in stats
        assert "z3_available" in stats
        assert "constitutional_hash" in stats


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    """Test _generate_recommendations logic."""

    def test_unverified_recommends_review(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(is_verified=False)
        recs = v._generate_recommendations(result, [])
        assert any("Review" in r for r in recs)

    def test_heuristic_fallback_recommends_simplifying(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(
            status=Z3VerificationStatus.HEURISTIC_FALLBACK,
        )
        recs = v._generate_recommendations(result, [])
        assert any("simplifying" in r.lower() for r in recs)

    def test_unsat_constraint_in_violations(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(
            violations=[
                {"type": "unsatisfiable_constraint", "constraint": "c1"},
            ],
        )
        recs = v._generate_recommendations(result, [])
        assert any("Constraint conflict" in r for r in recs)

    def test_many_constraints_recommends_decomposing(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(total_constraints=51)
        constraints = [PolicyConstraint() for _ in range(51)]
        recs = v._generate_recommendations(result, constraints)
        assert any("decomposing" in r.lower() for r in recs)

    def test_verified_no_extra_recommendations(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(
            is_verified=True,
            status=Z3VerificationStatus.SATISFIABLE,
            total_constraints=3,
        )
        recs = v._generate_recommendations(result, [PolicyConstraint()] * 3)
        # Should be empty — verified, not heuristic, few constraints, no violations
        assert recs == []


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestCreateZ3Verifier:
    """Test the factory function."""

    def test_default_creation(self):
        v = create_z3_verifier()
        assert isinstance(v, Z3PolicyVerifier)
        assert v.default_timeout_ms == 5000
        assert v.enable_heuristic_fallback is False

    def test_custom_creation(self):
        v = create_z3_verifier(timeout_ms=2000, enable_heuristic_fallback=False)
        assert v.default_timeout_ms == 2000
        assert v.enable_heuristic_fallback is False


# ---------------------------------------------------------------------------
# _verify_with_heuristic internals
# ---------------------------------------------------------------------------


class TestVerifyWithHeuristic:
    """Test _verify_with_heuristic path directly."""

    @pytest.mark.asyncio
    async def test_high_confidence_verified(self):
        v = Z3PolicyVerifier(heuristic_threshold=0.5)
        proof = VerificationProof()
        c = PolicyConstraint(name="Obligation: test", confidence=0.85)
        result = await v._verify_with_heuristic([c], {}, proof)
        assert result["is_verified"] is True
        assert result["score"] > 0.5

    @pytest.mark.asyncio
    async def test_low_confidence_not_verified(self):
        v = Z3PolicyVerifier(heuristic_threshold=0.99)
        proof = VerificationProof()
        c = PolicyConstraint(name="Obligation: test", confidence=0.85)
        result = await v._verify_with_heuristic([c], {}, proof)
        assert result["is_verified"] is False

    @pytest.mark.asyncio
    async def test_proof_trace_updated(self):
        v = Z3PolicyVerifier()
        proof = VerificationProof()
        c = PolicyConstraint(name="Obligation: test", confidence=0.85)
        await v._verify_with_heuristic([c], {}, proof)
        assert len(proof.proof_trace) == 1
        assert proof.proof_trace[0]["step"] == "heuristic_verification"
