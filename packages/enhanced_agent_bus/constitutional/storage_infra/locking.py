"""
Distributed Locking for ACGS-2 Constitutional Storage.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.observability.structured_logging import get_logger

from .cache import CacheManager
from .config import StorageConfig

logger = get_logger(__name__)


class LockManager:
    """Manages distributed locks for constitutional transitions."""

    def __init__(self, config: StorageConfig, cache: CacheManager):
        self.config = config
        self.cache = cache

    async def acquire_lock(self, tenant_id: str) -> bool:
        """Acquire distributed lock for version transition.

        Uses tenant-scoped lock keys.
        """
        if not self.cache.redis_client:
            logger.warning("Redis not available, lock acquisition skipped (unsafe)")
            return True

        try:
            lock_key = self.cache._get_tenant_key(self.config.lock_key, tenant_id)
            acquired = await self.cache.redis_client.set(
                lock_key, "1", nx=True, ex=self.config.lock_timeout
            )
            return bool(acquired)
        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False

    async def release_lock(self, tenant_id: str) -> bool:
        """Release distributed lock for version transition."""
        if not self.cache.redis_client:
            return True

        try:
            lock_key = self.cache._get_tenant_key(self.config.lock_key, tenant_id)
            await self.cache.redis_client.delete(lock_key)
            return True
        except (ConnectionError, OSError) as e:
            logger.warning(f"Failed to release lock: {e}")
            return False
