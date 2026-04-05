"""
Workflow Repository - Database abstraction for workflow persistence.

Constitutional Hash: 608508a9bd224290
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import UUID

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.data_flywheel.models import (
    CandidateArtifact,
    DatasetSnapshot,
    DecisionEvent,
    EvaluationRun,
    EvidenceBundle,
)

from .models import (
    CheckpointData,
    WorkflowCompensation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)

RepositoryIdT = TypeVar("RepositoryIdT")
CheckpointT = TypeVar("CheckpointT")
CheckpointSaveResultT = TypeVar("CheckpointSaveResultT")


class GovernanceRepository(
    ABC,
    Generic[RepositoryIdT, CheckpointT, CheckpointSaveResultT],
):
    """Shared governance persistence contract used by workflow and saga stores."""

    @property
    def constitutional_hash(self) -> str:
        """Return the constitutional hash for validation."""
        return CONSTITUTIONAL_HASH  # type: ignore[no-any-return]

    @abstractmethod
    async def save_checkpoint(self, checkpoint: CheckpointT) -> CheckpointSaveResultT:
        """Persist a checkpoint snapshot."""

    @abstractmethod
    async def get_latest_checkpoint(
        self, instance_id: RepositoryIdT
    ) -> CheckpointT | None:
        """Get the latest checkpoint for a governance record."""


class WorkflowRepository(GovernanceRepository[UUID, CheckpointData, None]):
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
    async def list_workflows(
        self, tenant_id: str, status: WorkflowStatus | None = None, limit: int = 100
    ) -> list[WorkflowInstance]:
        """List workflows matching criteria."""
        pass

    @abstractmethod
    async def save_decision_event(self, event: DecisionEvent) -> None:
        """Persist an immutable flywheel decision event."""

    @abstractmethod
    async def list_decision_events(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DecisionEvent]:
        """List flywheel decision events with tenant scoping."""

    @abstractmethod
    async def save_dataset_snapshot(self, snapshot: DatasetSnapshot) -> None:
        """Persist flywheel dataset snapshot metadata."""

    @abstractmethod
    async def get_dataset_snapshot(self, snapshot_id: str) -> DatasetSnapshot | None:
        """Fetch flywheel dataset snapshot metadata by identifier."""

    @abstractmethod
    async def list_dataset_snapshots(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DatasetSnapshot]:
        """List flywheel dataset snapshots with tenant scoping."""

    @abstractmethod
    async def save_candidate_artifact(self, candidate: CandidateArtifact) -> None:
        """Persist flywheel candidate metadata."""

    @abstractmethod
    async def get_candidate_artifact(self, candidate_id: str) -> CandidateArtifact | None:
        """Fetch flywheel candidate metadata by identifier."""

    @abstractmethod
    async def list_candidate_artifacts(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CandidateArtifact]:
        """List flywheel candidate artifacts with tenant scoping."""

    @abstractmethod
    async def save_evaluation_run(self, run: EvaluationRun) -> None:
        """Persist flywheel evaluation summary metadata."""

    @abstractmethod
    async def get_evaluation_run(self, run_id: str) -> EvaluationRun | None:
        """Fetch flywheel evaluation run metadata by identifier."""

    @abstractmethod
    async def list_evaluation_runs(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EvaluationRun]:
        """List flywheel evaluation runs with tenant scoping."""

    @abstractmethod
    async def save_evidence_bundle(self, evidence: EvidenceBundle) -> None:
        """Persist flywheel evidence bundle metadata."""

    @abstractmethod
    async def get_evidence_bundle(self, evidence_id: str) -> EvidenceBundle | None:
        """Fetch flywheel evidence bundle metadata by identifier."""

    @abstractmethod
    async def list_evidence_bundles(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EvidenceBundle]:
        """List evidence bundles with tenant and workload scoping."""


class InMemoryWorkflowRepository(WorkflowRepository):
    """In-memory implementation for testing and development."""

    def __init__(self) -> None:
        self._workflows: dict[UUID, WorkflowInstance] = {}
        self._steps: dict[UUID, WorkflowStep] = {}
        self._events: dict[UUID, list[WorkflowEvent]] = {}
        self._compensations: dict[UUID, list[WorkflowCompensation]] = {}
        self._checkpoints: dict[UUID, list[CheckpointData]] = {}
        self._decision_events: dict[str, DecisionEvent] = {}
        self._dataset_snapshots: dict[str, DatasetSnapshot] = {}
        self._candidate_artifacts: dict[str, CandidateArtifact] = {}
        self._evaluation_runs: dict[str, EvaluationRun] = {}
        self._evidence_bundles: dict[str, EvidenceBundle] = {}

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

    async def save_decision_event(self, event: DecisionEvent) -> None:
        self._decision_events[event.decision_id] = event

    async def list_decision_events(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DecisionEvent]:
        events = [event for event in self._decision_events.values() if event.tenant_id == tenant_id]
        if workload_key is not None:
            events = [event for event in events if event.workload_key == workload_key]
        events.sort(key=lambda item: item.created_at, reverse=True)
        return events[offset : offset + limit]

    async def save_dataset_snapshot(self, snapshot: DatasetSnapshot) -> None:
        self._dataset_snapshots[snapshot.snapshot_id] = snapshot

    async def get_dataset_snapshot(self, snapshot_id: str) -> DatasetSnapshot | None:
        return self._dataset_snapshots.get(snapshot_id)

    async def list_dataset_snapshots(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DatasetSnapshot]:
        snapshots = [
            snapshot for snapshot in self._dataset_snapshots.values() if snapshot.tenant_id == tenant_id
        ]
        if workload_key is not None:
            snapshots = [snapshot for snapshot in snapshots if snapshot.workload_key == workload_key]
        snapshots.sort(key=lambda item: item.created_at, reverse=True)
        return snapshots[offset : offset + limit]

    async def save_candidate_artifact(self, candidate: CandidateArtifact) -> None:
        self._candidate_artifacts[candidate.candidate_id] = candidate

    async def get_candidate_artifact(self, candidate_id: str) -> CandidateArtifact | None:
        return self._candidate_artifacts.get(candidate_id)

    async def list_candidate_artifacts(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CandidateArtifact]:
        candidates = [
            candidate
            for candidate in self._candidate_artifacts.values()
            if candidate.tenant_id == tenant_id
        ]
        if workload_key is not None:
            candidates = [candidate for candidate in candidates if candidate.workload_key == workload_key]
        candidates.sort(key=lambda item: item.created_at, reverse=True)
        return candidates[offset : offset + limit]

    async def save_evaluation_run(self, run: EvaluationRun) -> None:
        self._evaluation_runs[run.run_id] = run

    async def get_evaluation_run(self, run_id: str) -> EvaluationRun | None:
        return self._evaluation_runs.get(run_id)

    async def list_evaluation_runs(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EvaluationRun]:
        runs = [run for run in self._evaluation_runs.values() if run.tenant_id == tenant_id]
        if workload_key is not None:
            runs = [run for run in runs if run.workload_key == workload_key]
        runs.sort(key=lambda item: item.created_at, reverse=True)
        return runs[offset : offset + limit]

    async def save_evidence_bundle(self, evidence: EvidenceBundle) -> None:
        self._evidence_bundles[evidence.evidence_id] = evidence

    async def get_evidence_bundle(self, evidence_id: str) -> EvidenceBundle | None:
        return self._evidence_bundles.get(evidence_id)

    async def list_evidence_bundles(
        self,
        tenant_id: str,
        workload_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EvidenceBundle]:
        bundles = [bundle for bundle in self._evidence_bundles.values() if bundle.tenant_id == tenant_id]
        if workload_key is not None:
            bundles = [bundle for bundle in bundles if bundle.workload_key == workload_key]
        bundles.sort(key=lambda item: item.created_at, reverse=True)
        return bundles[offset : offset + limit]
