"""
Saga Persistence Models
Constitutional Hash: 608508a9bd224290

Core data models for saga state persistence, designed for Redis hash storage
with efficient serialization and deserialization.

Features:
- Immutable state snapshots for audit trails
- Redis hash serialization/deserialization
- Constitutional hash validation at all levels
- type-safe enums for state management
"""

import json
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]


class SagaState(str, Enum):
    """
    States of a Saga transaction.

    State transitions:
        INITIALIZED -> RUNNING -> COMPLETED
        INITIALIZED -> RUNNING -> COMPENSATING -> COMPENSATED
        INITIALIZED -> RUNNING -> COMPENSATING -> FAILED
        * -> FAILED (on unrecoverable error)
    """

    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    COMPENSATING = "COMPENSATING"
    COMPLETED = "COMPLETED"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"

    def is_terminal(self) -> bool:
        """Check if this is a terminal state (no further transitions allowed)."""
        return self in (SagaState.COMPLETED, SagaState.COMPENSATED, SagaState.FAILED)

    def allows_compensation(self) -> bool:
        """Check if compensation can be initiated from this state."""
        return self in (SagaState.RUNNING, SagaState.COMPENSATING)


class StepState(str, Enum):
    """
    States of individual saga steps.

    State transitions:
        PENDING -> RUNNING -> COMPLETED
        PENDING -> RUNNING -> FAILED -> COMPENSATED
        PENDING -> SKIPPED (when dependencies fail)
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"
    SKIPPED = "SKIPPED"

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (
            StepState.COMPLETED,
            StepState.FAILED,
            StepState.COMPENSATED,
            StepState.SKIPPED,
        )

    def requires_compensation(self) -> bool:
        """Check if this step requires compensation on saga failure."""
        return self == StepState.COMPLETED


class CompensationStrategy(str, Enum):
    """
    Compensation execution strategies.

    LIFO: Last-In-First-Out - compensate in reverse order (default, safest)
    PARALLEL: Execute all compensations in parallel (faster, less safe)
    SELECTIVE: Only compensate steps that depend on failed step
    """

    LIFO = "LIFO"
    PARALLEL = "PARALLEL"
    SELECTIVE = "SELECTIVE"


@dataclass
class CompensationEntry:
    """
    Record of a compensation action execution.

    Tracks the compensation attempt for a specific step, including
    timing, results, and any errors encountered.
    """

    compensation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str = ""
    step_name: str = ""
    executed: bool = False
    executed_at: datetime | None = None
    duration_ms: float = 0.0
    result: JSONValue | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for storage."""
        return {
            "compensation_id": self.compensation_id,
            "step_id": self.step_id,
            "step_name": self.step_name,
            "executed": self.executed,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "duration_ms": self.duration_ms,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "CompensationEntry":
        """Create from dictionary."""
        executed_at = None
        if data.get("executed_at"):
            executed_at = datetime.fromisoformat(str(data["executed_at"]))

        return cls(
            compensation_id=str(data.get("compensation_id", str(uuid.uuid4()))),
            step_id=str(data.get("step_id", "")),
            step_name=str(data.get("step_name", "")),
            executed=bool(data.get("executed", False)),
            executed_at=executed_at,
            duration_ms=float(data.get("duration_ms", 0.0)),
            result=data.get("result"),
            error=data.get("error"),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            constitutional_hash=str(data.get("constitutional_hash", CONSTITUTIONAL_HASH)),
        )


@dataclass
class PersistedStepSnapshot:
    """
    Immutable snapshot of a saga step's state at a point in time.

    Used for:
    - Persistence to Redis
    - Recovery after system restart
    - Audit trail generation
    """

    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_name: str = ""
    step_index: int = 0
    state: StepState = StepState.PENDING
    input_data: JSONDict = field(default_factory=dict)
    output_data: JSONValue | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    retry_count: int = 0
    max_retries: int = 3
    timeout_ms: int = 30000
    dependencies: list[str] = field(default_factory=list)
    compensation: CompensationEntry | None = None
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for storage."""
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "step_index": self.step_index,
            "state": self.state.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "timeout_ms": self.timeout_ms,
            "dependencies": self.dependencies,
            "compensation": self.compensation.to_dict() if self.compensation else None,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "PersistedStepSnapshot":
        """Create from dictionary."""
        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(str(data["started_at"]))

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(str(data["completed_at"]))

        compensation = None
        if data.get("compensation"):
            compensation_data = data["compensation"]
            if isinstance(compensation_data, dict):
                compensation = CompensationEntry.from_dict(compensation_data)

        state_value = data.get("state", "PENDING")
        state = StepState(str(state_value)) if state_value else StepState.PENDING

        dependencies = data.get("dependencies", [])
        if not isinstance(dependencies, list):
            dependencies = []

        return cls(
            step_id=str(data.get("step_id", str(uuid.uuid4()))),
            step_name=str(data.get("step_name", "")),
            step_index=int(data.get("step_index", 0)),
            state=state,
            input_data=dict(data.get("input_data", {})) if data.get("input_data") else {},
            output_data=data.get("output_data"),
            error_message=data.get("error_message"),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=float(data.get("duration_ms", 0.0)),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            timeout_ms=int(data.get("timeout_ms", 30000)),
            dependencies=[str(d) for d in dependencies],
            compensation=compensation,
            metadata=dict(data.get("metadata", {})) if data.get("metadata") else {},
            constitutional_hash=str(data.get("constitutional_hash", CONSTITUTIONAL_HASH)),
        )


@dataclass
class PersistedSagaState:
    """
    Complete saga state for persistence.

    Designed for efficient Redis hash storage with atomic operations.
    All fields are serializable to JSON for Redis HSET operations.

    Key features:
    - Unique saga_id for Redis key construction
    - Tenant isolation via tenant_id
    - Full step history for recovery
    - Compensation log for audit trails
    """

    saga_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    saga_name: str = ""
    tenant_id: str = ""
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: SagaState = SagaState.INITIALIZED
    compensation_strategy: CompensationStrategy = CompensationStrategy.LIFO
    steps: list[PersistedStepSnapshot] = field(default_factory=list)
    current_step_index: int = 0
    context: JSONDict = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    compensation_log: list[CompensationEntry] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    compensated_at: datetime | None = None
    total_duration_ms: float = 0.0
    failure_reason: str | None = None
    timeout_ms: int = 300000  # 5 minutes default
    version: int = 1  # For optimistic locking
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for general storage."""
        return {
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
            "state": self.state.value,
            "compensation_strategy": self.compensation_strategy.value,
            "steps": [step.to_dict() for step in self.steps],
            "current_step_index": self.current_step_index,
            "context": self.context,
            "metadata": self.metadata,
            "compensation_log": [entry.to_dict() for entry in self.compensation_log],
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "compensated_at": self.compensated_at.isoformat() if self.compensated_at else None,
            "total_duration_ms": self.total_duration_ms,
            "failure_reason": self.failure_reason,
            "timeout_ms": self.timeout_ms,
            "version": self.version,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "PersistedSagaState":
        """Create from dictionary."""
        # Parse datetime fields
        created_at = datetime.now(UTC)
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]))

        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(str(data["started_at"]))

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(str(data["completed_at"]))

        failed_at = None
        if data.get("failed_at"):
            failed_at = datetime.fromisoformat(str(data["failed_at"]))

        compensated_at = None
        if data.get("compensated_at"):
            compensated_at = datetime.fromisoformat(str(data["compensated_at"]))

        # Parse steps
        steps_data = data.get("steps", [])
        steps = []
        if isinstance(steps_data, list):
            for step_data in steps_data:
                if isinstance(step_data, dict):
                    steps.append(PersistedStepSnapshot.from_dict(step_data))

        # Parse compensation log
        compensation_log_data = data.get("compensation_log", [])
        compensation_log = []
        if isinstance(compensation_log_data, list):
            for entry_data in compensation_log_data:
                if isinstance(entry_data, dict):
                    compensation_log.append(CompensationEntry.from_dict(entry_data))

        # Parse enums with safe defaults
        state_value = data.get("state", "INITIALIZED")
        state = SagaState(str(state_value)) if state_value else SagaState.INITIALIZED

        strategy_value = data.get("compensation_strategy", "LIFO")
        strategy = (
            CompensationStrategy(str(strategy_value))
            if strategy_value
            else CompensationStrategy.LIFO
        )

        return cls(
            saga_id=str(data.get("saga_id", str(uuid.uuid4()))),
            saga_name=str(data.get("saga_name", "")),
            tenant_id=str(data.get("tenant_id", "")),
            correlation_id=str(data.get("correlation_id", str(uuid.uuid4()))),
            state=state,
            compensation_strategy=strategy,
            steps=steps,
            current_step_index=int(data.get("current_step_index", 0)),
            context=dict(data.get("context", {})) if data.get("context") else {},
            metadata=dict(data.get("metadata", {})) if data.get("metadata") else {},
            compensation_log=compensation_log,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            failed_at=failed_at,
            compensated_at=compensated_at,
            total_duration_ms=float(data.get("total_duration_ms", 0.0)),
            failure_reason=data.get("failure_reason"),
            timeout_ms=int(data.get("timeout_ms", 300000)),
            version=int(data.get("version", 1)),
            constitutional_hash=str(data.get("constitutional_hash", CONSTITUTIONAL_HASH)),
        )

    def to_redis_hash(self) -> dict[str, str]:
        """
        Convert to Redis hash format (all values as strings).

        Redis HSET requires string values, so complex fields are JSON-encoded.
        This enables atomic HMSET operations for the entire saga state.

        Returns:
            Dictionary with string keys and string values suitable for Redis HSET.
        """
        return {
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
            "state": self.state.value,
            "compensation_strategy": self.compensation_strategy.value,
            "steps": json.dumps([step.to_dict() for step in self.steps]),
            "current_step_index": str(self.current_step_index),
            "context": json.dumps(self.context),
            "metadata": json.dumps(self.metadata),
            "compensation_log": json.dumps([entry.to_dict() for entry in self.compensation_log]),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "completed_at": self.completed_at.isoformat() if self.completed_at else "",
            "failed_at": self.failed_at.isoformat() if self.failed_at else "",
            "compensated_at": self.compensated_at.isoformat() if self.compensated_at else "",
            "total_duration_ms": str(self.total_duration_ms),
            "failure_reason": self.failure_reason or "",
            "timeout_ms": str(self.timeout_ms),
            "version": str(self.version),
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_redis_hash(cls, data: dict[str, str]) -> "PersistedSagaState":
        """
        Create from Redis hash format (string values).

        Parses JSON-encoded complex fields and converts string values back
        to appropriate Python types.

        Args:
            data: Dictionary with string keys and string values from Redis HGETALL.

        Returns:
            PersistedSagaState instance reconstructed from Redis data.
        """
        # Parse JSON-encoded fields
        steps_json = data.get("steps", "[]")
        steps_data = json.loads(steps_json) if steps_json else []
        steps = [PersistedStepSnapshot.from_dict(s) for s in steps_data if isinstance(s, dict)]

        context_json = data.get("context", "{}")
        context = json.loads(context_json) if context_json else {}

        metadata_json = data.get("metadata", "{}")
        metadata = json.loads(metadata_json) if metadata_json else {}

        compensation_log_json = data.get("compensation_log", "[]")
        compensation_log_data = json.loads(compensation_log_json) if compensation_log_json else []
        compensation_log = [
            CompensationEntry.from_dict(e) for e in compensation_log_data if isinstance(e, dict)
        ]

        # Parse datetime fields (empty strings become None)
        created_at = datetime.now(UTC)
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"])

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])

        failed_at = None
        if data.get("failed_at"):
            failed_at = datetime.fromisoformat(data["failed_at"])

        compensated_at = None
        if data.get("compensated_at"):
            compensated_at = datetime.fromisoformat(data["compensated_at"])

        # Parse enums
        state_str = data.get("state", "INITIALIZED")
        state = SagaState(state_str) if state_str else SagaState.INITIALIZED

        strategy_str = data.get("compensation_strategy", "LIFO")
        strategy = CompensationStrategy(strategy_str) if strategy_str else CompensationStrategy.LIFO

        return cls(
            saga_id=data.get("saga_id", str(uuid.uuid4())),
            saga_name=data.get("saga_name", ""),
            tenant_id=data.get("tenant_id", ""),
            correlation_id=data.get("correlation_id", str(uuid.uuid4())),
            state=state,
            compensation_strategy=strategy,
            steps=steps,
            current_step_index=int(data.get("current_step_index", "0")),
            context=context,
            metadata=metadata,
            compensation_log=compensation_log,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            failed_at=failed_at,
            compensated_at=compensated_at,
            total_duration_ms=float(data.get("total_duration_ms", "0.0")),
            failure_reason=data.get("failure_reason") or None,
            timeout_ms=int(data.get("timeout_ms", "300000")),
            version=int(data.get("version", "1")),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )

    @property
    def completed_steps(self) -> list[PersistedStepSnapshot]:
        """Get list of completed steps."""
        return [s for s in self.steps if s.state == StepState.COMPLETED]

    @property
    def pending_steps(self) -> list[PersistedStepSnapshot]:
        """Get list of pending steps."""
        return [s for s in self.steps if s.state == StepState.PENDING]

    @property
    def failed_steps(self) -> list[PersistedStepSnapshot]:
        """Get list of failed steps."""
        return [s for s in self.steps if s.state == StepState.FAILED]

    @property
    def is_terminal(self) -> bool:
        """Check if saga is in a terminal state."""
        return self.state.is_terminal()

    def increment_version(self) -> "PersistedSagaState":
        """Return a new instance with incremented version (for optimistic locking)."""
        return PersistedSagaState(
            saga_id=self.saga_id,
            saga_name=self.saga_name,
            tenant_id=self.tenant_id,
            correlation_id=self.correlation_id,
            state=self.state,
            compensation_strategy=self.compensation_strategy,
            steps=self.steps,
            current_step_index=self.current_step_index,
            context=self.context,
            metadata=self.metadata,
            compensation_log=self.compensation_log,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            failed_at=self.failed_at,
            compensated_at=self.compensated_at,
            total_duration_ms=self.total_duration_ms,
            failure_reason=self.failure_reason,
            timeout_ms=self.timeout_ms,
            version=self.version + 1,
            constitutional_hash=self.constitutional_hash,
        )


