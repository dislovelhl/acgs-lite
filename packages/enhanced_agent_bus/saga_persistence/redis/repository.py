"""
Redis Saga State Repository Implementation
Constitutional Hash: cdd01ef066bc6cf2

Production-ready Redis implementation of SagaStateRepository with:
- Redis HASH for saga state storage
- Redis SET for state/tenant indexes
- Redis LIST for compensation log (LIFO)
- Distributed locking with SET NX
- Automatic TTL management
- Pipeline operations for atomicity
"""

import time
import uuid
from datetime import timedelta

import redis.asyncio as redis

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.saga_persistence.models import PersistedSagaState, SagaState

from ..repository import RepositoryError, SagaStateRepository, VersionConflictError
from .keys import DEFAULT_LOCK_TIMEOUT_SECONDS, DEFAULT_TTL_DAYS, RedisKeyMixin
from .locking import RedisLockManager
from .queries import RedisQueryOperations
from .state import RedisStateManager

logger = get_logger(__name__)


class RedisSagaStateRepository(
    RedisQueryOperations,
    RedisStateManager,
    RedisLockManager,
    RedisKeyMixin,
    SagaStateRepository,
):
    """
    Redis-backed implementation of SagaStateRepository.

    Uses Redis HASH for saga state storage with automatic TTL.
    Implements distributed locking using SET NX with TTL.

    Key Schema:
    - acgs2:saga:state:{saga_id} - HASH containing saga state
    - acgs2:saga:checkpoint:{saga_id}:{checkpoint_id} - HASH containing checkpoint
    - acgs2:saga:compensation:{saga_id} - LIST of compensation entries (LIFO)
    - acgs2:saga:lock:{saga_id} - STRING with lock holder ID
    - acgs2:saga:index:state:{state} - SET of saga IDs in this state
    - acgs2:saga:index:tenant:{tenant_id} - SET of saga IDs for this tenant

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        redis_client: object,
        default_ttl_days: int = DEFAULT_TTL_DAYS,
        lock_timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ):
        """
        Initialize Redis saga state repository.

        Args:
            redis_client: Async Redis client (redis.asyncio or aioredis)
            default_ttl_days: Default TTL for saga data in days
            lock_timeout_seconds: Default lock timeout in seconds
        """
        self._redis = redis_client
        self._default_ttl = timedelta(days=default_ttl_days)
        self._lock_timeout = lock_timeout_seconds
        self._node_id = self._generate_node_id()

    def _generate_node_id(self) -> str:
        """Generate a unique node identifier for distributed locking."""
        return f"node-{uuid.uuid4().hex[:8]}-{int(time.time())}"

    def _get_ttl_seconds(self) -> int:
        """Get TTL in seconds."""
        return int(self._default_ttl.total_seconds())

    async def _execute_with_retry(
        self,
        operation: str,
        saga_id: str,
        func: object,
    ) -> object:
        """Execute Redis operation with error handling."""
        try:
            return await func()
        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Redis {operation} failed for saga {saga_id}: {e}"
            )
            raise RepositoryError(f"Redis {operation} failed: {e}", saga_id) from e

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    async def save(self, saga: PersistedSagaState) -> bool:
        """
        Save or update a saga state with optimistic locking.

        Uses Redis pipeline for atomic operations:
        1. Check version if saga exists
        2. Update state hash
        3. Update indexes
        4. Set TTL

        Args:
            saga: The saga state to persist.

        Returns:
            True if save was successful, False if version conflict occurred.

        Raises:
            RepositoryError: On storage backend failures.
        """
        saga_id = saga.saga_id
        state_key = self._state_key(saga_id)
        ttl_seconds = self._get_ttl_seconds()

        try:
            # Check for version conflict
            existing_data = await self._redis.hgetall(state_key)

            if existing_data:
                # Saga exists - verify version for optimistic locking
                existing_version = int(existing_data.get("version", "0"))
                # Expected version is current version (before increment)
                if existing_version != saga.version - 1 and existing_version != saga.version:
                    logger.warning(
                        f"[{CONSTITUTIONAL_HASH}] Version conflict for saga {saga_id}: "
                        f"expected {saga.version - 1} or {saga.version}, got {existing_version}"
                    )
                    raise VersionConflictError(saga_id, saga.version, existing_version)

                # Get old state for index cleanup
                old_state_str = existing_data.get("state", "")
                old_state = SagaState(old_state_str) if old_state_str else None
            else:
                old_state = None

            # Prepare saga data for Redis hash
            saga_hash = saga.to_redis_hash()

            # Use pipeline for atomicity
            pipe = self._redis.pipeline()

            # Save saga state as hash
            pipe.hset(state_key, mapping=saga_hash)
            pipe.expire(state_key, ttl_seconds)

            # Update state index
            if old_state and old_state != saga.state:
                # Remove from old state index
                pipe.srem(self._state_index_key(old_state), saga_id)

            pipe.sadd(self._state_index_key(saga.state), saga_id)

            # Update tenant index
            if saga.tenant_id:
                pipe.sadd(self._tenant_index_key(saga.tenant_id), saga_id)

            # Execute pipeline
            await pipe.execute()

            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Saved saga {saga_id} "
                f"(state={saga.state.value}, version={saga.version})"
            )
            return True

        except VersionConflictError:
            raise
        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to save saga {saga_id}: {e}")
            raise RepositoryError(f"Failed to save saga: {e}", saga_id) from e

    async def get(self, saga_id: str) -> PersistedSagaState | None:
        """
        Retrieve a saga by its ID.

        Args:
            saga_id: Unique identifier of the saga.

        Returns:
            The saga state if found, None otherwise.

        Raises:
            RepositoryError: On storage backend failures.
        """
        state_key = self._state_key(saga_id)

        try:
            data = await self._redis.hgetall(state_key)

            if not data:
                return None

            return PersistedSagaState.from_redis_hash(data)

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get saga {saga_id}: {e}")
            raise RepositoryError(f"Failed to get saga: {e}", saga_id) from e

    async def delete(self, saga_id: str) -> bool:
        """
        Delete a saga by its ID.

        Cleans up:
        - Saga state hash
        - Compensation log
        - Checkpoints
        - Index entries

        Args:
            saga_id: Unique identifier of the saga to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        state_key = self._state_key(saga_id)

        try:
            # Get saga for cleanup
            data = await self._redis.hgetall(state_key)

            if not data:
                return False

            saga = PersistedSagaState.from_redis_hash(data)

            # Use pipeline for atomic cleanup
            pipe = self._redis.pipeline()

            # Delete main state
            pipe.delete(state_key)

            # Delete compensation log
            pipe.delete(self._compensation_key(saga_id))

            # Delete from state index
            pipe.srem(self._state_index_key(saga.state), saga_id)

            # Delete from tenant index
            if saga.tenant_id:
                pipe.srem(self._tenant_index_key(saga.tenant_id), saga_id)

            # Delete checkpoints
            checkpoint_list_key = self._checkpoint_list_key(saga_id)
            checkpoint_ids = await self._redis.zrange(checkpoint_list_key, 0, -1)

            if checkpoint_ids:
                for cp_id in checkpoint_ids:
                    cp_id_str = cp_id if isinstance(cp_id, str) else cp_id.decode("utf-8")
                    pipe.delete(self._checkpoint_key(saga_id, cp_id_str))

            pipe.delete(checkpoint_list_key)

            # Delete lock if exists
            pipe.delete(self._lock_key(saga_id))

            await pipe.execute()

            logger.info(f"[{CONSTITUTIONAL_HASH}] Deleted saga {saga_id}")
            return True

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to delete saga {saga_id}: {e}")
            raise RepositoryError(f"Failed to delete saga: {e}", saga_id) from e

    async def exists(self, saga_id: str) -> bool:
        """
        Check if a saga exists.

        Args:
            saga_id: Unique identifier to check.

        Returns:
            True if saga exists, False otherwise.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            return bool(await self._redis.exists(self._state_key(saga_id)))
        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to check saga existence {saga_id}: {e}")
            raise RepositoryError(f"Failed to check saga existence: {e}", saga_id) from e


__all__ = ["RedisSagaStateRepository"]
