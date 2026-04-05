# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for WorkflowCoordinator.

Targets ≥95% line coverage of coordinators/workflow_coordinator.py (76 stmts).
All external dependencies (langgraph, workflow_evolution) are mocked via sys.modules.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Helpers — build fake modules
# ---------------------------------------------------------------------------


def _make_fake_langgraph_module(
    *,
    raise_create: Exception | None = None,
    engine: object | None = None,
) -> ModuleType:
    """Return a fake langgraph_orchestrator module."""
    mod = ModuleType("enhanced_agent_bus.langgraph_orchestrator")
    if raise_create is not None:
        mod.create_governance_workflow = MagicMock(side_effect=raise_create)
    else:
        mock_engine = engine if engine is not None else MagicMock()
        mod.create_governance_workflow = MagicMock(return_value=mock_engine)
    return mod


def _make_fake_evolution_module(
    *,
    raise_create: Exception | None = None,
    engine: object | None = None,
) -> ModuleType:
    """Return a fake workflow_evolution module with OptimizationType."""
    mod = ModuleType("enhanced_agent_bus.workflow_evolution")
    if raise_create is not None:
        mod.create_workflow_engine = MagicMock(side_effect=raise_create)
    else:
        mock_engine = engine if engine is not None else MagicMock()
        mod.create_workflow_engine = MagicMock(return_value=mock_engine)
    # OptimizationType enum-alike
    opt_type = MagicMock()
    opt_type.LATENCY = "LATENCY"
    mod.OptimizationType = opt_type
    return mod


def _import_coordinator():
    """Import WorkflowCoordinator fresh (no reimport caching issue)."""
    from enhanced_agent_bus.coordinators.workflow_coordinator import (
        WorkflowCoordinator,
    )

    return WorkflowCoordinator


def _build_coordinator(
    *,
    enable_evolution: bool = True,
    saga_enabled: bool = True,
    langgraph_raises: Exception | None = ImportError("no langgraph"),
    evolution_raises: Exception | None = ImportError("no evolution"),
    workflow_engine: object | None = None,
    evolution_engine: object | None = None,
) -> object:
    """
    Build a WorkflowCoordinator with controlled module availability.

    Pass langgraph_raises=None to provide a real (mock) engine via workflow_engine.
    Pass evolution_raises=None to provide a real (mock) engine via evolution_engine.
    """
    lg_mod = _make_fake_langgraph_module(
        raise_create=langgraph_raises,
        engine=workflow_engine,
    )
    evo_mod = _make_fake_evolution_module(
        raise_create=evolution_raises,
        engine=evolution_engine,
    )

    lg_key = "enhanced_agent_bus.langgraph_orchestrator"
    evo_key = "enhanced_agent_bus.workflow_evolution"

    overrides = {lg_key: lg_mod, evo_key: evo_mod}
    with patch.dict(sys.modules, overrides):
        WorkflowCoordinator = _import_coordinator()
        coord = WorkflowCoordinator(enable_evolution=enable_evolution, saga_enabled=saga_enabled)
    return coord


def _build_engine() -> MagicMock:
    """Return a workflow engine mock with an AsyncMock execute."""
    engine = MagicMock()
    engine.execute = AsyncMock(return_value={"status": "ok"})
    return engine


def _build_evo_engine() -> MagicMock:
    """Return an evolution engine mock with a real proposal."""
    engine = MagicMock()
    proposal = MagicMock()
    proposal.id = "proposal-abc"
    proposal.changes = ["step-1"]
    proposal.risk_level = "low"
    engine.propose_evolution = AsyncMock(return_value=proposal)
    return engine


# ---------------------------------------------------------------------------
# Tests: __init__ / _initialize_engines
# ---------------------------------------------------------------------------


