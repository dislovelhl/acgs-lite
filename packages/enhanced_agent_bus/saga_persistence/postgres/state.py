"""
PostgreSQL Saga Repository State Management
Constitutional Hash: 608508a9bd224290

Contains state transition, checkpoint, and compensation log operations
for the PostgreSQL saga state repository.
"""

import json
import uuid
from datetime import UTC, datetime

import asyncpg

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.saga_persistence.models import (
    CompensationEntry,
    PersistedSagaState,
    PersistedStepSnapshot,
    SagaCheckpoint,
    SagaState,
    StepState,
)

from ..repository import InvalidStateTransitionError, RepositoryError
from .schema import VALID_STATE_TRANSITIONS

logger = get_logger(__name__)


class PostgresStateManager:
    """
    Mixin class providing state management operations for PostgresSagaStateRepository.

    Handles state transitions, checkpoints, and compensation log operations.

    Constitutional Hash: 608508a9bd224290
    """

    # Type hints for mixin - these are provided by the main repository class
    _pool: asyncpg.Pool | None

    def _ensure_initialized(self) -> asyncpg.Pool:
        """Ensure the repository is initialized and return the pool."""
        raise NotImplementedError("Must be implemented by repository class")

    def _row_to_checkpoint(self, row: asyncpg.Record) -> SagaCheckpoint:
        """Convert a database row to SagaCheckpoint."""
        raise NotImplementedError("Must be implemented by repository class")

    async def get(self, saga_id: str) -> PersistedSagaState | None:
        """Get a saga by ID."""
        raise NotImplementedError("Must be implemented by repository class")

    # =========================================================================
    # State Transition Operations
    # =========================================================================

    async def update_state(
        self,
        saga_id: str,
        new_state: SagaState,
        failure_reason: str | None = None,
    ) -> bool:
        """
        Atomically update a saga's state.

        Validates state transition and updates appropriate timestamp.

        Args:
            saga_id: Unique identifier of the saga.
            new_state: The new state to transition to.
            failure_reason: Optional reason if transitioning to FAILED.

        Returns:
            True if update was successful, False if saga not found.

        Raises:
            RepositoryError: On storage backend failures.
            InvalidStateTransitionError: If transition is not allowed.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                # Get current state
                row = await conn.fetchrow(
                    "SELECT state, version, started_at FROM saga_states WHERE saga_id = $1",
                    uuid.UUID(saga_id),
                )

                if not row:
                    return False

                current_state = SagaState(row["state"])
                version = row["version"]
                started_at = row["started_at"]

                # Validate state transition
                valid_transitions = VALID_STATE_TRANSITIONS.get(current_state, set())
                if new_state not in valid_transitions:
                    raise InvalidStateTransitionError(saga_id, current_state, new_state)

                # Prepare timestamp updates
                now = datetime.now(UTC)
                timestamp_field = None
                duration_update = ""

                if new_state == SagaState.RUNNING and started_at is None:
                    timestamp_field = "started_at"
                elif new_state == SagaState.COMPLETED:
                    timestamp_field = "completed_at"
                    if started_at:
                        duration_update = (
                            ", total_duration_ms = EXTRACT(EPOCH FROM ($4 - started_at)) * 1000"
                        )
                elif new_state == SagaState.COMPENSATED:
                    timestamp_field = "compensated_at"
                elif new_state == SagaState.FAILED:
                    timestamp_field = "failed_at"

                # Build and execute update query
                if timestamp_field:
                    if failure_reason and new_state == SagaState.FAILED:
                        await conn.execute(
                            f"UPDATE saga_states SET state = $2, version = version + 1, {timestamp_field} = $4, failure_reason = $5 {duration_update} WHERE saga_id = $1 AND version = $3",  # nosec B608
                            uuid.UUID(saga_id),
                            new_state.value,
                            version,
                            now,
                            failure_reason,
                        )
                    else:
                        await conn.execute(
                            f"UPDATE saga_states SET state = $2, version = version + 1, {timestamp_field} = $4 {duration_update} WHERE saga_id = $1 AND version = $3",  # nosec B608
                            uuid.UUID(saga_id),
                            new_state.value,
                            version,
                            now,
                        )
                else:
                    await conn.execute(
                        """
                        UPDATE saga_states
                        SET state = $2, version = version + 1
                        WHERE saga_id = $1 AND version = $3
                        """,
                        uuid.UUID(saga_id),
                        new_state.value,
                        version,
                    )

                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] Saga {saga_id} transitioned "
                    f"{current_state.value} -> {new_state.value}"
                )
                return True

        except InvalidStateTransitionError:
            raise
        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to update saga state: {e}")
            raise RepositoryError(f"Failed to update saga state: {e}", saga_id) from e

    async def update_step_state(
        self,
        saga_id: str,
        step_id: str,
        new_state: StepState,
        output_data: JSONDict | None = None,
        error_message: str | None = None,
    ) -> bool:
        """
        Update a specific step's state within a saga.

        Args:
            saga_id: Unique identifier of the saga.
            step_id: Unique identifier of the step.
            new_state: The new state for the step.
            output_data: Optional output data from step execution.
            error_message: Optional error message if step failed.

        Returns:
            True if update was successful, False if saga or step not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                # Get current saga
                saga = await self.get(saga_id)
                if not saga:
                    return False

                # Find and update step
                step_found = False
                now = datetime.now(UTC)
                updated_steps = []

                for step in saga.steps:
                    if step.step_id == step_id:
                        step_found = True
                        # Create updated step (immutable pattern)
                        updated_step = PersistedStepSnapshot(
                            step_id=step.step_id,
                            step_name=step.step_name,
                            step_index=step.step_index,
                            state=new_state,
                            input_data=step.input_data,
                            output_data=output_data if output_data else step.output_data,
                            error_message=error_message if error_message else step.error_message,
                            started_at=step.started_at
                            or (now if new_state == StepState.RUNNING else None),
                            completed_at=now if new_state.is_terminal() else step.completed_at,
                            duration_ms=(
                                (now - step.started_at).total_seconds() * 1000
                                if step.started_at and new_state.is_terminal()
                                else step.duration_ms
                            ),
                            retry_count=step.retry_count,
                            max_retries=step.max_retries,
                            timeout_ms=step.timeout_ms,
                            dependencies=step.dependencies,
                            compensation=step.compensation,
                            metadata=step.metadata,
                            constitutional_hash=step.constitutional_hash,
                        )
                        updated_steps.append(updated_step)
                    else:
                        updated_steps.append(step)

                if not step_found:
                    return False

                # Update steps in database
                await conn.execute(
                    """
                    UPDATE saga_states
                    SET steps = $2, version = version + 1
                    WHERE saga_id = $1
                    """,
                    uuid.UUID(saga_id),
                    json.dumps([s.to_dict() for s in updated_steps]),
                )

                logger.debug(
                    f"[{CONSTITUTIONAL_HASH}] Step {step_id} in saga {saga_id} "
                    f"updated to {new_state.value}"
                )
                return True

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to update step state: {e}")
            raise RepositoryError(f"Failed to update step state: {e}", saga_id) from e

    async def update_current_step(
        self,
        saga_id: str,
        step_index: int,
    ) -> bool:
        """
        Update the current step index of a saga.

        Args:
            saga_id: Unique identifier of the saga.
            step_index: The new current step index.

        Returns:
            True if update was successful, False if saga not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE saga_states
                    SET current_step_index = $2
                    WHERE saga_id = $1
                    """,
                    uuid.UUID(saga_id),
                    step_index,
                )
                return bool(result == "UPDATE 1")

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to update current step: {e}")
            raise RepositoryError(f"Failed to update current step: {e}", saga_id) from e

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    async def save_checkpoint(
        self,
        checkpoint: SagaCheckpoint,
    ) -> bool:
        """
        Save a saga checkpoint for recovery.

        Args:
            checkpoint: The checkpoint to persist.

        Returns:
            True if save was successful.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO saga_checkpoints (
                        checkpoint_id, saga_id, checkpoint_name,
                        state_snapshot, completed_step_ids, pending_step_ids,
                        is_constitutional, metadata, created_at, constitutional_hash
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    uuid.UUID(checkpoint.checkpoint_id),
                    uuid.UUID(checkpoint.saga_id),
                    checkpoint.checkpoint_name,
                    json.dumps(checkpoint.state_snapshot),
                    json.dumps(checkpoint.completed_step_ids),
                    json.dumps(checkpoint.pending_step_ids),
                    checkpoint.is_constitutional,
                    json.dumps(checkpoint.metadata),
                    checkpoint.created_at,
                    checkpoint.constitutional_hash,
                )

                logger.debug(
                    f"[{CONSTITUTIONAL_HASH}] Saved checkpoint {checkpoint.checkpoint_id} "
                    f"for saga {checkpoint.saga_id}"
                )
                return True

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to save checkpoint: {e}")
            raise RepositoryError(f"Failed to save checkpoint: {e}", checkpoint.saga_id) from e

    async def get_checkpoints(
        self,
        saga_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SagaCheckpoint]:
        """
        Get all checkpoints for a saga.

        Args:
            saga_id: Unique identifier of the saga.
            limit: Maximum number of checkpoints to return.
            offset: Number of checkpoints to skip.

        Returns:
            List of checkpoints, ordered by created_at descending.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM saga_checkpoints
                    WHERE saga_id = $1
                    ORDER BY created_at DESC
                    LIMIT $3 OFFSET $4
                    """,
                    uuid.UUID(saga_id),
                    limit,
                    offset,
                )

                return [self._row_to_checkpoint(row) for row in rows]

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get checkpoints: {e}")
            raise RepositoryError(f"Failed to get checkpoints: {e}", saga_id) from e

    async def get_latest_checkpoint(
        self,
        saga_id: str,
    ) -> SagaCheckpoint | None:
        """
        Get the most recent checkpoint for a saga.

        Args:
            saga_id: Unique identifier of the saga.

        Returns:
            The latest checkpoint if any exist, None otherwise.

        Raises:
            RepositoryError: On storage backend failures.
        """
        checkpoints = await self.get_checkpoints(saga_id, limit=1)
        return checkpoints[0] if checkpoints else None

    async def delete_checkpoints(
        self,
        saga_id: str,
    ) -> int:
        """
        Delete all checkpoints for a saga.

        Args:
            saga_id: Unique identifier of the saga.

        Returns:
            Number of checkpoints deleted.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM saga_checkpoints WHERE saga_id = $1",
                    uuid.UUID(saga_id),
                )
                # Parse "DELETE N" to get count
                deleted_count = int(result.split(" ")[1]) if result else 0

                if deleted_count > 0:
                    logger.info(
                        f"[{CONSTITUTIONAL_HASH}] Deleted {deleted_count} "
                        f"checkpoints for saga {saga_id}"
                    )
                return deleted_count

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to delete checkpoints: {e}")
            raise RepositoryError(f"Failed to delete checkpoints: {e}", saga_id) from e

    # =========================================================================
    # Compensation Log Operations
    # =========================================================================

    async def append_compensation_entry(
        self,
        saga_id: str,
        entry: CompensationEntry,
    ) -> bool:
        """
        Append a compensation entry to the saga's compensation log.

        Uses JSONB array append for atomic operation.

        Args:
            saga_id: Unique identifier of the saga.
            entry: The compensation entry to append.

        Returns:
            True if append was successful, False if saga not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE saga_states
                    SET compensation_log = compensation_log || $2::jsonb
                    WHERE saga_id = $1
                    """,
                    uuid.UUID(saga_id),
                    json.dumps([entry.to_dict()]),
                )
                success: bool = result == "UPDATE 1"

                if success:
                    logger.debug(
                        f"[{CONSTITUTIONAL_HASH}] Appended compensation entry "
                        f"{entry.compensation_id} for saga {saga_id}"
                    )
                return success

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to append compensation entry: {e}")
            raise RepositoryError(f"Failed to append compensation entry: {e}", saga_id) from e

    async def get_compensation_log(
        self,
        saga_id: str,
    ) -> list[CompensationEntry]:
        """
        Get the full compensation log for a saga.

        Args:
            saga_id: Unique identifier of the saga.

        Returns:
            List of compensation entries in chronological order.

        Raises:
            RepositoryError: On storage backend failures.
        """
        pool = self._ensure_initialized()

        try:
            async with pool.acquire() as conn:
                compensation_log = await conn.fetchval(
                    "SELECT compensation_log FROM saga_states WHERE saga_id = $1",
                    uuid.UUID(saga_id),
                )

                if not compensation_log:
                    return []

                log_data = (
                    json.loads(compensation_log)
                    if isinstance(compensation_log, str)
                    else compensation_log
                )
                return [
                    CompensationEntry.from_dict(entry)
                    for entry in log_data
                    if isinstance(entry, dict)
                ]

        except asyncpg.PostgresError as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get compensation log: {e}")
            raise RepositoryError(f"Failed to get compensation log: {e}", saga_id) from e


__all__ = ["PostgresStateManager"]
