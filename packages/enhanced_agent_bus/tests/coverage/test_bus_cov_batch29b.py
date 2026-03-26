"""
Coverage tests batch 29b — targeting uncovered lines in:
  1. saga_persistence/postgres/repository.py
  2. health_aggregator.py
  3. specs/fixtures/observability.py
  4. components/agent_registry_manager.py

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.saga_persistence.models import (
    CompensationEntry,
    CompensationStrategy,
    PersistedSagaState,
    PersistedStepSnapshot,
    SagaCheckpoint,
    SagaState,
    StepState,
)

# ---------------------------------------------------------------------------
# 1. saga_persistence/postgres/repository.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.saga_persistence.postgres.repository import (
    PostgresSagaStateRepository,
)
from enhanced_agent_bus.saga_persistence.repository import (
    RepositoryError,
    VersionConflictError,
)


def _make_saga(**overrides) -> PersistedSagaState:
    saga_id = overrides.pop("saga_id", str(uuid.uuid4()))
    correlation_id = overrides.pop("correlation_id", str(uuid.uuid4()))
    defaults = dict(
        saga_id=saga_id,
        saga_name="test-saga",
        tenant_id="t1",
        correlation_id=correlation_id,
        state=SagaState.INITIALIZED,
        compensation_strategy=CompensationStrategy.LIFO,
        steps=[],
        current_step_index=0,
        context={},
        metadata={},
        compensation_log=[],
        created_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
        failed_at=None,
        compensated_at=None,
        total_duration_ms=0.0,
        failure_reason=None,
        timeout_ms=300000,
        version=1,
        constitutional_hash="608508a9bd224290",
    )
    defaults.update(overrides)
    return PersistedSagaState(**defaults)


def _mock_pool():
    """Create a mock asyncpg pool with acquire context manager."""
    pool = MagicMock()
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    pool.close = AsyncMock()
    return pool, conn


class TestPostgresSagaStateRepositoryInit:
    """Tests for __init__ and initialization logic."""

    def test_init_with_dsn(self):
        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        assert repo._dsn == "postgres://localhost/test"
        assert repo._pool is None
        assert not repo._initialized
        assert repo._node_id.startswith("node-")

    def test_init_with_pool_marks_initialized(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)
        assert repo._initialized is True
        assert repo._pool is pool

    async def test_initialize_already_initialized(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)
        # Should return immediately (no-op)
        await repo.initialize()
        assert repo._initialized is True

    async def test_initialize_no_dsn_no_pool_raises(self):
        repo = PostgresSagaStateRepository(dsn=None, pool=None)
        with pytest.raises(RepositoryError, match="DSN required"):
            await repo.initialize()

    @patch("enhanced_agent_bus.saga_persistence.postgres.repository.asyncpg")
    async def test_initialize_creates_pool(self, mock_asyncpg):
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire.return_value = ctx
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        mock_asyncpg.PostgresError = Exception

        repo = PostgresSagaStateRepository(
            dsn="postgres://localhost/test",
            pool_min_size=2,
            pool_max_size=5,
            auto_initialize_schema=True,
        )
        await repo.initialize()

        mock_asyncpg.create_pool.assert_awaited_once()
        assert repo._initialized is True

    @patch("enhanced_agent_bus.saga_persistence.postgres.repository.asyncpg")
    async def test_initialize_schema_error_wrapped(self, mock_asyncpg):
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=RuntimeError("schema fail"))
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire.return_value = ctx
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        mock_asyncpg.PostgresError = Exception

        repo = PostgresSagaStateRepository(
            dsn="postgres://localhost/test",
            auto_initialize_schema=True,
        )
        with pytest.raises(RepositoryError, match="Failed to initialize"):
            await repo.initialize()

    async def test_initialize_schema_no_pool_raises(self):
        pool, _ = _mock_pool()
        repo = PostgresSagaStateRepository(pool=pool)
        repo._pool = None
        with pytest.raises(RepositoryError, match="Pool not initialized"):
            await repo._initialize_schema()


class TestPostgresSagaStateRepositoryClose:
    async def test_close_releases_pool(self):
        pool, _ = _mock_pool()
        repo = PostgresSagaStateRepository(pool=pool)
        await repo.close()
        pool.close.assert_awaited_once()
        assert repo._pool is None
        assert repo._initialized is False

    async def test_close_no_pool_noop(self):
        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        # Should not raise
        await repo.close()


class TestPostgresSagaStateRepositoryEnsureInitialized:
    def test_ensure_initialized_no_pool_raises(self):
        repo = PostgresSagaStateRepository(dsn="postgres://localhost/test")
        with pytest.raises(RepositoryError, match="not initialized"):
            repo._ensure_initialized()

    def test_ensure_initialized_returns_pool(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)
        assert repo._ensure_initialized() is pool


class TestPostgresSagaStateRepositorySave:
    async def test_save_new_saga(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock()
        repo = PostgresSagaStateRepository(pool=pool)

        saga = _make_saga()
        result = await repo.save(saga)
        assert result is True
        # Should have called INSERT (second execute)
        conn.execute.assert_awaited()

    async def test_save_existing_saga_update(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value={"version": 1})
        conn.execute = AsyncMock()
        repo = PostgresSagaStateRepository(pool=pool)

        saga = _make_saga(version=2)
        result = await repo.save(saga)
        assert result is True

    async def test_save_version_conflict(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value={"version": 5})
        repo = PostgresSagaStateRepository(pool=pool)

        saga = _make_saga(version=2)
        with pytest.raises(VersionConflictError):
            await repo.save(saga)

    async def test_save_postgres_error(self):
        import asyncpg as real_asyncpg

        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(side_effect=real_asyncpg.PostgresError("connection lost"))
        repo = PostgresSagaStateRepository(pool=pool)

        saga = _make_saga()
        with pytest.raises(RepositoryError, match="Failed to save"):
            await repo.save(saga)

    async def test_save_with_steps_and_compensation_log(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.execute = AsyncMock()
        repo = PostgresSagaStateRepository(pool=pool)

        step = PersistedStepSnapshot(step_name="step1", step_index=0)
        entry = CompensationEntry(step_id="s1", step_name="step1")
        saga = _make_saga(steps=[step], compensation_log=[entry])
        result = await repo.save(saga)
        assert result is True


class TestPostgresSagaStateRepositoryGet:
    async def test_get_not_found(self):
        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(return_value=None)
        repo = PostgresSagaStateRepository(pool=pool)

        result = await repo.get(str(uuid.uuid4()))
        assert result is None

    async def test_get_found(self):
        pool, conn = _mock_pool()
        saga_id = uuid.uuid4()
        corr_id = uuid.uuid4()
        row = {
            "saga_id": saga_id,
            "saga_name": "test",
            "tenant_id": "t1",
            "correlation_id": corr_id,
            "state": "INITIALIZED",
            "compensation_strategy": "LIFO",
            "current_step_index": 0,
            "version": 1,
            "steps": json.dumps([]),
            "context": json.dumps({}),
            "metadata": json.dumps({}),
            "compensation_log": json.dumps([]),
            "created_at": datetime.now(UTC),
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "compensated_at": None,
            "total_duration_ms": 0.0,
            "failure_reason": None,
            "timeout_ms": 300000,
            "constitutional_hash": "608508a9bd224290",
        }
        conn.fetchrow = AsyncMock(return_value=row)
        repo = PostgresSagaStateRepository(pool=pool)

        result = await repo.get(str(saga_id))
        assert result is not None
        assert result.saga_name == "test"

    async def test_get_postgres_error(self):
        import asyncpg as real_asyncpg

        pool, conn = _mock_pool()
        conn.fetchrow = AsyncMock(side_effect=real_asyncpg.PostgresError("fail"))
        repo = PostgresSagaStateRepository(pool=pool)

        with pytest.raises(RepositoryError, match="Failed to get"):
            await repo.get(str(uuid.uuid4()))


class TestPostgresSagaStateRepositoryDelete:
    async def test_delete_found(self):
        pool, conn = _mock_pool()
        conn.execute = AsyncMock(return_value="DELETE 1")
        repo = PostgresSagaStateRepository(pool=pool)

        result = await repo.delete(str(uuid.uuid4()))
        assert result is True
        assert conn.execute.await_count == 2  # DELETE saga + DELETE locks

    async def test_delete_not_found(self):
        pool, conn = _mock_pool()
        conn.execute = AsyncMock(return_value="DELETE 0")
        repo = PostgresSagaStateRepository(pool=pool)

        result = await repo.delete(str(uuid.uuid4()))
        assert result is False

    async def test_delete_postgres_error(self):
        import asyncpg as real_asyncpg

        pool, conn = _mock_pool()
        conn.execute = AsyncMock(side_effect=real_asyncpg.PostgresError("fail"))
        repo = PostgresSagaStateRepository(pool=pool)

        with pytest.raises(RepositoryError, match="Failed to delete"):
            await repo.delete(str(uuid.uuid4()))


class TestPostgresSagaStateRepositoryExists:
    async def test_exists_true(self):
        pool, conn = _mock_pool()
        conn.fetchval = AsyncMock(return_value=True)
        repo = PostgresSagaStateRepository(pool=pool)

        result = await repo.exists(str(uuid.uuid4()))
        assert result is True

    async def test_exists_false(self):
        pool, conn = _mock_pool()
        conn.fetchval = AsyncMock(return_value=False)
        repo = PostgresSagaStateRepository(pool=pool)

        result = await repo.exists(str(uuid.uuid4()))
        assert result is False

    async def test_exists_postgres_error(self):
        import asyncpg as real_asyncpg

        pool, conn = _mock_pool()
        conn.fetchval = AsyncMock(side_effect=real_asyncpg.PostgresError("fail"))
        repo = PostgresSagaStateRepository(pool=pool)

        with pytest.raises(RepositoryError, match="Failed to check"):
            await repo.exists(str(uuid.uuid4()))


class TestPostgresSagaStateRepositoryRowConversions:
    def test_row_to_saga_with_string_json_fields(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)

        saga_id = uuid.uuid4()
        corr_id = uuid.uuid4()
        step_dict = {
            "step_id": str(uuid.uuid4()),
            "step_name": "s1",
            "step_index": 0,
            "state": "COMPLETED",
            "input_data": {},
            "output_data": None,
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "duration_ms": 0.0,
            "retry_count": 0,
            "max_retries": 3,
            "timeout_ms": 30000,
            "dependencies": [],
            "compensation": None,
            "metadata": {},
            "constitutional_hash": "608508a9bd224290",
        }
        comp_dict = {
            "compensation_id": str(uuid.uuid4()),
            "step_id": "s1",
            "step_name": "s1",
            "executed": False,
        }
        row = {
            "saga_id": saga_id,
            "saga_name": "test",
            "tenant_id": "t1",
            "correlation_id": corr_id,
            "state": "RUNNING",
            "compensation_strategy": "PARALLEL",
            "current_step_index": 1,
            "version": 3,
            "steps": json.dumps([step_dict]),
            "context": json.dumps({"key": "val"}),
            "metadata": json.dumps({"m": 1}),
            "compensation_log": json.dumps([comp_dict]),
            "created_at": datetime.now(UTC),
            "started_at": datetime.now(UTC),
            "completed_at": None,
            "failed_at": None,
            "compensated_at": None,
            "total_duration_ms": 100.0,
            "failure_reason": None,
            "timeout_ms": 300000,
            "constitutional_hash": "608508a9bd224290",
        }

        result = repo._row_to_saga(row)
        assert result.saga_name == "test"
        assert result.state == SagaState.RUNNING
        assert result.compensation_strategy == CompensationStrategy.PARALLEL
        assert len(result.steps) == 1
        assert len(result.compensation_log) == 1
        assert result.context == {"key": "val"}
        assert result.metadata == {"m": 1}

    def test_row_to_saga_with_none_json_fields(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)

        row = {
            "saga_id": uuid.uuid4(),
            "saga_name": "test",
            "tenant_id": "t1",
            "correlation_id": uuid.uuid4(),
            "state": "INITIALIZED",
            "compensation_strategy": "LIFO",
            "current_step_index": 0,
            "version": 1,
            "steps": None,
            "context": None,
            "metadata": None,
            "compensation_log": None,
            "created_at": datetime.now(UTC),
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "compensated_at": None,
            "total_duration_ms": 0.0,
            "failure_reason": None,
            "timeout_ms": 300000,
            "constitutional_hash": "608508a9bd224290",
        }

        result = repo._row_to_saga(row)
        assert result.steps == []
        assert result.context == {}
        assert result.metadata == {}
        assert result.compensation_log == []

    def test_row_to_saga_with_dict_fields(self):
        """When asyncpg returns already-parsed dicts (JSONB)."""
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)

        row = {
            "saga_id": uuid.uuid4(),
            "saga_name": "test",
            "tenant_id": "t1",
            "correlation_id": uuid.uuid4(),
            "state": "INITIALIZED",
            "compensation_strategy": "LIFO",
            "current_step_index": 0,
            "version": 1,
            "steps": [],
            "context": {"already": "parsed"},
            "metadata": {"m": 2},
            "compensation_log": [],
            "created_at": datetime.now(UTC),
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "compensated_at": None,
            "total_duration_ms": 0.0,
            "failure_reason": None,
            "timeout_ms": 300000,
            "constitutional_hash": "608508a9bd224290",
        }

        result = repo._row_to_saga(row)
        assert result.context == {"already": "parsed"}

    def test_row_to_checkpoint_with_string_json(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)

        row = {
            "checkpoint_id": uuid.uuid4(),
            "saga_id": uuid.uuid4(),
            "checkpoint_name": "cp1",
            "state_snapshot": json.dumps({"snap": True}),
            "completed_step_ids": json.dumps(["s1", "s2"]),
            "pending_step_ids": json.dumps(["s3"]),
            "created_at": datetime.now(UTC),
            "is_constitutional": True,
            "metadata": json.dumps({"key": "val"}),
            "constitutional_hash": "608508a9bd224290",
        }

        result = repo._row_to_checkpoint(row)
        assert isinstance(result, SagaCheckpoint)
        assert result.checkpoint_name == "cp1"
        assert result.state_snapshot == {"snap": True}
        assert result.completed_step_ids == ["s1", "s2"]
        assert result.pending_step_ids == ["s3"]
        assert result.is_constitutional is True
        assert result.metadata == {"key": "val"}

    def test_row_to_checkpoint_with_none_fields(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)

        row = {
            "checkpoint_id": uuid.uuid4(),
            "saga_id": uuid.uuid4(),
            "checkpoint_name": "cp2",
            "state_snapshot": None,
            "completed_step_ids": None,
            "pending_step_ids": None,
            "created_at": datetime.now(UTC),
            "is_constitutional": False,
            "metadata": None,
            "constitutional_hash": "608508a9bd224290",
        }

        result = repo._row_to_checkpoint(row)
        assert result.state_snapshot == {}
        assert result.completed_step_ids == []
        assert result.pending_step_ids == []
        assert result.metadata == {}

    def test_row_to_checkpoint_with_dict_fields(self):
        pool = MagicMock()
        repo = PostgresSagaStateRepository(pool=pool)

        row = {
            "checkpoint_id": uuid.uuid4(),
            "saga_id": uuid.uuid4(),
            "checkpoint_name": "cp3",
            "state_snapshot": {"already": "dict"},
            "completed_step_ids": ["a"],
            "pending_step_ids": ["b"],
            "created_at": datetime.now(UTC),
            "is_constitutional": False,
            "metadata": {"k": 1},
            "constitutional_hash": "608508a9bd224290",
        }

        result = repo._row_to_checkpoint(row)
        assert result.state_snapshot == {"already": "dict"}


# ---------------------------------------------------------------------------
# 2. health_aggregator.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.health_aggregator import (
    HealthAggregator,
    HealthAggregatorConfig,
    HealthSnapshot,
    SystemHealthReport,
    SystemHealthStatus,
    get_health_aggregator,
    reset_health_aggregator,
)


class TestHealthAggregatorConfig:
    def test_defaults(self):
        config = HealthAggregatorConfig()
        assert config.enabled is True
        assert config.degraded_threshold == 0.7
        assert config.critical_threshold == 0.5
        assert config.max_history_size == 300

    def test_custom(self):
        config = HealthAggregatorConfig(
            enabled=False,
            degraded_threshold=0.8,
            critical_threshold=0.4,
        )
        assert config.enabled is False
        assert config.degraded_threshold == 0.8


class TestHealthSnapshot:
    def test_to_dict(self):
        now = datetime.now(UTC)
        snap = HealthSnapshot(
            timestamp=now,
            status=SystemHealthStatus.HEALTHY,
            health_score=0.95,
            total_breakers=3,
            closed_breakers=3,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={"svc1": "closed"},
        )
        d = snap.to_dict()
        assert d["status"] == "healthy"
        assert d["health_score"] == 0.95
        assert d["total_breakers"] == 3


class TestSystemHealthReport:
    def test_to_dict(self):
        now = datetime.now(UTC)
        report = SystemHealthReport(
            status=SystemHealthStatus.DEGRADED,
            health_score=0.65,
            timestamp=now,
            total_breakers=4,
            closed_breakers=2,
            half_open_breakers=1,
            open_breakers=1,
            circuit_details={"svc1": {"state": "open"}},
            degraded_services=["svc2"],
            critical_services=["svc1"],
        )
        d = report.to_dict()
        assert d["status"] == "degraded"
        assert d["degraded_services"] == ["svc2"]
        assert d["critical_services"] == ["svc1"]


class TestHealthAggregator:
    def test_init_no_circuit_breaker(self):
        with patch(
            "enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE",
            False,
        ):
            agg = HealthAggregator()
            report = agg.get_system_health()
            assert report.status == SystemHealthStatus.UNKNOWN

    async def test_start_disabled(self):
        config = HealthAggregatorConfig(enabled=False)
        agg = HealthAggregator(config=config)
        await agg.start()
        assert agg._running is False

    async def test_start_no_circuit_breaker(self):
        with patch(
            "enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE",
            False,
        ):
            agg = HealthAggregator()
            await agg.start()
            assert agg._running is False

    async def test_start_already_running(self):
        agg = HealthAggregator()
        agg._running = True
        old_task = agg._health_check_task
        await agg.start()
        assert agg._health_check_task is old_task

    async def test_stop(self):
        config = HealthAggregatorConfig(enabled=False)
        agg = HealthAggregator(config=config, registry=MagicMock())
        agg._running = True

        # Create a real cancelled task to test stop logic
        async def noop():
            await asyncio.sleep(100)

        task = asyncio.create_task(noop())
        agg._health_check_task = task
        await agg.stop()
        assert agg._running is False
        assert task.cancelled()

    def test_register_and_unregister_breaker(self):
        agg = HealthAggregator()
        breaker = MagicMock()
        breaker.current_state = "closed"
        agg.register_circuit_breaker("svc1", breaker)
        assert "svc1" in agg._custom_breakers
        agg.unregister_circuit_breaker("svc1")
        assert "svc1" not in agg._custom_breakers

    def test_unregister_nonexistent(self):
        agg = HealthAggregator()
        # Should not raise
        agg.unregister_circuit_breaker("nonexistent")

    def test_on_health_change(self):
        agg = HealthAggregator()

        def my_callback(report):
            pass

        agg.on_health_change(my_callback)
        assert my_callback in agg._health_change_callbacks

    def test_calculate_health_score_no_breakers(self):
        agg = HealthAggregator()
        assert agg._calculate_health_score(0, 0, 0, 0) == 1.0

    def test_calculate_health_score_mixed(self):
        agg = HealthAggregator()
        # 2 closed, 1 half-open, 1 open = (2*1.0 + 1*0.5 + 0) / 4 = 0.625
        score = agg._calculate_health_score(4, 2, 1, 1)
        assert abs(score - 0.625) < 0.001

    def test_determine_health_status_healthy(self):
        agg = HealthAggregator()
        assert agg._determine_health_status(0.9) == SystemHealthStatus.HEALTHY

    def test_determine_health_status_degraded(self):
        agg = HealthAggregator()
        assert agg._determine_health_status(0.6) == SystemHealthStatus.DEGRADED

    def test_determine_health_status_critical(self):
        agg = HealthAggregator()
        assert agg._determine_health_status(0.3) == SystemHealthStatus.CRITICAL

    def test_get_health_history_empty(self):
        agg = HealthAggregator()
        assert agg.get_health_history() == []

    def test_get_health_history_with_snapshots(self):
        agg = HealthAggregator()
        now = datetime.now(UTC)
        snap = HealthSnapshot(
            timestamp=now,
            status=SystemHealthStatus.HEALTHY,
            health_score=1.0,
            total_breakers=0,
            closed_breakers=0,
            half_open_breakers=0,
            open_breakers=0,
            circuit_states={},
        )
        agg._health_history.append(snap)
        result = agg.get_health_history(window_minutes=10)
        assert len(result) == 1

    def test_get_metrics(self):
        with patch(
            "enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE",
            False,
        ):
            agg = HealthAggregator()
            metrics = agg.get_metrics()
            assert "snapshots_collected" in metrics
            assert "running" in metrics
            assert metrics["running"] is False

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True)
    @patch("enhanced_agent_bus.health_aggregator.pybreaker")
    async def test_collect_health_snapshot_fires_callback(self, mock_pybreaker):
        mock_pybreaker.STATE_CLOSED = "closed"
        mock_pybreaker.STATE_HALF_OPEN = "half_open"
        mock_pybreaker.STATE_OPEN = "open"

        agg = HealthAggregator(registry=MagicMock(), config=HealthAggregatorConfig())
        agg._registry = None
        agg._custom_breakers = {}
        agg._last_status = None

        callback_called = []

        def my_callback(report):
            callback_called.append(report)

        agg.on_health_change(my_callback)
        await agg._collect_health_snapshot()

        assert agg._snapshots_collected == 1
        assert len(callback_called) == 0  # callback is fire-and-forget via task
        assert agg._callbacks_fired == 1
        # Wait for background tasks
        for task in list(agg._background_tasks):
            await task

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", False)
    async def test_collect_health_snapshot_no_breaker(self):
        agg = HealthAggregator()
        await agg._collect_health_snapshot()
        assert agg._snapshots_collected == 0

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True)
    @patch("enhanced_agent_bus.health_aggregator.pybreaker")
    async def test_collect_breaker_state(self, mock_pybreaker):
        mock_pybreaker.STATE_CLOSED = "closed"
        mock_pybreaker.STATE_HALF_OPEN = "half_open"
        mock_pybreaker.STATE_OPEN = "open"

        agg = HealthAggregator(registry=MagicMock())
        details = {}
        counts = [0, 0, 0]

        agg._collect_breaker_state("svc1", "closed", 0, 5, details, counts)
        assert counts == [1, 0, 0]
        assert details["svc1"]["state"] == "closed"

        agg._collect_breaker_state("svc2", "half_open", 2, 0, details, counts)
        assert counts == [1, 1, 0]

        agg._collect_breaker_state("svc3", "open", 5, 0, details, counts)
        assert counts == [1, 1, 1]

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True)
    @patch("enhanced_agent_bus.health_aggregator.pybreaker")
    def test_get_system_health_with_custom_breakers(self, mock_pybreaker):
        mock_pybreaker.STATE_CLOSED = "closed"
        mock_pybreaker.STATE_HALF_OPEN = "half_open"
        mock_pybreaker.STATE_OPEN = "open"

        agg = HealthAggregator(registry=MagicMock())
        agg._registry = None

        breaker = MagicMock()
        breaker.current_state = "closed"
        breaker.fail_counter = 0
        breaker.success_counter = 10
        agg.register_circuit_breaker("svc_custom", breaker)

        report = agg.get_system_health()
        assert report.total_breakers == 1
        assert report.closed_breakers == 1

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True)
    @patch("enhanced_agent_bus.health_aggregator.pybreaker")
    def test_get_system_health_with_registry(self, mock_pybreaker):
        mock_pybreaker.STATE_CLOSED = "closed"
        mock_pybreaker.STATE_HALF_OPEN = "half_open"
        mock_pybreaker.STATE_OPEN = "open"

        registry = MagicMock()
        registry.get_all_states.return_value = {
            "svc1": {"state": "closed", "fail_counter": 0, "success_counter": 5},
            "svc2": {"state": "open", "fail_counter": 3},
        }

        agg = HealthAggregator(registry=registry)
        report = agg.get_system_health()
        assert report.total_breakers == 2
        assert report.closed_breakers == 1
        assert report.open_breakers == 1
        assert "svc2" in report.critical_services

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True)
    @patch("enhanced_agent_bus.health_aggregator.pybreaker")
    async def test_invoke_callback_async(self, mock_pybreaker):
        agg = HealthAggregator(registry=MagicMock())

        async def async_callback(report):
            pass

        report = MagicMock()
        await agg._invoke_callback(async_callback, report)

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True)
    @patch("enhanced_agent_bus.health_aggregator.pybreaker")
    async def test_invoke_callback_error(self, mock_pybreaker):
        agg = HealthAggregator(registry=MagicMock())

        def failing_callback(report):
            raise RuntimeError("callback boom")

        report = MagicMock()
        # Should not raise, just log
        await agg._invoke_callback(failing_callback, report)

    @patch("enhanced_agent_bus.health_aggregator.CIRCUIT_BREAKER_AVAILABLE", True)
    @patch("enhanced_agent_bus.health_aggregator.pybreaker")
    async def test_health_check_loop_cancelled(self, mock_pybreaker):
        agg = HealthAggregator(
            config=HealthAggregatorConfig(health_check_interval_seconds=0.01),
            registry=MagicMock(),
        )
        agg._running = True

        async def stop_after_delay():
            await asyncio.sleep(0.05)
            agg._running = False

        task = asyncio.create_task(agg._health_check_loop())
        stopper = asyncio.create_task(stop_after_delay())
        await stopper
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestHealthAggregatorSingleton:
    def test_get_and_reset(self):
        reset_health_aggregator()
        agg1 = get_health_aggregator()
        agg2 = get_health_aggregator()
        assert agg1 is agg2
        reset_health_aggregator()
        agg3 = get_health_aggregator()
        assert agg3 is not agg1


# ---------------------------------------------------------------------------
# 3. specs/fixtures/observability.py
# ---------------------------------------------------------------------------

# Import Layer from the fixtures module (uses fallback if observability not available)
from enhanced_agent_bus.specs.fixtures.observability import (
    LatencyMeasurement,
    Layer,
    SpecMetricsRegistry,
    SpecTimeoutBudgetManager,
)


class TestLatencyMeasurement:
    def test_to_dict(self):
        m = LatencyMeasurement(
            layer="layer1_validation",
            operation="validate",
            latency_ms=3.5,
            within_budget=True,
            budget_ms=5.0,
        )
        d = m.to_dict()
        assert d["layer"] == "layer1_validation"
        assert d["latency_ms"] == 3.5
        assert "constitutional_hash" in d


class TestSpecTimeoutBudgetManager:
    def test_record_measurement_within_budget(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 2.0)
        assert m.within_budget is True
        assert m.budget_ms is not None

    def test_record_measurement_exceeds_budget(self):
        mgr = SpecTimeoutBudgetManager()
        # Layer1 budget is 5.0ms
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 100.0)
        assert m.within_budget is False

    def test_get_measurements_by_layer(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 2.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op2", 10.0)
        result = mgr.get_measurements_by_layer(Layer.LAYER1_VALIDATION)
        assert len(result) == 1
        assert result[0].operation == "op1"

    def test_get_budget_violations(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 2.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op2", 999.0)
        violations = mgr.get_budget_violations()
        assert len(violations) == 1
        assert violations[0].operation == "op2"

    def test_calculate_percentile(self):
        mgr = SpecTimeoutBudgetManager()
        for i in range(10):
            mgr.record_measurement(Layer.LAYER1_VALIDATION, f"op{i}", float(i))
        p50 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        assert p50 is not None
        assert 4.0 <= p50 <= 5.0

    def test_calculate_percentile_empty(self):
        mgr = SpecTimeoutBudgetManager()
        result = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        assert result is None

    def test_verify_budget_compliance_all_compliant(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op2", 5.0)
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is True
        assert report["violations"] == 0

    def test_verify_budget_compliance_with_violations(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 999.0)
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is False
        assert report["violations"] == 1

    def test_clear_measurements(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 1.0)
        mgr.clear_measurements()
        assert len(mgr.measurements) == 0


class TestSpecMetricsRegistry:
    def test_record_event(self):
        reg = SpecMetricsRegistry()
        reg.record_event("my_metric", 42.0, "gauge")
        assert len(reg.metric_events) == 1
        assert reg.metric_events[0]["metric_name"] == "my_metric"

    def test_increment_counter(self):
        reg = SpecMetricsRegistry()
        reg.increment_counter("requests", 5)
        assert reg.get_counter_total("requests") == 5

    def test_record_latency(self):
        reg = SpecMetricsRegistry()
        reg.record_latency("response_time", 12.5)
        events = reg.get_events_by_name("response_time")
        assert len(events) == 1
        assert events[0]["type"] == "histogram"

    def test_get_events_by_name(self):
        reg = SpecMetricsRegistry()
        reg.record_event("a", 1.0, "counter")
        reg.record_event("b", 2.0, "gauge")
        reg.record_event("a", 3.0, "counter")
        assert len(reg.get_events_by_name("a")) == 2
        assert len(reg.get_events_by_name("b")) == 1

    def test_get_counter_total_multiple(self):
        reg = SpecMetricsRegistry()
        reg.increment_counter("hits", 3)
        reg.increment_counter("hits", 7)
        assert reg.get_counter_total("hits") == 10

    def test_clear_events(self):
        reg = SpecMetricsRegistry()
        reg.record_event("x", 1.0, "counter")
        reg.clear_events()
        assert len(reg.metric_events) == 0


class TestFallbackClasses:
    """Test the fallback classes defined when observability imports fail."""

    def test_layer_enum_values(self):
        assert Layer.LAYER1_VALIDATION.value == "layer1_validation"
        assert Layer.LAYER4_AUDIT.value == "layer4_audit"

    def test_timeout_budget_manager_get_layer_budget(self):
        mgr = SpecTimeoutBudgetManager()
        budget = mgr.get_layer_budget(Layer.LAYER1_VALIDATION)
        assert budget.budget_ms == 5.0
        assert budget.layer == Layer.LAYER1_VALIDATION

    def test_metrics_registry_base_increment(self):
        reg = SpecMetricsRegistry(service_name="test")
        reg.increment_counter("c1", 2)
        # Verify via our spec-layer counter total
        assert reg.get_counter_total("c1") == 2


# ---------------------------------------------------------------------------
# 4. components/agent_registry_manager.py
# ---------------------------------------------------------------------------

from enhanced_agent_bus.components.agent_registry_manager import (
    AgentRegistryManager,
)


class TestAgentRegistryManagerInit:
    def test_init_with_custom_registry(self):
        registry = MagicMock()
        mgr = AgentRegistryManager(registry=registry)
        assert mgr._registry is registry

    def test_init_with_redis_url(self):
        with patch(
            "enhanced_agent_bus.components.agent_registry_manager.RedisAgentRegistry"
        ) as mock_redis:
            mock_redis.return_value = MagicMock()
            mgr = AgentRegistryManager(registry=None, redis_url="redis://localhost:6379")
            mock_redis.assert_called_once_with(redis_url="redis://localhost:6379")

    def test_init_fallback_inmemory(self):
        with patch(
            "enhanced_agent_bus.components.agent_registry_manager.InMemoryAgentRegistry"
        ) as mock_mem:
            mock_mem.return_value = MagicMock()
            mgr = AgentRegistryManager(registry=None, redis_url="")
            mock_mem.assert_called_once()


class TestAgentRegistryManagerRegister:
    async def test_register_agent(self):
        registry = MagicMock()
        registry._agents = {}
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.register_agent(
            agent_id="a1",
            agent_type="worker",
            capabilities=["cap1"],
            metadata={"key": "val"},
            tenant_id="t1",
        )
        assert result is True
        assert registry._agents["a1"]["agent_type"] == "worker"
        assert registry._agents["a1"]["capabilities"] == ["cap1"]

    async def test_register_agent_defaults(self):
        registry = MagicMock()
        registry._agents = {}
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.register_agent(agent_id="a2", agent_type="validator")
        assert result is True
        assert registry._agents["a2"]["capabilities"] == []
        assert registry._agents["a2"]["metadata"] == {}

    async def test_register_agent_error(self):
        registry = MagicMock()
        registry._agents = MagicMock()
        registry._agents.__setitem__ = MagicMock(side_effect=RuntimeError("fail"))
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.register_agent(agent_id="a3", agent_type="worker")
        assert result is False


class TestAgentRegistryManagerUnregister:
    async def test_unregister_existing(self):
        registry = MagicMock()
        registry._agents = {"a1": {"agent_id": "a1"}}
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.unregister_agent("a1")
        assert result is True
        assert "a1" not in registry._agents

    async def test_unregister_not_found(self):
        registry = MagicMock()
        registry._agents = {}
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.unregister_agent("nonexistent")
        assert result is False

    async def test_unregister_no_agents_attr(self):
        registry = MagicMock(spec=[])
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.unregister_agent("a1")
        assert result is False

    async def test_unregister_error(self):
        registry = MagicMock()
        # Make __contains__ raise
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.unregister_agent("a1")
        assert result is False


class TestAgentRegistryManagerGetInfo:
    def test_get_agent_info_found(self):
        registry = MagicMock()
        registry._agents = {"a1": {"agent_id": "a1", "status": "active"}}
        mgr = AgentRegistryManager(registry=registry)
        info = mgr.get_agent_info("a1")
        assert info["agent_id"] == "a1"

    def test_get_agent_info_not_found(self):
        registry = MagicMock()
        registry._agents = {}
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_agent_info("nonexistent") is None

    def test_get_agent_info_no_agents(self):
        registry = MagicMock(spec=[])
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_agent_info("a1") is None

    def test_get_agent_info_error(self):
        registry = MagicMock()
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_agent_info("a1") is None


class TestAgentRegistryManagerQueries:
    def _make_mgr(self):
        registry = MagicMock()
        registry._agents = {
            "a1": {
                "agent_type": "worker",
                "capabilities": ["cap1", "cap2"],
                "tenant_id": "t1",
                "status": "active",
            },
            "a2": {
                "agent_type": "validator",
                "capabilities": ["cap1"],
                "tenant_id": "t2",
                "status": "active",
            },
            "a3": {
                "agent_type": "worker",
                "capabilities": ["cap3"],
                "tenant_id": "t1",
                "status": "inactive",
            },
        }
        return AgentRegistryManager(registry=registry)

    def test_get_registered_agents(self):
        mgr = self._make_mgr()
        agents = mgr.get_registered_agents()
        assert set(agents) == {"a1", "a2", "a3"}

    def test_get_registered_agents_empty(self):
        registry = MagicMock(spec=[])
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_registered_agents() == []

    def test_get_registered_agents_error(self):
        registry = MagicMock()
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_registered_agents() == []

    def test_get_agents_by_type(self):
        mgr = self._make_mgr()
        workers = mgr.get_agents_by_type("worker")
        assert set(workers) == {"a1", "a3"}
        validators = mgr.get_agents_by_type("validator")
        assert validators == ["a2"]

    def test_get_agents_by_type_error(self):
        registry = MagicMock()
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_agents_by_type("worker") == []

    def test_get_agents_by_capability(self):
        mgr = self._make_mgr()
        result = mgr.get_agents_by_capability("cap1")
        assert set(result) == {"a1", "a2"}

    def test_get_agents_by_capability_error(self):
        registry = MagicMock()
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_agents_by_capability("cap1") == []

    def test_get_agents_by_tenant(self):
        mgr = self._make_mgr()
        result = mgr.get_agents_by_tenant("t1")
        assert set(result) == {"a1", "a3"}

    def test_get_agents_by_tenant_error(self):
        registry = MagicMock()
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        assert mgr.get_agents_by_tenant("t1") == []


class TestAgentRegistryManagerUpdateStatus:
    async def test_update_status_success(self):
        registry = MagicMock()
        registry._agents = {"a1": {"status": "active"}}
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.update_agent_status("a1", "inactive")
        assert result is True
        assert registry._agents["a1"]["status"] == "inactive"

    async def test_update_status_not_found(self):
        registry = MagicMock()
        registry._agents = {}
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.update_agent_status("nonexistent", "inactive")
        assert result is False

    async def test_update_status_error(self):
        registry = MagicMock()
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        result = await mgr.update_agent_status("a1", "inactive")
        assert result is False


class TestAgentRegistryManagerStats:
    def test_get_registry_stats(self):
        registry = MagicMock()
        registry._agents = {
            "a1": {"agent_type": "worker", "status": "active"},
            "a2": {"agent_type": "validator", "status": "active"},
            "a3": {"agent_type": "worker", "status": "inactive"},
        }
        mgr = AgentRegistryManager(registry=registry)
        stats = mgr.get_registry_stats()
        assert stats["total_agents"] == 3
        assert stats["agents_by_type"]["worker"] == 2
        assert stats["agents_by_type"]["validator"] == 1
        assert stats["agents_by_status"]["active"] == 2
        assert stats["agents_by_status"]["inactive"] == 1

    def test_get_registry_stats_no_agents(self):
        registry = MagicMock(spec=[])
        mgr = AgentRegistryManager(registry=registry)
        stats = mgr.get_registry_stats()
        assert stats["total_agents"] == 0

    def test_get_registry_stats_error(self):
        registry = MagicMock()
        type(registry)._agents = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
        mgr = AgentRegistryManager(registry=registry)
        stats = mgr.get_registry_stats()
        assert "error" in stats

    def test_cleanup_inactive_agents(self):
        registry = MagicMock()
        mgr = AgentRegistryManager(registry=registry)
        result = mgr.cleanup_inactive_agents(max_age_hours=12)
        assert result == 0
