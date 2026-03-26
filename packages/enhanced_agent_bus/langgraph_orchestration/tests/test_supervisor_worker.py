"""
ACGS-2 LangGraph Orchestration - Supervisor-Worker Tests
Constitutional Hash: 608508a9bd224290
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    ExecutionContext,
    ExecutionStatus,
    GraphState,
)

from ..supervisor_worker import (
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


class TestWorkerStatus:
    """Tests for WorkerStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert WorkerStatus.IDLE.value == "idle"
        assert WorkerStatus.BUSY.value == "busy"
        assert WorkerStatus.FAILED.value == "failed"
        assert WorkerStatus.TERMINATED.value == "terminated"


class TestTaskPriority:
    """Tests for TaskPriority enum."""

    def test_priority_values(self):
        """Test priority enum values."""
        assert TaskPriority.LOW.value == "low"
        assert TaskPriority.NORMAL.value == "normal"
        assert TaskPriority.HIGH.value == "high"
        assert TaskPriority.CRITICAL.value == "critical"


class TestWorkerTask:
    """Tests for WorkerTask."""

    def test_create_task(self):
        """Test creating worker task."""
        task = WorkerTask(
            name="process",
            input_data={"key": "value"},
            priority=TaskPriority.HIGH,
        )

        assert task.name == "process"
        assert task.input_data == {"key": "value"}
        assert task.priority == TaskPriority.HIGH
        assert task.constitutional_hash == CONSTITUTIONAL_HASH

    def test_task_defaults(self):
        """Test task default values."""
        task = WorkerTask()

        assert task.id is not None
        assert task.priority == TaskPriority.NORMAL
        assert task.timeout_ms == 5000.0
        assert task.retries == 3


class TestWorkerTaskResult:
    """Tests for WorkerTaskResult."""

    def test_create_success_result(self):
        """Test creating successful result."""
        result = WorkerTaskResult(
            task_id="task1",
            worker_id="worker1",
            success=True,
            output={"result": "value"},
            execution_time_ms=50.0,
        )

        assert result.success is True
        assert result.output == {"result": "value"}
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_failed_result(self):
        """Test creating failed result."""
        result = WorkerTaskResult(
            task_id="task1",
            worker_id="worker1",
            success=False,
            error="Task failed",
        )

        assert result.success is False
        assert result.error == "Task failed"


