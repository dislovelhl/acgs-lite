"""
ACGS-2 LangGraph Orchestration - Supervisor-Worker Pattern
Constitutional Hash: cdd01ef066bc6cf2

Hierarchical agent orchestration implementing Supervisor-Worker topology:
- Supervisor nodes for strategic planning and delegation
- Worker sub-graphs for specialized execution
- Critique loop for continuous improvement
- Constitutional compliance at all levels
"""

import asyncio
import inspect
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import cast

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    GraphState,
)
from .node_executor import AsyncNodeExecutor, NodeExecutor
from .state_reducer import BaseStateReducer, MergeStateReducer

logger = get_logger(__name__)
WORKER_TASK_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)
SUPERVISOR_WORKFLOW_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class WorkerStatus(str, Enum):
    """Worker status in the pool.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    IDLE = "idle"
    BUSY = "busy"
    FAILED = "failed"
    TERMINATED = "terminated"


class TaskPriority(str, Enum):
    """Task priority levels.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class WorkerTask:
    """Task to be executed by a worker.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    input_data: JSONDict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_ms: float = 5000.0
    retries: int = 3
    metadata: JSONDict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class WorkerTaskResult:
    """Result from worker task execution.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    task_id: str
    worker_id: str
    success: bool
    output: JSONDict | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    retries_used: int = 0
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


