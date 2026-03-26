"""
Redis Caching for ACGS-2 Constitutional Storage.

Constitutional Hash: 608508a9bd224290
"""

import json
import sys

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

from pydantic import ValidationError

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..version_model import ConstitutionalVersion
from .config import StorageConfig

logger = get_logger(__name__)

_module = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.constitutional.storage_infra.cache", _module)
sys.modules.setdefault("packages.enhanced_agent_bus.constitutional.storage_infra.cache", _module)


class CacheManager:
    """Manages Redis caching for constitutional versions."""

    def __init__(self, config: StorageConfig):
        self.config = config
        self.redis_client: object | None = None

    async def connect(self) -> bool:
        """Connect to Redis."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, caching disabled")
            return False

        try:
            self.redis_client = aioredis.from_url(
                self.config.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis_client.ping()
            return True
        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

    async def get_version(self, version_id: str, tenant_id: str) -> ConstitutionalVersion | None:
        """Get version from Redis cache."""
        if not self.redis_client:
            return None

        try:
            key = self._get_tenant_key(f"{self.config.version_prefix}{version_id}", tenant_id)
            json_str = await self.redis_client.get(key)
            if not json_str:
                return None

            data = json.loads(json_str)
            return ConstitutionalVersion(**data)
        except (ConnectionError, OSError, json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Failed to get version {version_id} from cache: {e}")
            return None

    async def set_version(self, version: ConstitutionalVersion, tenant_id: str) -> bool:
        """Cache version in Redis."""
        if not self.redis_client:
            return False

        try:
            key = self._get_tenant_key(
                f"{self.config.version_prefix}{version.version_id}", tenant_id
            )
            json_str = json.dumps(version.to_dict())
            await self.redis_client.setex(key, self.config.cache_ttl, json_str)
            return True
        except (ConnectionError, OSError, TypeError, ValueError) as e:
            logger.warning(f"Failed to cache version {version.version_id}: {e}")
            return False

    async def invalidate_version(self, version_id: str, tenant_id: str) -> bool:
        """Invalidate version cache in Redis."""
        if not self.redis_client:
            return False

        try:
            key = self._get_tenant_key(f"{self.config.version_prefix}{version_id}", tenant_id)
            await self.redis_client.delete(key)
            return True
        except (ConnectionError, OSError) as e:
            logger.warning(f"Failed to invalidate cache for version {version_id}: {e}")
            return False

    async def set_active_version(self, version_id: str, tenant_id: str) -> bool:
        """set active version ID in Redis cache."""
        if not self.redis_client:
            return False

        try:
            key = self._get_tenant_key(self.config.active_version_key, tenant_id)
            await self.redis_client.setex(key, self.config.cache_ttl, version_id)
            return True
        except (ConnectionError, OSError) as e:
            logger.warning(f"Failed to set active version cache: {e}")
            return False

    async def get_active_version_id(self, tenant_id: str) -> str | None:
        """Get active version ID from Redis cache."""
        if not self.redis_client:
            return None

        try:
            key = self._get_tenant_key(self.config.active_version_key, tenant_id)
            return await self.redis_client.get(key)  # type: ignore[no-any-return]
        except (ConnectionError, OSError) as e:
            logger.warning(f"Failed to get active version from cache: {e}")
            return None

    def _get_tenant_key(self, base_key: str, tenant_id: str) -> str:
        """Get tenant-scoped key."""
        return f"tenant:{tenant_id}:{base_key}"