class TestInit:
    def test_defaults_with_both_engines_unavailable(self):
        coord = _build_coordinator()
        assert coord._enable_evolution is True
        assert coord._saga_enabled is True
        assert coord._workflow_engine is None
        assert coord._evolution_engine is None
        assert coord._initialized is False
        assert coord._active_workflows == {}

    def test_constitutional_hash_class_attribute(self):
        coord = _build_coordinator()
        assert coord.constitutional_hash == CONSTITUTIONAL_HASH

    def test_workflow_engine_initialized_when_langgraph_available(self):
        engine = _build_engine()
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine)
        assert coord._workflow_engine is engine
        assert coord._initialized is True

    def test_evolution_engine_initialized_when_available(self):
        evo_engine = _build_evo_engine()
        coord = _build_coordinator(
            evolution_raises=None,
            evolution_engine=evo_engine,
        )
        assert coord._evolution_engine is evo_engine

    def test_enable_evolution_false_skips_evolution_init(self):
        coord = _build_coordinator(enable_evolution=False, evolution_raises=None)
        assert coord._evolution_engine is None

    def test_saga_disabled_stored(self):
        coord = _build_coordinator(saga_enabled=False)
        assert coord._saga_enabled is False

    def test_langgraph_runtime_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=RuntimeError("crash"))
        assert coord._workflow_engine is None
        assert coord._initialized is False

    def test_langgraph_value_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=ValueError("bad"))
        assert coord._workflow_engine is None

    def test_langgraph_type_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=TypeError("type"))
        assert coord._workflow_engine is None

    def test_langgraph_attribute_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=AttributeError("attr"))
        assert coord._workflow_engine is None

    def test_langgraph_lookup_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=LookupError("lookup"))
        assert coord._workflow_engine is None

    def test_langgraph_os_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=OSError("os"))
        assert coord._workflow_engine is None

    def test_langgraph_timeout_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=TimeoutError("timeout"))
        assert coord._workflow_engine is None

    def test_langgraph_connection_error_swallowed(self):
        coord = _build_coordinator(langgraph_raises=ConnectionError("conn"))
        assert coord._workflow_engine is None

    def test_evolution_runtime_error_swallowed(self):
        coord = _build_coordinator(evolution_raises=RuntimeError("evo crash"))
        assert coord._evolution_engine is None

    def test_evolution_value_error_swallowed(self):
        coord = _build_coordinator(evolution_raises=ValueError("bad evo"))
        assert coord._evolution_engine is None

    def test_evolution_os_error_swallowed(self):
        coord = _build_coordinator(evolution_raises=OSError("disk"))
        assert coord._evolution_engine is None

    def test_evolution_type_error_swallowed(self):
        coord = _build_coordinator(evolution_raises=TypeError("type evo"))
        assert coord._evolution_engine is None

    def test_both_engines_available(self):
        eng = _build_engine()
        evo = _build_evo_engine()
        coord = _build_coordinator(
            langgraph_raises=None,
            workflow_engine=eng,
            evolution_raises=None,
            evolution_engine=evo,
        )
        assert coord._workflow_engine is eng
        assert coord._evolution_engine is evo
        assert coord._initialized is True


# ---------------------------------------------------------------------------
# Tests: Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_is_langgraph_available_false(self):
        coord = _build_coordinator()
        assert coord.is_langgraph_available is False

    def test_is_langgraph_available_true(self):
        eng = _build_engine()
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=eng)
        assert coord.is_langgraph_available is True

    def test_is_evolution_available_false(self):
        coord = _build_coordinator()
        assert coord.is_evolution_available is False

    def test_is_evolution_available_true(self):
        evo = _build_evo_engine()
        coord = _build_coordinator(evolution_raises=None, evolution_engine=evo)
        assert coord.is_evolution_available is True


# ---------------------------------------------------------------------------
# Tests: execute_workflow — basic path (no engine)
# ---------------------------------------------------------------------------


class TestExecuteWorkflowBasicPath:
    async def test_returns_completed_state(self):
        coord = _build_coordinator()
        result = await coord.execute_workflow("wf-1", {"data": "hello"})
        assert result["state"] == "completed"
        assert result["workflow_id"] == "wf-1"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "execution_id" in result
        assert "result" in result

    async def test_basic_result_structure(self):
        coord = _build_coordinator()
        payload = {"key": "value"}
        result = await coord.execute_workflow("wf-basic", payload)
        inner = result["result"]
        assert inner["output"] == payload
        assert inner["workflow_id"] == "wf-basic"
        assert inner["steps_completed"] == 1

    async def test_execution_ids_are_unique(self):
        coord = _build_coordinator()
        r1 = await coord.execute_workflow("wf-A", {})
        r2 = await coord.execute_workflow("wf-B", {})
        assert r1["execution_id"] != r2["execution_id"]

    async def test_active_workflows_updated(self):
        coord = _build_coordinator()
        await coord.execute_workflow("wf-track", {"x": 1})
        assert len(coord._active_workflows) == 1

    async def test_active_workflow_state_completed(self):
        coord = _build_coordinator()
        await coord.execute_workflow("wf-state", {})
        wf = next(iter(coord._active_workflows.values()))
        assert wf["state"] == "completed"

    async def test_custom_timeout_accepted(self):
        coord = _build_coordinator()
        result = await coord.execute_workflow("wf-timeout", {}, timeout_seconds=60)
        assert result["state"] == "completed"

    async def test_empty_input_data(self):
        coord = _build_coordinator()
        result = await coord.execute_workflow("wf-empty", {})
        assert result["state"] == "completed"

    async def test_execution_id_includes_workflow_id(self):
        coord = _build_coordinator()
        result = await coord.execute_workflow("my-workflow", {})
        assert "my-workflow" in result["execution_id"]


