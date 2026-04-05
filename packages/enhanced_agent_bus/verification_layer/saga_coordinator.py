"""
ACGS-2 Saga Coordinator - Compensable Transaction Management
Constitutional Hash: 608508a9bd224290

Implements SagaLLM transaction guarantees for constitutional governance:
- Compensable operations with LIFO (Last-In-First-Out) rollback
- Transaction boundaries with constitutional checkpoints
- Automatic compensation on validation failure
- 99.9% transaction consistency target

Key Features:
- Saga pattern for distributed governance decisions
- Checkpoint-based state management for recovery
- Timeout handling with configurable thresholds
- Full audit trail for compliance

Performance Targets:
- Transaction completion rate: 99.9%
- Compensation execution: < 1s
- Checkpoint persistence: < 10ms
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar

# Constitutional hash for immutable validation
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_SAGA_COORDINATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

T = TypeVar("T")


class SagaState(Enum):
    """States of a Saga transaction."""

    INITIALIZED = "initialized"
    RUNNING = "running"
    CHECKPOINT = "checkpoint"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ABORTED = "aborted"


class StepState(Enum):
    """States of individual saga steps."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    SKIPPED = "skipped"


class CompensationStrategy(Enum):
    """Compensation execution strategies."""

    LIFO = "lifo"  # Last-In-First-Out (default)
    PARALLEL = "parallel"  # Execute all compensations in parallel
    SELECTIVE = "selective"  # Only compensate failed and dependent steps


@dataclass
class SagaCompensation:
    """Compensation action for a saga step."""

    compensation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str = ""
    compensation_func: Callable[..., Awaitable[object]] | None = None
    compensation_args: JSONDict = field(default_factory=dict)
    executed: bool = False
    executed_at: datetime | None = None
    result: object = None
    error: str | None = None
    duration_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "compensation_id": self.compensation_id,
            "step_id": self.step_id,
            "executed": self.executed,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "result": str(self.result) if self.result else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SagaStep:
    """A step in a Saga transaction."""

    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    execute_func: Callable[..., Awaitable[object]] | None = None
    compensate_func: Callable[..., Awaitable[object]] | None = None
    state: StepState = StepState.PENDING
    input_data: JSONDict = field(default_factory=dict)
    output_data: object = None
    error: str | None = None
    timeout_ms: int = 30000
    retry_count: int = 0
    max_retries: int = 3
    started_at: datetime | None = None
    completed_at: datetime | None = None
    compensated_at: datetime | None = None
    duration_ms: float = 0.0
    compensation: SagaCompensation | None = None
    dependencies: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "input_data": self.input_data,
            "output_data": str(self.output_data) if self.output_data else None,
            "error": self.error,
            "timeout_ms": self.timeout_ms,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "compensated_at": self.compensated_at.isoformat() if self.compensated_at else None,
            "duration_ms": self.duration_ms,
            "compensation": self.compensation.to_dict() if self.compensation else None,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SagaCheckpoint:
    """A checkpoint in saga execution for recovery."""

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    saga_id: str = ""
    name: str = ""
    state_snapshot: JSONDict = field(default_factory=dict)
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    is_constitutional_checkpoint: bool = False

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "saga_id": self.saga_id,
            "name": self.name,
            "state_snapshot": self.state_snapshot,
            "completed_steps": self.completed_steps,
            "pending_steps": self.pending_steps,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
            "is_constitutional_checkpoint": self.is_constitutional_checkpoint,
        }