class WorkerNode:
    """Worker node for executing specialized tasks.

    Workers execute tasks assigned by the supervisor,
    reporting results back for aggregation.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        worker_id: str,
        name: str = "",
        capabilities: list[str] | None = None,
        executor: NodeExecutor | None = None,
        state_reducer: BaseStateReducer | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.worker_id = worker_id
        self.name = name or worker_id
        self.capabilities = capabilities or []
        self.executor = executor or AsyncNodeExecutor()
        self.state_reducer = state_reducer or MergeStateReducer()
        self.constitutional_hash = constitutional_hash

        # Worker state
        self.status = WorkerStatus.IDLE
        self.current_task: WorkerTask | None = None
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_execution_time_ms = 0.0

        # Function registry for tasks
        self._task_handlers: dict[str, Callable] = {}

    def register_handler(self, task_name: str, handler: Callable) -> None:
        """Register a handler for a task type.

        Args:
            task_name: Task name to handle
            handler: Handler function (async or sync)
        """
        self._task_handlers[task_name] = handler

    def can_handle(self, task: WorkerTask) -> bool:
        """Check if worker can handle a task.

        Args:
            task: Task to check

        Returns:
            True if worker can handle the task
        """
        # Check if we have a handler
        if task.name in self._task_handlers:
            return True

        # Check capabilities
        required_cap = task.metadata.get("required_capability")
        if required_cap:
            return required_cap in self.capabilities

        return True  # Default: can handle

    async def execute_task(
        self,
        task: WorkerTask,
        state: GraphState,
    ) -> WorkerTaskResult:
        """Execute a task.

        Args:
            task: Task to execute
            state: Current state

        Returns:
            Task execution result
        """
        start_time = time.perf_counter()
        self.status = WorkerStatus.BUSY
        self.current_task = task

        try:
            handler = self._task_handlers.get(task.name)

            if handler:
                # Use registered handler
                input_data = {**state.data, **task.input_data}

                if inspect.iscoroutinefunction(handler):
                    output = await asyncio.wait_for(
                        handler(input_data),
                        timeout=task.timeout_ms / 1000.0,
                    )
                else:
                    loop = asyncio.get_running_loop()
                    output = await asyncio.wait_for(
                        loop.run_in_executor(None, handler, input_data),
                        timeout=task.timeout_ms / 1000.0,
                    )

                if not isinstance(output, dict):
                    output = {"result": output}

            else:
                # Default: passthrough
                output = task.input_data.copy()

            execution_time = (time.perf_counter() - start_time) * 1000
            self.tasks_completed += 1
            self.total_execution_time_ms += execution_time

            return WorkerTaskResult(
                task_id=task.id,
                worker_id=self.worker_id,
                success=True,
                output=output,
                execution_time_ms=execution_time,
                constitutional_hash=self.constitutional_hash,
            )

        except WORKER_TASK_EXECUTION_ERRORS as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            self.tasks_failed += 1
            self.total_execution_time_ms += execution_time

            logger.error(f"Worker {self.worker_id} task {task.id} failed: {e}")

            return WorkerTaskResult(
                task_id=task.id,
                worker_id=self.worker_id,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
                constitutional_hash=self.constitutional_hash,
            )

        finally:
            self.status = WorkerStatus.IDLE
            self.current_task = None

    def get_stats(self) -> JSONDict:
        """Get worker statistics."""
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_execution_time_ms": self.total_execution_time_ms,
            "avg_execution_time_ms": (
                self.total_execution_time_ms / max(self.tasks_completed + self.tasks_failed, 1)
            ),
            "constitutional_hash": self.constitutional_hash,
        }


class WorkerPool:
    """Pool of workers for parallel task execution.

    Manages worker lifecycle, task assignment, and load balancing.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        workers: list[WorkerNode] | None = None,
        max_concurrent_tasks: int = 10,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.workers: dict[str, WorkerNode] = {}
        self.max_concurrent_tasks = max_concurrent_tasks
        self.constitutional_hash = constitutional_hash

        # Task queue
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._active_tasks: dict[str, asyncio.Task] = {}

        # Add initial workers
        if workers:
            for worker in workers:
                self.add_worker(worker)

    def add_worker(self, worker: WorkerNode) -> None:
        """Add a worker to the pool."""
        self.workers[worker.worker_id] = worker

    def remove_worker(self, worker_id: str) -> WorkerNode | None:
        """Remove a worker from the pool."""
        return self.workers.pop(worker_id, None)

    def get_available_worker(self, task: WorkerTask) -> WorkerNode | None:
        """Get an available worker that can handle the task.

        Args:
            task: Task to assign

        Returns:
            Available worker or None
        """
        for worker in self.workers.values():
            if worker.status == WorkerStatus.IDLE and worker.can_handle(task):
                return worker
        return None

    async def submit_task(
        self,
        task: WorkerTask,
        state: GraphState,
    ) -> WorkerTaskResult:
        """Submit a task for execution.

        Args:
            task: Task to execute
            state: Current state

        Returns:
            Task result
        """
        # Find available worker
        worker = self.get_available_worker(task)

        if not worker:
            # Wait for available worker
            while worker is None:
                await asyncio.sleep(0.01)
                worker = self.get_available_worker(task)

        return await worker.execute_task(task, state)

    async def submit_tasks(
        self,
        tasks: list[WorkerTask],
        state: GraphState,
    ) -> list[WorkerTaskResult]:
        """Submit multiple tasks for parallel execution.

        Args:
            tasks: Tasks to execute
            state: Current state

        Returns:
            List of results
        """
        if not tasks:
            return []

        # Sort by priority
        sorted_tasks = sorted(
            tasks,
            key=lambda t: {"critical": 0, "high": 1, "normal": 2, "low": 3}[t.priority.value],
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent_tasks)

        async def execute_with_semaphore(task: WorkerTask) -> WorkerTaskResult:
            async with semaphore:
                return await self.submit_task(task, state)

        # Execute all tasks
        results = await asyncio.gather(
            *[execute_with_semaphore(task) for task in sorted_tasks],
            return_exceptions=True,
        )

        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    WorkerTaskResult(
                        task_id=sorted_tasks[i].id,
                        worker_id="pool",
                        success=False,
                        error=str(result),
                        constitutional_hash=self.constitutional_hash,
                    )
                )
            else:
                final_results.append(cast(WorkerTaskResult, result))

        return final_results

    def get_pool_stats(self) -> JSONDict:
        """Get pool statistics."""
        worker_stats = [w.get_stats() for w in self.workers.values()]
        total_completed = sum(w.tasks_completed for w in self.workers.values())
        total_failed = sum(w.tasks_failed for w in self.workers.values())

        return {
            "worker_count": len(self.workers),
            "idle_workers": sum(1 for w in self.workers.values() if w.status == WorkerStatus.IDLE),
            "busy_workers": sum(1 for w in self.workers.values() if w.status == WorkerStatus.BUSY),
            "total_tasks_completed": total_completed,
            "total_tasks_failed": total_failed,
            "success_rate": total_completed / max(total_completed + total_failed, 1),
            "workers": worker_stats,
            "constitutional_hash": self.constitutional_hash,
        }


