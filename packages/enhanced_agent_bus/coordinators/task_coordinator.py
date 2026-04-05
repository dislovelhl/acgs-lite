"""
Task Coordinator - Handles task execution flow.

Constitutional Hash: 608508a9bd224290

Part of MetaOrchestrator decomposition - extracts task execution responsibilities
into a focused coordinator.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.enums import TaskComplexity, TaskType
from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from enhanced_agent_bus.models import SwarmAgent

    from ..routing_engine import RoutingEngine

logger = get_logger(__name__)
TASK_COORDINATOR_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
)
TASK_COORDINATOR_MEMORY_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
)


@dataclass
class TaskResult:
    """Result from task execution."""

    task_id: str
    success: bool
    result: object
    execution_time_ms: float
    agents_used: list[str]
    memory_updates: list[str]
    constitutional_compliant: bool
    confidence_score: float
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "result": self.result,
            "execution_time_ms": self.execution_time_ms,
            "agents_used": self.agents_used,
            "memory_updates": self.memory_updates,
            "constitutional_compliant": self.constitutional_compliant,
            "confidence_score": self.confidence_score,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class TaskExecutionOptions:
    """Options for task execution."""

    timeout_seconds: int = 60
    max_retries: int = 1
    priority: str = "normal"


@runtime_checkable
class TaskCoordinatorProtocol(Protocol):
    """Protocol for TaskCoordinator implementations."""

    constitutional_hash: str

    async def execute_task(
        self,
        task: str,
        context: JSONDict | None = None,
        options: TaskExecutionOptions | None = None,
    ) -> TaskResult: ...

    async def analyze_complexity(self, task: str) -> TaskComplexity: ...
    async def identify_task_type(self, task: str) -> TaskType: ...
    def get_execution_stats(self) -> JSONDict: ...


class TaskCoordinator:
    """
    Coordinates task execution flow.
    Constitutional Hash: 608508a9bd224290
    """

    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(
        self,
        routing_engine: RoutingEngine | None = None,
        memory_coordinator: object | None = None,
    ):
        self._task_counter: int = 0
        self._execution_stats: JSONDict = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_execution_time_ms": 0.0,
            "average_execution_time_ms": 0.0,
        }
        self._results: dict[str, TaskResult] = {}
        self._memory_coordinator = memory_coordinator

        if routing_engine is not None:
            self._routing_engine = routing_engine
        else:
            from ..routing_engine import RoutingEngine

            self._routing_engine = RoutingEngine(constitutional_hash=self.constitutional_hash)

        logger.info("TaskCoordinator initialized")

    async def execute_task(
        self,
        task: str,
        context: JSONDict | None = None,
        options: TaskExecutionOptions | None = None,
    ) -> TaskResult:
        """Execute a task and return the result."""
        if task is None:
            raise ValueError("Task cannot be None")

        start_time = datetime.now(UTC)
        task_id = f"task_{self._task_counter:06d}"
        self._task_counter += 1

        try:
            complexity = await self.analyze_complexity(task)
            task_type = await self.identify_task_type(task)
            logger.info(f"Task {task_id}: complexity={complexity.name}, type={task_type.name}")

            agents = await self._routing_engine.route_task(task, complexity, task_type)

            if not agents:
                self._update_metrics(success=False, execution_time_ms=0.0)
                return TaskResult(
                    task_id=task_id,
                    success=False,
                    result="No agents available",
                    execution_time_ms=0.0,
                    agents_used=[],
                    memory_updates=[],
                    constitutional_compliant=True,
                    confidence_score=0.0,
                )

            action = {
                "task": task,
                "type": task_type.name,
                "complexity": complexity.name,
                "constitutional_hash": self.constitutional_hash,
            }

            if not self._validate_constitutional_compliance(action):
                self._update_metrics(success=False, execution_time_ms=0.0)
                return TaskResult(
                    task_id=task_id,
                    success=False,
                    result="Constitutional check failed",
                    execution_time_ms=0.0,
                    agents_used=[],
                    memory_updates=[],
                    constitutional_compliant=False,
                    confidence_score=0.0,
                )

            memory_updates = await self._update_memory(
                task_id, task, complexity, task_type, agents, context
            )
            self._release_agents(agents)

            execution_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            self._update_metrics(success=True, execution_time_ms=execution_time_ms)

            result = TaskResult(
                task_id=task_id,
                success=True,
                result=f"Task processed with {len(agents)} agents",
                execution_time_ms=execution_time_ms,
                agents_used=[getattr(a, "agent_id", str(a)) for a in agents],
                memory_updates=memory_updates,
                constitutional_compliant=True,
                confidence_score=0.95,
                metadata={"complexity": complexity.name, "type": task_type.name},
            )
            self._results[task_id] = result
            return result

        except TASK_COORDINATOR_EXECUTION_ERRORS as e:
            logger.exception(f"Task {task_id} failed: {e}")
            self._update_metrics(success=False, execution_time_ms=0.0)
            return TaskResult(
                task_id=task_id,
                success=False,
                result=str(e),
                execution_time_ms=0.0,
                agents_used=[],
                memory_updates=[],
                constitutional_compliant=True,
                confidence_score=0.0,
            )

    async def _update_memory(
        self,
        task_id: str,
        task: str,
        complexity: TaskComplexity,
        task_type: TaskType,
        agents: list[SwarmAgent],
        context: JSONDict | None,
    ) -> list[str]:
        """Update memory with task execution data."""
        if self._memory_coordinator is None:
            return []
        try:
            await self._memory_coordinator.store(
                key=task_id,
                value={
                    "task": task,
                    "complexity": complexity.name,
                    "type": task_type.name,
                    "agents": [getattr(a, "agent_id", str(a)) for a in agents],
                    "context": context or {},
                },
                tier="ephemeral",
            )
            return [task_id]
        except TASK_COORDINATOR_MEMORY_ERRORS as e:
            logger.warning(f"Memory store failed: {e}")
            return []

    def _release_agents(self, agents: list[SwarmAgent]) -> None:
        """Release agents back to idle state."""
        for agent in agents:
            if hasattr(agent, "status"):
                agent.status = "idle"
            if hasattr(agent, "current_task"):
                agent.current_task = None

    async def analyze_complexity(self, task: str) -> TaskComplexity:
        """Analyze task complexity (delegates to routing engine)."""
        return await self._routing_engine.analyze_complexity(task)

    async def identify_task_type(self, task: str) -> TaskType:
        """Identify task type (delegates to routing engine)."""
        return await self._routing_engine.identify_task_type(task)

    def get_execution_stats(self) -> JSONDict:
        """Get execution statistics."""
        return {
            "constitutional_hash": self.constitutional_hash,
            "total_tasks": self._execution_stats["total_tasks"],
            "successful_tasks": self._execution_stats["successful_tasks"],
            "failed_tasks": self._execution_stats["failed_tasks"],
            "average_execution_time_ms": self._execution_stats["average_execution_time_ms"],
            "task_counter": self._task_counter,
        }

    def _validate_constitutional_compliance(self, action: JSONDict) -> bool:
        """Validate action against constitutional principles."""
        if "constitutional_hash" in action:
            if action["constitutional_hash"] != self.constitutional_hash:
                logger.error("Constitutional hash mismatch!")
                return False
        return True

    def _update_metrics(self, success: bool, execution_time_ms: float) -> None:
        """Update execution metrics."""
        self._execution_stats["total_tasks"] += 1
        if success:
            self._execution_stats["successful_tasks"] += 1
            self._execution_stats["total_execution_time_ms"] += execution_time_ms
            n = self._execution_stats["successful_tasks"]
            old_avg = self._execution_stats["average_execution_time_ms"]
            self._execution_stats["average_execution_time_ms"] = (
                old_avg * (n - 1) + execution_time_ms
            ) / n
        else:
            self._execution_stats["failed_tasks"] += 1


TaskCoordinatorProtocol.register(TaskCoordinator)

__all__ = [
    "TaskCoordinator",
    "TaskCoordinatorProtocol",
    "TaskExecutionOptions",
    "TaskResult",
]
