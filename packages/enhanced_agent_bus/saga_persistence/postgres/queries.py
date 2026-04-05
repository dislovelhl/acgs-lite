"""
PostgreSQL Saga Repository Query Operations
Constitutional Hash: 608508a9bd224290

Contains query operation methods for listing and counting sagas
by various criteria (tenant, state, timeouts, etc.).
"""

from datetime import datetime

import asyncpg

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.saga_persistence.models import PersistedSagaState, SagaState

from ..repository import RepositoryError

logger = get_logger(__name__)


class PostgresQueryOperations:
    """
    Mixin class providing query operations for PostgresSagaStateRepository.

    Provides methods to list and count sagas by tenant, state, and other criteria.

    Constitutional Hash: 608508a9bd224290
    """

    # Type hints for mixin - these are provided by the main repository class
    _pool: asyncpg.Pool | None

    def _ensure_initialized(self) -> asyncpg.Pool:
        """Ensure the repository is initialized and return the pool."""
        raise NotImplementedError("Must be implemented by repository class")

    def _row_to_saga(self, row: asyncpg.Record) -> PersistedSagaState:
        """Convert a database row to PersistedSagaState."""
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
            List of matching sagas, ordered by created_at descending.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                if state:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM saga_states
                        WHERE tenant_id = $1 AND state = $2
                        ORDER BY created_at DESC
                        LIMIT $3 OFFSET $4
                        """,
                        tenant_id,
                        state.value,
                        limit,
                        offset,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM saga_states
                        WHERE tenant_id = $1
                        ORDER BY created_at DESC
                        LIMIT $2 OFFSET $3
                        """,
                        tenant_id,
                        limit,
                        offset,
                    )

                return [self._row_to_saga(row) for row in rows]

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list sagas by tenant: {e}")
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
            List of matching sagas, ordered by created_at descending.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM saga_states
                    WHERE state = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    state.value,
                    limit,
                    offset,
                )

                return [self._row_to_saga(row) for row in rows]

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list sagas by state: {e}")
            raise RepositoryError(f"Failed to list sagas by state: {e}") from e

    async def list_pending_compensations(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PersistedSagaState]:
        """
        List sagas that need compensation.

        Returns sagas in COMPENSATING or RUNNING states that may need
        recovery attention.

        Args:
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of sagas requiring compensation attention.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM saga_states
                    WHERE state IN ($1, $2)
                    ORDER BY created_at DESC
                    LIMIT $4 OFFSET $5
                    """,
                    SagaState.COMPENSATING.value,
                    SagaState.RUNNING.value,
                    limit,
                    offset,
                )

                return [self._row_to_saga(row) for row in rows]

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list pending compensations: {e}")
            raise RepositoryError(f"Failed to list pending compensations: {e}") from e

    async def list_timed_out(
        self,
        since: datetime,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PersistedSagaState]:
        """
        List sagas that have timed out.

        Returns RUNNING sagas that were started before the given timestamp
        and have exceeded their timeout_ms.

        Args:
            since: Timestamp to check for timeout.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of timed out sagas.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM saga_states
                    WHERE state = $1
                      AND started_at IS NOT NULL
                      AND started_at + (timeout_ms * INTERVAL '1 millisecond') < $2
                    ORDER BY started_at ASC
                    LIMIT $4 OFFSET $5
                    """,
                    SagaState.RUNNING.value,
                    since,
                    limit,
                    offset,
                )

                return [self._row_to_saga(row) for row in rows]

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list timed out sagas: {e}")
            raise RepositoryError(f"Failed to list timed out sagas: {e}") from e

    async def count_by_state(
        self,
        state: SagaState,
    ) -> int:
        """
        Count sagas in a specific state.

        Args:
            state: The saga state to count.

        Returns:
            Number of sagas in the specified state.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM saga_states WHERE state = $1",
                    state.value,
                )
                return int(count) if count else 0

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to count sagas by state: {e}")
            raise RepositoryError(f"Failed to count sagas by state: {e}") from e

    async def count_by_tenant(
        self,
        tenant_id: str,
    ) -> int:
        """
        Count all sagas for a tenant.

        Args:
            tenant_id: Tenant identifier.

        Returns:
            Total number of sagas for the tenant.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM saga_states WHERE tenant_id = $1",
                    tenant_id,
                )
                return int(count) if count else 0

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to count sagas by tenant: {e}")
            raise RepositoryError(f"Failed to count sagas by tenant: {e}") from e


__all__ = ["PostgresQueryOperations"]
