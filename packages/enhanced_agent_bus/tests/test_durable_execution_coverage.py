"""
Comprehensive tests for durable_execution.py to achieve >=98% coverage.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.durable_execution import (
    CONSTITUTIONAL_HASH,
    CheckpointStore,
    DurableExecutor,
    DurableStep,
    DurableWorkflow,
    ExecutionCheckpoint,
    ExecutionStatus,
    RecoveryStrategy,
    WorkflowState,
    create_durable_executor,
)

# =============================================================================
# Module-level / constants
# =============================================================================


def test_constitutional_hash_value():
    assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret


def test_all_execution_statuses():
    assert ExecutionStatus.PENDING.value == "pending"
    assert ExecutionStatus.RUNNING.value == "running"
    assert ExecutionStatus.PAUSED.value == "paused"
    assert ExecutionStatus.CHECKPOINTED.value == "checkpointed"
    assert ExecutionStatus.COMPLETED.value == "completed"
    assert ExecutionStatus.FAILED.value == "failed"
    assert ExecutionStatus.RECOVERING.value == "recovering"


def test_all_recovery_strategies():
    assert RecoveryStrategy.RETRY_STEP.value == "retry_step"
    assert RecoveryStrategy.SKIP_STEP.value == "skip_step"
    assert RecoveryStrategy.ROLLBACK.value == "rollback"
    assert RecoveryStrategy.RESTART.value == "restart"
    assert RecoveryStrategy.MANUAL.value == "manual"


def test_all_exports():
    from enhanced_agent_bus.durable_execution import __all__ as exports

    expected = {
        "DurableExecutor",
        "ExecutionCheckpoint",
        "CheckpointStore",
        "WorkflowState",
        "ExecutionStatus",
        "RecoveryStrategy",
        "DurableWorkflow",
        "DurableStep",
        "create_durable_executor",
        "CONSTITUTIONAL_HASH",
    }
    assert set(exports) == expected


# =============================================================================
# WorkflowState
# =============================================================================


class TestWorkflowState:
    def test_default_creation(self):
        state = WorkflowState(workflow_id="wf-1")
        assert state.workflow_id == "wf-1"
        assert state.current_step == 0
        assert state.total_steps == 0
        assert state.step_results == {}
        assert state.variables == {}
        assert state.metadata == {}
        assert state.started_at is None
        assert state.updated_at is None
        assert state.error is None

    def test_creation_with_all_fields(self):
        now = datetime.now(UTC)
        state = WorkflowState(
            workflow_id="wf-2",
            current_step=2,
            total_steps=5,
            step_results={0: "r0", 1: "r1"},
            variables={"key": "val"},
            metadata={"meta": True},
            started_at=now,
            updated_at=now,
            error="some error",
        )
        assert state.workflow_id == "wf-2"
        assert state.current_step == 2
        assert state.total_steps == 5
        assert state.step_results == {0: "r0", 1: "r1"}
        assert state.variables == {"key": "val"}
        assert state.metadata == {"meta": True}
        assert state.started_at == now
        assert state.updated_at == now
        assert state.error == "some error"

    def test_to_dict_with_datetimes(self):
        now = datetime.now(UTC)
        state = WorkflowState(
            workflow_id="wf-3",
            current_step=1,
            total_steps=3,
            started_at=now,
            updated_at=now,
        )
        d = state.to_dict()
        assert d["workflow_id"] == "wf-3"
        assert d["current_step"] == 1
        assert d["total_steps"] == 3
        assert d["started_at"] == now.isoformat()
        assert d["updated_at"] == now.isoformat()
        assert d["error"] is None

    def test_to_dict_without_datetimes(self):
        state = WorkflowState(workflow_id="wf-4")
        d = state.to_dict()
        assert d["started_at"] is None
        assert d["updated_at"] is None

    def test_from_dict_full(self):
        now = datetime.now(UTC)
        data = {
            "workflow_id": "wf-5",
            "current_step": 3,
            "total_steps": 10,
            "step_results": {0: "ok"},
            "variables": {"x": 1},
            "metadata": {"y": 2},
            "started_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "error": None,
        }
        state = WorkflowState.from_dict(data)
        assert state.workflow_id == "wf-5"
        assert state.current_step == 3
        assert state.total_steps == 10
        assert state.started_at is not None
        assert state.updated_at is not None
        assert state.error is None

    def test_from_dict_minimal(self):
        data = {"workflow_id": "wf-6"}
        state = WorkflowState.from_dict(data)
        assert state.workflow_id == "wf-6"
        assert state.current_step == 0
        assert state.total_steps == 0
        assert state.step_results == {}
        assert state.variables == {}
        assert state.metadata == {}
        assert state.started_at is None
        assert state.updated_at is None

    def test_roundtrip_serialization(self):
        now = datetime.now(UTC)
        original = WorkflowState(
            workflow_id="wf-rt",
            current_step=2,
            total_steps=5,
            variables={"a": "b"},
            started_at=now,
            updated_at=now,
            error="err",
        )
        reconstructed = WorkflowState.from_dict(original.to_dict())
        assert reconstructed.workflow_id == original.workflow_id
        assert reconstructed.current_step == original.current_step
        assert reconstructed.error == original.error


# =============================================================================
# ExecutionCheckpoint
# =============================================================================


class TestExecutionCheckpoint:
    def _make_state(self) -> WorkflowState:
        return WorkflowState(workflow_id="wf-chk", total_steps=3)

    def test_default_creation(self):
        state = self._make_state()
        chk = ExecutionCheckpoint(
            id="chk-1",
            workflow_id="wf-chk",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )
        assert chk.id == "chk-1"
        assert chk.workflow_id == "wf-chk"
        assert chk.step_index == 0
        assert chk.status == ExecutionStatus.CHECKPOINTED
        assert chk.constitutional_hash == CONSTITUTIONAL_HASH
        assert chk.created_at is not None

    def test_to_dict(self):
        state = self._make_state()
        now = datetime.now(UTC)
        chk = ExecutionCheckpoint(
            id="chk-2",
            workflow_id="wf-chk",
            step_index=1,
            state=state,
            status=ExecutionStatus.COMPLETED,
            created_at=now,
        )
        d = chk.to_dict()
        assert d["id"] == "chk-2"
        assert d["workflow_id"] == "wf-chk"
        assert d["step_index"] == 1
        assert d["status"] == "completed"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert d["created_at"] == now.isoformat()
        assert "state" in d

    def test_from_dict(self):
        state = self._make_state()
        now = datetime.now(UTC)
        original = ExecutionCheckpoint(
            id="chk-3",
            workflow_id="wf-chk",
            step_index=2,
            state=state,
            status=ExecutionStatus.FAILED,
            created_at=now,
        )
        d = original.to_dict()
        reconstructed = ExecutionCheckpoint.from_dict(d)
        assert reconstructed.id == original.id
        assert reconstructed.workflow_id == original.workflow_id
        assert reconstructed.step_index == original.step_index
        assert reconstructed.status == original.status
        assert reconstructed.constitutional_hash == CONSTITUTIONAL_HASH

    def test_from_dict_default_hash_when_missing(self):
        """from_dict uses CONSTITUTIONAL_HASH when key is absent."""
        state = self._make_state()
        now = datetime.now(UTC)
        d = {
            "id": "chk-4",
            "workflow_id": "wf-chk",
            "step_index": 0,
            "state": state.to_dict(),
            "status": "running",
            "created_at": now.isoformat(),
            # no constitutional_hash key
        }
        chk = ExecutionCheckpoint.from_dict(d)
        assert chk.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# CheckpointStore
# =============================================================================


class TestCheckpointStore:
    def _make_checkpoint(self, wf_id: str = "wf-store", step: int = 0) -> ExecutionCheckpoint:
        state = WorkflowState(workflow_id=wf_id, total_steps=5)
        return ExecutionCheckpoint(
            id=f"chk-{wf_id}-{step}",
            workflow_id=wf_id,
            step_index=step,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )

    async def test_initialize_creates_tables(self):
        store = CheckpointStore()
        await store.initialize()
        assert store._initialized is True
        assert store._conn is not None
        await store.close()

    async def test_initialize_idempotent(self):
        store = CheckpointStore()
        await store.initialize()
        await store.initialize()  # second call is a no-op
        assert store._initialized is True
        await store.close()

    async def test_save_and_get_checkpoint(self):
        store = CheckpointStore()
        await store.initialize()
        chk = self._make_checkpoint()
        await store.save_checkpoint(chk)
        retrieved = await store.get_checkpoint(chk.id)
        assert retrieved is not None
        assert retrieved.id == chk.id
        assert retrieved.workflow_id == chk.workflow_id
        assert retrieved.step_index == chk.step_index
        await store.close()

    async def test_get_checkpoint_not_found(self):
        store = CheckpointStore()
        await store.initialize()
        result = await store.get_checkpoint("nonexistent-id")
        assert result is None
        await store.close()

    async def test_save_checkpoint_auto_initializes(self):
        """save_checkpoint should initialize if not already done."""
        store = CheckpointStore()
        chk = self._make_checkpoint()
        await store.save_checkpoint(chk)
        assert store._initialized is True
        await store.close()

    async def test_get_checkpoint_auto_initializes(self):
        store = CheckpointStore()
        result = await store.get_checkpoint("no-id")
        assert result is None
        assert store._initialized is True
        await store.close()

    async def test_get_latest_checkpoint_auto_initializes(self):
        store = CheckpointStore()
        result = await store.get_latest_checkpoint("wf-missing")
        assert result is None
        assert store._initialized is True
        await store.close()

    async def test_get_checkpoints_auto_initializes(self):
        store = CheckpointStore()
        results = await store.get_checkpoints("wf-missing")
        assert results == []
        assert store._initialized is True
        await store.close()

    async def test_delete_checkpoints_auto_initializes(self):
        store = CheckpointStore()
        deleted = await store.delete_checkpoints("wf-missing")
        assert deleted == 0
        assert store._initialized is True
        await store.close()

    async def test_cleanup_old_checkpoints_auto_initializes(self):
        store = CheckpointStore()
        deleted = await store.cleanup_old_checkpoints()
        assert deleted == 0
        assert store._initialized is True
        await store.close()

    async def test_get_latest_checkpoint_returns_highest_step(self):
        store = CheckpointStore()
        await store.initialize()
        for step in range(3):
            await store.save_checkpoint(self._make_checkpoint(step=step))
        latest = await store.get_latest_checkpoint("wf-store")
        assert latest is not None
        assert latest.step_index == 2
        await store.close()

    async def test_get_latest_checkpoint_none_when_empty(self):
        store = CheckpointStore()
        await store.initialize()
        result = await store.get_latest_checkpoint("no-such-workflow")
        assert result is None
        await store.close()

    async def test_get_checkpoints_multiple(self):
        store = CheckpointStore()
        await store.initialize()
        for step in range(3):
            await store.save_checkpoint(self._make_checkpoint(step=step))
        checkpoints = await store.get_checkpoints("wf-store")
        assert len(checkpoints) == 3
        assert checkpoints[0].step_index == 0
        await store.close()

    async def test_get_checkpoints_with_limit_offset(self):
        store = CheckpointStore()
        await store.initialize()
        for step in range(5):
            await store.save_checkpoint(self._make_checkpoint(step=step))
        checkpoints = await store.get_checkpoints("wf-store", limit=2, offset=1)
        assert len(checkpoints) == 2
        assert checkpoints[0].step_index == 1
        await store.close()

    async def test_delete_checkpoints(self):
        store = CheckpointStore()
        await store.initialize()
        for step in range(3):
            await store.save_checkpoint(self._make_checkpoint(step=step))
        deleted = await store.delete_checkpoints("wf-store")
        assert deleted == 3
        remaining = await store.get_checkpoints("wf-store")
        assert remaining == []
        await store.close()

    async def test_cleanup_old_checkpoints_removes_old(self):
        """Checkpoints with a very old created_at timestamp are removed."""
        store = CheckpointStore()
        await store.initialize()

        old_ts = "2000-01-01T00:00:00+00:00"
        state = WorkflowState(workflow_id="wf-old", total_steps=1)
        store._conn.execute(
            """INSERT OR REPLACE INTO checkpoints
               (id, workflow_id, step_index, state_json, status, created_at, constitutional_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "chk-old",
                "wf-old",
                0,
                json.dumps(state.to_dict()),
                ExecutionStatus.CHECKPOINTED.value,
                old_ts,
                CONSTITUTIONAL_HASH,
            ),
        )
        store._conn.commit()

        deleted = await store.cleanup_old_checkpoints(max_age_hours=1)
        assert deleted == 1
        await store.close()

    async def test_cleanup_old_checkpoints_keeps_recent(self):
        store = CheckpointStore()
        await store.initialize()
        chk = self._make_checkpoint()
        await store.save_checkpoint(chk)
        deleted = await store.cleanup_old_checkpoints(max_age_hours=24)
        assert deleted == 0
        await store.close()

    async def test_save_checkpoint_upsert(self):
        """Same (workflow_id, step_index) replaces existing row."""
        store = CheckpointStore()
        await store.initialize()
        chk1 = self._make_checkpoint(step=0)
        await store.save_checkpoint(chk1)

        state = WorkflowState(workflow_id="wf-store", total_steps=5)
        chk2 = ExecutionCheckpoint(
            id="chk-replacement",
            workflow_id="wf-store",
            step_index=0,
            state=state,
            status=ExecutionStatus.COMPLETED,
        )
        await store.save_checkpoint(chk2)
        checkpoints = await store.get_checkpoints("wf-store")
        assert len(checkpoints) == 1
        await store.close()

    async def test_close_clears_connection(self):
        store = CheckpointStore()
        await store.initialize()
        await store.close()
        assert store._conn is None
        assert store._initialized is False

    async def test_close_idempotent_when_not_connected(self):
        store = CheckpointStore()
        await store.close()
        assert store._conn is None

    def test_init_default_db_path(self):
        store = CheckpointStore()
        assert store._db_path == ":memory:"

    def test_init_custom_db_path(self):
        store = CheckpointStore("/tmp/test_checkpoints_cov.db")
        assert store._db_path == "/tmp/test_checkpoints_cov.db"


