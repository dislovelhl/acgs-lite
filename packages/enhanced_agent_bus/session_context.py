"""
ACGS-2 Enhanced Agent Bus - Session Context Management
Constitutional Hash: cdd01ef066bc6cf2

Provides session context storage with Redis backend for dynamic
per-session governance configuration.
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import redis.asyncio as aioredis
    import redis.exceptions

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False


from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from .models import SessionGovernanceConfig

logger = get_logger(__name__)


class _AsyncRedisProtocol(Protocol):
    """Protocol for async Redis client operations used by SessionContextStore."""

    async def ping(self) -> Any: ...
    async def close(self) -> Any: ...
    async def setex(self, name: str, time: int, value: str) -> Any: ...
    async def set(self, name: str, value: str) -> Any: ...
    async def get(self, name: str) -> Any: ...
    async def delete(self, name: str) -> Any: ...
    async def exists(self, name: str) -> Any: ...
    async def expire(self, name: str, time: int) -> Any: ...


_SESSION_CONTEXT_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
)

DUAL_READ_MIGRATION_ENABLED = os.getenv("SESSION_DUAL_READ_MIGRATION", "true").lower() in (
    "true",
    "1",
    "yes",
)


class SessionContext(BaseModel):
    """Session context with governance configuration.

    Stores session-level governance settings, metadata, and lifecycle
    information for dynamic per-session policy enforcement.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session identifier",
    )
    tenant_id: str = Field(
        ...,
        description="Tenant identifier for multi-tenant isolation",
    )
    governance_config: SessionGovernanceConfig = Field(
        ...,
        description="Session governance configuration",
    )
    metadata: JSONDict = Field(
        default_factory=dict,
        description="Additional session metadata",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the session was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the session was last updated",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When the session expires (if TTL is set)",
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )

    model_config = {"from_attributes": True}

    def model_post_init(self, __context: object) -> None:
        """Validate constitutional hash after model initialization."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Constitutional hash mismatch: expected {CONSTITUTIONAL_HASH}, "
                f"got {self.constitutional_hash}"
            )

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for Redis storage."""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "governance_config": self.governance_config.model_dump(mode="json"),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "SessionContext":
        """Create from dictionary (Redis deserialization)."""
        governance_config = SessionGovernanceConfig(**data["governance_config"])
        return cls(
            session_id=data["session_id"],
            tenant_id=data["tenant_id"],
            governance_config=governance_config,
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            expires_at=(
                datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
            ),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )


class SessionContextStore:
    """Redis-backed storage for session contexts.

    Provides thread-safe CRUD operations with TTL support and
    automatic expiration for session lifecycle management.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "acgs:session",
        default_ttl: int = 3600,
    ):
        """Initialize session context store.

        Args:
            redis_url: Redis connection URL
            key_prefix: Key prefix for Redis keys
            default_ttl: Default TTL in seconds (1 hour default)
        """
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.redis_client: _AsyncRedisProtocol | None = None
        self._lock = asyncio.Lock()

    def _make_key(self, session_id: str, tenant_id: str) -> str:
        """Generate tenant-namespaced Redis key for session ID."""
        return f"{self.key_prefix}:t:{tenant_id}:{session_id}"

    def _make_legacy_key(self, session_id: str) -> str:
        """Generate legacy Redis key (pre-tenant-namespace) for migration."""
        return f"{self.key_prefix}:{session_id}"

    async def connect(self) -> bool:
        """Connect to Redis.

        Returns:
            True if connected successfully, False otherwise
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, session storage disabled")
            return False

        try:
            self.redis_client = aioredis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            # Test connection
            await self.redis_client.ping()
            logger.info(f"SessionContextStore connected to Redis at {self.redis_url}")
            return True
        except (ConnectionError, OSError, redis.exceptions.RedisError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("SessionContextStore disconnected from Redis")

    async def set(self, session_context: SessionContext, ttl: int | None = None) -> bool:
        """Store session context with TTL.

        Args:
            session_context: Session context to store
            ttl: Time-to-live in seconds (uses default_ttl if None)

        Returns:
            True if stored successfully
        """
        if not self.redis_client:
            logger.warning("Redis client not connected")
            return False

        try:
            # Update the updated_at timestamp
            session_context.updated_at = datetime.now(UTC)

            # Calculate expiration if TTL is set
            ttl_seconds = ttl if ttl is not None else self.default_ttl
            if ttl_seconds > 0:
                from datetime import timedelta

                session_context.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

            key = self._make_key(session_context.session_id, session_context.tenant_id)
            data = json.dumps(session_context.to_dict())

            # Use SETEX for atomic set with TTL
            if ttl_seconds > 0:
                await self.redis_client.setex(key, ttl_seconds, data)
            else:
                # No expiration
                await self.redis_client.set(key, data)

            logger.debug(
                f"Stored session context {session_context.session_id} with TTL={ttl_seconds}s"
            )
            return True

        except (ConnectionError, OSError, TypeError) as e:
            logger.error(f"Failed to store session context: {e}")
            return False

    async def get(self, session_id: str, tenant_id: str) -> SessionContext | None:
        """Retrieve session context by ID with tenant validation.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            SessionContext if found and tenant matches, None otherwise
        """
        if not self.redis_client:
            logger.warning("Redis client not connected")
            return None

        try:
            key = self._make_key(session_id, tenant_id)
            data = await self.redis_client.get(key)

            if not data and DUAL_READ_MIGRATION_ENABLED:
                legacy_key = self._make_legacy_key(session_id)
                data = await self.redis_client.get(legacy_key)
                if data:
                    logger.info(f"Session {session_id} found via legacy key - migration pending")

            if not data:
                logger.debug(f"Session context {session_id} not found")
                return None

            session_dict = json.loads(data)
            session_context = SessionContext.from_dict(session_dict)

            if session_context.tenant_id != tenant_id:
                logger.warning(
                    f"Tenant mismatch for session {session_id}: "
                    f"expected {tenant_id}, got {session_context.tenant_id}"
                )
                return None

            # Check if expired (shouldn't happen with Redis TTL, but defensive)
            if session_context.expires_at:  # noqa: SIM102
                if datetime.now(UTC) > session_context.expires_at:
                    logger.warning(f"Session {session_id} has expired")
                    await self.delete(session_id, tenant_id)
                    return None

            logger.debug(f"Retrieved session context {session_id}")
            return session_context

        except (ConnectionError, OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to retrieve session context: {e}")
            return None

    async def delete(self, session_id: str, tenant_id: str) -> bool:
        """Delete session context.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            True if deleted successfully
        """
        if not self.redis_client:
            logger.warning("Redis client not connected")
            return False

        try:
            key = self._make_key(session_id, tenant_id)
            result = await self.redis_client.delete(key)
            logger.debug(f"Deleted session context {session_id}")
            return bool(result > 0)

        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to delete session context: {e}")
            return False

    async def exists(self, session_id: str, tenant_id: str) -> bool:
        """Check if session context exists.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            True if session exists and is not expired
        """
        if not self.redis_client:
            return False

        try:
            key = self._make_key(session_id, tenant_id)
            result = await self.redis_client.exists(key)
            return bool(result > 0)

        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to check session existence: {e}")
            return False

    async def update_ttl(self, session_id: str, tenant_id: str, ttl: int) -> bool:
        """Update TTL for existing session.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation
            ttl: New time-to-live in seconds

        Returns:
            True if TTL updated successfully
        """
        if not self.redis_client:
            logger.warning("Redis client not connected")
            return False

        try:
            key = self._make_key(session_id, tenant_id)
            result = await self.redis_client.expire(key, ttl)
            if result:
                logger.debug(f"Updated TTL for session {session_id} to {ttl}s")
            return bool(result > 0)

        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to update session TTL: {e}")
            return False

    async def get_ttl(self, session_id: str, tenant_id: str) -> int | None:
        """Get remaining TTL for session.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            Remaining TTL in seconds, None if no TTL or not found
        """
        if not self.redis_client:
            return None

        try:
            key = self._make_key(session_id, tenant_id)
            ttl = await self.redis_client.ttl(key)
            if ttl < 0:
                return None
            return ttl  # type: ignore[no-any-return]

        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to get session TTL: {e}")
            return None


class SessionContextManager:
    """Manager for session contexts with caching and lifecycle management.

    Provides high-level CRUD operations with an in-memory LRU cache for
    performance optimization. Tracks metrics for cache hits/misses and
    ensures atomic operations for concurrent access.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        store: SessionContextStore | None = None,
        cache_size: int = 1000,
        cache_ttl: int = 300,
        redis_url: str = "redis://localhost:6379",
        default_session_ttl: int = 3600,
    ):
        """Initialize session context manager.

        Args:
            store: Optional SessionContextStore instance (creates new if None)
            cache_size: Maximum number of cached sessions (LRU eviction)
            cache_ttl: Cache entry TTL in seconds
            redis_url: Redis connection URL (used if store is None)
            default_session_ttl: Default TTL for new sessions in seconds
        """
        self.store = store or SessionContextStore(
            redis_url=redis_url, default_ttl=default_session_ttl
        )
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl
        self.default_session_ttl = default_session_ttl

        # LRU cache using OrderedDict
        from collections import OrderedDict, defaultdict

        self._cache: OrderedDict = OrderedDict()
        self._cache_timestamps: dict[str, float] = {}
        self._session_locks: defaultdict = defaultdict(asyncio.Lock)
        self._lock = asyncio.Lock()

        # Metrics
        self._metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "creates": 0,
            "reads": 0,
            "updates": 0,
            "deletes": 0,
            "errors": 0,
        }

        logger.info(
            f"SessionContextManager initialized with cache_size={cache_size}, "
            f"cache_ttl={cache_ttl}s"
        )

    async def connect(self) -> bool:
        """Connect to Redis backend.

        Returns:
            True if connected successfully
        """
        return await self.store.connect()

    async def disconnect(self) -> None:
        """Disconnect from Redis backend."""
        await self.store.disconnect()

    def _is_cache_valid(self, session_id: str) -> bool:
        """Check if cached entry is still valid.

        Args:
            session_id: Session identifier

        Returns:
            True if cache entry exists and is not expired
        """
        import time

        if session_id not in self._cache:
            return False

        timestamp = self._cache_timestamps.get(session_id, 0)
        return (time.monotonic() - timestamp) < self.cache_ttl

    def _update_cache(self, session_context: SessionContext) -> None:
        """Update cache with session context.

        Implements LRU eviction if cache is full.

        Args:
            session_context: Session context to cache
        """
        import time

        cache_key = f"{session_context.tenant_id}:{session_context.session_id}"

        while len(self._cache) >= self.cache_size:
            oldest_id = next(iter(self._cache))
            del self._cache[oldest_id]
            if oldest_id in self._cache_timestamps:
                del self._cache_timestamps[oldest_id]
            # Clean up lock for evicted session to prevent memory leak
            if oldest_id in self._session_locks:
                del self._session_locks[oldest_id]
                logger.debug(f"Cleaned up lock for evicted session {oldest_id}")

        self._cache[cache_key] = session_context
        self._cache_timestamps[cache_key] = time.monotonic()

        self._cache.move_to_end(cache_key)

    def _invalidate_cache(self, session_id: str, tenant_id: str) -> None:
        """Remove session from cache.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation
        """
        cache_key = f"{tenant_id}:{session_id}"
        if cache_key in self._cache:
            del self._cache[cache_key]
        if cache_key in self._cache_timestamps:
            del self._cache_timestamps[cache_key]
        # Clean up lock for invalidated session to prevent memory leak
        if cache_key in self._session_locks:
            del self._session_locks[cache_key]
            logger.debug(f"Cleaned up lock for invalidated session {session_id}")

    async def create(
        self,
        governance_config: SessionGovernanceConfig,
        tenant_id: str,
        session_id: str | None = None,
        metadata: JSONDict | None = None,
        ttl: int | None = None,
    ) -> SessionContext:
        """Create a new session context.

        Args:
            governance_config: Session governance configuration
            tenant_id: Tenant identifier for isolation
            session_id: Optional session ID (generated if None)
            metadata: Optional session metadata
            ttl: Optional TTL in seconds (uses default if None)

        Returns:
            Created SessionContext

        Raises:
            ValueError: If session already exists
        """
        session_id = session_id or str(uuid.uuid4())
        lock_key = f"{tenant_id}:{session_id}"
        async with self._session_locks[lock_key]:
            try:
                session_context = SessionContext(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    governance_config=governance_config,
                    metadata=metadata or {},
                )

                if await self.store.exists(session_context.session_id, tenant_id):
                    raise ValueError(f"Session {session_context.session_id} already exists")

                # Store in Redis
                ttl_seconds = ttl or self.default_session_ttl
                success = await self.store.set(session_context, ttl=ttl_seconds)

                if not success:
                    raise RuntimeError("Failed to store session context in Redis")

                # Update cache
                self._update_cache(session_context)

                # Update metrics
                self._metrics["creates"] += 1

                logger.info(f"Created session {session_context.session_id} with TTL={ttl_seconds}s")
                return session_context

            except _SESSION_CONTEXT_OPERATION_ERRORS as e:
                self._metrics["errors"] += 1
                logger.error(f"Failed to create session: {e}")
                raise

    async def _get_internal(self, session_id: str, tenant_id: str) -> SessionContext | None:
        """Internal get operation without locking.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            SessionContext if found, None otherwise
        """
        try:
            self._metrics["reads"] += 1

            cache_key = f"{tenant_id}:{session_id}"
            if self._is_cache_valid(cache_key):
                session_context = self._cache[cache_key]
                self._cache.move_to_end(cache_key)
                self._metrics["cache_hits"] += 1
                logger.debug(f"Cache hit for session {session_id}")
                return session_context  # type: ignore[no-any-return]

            self._metrics["cache_misses"] += 1
            logger.debug(f"Cache miss for session {session_id}")

            session_context = await self.store.get(session_id, tenant_id)

            if session_context:
                self._update_cache(session_context)

            return session_context

        except _SESSION_CONTEXT_OPERATION_ERRORS as e:
            self._metrics["errors"] += 1
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    async def get(self, session_id: str, tenant_id: str) -> SessionContext | None:
        """Get session context by ID.

        Uses cache for performance, falls back to Redis.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            SessionContext if found, None otherwise
        """
        lock_key = f"{tenant_id}:{session_id}"
        async with self._session_locks[lock_key]:
            return await self._get_internal(session_id, tenant_id)

    async def update(
        self,
        session_id: str,
        tenant_id: str,
        governance_config: SessionGovernanceConfig | None = None,
        metadata: JSONDict | None = None,
        ttl: int | None = None,
    ) -> SessionContext | None:
        """Update session context.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation
            governance_config: New governance config (keeps existing if None)
            metadata: New metadata (merges with existing if None)
            ttl: New TTL in seconds (keeps existing if None)

        Returns:
            Updated SessionContext if successful, None otherwise
        """
        lock_key = f"{tenant_id}:{session_id}"
        async with self._session_locks[lock_key]:
            try:
                self._metrics["updates"] += 1

                session_context = await self._get_internal(session_id, tenant_id)
                if not session_context:
                    logger.warning(f"Session {session_id} not found for update")
                    return None

                if governance_config:
                    session_context.governance_config = governance_config

                if metadata is not None:
                    session_context.metadata.update(metadata)

                session_context.updated_at = datetime.now(UTC)

                ttl_seconds = ttl or self.default_session_ttl
                success = await self.store.set(session_context, ttl=ttl_seconds)

                if not success:
                    logger.error(f"Failed to update session {session_id} in Redis")
                    return None

                self._invalidate_cache(session_id, tenant_id)
                self._update_cache(session_context)

                logger.info(f"Updated session {session_id}")
                return session_context

            except _SESSION_CONTEXT_OPERATION_ERRORS as e:
                self._metrics["errors"] += 1
                logger.error(f"Failed to update session {session_id}: {e}")
                return None

    async def delete(self, session_id: str, tenant_id: str) -> bool:
        """Delete session context.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            True if deleted successfully
        """
        lock_key = f"{tenant_id}:{session_id}"
        async with self._session_locks[lock_key]:
            try:
                self._metrics["deletes"] += 1

                success = await self.store.delete(session_id, tenant_id)

                self._invalidate_cache(session_id, tenant_id)

                if success:
                    logger.info(f"Deleted session {session_id}")
                else:
                    logger.warning(f"Session {session_id} not found for deletion")

                return success

            except _SESSION_CONTEXT_OPERATION_ERRORS as e:
                self._metrics["errors"] += 1
                logger.error(f"Failed to delete session {session_id}: {e}")
                return False

    async def exists(self, session_id: str, tenant_id: str) -> bool:
        """Check if session exists.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation

        Returns:
            True if session exists and is not expired
        """
        cache_key = f"{tenant_id}:{session_id}"
        if self._is_cache_valid(cache_key):
            return True

        return await self.store.exists(session_id, tenant_id)

    async def extend_ttl(self, session_id: str, tenant_id: str, ttl: int) -> bool:
        """Extend session TTL.

        Args:
            session_id: Session identifier
            tenant_id: Tenant identifier for isolation
            ttl: New TTL in seconds

        Returns:
            True if TTL updated successfully
        """
        success = await self.store.update_ttl(session_id, tenant_id, ttl)
        if success:
            logger.info(f"Extended TTL for session {session_id} to {ttl}s")
        return success

    def get_metrics(self) -> JSONDict:
        """Get current metrics.

        Returns:
            Dictionary of metrics including cache hits/misses and cache_hit_rate (float)
        """
        metrics: JSONDict = dict(self._metrics)
        # Calculate cache hit rate
        total_reads = metrics["cache_hits"] + metrics["cache_misses"]
        if total_reads > 0:
            metrics["cache_hit_rate"] = metrics["cache_hits"] / total_reads
        else:
            metrics["cache_hit_rate"] = 0.0

        metrics["cache_size"] = len(self._cache)
        metrics["cache_capacity"] = self.cache_size

        return metrics

    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        self._metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "creates": 0,
            "reads": 0,
            "updates": 0,
            "deletes": 0,
            "errors": 0,
        }
        logger.info("Metrics reset")

    async def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        async with self._lock:
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.info("Cache cleared")


__all__ = [
    "SessionContext",
    "SessionContextManager",
    "SessionContextStore",
]
