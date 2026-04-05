"""
PostgreSQL Saga Repository Locking and Maintenance Operations
Constitutional Hash: 608508a9bd224290

Contains distributed locking and maintenance operations (cleanup,
statistics, health checks) for the PostgreSQL saga state repository.
"""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import asyncpg

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.saga_persistence.models import SagaState

from ..repository import LockError, RepositoryError
from .schema import DEFAULT_LOCK_TIMEOUT_SECONDS

logger = get_logger(__name__)
LOCK_HEALTH_CHECK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    OSError,
    asyncpg.PostgresError,
)


class PostgresLockManager:
    """
    Mixin class providing locking and maintenance operations for PostgresSagaStateRepository.

    Handles distributed locking, cleanup, statistics, and health checks.

    Constitutional Hash: 608508a9bd224290
    """

    # Type hints for mixin - these are provided by the main repository class
    _pool: asyncpg.Pool | None
    _node_id: str

    def _ensure_initialized(self) -> asyncpg.Pool:
        """Ensure the repository is initialized and return the pool."""
        raise NotImplementedError("Must be implemented by repository class")

    # =========================================================================
    # Locking Operations
    # =========================================================================

    async def acquire_lock(
        self,
        saga_id: str,
        lock_holder: str,
        ttl_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> bool:
        """
        Acquire a distributed lock on a saga.

        Uses PostgreSQL table-based locking with expiration.

        Args:
            saga_id: Unique identifier of the saga to lock.
            lock_holder: Identifier of the lock holder.
            ttl_seconds: Lock time-to-live in seconds.

        Returns:
            True if lock was acquired, False if already locked.

        Raises:
            LockError: On storage backend failures.
        """
        pool = self._ensure_initialized()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        try:
            async with pool.acquire() as conn:
                # Clean up expired locks first
                await conn.execute(
                    "DELETE FROM saga_locks WHERE expires_at < $1",
                    now,
                )

                # Try to insert lock
                try:
                    await conn.execute(
                        """
                        INSERT INTO saga_locks (
                            saga_id, lock_holder, acquired_at, expires_at, constitutional_hash
                        ) VALUES ($1, $2, $3, $4, $5)
                        """,
                        uuid.UUID(saga_id),
                        lock_holder,
                        now,
                        expires_at,
                        CONSTITUTIONAL_HASH,
                    )
                    logger.debug(
                        f"[{CONSTITUTIONAL_HASH}] Lock acquired for saga {saga_id} by {lock_holder}"
                    )
                    return True
                except asyncpg.UniqueViolationError:
                    # Lock already held
                    return False

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to acquire lock: {e}")
            raise LockError(f"Failed to acquire lock: {e}", saga_id) from e

    async def release_lock(
        self,
        saga_id: str,
        lock_holder: str,
    ) -> bool:
        """
        Release a distributed lock on a saga.

        Only releases if the lock is held by the specified holder.

        Args:
            saga_id: Unique identifier of the saga.
            lock_holder: Identifier of the lock holder.

        Returns:
            True if lock was released, False if not held by this holder.

        Raises:
            LockError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM saga_locks
                    WHERE saga_id = $1 AND lock_holder = $2
                    """,
                    uuid.UUID(saga_id),
                    lock_holder,
                )
                released: bool = result == "DELETE 1"

                if released:
                    logger.debug(
                        f"[{CONSTITUTIONAL_HASH}] Lock released for saga {saga_id} by {lock_holder}"
                    )
                else:
                    logger.warning(
                        f"[{CONSTITUTIONAL_HASH}] Lock release denied for saga {saga_id}: "
                        f"not held by {lock_holder}"
                    )
                return released

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to release lock: {e}")
            raise LockError(f"Failed to release lock: {e}", saga_id) from e

    async def extend_lock(
        self,
        saga_id: str,
        lock_holder: str,
        ttl_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> bool:
        """
        Extend a distributed lock's TTL.

        Args:
            saga_id: Unique identifier of the saga.
            lock_holder: Identifier of the lock holder.
            ttl_seconds: New TTL in seconds.

        Returns:
            True if lock was extended, False if not held by this holder.

        Raises:
            LockError: On storage backend failures.
        """
        pool = self._ensure_initialized()
        now = datetime.now(UTC)
        new_expires_at = now + timedelta(seconds=ttl_seconds)

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE saga_locks
                    SET expires_at = $3
                    WHERE saga_id = $1 AND lock_holder = $2
                    """,
                    uuid.UUID(saga_id),
                    lock_holder,
                    new_expires_at,
                )
                extended: bool = result == "UPDATE 1"

                if extended:
                    logger.debug(
                        f"[{CONSTITUTIONAL_HASH}] Lock extended for saga {saga_id} "
                        f"by {lock_holder} ({ttl_seconds}s)"
                    )
                return extended

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to extend lock: {e}")
            raise LockError(f"Failed to extend lock: {e}", saga_id) from e

    @asynccontextmanager
    async def distributed_lock(
        self,
        saga_id: str,
        ttl_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> AsyncIterator[bool]:
        """
        Context manager for distributed locking.

        Usage:
            async with repo.distributed_lock(saga_id) as acquired:
                if acquired:
                    # Do work while holding lock
                    pass

        Args:
            saga_id: Unique identifier of the saga to lock.
            ttl_seconds: Lock time-to-live in seconds.

        Yields:
            True if lock was acquired, False otherwise.
        """
        lock_holder = f"{self._node_id}-{uuid.uuid4().hex[:8]}"
        acquired = await self.acquire_lock(saga_id, lock_holder, ttl_seconds)

        try:
            yield acquired
        finally:
            if acquired:
                await self.release_lock(saga_id, lock_holder)

    # =========================================================================
    # Maintenance Operations
    # =========================================================================

    async def cleanup_old_sagas(
        self,
        older_than: datetime,
        terminal_only: bool = True,
    ) -> int:
        """
        Delete old sagas for storage management.

        Args:
            older_than: Delete sagas completed/failed before this timestamp.
            terminal_only: If True, only delete terminal sagas.

        Returns:
            Number of sagas deleted.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                if terminal_only:
                    result = await conn.execute(
                        """
                        DELETE FROM saga_states
                        WHERE state IN ($1, $2, $3)
                          AND COALESCE(completed_at, compensated_at, failed_at, created_at) < $4
                        """,
                        SagaState.COMPLETED.value,
                        SagaState.COMPENSATED.value,
                        SagaState.FAILED.value,
                        older_than,
                    )
                else:
                    result = await conn.execute(
                        """
                        DELETE FROM saga_states
                        WHERE COALESCE(completed_at, compensated_at, failed_at, created_at) < $1
                        """,
                        older_than,
                    )

                # Parse "DELETE N" to get count
                deleted_count = int(result.split(" ")[1]) if result else 0

                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] Cleaned up {deleted_count} old sagas "
                    f"(older than {older_than.isoformat()})"
                )
                return deleted_count

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to cleanup old sagas: {e}")
            raise RepositoryError(f"Failed to cleanup old sagas: {e}") from e

    async def get_statistics(
        self,
    ) -> JSONDict:
        """
        Get repository statistics.

        Returns:
            Dictionary containing repository statistics.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                # Count by state
                state_counts = await conn.fetch("""
                    SELECT state, COUNT(*) as count
                    FROM saga_states
                    GROUP BY state
                    """)

                # Total count
                total = await conn.fetchval("SELECT COUNT(*) FROM saga_states")

                # Checkpoint count
                checkpoint_count = await conn.fetchval("SELECT COUNT(*) FROM saga_checkpoints")

                # Lock count
                lock_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM saga_locks WHERE expires_at > $1",
                    datetime.now(UTC),
                )

                counts_by_state = {row["state"]: row["count"] for row in state_counts}

                return {
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "counts_by_state": counts_by_state,
                    "total_sagas": int(total) if total else 0,
                    "total_checkpoints": int(checkpoint_count) if checkpoint_count else 0,
                    "active_locks": int(lock_count) if lock_count else 0,
                }

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get statistics: {e}")
            raise RepositoryError(f"Failed to get statistics: {e}") from e

    async def health_check(
        self,
    ) -> JSONDict:
        """
        Perform a health check on the repository.

        Returns:
            Dictionary with health status and details.

        Raises:
            RepositoryError: On storage backend failures.
        """
        health: JSONDict = {
            "healthy": False,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {},
        }

        try:
            pool = self._ensure_initialized()

            async with pool.acquire() as conn:
                # Test connectivity
                start_time = time.perf_counter()
                result = await conn.fetchval("SELECT 1")
                latency_ms = (time.perf_counter() - start_time) * 1000

                health["checks"]["postgres_ping"] = {
                    "status": "pass" if result == 1 else "fail",
                    "latency_ms": round(latency_ms, 2),
                }

                # Test table access
                start_time = time.perf_counter()
                await conn.fetchval("SELECT COUNT(*) FROM saga_states LIMIT 1")
                table_latency_ms = (time.perf_counter() - start_time) * 1000

                health["checks"]["table_access"] = {
                    "status": "pass",
                    "latency_ms": round(table_latency_ms, 2),
                }

                # Pool status
                health["checks"]["pool_status"] = {
                    "status": "pass",
                    "size": pool.get_size(),
                    "min_size": pool.get_min_size(),
                    "max_size": pool.get_max_size(),
                    "free_size": pool.get_idle_size(),
                }

                # All checks passed
                health["healthy"] = all(
                    check.get("status") == "pass" for check in health["checks"].values()
                )

        except LOCK_HEALTH_CHECK_ERRORS as e:
            health["error"] = str(e)
            health["checks"]["postgres_ping"] = {"status": "fail", "error": str(e)}

        return health


__all__ = ["PostgresLockManager"]