# ---------------------------------------------------------------------------
# Tests: execute_workflow — langgraph engine path
# ---------------------------------------------------------------------------


class TestExecuteWorkflowWithEngine:
    async def test_uses_engine_when_available(self):
        engine = _build_engine()
        engine_result = {"status": "approved", "score": 0.9}
        engine.execute = AsyncMock(return_value=engine_result)
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine)

        result = await coord.execute_workflow("wf-engine", {"msg": "hello"})

        assert result["state"] == "completed"
        assert result["result"] == engine_result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        engine.execute.assert_awaited_once()

    async def test_engine_called_with_correct_kwargs(self):
        engine = _build_engine()
        engine.execute = AsyncMock(return_value={})
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine)

        await coord.execute_workflow("wf-args", {"key": "val"}, timeout_seconds=120)

        call_kwargs = engine.execute.call_args.kwargs
        assert call_kwargs["workflow_id"] == "wf-args"
        assert call_kwargs["input_data"] == {"key": "val"}
        assert call_kwargs["timeout"] == 120

    async def test_active_workflow_state_completed_after_engine_success(self):
        engine = _build_engine()
        engine.execute = AsyncMock(return_value={})
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine)

        await coord.execute_workflow("wf-complete", {})
        wf = next(iter(coord._active_workflows.values()))
        assert wf["state"] == "completed"

    async def test_result_field_contains_engine_return(self):
        engine = _build_engine()
        engine_result = {"foo": "bar", "baz": 42}
        engine.execute = AsyncMock(return_value=engine_result)
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine)

        result = await coord.execute_workflow("wf-result", {})
        assert result["result"] == engine_result


# ---------------------------------------------------------------------------
# Tests: execute_workflow — error handling
# ---------------------------------------------------------------------------


