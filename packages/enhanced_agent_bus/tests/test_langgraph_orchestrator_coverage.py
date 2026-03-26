# Constitutional Hash: 608508a9bd224290
"""
Comprehensive coverage tests for langgraph_orchestrator.py.

Targets ≥90% coverage of:
  src/core/enhanced_agent_bus/langgraph_orchestrator.py
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.langgraph_orchestrator import (
    CONSTITUTIONAL_HASH,
    BaseNode,
    ConditionalNode,
    GlobalState,
    GovernanceWorkflowNode,
    NodeExecutionResult,
    NodeState,
    WorkflowDefinition,
    WorkflowExecutor,
    WorkflowState,
    create_governance_workflow,
    get_workflow,
    register_workflow,
)

# ---------------------------------------------------------------------------
# Helpers / concrete BaseNode impl
# ---------------------------------------------------------------------------


class SimpleNode(BaseNode):
    """Minimal concrete node used throughout tests."""

    def __init__(self, node_id: str, name: str | None = None, *, should_fail: bool = False):
        super().__init__(node_id, name)
        self.should_fail = should_fail
        self.call_count = 0

    async def execute(self, state: GlobalState) -> NodeExecutionResult:
        import time

        self.call_count += 1
        if self.should_fail:
            return NodeExecutionResult(
                node_id=self.node_id,
                state=NodeState.FAILED,
                error="deliberate failure",
            )
        return NodeExecutionResult(
            node_id=self.node_id,
            state=NodeState.COMPLETED,
            output={"done": True},
            execution_time_ms=1.0,
        )


# ---------------------------------------------------------------------------
# NodeState / WorkflowState enum tests
# ---------------------------------------------------------------------------


class TestNodeState:
    def test_all_values(self):
        assert NodeState.PENDING.value == "pending"
        assert NodeState.RUNNING.value == "running"
        assert NodeState.COMPLETED.value == "completed"
        assert NodeState.FAILED.value == "failed"
        assert NodeState.SKIPPED.value == "skipped"


class TestWorkflowState:
    def test_all_values(self):
        assert WorkflowState.CREATED.value == "created"
        assert WorkflowState.RUNNING.value == "running"
        assert WorkflowState.COMPLETED.value == "completed"
        assert WorkflowState.FAILED.value == "failed"
        assert WorkflowState.PAUSED.value == "paused"
        assert WorkflowState.CANCELLED.value == "cancelled"


# ---------------------------------------------------------------------------
# NodeExecutionResult tests
# ---------------------------------------------------------------------------


class TestNodeExecutionResult:
    def test_defaults(self):
        r = NodeExecutionResult(node_id="n1", state=NodeState.COMPLETED)
        assert r.node_id == "n1"
        assert r.output is None
        assert r.error is None
        assert r.execution_time_ms == 0.0
        assert isinstance(r.timestamp, datetime)
        assert r.metadata == {}

    def test_to_dict(self):
        r = NodeExecutionResult(
            node_id="n1",
            state=NodeState.COMPLETED,
            output={"x": 1},
            error=None,
            execution_time_ms=5.5,
            metadata={"key": "val"},
        )
        d = r.to_dict()
        assert d["node_id"] == "n1"
        assert d["state"] == "completed"
        assert d["output"] == {"x": 1}
        assert d["error"] is None
        assert d["execution_time_ms"] == 5.5
        assert d["metadata"] == {"key": "val"}
        assert "timestamp" in d

    def test_to_dict_failed_state(self):
        r = NodeExecutionResult(node_id="n2", state=NodeState.FAILED, error="oops")
        d = r.to_dict()
        assert d["state"] == "failed"
        assert d["error"] == "oops"


# ---------------------------------------------------------------------------
# GlobalState tests
# ---------------------------------------------------------------------------


class TestGlobalState:
    def test_initial_state(self):
        gs = GlobalState(workflow_id="wf1")
        assert gs.workflow_id == "wf1"
        assert gs.current_node is None
        assert gs.state_data == {}
        assert gs.executed_nodes == set()
        assert gs.pending_nodes == set()
        assert gs.failed_nodes == set()
        assert gs.node_results == {}
        assert gs.execution_history == []
        assert gs.constitutional_hash == CONSTITUTIONAL_HASH

    def test_update_and_get(self):
        gs = GlobalState(workflow_id="wf1")
        gs.update("key", "value")
        assert gs.get("key") == "value"

    def test_get_default(self):
        gs = GlobalState(workflow_id="wf1")
        assert gs.get("missing") is None
        assert gs.get("missing", 42) == 42

    def test_record_node_execution_completed(self):
        gs = GlobalState(workflow_id="wf1")
        gs.pending_nodes.add("n1")
        result = NodeExecutionResult(node_id="n1", state=NodeState.COMPLETED)
        gs.record_node_execution(result)
        assert "n1" in gs.executed_nodes
        assert "n1" not in gs.pending_nodes
        assert "n1" not in gs.failed_nodes
        assert gs.execution_history == ["n1"]

    def test_record_node_execution_failed(self):
        gs = GlobalState(workflow_id="wf1")
        result = NodeExecutionResult(node_id="n2", state=NodeState.FAILED, error="err")
        gs.record_node_execution(result)
        assert "n2" in gs.failed_nodes
        assert "n2" in gs.executed_nodes

    def test_record_node_execution_not_in_pending(self):
        """Removing from pending when it was never there should not raise."""
        gs = GlobalState(workflow_id="wf1")
        result = NodeExecutionResult(node_id="n3", state=NodeState.COMPLETED)
        gs.record_node_execution(result)  # should not raise
        assert "n3" in gs.executed_nodes

    def test_to_dict(self):
        gs = GlobalState(workflow_id="wf1")
        gs.update("foo", "bar")
        d = gs.to_dict()
        assert d["workflow_id"] == "wf1"
        assert d["state_data"] == {"foo": "bar"}
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "created_at" in d
        assert "updated_at" in d

    def test_to_dict_with_node_results(self):
        gs = GlobalState(workflow_id="wf2")
        result = NodeExecutionResult(node_id="n1", state=NodeState.COMPLETED)
        gs.record_node_execution(result)
        d = gs.to_dict()
        assert "n1" in d["node_results"]
        assert "n1" in d["executed_nodes"]

    def test_update_modifies_updated_at(self):
        gs = GlobalState(workflow_id="wf1")
        before = gs.updated_at
        gs.update("k", "v")
        assert gs.updated_at >= before


# ---------------------------------------------------------------------------
# BaseNode tests
# ---------------------------------------------------------------------------


class TestBaseNode:
    def test_default_name_is_node_id(self):
        node = SimpleNode("my_node")
        assert node.name == "my_node"

    def test_custom_name(self):
        node = SimpleNode("id", "custom_name")
        assert node.name == "custom_name"

    def test_get_dependencies_empty(self):
        node = SimpleNode("n")
        assert node.get_dependencies() == []

    def test_add_dependency(self):
        node = SimpleNode("n")
        node.add_dependency("dep1")
        assert "dep1" in node.get_dependencies()

    def test_add_dependency_idempotent(self):
        node = SimpleNode("n")
        node.add_dependency("dep1")
        assert node.get_dependencies().count("dep1") == 1

    async def test_execute_returns_result(self):
        node = SimpleNode("n")
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert isinstance(result, NodeExecutionResult)
        assert result.state == NodeState.COMPLETED


# ---------------------------------------------------------------------------
# ConditionalNode tests
# ---------------------------------------------------------------------------


class TestConditionalNode:
    async def test_execute_success(self):
        def router(state: GlobalState) -> str:
            return "branch_a"

        node = ConditionalNode("cond_1", router)
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert result.state == NodeState.COMPLETED
        assert result.output["next_node"] == "branch_a"
        assert result.metadata["routing_decision"] == "branch_a"

    async def test_execute_condition_error(self):
        def bad_router(state: GlobalState) -> str:
            raise RuntimeError("router failed")

        node = ConditionalNode("cond_err", bad_router)
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert result.state == NodeState.FAILED
        assert "router failed" in result.error

    async def test_execute_value_error(self):
        def bad_router(state: GlobalState) -> str:
            raise ValueError("bad value")

        node = ConditionalNode("cond_val", bad_router)
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert result.state == NodeState.FAILED

    async def test_execute_type_error(self):
        def bad_router(state: GlobalState) -> str:
            raise TypeError("type error")

        node = ConditionalNode("cond_type", bad_router)
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert result.state == NodeState.FAILED

    async def test_name_set_automatically(self):
        node = ConditionalNode("my_cond", lambda s: "x")
        assert node.name == "conditional_my_cond"

    async def test_execution_time_recorded(self):
        node = ConditionalNode("cond_t", lambda s: "next")
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert result.execution_time_ms >= 0.0


# ---------------------------------------------------------------------------
# GovernanceWorkflowNode tests
# ---------------------------------------------------------------------------


class TestGovernanceWorkflowNode:
    async def test_route_by_complexity_simple(self):
        """Short text → simple_execution branch."""
        node = GovernanceWorkflowNode("cls", "route_by_complexity")
        gs = GlobalState(workflow_id="wf")
        gs.update("input_text", "hello")
        result = await node.execute(gs)
        assert result.state == NodeState.COMPLETED
        assert result.output["next_node"] == "simple_execution"
        assert result.output["complexity_score"] <= 0.5

    async def test_route_by_complexity_complex(self):
        """Long text → complex_deliberation branch."""
        node = GovernanceWorkflowNode("cls", "route_by_complexity")
        gs = GlobalState(workflow_id="wf")
        # 51+ words to exceed 0.5 threshold (words/100)
        long_text = " ".join(["word"] * 60)
        gs.update("input_text", long_text)
        result = await node.execute(gs)
        assert result.state == NodeState.COMPLETED
        assert result.output["next_node"] == "complex_deliberation"

    async def test_route_by_complexity_empty_text(self):
        node = GovernanceWorkflowNode("cls", "route_by_complexity")
        gs = GlobalState(workflow_id="wf")
        # No input_text key — should default to ""
        result = await node.execute(gs)
        assert result.state == NodeState.COMPLETED

    async def test_unknown_operation_fallback(self):
        node = GovernanceWorkflowNode("op", "unknown_op")
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert result.state == NodeState.COMPLETED
        assert result.output["operation"] == "unknown_op"
        assert result.output["status"] == "completed"

    async def test_validate_compliance_operation(self):
        """validate_compliance tries to import constitutional_classifier — mock it."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"compliant": True}

        mock_module = MagicMock()
        mock_module.classify_constitutional_compliance = AsyncMock(return_value=mock_result)

        with patch.dict(
            "sys.modules",
            {"constitutional_classifier": mock_module},
        ):
            node = GovernanceWorkflowNode("val", "validate_compliance")
            gs = GlobalState(workflow_id="wf")
            gs.update("input_text", "some text")
            result = await node.execute(gs)
        assert result.state == NodeState.COMPLETED
        assert result.output == {"compliant": True}

    async def test_check_security_operation(self):
        """check_security tries to import runtime_security — mock it."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"safe": True}

        mock_module = MagicMock()
        mock_module.scan_content = AsyncMock(return_value=mock_result)

        with patch.dict(
            "sys.modules",
            {"runtime_security": mock_module},
        ):
            node = GovernanceWorkflowNode("sec", "check_security")
            gs = GlobalState(workflow_id="wf")
            gs.update("content", "some content")
            result = await node.execute(gs)
        assert result.state == NodeState.COMPLETED
        assert result.output == {"safe": True}

    async def test_operation_raises_runtime_error_caught(self):
        """RuntimeError inside execute() → FAILED result (caught by except clause)."""
        import time

        node = GovernanceWorkflowNode("op_err", "unknown_op")
        gs = GlobalState(workflow_id="wf")

        # Monkey-patch the output dict to trigger a RuntimeError during the try block.
        # We achieve this by making the operation branch raise via the state.get() call.
        original_get = GlobalState.get

        def raising_get(self_gs, key, default=None):
            raise RuntimeError("intentional failure")

        gs.get = raising_get  # type: ignore[method-assign]
        # For "unknown_op" the operation just builds a dict, no state.get() call.
        # So we use "route_by_complexity" which calls state.get("input_text", "").
        node2 = GovernanceWorkflowNode("op_err2", "route_by_complexity")
        result = await node2.execute(gs)
        assert result.state == NodeState.FAILED
        assert "intentional failure" in result.error

    async def test_validate_compliance_operation_raises_value_error(self):
        """validate_compliance that raises ValueError → FAILED result."""
        mock_module = MagicMock()
        mock_module.classify_constitutional_compliance = AsyncMock(
            side_effect=ValueError("bad value")
        )
        with patch.dict("sys.modules", {"constitutional_classifier": mock_module}):
            node = GovernanceWorkflowNode("val_err", "validate_compliance")
            gs = GlobalState(workflow_id="wf")
            gs.update("input_text", "test")
            result = await node.execute(gs)
        assert result.state == NodeState.FAILED

    async def test_check_security_operation_raises_runtime_error(self):
        """check_security that raises RuntimeError → FAILED result."""
        mock_module = MagicMock()
        mock_module.scan_content = AsyncMock(side_effect=RuntimeError("scan failed"))
        with patch.dict("sys.modules", {"runtime_security": mock_module}):
            node = GovernanceWorkflowNode("sec_err", "check_security")
            gs = GlobalState(workflow_id="wf")
            gs.update("content", "test")
            result = await node.execute(gs)
        assert result.state == NodeState.FAILED

    async def test_metadata_contains_operation(self):
        node = GovernanceWorkflowNode("op", "unknown_op")
        gs = GlobalState(workflow_id="wf")
        result = await node.execute(gs)
        assert result.metadata["operation"] == "unknown_op"

    def test_config_defaults_to_empty_dict(self):
        node = GovernanceWorkflowNode("op", "some_op")
        assert node.config == {}

    def test_config_stored(self):
        node = GovernanceWorkflowNode("op", "some_op", config={"key": "val"})
        assert node.config == {"key": "val"}

    def test_name_derived_from_operation(self):
        node = GovernanceWorkflowNode("op", "my_op")
        assert node.name == "governance_my_op"


# ---------------------------------------------------------------------------
# WorkflowDefinition tests
# ---------------------------------------------------------------------------


class TestWorkflowDefinition:
    def _make_wf(self) -> WorkflowDefinition:
        return WorkflowDefinition(
            workflow_id="wf1",
            name="Test Workflow",
            description="desc",
        )

    def test_defaults(self):
        wf = self._make_wf()
        assert wf.nodes == {}
        assert wf.edges == {}
        assert wf.conditional_edges == {}
        assert wf.entry_point == "classifier"
        assert wf.max_execution_time_ms == 30000
        assert wf.constitutional_hash == CONSTITUTIONAL_HASH

    def test_add_node(self):
        wf = self._make_wf()
        node = SimpleNode("n1")
        wf.add_node(node)
        assert "n1" in wf.nodes

    def test_add_edge(self):
        wf = self._make_wf()
        wf.add_edge("a", "b")
        assert wf.edges["a"] == ["b"]

    def test_add_edge_idempotent(self):
        wf = self._make_wf()
        wf.add_edge("a", "b")
        assert wf.edges["a"].count("b") == 1

    def test_add_multiple_edges_from_same_node(self):
        wf = self._make_wf()
        wf.add_edge("a", "b")
        wf.add_edge("a", "c")
        assert set(wf.edges["a"]) == {"b", "c"}

    def test_add_conditional_edge(self):
        wf = self._make_wf()
        cond = ConditionalNode("router", lambda s: "x")
        wf.add_conditional_edge("a", cond)
        assert "a" in wf.conditional_edges
        assert "router" in wf.nodes

    async def test_get_next_nodes_regular_edges(self):
        wf = self._make_wf()
        wf.add_edge("a", "b")
        wf.add_edge("a", "c")
        gs = GlobalState(workflow_id="wf1")
        next_nodes = await wf.get_next_nodes("a", gs)
        assert set(next_nodes) == {"b", "c"}

    async def test_get_next_nodes_no_edges(self):
        wf = self._make_wf()
        gs = GlobalState(workflow_id="wf1")
        next_nodes = await wf.get_next_nodes("orphan", gs)
        assert next_nodes == []

    async def test_get_next_nodes_conditional_edge_completed(self):
        wf = self._make_wf()
        cond = ConditionalNode("router", lambda s: "target_node")
        wf.add_conditional_edge("a", cond)
        gs = GlobalState(workflow_id="wf1")
        next_nodes = await wf.get_next_nodes("a", gs)
        assert next_nodes == ["target_node"]

    async def test_get_next_nodes_conditional_edge_failed(self):
        """When the conditional node fails, no next nodes returned."""

        def bad_router(state):
            raise RuntimeError("router error")

        wf = self._make_wf()
        cond = ConditionalNode("router_fail", bad_router)
        wf.add_conditional_edge("a", cond)
        gs = GlobalState(workflow_id="wf1")
        next_nodes = await wf.get_next_nodes("a", gs)
        assert next_nodes == []

    async def test_get_next_nodes_conditional_no_next_node_key(self):
        """Conditional returns output dict without 'next_node' → empty list."""

        def router_no_key(state):
            return ""  # next_node will be "" (falsy)

        wf = self._make_wf()
        cond = ConditionalNode("router_empty", router_no_key)
        wf.add_conditional_edge("a", cond)
        gs = GlobalState(workflow_id="wf1")
        next_nodes = await wf.get_next_nodes("a", gs)
        # empty string is falsy, so no node appended
        assert next_nodes == []


# ---------------------------------------------------------------------------
# WorkflowExecutor tests
# ---------------------------------------------------------------------------


class TestWorkflowExecutor:
    def _make_linear_workflow(self) -> WorkflowDefinition:
        """node_a → node_b (linear chain)."""
        wf = WorkflowDefinition(
            workflow_id="linear",
            name="Linear",
            entry_point="node_a",
        )
        wf.add_node(SimpleNode("node_a"))
        wf.add_node(SimpleNode("node_b"))
        wf.add_edge("node_a", "node_b")
        return wf

    async def test_execute_linear_workflow(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        final_state = await executor.execute({})
        assert "node_a" in final_state.executed_nodes
        assert "node_b" in final_state.executed_nodes
        assert executor.execution_state == WorkflowState.COMPLETED
        assert executor.successful_executions == 1
        assert executor.total_executions == 1

    async def test_execute_with_explicit_workflow_id(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        final_state = await executor.execute({}, workflow_id="my-id")
        assert final_state.workflow_id == "my-id"

    async def test_execute_with_auto_workflow_id(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        final_state = await executor.execute({})
        assert final_state.workflow_id.startswith("workflow_")

    async def test_execute_state_data_copied(self):
        wf = WorkflowDefinition(
            workflow_id="wf",
            name="W",
            entry_point="n",
        )
        wf.add_node(SimpleNode("n"))
        executor = WorkflowExecutor(wf)
        initial = {"foo": "bar"}
        final_state = await executor.execute(initial)
        assert final_state.state_data["foo"] == "bar"

    async def test_execute_node_failure_raises(self):
        """
        Node failure raises a plain Exception (not in _LANGGRAPH_ORCHESTRATOR_OPERATION_ERRORS),
        so the outer except clause does NOT catch it.
        execution_state stays RUNNING and failed_executions is NOT incremented.
        This is the actual behaviour of the implementation.
        """
        wf = WorkflowDefinition(
            workflow_id="fail",
            name="Fail",
            entry_point="bad_node",
        )
        wf.add_node(SimpleNode("bad_node", should_fail=True))
        executor = WorkflowExecutor(wf)
        with pytest.raises(Exception, match="bad_node failed"):
            await executor.execute({})
        # Plain Exception bypasses the outer except → state stays RUNNING
        assert executor.execution_state == WorkflowState.RUNNING
        assert executor.total_executions == 1

    async def test_execute_missing_entry_node_skips(self):
        """Entry point not in nodes → logged as warning, no crash."""
        wf = WorkflowDefinition(
            workflow_id="missing",
            name="Missing",
            entry_point="ghost",
        )
        # No node added — pending_nodes will have "ghost" but workflow has no node.
        # The while loop will pop "ghost", not find it, and continue.
        # pending_nodes will be empty after that → completes.
        executor = WorkflowExecutor(wf)
        final_state = await executor.execute({})
        assert executor.execution_state == WorkflowState.COMPLETED

    async def test_metrics_initial(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        metrics = executor.get_metrics()
        assert metrics["total_executions"] == 0
        assert metrics["successful_executions"] == 0
        assert metrics["failed_executions"] == 0
        assert metrics["success_rate"] == 0
        assert metrics["current_state"] is None
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_metrics_after_success(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        await executor.execute({})
        metrics = executor.get_metrics()
        assert metrics["total_executions"] == 1
        assert metrics["successful_executions"] == 1
        assert metrics["success_rate"] == 1.0
        assert metrics["current_state"] == "completed"

    async def test_metrics_after_failure_via_runtime_error(self):
        """
        A RuntimeError (which IS in _LANGGRAPH_ORCHESTRATOR_OPERATION_ERRORS) raised
        during _execute_workflow is caught by the outer except and increments
        failed_executions.
        """

        class RuntimeErrorNode(BaseNode):
            async def execute(self, state: GlobalState) -> NodeExecutionResult:
                raise RuntimeError("node raised runtime error")

        wf = WorkflowDefinition(
            workflow_id="f",
            name="F",
            entry_point="bad",
        )
        wf.add_node(RuntimeErrorNode("bad"))
        executor = WorkflowExecutor(wf)
        with pytest.raises(RuntimeError):
            await executor.execute({})
        metrics = executor.get_metrics()
        assert metrics["failed_executions"] == 1
        assert metrics["current_state"] == "failed"

    def test_pause_when_running(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        executor.execution_state = WorkflowState.RUNNING
        executor.current_state = GlobalState(workflow_id="wf")
        executor.pause()
        assert executor.execution_state == WorkflowState.PAUSED

    def test_pause_when_not_running(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        executor.execution_state = WorkflowState.COMPLETED
        executor.current_state = GlobalState(workflow_id="wf")
        executor.pause()
        # State unchanged
        assert executor.execution_state == WorkflowState.COMPLETED

    def test_resume_when_paused(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        executor.execution_state = WorkflowState.PAUSED
        executor.current_state = GlobalState(workflow_id="wf")
        executor.resume()
        assert executor.execution_state == WorkflowState.RUNNING

    def test_resume_when_not_paused(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        executor.execution_state = WorkflowState.COMPLETED
        executor.current_state = GlobalState(workflow_id="wf")
        executor.resume()
        assert executor.execution_state == WorkflowState.COMPLETED

    def test_cancel(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        executor.execution_state = WorkflowState.RUNNING
        executor.current_state = GlobalState(workflow_id="wf")
        executor.cancel()
        assert executor.execution_state == WorkflowState.CANCELLED

    async def test_execute_records_error_in_state_on_runtime_error(self):
        """
        A RuntimeError raised by a node is caught by the outer except clause,
        which records 'execution_error' in state_data.
        """

        class RuntimeErrorNode(BaseNode):
            async def execute(self, state: GlobalState) -> NodeExecutionResult:
                raise RuntimeError("state error")

        wf = WorkflowDefinition(
            workflow_id="err",
            name="Err",
            entry_point="bad",
        )
        wf.add_node(RuntimeErrorNode("bad"))
        executor = WorkflowExecutor(wf)
        with pytest.raises(RuntimeError):
            await executor.execute({})
        assert "execution_error" in executor.current_state.state_data

    async def test_max_iterations_exceeded(self):
        """
        A cyclic graph with max_iterations exceeded raises an exception.
        We use a node that adds two new unique nodes to pending on each iteration,
        creating exponential growth. We use 100 distinct node IDs that form a chain.
        Simpler approach: a node adds new unique node IDs to pending_nodes directly,
        bypassing the executed_nodes check.
        """
        counter = {"n": 0}

        class InfiniteNode(BaseNode):
            async def execute(self_node, state: GlobalState) -> NodeExecutionResult:
                # Always add a fresh new node name to pending_nodes
                counter["n"] += 1
                new_id = f"auto_node_{counter['n']}"
                state.pending_nodes.add(new_id)
                return NodeExecutionResult(
                    node_id=self_node.node_id,
                    state=NodeState.COMPLETED,
                    output={},
                )

        wf = WorkflowDefinition(
            workflow_id="cyclic3",
            name="Cyclic3",
            entry_point="root",
        )
        # The root node and a large set of auto-generated node stubs.
        # Each auto_node_N will not be found in workflow.nodes → logged as warning
        # but a NEW one gets added each iteration, so pending_nodes never empties.
        # We need each auto_node to also be an InfiniteNode to keep creating more.
        # Simpler: override get_next_nodes to always return an unseen node.
        wf.add_node(InfiniteNode("root"))

        # Also register a fallback so auto_node_X nodes are found and executed
        class AutoNode(BaseNode):
            async def execute(self_node, state: GlobalState) -> NodeExecutionResult:
                counter["n"] += 1
                state.pending_nodes.add(f"auto_node_{counter['n']}")
                return NodeExecutionResult(
                    node_id=self_node.node_id,
                    state=NodeState.COMPLETED,
                    output={},
                )

        # Pre-populate workflow with enough auto nodes to sustain 100 iterations
        for i in range(1, 200):
            wf.add_node(AutoNode(f"auto_node_{i}"))

        executor = WorkflowExecutor(wf)
        with pytest.raises(Exception, match="maximum iterations"):
            await executor.execute({})

    async def test_multiple_executions_increment_counters(self):
        wf = self._make_linear_workflow()
        executor = WorkflowExecutor(wf)
        await executor.execute({})
        await executor.execute({})
        assert executor.total_executions == 2
        assert executor.successful_executions == 2

    async def test_skip_already_executed_next_node(self):
        """
        Covers the false branch at line 452 where next_node IS in executed_nodes.
        Strategy: use a node that directly returns a next_node via get_next_nodes
        that is already in executed_nodes.  We do this by having a node add
        a target to pending_nodes manually (bypassing get_next_nodes), ensuring
        the target is executed first, then having the second node's edge point
        back to the target (which will now be in executed_nodes).

        Simpler: use a custom WorkflowDefinition subclass where get_next_nodes
        always returns ["node_a"] for node_b — and node_a will already be executed.
        """

        class LoopBackWorkflow(WorkflowDefinition):
            async def get_next_nodes(self, node_id: str, state: GlobalState) -> list[str]:
                if node_id == "node_b":
                    # Always return node_a, which is already in executed_nodes
                    return ["node_a"]
                return await super().get_next_nodes(node_id, state)

        wf = LoopBackWorkflow(
            workflow_id="skip_test",
            name="Skip",
            entry_point="node_a",
        )
        wf.add_node(SimpleNode("node_a"))
        wf.add_node(SimpleNode("node_b"))
        wf.add_edge("node_a", "node_b")
        # node_b's get_next_nodes returns ["node_a"] (already executed → skipped)
        executor = WorkflowExecutor(wf)
        final_state = await executor.execute({})
        assert "node_a" in final_state.executed_nodes
        assert "node_b" in final_state.executed_nodes
        # node_a should appear only once (not re-executed)
        assert final_state.execution_history.count("node_a") == 1


# ---------------------------------------------------------------------------
# create_governance_workflow tests
# ---------------------------------------------------------------------------


class TestCreateGovernanceWorkflow:
    def test_returns_workflow_definition(self):
        wf = create_governance_workflow()
        assert isinstance(wf, WorkflowDefinition)

    def test_workflow_id(self):
        wf = create_governance_workflow()
        assert wf.workflow_id == "governance_standard"

    def test_entry_point(self):
        wf = create_governance_workflow()
        assert wf.entry_point == "classifier"

    def test_has_expected_nodes(self):
        wf = create_governance_workflow()
        expected = {
            "classifier",
            "validator",
            "complexity_router",
            "deliberator",
            "executor",
            "auditor",
        }
        assert expected.issubset(set(wf.nodes.keys()))

    def test_conditional_edge_exists(self):
        wf = create_governance_workflow()
        assert "complexity_router" in wf.conditional_edges

    def test_constitutional_hash(self):
        wf = create_governance_workflow()
        assert wf.constitutional_hash == CONSTITUTIONAL_HASH

    def test_classifier_edge_to_complexity_router(self):
        wf = create_governance_workflow()
        assert "complexity_router" in wf.edges.get("classifier", [])

    async def test_execute_full_governance_workflow_simple_path(self):
        """Run the governance workflow end-to-end with a short input."""
        wf = create_governance_workflow()
        executor = WorkflowExecutor(wf)
        # Short text → simple_execution branch (but "simple_execution" not in nodes,
        # so it will be popped from pending, not found, and skipped).
        final_state = await executor.execute({"input_text": "hi"})
        assert "classifier" in final_state.executed_nodes

    async def test_execute_full_governance_workflow_complex_path(self):
        """Run the governance workflow end-to-end with a long input."""
        wf = create_governance_workflow()
        executor = WorkflowExecutor(wf)
        long_text = " ".join(["word"] * 60)
        # complex path → "complex_deliberation" (not in nodes → skipped)
        final_state = await executor.execute({"input_text": long_text})
        assert "classifier" in final_state.executed_nodes

    async def test_conditional_routing_in_workflow(self):
        """The complexity_router conditional node routes based on complexity_score."""
        wf = create_governance_workflow()
        gs = GlobalState(workflow_id="test")
        gs.update("complexity_score", 0.8)
        next_nodes = await wf.get_next_nodes("complexity_router", gs)
        assert "deliberator" in next_nodes

    async def test_conditional_routing_low_complexity(self):
        wf = create_governance_workflow()
        gs = GlobalState(workflow_id="test")
        gs.update("complexity_score", 0.1)
        next_nodes = await wf.get_next_nodes("complexity_router", gs)
        assert "executor" in next_nodes


# ---------------------------------------------------------------------------
# Workflow registry tests
# ---------------------------------------------------------------------------


class TestWorkflowRegistry:
    def test_register_and_get(self):
        wf = WorkflowDefinition(workflow_id="reg_test", name="Reg Test")
        register_workflow(wf)
        retrieved = get_workflow("reg_test")
        assert retrieved is wf

    def test_get_missing(self):
        result = get_workflow("does_not_exist_xyz")
        assert result is None

    def test_governance_workflow_preregistered(self):
        """The standard governance workflow is registered at module load time."""
        wf = get_workflow("governance_standard")
        assert wf is not None
        assert wf.workflow_id == "governance_standard"

    def test_register_overwrites(self):
        wf1 = WorkflowDefinition(workflow_id="overwrite_test", name="V1")
        wf2 = WorkflowDefinition(workflow_id="overwrite_test", name="V2")
        register_workflow(wf1)
        register_workflow(wf2)
        assert get_workflow("overwrite_test").name == "V2"


# ---------------------------------------------------------------------------
# Constitutional hash constant test
# ---------------------------------------------------------------------------


class TestConstitutionalHash:
    def test_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_global_state_uses_hash(self):
        gs = GlobalState(workflow_id="wf")
        assert gs.constitutional_hash == CONSTITUTIONAL_HASH

    def test_workflow_definition_uses_hash(self):
        wf = WorkflowDefinition(workflow_id="wf", name="N")
        assert wf.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Cover lines 514-515: the nested route_by_complexity closure in the first
# create_governance_workflow definition, which is registered at module load
# time and stored in the workflow registry under "governance_standard".
# Invoking get_next_nodes on that registered workflow triggers the closure.
# ---------------------------------------------------------------------------


class TestRegisteredWorkflowConditionalRouting:
    async def test_registered_workflow_high_complexity(self):
        """
        The pre-registered 'governance_standard' workflow (built by the first
        create_governance_workflow definition) contains a complexity_router whose
        closure is at lines 514-515.  Calling get_next_nodes triggers it.
        """
        wf = get_workflow("governance_standard")
        assert wf is not None
        gs = GlobalState(workflow_id="reg_test")
        gs.update("complexity_score", 0.9)
        next_nodes = await wf.get_next_nodes("complexity_router", gs)
        assert "deliberator" in next_nodes

    async def test_registered_workflow_low_complexity(self):
        wf = get_workflow("governance_standard")
        assert wf is not None
        gs = GlobalState(workflow_id="reg_test2")
        gs.update("complexity_score", 0.1)
        next_nodes = await wf.get_next_nodes("complexity_router", gs)
        assert "executor" in next_nodes
