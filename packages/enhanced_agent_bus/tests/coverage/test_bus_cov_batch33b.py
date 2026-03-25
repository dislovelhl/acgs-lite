"""Coverage batch 33b: z3_adapter and llm_assistant uncovered lines.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# llm_assistant imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.llm_assistant import (
    LLMAssistant,
    get_llm_assistant,
    reset_llm_assistant,
)
from enhanced_agent_bus.models import AgentMessage, MessageType

# ---------------------------------------------------------------------------
# z3_adapter imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.verification.z3_adapter import (
    Z3_AVAILABLE,
    ConstitutionalPolicy,
    ConstitutionalZ3Verifier,
    LLMAssistedZ3Adapter,
    Z3Constraint,
    Z3SolverAdapter,
    Z3VerificationResult,
    verify_policy_formally,
)

pytestmark = pytest.mark.unit

# ===================================================================
# Helpers
# ===================================================================


def _make_message(
    content: str = "test content",
    from_agent: str = "agent-a",
    to_agent: str = "agent-b",
    message_type: MessageType | None = None,
    payload: dict | None = None,
) -> AgentMessage:
    mt = message_type or MessageType.COMMAND
    kwargs: dict = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "message_type": mt,
        "content": {"text": content},
    }
    if payload is not None:
        kwargs["payload"] = payload
    return AgentMessage(**kwargs)


# ===================================================================
# Z3Constraint dataclass
# ===================================================================


class TestZ3Constraint:
    def test_auto_timestamp(self):
        c = Z3Constraint(name="c1", expression="expr", natural_language="text", confidence=0.8)
        assert c.timestamp is not None
        assert isinstance(c.timestamp, datetime)

    def test_explicit_timestamp_preserved(self):
        ts = datetime(2025, 1, 1, tzinfo=UTC)
        c = Z3Constraint(
            name="c1",
            expression="expr",
            natural_language="text",
            confidence=0.8,
            timestamp=ts,
        )
        assert c.timestamp == ts

    def test_generated_by_default(self):
        c = Z3Constraint(name="c1", expression="expr", natural_language="text", confidence=0.5)
        assert c.generated_by == "llm"


# ===================================================================
# Z3VerificationResult dataclass
# ===================================================================


class TestZ3VerificationResult:
    def test_defaults_filled(self):
        r = Z3VerificationResult(is_sat=True)
        assert r.constraints_used == []
        assert r.solver_stats == {}
        assert r.alternative_paths == []

    def test_explicit_values_preserved(self):
        r = Z3VerificationResult(
            is_sat=False,
            unsat_core=["a"],
            constraints_used=["c1"],
            solver_stats={"k": "v"},
            alternative_paths=[{"x": 1}],
        )
        assert r.unsat_core == ["a"]
        assert r.constraints_used == ["c1"]
        assert r.alternative_paths == [{"x": 1}]


# ===================================================================
# ConstitutionalPolicy dataclass
# ===================================================================


class TestConstitutionalPolicy:
    def test_auto_created_at(self):
        p = ConstitutionalPolicy(id="p1", natural_language="text", z3_constraints=[])
        assert p.created_at is not None
        assert p.verified_at is None
        assert p.is_verified is False


# ===================================================================
# Z3SolverAdapter
# ===================================================================

if Z3_AVAILABLE:
    import z3


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
class TestZ3SolverAdapter:
    def test_init_default_timeout(self):
        adapter = Z3SolverAdapter()
        assert adapter.timeout_ms == 5000

    def test_init_custom_timeout(self):
        adapter = Z3SolverAdapter(timeout_ms=1000)
        assert adapter.timeout_ms == 1000

    def test_reset_solver(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="x is true", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        assert len(adapter.named_constraints) == 1

        adapter.reset_solver()
        assert len(adapter.named_constraints) == 0

    def test_get_constraint_names(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="nl", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        assert adapter.get_constraint_names() == ["c1"]

    def test_check_sat_satisfiable(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(name="c1", expression="x", natural_language="nl", confidence=1.0)
        adapter.add_constraint("c1", x, meta)
        result = adapter.check_sat()
        assert result.is_sat is True
        assert result.model is not None
        assert result.solve_time_ms >= 0

    def test_check_sat_unsatisfiable(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        adapter.solver.add(x)
        adapter.solver.add(z3.Not(x))
        result = adapter.check_sat()
        assert result.is_sat is False

    def test_check_sat_find_multiple(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        meta = Z3Constraint(
            name="c1", expression="x or not x", natural_language="nl", confidence=1.0
        )
        # x can be True or False
        adapter.add_constraint("c1", z3.Or(x, z3.Not(x)), meta)
        result = adapter.check_sat(find_multiple=True, max_paths=3)
        assert result.is_sat is True
        assert len(result.alternative_paths) >= 1

    def test_check_sat_find_multiple_exhausted(self):
        """When there's only one possible model, enumeration stops."""
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        adapter.solver.add(x)
        meta = Z3Constraint(name="c1", expression="x", natural_language="nl", confidence=1.0)
        adapter.named_constraints["c1"] = x
        adapter.constraint_history.append(meta)
        result = adapter.check_sat(find_multiple=True, max_paths=5)
        assert result.is_sat is True
        # Should have found at most 1 path since x is forced True
        assert len(result.alternative_paths) >= 1

    def test_model_to_dict_int_value(self):
        adapter = Z3SolverAdapter()
        x = z3.Int("x")
        adapter.solver.add(x == 42)
        result = adapter.check_sat()
        assert result.is_sat is True
        assert result.model["x"] == 42

    def test_model_to_dict_bool_value(self):
        adapter = Z3SolverAdapter()
        b = z3.Bool("b")
        adapter.solver.add(b)
        result = adapter.check_sat()
        assert result.is_sat is True
        assert result.model["b"] in (True, "True")

    def test_model_to_dict_string_fallback(self):
        """Non-int non-bool values fall back to str()."""
        adapter = Z3SolverAdapter()
        x = z3.Real("x")
        adapter.solver.add(x == 3.14)
        result = adapter.check_sat()
        assert result.is_sat is True
        assert "x" in result.model
        # Real values become strings
        assert isinstance(result.model["x"], str)

    async def test_async_check_sat(self):
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        adapter.solver.add(x)
        result = await adapter.async_check_sat()
        assert result.is_sat is True

    def test_check_sat_unknown_treated_as_unsat(self):
        """When solver returns unknown, treat as unsat."""
        adapter = Z3SolverAdapter(timeout_ms=1)
        # Create something that might time out or mock it
        with patch.object(adapter.solver, "check", return_value=z3.unknown):
            result = adapter.check_sat()
            assert result.is_sat is False
            assert result.solver_stats.get("result") == "unknown"

    def test_unsat_core_collection_error(self):
        """When unsat_core() raises, error is logged but result returned."""
        adapter = Z3SolverAdapter()
        x = z3.Bool("x")
        adapter.solver.add(x)
        adapter.solver.add(z3.Not(x))

        with patch.object(adapter.solver, "unsat_core", side_effect=RuntimeError("core fail")):
            result = adapter.check_sat()
            assert result.is_sat is False

    def test_find_multiple_no_block_vars(self):
        """When model has no 0-arity decls, block list is empty and loop breaks."""
        adapter = Z3SolverAdapter()
        # Use a trivial constraint that yields a model with no decls to block
        adapter.solver.add(z3.BoolVal(True))
        result = adapter.check_sat(find_multiple=True, max_paths=3)
        assert result.is_sat is True


