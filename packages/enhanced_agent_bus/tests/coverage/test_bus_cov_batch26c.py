"""
Coverage tests for:
1. langgraph_orchestration/graph_orchestrator.py (missing 42 lines)
2. context_memory/hybrid_context_manager.py (missing 42 lines)
3. acgs-lite/src/fix_imports.py (44 missing lines, 0% coverage)

asyncio_mode = "auto" -- no @pytest.mark.asyncio decorator needed.
"""

import importlib
import importlib.util
import os
import statistics
import sys
import tempfile
import textwrap
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers for building minimal valid GraphDefinition fixtures
# ---------------------------------------------------------------------------


def _make_graph_definition(
    *,
    nodes=None,
    edges=None,
    conditional_edges=None,
    start_node_id="start",
    end_node_ids=None,
    name="test-graph",
):
    from enhanced_agent_bus.langgraph_orchestration.models import (
        EdgeType,
        GraphDefinition,
        GraphEdge,
        GraphNode,
        NodeType,
    )

    if nodes is None:
        nodes = [
            GraphNode(id="start", name="Start", node_type=NodeType.START),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
    if edges is None:
        edges = [
            GraphEdge(
                source_node_id="start",
                target_node_id="end",
                edge_type=EdgeType.SEQUENTIAL,
            )
        ]
    if end_node_ids is None:
        end_node_ids = ["end"]

    return GraphDefinition(
        name=name,
        nodes=nodes,
        edges=edges,
        conditional_edges=conditional_edges or [],
        start_node_id=start_node_id,
        end_node_ids=end_node_ids,
    )


def _make_orchestrator(graph=None, **kwargs):
    from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
        GraphOrchestrator,
        GraphOrchestratorConfig,
    )

    graph = graph or _make_graph_definition()
    config = kwargs.pop("config", None) or GraphOrchestratorConfig(
        persist_state=kwargs.pop("persist_state", False),
        enable_checkpoints=kwargs.pop("enable_checkpoints", False),
        hitl_enabled=kwargs.pop("hitl_enabled", False),
        constitutional_validation=False,
        maci_enforcement=False,
    )
    return GraphOrchestrator(graph=graph, config=config, **kwargs)


# ============================================================================
# GraphOrchestrator tests
# ============================================================================


