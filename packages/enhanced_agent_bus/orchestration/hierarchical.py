"""
ACGS-2 Hierarchical Orchestration
Constitutional Hash: 608508a9bd224290

Implements supervisor-worker topology for multi-agent orchestration.
Based on CEOS architecture with planning, delegation, and critique loops.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum

from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _CritiqueResult(TypedDict):
    """Type definition for critique result."""

    is_passed: bool
    feedback: str
    score: float


try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

logger = get_logger(__name__)
TASK_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)


class NodeStatus(Enum):
    """Status of an orchestration node."""

    IDLE = "idle"
    PLANNING = "planning"
    DELEGATING = "delegating"
    EXECUTING = "executing"
    CRITIQUING = "critiquing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Represents a task to be executed."""

    task_id: str
    description: str
    priority: int = 0  # Higher = more priority
    dependencies: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    result: object | None = None
    status: str = "pending"


@dataclass
class WorkerCapability:
    """Describes what a worker can do."""

    worker_id: str
    capabilities: list[str]  # List of task types this worker can handle
    capacity: int = 1  # Number of concurrent tasks
    current_load: int = 0
    performance_score: float = 1.0  # Historical performance (0.0-1.0)


class SupervisorNode:
    """
    Supervisor node that plans, delegates, and critiques worker execution.

    Implements the CEOS supervisor pattern:
    1. Planning: Break down high-level goals into tasks
    2. Delegation: Assign tasks to appropriate workers
    3. Critique: Review worker outputs and provide feedback
    """

    def __init__(
        self,
        supervisor_id: str = "supervisor",
        llm_client: object | None = None,
        critique_enabled: bool = True,
        require_handoff_contract: bool = True,
    ):
        """
        Initialize supervisor node.

        Args:
            supervisor_id: Unique identifier for this supervisor
            llm_client: Optional LLM client for planning/critique
            critique_enabled: Whether to enable critique loop
            require_handoff_contract: Whether task handoff contract is required
        """
        self.supervisor_id = supervisor_id
        self.llm_client = llm_client
        self.critique_enabled = critique_enabled
        self.require_handoff_contract = require_handoff_contract
        self.status = NodeStatus.IDLE
        self.plan: list[Task] = []
        self.plan_index = 0
        self.worker_capabilities: dict[str, WorkerCapability] = {}
        self.execution_history: list[JSONDict] = []

    def register_worker(self, worker_id: str, capabilities: list[str], capacity: int = 1):
        """Register a worker with its capabilities."""
        self.worker_capabilities[worker_id] = WorkerCapability(
            worker_id=worker_id,
            capabilities=capabilities,
            capacity=capacity,
        )
        logger.info(f"Registered worker {worker_id} with capabilities: {capabilities}")

    async def plan_tasks(self, goal: str, context: JSONDict) -> list[Task]:
        """
        Plan tasks to achieve a goal.

        Args:
            goal: High-level goal description
            context: Context information for planning

        Returns:
            List of planned tasks
        """
        self.status = NodeStatus.PLANNING
        logger.info(f"Planning tasks for goal: {goal}")

        # Simple planning logic (can be enhanced with LLM)
        if self.llm_client:
            # Use LLM for planning if available
            plan = await self._llm_plan(goal, context)
        else:
            # Rule-based planning fallback
            plan = await self._rule_based_plan(goal, context)

        self.plan = plan
        self.plan_index = 0
        self.status = NodeStatus.IDLE
        return plan

    async def _llm_plan(self, goal: str, context: JSONDict) -> list[Task]:
        """Use LLM for task planning."""
        # Placeholder for LLM-based planning
        # Would use DSPy signatures or similar

        return await self._rule_based_plan(goal, context)

    async def _rule_based_plan(self, goal: str, context: JSONDict) -> list[Task]:
        """Rule-based task planning fallback."""
        # Simple rule-based planning
        tasks = [
            Task(
                task_id=f"task_{i}",
                description=f"Step {i + 1} for: {goal}",
                priority=len(context.get("steps", [])) - i,  # Earlier steps have higher priority
                metadata={
                    "goal": goal,
                    "context": context,
                    "handoff_contract": {
                        "owner": "enhanced_agent_bus.supervisor_worker",
                        "input_contract": "Task.v1",
                        "done_criteria": "worker_output_and_critique_recorded",
                    },
                },
            )
            for i in range(len(context.get("steps", [goal])))
        ]
        return tasks

    def _validate_handoff_contract(self, task: Task) -> tuple[bool, str]:
        """Validate cross-agent handoff contract for delegated tasks."""
        if not self.require_handoff_contract:
            return True, "Bypassed: require_handoff_contract=False"

        contract = task.metadata.get("handoff_contract")
        if not isinstance(contract, dict):
            return False, "Missing required handoff contract"

        required_keys = ("owner", "input_contract", "done_criteria")
        missing = [key for key in required_keys if not contract.get(key)]
        if missing:
            return False, f"Missing required handoff keys: {', '.join(missing)}"

        return True, "Handoff contract complete"

    def select_worker(self, task: Task) -> str | None:
        """
        Select the best worker for a task.

        Args:
            task: Task to assign

        Returns:
            Worker ID or None if no suitable worker available
        """
        suitable_workers = []

        for worker_id, capability in self.worker_capabilities.items():
            # Check if worker can handle this task type
            task_type = task.metadata.get("task_type", "generic")
            if task_type in capability.capabilities or "generic" in capability.capabilities:
                # Check if worker has capacity
                if capability.current_load < capability.capacity:
                    suitable_workers.append((worker_id, capability))

        if not suitable_workers:
            return None

        # Select worker with best performance score and lowest load
        suitable_workers.sort(
            key=lambda x: (x[1].performance_score, -x[1].current_load), reverse=True
        )
        selected_worker_id = suitable_workers[0][0]

        # Update worker load
        self.worker_capabilities[selected_worker_id].current_load += 1

        return selected_worker_id

    async def delegate_task(self, task: Task, worker_id: str) -> JSONDict:
        """
        Delegate a task to a worker.

        Args:
            task: Task to delegate
            worker_id: Worker to assign the task to

        Returns:
            Delegation result
        """
        self.status = NodeStatus.DELEGATING
        logger.info(f"Delegating task {task.task_id} to worker {worker_id}")

        handoff_valid, handoff_detail = self._validate_handoff_contract(task)
        if not handoff_valid:
            delegation = {
                "task_id": task.task_id,
                "worker_id": worker_id,
                "timestamp": asyncio.get_running_loop().time(),
                "status": "failed",
                "error": handoff_detail,
            }
            self.execution_history.append(delegation)
            self.status = NodeStatus.IDLE
            return delegation

        delegation = {
            "task_id": task.task_id,
            "worker_id": worker_id,
            "timestamp": asyncio.get_running_loop().time(),
            "status": "delegated",
        }

        self.execution_history.append(delegation)
        self.status = NodeStatus.IDLE
        return delegation

    async def critique_result(self, task: Task, worker_output: JSONDict) -> JSONDict:
        """
        Critique worker output and provide feedback.

        Args:
            task: Original task
            worker_output: Output from worker

        Returns:
            Critique result with pass/fail and feedback
        """
        if not self.critique_enabled:
            return {"is_passed": True, "feedback": "Critique disabled"}

        self.status = NodeStatus.CRITIQUING

        # Simple critique logic (can be enhanced with LLM)
        critique: _CritiqueResult = {
            "is_passed": True,
            "feedback": "",
            "score": 1.0,
        }

        # Check for basic quality indicators
        if not worker_output.get("result"):
            critique["is_passed"] = False
            critique["feedback"] = "No result provided"
            critique["score"] = 0.0
        elif "error" in worker_output:
            critique["is_passed"] = False
            critique["feedback"] = f"Error in execution: {worker_output['error']}"
            critique["score"] = 0.3

        # Update worker performance score
        worker_id = worker_output.get("worker_id")
        if worker_id and worker_id in self.worker_capabilities:
            capability = self.worker_capabilities[worker_id]
            # Update performance score with exponential moving average
            alpha = 0.1
            capability.performance_score = (
                alpha * critique["score"] + (1 - alpha) * capability.performance_score
            )

        self.status = NodeStatus.IDLE
        return dict(critique)  # type: ignore[return-value]

    def get_next_task(self) -> Task | None:
        """Get the next task in the plan."""
        if self.plan_index < len(self.plan):
            task = self.plan[self.plan_index]
            self.plan_index += 1
            return task
        return None

    def has_more_tasks(self) -> bool:
        """Check if there are more tasks in the plan."""
        return self.plan_index < len(self.plan)


