"""Tests for langgraph_orchestration/supervisor_worker.py."""

import asyncio

import pytest

from enhanced_agent_bus.langgraph_orchestration.models import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    GraphState,
)
from enhanced_agent_bus.langgraph_orchestration.supervisor_worker import (
    SupervisorNode,
    SupervisorWorkerOrchestrator,
    TaskPriority,
    WorkerNode,
    WorkerPool,
    WorkerStatus,
    WorkerTask,
    WorkerTaskResult,
    create_supervisor_worker,
)

# ---------------------------------------------------------------------------
# WorkerTask / WorkerTaskResult dataclass tests
# ---------------------------------------------------------------------------


class TestWorkerTask:
    def test_defaults(self):
        task = WorkerTask()
        assert task.name == ""
        assert task.priority == TaskPriority.NORMAL
        assert task.timeout_ms == 5000.0
        assert task.retries == 3
        assert isinstance(task.id, str)

    def test_custom_values(self):
        task = WorkerTask(
            name="compute",
            description="desc",
            input_data={"x": 1},
            priority=TaskPriority.HIGH,
            timeout_ms=1000.0,
        )
        assert task.name == "compute"
        assert task.priority == TaskPriority.HIGH
        assert task.input_data == {"x": 1}


class TestWorkerTaskResult:
    def test_success_result(self):
        r = WorkerTaskResult(task_id="t1", worker_id="w1", success=True, output={"v": 42})
        assert r.success is True
        assert r.output == {"v": 42}
        assert r.error is None

    def test_failure_result(self):
        r = WorkerTaskResult(task_id="t1", worker_id="w1", success=False, error="boom")
        assert r.success is False
        assert r.error == "boom"


# ---------------------------------------------------------------------------
# WorkerNode tests
# ---------------------------------------------------------------------------


class TestWorkerNode:
    def test_init_defaults(self):
        node = WorkerNode(worker_id="w1")
        assert node.worker_id == "w1"
        assert node.name == "w1"
        assert node.status == WorkerStatus.IDLE
        assert node.tasks_completed == 0
        assert node.tasks_failed == 0

    def test_register_and_can_handle(self):
        node = WorkerNode(worker_id="w1")
        node.register_handler("add", lambda d: d)
        assert node.can_handle(WorkerTask(name="add")) is True

    def test_can_handle_by_capability(self):
        node = WorkerNode(worker_id="w1", capabilities=["math"])
        task = WorkerTask(name="unknown", metadata={"required_capability": "math"})
        assert node.can_handle(task) is True

    def test_can_handle_missing_capability(self):
        node = WorkerNode(worker_id="w1", capabilities=["io"])
        task = WorkerTask(name="unknown", metadata={"required_capability": "math"})
        assert node.can_handle(task) is False

    def test_can_handle_default_true(self):
        node = WorkerNode(worker_id="w1")
        assert node.can_handle(WorkerTask(name="anything")) is True

    @pytest.mark.asyncio
    async def test_execute_task_with_sync_handler(self):
        node = WorkerNode(worker_id="w1")
        node.register_handler("double", lambda d: {"result": d.get("x", 0) * 2})
        state = GraphState(data={"x": 5})
        task = WorkerTask(name="double")
        result = await node.execute_task(task, state)
        assert result.success is True
        assert result.output == {"result": 10}
        assert node.tasks_completed == 1
        assert node.status == WorkerStatus.IDLE

    @pytest.mark.asyncio
    async def test_execute_task_with_async_handler(self):
        async def async_handler(data):
            return {"sum": data.get("a", 0) + data.get("b", 0)}

        node = WorkerNode(worker_id="w1")
        node.register_handler("sum", async_handler)
        state = GraphState(data={"a": 3, "b": 7})
        task = WorkerTask(name="sum")
        result = await node.execute_task(task, state)
        assert result.success is True
        assert result.output == {"sum": 10}

    @pytest.mark.asyncio
    async def test_execute_task_non_dict_output(self):
        node = WorkerNode(worker_id="w1")
        node.register_handler("scalar", lambda d: 42)
        state = GraphState(data={})
        task = WorkerTask(name="scalar")
        result = await node.execute_task(task, state)
        assert result.success is True
        assert result.output == {"result": 42}

    @pytest.mark.asyncio
    async def test_execute_task_no_handler_passthrough(self):
        node = WorkerNode(worker_id="w1")
        state = GraphState(data={"existing": True})
        task = WorkerTask(name="noop", input_data={"key": "val"})
        result = await node.execute_task(task, state)
        assert result.success is True
        assert result.output == {"key": "val"}

    @pytest.mark.asyncio
    async def test_execute_task_handler_raises(self):
        def bad_handler(d):
            raise ValueError("oops")

        node = WorkerNode(worker_id="w1")
        node.register_handler("fail", bad_handler)
        state = GraphState(data={})
        task = WorkerTask(name="fail")
        result = await node.execute_task(task, state)
        assert result.success is False
        assert "oops" in result.error
        assert node.tasks_failed == 1
        assert node.status == WorkerStatus.IDLE

    def test_get_stats(self):
        node = WorkerNode(worker_id="w1", name="Worker One", capabilities=["a"])
        stats = node.get_stats()
        assert stats["worker_id"] == "w1"
        assert stats["name"] == "Worker One"
        assert stats["status"] == "idle"
        assert stats["capabilities"] == ["a"]