class TestGraphOrchestratorInit:
    """Tests for GraphOrchestrator.__init__ and _validate_graph."""

    def test_default_init_minimal(self):
        orch = _make_orchestrator()
        assert orch.graph is not None
        assert orch._executions == 0

    def test_self_loop_raises_cyclic_dependency(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import CyclicDependencyError
        from enhanced_agent_bus.langgraph_orchestration.models import (
            EdgeType,
            GraphEdge,
            GraphNode,
            NodeType,
        )

        nodes = [
            GraphNode(id="a", name="A", node_type=NodeType.FUNCTION),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        edges = [
            GraphEdge(source_node_id="a", target_node_id="a", edge_type=EdgeType.SEQUENTIAL),
            GraphEdge(source_node_id="a", target_node_id="end", edge_type=EdgeType.SEQUENTIAL),
        ]
        graph = _make_graph_definition(nodes=nodes, edges=edges, start_node_id="a")

        with pytest.raises(CyclicDependencyError):
            _make_orchestrator(graph=graph)

    def test_loop_edge_self_loop_is_allowed(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            EdgeType,
            GraphEdge,
            GraphNode,
            NodeType,
        )

        nodes = [
            GraphNode(id="a", name="A", node_type=NodeType.FUNCTION),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        edges = [
            GraphEdge(source_node_id="a", target_node_id="a", edge_type=EdgeType.LOOP),
            GraphEdge(source_node_id="a", target_node_id="end", edge_type=EdgeType.SEQUENTIAL),
        ]
        graph = _make_graph_definition(nodes=nodes, edges=edges, start_node_id="a")
        orch = _make_orchestrator(graph=graph)
        assert orch is not None

    def test_invalid_graph_raises_validation_error(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import GraphValidationError
        from enhanced_agent_bus.langgraph_orchestration.models import (
            GraphDefinition,
        )

        graph = GraphDefinition(name="bad", start_node_id=None, end_node_ids=[])
        with pytest.raises(GraphValidationError):
            _make_orchestrator(graph=graph)

    def test_build_edge_maps_populates_structures(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ConditionalEdge,
            EdgeType,
            GraphEdge,
            GraphNode,
            NodeType,
        )

        nodes = [
            GraphNode(id="s", name="S", node_type=NodeType.START),
            GraphNode(id="a", name="A", node_type=NodeType.FUNCTION),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        edges = [
            GraphEdge(source_node_id="s", target_node_id="a", edge_type=EdgeType.SEQUENTIAL),
            GraphEdge(source_node_id="a", target_node_id="end", edge_type=EdgeType.SEQUENTIAL),
        ]
        cond_edges = [
            ConditionalEdge(
                source_node_id="s",
                conditions={"yes": "a"},
                default_target="end",
            )
        ]
        graph = _make_graph_definition(
            nodes=nodes, edges=edges, conditional_edges=cond_edges, start_node_id="s"
        )
        orch = _make_orchestrator(graph=graph)
        assert "s" in orch._outgoing_edges
        assert "a" in orch._incoming_edges
        assert "s" in orch._conditional_edges

    def test_persistence_created_when_persist_state(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=False,
            hitl_enabled=False,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)
        assert orch.persistence is not None

    def test_checkpoint_manager_created_when_enabled(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            hitl_enabled=False,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)
        assert orch.checkpoint_manager is not None

    def test_hitl_handler_created_when_enabled(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            hitl_enabled=True,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)
        assert orch.hitl_handler is not None


class TestGraphOrchestratorRegister:
    """Tests for register_function / register_condition."""

    def test_register_function(self):
        orch = _make_orchestrator()

        def my_func(state):
            return state

        orch.register_function("my.path", my_func)
        # The function should be registered on the executor
        assert "my.path" in orch.executor._function_cache

    def test_register_condition(self):
        orch = _make_orchestrator()

        def cond(state):
            return "next"

        orch.register_condition("cond.path", cond)
        assert "cond.path" in orch.conditional_executor._condition_cache


class TestGraphOrchestratorRun:
    """Tests for the run() method and its sub-methods."""

    async def test_run_simple_two_node_graph(self):
        orch = _make_orchestrator()
        # Mock executor to return completed result
        mock_result = MagicMock()
        mock_result.status = MagicMock()
        mock_result.output_state = {"result": "ok"}
        mock_result.execution_time_ms = 1.0
        mock_result.error = None

        from enhanced_agent_bus.langgraph_orchestration.models import NodeResult, NodeStatus

        completed_result = NodeResult(
            node_id="start",
            status=NodeStatus.COMPLETED,
            output_state={"step": "start_done"},
            execution_time_ms=1.5,
        )
        end_result = NodeResult(
            node_id="end",
            status=NodeStatus.COMPLETED,
            output_state={"step": "end_done"},
            execution_time_ms=0.5,
        )

        call_count = 0

        async def mock_execute(node, state, ctx):
            nonlocal call_count
            call_count += 1
            if node.id == "start":
                return completed_result
            return end_result

        orch.executor.execute = mock_execute
        result = await orch.run(input_data={"input": "test"})

        from enhanced_agent_bus.langgraph_orchestration.models import ExecutionStatus

        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_execution_time_ms > 0

    async def test_run_with_initial_state(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            GraphState,
            NodeResult,
            NodeStatus,
        )

        orch = _make_orchestrator()

        async def mock_execute(node, state, ctx):
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.COMPLETED,
                output_state={"done": True},
                execution_time_ms=0.1,
            )

        orch.executor.execute = mock_execute
        initial = GraphState(data={"pre": "existing"})
        result = await orch.run(initial_state=initial)
        assert result.status.value == "completed"

    async def test_run_error_path_returns_failed(self):
        from enhanced_agent_bus.langgraph_orchestration.models import ExecutionStatus

        orch = _make_orchestrator()

        async def failing_execute(node, state, ctx):
            raise RuntimeError("boom")

        orch.executor.execute = failing_execute
        result = await orch.run(input_data={})
        assert result.status == ExecutionStatus.FAILED
        assert "boom" in result.error

    async def test_run_error_with_checkpoint_on_error(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import ExecutionStatus

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            checkpoint_on_error=True,
            hitl_enabled=False,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)

        async def failing_execute(node, state, ctx):
            raise ValueError("test error")

        orch.executor.execute = failing_execute
        # Mock checkpoint manager
        orch.checkpoint_manager.create_checkpoint = AsyncMock()

        result = await orch.run(input_data={})
        assert result.status == ExecutionStatus.FAILED
        orch.checkpoint_manager.create_checkpoint.assert_called_once()

    async def test_run_error_checkpoint_failure_is_swallowed(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import ExecutionStatus

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            checkpoint_on_error=True,
            hitl_enabled=False,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)

        async def failing_execute(node, state, ctx):
            raise ValueError("primary error")

        orch.executor.execute = failing_execute
        orch.checkpoint_manager.create_checkpoint = AsyncMock(
            side_effect=RuntimeError("checkpoint fail")
        )

        result = await orch.run(input_data={})
        assert result.status == ExecutionStatus.FAILED
        assert "primary error" in result.error

    async def test_run_persists_result_on_success(self):
        from enhanced_agent_bus.langgraph_orchestration.models import NodeResult, NodeStatus

        orch = _make_orchestrator(persist_state=True)

        async def mock_execute(node, state, ctx):
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.COMPLETED,
                output_state={},
                execution_time_ms=0.1,
            )

        orch.executor.execute = mock_execute
        orch.persistence.save_execution_result = AsyncMock()
        result = await orch.run()
        orch.persistence.save_execution_result.assert_called_once()


class TestGraphOrchestratorExecuteGraph:
    """Tests for _execute_graph internal flow."""

    async def test_max_iterations_warning(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            EdgeType,
            GraphEdge,
            GraphNode,
            NodeResult,
            NodeStatus,
            NodeType,
        )

        nodes = [
            GraphNode(id="s", name="S", node_type=NodeType.START),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        edges = [
            GraphEdge(source_node_id="s", target_node_id="s", edge_type=EdgeType.LOOP),
            GraphEdge(source_node_id="s", target_node_id="end", edge_type=EdgeType.SEQUENTIAL),
        ]
        graph = _make_graph_definition(nodes=nodes, edges=edges, start_node_id="s")
        config = GraphOrchestratorConfig(
            max_iterations=2,
            persist_state=False,
            enable_checkpoints=False,
            hitl_enabled=False,
        )
        orch = _make_orchestrator(graph=graph, config=config)

        call_count = 0

        async def mock_execute(node, state, ctx):
            nonlocal call_count
            call_count += 1
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.COMPLETED,
                output_state={},
                execution_time_ms=0.1,
            )

        orch.executor.execute = mock_execute

        # Mock _get_next_node to always loop back to "s"
        async def always_s(node_id, state):
            return "s"

        orch._get_next_node = always_s

        result = await orch.run()
        # Should have hit max_iterations and stopped
        assert result is not None

    async def test_node_not_found_raises(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import OrchestrationError

        orch = _make_orchestrator()
        with pytest.raises(OrchestrationError, match="not found"):
            orch._get_node_or_raise("nonexistent")


class TestExecuteNodeWithLifecycle:
    """Tests for _execute_node_with_lifecycle."""

    async def test_interrupt_before_is_called(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            GraphNode,
            NodeResult,
            NodeStatus,
            NodeType,
        )

        orch = _make_orchestrator(hitl_enabled=True)
        node = GraphNode(id="n1", name="N1", node_type=NodeType.FUNCTION, interrupt_before=True)
        orch._node_map["n1"] = node

        async def mock_execute(n, state, ctx):
            return NodeResult(
                node_id=n.id,
                status=NodeStatus.COMPLETED,
                output_state={"x": 1},
                execution_time_ms=0.1,
            )

        orch.executor.execute = mock_execute
        orch._handle_interrupt = AsyncMock(return_value=MagicMock(data={}))

        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphState,
        )

        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        # Make _handle_interrupt return the same state
        orch._handle_interrupt = AsyncMock(return_value=state)

        state_out, result = await orch._execute_node_with_lifecycle(node, state, ctx, [])
        orch._handle_interrupt.assert_called_once()

    async def test_interrupt_after_is_called(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeResult,
            NodeStatus,
            NodeType,
        )

        orch = _make_orchestrator(hitl_enabled=True)
        node = GraphNode(id="n2", name="N2", node_type=NodeType.FUNCTION, interrupt_after=True)
        orch._node_map["n2"] = node

        async def mock_execute(n, state, ctx):
            return NodeResult(
                node_id=n.id,
                status=NodeStatus.COMPLETED,
                output_state={"y": 2},
                execution_time_ms=0.1,
            )

        orch.executor.execute = mock_execute

        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        orch._handle_interrupt = AsyncMock(return_value=state)

        state_out, result = await orch._execute_node_with_lifecycle(node, state, ctx, [])
        orch._handle_interrupt.assert_called_once()

    async def test_failed_node_raises_node_execution_error(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import NodeExecutionError
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeResult,
            NodeStatus,
            NodeType,
        )

        orch = _make_orchestrator()
        node = GraphNode(id="fail", name="Fail", node_type=NodeType.FUNCTION)
        orch._node_map["fail"] = node

        async def mock_execute(n, state, ctx):
            return NodeResult(
                node_id=n.id,
                status=NodeStatus.FAILED,
                error="bad stuff",
                execution_time_ms=0.1,
            )

        orch.executor.execute = mock_execute
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        with pytest.raises(NodeExecutionError):
            await orch._execute_node_with_lifecycle(node, state, ctx, [])

    async def test_interrupted_node_sets_context_status(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeResult,
            NodeStatus,
            NodeType,
        )

        orch = _make_orchestrator()
        node = GraphNode(id="int", name="Int", node_type=NodeType.FUNCTION)
        orch._node_map["int"] = node

        async def mock_execute(n, state, ctx):
            return NodeResult(
                node_id=n.id,
                status=NodeStatus.INTERRUPTED,
                execution_time_ms=0.1,
            )

        orch.executor.execute = mock_execute
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        state_out, result = await orch._execute_node_with_lifecycle(node, state, ctx, [])
        assert ctx.status == ExecutionStatus.INTERRUPTED


class TestCreateCheckpointIfNeeded:
    """Tests for _create_checkpoint_if_needed."""

    async def test_constitutional_checkpoint_triggers(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeType,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            hitl_enabled=False,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)
        orch.checkpoint_manager.create_checkpoint = AsyncMock()

        node = GraphNode(
            id="cp", name="CP", node_type=NodeType.CHECKPOINT, constitutional_checkpoint=True
        )
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            step_count=1,
        )

        await orch._create_checkpoint_if_needed(node, state, ctx)
        orch.checkpoint_manager.create_checkpoint.assert_called_once()

    async def test_interval_checkpoint_triggers(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeType,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            checkpoint_interval=5,
            hitl_enabled=False,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)
        orch.checkpoint_manager.create_checkpoint = AsyncMock()

        node = GraphNode(id="n", name="N", node_type=NodeType.FUNCTION)
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            step_count=10,  # divisible by 5
        )

        await orch._create_checkpoint_if_needed(node, state, ctx)
        orch.checkpoint_manager.create_checkpoint.assert_called_once()

    async def test_no_checkpoint_when_not_needed(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeType,
        )

        orch = _make_orchestrator()  # checkpoints disabled
        node = GraphNode(id="n", name="N", node_type=NodeType.FUNCTION)
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            step_count=3,
        )
        # Should not raise; nothing to assert except no error
        await orch._create_checkpoint_if_needed(node, state, ctx)


