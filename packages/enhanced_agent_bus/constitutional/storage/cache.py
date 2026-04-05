"""
Cache Layer for Constitutional Storage
Constitutional Hash: 608508a9bd224290

Abstraction over Redis cache with tenant-aware key management.
"""

from typing import Any, Protocol

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.json_utils import dumps as json_dumps
from enhanced_agent_bus._compat.json_utils import loads as json_loads

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger


class _RedisClientProtocol(Protocol):
    """Minimal async Redis client interface required by ConstitutionalCache."""

    async def get(self, key: str) -> Any: ...
    async def setex(self, key: str, ttl: int, value: Any) -> Any: ...
    async def delete(self, key: str) -> Any: ...


logger = get_logger(__name__)
_CACHE_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class ConstitutionalCache:
    """
    Redis cache layer for constitutional version management.

    Features:
    - Hot path cache for active version (<1ms)
    - Tenant-scoped cache keys
    - TTL-based invalidation
    - JSON serialization for complex types

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        redis_client: _RedisClientProtocol,
        cache_ttl: int = 3600,
        version_prefix: str = "constitutional:version:",
        active_version_key: str = "constitutional:active_version",
    ):
        """
        Initialize constitutional cache layer.

        Args:
            redis_client: Redis client instance
            cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
            version_prefix: Prefix for version cache keys
            active_version_key: Key for active version ID
        """
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl
        self.version_prefix = version_prefix
        self.active_version_key = active_version_key

    async def get_version(self, version_id: str, tenant_id: str) -> JSONDict | None:
        """
        Get version from cache.

        Args:
            version_id: Version identifier
            tenant_id: Tenant identifier for key scoping

        Returns:
            Version data or None if not cached
        """
        cache_key = self._get_version_cache_key(version_id, tenant_id)
        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                return json_loads(cached_data)
            return None
        except _CACHE_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Cache get error: {e}")
            return None

    async def cache_version(self, version: JSONDict, tenant_id: str) -> bool:
        """
        Cache version data with TTL.

        Args:
            version: Version data to cache
            tenant_id: Tenant identifier for key scoping

        Returns:
            True if cached successfully, False otherwise
        """
        cache_key = self._get_version_cache_key(version["version_id"], tenant_id)
        try:
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json_dumps(version),
            )
            return True
        except _CACHE_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Cache set error: {e}")
            return False

    async def invalidate_version(self, version_id: str, tenant_id: str) -> bool:
        """
        Invalidate cached version.

        Args:
            version_id: Version identifier
            tenant_id: Tenant identifier for key scoping

        Returns:
            True if invalidated successfully, False otherwise
        """
        cache_key = self._get_version_cache_key(version_id, tenant_id)
        try:
            await self.redis_client.delete(cache_key)
            return True
        except _CACHE_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Cache delete error: {e}")
            return False

    async def get_active_version_id(self, tenant_id: str) -> str | None:
        """
        Get active version ID from cache.

        Args:
            tenant_id: Tenant identifier for key scoping

        Returns:
            Active version ID or None if not cached
        """
        cache_key = self._get_tenant_active_key(tenant_id)
        try:
            cached_data = await self.redis_client.get(cache_key)
            if not cached_data:
                return None
            return (
                cached_data.decode("utf-8") if isinstance(cached_data, bytes) else str(cached_data)
            )
        except _CACHE_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Active version get error: {e}")
            return None

    async def set_active_version_id(self, version_id: str, tenant_id: str) -> bool:
        """
        Set active version ID in cache.

        Args:
            version_id: Active version ID
            tenant_id: Tenant identifier for key scoping

        Returns:
            True if set successfully, False otherwise
        """
        cache_key = self._get_tenant_active_key(tenant_id)
        try:
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                version_id,
            )
            return True
        except _CACHE_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Active version set error: {e}")
            return False

    def _get_version_cache_key(self, version_id: str, tenant_id: str) -> str:
        """
        Get tenant-scoped version cache key.

        Args:
            version_id: Version identifier
            tenant_id: Tenant identifier

        Returns:
            Tenant-scoped cache key
        """
        return f"{self.version_prefix}tenant:{tenant_id}:{version_id}"

    def _get_tenant_active_key(self, tenant_id: str) -> str:
        """
        Get tenant-scoped active version key.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Tenant-scoped active version key
        """
        return f"{self.active_version_key}:tenant:{tenant_id}"
