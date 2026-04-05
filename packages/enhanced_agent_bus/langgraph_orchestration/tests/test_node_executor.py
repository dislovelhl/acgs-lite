"""
ACGS-2 LangGraph Orchestration - Node Executor Tests
Constitutional Hash: 608508a9bd224290
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    ConditionalEdge,
    GraphNode,
    GraphState,
    NodeResult,
    NodeStatus,
    NodeType,
)

from ..node_executor import (
    AsyncNodeExecutor,
    ConditionalNodeExecutor,
    NodeExecutor,
    ParallelNodeExecutor,
)


class TestAsyncNodeExecutor:
    """Tests for AsyncNodeExecutor."""

    def test_create_executor(self):
        """Test creating async executor."""
        executor = AsyncNodeExecutor()
        assert executor.default_timeout_ms == 5000.0
        assert executor.default_retries == 3
        assert executor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_executor_with_custom_settings(self):
        """Test creating executor with custom settings."""
        executor = AsyncNodeExecutor(
            default_timeout_ms=10000.0,
            default_retries=5,
            retry_backoff_factor=3.0,
        )
        assert executor.default_timeout_ms == 10000.0
        assert executor.default_retries == 5
        assert executor.retry_backoff_factor == 3.0

    def test_register_function(self):
        """Test registering a function."""
        executor = AsyncNodeExecutor()

        def my_func(state):
            return {"result": state.get("input", 0) * 2}

        executor.register_function("test.my_func", my_func)
        assert "test.my_func" in executor._function_cache

    def test_get_function_not_found(self):
        """Test getting function that doesn't exist."""
        executor = AsyncNodeExecutor()
        node = GraphNode(
            id="node1",
            name="Node",
            node_type=NodeType.FUNCTION,
            function_path="nonexistent.module.func",
        )
        func = executor.get_function(node)
        assert func is None

    def test_get_function_cached(self):
        """Test getting cached function."""
        executor = AsyncNodeExecutor()

        def my_func(state):
            return state

        executor._function_cache["cached.func"] = my_func
        node = GraphNode(
            id="node1",
            name="Node",
            node_type=NodeType.FUNCTION,
            function_path="cached.func",
        )
        result = executor.get_function(node)
        assert result is my_func

    async def test_execute_function_node(self):
        """Test executing a function node."""
        executor = AsyncNodeExecutor()

        def process(state):
            return {"result": state.get("value", 0) + 10}

        executor.register_function("test.process", process)

        node = GraphNode(
            id="node1",
            name="Process",
            node_type=NodeType.FUNCTION,
            function_path="test.process",
        )
        state = GraphState(data={"value": 5})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"result": 15}
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_execute_async_function_node(self):
        """Test executing an async function node."""
        executor = AsyncNodeExecutor()

        async def async_process(state):
            await asyncio.sleep(0.01)
            return {"result": "async_done"}

        executor.register_function("test.async_process", async_process)

        node = GraphNode(
            id="node1",
            name="AsyncProcess",
            node_type=NodeType.FUNCTION,
            function_path="test.async_process",
        )
        state = GraphState(data={})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"result": "async_done"}

    async def test_execute_start_node(self):
        """Test executing a start node."""
        executor = AsyncNodeExecutor()
        node = GraphNode(id="start", name="Start", node_type=NodeType.START)
        state = GraphState(data={"initial": "value"})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"initial": "value"}

    async def test_execute_end_node(self):
        """Test executing an end node."""
        executor = AsyncNodeExecutor()
        node = GraphNode(id="end", name="End", node_type=NodeType.END)
        state = GraphState(data={"final": "result"})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"final": "result"}

    async def test_execute_checkpoint_node(self):
        """Test executing a checkpoint node."""
        executor = AsyncNodeExecutor()
        node = GraphNode(id="cp1", name="Checkpoint", node_type=NodeType.CHECKPOINT)
        state = GraphState(data={})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.output_state["checkpoint_triggered"] is True
        assert result.output_state["node_id"] == "cp1"

    async def test_execute_missing_function(self):
        """Test executing node with missing function."""
        executor = AsyncNodeExecutor()
        node = GraphNode(
            id="node1",
            name="Missing",
            node_type=NodeType.FUNCTION,
            function_path="missing.func",
        )
        state = GraphState(data={})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.FAILED
        assert "not found" in result.error.lower()

    async def test_execute_with_timeout(self):
        """Test executing node that times out."""
        executor = AsyncNodeExecutor(default_timeout_ms=50)

        async def slow_func(state):
            await asyncio.sleep(1.0)
            return {"done": True}

        executor.register_function("test.slow", slow_func)

        node = GraphNode(
            id="node1",
            name="Slow",
            node_type=NodeType.FUNCTION,
            function_path="test.slow",
            timeout_ms=50,
            retry_count=0,
        )
        state = GraphState(data={})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.FAILED

    async def test_execute_with_retry_success(self):
        """Test executing node that succeeds after retry."""
        executor = AsyncNodeExecutor()
        call_count = 0

        def flaky_func(state):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary error")
            return {"success": True}

        executor.register_function("test.flaky", flaky_func)

        node = GraphNode(
            id="node1",
            name="Flaky",
            node_type=NodeType.FUNCTION,
            function_path="test.flaky",
            retry_count=3,
            retry_delay_ms=10,
        )
        state = GraphState(data={})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.retries_used == 1
        assert result.output_state == {"success": True}

    async def test_execute_non_dict_output(self):
        """Test executing function that returns non-dict."""
        executor = AsyncNodeExecutor()

        def returns_string(state):
            return "result_string"

        executor.register_function("test.string", returns_string)

        node = GraphNode(
            id="node1",
            name="String",
            node_type=NodeType.FUNCTION,
            function_path="test.string",
        )
        state = GraphState(data={})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"result": "result_string"}


