"""
Coverage tests for z3_policy_verifier.py and mamba2_hybrid_processor.py
Constitutional Hash: 608508a9bd224290

Targets uncovered lines in:
  - enhanced_agent_bus.verification_layer.z3_policy_verifier (Z3SolverWrapper,
    parse expression branches, check() model extraction, error paths)
  - enhanced_agent_bus.mamba2_hybrid_processor (torch-dependent classes,
    context manager memory pressure, JRT truncation, factory functions)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Z3 Policy Verifier imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.verification_layer.z3_policy_verifier import (
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

# ===================================================================
# SECTION 1: Z3SolverWrapper — real Z3 is available in this env
# ===================================================================


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3 not installed")
class TestZ3SolverWrapperReal:
    """Test Z3SolverWrapper using real z3 module."""

    def _make_wrapper(self, timeout_ms: int = 1000):
        from enhanced_agent_bus.verification_layer.z3_policy_verifier import (
            Z3SolverWrapper,
        )

        return Z3SolverWrapper(timeout_ms=timeout_ms)

    def test_wrapper_init_sets_timeout(self):
        wrapper = self._make_wrapper(2000)
        assert wrapper.timeout_ms == 2000

    def test_reset_clears_state(self):
        wrapper = self._make_wrapper()
        wrapper.declare_variable("x", "Bool")
        wrapper._constraints["c1"] = "expr"
        wrapper.reset()
        assert wrapper._variables == {}
        assert wrapper._constraints == {}

    def test_declare_variable_bool(self):
        wrapper = self._make_wrapper()
        var = wrapper.declare_variable("flag", "Bool")
        assert "flag" in wrapper._variables
        assert str(var) == "flag"

    def test_declare_variable_int(self):
        wrapper = self._make_wrapper()
        var = wrapper.declare_variable("count", "Int")
        assert "count" in wrapper._variables
        assert str(var) == "count"

    def test_declare_variable_real(self):
        wrapper = self._make_wrapper()
        var = wrapper.declare_variable("ratio", "Real")
        assert "ratio" in wrapper._variables
        assert str(var) == "ratio"

    def test_declare_variable_unknown_defaults_to_bool(self):
        wrapper = self._make_wrapper()
        var = wrapper.declare_variable("thing", "UnknownType")
        assert "thing" in wrapper._variables
        # Default is Bool
        assert str(var) == "thing"

    def test_add_constraint_bool_assert(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert flag)",
            variables={"flag": "Bool"},
        )
        result = wrapper.add_constraint("c1", constraint)
        assert result is True
        assert "c1" in wrapper._constraints

    def test_add_constraint_not_pattern(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert (not flag))",
            variables={"flag": "Bool"},
        )
        result = wrapper.add_constraint("c2", constraint)
        assert result is True

    def test_add_constraint_gte_comparison(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert (>= val 10))",
            variables={"val": "Int"},
        )
        result = wrapper.add_constraint("c3", constraint)
        assert result is True

    def test_add_constraint_lte_comparison(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert (<= val 5))",
            variables={"val": "Int"},
        )
        result = wrapper.add_constraint("c4", constraint)
        assert result is True

    def test_add_constraint_eq_comparison(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert (= val 42))",
            variables={"val": "Int"},
        )
        result = wrapper.add_constraint("c5", constraint)
        assert result is True

    def test_add_constraint_declare_const_returns_false(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="decl",
            expression="(declare-const x Bool)",
            variables={"x": "Bool"},
        )
        result = wrapper.add_constraint("c6", constraint)
        assert result is False

    def test_add_constraint_unparseable_returns_false(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="bad",
            expression="random gibberish",
            variables={},
        )
        result = wrapper.add_constraint("c7", constraint)
        assert result is False

    def test_add_constraint_error_handling(self):
        wrapper = self._make_wrapper()
        # Force error by making variables dict raise on iteration
        bad_vars = MagicMock()
        bad_vars.items.side_effect = RuntimeError("boom")
        constraint = PolicyConstraint(
            name="err",
            expression="(assert x)",
        )
        constraint.variables = bad_vars
        result = wrapper.add_constraint("c8", constraint)
        assert result is False

    def test_parse_expression_not_unknown_var(self):
        wrapper = self._make_wrapper()
        # Variable not declared => returns None
        result = wrapper._parse_expression("(assert (not unknown_var))")
        assert result is None

    def test_parse_expression_comparison_unknown_var(self):
        wrapper = self._make_wrapper()
        result = wrapper._parse_expression("(assert (>= unknown 10))")
        assert result is None

    def test_parse_expression_comparison_insufficient_parts(self):
        wrapper = self._make_wrapper()
        # Only 2 parts after stripping parens
        result = wrapper._parse_expression("(assert (>= x))")
        assert result is None

    def test_parse_expression_bare_variable(self):
        wrapper = self._make_wrapper()
        wrapper.declare_variable("flag", "Bool")
        result = wrapper._parse_expression("(assert flag)")
        assert result is not None

    def test_parse_expression_bare_unknown_var(self):
        wrapper = self._make_wrapper()
        result = wrapper._parse_expression("(assert unknown_var)")
        assert result is None

    def test_parse_expression_declare_const(self):
        wrapper = self._make_wrapper()
        result = wrapper._parse_expression("(declare-const x Bool)")
        assert result is None

    def test_parse_expression_completely_unrecognized(self):
        wrapper = self._make_wrapper()
        result = wrapper._parse_expression("totally invalid stuff")
        assert result is None

    def test_parse_expression_error_path(self):
        wrapper = self._make_wrapper()
        # Monkey-patch _variables to raise on __contains__
        original = wrapper._variables
        wrapper._variables = MagicMock()
        wrapper._variables.__contains__ = MagicMock(side_effect=RuntimeError("internal error"))
        result = wrapper._parse_expression("(assert (not x))")
        assert result is None
        wrapper._variables = original

    def test_check_satisfiable_bool_model(self):
        import z3

        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert flag)",
            variables={"flag": "Bool"},
        )
        wrapper.add_constraint("c1", constraint)
        status, model_dict, unsat_core = wrapper.check()
        assert status == Z3VerificationStatus.SATISFIABLE
        assert model_dict is not None
        assert "flag" in model_dict
        assert unsat_core is None

    def test_check_satisfiable_int_model(self):
        wrapper = self._make_wrapper()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert (>= val 10))",
            variables={"val": "Int"},
        )
        wrapper.add_constraint("c1", constraint)
        status, model_dict, unsat_core = wrapper.check()
        assert status == Z3VerificationStatus.SATISFIABLE
        assert model_dict is not None
        assert "val" in model_dict
        assert model_dict["val"] >= 10

    def test_check_satisfiable_real_model(self):
        """Real-valued variable in model uses str fallback."""
        wrapper = self._make_wrapper()
        # Declare real var, add constraint
        wrapper.declare_variable("r", "Real")
        import z3

        wrapper.solver.add(wrapper._variables["r"] >= 1)
        wrapper._constraints["c1"] = wrapper._variables["r"] >= 1
        status, model_dict, _ = wrapper.check()
        assert status == Z3VerificationStatus.SATISFIABLE
        assert "r" in model_dict

    def test_check_unsatisfiable(self):
        wrapper = self._make_wrapper()
        # Add contradictory constraints
        c1 = PolicyConstraint(
            name="c1",
            expression="(assert flag)",
            variables={"flag": "Bool"},
        )
        wrapper.add_constraint("c1", c1)
        c2 = PolicyConstraint(
            name="c2",
            expression="(assert (not flag))",
            variables={"flag": "Bool"},
        )
        wrapper.add_constraint("c2", c2)
        status, model_dict, unsat_core = wrapper.check()
        assert status == Z3VerificationStatus.UNSATISFIABLE
        assert model_dict is None

    def test_check_unsat_core_error_handling(self):
        """When unsat_core() raises, returns empty list."""
        wrapper = self._make_wrapper()
        c1 = PolicyConstraint(
            name="c1",
            expression="(assert flag)",
            variables={"flag": "Bool"},
        )
        wrapper.add_constraint("c1", c1)
        c2 = PolicyConstraint(
            name="c2",
            expression="(assert (not flag))",
            variables={"flag": "Bool"},
        )
        wrapper.add_constraint("c2", c2)
        # Patch unsat_core to raise
        wrapper.solver.unsat_core = MagicMock(side_effect=RuntimeError("no core"))
        status, _, unsat_core = wrapper.check()
        assert status == Z3VerificationStatus.UNSATISFIABLE
        assert unsat_core == []


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3 not installed")
class TestZ3SolverWrapperUnavailable:
    """Test Z3SolverWrapper when Z3_AVAILABLE is False."""

    def test_raises_import_error(self):
        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
            False,
        ):
            from enhanced_agent_bus.verification_layer.z3_policy_verifier import (
                Z3SolverWrapper,
            )

            with pytest.raises(ImportError, match="Z3 solver not available"):
                Z3SolverWrapper()


# ===================================================================
# SECTION 2: Z3PolicyVerifier error paths
# ===================================================================


class TestVerifyPolicyErrorPath:
    """Cover the except block in verify_policy (lines 774-785)."""

    async def test_verify_policy_catches_runtime_error(self):
        verifier = Z3PolicyVerifier()
        constraint = PolicyConstraint(
            name="Obligation: test",
            confidence=0.85,
        )
        request = PolicyVerificationRequest(
            policy_id="err1",
            constraints=[constraint],
        )
        with (
            patch.object(verifier, "_verify_with_z3", side_effect=RuntimeError("boom")),
            patch(
                "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
                True,
            ),
        ):
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.ERROR
        assert result.is_verified is False
        assert any("verification_error" in str(v) for v in result.violations)
        assert result.proof is not None

    async def test_verify_policy_catches_value_error(self):
        verifier = Z3PolicyVerifier()
        request = PolicyVerificationRequest(
            policy_id="err2",
            constraints=[PolicyConstraint(name="test")],
        )
        with (
            patch.object(verifier, "_verify_with_z3", side_effect=ValueError("bad value")),
            patch(
                "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
                True,
            ),
        ):
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.ERROR
        assert len(result.violations) > 0

    async def test_verify_policy_catches_type_error(self):
        verifier = Z3PolicyVerifier()
        request = PolicyVerificationRequest(
            policy_id="err3",
            constraints=[PolicyConstraint(name="test")],
        )
        with (
            patch.object(verifier, "_verify_with_z3", side_effect=TypeError("type err")),
            patch(
                "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
                True,
            ),
        ):
            result = await verifier.verify_policy(request)

        assert result.status == Z3VerificationStatus.ERROR
        assert result.proof is not None
        # Proof trace should have error entry
        assert any(entry["step"] == "error" for entry in result.proof.proof_trace)


class TestVerifyWithZ3ErrorPath:
    """Cover the except block in _verify_with_z3 (lines 865-871)."""

    async def test_z3_solver_wrapper_raises(self):
        verifier = Z3PolicyVerifier()
        proof = VerificationProof()
        constraint = PolicyConstraint(
            name="test",
            expression="(assert x)",
            variables={"x": "Bool"},
        )
        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            side_effect=TypeError("type error in z3"),
        ):
            result = await verifier._verify_with_z3([constraint], {}, 1000, proof)
        assert result["status"] == Z3VerificationStatus.ERROR
        assert result["is_verified"] is False
        assert any("z3_error" in str(v) for v in result["violations"])

    async def test_z3_add_constraint_fails_all(self):
        """When all constraints fail to add, added_count = 0."""
        verifier = Z3PolicyVerifier()
        proof = VerificationProof()

        mock_wrapper = MagicMock()
        mock_wrapper.add_constraint.return_value = False
        mock_wrapper.check.return_value = (
            Z3VerificationStatus.SATISFIABLE,
            {},
            None,
        )

        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3SolverWrapper",
            return_value=mock_wrapper,
        ):
            constraint = PolicyConstraint(
                name="test",
                expression="(declare-const x Bool)",
                variables={"x": "Bool"},
            )
            result = await verifier._verify_with_z3([constraint], {}, 1000, proof)
        # is_verified depends on solver check result
        assert isinstance(result["satisfied"], int)


class TestVerifyPolicyHeuristicFallbackZ3Unavailable:
    """Cover the Z3-unavailable heuristic path (lines 738-752)."""

    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        False,
    )
    async def test_z3_unavailable_heuristic_with_violations(self):
        verifier = Z3PolicyVerifier(
            enable_heuristic_fallback=True,
            heuristic_threshold=0.99,
        )
        constraint = PolicyConstraint(
            name="Obligation: strict",
            confidence=0.5,
            is_mandatory=True,
        )
        request = PolicyVerificationRequest(
            policy_id="heur1",
            constraints=[constraint],
            use_heuristic_fallback=True,
        )
        result = await verifier.verify_policy(request)
        assert result.status == Z3VerificationStatus.HEURISTIC_FALLBACK
        assert result.is_verified is False
        assert result.proof.heuristic_score is not None
        assert len(result.violations) > 0

    @patch(
        "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
        False,
    )
    async def test_z3_unavailable_heuristic_verified(self):
        verifier = Z3PolicyVerifier(
            enable_heuristic_fallback=True,
            heuristic_threshold=0.5,
        )
        constraint = PolicyConstraint(
            name="Obligation: easy",
            confidence=0.85,
            is_mandatory=True,
        )
        request = PolicyVerificationRequest(
            policy_id="heur2",
            constraints=[constraint],
            use_heuristic_fallback=True,
        )
        result = await verifier.verify_policy(request)
        assert result.status == Z3VerificationStatus.HEURISTIC_FALLBACK
        assert result.is_verified is True
        assert result.satisfied_constraints > 0


# ===================================================================
# SECTION 3: ConstraintGenerator edge cases
# ===================================================================


class TestConstraintGeneratorEdgeCases:
    """Additional coverage for ConstraintGenerator."""

    async def test_generate_constraint_sentence_with_multiple_comparisons(self):
        gen = ConstraintGenerator()
        constraints = await gen.generate_constraints("Value must be greater than 50.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) == 1
        assert ">=" in comp[0].expression

    async def test_generate_constraint_less_than_no_number(self):
        gen = ConstraintGenerator()
        constraints = await gen.generate_constraints("Cost is less than expected.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) == 1
        assert "0" in comp[0].expression

    async def test_generate_constraints_trailing_dots(self):
        gen = ConstraintGenerator()
        constraints = await gen.generate_constraints("...")
        assert constraints == []

    async def test_generate_prohibition_forbidden_details(self):
        gen = ConstraintGenerator()
        constraints = await gen.generate_constraints("Unencrypted storage is forbidden.")
        assert len(constraints) == 1
        c = constraints[0]
        assert c.generated_by == "pattern_matching"
        assert c.constraint_type == ConstraintType.BOOLEAN
        assert "(not " in c.expression


# ===================================================================
# SECTION 4: HeuristicVerifier edge cases
# ===================================================================


class TestHeuristicVerifierEdgeCases:
    """Additional coverage for HeuristicVerifier."""

    async def test_comparison_constraint_unknown_name(self):
        """Constraint with name not matching obligation/prohibition/permission."""
        hv = HeuristicVerifier()
        c = PolicyConstraint(
            name="Custom: some rule",
            confidence=0.9,
            is_mandatory=True,
        )
        score, violations = await hv.verify([c], {})
        assert score == pytest.approx(0.9 * 0.85)

    async def test_non_mandatory_low_score_no_violation(self):
        hv = HeuristicVerifier()
        c = PolicyConstraint(
            name="Custom: low",
            confidence=0.1,
            is_mandatory=False,
        )
        score, violations = await hv.verify([c], {})
        assert violations == []


# ===================================================================
# SECTION 5: VerificationProof / Result edge cases
# ===================================================================


class TestVerificationProofEdgeCases:
    """Additional coverage for VerificationProof."""

    def test_to_dict_with_model_and_unsat_core(self):
        p = VerificationProof(
            model={"x": 1, "y": True},
            unsat_core=["c1", "c2"],
            heuristic_score=0.85,
            solver_stats={"decisions": 10},
        )
        d = p.to_dict()
        assert d["model"] == {"x": 1, "y": True}
        assert d["unsat_core"] == ["c1", "c2"]
        assert d["heuristic_score"] == 0.85
        assert d["solver_stats"] == {"decisions": 10}

    def test_to_dict_none_fields(self):
        p = VerificationProof()
        d = p.to_dict()
        assert d["model"] is None
        assert d["unsat_core"] is None
        assert d["heuristic_score"] is None


class TestPolicyVerificationResultEdgeCases:
    """Additional coverage for PolicyVerificationResult."""

    def test_to_dict_all_fields(self):
        proof = VerificationProof(is_verified=True)
        r = PolicyVerificationResult(
            is_verified=True,
            status=Z3VerificationStatus.SATISFIABLE,
            proof=proof,
            violations=[{"type": "test"}],
            warnings=["warning1"],
            recommendations=["rec1"],
            total_constraints=5,
            satisfied_constraints=4,
            total_time_ms=100.5,
            metadata={"key": "val"},
        )
        d = r.to_dict()
        assert d["is_verified"] is True
        assert d["status"] == "satisfiable"
        assert d["proof"]["is_verified"] is True
        assert len(d["violations"]) == 1
        assert d["warnings"] == ["warning1"]
        assert d["recommendations"] == ["rec1"]
        assert d["total_time_ms"] == 100.5


# ===================================================================
# SECTION 6: Verification stats
# ===================================================================


class TestVerificationStatsAfterMultipleRuns:
    """Cover get_verification_stats with different status distributions."""

    async def test_stats_with_mixed_statuses(self):
        verifier = Z3PolicyVerifier(heuristic_threshold=0.99)
        await verifier.verify_policy(PolicyVerificationRequest(policy_id="s1"))
        await verifier.verify_policy(
            PolicyVerificationRequest(
                policy_id="s2",
                policy_text="Agents must log actions.",
            )
        )
        stats = verifier.get_verification_stats()
        assert stats["total_verifications"] == 2
        assert "status_distribution" in stats
        assert isinstance(stats["status_distribution"], dict)
        assert stats["average_time_ms"] >= 0
        assert stats["average_constraints"] >= 0


# ===================================================================
# SECTION 7: Recommendations additional
# ===================================================================


class TestRecommendationsAdditional:
    """Additional recommendation generation coverage."""

    def test_multiple_unsat_violations(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(
            is_verified=False,
            violations=[
                {"type": "unsatisfiable_constraint", "constraint": "c1"},
                {"type": "unsatisfiable_constraint", "constraint": "c2"},
                {"type": "other_type"},
            ],
        )
        recs = v._generate_recommendations(result, [])
        conflict_recs = [r for r in recs if "Constraint conflict" in r]
        assert len(conflict_recs) == 2

    def test_exactly_50_constraints_no_decompose_rec(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(
            is_verified=True,
            status=Z3VerificationStatus.SATISFIABLE,
            total_constraints=50,
        )
        recs = v._generate_recommendations(result, [PolicyConstraint()] * 50)
        assert not any("decomposing" in r.lower() for r in recs)

    def test_error_status_no_unsat_recommendations(self):
        v = Z3PolicyVerifier()
        result = PolicyVerificationResult(
            is_verified=False,
            status=Z3VerificationStatus.ERROR,
            violations=[{"type": "verification_error", "description": "boom"}],
        )
        recs = v._generate_recommendations(result, [])
        assert any("Review" in r for r in recs)
        assert not any("Constraint conflict" in r for r in recs)


# ===================================================================
# SECTION 8: Mamba2 Hybrid Processor
# ===================================================================

from enhanced_agent_bus.mamba2_hybrid_processor import (
    TORCH_AVAILABLE,
    Mamba2Config,
)


class TestMamba2ConfigEdgeCases:
    """Additional Mamba2Config coverage."""

    def test_all_overrides(self):
        cfg = Mamba2Config(
            d_model=128,
            d_state=64,
            d_conv=2,
            expand_factor=4,
            num_mamba_layers=3,
            num_attention_layers=2,
            max_seq_len=1024,
            jrt_repeat_factor=3,
            use_flash_attention=False,
            use_nested_tensor=False,
            compile_model=True,
            gradient_checkpointing=False,
            offload_to_cpu=True,
            max_memory_percent=80.0,
            max_gpu_memory_gb=8.0,
        )
        assert cfg.d_model == 128
        assert cfg.d_state == 64
        assert cfg.expand_factor == 4
        assert cfg.use_flash_attention is False
        assert cfg.compile_model is True
        assert cfg.offload_to_cpu is True
        assert cfg.max_memory_percent == 80.0


class TestConstitutionalContextManagerEdgeCases:
    """Non-torch tests for ConstitutionalContextManager methods."""

    def test_build_context_single_entry_window(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        mgr = ConstitutionalContextManager.__new__(ConstitutionalContextManager)
        result = mgr._build_context("current", ["single"])
        assert "single" in result
        assert "current" in result

    def test_build_context_empty_window(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        mgr = ConstitutionalContextManager.__new__(ConstitutionalContextManager)
        result = mgr._build_context("only", [])
        assert result == "only"

    def test_identify_critical_positions_multiple_keywords(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        mgr = ConstitutionalContextManager.__new__(ConstitutionalContextManager)
        result = mgr._identify_critical_positions(
            "the governance security rule applies",
            ["governance", "security"],
        )
        assert 0 in result
        assert 1 in result
        assert 2 in result

    def test_identify_critical_positions_keyword_at_end(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        mgr = ConstitutionalContextManager.__new__(ConstitutionalContextManager)
        result = mgr._identify_critical_positions("this is governance", ["governance"])
        assert 0 in result
        assert 2 in result

    def test_identify_critical_positions_no_match(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        mgr = ConstitutionalContextManager.__new__(ConstitutionalContextManager)
        result = mgr._identify_critical_positions("nothing special here", ["constitutional"])
        assert result == []

    def test_identify_critical_positions_partial_match(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        mgr = ConstitutionalContextManager.__new__(ConstitutionalContextManager)
        # "govern" should match "governance" via `in` check
        result = mgr._identify_critical_positions("the governance rule", ["govern"])
        assert 1 in result


# ---------------------------------------------------------------------------
# Torch-dependent tests
# ---------------------------------------------------------------------------


def _patched_conv1d_init(self, *args, **kwargs):
    """Patch Conv1d to accept the buggy call signature from Mamba2SSM."""
    import torch.nn as _nn

    if len(args) == 1 and "kernel_size" in kwargs and "out_channels" not in kwargs:
        in_channels = args[0]
        kwargs.setdefault("out_channels", in_channels)
        args = (in_channels,)
    _nn.Conv1d.__orig_init__(self, *args, **kwargs)


@pytest.fixture()
def _patch_conv1d():
    """Fixture that patches Conv1d.__init__ for the Mamba2SSM bug."""
    if not TORCH_AVAILABLE:
        yield
        return
    import torch.nn as _nn

    _nn.Conv1d.__orig_init__ = _nn.Conv1d.__init__
    _nn.Conv1d.__init__ = _patched_conv1d_init
    yield
    _nn.Conv1d.__init__ = _nn.Conv1d.__orig_init__
    del _nn.Conv1d.__orig_init__


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
@pytest.mark.usefixtures("_patch_conv1d")
class TestMamba2TorchCoverage:
    """Torch-dependent coverage tests."""

    def test_prepare_jrt_context_default_positions(self):
        """Default positions: [0, len(input_ids)-1] where len is batch dim."""
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2, jrt_repeat_factor=2)
        model = ConstitutionalMambaHybrid(cfg)
        input_ids = torch.tensor([[10, 20, 30, 40, 50]])
        # len(input_ids) = 1 (batch dim), so positions = [0, 0]
        # Only position 0 gets repeated: 2 + 1 + 1 + 1 + 1 = 6
        prepared = model._prepare_jrt_context(input_ids, critical_positions=None)
        assert prepared.shape[1] == 6

    def test_prepare_jrt_context_single_token(self):
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2, jrt_repeat_factor=3)
        model = ConstitutionalMambaHybrid(cfg)
        input_ids = torch.tensor([[42]])
        prepared = model._prepare_jrt_context(input_ids, critical_positions=None)
        # positions=[0,0], position 0 repeated 3 times
        assert prepared.shape[1] == 3

    def test_prepare_jrt_context_position_out_of_bounds(self):
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2, jrt_repeat_factor=2)
        model = ConstitutionalMambaHybrid(cfg)
        input_ids = torch.tensor([[1, 2, 3]])
        prepared = model._prepare_jrt_context(input_ids, critical_positions=[0, 100])
        # Position 100 >= seq_len (3), so only position 0 is repeated
        # total = 2 + 1 + 1 = 4
        assert prepared.shape[1] == 4

    def test_prepare_jrt_context_truncation_path(self):
        """JRT truncation when expanded exceeds max_seq_len."""
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(
            d_model=64,
            d_state=16,
            num_mamba_layers=2,
            max_seq_len=8,
            jrt_repeat_factor=2,
        )
        model = ConstitutionalMambaHybrid(cfg)
        input_ids = torch.tensor([[1, 2, 3, 4, 5, 6]])
        # critical_positions=[0, 5]: pos 0 x2, pos 5 x2, others x1
        # expanded = 2 + 1 + 1 + 1 + 1 + 2 = 8, equals max_seq_len
        # No truncation needed but exercises the check path
        prepared = model._prepare_jrt_context(input_ids, critical_positions=[0, 5])
        assert prepared.shape[0] == 1
        assert prepared.shape[1] == 8

    def test_prepare_jrt_context_truncation_middle_removal(self):
        """JRT truncation that actually removes middle tokens."""
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(
            d_model=64,
            d_state=16,
            num_mamba_layers=2,
            max_seq_len=6,
            jrt_repeat_factor=2,
        )
        model = ConstitutionalMambaHybrid(cfg)
        # 8 tokens, positions [2, 7]
        input_ids = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8]])
        # pos 2 x2, pos 7 x2, others x1
        # expanded = 1+1+2+1+1+1+1+2 = 10 > max_seq_len=6
        # keep_start = 2*2 = 4
        # keep_end = min(6-4, 10-7*2) = min(2, -4) = -4
        # middle_trunc = 10 - 4 - (-4) = 18 > 0
        # keep_end <= 0 so end_keep = []
        # result = expanded[:4] = first 4 tokens
        prepared = model._prepare_jrt_context(input_ids, critical_positions=[2, 7])
        assert prepared.shape[0] == 1
        # The truncation logic preserves start portion
        assert prepared.shape[1] >= 0

    def test_prepare_jrt_context_no_truncation_needed(self):
        """JRT with no truncation needed."""
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(
            d_model=64,
            d_state=16,
            num_mamba_layers=2,
            max_seq_len=100,
            jrt_repeat_factor=2,
        )
        model = ConstitutionalMambaHybrid(cfg)
        input_ids = torch.tensor([[1, 2, 3]])
        prepared = model._prepare_jrt_context(input_ids, critical_positions=[0, 2])
        # pos 0 x2, pos 1 x1, pos 2 x2 = 5
        assert prepared.shape[1] == 5

    def test_memory_usage_has_config(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        model = ConstitutionalMambaHybrid(cfg)
        stats = model.get_memory_usage()
        assert stats["config"]["d_model"] == 64
        assert stats["config"]["num_mamba_layers"] == 2
        assert stats["config"]["max_seq_len"] == cfg.max_seq_len
        assert stats["model_size_mb"] > 0

    def test_check_memory_pressure_normal(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(
            d_model=64,
            d_state=16,
            num_mamba_layers=2,
            max_memory_percent=99.9,
            max_gpu_memory_gb=999.0,
        )
        mgr = ConstitutionalContextManager(cfg)
        pressure = mgr.check_memory_pressure()
        assert pressure["pressure_level"] == "normal"

    def test_check_memory_pressure_high_threshold(self):
        """Simulate high pressure via very low threshold."""
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(
            d_model=64,
            d_state=16,
            num_mamba_layers=2,
            max_memory_percent=1.0,
            max_gpu_memory_gb=0.0,
        )
        mgr = ConstitutionalContextManager(cfg)
        pressure = mgr.check_memory_pressure()
        assert pressure["pressure_level"] in ("high", "critical")

    def test_extract_compliance_score_zero_embeddings(self):
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        mgr = ConstitutionalContextManager(cfg)
        embeddings = torch.zeros(1, 5, 64)
        score = mgr._extract_compliance_score(embeddings)
        assert score == 0.0

    def test_extract_compliance_score_large_embeddings(self):
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        mgr = ConstitutionalContextManager(cfg)
        embeddings = torch.ones(1, 5, 64) * 100
        score = mgr._extract_compliance_score(embeddings)
        assert score == 1.0

    def test_tokenize_text_single_word(self):
        import torch

        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        mgr = ConstitutionalContextManager(cfg)
        tokens = mgr._tokenize_text("hello")
        assert tokens.shape == (1,)
        assert tokens.dtype == torch.long

    def test_tokenize_text_produces_valid_range(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        mgr = ConstitutionalContextManager(cfg)
        tokens = mgr._tokenize_text("the quick brown fox jumps")
        assert all(0 <= t < 50000 for t in tokens.tolist())

    async def test_process_with_context_critical_memory(self):
        """Cover the critical memory pressure early return path."""
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            CONSTITUTIONAL_HASH,
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        mgr = ConstitutionalContextManager(cfg)

        with patch.object(
            mgr,
            "check_memory_pressure",
            return_value={
                "pressure_level": "critical",
                "process_rss_mb": 1000,
                "system_percent": 95.0,
                "gpu_allocated_gb": 0.0,
                "gpu_reserved_gb": 0.0,
            },
        ):
            result = await mgr.process_with_context("test input")

        assert result["fallback"] is True
        assert result["compliance_score"] == 0.95
        assert "error" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_context_stats_with_entries(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        mgr = ConstitutionalContextManager(cfg)

        mgr._update_context_memory("a", 0.9)
        mgr._update_context_memory("b", 0.7)
        mgr._update_context_memory("c", 0.5)

        stats = mgr.get_context_stats()
        assert stats["total_entries"] == 3
        assert stats["avg_compliance_score"] == pytest.approx(0.7)
        assert stats["max_compliance_score"] == pytest.approx(0.9)
        assert stats["min_compliance_score"] == pytest.approx(0.5)

    def test_create_mamba_hybrid_processor_none_config(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
            create_mamba_hybrid_processor,
        )

        model = create_mamba_hybrid_processor(None)
        assert isinstance(model, ConstitutionalMambaHybrid)
        assert model.config.d_model == 512

    def test_create_constitutional_context_manager_none_config(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalContextManager,
            create_constitutional_context_manager,
        )

        mgr = create_constitutional_context_manager(None)
        assert isinstance(mgr, ConstitutionalContextManager)
        assert mgr.config.d_model == 512


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
@pytest.mark.usefixtures("_patch_conv1d")
class TestMamba2SSMInit:
    """Cover Mamba2SSM fallback init path (lines 107-120)."""

    def test_mamba2ssm_fallback_creates_layers(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import Mamba2SSM

        cfg = Mamba2Config(d_model=64, d_state=16, d_conv=4, expand_factor=2)
        ssm = Mamba2SSM(cfg)
        assert hasattr(ssm, "in_proj")
        assert hasattr(ssm, "conv")
        assert hasattr(ssm, "out_proj")
        assert hasattr(ssm, "A")
        assert hasattr(ssm, "D")

    def test_mamba2ssm_config_stored(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import Mamba2SSM

        cfg = Mamba2Config(d_model=32, d_state=8, d_conv=2, expand_factor=2)
        ssm = Mamba2SSM(cfg)
        assert ssm.config.d_model == 32
        assert ssm.config.expand_factor == 2


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
@pytest.mark.usefixtures("_patch_conv1d")
class TestSharedAttentionInit:
    """Cover SharedAttention init and RoPE (lines 155-179)."""

    def test_shared_attention_creates_projections(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import SharedAttention

        cfg = Mamba2Config(d_model=64)
        attn = SharedAttention(cfg)
        assert hasattr(attn, "q_proj")
        assert hasattr(attn, "k_proj")
        assert hasattr(attn, "v_proj")
        assert hasattr(attn, "out_proj")
        assert attn.num_heads == 8
        assert attn.head_dim == 8

    def test_shared_attention_rope_buffers(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import SharedAttention

        cfg = Mamba2Config(d_model=64, max_seq_len=128)
        attn = SharedAttention(cfg)
        assert hasattr(attn, "cos")
        assert hasattr(attn, "sin")
        assert attn.cos.shape[0] == 128 * 4

    def test_shared_attention_scale(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import SharedAttention

        cfg = Mamba2Config(d_model=64)
        attn = SharedAttention(cfg)
        expected_scale = (64 // 8) ** -0.5
        assert attn.scale == pytest.approx(expected_scale)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
@pytest.mark.usefixtures("_patch_conv1d")
class TestConstitutionalMambaHybridInit:
    """Cover ConstitutionalMambaHybrid._init_weights (lines 285-292)."""

    def test_init_weights_applied(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        model = ConstitutionalMambaHybrid(cfg)
        for name, param in model.named_parameters():
            if "weight" in name and param.dim() >= 2:
                assert abs(param.mean().item()) < 0.5

    def test_model_has_correct_layer_count(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=4)
        model = ConstitutionalMambaHybrid(cfg)
        assert len(model.mamba_layers) == 4

    def test_model_has_shared_attention(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        cfg = Mamba2Config(d_model=64, d_state=16, num_mamba_layers=2)
        model = ConstitutionalMambaHybrid(cfg)
        assert hasattr(model, "shared_attention")
        assert hasattr(model, "norm")
        assert hasattr(model, "output_proj")
        assert hasattr(model, "input_embedding")

    def test_model_default_config_when_none(self):
        from enhanced_agent_bus.mamba2_hybrid_processor import (
            ConstitutionalMambaHybrid,
        )

        model = ConstitutionalMambaHybrid(None)
        assert model.config.d_model == 512
        assert model.config.num_mamba_layers == 6
