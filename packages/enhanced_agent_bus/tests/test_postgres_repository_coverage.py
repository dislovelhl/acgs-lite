# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for PostgresWorkflowRepository.

Targets ≥95% line coverage of:
  src/core/enhanced_agent_bus/persistence/postgres_repository.py

Coverage invocation:
  python -m pytest <this file> \\
    --cov=src/core/enhanced_agent_bus/persistence/postgres_repository \\
    --cov-report=term-missing --import-mode=importlib -q

Strategy
--------
- asyncpg_module is patched via patch.dict on the live module dict.
- All DB interactions go through an async mock pool / connection — no real DB.
- The module is imported eagerly at module level so coverage instruments it.
"""

from __future__ import annotations

import sys
import types
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject a minimal asyncpg stub so the module can be imported without the
# real asyncpg package.  Must happen BEFORE the first import of the module.
# ---------------------------------------------------------------------------

_asyncpg_stub = types.ModuleType("asyncpg")


class _PostgresError(Exception):
    pass


class _UniqueViolationError(_PostgresError):
    pass


class _Record(dict):
    """Dict-backed stub for asyncpg.Record."""

    def __getitem__(self, key: str) -> Any:  # type: ignore[override]
        return super().__getitem__(key)


_asyncpg_stub.PostgresError = _PostgresError  # type: ignore[attr-defined]
_asyncpg_stub.UniqueViolationError = _UniqueViolationError  # type: ignore[attr-defined]
_asyncpg_stub.Record = _Record  # type: ignore[attr-defined]
_asyncpg_stub.Pool = MagicMock  # type: ignore[attr-defined]
_asyncpg_stub.Connection = MagicMock  # type: ignore[attr-defined]

if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = _asyncpg_stub

# ---------------------------------------------------------------------------
# Eager import — coverage must instrument the module before any test runs.
# ---------------------------------------------------------------------------
# Model imports
# ---------------------------------------------------------------------------
from uuid import UUID, uuid4

import enhanced_agent_bus.persistence.postgres_repository as _pg_repo_module
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.persistence.models import (
    CheckpointData,
    EventType,
    StepStatus,
    StepType,
    WorkflowCompensation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from enhanced_agent_bus.persistence.postgres_repository import (
    SCHEMA_SQL,
    PostgresWorkflowRepository,
)

# Under pytest's importlib import mode the module object that ``_pg_repo_module``
# points to may be a *different* object from the one whose ``__dict__`` is used
# as ``__globals__`` by the class methods.  Obtain the canonical globals dict so
# that ``patch.dict`` actually affects runtime behaviour.
_pg_globals: dict = PostgresWorkflowRepository.__init__.__globals__  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOW = datetime.now(UTC)
TENANT = "tenant-abc"


# ---------------------------------------------------------------------------
# Data builder helpers
# ---------------------------------------------------------------------------


def _make_workflow(**kwargs: Any) -> WorkflowInstance:
    defaults: dict[str, Any] = dict(
        workflow_type="test_wf",
        workflow_id="wf-001",
        tenant_id=TENANT,
        constitutional_hash=CONSTITUTIONAL_HASH,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(kwargs)
    return WorkflowInstance(**defaults)


def _make_step(workflow_instance_id: Any = None, **kwargs: Any) -> WorkflowStep:
    defaults: dict[str, Any] = dict(
        workflow_instance_id=workflow_instance_id or uuid4(),
        step_name="step1",
        step_type=StepType.ACTIVITY,
        created_at=NOW,
    )
    defaults.update(kwargs)
    return WorkflowStep(**defaults)


def _make_event(workflow_instance_id: Any = None, **kwargs: Any) -> WorkflowEvent:
    defaults: dict[str, Any] = dict(
        workflow_instance_id=workflow_instance_id or uuid4(),
        event_type=EventType.WORKFLOW_STARTED,
        event_data={"key": "value"},
        sequence_number=1,
        timestamp=NOW,
    )
    defaults.update(kwargs)
    return WorkflowEvent(**defaults)


def _make_compensation(
    workflow_instance_id: Any = None, step_id: Any = None, **kwargs: Any
) -> WorkflowCompensation:
    defaults: dict[str, Any] = dict(
        workflow_instance_id=workflow_instance_id or uuid4(),
        step_id=step_id or uuid4(),
        compensation_name="rollback",
        created_at=NOW,
    )
    defaults.update(kwargs)
    return WorkflowCompensation(**defaults)


def _make_checkpoint(workflow_instance_id: Any = None, **kwargs: Any) -> CheckpointData:
    defaults: dict[str, Any] = dict(
        workflow_instance_id=workflow_instance_id or uuid4(),
        step_index=2,
        state={"foo": "bar"},
        created_at=NOW,
    )
    defaults.update(kwargs)
    return CheckpointData(**defaults)


def _make_wf_record(wf: WorkflowInstance) -> _Record:
    return _Record(
        id=wf.id,
        workflow_type=wf.workflow_type,
        workflow_id=wf.workflow_id,
        tenant_id=wf.tenant_id,
        status=wf.status if isinstance(wf.status, str) else wf.status.value,
        input=wf.input,
        output=wf.output,
        error=wf.error,
        started_at=wf.started_at,
        completed_at=wf.completed_at,
        constitutional_hash=wf.constitutional_hash,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
    )


def _make_step_record(step: WorkflowStep) -> _Record:
    return _Record(
        id=step.id,
        workflow_instance_id=step.workflow_instance_id,
        step_name=step.step_name,
        step_type=step.step_type if isinstance(step.step_type, str) else step.step_type.value,
        status=step.status if isinstance(step.status, str) else step.status.value,
        input=step.input,
        output=step.output,
        error=step.error,
        idempotency_key=step.idempotency_key,
        attempt_count=step.attempt_count,
        started_at=step.started_at,
        completed_at=step.completed_at,
        created_at=step.created_at,
    )


def _make_event_record(event: WorkflowEvent) -> _Record:
    return _Record(
        id=event.id,
        workflow_instance_id=event.workflow_instance_id,
        event_type=(
            event.event_type if isinstance(event.event_type, str) else event.event_type.value
        ),
        event_data=event.event_data,
        sequence_number=event.sequence_number,
        timestamp=event.timestamp,
    )


def _make_compensation_record(comp: WorkflowCompensation) -> _Record:
    return _Record(
        id=comp.id,
        workflow_instance_id=comp.workflow_instance_id,
        step_id=comp.step_id,
        compensation_name=comp.compensation_name,
        status=comp.status if isinstance(comp.status, str) else comp.status.value,
        input=comp.input,
        output=comp.output,
        error=comp.error,
        executed_at=comp.executed_at,
        created_at=comp.created_at,
    )


def _make_checkpoint_record(cp: CheckpointData) -> _Record:
    return _Record(
        id=cp.checkpoint_id,
        workflow_instance_id=cp.workflow_instance_id,
        step_index=cp.step_index,
        state=cp.state,
        created_at=cp.created_at,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_conn() -> AsyncMock:
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=1)
    return conn


@pytest.fixture
def mock_pool(mock_conn: AsyncMock) -> MagicMock:
    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():  # type: ignore[return]
        yield mock_conn

    pool.acquire = _acquire
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def repo(mock_pool: MagicMock):
    """Return a repository instance backed by a mock pool."""
    mock_asyncpg = MagicMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

    with patch.dict(_pg_globals, {"asyncpg_module": mock_asyncpg}):
        r = PostgresWorkflowRepository.__new__(PostgresWorkflowRepository)
        r.dsn = "postgresql://localhost/test"
        r.min_connections = 2
        r.max_connections = 10
        r._pool = mock_pool
    return r


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_raises_when_asyncpg_missing(self) -> None:
        with patch.dict(_pg_globals, {"asyncpg_module": None}):
            with pytest.raises(ImportError, match="asyncpg required"):
                PostgresWorkflowRepository("postgresql://localhost/test")

    def test_init_stores_dsn_and_pool_sizes(self) -> None:
        mock_asyncpg = MagicMock()
        with patch.dict(_pg_globals, {"asyncpg_module": mock_asyncpg}):
            r = PostgresWorkflowRepository("dsn://x", min_connections=3, max_connections=15)
        assert r.dsn == "dsn://x"
        assert r.min_connections == 3
        assert r.max_connections == 15
        assert r._pool is None

    def test_init_default_pool_sizes(self) -> None:
        mock_asyncpg = MagicMock()
        with patch.dict(_pg_globals, {"asyncpg_module": mock_asyncpg}):
            r = PostgresWorkflowRepository("dsn://y")
        assert r.min_connections == 5
        assert r.max_connections == 20


# ---------------------------------------------------------------------------
# initialize / close
# ---------------------------------------------------------------------------


class TestInitializeClose:
    async def test_initialize_creates_pool_and_executes_schema(
        self, mock_pool: MagicMock, mock_conn: AsyncMock
    ) -> None:
        mock_asyncpg = MagicMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        with patch.dict(_pg_globals, {"asyncpg_module": mock_asyncpg}):
            r = PostgresWorkflowRepository.__new__(PostgresWorkflowRepository)
            r.dsn = "dsn://x"
            r.min_connections = 2
            r.max_connections = 10
            r._pool = None
            await r.initialize()

        mock_asyncpg.create_pool.assert_awaited_once()
        mock_conn.execute.assert_awaited_once()  # SCHEMA_SQL

    async def test_initialize_passes_correct_pool_params(
        self, mock_pool: MagicMock, mock_conn: AsyncMock
    ) -> None:
        mock_asyncpg = MagicMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        with patch.dict(_pg_globals, {"asyncpg_module": mock_asyncpg}):
            r = PostgresWorkflowRepository.__new__(PostgresWorkflowRepository)
            r.dsn = "postgresql://myhost/mydb"
            r.min_connections = 3
            r.max_connections = 12
            r._pool = None
            await r.initialize()

        mock_asyncpg.create_pool.assert_awaited_once_with(
            "postgresql://myhost/mydb",
            min_size=3,
            max_size=12,
        )

    async def test_close_calls_pool_close(self, repo, mock_pool: MagicMock) -> None:
        await repo.close()
        mock_pool.close.assert_awaited_once()

    async def test_close_when_pool_is_none(self) -> None:
        mock_asyncpg = MagicMock()
        with patch.dict(_pg_globals, {"asyncpg_module": mock_asyncpg}):
            r = PostgresWorkflowRepository.__new__(PostgresWorkflowRepository)
            r._pool = None
        await r.close()  # must not raise


# ---------------------------------------------------------------------------
# _connection context manager
# ---------------------------------------------------------------------------


class TestConnection:
    async def test_connection_raises_when_not_initialized(self) -> None:
        mock_asyncpg = MagicMock()
        with patch.dict(_pg_globals, {"asyncpg_module": mock_asyncpg}):
            r = PostgresWorkflowRepository.__new__(PostgresWorkflowRepository)
            r._pool = None
        with pytest.raises(RuntimeError, match="not initialized"):
            async with r._connection():
                pass  # pragma: no cover

    async def test_connection_yields_conn(self, repo, mock_conn: AsyncMock) -> None:
        async with repo._connection() as conn:
            assert conn is mock_conn


# ---------------------------------------------------------------------------
# save_workflow / get_workflow
# ---------------------------------------------------------------------------


class TestSaveGetWorkflow:
    async def test_save_workflow_executes_upsert(self, repo, mock_conn: AsyncMock) -> None:
        wf = _make_workflow()
        await repo.save_workflow(wf)
        mock_conn.execute.assert_awaited_once()
        call_sql = mock_conn.execute.call_args[0][0]
        assert "workflow_instances" in call_sql
        assert "ON CONFLICT" in call_sql

    async def test_save_workflow_passes_instance_id(self, repo, mock_conn: AsyncMock) -> None:
        wf = _make_workflow()
        await repo.save_workflow(wf)
        args = mock_conn.execute.call_args[0]
        assert args[1] == wf.id

    async def test_save_workflow_passes_workflow_type(self, repo, mock_conn: AsyncMock) -> None:
        wf = _make_workflow(workflow_type="order_flow")
        await repo.save_workflow(wf)
        args = mock_conn.execute.call_args[0]
        assert args[2] == "order_flow"

    async def test_save_workflow_passes_constitutional_hash(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        wf = _make_workflow()
        await repo.save_workflow(wf)
        args = mock_conn.execute.call_args[0]
        # constitutional_hash is the 11th positional arg (index 11)
        assert CONSTITUTIONAL_HASH in args

    async def test_get_workflow_returns_none_when_not_found(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        mock_conn.fetchrow.return_value = None
        result = await repo.get_workflow(uuid4())
        assert result is None

    async def test_get_workflow_returns_instance_when_found(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        wf = _make_workflow()
        mock_conn.fetchrow.return_value = _make_wf_record(wf)
        result = await repo.get_workflow(wf.id)
        assert result is not None
        assert result.workflow_type == wf.workflow_type
        assert result.tenant_id == wf.tenant_id

    async def test_get_workflow_sql_selects_by_id(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchrow.return_value = None
        wid = uuid4()
        await repo.get_workflow(wid)
        sql = mock_conn.fetchrow.call_args[0][0]
        assert "workflow_instances" in sql
        assert "$1" in sql


# ---------------------------------------------------------------------------
# get_workflow_by_business_id
# ---------------------------------------------------------------------------


class TestGetWorkflowByBusinessId:
    async def test_returns_none_when_not_found(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchrow.return_value = None
        result = await repo.get_workflow_by_business_id("wf-999", TENANT)
        assert result is None

    async def test_returns_instance_when_found(self, repo, mock_conn: AsyncMock) -> None:
        wf = _make_workflow()
        mock_conn.fetchrow.return_value = _make_wf_record(wf)
        result = await repo.get_workflow_by_business_id(wf.workflow_id, TENANT)
        assert result is not None
        assert result.workflow_id == wf.workflow_id

    async def test_passes_both_params_to_db(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchrow.return_value = None
        await repo.get_workflow_by_business_id("biz-id", "my-tenant")
        args = mock_conn.fetchrow.call_args[0]
        assert "biz-id" in args
        assert "my-tenant" in args


# ---------------------------------------------------------------------------
# save_step / get_step_by_idempotency_key / get_steps
# ---------------------------------------------------------------------------


class TestSteps:
    async def test_save_step_executes_upsert(self, repo, mock_conn: AsyncMock) -> None:
        step = _make_step()
        await repo.save_step(step)
        mock_conn.execute.assert_awaited_once()
        call_sql = mock_conn.execute.call_args[0][0]
        assert "workflow_steps" in call_sql
        assert "ON CONFLICT" in call_sql

    async def test_save_step_passes_step_id(self, repo, mock_conn: AsyncMock) -> None:
        step = _make_step()
        await repo.save_step(step)
        args = mock_conn.execute.call_args[0]
        assert args[1] == step.id

    async def test_save_step_with_null_optional_fields(self, repo, mock_conn: AsyncMock) -> None:
        step = _make_step(error=None, output=None, started_at=None, completed_at=None)
        await repo.save_step(step)
        mock_conn.execute.assert_awaited_once()

    async def test_get_step_by_idempotency_key_returns_none(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        mock_conn.fetchrow.return_value = None
        result = await repo.get_step_by_idempotency_key(uuid4(), "key-1")
        assert result is None

    async def test_get_step_by_idempotency_key_returns_step(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        step = _make_step(idempotency_key="key-1")
        mock_conn.fetchrow.return_value = _make_step_record(step)
        result = await repo.get_step_by_idempotency_key(step.workflow_instance_id, "key-1")
        assert result is not None
        assert result.step_name == step.step_name

    async def test_get_step_sql_includes_idempotency_key(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchrow.return_value = None
        await repo.get_step_by_idempotency_key(uuid4(), "key-abc")
        sql = mock_conn.fetchrow.call_args[0][0]
        assert "idempotency_key" in sql

    async def test_get_steps_returns_empty_list(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        result = await repo.get_steps(uuid4())
        assert result == []

    async def test_get_steps_returns_multiple(self, repo, mock_conn: AsyncMock) -> None:
        wf_id = uuid4()
        step1 = _make_step(workflow_instance_id=wf_id, step_name="s1")
        step2 = _make_step(workflow_instance_id=wf_id, step_name="s2")
        mock_conn.fetch.return_value = [
            _make_step_record(step1),
            _make_step_record(step2),
        ]
        result = await repo.get_steps(wf_id)
        assert len(result) == 2

    async def test_get_steps_sql_orders_by_created_at(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        await repo.get_steps(uuid4())
        sql = mock_conn.fetch.call_args[0][0]
        assert "ORDER BY created_at" in sql


# ---------------------------------------------------------------------------
# save_event / get_events / get_next_sequence
# ---------------------------------------------------------------------------


class TestEvents:
    async def test_save_event_executes_insert(self, repo, mock_conn: AsyncMock) -> None:
        event = _make_event()
        await repo.save_event(event)
        mock_conn.execute.assert_awaited_once()
        call_sql = mock_conn.execute.call_args[0][0]
        assert "workflow_events" in call_sql

    async def test_save_event_passes_sequence_number(self, repo, mock_conn: AsyncMock) -> None:
        event = _make_event(sequence_number=9)
        await repo.save_event(event)
        args = mock_conn.execute.call_args[0]
        assert 9 in args

    async def test_get_events_returns_empty(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        result = await repo.get_events(uuid4())
        assert result == []

    async def test_get_events_with_limit_and_offset(self, repo, mock_conn: AsyncMock) -> None:
        event = _make_event()
        mock_conn.fetch.return_value = [_make_event_record(event)]
        result = await repo.get_events(event.workflow_instance_id, limit=10, offset=5)
        assert len(result) == 1
        call_args = mock_conn.fetch.call_args[0]
        assert 10 in call_args
        assert 5 in call_args

    async def test_get_events_default_limit_offset(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        wid = uuid4()
        await repo.get_events(wid)
        call_args = mock_conn.fetch.call_args[0]
        assert 100 in call_args
        assert 0 in call_args

    async def test_get_events_sql_orders_by_sequence(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        await repo.get_events(uuid4())
        sql = mock_conn.fetch.call_args[0][0]
        assert "sequence_number" in sql

    async def test_get_next_sequence_returns_value(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchval.return_value = 7
        result = await repo.get_next_sequence(uuid4())
        assert result == 7

    async def test_get_next_sequence_sql_uses_coalesce(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchval.return_value = 1
        await repo.get_next_sequence(uuid4())
        call_sql = mock_conn.fetchval.call_args[0][0]
        assert "COALESCE" in call_sql
        assert "MAX" in call_sql


# ---------------------------------------------------------------------------
# save_compensation / get_compensations
# ---------------------------------------------------------------------------


class TestCompensations:
    async def test_save_compensation_executes_upsert(self, repo, mock_conn: AsyncMock) -> None:
        comp = _make_compensation()
        await repo.save_compensation(comp)
        mock_conn.execute.assert_awaited_once()
        call_sql = mock_conn.execute.call_args[0][0]
        assert "workflow_compensations" in call_sql
        assert "ON CONFLICT" in call_sql

    async def test_save_compensation_passes_id(self, repo, mock_conn: AsyncMock) -> None:
        comp = _make_compensation()
        await repo.save_compensation(comp)
        args = mock_conn.execute.call_args[0]
        assert args[1] == comp.id

    async def test_get_compensations_returns_empty(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        result = await repo.get_compensations(uuid4())
        assert result == []

    async def test_get_compensations_returns_list(self, repo, mock_conn: AsyncMock) -> None:
        comp = _make_compensation()
        mock_conn.fetch.return_value = [_make_compensation_record(comp)]
        result = await repo.get_compensations(comp.workflow_instance_id)
        assert len(result) == 1
        assert result[0].compensation_name == "rollback"

    async def test_get_compensations_with_limit_offset(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        await repo.get_compensations(uuid4(), limit=5, offset=2)
        call_args = mock_conn.fetch.call_args[0]
        assert 5 in call_args
        assert 2 in call_args

    async def test_get_compensations_default_limit_offset(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        await repo.get_compensations(uuid4())
        call_args = mock_conn.fetch.call_args[0]
        assert 100 in call_args
        assert 0 in call_args


# ---------------------------------------------------------------------------
# save_checkpoint / get_latest_checkpoint
# ---------------------------------------------------------------------------


class TestCheckpoints:
    async def test_save_checkpoint_executes_insert(self, repo, mock_conn: AsyncMock) -> None:
        cp = _make_checkpoint()
        await repo.save_checkpoint(cp)
        mock_conn.execute.assert_awaited_once()
        call_sql = mock_conn.execute.call_args[0][0]
        assert "workflow_checkpoints" in call_sql

    async def test_save_checkpoint_uses_checkpoint_id(self, repo, mock_conn: AsyncMock) -> None:
        cp = _make_checkpoint()
        await repo.save_checkpoint(cp)
        args = mock_conn.execute.call_args[0]
        assert args[1] == cp.checkpoint_id

    async def test_save_checkpoint_passes_step_index(self, repo, mock_conn: AsyncMock) -> None:
        cp = _make_checkpoint(step_index=7)
        await repo.save_checkpoint(cp)
        args = mock_conn.execute.call_args[0]
        assert 7 in args

    async def test_get_latest_checkpoint_returns_none(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchrow.return_value = None
        result = await repo.get_latest_checkpoint(uuid4())
        assert result is None

    async def test_get_latest_checkpoint_returns_data(self, repo, mock_conn: AsyncMock) -> None:
        cp = _make_checkpoint()
        mock_conn.fetchrow.return_value = _make_checkpoint_record(cp)
        result = await repo.get_latest_checkpoint(cp.workflow_instance_id)
        assert result is not None
        assert result.step_index == cp.step_index
        assert result.state == cp.state

    async def test_get_latest_checkpoint_sql_desc_limit1(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetchrow.return_value = None
        await repo.get_latest_checkpoint(uuid4())
        sql = mock_conn.fetchrow.call_args[0][0]
        assert "DESC" in sql
        assert "LIMIT 1" in sql


# ---------------------------------------------------------------------------
# list_workflows
# ---------------------------------------------------------------------------


class TestListWorkflows:
    async def test_list_workflows_no_status_filter(self, repo, mock_conn: AsyncMock) -> None:
        wf = _make_workflow()
        mock_conn.fetch.return_value = [_make_wf_record(wf)]
        result = await repo.list_workflows(TENANT)
        assert len(result) == 1

    async def test_list_workflows_with_status_filter(self, repo, mock_conn: AsyncMock) -> None:
        wf = _make_workflow(status=WorkflowStatus.RUNNING)
        mock_conn.fetch.return_value = [_make_wf_record(wf)]
        result = await repo.list_workflows(TENANT, status=WorkflowStatus.RUNNING)
        assert len(result) == 1
        call_sql = mock_conn.fetch.call_args[0][0]
        assert "$2" in call_sql

    async def test_list_workflows_status_appends_filter_condition(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        mock_conn.fetch.return_value = []
        await repo.list_workflows(TENANT, status=WorkflowStatus.PENDING)
        sql = mock_conn.fetch.call_args[0][0]
        assert "status" in sql
        assert "$2" in sql

    async def test_list_workflows_no_status_no_extra_and_condition(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        mock_conn.fetch.return_value = []
        await repo.list_workflows(TENANT)
        sql = mock_conn.fetch.call_args[0][0]
        assert "AND status" not in sql

    async def test_list_workflows_empty(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        result = await repo.list_workflows(TENANT, limit=50)
        assert result == []

    async def test_list_workflows_limit_in_query(self, repo, mock_conn: AsyncMock) -> None:
        mock_conn.fetch.return_value = []
        await repo.list_workflows(TENANT, limit=42)
        call_args = mock_conn.fetch.call_args[0]
        assert 42 in call_args

    async def test_list_workflows_all_statuses(self, repo, mock_conn: AsyncMock) -> None:
        for status in WorkflowStatus:
            wf = _make_workflow(status=status)
            mock_conn.fetch.return_value = [_make_wf_record(wf)]
            result = await repo.list_workflows(TENANT, status=status)
            assert len(result) == 1

    async def test_list_workflows_with_status_passes_status_value(
        self, repo, mock_conn: AsyncMock
    ) -> None:
        mock_conn.fetch.return_value = []
        await repo.list_workflows(TENANT, status=WorkflowStatus.FAILED)
        args = mock_conn.fetch.call_args[0]
        assert "failed" in args


# ---------------------------------------------------------------------------
# Private row-mapping helpers
# ---------------------------------------------------------------------------


class TestRowToWorkflow:
    def test_row_to_workflow_pending_status(self, repo) -> None:
        wf = _make_workflow()
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert isinstance(result, WorkflowInstance)
        assert result.workflow_type == wf.workflow_type

    def test_row_to_workflow_running_status(self, repo) -> None:
        wf = _make_workflow(status=WorkflowStatus.RUNNING)
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert result.status == WorkflowStatus.RUNNING.value

    def test_row_to_workflow_completed_status(self, repo) -> None:
        wf = _make_workflow(status=WorkflowStatus.COMPLETED)
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert result.status == WorkflowStatus.COMPLETED.value

    def test_row_to_workflow_failed_status(self, repo) -> None:
        wf = _make_workflow(status=WorkflowStatus.FAILED, error="boom")
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert result.status == WorkflowStatus.FAILED.value
        assert result.error == "boom"

    def test_row_to_workflow_cancelled_status(self, repo) -> None:
        wf = _make_workflow(status=WorkflowStatus.CANCELLED)
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert result.status == WorkflowStatus.CANCELLED.value

    def test_row_to_workflow_compensating_status(self, repo) -> None:
        wf = _make_workflow(status=WorkflowStatus.COMPENSATING)
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert result.status == WorkflowStatus.COMPENSATING.value

    def test_row_to_workflow_preserves_hash(self, repo) -> None:
        wf = _make_workflow()
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_row_to_workflow_with_output_and_timestamps(self, repo) -> None:
        wf = _make_workflow(
            output={"result": "ok"},
            started_at=NOW,
            completed_at=NOW,
        )
        rec = _make_wf_record(wf)
        result = repo._row_to_workflow(rec)
        assert result.output == {"result": "ok"}
        assert result.started_at == NOW


class TestRowToStep:
    def test_row_to_step_all_fields(self, repo) -> None:
        step = _make_step(idempotency_key="ik-1", attempt_count=3)
        rec = _make_step_record(step)
        result = repo._row_to_step(rec)
        assert isinstance(result, WorkflowStep)
        assert result.idempotency_key == "ik-1"
        assert result.attempt_count == 3

    def test_row_to_step_activity_type(self, repo) -> None:
        step = _make_step(step_type=StepType.ACTIVITY)
        rec = _make_step_record(step)
        result = repo._row_to_step(rec)
        assert result.step_type == StepType.ACTIVITY.value

    def test_row_to_step_decision_type(self, repo) -> None:
        step = _make_step(step_type=StepType.DECISION)
        rec = _make_step_record(step)
        result = repo._row_to_step(rec)
        assert result.step_type == StepType.DECISION.value

    def test_row_to_step_compensation_type(self, repo) -> None:
        step = _make_step(step_type=StepType.COMPENSATION)
        rec = _make_step_record(step)
        result = repo._row_to_step(rec)
        assert result.step_type == StepType.COMPENSATION.value

    def test_row_to_step_checkpoint_type(self, repo) -> None:
        step = _make_step(step_type=StepType.CHECKPOINT)
        rec = _make_step_record(step)
        result = repo._row_to_step(rec)
        assert result.step_type == StepType.CHECKPOINT.value

    def test_row_to_step_wait_type(self, repo) -> None:
        step = _make_step(step_type=StepType.WAIT)
        rec = _make_step_record(step)
        result = repo._row_to_step(rec)
        assert result.step_type == StepType.WAIT.value

    def test_row_to_step_all_statuses(self, repo) -> None:
        for ss in StepStatus:
            step = _make_step(status=ss)
            rec = _make_step_record(step)
            result = repo._row_to_step(rec)
            assert result.status == ss.value

    def test_row_to_step_null_idempotency_key(self, repo) -> None:
        step = _make_step(idempotency_key=None)
        rec = _make_step_record(step)
        result = repo._row_to_step(rec)
        assert result.idempotency_key is None


class TestRowToEvent:
    def test_row_to_event(self, repo) -> None:
        event = _make_event()
        rec = _make_event_record(event)
        result = repo._row_to_event(rec)
        assert isinstance(result, WorkflowEvent)
        assert result.sequence_number == event.sequence_number
        assert result.event_data == event.event_data

    def test_row_to_event_all_types(self, repo) -> None:
        for et in EventType:
            event = _make_event(event_type=et)
            rec = _make_event_record(event)
            result = repo._row_to_event(rec)
            assert result.event_type == et.value

    def test_row_to_event_preserves_workflow_instance_id(self, repo) -> None:
        wid = uuid4()
        event = _make_event(workflow_instance_id=wid)
        rec = _make_event_record(event)
        result = repo._row_to_event(rec)
        assert result.workflow_instance_id == wid


class TestRowToCompensation:
    def test_row_to_compensation(self, repo) -> None:
        comp = _make_compensation(executed_at=NOW)
        rec = _make_compensation_record(comp)
        result = repo._row_to_compensation(rec)
        assert isinstance(result, WorkflowCompensation)
        assert result.compensation_name == "rollback"

    def test_row_to_compensation_completed_status(self, repo) -> None:
        comp = _make_compensation(status=StepStatus.COMPLETED)
        rec = _make_compensation_record(comp)
        result = repo._row_to_compensation(rec)
        assert result.status == StepStatus.COMPLETED.value

    def test_row_to_compensation_failed_status(self, repo) -> None:
        comp = _make_compensation(status=StepStatus.FAILED)
        rec = _make_compensation_record(comp)
        result = repo._row_to_compensation(rec)
        assert result.status == StepStatus.FAILED.value

    def test_row_to_compensation_null_optional_fields(self, repo) -> None:
        comp = _make_compensation(input=None, output=None, error=None, executed_at=None)
        rec = _make_compensation_record(comp)
        result = repo._row_to_compensation(rec)
        assert result.input is None
        assert result.output is None
        assert result.executed_at is None


class TestRowToCheckpoint:
    def test_row_to_checkpoint(self, repo) -> None:
        cp = _make_checkpoint()
        rec = _make_checkpoint_record(cp)
        result = repo._row_to_checkpoint(rec)
        assert isinstance(result, CheckpointData)
        assert result.step_index == cp.step_index
        assert result.state == cp.state

    def test_row_to_checkpoint_complex_state(self, repo) -> None:
        cp = _make_checkpoint(state={"nested": {"a": [1, 2, 3]}, "x": None})
        rec = _make_checkpoint_record(cp)
        result = repo._row_to_checkpoint(rec)
        assert result.state == {"nested": {"a": [1, 2, 3]}, "x": None}

    def test_row_to_checkpoint_preserves_workflow_instance_id(self, repo) -> None:
        wid = uuid4()
        cp = _make_checkpoint(workflow_instance_id=wid)
        rec = _make_checkpoint_record(cp)
        result = repo._row_to_checkpoint(rec)
        assert result.workflow_instance_id == wid


# ---------------------------------------------------------------------------
# SCHEMA_SQL constant sanity check
# ---------------------------------------------------------------------------


class TestSchemaSql:
    def test_schema_contains_all_tables(self) -> None:
        for table in (
            "workflow_instances",
            "workflow_steps",
            "workflow_events",
            "workflow_compensations",
            "workflow_checkpoints",
        ):
            assert table in SCHEMA_SQL

    def test_schema_contains_indexes(self) -> None:
        assert "CREATE INDEX IF NOT EXISTS" in SCHEMA_SQL

    def test_schema_contains_if_not_exists(self) -> None:
        assert "CREATE TABLE IF NOT EXISTS" in SCHEMA_SQL

    def test_schema_contains_uuid_primary_key(self) -> None:
        assert "UUID PRIMARY KEY" in SCHEMA_SQL

    def test_schema_contains_constitutional_hash_column(self) -> None:
        assert "constitutional_hash" in SCHEMA_SQL


# ---------------------------------------------------------------------------
# Full round-trip tests (higher-level, exercises multiple methods together)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    async def test_save_then_get_workflow(self, repo, mock_conn: AsyncMock) -> None:
        wf = _make_workflow()
        await repo.save_workflow(wf)
        mock_conn.fetchrow.return_value = _make_wf_record(wf)
        retrieved = await repo.get_workflow(wf.id)
        assert retrieved is not None
        assert retrieved.id == wf.id

    async def test_save_then_get_step(self, repo, mock_conn: AsyncMock) -> None:
        wid = uuid4()
        step = _make_step(workflow_instance_id=wid)
        await repo.save_step(step)
        mock_conn.fetch.return_value = [_make_step_record(step)]
        steps = await repo.get_steps(wid)
        assert len(steps) == 1

    async def test_save_then_get_event(self, repo, mock_conn: AsyncMock) -> None:
        event = _make_event()
        await repo.save_event(event)
        mock_conn.fetch.return_value = [_make_event_record(event)]
        events = await repo.get_events(event.workflow_instance_id)
        assert len(events) == 1

    async def test_save_then_get_compensation(self, repo, mock_conn: AsyncMock) -> None:
        comp = _make_compensation()
        await repo.save_compensation(comp)
        mock_conn.fetch.return_value = [_make_compensation_record(comp)]
        comps = await repo.get_compensations(comp.workflow_instance_id)
        assert len(comps) == 1

    async def test_save_then_get_checkpoint(self, repo, mock_conn: AsyncMock) -> None:
        cp = _make_checkpoint()
        await repo.save_checkpoint(cp)
        mock_conn.fetchrow.return_value = _make_checkpoint_record(cp)
        result = await repo.get_latest_checkpoint(cp.workflow_instance_id)
        assert result is not None
        assert result.step_index == cp.step_index
