"""
Redis Query Operations for Saga Persistence
Constitutional Hash: 608508a9bd224290

Provides query operations for listing and counting sagas by various criteria.
Implements index-based lookups for efficient querying.
"""

from datetime import datetime

import redis.asyncio as redis

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.saga_persistence.models import PersistedSagaState, SagaState

from ..repository import RepositoryError
from .keys import RedisKeyMixin

logger = get_logger(__name__)


class RedisQueryOperations(RedisKeyMixin):
    """
    Mixin providing query operations for Redis saga repository.

    Implements listing and counting operations using Redis SET indexes
    for efficient lookups without full table scans.

    Constitutional Hash: 608508a9bd224290
    """

    # Type hints for mixin - these are provided by the main repository class
    _redis: redis.Redis

    async def get(self, saga_id: str) -> PersistedSagaState | None:
        """Get saga by ID (implemented in main repository)."""
        raise NotImplementedError("Must be implemented by repository class")

    async def list_by_tenant(
        self,
        tenant_id: str,
        state: SagaState | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PersistedSagaState]:
        """
        List sagas for a specific tenant.

        Args:
            tenant_id: Tenant identifier for isolation.
            state: Optional state filter.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of matching sagas.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            # Get saga IDs from tenant index
            saga_ids = await self._redis.smembers(self._tenant_index_key(tenant_id))

            if not saga_ids:
                return []

            # If state filter, intersect with state index
            if state:
                state_saga_ids = await self._redis.smembers(self._state_index_key(state))
                saga_ids = saga_ids.intersection(state_saga_ids)

            # Sort and paginate
            saga_id_list = sorted(
                [s if isinstance(s, str) else s.decode("utf-8") for s in saga_ids],
                reverse=True,
            )
            paginated_ids = saga_id_list[offset : offset + limit]

            # Fetch sagas
            sagas = []
            for saga_id in paginated_ids:
                saga = await self.get(saga_id)
                if saga:
                    sagas.append(saga)

            # Sort by created_at descending
            sagas.sort(key=lambda s: s.created_at, reverse=True)

            return sagas

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list sagas by tenant {tenant_id}: {e}")
            raise RepositoryError(f"Failed to list sagas by tenant: {e}") from e

    async def list_by_state(
        self,
        state: SagaState,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PersistedSagaState]:
        """
        List sagas in a specific state across all tenants.

        Args:
            state: The saga state to filter by.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of matching sagas.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            # Get saga IDs from state index
            saga_ids = await self._redis.smembers(self._state_index_key(state))

            if not saga_ids:
                return []

            # Sort and paginate
            saga_id_list = sorted(
                [s if isinstance(s, str) else s.decode("utf-8") for s in saga_ids],
                reverse=True,
            )
            paginated_ids = saga_id_list[offset : offset + limit]

            # Fetch sagas
            sagas = []
            for saga_id in paginated_ids:
                saga = await self.get(saga_id)
                if saga:
                    sagas.append(saga)

            # Sort by created_at descending
            sagas.sort(key=lambda s: s.created_at, reverse=True)

            return sagas

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list sagas by state {state}: {e}")
            raise RepositoryError(f"Failed to list sagas by state: {e}") from e

    async def list_pending_compensations(
        self,
        limit: int = 100,
    ) -> list[PersistedSagaState]:
        """
        List sagas that need compensation.

        Returns sagas in COMPENSATING or RUNNING states.

        Args:
            limit: Maximum number of results.

        Returns:
            List of sagas requiring compensation attention.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            # Get sagas in COMPENSATING state
            compensating_ids = await self._redis.smembers(
                self._state_index_key(SagaState.COMPENSATING)
            )

            # Also check RUNNING sagas that may have failed mid-execution
            running_ids = await self._redis.smembers(self._state_index_key(SagaState.RUNNING))

            # Combine and dedupe
            all_ids = set()
            for sid in compensating_ids:
                all_ids.add(sid if isinstance(sid, str) else sid.decode("utf-8"))
            for sid in running_ids:
                all_ids.add(sid if isinstance(sid, str) else sid.decode("utf-8"))

            # Fetch and filter
            sagas = []
            for saga_id in list(all_ids)[:limit]:
                saga = await self.get(saga_id)
                if saga:
                    sagas.append(saga)

            return sagas

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list pending compensations: {e}")
            raise RepositoryError(f"Failed to list pending compensations: {e}") from e

    async def list_timed_out(
        self,
        since: datetime,
        limit: int = 100,
    ) -> list[PersistedSagaState]:
        """
        List sagas that have timed out.

        Args:
            since: Timestamp to check for timeout.
            limit: Maximum number of results.

        Returns:
            List of timed out sagas.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            # Get RUNNING sagas
            running_ids = await self._redis.smembers(self._state_index_key(SagaState.RUNNING))

            timed_out = []
            for saga_id in running_ids:
                saga_id_str = saga_id if isinstance(saga_id, str) else saga_id.decode("utf-8")
                saga = await self.get(saga_id_str)

                if saga and saga.started_at:
                    # Check if saga has exceeded its timeout
                    elapsed_ms = (since - saga.started_at).total_seconds() * 1000
                    if elapsed_ms > saga.timeout_ms:
                        timed_out.append(saga)

                if len(timed_out) >= limit:
                    break

            return timed_out

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list timed out sagas: {e}")
            raise RepositoryError(f"Failed to list timed out sagas: {e}") from e

    async def count_by_state(self, state: SagaState) -> int:
        """
        Count sagas in a specific state.

        Args:
            state: The saga state to count.

        Returns:
            Number of sagas in the specified state.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            return int(await self._redis.scard(self._state_index_key(state)))
        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to count sagas by state: {e}")
            raise RepositoryError(f"Failed to count sagas by state: {e}") from e

    async def count_by_tenant(self, tenant_id: str) -> int:
        """
        Count all sagas for a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Total number of sagas for the tenant.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            return int(await self._redis.scard(self._tenant_index_key(tenant_id)))
        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to count sagas by tenant: {e}")
            raise RepositoryError(f"Failed to count sagas by tenant: {e}") from e


__all__ = ["RedisQueryOperations"]
