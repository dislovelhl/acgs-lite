"""
Coverage batch 23e: Tests for hp_governance_workflow, resource_registry,
constitutional invariants, and mcp_server.server.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. HighPerformanceGovernanceWorkflow
# ---------------------------------------------------------------------------
from enhanced_agent_bus.workflows.hp_governance_workflow import (
    HighPerformanceGovernanceWorkflow,
)


class TestHighPerformanceGovernanceWorkflow:
    """Tests for HighPerformanceGovernanceWorkflow (44 missing lines, 0%)."""

    def test_name_property(self):
        wf = HighPerformanceGovernanceWorkflow()
        assert wf.name == "high_performance_governance"

    def test_init_with_default_enforcer(self):
        wf = HighPerformanceGovernanceWorkflow()
        assert wf.enforcer is not None

    def test_init_with_custom_enforcer(self):
        enforcer = MagicMock()
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)
        assert wf.enforcer is enforcer

    async def test_run_success(self):
        enforcer = MagicMock()
        enforcer.validate_action = AsyncMock(
            return_value=MagicMock(is_valid=True, error_message=None)
        )
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        result = await wf.run({"agent_id": "agent-1"})

        assert result["status"] == "success"
        assert "transaction_id" in result
        assert result["constitutional_hash"] is not None
        assert result["result"] is not None

    async def test_run_maci_authorization_failure(self):
        enforcer = MagicMock()
        enforcer.validate_action = AsyncMock(
            return_value=MagicMock(is_valid=False, error_message="not allowed")
        )
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        result = await wf.run({"agent_id": "bad-agent"})

        assert result["status"] == "failed"
        assert "MACI Authorization failed" in result["error"]
        assert "transaction_id" in result

    async def test_run_with_missing_agent_id(self):
        enforcer = MagicMock()
        enforcer.validate_action = AsyncMock(
            return_value=MagicMock(is_valid=True, error_message=None)
        )
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        result = await wf.run({})

        assert result["status"] == "success"

    async def test_maci_authorize_step_directly(self):
        enforcer = MagicMock()
        enforcer.validate_action = AsyncMock(
            return_value=MagicMock(is_valid=True, error_message=None)
        )
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        result = await wf._maci_authorize_step(input_data={"agent_id": "a1"})
        assert result["authorized"] is True
        assert result["agent_id"] == "a1"

    async def test_maci_authorize_step_no_agent_id(self):
        enforcer = MagicMock()
        enforcer.validate_action = AsyncMock(
            return_value=MagicMock(is_valid=True, error_message=None)
        )
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        result = await wf._maci_authorize_step(input_data={})
        assert result["agent_id"] == "unknown"

    async def test_maci_authorize_step_raises_on_invalid(self):
        enforcer = MagicMock()
        enforcer.validate_action = AsyncMock(
            return_value=MagicMock(is_valid=False, error_message="denied")
        )
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        with pytest.raises(PermissionError, match="MACI Authorization failed"):
            await wf._maci_authorize_step(input_data={"agent_id": "x"})

    async def test_maci_rollback_step(self):
        wf = HighPerformanceGovernanceWorkflow()
        # Should not raise
        await wf._maci_rollback_step({"agent_id": "a1"})

    async def test_validate_step(self):
        wf = HighPerformanceGovernanceWorkflow()
        result = await wf._validate_step()
        assert result == {"validated": True}

    async def test_execute_step(self):
        wf = HighPerformanceGovernanceWorkflow()
        result = await wf._execute_step()
        assert result == {"executed": True}

    async def test_rollback_execution_step(self):
        wf = HighPerformanceGovernanceWorkflow()
        # Should not raise
        await wf._rollback_execution_step(None)

    async def test_run_handles_runtime_error(self):
        """Saga execute raising RuntimeError should produce failed status."""
        enforcer = MagicMock()
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        with patch(
            "enhanced_agent_bus.workflows.hp_governance_workflow.SagaTransaction"
        ) as mock_saga_cls:
            saga_instance = MagicMock()
            saga_instance.execute = AsyncMock(side_effect=RuntimeError("boom"))
            saga_instance.transaction_id = "txn-123"
            mock_saga_cls.return_value = saga_instance

            result = await wf.run({"agent_id": "a1"})

        assert result["status"] == "failed"
        assert "boom" in result["error"]

    async def test_run_handles_timeout_error(self):
        enforcer = MagicMock()
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        with patch(
            "enhanced_agent_bus.workflows.hp_governance_workflow.SagaTransaction"
        ) as mock_saga_cls:
            saga_instance = MagicMock()
            saga_instance.execute = AsyncMock(side_effect=TimeoutError("timed out"))
            saga_instance.transaction_id = "txn-456"
            mock_saga_cls.return_value = saga_instance

            result = await wf.run({})

        assert result["status"] == "failed"

    async def test_run_handles_value_error(self):
        enforcer = MagicMock()
        wf = HighPerformanceGovernanceWorkflow(enforcer=enforcer)

        with patch(
            "enhanced_agent_bus.workflows.hp_governance_workflow.SagaTransaction"
        ) as mock_saga_cls:
            saga_instance = MagicMock()
            saga_instance.execute = AsyncMock(side_effect=ValueError("bad value"))
            saga_instance.transaction_id = "txn-789"
            mock_saga_cls.return_value = saga_instance

            result = await wf.run({})

        assert result["status"] == "failed"
        assert "bad value" in result["error"]


# ---------------------------------------------------------------------------
# 2. MCPResourceRegistry
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp_integration.resource_registry import MCPResourceRegistry


def _make_resource(uri: str = "test://r1") -> MagicMock:
    r = MagicMock()
    r.uri = uri
    r.to_mcp_definition.return_value = {"uri": uri, "name": "test"}
    return r


def _make_metrics() -> MagicMock:
    m = MagicMock()
    m.resources_registered = 0
    m.to_dict.return_value = {"resources_registered": 0}
    return m


def _make_registry(
    resources: dict | None = None,
    audit_log: list | None = None,
) -> MCPResourceRegistry:
    return MCPResourceRegistry(
        resources=resources if resources is not None else {},
        metrics=_make_metrics(),
        audit_log=audit_log if audit_log is not None else [],
        constitutional_hash="608508a9bd224290",
        resource_factory=MagicMock(side_effect=lambda **kw: _make_resource(kw.get("uri", "x"))),
        logger_instance=logging.getLogger("test"),
    )


class TestMCPResourceRegistry:
    """Tests for MCPResourceRegistry (44 missing lines, 0%)."""

    def test_register_resource(self):
        reg = _make_registry()
        r = _make_resource("test://a")
        assert reg.register_resource(r) is True
        assert "test://a" in reg._resources

    def test_register_resource_updates_metrics(self):
        metrics = _make_metrics()
        reg = MCPResourceRegistry(
            resources={},
            metrics=metrics,
            audit_log=[],
            constitutional_hash="608508a9bd224290",
            resource_factory=MagicMock(),
            logger_instance=logging.getLogger("test"),
        )
        reg.register_resource(_make_resource("test://b"))
        assert metrics.resources_registered == 1

    def test_register_duplicate_resource_warns(self):
        reg = _make_registry()
        r1 = _make_resource("test://dup")
        r2 = _make_resource("test://dup")
        reg.register_resource(r1)
        # Second registration should still succeed (update)
        assert reg.register_resource(r2) is True

    def test_unregister_resource_exists(self):
        reg = _make_registry()
        reg.register_resource(_make_resource("test://rm"))
        assert reg.unregister_resource("test://rm") is True
        assert "test://rm" not in reg._resources

    def test_unregister_resource_not_found(self):
        reg = _make_registry()
        assert reg.unregister_resource("test://missing") is False

    def test_unregister_updates_metrics(self):
        metrics = _make_metrics()
        reg = MCPResourceRegistry(
            resources={},
            metrics=metrics,
            audit_log=[],
            constitutional_hash="608508a9bd224290",
            resource_factory=MagicMock(),
            logger_instance=logging.getLogger("test"),
        )
        reg.register_resource(_make_resource("test://c"))
        reg.unregister_resource("test://c")
        assert metrics.resources_registered == 0

    def test_initialize_builtin_resources(self):
        factory = MagicMock(side_effect=lambda **kw: _make_resource(kw.get("uri", "x")))
        reg = MCPResourceRegistry(
            resources={},
            metrics=_make_metrics(),
            audit_log=[],
            constitutional_hash="608508a9bd224290",
            resource_factory=factory,
            logger_instance=logging.getLogger("test"),
        )
        reg._initialize_builtin_resources()

        assert factory.call_count == 3
        call_uris = [c.kwargs["uri"] for c in factory.call_args_list]
        assert "acgs2://constitutional/principles" in call_uris
        assert "acgs2://governance/metrics" in call_uris
        assert "acgs2://governance/audit" in call_uris

    async def test_resource_principles(self):
        reg = _make_registry()
        result = await reg._resource_principles({})
        assert "principles" in result
        assert result["constitutional_hash"] == "608508a9bd224290"
        assert "timestamp" in result
        assert "beneficence" in result["principles"]

    async def test_resource_metrics(self):
        metrics = _make_metrics()
        metrics.to_dict.return_value = {"total": 42}
        reg = MCPResourceRegistry(
            resources={},
            metrics=metrics,
            audit_log=[],
            constitutional_hash="608508a9bd224290",
            resource_factory=MagicMock(),
            logger_instance=logging.getLogger("test"),
        )
        result = await reg._resource_metrics({})
        assert result == {"total": 42}

    async def test_resource_audit(self):
        audit_log = [{"event": "test", "i": i} for i in range(5)]
        reg = _make_registry(audit_log=audit_log)
        result = await reg._resource_audit({})
        assert result["total_entries"] == 5
        assert len(result["entries"]) == 5
        assert result["constitutional_hash"] == "608508a9bd224290"

    async def test_resource_audit_caps_at_100(self):
        audit_log = [{"i": i} for i in range(150)]
        reg = _make_registry(audit_log=audit_log)
        result = await reg._resource_audit({})
        assert len(result["entries"]) == 100
        assert result["total_entries"] == 150

    def test_get_resources(self):
        reg = _make_registry()
        r1 = _make_resource("test://1")
        r2 = _make_resource("test://2")
        reg.register_resource(r1)
        reg.register_resource(r2)
        resources = reg.get_resources()
        assert len(resources) == 2
        assert all(isinstance(r, dict) for r in resources)


# ---------------------------------------------------------------------------
# 3. Constitutional Invariants
# ---------------------------------------------------------------------------
from enhanced_agent_bus.constitutional.invariants import (
    ChangeClassification,
    EnforcementMode,
    InvariantCheckResult,
    InvariantDefinition,
    InvariantManifest,
    InvariantScope,
    check_append_only_audit,
    check_constitutional_hash_required,
    check_fail_closed,
    check_human_approval_for_activation,
    check_maci_separation,
    check_tenant_isolation,
    get_default_manifest,
)


class TestInvariantEnums:
    def test_invariant_scope_values(self):
        assert InvariantScope.HARD == "hard"
        assert InvariantScope.META == "meta"
        assert InvariantScope.SOFT == "soft"

    def test_enforcement_mode_values(self):
        assert EnforcementMode.PRE_PROPOSAL == "pre_proposal"
        assert EnforcementMode.PRE_ACTIVATION == "pre_activation"
        assert EnforcementMode.RUNTIME == "runtime"


class TestInvariantCheckResult:
    def test_passed_result(self):
        r = InvariantCheckResult(passed=True, invariant_id="INV-001", message="ok")
        assert r.passed is True

    def test_failed_result_with_message(self):
        r = InvariantCheckResult(passed=False, invariant_id="INV-002", message="bad")
        assert r.passed is False
        assert r.message == "bad"

    def test_default_message(self):
        r = InvariantCheckResult(passed=True, invariant_id="X")
        assert r.message == ""


class TestInvariantDefinition:
    def test_create_definition(self):
        d = InvariantDefinition(
            invariant_id="INV-TEST",
            name="Test",
            scope=InvariantScope.SOFT,
        )
        assert d.invariant_id == "INV-TEST"
        assert d.protected_paths == []
        assert d.enforcement_modes == []
        assert d.predicate_module == ""


class TestChangeClassification:
    def test_defaults(self):
        c = ChangeClassification(touches_invariants=False, blocked=False)
        assert c.touched_invariant_ids == []
        assert c.requires_refoundation is False
        assert c.reason is None

    def test_blocked_with_reason(self):
        c = ChangeClassification(
            touches_invariants=True,
            blocked=True,
            touched_invariant_ids=["INV-001"],
            requires_refoundation=True,
            reason="Needs refoundation",
        )
        assert c.blocked is True
        assert c.requires_refoundation is True


class TestInvariantManifest:
    def test_empty_manifest_computes_hash(self):
        m = InvariantManifest(constitutional_hash="608508a9bd224290")
        assert m.invariant_hash != ""
        assert len(m.invariant_hash) == 16

    def test_manifest_with_invariants_computes_hash(self):
        inv = InvariantDefinition(
            invariant_id="INV-T1",
            name="Test",
            scope=InvariantScope.HARD,
        )
        m = InvariantManifest(constitutional_hash="608508a9bd224290", invariants=[inv])
        assert m.invariant_hash != ""

    def test_manifest_hash_mismatch_raises(self):
        with pytest.raises(ValueError, match="Invariant hash mismatch"):
            InvariantManifest(
                constitutional_hash="608508a9bd224290",
                invariant_hash="0000000000000000",
            )

    def test_manifest_correct_hash_accepted(self):
        m1 = InvariantManifest(constitutional_hash="608508a9bd224290")
        h = m1.invariant_hash
        m2 = InvariantManifest(
            constitutional_hash="608508a9bd224290",
            invariant_hash=h,
        )
        assert m2.invariant_hash == h

    def test_manifest_deterministic_hash(self):
        inv = InvariantDefinition(
            invariant_id="INV-A",
            name="A",
            scope=InvariantScope.HARD,
        )
        m1 = InvariantManifest(constitutional_hash="608508a9bd224290", invariants=[inv])
        m2 = InvariantManifest(constitutional_hash="608508a9bd224290", invariants=[inv])
        assert m1.invariant_hash == m2.invariant_hash

    def test_manifest_hash_changes_with_invariants(self):
        m_empty = InvariantManifest(constitutional_hash="608508a9bd224290")
        inv = InvariantDefinition(
            invariant_id="INV-B",
            name="B",
            scope=InvariantScope.SOFT,
        )
        m_with = InvariantManifest(constitutional_hash="608508a9bd224290", invariants=[inv])
        assert m_empty.invariant_hash != m_with.invariant_hash


class TestCheckMACISeparation:
    def test_all_distinct_passes(self):
        r = check_maci_separation({}, {"proposer_id": "a", "validator_id": "b", "executor_id": "c"})
        assert r.passed is True
        assert r.invariant_id == "INV-001"

    def test_missing_roles_fails(self):
        r = check_maci_separation({}, {"proposer_id": "a"})
        assert r.passed is False
        assert "all three roles" in r.message

    def test_duplicate_roles_fails(self):
        r = check_maci_separation({}, {"proposer_id": "a", "validator_id": "a", "executor_id": "b"})
        assert r.passed is False
        assert "distinct agents" in r.message

    def test_all_same_fails(self):
        r = check_maci_separation({}, {"proposer_id": "x", "validator_id": "x", "executor_id": "x"})
        assert r.passed is False

    def test_empty_roles_fails(self):
        r = check_maci_separation({}, {"proposer_id": "", "validator_id": "", "executor_id": ""})
        assert r.passed is False

    def test_two_roles_missing_fails(self):
        r = check_maci_separation({}, {"proposer_id": "a", "validator_id": "", "executor_id": ""})
        assert r.passed is False


class TestCheckFailClosed:
    def test_no_error_action_passes(self):
        r = check_fail_closed({}, {})
        assert r.passed is True

    def test_deny_passes(self):
        r = check_fail_closed({}, {"on_error": "deny"})
        assert r.passed is True

    def test_allow_on_error_fails(self):
        r = check_fail_closed({}, {"on_error": "allow"})
        assert r.passed is False
        assert "on_error" in r.message

    def test_governance_bypass_fails(self):
        r = check_fail_closed({}, {"governance_bypass": True})
        assert r.passed is False
        assert "governance_bypass" in r.message

    def test_governance_bypass_false_passes(self):
        r = check_fail_closed({}, {"governance_bypass": False})
        assert r.passed is True

    def test_both_violations(self):
        r = check_fail_closed({}, {"on_error": "allow", "governance_bypass": True})
        # First check (on_error) should fail first
        assert r.passed is False


class TestCheckAppendOnlyAudit:
    def test_no_audit_op_passes(self):
        r = check_append_only_audit({}, {})
        assert r.passed is True

    def test_insert_passes(self):
        r = check_append_only_audit({}, {"audit_operation": "insert"})
        assert r.passed is True

    def test_delete_fails(self):
        r = check_append_only_audit({}, {"audit_operation": "delete"})
        assert r.passed is False

    def test_update_fails(self):
        r = check_append_only_audit({}, {"audit_operation": "update"})
        assert r.passed is False

    def test_truncate_fails(self):
        r = check_append_only_audit({}, {"audit_operation": "truncate"})
        assert r.passed is False

    def test_drop_fails(self):
        r = check_append_only_audit({}, {"audit_operation": "drop"})
        assert r.passed is False


class TestCheckConstitutionalHashRequired:
    def test_matching_hash_passes(self):
        r = check_constitutional_hash_required(
            {"constitutional_hash": "608508a9bd224290"},
            {"constitutional_hash": "608508a9bd224290"},
        )
        assert r.passed is True

    def test_missing_hash_fails(self):
        r = check_constitutional_hash_required(
            {"constitutional_hash": "608508a9bd224290"},
            {},
        )
        assert r.passed is False
        assert "missing" in r.message.lower()

    def test_mismatched_hash_fails(self):
        r = check_constitutional_hash_required(
            {"constitutional_hash": "608508a9bd224290"},
            {"constitutional_hash": "0000000000000000"},
        )
        assert r.passed is False
        assert "mismatch" in r.message.lower()

    def test_no_expected_hash_passes(self):
        # State has no hash, so any provided hash is accepted
        r = check_constitutional_hash_required(
            {},
            {"constitutional_hash": "anything"},
        )
        assert r.passed is True

    def test_empty_provided_hash_fails(self):
        r = check_constitutional_hash_required(
            {"constitutional_hash": "608508a9bd224290"},
            {"constitutional_hash": ""},
        )
        assert r.passed is False


class TestCheckTenantIsolation:
    def test_same_tenant_passes(self):
        r = check_tenant_isolation({}, {"source_tenant_id": "t1", "target_tenant_id": "t1"})
        assert r.passed is True

    def test_cross_tenant_fails(self):
        r = check_tenant_isolation({}, {"source_tenant_id": "t1", "target_tenant_id": "t2"})
        assert r.passed is False
        assert "cannot cross" in r.message

    def test_no_tenants_passes(self):
        r = check_tenant_isolation({}, {})
        assert r.passed is True

    def test_only_source_passes(self):
        r = check_tenant_isolation({}, {"source_tenant_id": "t1"})
        assert r.passed is True

    def test_only_target_passes(self):
        r = check_tenant_isolation({}, {"target_tenant_id": "t2"})
        assert r.passed is True


class TestCheckHumanApprovalForActivation:
    def test_not_activation_passes(self):
        r = check_human_approval_for_activation({}, {})
        assert r.passed is True

    def test_activation_with_approval_passes(self):
        r = check_human_approval_for_activation({}, {"is_activation": True, "human_approved": True})
        assert r.passed is True

    def test_activation_without_approval_fails(self):
        r = check_human_approval_for_activation(
            {}, {"is_activation": True, "human_approved": False}
        )
        assert r.passed is False
        assert "Human approval required" in r.message

    def test_activation_missing_approval_fails(self):
        r = check_human_approval_for_activation({}, {"is_activation": True})
        assert r.passed is False

    def test_not_activation_ignored(self):
        r = check_human_approval_for_activation(
            {}, {"is_activation": False, "human_approved": False}
        )
        assert r.passed is True


class TestGetDefaultManifest:
    def test_returns_manifest(self):
        m = get_default_manifest()
        assert isinstance(m, InvariantManifest)
        assert m.constitutional_hash == "608508a9bd224290"

    def test_has_six_invariants(self):
        m = get_default_manifest()
        assert len(m.invariants) == 6

    def test_invariant_ids_sequential(self):
        m = get_default_manifest()
        ids = sorted(inv.invariant_id for inv in m.invariants)
        expected = [f"INV-00{i}" for i in range(1, 7)]
        assert ids == expected

    def test_hash_is_computed(self):
        m = get_default_manifest()
        assert m.invariant_hash != ""
        assert len(m.invariant_hash) == 16

    def test_all_hard_or_meta_scope(self):
        m = get_default_manifest()
        for inv in m.invariants:
            assert inv.scope in (InvariantScope.HARD, InvariantScope.META)


# ---------------------------------------------------------------------------
# 4. MCPServer
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp_server.config import MCPConfig, TransportType
from enhanced_agent_bus.mcp_server.protocol.types import (
    MCPError,
    MCPRequest,
    MCPResponse,
)
from enhanced_agent_bus.mcp_server.server import MCPServer, create_mcp_server


class TestMCPServerInit:
    def test_default_creation(self):
        server = MCPServer()
        assert server._running is False
        assert server._request_count == 0
        assert server._error_count == 0
        assert server._handler is not None
        assert server._shutdown_event is not None

    def test_creation_with_config(self):
        config = MCPConfig(server_name="test-srv", server_version="1.2.3")
        server = MCPServer(config=config)
        assert server.config.server_name == "test-srv"
        assert server.config.server_version == "1.2.3"

    def test_adapters_initialized(self):
        server = MCPServer()
        assert "agent_bus" in server._adapters
        assert "policy_client" in server._adapters
        assert "audit_client" in server._adapters

    def test_tools_initialized(self):
        server = MCPServer()
        assert "validate_constitutional_compliance" in server._tools
        assert "get_active_principles" in server._tools
        assert "query_governance_precedents" in server._tools
        assert "submit_governance_request" in server._tools
        assert "get_governance_metrics" in server._tools

    def test_resources_initialized(self):
        server = MCPServer()
        assert "principles" in server._resources
        assert "metrics" in server._resources
        assert "decisions" in server._resources
        assert "audit_trail" in server._resources


class TestMCPServerCapabilities:
    def test_get_capabilities(self):
        server = MCPServer()
        caps = server.get_capabilities()
        assert caps.tools == {"listChanged": True}
        assert caps.resources == {"subscribe": False, "listChanged": True}

    def test_get_tool_definitions(self):
        server = MCPServer()
        defs = server.get_tool_definitions()
        assert len(defs) == 5

    def test_get_resource_definitions(self):
        server = MCPServer()
        defs = server.get_resource_definitions()
        assert len(defs) == 4


class TestMCPServerMetrics:
    def test_get_metrics_structure(self):
        server = MCPServer()
        metrics = server.get_metrics()
        assert "server" in metrics
        assert metrics["server"]["running"] is False
        assert metrics["server"]["request_count"] == 0
        assert metrics["server"]["error_count"] == 0
        assert "tools" in metrics
        assert "resources" in metrics
        assert "adapters" in metrics

    def test_get_metrics_tool_metrics(self):
        server = MCPServer()
        # Add a tool with get_metrics
        mock_tool = MagicMock()
        mock_tool.get_metrics.return_value = {"calls": 5}
        mock_tool.get_definition.return_value = MagicMock()
        server._tools["custom_tool"] = mock_tool

        metrics = server.get_metrics()
        assert "custom_tool" in metrics["tools"]
        assert metrics["tools"]["custom_tool"] == {"calls": 5}


class TestMCPServerHandleRequest:
    async def test_handle_request_success(self):
        server = MCPServer()
        server._handler = MagicMock()
        expected_resp = MCPResponse(jsonrpc="2.0", id="1", result={"ok": True})
        server._handler.handle_request = AsyncMock(return_value=expected_resp)

        request = MCPRequest(jsonrpc="2.0", method="test", id="1")
        response = await server.handle_request(request)

        assert response is not None
        assert response.result == {"ok": True}
        assert server._request_count == 1

    async def test_handle_request_error(self):
        server = MCPServer()
        server._handler = MagicMock()
        server._handler.handle_request = AsyncMock(side_effect=RuntimeError("handler failed"))

        request = MCPRequest(jsonrpc="2.0", method="test", id="2")
        response = await server.handle_request(request)

        assert response is not None
        assert response.error is not None
        assert response.error.code == -32603
        assert server._error_count == 1

    async def test_handle_request_value_error(self):
        server = MCPServer()
        server._handler = MagicMock()
        server._handler.handle_request = AsyncMock(side_effect=ValueError("bad input"))

        request = MCPRequest(jsonrpc="2.0", method="test", id="3")
        response = await server.handle_request(request)

        assert response.error is not None
        assert "bad input" in response.error.data["detail"]

    async def test_handle_request_increments_count(self):
        server = MCPServer()
        server._handler = MagicMock()
        server._handler.handle_request = AsyncMock(
            return_value=MCPResponse(jsonrpc="2.0", id="x", result={})
        )

        req = MCPRequest(jsonrpc="2.0", method="m", id="x")
        await server.handle_request(req)
        await server.handle_request(req)
        assert server._request_count == 2


class TestMCPServerStartStop:
    async def test_start_already_running(self):
        server = MCPServer()
        server._running = True
        # Should return early without error
        await server.start()

    async def test_stop_not_running(self):
        server = MCPServer()
        server._running = False
        # Should return early without error
        await server.stop()

    async def test_stop_running_server(self):
        server = MCPServer()
        server._running = True
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].disconnect = AsyncMock()
        server._resources["audit_trail"] = MagicMock()

        await server.stop()

        assert server._running is False
        assert server._shutdown_event.is_set()

    async def test_connect_adapters(self):
        server = MCPServer()
        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock(return_value=True)
        server._adapters["agent_bus"] = mock_adapter

        result = await server.connect_adapters()
        assert result is True
        mock_adapter.connect.assert_awaited_once()

    async def test_connect_adapters_standalone(self):
        server = MCPServer()
        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock(return_value=False)
        server._adapters["agent_bus"] = mock_adapter

        # Still returns True (standalone mode)
        result = await server.connect_adapters()
        assert result is True

    async def test_disconnect_adapters(self):
        server = MCPServer()
        mock_adapter = MagicMock()
        mock_adapter.disconnect = AsyncMock()
        server._adapters["agent_bus"] = mock_adapter

        await server.disconnect_adapters()
        mock_adapter.disconnect.assert_awaited_once()

    async def test_start_unknown_transport_raises(self):
        config = MCPConfig()
        server = MCPServer(config=config)
        server._running = False
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].connect = AsyncMock(return_value=True)
        # Bypass the enum validation by setting after init
        server.config.transport_type = "invalid"

        with pytest.raises((ValueError, AttributeError)):
            await server.start()


class TestCreateMCPServer:
    def test_create_with_defaults(self):
        server = create_mcp_server()
        assert isinstance(server, MCPServer)

    def test_create_with_config(self):
        config = MCPConfig(server_name="custom")
        server = create_mcp_server(config=config)
        assert server.config.server_name == "custom"

    def test_create_with_agent_bus(self):
        bus = MagicMock()
        server = create_mcp_server(agent_bus=bus)
        assert server._adapters["agent_bus"].agent_bus is bus

    def test_create_with_policy_client(self):
        pc = MagicMock()
        server = create_mcp_server(policy_client=pc)
        assert server._adapters["policy_client"].policy_client is pc

    def test_create_with_audit_client(self):
        ac = MagicMock()
        server = create_mcp_server(audit_client=ac)
        assert server._adapters["audit_client"].audit_client is ac

    def test_create_with_all_services(self):
        server = create_mcp_server(
            agent_bus=MagicMock(),
            policy_client=MagicMock(),
            audit_client=MagicMock(),
        )
        assert isinstance(server, MCPServer)


class TestMCPServerSSETransport:
    async def test_sse_transport_falls_back(self):
        """SSE transport should fall back to STDIO (placeholder behavior)."""
        server = MCPServer()
        server._running = False
        server._shutdown_event.set()  # Immediately stop

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock) as mock_stdio:
            await server._run_sse_transport()
            mock_stdio.assert_awaited_once()
