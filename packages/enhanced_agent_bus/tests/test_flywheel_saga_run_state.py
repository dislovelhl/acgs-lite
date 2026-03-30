from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from enhanced_agent_bus.data_flywheel.models import EvaluationMode
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
        self.next_update_result = True

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
        rows = [s for s in self.saved.values() if s.tenant_id == tenant_id]
        if state is not None:
            rows = [s for s in rows if s.state == state]
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def list_by_state(self, state, limit=100, offset=0):
        rows = [s for s in self.saved.values() if s.state == state]
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def list_pending_compensations(self, limit=100):
        return []

    async def list_timed_out(self, since, limit=100):
        return []

    async def count_by_state(self, state):
        return len([s for s in self.saved.values() if s.state == state])

    async def count_by_tenant(self, tenant_id):
        return len([s for s in self.saved.values() if s.tenant_id == tenant_id])

    async def update_state(self, saga_id, new_state, failure_reason=None):
        saga = self.saved.get(saga_id)
        if saga is None:
            return False
        saga.state = new_state
        saga.failure_reason = failure_reason
        if new_state == SagaState.RUNNING and saga.started_at is None:
            saga.started_at = NOW
        if new_state == SagaState.COMPLETED:
            saga.completed_at = NOW
        if new_state == SagaState.FAILED:
            saga.failed_at = NOW
        return self.next_update_result

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
        "candidate_id": "candidate-001",
        "evaluation_mode": EvaluationMode.OFFLINE_REPLAY,
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(kwargs)
    return FlywheelRunRecord(**defaults)


class TestFlywheelRunRecord:
    def test_round_trips_through_saga_state(self) -> None:
        run = make_run()

        saga = run.to_saga_state()
        restored = FlywheelRunRecord.from_saga_state(saga)

        assert saga.saga_name == "flywheel_run"
        assert restored == run

    def test_from_saga_state_rejects_non_flywheel_sagas(self) -> None:
        saga = make_run().to_saga_state()
        saga.saga_name = "other"

        with pytest.raises(ValueError, match="flywheel"):
            FlywheelRunRecord.from_saga_state(saga)


class TestSagaStateRepositoryFlywheelHelpers:
    async def test_save_and_get_flywheel_run(self) -> None:
        repo = RecordingSagaRepository()
        run = make_run()

        saved = await repo.save_flywheel_run(run)
        loaded = await repo.get_flywheel_run(run.run_id)

        assert saved is True
        assert loaded == run

    async def test_list_flywheel_runs_by_tenant_filters_non_flywheel_sagas(self) -> None:
        repo = RecordingSagaRepository()
        keep = make_run()
        await repo.save_flywheel_run(keep)
        repo.saved[str(uuid4())] = PersistedSagaState(
            saga_id=str(uuid4()),
            saga_name="migration",
            tenant_id="tenant-a",
            created_at=NOW,
        )

        result = await repo.list_flywheel_runs_by_tenant("tenant-a")

        assert result == [keep]

    async def test_start_pause_resume_complete_stop_flow(self) -> None:
        repo = RecordingSagaRepository()
        run = make_run()
        await repo.save_flywheel_run(run)

        assert await repo.start_flywheel_run(run.run_id) is True
        started = await repo.get_flywheel_run(run.run_id)
        assert started is not None
        assert started.state == SagaState.RUNNING

        assert await repo.pause_flywheel_run(run.run_id, reason="manual") is True
        paused = await repo.get_flywheel_run(run.run_id)
        assert paused is not None
        assert paused.paused is True
        assert paused.metadata["pause_reason"] == "manual"

        assert await repo.resume_flywheel_run(run.run_id) is True
        resumed = await repo.get_flywheel_run(run.run_id)
        assert resumed is not None
        assert resumed.paused is False

        assert await repo.complete_flywheel_run(run.run_id) is True
        completed = await repo.get_flywheel_run(run.run_id)
        assert completed is not None
        assert completed.state == SagaState.COMPLETED

        stop_run = make_run(run_id=str(uuid4()))
        await repo.save_flywheel_run(stop_run)
        await repo.start_flywheel_run(stop_run.run_id)
        assert await repo.stop_flywheel_run(stop_run.run_id, reason="operator stop") is True
        stopped = await repo.get_flywheel_run(stop_run.run_id)
        assert stopped is not None
        assert stopped.state == SagaState.FAILED
        assert stopped.failure_reason == "operator stop"

    async def test_checkpoint_and_resume_after_interruption(self) -> None:
        repo = RecordingSagaRepository()
        run = make_run()
        await repo.save_flywheel_run(run)

        await repo.start_flywheel_run(run.run_id)
        await repo.advance_flywheel_run_stage(
            run.run_id,
            FlywheelRunStage.EVALUATION,
            current_step_index=3,
            metadata={"checkpoint": "ready"},
        )
        await repo.save_flywheel_checkpoint(run.run_id, "eval-ready")

        latest = await repo.get_latest_flywheel_checkpoint(run.run_id)
        resumed = await repo.resume_flywheel_run(run.run_id)
        loaded = await repo.get_flywheel_run(run.run_id)

        assert latest is not None
        assert latest.checkpoint_name == "eval-ready"
        assert resumed is True
        assert loaded is not None
        assert loaded.stage == FlywheelRunStage.EVALUATION
        assert loaded.current_step_index == 3
        assert loaded.metadata["checkpoint"] == "ready"