class TestExecuteWorkflowErrors:
    async def _run_with_engine_error(self, exc: Exception, saga: bool = True):
        engine = _build_engine()
        engine.execute = AsyncMock(side_effect=exc)
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine, saga_enabled=saga)
        return await coord.execute_workflow("wf-err", {})

    async def test_runtime_error_returns_failed(self):
        result = await self._run_with_engine_error(RuntimeError("crash"))
        assert result["state"] == "failed"
        assert "crash" in result["error"]

    async def test_value_error_returns_failed(self):
        result = await self._run_with_engine_error(ValueError("bad"))
        assert result["state"] == "failed"

    async def test_type_error_returns_failed(self):
        result = await self._run_with_engine_error(TypeError("type"))
        assert result["state"] == "failed"

    async def test_timeout_error_returns_failed(self):
        result = await self._run_with_engine_error(TimeoutError("timeout"))
        assert result["state"] == "failed"

    async def test_connection_error_returns_failed(self):
        result = await self._run_with_engine_error(ConnectionError("conn"))
        assert result["state"] == "failed"

    async def test_os_error_returns_failed(self):
        result = await self._run_with_engine_error(OSError("os"))
        assert result["state"] == "failed"

    async def test_attribute_error_returns_failed(self):
        result = await self._run_with_engine_error(AttributeError("attr"))
        assert result["state"] == "failed"

    async def test_lookup_error_returns_failed(self):
        result = await self._run_with_engine_error(LookupError("lookup"))
        assert result["state"] == "failed"

    async def test_failed_result_contains_constitutional_hash(self):
        result = await self._run_with_engine_error(RuntimeError("hash"))
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_rolled_back_true_when_saga_enabled(self):
        result = await self._run_with_engine_error(RuntimeError("saga"), saga=True)
        assert result["rolled_back"] is True

    async def test_rolled_back_false_when_saga_disabled(self):
        result = await self._run_with_engine_error(RuntimeError("no-saga"), saga=False)
        assert result["rolled_back"] is False

    async def test_error_stored_in_active_workflows(self):
        engine = _build_engine()
        engine.execute = AsyncMock(side_effect=RuntimeError("stored"))
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine)

        await coord.execute_workflow("wf-stored", {})
        wf = next(iter(coord._active_workflows.values()))
        assert "error" in wf

    async def test_basic_workflow_runtime_error_caught(self):
        """_execute_basic_workflow raising propagates to error handler."""
        coord = _build_coordinator()
        with patch.object(
            coord,
            "_execute_basic_workflow",
            new=AsyncMock(side_effect=RuntimeError("basic fail")),
        ):
            result = await coord.execute_workflow("wf-basic-err", {})

        assert result["state"] == "failed"
        assert "basic fail" in result["error"]

    async def test_saga_rollback_called_on_failure_saga_enabled(self):
        engine = _build_engine()
        engine.execute = AsyncMock(side_effect=RuntimeError("trigger"))
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine, saga_enabled=True)
        with patch.object(coord, "_rollback_workflow", new=AsyncMock()) as mock_rb:
            await coord.execute_workflow("wf-rb", {})
        mock_rb.assert_awaited_once()

    async def test_saga_rollback_not_called_when_disabled(self):
        engine = _build_engine()
        engine.execute = AsyncMock(side_effect=RuntimeError("no-rb"))
        coord = _build_coordinator(
            langgraph_raises=None, workflow_engine=engine, saga_enabled=False
        )
        with patch.object(coord, "_rollback_workflow", new=AsyncMock()) as mock_rb:
            await coord.execute_workflow("wf-no-rb", {})
        mock_rb.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: _execute_basic_workflow
# ---------------------------------------------------------------------------


class TestExecuteBasicWorkflow:
    async def test_returns_expected_keys(self):
        coord = _build_coordinator()
        result = await coord._execute_basic_workflow("wf-direct", {"a": 1})
        assert result["workflow_id"] == "wf-direct"
        assert result["steps_completed"] == 1
        assert result["output"] == {"a": 1}

    async def test_preserves_complex_input(self):
        coord = _build_coordinator()
        data = {"nested": {"list": [1, 2, 3]}, "flag": True}
        result = await coord._execute_basic_workflow("wf-complex", data)
        assert result["output"] == data

    async def test_empty_input_data(self):
        coord = _build_coordinator()
        result = await coord._execute_basic_workflow("wf-empty", {})
        assert result["output"] == {}


# ---------------------------------------------------------------------------
# Tests: _rollback_workflow
# ---------------------------------------------------------------------------


class TestRollbackWorkflow:
    async def test_marks_existing_execution_as_rolled_back(self):
        coord = _build_coordinator()
        coord._active_workflows["exec-1"] = {"workflow_id": "wf", "state": "failed"}
        await coord._rollback_workflow("exec-1")
        assert coord._active_workflows["exec-1"]["state"] == "rolled_back"

    async def test_missing_execution_id_does_not_raise(self):
        coord = _build_coordinator()
        await coord._rollback_workflow("nonexistent")  # must not raise

    async def test_rollback_preserves_other_fields(self):
        coord = _build_coordinator()
        coord._active_workflows["exec-2"] = {
            "workflow_id": "wf-keep",
            "state": "failed",
            "error": "original error",
        }
        await coord._rollback_workflow("exec-2")
        wf = coord._active_workflows["exec-2"]
        assert wf["state"] == "rolled_back"
        assert wf["error"] == "original error"


# ---------------------------------------------------------------------------
# Tests: evolve_workflow — no engine
# ---------------------------------------------------------------------------


class TestEvolveWorkflowNoEngine:
    async def test_returns_failure_when_engine_absent(self):
        coord = _build_coordinator()
        result = await coord.evolve_workflow("wf-evo", {"signal": "slow"})
        assert result["success"] is False
        assert "not available" in result["reason"]
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_strategy_ignored_when_engine_absent(self):
        coord = _build_coordinator()
        result = await coord.evolve_workflow("wf-evo", {}, strategy="aggressive")
        assert result["success"] is False

    async def test_empty_feedback_when_no_engine(self):
        coord = _build_coordinator()
        result = await coord.evolve_workflow("wf-evo-empty", {})
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: evolve_workflow — with engine
# ---------------------------------------------------------------------------