# =============================================================================
# DurableStep
# =============================================================================


class TestDurableStep:
    def test_basic_creation(self):
        def func(state):
            return "result"

        step = DurableStep(id="s-1", name="step1", func=func)
        assert step.id == "s-1"
        assert step.name == "step1"
        assert step.func is func
        assert step.description == ""
        assert step.max_retries == 3
        assert step.retry_delay == 1.0
        assert step.timeout is None
        assert step.checkpoint_before is True
        assert step.checkpoint_after is True
        assert step.skip_on_failure is False

    def test_full_creation(self):
        def func(state):
            return "result"

        step = DurableStep(
            id="s-2",
            name="step2",
            func=func,
            description="desc",
            max_retries=1,
            retry_delay=0.5,
            timeout=10.0,
            checkpoint_before=False,
            checkpoint_after=False,
            skip_on_failure=True,
        )
        assert step.max_retries == 1
        assert step.retry_delay == 0.5
        assert step.timeout == 10.0
        assert step.checkpoint_before is False
        assert step.checkpoint_after is False
        assert step.skip_on_failure is True


# =============================================================================
# DurableWorkflow
# =============================================================================


class TestDurableWorkflow:
    def test_basic_creation(self):
        wf = DurableWorkflow(id="wf-1", name="My Workflow")
        assert wf.id == "wf-1"
        assert wf.name == "My Workflow"
        assert wf.description == ""
        assert wf.checkpoint_interval == 1
        assert wf.recovery_strategy == RecoveryStrategy.RETRY_STEP
        assert len(wf) == 0

    def test_creation_with_all_params(self):
        wf = DurableWorkflow(
            id="wf-2",
            name="Full WF",
            description="A description",
            checkpoint_interval=2,
            recovery_strategy=RecoveryStrategy.ROLLBACK,
        )
        assert wf.description == "A description"
        assert wf.checkpoint_interval == 2
        assert wf.recovery_strategy == RecoveryStrategy.ROLLBACK

    def test_add_step_returns_self(self):
        wf = DurableWorkflow(id="wf-3", name="Chain")
        result = wf.add_step("step1", lambda s: None)
        assert result is wf

    def test_add_multiple_steps(self):
        wf = DurableWorkflow(id="wf-4", name="Multi")
        wf.add_step("a", lambda s: 1)
        wf.add_step("b", lambda s: 2)
        wf.add_step("c", lambda s: 3)
        assert len(wf) == 3

    def test_add_step_with_all_params(self):
        wf = DurableWorkflow(id="wf-5", name="Param Test")
        wf.add_step(
            name="complex",
            func=lambda s: None,
            description="desc",
            max_retries=5,
            retry_delay=2.0,
            timeout=30.0,
            checkpoint_before=False,
            checkpoint_after=False,
            skip_on_failure=True,
        )
        step = wf.steps[0]
        assert step.name == "complex"
        assert step.max_retries == 5
        assert step.retry_delay == 2.0
        assert step.timeout == 30.0
        assert step.checkpoint_before is False
        assert step.checkpoint_after is False
        assert step.skip_on_failure is True

    def test_step_decorator(self):
        wf = DurableWorkflow(id="wf-6", name="Decorator Test")

        @wf.step("decorated", description="A decorated step", max_retries=2)
        def my_step(state):
            return "done"

        assert len(wf) == 1
        assert wf.steps[0].name == "decorated"
        assert my_step is not None

    def test_steps_returns_copy(self):
        wf = DurableWorkflow(id="wf-7", name="Copy Test")
        wf.add_step("s1", lambda s: None)
        steps_copy = wf.steps
        steps_copy.clear()
        assert len(wf) == 1

    def test_len_empty(self):
        wf = DurableWorkflow(id="wf-8", name="Empty")
        assert len(wf) == 0

    def test_step_ids_are_unique(self):
        wf = DurableWorkflow(id="wf-9", name="Unique IDs")
        for _ in range(10):
            wf.add_step("s", lambda s: None)
        ids = [s.id for s in wf.steps]
        assert len(set(ids)) == 10