class TestWorkerNode:
    """Tests for WorkerNode."""

    def test_create_worker(self):
        """Test creating worker node."""
        worker = WorkerNode(
            worker_id="worker1",
            name="Test Worker",
            capabilities=["process", "analyze"],
        )

        assert worker.worker_id == "worker1"
        assert worker.name == "Test Worker"
        assert worker.capabilities == ["process", "analyze"]
        assert worker.status == WorkerStatus.IDLE

    def test_register_handler(self):
        """Test registering task handler."""
        worker = WorkerNode(worker_id="worker1")

        def handler(data):
            return {"processed": True}

        worker.register_handler("process", handler)

        assert "process" in worker._task_handlers

    def test_can_handle_with_handler(self):
        """Test can_handle with registered handler."""
        worker = WorkerNode(worker_id="worker1")
        worker.register_handler("process", lambda x: x)

        task = WorkerTask(name="process")
        assert worker.can_handle(task) is True

    def test_can_handle_with_capability(self):
        """Test can_handle with matching capability."""
        worker = WorkerNode(worker_id="worker1", capabilities=["analyze"])

        task = WorkerTask(
            name="analyze_data",
            metadata={"required_capability": "analyze"},
        )

        assert worker.can_handle(task) is True

    def test_can_handle_missing_capability(self):
        """Test can_handle with missing capability."""
        worker = WorkerNode(worker_id="worker1", capabilities=["process"])

        task = WorkerTask(
            name="analyze_data",
            metadata={"required_capability": "analyze"},
        )

        assert worker.can_handle(task) is False

    async def test_execute_task_with_handler(self):
        """Test executing task with registered handler."""
        worker = WorkerNode(worker_id="worker1")

        def handler(data):
            return {"result": data.get("input", 0) * 2}

        worker.register_handler("double", handler)

        task = WorkerTask(name="double", input_data={"input": 5})
        state = GraphState(data={})

        result = await worker.execute_task(task, state)

        assert result.success is True
        assert result.output == {"result": 10}
        assert worker.tasks_completed == 1

    async def test_execute_task_async_handler(self):
        """Test executing task with async handler."""
        worker = WorkerNode(worker_id="worker1")

        async def async_handler(data):
            await asyncio.sleep(0.01)
            return {"async_result": "done"}

        worker.register_handler("async_task", async_handler)

        task = WorkerTask(name="async_task")
        state = GraphState(data={})

        result = await worker.execute_task(task, state)

        assert result.success is True
        assert result.output == {"async_result": "done"}

    async def test_execute_task_failure(self):
        """Test executing task that fails."""
        worker = WorkerNode(worker_id="worker1")

        def failing_handler(data):
            raise ValueError("Intentional error")

        worker.register_handler("fail", failing_handler)

        task = WorkerTask(name="fail")
        state = GraphState(data={})

        result = await worker.execute_task(task, state)

        assert result.success is False
        assert "Intentional error" in result.error
        assert worker.tasks_failed == 1

    async def test_execute_task_passthrough(self):
        """Test executing task without handler (passthrough)."""
        worker = WorkerNode(worker_id="worker1")

        task = WorkerTask(
            name="unknown",
            input_data={"pass": "through"},
        )
        state = GraphState(data={})

        result = await worker.execute_task(task, state)

        assert result.success is True
        assert result.output == {"pass": "through"}

    def test_get_stats(self):
        """Test getting worker statistics."""
        worker = WorkerNode(worker_id="worker1", name="Test Worker")
        worker.tasks_completed = 10
        worker.tasks_failed = 2
        worker.total_execution_time_ms = 500.0

        stats = worker.get_stats()

        assert stats["worker_id"] == "worker1"
        assert stats["tasks_completed"] == 10
        assert stats["tasks_failed"] == 2
        assert stats["avg_execution_time_ms"] == pytest.approx(41.67, rel=0.01)


class TestWorkerPool:
    """Tests for WorkerPool."""

    def test_create_pool(self):
        """Test creating worker pool."""
        pool = WorkerPool()
        assert len(pool.workers) == 0
        assert pool.max_concurrent_tasks == 10

    def test_add_worker(self):
        """Test adding worker to pool."""
        pool = WorkerPool()
        worker = WorkerNode(worker_id="worker1")

        pool.add_worker(worker)

        assert "worker1" in pool.workers

    def test_remove_worker(self):
        """Test removing worker from pool."""
        worker = WorkerNode(worker_id="worker1")
        pool = WorkerPool(workers=[worker])

        removed = pool.remove_worker("worker1")

        assert removed is worker
        assert "worker1" not in pool.workers

    def test_get_available_worker(self):
        """Test getting available worker."""
        worker = WorkerNode(worker_id="worker1")
        pool = WorkerPool(workers=[worker])

        task = WorkerTask(name="test")
        available = pool.get_available_worker(task)

        assert available is worker

    def test_get_available_worker_none(self):
        """Test no available worker."""
        worker = WorkerNode(worker_id="worker1")
        worker.status = WorkerStatus.BUSY
        pool = WorkerPool(workers=[worker])

        task = WorkerTask(name="test")
        available = pool.get_available_worker(task)

        assert available is None

    async def test_submit_task(self):
        """Test submitting single task."""
        worker = WorkerNode(worker_id="worker1")
        worker.register_handler("test", lambda x: {"done": True})
        pool = WorkerPool(workers=[worker])

        task = WorkerTask(name="test")
        state = GraphState(data={})

        result = await pool.submit_task(task, state)

        assert result.success is True
        assert result.output == {"done": True}

    async def test_submit_tasks_parallel(self):
        """Test submitting multiple tasks in parallel."""
        workers = [WorkerNode(worker_id=f"worker{i}") for i in range(3)]
        for worker in workers:
            worker.register_handler("process", lambda x: {"processed": True})

        pool = WorkerPool(workers=workers, max_concurrent_tasks=3)

        tasks = [WorkerTask(name="process") for _ in range(3)]
        state = GraphState(data={})

        results = await pool.submit_tasks(tasks, state)

        assert len(results) == 3
        assert all(r.success for r in results)

    async def test_submit_tasks_priority_order(self):
        """Test tasks are sorted by priority."""
        worker = WorkerNode(worker_id="worker1")
        execution_order = []

        def tracking_handler(data):
            execution_order.append(data.get("id"))
            return {"done": True}

        worker.register_handler("track", tracking_handler)
        pool = WorkerPool(workers=[worker], max_concurrent_tasks=1)

        tasks = [
            WorkerTask(name="track", input_data={"id": "low"}, priority=TaskPriority.LOW),
            WorkerTask(name="track", input_data={"id": "critical"}, priority=TaskPriority.CRITICAL),
            WorkerTask(name="track", input_data={"id": "normal"}, priority=TaskPriority.NORMAL),
        ]
        state = GraphState(data={})

        await pool.submit_tasks(tasks, state)

        # Critical should be first
        assert execution_order[0] == "critical"

    def test_get_pool_stats(self):
        """Test getting pool statistics."""
        workers = [WorkerNode(worker_id=f"worker{i}") for i in range(2)]
        workers[0].tasks_completed = 5
        workers[1].tasks_completed = 3
        pool = WorkerPool(workers=workers)

        stats = pool.get_pool_stats()

        assert stats["worker_count"] == 2
        assert stats["total_tasks_completed"] == 8
        assert stats["idle_workers"] == 2