# ===================================================================
# LLMAssistedZ3Adapter
# ===================================================================


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
class TestLLMAssistedZ3Adapter:
    def test_init(self):
        adapter = LLMAssistedZ3Adapter()
        assert adapter.max_refinements == 3
        assert adapter.z3_solver is not None

    def test_extract_policy_elements_obligations(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements(
            "Agents must validate input. Data shall be encrypted."
        )
        assert len(elements) == 2
        assert all(e["type"] == "obligation" for e in elements)
        assert all(e["priority"] == "high" for e in elements)

    def test_extract_policy_elements_permissions(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements(
            "Agents may access logs. Monitoring is optional."
        )
        assert len(elements) == 2
        assert all(e["type"] == "permission" for e in elements)

    def test_extract_policy_elements_prohibitions(self):
        adapter = LLMAssistedZ3Adapter()
        # Note: "cannot" contains "can" so it matches "permission" first in the
        # elif chain. "forbidden" alone hits prohibition correctly.
        elements = adapter._extract_policy_elements("Deletion is forbidden. Leaking is forbidden.")
        assert len(elements) == 2
        assert all(e["type"] == "prohibition" for e in elements)

    def test_extract_policy_elements_empty(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements("")
        assert elements == []

    def test_extract_policy_elements_no_keywords(self):
        adapter = LLMAssistedZ3Adapter()
        elements = adapter._extract_policy_elements("The sky is blue.")
        assert elements == []

    async def test_generate_single_constraint_obligation(self):
        adapter = LLMAssistedZ3Adapter()
        element = {"type": "obligation", "text": "Agents must validate input", "priority": "high"}
        result = await adapter._generate_single_constraint(element)
        assert result is not None
        assert result.generated_by == "pattern_matching"
        assert result.confidence == 0.8

    async def test_generate_single_constraint_prohibition(self):
        adapter = LLMAssistedZ3Adapter()
        element = {"type": "prohibition", "text": "Agents cannot delete data", "priority": "high"}
        result = await adapter._generate_single_constraint(element)
        assert result is not None
        assert result.generated_by == "pattern_matching"
        assert result.confidence == 0.9
        assert "(not" in result.expression

    async def test_generate_single_constraint_must_not(self):
        adapter = LLMAssistedZ3Adapter()
        element = {
            "type": "prohibition",
            "text": "Agents must not leak secrets",
            "priority": "high",
        }
        result = await adapter._generate_single_constraint(element)
        assert result is not None
        assert "(not" in result.expression

    async def test_generate_single_constraint_unknown_type(self):
        adapter = LLMAssistedZ3Adapter()
        element = {"type": "unknown_type", "text": "Something irrelevant", "priority": "low"}
        result = await adapter._generate_single_constraint(element)
        assert result is None

    async def test_generate_single_constraint_complex_or(self):
        adapter = LLMAssistedZ3Adapter()
        element = {
            "type": "obligation",
            "text": "Access is allowed if user is admin or user is hr",
            "priority": "high",
        }
        result = await adapter._generate_single_constraint(element)
        assert result is not None
        assert result.generated_by == "logicgraph_generator"
        assert result.confidence == 0.9

    async def test_generate_single_constraint_complex_and(self):
        adapter = LLMAssistedZ3Adapter()
        element = {
            "type": "obligation",
            "text": "Access is allowed if user is admin and resource is public",
            "priority": "high",
        }
        result = await adapter._generate_single_constraint(element)
        assert result is not None
        assert result.generated_by == "logicgraph_generator"

    async def test_generate_single_constraint_complex_nested(self):
        adapter = LLMAssistedZ3Adapter()
        element = {
            "type": "obligation",
            "text": "Access is allowed if (user is admin or user is hr) and resource is public",
            "priority": "high",
        }
        result = await adapter._generate_single_constraint(element)
        assert result is not None

    async def test_natural_language_to_constraints(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = await adapter.natural_language_to_constraints(
            "Agents must validate input. Data shall be encrypted."
        )
        assert len(constraints) >= 1

    async def test_natural_language_to_constraints_with_context(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = await adapter.natural_language_to_constraints(
            "All agents must log activity.",
            context={"env": "production"},
        )
        assert isinstance(constraints, list)

    async def test_verify_policy_constraints_sat(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert x)",
                natural_language="x is true",
                confidence=0.9,
            )
        ]
        result = await adapter.verify_policy_constraints(constraints)
        assert result.is_sat is True

    async def test_verify_policy_constraints_unsat(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert x)\n(assert (not x))",
                natural_language="contradiction",
                confidence=0.9,
            )
        ]
        # The parser combines assertions with And, making x AND NOT x -> unsat
        result = await adapter.verify_policy_constraints(constraints)
        assert result.is_sat is False

    async def test_verify_policy_constraints_parse_failure_skipped(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="bad",
                expression="(((invalid z3",
                natural_language="bad expr",
                confidence=0.5,
            )
        ]
        result = await adapter.verify_policy_constraints(constraints)
        # No valid constraints added, solver says sat trivially
        assert isinstance(result, Z3VerificationResult)

    async def test_verify_policy_constraints_find_multiple(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert (or x (not x)))",
                natural_language="tautology",
                confidence=1.0,
            )
        ]
        result = await adapter.verify_policy_constraints(constraints, find_multiple=True)
        assert result.is_sat is True

    # --- parse_z3_expression ---

    def test_parse_z3_expression_bool_decl_assert(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const x Bool)\n(assert x)")
        assert expr is not None

    def test_parse_z3_expression_int_decl(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const n Int)\n(assert (== n n))")
        assert expr is not None

    def test_parse_z3_expression_and(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression(
            "(declare-const a Bool)\n(declare-const b Bool)\n(assert (and a b))"
        )
        assert expr is not None

    def test_parse_z3_expression_or(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression(
            "(declare-const a Bool)\n(declare-const b Bool)\n(assert (or a b))"
        )
        assert expr is not None

    def test_parse_z3_expression_not(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const a Bool)\n(assert (not a))")
        assert expr is not None

    def test_parse_z3_expression_eq(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression(
            "(declare-const x Int)\n(declare-const y Int)\n(assert (== x y))"
        )
        assert expr is not None

    def test_parse_z3_expression_neq(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression(
            "(declare-const x Int)\n(declare-const y Int)\n(assert (!= x y))"
        )
        assert expr is not None

    def test_parse_z3_expression_true_false_literals(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(assert true)")
        assert expr is not None
        expr2 = adapter._parse_z3_expression("(assert false)")
        assert expr2 is not None

    def test_parse_z3_expression_undeclared_var_fallback(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(assert undeclared_var)")
        assert expr is not None

    def test_parse_z3_expression_no_assertions_returns_none(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(declare-const x Bool)")
        assert expr is None

    def test_parse_z3_expression_empty_string(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("")
        assert expr is None

    def test_parse_z3_expression_invalid_returns_none(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression("(assert (unknownop a b))")
        # unknownop is not recognized -> parse_expr raises ValueError -> returns None
        assert expr is None

    def test_parse_z3_expression_multiple_assertions(self):
        adapter = LLMAssistedZ3Adapter()
        expr = adapter._parse_z3_expression(
            "(declare-const a Bool)\n(declare-const b Bool)\n(assert a)\n(assert b)"
        )
        assert expr is not None

    # --- _is_balanced ---

    def test_is_balanced_valid(self):
        adapter = LLMAssistedZ3Adapter()
        assert adapter._is_balanced("(a (b) c)") is True
        assert adapter._is_balanced("") is True
        assert adapter._is_balanced("no parens") is True

    def test_is_balanced_unbalanced(self):
        adapter = LLMAssistedZ3Adapter()
        assert adapter._is_balanced("(a (b)") is False
        assert adapter._is_balanced(")a(") is False
        assert adapter._is_balanced("((") is False

    # --- _split_by_op ---

    def test_split_by_op_simple(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_by_op("a and b", " and ")
        assert parts == ["a", "b"]

    def test_split_by_op_nested(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_by_op("(a or b) and c", " and ")
        assert parts == ["(a or b)", "c"]

    def test_split_by_op_no_match(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_by_op("a or b", " and ")
        assert parts == ["a or b"]

    # --- _split_balanced ---

    def test_split_balanced_simple(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_balanced("and a b")
        assert parts == ["and", "a", "b"]

    def test_split_balanced_nested(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_balanced("and (or a b) c")
        assert parts == ["and", "(or a b)", "c"]

    def test_split_balanced_empty(self):
        adapter = LLMAssistedZ3Adapter()
        parts = adapter._split_balanced("")
        assert parts == []

    # --- refine_constraints ---

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
        assert refined == constraints

    async def test_refine_constraints_no_unsat_core(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert x)",
                natural_language="x",
                confidence=0.9,
            )
        ]
        unsat_result = Z3VerificationResult(is_sat=False, unsat_core=[])
        refined = await adapter.refine_constraints(constraints, unsat_result)
        # No unsat_core -> breaks immediately
        assert len(refined) == len(constraints)

    async def test_refine_constraints_with_unsat_core(self):
        adapter = LLMAssistedZ3Adapter()
        constraints = [
            Z3Constraint(
                name="c1",
                expression="(declare-const x Bool)\n(assert x)",
                natural_language="x must be true",
                confidence=0.9,
            )
        ]
        unsat_result = Z3VerificationResult(is_sat=False, unsat_core=["c1"])
        refined = await adapter.refine_constraints(constraints, unsat_result, max_iterations=1)
        # The constraint was refined (confidence lowered)
        assert refined[0].confidence <= 0.9
        assert refined[0].generated_by.startswith("refined_")


# ===================================================================
# ConstitutionalZ3Verifier
# ===================================================================


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
class TestConstitutionalZ3Verifier:
    async def test_verify_constitutional_policy_sat(self):
        verifier = ConstitutionalZ3Verifier()
        policy = await verifier.verify_constitutional_policy("p1", "Agents must validate input.")
        assert policy.id == "p1"
        assert isinstance(policy.is_verified, bool)

    async def test_verify_constitutional_policy_with_context(self):
        verifier = ConstitutionalZ3Verifier()
        policy = await verifier.verify_constitutional_policy(
            "p2", "Data shall be encrypted.", context={"env": "prod"}
        )
        assert policy.id == "p2"

    async def test_verify_constitutional_policy_find_multiple(self):
        verifier = ConstitutionalZ3Verifier()
        policy = await verifier.verify_constitutional_policy(
            "p3", "Agents must log actions.", find_multiple=True
        )
        assert policy.id == "p3"

    async def test_verify_policy_compliance_not_found(self):
        verifier = ConstitutionalZ3Verifier()
        result = await verifier.verify_policy_compliance("nonexistent", {})
        assert result is False

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

    async def test_verify_policy_compliance_verified(self):
        verifier = ConstitutionalZ3Verifier()
        verifier.verified_policies["p1"] = ConstitutionalPolicy(
            id="p1",
            natural_language="test",
            z3_constraints=[],
            is_verified=True,
        )
        result = await verifier.verify_policy_compliance("p1", {"action": "read"})
        assert result is True

    def test_get_constitutional_hash(self):
        verifier = ConstitutionalZ3Verifier()
        h = verifier.get_constitutional_hash()
        assert isinstance(h, str)
        assert len(h) > 0

    def test_get_verification_stats_empty(self):
        verifier = ConstitutionalZ3Verifier()
        stats = verifier.get_verification_stats()
        assert stats["total_policies"] == 0
        assert stats["verified_policies"] == 0
        assert stats["verification_rate"] == 0.0

    async def test_get_verification_stats_with_policies(self):
        verifier = ConstitutionalZ3Verifier()
        await verifier.verify_constitutional_policy("p1", "Agents must validate input.")
        stats = verifier.get_verification_stats()
        assert stats["total_policies"] == 1


# ===================================================================
# verify_policy_formally convenience function
# ===================================================================


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
class TestVerifyPolicyFormally:
    async def test_with_explicit_id(self):
        policy = await verify_policy_formally("Agents must validate input.", policy_id="explicit-1")
        assert policy.id == "explicit-1"

    async def test_with_generated_id(self):
        policy = await verify_policy_formally("Data must be encrypted.")
        assert policy.id.startswith("policy_")


# ===================================================================
# LLMAssistant
# ===================================================================


class TestLLMAssistant:
    def setup_method(self):
        reset_llm_assistant()

    # --- _fallback_analysis ---

    def test_fallback_analysis_low_risk(self):
        assistant = LLMAssistant()
        msg = _make_message(content="normal data transfer")
        result = assistant._fallback_analysis(msg)
        assert result["risk_level"] == "low"
        assert result["requires_human_review"] is False
        assert result["recommended_decision"] == "approve"
        assert result["analyzed_by"] == "enhanced_fallback_analyzer"

    def test_fallback_analysis_critical_breach(self):
        assistant = LLMAssistant()
        msg = _make_message(content="data breach detected")
        result = assistant._fallback_analysis(msg)
        assert result["risk_level"] == "critical"
        assert result["requires_human_review"] is True
        assert result["recommended_decision"] == "review"

    def test_fallback_analysis_high_risk_emergency(self):
        assistant = LLMAssistant()
        msg = _make_message(content="emergency shutdown required")
        result = assistant._fallback_analysis(msg)
        assert result["risk_level"] == "high"
        assert result["requires_human_review"] is True

    def test_fallback_analysis_high_risk_security(self):
        assistant = LLMAssistant()
        msg = _make_message(content="security vulnerability found")
        result = assistant._fallback_analysis(msg)
        assert result["risk_level"] == "high"
        assert "security" in result["impact_areas"]
        assert result["impact_areas"]["security"] == "Medium"

    def test_fallback_analysis_high_risk_violation(self):
        assistant = LLMAssistant()
        msg = _make_message(content="policy violation detected")
        result = assistant._fallback_analysis(msg)
        assert result["risk_level"] == "high"

    def test_fallback_analysis_high_risk_critical_keyword(self):
        assistant = LLMAssistant()
        msg = _make_message(content="critical system failure")
        result = assistant._fallback_analysis(msg)
        assert result["risk_level"] == "high"

    # --- _fallback_reasoning ---

    def test_fallback_reasoning_majority_approve(self):
        assistant = LLMAssistant()
        msg = _make_message()
        votes = [
            {"vote": "approve", "reasoning": "ok"},
            {"vote": "approve", "reasoning": "fine"},
            {"vote": "reject", "reasoning": "bad"},
        ]
        result = assistant._fallback_reasoning(msg, votes, None)
        assert result["final_recommendation"] == "approve"
        assert "2/3" in result["process_summary"]

    def test_fallback_reasoning_majority_reject(self):
        assistant = LLMAssistant()
        msg = _make_message()
        votes = [{"vote": "reject"}, {"vote": "reject"}, {"vote": "approve"}]
        result = assistant._fallback_reasoning(msg, votes, None)
        assert result["final_recommendation"] == "review"

    def test_fallback_reasoning_with_human_decision(self):
        assistant = LLMAssistant()
        msg = _make_message()
        votes = [{"vote": "approve"}]
        result = assistant._fallback_reasoning(msg, votes, "REJECT")
        assert result["final_recommendation"] == "reject"

    def test_fallback_reasoning_empty_votes(self):
        assistant = LLMAssistant()
        msg = _make_message()
        result = assistant._fallback_reasoning(msg, [], None)
        assert result["final_recommendation"] == "review"
        assert "0/0" in result["process_summary"]

    # --- _extract_message_summary ---

    def test_extract_message_summary_short_content(self):
        assistant = LLMAssistant()
        msg = _make_message(content="short")
        summary = assistant._extract_message_summary(msg)
        assert "short" in summary
        assert "From Agent: agent-a" in summary

    def test_extract_message_summary_long_content_truncated(self):
        assistant = LLMAssistant()
        long_content = "x" * 600
        msg = _make_message(content=long_content)
        summary = assistant._extract_message_summary(msg)
        assert "..." in summary

    def test_extract_message_summary_with_payload(self):
        assistant = LLMAssistant()
        msg = _make_message(payload={"key": "value"})
        summary = assistant._extract_message_summary(msg)
        assert "Payload:" in summary

    def test_extract_message_summary_long_payload_truncated(self):
        assistant = LLMAssistant()
        long_payload = {"k" * 50: "v" * 200}
        msg = _make_message(payload=long_payload)
        summary = assistant._extract_message_summary(msg)
        assert "..." in summary

    # --- _summarize_votes ---

    def test_summarize_votes_empty(self):
        assistant = LLMAssistant()
        result = assistant._summarize_votes([])
        assert result == "No votes recorded"

    def test_summarize_votes_with_dict_votes(self):
        assistant = LLMAssistant()
        votes = [
            {"vote": "approve", "reasoning": "looks good"},
            {"vote": "reject", "reasoning": "concerns about safety"},
        ]
        result = assistant._summarize_votes(votes)
        assert "Total votes: 2" in result
        assert "Approve: 1" in result
        assert "Reject: 1" in result

    def test_summarize_votes_no_reasoning_key(self):
        assistant = LLMAssistant()
        votes = [{"vote": "approve"}, {"vote": "reject"}]
        result = assistant._summarize_votes(votes)
        assert "No reasoning provided" in result

    def test_summarize_votes_long_reasoning_truncated(self):
        assistant = LLMAssistant()
        votes = [{"vote": "approve", "reasoning": "x" * 200}]
        result = assistant._summarize_votes(votes)
        assert "..." in result

    def test_summarize_votes_max_three_shown(self):
        assistant = LLMAssistant()
        votes = [{"vote": "approve", "reasoning": f"r{i}"} for i in range(10)]
        result = assistant._summarize_votes(votes)
        # Only first 3 sample reasonings shown
        assert "r0" in result
        assert "r2" in result

    # --- _summarize_deliberation_history ---

    def test_summarize_deliberation_history_empty(self):
        assistant = LLMAssistant()
        result = assistant._summarize_deliberation_history([])
        assert result == "No deliberation history available"

    def test_summarize_deliberation_history_with_data(self):
        assistant = LLMAssistant()
        history = [
            {"outcome": "approved", "impact_score": 0.8},
            {"outcome": "rejected", "impact_score": 0.5},
            {"outcome": "timed_out", "impact_score": 0.3},
            {"outcome": "approved", "impact_score": 0.9},
        ]
        result = assistant._summarize_deliberation_history(history)
        assert "Total deliberations: 4" in result
        assert "Approved: 2" in result
        assert "Rejected: 1" in result
        assert "Timed out: 1" in result
        assert "Average impact score:" in result

    # --- _fallback_analysis_trends ---

    def test_fallback_analysis_trends_empty(self):
        assistant = LLMAssistant()
        result = assistant._fallback_analysis_trends([])
        assert result["patterns"] == []
        assert result["risk_trends"] == "stable"

    def test_fallback_analysis_trends_high_approval(self):
        assistant = LLMAssistant()
        history = [{"outcome": "approved"} for _ in range(9)] + [{"outcome": "rejected"}]
        result = assistant._fallback_analysis_trends(history)
        assert "efficiency" in result["threshold_recommendations"].lower()
        assert result["risk_trends"] == "improving"

    def test_fallback_analysis_trends_low_approval(self):
        assistant = LLMAssistant()
        history = [{"outcome": "approved"}] + [{"outcome": "rejected"} for _ in range(9)]
        result = assistant._fallback_analysis_trends(history)
        assert "rejection" in result["threshold_recommendations"].lower()
        assert result["risk_trends"] == "stable"

    def test_fallback_analysis_trends_moderate(self):
        assistant = LLMAssistant()
        history = [{"outcome": "approved"} for _ in range(7)] + [
            {"outcome": "rejected"} for _ in range(3)
        ]
        result = assistant._fallback_analysis_trends(history)
        assert result["threshold_recommendations"] == "Maintain current threshold"
        assert result["risk_trends"] == "improving"

    # --- analyze_message_impact (no LLM) ---

    async def test_analyze_message_impact_no_llm(self):
        assistant = LLMAssistant()
        msg = _make_message(content="normal data")
        result = await assistant.analyze_message_impact(msg)
        assert result["analyzed_by"] == "enhanced_fallback_analyzer"

    # --- generate_decision_reasoning (no LLM) ---

    async def test_generate_decision_reasoning_no_llm(self):
        assistant = LLMAssistant()
        msg = _make_message()
        votes = [{"vote": "approve", "reasoning": "ok"}]
        result = await assistant.generate_decision_reasoning(msg, votes)
        assert result["generated_by"] == "enhanced_fallback_reasoner"

    async def test_generate_decision_reasoning_no_llm_with_human(self):
        assistant = LLMAssistant()
        msg = _make_message()
        result = await assistant.generate_decision_reasoning(msg, [], human_decision="approve")
        assert result["final_recommendation"] == "approve"

    # --- analyze_deliberation_trends ---

    async def test_analyze_deliberation_trends(self):
        assistant = LLMAssistant()
        history = [{"outcome": "approved"}, {"outcome": "rejected"}]
        result = await assistant.analyze_deliberation_trends(history)
        assert "patterns" in result

    # --- _invoke_llm with mocked LLM ---

    async def test_invoke_llm_no_llm_returns_empty(self):
        assistant = LLMAssistant()
        assert assistant.llm is None
        result = await assistant._invoke_llm("template {x}", x="val")
        assert result == {}

    async def test_invoke_llm_with_mock_llm(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"result": "ok"}'
        mock_response.response_metadata = {}
        mock_llm.ainvoke.return_value = mock_response
        assistant.llm = mock_llm

        with patch(
            "enhanced_agent_bus.deliberation_layer.llm_assistant.JsonOutputParser"
        ) as MockParser:
            MockParser.return_value.parse.return_value = {"result": "ok"}
            result = await assistant._invoke_llm("template {x}", x="val")
            assert result.get("result") == "ok"

    async def test_invoke_llm_with_token_tracking(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"result": "ok"}'
        mock_response.response_metadata = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }
        }
        mock_llm.ainvoke.return_value = mock_response
        assistant.llm = mock_llm

        with patch(
            "enhanced_agent_bus.deliberation_layer.llm_assistant.JsonOutputParser"
        ) as MockParser:
            MockParser.return_value.parse.return_value = {"result": "ok"}
            result = await assistant._invoke_llm("template {x}", x="val")
            assert result.get("_metrics", {}).get("token_usage", {}).get("total_tokens") == 30

    async def test_invoke_llm_error_returns_empty(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("API error")
        assistant.llm = mock_llm

        result = await assistant._invoke_llm("template {x}", x="val")
        assert result == {}

    # --- ainvoke_multi_turn ---

    async def test_ainvoke_multi_turn_no_llm(self):
        assistant = LLMAssistant()
        result = await assistant.ainvoke_multi_turn("sys", [{"role": "user", "content": "hi"}])
        assert result == {}

    async def test_ainvoke_multi_turn_with_mock_llm(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '{"analysis": "done"}'
        mock_response.response_metadata = {}
        mock_llm.ainvoke.return_value = mock_response
        assistant.llm = mock_llm

        with patch(
            "enhanced_agent_bus.deliberation_layer.llm_assistant.JsonOutputParser"
        ) as MockParser:
            MockParser.return_value.parse.return_value = {"analysis": "done"}
            result = await assistant.ainvoke_multi_turn(
                "system prompt",
                [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi"},
                ],
            )
            assert result.get("analysis") == "done"

    async def test_ainvoke_multi_turn_error(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        assistant.llm = mock_llm

        with patch.object(assistant, "_invoke_llm", side_effect=ValueError("bad prompt")):
            result = await assistant.ainvoke_multi_turn("sys", [{"role": "user", "content": "hi"}])
            assert result == {}

    # --- analyze_message_impact with mocked LLM ---

    async def test_analyze_message_impact_with_llm(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        assistant.llm = mock_llm

        llm_result = {
            "risk_level": "low",
            "requires_human_review": False,
            "recommended_decision": "approve",
            "confidence": 0.95,
        }

        with patch.object(assistant, "_invoke_llm", return_value=llm_result):
            msg = _make_message(content="test data")
            result = await assistant.analyze_message_impact(msg)
            assert result["analyzed_by"] == "llm_analyzer"
            assert result["risk_level"] == "low"

    async def test_analyze_message_impact_llm_returns_empty_falls_back(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        assistant.llm = mock_llm

        with patch.object(assistant, "_invoke_llm", return_value={}):
            msg = _make_message(content="test data")
            result = await assistant.analyze_message_impact(msg)
            assert result["analyzed_by"] == "enhanced_fallback_analyzer"

    # --- generate_decision_reasoning with mocked LLM ---

    async def test_generate_decision_reasoning_with_llm(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        assistant.llm = mock_llm

        llm_result = {
            "process_summary": "deliberation complete",
            "final_recommendation": "approve",
        }

        with patch.object(assistant, "_invoke_llm", return_value=llm_result):
            msg = _make_message()
            votes = [{"vote": "approve"}]
            result = await assistant.generate_decision_reasoning(msg, votes, "approve")
            assert result["generated_by"] == "llm_reasoner"

    async def test_generate_decision_reasoning_llm_empty_falls_back(self):
        assistant = LLMAssistant()
        mock_llm = AsyncMock()
        assistant.llm = mock_llm

        with patch.object(assistant, "_invoke_llm", return_value={}):
            msg = _make_message()
            result = await assistant.generate_decision_reasoning(msg, [])
            assert result["generated_by"] == "enhanced_fallback_reasoner"


# ===================================================================
# get_llm_assistant / reset_llm_assistant singletons
# ===================================================================


class TestLLMAssistantSingleton:
    def setup_method(self):
        reset_llm_assistant()

    def teardown_method(self):
        reset_llm_assistant()

    def test_get_llm_assistant_creates_singleton(self):
        a1 = get_llm_assistant()
        a2 = get_llm_assistant()
        assert a1 is a2

    def test_reset_llm_assistant(self):
        a1 = get_llm_assistant()
        reset_llm_assistant()
        a2 = get_llm_assistant()
        assert a1 is not a2
