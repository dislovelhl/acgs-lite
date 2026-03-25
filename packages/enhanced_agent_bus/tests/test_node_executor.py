"""Tests for langgraph_orchestration.node_executor module.

Covers AsyncNodeExecutor, ParallelNodeExecutor, ConditionalNodeExecutor,
including timeout, retry, special node types, and dependency execution.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.langgraph_orchestration.models import (
    ConditionalEdge,
    GraphNode,
    GraphState,
    NodeResult,
    NodeStatus,
    NodeType,
)
from enhanced_agent_bus.langgraph_orchestration.node_executor import (
    AsyncNodeExecutor,
    ConditionalNodeExecutor,
    ParallelNodeExecutor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str = "n1",
    name: str = "node1",
    node_type: NodeType = NodeType.FUNCTION,
    function_path: str | None = "some.module.func",
    timeout_ms: float = 5000.0,
    retry_count: int = 0,
    retry_delay_ms: float = 10.0,
) -> GraphNode:
    return GraphNode(
        id=node_id,
        name=name,
        node_type=node_type,
        function_path=function_path,
        timeout_ms=timeout_ms,
        retry_count=retry_count,
        retry_delay_ms=retry_delay_ms,
    )


def _make_state(data: dict | None = None) -> GraphState:
    return GraphState(data=data or {})


# ---------------------------------------------------------------------------
# AsyncNodeExecutor
# ---------------------------------------------------------------------------


class TestAsyncNodeExecutor:
    @pytest.mark.asyncio
    async def test_execute_start_node(self):
        executor = AsyncNodeExecutor()
        node = _make_node(node_type=NodeType.START, function_path=None)
        state = _make_state({"key": "value"})
        result = await executor.execute(node, state)
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"key": "value"}

    @pytest.mark.asyncio
    async def test_execute_end_node(self):
        executor = AsyncNodeExecutor()
        node = _make_node(node_type=NodeType.END, function_path=None)
        state = _make_state({"result": 42})
        result = await executor.execute(node, state)
        assert result.status == NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_checkpoint_node(self):
        executor = AsyncNodeExecutor()
        node = _make_node(node_type=NodeType.CHECKPOINT, function_path=None)
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state["checkpoint_triggered"] is True

    @pytest.mark.asyncio
    async def test_execute_interrupt_node(self):
        executor = AsyncNodeExecutor()
        node = _make_node(node_type=NodeType.INTERRUPT, function_path=None)
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state["interrupt_triggered"] is True

    @pytest.mark.asyncio
    async def test_execute_function_node_async(self):
        executor = AsyncNodeExecutor()
        node = _make_node()

        async def my_func(data):
            return {"processed": True}

        executor.register_function("some.module.func", my_func)
        state = _make_state({"input": "data"})
        result = await executor.execute(node, state)
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state["processed"] is True

    @pytest.mark.asyncio
    async def test_execute_function_node_sync(self):
        executor = AsyncNodeExecutor()
        node = _make_node()

        def my_func(data):
            return {"sync": True}

        executor.register_function("some.module.func", my_func)
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state["sync"] is True

    @pytest.mark.asyncio
    async def test_execute_function_returns_non_dict(self):
        executor = AsyncNodeExecutor()
        node = _make_node()

        async def my_func(data):
            return 42

        executor.register_function("some.module.func", my_func)
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"result": 42}

    @pytest.mark.asyncio
    async def test_execute_function_not_found(self):
        executor = AsyncNodeExecutor()
        node = _make_node(function_path="nonexistent.module.func")
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.FAILED
        assert "Function not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_with_context(self):
        executor = AsyncNodeExecutor()
        node = _make_node()

        async def my_func(data):
            assert "_context" in data
            return {"got_context": True}

        executor.register_function("some.module.func", my_func)
        result = await executor.execute(node, _make_state(), context={"extra": "info"})
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state["got_context"] is True

    @pytest.mark.asyncio
    async def test_execute_with_retry(self):
        executor = AsyncNodeExecutor(retry_backoff_factor=1.0)
        node = _make_node(retry_count=2, retry_delay_ms=10.0)

        call_count = 0

        async def failing_then_ok(data):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return {"ok": True}

        executor.register_function("some.module.func", failing_then_ok)
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.COMPLETED
        assert result.retries_used == 2

    @pytest.mark.asyncio
    async def test_execute_all_retries_exhausted(self):
        executor = AsyncNodeExecutor(retry_backoff_factor=1.0)
        node = _make_node(retry_count=1, retry_delay_ms=10.0)

        async def always_fail(data):
            raise RuntimeError("permanent")

        executor.register_function("some.module.func", always_fail)
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.FAILED
        assert "permanent" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        executor = AsyncNodeExecutor()
        node = _make_node(timeout_ms=50.0, retry_count=0)

        async def slow_func(data):
            await asyncio.sleep(10)
            return {}

        executor.register_function("some.module.func", slow_func)
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.FAILED

    @pytest.mark.asyncio
    async def test_passthrough_node(self):
        executor = AsyncNodeExecutor()
        # PARALLEL type without function_path = passthrough
        node = _make_node(node_type=NodeType.PARALLEL, function_path=None)
        state = _make_state({"x": 1})
        result = await executor.execute(node, state)
        assert result.status == NodeStatus.COMPLETED
        assert result.output_state == {"x": 1}

    def test_register_function(self):
        executor = AsyncNodeExecutor()

        async def f(data):
            return {}

        executor.register_function("my.path", f)
        assert "my.path" in executor._function_cache

    def test_get_function_no_path(self):
        executor = AsyncNodeExecutor()
        node = _make_node(function_path=None)
        assert executor.get_function(node) is None

    def test_get_function_invalid_path(self):
        executor = AsyncNodeExecutor()
        node = _make_node(function_path="no_dot_in_path")
        assert executor.get_function(node) is None

    def test_get_function_cached(self):
        executor = AsyncNodeExecutor()

        async def f(data):
            return {}

        executor.register_function("my.mod.func", f)
        node = _make_node(function_path="my.mod.func")
        result = executor.get_function(node)
        assert result is f


# ---------------------------------------------------------------------------
# ParallelNodeExecutor
# ---------------------------------------------------------------------------


class TestParallelNodeExecutor:
    @pytest.mark.asyncio
    async def test_execute_single_delegates(self):
        executor = ParallelNodeExecutor()

        async def f(data):
            return {"done": True}

        executor.base_executor.register_function("some.module.func", f)
        node = _make_node()
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_parallel_empty(self):
        executor = ParallelNodeExecutor()
        results = await executor.execute_parallel([], _make_state())
        assert results == []

    @pytest.mark.asyncio
    async def test_execute_parallel_multiple(self):
        executor = ParallelNodeExecutor()

        async def f1(data):
            return {"f1": True}

        async def f2(data):
            return {"f2": True}

        executor.base_executor.register_function("mod.f1", f1)
        executor.base_executor.register_function("mod.f2", f2)

        nodes = [
            _make_node(node_id="n1", function_path="mod.f1"),
            _make_node(node_id="n2", function_path="mod.f2"),
        ]
        results = await executor.execute_parallel(nodes, _make_state())
        assert len(results) == 2
        assert all(r.status == NodeStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_execute_parallel_handles_exception(self):
        base = AsyncNodeExecutor()

        async def failing(data):
            raise RuntimeError("boom")

        base.register_function("mod.fail", failing)
        executor = ParallelNodeExecutor(base_executor=base)

        nodes = [_make_node(node_id="n1", function_path="mod.fail", retry_count=0)]
        results = await executor.execute_parallel(nodes, _make_state())
        assert len(results) == 1
        assert results[0].status == NodeStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_with_dependencies(self):
        executor = ParallelNodeExecutor()

        async def step1(data):
            return {"step": 1}

        async def step2(data):
            return {"step": 2}

        executor.base_executor.register_function("mod.s1", step1)
        executor.base_executor.register_function("mod.s2", step2)

        nodes = [
            _make_node(node_id="n1", function_path="mod.s1"),
            _make_node(node_id="n2", function_path="mod.s2"),
        ]
        deps = {"n1": set(), "n2": {"n1"}}

        results, final_state = await executor.execute_with_dependencies(nodes, deps, _make_state())
        assert len(results) == 2
        # n1 should complete before n2
        node_ids = [r.node_id for r in results]
        assert node_ids.index("n1") < node_ids.index("n2")


# ---------------------------------------------------------------------------
# ConditionalNodeExecutor
# ---------------------------------------------------------------------------


class TestConditionalNodeExecutor:
    @pytest.mark.asyncio
    async def test_execute_delegates_to_base(self):
        executor = ConditionalNodeExecutor()

        async def f(data):
            return {"done": True}

        executor.base_executor.register_function("some.module.func", f)
        node = _make_node()
        result = await executor.execute(node, _make_state())
        assert result.status == NodeStatus.COMPLETED

    def test_register_condition(self):
        executor = ConditionalNodeExecutor()

        def cond(data):
            return "yes"

        executor.register_condition("my.cond", cond)
        assert "my.cond" in executor._condition_cache

    @pytest.mark.asyncio
    async def test_evaluate_condition_with_function(self):
        executor = ConditionalNodeExecutor()

        def cond(data):
            return "high" if data.get("score", 0) > 0.5 else "low"

        executor.register_condition("my.cond", cond)

        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={"high": "n2", "low": "n3"},
            condition_function_path="my.cond",
        )
        state = _make_state({"score": 0.8})
        result = await executor.evaluate_condition(edge, state)
        assert result == "n2"

    @pytest.mark.asyncio
    async def test_evaluate_condition_async_function(self):
        executor = ConditionalNodeExecutor()

        async def cond(data):
            return "go"

        executor.register_condition("my.async_cond", cond)

        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={"go": "n2"},
            condition_function_path="my.async_cond",
        )
        result = await executor.evaluate_condition(edge, _make_state())
        assert result == "n2"

    @pytest.mark.asyncio
    async def test_evaluate_condition_default_target(self):
        executor = ConditionalNodeExecutor()

        def cond(data):
            return "unknown"

        executor.register_condition("my.cond", cond)

        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={"high": "n2"},
            default_target="n_default",
            condition_function_path="my.cond",
        )
        result = await executor.evaluate_condition(edge, _make_state())
        assert result == "n_default"

    @pytest.mark.asyncio
    async def test_evaluate_condition_function_error_returns_default(self):
        executor = ConditionalNodeExecutor()

        def cond(data):
            raise ValueError("bad")

        executor.register_condition("my.cond", cond)

        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={},
            default_target="n_fallback",
            condition_function_path="my.cond",
        )
        result = await executor.evaluate_condition(edge, _make_state())
        assert result == "n_fallback"

    @pytest.mark.asyncio
    async def test_evaluate_expression_key_value(self):
        executor = ConditionalNodeExecutor()
        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={"status=ready": "n2"},
        )
        state = _make_state({"status": "ready"})
        result = await executor.evaluate_condition(edge, state)
        assert result == "n2"

    @pytest.mark.asyncio
    async def test_evaluate_expression_boolean(self):
        executor = ConditionalNodeExecutor()
        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={"is_valid": "n2"},
        )
        state = _make_state({"is_valid": True})
        result = await executor.evaluate_condition(edge, state)
        assert result == "n2"

    @pytest.mark.asyncio
    async def test_evaluate_no_match_returns_default(self):
        executor = ConditionalNodeExecutor()
        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={"status=done": "n2"},
            default_target="n_default",
        )
        state = _make_state({"status": "pending"})
        result = await executor.evaluate_condition(edge, state)
        assert result == "n_default"

    @pytest.mark.asyncio
    async def test_route(self):
        executor = ConditionalNodeExecutor()

        def cond(data):
            return "next"

        executor.register_condition("my.cond", cond)

        edges = [
            ConditionalEdge(
                source_node_id="n1",
                conditions={"next": "n2"},
                condition_function_path="my.cond",
            ),
        ]
        result = await executor.route(edges, "n1", _make_state())
        assert result == "n2"

    @pytest.mark.asyncio
    async def test_route_no_matching_edge(self):
        executor = ConditionalNodeExecutor()
        edges = [
            ConditionalEdge(
                source_node_id="other",
                conditions={"x": "n2"},
            ),
        ]
        result = await executor.route(edges, "n1", _make_state())
        assert result is None

    def test_get_condition_function_no_path(self):
        executor = ConditionalNodeExecutor()
        edge = ConditionalEdge(source_node_id="n1", conditions={})
        assert executor.get_condition_function(edge) is None

    def test_get_condition_function_invalid_path(self):
        executor = ConditionalNodeExecutor()
        edge = ConditionalEdge(
            source_node_id="n1",
            conditions={},
            condition_function_path="no_dot",
        )
        assert executor.get_condition_function(edge) is None