@dataclass
class SagaTransaction:
    """A complete Saga transaction."""

    saga_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    state: SagaState = SagaState.INITIALIZED
    steps: list[SagaStep] = field(default_factory=list)
    checkpoints: list[SagaCheckpoint] = field(default_factory=list)
    current_step_index: int = 0
    compensation_strategy: CompensationStrategy = CompensationStrategy.LIFO
    timeout_ms: int = 300000  # 5 minutes default
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    compensated_at: datetime | None = None
    total_duration_ms: float = 0.0
    failure_reason: str | None = None
    compensation_log: list[JSONDict] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    context: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "saga_id": self.saga_id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "steps": [s.to_dict() for s in self.steps],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "current_step_index": self.current_step_index,
            "compensation_strategy": self.compensation_strategy.value,
            "timeout_ms": self.timeout_ms,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "compensated_at": self.compensated_at.isoformat() if self.compensated_at else None,
            "total_duration_ms": self.total_duration_ms,
            "failure_reason": self.failure_reason,
            "compensation_log": self.compensation_log,
            "metadata": self.metadata,
            "context": self.context,
            "constitutional_hash": self.constitutional_hash,
        }

    @property
    def completed_steps(self) -> list[SagaStep]:
        """Get list of completed steps."""
        return [s for s in self.steps if s.state == StepState.COMPLETED]

    @property
    def pending_steps(self) -> list[SagaStep]:
        """Get list of pending steps."""
        return [s for s in self.steps if s.state == StepState.PENDING]

    @property
    def failed_steps(self) -> list[SagaStep]:
        """Get list of failed steps."""
        return [s for s in self.steps if s.state == StepState.FAILED]