# ---------------------------------------------------------------------------
# WorkerPool tests
# ---------------------------------------------------------------------------


class TestWorkerPool:
    def test_add_and_remove_worker(self):
        pool = WorkerPool()
        w = WorkerNode(worker_id="w1")
        pool.add_worker(w)
        assert "w1" in pool.workers
        removed = pool.remove_worker("w1")
        assert removed is w
        assert pool.remove_worker("nonexistent") is None

    def test_get_available_worker(self):
        w1 = WorkerNode(worker_id="w1")
        pool = WorkerPool(workers=[w1])
        task = WorkerTask(name="t")
        assert pool.get_available_worker(task) is w1

    def test_get_available_worker_none_when_busy(self):
        w1 = WorkerNode(worker_id="w1")
        w1.status = WorkerStatus.BUSY
        pool = WorkerPool(workers=[w1])
        assert pool.get_available_worker(WorkerTask(name="t")) is None

    @pytest.mark.asyncio
    async def test_submit_task(self):
        w = WorkerNode(worker_id="w1")
        pool = WorkerPool(workers=[w])
        state = GraphState(data={})
        task = WorkerTask(name="noop", input_data={"a": 1})
        result = await pool.submit_task(task, state)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_submit_tasks_empty(self):
        pool = WorkerPool()
        results = await pool.submit_tasks([], GraphState(data={}))
        assert results == []

    @pytest.mark.asyncio
    async def test_submit_tasks_sorted_by_priority(self):
        w1 = WorkerNode(worker_id="w1")
        w2 = WorkerNode(worker_id="w2")
        pool = WorkerPool(workers=[w1, w2])
        state = GraphState(data={})
        tasks = [
            WorkerTask(name="low", priority=TaskPriority.LOW, input_data={"p": "low"}),
            WorkerTask(name="high", priority=TaskPriority.HIGH, input_data={"p": "high"}),
        ]
        results = await pool.submit_tasks(tasks, state)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_get_pool_stats(self):
        w1 = WorkerNode(worker_id="w1")
        w2 = WorkerNode(worker_id="w2")
        pool = WorkerPool(workers=[w1, w2])
        stats = pool.get_pool_stats()
        assert stats["worker_count"] == 2
        assert stats["idle_workers"] == 2
        assert stats["busy_workers"] == 0


# ---------------------------------------------------------------------------
# SupervisorNode tests
# ---------------------------------------------------------------------------