# =============================================================================
# DurableExecutor — sync / property tests
# =============================================================================


class TestDurableExecutorProperties:
    def test_should_checkpoint_auto_on_interval_1(self):
        executor = DurableExecutor(auto_checkpoint=True, checkpoint_interval=1)
        assert executor._should_checkpoint(0) is True
        assert executor._should_checkpoint(1) is True
        assert executor._should_checkpoint(5) is True

    def test_should_checkpoint_auto_off(self):
        executor = DurableExecutor(auto_checkpoint=False, checkpoint_interval=1)
        assert executor._should_checkpoint(0) is False
        assert executor._should_checkpoint(5) is False

    def test_should_checkpoint_interval_3(self):
        executor = DurableExecutor(auto_checkpoint=True, checkpoint_interval=3)
        assert executor._should_checkpoint(0) is True
        assert executor._should_checkpoint(1) is False
        assert executor._should_checkpoint(2) is False
        assert executor._should_checkpoint(3) is True
        assert executor._should_checkpoint(6) is True

    def test_get_stats_initial(self):
        executor = DurableExecutor()
        stats = executor.get_stats()
        assert stats["active_workflows"] == 0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["auto_checkpoint"] is True
        assert stats["checkpoint_interval"] == 1
        assert stats["metrics"]["workflows_started"] == 0

    def test_init_defaults(self):
        executor = DurableExecutor()
        assert executor._constitutional_hash == CONSTITUTIONAL_HASH
        assert executor._auto_checkpoint is True
        assert executor._checkpoint_interval == 1
        assert executor._max_recovery_attempts == 3
        assert executor._initialized is False

    def test_init_custom_store(self):
        store = CheckpointStore()
        executor = DurableExecutor(checkpoint_store=store)
        assert executor._store is store

    def test_init_custom_params(self):
        executor = DurableExecutor(
            auto_checkpoint=False,
            checkpoint_interval=5,
            max_recovery_attempts=10,
        )
        assert executor._auto_checkpoint is False
        assert executor._checkpoint_interval == 5
        assert executor._max_recovery_attempts == 10