class SagaCoordinator:
    """
    Saga Coordinator: Manages compensable transactions for governance.

    Implements:
    - LIFO rollback on failure (compensate in reverse order)
    - Constitutional checkpoints for critical decision points
    - Automatic compensation on validation failure
    - Full audit trail for compliance

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        default_timeout_ms: int = 300000,
        compensation_timeout_ms: int = 60000,
        max_concurrent_compensations: int = 5,
    ):
        self.default_timeout_ms = default_timeout_ms
        self.compensation_timeout_ms = compensation_timeout_ms
        self.max_concurrent_compensations = max_concurrent_compensations

        self._active_sagas: dict[str, SagaTransaction] = {}
        self._completed_sagas: dict[str, SagaTransaction] = {}
        self._checkpoint_store: dict[str, list[SagaCheckpoint]] = {}

        self.constitutional_hash = CONSTITUTIONAL_HASH

        logger.info("Initialized Saga Coordinator")
        logger.info(f"Constitutional Hash: {self.constitutional_hash}")

    def create_saga(
        self,
        name: str,
        description: str = "",
        timeout_ms: int | None = None,
        compensation_strategy: CompensationStrategy = CompensationStrategy.LIFO,
        metadata: JSONDict | None = None,
    ) -> SagaTransaction:
        """Create a new saga transaction."""
        saga = SagaTransaction(
            name=name,
            description=description,
            timeout_ms=timeout_ms or self.default_timeout_ms,
            compensation_strategy=compensation_strategy,
            metadata=metadata or {},
        )

        self._active_sagas[saga.saga_id] = saga
        logger.info(f"Created saga: {saga.saga_id} ({name})")

        return saga

    def add_step(
        self,
        saga: SagaTransaction,
        name: str,
        execute_func: Callable[..., Awaitable[object]],
        compensate_func: Callable[..., Awaitable[object]] | None = None,
        description: str = "",
        timeout_ms: int = 30000,
        max_retries: int = 3,
        dependencies: list[str] | None = None,
        metadata: JSONDict | None = None,
    ) -> SagaStep:
        """Add a step to a saga transaction."""
        if saga.state != SagaState.INITIALIZED:
            raise ValueError(f"Cannot add steps to saga in state: {saga.state.value}")

        step = SagaStep(
            name=name,
            description=description,
            execute_func=execute_func,
            compensate_func=compensate_func,
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )

        if compensate_func:
            step.compensation = SagaCompensation(
                step_id=step.step_id,
                compensation_func=compensate_func,
            )

        saga.steps.append(step)
        logger.debug(f"Added step '{name}' to saga {saga.saga_id}")

        return step

    def create_checkpoint(
        self,
        saga: SagaTransaction,
        name: str,
        is_constitutional: bool = False,
        metadata: JSONDict | None = None,
    ) -> SagaCheckpoint:
        """Create a checkpoint for saga recovery."""
        checkpoint = SagaCheckpoint(
            saga_id=saga.saga_id,
            name=name,
            state_snapshot={
                "current_step_index": saga.current_step_index,
                "context": saga.context.copy(),
            },
            completed_steps=[s.step_id for s in saga.completed_steps],
            pending_steps=[s.step_id for s in saga.pending_steps],
            metadata=metadata or {},
            is_constitutional_checkpoint=is_constitutional,
        )

        saga.checkpoints.append(checkpoint)

        if saga.saga_id not in self._checkpoint_store:
            self._checkpoint_store[saga.saga_id] = []
        self._checkpoint_store[saga.saga_id].append(checkpoint)

        logger.debug(
            f"Created {'constitutional ' if is_constitutional else ''}checkpoint "
            f"'{name}' for saga {saga.saga_id}"
        )

        return checkpoint

    async def execute_saga(
        self,
        saga: SagaTransaction,
        context: JSONDict | None = None,
    ) -> bool:
        """
        Execute a saga transaction with full compensation guarantees.

        Args:
            saga: The saga transaction to execute
            context: Optional context data for step execution

        Returns:
            True if saga completed successfully, False if compensated
        """
        if saga.state != SagaState.INITIALIZED:
            raise ValueError(f"Cannot execute saga in state: {saga.state.value}")

        saga.state = SagaState.RUNNING
        saga.started_at = datetime.now(UTC)
        saga.context = context or {}

        logger.info(f"Executing saga: {saga.saga_id} ({saga.name})")

        try:
            # Execute steps in order
            for i, step in enumerate(saga.steps):
                saga.current_step_index = i

                # Check for dependencies
                if step.dependencies:
                    for dep_id in step.dependencies:
                        dep_step = next((s for s in saga.steps if s.step_id == dep_id), None)
                        if dep_step and dep_step.state != StepState.COMPLETED:
                            logger.warning(f"Step {step.name} dependency {dep_id} not completed")
                            step.state = StepState.SKIPPED
                            continue

                success = await self._execute_step_with_retry(saga, step)

                if not success:
                    logger.warning(f"Step '{step.name}' failed, starting compensation")
                    saga.state = SagaState.COMPENSATING
                    await self._compensate_saga(saga)
                    return False

            # All steps completed successfully
            saga.state = SagaState.COMPLETED
            saga.completed_at = datetime.now(UTC)
            saga.total_duration_ms = (saga.completed_at - saga.started_at).total_seconds() * 1000

            # Move to completed storage
            self._completed_sagas[saga.saga_id] = saga
            if saga.saga_id in self._active_sagas:
                del self._active_sagas[saga.saga_id]

            logger.info(
                f"Saga {saga.saga_id} completed successfully in {saga.total_duration_ms:.2f}ms"
            )
            return True

        except TimeoutError:
            saga.state = SagaState.TIMEOUT
            saga.failure_reason = "Saga execution timeout"
            saga.failed_at = datetime.now(UTC)
            logger.error(f"Saga {saga.saga_id} timed out")
            await self._compensate_saga(saga)
            return False

        except _SAGA_COORDINATOR_OPERATION_ERRORS as e:
            saga.state = SagaState.FAILED
            saga.failure_reason = str(e)
            saga.failed_at = datetime.now(UTC)
            logger.error(f"Saga {saga.saga_id} failed: {e}")
            await self._compensate_saga(saga)
            return False

    async def _execute_step_with_retry(
        self,
        saga: SagaTransaction,
        step: SagaStep,
    ) -> bool:
        """Execute a step with retry logic."""
        for attempt in range(step.max_retries + 1):
            try:
                step.state = StepState.RUNNING
                step.started_at = datetime.now(UTC)
                step.retry_count = attempt

                # Execute with timeout
                step_start = datetime.now(UTC)

                result = await asyncio.wait_for(
                    step.execute_func(saga.context, step.input_data),
                    timeout=step.timeout_ms / 1000,
                )

                step_end = datetime.now(UTC)
                step.duration_ms = (step_end - step_start).total_seconds() * 1000

                step.state = StepState.COMPLETED
                step.completed_at = step_end
                step.output_data = result

                # Store output in saga context for subsequent steps
                saga.context[f"step_{step.step_id}_output"] = result

                logger.debug(f"Step '{step.name}' completed in {step.duration_ms:.2f}ms")
                return True

            except TimeoutError:
                logger.warning(
                    f"Step '{step.name}' timeout (attempt {attempt + 1}/{step.max_retries + 1})"
                )
                if attempt == step.max_retries:
                    step.state = StepState.FAILED
                    step.error = "Step timeout"
                    return False

            except _SAGA_COORDINATOR_OPERATION_ERRORS as e:
                logger.warning(f"Step '{step.name}' failed (attempt {attempt + 1}): {e}")
                if attempt == step.max_retries:
                    step.state = StepState.FAILED
                    step.error = str(e)
                    return False

            # Exponential backoff before retry
            await asyncio.sleep(0.1 * (2**attempt))

        return False

    async def _compensate_saga(self, saga: SagaTransaction) -> None:
        """Execute compensation for saga based on configured strategy."""
        logger.info(f"Starting compensation for saga: {saga.saga_id}")

        completed_steps = [
            s for s in saga.steps if s.state == StepState.COMPLETED and s.compensation
        ]

        if saga.compensation_strategy == CompensationStrategy.LIFO:
            await self._compensate_lifo(saga, completed_steps)
        elif saga.compensation_strategy == CompensationStrategy.PARALLEL:
            await self._compensate_parallel(saga, completed_steps)
        elif saga.compensation_strategy == CompensationStrategy.SELECTIVE:
            await self._compensate_selective(saga, completed_steps)

        # Only set to COMPENSATED if not already ABORTED (preserve abort state)
        if saga.state != SagaState.ABORTED:
            saga.state = SagaState.COMPENSATED
        saga.compensated_at = datetime.now(UTC)

        logger.info(f"Compensation complete for saga: {saga.saga_id}")

    async def _compensate_lifo(
        self,
        saga: SagaTransaction,
        steps: list[SagaStep],
    ) -> None:
        """Execute compensations in LIFO order (reverse execution order)."""
        for step in reversed(steps):
            await self._execute_compensation(saga, step)

    async def _compensate_parallel(
        self,
        saga: SagaTransaction,
        steps: list[SagaStep],
    ) -> None:
        """Execute all compensations in parallel."""
        tasks = [self._execute_compensation(saga, step) for step in steps]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _compensate_selective(
        self,
        saga: SagaTransaction,
        steps: list[SagaStep],
    ) -> None:
        """Execute compensations only for failed and dependent steps."""
        failed_step_ids = {s.step_id for s in saga.failed_steps}

        for step in reversed(steps):
            # Compensate if this step depends on a failed step
            if step.dependencies and any(d in failed_step_ids for d in step.dependencies):
                await self._execute_compensation(saga, step)
            elif step.state == StepState.FAILED:
                await self._execute_compensation(saga, step)

    async def _execute_compensation(
        self,
        saga: SagaTransaction,
        step: SagaStep,
    ) -> None:
        """Execute compensation for a single step."""
        if not step.compensation or not step.compensation.compensation_func:
            saga.compensation_log.append(
                {
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "status": "no_compensation",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            return

        step.state = StepState.COMPENSATING
        compensation = step.compensation

        try:
            comp_start = datetime.now(UTC)

            result = await asyncio.wait_for(
                compensation.compensation_func(step.output_data),
                timeout=self.compensation_timeout_ms / 1000,
            )

            comp_end = datetime.now(UTC)
            compensation.duration_ms = (comp_end - comp_start).total_seconds() * 1000

            compensation.executed = True
            compensation.executed_at = comp_end
            compensation.result = result
            step.state = StepState.COMPENSATED
            step.compensated_at = comp_end

            saga.compensation_log.append(
                {
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "status": "compensated",
                    "result": str(result),
                    "duration_ms": compensation.duration_ms,
                    "timestamp": comp_end.isoformat(),
                }
            )

            logger.debug(f"Compensated step '{step.name}' in {compensation.duration_ms:.2f}ms")

        except _SAGA_COORDINATOR_OPERATION_ERRORS as e:
            compensation.error = str(e)
            saga.compensation_log.append(
                {
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "status": "compensation_failed",
                    "error": str(e),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            logger.error(f"Compensation failed for step '{step.name}': {e}")

    async def abort_saga(self, saga_id: str, reason: str = "Manual abort") -> bool:
        """Abort a running saga and trigger compensation."""
        saga = self._active_sagas.get(saga_id)
        if not saga:
            logger.warning(f"Saga {saga_id} not found for abort")
            return False

        if saga.state not in (SagaState.INITIALIZED, SagaState.RUNNING):
            logger.warning(f"Cannot abort saga {saga_id} in state {saga.state.value}")
            return False

        saga.state = SagaState.ABORTED
        saga.failure_reason = reason
        saga.failed_at = datetime.now(UTC)

        await self._compensate_saga(saga)
        return True

    def get_saga(self, saga_id: str) -> SagaTransaction | None:
        """Get a saga by ID."""
        return self._active_sagas.get(saga_id) or self._completed_sagas.get(saga_id)

    def get_saga_status(self, saga_id: str) -> JSONDict:
        """Get detailed status of a saga."""
        saga = self.get_saga(saga_id)
        if not saga:
            return {"error": "Saga not found"}

        return {
            "saga_id": saga.saga_id,
            "name": saga.name,
            "state": saga.state.value,
            "total_steps": len(saga.steps),
            "completed_steps": len(saga.completed_steps),
            "failed_steps": len(saga.failed_steps),
            "checkpoints": len(saga.checkpoints),
            "duration_ms": saga.total_duration_ms,
            "failure_reason": saga.failure_reason,
            "constitutional_hash": self.constitutional_hash,
        }

    def list_active_sagas(self) -> list[JSONDict]:
        """List all active sagas."""
        return [
            {
                "saga_id": s.saga_id,
                "name": s.name,
                "state": s.state.value,
                "steps": len(s.steps),
            }
            for s in self._active_sagas.values()
        ]

    async def get_coordinator_status(self) -> JSONDict:
        """Get coordinator status and statistics."""
        active_count = len(self._active_sagas)
        completed_count = len(self._completed_sagas)

        total_sagas = list(self._active_sagas.values()) + list(self._completed_sagas.values())
        completed_sagas = [s for s in total_sagas if s.state == SagaState.COMPLETED]
        compensated_sagas = [s for s in total_sagas if s.state == SagaState.COMPENSATED]

        success_rate = len(completed_sagas) / len(total_sagas) * 100 if total_sagas else 0.0

        return {
            "coordinator": "Saga Coordinator",
            "status": "operational",
            "active_sagas": active_count,
            "completed_sagas": completed_count,
            "success_rate": success_rate,
            "compensated_sagas": len(compensated_sagas),
            "default_timeout_ms": self.default_timeout_ms,
            "compensation_timeout_ms": self.compensation_timeout_ms,
            "constitutional_hash": self.constitutional_hash,
        }


@asynccontextmanager
async def saga_context(
    coordinator: SagaCoordinator,
    name: str,
    description: str = "",
    auto_execute: bool = True,
    context: JSONDict | None = None,
):
    """
    Context manager for saga transactions.

    Usage:
        async with saga_context(coordinator, "Governance Decision") as saga:
            coordinator.add_step(saga, "validate", validate_func, compensate_func)
            coordinator.add_step(saga, "execute", execute_func, rollback_func)
            # Saga executes automatically on context exit
    """
    saga = coordinator.create_saga(name, description)

    try:
        yield saga

        if auto_execute:
            success = await coordinator.execute_saga(saga, context)
            if not success:
                raise RuntimeError(f"Saga {saga.saga_id} failed and was compensated")

    except _SAGA_COORDINATOR_OPERATION_ERRORS as e:
        logger.error(f"Saga context failed: {e}")
        if saga.state == SagaState.INITIALIZED:
            saga.state = SagaState.FAILED
            saga.failure_reason = str(e)
        raise


def create_saga_coordinator(
    default_timeout_ms: int = 300000,
    compensation_timeout_ms: int = 60000,
) -> SagaCoordinator:
    """Factory function to create a saga coordinator."""
    return SagaCoordinator(
        default_timeout_ms=default_timeout_ms,
        compensation_timeout_ms=compensation_timeout_ms,
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "CompensationStrategy",
    "SagaCheckpoint",
    "SagaCompensation",
    "SagaCoordinator",
    "SagaState",
    "SagaStep",
    "SagaTransaction",
    "StepState",
    "create_saga_coordinator",
    "saga_context",
]
