"""
ACGS-2 Enhanced Agent Bus - Agent Entity Workflow
Constitutional Hash: 608508a9bd224290

Long-lived workflow representing a single agent instance lifecycle.
Implements the Entity Workflow pattern (Actor Model) for agent management.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .workflow_base import WorkflowContext, WorkflowDefinition, query, signal

logger = get_logger(__name__)
_AGENT_WORKFLOW_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AgentState(Enum):
    """Agent lifecycle states.

    Constitutional Hash: 608508a9bd224290
    """

    INITIALIZING = "initializing"
    IDLE = "idle"
    PROCESSING = "processing"
    SUSPENDED = "suspended"
    RECOVERING = "recovering"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class AgentConfig:
    """Configuration for agent initialization.

    Constitutional Hash: 608508a9bd224290
    """

    agent_id: str
    agent_type: str
    capabilities: list[str] = field(default_factory=list)
    max_concurrent_tasks: int = 5
    idle_timeout_seconds: float = 3600.0  # 1 hour
    heartbeat_interval_seconds: float = 30.0
    checkpoint_interval_seconds: float = 300.0  # 5 minutes
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "capabilities": self.capabilities,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "checkpoint_interval_seconds": self.checkpoint_interval_seconds,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class Task:
    """Task to be executed by an agent.

    Constitutional Hash: 608508a9bd224290
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    payload: JSONDict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: float = 300.0
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "priority": self.priority.value,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class TaskResult:
    """Result of task execution.

    Constitutional Hash: 608508a9bd224290
    """

    task_id: str
    success: bool
    result: JSONDict | None = None
    error: str | None = None
    duration_ms: float = 0.0
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "completed_at": self.completed_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class AgentStatus:
    """Current status of an agent.

    Constitutional Hash: 608508a9bd224290
    """

    agent_id: str
    state: AgentState
    current_task: str | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_pending: int = 0
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    uptime_seconds: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "current_task": self.current_task,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_pending": self.tasks_pending,
            "last_activity": self.last_activity.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "memory_usage_mb": self.memory_usage_mb,
            "cpu_usage_percent": self.cpu_usage_percent,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class AgentResult:
    """Final result of agent lifecycle.

    Constitutional Hash: 608508a9bd224290
    """

    agent_id: str
    final_state: AgentState
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    total_runtime_seconds: float = 0.0
    shutdown_reason: str = ""
    checkpoints: list[JSONDict] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "final_state": self.final_state.value,
            "total_tasks_completed": self.total_tasks_completed,
            "total_tasks_failed": self.total_tasks_failed,
            "total_runtime_seconds": self.total_runtime_seconds,
            "shutdown_reason": self.shutdown_reason,
            "checkpoints": self.checkpoints,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ShutdownRequest:
    """Request to shutdown an agent.

    Constitutional Hash: 608508a9bd224290
    """

    agent_id: str
    reason: str = "requested"
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "reason": self.reason,
            "constitutional_hash": self.constitutional_hash,
        }


# =============================================================================
# Workflow Activities
# =============================================================================


class WorkflowActivity:
    """Base class for workflow activities.

    Constitutional Hash: 608508a9bd224290
    """

    activity_name: str = ""
    activity_timeout_seconds: float = 60.0

    @property
    def name(self) -> str:
        """Activity name."""
        return self.activity_name or self.__class__.__name__

    @property
    def timeout_seconds(self) -> float:
        """Activity timeout."""
        return self.activity_timeout_seconds


