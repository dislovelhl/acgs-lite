"""
Tests for langgraph_orchestration/graph_orchestrator.py

Covers:
- GraphOrchestratorConfig defaults
- GraphOrchestrator initialization and graph validation
- run() happy path, error paths
- _execute_graph, _get_next_node, _execute_node
- _handle_interrupt
- get_metrics
- resume_from_checkpoint
- create_graph_orchestrator factory
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.langgraph_orchestration.exceptions import (
    CyclicDependencyError,
    GraphValidationError,
    OrchestrationError,
)
from enhanced_agent_bus.langgraph_orchestration.graph_orchestrator import (
    GraphOrchestrator,
    GraphOrchestratorConfig,
    create_graph_orchestrator,
)
from enhanced_agent_bus.langgraph_orchestration.models import (
    ConditionalEdge,
    EdgeType,
    ExecutionResult,
    ExecutionStatus,
    GraphDefinition,
    GraphEdge,
    GraphNode,
    GraphState,
    NodeResult,
    NodeStatus,
    NodeType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_graph(
    *,
    node_count: int = 2,
    self_loop: bool = False,
    self_loop_type: EdgeType = EdgeType.SEQUENTIAL,
) -> GraphDefinition:
    """Create a minimal valid graph for testing."""
    nodes = []
    edges = []
    for i in range(node_count):
        ntype = (
            NodeType.START
            if i == 0
            else (NodeType.END if i == node_count - 1 else NodeType.FUNCTION)
        )
        nodes.append(
            GraphNode(
                id=f"node_{i}",
                name=f"Node {i}",
                node_type=ntype,
                function_path=f"test.func_{i}",
            )
        )

    for i in range(node_count - 1):
        edges.append(
            GraphEdge(
                source_node_id=f"node_{i}",
                target_node_id=f"node_{i + 1}",
                edge_type=EdgeType.SEQUENTIAL,
            )
        )

    if self_loop:
        edges.append(
            GraphEdge(
                source_node_id="node_0",
                target_node_id="node_0",
                edge_type=self_loop_type,
            )
        )

    return GraphDefinition(
        name="test-graph",
        nodes=nodes,
        edges=edges,
        start_node_id="node_0",
        end_node_ids=[f"node_{node_count - 1}"],
    )


def _make_node_result(node_id: str = "node_0", success: bool = True) -> NodeResult:
    return NodeResult(
        node_id=node_id,
        status=NodeStatus.COMPLETED if success else NodeStatus.FAILED,
        output_state={"result": "ok"} if success else None,
        execution_time_ms=1.0,
        constitutional_validated=True,
    )


def _build_orchestrator(
    graph: GraphDefinition | None = None,
    config: GraphOrchestratorConfig | None = None,
) -> GraphOrchestrator:
    """Build orchestrator with mocked executor."""
    g = graph or _simple_graph()
    cfg = config or GraphOrchestratorConfig(
        enable_checkpoints=False,
        hitl_enabled=False,
        persist_state=False,
    )

    executor = AsyncMock()
    executor.execute = AsyncMock(return_value=_make_node_result())
    executor.register_function = MagicMock()

    return GraphOrchestrator(
        graph=g,
        config=cfg,
        executor=executor,
        persistence=None,
        checkpoint_manager=None,
        hitl_handler=None,
    )


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestGraphOrchestratorConfig:
    def test_defaults(self):
        cfg = GraphOrchestratorConfig()
        assert cfg.max_iterations == 100
        assert cfg.global_timeout_ms == 30000.0
        assert cfg.constitutional_validation is True
        assert cfg.hitl_enabled is True
        assert cfg.parallel_execution is True

    def test_custom_values(self):
        cfg = GraphOrchestratorConfig(max_iterations=5, hitl_enabled=False)
        assert cfg.max_iterations == 5
        assert cfg.hitl_enabled is False


# ---------------------------------------------------------------------------
# Initialization & validation
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_valid_graph(self):
        orch = _build_orchestrator()
        assert orch.graph.name == "test-graph"
        assert len(orch._node_map) == 2

    def test_invalid_graph_raises(self):
        bad_graph = GraphDefinition(
            name="bad",
            nodes=[],
            edges=[],
            start_node_id=None,
            end_node_ids=[],
        )
        with pytest.raises(GraphValidationError):
            _build_orchestrator(graph=bad_graph)

    def test_self_loop_sequential_raises(self):
        g = _simple_graph(self_loop=True, self_loop_type=EdgeType.SEQUENTIAL)
        with pytest.raises(CyclicDependencyError):
            _build_orchestrator(graph=g)

    def test_self_loop_allowed(self):
        g = _simple_graph(self_loop=True, self_loop_type=EdgeType.LOOP)
        orch = _build_orchestrator(graph=g)
        assert orch is not None

    def test_edge_maps_built(self):
        orch = _build_orchestrator()
        assert "node_0" in orch._outgoing_edges
        assert "node_1" in orch._incoming_edges


# ---------------------------------------------------------------------------
# run() tests
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        orch = _build_orchestrator()
        result = await orch.run(input_data={"key": "value"})
        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_execution_time_ms > 0
        assert result.constitutional_validated is True

    @pytest.mark.asyncio
    async def test_with_initial_state(self):
        orch = _build_orchestrator()
        state = GraphState(data={"init": True})
        result = await orch.run(initial_state=state)
        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_records_metrics(self):
        orch = _build_orchestrator()
        await orch.run(input_data={})
        assert orch._executions == 1
        assert len(orch._execution_times) == 1

    @pytest.mark.asyncio
    async def test_run_error_handling(self):
        orch = _build_orchestrator()
        orch.executor.execute = AsyncMock(side_effect=RuntimeError("node failure"))
        result = await orch.run(input_data={})
        assert result.status == ExecutionStatus.FAILED
        assert result.error == "node failure"

    @pytest.mark.asyncio
    async def test_run_with_persistence(self):
        orch = _build_orchestrator()
        persistence = AsyncMock()
        persistence.save_state = AsyncMock()
        persistence.save_execution_result = AsyncMock()
        orch.persistence = persistence
        result = await orch.run(input_data={})
        assert result.status == ExecutionStatus.COMPLETED
        persistence.save_execution_result.assert_called_once()


# ---------------------------------------------------------------------------
# _get_next_node tests
# ---------------------------------------------------------------------------


class TestGetNextNode:
    @pytest.mark.asyncio
    async def test_sequential_edge(self):
        orch = _build_orchestrator()
        state = GraphState(data={})
        next_id = await orch._get_next_node("node_0", state)
        assert next_id == "node_1"

    @pytest.mark.asyncio
    async def test_no_outgoing_edges(self):
        orch = _build_orchestrator()
        state = GraphState(data={})
        next_id = await orch._get_next_node("node_1", state)
        assert next_id is None

    @pytest.mark.asyncio
    async def test_conditional_edge(self):
        g = _simple_graph(node_count=3)
        g.conditional_edges = [
            ConditionalEdge(
                source_node_id="node_0",
                conditions={"branch_a": "node_2"},
                default_target="node_1",
                condition_function_path="test.condition",
            )
        ]
        orch = _build_orchestrator(graph=g)
        orch.conditional_executor = AsyncMock()
        orch.conditional_executor.route = AsyncMock(return_value="node_2")
        state = GraphState(data={})
        next_id = await orch._get_next_node("node_0", state)
        assert next_id == "node_2"


# ---------------------------------------------------------------------------
# _get_node_or_raise tests
# ---------------------------------------------------------------------------


class TestGetNodeOrRaise:
    def test_existing_node(self):
        orch = _build_orchestrator()
        node = orch._get_node_or_raise("node_0")
        assert node.id == "node_0"

    def test_missing_node_raises(self):
        orch = _build_orchestrator()
        with pytest.raises(OrchestrationError):
            orch._get_node_or_raise("nonexistent")


# ---------------------------------------------------------------------------
# get_metrics tests
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_empty_metrics(self):
        orch = _build_orchestrator()
        m = orch.get_metrics()
        assert m["executions"] == 0
        assert "constitutional_hash" in m

    @pytest.mark.asyncio
    async def test_metrics_after_run(self):
        orch = _build_orchestrator()
        await orch.run(input_data={})
        m = orch.get_metrics()
        assert m["executions"] == 1
        assert "avg_execution_time_ms" in m
        assert "p50_execution_time_ms" in m

    @pytest.mark.asyncio
    async def test_metrics_after_multiple_runs(self):
        orch = _build_orchestrator()
        await orch.run(input_data={})
        await orch.run(input_data={})
        m = orch.get_metrics()
        assert m["executions"] == 2


# ---------------------------------------------------------------------------
# register_function tests
# ---------------------------------------------------------------------------


class TestRegisterFunction:
    def test_register_function(self):
        orch = _build_orchestrator()
        func = AsyncMock()
        orch.register_function("test.path", func)
        orch.executor.register_function.assert_called_with("test.path", func)


# ---------------------------------------------------------------------------
# resume_from_checkpoint tests
# ---------------------------------------------------------------------------


class TestResumeFromCheckpoint:
    @pytest.mark.asyncio
    async def test_no_checkpoint_manager_raises(self):
        orch = _build_orchestrator()
        orch.checkpoint_manager = None
        with pytest.raises(OrchestrationError):
            await orch.resume_from_checkpoint("cp-1", "wf-1")

    @pytest.mark.asyncio
    async def test_resume_delegates_to_run(self):
        orch = _build_orchestrator()
        checkpoint = MagicMock()
        checkpoint.node_id = "node_0"
        checkpoint.step_index = 3
        state = GraphState(data={"resumed": True})

        cm = AsyncMock()
        cm.restore_checkpoint = AsyncMock(return_value=(checkpoint, state))
        orch.checkpoint_manager = cm

        result = await orch.resume_from_checkpoint("cp-1", "wf-1")
        assert result.status == ExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestFactory:
    def test_create_graph_orchestrator(self):
        g = _simple_graph()
        orch = create_graph_orchestrator(graph=g)
        assert isinstance(orch, GraphOrchestrator)

    def test_create_graph_orchestrator_custom_config(self):
        g = _simple_graph()
        cfg = GraphOrchestratorConfig(max_iterations=10, hitl_enabled=False)
        orch = create_graph_orchestrator(graph=g, config=cfg)
        assert orch.config.max_iterations == 10