class TestDetermineNextNode:
    """Tests for _determine_next_node_and_persist and _get_next_node."""

    async def test_sequential_edge_returns_target(self):
        orch = _make_orchestrator()
        next_id = await orch._get_next_node("start", MagicMock(data={}))
        assert next_id == "end"

    async def test_no_outgoing_returns_none(self):
        orch = _make_orchestrator()
        next_id = await orch._get_next_node("end", MagicMock(data={}))
        assert next_id is None

    async def test_conditional_edge_routing(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ConditionalEdge,
            EdgeType,
            GraphEdge,
            GraphNode,
            NodeType,
        )

        nodes = [
            GraphNode(id="s", name="S", node_type=NodeType.START),
            GraphNode(id="a", name="A", node_type=NodeType.FUNCTION),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        edges = [
            GraphEdge(source_node_id="s", target_node_id="end", edge_type=EdgeType.SEQUENTIAL),
        ]
        cond_edges = [
            ConditionalEdge(
                source_node_id="s",
                conditions={"go": "a"},
                default_target="end",
            )
        ]
        graph = _make_graph_definition(
            nodes=nodes, edges=edges, conditional_edges=cond_edges, start_node_id="s"
        )
        orch = _make_orchestrator(graph=graph)

        # Mock the conditional executor route to return "a"
        orch.conditional_executor.route = AsyncMock(return_value="a")

        next_id = await orch._get_next_node("s", MagicMock(data={}))
        assert next_id == "a"

    async def test_determine_next_persists_state(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeType,
        )

        orch = _make_orchestrator(persist_state=True)
        orch.persistence.save_state = AsyncMock()

        node = orch._node_map["start"]
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            workflow_id="w1",
            run_id="r1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            step_count=1,
        )

        next_id = await orch._determine_next_node_and_persist(node, state, ctx)
        orch.persistence.save_state.assert_called_once()


