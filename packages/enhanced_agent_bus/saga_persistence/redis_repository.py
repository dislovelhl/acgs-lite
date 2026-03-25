"""
Redis Saga State Repository Implementation
Constitutional Hash: 608508a9bd224290

BACKWARD COMPATIBILITY SHIM

This file re-exports all public APIs from the refactored redis/ module
to maintain backward compatibility with existing imports.

The implementation has been split into modular components:
- redis/repository.py: Main class, CRUD, connection management
- redis/keys.py: Redis key prefixes and generation utilities
- redis/queries.py: Query operations (list_by_tenant, list_by_state, etc.)
- redis/state.py: State transitions, checkpoints, compensation logs
- redis/locking.py: Distributed locking and maintenance operations

All original imports continue to work:
    from .redis_repository import RedisSagaStateRepository
    from .redis_repository import SAGA_STATE_PREFIX
"""

from .redis import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_TTL_DAYS,
    SAGA_CHECKPOINT_PREFIX,
    SAGA_COMPENSATION_PREFIX,
    SAGA_INDEX_STATE_PREFIX,
    SAGA_INDEX_TENANT_PREFIX,
    SAGA_LOCK_PREFIX,
    SAGA_STATE_PREFIX,
    SAGA_STEP_PREFIX,
    VALID_STATE_TRANSITIONS,
    RedisKeyMixin,
    RedisLockManager,
    RedisQueryOperations,
    RedisSagaStateRepository,
    RedisStateManager,
)

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    # Configuration
    "DEFAULT_TTL_DAYS",
    "SAGA_CHECKPOINT_PREFIX",
    "SAGA_COMPENSATION_PREFIX",
    "SAGA_INDEX_STATE_PREFIX",
    "SAGA_INDEX_TENANT_PREFIX",
    "SAGA_LOCK_PREFIX",
    # Key prefixes
    "SAGA_STATE_PREFIX",
    "SAGA_STEP_PREFIX",
    # State transitions
    "VALID_STATE_TRANSITIONS",
    # Mixin classes exposed for extension
    "RedisKeyMixin",
    "RedisLockManager",
    "RedisQueryOperations",
    "RedisSagaStateRepository",
    "RedisStateManager",
]
