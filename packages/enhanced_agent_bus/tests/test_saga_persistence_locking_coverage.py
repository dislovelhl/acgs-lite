# Constitutional Hash: 608508a9bd224290
"""
Comprehensive pytest test suite for saga_persistence/postgres/locking.py.
Target: ≥95% coverage of PostgresLockManager.

Tests cover:
- acquire_lock: success, UniqueViolationError (lock held), PostgresError
- release_lock: released (DELETE 1), not released (DELETE 0/other), PostgresError
- extend_lock: extended (UPDATE 1), not extended (UPDATE 0/other), PostgresError
- distributed_lock: acquired path (acquire+release), not-acquired path, exception in body
- cleanup_old_sagas: terminal_only=True, terminal_only=False, parse "DELETE N", PostgresError
- get_statistics: success, zero values (None returns), PostgresError
- health_check: all checks pass, postgres_ping fail (result != 1), all exception types
- _ensure_initialized: NotImplementedError (base implementation)
- LOCK_HEALTH_CHECK_ERRORS tuple contents
- Module-level __all__ export
"""

from __future__ import annotations

import sys
import types
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    _asyncpg_stub.Connection = MagicMock  # type: ignore[attr-defined]

    sys.modules["asyncpg"] = _asyncpg_stub
else:
    # asyncpg is available — create aliases for use in tests
    import asyncpg as _asyncpg_real  # type: ignore[import]

    _asyncpg_stub = _asyncpg_real

# Re-export stubs for use in this module
_PostgresError = sys.modules["asyncpg"].PostgresError  # type: ignore[attr-defined]
_UniqueViolationError = sys.modules["asyncpg"].UniqueViolationError  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Now import the module under test (deferred so coverage instruments it).
# ---------------------------------------------------------------------------

