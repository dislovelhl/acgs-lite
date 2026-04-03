"""
Saga State Repository Interface
Constitutional Hash: 608508a9bd224290

Abstract base class defining the interface for saga state persistence.
Implementations can use Redis, PostgreSQL, or other storage backends.

Features:
- Async-first design for non-blocking I/O
- Optimistic locking with version checks
- Tenant isolation for multi-tenant deployments
- Checkpoint management for recovery
"""

from abc import abstractmethod
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.core.shared.errors.exceptions import ACGSBaseError

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.persistence.repository import GovernanceRepository

from .models import (
    FLYWHEEL_RUN_SAGA_NAME,
    CompensationEntry,
    FlywheelRunRecord,
    FlywheelRunStage,
    PersistedSagaState,
    SagaCheckpoint,
    SagaState,
    StepState,
)


class SagaStateRepository(GovernanceRepository[str, SagaCheckpoint, bool]):
    """
    Abstract repository for saga state persistence.

    Implementations must provide atomic operations for saga state management,
    supporting recovery scenarios and multi-tenant isolation.

    Constitutional Hash: 608508a9bd224290
    """

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    @abstractmethod
    async def save(self, saga: PersistedSagaState) -> bool:
        """
        Save or update a saga state.

        Uses optimistic locking via version field. If the saga exists with
        a different version, the save will fail to prevent lost updates.

        Args:
            saga: The saga state to persist.

        Returns:
            True if save was successful, False if version conflict occurred.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    async def delete(self, saga_id: str) -> bool:
        """
        Delete a saga by its ID.

        Should only be called for terminal sagas (COMPLETED, COMPENSATED, FAILED).
        Non-terminal sagas should not be deleted.

        Args:
            saga_id: Unique identifier of the saga to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
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
        ...

    # =========================================================================
    # Query Operations
    # =========================================================================

    @abstractmethod
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
            state: Optional state filter (e.g., only RUNNING sagas).
            limit: Maximum number of results (default 100).
            offset: Number of results to skip (for pagination).

        Returns:
            List of matching sagas, ordered by created_at descending.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
    async def list_by_state(
        self,
        state: SagaState,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PersistedSagaState]:
        """
        List sagas in a specific state across all tenants.

        Useful for system-wide operations like recovery of COMPENSATING sagas.

        Args:
            state: The saga state to filter by.
            limit: Maximum number of results (default 100).
            offset: Number of results to skip (for pagination).

        Returns:
            List of matching sagas, ordered by created_at descending.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
    async def list_pending_compensations(
        self,
        limit: int = 100,
    ) -> list[PersistedSagaState]:
        """
        List sagas that need compensation.

        Returns sagas in COMPENSATING or RUNNING states that may need
        recovery attention.

        Args:
            limit: Maximum number of results (default 100).

        Returns:
            List of sagas requiring compensation attention.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
    async def list_timed_out(
        self,
        since: datetime,
        limit: int = 100,
    ) -> list[PersistedSagaState]:
        """
        List sagas that have timed out.

        Returns RUNNING sagas that were started before the given timestamp
        and have exceeded their timeout_ms.

        Args:
            since: Timestamp to check for timeout (sagas started before this).
            limit: Maximum number of results (default 100).

        Returns:
            List of timed out sagas.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
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
        ...

    # =========================================================================
    # State Transition Operations
    # =========================================================================

    @abstractmethod
    async def update_state(
        self,
        saga_id: str,
        new_state: SagaState,
        failure_reason: str | None = None,
    ) -> bool:
        """
        Atomically update a saga's state.

        Updates the state and optionally sets failure_reason. Also updates
        the appropriate timestamp field (failed_at, compensated_at, completed_at).

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
        ...

    @abstractmethod
    async def update_step_state(
        self,
        saga_id: str,
        step_id: str,
        new_state: "StepState",
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
        ...

    @abstractmethod
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
        ...

    # =========================================================================
    # Checkpoint Operations
    # =========================================================================

    @abstractmethod
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
        ...

    @abstractmethod
    async def delete_checkpoints(self, saga_id: str) -> int:
        """
        Delete all checkpoints for a saga.

        Typically called when deleting a completed saga.

        Args:
            saga_id: Unique identifier of the saga.

        Returns:
            Number of checkpoints deleted.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    # =========================================================================
    # Compensation Log Operations
    # =========================================================================

    @abstractmethod
    async def append_compensation_entry(
        self,
        saga_id: str,
        entry: "CompensationEntry",
    ) -> bool:
        """
        Append a compensation entry to the saga's compensation log.

        Args:
            saga_id: Unique identifier of the saga.
            entry: The compensation entry to append.

        Returns:
            True if append was successful, False if saga not found.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
    async def get_compensation_log(
        self,
        saga_id: str,
    ) -> list["CompensationEntry"]:
        """
        Get the full compensation log for a saga.

        Args:
            saga_id: Unique identifier of the saga.

        Returns:
            List of compensation entries in chronological order.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    # =========================================================================
    # Locking Operations (Optional - for distributed deployments)
    # =========================================================================

    @abstractmethod
    async def acquire_lock(
        self,
        saga_id: str,
        lock_holder: str,
        ttl_seconds: int = 30,
    ) -> bool:
        """
        Acquire a distributed lock on a saga.

        Used to prevent concurrent modifications in distributed deployments.

        Args:
            saga_id: Unique identifier of the saga to lock.
            lock_holder: Identifier of the lock holder (e.g., worker ID).
            ttl_seconds: Lock time-to-live in seconds (default 30).

        Returns:
            True if lock was acquired, False if already locked.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    async def extend_lock(
        self,
        saga_id: str,
        lock_holder: str,
        ttl_seconds: int = 30,
    ) -> bool:
        """
        Extend a distributed lock's TTL.

        Used to keep the lock alive during long-running operations.

        Args:
            saga_id: Unique identifier of the saga.
            lock_holder: Identifier of the lock holder.
            ttl_seconds: New TTL in seconds.

        Returns:
            True if lock was extended, False if not held by this holder.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    # =========================================================================
    # Maintenance Operations
    # =========================================================================

    @abstractmethod
    async def cleanup_old_sagas(
        self,
        older_than: datetime,
        terminal_only: bool = True,
    ) -> int:
        """
        Delete old sagas for storage management.

        Args:
            older_than: Delete sagas completed/failed before this timestamp.
            terminal_only: If True, only delete terminal sagas (default True).

        Returns:
            Number of sagas deleted.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
    async def get_statistics(self) -> JSONDict:
        """
        Get repository statistics.

        Returns metrics like total sagas, sagas by state, average duration, etc.

        Returns:
            Dictionary containing repository statistics.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    @abstractmethod
    async def health_check(self) -> JSONDict:
        """
        Perform a health check on the repository.

        Tests connectivity and basic operations on the storage backend.

        Returns:
            Dictionary with health status and details.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

    async def save_flywheel_run(self, run: FlywheelRunRecord) -> bool:
        """Persist a bounded flywheel run via the canonical saga store."""
        return await self.save(run.to_saga_state())

    async def get_flywheel_run(self, run_id: str) -> FlywheelRunRecord | None:
        """Load a flywheel run if the saga belongs to the flywheel namespace."""
        saga = await self.get(run_id)
        if saga is None or saga.saga_name != FLYWHEEL_RUN_SAGA_NAME:
            return None
        return FlywheelRunRecord.from_saga_state(saga)

    async def list_flywheel_runs_by_tenant(
        self,
        tenant_id: str,
        state: SagaState | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FlywheelRunRecord]:
        """List flywheel runs for a tenant while preserving the generic saga backends."""
        return await self._scan_flywheel_runs(
            lambda batch_limit, batch_offset: self.list_by_tenant(
                tenant_id, state=state, limit=batch_limit, offset=batch_offset
            ),
            limit=limit,
            offset=offset,
        )

    async def list_flywheel_runs_by_state(
        self,
        state: SagaState,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FlywheelRunRecord]:
        """List flywheel runs for a specific saga state across all tenants."""
        return await self._scan_flywheel_runs(
            lambda batch_limit, batch_offset: self.list_by_state(
                state, limit=batch_limit, offset=batch_offset
            ),
            limit=limit,
            offset=offset,
        )

    async def start_flywheel_run(self, run_id: str) -> bool:
        """Transition a flywheel run into RUNNING state."""
        return await self.update_state(run_id, SagaState.RUNNING)

    async def pause_flywheel_run(self, run_id: str, reason: str | None = None) -> bool:
        """Pause a flywheel run at a safe boundary without mutating immutable evidence."""
        run = await self.get_flywheel_run(run_id)
        if run is None:
            return False
        run.paused = True
        run.updated_at = datetime.now(UTC)
        if reason:
            run.metadata["pause_reason"] = reason
        run.version += 1
        return await self.save_flywheel_run(run)

    async def resume_flywheel_run(self, run_id: str) -> bool:
        """Resume a paused flywheel run from the latest checkpointed state."""
        run = await self.get_flywheel_run(run_id)
        if run is None:
            return False
        if run.state == SagaState.INITIALIZED:
            state_updated = await self.update_state(run_id, SagaState.RUNNING)
            if not state_updated:
                return False
            run = await self.get_flywheel_run(run_id)
            if run is None:
                return False
        run.paused = False
        run.metadata.pop("pause_reason", None)
        run.updated_at = datetime.now(UTC)
        run.version += 1
        return await self.save_flywheel_run(run)

    async def advance_flywheel_run_stage(
        self,
        run_id: str,
        stage: FlywheelRunStage,
        current_step_index: int | None = None,
        metadata: JSONDict | None = None,
    ) -> bool:
        """Advance a flywheel run to a new stage and checkpointable progress index."""
        run = await self.get_flywheel_run(run_id)
        if run is None:
            return False
        run.stage = stage
        if current_step_index is not None:
            run.current_step_index = current_step_index
            updated = await self.update_current_step(run_id, current_step_index)
            if not updated:
                return False
        if metadata:
            run.metadata.update(metadata)
        run.updated_at = datetime.now(UTC)
        run.version += 1
        return await self.save_flywheel_run(run)

    async def complete_flywheel_run(self, run_id: str) -> bool:
        """Mark a flywheel run as completed."""
        return await self.update_state(run_id, SagaState.COMPLETED)

    async def stop_flywheel_run(self, run_id: str, reason: str) -> bool:
        """Fail a flywheel run due to operator intervention or a hard stop."""
        return await self.update_state(run_id, SagaState.FAILED, failure_reason=reason)

    async def save_flywheel_checkpoint(
        self,
        run_id: str,
        checkpoint_name: str,
        *,
        is_constitutional: bool = False,
        metadata: JSONDict | None = None,
    ) -> bool:
        """Persist a checkpoint snapshot for a flywheel run."""
        saga = await self.get(run_id)
        if saga is None or saga.saga_name != FLYWHEEL_RUN_SAGA_NAME:
            return False
        checkpoint = SagaCheckpoint(
            saga_id=run_id,
            checkpoint_name=checkpoint_name,
            state_snapshot=saga.to_dict(),
            completed_step_ids=[step.step_id for step in saga.completed_steps],
            pending_step_ids=[step.step_id for step in saga.pending_steps],
            is_constitutional=is_constitutional,
            metadata=metadata or {},
            constitutional_hash=saga.constitutional_hash,
        )
        return await self.save_checkpoint(checkpoint)

    async def get_latest_flywheel_checkpoint(self, run_id: str) -> SagaCheckpoint | None:
        """Return the latest checkpoint for a flywheel run."""
        run = await self.get_flywheel_run(run_id)
        if run is None:
            return None
        return await self.get_latest_checkpoint(run_id)

    async def _scan_flywheel_runs(
        self,
        fetch_page: Callable[[int, int], Awaitable[list[PersistedSagaState]]],
        *,
        limit: int,
        offset: int,
    ) -> list[FlywheelRunRecord]:
        """Paginate generic saga queries until enough flywheel runs have been collected."""
        results: list[FlywheelRunRecord] = []
        seen = 0
        batch_limit = max(limit, 100)
        batch_offset = 0
        while len(results) < limit:
            batch = await fetch_page(batch_limit, batch_offset)
            if not batch:
                break
            for saga in batch:
                if saga.saga_name != FLYWHEEL_RUN_SAGA_NAME:
                    continue
                if seen < offset:
                    seen += 1
                    continue
                results.append(FlywheelRunRecord.from_saga_state(saga))
                if len(results) >= limit:
                    break
            batch_offset += batch_limit
        return results


class RepositoryError(ACGSBaseError):
    """Base exception for repository operations."""

    http_status_code = 500
    error_code = "REPOSITORY_ERROR"

    def __init__(self, message: str, saga_id: str | None = None):
        self.saga_id = saga_id
        super().__init__(message, details={"saga_id": saga_id})


class SagaNotFoundError(RepositoryError):
    """Raised when a saga is not found."""

    http_status_code = 404
    error_code = "SAGA_NOT_FOUND"


class VersionConflictError(RepositoryError):
    """Raised when optimistic locking fails due to version mismatch."""

    http_status_code = 409
    error_code = "VERSION_CONFLICT"

    def __init__(
        self,
        saga_id: str,
        expected_version: int,
        actual_version: int,
    ):
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Version conflict for saga {saga_id}: "
            f"expected {expected_version}, got {actual_version}",
            saga_id,
        )


class InvalidStateTransitionError(RepositoryError):
    """Raised when an invalid state transition is attempted."""

    http_status_code = 400
    error_code = "INVALID_STATE_TRANSITION"

    def __init__(
        self,
        saga_id: str,
        current_state: SagaState,
        target_state: SagaState,
    ):
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            f"Invalid state transition for saga {saga_id}: "
            f"{current_state.value} -> {target_state.value}",
            saga_id,
        )


class LockError(RepositoryError):
    """Raised when lock operations fail."""

    http_status_code = 423
    error_code = "LOCK_ERROR"


__all__ = [
    "InvalidStateTransitionError",
    "LockError",
    "RepositoryError",
    "SagaNotFoundError",
    "SagaStateRepository",
    "VersionConflictError",
]