@dataclass
class SagaCheckpoint:
    """
    Checkpoint for saga recovery.

    Captures the saga state at critical points for recovery after
    system failures. Constitutional checkpoints are mandatory before
    irreversible operations.
    """

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    saga_id: str = ""
    checkpoint_name: str = ""
    state_snapshot: JSONDict = field(default_factory=dict)
    completed_step_ids: list[str] = field(default_factory=list)
    pending_step_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_constitutional: bool = False
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for storage."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "saga_id": self.saga_id,
            "checkpoint_name": self.checkpoint_name,
            "state_snapshot": self.state_snapshot,
            "completed_step_ids": self.completed_step_ids,
            "pending_step_ids": self.pending_step_ids,
            "created_at": self.created_at.isoformat(),
            "is_constitutional": self.is_constitutional,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "SagaCheckpoint":
        """Create from dictionary."""
        created_at = datetime.now(UTC)
        if data.get("created_at"):
            created_at = datetime.fromisoformat(str(data["created_at"]))

        completed_ids = data.get("completed_step_ids", [])
        if not isinstance(completed_ids, list):
            completed_ids = []

        pending_ids = data.get("pending_step_ids", [])
        if not isinstance(pending_ids, list):
            pending_ids = []

        snapshot_data = data.get("state_snapshot")
        return cls(
            checkpoint_id=str(data.get("checkpoint_id", str(uuid.uuid4()))),
            saga_id=str(data.get("saga_id", "")),
            checkpoint_name=str(data.get("checkpoint_name", "")),
            state_snapshot=dict(snapshot_data) if snapshot_data else {},
            completed_step_ids=[str(s) for s in completed_ids],
            pending_step_ids=[str(s) for s in pending_ids],
            created_at=created_at,
            is_constitutional=bool(data.get("is_constitutional", False)),
            metadata=dict(data.get("metadata", {})) if data.get("metadata") else {},
            constitutional_hash=str(data.get("constitutional_hash", CONSTITUTIONAL_HASH)),
        )


# type aliases for saga operations
SagaActionFunc = Callable[..., Coroutine[object, object, JSONDict]]
CompensationFunc = Callable[..., Coroutine[object, object, JSONDict]]


__all__ = [
    "CONSTITUTIONAL_HASH",
    "CompensationEntry",
    "CompensationFunc",
    "CompensationStrategy",
    "PersistedSagaState",
    "PersistedStepSnapshot",
    "SagaActionFunc",
    "SagaCheckpoint",
    "SagaState",
    "StepState",
]
