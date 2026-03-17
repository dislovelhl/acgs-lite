"""
Saga Persistence Layer
Constitutional Hash: cdd01ef066bc6cf2

Provides persistent storage for saga state management, enabling recovery
from system failures and audit trails for governance decisions.

Key Components:
- PersistedSagaState: Complete saga state for persistence
- PersistedStepSnapshot: Immutable step state snapshot
- SagaStateRepository: Abstract interface for storage backends
- RedisSagaStateRepository: Redis-backed implementation
- PostgresSagaStateRepository: PostgreSQL-backed implementation
- CompensationEntry: Compensation action record
- create_saga_repository: Factory function for repository creation

Usage:
    from saga_persistence import (
        create_saga_repository,
        SagaBackend,
        PersistedSagaState,
        SagaState,
        StepState,
    )

    # Create repository using factory (recommended)
    repo = await create_saga_repository(SagaBackend.REDIS, redis_url="redis://localhost")

    # Auto-detect backend from environment
    repo = await create_saga_repository()  # Uses SAGA_BACKEND env var

    # Create a saga state
    saga = PersistedSagaState(
        saga_name="governance_decision",
        tenant_id="tenant-123",
    )

    # Save saga
    await repo.save(saga)

Features:
- Factory-based repository creation with fallback support
- Redis hash serialization for efficient storage
- PostgreSQL with JSONB for complex fields
- Optimistic locking via version field
- Constitutional hash validation
- Multi-tenant isolation
- Checkpoint-based recovery
- Distributed locking for concurrent access
"""

# -- Namespace Boundary ---------------------------------------------------
# This package handles DISTRIBUTED SAGA STATE management:
#   PersistedSagaState, SagaCheckpoint, CompensationEntry
#   Multi-backend: Redis + PostgreSQL, factory-based creation
#   Self-contained: no external consumers outside this package
#
# DO NOT CONFUSE with persistence/ which handles WORKFLOW EXECUTION lifecycle
# (WorkflowInstance, DurableWorkflowExecutor, ReplayEngine, PostgreSQL-only).
# The two packages have ZERO cross-domain imports.
# -------------------------------------------------------------------------

from src.core.shared.constants import CONSTITUTIONAL_HASH

from .models import (
    CompensationEntry,
    CompensationFunc,
    CompensationStrategy,
    PersistedSagaState,
    PersistedStepSnapshot,
    SagaActionFunc,
    SagaCheckpoint,
    SagaState,
    StepState,
)

# PostgreSQL implementation (optional - requires asyncpg)
try:
    from .postgres_repository import (
        DEFAULT_POOL_MAX_SIZE,
        DEFAULT_POOL_MIN_SIZE,
        SCHEMA_SQL,
        VALID_STATE_TRANSITIONS,
        PostgresSagaStateRepository,
    )

    POSTGRES_AVAILABLE = True
except ImportError:
    # asyncpg not installed - PostgreSQL backend unavailable
    PostgresSagaStateRepository = None  # type: ignore[assignment]
    SCHEMA_SQL = None
    VALID_STATE_TRANSITIONS = None
    DEFAULT_POOL_MIN_SIZE = 5
    DEFAULT_POOL_MAX_SIZE = 20
    POSTGRES_AVAILABLE = False
# Redis implementation (optional - requires redis)
try:
    from .redis_repository import (
        DEFAULT_LOCK_TIMEOUT_SECONDS,
        DEFAULT_TTL_DAYS,
        SAGA_CHECKPOINT_PREFIX,
        SAGA_COMPENSATION_PREFIX,
        SAGA_INDEX_STATE_PREFIX,
        SAGA_INDEX_TENANT_PREFIX,
        SAGA_LOCK_PREFIX,
        SAGA_STATE_PREFIX,
        RedisSagaStateRepository,
    )

    REDIS_AVAILABLE = True
except ImportError:
    # redis not installed - Redis backend unavailable
    RedisSagaStateRepository = None  # type: ignore[assignment]
    SAGA_STATE_PREFIX = "saga:state:"
    SAGA_CHECKPOINT_PREFIX = "saga:checkpoint:"
    SAGA_COMPENSATION_PREFIX = "saga:compensation:"
    SAGA_LOCK_PREFIX = "saga:lock:"
    SAGA_INDEX_STATE_PREFIX = "saga:idx:state:"
    SAGA_INDEX_TENANT_PREFIX = "saga:idx:tenant:"
    DEFAULT_TTL_DAYS = 30
    DEFAULT_LOCK_TIMEOUT_SECONDS = 30
    REDIS_AVAILABLE = False
# Factory (always available)
from .factory import (
    BackendUnavailableError,
    SagaBackend,
    create_saga_repository,
)
from .repository import (
    InvalidStateTransitionError,
    LockError,
    RepositoryError,
    SagaNotFoundError,
    SagaStateRepository,
    VersionConflictError,
)

__version__ = "1.0.0"
__author__ = "ACGS-2 Team"

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_POOL_MAX_SIZE",
    "DEFAULT_POOL_MIN_SIZE",
    # Configuration
    "DEFAULT_TTL_DAYS",
    # Availability Flags
    "POSTGRES_AVAILABLE",
    "REDIS_AVAILABLE",
    "SAGA_CHECKPOINT_PREFIX",
    "SAGA_COMPENSATION_PREFIX",
    "SAGA_INDEX_STATE_PREFIX",
    "SAGA_INDEX_TENANT_PREFIX",
    "SAGA_LOCK_PREFIX",
    # Redis Key Prefixes
    "SAGA_STATE_PREFIX",
    "SCHEMA_SQL",
    "VALID_STATE_TRANSITIONS",
    "BackendUnavailableError",
    "CompensationEntry",
    "CompensationFunc",
    "CompensationStrategy",
    "InvalidStateTransitionError",
    "LockError",
    # Core Models
    "PersistedSagaState",
    "PersistedStepSnapshot",
    # PostgreSQL Implementation
    "PostgresSagaStateRepository",
    # Redis Implementation
    "RedisSagaStateRepository",
    # Exceptions
    "RepositoryError",
    # Type Aliases
    "SagaActionFunc",
    "SagaBackend",
    "SagaCheckpoint",
    "SagaNotFoundError",
    # Enums
    "SagaState",
    # Repository Interface
    "SagaStateRepository",
    "StepState",
    "VersionConflictError",
    # Factory (recommended entry point)
    "create_saga_repository",
]