from enhanced_agent_bus.saga_persistence.postgres.locking import (
    LOCK_HEALTH_CHECK_ERRORS,
    PostgresLockManager,
)
from enhanced_agent_bus.saga_persistence.postgres.locking import (
    __all__ as locking_all,
)
from enhanced_agent_bus.saga_persistence.postgres.schema import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
)
from enhanced_agent_bus.saga_persistence.repository import (
    LockError,
    RepositoryError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAGA_ID = str(uuid.uuid4())
LOCK_HOLDER = "test-node-abc12345"
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(pool: Any = None, node_id: str = "node-1") -> PostgresLockManager:
    """Create a PostgresLockManager concrete subclass for testing."""

    class ConcreteManager(PostgresLockManager):
        def __init__(self, pool_obj: Any, nid: str) -> None:
            self._pool = pool_obj
            self._node_id = nid

        def _ensure_initialized(self) -> Any:
            if self._pool is None:
                raise RuntimeError("Not initialized")
            return self._pool

    return ConcreteManager(pool, node_id)


def _make_pool_with_conn(conn: Any) -> Any:
    """Return a mock pool whose acquire() context manager yields the given conn."""
    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool


# ---------------------------------------------------------------------------
# Module-level checks
# ---------------------------------------------------------------------------


class TestModuleLevel:
    def test_all_export(self):
        assert "PostgresLockManager" in locking_all

    def test_lock_health_check_errors_contains_postgres_error(self):
        assert _PostgresError in LOCK_HEALTH_CHECK_ERRORS

    def test_lock_health_check_errors_contains_runtime_error(self):
        assert RuntimeError in LOCK_HEALTH_CHECK_ERRORS

    def test_lock_health_check_errors_contains_value_error(self):
        assert ValueError in LOCK_HEALTH_CHECK_ERRORS

    def test_lock_health_check_errors_contains_type_error(self):
        assert TypeError in LOCK_HEALTH_CHECK_ERRORS

    def test_lock_health_check_errors_contains_key_error(self):
        assert KeyError in LOCK_HEALTH_CHECK_ERRORS

    def test_lock_health_check_errors_contains_attribute_error(self):
        assert AttributeError in LOCK_HEALTH_CHECK_ERRORS

    def test_lock_health_check_errors_contains_os_error(self):
        assert OSError in LOCK_HEALTH_CHECK_ERRORS


# ---------------------------------------------------------------------------
# _ensure_initialized
# ---------------------------------------------------------------------------


class TestEnsureInitialized:
    def test_base_raises_not_implemented(self):
        """The base class raises NotImplementedError."""
        mgr = PostgresLockManager()
        with pytest.raises(NotImplementedError):
            mgr._ensure_initialized()


# ---------------------------------------------------------------------------
# acquire_lock
# ---------------------------------------------------------------------------


class TestAcquireLock:
    async def test_acquire_lock_success(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER, ttl_seconds=60)

        assert result is True
        # First call: DELETE expired locks; second call: INSERT
        assert conn.execute.call_count == 2

    async def test_acquire_lock_unique_violation_returns_false(self):
        conn = AsyncMock()
        # DELETE succeeds, INSERT raises UniqueViolationError
        conn.execute = AsyncMock(side_effect=[None, _UniqueViolationError("duplicate")])
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER)

        assert result is False

    async def test_acquire_lock_postgres_error_raises_lock_error(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("pg error"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(LockError) as exc_info:
            await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER)

        assert "Failed to acquire lock" in str(exc_info.value)

    async def test_acquire_lock_default_ttl(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER)

        assert result is True

    async def test_acquire_lock_passes_constitutional_hash(self):
        """Verify that the constitutional hash is passed as argument."""
        captured_args: list[Any] = []

        async def mock_execute(query: str, *args: Any) -> None:
            captured_args.append(list(args))
            return None

        conn = AsyncMock()
        conn.execute = mock_execute
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER, ttl_seconds=30)

        # Second call (INSERT) should include CONSTITUTIONAL_HASH
        insert_args = captured_args[1]
        assert CONSTITUTIONAL_HASH in insert_args

    async def test_acquire_lock_lock_error_saga_id_propagated(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(LockError) as exc_info:
            await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER)

        assert exc_info.value.saga_id == SAGA_ID

    async def test_acquire_lock_passes_uuid_to_first_delete(self):
        """The DELETE statement receives a datetime, not the saga_id."""
        captured_args: list[Any] = []

        async def mock_execute(query: str, *args: Any) -> None:
            captured_args.append(list(args))
            return None

        conn = AsyncMock()
        conn.execute = mock_execute
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER, ttl_seconds=30)

        # First call is DELETE WHERE expires_at < $1 (passes a datetime)
        delete_args = captured_args[0]
        assert len(delete_args) == 1
        assert isinstance(delete_args[0], datetime)


# ---------------------------------------------------------------------------
# release_lock
# ---------------------------------------------------------------------------


class TestReleaseLock:
    async def test_release_lock_success(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 1")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert result is True

    async def test_release_lock_not_held(self):
        """Returns False when DELETE affects 0 rows."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 0")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert result is False

    async def test_release_lock_postgres_error_raises_lock_error(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("pg error"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(LockError) as exc_info:
            await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert "Failed to release lock" in str(exc_info.value)

    async def test_release_lock_error_has_saga_id(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(LockError) as exc_info:
            await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert exc_info.value.saga_id == SAGA_ID

    async def test_release_lock_result_other_than_delete_1(self):
        """Any result other than 'DELETE 1' is treated as not-released."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 5")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert result is False

    async def test_release_lock_passes_uuid_and_holder(self):
        captured: list[Any] = []

        async def mock_execute(query: str, *args: Any) -> str:
            captured.extend(args)
            return "DELETE 1"

        conn = AsyncMock()
        conn.execute = mock_execute
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert uuid.UUID(SAGA_ID) in captured
        assert LOCK_HOLDER in captured


# ---------------------------------------------------------------------------
# extend_lock
# ---------------------------------------------------------------------------