class WorkerNode:
    """
    Worker node that executes specific tasks.

    Workers are specialized agents that perform specific types of work.
    """

    def __init__(self, worker_id: str, capabilities: list[str], capacity: int = 1):
        """
        Initialize worker node.

        Args:
            worker_id: Unique identifier for this worker
            capabilities: List of task types this worker can handle
            capacity: Number of concurrent tasks
        """
        self.worker_id = worker_id
        self.capabilities = capabilities
        self.capacity = capacity
        self.current_tasks: set[str] = set()
        self.status = NodeStatus.IDLE

    async def execute_task(self, task: Task) -> JSONDict:
        """
        Execute a task.

        Args:
            task: Task to execute

        Returns:
            Execution result
        """
        if len(self.current_tasks) >= self.capacity:
            raise RuntimeError(f"Worker {self.worker_id} at capacity")

        self.status = NodeStatus.EXECUTING
        self.current_tasks.add(task.task_id)
        logger.info(f"Worker {self.worker_id} executing task {task.task_id}")

        try:
            # Execute task (placeholder - would call actual worker logic)
            result = await self._do_work(task)

            output = {
                "task_id": task.task_id,
                "worker_id": self.worker_id,
                "result": result,
                "status": "completed",
            }

            task.status = "completed"
            task.result = result
            return output
        except TASK_EXECUTION_ERRORS as e:
            logger.error(f"Task execution failed: {e}")
            output = {
                "task_id": task.task_id,
                "worker_id": self.worker_id,
                "error": str(e),
                "status": "failed",
            }
            task.status = "failed"
            return output
        finally:
            self.current_tasks.discard(task.task_id)
            self.status = NodeStatus.IDLE if not self.current_tasks else NodeStatus.EXECUTING

    async def _do_work(self, task: Task) -> object:
        """Perform the actual work (to be implemented by subclasses)."""
        # Placeholder - would be implemented by specific worker types
        await asyncio.sleep(0.1)  # Simulate work
        return {"output": f"Completed {task.description}"}


