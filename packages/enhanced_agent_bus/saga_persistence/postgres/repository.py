"""
PostgreSQL Saga State Repository Implementation
Constitutional Hash: 608508a9bd224290

Production-ready PostgreSQL implementation of SagaStateRepository with:
- asyncpg for high-performance async database operations
- Connection pooling for efficient resource management
- Optimistic locking via version field
- Distributed locking with advisory locks
- Full transaction support for atomicity
- JSONB storage for complex fields

Database Schema:
    - saga_states: Main saga state table
    - saga_checkpoints: Recovery checkpoints
    - saga_locks: Distributed lock management
"""

import json
import time
import uuid

import asyncpg

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.saga_persistence.models import (
    CompensationEntry,
    CompensationStrategy,
    PersistedSagaState,
    PersistedStepSnapshot,
    SagaCheckpoint,
    SagaState,
)

from ..repository import (
    RepositoryError,
    SagaStateRepository,
    VersionConflictError,
)
from .locking import PostgresLockManager
from .queries import PostgresQueryOperations
from .schema import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_POOL_MAX_SIZE,
    DEFAULT_POOL_MIN_SIZE,
    SCHEMA_SQL,
)
from .state import PostgresStateManager

logger = get_logger(__name__)
REPOSITORY_INITIALIZATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    OSError,
    asyncpg.PostgresError,
)


