"""
Workflow Repository - Database abstraction for workflow persistence.

Constitutional Hash: cdd01ef066bc6cf2
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID

from .models import (
    CheckpointData,
    WorkflowCompensation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)


class WorkflowRepository(ABC):
    """Abstract repository for workflow persistence operations."""

    @abstractmethod
    async def save_workflow(self, instance: WorkflowInstance) -> None:
        """Save or update a workflow instance."""

    @abstractmethod
    async def get_workflow(self, instance_id: UUID) -> WorkflowInstance | None:
        """Get workflow by internal ID."""

    @abstractmethod
    async def get_workflow_by_business_id(
        self, workflow_id: str, tenant_id: str
    ) -> WorkflowInstance | None:
        """Get workflow by business ID and tenant."""

    @abstractmethod
    async def save_step(self, step: WorkflowStep) -> None:
        """Save or update a workflow step."""

    @abstractmethod
    async def get_step_by_idempotency_key(
        self, workflow_instance_id: UUID, idempotency_key: str
    ) -> WorkflowStep | None:
        """Get step by idempotency key for deduplication."""

    @abstractmethod
    async def get_steps(self, workflow_instance_id: UUID) -> list[WorkflowStep]:
        """Get all steps for a workflow."""

    @abstractmethod
    async def save_event(self, event: WorkflowEvent) -> None:
        """Append an event to the workflow event log."""

    @abstractmethod
    async def get_events(self, workflow_instance_id: UUID) -> list[WorkflowEvent]:
        """Get all events for a workflow in sequence order."""

    @abstractmethod
    async def get_next_sequence(self, workflow_instance_id: UUID) -> int:
        """Get the next sequence number for a workflow."""

    @abstractmethod
    async def save_compensation(self, compensation: WorkflowCompensation) -> None:
        """Save or update a compensation record."""

    @abstractmethod
    async def get_compensations(self, workflow_instance_id: UUID) -> list[WorkflowCompensation]:
        """Get all compensations for a workflow."""

    @abstractmethod
    async def save_checkpoint(self, checkpoint: CheckpointData) -> None:
        """Save a checkpoint snapshot."""

    @abstractmethod
    async def get_latest_checkpoint(self, workflow_instance_id: UUID) -> CheckpointData | None:
        """Get latest checkpoint for a workflow."""
        pass

    @abstractmethod
    async def list_workflows(
        self, tenant_id: str, status: WorkflowStatus | None = None, limit: int = 100
    ) -> list[WorkflowInstance]:
        """List workflows matching criteria."""
        pass


class InMemoryWorkflowRepository(WorkflowRepository):
    """In-memory implementation for testing and development."""

    def __init__(self) -> None:
        self._workflows: dict[UUID, WorkflowInstance] = {}
        self._steps: dict[UUID, WorkflowStep] = {}
        self._events: dict[UUID, list[WorkflowEvent]] = {}
        self._compensations: dict[UUID, list[WorkflowCompensation]] = {}
        self._checkpoints: dict[UUID, list[CheckpointData]] = {}

    async def save_workflow(self, instance: WorkflowInstance) -> None:
        self._workflows[instance.id] = instance

    async def get_workflow(self, instance_id: UUID) -> WorkflowInstance | None:
        return self._workflows.get(instance_id)

    async def get_workflow_by_business_id(
        self, workflow_id: str, tenant_id: str
    ) -> WorkflowInstance | None:
        for wf in self._workflows.values():
            if wf.workflow_id == workflow_id and wf.tenant_id == tenant_id:
                return wf
        return None

    async def save_step(self, step: WorkflowStep) -> None:
        self._steps[step.id] = step

    async def get_step_by_idempotency_key(
        self, workflow_instance_id: UUID, idempotency_key: str
    ) -> WorkflowStep | None:
        for step in self._steps.values():
            if (
                step.workflow_instance_id == workflow_instance_id
                and step.idempotency_key == idempotency_key
            ):
                return step
        return None

    async def get_steps(self, workflow_instance_id: UUID) -> list[WorkflowStep]:
        steps = [
            step
            for step in self._steps.values()
            if step.workflow_instance_id == workflow_instance_id
        ]
        return sorted(steps, key=lambda s: s.created_at)

    async def save_event(self, event: WorkflowEvent) -> None:
        if event.workflow_instance_id not in self._events:
            self._events[event.workflow_instance_id] = []
        self._events[event.workflow_instance_id].append(event)

    async def get_events(self, workflow_instance_id: UUID) -> list[WorkflowEvent]:
        events = self._events.get(workflow_instance_id, [])
        return sorted(events, key=lambda e: e.sequence_number)

    async def get_next_sequence(self, workflow_instance_id: UUID) -> int:
        events = self._events.get(workflow_instance_id, [])
        if not events:
            return 1
        return max(e.sequence_number for e in events) + 1

    async def save_compensation(self, compensation: WorkflowCompensation) -> None:
        if compensation.workflow_instance_id not in self._compensations:
            self._compensations[compensation.workflow_instance_id] = []
        existing = [
            c
            for c in self._compensations[compensation.workflow_instance_id]
            if c.id == compensation.id
        ]
        if existing:
            idx = self._compensations[compensation.workflow_instance_id].index(existing[0])
            self._compensations[compensation.workflow_instance_id][idx] = compensation
        else:
            self._compensations[compensation.workflow_instance_id].append(compensation)

    async def get_compensations(self, workflow_instance_id: UUID) -> list[WorkflowCompensation]:
        return self._compensations.get(workflow_instance_id, [])

    async def save_checkpoint(self, checkpoint: CheckpointData) -> None:
        if checkpoint.workflow_instance_id not in self._checkpoints:
            self._checkpoints[checkpoint.workflow_instance_id] = []
        self._checkpoints[checkpoint.workflow_instance_id].append(checkpoint)

    async def get_latest_checkpoint(self, workflow_instance_id: UUID) -> CheckpointData | None:
        checkpoints = self._checkpoints.get(workflow_instance_id, [])
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda c: c.created_at)

    async def list_workflows(
        self, tenant_id: str, status: WorkflowStatus | None = None, limit: int = 100
    ) -> list[WorkflowInstance]:
        results = []
        for wf in self._workflows.values():
            if wf.tenant_id == tenant_id:
                if status is None or wf.status == status:
                    results.append(wf)

        # Sort by created_at descending (newest first)
        results.sort(key=lambda x: x.created_at or datetime.now(UTC), reverse=True)
        return results[:limit]