class TestEvolveWorkflowWithEngine:
    def _make_coord_with_evo(self, proposal=None, raise_propose=None):
        """Build a coordinator that has an evolution engine."""
        evo_engine = MagicMock()
        if raise_propose:
            evo_engine.propose_evolution = AsyncMock(side_effect=raise_propose)
        else:
            if proposal is None:
                proposal = MagicMock()
                proposal.id = "prop-123"
                proposal.changes = ["change-A"]
                proposal.risk_level = "medium"
            evo_engine.propose_evolution = AsyncMock(return_value=proposal)

        # Build coordinator with real evo engine + OptimizationType in module
        lg_key = "enhanced_agent_bus.langgraph_orchestrator"
        evo_key = "enhanced_agent_bus.workflow_evolution"
        lg_mod = _make_fake_langgraph_module(raise_create=ImportError("no lg"))
        evo_mod = _make_fake_evolution_module(raise_create=None, engine=evo_engine)
        # Attach the engine to the module directly so evolve_workflow can import
        # OptimizationType from it
        opt_type = MagicMock()
        opt_type.LATENCY = "LATENCY"
        evo_mod.OptimizationType = opt_type

        with patch.dict(sys.modules, {lg_key: lg_mod, evo_key: evo_mod}):
            WorkflowCoordinator = _import_coordinator()
            coord = WorkflowCoordinator(enable_evolution=True)
        # Swap in our controlled engine
        coord._evolution_engine = evo_engine
        # Store evo_mod so we can patch it in tests
        coord._test_evo_mod = evo_mod
        return coord, evo_engine

    async def test_success_with_proposal_attributes(self):
        coord, _ = self._make_coord_with_evo()
        evo_key = "enhanced_agent_bus.workflow_evolution"
        evo_mod = coord._test_evo_mod
        with patch.dict(sys.modules, {evo_key: evo_mod}):
            result = await coord.evolve_workflow("wf-evolve", {"latency_ms": 200})

        assert result["success"] is True
        assert result["proposal_id"] == "prop-123"
        assert result["changes"] == ["change-A"]
        assert result["risk_level"] == "medium"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_proposal_without_id_uses_default(self):
        proposal = MagicMock(spec=[])  # no attrs
        coord, _ = self._make_coord_with_evo(proposal=proposal)
        evo_key = "enhanced_agent_bus.workflow_evolution"
        evo_mod = coord._test_evo_mod
        with patch.dict(sys.modules, {evo_key: evo_mod}):
            result = await coord.evolve_workflow("wf-no-id", {})

        assert result["proposal_id"] == "prop-1"
        assert result["changes"] == []
        assert result["risk_level"] == "low"

    async def test_runtime_error_returns_failure(self):
        coord, _ = self._make_coord_with_evo(raise_propose=RuntimeError("evo crash"))
        evo_key = "enhanced_agent_bus.workflow_evolution"
        evo_mod = coord._test_evo_mod
        with patch.dict(sys.modules, {evo_key: evo_mod}):
            result = await coord.evolve_workflow("wf-evo-err", {})

        assert result["success"] is False
        assert "evo crash" in result["error"]
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_value_error_returns_failure(self):
        coord, _ = self._make_coord_with_evo(raise_propose=ValueError("bad val"))
        evo_key = "enhanced_agent_bus.workflow_evolution"
        evo_mod = coord._test_evo_mod
        with patch.dict(sys.modules, {evo_key: evo_mod}):
            result = await coord.evolve_workflow("wf-ve", {})
        assert result["success"] is False

    async def test_attribute_error_returns_failure(self):
        coord, _ = self._make_coord_with_evo(raise_propose=AttributeError("no attr"))
        evo_key = "enhanced_agent_bus.workflow_evolution"
        evo_mod = coord._test_evo_mod
        with patch.dict(sys.modules, {evo_key: evo_mod}):
            result = await coord.evolve_workflow("wf-attr", {})
        assert result["success"] is False

    async def test_default_strategy_moderate(self):
        coord, _ = self._make_coord_with_evo()
        evo_key = "enhanced_agent_bus.workflow_evolution"
        evo_mod = coord._test_evo_mod
        with patch.dict(sys.modules, {evo_key: evo_mod}):
            result = await coord.evolve_workflow("wf-default", {})
        assert result["success"] is True

    async def test_custom_strategy_accepted(self):
        coord, _ = self._make_coord_with_evo()
        evo_key = "enhanced_agent_bus.workflow_evolution"
        evo_mod = coord._test_evo_mod
        with patch.dict(sys.modules, {evo_key: evo_mod}):
            result = await coord.evolve_workflow("wf-conservative", {}, strategy="conservative")
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tests: get_workflow_stats
# ---------------------------------------------------------------------------