class TestExtendLock:
    async def test_extend_lock_success(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.extend_lock(SAGA_ID, LOCK_HOLDER, ttl_seconds=120)

        assert result is True

    async def test_extend_lock_not_held(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 0")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.extend_lock(SAGA_ID, LOCK_HOLDER)

        assert result is False

    async def test_extend_lock_postgres_error_raises_lock_error(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("pg fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(LockError) as exc_info:
            await mgr.extend_lock(SAGA_ID, LOCK_HOLDER)

        assert "Failed to extend lock" in str(exc_info.value)

    async def test_extend_lock_error_has_saga_id(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(LockError) as exc_info:
            await mgr.extend_lock(SAGA_ID, LOCK_HOLDER)

        assert exc_info.value.saga_id == SAGA_ID

    async def test_extend_lock_default_ttl(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.extend_lock(SAGA_ID, LOCK_HOLDER)

        assert result is True

    async def test_extend_lock_result_not_update_1(self):
        """Anything other than 'UPDATE 1' returns False."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 2")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        result = await mgr.extend_lock(SAGA_ID, LOCK_HOLDER)

        assert result is False

    async def test_extend_lock_passes_new_expiry_datetime(self):
        captured: list[Any] = []

        async def mock_execute(query: str, *args: Any) -> str:
            captured.extend(args)
            return "UPDATE 1"

        conn = AsyncMock()
        conn.execute = mock_execute
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        await mgr.extend_lock(SAGA_ID, LOCK_HOLDER, ttl_seconds=90)

        # Args: saga_id uuid, lock_holder str, new_expires_at datetime
        assert uuid.UUID(SAGA_ID) in captured
        assert LOCK_HOLDER in captured
        # The datetime arg should be roughly now + 90s
        dt_args = [a for a in captured if isinstance(a, datetime)]
        assert len(dt_args) == 1
        future = datetime.now(UTC) + timedelta(seconds=90)
        diff = abs((dt_args[0] - future).total_seconds())
        assert diff < 5  # within 5 seconds


# ---------------------------------------------------------------------------
# distributed_lock
# ---------------------------------------------------------------------------


class TestDistributedLock:
    async def test_distributed_lock_acquired_and_released(self):
        """Full happy path: lock acquired, body runs, lock released."""
        acquire_calls: list[tuple[str, str]] = []
        release_calls: list[tuple[str, str]] = []

        async def mock_acquire(
            sid: str, holder: str, ttl: int = DEFAULT_LOCK_TIMEOUT_SECONDS
        ) -> bool:
            acquire_calls.append((sid, holder))
            return True

        async def mock_release(sid: str, holder: str) -> bool:
            release_calls.append((sid, holder))
            return True

        mgr = _make_manager(MagicMock())
        mgr.acquire_lock = mock_acquire  # type: ignore[method-assign]
        mgr.release_lock = mock_release  # type: ignore[method-assign]

        async with mgr.distributed_lock(SAGA_ID, ttl_seconds=60) as acquired:
            assert acquired is True

        assert len(acquire_calls) == 1
        assert acquire_calls[0][0] == SAGA_ID
        assert len(release_calls) == 1
        assert release_calls[0][0] == SAGA_ID

    async def test_distributed_lock_not_acquired_no_release(self):
        """If acquire returns False, release is NOT called."""
        release_calls: list[Any] = []

        async def mock_acquire(
            sid: str, holder: str, ttl: int = DEFAULT_LOCK_TIMEOUT_SECONDS
        ) -> bool:
            return False

        async def mock_release(sid: str, holder: str) -> bool:
            release_calls.append((sid, holder))
            return True

        mgr = _make_manager(MagicMock())
        mgr.acquire_lock = mock_acquire  # type: ignore[method-assign]
        mgr.release_lock = mock_release  # type: ignore[method-assign]

        async with mgr.distributed_lock(SAGA_ID) as acquired:
            assert acquired is False

        assert len(release_calls) == 0

    async def test_distributed_lock_exception_in_body_releases(self):
        """If an exception is raised in the body, the lock is still released."""
        release_calls: list[Any] = []

        async def mock_acquire(
            sid: str, holder: str, ttl: int = DEFAULT_LOCK_TIMEOUT_SECONDS
        ) -> bool:
            return True

        async def mock_release(sid: str, holder: str) -> bool:
            release_calls.append((sid, holder))
            return True

        mgr = _make_manager(MagicMock())
        mgr.acquire_lock = mock_acquire  # type: ignore[method-assign]
        mgr.release_lock = mock_release  # type: ignore[method-assign]

        with pytest.raises(ValueError):
            async with mgr.distributed_lock(SAGA_ID) as acquired:
                assert acquired is True
                raise ValueError("body error")

        assert len(release_calls) == 1

    async def test_distributed_lock_generates_unique_holders(self):
        """Each call generates a different lock_holder."""
        holders_seen: list[str] = []

        async def mock_acquire(
            sid: str, holder: str, ttl: int = DEFAULT_LOCK_TIMEOUT_SECONDS
        ) -> bool:
            holders_seen.append(holder)
            return False

        async def mock_release(sid: str, holder: str) -> bool:
            return True

        mgr = _make_manager(MagicMock(), node_id="mynode")
        mgr.acquire_lock = mock_acquire  # type: ignore[method-assign]
        mgr.release_lock = mock_release  # type: ignore[method-assign]

        async with mgr.distributed_lock(SAGA_ID):
            pass
        async with mgr.distributed_lock(SAGA_ID):
            pass

        assert len(holders_seen) == 2
        assert holders_seen[0] != holders_seen[1]
        assert holders_seen[0].startswith("mynode-")

    async def test_distributed_lock_not_acquired_exception_no_release(self):
        """If not acquired AND exception in body, release is NOT called."""
        release_calls: list[Any] = []

        async def mock_acquire(
            sid: str, holder: str, ttl: int = DEFAULT_LOCK_TIMEOUT_SECONDS
        ) -> bool:
            return False

        async def mock_release(sid: str, holder: str) -> None:
            release_calls.append((sid, holder))

        mgr = _make_manager(MagicMock())
        mgr.acquire_lock = mock_acquire  # type: ignore[method-assign]
        mgr.release_lock = mock_release  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            async with mgr.distributed_lock(SAGA_ID):
                raise RuntimeError("fail in body, not acquired")

        assert release_calls == []


# ---------------------------------------------------------------------------
# cleanup_old_sagas
# ---------------------------------------------------------------------------


class TestCleanupOldSagas:
    async def test_cleanup_terminal_only_true(self):
        """terminal_only=True uses the three-state filter."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 5")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        cutoff = datetime.now(UTC) - timedelta(days=7)
        count = await mgr.cleanup_old_sagas(cutoff, terminal_only=True)

        assert count == 5
        query_used = conn.execute.call_args[0][0]
        assert "IN" in query_used  # state IN ($1, $2, $3)

    async def test_cleanup_all_sagas(self):
        """terminal_only=False uses the simpler date filter."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 12")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        cutoff = datetime.now(UTC) - timedelta(days=7)
        count = await mgr.cleanup_old_sagas(cutoff, terminal_only=False)

        assert count == 12

    async def test_cleanup_zero_deleted(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 0")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        cutoff = datetime.now(UTC)
        count = await mgr.cleanup_old_sagas(cutoff, terminal_only=True)

        assert count == 0

    async def test_cleanup_none_result(self):
        """If result is None/falsy, deleted_count is 0."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        cutoff = datetime.now(UTC)
        count = await mgr.cleanup_old_sagas(cutoff)

        assert count == 0

    async def test_cleanup_empty_string_result(self):
        """If result is empty string, deleted_count is 0."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        count = await mgr.cleanup_old_sagas(datetime.now(UTC))

        assert count == 0

    async def test_cleanup_postgres_error_raises_repository_error(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await mgr.cleanup_old_sagas(datetime.now(UTC))

        assert "Failed to cleanup old sagas" in str(exc_info.value)

    async def test_cleanup_default_terminal_only_is_true(self):
        """Default value for terminal_only should be True (uses state filter)."""
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 3")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        count = await mgr.cleanup_old_sagas(datetime.now(UTC))

        assert count == 3
        query = conn.execute.call_args[0][0]
        assert "IN" in query

    async def test_cleanup_large_count(self):
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 1000")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        count = await mgr.cleanup_old_sagas(datetime.now(UTC))

        assert count == 1000


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


class TestGetStatistics:
    def _make_conn_for_stats(
        self,
        state_counts: list[Any] | None = None,
        total: Any = 10,
        checkpoint_count: Any = 5,
        lock_count: Any = 2,
    ) -> Any:
        if state_counts is None:
            state_counts = [
                {"state": "RUNNING", "count": 3},
                {"state": "COMPLETED", "count": 7},
            ]

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=state_counts)
        conn.fetchval = AsyncMock(side_effect=[total, checkpoint_count, lock_count])
        return conn

    async def test_get_statistics_success(self):
        conn = self._make_conn_for_stats()
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        stats = await mgr.get_statistics()

        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["total_sagas"] == 10
        assert stats["total_checkpoints"] == 5
        assert stats["active_locks"] == 2
        assert stats["counts_by_state"]["RUNNING"] == 3
        assert stats["counts_by_state"]["COMPLETED"] == 7
        assert "timestamp" in stats

    async def test_get_statistics_all_none_values(self):
        """If fetchval returns None, int fallbacks to 0."""
        conn = self._make_conn_for_stats(total=None, checkpoint_count=None, lock_count=None)
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        stats = await mgr.get_statistics()

        assert stats["total_sagas"] == 0
        assert stats["total_checkpoints"] == 0
        assert stats["active_locks"] == 0

    async def test_get_statistics_empty_state_counts(self):
        conn = self._make_conn_for_stats(state_counts=[], total=0, checkpoint_count=0, lock_count=0)
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        stats = await mgr.get_statistics()

        assert stats["counts_by_state"] == {}
        assert stats["total_sagas"] == 0

    async def test_get_statistics_postgres_error_raises_repository_error(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with pytest.raises(RepositoryError) as exc_info:
            await mgr.get_statistics()

        assert "Failed to get statistics" in str(exc_info.value)

    async def test_get_statistics_constitutional_hash_present(self):
        conn = self._make_conn_for_stats()
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        stats = await mgr.get_statistics()

        assert CONSTITUTIONAL_HASH in stats["constitutional_hash"]

    async def test_get_statistics_timestamp_is_parseable(self):
        conn = self._make_conn_for_stats()
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        stats = await mgr.get_statistics()

        # Should not raise
        datetime.fromisoformat(stats["timestamp"])

    async def test_get_statistics_multiple_states(self):
        state_counts = [
            {"state": "INITIALIZED", "count": 1},
            {"state": "RUNNING", "count": 5},
            {"state": "COMPLETED", "count": 10},
            {"state": "FAILED", "count": 2},
        ]
        conn = self._make_conn_for_stats(state_counts=state_counts, total=18)
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        stats = await mgr.get_statistics()

        assert len(stats["counts_by_state"]) == 4
        assert stats["counts_by_state"]["INITIALIZED"] == 1
        assert stats["counts_by_state"]["FAILED"] == 2


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def _make_pool_for_health(
        self,
        ping_result: Any = 1,
        table_result: Any = 5,
        pool_size: int = 10,
        min_size: int = 2,
        max_size: int = 20,
        idle_size: int = 5,
        first_fetchval_raises: Exception | None = None,
    ) -> Any:
        conn = AsyncMock()

        if first_fetchval_raises is not None:
            conn.fetchval = AsyncMock(side_effect=first_fetchval_raises)
        else:
            conn.fetchval = AsyncMock(side_effect=[ping_result, table_result])

        pool = _make_pool_with_conn(conn)
        pool.get_size = MagicMock(return_value=pool_size)
        pool.get_min_size = MagicMock(return_value=min_size)
        pool.get_max_size = MagicMock(return_value=max_size)
        pool.get_idle_size = MagicMock(return_value=idle_size)
        return pool

    async def test_health_check_all_pass(self):
        pool = self._make_pool_for_health()
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is True
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert health["checks"]["postgres_ping"]["status"] == "pass"
        assert health["checks"]["table_access"]["status"] == "pass"
        assert health["checks"]["pool_status"]["status"] == "pass"
        assert health["checks"]["pool_status"]["size"] == 10
        assert health["checks"]["pool_status"]["min_size"] == 2
        assert health["checks"]["pool_status"]["max_size"] == 20
        assert health["checks"]["pool_status"]["free_size"] == 5

    async def test_health_check_ping_result_not_1_status_fail(self):
        """If SELECT 1 returns something other than 1, postgres_ping status is 'fail'."""
        pool = self._make_pool_for_health(ping_result=0)
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["checks"]["postgres_ping"]["status"] == "fail"
        assert health["healthy"] is False

    async def test_health_check_ping_result_none(self):
        pool = self._make_pool_for_health(ping_result=None)
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["checks"]["postgres_ping"]["status"] == "fail"
        assert health["healthy"] is False

    async def test_health_check_runtime_error_caught(self):
        pool = self._make_pool_for_health(first_fetchval_raises=RuntimeError("connection refused"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False
        assert "error" in health
        assert "connection refused" in health["error"]
        assert health["checks"]["postgres_ping"]["status"] == "fail"

    async def test_health_check_postgres_error_caught(self):
        pool = self._make_pool_for_health(first_fetchval_raises=_PostgresError("db gone"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False

    async def test_health_check_value_error_caught(self):
        pool = self._make_pool_for_health(first_fetchval_raises=ValueError("bad value"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False
        assert "bad value" in health["error"]

    async def test_health_check_type_error_caught(self):
        pool = self._make_pool_for_health(first_fetchval_raises=TypeError("type issue"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False

    async def test_health_check_attribute_error_caught(self):
        pool = self._make_pool_for_health(first_fetchval_raises=AttributeError("attr missing"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False

    async def test_health_check_key_error_caught(self):
        pool = self._make_pool_for_health(first_fetchval_raises=KeyError("missing key"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False

    async def test_health_check_os_error_caught(self):
        pool = self._make_pool_for_health(first_fetchval_raises=OSError("os fail"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False

    async def test_health_check_ensure_initialized_raises(self):
        """If _ensure_initialized raises (pool is None), error is caught."""
        mgr = _make_manager(None)  # pool=None → RuntimeError

        health = await mgr.health_check()

        assert health["healthy"] is False
        assert "error" in health

    async def test_health_check_has_timestamp(self):
        pool = self._make_pool_for_health()
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert "timestamp" in health
        datetime.fromisoformat(health["timestamp"])

    async def test_health_check_latency_ms_present_and_non_negative(self):
        pool = self._make_pool_for_health()
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert "latency_ms" in health["checks"]["postgres_ping"]
        assert "latency_ms" in health["checks"]["table_access"]
        assert health["checks"]["postgres_ping"]["latency_ms"] >= 0.0
        assert health["checks"]["table_access"]["latency_ms"] >= 0.0

    async def test_health_check_initial_healthy_false_until_all_pass(self):
        """health dict starts with healthy=False — stays False if ping fails."""
        pool = self._make_pool_for_health(ping_result=0)
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert health["healthy"] is False

    async def test_health_check_pool_status_fields_present(self):
        pool = self._make_pool_for_health(pool_size=7, min_size=1, max_size=15, idle_size=3)
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        ps = health["checks"]["pool_status"]
        assert ps["size"] == 7
        assert ps["min_size"] == 1
        assert ps["max_size"] == 15
        assert ps["free_size"] == 3

    async def test_health_check_error_key_set_on_exception(self):
        pool = self._make_pool_for_health(first_fetchval_raises=RuntimeError("fatal error"))
        mgr = _make_manager(pool)

        health = await mgr.health_check()

        assert "fatal error" in health.get("error", "")


# ---------------------------------------------------------------------------
# Edge cases: ensure_initialized failure propagation
# ---------------------------------------------------------------------------


class TestEnsureInitializedPropagation:
    async def test_acquire_lock_uninitialized_propagates(self):
        """When pool is None, RuntimeError from _ensure_initialized propagates."""
        mgr = _make_manager(None)

        with pytest.raises(RuntimeError):
            await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER)

    async def test_release_lock_uninitialized_propagates(self):
        mgr = _make_manager(None)

        with pytest.raises(RuntimeError):
            await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

    async def test_extend_lock_uninitialized_propagates(self):
        mgr = _make_manager(None)

        with pytest.raises(RuntimeError):
            await mgr.extend_lock(SAGA_ID, LOCK_HOLDER)

    async def test_cleanup_uninitialized_propagates(self):
        mgr = _make_manager(None)

        with pytest.raises(RuntimeError):
            await mgr.cleanup_old_sagas(datetime.now(UTC))

    async def test_get_statistics_uninitialized_propagates(self):
        mgr = _make_manager(None)

        with pytest.raises(RuntimeError):
            await mgr.get_statistics()


# ---------------------------------------------------------------------------
# Logging coverage (verify no exceptions from logger calls)
# ---------------------------------------------------------------------------


class TestLoggingPaths:
    async def test_acquire_lock_success_logs_debug(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.DEBUG,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER)

        assert any("Lock acquired" in r.message for r in caplog.records)

    async def test_release_lock_success_logs_debug(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 1")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.DEBUG,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert any("Lock released" in r.message for r in caplog.records)

    async def test_release_lock_denied_logs_warning(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 0")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.WARNING,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert any("Lock release denied" in r.message for r in caplog.records)

    async def test_extend_lock_success_logs_debug(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.DEBUG,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            await mgr.extend_lock(SAGA_ID, LOCK_HOLDER, ttl_seconds=60)

        assert any("Lock extended" in r.message for r in caplog.records)

    async def test_cleanup_logs_info(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="DELETE 7")
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.INFO,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            await mgr.cleanup_old_sagas(datetime.now(UTC))

        assert any("Cleaned up" in r.message for r in caplog.records)

    async def test_acquire_lock_error_logs_error(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.ERROR,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            with pytest.raises(LockError):
                await mgr.acquire_lock(SAGA_ID, LOCK_HOLDER)

        assert any("Failed to acquire lock" in r.message for r in caplog.records)

    async def test_release_lock_error_logs_error(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.ERROR,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            with pytest.raises(LockError):
                await mgr.release_lock(SAGA_ID, LOCK_HOLDER)

        assert any("Failed to release lock" in r.message for r in caplog.records)

    async def test_extend_lock_error_logs_error(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.ERROR,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            with pytest.raises(LockError):
                await mgr.extend_lock(SAGA_ID, LOCK_HOLDER)

        assert any("Failed to extend lock" in r.message for r in caplog.records)

    async def test_get_statistics_error_logs_error(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.ERROR,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            with pytest.raises(RepositoryError):
                await mgr.get_statistics()

        assert any("Failed to get statistics" in r.message for r in caplog.records)

    async def test_cleanup_error_logs_error(self, caplog: Any) -> None:
        import logging

        conn = AsyncMock()
        conn.execute = AsyncMock(side_effect=_PostgresError("fail"))
        pool = _make_pool_with_conn(conn)
        mgr = _make_manager(pool)

        with caplog.at_level(
            logging.ERROR,
            logger="enhanced_agent_bus.saga_persistence.postgres.locking",
        ):
            with pytest.raises(RepositoryError):
                await mgr.cleanup_old_sagas(datetime.now(UTC))

        assert any("Failed to cleanup old sagas" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# LockError and RepositoryError structural checks
# ---------------------------------------------------------------------------


class TestExceptionStructure:
    def test_lock_error_has_correct_http_status(self):
        err = LockError("test", SAGA_ID)
        assert err.http_status_code == 423

    def test_lock_error_stores_saga_id(self):
        err = LockError("test msg", SAGA_ID)
        assert err.saga_id == SAGA_ID

    def test_repository_error_http_status(self):
        err = RepositoryError("repo failed")
        assert err.http_status_code == 500

    def test_lock_error_is_repository_error(self):
        err = LockError("test", SAGA_ID)
        assert isinstance(err, RepositoryError)

    def test_lock_error_message_content(self):
        err = LockError("lock failed hard", SAGA_ID)
        assert "lock failed hard" in str(err)