class TestParallelNodeExecutor:
    """Tests for ParallelNodeExecutor."""

    def test_create_executor(self):
        """Test creating parallel executor."""
        executor = ParallelNodeExecutor()
        assert executor.max_concurrent == 10
        assert executor.base_executor is not None

    def test_create_with_custom_settings(self):
        """Test creating with custom settings."""
        base = AsyncNodeExecutor()
        executor = ParallelNodeExecutor(base_executor=base, max_concurrent=5)
        assert executor.max_concurrent == 5
        assert executor.base_executor is base

    async def test_execute_single_node(self):
        """Test executing single node through parallel executor."""
        executor = ParallelNodeExecutor()

        def process(state):
            return {"value": 42}

        executor.base_executor.register_function("test.process", process)

        node = GraphNode(
            id="node1",
            name="Process",
            node_type=NodeType.FUNCTION,
            function_path="test.process",
        )
        state = GraphState(data={})

        result = await executor.execute(node, state)

        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"value": 42}

    async def test_execute_parallel_empty(self):
        """Test parallel execution with empty list."""
        executor = ParallelNodeExecutor()
        results = await executor.execute_parallel([], GraphState())
        assert results == []

    async def test_execute_parallel_multiple(self):
        """Test parallel execution of multiple nodes."""
        executor = ParallelNodeExecutor()

        def make_func(value):
            def func(state):
                return {"value": value}

            return func

        for i in range(3):
            executor.base_executor.register_function(f"test.func{i}", make_func(i))

        nodes = [
            GraphNode(
                id=f"node{i}",
                name=f"Node{i}",
                node_type=NodeType.FUNCTION,
                function_path=f"test.func{i}",
            )
            for i in range(3)
        ]
        state = GraphState(data={})

        results = await executor.execute_parallel(nodes, state)

        assert len(results) == 3
        assert all(r.status == NodeStatus.COMPLETED for r in results)

    async def test_execute_parallel_with_failure(self):
        """Test parallel execution handles failures."""
        executor = ParallelNodeExecutor()

        def success_func(state):
            return {"success": True}

        def fail_func(state):
            raise ValueError("Intentional failure")

        executor.base_executor.register_function("test.success", success_func)
        executor.base_executor.register_function("test.fail", fail_func)

        nodes = [
            GraphNode(
                id="node1",
                name="Success",
                node_type=NodeType.FUNCTION,
                function_path="test.success",
            ),
            GraphNode(
                id="node2",
                name="Fail",
                node_type=NodeType.FUNCTION,
                function_path="test.fail",
                retry_count=0,
            ),
        ]
        state = GraphState(data={})

        results = await executor.execute_parallel(nodes, state)

        assert len(results) == 2
        assert results[0].status == NodeStatus.COMPLETED
        assert results[1].status == NodeStatus.FAILED

    async def test_execute_with_dependencies(self):
        """Test execution with dependency ordering."""
        executor = ParallelNodeExecutor()
        execution_order = []

        def make_func(node_id):
            def func(state):
                execution_order.append(node_id)
                return {"executed": node_id}

            return func

        for i in ["a", "b", "c"]:
            executor.base_executor.register_function(f"test.func_{i}", make_func(i))

        nodes = [
            GraphNode(id="a", name="A", node_type=NodeType.FUNCTION, function_path="test.func_a"),
            GraphNode(id="b", name="B", node_type=NodeType.FUNCTION, function_path="test.func_b"),
            GraphNode(id="c", name="C", node_type=NodeType.FUNCTION, function_path="test.func_c"),
        ]

        # b depends on a, c depends on b
        dependencies = {
            "a": set(),
            "b": {"a"},
            "c": {"b"},
        }

        state = GraphState(data={})
        results, _final_state = await executor.execute_with_dependencies(nodes, dependencies, state)

        assert len(results) == 3
        # Check order: a before b, b before c
        assert execution_order.index("a") < execution_order.index("b")
        assert execution_order.index("b") < execution_order.index("c")


