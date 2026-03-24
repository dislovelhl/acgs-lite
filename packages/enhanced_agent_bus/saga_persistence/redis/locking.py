"""
Redis Distributed Locking for Saga Persistence
Constitutional Hash: cdd01ef066bc6cf2

Provides distributed locking operations and maintenance utilities
for saga state management using Redis SET NX with TTL.
"""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import redis.asyncio as redis

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.saga_persistence.models import PersistedSagaState, SagaState

from ..repository import LockError, RepositoryError
from .keys import DEFAULT_LOCK_TIMEOUT_SECONDS, RedisKeyMixin

logger = get_logger(__name__)


class RedisLockManager(RedisKeyMixin):
    """
    Mixin providing distributed locking and maintenance operations
    for Redis saga repository.

    Implements distributed locks using Redis SET NX with TTL,
    providing safe concurrent access to saga state.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    # Type hints for mixin - these are provided by the main repository class
    _redis: redis.Redis
    _node_id: str

    async def get(self, saga_id: str) -> PersistedSagaState | None:
        """Get saga by ID (implemented in main repository)."""
        raise NotImplementedError("Must be implemented by repository class")

    async def delete(self, saga_id: str) -> bool:
        """Delete saga by ID (implemented in main repository)."""
        raise NotImplementedError("Must be implemented by repository class")

    async def count_by_state(self, state: SagaState) -> int:
        """Count sagas by state (implemented in queries mixin)."""
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
        Acquire a distributed lock on a saga using SET NX.

        Args:
            saga_id: Unique identifier of the saga to lock.
            lock_holder: Identifier of the lock holder.
            ttl_seconds: Lock time-to-live in seconds.

        Returns:
            True if lock was acquired, False if already locked.

        Raises:
            RepositoryError: On storage backend failures.
        """
        lock_key = self._lock_key(saga_id)

        try:
            # Use SET NX (set if not exists) with TTL
            acquired = await self._redis.set(
                lock_key,
                lock_holder,
                nx=True,
                ex=ttl_seconds,
            )

            if acquired:
                logger.debug(
                    f"[{CONSTITUTIONAL_HASH}] Lock acquired for saga {saga_id} by {lock_holder}"
                )
            return bool(acquired)

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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
            RepositoryError: On storage backend failures.
        """
        lock_key = self._lock_key(saga_id)

        try:
            # Check current holder
            current_holder = await self._redis.get(lock_key)

            if not current_holder:
                return False

            current_holder_str = (
                current_holder
                if isinstance(current_holder, str)
                else current_holder.decode("utf-8")
            )

            if current_holder_str != lock_holder:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Lock release denied for saga {saga_id}: "
                    f"held by {current_holder_str}, requested by {lock_holder}"
                )
                return False

            # Delete lock
            await self._redis.delete(lock_key)
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Lock released for saga {saga_id} by {lock_holder}"
            )
            return True

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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
            RepositoryError: On storage backend failures.
        """
        lock_key = self._lock_key(saga_id)

        try:
            # Verify holder
            current_holder = await self._redis.get(lock_key)

            if not current_holder:
                return False

            current_holder_str = (
                current_holder
                if isinstance(current_holder, str)
                else current_holder.decode("utf-8")
            )

            if current_holder_str != lock_holder:
                return False

            # Extend TTL
            await self._redis.expire(lock_key, ttl_seconds)
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Lock extended for saga {saga_id} "
                f"by {lock_holder} ({ttl_seconds}s)"
            )
            return True

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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
        try:
            deleted_count = 0
            states_to_check = [SagaState.COMPLETED, SagaState.COMPENSATED, SagaState.FAILED]

            if not terminal_only:
                states_to_check.extend([SagaState.INITIALIZED, SagaState.RUNNING])

            for state in states_to_check:
                saga_ids = await self._redis.smembers(self._state_index_key(state))

                for saga_id in saga_ids:
                    saga_id_str = saga_id if isinstance(saga_id, str) else saga_id.decode("utf-8")
                    saga = await self.get(saga_id_str)

                    if not saga:
                        continue

                    # Check age based on terminal timestamp or created_at
                    check_time = (
                        saga.completed_at
                        or saga.compensated_at
                        or saga.failed_at
                        or saga.created_at
                    )

                    if check_time < older_than:
                        if await self.delete(saga_id_str):
                            deleted_count += 1

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Cleaned up {deleted_count} old sagas "
                f"(older than {older_than.isoformat()})"
            )
            return deleted_count

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to cleanup old sagas: {e}")
            raise RepositoryError(f"Failed to cleanup old sagas: {e}") from e

    async def get_statistics(self) -> JSONDict:
        """
        Get repository statistics.

        Returns:
            Dictionary containing repository statistics.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            stats: JSONDict = {
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "timestamp": datetime.now(UTC).isoformat(),
                "counts_by_state": {},
                "total_sagas": 0,
            }

            # Count by state
            total = 0
            for state in SagaState:
                count = await self.count_by_state(state)
                stats["counts_by_state"][state.value] = count
                total += count

            stats["total_sagas"] = total

            return stats

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get statistics: {e}")
            raise RepositoryError(f"Failed to get statistics: {e}") from e

    async def health_check(self) -> JSONDict:
        """
        Perform a health check on the repository.

        Returns:
            Dictionary with health status and details.

        Raises:
            RepositoryError: On storage backend failures.
        """
        from .keys import SAGA_STATE_PREFIX

        health: JSONDict = {
            "healthy": False,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {},
        }

        try:
            # Test Redis connectivity
            start_time = time.perf_counter()
            pong = await self._redis.ping()
            latency_ms = (time.perf_counter() - start_time) * 1000

            health["checks"]["redis_ping"] = {
                "status": "pass" if pong else "fail",
                "latency_ms": round(latency_ms, 2),
            }

            # Test basic operations
            test_key = f"{SAGA_STATE_PREFIX}healthcheck:{uuid.uuid4().hex[:8]}"
            await self._redis.setex(test_key, 10, "test")
            value = await self._redis.get(test_key)
            await self._redis.delete(test_key)

            health["checks"]["redis_ops"] = {
                "status": "pass" if value else "fail",
            }

            # All checks passed
            health["healthy"] = all(
                check.get("status") == "pass" for check in health["checks"].values()
            )

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            health["error"] = str(e)
            health["checks"]["redis_ping"] = {"status": "fail", "error": str(e)}

        return health


__all__ = ["RedisLockManager"]
