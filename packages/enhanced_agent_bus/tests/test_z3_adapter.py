"""Tests for Z3 Adapter module.

Covers Z3Constraint, Z3VerificationResult, ConstitutionalPolicy,
Z3SolverAdapter, LLMAssistedZ3Adapter, ConstitutionalZ3Verifier,
and convenience functions.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Z3 may not be available, skip entire module if not
z3 = pytest.importorskip("z3", reason="z3-solver not installed")

from enhanced_agent_bus.verification.z3_adapter import (
    CONSTITUTIONAL_HASH,
    ConstitutionalPolicy,
    ConstitutionalZ3Verifier,
    LLMAssistedZ3Adapter,
    Z3Constraint,
    Z3SolverAdapter,
    Z3VerificationResult,
    verify_policy_formally,
)

# ---------------------------------------------------------------------------
# Z3Constraint dataclass
# ---------------------------------------------------------------------------


class TestZ3Constraint:
    def test_defaults(self):
        c = Z3Constraint(
            name="c1",
            expression="(assert x)",
            natural_language="x must be true",
            confidence=0.9,
        )
        assert c.generated_by == "llm"
        assert c.timestamp is not None

    def test_custom_timestamp(self):
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        c = Z3Constraint(
            name="c1",
            expression="expr",
            natural_language="text",
            confidence=0.8,
            timestamp=ts,
        )
        assert c.timestamp == ts


# ---------------------------------------------------------------------------
# Z3VerificationResult dataclass
# ---------------------------------------------------------------------------


class TestZ3VerificationResult:
    def test_defaults(self):
        r = Z3VerificationResult(is_sat=True)
        assert r.constraints_used == []
        assert r.solver_stats == {}
        assert r.alternative_paths == []
        assert r.solve_time_ms == 0.0

    def test_custom(self):
        r = Z3VerificationResult(
            is_sat=False,
            unsat_core=["c1", "c2"],
            solve_time_ms=5.0,
        )
        assert r.unsat_core == ["c1", "c2"]

    def test_verification_result_with_model(self):
        result = Z3VerificationResult(
            is_sat=True, model={"x": True, "y": 42}, solve_time_ms=150.5, solver_stats={"decls": 2}
        )
        assert result.is_sat
        assert result.model == {"x": True, "y": 42}
        assert result.solve_time_ms == 150.5
        assert result.solver_stats == {"decls": 2}


# ---------------------------------------------------------------------------
# ConstitutionalPolicy dataclass
# ---------------------------------------------------------------------------


class TestConstitutionalPolicy:
    def test_defaults(self):
        p = ConstitutionalPolicy(
            id="p1",
            natural_language="Test policy",
            z3_constraints=[],
        )
        assert p.is_verified is False
        assert p.created_at is not None
        assert p.verified_at is None
        assert p.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_constraints(self):
        constraints = [
            Z3Constraint(
                name="constraint1",
                expression="(declare-const x Bool)",
                natural_language="Test constraint",
                confidence=0.8,
            )
        ]
        policy = ConstitutionalPolicy(
            id="test-policy",
            natural_language="Test policy text",
            z3_constraints=constraints,
            is_verified=True,
        )
        assert len(policy.z3_constraints) == 1
        assert policy.is_verified


# ---------------------------------------------------------------------------
# Z3SolverAdapter
# ---------------------------------------------------------------------------


class TestZ3SolverAdapter:
    def test_init(self):
        adapter = Z3SolverAdapter(timeout_ms=3000)
        assert adapter.timeout_ms == 3000

    def test_reset_solver(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="x is true", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        assert "c1" in adapter.named_constraints
        adapter.reset_solver()
        assert len(adapter.named_constraints) == 0

    def test_add_constraint(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="x", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        assert "c1" in adapter.named_constraints
        assert len(adapter.constraint_history) == 1

    def test_get_constraint_names(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="x", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        assert adapter.get_constraint_names() == ["c1"]

    def test_check_sat_satisfiable(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="x", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        result = adapter.check_sat()
        assert result.is_sat is True
        assert result.model is not None
        assert result.solve_time_ms >= 0

    def test_check_sat_unsatisfiable(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta1 = Z3Constraint(name="c1", expression="x", natural_language="x", confidence=1.0)
        meta2 = Z3Constraint(
            name="c2", expression="not x", natural_language="not x", confidence=1.0
        )
        adapter.add_constraint("c1", x, meta1)
        adapter.add_constraint("c2", z3.Not(x), meta2)
        result = adapter.check_sat()
        assert result.is_sat is False

    def test_check_sat_find_multiple(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        y = z3.Bool("y")
        meta = Z3Constraint(name="c1", expression="or", natural_language="x or y", confidence=1.0)
        adapter.add_constraint("c1", z3.Or(x, y), meta)
        result = adapter.check_sat(find_multiple=True, max_paths=3)
        assert result.is_sat is True
        assert len(result.alternative_paths) >= 1

    @pytest.mark.asyncio
    async def test_async_check_sat(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="x", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        result = await adapter.async_check_sat()
        assert result.is_sat is True

    def test_model_to_dict_bool(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        adapter.add_constraint(
            "c1",
            x,
            Z3Constraint(name="c1", expression="x", natural_language="x", confidence=1.0),
        )
        result = adapter.check_sat()
        assert "x" in result.model

    def test_model_to_dict_int(self):
        adapter = Z3SolverAdapter()
        x = z3.Int("x")
        adapter.add_constraint(
            "c1",
            x == 42,
            Z3Constraint(name="c1", expression="x==42", natural_language="x is 42", confidence=1.0),
        )
        result = adapter.check_sat()
        assert result.model["x"] == 42

    def test_z3_unavailable(self):
        """Test behavior when Z3 is not available."""
        z3_globals = Z3SolverAdapter.__init__.__globals__
        original_available = z3_globals["Z3_AVAILABLE"]
        z3_globals["Z3_AVAILABLE"] = False
        try:
            with pytest.raises(ImportError, match="Z3 solver not available"):
                Z3SolverAdapter()
        finally:
            z3_globals["Z3_AVAILABLE"] = original_available


# ---------------------------------------------------------------------------
# LLMAssistedZ3Adapter
# ---------------------------------------------------------------------------


class TestLLMAssistedZ3Adapter:
    def test_init(self):
        adapter = LLMAssistedZ3Adapter(max_refinements=5)
        assert adapter.max_refinements == 5

    def test_extract_policy_elements_obligation(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements("Users must be authenticated.")
        assert len(elements) == 1
        assert elements[0]["type"] == "obligation"

    def test_extract_policy_elements_permission(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements("Users may access public data.")
        assert len(elements) == 1
        assert elements[0]["type"] == "permission"

    def test_extract_policy_elements_prohibition(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements(
            "Users are forbidden from accessing admin data."
        )
        assert len(elements) == 1
        assert elements[0]["type"] == "prohibition"

    def test_extract_policy_elements_empty(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements("Nothing important here.")
        assert len(elements) == 0

    def test_extract_policy_elements_multiple(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements(
            "Users must log in. Users may view dashboards. Users cannot delete others."
        )
        assert len(elements) == 3

    @pytest.mark.asyncio
    async def test_generate_single_constraint_obligation(self):
        adapter = LLMAssistedZ3Adapter()
        element = {"type": "obligation", "text": "Users must be authenticated", "priority": "high"}
        result = await adapter._generate_single_constraint(element)
        assert result is not None
        assert result.generated_by == "pattern_matching"
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_generate_single_constraint_prohibition(self):
        adapter = LLMAssistedZ3Adapter()
        element = {"type": "prohibition", "text": "Users cannot access admin", "priority": "high"}
        result = await adapter._generate_single_constraint(element)
        assert result is not None
        assert "not" in result.expression

    @pytest.mark.asyncio
    async def test_generate_single_constraint_permission_returns_none(self):
        adapter = LLMAssistedZ3Adapter()
        element = {"type": "permission", "text": "Users may view data", "priority": "medium"}
        result = await adapter._generate_single_constraint(element)
        assert result is None

    @pytest.mark.asyncio
    async def test_natural_language_to_constraints(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = await adapter.natural_language_to_constraints(
            "All users must be authenticated."
        )
        assert len(constraints) >= 1

    @pytest.mark.asyncio
    async def test_natural_language_to_constraints_empty(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = await adapter.natural_language_to_constraints("Nothing interesting here")
        assert len(constraints) == 0

    @pytest.mark.asyncio
    async def test_verify_policy_constraints_sat(self):
        adapter = LLMAssistedZ3Adapter()
        constraint = Z3Constraint(
            name="c1",
            expression="(declare-const x Bool)\n(assert x)",
            natural_language="x must be true",
            confidence=0.9,
        )
        result = await adapter.verify_policy_constraints([constraint])
        assert result.is_sat is True

    @pytest.mark.asyncio
    async def test_verify_policy_constraints_unsat(self):
        adapter = LLMAssistedZ3Adapter()
        c1 = Z3Constraint(
            name="c1",
            expression="(declare-const x Bool)\n(assert x)",
            natural_language="x must be true",
            confidence=0.9,
        )
        c2 = Z3Constraint(
            name="c2",
            expression="(declare-const x Bool)\n(assert (not x))",
            natural_language="x must be false",
            confidence=0.9,
        )
        result = await adapter.verify_policy_constraints([c1, c2])
        assert result.is_sat is False

    @pytest.mark.asyncio
    async def test_verify_policy_constraints_invalid_expression(self):
        adapter = LLMAssistedZ3Adapter()
        constraint = Z3Constraint(
            name="c1",
            expression="totally invalid",
            natural_language="garbage",
            confidence=0.1,
        )
        result = await adapter.verify_policy_constraints([constraint])
        assert isinstance(result, Z3VerificationResult)

    # --- _parse_z3_expression ---

    def test_parse_z3_expression_simple_bool(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const x Bool)\n(assert x)")
        assert expr is not None

    def test_parse_z3_expression_and(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression(
            "(declare-const x Bool)\n(declare-const y Bool)\n(assert (and x y))"
        )
        assert expr is not None

    def test_parse_z3_expression_or(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression(
            "(declare-const x Bool)\n(declare-const y Bool)\n(assert (or x y))"
        )
        assert expr is not None

    def test_parse_z3_expression_not(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const x Bool)\n(assert (not x))")
        assert expr is not None

    def test_parse_z3_expression_true_false(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(assert true)")
        assert expr is not None

    def test_parse_z3_expression_invalid_returns_none(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("garbage input")
        assert expr is None

    def test_parse_z3_expression_no_assertions(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const x Bool)")
        assert expr is None

    def test_parse_z3_expression_int(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const x Int)")
        assert expr is None  # No assertion

    # --- helper methods ---

    def test_is_balanced(self):
        adapter = LLMAssistedZ3Adapter()
        assert adapter._is_balanced("(a (b) c)") is True
        assert adapter._is_balanced("(a (b c)") is False
        assert adapter._is_balanced("") is True

    def test_split_by_op(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_by_op("a and b", " and ")
        assert parts == ["a", "b"]

    def test_split_by_op_nested(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_by_op("(a and b) or c", " or ")
        assert len(parts) == 2
        assert parts[0] == "(a and b)"
        assert parts[1] == "c"

    def test_split_balanced(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_balanced("and x (or a b)")
        assert parts == ["and", "x", "(or a b)"]

    # --- refine_constraints ---

    @pytest.mark.asyncio
    async def test_refine_constraints_already_sat(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert x)",
                natural_language="x",
                confidence=0.9,
            )
        ]
        sat_result = Z3VerificationResult(is_sat=True)
        refined = await adapter.refine_constraints(constraints, sat_result)
        assert refined is constraints

    @pytest.mark.asyncio
    async def test_refine_constraints_with_unsat_core(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert x)",
                natural_language="x must be true",
                confidence=0.9,
            ),
        ]
        unsat_result = Z3VerificationResult(
            is_sat=False,
            unsat_core=["c1"],
        )
        refined = await adapter.refine_constraints(constraints, unsat_result, max_iterations=1)
        assert refined[0].confidence < 0.9

    @pytest.mark.asyncio
    async def test_refine_constraints_no_unsat_core(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert x)",
                natural_language="x",
                confidence=0.9,
            ),
        ]
        unsat_result = Z3VerificationResult(is_sat=False, unsat_core=[])
        refined = await adapter.refine_constraints(constraints, unsat_result, max_iterations=3)
        # No refinement possible without unsat core, confidence unchanged
        assert refined[0].confidence == 0.9


# ---------------------------------------------------------------------------
# ConstitutionalZ3Verifier
# ---------------------------------------------------------------------------


class TestConstitutionalZ3Verifier:
    @pytest.mark.asyncio
    async def test_verify_constitutional_policy_sat(self):
        verifier = ConstitutionalZ3Verifier()
        policy = await verifier.verify_constitutional_policy(
            "p1", "All agents must be authenticated."
        )
        assert policy.id == "p1"
        assert policy.is_verified is True
        assert policy.verification_result is not None
        assert "p1" in verifier.verified_policies

    @pytest.mark.asyncio
    async def test_verify_policy_compliance_verified(self):
        verifier = ConstitutionalZ3Verifier()
        await verifier.verify_constitutional_policy("p1", "All agents must be authenticated.")
        result = await verifier.verify_policy_compliance("p1", {"action": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_policy_compliance_not_found(self):
        verifier = ConstitutionalZ3Verifier()
        result = await verifier.verify_policy_compliance("nonexistent", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_policy_compliance_not_verified(self):
        verifier = ConstitutionalZ3Verifier()
        verifier.verified_policies["p1"] = ConstitutionalPolicy(
            id="p1",
            natural_language="test",
            z3_constraints=[],
            is_verified=False,
        )
        result = await verifier.verify_policy_compliance("p1", {})
        assert result is False

    def test_get_constitutional_hash(self):
        verifier = ConstitutionalZ3Verifier()
        assert verifier.get_constitutional_hash() == CONSTITUTIONAL_HASH

    def test_get_verification_stats_empty(self):
        verifier = ConstitutionalZ3Verifier()
        stats = verifier.get_verification_stats()
        assert stats["total_policies"] == 0
        assert stats["verification_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_get_verification_stats_with_policies(self):
        verifier = ConstitutionalZ3Verifier()
        await verifier.verify_constitutional_policy("p1", "Agents must be authenticated.")
        stats = verifier.get_verification_stats()
        assert stats["total_policies"] == 1
        assert stats["verified_policies"] == 1
        assert stats["verification_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_policy(self):
        verifier = ConstitutionalZ3Verifier()
        policy = await verifier.verify_constitutional_policy("empty-policy", "")
        assert policy.id == "empty-policy"
        assert policy.natural_language == ""

    @pytest.mark.asyncio
    async def test_verify_with_find_multiple(self):
        verifier = ConstitutionalZ3Verifier()
        policy = await verifier.verify_constitutional_policy(
            "p1", "Agents must be authenticated.", find_multiple=True
        )
        assert policy.verification_result is not None


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


class TestVerifyPolicyFormally:
    @pytest.mark.asyncio
    async def test_with_explicit_id(self):
        policy = await verify_policy_formally("Users must log in.", policy_id="test_1")
        assert policy.id == "test_1"

    @pytest.mark.asyncio
    async def test_with_auto_id(self):
        policy = await verify_policy_formally("Users must log in.")
        assert policy.id.startswith("policy_")

    @pytest.mark.asyncio
    async def test_complex_or_and_policy(self):
        """Test LogicGraph P2: complex logic with OR/AND."""
        adapter = LLMAssistedZ3Adapter()
        constraint = await adapter._generate_single_constraint(
            {
                "type": "obligation",
                "text": "Access is allowed if user is admin or user is hr",
                "priority": "high",
            }
        )
        assert constraint is not None
        assert constraint.generated_by == "logicgraph_generator"


if __name__ == "__main__":
    pytest.main([__file__])
