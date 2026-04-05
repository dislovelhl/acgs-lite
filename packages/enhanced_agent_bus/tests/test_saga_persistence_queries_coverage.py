# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for saga_persistence/postgres/queries.py.

Targets ≥95% line coverage of PostgresQueryOperations (67 statements).

Coverage plan:
- list_by_tenant: with state, without state, postgres error
- list_by_state: success, postgres error
- list_pending_compensations: success, postgres error
- list_timed_out: success, postgres error
- count_by_state: non-null count, null/zero count, postgres error
- count_by_tenant: non-null count, null/zero count, postgres error
- _ensure_initialized / _row_to_saga: provided by concrete subclass
"""

from __future__ import annotations

import sys
import types
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Inject a minimal asyncpg stub into sys.modules so the module under test can
# be imported without the real asyncpg package installed.
# ---------------------------------------------------------------------------

if "asyncpg" not in sys.modules:
    _asyncpg_stub = types.ModuleType("asyncpg")

    class _PostgresError(Exception):
        """Stub for asyncpg.PostgresError."""

    class _UniqueViolationError(_PostgresError):
        """Stub for asyncpg.UniqueViolationError."""

    _asyncpg_stub.PostgresError = _PostgresError  # type: ignore[attr-defined]
    _asyncpg_stub.UniqueViolationError = _UniqueViolationError  # type: ignore[attr-defined]
    _asyncpg_stub.Pool = MagicMock  # type: ignore[attr-defined]
    _asyncpg_stub.Record = MagicMock  # type: ignore[attr-defined]
    _asyncpg_stub.Connection = MagicMock  # type: ignore[attr-defined]

    sys.modules["asyncpg"] = _asyncpg_stub
else:
    import asyncpg as _asyncpg_real  # type: ignore[import]

    _asyncpg_stub = _asyncpg_real  # type: ignore[assignment]

# Re-export stubs for use in this module
_PostgresError = sys.modules["asyncpg"].PostgresError  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Now import the modules under test (deferred so coverage instruments them).
# ---------------------------------------------------------------------------

from enhanced_agent_bus.saga_persistence.models import (
    PersistedSagaState,
    SagaState,
)
from enhanced_agent_bus.saga_persistence.postgres.queries import (
    PostgresQueryOperations,
)
from enhanced_agent_bus.saga_persistence.repository import (
    RepositoryError,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_persisted_saga(
    saga_id: str = "saga-001", state: SagaState = SagaState.RUNNING
) -> PersistedSagaState:
    """Return a minimal PersistedSagaState for use as a mock return value."""
    return PersistedSagaState(
        saga_id=saga_id,
        saga_name="test-saga",
        tenant_id="tenant-abc",
        state=state,
    )


def _make_fake_row(saga_id: str = "saga-001") -> MagicMock:
    """Return a mock asyncpg.Record-like object."""
    row = MagicMock()
    row["saga_id"] = saga_id
    return row


_SENTINEL = object()  # Sentinel to distinguish "not provided" from None


def _make_conn_ctx(fetch_return=_SENTINEL, fetchval_return=_SENTINEL):
    """
    Build a mock connection whose fetch/fetchval return the given values.

    Returns (mock_pool, mock_conn) so tests can inspect call args.
    Pass fetch_return=[] or fetchval_return=None explicitly to set those values.
    """
    mock_conn = AsyncMock()
    if fetch_return is not _SENTINEL:
        mock_conn.fetch = AsyncMock(return_value=fetch_return)
    if fetchval_return is not _SENTINEL:
        mock_conn.fetchval = AsyncMock(return_value=fetchval_return)

    mock_pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield mock_conn

    mock_pool.acquire = _acquire
    return mock_pool, mock_conn


class ConcreteQueryOps(PostgresQueryOperations):
    """
    Concrete subclass that wires _ensure_initialized and _row_to_saga
    so the mixin methods can be tested in isolation.
    """

    def __init__(self, pool: Any, row_converter: Any = None) -> None:
        self._pool = pool
        self._row_converter = row_converter or (lambda row: _make_persisted_saga())

    def _ensure_initialized(self):  # type: ignore[override]
        return self._pool

    def _row_to_saga(self, row: Any) -> PersistedSagaState:  # type: ignore[override]
        return self._row_converter(row)


# ---------------------------------------------------------------------------
# list_by_tenant
# ---------------------------------------------------------------------------


class TestListByTenant:
    """Tests for PostgresQueryOperations.list_by_tenant."""

    async def test_list_by_tenant_without_state_returns_sagas(self) -> None:
        """When state=None, the no-state SQL branch is used and results are returned."""
        fake_row = _make_fake_row("s1")
        pool, conn = _make_conn_ctx(fetch_return=[fake_row])
        ops = ConcreteQueryOps(pool)

        result = await ops.list_by_tenant("tenant-1")

        assert len(result) == 1
        assert isinstance(result[0], PersistedSagaState)
        conn.fetch.assert_awaited_once()
        call_args = conn.fetch.call_args
        assert "tenant-1" in call_args.args

    async def test_list_by_tenant_without_state_default_limit_offset(self) -> None:
        """Default limit=100 and offset=0 are forwarded to the query."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_tenant("t1")

        args = conn.fetch.call_args.args
        assert 100 in args
        assert 0 in args

    async def test_list_by_tenant_without_state_custom_limit_offset(self) -> None:
        """Custom limit/offset values are forwarded to the query."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_tenant("t1", limit=50, offset=10)

        args = conn.fetch.call_args.args
        assert 50 in args
        assert 10 in args

    async def test_list_by_tenant_without_state_empty_result(self) -> None:
        """Empty result set returns empty list."""
        pool, _conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        result = await ops.list_by_tenant("tenant-empty")

        assert result == []

    async def test_list_by_tenant_with_state_uses_state_sql(self) -> None:
        """When state is provided, the with-state SQL branch is used."""
        fake_row = _make_fake_row("s2")
        pool, conn = _make_conn_ctx(fetch_return=[fake_row])
        ops = ConcreteQueryOps(pool)

        result = await ops.list_by_tenant("tenant-1", state=SagaState.RUNNING)

        assert len(result) == 1
        args = conn.fetch.call_args.args
        assert SagaState.RUNNING.value in args

    async def test_list_by_tenant_with_state_passes_tenant_id(self) -> None:
        """tenant_id is forwarded in the with-state SQL branch."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_tenant("tenant-xyz", state=SagaState.COMPLETED)

        args = conn.fetch.call_args.args
        assert "tenant-xyz" in args

    async def test_list_by_tenant_with_state_custom_limit_offset(self) -> None:
        """Custom limit/offset are forwarded in the with-state SQL branch."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_tenant("t1", state=SagaState.FAILED, limit=25, offset=5)

        args = conn.fetch.call_args.args
        assert 25 in args
        assert 5 in args

    async def test_list_by_tenant_with_state_multiple_rows(self) -> None:
        """Multiple rows are all converted and returned."""
        rows = [_make_fake_row(f"s{i}") for i in range(3)]
        pool, _conn = _make_conn_ctx(fetch_return=rows)
        ops = ConcreteQueryOps(pool)

        result = await ops.list_by_tenant("t1", state=SagaState.RUNNING)

        assert len(result) == 3

    async def test_list_by_tenant_postgres_error_raises_repository_error(self) -> None:
        """asyncpg.PostgresError is caught and re-raised as RepositoryError."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("db down"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError, match="Failed to list sagas by tenant"):
            await ops.list_by_tenant("t1")

    async def test_list_by_tenant_with_state_postgres_error(self) -> None:
        """asyncpg.PostgresError in state branch is caught and re-raised."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("timeout"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError, match="Failed to list sagas by tenant"):
            await ops.list_by_tenant("t1", state=SagaState.RUNNING)

    async def test_list_by_tenant_row_converter_called_per_row(self) -> None:
        """_row_to_saga is called once per returned row."""
        rows = [_make_fake_row(f"s{i}") for i in range(4)]
        pool, _ = _make_conn_ctx(fetch_return=rows)

        call_count = [0]

        def counting_converter(row: Any) -> PersistedSagaState:
            call_count[0] += 1
            return _make_persisted_saga(f"s{call_count[0]}")

        ops = ConcreteQueryOps(pool, row_converter=counting_converter)
        result = await ops.list_by_tenant("t1")

        assert call_count[0] == 4
        assert len(result) == 4

    async def test_list_by_tenant_without_state_sql_contains_tenant_filter(self) -> None:
        """The SQL used contains WHERE tenant_id = $1."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_tenant("t1")

        sql = conn.fetch.call_args.args[0]
        assert "tenant_id" in sql
        assert "saga_states" in sql

    async def test_list_by_tenant_with_state_sql_contains_state_filter(self) -> None:
        """The SQL used in state branch contains both tenant_id and state filters."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_tenant("t1", state=SagaState.FAILED)

        sql = conn.fetch.call_args.args[0]
        assert "tenant_id" in sql
        assert "state" in sql


# ---------------------------------------------------------------------------
# list_by_state
# ---------------------------------------------------------------------------


class TestListByState:
    """Tests for PostgresQueryOperations.list_by_state."""

    async def test_list_by_state_returns_sagas(self) -> None:
        """Matching rows are converted and returned."""
        rows = [_make_fake_row("s1"), _make_fake_row("s2")]
        pool, conn = _make_conn_ctx(fetch_return=rows)
        ops = ConcreteQueryOps(pool)

        result = await ops.list_by_state(SagaState.RUNNING)

        assert len(result) == 2
        conn.fetch.assert_awaited_once()

    async def test_list_by_state_passes_state_value(self) -> None:
        """state.value is forwarded as a query parameter."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_state(SagaState.COMPENSATING)

        args = conn.fetch.call_args.args
        assert SagaState.COMPENSATING.value in args

    async def test_list_by_state_default_limit_offset(self) -> None:
        """Default limit=100 and offset=0 are forwarded."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_state(SagaState.RUNNING)

        args = conn.fetch.call_args.args
        assert 100 in args
        assert 0 in args

    async def test_list_by_state_custom_limit_offset(self) -> None:
        """Custom limit/offset are forwarded."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_state(SagaState.FAILED, limit=20, offset=40)

        args = conn.fetch.call_args.args
        assert 20 in args
        assert 40 in args

    async def test_list_by_state_empty_result(self) -> None:
        """Empty result from DB returns empty list."""
        pool, _conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        result = await ops.list_by_state(SagaState.COMPLETED)

        assert result == []

    async def test_list_by_state_sql_queries_saga_states(self) -> None:
        """The SQL references saga_states table with state filter."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_by_state(SagaState.INITIALIZED)

        sql = conn.fetch.call_args.args[0]
        assert "saga_states" in sql
        assert "state" in sql

    async def test_list_by_state_postgres_error_raises_repository_error(self) -> None:
        """asyncpg.PostgresError is caught and re-raised as RepositoryError."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("connection lost"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError, match="Failed to list sagas by state"):
            await ops.list_by_state(SagaState.RUNNING)

    async def test_list_by_state_all_states(self) -> None:
        """Can be called with every SagaState value without error."""
        for state in SagaState:
            pool, _conn = _make_conn_ctx(fetch_return=[])
            ops = ConcreteQueryOps(pool)
            result = await ops.list_by_state(state)
            assert isinstance(result, list)


