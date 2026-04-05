"""
Durable Execution Engine for ACGS-2.

Implements checkpoint-based failure recovery and automatic resume capabilities
for long-running agentic workflows. Based on LangGraph's durable execution pattern.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import inspect
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar

from enhanced_agent_bus.observability.structured_logging import get_logger

# Generic type for step results
StepResult = TypeVar("StepResult")
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

logger = get_logger(__name__)
STEP_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)

# Constitutional compliance
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__all__ = [
    "CONSTITUTIONAL_HASH",
    "CheckpointStore",
    "DurableExecutor",
    "DurableStep",
    "DurableWorkflow",
    "ExecutionCheckpoint",
    "ExecutionStatus",
    "RecoveryStrategy",
    "WorkflowState",
    "create_durable_executor",
]


class ExecutionStatus(Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


class RecoveryStrategy(Enum):
    """Strategy for recovering from failures."""

    RETRY_STEP = "retry_step"  # Retry the failed step
    SKIP_STEP = "skip_step"  # Skip and continue
    ROLLBACK = "rollback"  # Rollback to previous checkpoint
    RESTART = "restart"  # Restart from beginning
    MANUAL = "manual"  # Require manual intervention


@dataclass
class WorkflowState:
    """
    Workflow execution state.

    Tracks all intermediate results and metadata for recovery.
    """

    workflow_id: str
    current_step: int = 0
    total_steps: int = 0
    step_results: dict[int, object] = field(default_factory=dict)
    variables: JSONDict = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "workflow_id": self.workflow_id,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "step_results": self.step_results,
            "variables": self.variables,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "WorkflowState":
        """Create from dictionary."""
        return cls(
            workflow_id=data["workflow_id"],
            current_step=data.get("current_step", 0),
            total_steps=data.get("total_steps", 0),
            step_results=data.get("step_results", {}),
            variables=data.get("variables", {}),
            metadata=data.get("metadata", {}),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
            ),
            error=data.get("error"),
        )


@dataclass
class ExecutionCheckpoint:
    """
    Checkpoint for durable execution.

    Captures complete execution state for recovery.
    """

    id: str
    workflow_id: str
    step_index: int
    state: WorkflowState
    status: ExecutionStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "step_index": self.step_index,
            "state": self.state.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "ExecutionCheckpoint":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            workflow_id=data["workflow_id"],
            step_index=data["step_index"],
            state=WorkflowState.from_dict(data["state"]),
            status=ExecutionStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )


class CheckpointStore:
    """
    Persistent checkpoint storage.

    Uses SQLite for durability with support for multiple workflows.
    """

    def __init__(self, db_path: str | None = None):
        """Initialize checkpoint store."""
        self._db_path = db_path or ":memory:"
        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the database."""
        if self._initialized:
            return

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Create tables
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                constitutional_hash TEXT NOT NULL,
                UNIQUE(workflow_id, step_index)
            );

            CREATE INDEX IF NOT EXISTS idx_workflow_id ON checkpoints(workflow_id);
            CREATE INDEX IF NOT EXISTS idx_created_at ON checkpoints(created_at);

            CREATE TABLE IF NOT EXISTS workflow_metadata (
                workflow_id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                total_steps INTEGER DEFAULT 0,
                completed_steps INTEGER DEFAULT 0
            );
        """)
        self._conn.commit()
        self._initialized = True
        logger.info(f"Checkpoint store initialized: {self._db_path}")

    async def save_checkpoint(self, checkpoint: ExecutionCheckpoint) -> None:
        """Save a checkpoint."""
        if not self._conn:
            await self.initialize()

        await asyncio.to_thread(self._sync_save_checkpoint, checkpoint)
        logger.debug(f"Saved checkpoint: {checkpoint.id} for workflow {checkpoint.workflow_id}")

    def _sync_save_checkpoint(self, checkpoint: ExecutionCheckpoint) -> None:
        """Synchronous checkpoint save."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO checkpoints
            (id, workflow_id, step_index, state_json, status, created_at, constitutional_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                checkpoint.id,
                checkpoint.workflow_id,
                checkpoint.step_index,
                json.dumps(checkpoint.state.to_dict()),
                checkpoint.status.value,
                checkpoint.created_at.isoformat(),
                checkpoint.constitutional_hash,
            ),
        )
        self._conn.commit()

    async def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        """Get a specific checkpoint."""
        if not self._conn:
            await self.initialize()

        row = await asyncio.to_thread(self._sync_get_checkpoint, checkpoint_id)

        if not row:
            return None

        return ExecutionCheckpoint(
            id=row["id"],
            workflow_id=row["workflow_id"],
            step_index=row["step_index"],
            state=WorkflowState.from_dict(json.loads(row["state_json"])),
            status=ExecutionStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            constitutional_hash=row["constitutional_hash"],
        )

    def _sync_get_checkpoint(self, checkpoint_id: str) -> dict | None:
        """Synchronous checkpoint retrieval."""
        cursor = self._conn.execute("SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,))
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    async def get_latest_checkpoint(self, workflow_id: str) -> ExecutionCheckpoint | None:
        """Get the latest checkpoint for a workflow."""
        if not self._conn:
            await self.initialize()

        cursor = self._conn.execute(
            """
            SELECT * FROM checkpoints
            WHERE workflow_id = ?
            ORDER BY step_index DESC, created_at DESC
            LIMIT 1
        """,
            (workflow_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return ExecutionCheckpoint(
            id=row["id"],
            workflow_id=row["workflow_id"],
            step_index=row["step_index"],
            state=WorkflowState.from_dict(json.loads(row["state_json"])),
            status=ExecutionStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            constitutional_hash=row["constitutional_hash"],
        )

    async def get_checkpoints(
        self, workflow_id: str, limit: int = 100, offset: int = 0
    ) -> list[ExecutionCheckpoint]:
        """Get all checkpoints for a workflow."""
        if not self._conn:
            await self.initialize()

        cursor = self._conn.execute(
            "SELECT * FROM checkpoints WHERE workflow_id = ? ORDER BY step_index LIMIT ? OFFSET ?",
            (workflow_id, limit, offset),
        )

        checkpoints = []
        for row in cursor.fetchall():
            checkpoints.append(
                ExecutionCheckpoint(
                    id=row["id"],
                    workflow_id=row["workflow_id"],
                    step_index=row["step_index"],
                    state=WorkflowState.from_dict(json.loads(row["state_json"])),
                    status=ExecutionStatus(row["status"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    constitutional_hash=row["constitutional_hash"],
                )
            )

        return checkpoints

    async def delete_checkpoints(self, workflow_id: str) -> int:
        """Delete all checkpoints for a workflow."""
        if not self._conn:
            await self.initialize()

        cursor = self._conn.execute("DELETE FROM checkpoints WHERE workflow_id = ?", (workflow_id,))
        self._conn.commit()
        return cursor.rowcount

    async def cleanup_old_checkpoints(self, max_age_hours: int = 24) -> int:
        """Clean up checkpoints older than max_age_hours."""
        if not self._conn:
            await self.initialize()

        cutoff = datetime.now(UTC).timestamp() - (max_age_hours * 3600)
        cutoff_str = datetime.fromtimestamp(cutoff, tz=UTC).isoformat()

        cursor = self._conn.execute("DELETE FROM checkpoints WHERE created_at < ?", (cutoff_str,))
        self._conn.commit()
        return cursor.rowcount

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False


@dataclass
class DurableStep:
    """
    A single step in a durable workflow.

    Each step has a unique ID, execution function, and retry configuration.
    """

    id: str
    name: str
    func: Callable
    description: str = ""
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float | None = None
    checkpoint_before: bool = True
    checkpoint_after: bool = True
    skip_on_failure: bool = False


class DurableWorkflow:
    """
    Durable workflow definition.

    A workflow is a sequence of steps with checkpointing and recovery support.
    """

    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        checkpoint_interval: int = 1,
        recovery_strategy: RecoveryStrategy = RecoveryStrategy.RETRY_STEP,
    ):
        """Initialize workflow."""
        self.id = id
        self.name = name
        self.description = description
        self.checkpoint_interval = checkpoint_interval
        self.recovery_strategy = recovery_strategy
        self._steps: list[DurableStep] = []

    def add_step(
        self,
        name: str,
        func: Callable,
        description: str = "",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float | None = None,
        checkpoint_before: bool = True,
        checkpoint_after: bool = True,
        skip_on_failure: bool = False,
    ) -> "DurableWorkflow":
        """Add a step to the workflow."""
        step = DurableStep(
            id=str(uuid4()),
            name=name,
            func=func,
            description=description,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout=timeout,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
            skip_on_failure=skip_on_failure,
        )
        self._steps.append(step)
        return self

    def step(self, name: str, description: str = "", max_retries: int = 3, **kwargs) -> Callable:
        """Decorator to add a step."""

        def decorator(func: Callable) -> Callable:
            self.add_step(
                name=name, func=func, description=description, max_retries=max_retries, **kwargs
            )
            return func

        return decorator

    @property
    def steps(self) -> list[DurableStep]:
        """Get workflow steps."""
        return self._steps.copy()

    def __len__(self) -> int:
        """Get number of steps."""
        return len(self._steps)


class DurableExecutor:
    """
    Durable execution engine.

    Executes workflows with automatic checkpointing and failure recovery.
    Implements the durable execution pattern from LangGraph.
    """

    def __init__(
        self,
        checkpoint_store: CheckpointStore | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        auto_checkpoint: bool = True,
        checkpoint_interval: int = 1,
        max_recovery_attempts: int = 3,
    ):
        """Initialize durable executor."""
        self._store = checkpoint_store or CheckpointStore()
        self._constitutional_hash = constitutional_hash
        self._auto_checkpoint = auto_checkpoint
        self._checkpoint_interval = checkpoint_interval
        self._max_recovery_attempts = max_recovery_attempts

        # Active executions
        self._active_workflows: dict[str, WorkflowState] = {}

        # Metrics
        self._metrics = {
            "workflows_started": 0,
            "workflows_completed": 0,
            "workflows_failed": 0,
            "checkpoints_created": 0,
            "recoveries_attempted": 0,
            "recoveries_successful": 0,
            "steps_executed": 0,
            "steps_retried": 0,
        }

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the executor."""
        if self._initialized:
            return

        await self._store.initialize()
        self._initialized = True
        logger.info("Durable executor initialized")

    async def execute(
        self,
        workflow: DurableWorkflow,
        initial_context: JSONDict | None = None,
        resume_from: str | None = None,
    ) -> tuple[bool, WorkflowState]:
        """
        Execute a workflow with durable checkpointing.

        Args:
            workflow: The workflow to execute
            initial_context: Initial variables for the workflow
            resume_from: Checkpoint ID to resume from (optional)

        Returns:
            Tuple of (success, final_state)
        """
        if not self._initialized:
            await self.initialize()

        # Initialize or resume state
        if resume_from:
            checkpoint = await self._store.get_checkpoint(resume_from)
            if not checkpoint:
                raise ValueError(f"Checkpoint not found: {resume_from}")
            state = checkpoint.state
            start_step = checkpoint.step_index + 1
            logger.info(f"Resuming workflow {workflow.id} from step {start_step}")
            self._metrics["recoveries_attempted"] += 1
        else:
            state = WorkflowState(
                workflow_id=workflow.id,
                total_steps=len(workflow),
                variables=initial_context or {},
                started_at=datetime.now(UTC),
            )
            start_step = 0
            self._metrics["workflows_started"] += 1

        self._active_workflows[workflow.id] = state

        try:
            # Execute steps
            for i, step in enumerate(workflow.steps[start_step:], start=start_step):
                state.current_step = i
                state.updated_at = datetime.now(UTC)

                # Checkpoint before step (if configured)
                if step.checkpoint_before and self._should_checkpoint(i):
                    await self._create_checkpoint(
                        workflow.id, i, state, ExecutionStatus.CHECKPOINTED
                    )

                # Execute step with retry logic
                success, result = await self._execute_step(step, state)

                if success:
                    state.step_results[i] = result
                    self._metrics["steps_executed"] += 1

                    # Checkpoint after step (if configured)
                    if step.checkpoint_after and self._should_checkpoint(i):
                        await self._create_checkpoint(
                            workflow.id, i, state, ExecutionStatus.CHECKPOINTED
                        )
                else:
                    if step.skip_on_failure:
                        state.step_results[i] = {"skipped": True, "error": str(result)}
                        logger.warning(f"Skipped failed step {step.name}")
                    else:
                        state.error = str(result)
                        await self._create_checkpoint(workflow.id, i, state, ExecutionStatus.FAILED)
                        self._metrics["workflows_failed"] += 1
                        return False, state

            # Workflow completed successfully
            state.updated_at = datetime.now(UTC)
            await self._create_checkpoint(
                workflow.id, len(workflow) - 1, state, ExecutionStatus.COMPLETED
            )
            self._metrics["workflows_completed"] += 1

            if resume_from:
                self._metrics["recoveries_successful"] += 1

            return True, state

        finally:
            self._active_workflows.pop(workflow.id, None)

    async def _execute_step(
        self,
        step: DurableStep,
        state: WorkflowState,
    ) -> tuple[bool, object]:
        """Execute a single step with retry logic."""
        last_error: Exception | None = None

        for attempt in range(step.max_retries + 1):
            try:
                # Execute with optional timeout
                result: object
                if step.timeout:
                    result = await asyncio.wait_for(
                        self._run_step(step, state), timeout=step.timeout
                    )
                else:
                    result = await self._run_step(step, state)

                return True, result

            except TimeoutError:
                last_error = TimeoutError(f"Step {step.name} timed out after {step.timeout}s")
                logger.warning(
                    f"Step {step.name} timed out (attempt {attempt + 1}/{step.max_retries + 1})"
                )

                if attempt < step.max_retries:
                    self._metrics["steps_retried"] += 1
                    await asyncio.sleep(step.retry_delay * (2**attempt))
            except STEP_EXECUTION_ERRORS as e:
                last_error = e
                logger.warning(
                    f"Step {step.name} failed (attempt {attempt + 1}/{step.max_retries + 1}): {e}"
                )

                if attempt < step.max_retries:
                    self._metrics["steps_retried"] += 1
                    await asyncio.sleep(step.retry_delay * (2**attempt))  # Exponential backoff

        return False, last_error

    async def _run_step(self, step: DurableStep, state: WorkflowState) -> StepResult:
        """Run a step function."""
        func = step.func

        # Check if function is async
        if inspect.iscoroutinefunction(func):
            return await func(state)  # type: ignore[no-any-return]
        else:
            return func(state)  # type: ignore[no-any-return]

    def _should_checkpoint(self, step_index: int) -> bool:
        """Determine if we should create a checkpoint."""
        if not self._auto_checkpoint:
            return False
        return step_index % self._checkpoint_interval == 0

    async def _create_checkpoint(
        self,
        workflow_id: str,
        step_index: int,
        state: WorkflowState,
        status: ExecutionStatus,
    ) -> ExecutionCheckpoint:
        """Create and save a checkpoint."""
        checkpoint = ExecutionCheckpoint(
            id=str(uuid4()),
            workflow_id=workflow_id,
            step_index=step_index,
            state=state,
            status=status,
            constitutional_hash=self._constitutional_hash,
        )

        await self._store.save_checkpoint(checkpoint)
        self._metrics["checkpoints_created"] += 1
        logger.debug(f"Created checkpoint at step {step_index} for workflow {workflow_id}")

        return checkpoint

    async def resume(self, workflow: DurableWorkflow) -> tuple[bool, WorkflowState]:
        """
        Resume a workflow from its latest checkpoint.

        Args:
            workflow: The workflow to resume

        Returns:
            Tuple of (success, final_state)
        """
        checkpoint = await self._store.get_latest_checkpoint(workflow.id)

        if not checkpoint:
            raise ValueError(f"No checkpoint found for workflow: {workflow.id}")

        if checkpoint.status == ExecutionStatus.COMPLETED:
            logger.info(f"Workflow {workflow.id} already completed")
            return True, checkpoint.state

        return await self.execute(workflow, resume_from=checkpoint.id)

    async def get_workflow_status(self, workflow_id: str) -> JSONDict | None:
        """Get the current status of a workflow."""
        # Check active workflows first
        if workflow_id in self._active_workflows:
            state = self._active_workflows[workflow_id]
            return {
                "workflow_id": workflow_id,
                "status": "running",
                "current_step": state.current_step,
                "total_steps": state.total_steps,
                "progress": state.current_step / max(state.total_steps, 1),
            }

        # Check checkpoints
        checkpoint = await self._store.get_latest_checkpoint(workflow_id)
        if checkpoint:
            return {
                "workflow_id": workflow_id,
                "status": checkpoint.status.value,
                "current_step": checkpoint.step_index,
                "total_steps": checkpoint.state.total_steps,
                "progress": checkpoint.step_index / max(checkpoint.state.total_steps, 1),
                "last_checkpoint": checkpoint.created_at.isoformat(),
            }

        return None

    async def cancel(self, workflow_id: str) -> bool:
        """Cancel an active workflow."""
        if workflow_id in self._active_workflows:
            state = self._active_workflows[workflow_id]
            await self._create_checkpoint(
                workflow_id,
                state.current_step,
                state,
                ExecutionStatus.PAUSED,
            )
            self._active_workflows.pop(workflow_id, None)
            return True
        return False

    def get_stats(self) -> JSONDict:
        """Get executor statistics."""
        return {
            "active_workflows": len(self._active_workflows),
            "metrics": self._metrics.copy(),
            "constitutional_hash": self._constitutional_hash,
            "auto_checkpoint": self._auto_checkpoint,
            "checkpoint_interval": self._checkpoint_interval,
        }

    async def close(self) -> None:
        """Close the executor."""
        await self._store.close()
        self._initialized = False
        logger.info("Durable executor closed")


def create_durable_executor(
    db_path: str | None = None,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
    auto_checkpoint: bool = True,
    checkpoint_interval: int = 1,
) -> DurableExecutor:
    """
    Factory function to create a durable executor.

    USE THIS WHEN:
    - You need to execute long-running workflows with failure recovery
    - Your workflow has multiple steps that may fail independently
    - You want automatic checkpointing for durability

    DO NOT USE FOR:
    - Simple, single-step operations
    - Operations that complete in <1 second
    - Workflows that don't need recovery capability

    Args:
        db_path: Path to SQLite database for checkpoints (None for in-memory)
        constitutional_hash: Constitutional hash for compliance
        auto_checkpoint: Whether to auto-checkpoint
        checkpoint_interval: Create checkpoint every N steps

    Returns:
        Configured DurableExecutor instance

    EXAMPLE:
        executor = create_durable_executor(db_path="checkpoints.db")
        await executor.initialize()

        workflow = DurableWorkflow("my-workflow", "My Workflow")
        workflow.add_step("step1", step1_func)
        workflow.add_step("step2", step2_func)

        success, state = await executor.execute(workflow)
    """
    store = CheckpointStore(db_path)
    return DurableExecutor(
        checkpoint_store=store,
        constitutional_hash=constitutional_hash,
        auto_checkpoint=auto_checkpoint,
        checkpoint_interval=checkpoint_interval,
    )