class PostgresSagaStateRepository(
    PostgresQueryOperations,
    PostgresStateManager,
    PostgresLockManager,
    SagaStateRepository,
):
    """
    PostgreSQL-backed implementation of SagaStateRepository.

    Uses asyncpg for high-performance async database operations with
    connection pooling. Supports full ACID transactions and optimistic
    locking via version field.

    Features:
    - Connection pooling with configurable min/max connections
    - Optimistic locking to prevent lost updates
    - Distributed locking via advisory locks
    - JSONB storage for complex nested structures
    - Automatic schema initialization

    This class uses multiple inheritance to compose functionality from:
    - PostgresQueryOperations: Query and listing operations
    - PostgresStateManager: State transitions and checkpoints
    - PostgresLockManager: Distributed locking and maintenance

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        dsn: str | None = None,
        pool: asyncpg.Pool | None = None,
        pool_min_size: int = DEFAULT_POOL_MIN_SIZE,
        pool_max_size: int = DEFAULT_POOL_MAX_SIZE,
        lock_timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
        auto_initialize_schema: bool = True,
    ):
        """
        Initialize PostgreSQL saga state repository.

        Args:
            dsn: PostgreSQL connection string (required if pool not provided)
            pool: Existing asyncpg connection pool (optional)
            pool_min_size: Minimum connections in pool (default 5)
            pool_max_size: Maximum connections in pool (default 20)
            lock_timeout_seconds: Default lock timeout in seconds (default 30)
            auto_initialize_schema: Whether to auto-create tables (default True)
        """
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = pool
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size
        self._lock_timeout = lock_timeout_seconds
        self._auto_initialize_schema = auto_initialize_schema
        self._node_id = self._generate_node_id()
        self._initialized = pool is not None

    def _generate_node_id(self) -> str:
        """Generate a unique node identifier for distributed locking."""
        return f"node-{uuid.uuid4().hex[:8]}-{int(time.time())}"

    async def initialize(self) -> None:
        """
        Initialize the repository with connection pool and schema.

        Creates the asyncpg connection pool if not provided, and optionally
        initializes the database schema.

        Raises:
            RepositoryError: If initialization fails.
        """
        if self._initialized:
            return

        try:
            if self._pool is None:
                if not self._dsn:
                    raise RepositoryError("DSN required when pool not provided")

                self._pool = await asyncpg.create_pool(
                    dsn=self._dsn,
                    min_size=self._pool_min_size,
                    max_size=self._pool_max_size,
                )
                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] PostgreSQL connection pool created "
                    f"(min={self._pool_min_size}, max={self._pool_max_size})"
                )

            if self._auto_initialize_schema:
                await self._initialize_schema()

            self._initialized = True

        except REPOSITORY_INITIALIZATION_ERRORS as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to initialize repository: {e}")
            raise RepositoryError(f"Failed to initialize repository: {e}") from e

    async def _initialize_schema(self) -> None:
        """Initialize database schema if not exists."""
        if self._pool is None:
            raise RepositoryError("Pool not initialized")

        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            logger.info(f"[{CONSTITUTIONAL_HASH}] Database schema initialized")

    async def close(self) -> None:
        """
        Close the repository and release resources.

        Closes the connection pool gracefully.
        """
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.info(f"[{CONSTITUTIONAL_HASH}] PostgreSQL connection pool closed")

    def _ensure_initialized(self) -> asyncpg.Pool:
        """Ensure the repository is initialized and return the pool."""
        if self._pool is None:
            raise RepositoryError("Repository not initialized. Call initialize() first.")
        return self._pool

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    async def save(self, saga: PersistedSagaState) -> bool:
        """
        Save or update a saga state with optimistic locking.

        Uses UPSERT with version check for optimistic locking. If the saga
        exists with a different version, raises VersionConflictError.

        Args:
            saga: The saga state to persist.

        Returns:
            True if save was successful.

        Raises:
            VersionConflictError: If version conflict occurred.
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                # Check for existing saga and version
                existing = await conn.fetchrow(
                    "SELECT version FROM saga_states WHERE saga_id = $1",
                    uuid.UUID(saga.saga_id),
                )

                if existing:
                    existing_version = existing["version"]
                    # Optimistic locking check
                    if existing_version != saga.version - 1 and existing_version != saga.version:
                        raise VersionConflictError(saga.saga_id, saga.version, existing_version)

                    # Update existing saga
                    await conn.execute(
                        """
                        UPDATE saga_states SET
                            saga_name = $2,
                            tenant_id = $3,
                            correlation_id = $4,
                            state = $5,
                            compensation_strategy = $6,
                            current_step_index = $7,
                            version = $8,
                            steps = $9,
                            context = $10,
                            metadata = $11,
                            compensation_log = $12,
                            started_at = $13,
                            completed_at = $14,
                            failed_at = $15,
                            compensated_at = $16,
                            total_duration_ms = $17,
                            failure_reason = $18,
                            timeout_ms = $19,
                            constitutional_hash = $20
                        WHERE saga_id = $1 AND version <= $8
                        """,
                        uuid.UUID(saga.saga_id),
                        saga.saga_name,
                        saga.tenant_id,
                        uuid.UUID(saga.correlation_id),
                        saga.state.value,
                        saga.compensation_strategy.value,
                        saga.current_step_index,
                        saga.version,
                        json.dumps([s.to_dict() for s in saga.steps]),
                        json.dumps(saga.context),
                        json.dumps(saga.metadata),
                        json.dumps([e.to_dict() for e in saga.compensation_log]),
                        saga.started_at,
                        saga.completed_at,
                        saga.failed_at,
                        saga.compensated_at,
                        saga.total_duration_ms,
                        saga.failure_reason,
                        saga.timeout_ms,
                        saga.constitutional_hash,
                    )
                else:
                    # Insert new saga
                    await conn.execute(
                        """
                        INSERT INTO saga_states (
                            saga_id, saga_name, tenant_id, correlation_id,
                            state, compensation_strategy, current_step_index, version,
                            steps, context, metadata, compensation_log,
                            created_at, started_at, completed_at, failed_at,
                            compensated_at, total_duration_ms, failure_reason,
                            timeout_ms, constitutional_hash
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, $19, $20, $21
                        )
                        """,
                        uuid.UUID(saga.saga_id),
                        saga.saga_name,
                        saga.tenant_id,
                        uuid.UUID(saga.correlation_id),
                        saga.state.value,
                        saga.compensation_strategy.value,
                        saga.current_step_index,
                        saga.version,
                        json.dumps([s.to_dict() for s in saga.steps]),
                        json.dumps(saga.context),
                        json.dumps(saga.metadata),
                        json.dumps([e.to_dict() for e in saga.compensation_log]),
                        saga.created_at,
                        saga.started_at,
                        saga.completed_at,
                        saga.failed_at,
                        saga.compensated_at,
                        saga.total_duration_ms,
                        saga.failure_reason,
                        saga.timeout_ms,
                        saga.constitutional_hash,
                    )

                logger.debug(
                    f"[{CONSTITUTIONAL_HASH}] Saved saga {saga.saga_id} "
                    f"(state={saga.state.value}, version={saga.version})"
                )
                return True

        except VersionConflictError:
            raise
        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to save saga {saga.saga_id}: {e}")
            raise RepositoryError(f"Failed to save saga: {e}", saga.saga_id) from e

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
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM saga_states WHERE saga_id = $1",
                    uuid.UUID(saga_id),
                )

                if not row:
                    return None

                return self._row_to_saga(row)

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get saga {saga_id}: {e}")
            raise RepositoryError(f"Failed to get saga: {e}", saga_id) from e

    async def delete(self, saga_id: str) -> bool:
        """
        Delete a saga by its ID.

        Also deletes associated checkpoints and locks via CASCADE.

        Args:
            saga_id: Unique identifier of the saga to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM saga_states WHERE saga_id = $1",
                    uuid.UUID(saga_id),
                )
                deleted = result == "DELETE 1"

                if deleted:
                    # Also clean up locks (not cascaded by FK)
                    await conn.execute(
                        "DELETE FROM saga_locks WHERE saga_id = $1",
                        uuid.UUID(saga_id),
                    )
                    logger.info(f"[{CONSTITUTIONAL_HASH}] Deleted saga {saga_id}")

                return deleted  # type: ignore[no-any-return]

        except asyncpg.PostgresError as e:
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
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM saga_states WHERE saga_id = $1)",
                    uuid.UUID(saga_id),
                )
                return bool(result)

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to check saga existence: {e}")
            raise RepositoryError(f"Failed to check saga existence: {e}", saga_id) from e

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _row_to_saga(self, row: asyncpg.Record) -> PersistedSagaState:
        """Convert a database row to PersistedSagaState."""
        # Parse JSONB fields
        steps_data = row["steps"] if row["steps"] else []
        if isinstance(steps_data, str):
            steps_data = json.loads(steps_data)
        steps = [PersistedStepSnapshot.from_dict(s) for s in steps_data if isinstance(s, dict)]

        context = row["context"] if row["context"] else {}
        if isinstance(context, str):
            context = json.loads(context)

        metadata = row["metadata"] if row["metadata"] else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        compensation_log_data = row["compensation_log"] if row["compensation_log"] else []
        if isinstance(compensation_log_data, str):
            compensation_log_data = json.loads(compensation_log_data)
        compensation_log = [
            CompensationEntry.from_dict(e) for e in compensation_log_data if isinstance(e, dict)
        ]

        return PersistedSagaState(
            saga_id=str(row["saga_id"]),
            saga_name=row["saga_name"],
            tenant_id=row["tenant_id"],
            correlation_id=str(row["correlation_id"]),
            state=SagaState(row["state"]),
            compensation_strategy=CompensationStrategy(row["compensation_strategy"]),
            steps=steps,
            current_step_index=row["current_step_index"],
            context=context,
            metadata=metadata,
            compensation_log=compensation_log,
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            failed_at=row["failed_at"],
            compensated_at=row["compensated_at"],
            total_duration_ms=row["total_duration_ms"],
            failure_reason=row["failure_reason"],
            timeout_ms=row["timeout_ms"],
            version=row["version"],
            constitutional_hash=row["constitutional_hash"],
        )

    def _row_to_checkpoint(self, row: asyncpg.Record) -> SagaCheckpoint:
        """Convert a database row to SagaCheckpoint."""
        state_snapshot = row["state_snapshot"] if row["state_snapshot"] else {}
        if isinstance(state_snapshot, str):
            state_snapshot = json.loads(state_snapshot)

        completed_step_ids = row["completed_step_ids"] if row["completed_step_ids"] else []
        if isinstance(completed_step_ids, str):
            completed_step_ids = json.loads(completed_step_ids)

        pending_step_ids = row["pending_step_ids"] if row["pending_step_ids"] else []
        if isinstance(pending_step_ids, str):
            pending_step_ids = json.loads(pending_step_ids)

        metadata = row["metadata"] if row["metadata"] else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return SagaCheckpoint(
            checkpoint_id=str(row["checkpoint_id"]),
            saga_id=str(row["saga_id"]),
            checkpoint_name=row["checkpoint_name"],
            state_snapshot=state_snapshot,
            completed_step_ids=completed_step_ids,
            pending_step_ids=pending_step_ids,
            created_at=row["created_at"],
            is_constitutional=row["is_constitutional"],
            metadata=metadata,
            constitutional_hash=row["constitutional_hash"],
        )


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_POOL_MAX_SIZE",
    "DEFAULT_POOL_MIN_SIZE",
    "SCHEMA_SQL",
    "PostgresSagaStateRepository",
]
