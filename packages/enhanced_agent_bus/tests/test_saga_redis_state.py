"""Tests for saga_persistence.redis.state.RedisStateManager."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.saga_persistence.models import (
    CompensationEntry,
    PersistedSagaState,
    PersistedStepSnapshot,
    SagaCheckpoint,
    SagaState,
    StepState,
)
from enhanced_agent_bus.saga_persistence.redis.state import (
    VALID_STATE_TRANSITIONS,
    RedisStateManager,
)
from enhanced_agent_bus.saga_persistence.repository import (
    InvalidStateTransitionError,
    RepositoryError,
)

# ---------------------------------------------------------------------------
# Concrete subclass that fulfils the mixin's abstract interface
# ---------------------------------------------------------------------------


class ConcreteStateManager(RedisStateManager):
    """Testable subclass providing the required abstract methods."""

    def __init__(self, redis_client, saga_store=None):
        self._redis = redis_client
        self._saga_store = saga_store or {}
        self._ttl = 86400

    def _get_ttl_seconds(self) -> int:
        return self._ttl

    async def get(self, saga_id: str) -> PersistedSagaState | None:
        return self._saga_store.get(saga_id)

    async def exists(self, saga_id: str) -> bool:
        return saga_id in self._saga_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_saga(
    saga_id="saga-1",
    state=SagaState.INITIALIZED,
    version=1,
    started_at=None,
    steps=None,
) -> PersistedSagaState:
    return PersistedSagaState(
        saga_id=saga_id,
        saga_name="test-saga",
        tenant_id="t1",
        state=state,
        version=version,
        started_at=started_at,
        steps=steps or [],
    )


def _saga_to_redis_hash(saga: PersistedSagaState) -> dict[str, str]:
    return saga.to_redis_hash()


@pytest.fixture()
def mock_redis():
    r = AsyncMock()
    # pipeline() is synchronous in redis.asyncio, returns a Pipeline object
    # whose methods (hset, sadd, etc.) are sync, only execute() is async
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[])
    # Make pipeline() a regular function returning the sync pipe object
    r.pipeline = MagicMock(return_value=pipe)
    return r


@pytest.fixture()
def manager(mock_redis) -> ConcreteStateManager:
    return ConcreteStateManager(redis_client=mock_redis)


# ---------------------------------------------------------------------------
# VALID_STATE_TRANSITIONS
# ---------------------------------------------------------------------------


class TestStateTransitions:
    def test_initialized_can_go_to_running(self):
        assert SagaState.RUNNING in VALID_STATE_TRANSITIONS[SagaState.INITIALIZED]

    def test_initialized_can_go_to_failed(self):
        assert SagaState.FAILED in VALID_STATE_TRANSITIONS[SagaState.INITIALIZED]

    def test_running_transitions(self):
        valid = VALID_STATE_TRANSITIONS[SagaState.RUNNING]
        assert SagaState.COMPLETED in valid
        assert SagaState.COMPENSATING in valid
        assert SagaState.FAILED in valid

    def test_terminal_states_have_no_transitions(self):
        for state in (SagaState.COMPLETED, SagaState.COMPENSATED, SagaState.FAILED):
            assert VALID_STATE_TRANSITIONS[state] == set()


# ---------------------------------------------------------------------------
# update_state
# ---------------------------------------------------------------------------


class TestUpdateState:
    @pytest.mark.asyncio
    async def test_valid_transition(self, manager, mock_redis):
        saga = _make_saga(state=SagaState.INITIALIZED)
        mock_redis.hgetall.return_value = _saga_to_redis_hash(saga)

        result = await manager.update_state("saga-1", SagaState.RUNNING)
        assert result is True

        pipe = mock_redis.pipeline.return_value
        pipe.hset.assert_called_once()
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_saga_not_found(self, manager, mock_redis):
        mock_redis.hgetall.return_value = {}
        result = await manager.update_state("nope", SagaState.RUNNING)
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, manager, mock_redis):
        saga = _make_saga(state=SagaState.COMPLETED)
        mock_redis.hgetall.return_value = _saga_to_redis_hash(saga)

        with pytest.raises(InvalidStateTransitionError):
            await manager.update_state("saga-1", SagaState.RUNNING)

    @pytest.mark.asyncio
    async def test_failed_state_records_reason(self, manager, mock_redis):
        saga = _make_saga(state=SagaState.INITIALIZED)
        mock_redis.hgetall.return_value = _saga_to_redis_hash(saga)

        await manager.update_state("saga-1", SagaState.FAILED, failure_reason="timeout")

        pipe = mock_redis.pipeline.return_value
        mapping = pipe.hset.call_args[1]["mapping"]
        assert mapping["failure_reason"] == "timeout"
        assert mapping["state"] == "FAILED"

    @pytest.mark.asyncio
    async def test_completed_state_records_duration(self, manager, mock_redis):
        saga = _make_saga(
            state=SagaState.RUNNING,
            started_at=datetime.now(UTC),
        )
        mock_redis.hgetall.return_value = _saga_to_redis_hash(saga)

        await manager.update_state("saga-1", SagaState.COMPLETED)

        pipe = mock_redis.pipeline.return_value
        mapping = pipe.hset.call_args[1]["mapping"]
        assert "completed_at" in mapping
        assert "total_duration_ms" in mapping

    @pytest.mark.asyncio
    async def test_redis_error_raises_repository_error(self, manager, mock_redis):
        import redis.asyncio as aioredis

        mock_redis.hgetall.side_effect = aioredis.RedisError("conn failed")

        with pytest.raises(RepositoryError):
            await manager.update_state("saga-1", SagaState.RUNNING)


# ---------------------------------------------------------------------------
# update_step_state
# ---------------------------------------------------------------------------


class TestUpdateStepState:
    @pytest.mark.asyncio
    async def test_update_existing_step(self, manager, mock_redis):
        step = PersistedStepSnapshot(step_id="step-1", step_name="do_thing", step_index=0)
        saga = _make_saga(steps=[step])
        manager._saga_store["saga-1"] = saga

        result = await manager.update_step_state("saga-1", "step-1", StepState.RUNNING)
        assert result is True
        mock_redis.hset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_nonexistent_saga(self, manager, mock_redis):
        result = await manager.update_step_state("nope", "step-1", StepState.RUNNING)
        assert result is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_step(self, manager, mock_redis):
        saga = _make_saga(steps=[])
        manager._saga_store["saga-1"] = saga

        result = await manager.update_step_state("saga-1", "no-step", StepState.RUNNING)
        assert result is False

    @pytest.mark.asyncio
    async def test_step_completed_sets_completed_at(self, manager, mock_redis):
        step = PersistedStepSnapshot(
            step_id="step-1",
            step_name="do_thing",
            step_index=0,
            started_at=datetime.now(UTC),
        )
        saga = _make_saga(steps=[step])
        manager._saga_store["saga-1"] = saga

        await manager.update_step_state("saga-1", "step-1", StepState.COMPLETED)
        call_mapping = mock_redis.hset.call_args[1]["mapping"]
        steps_data = json.loads(call_mapping["steps"])
        assert steps_data[0]["state"] == "COMPLETED"
        assert steps_data[0]["completed_at"] is not None


# ---------------------------------------------------------------------------
# update_current_step
# ---------------------------------------------------------------------------


class TestUpdateCurrentStep:
    @pytest.mark.asyncio
    async def test_update_success(self, manager, mock_redis):
        mock_redis.exists.return_value = True
        result = await manager.update_current_step("saga-1", 3)
        assert result is True
        mock_redis.hset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_saga_not_found(self, manager, mock_redis):
        mock_redis.exists.return_value = False
        result = await manager.update_current_step("nope", 0)
        assert result is False


# ---------------------------------------------------------------------------
# save_checkpoint / get_checkpoints / delete_checkpoints
# ---------------------------------------------------------------------------


class TestCheckpoints:
    @pytest.mark.asyncio
    async def test_save_checkpoint(self, manager, mock_redis):
        cp = SagaCheckpoint(
            checkpoint_id="cp-1",
            saga_id="saga-1",
            checkpoint_name="before_commit",
        )
        result = await manager.save_checkpoint(cp)
        assert result is True

        pipe = mock_redis.pipeline.return_value
        pipe.setex.assert_called_once()
        pipe.zadd.assert_called_once()
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_checkpoints_empty(self, manager, mock_redis):
        mock_redis.zrevrange.return_value = []
        result = await manager.get_checkpoints("saga-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_checkpoints_returns_data(self, manager, mock_redis):
        cp = SagaCheckpoint(
            checkpoint_id="cp-1",
            saga_id="saga-1",
            checkpoint_name="test",
        )
        mock_redis.zrevrange.return_value = [b"cp-1"]
        mock_redis.get.return_value = json.dumps(cp.to_dict()).encode()

        result = await manager.get_checkpoints("saga-1")
        assert len(result) == 1
        assert result[0].checkpoint_id == "cp-1"

    @pytest.mark.asyncio
    async def test_get_latest_checkpoint_none(self, manager, mock_redis):
        mock_redis.zrevrange.return_value = []
        result = await manager.get_latest_checkpoint("saga-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_checkpoint(self, manager, mock_redis):
        cp = SagaCheckpoint(checkpoint_id="cp-latest", saga_id="saga-1")
        mock_redis.zrevrange.return_value = [b"cp-latest"]
        mock_redis.get.return_value = json.dumps(cp.to_dict()).encode()

        result = await manager.get_latest_checkpoint("saga-1")
        assert result is not None
        assert result.checkpoint_id == "cp-latest"

    @pytest.mark.asyncio
    async def test_delete_checkpoints_empty(self, manager, mock_redis):
        mock_redis.zrange.return_value = []
        count = await manager.delete_checkpoints("saga-1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_checkpoints(self, manager, mock_redis):
        mock_redis.zrange.return_value = [b"cp-1", b"cp-2"]

        count = await manager.delete_checkpoints("saga-1")
        assert count == 2

        pipe = mock_redis.pipeline.return_value
        # 2 checkpoint deletes + 1 list delete
        assert pipe.delete.call_count == 3
        pipe.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# Compensation log
# ---------------------------------------------------------------------------


class TestCompensationLog:
    @pytest.mark.asyncio
    async def test_append_compensation_entry(self, manager, mock_redis):
        manager._saga_store["saga-1"] = _make_saga()
        entry = CompensationEntry(
            compensation_id="comp-1",
            step_id="step-1",
            step_name="rollback",
            executed=True,
        )
        result = await manager.append_compensation_entry("saga-1", entry)
        assert result is True

        pipe = mock_redis.pipeline.return_value
        pipe.lpush.assert_called_once()
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_append_nonexistent_saga(self, manager, mock_redis):
        entry = CompensationEntry(step_id="s1")
        result = await manager.append_compensation_entry("nope", entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_compensation_log_empty(self, manager, mock_redis):
        mock_redis.lrange.return_value = []
        result = await manager.get_compensation_log("saga-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_compensation_log(self, manager, mock_redis):
        entry = CompensationEntry(
            compensation_id="comp-1",
            step_id="step-1",
            step_name="rollback",
        )
        mock_redis.lrange.return_value = [json.dumps(entry.to_dict()).encode()]

        result = await manager.get_compensation_log("saga-1")
        assert len(result) == 1
        assert result[0].compensation_id == "comp-1"

    @pytest.mark.asyncio
    async def test_redis_error_on_get_log(self, manager, mock_redis):
        import redis.asyncio as aioredis

        mock_redis.lrange.side_effect = aioredis.RedisError("fail")

        with pytest.raises(RepositoryError):
            await manager.get_compensation_log("saga-1")
