from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from enhanced_agent_bus.data_flywheel.dataset_builder import (
    CrossTenantDatasetError,
    InMemoryFeedbackEventSource,
)
from enhanced_agent_bus.data_flywheel.models import DecisionEvent, EvaluationMode, FeedbackEvent
from enhanced_agent_bus.data_flywheel.run_orchestrator import (
    FlywheelRunOrchestrator,
    FlywheelRunPausedError,
)
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository
from enhanced_agent_bus.saga_persistence.models import (
    FlywheelRunRecord,
    FlywheelRunStage,
    PersistedSagaState,
    SagaCheckpoint,
    SagaState,
)
from enhanced_agent_bus.saga_persistence.repository import SagaStateRepository

NOW = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)


class RecordingSagaRepository(SagaStateRepository):
    def __init__(self) -> None:
        self.saved: dict[str, PersistedSagaState] = {}
        self.checkpoints: dict[str, list[SagaCheckpoint]] = {}

    async def save(self, saga: PersistedSagaState) -> bool:
        self.saved[saga.saga_id] = saga
        return True

    async def get(self, saga_id: str) -> PersistedSagaState | None:
        return self.saved.get(saga_id)

    async def delete(self, saga_id: str) -> bool:
        return self.saved.pop(saga_id, None) is not None

    async def exists(self, saga_id: str) -> bool:
        return saga_id in self.saved

    async def list_by_tenant(self, tenant_id: str, state=None, limit=100, offset=0):
        rows = [saga for saga in self.saved.values() if saga.tenant_id == tenant_id]
        if state is not None:
            rows = [saga for saga in rows if saga.state == state]
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def list_by_state(self, state, limit=100, offset=0):
        rows = [saga for saga in self.saved.values() if saga.state == state]
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def list_pending_compensations(self, limit=100):
        return []

    async def list_timed_out(self, since, limit=100):
        return []

    async def count_by_state(self, state):
        return len([saga for saga in self.saved.values() if saga.state == state])

    async def count_by_tenant(self, tenant_id):
        return len([saga for saga in self.saved.values() if saga.tenant_id == tenant_id])

    async def update_state(self, saga_id, new_state, failure_reason=None):
        saga = self.saved.get(saga_id)
        if saga is None:
            return False
        saga.state = new_state
        saga.failure_reason = failure_reason
        if new_state == SagaState.RUNNING and saga.started_at is None:
            saga.started_at = NOW
        if new_state == SagaState.FAILED:
            saga.failed_at = NOW
        if new_state == SagaState.COMPLETED:
            saga.completed_at = NOW
        return True

    async def update_step_state(
        self, saga_id, step_id, new_state, output_data=None, error_message=None
    ):
        return True

    async def update_current_step(self, saga_id, step_index):
        saga = self.saved.get(saga_id)
        if saga is None:
            return False
        saga.current_step_index = step_index
        return True

    async def save_checkpoint(self, checkpoint):
        self.checkpoints.setdefault(checkpoint.saga_id, []).append(checkpoint)
        return True

    async def get_checkpoints(self, saga_id, limit=100):
        rows = list(reversed(self.checkpoints.get(saga_id, [])))
        return rows[:limit]

    async def get_latest_checkpoint(self, saga_id):
        rows = self.checkpoints.get(saga_id, [])
        return rows[-1] if rows else None

    async def delete_checkpoints(self, saga_id):
        rows = self.checkpoints.pop(saga_id, [])
        return len(rows)

    async def append_compensation_entry(self, saga_id, entry):
        return True

    async def get_compensation_log(self, saga_id):
        return []

    async def acquire_lock(self, saga_id, lock_holder, ttl_seconds=30):
        return True

    async def release_lock(self, saga_id, lock_holder):
        return True

    async def extend_lock(self, saga_id, lock_holder, ttl_seconds=30):
        return True

    async def cleanup_old_sagas(self, older_than, terminal_only=True):
        return 0

    async def get_statistics(self):
        return {}

    async def health_check(self):
        return {"status": "ok"}


