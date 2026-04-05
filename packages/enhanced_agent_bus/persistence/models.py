"""
Workflow Persistence Models

Constitutional Hash: 608508a9bd224290
Version: 1.0.0

Data models for durable workflow execution with full audit trail support.
"""

from datetime import UTC, datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from enhanced_agent_bus.data_flywheel.models import (
    CandidateArtifact,
    DatasetSnapshot,
    DecisionEvent,
    EvaluationRun,
    EvidenceBundle,
)

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class WorkflowStatus(str, Enum):
    """Workflow instance status states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


class StepStatus(str, Enum):
    """Workflow step status states."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"


class StepType(str, Enum):
    """Types of workflow steps."""

    ACTIVITY = "activity"
    DECISION = "decision"
    COMPENSATION = "compensation"
    CHECKPOINT = "checkpoint"
    WAIT = "wait"


class EventType(str, Enum):
    """Types of workflow events for replay."""

    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    COMPENSATION_STARTED = "compensation_started"
    COMPENSATION_COMPLETED = "compensation_completed"
    COMPENSATION_FAILED = "compensation_failed"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    TIMER_FIRED = "timer_fired"
    SIGNAL_RECEIVED = "signal_received"


class WorkflowInstance(BaseModel):
    """
    Top-level workflow instance tracking.

    Attributes:
        id: Unique instance identifier
        workflow_type: Type/name of the workflow
        workflow_id: Business identifier for the workflow
        tenant_id: Tenant isolation identifier
        status: Current workflow status
        input: Input data for the workflow
        output: Output data from completed workflow
        error: Error message if failed
        started_at: When execution started
        completed_at: When execution completed
        constitutional_hash: Hash for governance validation
    """

    id: UUID = Field(default_factory=uuid4)
    workflow_type: str
    workflow_id: str
    tenant_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    input: dict | None = None
    output: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)


class WorkflowStep(BaseModel):
    """
    Individual step execution within a workflow.

    Attributes:
        id: Unique step identifier
        workflow_instance_id: Parent workflow instance
        step_name: Name of the step
        step_type: Type of step (activity, decision, etc.)
        status: Current step status
        input: Input data for the step
        output: Output data from completed step
        error: Error message if failed
        idempotency_key: Key for deduplication
        attempt_count: Number of execution attempts
    """

    id: UUID = Field(default_factory=uuid4)
    workflow_instance_id: UUID
    step_name: str
    step_type: StepType
    status: StepStatus = StepStatus.PENDING
    input: dict | None = None
    output: dict | None = None
    error: str | None = None
    idempotency_key: str | None = None
    attempt_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)


class WorkflowEvent(BaseModel):
    """
    Event sourcing record for deterministic replay.

    Events are immutable and ordered by sequence number.
    Replay produces identical results by re-applying events.

    Attributes:
        id: Auto-incrementing event ID
        workflow_instance_id: Parent workflow instance
        event_type: Type of event
        event_data: Event payload
        sequence_number: Order within workflow
        timestamp: When event occurred
    """

    id: int | None = None
    workflow_instance_id: UUID
    event_type: EventType
    event_data: dict
    sequence_number: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)


class WorkflowCompensation(BaseModel):
    """
    Saga compensation tracking for rollback.

    Compensations execute in LIFO order (reverse of execution).
    Must be idempotent for safe retry.

    Attributes:
        id: Unique compensation identifier
        workflow_instance_id: Parent workflow instance
        step_id: Step being compensated
        compensation_name: Name of compensation action
        status: Current compensation status
        input: Input data for compensation
        output: Output data from compensation
        error: Error message if failed
        executed_at: When compensation executed
    """

    id: UUID = Field(default_factory=uuid4)
    workflow_instance_id: UUID
    step_id: UUID
    compensation_name: str
    status: StepStatus = StepStatus.PENDING
    input: dict | None = None
    output: dict | None = None
    error: str | None = None
    executed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)


class CheckpointData(BaseModel):
    """
    Checkpoint snapshot for workflow recovery.

    Attributes:
        workflow_instance_id: Parent workflow instance
        checkpoint_id: Unique checkpoint identifier
        step_index: Index of last completed step
        state: Serialized workflow state
        created_at: When checkpoint was created
    """

    workflow_instance_id: UUID
    checkpoint_id: UUID = Field(default_factory=uuid4)
    step_index: int
    state: dict
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "CandidateArtifact",
    "CheckpointData",
    "DatasetSnapshot",
    "DecisionEvent",
    "EvaluationRun",
    "EventType",
    "EvidenceBundle",
    "StepStatus",
    "StepType",
    "WorkflowCompensation",
    "WorkflowEvent",
    "WorkflowInstance",
    "WorkflowStatus",
    "WorkflowStep",
]