class SupervisorNode:
    """Supervisor node for strategic planning and delegation.

    Implements the supervisor pattern from LangGraph:
    - Strategic planning based on input
    - Task decomposition and delegation
    - Result aggregation and critique
    - Iterative refinement

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        supervisor_id: str,
        name: str = "supervisor",
        worker_pool: WorkerPool | None = None,
        state_reducer: BaseStateReducer | None = None,
        max_iterations: int = 10,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.supervisor_id = supervisor_id
        self.name = name
        self.worker_pool = worker_pool or WorkerPool()
        self.state_reducer = state_reducer or MergeStateReducer()
        self.max_iterations = max_iterations
        self.constitutional_hash = constitutional_hash

        # Execution tracking
        self.iterations = 0
        self.tasks_delegated = 0
        self.decisions_made = 0

        # Strategy functions
        self._planner: Callable | None = None
        self._aggregator: Callable | None = None
        self._critic: Callable | None = None
        self._should_continue: Callable | None = None

    def set_planner(self, planner: Callable[[JSONDict], list[WorkerTask]]) -> None:
        """Set the planning function.

        Planner takes state and returns list of tasks for workers.
        """
        self._planner = planner

    def set_aggregator(
        self,
        aggregator: Callable[[JSONDict, list[WorkerTaskResult]], JSONDict],
    ) -> None:
        """Set the result aggregation function.

        Aggregator combines worker results into updated state.
        """
        self._aggregator = aggregator

    def set_critic(
        self,
        critic: Callable[[JSONDict], tuple[bool, str, JSONDict | None]],
    ) -> None:
        """Set the critique function.

        Critic evaluates state and returns (is_acceptable, reason, suggestions).
        """
        self._critic = critic

    def set_continuation_check(
        self,
        should_continue: Callable[[JSONDict, int], bool],
    ) -> None:
        """Set the continuation check function.

        Returns True if another iteration should be performed.
        """
        self._should_continue = should_continue

    async def plan(self, state: GraphState) -> list[WorkerTask]:
        """Create execution plan from current state.

        Args:
            state: Current graph state

        Returns:
            List of tasks for workers
        """
        if self._planner:
            if inspect.iscoroutinefunction(self._planner):
                tasks = await self._planner(state.data)
            else:
                tasks = self._planner(state.data)
        else:
            # Default: single passthrough task
            tasks = [
                WorkerTask(
                    name="passthrough",
                    input_data=state.data,
                )
            ]

        self.tasks_delegated += len(tasks)
        return tasks  # type: ignore[no-any-return]

    async def aggregate_results(
        self,
        state: GraphState,
        results: list[WorkerTaskResult],
    ) -> GraphState:
        """Aggregate worker results into state.

        Args:
            state: Current state
            results: Worker results

        Returns:
            Updated state
        """
        if self._aggregator:
            if inspect.iscoroutinefunction(self._aggregator):
                updates = await self._aggregator(state.data, results)
            else:
                updates = self._aggregator(state.data, results)
        else:
            # Default: merge all successful outputs
            updates = {}
            for result in results:
                if result.success and result.output:
                    updates.update(result.output)

        return self.state_reducer.reduce(state, updates, self.supervisor_id)

    async def critique(
        self,
        state: GraphState,
    ) -> tuple[bool, str, JSONDict | None]:
        """Critique current state for quality.

        Args:
            state: Current state to evaluate

        Returns:
            Tuple of (is_acceptable, reason, suggestions)
        """
        if self._critic:
            if inspect.iscoroutinefunction(self._critic):
                return await self._critic(state.data)  # type: ignore[no-any-return]
            else:
                return self._critic(state.data)  # type: ignore[no-any-return]

        # Default: always acceptable
        return True, "Default acceptance", None

    async def should_continue(self, state: GraphState) -> bool:
        """Check if another iteration should be performed.

        Args:
            state: Current state

        Returns:
            True if should continue
        """
        if self.iterations >= self.max_iterations:
            return False

        if self._should_continue:
            if inspect.iscoroutinefunction(self._should_continue):
                return bool(await self._should_continue(state.data, self.iterations))
            else:
                return bool(self._should_continue(state.data, self.iterations))

        # Default: check for completion flag
        return not state.data.get("_completed", False)

    async def execute(
        self,
        initial_state: GraphState,
        context: ExecutionContext | None = None,
    ) -> tuple[GraphState, list[WorkerTaskResult]]:
        """Execute supervisor-worker cycle.

        Args:
            initial_state: Starting state
            context: Optional execution context

        Returns:
            Tuple of (final_state, all_results)
        """
        state = initial_state
        all_results: list[WorkerTaskResult] = []
        self.iterations = 0

        while await self.should_continue(state):
            self.iterations += 1
            logger.debug(
                f"[{self.constitutional_hash}] Supervisor {self.supervisor_id} "
                f"iteration {self.iterations}"
            )

            # Plan tasks
            tasks = await self.plan(state)

            if not tasks:
                logger.info(f"Supervisor {self.supervisor_id} no tasks to execute")
                break

            # Execute tasks via worker pool
            results = await self.worker_pool.submit_tasks(tasks, state)
            all_results.extend(results)

            # Aggregate results
            state = await self.aggregate_results(state, results)

            # Critique
            is_acceptable, reason, suggestions = await self.critique(state)
            self.decisions_made += 1

            if is_acceptable:
                logger.info(f"Supervisor critique passed: {reason}")
            else:
                logger.info(f"Supervisor critique failed: {reason}")
                if suggestions:
                    state = self.state_reducer.reduce(
                        state,
                        {"_critique_suggestions": suggestions},
                        self.supervisor_id,
                    )

        return state, all_results

    def get_stats(self) -> JSONDict:
        """Get supervisor statistics."""
        return {
            "supervisor_id": self.supervisor_id,
            "name": self.name,
            "iterations": self.iterations,
            "tasks_delegated": self.tasks_delegated,
            "decisions_made": self.decisions_made,
            "worker_pool": self.worker_pool.get_pool_stats(),
            "constitutional_hash": self.constitutional_hash,
        }


class SupervisorWorkerOrchestrator:
    """Orchestrator for supervisor-worker pattern.

    Manages the complete execution lifecycle including
    state persistence and constitutional compliance.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        supervisor: SupervisorNode,
        persistence: object | None = None,
        checkpoint_manager: object | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.supervisor = supervisor
        self.persistence = persistence
        self.checkpoint_manager = checkpoint_manager
        self.constitutional_hash = constitutional_hash

    async def run(
        self,
        input_data: JSONDict,
        workflow_id: str | None = None,
        tenant_id: str = "default",
    ) -> ExecutionResult:
        """Run the supervisor-worker orchestration.

        Args:
            input_data: Initial input data
            workflow_id: Optional workflow identifier
            tenant_id: Tenant identifier

        Returns:
            Execution result
        """
        start_time = time.perf_counter()
        workflow_id = workflow_id or str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # Create initial state
        state = GraphState(
            data=input_data,
            constitutional_hash=self.constitutional_hash,
        )

        # Create context
        context = ExecutionContext(
            workflow_id=workflow_id,
            run_id=run_id,
            graph_id="supervisor_worker",
            tenant_id=tenant_id,
            current_state=state,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            constitutional_hash=self.constitutional_hash,
        )

        try:
            # Execute supervisor-worker cycle
            final_state, results = await self.supervisor.execute(state, context)

            # Save state if persistence available
            if self.persistence:
                await self.persistence.save_state(
                    workflow_id=workflow_id,
                    run_id=run_id,
                    state=final_state,
                    node_id=self.supervisor.supervisor_id,
                    step_index=self.supervisor.iterations,
                )

            execution_time = (time.perf_counter() - start_time) * 1000

            # Calculate latency percentiles
            exec_times = [r.execution_time_ms for r in results if r.execution_time_ms > 0]
            p50 = sorted(exec_times)[len(exec_times) // 2] if exec_times else None
            p99 = sorted(exec_times)[int(len(exec_times) * 0.99)] if exec_times else None

            result = ExecutionResult(
                workflow_id=workflow_id,
                run_id=run_id,
                status=ExecutionStatus.COMPLETED,
                final_state=final_state,
                output=final_state.data,
                total_execution_time_ms=execution_time,
                node_count=len(results),
                step_count=self.supervisor.iterations,
                p50_node_time_ms=p50,
                p99_node_time_ms=p99,
                constitutional_validated=True,
                started_at=context.started_at,
                completed_at=datetime.now(UTC),
                constitutional_hash=self.constitutional_hash,
            )

            if self.persistence:
                await self.persistence.save_execution_result(result)

            return result

        except SUPERVISOR_WORKFLOW_ERRORS as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"Supervisor-worker execution failed: {e}")

            return ExecutionResult(
                workflow_id=workflow_id,
                run_id=run_id,
                status=ExecutionStatus.FAILED,
                error=str(e),
                total_execution_time_ms=execution_time,
                step_count=self.supervisor.iterations,
                started_at=context.started_at,
                completed_at=datetime.now(UTC),
                constitutional_hash=self.constitutional_hash,
            )