class TestSupervisorNode:
    """Tests for SupervisorNode."""

    def test_create_supervisor(self):
        """Test creating supervisor node."""
        supervisor = SupervisorNode(
            supervisor_id="supervisor1",
            name="Main Supervisor",
        )

        assert supervisor.supervisor_id == "supervisor1"
        assert supervisor.name == "Main Supervisor"
        assert supervisor.max_iterations == 10

    def test_set_planner(self):
        """Test setting planner function."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")

        def planner(state):
            return [WorkerTask(name="task1")]

        supervisor.set_planner(planner)

        assert supervisor._planner is planner

    def test_set_aggregator(self):
        """Test setting aggregator function."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")

        def aggregator(state, results):
            return {"aggregated": True}

        supervisor.set_aggregator(aggregator)

        assert supervisor._aggregator is aggregator

    def test_set_critic(self):
        """Test setting critic function."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")

        def critic(state):
            return True, "Good", None

        supervisor.set_critic(critic)

        assert supervisor._critic is critic

    async def test_plan_default(self):
        """Test default planning."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")
        state = GraphState(data={"input": "data"})

        tasks = await supervisor.plan(state)

        assert len(tasks) == 1
        assert tasks[0].name == "passthrough"

    async def test_plan_custom(self):
        """Test custom planning function."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")

        def planner(state):
            return [
                WorkerTask(name="task1"),
                WorkerTask(name="task2"),
            ]

        supervisor.set_planner(planner)
        state = GraphState(data={})

        tasks = await supervisor.plan(state)

        assert len(tasks) == 2

    async def test_aggregate_results_default(self):
        """Test default result aggregation."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")
        state = GraphState(data={"existing": "data"})

        results = [
            WorkerTaskResult(
                task_id="t1",
                worker_id="w1",
                success=True,
                output={"new": "value"},
            ),
        ]

        new_state = await supervisor.aggregate_results(state, results)

        assert new_state.data["existing"] == "data"
        assert new_state.data["new"] == "value"

    async def test_critique_default(self):
        """Test default critique."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")
        state = GraphState(data={})

        is_acceptable, _reason, suggestions = await supervisor.critique(state)

        assert is_acceptable is True
        assert suggestions is None

    async def test_should_continue_max_iterations(self):
        """Test continuation check with max iterations."""
        supervisor = SupervisorNode(
            supervisor_id="supervisor1",
            max_iterations=5,
        )
        supervisor.iterations = 5
        state = GraphState(data={})

        should_continue = await supervisor.should_continue(state)

        assert should_continue is False

    async def test_execute_simple(self):
        """Test simple execution cycle."""
        # Create worker
        worker = WorkerNode(worker_id="worker1")
        worker.register_handler("process", lambda x: {"processed": True})

        # Create supervisor
        pool = WorkerPool(workers=[worker])
        supervisor = SupervisorNode(
            supervisor_id="supervisor1",
            worker_pool=pool,
            max_iterations=1,
        )

        def planner(state):
            return [WorkerTask(name="process")]

        supervisor.set_planner(planner)

        state = GraphState(data={"input": "data"})
        final_state, results = await supervisor.execute(state)

        assert len(results) >= 1
        assert final_state.data["processed"] is True

    def test_get_stats(self):
        """Test getting supervisor statistics."""
        supervisor = SupervisorNode(supervisor_id="supervisor1")
        supervisor.iterations = 5
        supervisor.tasks_delegated = 10
        supervisor.decisions_made = 5

        stats = supervisor.get_stats()

        assert stats["supervisor_id"] == "supervisor1"
        assert stats["iterations"] == 5
        assert stats["tasks_delegated"] == 10


class TestSupervisorWorkerOrchestrator:
    """Tests for SupervisorWorkerOrchestrator."""

    async def test_run_successful(self):
        """Test successful orchestration run."""
        # Create worker
        worker = WorkerNode(worker_id="worker1")
        worker.register_handler("process", lambda x: {"processed": True, "_completed": True})

        # Create supervisor
        pool = WorkerPool(workers=[worker])
        supervisor = SupervisorNode(
            supervisor_id="supervisor1",
            worker_pool=pool,
            max_iterations=5,
        )

        def planner(state):
            if state.get("processed"):
                return []
            return [WorkerTask(name="process")]

        supervisor.set_planner(planner)

        # Create orchestrator
        orchestrator = SupervisorWorkerOrchestrator(supervisor=supervisor)

        result = await orchestrator.run({"input": "data"})

        assert result.status == ExecutionStatus.COMPLETED
        assert result.final_state.data["processed"] is True

    async def test_run_with_persistence(self):
        """Test orchestration with persistence."""
        worker = WorkerNode(worker_id="worker1")
        worker.register_handler("process", lambda x: {"done": True, "_completed": True})

        pool = WorkerPool(workers=[worker])
        supervisor = SupervisorNode(
            supervisor_id="supervisor1",
            worker_pool=pool,
        )

        def planner(state):
            if state.get("done"):
                return []
            return [WorkerTask(name="process")]

        supervisor.set_planner(planner)

        # Mock persistence
        mock_persistence = AsyncMock()

        orchestrator = SupervisorWorkerOrchestrator(
            supervisor=supervisor,
            persistence=mock_persistence,
        )

        result = await orchestrator.run({"input": "data"})

        assert result.status == ExecutionStatus.COMPLETED
        mock_persistence.save_state.assert_called()
        mock_persistence.save_execution_result.assert_called()


class TestCreateSupervisorWorker:
    """Tests for create_supervisor_worker factory."""

    def test_create_default(self):
        """Test creating with defaults."""
        orchestrator = create_supervisor_worker()

        assert isinstance(orchestrator, SupervisorWorkerOrchestrator)
        assert orchestrator.supervisor.supervisor_id == "supervisor"
        assert len(orchestrator.supervisor.worker_pool.workers) == 3

    def test_create_with_options(self):
        """Test creating with custom options."""
        orchestrator = create_supervisor_worker(
            supervisor_id="custom",
            worker_count=5,
            max_iterations=20,
        )

        assert orchestrator.supervisor.supervisor_id == "custom"
        assert len(orchestrator.supervisor.worker_pool.workers) == 5
        assert orchestrator.supervisor.max_iterations == 20

    def test_create_with_custom_hash(self):
        """Test creating with custom constitutional hash."""
        orchestrator = create_supervisor_worker(constitutional_hash="custom_hash")

        assert orchestrator.constitutional_hash == "custom_hash"
        assert orchestrator.supervisor.constitutional_hash == "custom_hash"