# ---------------------------------------------------------------------------
# list_pending_compensations
# ---------------------------------------------------------------------------


class TestListPendingCompensations:
    """Tests for PostgresQueryOperations.list_pending_compensations."""

    async def test_list_pending_compensations_returns_sagas(self) -> None:
        """Rows are converted and returned."""
        rows = [_make_fake_row("s1")]
        pool, _conn = _make_conn_ctx(fetch_return=rows)
        ops = ConcreteQueryOps(pool)

        result = await ops.list_pending_compensations()

        assert len(result) == 1

    async def test_list_pending_compensations_passes_correct_states(self) -> None:
        """COMPENSATING and RUNNING state values are passed as parameters."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_pending_compensations()

        args = conn.fetch.call_args.args
        assert SagaState.COMPENSATING.value in args
        assert SagaState.RUNNING.value in args

    async def test_list_pending_compensations_default_limit_offset(self) -> None:
        """Default limit=100 and offset=0 are forwarded."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_pending_compensations()

        args = conn.fetch.call_args.args
        assert 100 in args
        assert 0 in args

    async def test_list_pending_compensations_custom_limit_offset(self) -> None:
        """Custom limit and offset values are forwarded."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_pending_compensations(limit=10, offset=5)

        args = conn.fetch.call_args.args
        assert 10 in args
        assert 5 in args

    async def test_list_pending_compensations_empty_result(self) -> None:
        """Empty DB result returns empty list."""
        pool, _conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        result = await ops.list_pending_compensations()

        assert result == []

    async def test_list_pending_compensations_sql_uses_in_clause(self) -> None:
        """The SQL uses an IN clause for multiple states."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_pending_compensations()

        sql = conn.fetch.call_args.args[0]
        assert "saga_states" in sql
        assert "$1" in sql

    async def test_list_pending_compensations_postgres_error_raises_repository_error(self) -> None:
        """asyncpg.PostgresError is caught and re-raised as RepositoryError."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("timeout"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError, match="Failed to list pending compensations"):
            await ops.list_pending_compensations()

    async def test_list_pending_compensations_multiple_rows(self) -> None:
        """Multiple rows are all returned."""
        rows = [_make_fake_row(f"s{i}") for i in range(5)]
        pool, _conn = _make_conn_ctx(fetch_return=rows)
        ops = ConcreteQueryOps(pool)

        result = await ops.list_pending_compensations()

        assert len(result) == 5


# ---------------------------------------------------------------------------
# list_timed_out
# ---------------------------------------------------------------------------


class TestListTimedOut:
    """Tests for PostgresQueryOperations.list_timed_out."""

    async def test_list_timed_out_returns_sagas(self) -> None:
        """Matching rows are converted and returned."""
        rows = [_make_fake_row("s1")]
        pool, _conn = _make_conn_ctx(fetch_return=rows)
        ops = ConcreteQueryOps(pool)

        since = datetime(2024, 1, 1, tzinfo=UTC)
        result = await ops.list_timed_out(since)

        assert len(result) == 1

    async def test_list_timed_out_passes_running_state(self) -> None:
        """RUNNING state value is passed as a parameter."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        since = datetime.now(UTC)
        await ops.list_timed_out(since)

        args = conn.fetch.call_args.args
        assert SagaState.RUNNING.value in args

    async def test_list_timed_out_passes_since_timestamp(self) -> None:
        """The `since` datetime is forwarded to the query."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        since = datetime(2023, 6, 15, 12, 0, 0, tzinfo=UTC)
        await ops.list_timed_out(since)

        args = conn.fetch.call_args.args
        assert since in args

    async def test_list_timed_out_default_limit_offset(self) -> None:
        """Default limit=100 and offset=0 are forwarded."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_timed_out(datetime.now(UTC))

        args = conn.fetch.call_args.args
        assert 100 in args
        assert 0 in args

    async def test_list_timed_out_custom_limit_offset(self) -> None:
        """Custom limit and offset values are forwarded."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        since = datetime.now(UTC)
        await ops.list_timed_out(since, limit=30, offset=15)

        args = conn.fetch.call_args.args
        assert 30 in args
        assert 15 in args

    async def test_list_timed_out_empty_result(self) -> None:
        """Empty DB result returns empty list."""
        pool, _conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        result = await ops.list_timed_out(datetime.now(UTC))

        assert result == []

    async def test_list_timed_out_sql_filters_on_started_at(self) -> None:
        """The SQL references started_at for timeout filtering."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        ops = ConcreteQueryOps(pool)

        await ops.list_timed_out(datetime.now(UTC))

        sql = conn.fetch.call_args.args[0]
        assert "started_at" in sql
        assert "timeout_ms" in sql

    async def test_list_timed_out_postgres_error_raises_repository_error(self) -> None:
        """asyncpg.PostgresError is caught and re-raised as RepositoryError."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("connection refused"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError, match="Failed to list timed out sagas"):
            await ops.list_timed_out(datetime.now(UTC))

    async def test_list_timed_out_multiple_rows(self) -> None:
        """Multiple rows are converted and returned."""
        rows = [_make_fake_row(f"s{i}") for i in range(3)]
        pool, _conn = _make_conn_ctx(fetch_return=rows)
        ops = ConcreteQueryOps(pool)

        result = await ops.list_timed_out(datetime.now(UTC))

        assert len(result) == 3


# ---------------------------------------------------------------------------
# count_by_state
# ---------------------------------------------------------------------------


class TestCountByState:
    """Tests for PostgresQueryOperations.count_by_state."""

    async def test_count_by_state_returns_integer(self) -> None:
        """Non-None count is returned as an int."""
        pool, _conn = _make_conn_ctx(fetchval_return=42)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_state(SagaState.RUNNING)

        assert result == 42
        assert isinstance(result, int)

    async def test_count_by_state_passes_state_value(self) -> None:
        """state.value is forwarded to the query."""
        pool, conn = _make_conn_ctx(fetchval_return=0)
        ops = ConcreteQueryOps(pool)

        await ops.count_by_state(SagaState.COMPLETED)

        args = conn.fetchval.call_args.args
        assert SagaState.COMPLETED.value in args

    async def test_count_by_state_zero_count_returns_zero(self) -> None:
        """Zero count returns 0."""
        pool, _conn = _make_conn_ctx(fetchval_return=0)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_state(SagaState.FAILED)

        assert result == 0

    async def test_count_by_state_none_count_returns_zero(self) -> None:
        """When fetchval returns None, result is 0 (falsy branch)."""
        pool, _conn = _make_conn_ctx(fetchval_return=None)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_state(SagaState.INITIALIZED)

        assert result == 0

    async def test_count_by_state_large_count(self) -> None:
        """Large int counts are returned correctly."""
        pool, _conn = _make_conn_ctx(fetchval_return=999999)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_state(SagaState.COMPENSATING)

        assert result == 999999

    async def test_count_by_state_sql_uses_count(self) -> None:
        """The SQL uses COUNT(*)."""
        pool, conn = _make_conn_ctx(fetchval_return=1)
        ops = ConcreteQueryOps(pool)

        await ops.count_by_state(SagaState.RUNNING)

        sql = conn.fetchval.call_args.args[0]
        assert "COUNT" in sql.upper()
        assert "saga_states" in sql

    async def test_count_by_state_postgres_error_raises_repository_error(self) -> None:
        """asyncpg.PostgresError is caught and re-raised as RepositoryError."""
        pool, conn = _make_conn_ctx(fetchval_return=0)
        conn.fetchval = AsyncMock(side_effect=_PostgresError("query failed"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError, match="Failed to count sagas by state"):
            await ops.count_by_state(SagaState.RUNNING)

    async def test_count_by_state_all_states(self) -> None:
        """Can count sagas for every SagaState without error."""
        for state in SagaState:
            pool, _conn = _make_conn_ctx(fetchval_return=0)
            ops = ConcreteQueryOps(pool)
            result = await ops.count_by_state(state)
            assert isinstance(result, int)

    async def test_count_by_state_int_conversion(self) -> None:
        """The return value is explicitly cast to int."""
        pool, _conn = _make_conn_ctx(fetchval_return=7)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_state(SagaState.RUNNING)

        assert result == 7
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# count_by_tenant
# ---------------------------------------------------------------------------


class TestCountByTenant:
    """Tests for PostgresQueryOperations.count_by_tenant."""

    async def test_count_by_tenant_returns_integer(self) -> None:
        """Non-None count is returned as an int."""
        pool, _conn = _make_conn_ctx(fetchval_return=15)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_tenant("tenant-abc")

        assert result == 15
        assert isinstance(result, int)

    async def test_count_by_tenant_passes_tenant_id(self) -> None:
        """tenant_id is forwarded to the query."""
        pool, conn = _make_conn_ctx(fetchval_return=0)
        ops = ConcreteQueryOps(pool)

        await ops.count_by_tenant("tenant-xyz")

        args = conn.fetchval.call_args.args
        assert "tenant-xyz" in args

    async def test_count_by_tenant_zero_count(self) -> None:
        """Zero count returns 0."""
        pool, _conn = _make_conn_ctx(fetchval_return=0)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_tenant("tenant-empty")

        assert result == 0

    async def test_count_by_tenant_none_count_returns_zero(self) -> None:
        """When fetchval returns None, result is 0 (falsy branch)."""
        pool, _conn = _make_conn_ctx(fetchval_return=None)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_tenant("tenant-none")

        assert result == 0

    async def test_count_by_tenant_large_count(self) -> None:
        """Large int counts are returned correctly."""
        pool, _conn = _make_conn_ctx(fetchval_return=500000)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_tenant("tenant-big")

        assert result == 500000

    async def test_count_by_tenant_sql_uses_count_and_tenant_filter(self) -> None:
        """The SQL uses COUNT(*) and filters by tenant_id."""
        pool, conn = _make_conn_ctx(fetchval_return=3)
        ops = ConcreteQueryOps(pool)

        await ops.count_by_tenant("t1")

        sql = conn.fetchval.call_args.args[0]
        assert "COUNT" in sql.upper()
        assert "tenant_id" in sql
        assert "saga_states" in sql

    async def test_count_by_tenant_postgres_error_raises_repository_error(self) -> None:
        """asyncpg.PostgresError is caught and re-raised as RepositoryError."""
        pool, conn = _make_conn_ctx(fetchval_return=0)
        conn.fetchval = AsyncMock(side_effect=_PostgresError("network error"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError, match="Failed to count sagas by tenant"):
            await ops.count_by_tenant("tenant-error")

    async def test_count_by_tenant_int_conversion(self) -> None:
        """The return value is explicitly cast to int."""
        pool, _conn = _make_conn_ctx(fetchval_return=3)
        ops = ConcreteQueryOps(pool)

        result = await ops.count_by_tenant("t1")

        assert result == 3
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Mixin abstract method stubs
# ---------------------------------------------------------------------------


class TestMixinAbstractStubs:
    """Ensure the mixin raises NotImplementedError for abstract methods."""

    def test_ensure_initialized_raises_not_implemented(self) -> None:
        """_ensure_initialized must be overridden by the concrete repository."""

        class BareOps(PostgresQueryOperations):
            """Bare subclass that does NOT override the abstract stubs."""

        ops = BareOps()
        with pytest.raises(NotImplementedError, match="Must be implemented by repository class"):
            ops._ensure_initialized()

    def test_row_to_saga_raises_not_implemented(self) -> None:
        """_row_to_saga must be overridden by the concrete repository."""

        class BareOps(PostgresQueryOperations):
            pass

        ops = BareOps()
        fake_row = MagicMock()
        with pytest.raises(NotImplementedError, match="Must be implemented by repository class"):
            ops._row_to_saga(fake_row)


# ---------------------------------------------------------------------------
# Module-level assertions
# ---------------------------------------------------------------------------


class TestModuleMetadata:
    """Verify module exports and constitutional hash inclusion."""

    def test_postgres_query_operations_exported(self) -> None:
        """PostgresQueryOperations is exported from the module."""
        from enhanced_agent_bus.saga_persistence.postgres.queries import (
            PostgresQueryOperations,
        )

        assert PostgresQueryOperations is not None

    def test_all_contains_postgres_query_operations(self) -> None:
        """__all__ lists PostgresQueryOperations."""
        import enhanced_agent_bus.saga_persistence.postgres.queries as mod

        assert "PostgresQueryOperations" in mod.__all__

    def test_module_uses_constitutional_hash(self) -> None:
        """The module references CONSTITUTIONAL_HASH (imported from constants)."""
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as CH2
        from enhanced_agent_bus.saga_persistence.postgres.queries import (
            CONSTITUTIONAL_HASH as CH1,
        )

        assert CH1 == CH2  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Error message content
# ---------------------------------------------------------------------------


class TestErrorMessages:
    """Verify that RepositoryError messages include useful context."""

    async def test_list_by_tenant_error_contains_original_message(self) -> None:
        """RepositoryError from list_by_tenant wraps the original DB error."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("SSL connection required"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await ops.list_by_tenant("t1")

        assert "SSL connection required" in str(exc_info.value)

    async def test_list_by_state_error_contains_original_message(self) -> None:
        """RepositoryError from list_by_state wraps the original DB error."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("out of memory"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await ops.list_by_state(SagaState.RUNNING)

        assert "out of memory" in str(exc_info.value)

    async def test_list_pending_compensations_error_contains_original_message(self) -> None:
        """RepositoryError from list_pending_compensations wraps the original DB error."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("disk full"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await ops.list_pending_compensations()

        assert "disk full" in str(exc_info.value)

    async def test_list_timed_out_error_contains_original_message(self) -> None:
        """RepositoryError from list_timed_out wraps the original DB error."""
        pool, conn = _make_conn_ctx(fetch_return=[])
        conn.fetch = AsyncMock(side_effect=_PostgresError("too many connections"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await ops.list_timed_out(datetime.now(UTC))

        assert "too many connections" in str(exc_info.value)

    async def test_count_by_state_error_contains_original_message(self) -> None:
        """RepositoryError from count_by_state wraps the original DB error."""
        pool, conn = _make_conn_ctx(fetchval_return=0)
        conn.fetchval = AsyncMock(side_effect=_PostgresError("query cancelled"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await ops.count_by_state(SagaState.RUNNING)

        assert "query cancelled" in str(exc_info.value)

    async def test_count_by_tenant_error_contains_original_message(self) -> None:
        """RepositoryError from count_by_tenant wraps the original DB error."""
        pool, conn = _make_conn_ctx(fetchval_return=0)
        conn.fetchval = AsyncMock(side_effect=_PostgresError("authentication failed"))
        ops = ConcreteQueryOps(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await ops.count_by_tenant("t1")

        assert "authentication failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Row converter integration
# ---------------------------------------------------------------------------


class TestRowConverterIntegration:
    """Verify row converter receives the actual row objects from the DB."""

    async def test_list_by_state_passes_row_to_converter(self) -> None:
        """_row_to_saga receives the exact asyncpg record returned by fetch."""
        sentinel_row = object()
        pool, _conn = _make_conn_ctx(fetch_return=[sentinel_row])

        received = []

        def capturing_converter(row: Any) -> PersistedSagaState:
            received.append(row)
            return _make_persisted_saga()

        ops = ConcreteQueryOps(pool, row_converter=capturing_converter)
        await ops.list_by_state(SagaState.RUNNING)

        assert received == [sentinel_row]

    async def test_list_timed_out_passes_row_to_converter(self) -> None:
        """_row_to_saga receives the exact asyncpg record returned by fetch."""
        sentinel_row = object()
        pool, _conn = _make_conn_ctx(fetch_return=[sentinel_row])

        received = []

        def capturing_converter(row: Any) -> PersistedSagaState:
            received.append(row)
            return _make_persisted_saga()

        ops = ConcreteQueryOps(pool, row_converter=capturing_converter)
        await ops.list_timed_out(datetime.now(UTC))

        assert received == [sentinel_row]

    async def test_list_pending_compensations_passes_row_to_converter(self) -> None:
        """_row_to_saga receives the exact asyncpg record from list_pending_compensations."""
        sentinel_row = object()
        pool, _conn = _make_conn_ctx(fetch_return=[sentinel_row])

        received = []

        def capturing_converter(row: Any) -> PersistedSagaState:
            received.append(row)
            return _make_persisted_saga()

        ops = ConcreteQueryOps(pool, row_converter=capturing_converter)
        await ops.list_pending_compensations()

        assert received == [sentinel_row]