def make_run(**kwargs) -> FlywheelRunRecord:
    defaults = {
        "run_id": str(uuid4()),
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "stage": FlywheelRunStage.DATASET_BUILD,
        "evaluation_mode": EvaluationMode.OFFLINE_REPLAY,
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(kwargs)
    return FlywheelRunRecord(**defaults)


def make_decision_event(**kwargs) -> DecisionEvent:
    defaults = {
        "decision_id": "decision-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "constitutional_hash": "608508a9bd224290",
        "decision_kind": "policy",
        "request_context": {"request_id": "req-1"},
        "decision_payload": {"score": 0.92},
        "outcome": "approved",
        "created_at": NOW,
    }
    defaults.update(kwargs)
    return DecisionEvent(**defaults)


def make_feedback_event(**kwargs) -> FeedbackEvent:
    defaults = {
        "feedback_id": "feedback-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "constitutional_hash": "608508a9bd224290",
        "feedback_type": "general",
        "outcome_status": "submitted",
        "comment": "Looks fine",
        "metadata": {"page": "/governance"},
        "created_at": NOW.replace(minute=5),
    }
    defaults.update(kwargs)
    return FeedbackEvent(**defaults)


@pytest.mark.asyncio
async def test_dataset_build_step_advances_run_and_checkpoints(tmp_path: Path) -> None:
    workflow_repository = InMemoryWorkflowRepository()
    decision = make_decision_event()
    await workflow_repository.save_decision_event(decision)
    feedback = make_feedback_event()

    saga_repository = RecordingSagaRepository()
    run = make_run()
    await saga_repository.save_flywheel_run(run)

    orchestrator = FlywheelRunOrchestrator(
        workflow_repository,
        saga_repository,
        InMemoryFeedbackEventSource([feedback]),
        artifact_root=tmp_path,
    )

    snapshot = await orchestrator.run_dataset_build_step(run.run_id)
    updated_run = await saga_repository.get_flywheel_run(run.run_id)
    checkpoint = await saga_repository.get_latest_checkpoint(run.run_id)

    assert snapshot.record_count == 2
    assert updated_run is not None
    assert updated_run.state == SagaState.RUNNING
    assert updated_run.stage == FlywheelRunStage.CANDIDATE_GENERATION
    assert updated_run.dataset_snapshot_id == snapshot.snapshot_id
    assert (
        updated_run.context["dataset_snapshot"]["artifact_manifest_uri"]
        == snapshot.artifact_manifest_uri
    )
    assert updated_run.metadata["latest_dataset_snapshot_id"] == snapshot.snapshot_id
    assert checkpoint is not None
    assert checkpoint.checkpoint_name == "dataset_build_completed"
    assert checkpoint.metadata["dataset_snapshot_id"] == snapshot.snapshot_id


@pytest.mark.asyncio
async def test_dataset_build_step_rejects_paused_runs(tmp_path: Path) -> None:
    workflow_repository = InMemoryWorkflowRepository()
    saga_repository = RecordingSagaRepository()
    run = make_run(paused=True)
    await saga_repository.save_flywheel_run(run)

    orchestrator = FlywheelRunOrchestrator(
        workflow_repository,
        saga_repository,
        InMemoryFeedbackEventSource([]),
        artifact_root=tmp_path,
    )

    with pytest.raises(FlywheelRunPausedError):
        await orchestrator.run_dataset_build_step(run.run_id)


@pytest.mark.asyncio
async def test_dataset_build_step_marks_run_failed_when_build_errors(tmp_path: Path) -> None:
    workflow_repository = InMemoryWorkflowRepository()
    await workflow_repository.save_decision_event(make_decision_event())
    saga_repository = RecordingSagaRepository()
    run = make_run()
    await saga_repository.save_flywheel_run(run)

    orchestrator = FlywheelRunOrchestrator(
        workflow_repository,
        saga_repository,
        InMemoryFeedbackEventSource(
            [
                make_feedback_event(
                    tenant_id="tenant-b",
                    workload_key="tenant-b/api/tool/policy/608508a9bd224290",
                )
            ]
        ),
        artifact_root=tmp_path,
    )

    async def _boom(*args, **kwargs):
        raise CrossTenantDatasetError("mixed tenant dataset")

    orchestrator._workflow_repository.list_decision_events = _boom  # type: ignore[method-assign]

    with pytest.raises(CrossTenantDatasetError):
        await orchestrator.run_dataset_build_step(run.run_id)

    failed_run = await saga_repository.get_flywheel_run(run.run_id)
    assert failed_run is not None
    assert failed_run.state == SagaState.FAILED
    assert failed_run.failure_reason == "dataset_build_failed:CrossTenantDatasetError"