class TestExecuteNode:
    """Tests for _execute_node (parallel node handling)."""

    async def test_parallel_node_executes_parallel(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            EdgeType,
            ExecutionContext,
            ExecutionStatus,
            GraphEdge,
            GraphNode,
            GraphState,
            NodeResult,
            NodeStatus,
            NodeType,
        )

        nodes = [
            GraphNode(id="par", name="Parallel", node_type=NodeType.PARALLEL),
            GraphNode(id="w1", name="W1", node_type=NodeType.WORKER),
            GraphNode(id="w2", name="W2", node_type=NodeType.WORKER),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        edges = [
            GraphEdge(source_node_id="par", target_node_id="w1", edge_type=EdgeType.PARALLEL),
            GraphEdge(source_node_id="par", target_node_id="w2", edge_type=EdgeType.PARALLEL),
            GraphEdge(source_node_id="par", target_node_id="end", edge_type=EdgeType.SEQUENTIAL),
        ]
        graph = _make_graph_definition(nodes=nodes, edges=edges, start_node_id="par")
        orch = _make_orchestrator(graph=graph)

        r1 = NodeResult(
            node_id="w1",
            status=NodeStatus.COMPLETED,
            output_state={"w1": "done"},
            execution_time_ms=1.0,
        )
        r2 = NodeResult(
            node_id="w2",
            status=NodeStatus.COMPLETED,
            output_state={"w2": "done"},
            execution_time_ms=2.0,
        )
        orch.parallel_executor.execute_parallel = AsyncMock(return_value=[r1, r2])

        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        node = orch._node_map["par"]
        result = await orch._execute_node(node, state, ctx)
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"w1": "done", "w2": "done"}
        assert result.execution_time_ms == 2.0  # max of the two