class TestConditionalNodeExecutor:
    """Tests for ConditionalNodeExecutor."""

    def test_create_executor(self):
        """Test creating conditional executor."""
        executor = ConditionalNodeExecutor()
        assert executor.base_executor is not None
        assert executor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_register_condition(self):
        """Test registering condition function."""
        executor = ConditionalNodeExecutor()

        def route_condition(state):
            return "success" if state.get("status") == "ok" else "failure"

        executor.register_condition("test.route", route_condition)
        assert "test.route" in executor._condition_cache

    async def test_evaluate_condition_with_function(self):
        """Test condition evaluation with registered function."""
        executor = ConditionalNodeExecutor()

        def route_condition(state):
            return "success" if state.get("status") == "ok" else "failure"

        executor.register_condition("test.route", route_condition)

        edge = ConditionalEdge(
            source_node_id="node1",
            conditions={"success": "node2", "failure": "node3"},
            default_target="node4",
            condition_function_path="test.route",
        )

        state = GraphState(data={"status": "ok"})
        result = await executor.evaluate_condition(edge, state)
        assert result == "node2"

        state = GraphState(data={"status": "error"})
        result = await executor.evaluate_condition(edge, state)
        assert result == "node3"

    async def test_evaluate_condition_key_value(self):
        """Test condition evaluation with key=value expression."""
        executor = ConditionalNodeExecutor()

        edge = ConditionalEdge(
            source_node_id="node1",
            conditions={"status=complete": "node2", "status=pending": "node3"},
            default_target="node4",
        )

        state = GraphState(data={"status": "complete"})
        result = await executor.evaluate_condition(edge, state)
        assert result == "node2"

    async def test_evaluate_condition_boolean(self):
        """Test condition evaluation with boolean key."""
        executor = ConditionalNodeExecutor()

        edge = ConditionalEdge(
            source_node_id="node1",
            conditions={"is_valid": "node2"},
            default_target="node3",
        )

        state = GraphState(data={"is_valid": True})
        result = await executor.evaluate_condition(edge, state)
        assert result == "node2"

        state = GraphState(data={"is_valid": False})
        result = await executor.evaluate_condition(edge, state)
        assert result == "node3"

    async def test_evaluate_condition_default(self):
        """Test condition evaluation falls back to default."""
        executor = ConditionalNodeExecutor()

        edge = ConditionalEdge(
            source_node_id="node1",
            conditions={"status=complete": "node2"},
            default_target="node4",
        )

        state = GraphState(data={"status": "unknown"})
        result = await executor.evaluate_condition(edge, state)
        assert result == "node4"

    async def test_route_with_matching_edge(self):
        """Test routing with matching conditional edge."""
        executor = ConditionalNodeExecutor()

        def route_fn(state):
            return "path_a" if state.get("choice") == "a" else "path_b"

        executor.register_condition("test.router", route_fn)

        edges = [
            ConditionalEdge(
                source_node_id="node1",
                conditions={"path_a": "node_a", "path_b": "node_b"},
                default_target="default",
                condition_function_path="test.router",
            ),
        ]

        state = GraphState(data={"choice": "a"})
        result = await executor.route(edges, "node1", state)
        assert result == "node_a"

    async def test_route_no_matching_source(self):
        """Test routing when no edge matches source."""
        executor = ConditionalNodeExecutor()

        edges = [
            ConditionalEdge(
                source_node_id="node2",
                conditions={"test": "node3"},
                default_target="node4",
            ),
        ]

        state = GraphState(data={"test": True})
        result = await executor.route(edges, "node1", state)
        assert result is None