class TestSupervisorNode:
    @pytest.mark.asyncio
    async def test_plan_default_passthrough(self):
        sup = SupervisorNode(supervisor_id="s1")
        state = GraphState(data={"foo": "bar"})
        tasks = await sup.plan(state)
        assert len(tasks) == 1
        assert tasks[0].name == "passthrough"
        assert sup.tasks_delegated == 1

    @pytest.mark.asyncio
    async def test_plan_with_custom_planner(self):
        def planner(data):
            return [WorkerTask(name="a"), WorkerTask(name="b")]

        sup = SupervisorNode(supervisor_id="s1")
        sup.set_planner(planner)
        tasks = await sup.plan(GraphState(data={}))
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_plan_with_async_planner(self):
        async def planner(data):
            return [WorkerTask(name="async_task")]

        sup = SupervisorNode(supervisor_id="s1")
        sup.set_planner(planner)
        tasks = await sup.plan(GraphState(data={}))
        assert len(tasks) == 1
        assert tasks[0].name == "async_task"

    @pytest.mark.asyncio
    async def test_aggregate_results_default(self):
        sup = SupervisorNode(supervisor_id="s1")
        state = GraphState(data={"old": 1})
        results = [
            WorkerTaskResult(task_id="t1", worker_id="w1", success=True, output={"new": 2}),
            WorkerTaskResult(task_id="t2", worker_id="w2", success=False, error="fail"),
        ]
        new_state = await sup.aggregate_results(state, results)
        assert new_state.data.get("new") == 2

    @pytest.mark.asyncio
    async def test_aggregate_results_custom_aggregator(self):
        def aggregator(data, results):
            return {"count": len(results)}

        sup = SupervisorNode(supervisor_id="s1")
        sup.set_aggregator(aggregator)
        state = GraphState(data={})
        results = [WorkerTaskResult(task_id="t1", worker_id="w1", success=True)]
        new_state = await sup.aggregate_results(state, results)
        assert new_state.data.get("count") == 1

    @pytest.mark.asyncio
    async def test_critique_default_acceptable(self):
        sup = SupervisorNode(supervisor_id="s1")
        ok, reason, suggestions = await sup.critique(GraphState(data={}))
        assert ok is True
        assert suggestions is None

    @pytest.mark.asyncio
    async def test_critique_custom(self):
        def critic(data):
            return (False, "not good enough", {"hint": "try harder"})

        sup = SupervisorNode(supervisor_id="s1")
        sup.set_critic(critic)
        ok, reason, suggestions = await sup.critique(GraphState(data={}))
        assert ok is False
        assert suggestions == {"hint": "try harder"}

    @pytest.mark.asyncio
    async def test_should_continue_max_iterations(self):
        sup = SupervisorNode(supervisor_id="s1", max_iterations=2)
        sup.iterations = 2
        assert await sup.should_continue(GraphState(data={})) is False

    @pytest.mark.asyncio
    async def test_should_continue_completed_flag(self):
        sup = SupervisorNode(supervisor_id="s1")
        state = GraphState(data={"_completed": True})
        assert await sup.should_continue(state) is False

    @pytest.mark.asyncio
    async def test_should_continue_custom(self):
        def check(data, iterations):
            return iterations < 1

        sup = SupervisorNode(supervisor_id="s1")
        sup.set_continuation_check(check)
        sup.iterations = 0
        assert await sup.should_continue(GraphState(data={})) is True
        sup.iterations = 1
        assert await sup.should_continue(GraphState(data={})) is False

    @pytest.mark.asyncio
    async def test_execute_single_iteration(self):
        w = WorkerNode(worker_id="w1")
        pool = WorkerPool(workers=[w])
        sup = SupervisorNode(supervisor_id="s1", worker_pool=pool, max_iterations=1)
        state = GraphState(data={"input": "data"})
        final_state, results = await sup.execute(state)
        assert sup.iterations == 1
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_execute_no_tasks_breaks(self):
        def empty_planner(data):
            return []

        w = WorkerNode(worker_id="w1")
        pool = WorkerPool(workers=[w])
        sup = SupervisorNode(supervisor_id="s1", worker_pool=pool)
        sup.set_planner(empty_planner)
        state = GraphState(data={})
        final_state, results = await sup.execute(state)
        assert results == []

    def test_get_stats(self):
        sup = SupervisorNode(supervisor_id="s1")
        stats = sup.get_stats()
        assert stats["supervisor_id"] == "s1"
        assert "worker_pool" in stats


# ---------------------------------------------------------------------------
# SupervisorWorkerOrchestrator tests
# ---------------------------------------------------------------------------


class TestSupervisorWorkerOrchestrator:
    @pytest.mark.asyncio
    async def test_run_success(self):
        w = WorkerNode(worker_id="w1")
        pool = WorkerPool(workers=[w])
        sup = SupervisorNode(supervisor_id="s1", worker_pool=pool, max_iterations=1)
        orch = SupervisorWorkerOrchestrator(supervisor=sup)
        result = await orch.run(input_data={"x": 1})
        assert result.status == ExecutionStatus.COMPLETED
        assert result.total_execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_run_with_error(self):
        def bad_planner(data):
            raise RuntimeError("plan exploded")

        w = WorkerNode(worker_id="w1")
        pool = WorkerPool(workers=[w])
        sup = SupervisorNode(supervisor_id="s1", worker_pool=pool)
        sup.set_planner(bad_planner)
        orch = SupervisorWorkerOrchestrator(supervisor=sup)
        result = await orch.run(input_data={})
        assert result.status == ExecutionStatus.FAILED
        assert "plan exploded" in result.error


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateSupervisorWorker:
    def test_default_factory(self):
        orch = create_supervisor_worker()
        assert isinstance(orch, SupervisorWorkerOrchestrator)
        pool_stats = orch.supervisor.worker_pool.get_pool_stats()
        assert pool_stats["worker_count"] == 3

    def test_custom_worker_count(self):
        orch = create_supervisor_worker(worker_count=5)
        pool_stats = orch.supervisor.worker_pool.get_pool_stats()
        assert pool_stats["worker_count"] == 5

    @pytest.mark.asyncio
    async def test_factory_end_to_end(self):
        orch = create_supervisor_worker(worker_count=2, max_iterations=1)
        result = await orch.run(input_data={"test": True})
        assert result.status == ExecutionStatus.COMPLETED
