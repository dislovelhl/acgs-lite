"""
Redis Saga Persistence Module
Constitutional Hash: 608508a9bd224290

Provides Redis-backed saga state persistence with distributed locking,
checkpoint management, and automatic TTL handling.

This module is organized into focused submodules:
- repository.py: Main class with core CRUD operations
- keys.py: Redis key prefixes and generation utilities
- queries.py: Query operations (list_by_*, count_by_*)
- state.py: State transitions, checkpoints, compensation logs
- locking.py: Distributed locking and maintenance operations
"""

from .keys import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_TTL_DAYS,
    SAGA_CHECKPOINT_PREFIX,
    SAGA_COMPENSATION_PREFIX,
    SAGA_INDEX_STATE_PREFIX,
    SAGA_INDEX_TENANT_PREFIX,
    SAGA_LOCK_PREFIX,
    SAGA_STATE_PREFIX,
    SAGA_STEP_PREFIX,
    RedisKeyMixin,
)
from .locking import RedisLockManager
from .queries import RedisQueryOperations
from .repository import RedisSagaStateRepository
from .state import VALID_STATE_TRANSITIONS, RedisStateManager

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_TTL_DAYS",
    "SAGA_CHECKPOINT_PREFIX",
    "SAGA_COMPENSATION_PREFIX",
    "SAGA_INDEX_STATE_PREFIX",
    "SAGA_INDEX_TENANT_PREFIX",
    "SAGA_LOCK_PREFIX",
    # Constants
    "SAGA_STATE_PREFIX",
    "SAGA_STEP_PREFIX",
    "VALID_STATE_TRANSITIONS",
    # Mixins (for extension)
    "RedisKeyMixin",
    "RedisLockManager",
    "RedisQueryOperations",
    # Main repository class
    "RedisSagaStateRepository",
    "RedisStateManager",
]