class TestGetWorkflowStats:
    def test_empty_workflows_stats(self):
        coord = _build_coordinator()
        stats = coord.get_workflow_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["langgraph_available"] is False
        assert stats["evolution_available"] is False
        assert stats["saga_enabled"] is True
        assert stats["active_workflows"] == 0
        assert stats["state_distribution"] == {}

    def test_active_workflows_count(self):
        coord = _build_coordinator()
        coord._active_workflows = {
            "e1": {"state": "completed"},
            "e2": {"state": "completed"},
            "e3": {"state": "failed"},
        }
        stats = coord.get_workflow_stats()
        assert stats["active_workflows"] == 3

    def test_state_distribution_aggregation(self):
        coord = _build_coordinator()
        coord._active_workflows = {
            "e1": {"state": "completed"},
            "e2": {"state": "completed"},
            "e3": {"state": "failed"},
            "e4": {"state": "running"},
        }
        stats = coord.get_workflow_stats()
        dist = stats["state_distribution"]
        assert dist["completed"] == 2
        assert dist["failed"] == 1
        assert dist["running"] == 1

    def test_missing_state_key_defaults_to_unknown(self):
        coord = _build_coordinator()
        coord._active_workflows = {"e1": {}}  # no "state"
        stats = coord.get_workflow_stats()
        assert stats["state_distribution"]["unknown"] == 1

    def test_langgraph_available_true_in_stats(self):
        eng = _build_engine()
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=eng)
        stats = coord.get_workflow_stats()
        assert stats["langgraph_available"] is True

    def test_evolution_available_true_in_stats(self):
        evo = _build_evo_engine()
        coord = _build_coordinator(evolution_raises=None, evolution_engine=evo)
        stats = coord.get_workflow_stats()
        assert stats["evolution_available"] is True

    def test_saga_disabled_in_stats(self):
        coord = _build_coordinator(saga_enabled=False)
        stats = coord.get_workflow_stats()
        assert stats["saga_enabled"] is False


# ---------------------------------------------------------------------------
# Tests: Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_implements_workflow_coordinator_protocol(self):
        from enhanced_agent_bus.coordinators import WorkflowCoordinatorProtocol

        coord = _build_coordinator()
        assert isinstance(coord, WorkflowCoordinatorProtocol)


# ---------------------------------------------------------------------------
# Tests: Multiple concurrent workflows (integration)
# ---------------------------------------------------------------------------


class TestMultipleWorkflows:
    async def test_multiple_basic_workflows_tracked(self):
        coord = _build_coordinator()
        for i in range(5):
            await coord.execute_workflow(f"wf-{i}", {"i": i})
        assert len(coord._active_workflows) == 5

    async def test_stats_after_mixed_success_and_failure(self):
        engine = _build_engine()
        coord = _build_coordinator(langgraph_raises=None, workflow_engine=engine)

        # 2 successes
        engine.execute = AsyncMock(return_value={"ok": True})
        await coord.execute_workflow("wf-ok-0", {})
        await coord.execute_workflow("wf-ok-1", {})

        # 1 failure
        engine.execute = AsyncMock(side_effect=RuntimeError("fail"))
        await coord.execute_workflow("wf-fail", {})

        stats = coord.get_workflow_stats()
        assert stats["active_workflows"] == 3

    async def test_rollback_state_in_active_workflows_after_saga(self):
        coord = _build_coordinator()
        coord._active_workflows["exec-rb"] = {"workflow_id": "wf", "state": "failed"}
        await coord._rollback_workflow("exec-rb")
        assert coord._active_workflows["exec-rb"]["state"] == "rolled_back"