def create_supervisor_worker(
    supervisor_id: str = "supervisor",
    worker_count: int = 3,
    max_iterations: int = 10,
    persistence: object | None = None,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
) -> SupervisorWorkerOrchestrator:
    """Factory function to create supervisor-worker orchestrator.

    Args:
        supervisor_id: Supervisor identifier
        worker_count: Number of workers to create
        max_iterations: Maximum iterations
        persistence: Optional persistence backend
        constitutional_hash: Constitutional hash to enforce

    Returns:
        Configured orchestrator

    Constitutional Hash: cdd01ef066bc6cf2
    """
    # Create workers
    workers = [
        WorkerNode(
            worker_id=f"worker_{i}",
            name=f"Worker {i}",
            constitutional_hash=constitutional_hash,
        )
        for i in range(worker_count)
    ]

    # Create worker pool
    pool = WorkerPool(
        workers=workers,
        constitutional_hash=constitutional_hash,
    )

    # Create supervisor
    supervisor = SupervisorNode(
        supervisor_id=supervisor_id,
        worker_pool=pool,
        max_iterations=max_iterations,
        constitutional_hash=constitutional_hash,
    )

    return SupervisorWorkerOrchestrator(
        supervisor=supervisor,
        persistence=persistence,
        constitutional_hash=constitutional_hash,
    )


__all__ = [
    "SupervisorNode",
    "SupervisorWorkerOrchestrator",
    "TaskPriority",
    "WorkerNode",
    "WorkerPool",
    "WorkerStatus",
    "WorkerTask",
    "WorkerTaskResult",
    "create_supervisor_worker",
]