class TestHandleInterrupt:
    """Tests for _handle_interrupt."""

    async def test_no_handler_returns_state(self):
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeType,
        )

        orch = _make_orchestrator(hitl_enabled=False)
        node = GraphNode(id="n", name="N", node_type=NodeType.FUNCTION)
        state = GraphState(data={"key": "val"})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        result = await orch._handle_interrupt(node, state, ctx, before=True)
        assert result.data["key"] == "val"

    async def test_abort_raises_orchestration_error(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import OrchestrationError
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.hitl_integration import (
            HITLAction,
            HITLResponse,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeType,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            hitl_enabled=True,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)

        mock_request = MagicMock()
        orch.hitl_handler.create_interrupt = AsyncMock(return_value=mock_request)
        orch.hitl_handler.handle_interrupt = AsyncMock(
            return_value=HITLResponse(
                request_id="r1",
                action=HITLAction.ABORT,
                reason="user said no",
            )
        )

        node = GraphNode(id="n", name="N", node_type=NodeType.FUNCTION)
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        with pytest.raises(OrchestrationError, match="aborted"):
            await orch._handle_interrupt(node, state, ctx, before=True)

    async def test_modify_returns_modified_state(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.hitl_integration import (
            HITLAction,
            HITLResponse,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            ExecutionContext,
            ExecutionStatus,
            GraphNode,
            GraphState,
            NodeType,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            hitl_enabled=True,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)

        modified = GraphState(data={"modified": True})
        mock_request = MagicMock()
        orch.hitl_handler.create_interrupt = AsyncMock(return_value=mock_request)
        orch.hitl_handler.handle_interrupt = AsyncMock(
            return_value=HITLResponse(
                request_id="r1",
                action=HITLAction.MODIFY,
                modified_state=modified,
            )
        )

        node = GraphNode(id="n", name="N", node_type=NodeType.FUNCTION)
        state = GraphState(data={})
        ctx = ExecutionContext(
            graph_id="g1",
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        result = await orch._handle_interrupt(node, state, ctx, before=False)
        assert result.data["modified"] is True


class TestResumeFromCheckpoint:
    """Tests for resume_from_checkpoint."""

    async def test_no_checkpoint_manager_raises(self):
        from enhanced_agent_bus.langgraph_orchestration.exceptions import OrchestrationError

        orch = _make_orchestrator(enable_checkpoints=False)
        with pytest.raises(OrchestrationError, match="not enabled"):
            await orch.resume_from_checkpoint("cp-1", "w-1")

    async def test_resume_delegates_to_run(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestrator,
            GraphOrchestratorConfig,
        )
        from enhanced_agent_bus.langgraph_orchestration.models import (
            Checkpoint,
            CheckpointStatus,
            ExecutionStatus,
            GraphState,
        )

        config = GraphOrchestratorConfig(
            persist_state=True,
            enable_checkpoints=True,
            hitl_enabled=False,
        )
        orch = GraphOrchestrator(graph=_make_graph_definition(), config=config)

        mock_state = GraphState(data={"restored": True})
        mock_checkpoint = Checkpoint(
            workflow_id="w1",
            run_id="r1",
            node_id="start",
            step_index=3,
            state=mock_state,
        )
        orch.checkpoint_manager.restore_checkpoint = AsyncMock(
            return_value=(mock_checkpoint, mock_state)
        )

        # Mock run to avoid full execution
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.COMPLETED
        orch.run = AsyncMock(return_value=mock_result)

        result = await orch.resume_from_checkpoint("cp-1", "w-1")
        orch.run.assert_called_once()
        call_kwargs = orch.run.call_args[1]
        assert call_kwargs["initial_state"] == mock_state
        assert call_kwargs["metadata"]["resumed_from_checkpoint"] == "cp-1"


class TestGetMetrics:
    """Tests for get_metrics."""

    def test_empty_metrics(self):
        orch = _make_orchestrator()
        m = orch.get_metrics()
        assert m["executions"] == 0
        assert "constitutional_hash" in m

    def test_populated_metrics(self):
        orch = _make_orchestrator()
        orch._execution_times = [1.0, 2.0, 3.0, 4.0, 5.0]
        orch._executions = 5
        m = orch.get_metrics()
        assert m["executions"] == 5
        assert m["avg_execution_time_ms"] == 3.0
        assert m["min_execution_time_ms"] == 1.0
        assert m["max_execution_time_ms"] == 5.0

    def test_single_execution_metrics(self):
        orch = _make_orchestrator()
        orch._execution_times = [42.0]
        orch._executions = 1
        m = orch.get_metrics()
        assert m["p95_execution_time_ms"] == 42.0
        assert m["p99_execution_time_ms"] == 42.0


class TestCreateGraphOrchestrator:
    """Tests for the factory function."""

    def test_factory_default(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            create_graph_orchestrator,
        )

        graph = _make_graph_definition()
        orch = create_graph_orchestrator(graph)
        assert orch is not None
        assert orch.persistence is not None

    def test_factory_with_config(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            GraphOrchestratorConfig,
            create_graph_orchestrator,
        )

        graph = _make_graph_definition()
        config = GraphOrchestratorConfig(
            persist_state=False,
            enable_checkpoints=False,
            hitl_enabled=False,
        )
        orch = create_graph_orchestrator(graph, config=config)
        assert orch.persistence is None
        assert orch.checkpoint_manager is None

    def test_factory_with_custom_hash(self):
        from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
            create_graph_orchestrator,
        )

        graph = _make_graph_definition()
        orch = create_graph_orchestrator(graph, constitutional_hash="standalone")
        assert orch.constitutional_hash == "standalone"


class TestRunMetricsCalculation:
    """Tests for p50/p99 calculation paths in run()."""

    async def test_multiple_node_results_metrics(self):
        """Exercise the sorted_times branch with len > 1."""
        from enhanced_agent_bus.langgraph_orchestration.models import (
            EdgeType,
            GraphEdge,
            GraphNode,
            NodeResult,
            NodeStatus,
            NodeType,
        )

        nodes = [
            GraphNode(id="s", name="S", node_type=NodeType.START),
            GraphNode(id="a", name="A", node_type=NodeType.FUNCTION),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        edges = [
            GraphEdge(source_node_id="s", target_node_id="a", edge_type=EdgeType.SEQUENTIAL),
            GraphEdge(source_node_id="a", target_node_id="end", edge_type=EdgeType.SEQUENTIAL),
        ]
        graph = _make_graph_definition(nodes=nodes, edges=edges, start_node_id="s")
        orch = _make_orchestrator(graph=graph)

        call_idx = 0
        times = [1.0, 2.0, 3.0]

        async def mock_execute(node, state, ctx):
            nonlocal call_idx
            t = times[call_idx % len(times)]
            call_idx += 1
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.COMPLETED,
                output_state={"idx": call_idx},
                execution_time_ms=t,
            )

        orch.executor.execute = mock_execute
        result = await orch.run()
        # With 3 nodes (s, a, end), we have execution times [1.0, 2.0, 3.0]
        assert result.p50_node_time_ms is not None
        assert result.p99_node_time_ms is not None


# ============================================================================
# HybridContextManager tests
# ============================================================================


class TestHybridContextConfig:
    """Tests for HybridContextConfig."""

    def test_default_config(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import HybridContextConfig

        config = HybridContextConfig()
        assert config.mamba_d_model == 256
        assert config.default_mode.value == "auto"

    def test_invalid_hash_raises(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import HybridContextConfig

        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            HybridContextConfig(constitutional_hash="bad_hash")


class TestSharedAttentionProcessor:
    """Tests for SharedAttentionProcessor."""

    def test_init_default(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import (
            SharedAttentionProcessor,
        )

        proc = SharedAttentionProcessor()
        assert proc.d_model == 256
        assert proc.num_heads == 8

    def test_invalid_hash_raises(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import (
            SharedAttentionProcessor,
        )

        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            SharedAttentionProcessor(constitutional_hash="wrong")

    def test_forward_with_non_tensor_returns_input(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import (
            SharedAttentionProcessor,
        )

        proc = SharedAttentionProcessor()
        # plain python object -- not torch or numpy
        with (
            patch(
                "enhanced_agent_bus.context_memory.hybrid_context_manager.TORCH_AVAILABLE", False
            ),
            patch(
                "enhanced_agent_bus.context_memory.hybrid_context_manager.NUMPY_AVAILABLE", False
            ),
        ):
            result = proc.forward("not a tensor")
            assert result == "not a tensor"

    def test_forward_numpy(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")

        from enhanced_agent_bus.context_memory.hybrid_context_manager import (
            SharedAttentionProcessor,
        )

        proc = SharedAttentionProcessor()
        x = np.random.randn(1, 4, 256).astype(np.float32)
        with patch(
            "enhanced_agent_bus.context_memory.hybrid_context_manager.TORCH_AVAILABLE", False
        ):
            result = proc.forward(x, critical_positions=[0, 2])
        assert result.shape == (1, 4, 256)

    def test_forward_numpy_2d(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")

        from enhanced_agent_bus.context_memory.hybrid_context_manager import (
            SharedAttentionProcessor,
        )

        proc = SharedAttentionProcessor()
        x = np.random.randn(4, 256).astype(np.float32)
        with patch(
            "enhanced_agent_bus.context_memory.hybrid_context_manager.TORCH_AVAILABLE", False
        ):
            result = proc.forward(x)
        assert result.shape == (1, 4, 256)


class TestHybridContextManager:
    """Tests for HybridContextManager."""

    def _make_window(self, chunks=None, total_tokens=100):
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
            ContextWindow,
        )

        if chunks is None:
            chunks = [
                ContextChunk(
                    content="Hello world",
                    context_type=ContextType.WORKING,
                    priority=ContextPriority.MEDIUM,
                    token_count=total_tokens,
                )
            ]
        return ContextWindow(chunks=chunks, window_id="test-win")

    def _make_manager(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import (
            HybridContextConfig,
            HybridContextManager,
        )

        config = HybridContextConfig(enable_caching=True)
        return HybridContextManager(config=config)

    def test_init(self):
        mgr = self._make_manager()
        assert mgr is not None
        assert mgr._metrics["ssm_calls"] == 0

    def test_invalid_hash_raises(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import HybridContextManager

        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            HybridContextManager(constitutional_hash="bad")

    async def test_process_ssm_only(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode

        mgr = self._make_manager()
        window = self._make_window(total_tokens=100)
        result = await mgr.process_context_window(window, mode=ProcessingMode.SSM_ONLY)
        assert result.processing_mode == ProcessingMode.SSM_ONLY
        assert result.ssm_processed_tokens > 0
        assert mgr._metrics["ssm_calls"] == 1

    async def test_process_attention_only(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode

        mgr = self._make_manager()
        window = self._make_window(total_tokens=50)
        result = await mgr.process_context_window(window, mode=ProcessingMode.ATTENTION_ONLY)
        assert result.processing_mode == ProcessingMode.ATTENTION_ONLY
        assert result.attention_processed_tokens > 0

    async def test_process_hybrid_with_critical_and_regular(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        chunks = [
            ContextChunk(
                content="Constitutional rule",
                context_type=ContextType.CONSTITUTIONAL,
                priority=ContextPriority.CRITICAL,
                token_count=50,
                is_critical=True,
            ),
            ContextChunk(
                content="Regular content",
                context_type=ContextType.WORKING,
                priority=ContextPriority.LOW,
                token_count=50,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.HYBRID)
        assert result.processing_mode == ProcessingMode.HYBRID
        assert result.critical_sections_count == 1
        assert mgr._metrics["hybrid_calls"] == 1

    async def test_process_hybrid_only_critical(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        chunks = [
            ContextChunk(
                content="Critical only",
                context_type=ContextType.CONSTITUTIONAL,
                priority=ContextPriority.CRITICAL,
                token_count=50,
                is_critical=True,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.HYBRID)
        assert result.processing_mode == ProcessingMode.HYBRID

    async def test_process_hybrid_only_regular(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        chunks = [
            ContextChunk(
                content="Regular only",
                context_type=ContextType.WORKING,
                priority=ContextPriority.LOW,
                token_count=50,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.HYBRID)
        assert result.processing_mode == ProcessingMode.HYBRID

    async def test_cache_hit(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode

        mgr = self._make_manager()
        window = self._make_window(total_tokens=50)

        # First call: cache miss
        r1 = await mgr.process_context_window(window, mode=ProcessingMode.SSM_ONLY)
        assert not r1.cache_hit
        assert mgr._metrics["cache_misses"] == 1

        # Second call: cache hit
        r2 = await mgr.process_context_window(window, mode=ProcessingMode.SSM_ONLY)
        assert r2.cache_hit
        assert mgr._metrics["cache_hits"] == 1

    async def test_auto_mode_constitutional(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        chunks = [
            ContextChunk(
                content="Constitutional",
                context_type=ContextType.CONSTITUTIONAL,
                priority=ContextPriority.CRITICAL,
                token_count=50,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.AUTO)
        # Constitutional always -> HYBRID
        assert result.processing_mode == ProcessingMode.HYBRID

    async def test_auto_mode_critical_chunks(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        chunks = [
            ContextChunk(
                content="Critical but not constitutional",
                context_type=ContextType.WORKING,
                priority=ContextPriority.HIGH,
                token_count=50,
                is_critical=True,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.AUTO)
        assert result.processing_mode == ProcessingMode.HYBRID

    async def test_auto_mode_long_sequence_ssm(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        # Over ssm_threshold_tokens (4096)
        chunks = [
            ContextChunk(
                content="Long" * 1000,
                context_type=ContextType.WORKING,
                priority=ContextPriority.LOW,
                token_count=5000,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.AUTO)
        assert result.processing_mode == ProcessingMode.SSM_ONLY

    async def test_auto_mode_short_attention(self):
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        chunks = [
            ContextChunk(
                content="Short text",
                context_type=ContextType.WORKING,
                priority=ContextPriority.LOW,
                token_count=100,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.AUTO)
        assert result.processing_mode == ProcessingMode.ATTENTION_ONLY

    def test_clear_cache(self):
        mgr = self._make_manager()
        mgr._cache["k1"] = ("data", datetime.now(UTC))
        mgr._cache["k2"] = ("data", datetime.now(UTC))
        count = mgr.clear_cache()
        assert count == 2
        assert len(mgr._cache) == 0

    def test_get_metrics(self):
        mgr = self._make_manager()
        m = mgr.get_metrics()
        assert "ssm_calls" in m
        assert "mamba_metrics" in m
        assert "cache_size" in m

    def test_reset_state(self):
        mgr = self._make_manager()
        mgr._cache["k1"] = ("data", datetime.now(UTC))
        mgr.reset_state()
        assert len(mgr._cache) == 0

    async def test_attention_only_with_critical_chunks(self):
        """Exercise the critical_positions path in _process_attention_only."""
        from enhanced_agent_bus.context_memory.hybrid_context_manager import ProcessingMode
        from enhanced_agent_bus.context_memory.models import (
            ContextChunk,
            ContextPriority,
            ContextType,
        )

        mgr = self._make_manager()
        chunks = [
            ContextChunk(
                content="Critical section",
                context_type=ContextType.WORKING,
                priority=ContextPriority.HIGH,
                token_count=10,
                is_critical=True,
            ),
            ContextChunk(
                content="Normal section",
                context_type=ContextType.WORKING,
                priority=ContextPriority.LOW,
                token_count=10,
            ),
        ]
        window = self._make_window(chunks=chunks)
        result = await mgr.process_context_window(window, mode=ProcessingMode.ATTENTION_ONLY)
        assert result.processing_mode == ProcessingMode.ATTENTION_ONLY
        assert result.metadata.get("critical_positions", 0) > 0


# ============================================================================
# fix_imports.py tests
# ============================================================================


class TestFixImports:
    """Tests for packages/acgs-lite/src/fix_imports.py."""

    def _run_fix_imports_in_tmpdir(self, files: dict[str, str]) -> dict[str, str]:
        """
        Create temp files matching the paths that fix_imports.py expects,
        run fix_imports via importlib, then return the resulting file contents.

        Args:
            files: mapping of relative path -> content

        Returns:
            mapping of relative path -> modified content
        """
        original_cwd = os.getcwd()
        tmpdir = tempfile.mkdtemp()
        try:
            # Create all directories and files
            for relpath, content in files.items():
                fullpath = os.path.join(tmpdir, relpath)
                os.makedirs(os.path.dirname(fullpath), exist_ok=True)
                with open(fullpath, "w") as f:
                    f.write(content)

            os.chdir(tmpdir)

            # Load the fix_imports module via importlib to avoid path conflicts
            spec = importlib.util.spec_from_file_location(
                "fix_imports_test",
                os.path.join(
                    original_cwd,
                    "packages/acgs-lite/src/fix_imports.py",
                ),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Read back modified files
            result = {}
            for relpath in files:
                fullpath = os.path.join(tmpdir, relpath)
                if os.path.exists(fullpath):
                    with open(fullpath) as f:
                        result[relpath] = f.read()
            return result
        finally:
            os.chdir(original_cwd)

    def test_analytics_gets_rule_import(self):
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\n\ndef analyze():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\n\nclass Rule:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\n\ndef template():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\n\nclass RuleSnapshot:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)

        # analytics.py should now contain "from .core import Rule"
        assert (
            "from .core import Rule"
            in result["packages/acgs-lite/src/acgs_lite/constitution/analytics.py"]
        )

    def test_analytics_idempotent(self):
        """If analytics already has the import, it should not be added again."""
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\nfrom .core import Rule\n\ndef analyze():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\n\nclass Rule:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\n\ndef template():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\n\nclass RuleSnapshot:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/constitution/analytics.py"]
        # Should appear exactly once
        assert content.count("from .core import Rule") == 1

    def test_core_gets_analytics_import(self):
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\n\ndef analyze():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\n\nclass Rule:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\n\ndef template():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\n\nclass RuleSnapshot:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/constitution/core.py"]
        assert "from .analytics import" in content

    def test_core_idempotent(self):
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\nfrom .analytics import _KW_NEGATIVE_RE\n\n"
                "class Rule:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\n\ndef template():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\n\nclass RuleSnapshot:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/constitution/core.py"]
        assert content.count("from .analytics import") == 1

    def test_templates_gets_core_import(self):
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\nfrom .analytics import _KW_NEGATIVE_RE\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\n\ndef template():\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\n\nclass RuleSnapshot:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/constitution/templates.py"]
        assert "from .core import" in content

    def test_versioning_gets_type_checking_import(self):
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\nfrom .analytics import _KW_NEGATIVE_RE\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\n\nclass RuleSnapshot:\n    pass\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/constitution/versioning.py"]
        assert "TYPE_CHECKING" in content
        assert "from .core import Rule" in content

    def test_engine_batch_broken_try_block_fixed(self):
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\nfrom .analytics import _KW_NEGATIVE_RE\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "try:\n\nfrom typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
                "# Optional Aho-Corasick C extension for O(n) keyword scanning\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/engine/batch.py"]
        # The broken try block should be removed
        assert "try:\n\nfrom typing" not in content
        assert "from typing import Any" in content
        # The Aho-Corasick comment should be removed
        assert "Aho-Corasick" not in content

    def test_engine_core_broken_try_fixed(self):
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\nfrom .analytics import _KW_NEGATIVE_RE\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\ntry:\n\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/engine/core.py"]
        assert "try:\n\nfrom .rust" not in content
        assert "from .rust" in content

    def test_core_rule_snapshot_replacement(self):
        """Test that RuleSnapshot.from_rule( gets inline import."""
        files = {
            "packages/acgs-lite/src/acgs_lite/constitution/analytics.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/core.py": (
                "from typing import Any\n\n"
                "class Rule:\n"
                "    def snapshot(self):\n"
                "        return RuleSnapshot.from_rule(self)\n"
                "    def build(self):\n"
                "        b = ConstitutionBuilder(\n"
                "            name='test'\n"
                "        )\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/templates.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/constitution/versioning.py": (
                "from typing import Any\nfrom .core import Rule\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/batch.py": (
                "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult\n"
            ),
            "packages/acgs-lite/src/acgs_lite/engine/core.py": (
                "from typing import Any\nfrom .rust import something\n"
            ),
        }
        result = self._run_fix_imports_in_tmpdir(files)
        content = result["packages/acgs-lite/src/acgs_lite/constitution/core.py"]
        assert "from .versioning import RuleSnapshot" in content
        assert "from .templates import ConstitutionBuilder" in content
