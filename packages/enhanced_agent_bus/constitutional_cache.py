"""
Constitutional Cache Implementation

Provides Redis-based caching for MACI governance operations with
constitutional hash validation and automatic invalidation strategies.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

import redis.asyncio as redis

try:
    from enhanced_agent_bus._compat.types import (
        CONSTITUTIONAL_HASH,
        JSONDict,
    )
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"  # type: ignore[misc,assignment]
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# =============================================================================
# Cache Configuration Constants
# Constitutional Hash: 608508a9bd224290
# =============================================================================

DEFAULT_CACHE_TTL_SECONDS = 3600  # 1 hour - default TTL for cached entries
MAX_CACHE_ENTRIES = 10000  # Maximum number of entries in cache
VALIDATION_CACHE_TTL_SECONDS = 300  # 5 minutes - TTL for validation results
CACHE_KEY_HASH_LENGTH = 8  # Length of hash suffix in cache keys


@dataclass
class CacheEntry:
    """Cache entry with metadata."""

    value: object
    constitutional_hash: str
    created_at: datetime
    ttl: int  # seconds
    tags: list[str]
    access_count: int = 0


class ConstitutionalCache:
    """
    Redis-based cache with constitutional compliance.

    Features:
    - Constitutional hash validation on all cached data
    - Tag-based invalidation
    - TTL management
    - Cache hit/miss metrics
    - Automatic serialization

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        default_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
        max_entries: int = MAX_CACHE_ENTRIES,
    ):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._local_cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _generate_key(self, namespace: str, identifier: str) -> str:
        """Generate a cache key with constitutional hash."""
        base = f"{namespace}:{identifier}"
        hash_suffix = hashlib.sha256(f"{base}:{CONSTITUTIONAL_HASH}".encode()).hexdigest()[
            :CACHE_KEY_HASH_LENGTH
        ]
        return f"acgs:cache:{base}:{hash_suffix}"

    def _validate_constitutional_hash(self, entry: CacheEntry) -> bool:
        """Validate that cached data matches current constitutional hash."""
        return entry.constitutional_hash == CONSTITUTIONAL_HASH  # type: ignore[no-any-return]

    async def get(
        self, namespace: str, identifier: str, tags: list[str] | None = None
    ) -> object | None:
        """
        Retrieve value from cache.

        Args:
            namespace: Cache namespace (e.g., 'policy', 'validation')
            identifier: Unique identifier within namespace
            tags: Optional tags for cache management

        Returns:
            Cached value or None if not found/invalid
        """
        key = self._generate_key(namespace, identifier)

        # Check local cache first (L1)
        if key in self._local_cache:
            entry = self._local_cache[key]
            if self._validate_constitutional_hash(entry):
                if datetime.now() < entry.created_at + timedelta(seconds=entry.ttl):
                    entry.access_count += 1
                    return entry.value
                else:
                    # Expired
                    del self._local_cache[key]

        # Check Redis (L2)
        try:
            data = await self.redis.get(key)
            if data:
                entry = CacheEntry(**json.loads(data))

                if not self._validate_constitutional_hash(entry):
                    # Constitutional hash mismatch - invalidate
                    await self.delete(namespace, identifier)
                    return None

                if datetime.now() < entry.created_at + timedelta(seconds=entry.ttl):
                    # Cache hit - update local cache
                    entry.access_count += 1
                    self._local_cache[key] = entry
                    return entry.value
                else:
                    # Expired
                    await self.delete(namespace, identifier)

        except (redis.RedisError, json.JSONDecodeError, TypeError, ValueError) as e:
            # Log error but don't fail - cache miss is acceptable
            logger.error(
                "Cache read error: %s",
                e,
                extra={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "namespace": namespace,
                    "identifier": identifier,
                },
            )

        return None

    async def set(
        self,
        namespace: str,
        identifier: str,
        value: object,
        ttl: int | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """
        Store value in cache.

        Args:
            namespace: Cache namespace
            identifier: Unique identifier
            value: Value to cache
            ttl: Time to live in seconds (default: DEFAULT_CACHE_TTL_SECONDS)
            tags: Tags for cache management

        Returns:
            True if successful
        """
        key = self._generate_key(namespace, identifier)
        actual_ttl = ttl or self.default_ttl

        entry = CacheEntry(
            value=value,
            constitutional_hash=CONSTITUTIONAL_HASH,
            created_at=datetime.now(),
            ttl=actual_ttl,
            tags=tags or [],
        )

        try:
            # Store in Redis
            serialized = json.dumps(entry.__dict__, default=str)
            await self.redis.setex(key, actual_ttl, serialized)

            # Add key to tag index SETs for efficient invalidation
            if tags:
                for tag in tags:
                    tag_key = f"acgs:tag:{tag}"
                    await self.redis.sadd(tag_key, key)
                    # Set TTL on tag index to match or exceed cache entry TTL
                    await self.redis.expire(tag_key, actual_ttl + 60)

            # Update local cache
            async with self._lock:
                self._local_cache[key] = entry

                # Evict oldest if over limit
                if len(self._local_cache) > self.max_entries:
                    oldest_key = min(
                        self._local_cache.keys(), key=lambda k: self._local_cache[k].created_at
                    )
                    del self._local_cache[oldest_key]

            return True

        except (redis.RedisError, json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(
                "Cache write error: %s",
                e,
                extra={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "namespace": namespace,
                    "identifier": identifier,
                    "ttl": actual_ttl,
                },
            )
            return False

    async def delete(self, namespace: str, identifier: str) -> bool:
        """Delete a specific cache entry."""
        key = self._generate_key(namespace, identifier)

        try:
            # Get tags before deletion to clean up tag indexes
            tags = []
            if key in self._local_cache:
                tags = self._local_cache[key].tags
            else:
                # Try to get from Redis
                try:
                    data = await self.redis.get(key)
                    if data:
                        entry_dict = json.loads(data)
                        tags = entry_dict.get("tags", [])
                except (redis.RedisError, json.JSONDecodeError, TypeError):
                    pass

            # Delete the cache entry
            await self.redis.delete(key)

            # Remove key from all tag indexes
            for tag in tags:
                tag_key = f"acgs:tag:{tag}"
                await self.redis.srem(tag_key, key)

            # Delete from local cache
            if key in self._local_cache:
                del self._local_cache[key]

            return True
        except (redis.RedisError, TypeError, KeyError) as e:
            logger.error(
                "Cache delete error: %s",
                e,
                extra={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "namespace": namespace,
                    "identifier": identifier,
                },
            )
            return False

    async def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all cache entries with a specific tag.

        Uses Redis SET-based tag index for O(K) performance where K = keys with tag.
        Falls back to full scan if tag index not available.

        Args:
            tag: Tag to invalidate

        Returns:
            Number of entries invalidated
        """
        count = self._invalidate_local_entries_for_tag(tag)
        tag_key = f"acgs:tag:{tag}"

        try:
            redis_count = await self._invalidate_tagged_redis_members(tag_key)
            if redis_count > 0:
                return count + redis_count

            logger.debug(
                "Tag index not found, falling back to scan",
                extra={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "tag": tag,
                },
            )
            return count + await self._scan_and_invalidate_tag(tag)
        except (redis.RedisError, json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(
                "Tag-based invalidation failed, falling back to scan: %s",
                e,
                extra={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "tag": tag,
                },
            )
            return count + await self._safe_scan_fallback(tag)

    def _invalidate_local_entries_for_tag(self, tag: str) -> int:
        """Remove local-cache entries that include a specific tag."""
        keys_to_delete = [key for key, entry in self._local_cache.items() if tag in entry.tags]
        for key in keys_to_delete:
            del self._local_cache[key]
        return len(keys_to_delete)

    async def _invalidate_tagged_redis_members(self, tag_key: str) -> int:
        """Invalidate redis members recorded in the tag index key."""
        members = await self.redis.smembers(tag_key)
        if not members:
            return 0

        await self.redis.delete(*members)
        await self.redis.delete(tag_key)
        return len(members)

    async def _scan_and_invalidate_tag(self, tag: str) -> int:
        """Fallback scan that removes cache entries containing the given tag."""
        pattern = "acgs:cache:*"
        count = 0
        async for key in self.redis.scan_iter(match=pattern):
            data = await self.redis.get(key)
            if not data:
                continue

            entry_dict = json.loads(data)
            if tag in entry_dict.get("tags", []):
                await self.redis.delete(key)
                count += 1

        return count

    async def _safe_scan_fallback(self, tag: str) -> int:
        """Run scan fallback with defensive error logging."""
        try:
            return await self._scan_and_invalidate_tag(tag)
        except (redis.RedisError, json.JSONDecodeError, TypeError, ValueError) as fallback_err:
            logger.error(
                "Fallback tag invalidation also failed: %s",
                fallback_err,
                extra={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "tag": tag,
                },
            )
            return 0

    async def clear_namespace(self, namespace: str) -> int:
        """
        Clear all entries in a namespace.

        Args:
            namespace: Namespace to clear

        Returns:
            Number of entries cleared
        """
        pattern = f"acgs:cache:{namespace}:*"
        count = 0

        try:
            async for key in self.redis.scan_iter(match=pattern):
                await self.redis.delete(key)
                if key.decode() in self._local_cache:
                    del self._local_cache[key.decode()]
                count += 1
        except (redis.RedisError, TypeError, UnicodeDecodeError, KeyError) as e:
            logger.error(
                "Namespace clear error: %s",
                e,
                extra={
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "namespace": namespace,
                },
            )

        return count

    async def get_stats(self) -> JSONDict:
        """Get cache statistics."""
        return {
            "local_cache_size": len(self._local_cache),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "default_ttl": self.default_ttl,
            "max_entries": self.max_entries,
        }


class PolicyCache(ConstitutionalCache):
    """
    Specialized cache for OPA policies.

    Provides automatic invalidation when policies are updated.
    """

    async def cache_policy(
        self, policy_id: str, policy_content: str, ttl: int | None = None
    ) -> bool:
        """Cache a policy with validation metadata."""
        return await self.set(
            namespace="policy",
            identifier=policy_id,
            value={
                "content": policy_content,
                "hash": hashlib.sha256(policy_content.encode()).hexdigest(),
            },
            ttl=ttl,
            tags=["policy", f"policy:{policy_id}"],
        )

    async def get_policy(self, policy_id: str) -> dict[str, str] | None:
        """Retrieve cached policy."""
        return await self.get(
            namespace="policy", identifier=policy_id, tags=["policy", f"policy:{policy_id}"]
        )

    async def invalidate_policy(self, policy_id: str) -> bool:
        """Invalidate a specific policy."""
        return await self.delete("policy", policy_id)

    async def invalidate_all_policies(self) -> int:
        """Invalidate all cached policies."""
        return await self.invalidate_by_tag("policy")


class ValidationCache(ConstitutionalCache):
    """
    Specialized cache for constitutional validation results.

    Caches validation outcomes to avoid redundant checks.
    """

    async def cache_validation(
        self, validation_key: str, result: JSONDict, ttl: int | None = None
    ) -> bool:
        """Cache a validation result."""
        return await self.set(
            namespace="validation",
            identifier=validation_key,
            value=result,
            ttl=ttl or VALIDATION_CACHE_TTL_SECONDS,
            tags=["validation", "constitutional"],
        )

    async def get_validation(self, validation_key: str) -> JSONDict | None:
        """Retrieve cached validation result."""
        return await self.get(namespace="validation", identifier=validation_key)
