"""
Redis State Management for Saga Persistence
Constitutional Hash: cdd01ef066bc6cf2

Provides state transition operations, checkpoint management,
and compensation log operations for saga persistence.
"""

import json
from datetime import UTC, datetime

import redis.asyncio as redis
from packages.enhanced_agent_bus.saga_persistence.models import (
    CompensationEntry,
    PersistedSagaState,
    PersistedStepSnapshot,
    SagaCheckpoint,
    SagaState,
    StepState,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..repository import InvalidStateTransitionError, RepositoryError
from .keys import RedisKeyMixin

logger = get_logger(__name__)
# Valid state transitions
VALID_STATE_TRANSITIONS: dict[SagaState, set[SagaState]] = {
    SagaState.INITIALIZED: {SagaState.RUNNING, SagaState.FAILED},
    SagaState.RUNNING: {SagaState.COMPLETED, SagaState.COMPENSATING, SagaState.FAILED},
    SagaState.COMPENSATING: {SagaState.COMPENSATED, SagaState.FAILED},
    SagaState.COMPLETED: set(),  # Terminal state
    SagaState.COMPENSATED: set(),  # Terminal state
    SagaState.FAILED: set(),  # Terminal state
}


class RedisStateManager(RedisKeyMixin):
    """
    Mixin providing state management operations for Redis saga repository.

    Implements state transitions, checkpoint persistence, and compensation
    log management using Redis atomic operations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    # Type hints for mixin - these are provided by the main repository class
    _redis: redis.Redis

    def _get_ttl_seconds(self) -> int:
        """Get TTL in seconds (implemented in main repository)."""
        raise NotImplementedError("Must be implemented by repository class")

    async def get(self, saga_id: str) -> PersistedSagaState | None:
        """Get saga by ID (implemented in main repository)."""
        raise NotImplementedError("Must be implemented by repository class")

    async def exists(self, saga_id: str) -> bool:
        """Check if saga exists (implemented in main repository)."""
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
        state_key = self._state_key(saga_id)

        try:
            # Get current saga
            data = await self._redis.hgetall(state_key)
            if not data:
                return False

            saga = PersistedSagaState.from_redis_hash(data)
            current_state = saga.state

            # Validate state transition
            valid_transitions = VALID_STATE_TRANSITIONS.get(current_state, set())
            if new_state not in valid_transitions:
                raise InvalidStateTransitionError(saga_id, current_state, new_state)

            # Prepare updates
            now = datetime.now(UTC)
            updates: dict[str, str] = {
                "state": new_state.value,
                "version": str(saga.version + 1),
            }

            # Set appropriate timestamp
            if new_state == SagaState.RUNNING and not saga.started_at:
                updates["started_at"] = now.isoformat()
            elif new_state == SagaState.COMPLETED:
                updates["completed_at"] = now.isoformat()
                if saga.started_at:
                    updates["total_duration_ms"] = str(
                        (now - saga.started_at).total_seconds() * 1000
                    )
            elif new_state == SagaState.COMPENSATED:
                updates["compensated_at"] = now.isoformat()
            elif new_state == SagaState.FAILED:
                updates["failed_at"] = now.isoformat()
                if failure_reason:
                    updates["failure_reason"] = failure_reason

            # Use pipeline for atomic update
            pipe = self._redis.pipeline()

            # Update saga hash
            pipe.hset(state_key, mapping=updates)

            # Update state indexes
            pipe.srem(self._state_index_key(current_state), saga_id)
            pipe.sadd(self._state_index_key(new_state), saga_id)

            await pipe.execute()

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Saga {saga_id} transitioned "
                f"{current_state.value} -> {new_state.value}"
            )
            return True

        except InvalidStateTransitionError:
            raise
        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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
        state_key = self._state_key(saga_id)

        try:
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

            # Update steps in Redis
            steps_json = json.dumps([s.to_dict() for s in updated_steps])
            await self._redis.hset(
                state_key,
                mapping={
                    "steps": steps_json,
                    "version": str(saga.version + 1),
                },
            )

            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Step {step_id} in saga {saga_id} "
                f"updated to {new_state.value}"
            )
            return True

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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
        state_key = self._state_key(saga_id)

        try:
            exists = await self._redis.exists(state_key)
            if not exists:
                return False

            await self._redis.hset(
                state_key,
                mapping={"current_step_index": str(step_index)},
            )
            return True

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to update current step: {e}")
            raise RepositoryError(f"Failed to update current step: {e}", saga_id) from e

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    async def save_checkpoint(self, checkpoint: SagaCheckpoint) -> bool:
        """
        Save a saga checkpoint for recovery.

        Args:
            checkpoint: The checkpoint to persist.

        Returns:
            True if save was successful.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            checkpoint_key = self._checkpoint_key(checkpoint.saga_id, checkpoint.checkpoint_id)
            checkpoint_list_key = self._checkpoint_list_key(checkpoint.saga_id)
            ttl_seconds = self._get_ttl_seconds()

            # Serialize checkpoint
            checkpoint_data = json.dumps(checkpoint.to_dict())

            # Use pipeline for atomicity
            pipe = self._redis.pipeline()

            # Save checkpoint as string
            pipe.setex(checkpoint_key, ttl_seconds, checkpoint_data)

            # Add to sorted set (score = timestamp for ordering)
            score = checkpoint.created_at.timestamp()
            pipe.zadd(checkpoint_list_key, {checkpoint.checkpoint_id: score})
            pipe.expire(checkpoint_list_key, ttl_seconds)

            await pipe.execute()

            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Saved checkpoint {checkpoint.checkpoint_id} "
                f"for saga {checkpoint.saga_id}"
            )
            return True

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to save checkpoint: {e}")
            raise RepositoryError(f"Failed to save checkpoint: {e}", checkpoint.saga_id) from e

    async def get_checkpoints(
        self,
        saga_id: str,
        limit: int = 100,
    ) -> list[SagaCheckpoint]:
        """
        Get all checkpoints for a saga.

        Args:
            saga_id: Unique identifier of the saga.
            limit: Maximum number of checkpoints to return.

        Returns:
            List of checkpoints, ordered by created_at descending.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            checkpoint_list_key = self._checkpoint_list_key(saga_id)

            # Get checkpoint IDs from sorted set (newest first)
            checkpoint_ids = await self._redis.zrevrange(checkpoint_list_key, 0, limit - 1)

            if not checkpoint_ids:
                return []

            # Fetch checkpoints
            checkpoints = []
            for cp_id in checkpoint_ids:
                cp_id_str = cp_id if isinstance(cp_id, str) else cp_id.decode("utf-8")
                checkpoint_key = self._checkpoint_key(saga_id, cp_id_str)
                data = await self._redis.get(checkpoint_key)

                if data:
                    data_str = data if isinstance(data, str) else data.decode("utf-8")
                    checkpoint_dict = json.loads(data_str)
                    checkpoints.append(SagaCheckpoint.from_dict(checkpoint_dict))

            return checkpoints

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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

    async def delete_checkpoints(self, saga_id: str) -> int:
        """
        Delete all checkpoints for a saga.

        Args:
            saga_id: Unique identifier of the saga.

        Returns:
            Number of checkpoints deleted.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            checkpoint_list_key = self._checkpoint_list_key(saga_id)

            # Get all checkpoint IDs
            checkpoint_ids = await self._redis.zrange(checkpoint_list_key, 0, -1)

            if not checkpoint_ids:
                return 0

            # Delete all checkpoints
            pipe = self._redis.pipeline()
            for cp_id in checkpoint_ids:
                cp_id_str = cp_id if isinstance(cp_id, str) else cp_id.decode("utf-8")
                pipe.delete(self._checkpoint_key(saga_id, cp_id_str))

            pipe.delete(checkpoint_list_key)

            await pipe.execute()

            deleted_count = len(checkpoint_ids)
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Deleted {deleted_count} checkpoints for saga {saga_id}"
            )
            return deleted_count

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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

        Uses Redis LIST with LPUSH for LIFO ordering.

        Args:
            saga_id: Unique identifier of the saga.
            entry: The compensation entry to append.

        Returns:
            True if append was successful, False if saga not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            # Verify saga exists
            if not await self.exists(saga_id):
                return False

            compensation_key = self._compensation_key(saga_id)
            entry_json = json.dumps(entry.to_dict())
            ttl_seconds = self._get_ttl_seconds()

            # Use LPUSH for LIFO ordering (most recent first)
            pipe = self._redis.pipeline()
            pipe.lpush(compensation_key, entry_json)
            pipe.expire(compensation_key, ttl_seconds)
            await pipe.execute()

            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Appended compensation entry "
                f"{entry.compensation_id} for saga {saga_id}"
            )
            return True

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
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
            List of compensation entries (most recent first).

        Raises:
            RepositoryError: On storage backend failures.
        """
        try:
            compensation_key = self._compensation_key(saga_id)
            entries_json = await self._redis.lrange(compensation_key, 0, -1)

            if not entries_json:
                return []

            entries = []
            for entry_json in entries_json:
                entry_str = (
                    entry_json if isinstance(entry_json, str) else entry_json.decode("utf-8")
                )
                entry_dict = json.loads(entry_str)
                entries.append(CompensationEntry.from_dict(entry_dict))

            return entries

        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get compensation log: {e}")
            raise RepositoryError(f"Failed to get compensation log: {e}", saga_id) from e


__all__ = ["VALID_STATE_TRANSITIONS", "RedisStateManager"]
