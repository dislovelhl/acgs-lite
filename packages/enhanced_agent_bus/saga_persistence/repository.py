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

from abc import ABC, abstractmethod
from datetime import datetime

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import ACGSBaseError

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .models import (
    CompensationEntry,
    PersistedSagaState,
    SagaCheckpoint,
    SagaState,
    StepState,
)


class SagaStateRepository(ABC):
    """
    Abstract repository for saga state persistence.

    Implementations must provide atomic operations for saga state management,
    supporting recovery scenarios and multi-tenant isolation.

    Constitutional Hash: 608508a9bd224290
    """

    @property
    def constitutional_hash(self) -> str:
        """Return the constitutional hash for validation."""
        return CONSTITUTIONAL_HASH  # type: ignore[no-any-return]

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
    async def save_checkpoint(self, checkpoint: SagaCheckpoint) -> bool:
        """
        Save a saga checkpoint for recovery.

        Checkpoints capture the saga state at critical points and enable
        recovery after system failures.

        Args:
            checkpoint: The checkpoint to persist.

        Returns:
            True if save was successful.

        Raises:
            RepositoryError: On storage backend failures.
        """
        ...

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
