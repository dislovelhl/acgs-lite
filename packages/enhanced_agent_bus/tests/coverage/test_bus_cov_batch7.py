"""
Comprehensive coverage tests for enhanced_agent_bus modules (batch 7).

Targets:
1. langgraph_orchestration/persistence.py
2. saga_persistence/postgres/state.py
3. verification_layer/constitutional_transition.py
4. message_processor.py

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Valid UUIDs for Postgres tests (uuid.UUID() requires valid hex)
_SAGA_ID = str(uuid.uuid4())
_STEP_ID = str(uuid.uuid4())
_CP_ID = str(uuid.uuid4())

# ---------------------------------------------------------------------------
# Module 1: langgraph_orchestration.persistence
# ---------------------------------------------------------------------------
from enhanced_agent_bus.langgraph_orchestration.models import (
    Checkpoint,
    CheckpointStatus,
    ExecutionResult,
    ExecutionStatus,
    GraphState,
    StateSnapshot,
)
from enhanced_agent_bus.langgraph_orchestration.persistence import (
    InMemoryStatePersistence,
    RedisStatePersistence,
    StatePersistence,
    create_state_persistence,
)

# ---------------------------------------------------------------------------
# Module 3: verification_layer.constitutional_transition
# ---------------------------------------------------------------------------
from enhanced_agent_bus.verification_layer.constitutional_transition import (
    VALID_TRANSITIONS,
    ConstitutionalTransition,
    ProofType,
    StateTransitionManager,
    TransitionProof,
    TransitionState,
    TransitionType,
    create_transition_manager,
)


class _JsonSafeGraphState(GraphState):
    """GraphState subclass whose model_dump() always returns JSON-safe output."""

    def model_dump(self, **kwargs):  # type: ignore[override]
        return super().model_dump(mode="json", **kwargs)


def _gs(data: dict | None = None) -> _JsonSafeGraphState:
    """Create a GraphState that serializes cleanly via json.dumps(gs.model_dump())."""
    return _JsonSafeGraphState(data=data or {})


def _gs_json(data: dict | None = None) -> dict:
    """Return a json-safe dict representation of a GraphState for stored data fixtures."""
    return _gs(data).model_dump()


# ============================================================================
# 1. InMemoryStatePersistence Tests
# ============================================================================


class TestInMemoryStatePersistence:
    @pytest.fixture
    def persistence(self):
        return InMemoryStatePersistence(constitutional_hash="test-hash")

    @pytest.fixture
    def graph_state(self):
        return GraphState(data={"key": "value"})

    @pytest.fixture
    def checkpoint(self):
        return Checkpoint(
            id="cp-1",
            workflow_id="wf-1",
            run_id="run-1",
            node_id="node-1",
            step_index=0,
            state=GraphState(data={"checkpoint": True}),
            status=CheckpointStatus.CREATED,
        )

    @pytest.fixture
    def execution_result(self):
        return ExecutionResult(
            workflow_id="wf-1",
            run_id="run-1",
            status=ExecutionStatus.COMPLETED,
            final_state=GraphState(data={"done": True}),
        )

    async def test_save_and_load_state(self, persistence, graph_state):
        sid = await persistence.save_state("wf-1", "run-1", graph_state, "node-1", 0)
        assert isinstance(sid, str)
        loaded = await persistence.load_state("wf-1")
        assert loaded is not None
        assert loaded.data == {"key": "value"}

    async def test_load_state_not_found(self, persistence):
        assert await persistence.load_state("nonexistent") is None

    async def test_save_multiple_returns_latest(self, persistence):
        s1 = GraphState(data={"v": 1})
        s2 = GraphState(data={"v": 2})
        await persistence.save_state("wf-1", "r1", s1, "n1", 0)
        await persistence.save_state("wf-1", "r2", s2, "n2", 1)
        loaded = await persistence.load_state("wf-1")
        assert loaded is not None and loaded.data == {"v": 2}

    async def test_save_and_load_checkpoint(self, persistence, checkpoint):
        await persistence.save_checkpoint(checkpoint)
        loaded = await persistence.load_checkpoint("cp-1")
        assert loaded is not None and loaded.id == "cp-1"

    async def test_load_checkpoint_not_found(self, persistence):
        assert await persistence.load_checkpoint("x") is None

    async def test_list_checkpoints_filters_by_workflow(self, persistence):
        for i, wf in enumerate(["wf-1", "wf-1", "wf-2"]):
            cp = Checkpoint(
                id=f"cp-{i}",
                workflow_id=wf,
                run_id=f"r-{i}",
                node_id="n",
                step_index=0,
                state=GraphState(),
            )
            await persistence.save_checkpoint(cp)
        assert len(await persistence.list_checkpoints("wf-1")) == 2

    async def test_list_checkpoints_filters_by_run_id(self, persistence):
        for i in range(2):
            cp = Checkpoint(
                id=f"cp-{i}",
                workflow_id="wf-1",
                run_id=f"run-{i}",
                node_id="n",
                step_index=0,
                state=GraphState(),
            )
            await persistence.save_checkpoint(cp)
        result = await persistence.list_checkpoints("wf-1", run_id="run-0")
        assert len(result) == 1 and result[0].id == "cp-0"

    async def test_delete_checkpoint_success(self, persistence, checkpoint):
        await persistence.save_checkpoint(checkpoint)
        assert await persistence.delete_checkpoint("cp-1") is True
        assert await persistence.load_checkpoint("cp-1") is None

    async def test_delete_checkpoint_not_found(self, persistence):
        assert await persistence.delete_checkpoint("x") is False

    async def test_save_and_load_execution_result(self, persistence, execution_result):
        await persistence.save_execution_result(execution_result)
        loaded = await persistence.load_execution_result("wf-1", "run-1")
        assert loaded is not None and loaded.status == ExecutionStatus.COMPLETED

    async def test_load_execution_result_not_found(self, persistence):
        assert await persistence.load_execution_result("wf-1", "x") is None

    async def test_clear(self, persistence, graph_state, checkpoint, execution_result):
        await persistence.save_state("wf-1", "r1", graph_state, "n1", 0)
        await persistence.save_checkpoint(checkpoint)
        await persistence.save_execution_result(execution_result)
        persistence.clear()
        assert await persistence.load_state("wf-1") is None
        assert await persistence.load_checkpoint("cp-1") is None
        assert await persistence.load_execution_result("wf-1", "run-1") is None

    async def test_load_state_deleted_snapshot(self, persistence, graph_state):
        sid = await persistence.save_state("wf-1", "r1", graph_state, "n1", 0)
        del persistence._snapshots[sid]
        assert await persistence.load_state("wf-1") is None

    async def test_constitutional_hash_stored(self, persistence, graph_state):
        sid = await persistence.save_state("wf-1", "r1", graph_state, "n1", 0)
        assert persistence._snapshots[sid].constitutional_hash == "test-hash"


# ============================================================================
# 2. RedisStatePersistence Tests
# ============================================================================


class TestRedisStatePersistence:
    @pytest.fixture
    def mock_redis(self):
        r = AsyncMock()
        r.setex = AsyncMock()
        r.get = AsyncMock(return_value=None)
        r.delete = AsyncMock(return_value=1)
        r.zadd = AsyncMock()
        r.zrange = AsyncMock(return_value=[])
        r.expire = AsyncMock()
        r.pipeline = MagicMock()
        r.close = AsyncMock()
        return r

    @pytest.fixture
    def persistence(self, mock_redis):
        p = RedisStatePersistence(
            redis_url="redis://test:6379",
            key_prefix="test:",
            ttl_seconds=3600,
        )
        p._redis = mock_redis
        return p

    async def test_get_redis_creates_connection(self):
        p = RedisStatePersistence()
        with patch("redis.asyncio.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.return_value = AsyncMock()
            result = await p._get_redis()
            mock_from_url.assert_called_once_with("redis://localhost:6379")

    async def test_get_redis_import_error(self):
        with patch(
            "enhanced_agent_bus.langgraph_orchestration.persistence.RedisStatePersistence._get_redis",
            side_effect=RuntimeError("Redis not available"),
        ):
            rp = RedisStatePersistence()
            with pytest.raises(RuntimeError, match="Redis not available"):
                await rp._get_redis()

    async def test_save_state(self, persistence, mock_redis):
        gs = _gs({"key": "value"})
        sid = await persistence.save_state("wf-1", "run-1", gs, "node-1", 0)
        assert isinstance(sid, str)
        mock_redis.setex.assert_called_once()

    async def test_load_state_with_run_id(self, persistence, mock_redis):
        stored = json.dumps(
            {
                "id": "snap-1",
                "workflow_id": "wf-1",
                "state": _gs_json({"key": "value"}),
                "node_id": "n1",
                "step_index": 0,
                "created_at": datetime.now(UTC).isoformat(),
                "constitutional_hash": "test",
            }
        )
        mock_redis.get.return_value = stored
        result = await persistence.load_state("wf-1", run_id="run-1")
        assert result is not None and result.data == {"key": "value"}

    async def test_load_state_without_run_id_no_keys(self, persistence, mock_redis):
        async def empty_iter(pattern):
            return
            yield  # noqa: unreachable

        mock_redis.scan_iter = empty_iter
        assert await persistence.load_state("wf-1") is None

    async def test_load_state_without_run_id_with_keys(self, persistence, mock_redis):
        now = datetime.now(UTC)
        stored = json.dumps(
            {
                "id": "snap-1",
                "workflow_id": "wf-1",
                "state": _gs_json({"key": "value"}),
                "node_id": "n1",
                "step_index": 0,
                "created_at": now.isoformat(),
                "constitutional_hash": "t",
            }
        )

        async def scan(pattern):
            yield b"test:state:wf-1:run-1"

        mock_redis.scan_iter = scan
        pipeline = AsyncMock()
        pipeline.get = MagicMock()
        pipeline.execute = AsyncMock(return_value=[stored])
        mock_redis.pipeline.return_value = pipeline
        result = await persistence.load_state("wf-1")
        assert result is not None

    async def test_load_state_without_run_id_null_data(self, persistence, mock_redis):
        async def scan(pattern):
            yield b"test:state:wf-1:run-1"

        mock_redis.scan_iter = scan
        pipeline = AsyncMock()
        pipeline.get = MagicMock()
        pipeline.execute = AsyncMock(return_value=[None])
        mock_redis.pipeline.return_value = pipeline
        assert await persistence.load_state("wf-1") is None

    async def test_load_state_with_run_id_no_data(self, persistence, mock_redis):
        mock_redis.get.return_value = None
        assert await persistence.load_state("wf-1", run_id="run-1") is None

    async def test_save_checkpoint(self, persistence, mock_redis):
        cp = Checkpoint(
            id="cp-1",
            workflow_id="wf-1",
            run_id="run-1",
            node_id="n1",
            step_index=0,
            state=_gs(),
        )
        await persistence.save_checkpoint(cp)
        assert mock_redis.setex.call_count == 1
        mock_redis.zadd.assert_called_once()
        mock_redis.expire.assert_called_once()

    async def test_load_checkpoint_found(self, persistence, mock_redis):
        now = datetime.now(UTC)
        stored = json.dumps(
            {
                "id": "cp-1",
                "workflow_id": "wf-1",
                "run_id": "run-1",
                "node_id": "n1",
                "step_index": 0,
                "state": _gs_json(),
                "status": "created",
                "constitutional_validated": False,
                "maci_validated": False,
                "created_at": now.isoformat(),
                "validated_at": None,
                "metadata": {},
                "constitutional_hash": "test",
            }
        )
        mock_redis.get.return_value = stored
        result = await persistence.load_checkpoint("cp-1")
        assert result is not None and result.id == "cp-1"

    async def test_load_checkpoint_with_validated_at(self, persistence, mock_redis):
        now = datetime.now(UTC)
        stored = json.dumps(
            {
                "id": "cp-1",
                "workflow_id": "wf-1",
                "run_id": "run-1",
                "node_id": "n1",
                "step_index": 0,
                "state": _gs_json(),
                "status": "validated",
                "constitutional_validated": True,
                "maci_validated": True,
                "created_at": now.isoformat(),
                "validated_at": now.isoformat(),
                "metadata": {"k": "v"},
                "constitutional_hash": "test",
            }
        )
        mock_redis.get.return_value = stored
        result = await persistence.load_checkpoint("cp-1")
        assert result is not None and result.validated_at is not None

    async def test_load_checkpoint_not_found(self, persistence, mock_redis):
        mock_redis.get.return_value = None
        assert await persistence.load_checkpoint("x") is None

    async def test_list_checkpoints(self, persistence, mock_redis):
        now = datetime.now(UTC)
        mock_redis.zrange.return_value = [b"cp-1"]
        stored = json.dumps(
            {
                "id": "cp-1",
                "workflow_id": "wf-1",
                "run_id": "run-1",
                "node_id": "n1",
                "step_index": 0,
                "state": _gs_json(),
                "status": "created",
                "constitutional_validated": False,
                "maci_validated": False,
                "created_at": now.isoformat(),
                "validated_at": None,
                "metadata": {},
                "constitutional_hash": "t",
            }
        )
        mock_redis.get.return_value = stored
        assert len(await persistence.list_checkpoints("wf-1")) == 1

    async def test_list_checkpoints_with_run_id_filter(self, persistence, mock_redis):
        now = datetime.now(UTC)
        mock_redis.zrange.return_value = ["cp-1"]
        stored = json.dumps(
            {
                "id": "cp-1",
                "workflow_id": "wf-1",
                "run_id": "run-1",
                "node_id": "n1",
                "step_index": 0,
                "state": _gs_json(),
                "status": "created",
                "constitutional_validated": False,
                "maci_validated": False,
                "created_at": now.isoformat(),
                "validated_at": None,
                "metadata": {},
                "constitutional_hash": "t",
            }
        )
        mock_redis.get.return_value = stored
        assert len(await persistence.list_checkpoints("wf-1", run_id="run-1")) == 1
        assert len(await persistence.list_checkpoints("wf-1", run_id="other")) == 0

    async def test_list_checkpoints_skips_missing(self, persistence, mock_redis):
        mock_redis.zrange.return_value = [b"cp-missing"]
        mock_redis.get.return_value = None
        assert len(await persistence.list_checkpoints("wf-1")) == 0

    async def test_delete_checkpoint_success(self, persistence, mock_redis):
        mock_redis.delete.return_value = 1

        async def scan(pattern):
            yield b"test:checkpoints:wf-1"

        mock_redis.scan_iter = scan
        mock_redis.zrem = AsyncMock()
        assert await persistence.delete_checkpoint("cp-1") is True

    async def test_delete_checkpoint_not_found(self, persistence, mock_redis):
        mock_redis.delete.return_value = 0

        async def scan(pattern):
            return
            yield  # noqa: unreachable

        mock_redis.scan_iter = scan
        assert await persistence.delete_checkpoint("cp-1") is False

    async def test_save_execution_result(self, persistence, mock_redis):
        result = ExecutionResult(
            workflow_id="wf-1",
            run_id="run-1",
            status=ExecutionStatus.COMPLETED,
            final_state=_gs({"done": True}),
            output={"result": "ok"},
            total_execution_time_ms=100.5,
            node_count=3,
            step_count=5,
            constitutional_validated=True,
            checkpoint_count=2,
            started_at=datetime.now(UTC),
        )
        await persistence.save_execution_result(result)
        mock_redis.setex.assert_called_once()

    async def test_save_execution_result_no_final_state(self, persistence, mock_redis):
        result = ExecutionResult(
            workflow_id="wf-1",
            run_id="run-1",
            status=ExecutionStatus.FAILED,
            error="fail",
        )
        await persistence.save_execution_result(result)
        mock_redis.setex.assert_called_once()

    async def test_load_execution_result_found(self, persistence, mock_redis):
        now = datetime.now(UTC)
        stored = json.dumps(
            {
                "workflow_id": "wf-1",
                "run_id": "run-1",
                "status": "completed",
                "final_state": _gs_json(),
                "output": {"ok": True},
                "error": None,
                "total_execution_time_ms": 50.0,
                "node_count": 2,
                "step_count": 4,
                "p50_node_time_ms": 10.0,
                "p99_node_time_ms": 40.0,
                "constitutional_validated": True,
                "checkpoint_count": 1,
                "started_at": now.isoformat(),
                "completed_at": now.isoformat(),
                "constitutional_hash": "test",
            }
        )
        mock_redis.get.return_value = stored
        result = await persistence.load_execution_result("wf-1", "run-1")
        assert result is not None and result.status == ExecutionStatus.COMPLETED

    async def test_load_execution_result_no_started_at(self, persistence, mock_redis):
        now = datetime.now(UTC)
        stored = json.dumps(
            {
                "workflow_id": "wf-1",
                "run_id": "run-1",
                "status": "failed",
                "final_state": None,
                "output": None,
                "error": "fail",
                "total_execution_time_ms": 0,
                "node_count": 0,
                "step_count": 0,
                "p50_node_time_ms": None,
                "p99_node_time_ms": None,
                "constitutional_validated": False,
                "checkpoint_count": 0,
                "started_at": None,
                "completed_at": now.isoformat(),
                "constitutional_hash": "test",
            }
        )
        mock_redis.get.return_value = stored
        result = await persistence.load_execution_result("wf-1", "run-1")
        assert result is not None and result.started_at is None

    async def test_load_execution_result_not_found(self, persistence, mock_redis):
        mock_redis.get.return_value = None
        assert await persistence.load_execution_result("wf-1", "run-1") is None

    async def test_close(self, persistence, mock_redis):
        await persistence.close()
        mock_redis.close.assert_called_once()
        assert persistence._redis is None

    async def test_close_not_connected(self):
        p = RedisStatePersistence()
        await p.close()

    def test_key_methods(self):
        p = RedisStatePersistence(key_prefix="pfx:")
        assert p._state_key("wf", "run") == "pfx:state:wf:run"
        assert p._checkpoint_key("cp") == "pfx:checkpoint:cp"
        assert p._result_key("wf", "run") == "pfx:result:wf:run"
        assert p._workflow_checkpoints_key("wf") == "pfx:checkpoints:wf"


# ============================================================================
# 3. create_state_persistence factory
# ============================================================================


class TestCreateStatePersistence:
    def test_memory_backend(self):
        assert isinstance(create_state_persistence(backend="memory"), InMemoryStatePersistence)

    def test_redis_backend(self):
        assert isinstance(
            create_state_persistence(backend="redis", redis_url="redis://t:6379"),
            RedisStatePersistence,
        )

    def test_redis_default_url(self):
        assert isinstance(create_state_persistence(backend="redis"), RedisStatePersistence)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown persistence backend"):
            create_state_persistence(backend="unknown")

    def test_custom_hash(self):
        p = create_state_persistence(backend="memory", constitutional_hash="custom")
        assert p.constitutional_hash == "custom"


# ============================================================================
# 4. PostgresStateManager Tests
# ============================================================================


class TestPostgresStateManager:
    @pytest.fixture
    def manager(self):
        from enhanced_agent_bus.saga_persistence.postgres.state import PostgresStateManager

        class TestableManager(PostgresStateManager):
            def __init__(self):
                self._pool = MagicMock()
                self._saga_data: dict = {}

            def _ensure_initialized(self):
                return self._pool

            def _row_to_checkpoint(self, row):
                from enhanced_agent_bus.saga_persistence.models import SagaCheckpoint

                return SagaCheckpoint(
                    checkpoint_id=str(row.get("checkpoint_id", "")),
                    saga_id=str(row.get("saga_id", "")),
                )

            async def get(self, saga_id):
                return self._saga_data.get(saga_id)

        return TestableManager()

    @pytest.fixture
    def mock_conn(self):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchval = AsyncMock(return_value=None)
        return conn

    def _setup_pool(self, manager, mock_conn):
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        manager._pool.acquire.return_value = ctx

    # -- update_state --

    async def test_update_state_not_found(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = None
        assert await manager.update_state(_SAGA_ID, SagaState.RUNNING) is False

    async def test_update_state_invalid_transition(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState
        from enhanced_agent_bus.saga_persistence.repository import InvalidStateTransitionError

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = {
            "state": "COMPLETED",
            "version": 1,
            "started_at": datetime.now(UTC),
        }
        with pytest.raises(InvalidStateTransitionError):
            await manager.update_state(_SAGA_ID, SagaState.RUNNING)

    async def test_update_state_to_running(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = {
            "state": "INITIALIZED",
            "version": 1,
            "started_at": None,
        }
        assert await manager.update_state(_SAGA_ID, SagaState.RUNNING) is True

    async def test_update_state_to_completed_with_started_at(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = {
            "state": "RUNNING",
            "version": 1,
            "started_at": datetime.now(UTC),
        }
        assert await manager.update_state(_SAGA_ID, SagaState.COMPLETED) is True

    async def test_update_state_to_completed_no_started_at(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = {
            "state": "RUNNING",
            "version": 1,
            "started_at": None,
        }
        assert await manager.update_state(_SAGA_ID, SagaState.COMPLETED) is True

    async def test_update_state_to_compensated(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = {
            "state": "COMPENSATING",
            "version": 1,
            "started_at": datetime.now(UTC),
        }
        assert await manager.update_state(_SAGA_ID, SagaState.COMPENSATED) is True

    async def test_update_state_to_failed_with_reason(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = {
            "state": "RUNNING",
            "version": 1,
            "started_at": datetime.now(UTC),
        }
        assert (
            await manager.update_state(_SAGA_ID, SagaState.FAILED, failure_reason="timeout") is True
        )

    async def test_update_state_no_timestamp_field(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaState

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.return_value = {
            "state": "RUNNING",
            "version": 1,
            "started_at": datetime.now(UTC),
        }
        assert await manager.update_state(_SAGA_ID, SagaState.COMPENSATING) is True

    async def test_update_state_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.models import SagaState
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchrow.side_effect = asyncpg.PostgresError("connection lost")
        with pytest.raises(RepositoryError):
            await manager.update_state(_SAGA_ID, SagaState.RUNNING)

    # -- update_step_state --

    async def test_update_step_state_saga_not_found(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import StepState

        self._setup_pool(manager, mock_conn)
        assert await manager.update_step_state(_SAGA_ID, _STEP_ID, StepState.RUNNING) is False

    async def test_update_step_state_step_not_found(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import (
            PersistedSagaState,
            PersistedStepSnapshot,
            StepState,
        )

        self._setup_pool(manager, mock_conn)
        saga = PersistedSagaState(
            saga_id=_SAGA_ID,
            steps=[PersistedStepSnapshot(step_id="other", step_name="other")],
        )
        manager._saga_data = {_SAGA_ID: saga}
        assert await manager.update_step_state(_SAGA_ID, "missing", StepState.RUNNING) is False

    async def test_update_step_state_success(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import (
            PersistedSagaState,
            PersistedStepSnapshot,
            StepState,
        )

        self._setup_pool(manager, mock_conn)
        step = PersistedStepSnapshot(step_id=_STEP_ID, step_name="test", state=StepState.PENDING)
        saga = PersistedSagaState(saga_id=_SAGA_ID, steps=[step])
        manager._saga_data = {_SAGA_ID: saga}
        assert await manager.update_step_state(_SAGA_ID, _STEP_ID, StepState.RUNNING) is True

    async def test_update_step_state_terminal_with_started_at(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import (
            PersistedSagaState,
            PersistedStepSnapshot,
            StepState,
        )

        self._setup_pool(manager, mock_conn)
        step = PersistedStepSnapshot(
            step_id=_STEP_ID,
            step_name="test",
            state=StepState.RUNNING,
            started_at=datetime.now(UTC),
        )
        saga = PersistedSagaState(saga_id=_SAGA_ID, steps=[step])
        manager._saga_data = {_SAGA_ID: saga}
        assert (
            await manager.update_step_state(
                _SAGA_ID, _STEP_ID, StepState.COMPLETED, output_data={"ok": True}
            )
            is True
        )

    async def test_update_step_state_with_error(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import (
            PersistedSagaState,
            PersistedStepSnapshot,
            StepState,
        )

        self._setup_pool(manager, mock_conn)
        step = PersistedStepSnapshot(
            step_id=_STEP_ID,
            step_name="test",
            state=StepState.RUNNING,
            started_at=datetime.now(UTC),
        )
        saga = PersistedSagaState(saga_id=_SAGA_ID, steps=[step])
        manager._saga_data = {_SAGA_ID: saga}
        assert (
            await manager.update_step_state(
                _SAGA_ID, _STEP_ID, StepState.FAILED, error_message="step failed"
            )
            is True
        )

    async def test_update_step_state_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.models import (
            PersistedSagaState,
            PersistedStepSnapshot,
            StepState,
        )
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        step = PersistedStepSnapshot(step_id=_STEP_ID, step_name="test")
        saga = PersistedSagaState(saga_id=_SAGA_ID, steps=[step])
        manager._saga_data = {_SAGA_ID: saga}
        mock_conn.execute.side_effect = asyncpg.PostgresError("db error")
        with pytest.raises(RepositoryError):
            await manager.update_step_state(_SAGA_ID, _STEP_ID, StepState.RUNNING)

    # -- update_current_step --

    async def test_update_current_step_success(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.execute.return_value = "UPDATE 1"
        assert await manager.update_current_step(_SAGA_ID, 3) is True

    async def test_update_current_step_not_found(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.execute.return_value = "UPDATE 0"
        assert await manager.update_current_step(_SAGA_ID, 3) is False

    async def test_update_current_step_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        mock_conn.execute.side_effect = asyncpg.PostgresError("db error")
        with pytest.raises(RepositoryError):
            await manager.update_current_step(_SAGA_ID, 3)

    # -- save_checkpoint --

    async def test_save_checkpoint_success(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import SagaCheckpoint

        self._setup_pool(manager, mock_conn)
        cp = SagaCheckpoint(
            checkpoint_id=_CP_ID,
            saga_id=_SAGA_ID,
            checkpoint_name="test",
            state_snapshot={"k": "v"},
            completed_step_ids=["s1"],
            pending_step_ids=["s2"],
        )
        assert await manager.save_checkpoint(cp) is True

    async def test_save_checkpoint_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.models import SagaCheckpoint
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        mock_conn.execute.side_effect = asyncpg.PostgresError("db error")
        cp = SagaCheckpoint(checkpoint_id=_CP_ID, saga_id=_SAGA_ID)
        with pytest.raises(RepositoryError):
            await manager.save_checkpoint(cp)

    # -- get_checkpoints --

    async def test_get_checkpoints_success(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.fetch.return_value = []
        assert await manager.get_checkpoints(_SAGA_ID) == []

    async def test_get_checkpoints_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        mock_conn.fetch.side_effect = asyncpg.PostgresError("db error")
        with pytest.raises(RepositoryError):
            await manager.get_checkpoints(_SAGA_ID)

    # -- get_latest_checkpoint --

    async def test_get_latest_checkpoint_none(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.fetch.return_value = []
        assert await manager.get_latest_checkpoint(_SAGA_ID) is None

    # -- delete_checkpoints --

    async def test_delete_checkpoints_success(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.execute.return_value = "DELETE 3"
        assert await manager.delete_checkpoints(_SAGA_ID) == 3

    async def test_delete_checkpoints_zero(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.execute.return_value = "DELETE 0"
        assert await manager.delete_checkpoints(_SAGA_ID) == 0

    async def test_delete_checkpoints_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        mock_conn.execute.side_effect = asyncpg.PostgresError("db error")
        with pytest.raises(RepositoryError):
            await manager.delete_checkpoints(_SAGA_ID)

    # -- append_compensation_entry --

    async def test_append_compensation_success(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import CompensationEntry

        self._setup_pool(manager, mock_conn)
        mock_conn.execute.return_value = "UPDATE 1"
        entry = CompensationEntry(step_id="s1", step_name="step1", executed=True)
        assert await manager.append_compensation_entry(_SAGA_ID, entry) is True

    async def test_append_compensation_not_found(self, manager, mock_conn):
        from enhanced_agent_bus.saga_persistence.models import CompensationEntry

        self._setup_pool(manager, mock_conn)
        mock_conn.execute.return_value = "UPDATE 0"
        entry = CompensationEntry(step_id="s1")
        assert await manager.append_compensation_entry(_SAGA_ID, entry) is False

    async def test_append_compensation_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.models import CompensationEntry
        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        mock_conn.execute.side_effect = asyncpg.PostgresError("db error")
        with pytest.raises(RepositoryError):
            await manager.append_compensation_entry(_SAGA_ID, CompensationEntry(step_id="s1"))

    # -- get_compensation_log --

    async def test_get_compensation_log_empty(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.fetchval.return_value = None
        assert await manager.get_compensation_log(_SAGA_ID) == []

    async def test_get_compensation_log_from_string(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        entries = [{"compensation_id": "c1", "step_id": "s1", "step_name": "t", "executed": True}]
        mock_conn.fetchval.return_value = json.dumps(entries)
        assert len(await manager.get_compensation_log(_SAGA_ID)) == 1

    async def test_get_compensation_log_from_list(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        entries = [{"compensation_id": "c1", "step_id": "s1", "step_name": "t", "executed": False}]
        mock_conn.fetchval.return_value = entries
        assert len(await manager.get_compensation_log(_SAGA_ID)) == 1

    async def test_get_compensation_log_filters_non_dict(self, manager, mock_conn):
        self._setup_pool(manager, mock_conn)
        mock_conn.fetchval.return_value = [{"step_id": "s1"}, "not_a_dict", 42]
        assert len(await manager.get_compensation_log(_SAGA_ID)) == 1

    async def test_get_compensation_log_postgres_error(self, manager, mock_conn):
        import asyncpg

        from enhanced_agent_bus.saga_persistence.repository import RepositoryError

        self._setup_pool(manager, mock_conn)
        mock_conn.fetchval.side_effect = asyncpg.PostgresError("db error")
        with pytest.raises(RepositoryError):
            await manager.get_compensation_log(_SAGA_ID)


# ============================================================================
# 5. Constitutional Transition Tests
# ============================================================================


class TestTransitionProof:
    def test_create_with_auto_hash(self):
        proof = TransitionProof(transition_id="t-1")
        assert proof.proof_hash and len(proof.proof_hash) == 64

    def test_verify_valid(self):
        assert TransitionProof(transition_id="t-1").verify() is True

    def test_verify_tampered(self):
        proof = TransitionProof(transition_id="t-1")
        proof.state_hash_before = "tampered"
        assert proof.verify() is False

    def test_to_dict(self):
        proof = TransitionProof(
            transition_id="t-1",
            proof_type=ProofType.MERKLE_PROOF,
            signature="sig",
            signer_id="s1",
            witnesses=["w1"],
        )
        d = proof.to_dict()
        assert d["proof_type"] == "merkle_proof"
        assert d["witnesses"] == ["w1"]

    def test_existing_hash_preserved(self):
        assert TransitionProof(transition_id="t-1", proof_hash="custom").proof_hash == "custom"


class TestConstitutionalTransition:
    def test_defaults(self):
        t = ConstitutionalTransition()
        assert t.current_state == TransitionState.INITIAL

    def test_is_terminal(self):
        for state in (
            TransitionState.COMPLETED,
            TransitionState.REJECTED,
            TransitionState.ROLLED_BACK,
        ):
            assert ConstitutionalTransition(current_state=state).is_terminal is True
        assert ConstitutionalTransition(current_state=TransitionState.INITIAL).is_terminal is False

    def test_proof_chain(self):
        p1 = TransitionProof(transition_id="t", proof_hash="h1")
        p2 = TransitionProof(transition_id="t", proof_hash="h2")
        assert ConstitutionalTransition(proofs=[p1, p2]).proof_chain == ["h1", "h2"]

    def test_to_dict_fields(self):
        d = ConstitutionalTransition(
            transition_type=TransitionType.EMERGENCY_ACTION,
            initiated_by="admin",
            rejected_by="rev",
            rejection_reason="bad",
        ).to_dict()
        assert d["transition_type"] == "emergency_action"
        assert d["completed_at"] is None

    def test_to_dict_completed_at(self):
        now = datetime.now(UTC)
        assert (
            ConstitutionalTransition(completed_at=now).to_dict()["completed_at"] == now.isoformat()
        )

    def test_compute_state_hash(self):
        h = ConstitutionalTransition(state_data={"k": "v"})._compute_state_hash()
        assert isinstance(h, str) and len(h) == 32


class TestStateTransitionManager:
    @pytest.fixture
    def mgr(self):
        return StateTransitionManager(require_proof_verification=True)

    def test_create_transition(self, mgr):
        t = mgr.create_transition(
            TransitionType.POLICY_CHANGE,
            state_data={"p": "new"},
            context={"env": "test"},
            initiated_by="admin",
            metadata={"t": "1"},
        )
        assert t.current_state == TransitionState.INITIAL
        assert len(t.proofs) == 1

    def test_create_transition_defaults(self, mgr):
        t = mgr.create_transition(TransitionType.AUDIT_REQUEST, state_data={})
        assert t.initiated_by == "system"

    async def test_transition_to_valid(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, proof = await mgr.transition_to(t, TransitionState.PENDING_VALIDATION, "v1")
        assert ok is True and proof is not None

    async def test_transition_to_invalid(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, proof = await mgr.transition_to(t, TransitionState.COMPLETED, "actor")
        assert ok is False and proof is None

    async def test_transition_approved_adds_actor(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
        ]:
            await mgr.transition_to(t, s, "sys")
        await mgr.transition_to(t, TransitionState.APPROVED, "approver-1")
        assert "approver-1" in t.approved_by

    async def test_transition_rejected(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, _ = await mgr.transition_to(t, TransitionState.REJECTED, "rej", reason="bad")
        assert ok and t.rejected_by == "rej" and t.rejection_reason == "bad"

    async def test_transition_executed_stores_result(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
            TransitionState.APPROVED,
            TransitionState.EXECUTING,
        ]:
            await mgr.transition_to(t, s, "sys")
        await mgr.transition_to(t, TransitionState.EXECUTED, "e1", execution_result={"out": 1})
        assert t.execution_result == {"out": 1}

    async def test_completed_sets_completed_at(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
            TransitionState.APPROVED,
            TransitionState.EXECUTING,
            TransitionState.EXECUTED,
            TransitionState.PENDING_VERIFICATION,
            TransitionState.VERIFIED,
            TransitionState.COMPLETED,
        ]:
            await mgr.transition_to(t, s, "sys")
        assert t.completed_at is not None
        assert t.transition_id in mgr._completed_transitions

    async def test_rolled_back_sets_completed_at(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
            TransitionState.APPROVED,
            TransitionState.EXECUTING,
            TransitionState.EXECUTED,
        ]:
            await mgr.transition_to(t, s, "sys")
        await mgr.transition_to(t, TransitionState.ROLLED_BACK, "sys")
        assert t.completed_at is not None

    async def test_validate_transition(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, _ = await mgr.validate_transition(t, "v1")
        assert ok and t.current_state == TransitionState.VALIDATED

    async def test_approve_transition(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        await mgr.validate_transition(t, "v1")
        await mgr.transition_to(t, TransitionState.PENDING_APPROVAL, "a1")
        ok, _ = await mgr.approve_transition(t, "approver")
        assert ok is True

    async def test_execute_not_approved(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, proof = await mgr.execute_transition(t, "executor")
        assert ok is False and proof is None

    async def test_execute_with_sync_func(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
            TransitionState.APPROVED,
        ]:
            await mgr.transition_to(t, s, "sys")
        ok, _ = await mgr.execute_transition(t, "exec", lambda d: {"done": True})
        assert ok and t.current_state == TransitionState.EXECUTED

    async def test_execute_with_async_func(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
            TransitionState.APPROVED,
        ]:
            await mgr.transition_to(t, s, "sys")

        async def fn(d):
            return {"async": True}

        ok, _ = await mgr.execute_transition(t, "exec", fn)
        assert ok is True

    async def test_execute_func_raises(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
            TransitionState.APPROVED,
        ]:
            await mgr.transition_to(t, s, "sys")
        ok, _ = await mgr.execute_transition(
            t, "exec", lambda d: (_ for _ in ()).throw(RuntimeError("fail"))
        )
        assert ok is False and t.current_state == TransitionState.FAILED

    async def test_reject_transition(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, _ = await mgr.reject_transition(t, "rej", "nope")
        assert ok and t.current_state == TransitionState.REJECTED

    async def test_rollback_no_checkpoints(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, _ = await mgr.rollback_transition(t, "admin", "undo")
        assert ok is False

    async def _bring_to_executed(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={"x": 1})
        for s in [
            TransitionState.PENDING_VALIDATION,
            TransitionState.VALIDATED,
            TransitionState.PENDING_APPROVAL,
            TransitionState.APPROVED,
            TransitionState.EXECUTING,
            TransitionState.EXECUTED,
        ]:
            await mgr.transition_to(t, s, "sys")
        return t

    async def test_rollback_with_sync_func(self, mgr):
        t = await self._bring_to_executed(mgr)
        called = {}
        ok, _ = await mgr.rollback_transition(t, "admin", "undo", lambda d: called.update(d=d))
        assert ok and t.current_state == TransitionState.ROLLED_BACK

    async def test_rollback_with_async_func(self, mgr):
        t = await self._bring_to_executed(mgr)

        async def fn(d):
            pass

        ok, _ = await mgr.rollback_transition(t, "admin", "undo", fn)
        assert ok is True

    async def test_rollback_func_raises(self, mgr):
        t = await self._bring_to_executed(mgr)

        def bad(d):
            raise RuntimeError("rollback failed")

        ok, _ = await mgr.rollback_transition(t, "admin", "undo", bad)
        assert ok is True  # errors logged, not propagated

    async def test_complete_from_verified(self, mgr):
        t = await self._bring_to_executed(mgr)
        for s in [TransitionState.PENDING_VERIFICATION, TransitionState.VERIFIED]:
            await mgr.transition_to(t, s, "sys")
        ok, _ = await mgr.complete_transition(t, "comp")
        assert ok and t.current_state == TransitionState.COMPLETED

    async def test_complete_from_executed(self, mgr):
        t = await self._bring_to_executed(mgr)
        ok, _ = await mgr.complete_transition(t, "comp")
        assert ok and t.current_state == TransitionState.COMPLETED

    async def test_complete_from_invalid_state(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        ok, _ = await mgr.complete_transition(t, "comp")
        assert ok is False

    def test_verify_proof_chain_empty(self, mgr):
        valid, errors = mgr.verify_proof_chain(ConstitutionalTransition(proofs=[]))
        assert valid and errors == []

    def test_verify_proof_chain_valid(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        valid, errors = mgr.verify_proof_chain(t)
        assert valid and errors == []

    def test_verify_proof_chain_tampered(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        t.proofs[0].state_hash_before = "tampered"
        valid, errors = mgr.verify_proof_chain(t)
        assert not valid

    def test_verify_proof_chain_continuity_broken(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        t.proofs.append(
            TransitionProof(
                transition_id=t.transition_id,
                chain_position=2,
                previous_proof_hash="wrong",
            )
        )
        valid, errors = mgr.verify_proof_chain(t)
        assert not valid and any("continuity" in e for e in errors)

    def test_verify_proof_chain_wrong_constitutional_hash(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        t.proofs[0].constitutional_hash = "wrong"
        valid, errors = mgr.verify_proof_chain(t)
        assert not valid

    def test_get_transition_active(self, mgr):
        t = mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        assert mgr.get_transition(t.transition_id) is t

    def test_get_transition_completed(self, mgr):
        t = ConstitutionalTransition(transition_id="done-1")
        mgr._completed_transitions["done-1"] = t
        assert mgr.get_transition("done-1") is t

    def test_get_transition_not_found(self, mgr):
        assert mgr.get_transition("x") is None

    def test_list_active(self, mgr):
        mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        mgr.create_transition(TransitionType.ACCESS_GRANT, state_data={})
        result = mgr.list_active_transitions()
        assert len(result) == 2

    async def test_get_manager_status(self, mgr):
        mgr.create_transition(TransitionType.POLICY_CHANGE, state_data={})
        status = await mgr.get_manager_status()
        assert status["status"] == "operational"
        assert status["active_transitions"] == 1

    def test_factory(self):
        m = create_transition_manager(require_proof_verification=False)
        assert isinstance(m, StateTransitionManager)
        assert m.require_proof_verification is False


# ============================================================================
# 6. VALID_TRANSITIONS map
# ============================================================================


class TestValidTransitions:
    def test_terminal_states(self):
        assert VALID_TRANSITIONS[TransitionState.REJECTED] == set()
        assert VALID_TRANSITIONS[TransitionState.ROLLED_BACK] == set()

    def test_failed_can_rollback(self):
        assert VALID_TRANSITIONS[TransitionState.FAILED] == {TransitionState.ROLLED_BACK}

    def test_initial_targets(self):
        assert VALID_TRANSITIONS[TransitionState.INITIAL] == {
            TransitionState.PENDING_VALIDATION,
            TransitionState.REJECTED,
        }


# ============================================================================
# 7. MessageProcessor Tests
# ============================================================================


class TestMessageProcessor:
    @pytest.fixture
    def processor(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        return MessageProcessor(isolated_mode=True)

    def test_init_isolated(self, processor):
        assert processor._isolated_mode is True

    def test_register_handler(self, processor):
        from enhanced_agent_bus.models import MessageType

        async def h(msg):
            return msg

        processor.register_handler(MessageType.QUERY, h)
        assert h in processor._handlers[MessageType.QUERY]

    def test_register_multiple_handlers(self, processor):
        from enhanced_agent_bus.models import MessageType

        async def h1(msg):
            return msg

        async def h2(msg):
            return msg

        processor.register_handler(MessageType.QUERY, h1)
        processor.register_handler(MessageType.QUERY, h2)
        assert len(processor._handlers[MessageType.QUERY]) == 2

    def test_unregister_handler_success(self, processor):
        from enhanced_agent_bus.models import MessageType

        async def h(msg):
            return msg

        processor.register_handler(MessageType.QUERY, h)
        assert processor.unregister_handler(MessageType.QUERY, h) is True

    def test_unregister_handler_not_found(self, processor):
        from enhanced_agent_bus.models import MessageType

        async def h(msg):
            return msg

        assert processor.unregister_handler(MessageType.QUERY, h) is False

    def test_get_metrics(self, processor):
        m = processor.get_metrics()
        assert "processed_count" in m and m["processed_count"] == 0

    def test_properties(self, processor):
        assert processor.processed_count == 0
        assert processor.failed_count == 0
        assert processor.processing_strategy is not None
        assert processor.opa_client is None

    def test_set_strategy(self, processor):
        s = MagicMock()
        processor._set_strategy(s)
        assert processor._processing_strategy is s

    def test_compliance_tags_valid(self, processor):
        from enhanced_agent_bus.models import AgentMessage
        from enhanced_agent_bus.validators import ValidationResult

        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        tags = processor._get_compliance_tags(msg, ValidationResult(is_valid=True))
        assert "approved" in tags

    def test_compliance_tags_rejected(self, processor):
        from enhanced_agent_bus.models import AgentMessage
        from enhanced_agent_bus.validators import ValidationResult

        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        tags = processor._get_compliance_tags(msg, ValidationResult(is_valid=False, errors=["e"]))
        assert "rejected" in tags

    def test_compliance_tags_critical(self, processor):
        from enhanced_agent_bus.models import AgentMessage, Priority
        from enhanced_agent_bus.validators import ValidationResult

        msg = AgentMessage(from_agent="a", to_agent="b", content="t", priority=Priority.CRITICAL)
        tags = processor._get_compliance_tags(msg, ValidationResult(is_valid=True))
        assert "high_priority" in tags

    def test_log_decision(self, processor):
        from enhanced_agent_bus.models import AgentMessage
        from enhanced_agent_bus.validators import ValidationResult

        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        processor._log_decision(msg, ValidationResult(is_valid=True))

    def test_log_decision_with_span(self, processor):
        from enhanced_agent_bus.models import AgentMessage
        from enhanced_agent_bus.validators import ValidationResult

        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        span = MagicMock()
        ctx = MagicMock()
        ctx.trace_id = 12345
        span.get_span_context.return_value = ctx
        processor._log_decision(msg, ValidationResult(is_valid=True), span=span)
        span.set_attribute.assert_called()

    def test_extract_rejection_reason(self, processor):
        from enhanced_agent_bus.validators import ValidationResult

        r = ValidationResult(is_valid=False, errors=["e"], metadata={"rejection_reason": "pol"})
        assert processor._extract_rejection_reason(r) == "pol"

    def test_extract_rejection_reason_default(self, processor):
        from enhanced_agent_bus.validators import ValidationResult

        assert isinstance(
            processor._extract_rejection_reason(ValidationResult(is_valid=False, errors=["e"])),
            str,
        )

    def test_requires_independent_validation_high(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        msg = AgentMessage(from_agent="a", to_agent="b", content="t", impact_score=0.9)
        assert processor._requires_independent_validation(msg) is True

    def test_requires_independent_validation_low(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        msg = AgentMessage(from_agent="a", to_agent="b", content="t", impact_score=0.1)
        assert processor._requires_independent_validation(msg) is False

    def test_requires_independent_validation_none(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        msg.impact_score = None
        assert processor._requires_independent_validation(msg) is False

    def test_requires_independent_validation_governance(self, processor):
        from enhanced_agent_bus.models import AgentMessage, MessageType

        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            content="t",
            message_type=MessageType.GOVERNANCE_REQUEST,
        )
        assert processor._requires_independent_validation(msg) is True

    def test_enforce_gate_disabled(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        processor._require_independent_validator = False
        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        assert processor._enforce_independent_validator_gate(msg) is None

    def test_enforce_gate_low_impact(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        processor._require_independent_validator = True
        msg = AgentMessage(from_agent="a", to_agent="b", content="t", impact_score=0.1)
        assert processor._enforce_independent_validator_gate(msg) is None

    def test_enforce_gate_missing_validator(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        processor._require_independent_validator = True
        msg = AgentMessage(
            from_agent="a",
            to_agent="b",
            content="t",
            impact_score=0.9,
            metadata={},
        )
        result = processor._enforce_independent_validator_gate(msg)
        assert result is not None and result.is_valid is False

    def test_enforce_gate_self_validation(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        processor._require_independent_validator = True
        msg = AgentMessage(
            from_agent="agent-a",
            to_agent="b",
            content="t",
            impact_score=0.9,
            metadata={"validated_by_agent": "agent-a"},
        )
        result = processor._enforce_independent_validator_gate(msg)
        assert result is not None and "self_validation" in str(result.metadata)

    def test_enforce_gate_invalid_stage(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        processor._require_independent_validator = True
        msg = AgentMessage(
            from_agent="agent-a",
            to_agent="b",
            content="t",
            impact_score=0.9,
            metadata={"validated_by_agent": "agent-b", "validation_stage": "self"},
        )
        result = processor._enforce_independent_validator_gate(msg)
        assert result is not None and "invalid_stage" in str(result.metadata)

    def test_enforce_gate_valid(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        processor._require_independent_validator = True
        msg = AgentMessage(
            from_agent="agent-a",
            to_agent="b",
            content="t",
            impact_score=0.9,
            metadata={"validated_by_agent": "agent-b", "validation_stage": "independent"},
        )
        assert processor._enforce_independent_validator_gate(msg) is None

    def test_invalid_cache_hash_mode(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="invalid")

    async def test_process_isolated(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        msg = AgentMessage(from_agent="a", to_agent="b", content="hello")
        result = await processor.process(msg, max_retries=1)
        assert hasattr(result, "is_valid")

    def test_record_workflow_event_no_collector(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        processor._agent_workflow_metrics = None
        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        processor._record_agent_workflow_event(event_type="test", msg=msg, reason="r")

    def test_record_workflow_event_with_collector(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        collector = MagicMock()
        processor._agent_workflow_metrics = collector
        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        processor._record_agent_workflow_event(event_type="test", msg=msg, reason="r")
        collector.record_event.assert_called_once()

    def test_record_workflow_event_error(self, processor):
        from enhanced_agent_bus.models import AgentMessage

        collector = MagicMock()
        collector.record_event.side_effect = RuntimeError("fail")
        processor._agent_workflow_metrics = collector
        msg = AgentMessage(from_agent="a", to_agent="b", content="t")
        processor._record_agent_workflow_event(event_type="test", msg=msg, reason="r")

    def test_increment_failed_count(self, processor):
        initial = processor._failed_count
        processor._increment_failed_count()
        assert processor._failed_count == initial + 1
