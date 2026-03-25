"""
PostgreSQL Saga State Repository Implementation
Constitutional Hash: 608508a9bd224290

BACKWARD COMPATIBILITY SHIM

This file re-exports all public APIs from the refactored postgres/ module
to maintain backward compatibility with existing imports.

The implementation has been split into modular components:
- postgres/repository.py: Main class, CRUD, connection pool
- postgres/schema.py: SCHEMA_SQL, version constants
- postgres/queries.py: Query operations (list_by_tenant, search, etc.)
- postgres/state.py: State transitions, checkpoints, compensation
- postgres/locking.py: Distributed locking, acquire, release, extend

All original imports continue to work:
    from .postgres_repository import PostgresSagaStateRepository
    from .postgres_repository import SCHEMA_SQL
"""

from .postgres import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_POOL_MAX_SIZE,
    DEFAULT_POOL_MIN_SIZE,
    DEFAULT_TTL_DAYS,
    SCHEMA_SQL,
    VALID_STATE_TRANSITIONS,
    PostgresLockManager,
    PostgresQueryOperations,
    PostgresSagaStateRepository,
    PostgresStateManager,
)

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_POOL_MAX_SIZE",
    "DEFAULT_POOL_MIN_SIZE",
    "DEFAULT_TTL_DAYS",
    "SCHEMA_SQL",
    "VALID_STATE_TRANSITIONS",
    "PostgresLockManager",
    # Mixin classes exposed for extension
    "PostgresQueryOperations",
    "PostgresSagaStateRepository",
    "PostgresStateManager",
]
