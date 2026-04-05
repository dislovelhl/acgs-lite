"""
ACGS-2 LangGraph Orchestration - Model Tests
Constitutional Hash: 608508a9bd224290
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.langgraph_orchestration.models import (
    Checkpoint,
    CheckpointStatus,
    ConditionalEdge,
    EdgeType,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    GraphConfig,
    GraphDefinition,
    GraphEdge,
    GraphNode,
    GraphState,
    InterruptRequest,
    InterruptResponse,
    InterruptType,
    NodeResult,
    NodeStatus,
    NodeType,
    StateDelta,
    StateSnapshot,
)


class TestGraphState:
    """Tests for GraphState model."""

    def test_create_empty_state(self):
        """Test creating empty state."""
        state = GraphState()
        assert state.data == {}
        assert state.version == 0
        assert state.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_state_with_data(self):
        """Test creating state with initial data."""
        state = GraphState(data={"key": "value"})
        assert state.data == {"key": "value"}
        assert state.version == 0

    def test_get_value(self):
        """Test getting values from state."""
        state = GraphState(data={"key": "value"})
        assert state.get("key") == "value"
        assert state.get("missing") is None
        assert state.get("missing", "default") == "default"

    def test_set_value(self):
        """Test setting values creates new state."""
        state = GraphState(data={"key": "value"})
        new_state = state.set("key2", "value2", "node1")

        assert state.data == {"key": "value"}  # Original unchanged
        assert new_state.data == {"key": "value", "key2": "value2"}
        assert new_state.version == 1
        assert new_state.last_node_id == "node1"

    def test_merge_updates(self):
        """Test merging updates into state."""
        state = GraphState(data={"a": 1})
        new_state = state.merge({"b": 2, "c": 3}, "node1")

        assert new_state.data == {"a": 1, "b": 2, "c": 3}
        assert new_state.version == 1

    def test_mutation_history(self):
        """Test mutation history tracking."""
        state = GraphState()
        state = state.set("key1", "value1", "node1")
        state = state.set("key2", "value2", "node2")

        assert len(state.mutation_history) == 2
        assert state.mutation_history[0]["key"] == "key1"
        assert state.mutation_history[1]["key"] == "key2"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        state = GraphState(data={"key": "value"}, version=5)
        result = state.to_dict()

        assert result["data"] == {"key": "value"}
        assert result["version"] == 5
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "data": {"key": "value"},
            "version": 3,
            "last_node_id": "node1",
        }
        state = GraphState.from_dict(data)

        assert state.data == {"key": "value"}
        assert state.version == 3
        assert state.last_node_id == "node1"


class TestGraphNode:
    """Tests for GraphNode model."""

    def test_create_basic_node(self):
        """Test creating basic node."""
        node = GraphNode(
            id="node1",
            name="Test Node",
            node_type=NodeType.FUNCTION,
        )

        assert node.id == "node1"
        assert node.name == "Test Node"
        assert node.node_type == NodeType.FUNCTION
        assert node.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_node_with_function(self):
        """Test creating node with function path."""
        node = GraphNode(
            id="node1",
            name="Function Node",
            node_type=NodeType.FUNCTION,
            function_path="module.function",
        )

        assert node.function_path == "module.function"

    def test_node_timeout_default(self):
        """Test node timeout default value."""
        node = GraphNode(id="node1", name="Node", node_type=NodeType.FUNCTION)
        assert node.timeout_ms == 5000.0

    def test_node_retry_default(self):
        """Test node retry default value."""
        node = GraphNode(id="node1", name="Node", node_type=NodeType.FUNCTION)
        assert node.retry_count == 3

    def test_node_interrupt_config(self):
        """Test node interrupt configuration."""
        node = GraphNode(
            id="node1",
            name="Node",
            node_type=NodeType.FUNCTION,
            interrupt_before=True,
            interrupt_after=True,
        )

        assert node.interrupt_before is True
        assert node.interrupt_after is True

    def test_node_maci_role(self):
        """Test node MACI role requirement."""
        node = GraphNode(
            id="node1",
            name="Node",
            node_type=NodeType.FUNCTION,
            requires_maci_role="executive",
        )

        assert node.requires_maci_role == "executive"


class TestGraphEdge:
    """Tests for GraphEdge model."""

    def test_create_sequential_edge(self):
        """Test creating sequential edge."""
        edge = GraphEdge(
            source_node_id="node1",
            target_node_id="node2",
        )

        assert edge.source_node_id == "node1"
        assert edge.target_node_id == "node2"
        assert edge.edge_type == EdgeType.SEQUENTIAL

    def test_create_conditional_edge(self):
        """Test creating conditional edge."""
        edge = GraphEdge(
            source_node_id="node1",
            target_node_id="node2",
            edge_type=EdgeType.CONDITIONAL,
            condition="key=value",
        )

        assert edge.edge_type == EdgeType.CONDITIONAL
        assert edge.condition == "key=value"


class TestConditionalEdge:
    """Tests for ConditionalEdge model."""

    def test_create_conditional_edge(self):
        """Test creating conditional edge with conditions."""
        edge = ConditionalEdge(
            source_node_id="node1",
            conditions={
                "success": "node2",
                "failure": "node3",
            },
            default_target="node4",
        )

        assert edge.source_node_id == "node1"
        assert edge.conditions["success"] == "node2"
        assert edge.conditions["failure"] == "node3"
        assert edge.default_target == "node4"


class TestGraphDefinition:
    """Tests for GraphDefinition model."""

    def test_create_empty_graph(self):
        """Test creating empty graph."""
        graph = GraphDefinition(name="Test Graph")

        assert graph.name == "Test Graph"
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_create_graph_with_nodes(self):
        """Test creating graph with nodes."""
        nodes = [
            GraphNode(id="start", name="Start", node_type=NodeType.START),
            GraphNode(id="end", name="End", node_type=NodeType.END),
        ]
        graph = GraphDefinition(
            name="Test Graph",
            nodes=nodes,
            start_node_id="start",
            end_node_ids=["end"],
        )

        assert len(graph.nodes) == 2
        assert graph.start_node_id == "start"

    def test_get_node(self):
        """Test getting node by ID."""
        nodes = [
            GraphNode(id="node1", name="Node 1", node_type=NodeType.FUNCTION),
        ]
        graph = GraphDefinition(name="Test", nodes=nodes)

        assert graph.get_node("node1") is not None
        assert graph.get_node("nonexistent") is None

    def test_get_outgoing_edges(self):
        """Test getting outgoing edges."""
        nodes = [
            GraphNode(id="node1", name="Node 1", node_type=NodeType.FUNCTION),
            GraphNode(id="node2", name="Node 2", node_type=NodeType.FUNCTION),
        ]
        edges = [
            GraphEdge(source_node_id="node1", target_node_id="node2"),
        ]
        graph = GraphDefinition(name="Test", nodes=nodes, edges=edges)

        outgoing = graph.get_outgoing_edges("node1")
        assert len(outgoing) == 1
        assert outgoing[0].target_node_id == "node2"

    def test_validate_missing_start_node(self):
        """Test validation catches missing start node."""
        graph = GraphDefinition(name="Test")
        errors = graph.validate_graph()

        assert any("start node" in e.lower() for e in errors)

    def test_validate_missing_end_nodes(self):
        """Test validation catches missing end nodes."""
        nodes = [
            GraphNode(id="start", name="Start", node_type=NodeType.START),
        ]
        graph = GraphDefinition(
            name="Test",
            nodes=nodes,
            start_node_id="start",
        )
        errors = graph.validate_graph()

        assert any("end node" in e.lower() for e in errors)

    def test_validate_invalid_edge_reference(self):
        """Test validation catches invalid edge references."""
        nodes = [
            GraphNode(id="node1", name="Node 1", node_type=NodeType.FUNCTION),
        ]
        edges = [
            GraphEdge(source_node_id="node1", target_node_id="nonexistent"),
        ]
        graph = GraphDefinition(
            name="Test",
            nodes=nodes,
            edges=edges,
            start_node_id="node1",
            end_node_ids=["node1"],
        )
        errors = graph.validate_graph()

        assert any("nonexistent" in e for e in errors)


class TestNodeResult:
    """Tests for NodeResult model."""

    def test_create_success_result(self):
        """Test creating successful result."""
        result = NodeResult(
            node_id="node1",
            status=NodeStatus.COMPLETED,
            output_state={"result": "value"},
            execution_time_ms=10.5,
        )

        assert result.node_id == "node1"
        assert result.status == NodeStatus.COMPLETED
        assert result.success is True

    def test_create_failed_result(self):
        """Test creating failed result."""
        result = NodeResult(
            node_id="node1",
            status=NodeStatus.FAILED,
            error="Something went wrong",
        )

        assert result.status == NodeStatus.FAILED
        assert result.success is False
        assert result.error == "Something went wrong"


class TestExecutionContext:
    """Tests for ExecutionContext model."""

    def test_create_context(self):
        """Test creating execution context."""
        context = ExecutionContext(
            graph_id="graph1",
            tenant_id="tenant1",
        )

        assert context.graph_id == "graph1"
        assert context.tenant_id == "tenant1"
        assert context.status == ExecutionStatus.PENDING
        assert context.step_count == 0

    def test_context_has_workflow_id(self):
        """Test context generates workflow ID."""
        context = ExecutionContext(graph_id="graph1")
        assert context.workflow_id is not None
        assert len(context.workflow_id) > 0


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_create_completed_result(self):
        """Test creating completed result."""
        result = ExecutionResult(
            workflow_id="wf1",
            run_id="run1",
            status=ExecutionStatus.COMPLETED,
            total_execution_time_ms=100.0,
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_execution_time_ms == 100.0

    def test_create_failed_result(self):
        """Test creating failed result."""
        result = ExecutionResult(
            workflow_id="wf1",
            run_id="run1",
            status=ExecutionStatus.FAILED,
            error="Execution failed",
        )

        assert result.status == ExecutionStatus.FAILED
        assert result.error == "Execution failed"


class TestCheckpoint:
    """Tests for Checkpoint model."""

    def test_create_checkpoint(self):
        """Test creating checkpoint."""
        state = GraphState(data={"key": "value"})
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=5,
            state=state,
        )

        assert checkpoint.workflow_id == "wf1"
        assert checkpoint.node_id == "node1"
        assert checkpoint.step_index == 5
        assert checkpoint.status == CheckpointStatus.CREATED

    def test_checkpoint_constitutional_hash(self):
        """Test checkpoint has constitutional hash."""
        state = GraphState()
        checkpoint = Checkpoint(
            workflow_id="wf1",
            run_id="run1",
            node_id="node1",
            step_index=0,
            state=state,
        )

        assert checkpoint.constitutional_hash == CONSTITUTIONAL_HASH


class TestInterruptRequest:
    """Tests for InterruptRequest model."""

    def test_create_interrupt_request(self):
        """Test creating interrupt request."""
        state = GraphState(data={"key": "value"})
        request = InterruptRequest(
            workflow_id="wf1",
            node_id="node1",
            interrupt_type=InterruptType.HITL,
            reason="User approval required",
            current_state=state,
        )

        assert request.workflow_id == "wf1"
        assert request.interrupt_type == InterruptType.HITL
        assert request.reason == "User approval required"


class TestInterruptResponse:
    """Tests for InterruptResponse model."""

    def test_create_continue_response(self):
        """Test creating continue response."""
        response = InterruptResponse(
            request_id="req1",
            action="continue",
        )

        assert response.request_id == "req1"
        assert response.action == "continue"

    def test_create_modify_response(self):
        """Test creating modify response with new state."""
        new_state = GraphState(data={"modified": True})
        response = InterruptResponse(
            request_id="req1",
            action="modify",
            modified_state=new_state,
        )

        assert response.action == "modify"
        assert response.modified_state is not None


class TestGraphConfig:
    """Tests for GraphConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GraphConfig()

        assert config.max_iterations == 100
        assert config.enable_checkpoints is True
        assert config.constitutional_validation is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = GraphConfig(
            max_iterations=50,
            enable_checkpoints=False,
            hitl_enabled=False,
        )

        assert config.max_iterations == 50
        assert config.enable_checkpoints is False
        assert config.hitl_enabled is False
