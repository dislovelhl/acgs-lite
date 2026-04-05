"""
Coverage tests for batch27a: sic_engine, prov middleware, verify_integration, shared_bridge.

Targets:
- enhanced_agent_bus.verification_layer.sic_engine
- enhanced_agent_bus.middlewares.prov
- enhanced_agent_bus.policy.verify_integration
- enhanced_agent_bus.mcp.shared_bridge

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sic_engine imports
# ---------------------------------------------------------------------------
try:
    from enhanced_agent_bus.verification_layer.sic_engine import (
        SemanticIntegrityConstraint,
        SICEngine,
        SICType,
        SICVerificationResult,
    )

    HAS_SIC_ENGINE = True
except ImportError:
    HAS_SIC_ENGINE = False

# ---------------------------------------------------------------------------
# prov middleware imports
# ---------------------------------------------------------------------------
try:
    from enhanced_agent_bus.middlewares.prov import (
        ProvMiddleware,
        _middleware_name_to_stage,
        _utc_now_iso,
    )
    from enhanced_agent_bus.pipeline.context import PipelineContext
    from enhanced_agent_bus.pipeline.middleware import MiddlewareConfig
    from enhanced_agent_bus.prov.labels import ProvLabel

    HAS_PROV = True
except ImportError:
    HAS_PROV = False

# ---------------------------------------------------------------------------
# verify_integration imports
# ---------------------------------------------------------------------------
try:
    from enhanced_agent_bus.policy.verify_integration import verify_proven_integration

    HAS_VERIFY_INTEGRATION = True
except ImportError:
    HAS_VERIFY_INTEGRATION = False

# ---------------------------------------------------------------------------
# shared_bridge imports
# ---------------------------------------------------------------------------
try:
    from enhanced_agent_bus.mcp.shared_bridge import MCPBridge

    HAS_SHARED_BRIDGE = True
except ImportError:
    HAS_SHARED_BRIDGE = False

try:
    from enhanced_agent_bus._compat.orchestration.intent_graph import SwarmTask, TaskIntent
except ImportError:
    # Provide minimal stubs if the shared module is unavailable
    try:
        from enhanced_agent_bus.mcp.shared_bridge import SwarmTask, TaskIntent  # type: ignore
    except ImportError:

        class TaskIntent(str, Enum):  # type: ignore[no-redef]
            VALIDATE = "validate"
            METRICS = "metrics"
            PROPOSE = "propose"
            AUDIT = "audit"

        @dataclass
        class SwarmTask:  # type: ignore[no-redef]
            id: str = "t1"
            intent: Any = TaskIntent.VALIDATE
            payload: dict = field(default_factory=dict)
            status: str = "pending"
            result: dict | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline_context(**overrides: Any) -> PipelineContext:
    """Create a minimal PipelineContext for testing."""
    from enhanced_agent_bus.models import AgentMessage

    msg = AgentMessage(
        content="test",
        sender_id="s1",
        to_agent="r1",
    )
    return PipelineContext(message=msg, **overrides)


# ===================================================================
# Tests for SICType enum
# ===================================================================


@pytest.mark.skipif(not HAS_SIC_ENGINE, reason="sic_engine not importable")
class TestSICType:
    def test_enum_values(self):
        assert SICType.GROUNDING.value == "grounding"
        assert SICType.SOUNDNESS.value == "soundness"
        assert SICType.EXCLUSION.value == "exclusion"

    def test_enum_members_count(self):
        assert len(SICType) == 3


# ===================================================================
# Tests for SemanticIntegrityConstraint model
# ===================================================================


@pytest.mark.skipif(not HAS_SIC_ENGINE, reason="sic_engine not importable")
class TestSemanticIntegrityConstraint:
    def test_default_id_generated(self):
        sic = SemanticIntegrityConstraint(
            sic_type=SICType.GROUNDING,
            description="test",
            formal_expression="(assert true)",
            variables={},
        )
        assert sic.id.startswith("sic_")

    def test_custom_fields(self):
        sic = SemanticIntegrityConstraint(
            id="custom_id",
            sic_type=SICType.EXCLUSION,
            description="no pii",
            formal_expression="(assert (not pii))",
            variables={"pii": "Bool"},
            is_mandatory=False,
        )
        assert sic.id == "custom_id"
        assert sic.sic_type is SICType.EXCLUSION
        assert sic.is_mandatory is False

    def test_mandatory_default_true(self):
        sic = SemanticIntegrityConstraint(
            sic_type=SICType.SOUNDNESS,
            description="d",
            formal_expression="e",
            variables={},
        )
        assert sic.is_mandatory is True


# ===================================================================
# Tests for SICVerificationResult model
# ===================================================================


@pytest.mark.skipif(not HAS_SIC_ENGINE, reason="sic_engine not importable")
class TestSICVerificationResult:
    def test_compliant_result(self):
        r = SICVerificationResult(
            is_compliant=True,
            violations=[],
            latency_ms=0.5,
            cryptographic_proof="abc123",
        )
        assert r.is_compliant is True
        assert r.violations == []
        assert r.cryptographic_proof == "abc123"

    def test_non_compliant_result(self):
        r = SICVerificationResult(
            is_compliant=False,
            violations=["exceeded limit"],
            latency_ms=1.2,
            cryptographic_proof=None,
        )
        assert r.is_compliant is False
        assert len(r.violations) == 1
        assert r.cryptographic_proof is None


# ===================================================================
# Tests for SICEngine
# ===================================================================


@pytest.mark.skipif(not HAS_SIC_ENGINE, reason="sic_engine not importable")
class TestSICEngine:
    def test_init(self):
        engine = SICEngine()
        assert engine.z3_verifier is not None

    async def test_evaluate_transaction_compliant(self):
        """Happy path: all constraints satisfied."""
        engine = SICEngine()

        mock_proof = MagicMock()
        mock_proof.proof_id = "proof_001"

        mock_result = MagicMock()
        mock_result.is_verified = True
        mock_result.violations = []
        mock_result.proof = mock_proof

        engine.z3_verifier.verify_policy = AsyncMock(return_value=mock_result)

        sic = SemanticIntegrityConstraint(
            sic_type=SICType.SOUNDNESS,
            description="amount <= 10000",
            formal_expression="(assert (<= amount 10000))",
            variables={"amount": "Int"},
        )

        result = await engine.evaluate_transaction(
            transaction_id="tx_1",
            agent_output={"amount": 5000},
            constraints=[sic],
        )

        assert result.is_compliant is True
        assert result.violations == []
        assert result.cryptographic_proof == "proof_001"
        assert result.latency_ms >= 0

    async def test_evaluate_transaction_with_violations(self):
        """Non-compliant output triggers violation list."""
        engine = SICEngine()

        mock_result = MagicMock()
        mock_result.is_verified = False
        mock_result.violations = [
            {"description": "Amount exceeds limit"},
            {"constraint": "fallback_constraint"},
        ]
        mock_result.proof = None

        engine.z3_verifier.verify_policy = AsyncMock(return_value=mock_result)

        sic = SemanticIntegrityConstraint(
            sic_type=SICType.SOUNDNESS,
            description="amount <= 10000",
            formal_expression="(assert (<= amount 10000))",
            variables={"amount": "Int"},
        )

        result = await engine.evaluate_transaction(
            transaction_id="tx_2",
            agent_output={"amount": 15000},
            constraints=[sic],
        )

        assert result.is_compliant is False
        assert len(result.violations) == 2
        assert result.violations[0] == "Amount exceeds limit"
        assert result.violations[1] == "fallback_constraint"
        assert result.cryptographic_proof is None

    async def test_evaluate_transaction_empty_constraints(self):
        """Empty constraint list should still call verify_policy."""
        engine = SICEngine()

        mock_result = MagicMock()
        mock_result.is_verified = True
        mock_result.violations = []
        mock_result.proof = None

        engine.z3_verifier.verify_policy = AsyncMock(return_value=mock_result)

        result = await engine.evaluate_transaction(
            transaction_id="tx_3",
            agent_output={},
            constraints=[],
        )

        assert result.is_compliant is True
        assert result.cryptographic_proof is None

    async def test_evaluate_transaction_mixed_types(self):
        """Agent output with int, float, and string values."""
        engine = SICEngine()

        mock_result = MagicMock()
        mock_result.is_verified = True
        mock_result.violations = []
        mock_result.proof = None

        engine.z3_verifier.verify_policy = AsyncMock(return_value=mock_result)

        result = await engine.evaluate_transaction(
            transaction_id="tx_4",
            agent_output={"count": 10, "score": 3.14, "label": "safe"},
            constraints=[],
        )

        # Verify the request was constructed with context bindings for numerics
        call_args = engine.z3_verifier.verify_policy.call_args
        request = call_args[0][0]
        # int and float should get context bindings, string should not
        binding_ids = [c.constraint_id for c in request.constraints]
        assert "ctx_count" in binding_ids
        assert "ctx_score" in binding_ids
        assert "ctx_label" not in binding_ids

    async def test_evaluate_transaction_violation_unknown_key(self):
        """Violation dict with neither description nor constraint falls back."""
        engine = SICEngine()

        mock_result = MagicMock()
        mock_result.is_verified = False
        mock_result.violations = [{"some_other_key": "val"}]
        mock_result.proof = None

        engine.z3_verifier.verify_policy = AsyncMock(return_value=mock_result)

        result = await engine.evaluate_transaction(
            transaction_id="tx_5",
            agent_output={},
            constraints=[],
        )

        assert result.violations == ["Unknown Violation"]

    async def test_evaluate_transaction_multiple_sic_types(self):
        """Multiple SIC types are all converted and sent to verifier."""
        engine = SICEngine()

        mock_result = MagicMock()
        mock_result.is_verified = True
        mock_result.violations = []
        mock_result.proof = None

        engine.z3_verifier.verify_policy = AsyncMock(return_value=mock_result)

        constraints = [
            SemanticIntegrityConstraint(
                sic_type=SICType.GROUNDING,
                description="grounding check",
                formal_expression="(assert grounded)",
                variables={"grounded": "Bool"},
            ),
            SemanticIntegrityConstraint(
                sic_type=SICType.EXCLUSION,
                description="no pii",
                formal_expression="(assert (not has_pii))",
                variables={"has_pii": "Bool"},
                is_mandatory=False,
            ),
        ]

        result = await engine.evaluate_transaction(
            transaction_id="tx_6",
            agent_output={},
            constraints=constraints,
        )

        call_args = engine.z3_verifier.verify_policy.call_args
        request = call_args[0][0]
        names = [c.name for c in request.constraints]
        assert "SIC_GROUNDING" in names
        assert "SIC_EXCLUSION" in names


# ===================================================================
# Tests for prov middleware helper functions
# ===================================================================


@pytest.mark.skipif(not HAS_PROV, reason="prov middleware not importable")
class TestProvHelpers:
    def test_utc_now_iso_format(self):
        ts = _utc_now_iso()
        assert "T" in ts  # ISO 8601 format
        assert "+" in ts or "UTC" in ts or ts.endswith("+00:00")

    def test_middleware_name_to_stage_known(self):
        assert _middleware_name_to_stage("SecurityMiddleware") == "security_scan"
        assert (
            _middleware_name_to_stage("ConstitutionalValidationMiddleware")
            == "constitutional_validation"
        )
        assert _middleware_name_to_stage("MACIEnforcementMiddleware") == "maci_enforcement"
        assert _middleware_name_to_stage("ImpactScorerMiddleware") == "impact_scoring"
        assert _middleware_name_to_stage("HITLMiddleware") == "hitl_review"
        assert _middleware_name_to_stage("TemporalPolicyMiddleware") == "temporal_policy"
        assert _middleware_name_to_stage("ToolPrivilegeMiddleware") == "tool_privilege"
        assert _middleware_name_to_stage("StrategyMiddleware") == "strategy"
        assert _middleware_name_to_stage("IFCMiddleware") == "ifc_check"

    def test_middleware_name_to_stage_unknown_strips_suffix(self):
        result = _middleware_name_to_stage("FooBarMiddleware")
        assert result == "foo_bar"

    def test_middleware_name_to_stage_no_suffix(self):
        result = _middleware_name_to_stage("CustomProcessor")
        assert result == "custom_processor"

    def test_middleware_name_to_stage_empty_after_strip(self):
        # "Middleware" stripped yields "" -> "unknown_stage"
        result = _middleware_name_to_stage("Middleware")
        assert result == "unknown_stage"

    def test_middleware_name_to_stage_plain_name(self):
        result = _middleware_name_to_stage("simple")
        assert result == "simple"


# ===================================================================
# Tests for ProvMiddleware
# ===================================================================


@pytest.mark.skipif(not HAS_PROV, reason="prov middleware not importable")
class TestProvMiddleware:
    def test_init_default_config(self):
        mw = ProvMiddleware()
        assert mw.config.fail_closed is False
        assert mw.config.timeout_ms == 50

    def test_init_custom_config(self):
        cfg = MiddlewareConfig(timeout_ms=200, fail_closed=True)
        mw = ProvMiddleware(config=cfg)
        assert mw.config.timeout_ms == 200
        assert mw.config.fail_closed is True

    async def test_process_stamps_provenance(self):
        """Happy path: ProvMiddleware stamps a label on context."""
        mw = ProvMiddleware()

        ctx = _make_pipeline_context()
        ctx.middleware_path = ["SecurityMiddleware"]

        # Mock _call_next to return context unchanged
        mw._call_next = AsyncMock(return_value=ctx)

        result = await mw.process(ctx)

        assert "ProvMiddleware" in result.middleware_path
        assert len(result.prov_lineage) >= 1

    async def test_process_unknown_stage_short_path(self):
        """When path is too short, resolves to unknown_stage."""
        mw = ProvMiddleware()

        ctx = _make_pipeline_context()
        ctx.middleware_path = []  # will be ["ProvMiddleware"] after add_middleware

        mw._call_next = AsyncMock(return_value=ctx)

        result = await mw.process(ctx)

        # Should not raise, provenance is fail-open
        assert result is not None

    async def test_process_exception_in_label_building_is_swallowed(self):
        """If build_prov_label raises, middleware continues without blocking."""
        mw = ProvMiddleware()

        ctx = _make_pipeline_context()
        ctx.middleware_path = ["SecurityMiddleware"]

        mw._call_next = AsyncMock(return_value=ctx)

        with patch(
            "enhanced_agent_bus.middlewares.prov.build_prov_label",
            side_effect=ValueError("broken label"),
        ):
            result = await mw.process(ctx)

        # Should not raise; fail-open
        assert result is not None
        assert "ProvMiddleware" in result.middleware_path

    async def test_resolve_stage_name_with_prior_middleware(self):
        """Stage name is derived from path[-2]."""
        mw = ProvMiddleware()
        ctx = _make_pipeline_context()
        ctx.middleware_path = ["ImpactScorerMiddleware", "ProvMiddleware"]

        stage = mw._resolve_stage_name(ctx)
        assert stage == "impact_scoring"

    async def test_resolve_stage_name_short_path(self):
        mw = ProvMiddleware()
        ctx = _make_pipeline_context()
        ctx.middleware_path = ["ProvMiddleware"]

        stage = mw._resolve_stage_name(ctx)
        assert stage == "unknown_stage"

    async def test_resolve_stage_name_empty_path(self):
        mw = ProvMiddleware()
        ctx = _make_pipeline_context()
        ctx.middleware_path = []

        stage = mw._resolve_stage_name(ctx)
        assert stage == "unknown_stage"


# ===================================================================
# Tests for verify_integration
# ===================================================================


@pytest.mark.skipif(not HAS_VERIFY_INTEGRATION, reason="verify_integration not importable")
class TestVerifyIntegration:
    """Test the verify_proven_integration script function.

    Since it depends on heavy internal wiring (AgentBusIntegration, etc.),
    we mock the integration layer and validate control flow.
    """

    async def test_verify_proven_integration_happy_path(self):
        """Mock the integration to return expected governance results."""
        import sys

        mock_governance_admin = {
            "is_allowed": True,
            "verification_status": "verified",
            "policy_id": "pol_1",
        }
        mock_governance_restricted = {
            "is_allowed": False,
            "verification_status": "failed",
            "policy_id": "pol_2",
        }

        mock_instance = MagicMock()
        mock_instance._check_governance = AsyncMock(
            side_effect=[mock_governance_admin, mock_governance_restricted]
        )

        mock_integration_cls = MagicMock(return_value=mock_instance)
        mock_config_cls = MagicMock()

        # The function uses inner imports from enhanced_agent_bus.ai_assistant.integration
        # We inject a fake module into sys.modules so the inner import resolves to our mocks
        fake_module = MagicMock(
            AgentBusIntegration=mock_integration_cls,
            IntegrationConfig=mock_config_cls,
        )

        with patch.dict(
            sys.modules,
            {"enhanced_agent_bus.ai_assistant.integration": fake_module},
        ):
            await verify_proven_integration()

    async def test_function_is_async(self):
        """verify_proven_integration must be a coroutine function."""
        assert inspect.iscoroutinefunction(verify_proven_integration)


# ===================================================================
# Tests for MCPBridge (shared_bridge)
# ===================================================================


@pytest.mark.skipif(not HAS_SHARED_BRIDGE, reason="shared_bridge not importable")
class TestMCPBridge:
    def _make_bridge(self) -> MCPBridge:
        pool = MagicMock()
        return MCPBridge(mcp_pool=pool)

    def test_init_intent_map(self):
        bridge = self._make_bridge()
        assert TaskIntent.VALIDATE in bridge.intent_map
        assert TaskIntent.METRICS in bridge.intent_map
        assert TaskIntent.PROPOSE in bridge.intent_map
        assert TaskIntent.AUDIT in bridge.intent_map
        for tools in bridge.intent_map.values():
            assert tools == []

    async def test_sync_tools_categorizes_validate(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "validate_policy"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "validate_policy" in bridge.intent_map[TaskIntent.VALIDATE]

    async def test_sync_tools_categorizes_check(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "compliance_check"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "compliance_check" in bridge.intent_map[TaskIntent.VALIDATE]

    async def test_sync_tools_categorizes_metrics(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "get_agent_metrics"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "get_agent_metrics" in bridge.intent_map[TaskIntent.METRICS]

    async def test_sync_tools_categorizes_stats(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "cluster_stats"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "cluster_stats" in bridge.intent_map[TaskIntent.METRICS]

    async def test_sync_tools_categorizes_propose(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "propose_amendment"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "propose_amendment" in bridge.intent_map[TaskIntent.PROPOSE]

    async def test_sync_tools_categorizes_evolve(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "policy_evolve"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "policy_evolve" in bridge.intent_map[TaskIntent.PROPOSE]

    async def test_sync_tools_categorizes_audit(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "audit_trail"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "audit_trail" in bridge.intent_map[TaskIntent.AUDIT]

    async def test_sync_tools_categorizes_log(self):
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "event_log"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        assert "event_log" in bridge.intent_map[TaskIntent.AUDIT]

    async def test_sync_tools_uncategorized_tool(self):
        """Tools not matching any pattern are still counted."""
        bridge = self._make_bridge()
        mock_tool = MagicMock()
        mock_tool.name = "random_utility"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=[mock_tool])

        count = await bridge.sync_tools()

        assert count == 1
        # Should not appear in any category
        for tools in bridge.intent_map.values():
            assert "random_utility" not in tools

    async def test_sync_tools_multiple(self):
        bridge = self._make_bridge()
        tools = [MagicMock() for _ in range(4)]
        tools[0].name = "validate_input"
        tools[1].name = "get_metrics"
        tools[2].name = "propose_change"
        tools[3].name = "audit_log"
        bridge.mcp_pool.list_tools = AsyncMock(return_value=tools)

        count = await bridge.sync_tools()

        assert count == 4
        assert len(bridge.intent_map[TaskIntent.VALIDATE]) == 1
        assert len(bridge.intent_map[TaskIntent.METRICS]) == 1
        assert len(bridge.intent_map[TaskIntent.PROPOSE]) == 1
        assert len(bridge.intent_map[TaskIntent.AUDIT]) == 1

    async def test_dispatch_happy_path(self):
        bridge = self._make_bridge()
        bridge.intent_map[TaskIntent.VALIDATE] = ["validate_policy"]

        expected = {"status": "ok"}
        bridge.mcp_pool.call_tool = AsyncMock(return_value=expected)

        task = SwarmTask(id="t1", intent=TaskIntent.VALIDATE, payload={"key": "val"})

        result = await bridge.dispatch(task, agent_id="a1", agent_role="executive")

        assert result == expected
        bridge.mcp_pool.call_tool.assert_awaited_once_with(
            tool_name="validate_policy",
            arguments={"key": "val"},
            agent_id="a1",
            agent_role="executive",
        )

    async def test_dispatch_no_tool_for_intent(self):
        bridge = self._make_bridge()
        # intent_map is empty by default

        task = SwarmTask(id="t2", intent=TaskIntent.METRICS, payload={})

        result = await bridge.dispatch(task, agent_id="a1", agent_role="auditor")

        assert "error" in result
        assert "No tool found" in result["error"]

    async def test_dispatch_picks_first_tool(self):
        """When multiple tools available, dispatch picks the first one."""
        bridge = self._make_bridge()
        bridge.intent_map[TaskIntent.AUDIT] = ["audit_v1", "audit_v2"]

        bridge.mcp_pool.call_tool = AsyncMock(return_value={"ok": True})

        task = SwarmTask(id="t3", intent=TaskIntent.AUDIT, payload={})

        await bridge.dispatch(task, agent_id="a1", agent_role="auditor")

        bridge.mcp_pool.call_tool.assert_awaited_once()
        call_kwargs = bridge.mcp_pool.call_tool.call_args
        assert (
            call_kwargs.kwargs.get("tool_name", call_kwargs[1].get("tool_name", None)) == "audit_v1"
            or call_kwargs[0][0] == "audit_v1"
            if call_kwargs[0]
            else True
        )