class HierarchicalOrchestrator:
    """
    Hierarchical orchestrator managing supervisor-worker topology.

    Coordinates the execution of tasks through a supervisor that plans,
    delegates, and critiques worker execution.
    """

    def __init__(self, supervisor: SupervisorNode | None = None):
        """
        Initialize hierarchical orchestrator.

        Args:
            supervisor: Supervisor node (creates default if None)
        """
        self.supervisor = supervisor or SupervisorNode()
        self.workers: dict[str, WorkerNode] = {}
        self.active_tasks: dict[str, Task] = {}
        self.completed_tasks: list[Task] = []

    def register_worker(self, worker: WorkerNode):
        """Register a worker with the orchestrator."""
        self.workers[worker.worker_id] = worker
        self.supervisor.register_worker(worker.worker_id, worker.capabilities, worker.capacity)
        logger.info(f"Registered worker {worker.worker_id}")

    async def execute_goal(self, goal: str, context: JSONDict | None = None) -> JSONDict:
        """
        Execute a high-level goal through hierarchical orchestration.

        Args:
            goal: High-level goal description
            context: Context information

        Returns:
            Execution result with all task results
        """
        context = context or {}
        logger.info(f"Executing goal: {goal}")

        # 1. Planning phase
        plan = await self.supervisor.plan_tasks(goal, context)
        logger.info(f"Planned {len(plan)} tasks")

        # 2. Execution phase with critique loop
        results = []
        max_iterations = len(plan) * 3  # Allow retries
        iteration = 0

        while self.supervisor.has_more_tasks() and iteration < max_iterations:
            iteration += 1

            # Get next task
            task = self.supervisor.get_next_task()
            if not task:
                break

            # Select worker
            worker_id = self.supervisor.select_worker(task)
            if not worker_id:
                logger.warning(f"No available worker for task {task.task_id}")
                task.status = "failed"
                task.result = {"error": "No available worker"}
                results.append(task)
                continue

            # Delegate task
            delegation = await self.supervisor.delegate_task(task, worker_id)
            if delegation.get("status") != "delegated":
                logger.warning(
                    f"Task {task.task_id} handoff validation failed: {delegation.get('error')}"
                )
                task.status = "failed"
                task.result = {"error": delegation.get("error", "Delegation failed")}
                results.append(task)
                continue

            # Execute task
            worker = self.workers[worker_id]
            worker_output = await worker.execute_task(task)

            # Critique result
            critique = await self.supervisor.critique_result(task, worker_output)

            # Handle critique feedback
            if not critique["is_passed"]:
                logger.warning(f"Task {task.task_id} failed critique: {critique['feedback']}")
                # Could retry or escalate here
                if "retry" in task.metadata and task.metadata["retry"] < 3:
                    task.metadata["retry"] = task.metadata.get("retry", 0) + 1
                    self.supervisor.plan_index -= 1  # Retry this task
                    continue

            results.append(task)
            self.completed_tasks.append(task)

        # 3. Summary
        summary = {
            "goal": goal,
            "total_tasks": len(plan),
            "completed_tasks": len([t for t in results if t.status == "completed"]),
            "failed_tasks": len([t for t in results if t.status == "failed"]),
            "results": [
                {"task_id": t.task_id, "status": t.status, "result": t.result} for t in results
            ],
        }

        logger.info(
            f"Goal execution completed: {summary['completed_tasks']}/{summary['total_tasks']} tasks"
        )
        return summary