class InitializeAgentActivity(WorkflowActivity):
    """Activity to initialize an agent.

    Constitutional Hash: 608508a9bd224290
    """

    activity_name = "initialize_agent"
    activity_timeout_seconds = 30.0

    async def execute(self, config: AgentConfig, context: WorkflowContext) -> JSONDict:
        """Initialize the agent.

        Args:
            config: Agent configuration
            context: Workflow context

        Returns:
            Initialization result
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Initializing agent {config.agent_id} "
            f"of type {config.agent_type}"
        )

        # Simulate initialization work
        await asyncio.sleep(0.01)  # Small delay for realism

        # Validate constitutional compliance
        if config.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Constitutional hash mismatch: expected {CONSTITUTIONAL_HASH}, "
                f"got {config.constitutional_hash}"
            )

        return {
            "status": "initialized",
            "agent_id": config.agent_id,
            "capabilities": config.capabilities,
            "initialized_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


class ExecuteTaskActivity(WorkflowActivity):
    """Activity to execute a task.

    Constitutional Hash: 608508a9bd224290
    """

    activity_name = "execute_task"
    activity_timeout_seconds = 300.0

    async def execute(self, task: Task, context: WorkflowContext) -> TaskResult:
        """Execute a task.

        Args:
            task: Task to execute
            context: Workflow context

        Returns:
            Task execution result
        """
        start_time = datetime.now(UTC)
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Executing task {task.task_id} of type {task.task_type}"
        )

        try:
            # Validate constitutional compliance
            if task.constitutional_hash != CONSTITUTIONAL_HASH:
                raise ValueError("Constitutional hash mismatch")

            # Simulate task execution (would be replaced with actual logic)
            await asyncio.sleep(0.01)

            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return TaskResult(
                task_id=task.task_id,
                success=True,
                result={"processed": True, "task_type": task.task_type},
                duration_ms=duration,
            )

        except _AGENT_WORKFLOW_OPERATION_ERRORS as e:
            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000
            logger.error(f"[{CONSTITUTIONAL_HASH}] Task {task.task_id} failed: {e}")
            return TaskResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                duration_ms=duration,
            )


class CheckpointAgentActivity(WorkflowActivity):
    """Activity to checkpoint agent state.

    Constitutional Hash: 608508a9bd224290
    """

    activity_name = "checkpoint_agent"
    activity_timeout_seconds = 10.0

    async def execute(self, status: AgentStatus, context: WorkflowContext) -> JSONDict:
        """Create a checkpoint of agent state.

        Args:
            status: Current agent status
            context: Workflow context

        Returns:
            Checkpoint data
        """

        checkpoint = {
            "checkpoint_id": str(uuid.uuid4()),
            "agent_id": status.agent_id,
            "state": status.state.value,
            "tasks_completed": status.tasks_completed,
            "tasks_failed": status.tasks_failed,
            "checkpoint_time": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        return checkpoint


class ShutdownAgentActivity(WorkflowActivity):
    """Activity to shutdown an agent.

    Constitutional Hash: 608508a9bd224290
    """

    activity_name = "shutdown_agent"
    activity_timeout_seconds = 30.0

    async def execute(self, request: "ShutdownRequest", context: WorkflowContext) -> JSONDict:
        """Shutdown the agent.

        Args:
            request: Shutdown request containing agent_id and reason
            context: Workflow context

        Returns:
            Shutdown result
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Shutting down agent {request.agent_id}: {request.reason}"
        )

        # Simulate graceful shutdown
        await asyncio.sleep(0.01)

        return {
            "status": "shutdown",
            "agent_id": request.agent_id,
            "reason": request.reason,
            "shutdown_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# Activity instances for convenience
initialize_agent_activity = InitializeAgentActivity()
execute_task_activity = ExecuteTaskActivity()
checkpoint_agent_activity = CheckpointAgentActivity()
shutdown_agent_activity = ShutdownAgentActivity()

# =============================================================================
# Agent Entity Workflow
# =============================================================================


class AgentEntityWorkflow(WorkflowDefinition[AgentConfig, AgentResult]):
    """Long-lived workflow representing a single agent instance.

    This workflow implements the Entity Workflow pattern (Actor Model):
    - Receives tasks via signals
    - Maintains agent state across tasks
    - Supports queries for status inspection
    - Handles graceful shutdown

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self) -> None:
        super().__init__()
        self._state: AgentState = AgentState.INITIALIZING
        self._config: AgentConfig | None = None
        self._task_queue: asyncio.Queue[Task] = asyncio.Queue()
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._current_task: str | None = None
        self._shutdown_requested: bool = False
        self._shutdown_reason: str = ""
        self._suspend_requested: bool = False
        self._checkpoints: list[JSONDict] = []
        self._start_time: datetime = datetime.now(UTC)
        self._last_activity: datetime = datetime.now(UTC)
        self._task_results: list[TaskResult] = []

    @property
    def name(self) -> str:
        """Workflow name."""
        return "AgentEntityWorkflow"

    @property
    def state(self) -> AgentState:
        """Current agent state."""
        return self._state

    @property
    def config(self) -> AgentConfig | None:
        """Agent configuration."""
        return self._config

    async def run(self, config: AgentConfig) -> AgentResult:
        """Main workflow execution - agent lifecycle management.

        Args:
            config: Agent configuration

        Returns:
            Final agent result
        """
        self._config = config
        self._start_time = datetime.now(UTC)

        logger.info(f"[{CONSTITUTIONAL_HASH}] Starting AgentEntityWorkflow for {config.agent_id}")

        try:
            # Initialize agent
            await self.execute_activity(
                initialize_agent_activity,  # type: ignore[arg-type]
                config,
            )

            self._state = AgentState.IDLE
            self._last_activity = datetime.now(UTC)

            # Main event loop - process tasks and signals
            while self._state != AgentState.TERMINATED:
                # Check for shutdown request
                if self._shutdown_requested:
                    await self._handle_shutdown()
                    break

                # Check for suspend request
                if self._suspend_requested:
                    self._state = AgentState.SUSPENDED
                    await self._wait_for_resume()
                    continue

                # Process pending tasks
                if not self._task_queue.empty():
                    await self._process_next_task()
                else:
                    # Wait for new signals or timeout
                    self._state = AgentState.IDLE
                    try:
                        # Wait for task with idle timeout
                        await asyncio.wait_for(
                            self._wait_for_task_or_signal(),
                            timeout=config.idle_timeout_seconds,
                        )
                    except TimeoutError:
                        # Idle timeout - trigger shutdown
                        logger.info(
                            f"[{CONSTITUTIONAL_HASH}] Agent {config.agent_id} idle timeout reached"
                        )
                        self._shutdown_requested = True
                        self._shutdown_reason = "idle_timeout"

                # Periodic checkpoint
                await self._maybe_checkpoint()

        except asyncio.CancelledError:
            logger.info(f"[{CONSTITUTIONAL_HASH}] Agent {config.agent_id} cancelled")
            self._state = AgentState.TERMINATED
            self._shutdown_reason = "cancelled"
        except _AGENT_WORKFLOW_OPERATION_ERRORS as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Agent {config.agent_id} failed: {e}")
            self._state = AgentState.FAILED
            self._shutdown_reason = f"error: {e!s}"

        # Calculate final runtime
        runtime = (datetime.now(UTC) - self._start_time).total_seconds()

        return AgentResult(
            agent_id=config.agent_id,
            final_state=self._state,
            total_tasks_completed=self._tasks_completed,
            total_tasks_failed=self._tasks_failed,
            total_runtime_seconds=runtime,
            shutdown_reason=self._shutdown_reason,
            checkpoints=self._checkpoints,
        )

    async def _wait_for_task_or_signal(self) -> None:
        """Wait for a task to be queued or a signal to be received."""
        while (
            self._task_queue.empty()
            and not self._shutdown_requested
            and not self._suspend_requested
        ):
            await asyncio.sleep(0.1)

    async def _wait_for_resume(self) -> None:
        """Wait for resume signal when suspended."""
        while self._suspend_requested and not self._shutdown_requested:
            await asyncio.sleep(0.1)
        if not self._shutdown_requested:
            self._state = AgentState.IDLE

    async def _process_next_task(self) -> None:
        """Process the next task in the queue."""
        if self._task_queue.empty():
            return

        task = await self._task_queue.get()
        self._state = AgentState.PROCESSING
        self._current_task = task.task_id
        self._last_activity = datetime.now(UTC)

        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Processing task {task.task_id} "
            f"for agent {self._config.agent_id}"
        )

        try:
            result = await self.execute_activity(
                execute_task_activity,  # type: ignore[arg-type]
                task,  # type: ignore[arg-type]
                timeout=task.timeout_seconds,
            )

            self._task_results.append(result)  # type: ignore[arg-type]

            if getattr(result, "success", True):  # type: ignore[attr-defined]
                self._tasks_completed += 1
            else:
                self._tasks_failed += 1
                # Retry logic
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    await self._task_queue.put(task)
                    logger.debug(
                        f"[{CONSTITUTIONAL_HASH}] Retrying task {task.task_id} "
                        f"(attempt {task.retry_count})"
                    )

        except _AGENT_WORKFLOW_OPERATION_ERRORS as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Task processing error: {e}")
            self._tasks_failed += 1

        finally:
            self._current_task = None
            self._state = AgentState.IDLE

    async def _handle_shutdown(self) -> None:
        """Handle graceful shutdown."""
        self._state = AgentState.TERMINATING

        # Shutdown activity
        shutdown_request = ShutdownRequest(
            agent_id=self._config.agent_id,
            reason=self._shutdown_reason,
        )
        await self.execute_activity(
            shutdown_agent_activity,  # type: ignore[arg-type]
            shutdown_request,  # type: ignore[arg-type]
        )

        self._state = AgentState.TERMINATED

    async def _maybe_checkpoint(self) -> None:
        """Create checkpoint if interval has passed."""
        if not self._config:
            return

        if not self._checkpoints:
            # Create initial checkpoint
            await self._create_checkpoint()
            return

        last_checkpoint_time = datetime.fromisoformat(
            self._checkpoints[-1].get("checkpoint_time", "")
        )
        elapsed = (datetime.now(UTC) - last_checkpoint_time).total_seconds()

        if elapsed >= self._config.checkpoint_interval_seconds:
            await self._create_checkpoint()

    async def _create_checkpoint(self) -> None:
        """Create a state checkpoint."""
        status = self._get_status()
        checkpoint = await self.execute_activity(
            checkpoint_agent_activity,  # type: ignore[arg-type]
            status,  # type: ignore[arg-type]
        )
        self._checkpoints.append(checkpoint)  # type: ignore[arg-type]

    def _get_status(self) -> AgentStatus:
        """Get current agent status."""
        uptime = (datetime.now(UTC) - self._start_time).total_seconds()
        return AgentStatus(
            agent_id=self._config.agent_id if self._config else "",
            state=self._state,
            current_task=self._current_task,
            tasks_completed=self._tasks_completed,
            tasks_failed=self._tasks_failed,
            tasks_pending=self._task_queue.qsize(),
            last_activity=self._last_activity,
            uptime_seconds=uptime,
        )

    # =========================================================================
    # Signals
    # =========================================================================

    @signal("assign_task")
    async def assign_task(self, task: Task) -> None:
        """Signal handler to assign a new task.

        Args:
            task: Task to assign
        """

        await self._task_queue.put(task)
        self._last_activity = datetime.now(UTC)

    @signal("suspend")
    async def suspend(self, reason: str = "") -> None:
        """Signal handler to suspend the agent.

        Args:
            reason: Suspension reason
        """
        logger.info(f"[{CONSTITUTIONAL_HASH}] Agent suspend requested: {reason}")
        self._suspend_requested = True

    @signal("resume")
    async def resume(self, _data: object = None) -> None:
        """Signal handler to resume a suspended agent."""
        logger.info(f"[{CONSTITUTIONAL_HASH}] Agent resume requested")
        self._suspend_requested = False

    @signal("shutdown")
    async def shutdown(self, reason: str = "requested") -> None:
        """Signal handler to initiate graceful shutdown.

        Args:
            reason: Shutdown reason
        """
        logger.info(f"[{CONSTITUTIONAL_HASH}] Agent shutdown requested: {reason}")
        self._shutdown_requested = True
        self._shutdown_reason = reason

    @signal("update_config")
    async def update_config(self, updates: JSONDict) -> None:
        """Signal handler to update agent configuration.

        Args:
            updates: Configuration updates
        """
        if self._config:
            for key, value in updates.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)

    # =========================================================================
    # Queries
    # =========================================================================

    @query("get_status")
    def get_status(self) -> AgentStatus:
        """Query handler to get current agent status.

        Returns:
            Current agent status
        """
        return self._get_status()

    @query("get_state")
    def get_state(self) -> AgentState:
        """Query handler to get current agent state.

        Returns:
            Current agent state
        """
        return self._state

    @query("get_task_results")
    def get_task_results(self) -> list[TaskResult]:
        """Query handler to get task results.

        Returns:
            List of task results
        """
        return self._task_results.copy()

    @query("get_pending_tasks")
    def get_pending_tasks(self) -> int:
        """Query handler to get pending task count.

        Returns:
            Number of pending tasks
        """
        return self._task_queue.qsize()

    @query("get_checkpoints")
    def get_checkpoints(self) -> list[JSONDict]:
        """Query handler to get checkpoints.

        Returns:
            List of checkpoints
        """
        return self._checkpoints.copy()


__all__ = [
    # Data classes
    "AgentConfig",
    # Workflow
    "AgentEntityWorkflow",
    "AgentResult",
    # Enums
    "AgentState",
    "AgentStatus",
    "CheckpointAgentActivity",
    "ExecuteTaskActivity",
    "InitializeAgentActivity",
    "ShutdownAgentActivity",
    "ShutdownRequest",
    "Task",
    "TaskPriority",
    "TaskResult",
    # Activities
    "WorkflowActivity",
    "checkpoint_agent_activity",
    "execute_task_activity",
    "initialize_agent_activity",
    "shutdown_agent_activity",
]
