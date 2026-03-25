"""
PostgreSQL Saga Persistence Module
Constitutional Hash: 608508a9bd224290

Production-ready PostgreSQL implementation of saga state persistence
with connection pooling, optimistic locking, and distributed locks.

Re-exports all public APIs for backward compatibility.
"""

from .locking import PostgresLockManager
from .queries import PostgresQueryOperations
from .repository import PostgresSagaStateRepository
from .schema import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_POOL_MAX_SIZE,
    DEFAULT_POOL_MIN_SIZE,
    DEFAULT_TTL_DAYS,
    SCHEMA_SQL,
    VALID_STATE_TRANSITIONS,
)
from .state import PostgresStateManager

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_POOL_MAX_SIZE",
    "DEFAULT_POOL_MIN_SIZE",
    "DEFAULT_TTL_DAYS",
    # Schema and constants
    "SCHEMA_SQL",
    "VALID_STATE_TRANSITIONS",
    "PostgresLockManager",
    # Mixin classes (for extension/testing)
    "PostgresQueryOperations",
    # Main repository class
    "PostgresSagaStateRepository",
    "PostgresStateManager",
]