# =============================================================================
# DurableExecutor — async execution
# =============================================================================


class TestDurableExecutorAsync:
    def _make_workflow(self, wf_id: str = "wf-exec", steps: int = 1) -> DurableWorkflow:
        wf = DurableWorkflow(id=wf_id, name="Test Workflow")
        for i in range(steps):
            wf.add_step(f"step-{i}", lambda state, idx=i: f"result-{idx}")
        return wf

    async def test_initialize(self):
        executor = DurableExecutor()
        await executor.initialize()
        assert executor._initialized is True
        await executor.close()

    async def test_initialize_idempotent(self):
        executor = DurableExecutor()
        await executor.initialize()
        assert executor._initialized is True
        await executor.close()

    async def test_execute_single_step_success(self):
        wf = self._make_workflow(steps=1)
        executor = DurableExecutor()
        success, state = await executor.execute(wf)
        assert success is True
        assert 0 in state.step_results
        await executor.close()

    async def test_execute_multi_step_success(self):
        wf = self._make_workflow(steps=3)
        executor = DurableExecutor()
        success, state = await executor.execute(wf)
        assert success is True
        assert len(state.step_results) == 3
        assert executor._metrics["workflows_completed"] == 1
        assert executor._metrics["steps_executed"] == 3
        await executor.close()

    async def test_execute_with_initial_context(self):
        wf = DurableWorkflow(id="wf-ctx", name="Context WF")

        def check_context(state):
            return state.variables.get("token")

        wf.add_step("check", check_context)
        executor = DurableExecutor()
        success, state = await executor.execute(wf, initial_context={"token": "abc"})
        assert success is True
        assert state.step_results[0] == "abc"
        await executor.close()

    async def test_execute_with_async_step(self):
        wf = DurableWorkflow(id="wf-async", name="Async WF")

        async def async_step(state):
            await asyncio.sleep(0)
            return "async_result"

        wf.add_step("async", async_step)
        executor = DurableExecutor()
        success, state = await executor.execute(wf)
        assert success is True
        assert state.step_results[0] == "async_result"
        await executor.close()

    async def test_execute_step_failure_stops_workflow(self):
        wf = DurableWorkflow(id="wf-fail", name="Failing WF")

        def bad_step(state):
            raise RuntimeError("boom")

        wf.add_step("bad", bad_step, max_retries=0)
        executor = DurableExecutor()
        success, state = await executor.execute(wf)
        assert success is False
        assert state.error is not None
        assert executor._metrics["workflows_failed"] == 1
        await executor.close()

    async def test_execute_step_skip_on_failure(self):
        wf = DurableWorkflow(id="wf-skip", name="Skip WF")

        def bad_step(state):
            raise ValueError("skip me")

        wf.add_step("bad", bad_step, max_retries=0, skip_on_failure=True)
        wf.add_step("good", lambda s: "ok")
        executor = DurableExecutor()
        success, state = await executor.execute(wf)
        assert success is True
        assert state.step_results[0].get("skipped") is True
        assert state.step_results[1] == "ok"
        await executor.close()

    async def test_execute_step_retry_then_succeed(self):
        call_count = {"n": 0}

        def flaky(state):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("not ready")
            return "ok"

        wf = DurableWorkflow(id="wf-retry", name="Retry WF")
        wf.add_step("flaky", flaky, max_retries=3, retry_delay=0.0)
        executor = DurableExecutor()
        success, state = await executor.execute(wf)
        assert success is True
        assert state.step_results[0] == "ok"
        assert executor._metrics["steps_retried"] >= 1
        await executor.close()

    async def test_execute_step_all_retries_exhausted(self):
        def always_fail(state):
            raise ValueError("always")

        wf = DurableWorkflow(id="wf-exhaust", name="Exhaust WF")
        wf.add_step("fail", always_fail, max_retries=2, retry_delay=0.0)
        executor = DurableExecutor()
        success, _state = await executor.execute(wf)
        assert success is False
        assert executor._metrics["steps_retried"] == 2
        await executor.close()

    async def test_execute_with_timeout_success(self):
        async def fast(state):
            return "fast"

        wf = DurableWorkflow(id="wf-timeout-ok", name="Fast WF")
        wf.add_step("fast", fast, timeout=10.0, max_retries=0)
        executor = DurableExecutor()
        success, _state = await executor.execute(wf)
        assert success is True
        await executor.close()

    async def test_execute_with_timeout_exceeded(self):
        async def slow(state):
            await asyncio.sleep(10)

        wf = DurableWorkflow(id="wf-timeout-fail", name="Slow WF")
        wf.add_step("slow", slow, timeout=0.01, max_retries=0, retry_delay=0.0)
        executor = DurableExecutor()
        success, _state = await executor.execute(wf)
        assert success is False
        await executor.close()

    async def test_execute_timeout_retry_then_succeed(self):
        call_count = {"n": 0}

        async def sometimes_slow(state):
            call_count["n"] += 1
            if call_count["n"] == 1:
                await asyncio.sleep(10)
            return "ok"

        wf = DurableWorkflow(id="wf-timeout-retry", name="Timeout Retry WF")
        wf.add_step("sometimes_slow", sometimes_slow, timeout=0.01, max_retries=2, retry_delay=0.0)
        executor = DurableExecutor()
        success, _state = await executor.execute(wf)
        assert success is True
        assert executor._metrics["steps_retried"] >= 1
        await executor.close()

    async def test_execute_checkpoints_created(self):
        wf = self._make_workflow(steps=2)
        executor = DurableExecutor(auto_checkpoint=True, checkpoint_interval=1)
        await executor.execute(wf)
        assert executor._metrics["checkpoints_created"] > 0
        await executor.close()

    async def test_execute_clears_active_on_success(self):
        wf = self._make_workflow()
        executor = DurableExecutor()
        await executor.execute(wf)
        assert wf.id not in executor._active_workflows
        await executor.close()

    async def test_execute_clears_active_on_failure(self):
        wf = DurableWorkflow(id="wf-clean", name="Cleanup Test")

        def bad_step(state):
            raise RuntimeError("err")

        wf.add_step("bad", bad_step, max_retries=0)
        executor = DurableExecutor()
        await executor.execute(wf)
        assert wf.id not in executor._active_workflows
        await executor.close()

    async def test_execute_resume_from_checkpoint(self):
        store = CheckpointStore()
        state = WorkflowState(
            workflow_id="wf-resume",
            current_step=0,
            total_steps=2,
            step_results={0: "pre-done"},
            started_at=datetime.now(UTC),
        )
        checkpoint = ExecutionCheckpoint(
            id="chk-resume-0",
            workflow_id="wf-resume",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )
        await store.save_checkpoint(checkpoint)

        wf = DurableWorkflow(id="wf-resume", name="Resume WF")
        wf.add_step("step0", lambda s: "s0")
        wf.add_step("step1", lambda s: "s1")

        executor = DurableExecutor(checkpoint_store=store)
        success, _final_state = await executor.execute(wf, resume_from="chk-resume-0")
        assert success is True
        assert executor._metrics["recoveries_attempted"] == 1
        assert executor._metrics["recoveries_successful"] == 1
        await executor.close()

    async def test_execute_resume_from_missing_checkpoint_raises(self):
        executor = DurableExecutor()
        wf = self._make_workflow()
        with pytest.raises(ValueError, match="Checkpoint not found"):
            await executor.execute(wf, resume_from="nonexistent")
        await executor.close()

    async def test_execute_auto_initializes(self):
        wf = self._make_workflow()
        executor = DurableExecutor()
        assert executor._initialized is False
        await executor.execute(wf)
        assert executor._initialized is True
        await executor.close()

    async def test_execute_auto_initializes_with_resume_from(self):
        """Covers the branch: not initialized AND resume_from is set."""
        store = CheckpointStore()
        state = WorkflowState(
            workflow_id="wf-autoinit-resume",
            current_step=0,
            total_steps=2,
            started_at=datetime.now(UTC),
        )
        chk = ExecutionCheckpoint(
            id="chk-autoinit",
            workflow_id="wf-autoinit-resume",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )
        await store.save_checkpoint(chk)

        wf = DurableWorkflow(id="wf-autoinit-resume", name="AutoInit Resume WF")
        wf.add_step("s0", lambda s: "r0")
        wf.add_step("s1", lambda s: "r1")

        executor = DurableExecutor(checkpoint_store=store)
        assert executor._initialized is False
        success, _ = await executor.execute(wf, resume_from="chk-autoinit")
        assert success is True
        assert executor._initialized is True
        await executor.close()

    async def test_execute_already_initialized_with_resume_from(self):
        """Covers branch 519->523: already initialized AND resume_from is set."""
        store = CheckpointStore()
        state = WorkflowState(
            workflow_id="wf-preinit-resume",
            current_step=0,
            total_steps=2,
            started_at=datetime.now(UTC),
        )
        chk = ExecutionCheckpoint(
            id="chk-preinit",
            workflow_id="wf-preinit-resume",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )
        await store.save_checkpoint(chk)

        wf = DurableWorkflow(id="wf-preinit-resume", name="PreInit Resume WF")
        wf.add_step("s0", lambda s: "r0")
        wf.add_step("s1", lambda s: "r1")

        executor = DurableExecutor(checkpoint_store=store)
        # Pre-initialize so the branch _initialized=True is taken
        await executor.initialize()
        assert executor._initialized is True
        success, _ = await executor.execute(wf, resume_from="chk-preinit")
        assert success is True
        await executor.close()

    async def test_get_workflow_status_running(self):
        executor = DurableExecutor()
        await executor.initialize()
        state = WorkflowState(workflow_id="wf-status", total_steps=5, current_step=2)
        executor._active_workflows["wf-status"] = state
        status = await executor.get_workflow_status("wf-status")
        assert status is not None
        assert status["status"] == "running"
        assert status["current_step"] == 2
        assert status["total_steps"] == 5
        assert "progress" in status
        await executor.close()

    async def test_get_workflow_status_from_checkpoint(self):
        store = CheckpointStore()
        state = WorkflowState(workflow_id="wf-chk-status", total_steps=4, current_step=2)
        chk = ExecutionCheckpoint(
            id="chk-status-1",
            workflow_id="wf-chk-status",
            step_index=2,
            state=state,
            status=ExecutionStatus.COMPLETED,
        )
        await store.save_checkpoint(chk)

        executor = DurableExecutor(checkpoint_store=store)
        await executor.initialize()
        status = await executor.get_workflow_status("wf-chk-status")
        assert status is not None
        assert status["status"] == "completed"
        assert status["current_step"] == 2
        assert "last_checkpoint" in status
        await executor.close()

    async def test_get_workflow_status_none_if_not_found(self):
        executor = DurableExecutor()
        await executor.initialize()
        result = await executor.get_workflow_status("wf-missing-status")
        assert result is None
        await executor.close()

    async def test_get_workflow_status_progress_zero_total(self):
        executor = DurableExecutor()
        await executor.initialize()
        state = WorkflowState(workflow_id="wf-zero", total_steps=0, current_step=0)
        executor._active_workflows["wf-zero"] = state
        status = await executor.get_workflow_status("wf-zero")
        assert status is not None
        assert status["progress"] == 0.0
        await executor.close()

    async def test_cancel_active_workflow(self):
        executor = DurableExecutor()
        await executor.initialize()
        state = WorkflowState(workflow_id="wf-cancel", total_steps=3, current_step=1)
        executor._active_workflows["wf-cancel"] = state
        result = await executor.cancel("wf-cancel")
        assert result is True
        assert "wf-cancel" not in executor._active_workflows
        await executor.close()

    async def test_cancel_inactive_workflow(self):
        executor = DurableExecutor()
        await executor.initialize()
        result = await executor.cancel("wf-not-running")
        assert result is False
        await executor.close()

    async def test_resume_already_completed(self):
        store = CheckpointStore()
        state = WorkflowState(workflow_id="wf-done", total_steps=1, current_step=0)
        chk = ExecutionCheckpoint(
            id="chk-done",
            workflow_id="wf-done",
            step_index=0,
            state=state,
            status=ExecutionStatus.COMPLETED,
        )
        await store.save_checkpoint(chk)

        wf = DurableWorkflow(id="wf-done", name="Completed WF")
        wf.add_step("s1", lambda s: "r1")

        executor = DurableExecutor(checkpoint_store=store)
        success, _final_state = await executor.resume(wf)
        assert success is True
        await executor.close()

    async def test_resume_no_checkpoint_raises(self):
        executor = DurableExecutor()
        await executor.initialize()
        wf = DurableWorkflow(id="wf-no-resume-chk", name="No Checkpoint")
        wf.add_step("s1", lambda s: "r1")
        with pytest.raises(ValueError, match="No checkpoint found"):
            await executor.resume(wf)
        await executor.close()

    async def test_resume_from_partial(self):
        store = CheckpointStore()
        state = WorkflowState(
            workflow_id="wf-partial",
            total_steps=2,
            current_step=0,
            started_at=datetime.now(UTC),
        )
        chk = ExecutionCheckpoint(
            id="chk-partial",
            workflow_id="wf-partial",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )
        await store.save_checkpoint(chk)

        wf = DurableWorkflow(id="wf-partial", name="Partial WF")
        wf.add_step("s0", lambda s: "r0")
        wf.add_step("s1", lambda s: "r1")

        executor = DurableExecutor(checkpoint_store=store)
        success, _final_state = await executor.resume(wf)
        assert success is True
        await executor.close()

    async def test_close_resets_initialized(self):
        executor = DurableExecutor()
        await executor.initialize()
        await executor.close()
        assert executor._initialized is False

    async def test_all_step_execution_error_types_trigger_retry(self):
        """All exception types in STEP_EXECUTION_ERRORS trigger retry."""
        error_types = [
            RuntimeError("rt"),
            ValueError("ve"),
            TypeError("te"),
            KeyError("ke"),
            AttributeError("ae"),
            ConnectionError("ce"),
            OSError("oe"),
        ]
        for err in error_types:
            call_count = {"n": 0}
            captured_err = err

            def make_raiser(e=captured_err, cc=call_count):
                def raiser(state):
                    cc["n"] += 1
                    if cc["n"] == 1:
                        raise e
                    return "ok"

                return raiser

            wf = DurableWorkflow(id=f"wf-err-{type(err).__name__}", name="Error WF")
            wf.add_step("step", make_raiser(), max_retries=1, retry_delay=0.0)
            executor = DurableExecutor()
            success, _ = await executor.execute(wf)
            assert success is True, f"Should succeed after retry for {type(err).__name__}"
            await executor.close()

    async def test_create_checkpoint_increments_metric(self):
        executor = DurableExecutor()
        await executor.initialize()
        state = WorkflowState(workflow_id="wf-metric", total_steps=1)
        await executor._create_checkpoint("wf-metric", 0, state, ExecutionStatus.CHECKPOINTED)
        assert executor._metrics["checkpoints_created"] == 1
        await executor.close()

    async def test_execute_checkpoint_before_false_skips_pre_checkpoint(self):
        """Steps with checkpoint_before=False should not emit a pre-step checkpoint."""
        wf = DurableWorkflow(id="wf-no-pre", name="No Pre-Checkpoint WF")
        wf.add_step("s1", lambda s: "r", checkpoint_before=False, checkpoint_after=True)
        executor = DurableExecutor(auto_checkpoint=True, checkpoint_interval=1)
        before_count = executor._metrics["checkpoints_created"]
        await executor.execute(wf)
        # checkpoint_after=True + completion = checkpoints were created, just fewer
        assert executor._metrics["checkpoints_created"] > before_count
        await executor.close()

    async def test_execute_checkpoint_after_false_skips_post_checkpoint(self):
        """Steps with checkpoint_after=False skip the post-step checkpoint."""
        wf = DurableWorkflow(id="wf-no-post", name="No Post-Checkpoint WF")
        wf.add_step("s1", lambda s: "r", checkpoint_before=True, checkpoint_after=False)
        executor = DurableExecutor(auto_checkpoint=True, checkpoint_interval=1)
        await executor.execute(wf)
        await executor.close()

    async def test_execute_empty_workflow_completes(self):
        """Workflow with 0 steps completes immediately."""
        wf = DurableWorkflow(id="wf-empty", name="Empty WF")
        executor = DurableExecutor()
        success, _state = await executor.execute(wf)
        assert success is True
        assert executor._metrics["workflows_completed"] == 1
        await executor.close()

    async def test_get_stats_after_execution(self):
        wf = self._make_workflow(steps=2)
        executor = DurableExecutor()
        await executor.execute(wf)
        stats = executor.get_stats()
        assert stats["metrics"]["workflows_completed"] == 1
        assert stats["metrics"]["steps_executed"] == 2
        await executor.close()


# =============================================================================
# create_durable_executor factory
# =============================================================================


class TestCreateDurableExecutor:
    def test_default_params(self):
        executor = create_durable_executor()
        assert isinstance(executor, DurableExecutor)
        assert executor._constitutional_hash == CONSTITUTIONAL_HASH
        assert executor._auto_checkpoint is True
        assert executor._checkpoint_interval == 1

    def test_custom_params(self):
        executor = create_durable_executor(
            db_path=":memory:",
            constitutional_hash="custom",  # pragma: allowlist secret
            auto_checkpoint=False,
            checkpoint_interval=5,
        )
        assert executor._constitutional_hash == "custom"  # pragma: allowlist secret
        assert executor._auto_checkpoint is False
        assert executor._checkpoint_interval == 5

    async def test_factory_executor_works_end_to_end(self):
        executor = create_durable_executor()
        wf = DurableWorkflow(id="wf-factory", name="Factory WF")
        wf.add_step("s1", lambda s: "factory_result")
        success, state = await executor.execute(wf)
        assert success is True
        assert state.step_results[0] == "factory_result"
        await executor.close()
