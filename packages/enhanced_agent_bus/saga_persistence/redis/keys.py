"""
Redis Key Management for Saga Persistence
Constitutional Hash: 608508a9bd224290

Defines Redis key prefixes and generation utilities for saga storage.
Provides namespace isolation and consistent key formatting.
"""

from enhanced_agent_bus.saga_persistence.models import SagaState

# Redis key prefixes for namespace isolation
SAGA_STATE_PREFIX = "acgs2:saga:state:"
SAGA_STEP_PREFIX = "acgs2:saga:step:"
SAGA_COMPENSATION_PREFIX = "acgs2:saga:compensation:"
SAGA_CHECKPOINT_PREFIX = "acgs2:saga:checkpoint:"
SAGA_LOCK_PREFIX = "acgs2:saga:lock:"
SAGA_INDEX_STATE_PREFIX = "acgs2:saga:index:state:"
SAGA_INDEX_TENANT_PREFIX = "acgs2:saga:index:tenant:"

# Default TTL for saga data (7 days)
DEFAULT_TTL_DAYS = 7
DEFAULT_LOCK_TIMEOUT_SECONDS = 30


class RedisKeyMixin:
    """
    Mixin providing Redis key generation methods.

    Provides consistent key formatting for all saga-related Redis operations.
    """

    def _state_key(self, saga_id: str) -> str:
        """Get Redis key for saga state."""
        return f"{SAGA_STATE_PREFIX}{saga_id}"

    def _checkpoint_key(self, saga_id: str, checkpoint_id: str) -> str:
        """Get Redis key for checkpoint."""
        return f"{SAGA_CHECKPOINT_PREFIX}{saga_id}:{checkpoint_id}"

    def _checkpoint_list_key(self, saga_id: str) -> str:
        """Get Redis key for checkpoint list (sorted set)."""
        return f"{SAGA_CHECKPOINT_PREFIX}{saga_id}:list"

    def _compensation_key(self, saga_id: str) -> str:
        """Get Redis key for compensation log."""
        return f"{SAGA_COMPENSATION_PREFIX}{saga_id}"

    def _lock_key(self, saga_id: str) -> str:
        """Get Redis key for distributed lock."""
        return f"{SAGA_LOCK_PREFIX}{saga_id}"

    def _state_index_key(self, state: SagaState) -> str:
        """Get Redis key for state index."""
        return f"{SAGA_INDEX_STATE_PREFIX}{state.value}"

    def _tenant_index_key(self, tenant_id: str) -> str:
        """Get Redis key for tenant index."""
        return f"{SAGA_INDEX_TENANT_PREFIX}{tenant_id}"


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_TTL_DAYS",
    "SAGA_CHECKPOINT_PREFIX",
    "SAGA_COMPENSATION_PREFIX",
    "SAGA_INDEX_STATE_PREFIX",
    "SAGA_INDEX_TENANT_PREFIX",
    "SAGA_LOCK_PREFIX",
    "SAGA_STATE_PREFIX",
    "SAGA_STEP_PREFIX",
    "RedisKeyMixin",
]
