"""
ACGS-2 Decision Store - Redis-backed Decision Explanation Storage
Constitutional Hash: cdd01ef066bc6cf2

Implements FR-12 Decision Explanation API storage requirements:
- Redis-backed storage with 24-hour TTL
- Async CRUD operations
- Tenant isolation via key prefixes
- Integration with audit trail

Performance Targets:
- P99 latency <5ms for single operations
- Support for high-throughput batch operations
"""

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Optional

from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _DecisionStoreMetrics(TypedDict, total=False):
    """Type definition for decision store metrics."""

    total_stores: int
    total_retrievals: int
    total_deletes: int
    cache_hits: int
    cache_misses: int
    failed_operations: int
    total_latency_ms: float
    memory_fallback_active: bool
    created_at: str
    cache_hit_rate: float
    avg_latency_ms: float
    constitutional_hash: str


from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
from src.core.shared.types import JSONDict  # noqa: E402

try:
    from src.core.shared.event_schemas.decision_explanation import (
        DecisionExplanationV1,
        create_decision_explanation,
    )
except ImportError:
    DecisionExplanationV1 = None  # type: ignore[misc, assignment]
    create_decision_explanation = None  # type: ignore[misc, assignment]

from .redis_pool import (  # noqa: E402
    REDIS_AVAILABLE,
    RedisConnectionPool,
    get_shared_pool,
)

logger = get_logger(__name__)
# Default configuration
DEFAULT_TTL_SECONDS = 900  # 15 minutes
DEFAULT_KEY_PREFIX = "acgs:decision"
DEFAULT_INDEX_PREFIX = "acgs:decision:idx"


class DecisionStore:
    """
    Redis-backed storage for governance decision explanations.

    Features:
    - 24-hour TTL for decision explanations
    - Tenant isolation via key prefixes
    - Message ID indexing for lookup
    - Batch operations with pipelining
    - Metrics collection for observability
    - Audit trail integration

    Key Schema:
    - Decision: {prefix}:{tenant_id}:{decision_id}
    - Message Index: {index_prefix}:msg:{tenant_id}:{message_id}
    - Time Index: {index_prefix}:time:{tenant_id}:{timestamp}

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        redis_pool: RedisConnectionPool | None = None,
        redis_url: str = "redis://localhost:6379",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        index_prefix: str = DEFAULT_INDEX_PREFIX,
        enable_metrics: bool = True,
    ):
        """
        Initialize the Decision Store.

        Args:
            redis_pool: Optional shared Redis pool (creates new if None)
            redis_url: Redis connection URL (only used if pool not provided)
            ttl_seconds: TTL for stored decisions (default 24 hours)
            key_prefix: Key prefix for decision storage
            index_prefix: Key prefix for indexes
            enable_metrics: Whether to collect operation metrics
        """
        self._pool = redis_pool
        self._redis_url = redis_url
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix
        self._index_prefix = index_prefix
        self._enable_metrics = enable_metrics
        self.constitutional_hash = CONSTITUTIONAL_HASH

        self._initialized = False
        self._lock = asyncio.Lock()

        # In-memory fallback when Redis unavailable
        self._memory_store: dict[str, str] = {}
        self._memory_indexes: dict[str, str] = {}
        self._use_memory_fallback = False

        # Metrics tracking
        self._metrics: _DecisionStoreMetrics = {
            "total_stores": 0,
            "total_retrievals": 0,
            "total_deletes": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "failed_operations": 0,
            "total_latency_ms": 0.0,
            "memory_fallback_active": False,
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def initialize(self) -> bool:
        """
        Initialize the decision store and Redis connection.

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            return True

        async with self._lock:
            if self._initialized:
                return True

            if not REDIS_AVAILABLE:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Redis not available, using memory fallback"
                )
                self._use_memory_fallback = True
                self._metrics["memory_fallback_active"] = True
                self._initialized = True
                return True

            try:
                if self._pool is None:
                    self._pool = await get_shared_pool(redis_url=self._redis_url)

                # Verify connection
                health = await self._pool.health_check()
                if not health.get("healthy"):
                    logger.warning(
                        f"[{CONSTITUTIONAL_HASH}] Redis unhealthy, using memory fallback: "
                        f"{health.get('error', 'unknown error')}"
                    )
                    self._use_memory_fallback = True
                    self._metrics["memory_fallback_active"] = True
                else:
                    self._use_memory_fallback = False
                    self._metrics["memory_fallback_active"] = False

                self._initialized = True
                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] DecisionStore initialized: "
                    f"redis={not self._use_memory_fallback}, ttl={self._ttl_seconds}s"
                )
                return True

            except (OSError, ConnectionError, ValueError, TypeError, RuntimeError) as e:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Redis init failed, using memory fallback: {e}"
                )
                self._use_memory_fallback = True
                self._metrics["memory_fallback_active"] = True
                self._initialized = True
                return True

    def _make_key(self, tenant_id: str, decision_id: str) -> str:
        """Generate storage key for a decision."""
        safe_tenant = tenant_id.replace(":", "_") if tenant_id else "default"
        return f"{self._key_prefix}:{safe_tenant}:{decision_id}"

    def _make_message_index_key(self, tenant_id: str, message_id: str) -> str:
        """Generate index key for message ID lookup."""
        safe_tenant = tenant_id.replace(":", "_") if tenant_id else "default"
        return f"{self._index_prefix}:msg:{safe_tenant}:{message_id}"

    def _make_time_index_key(self, tenant_id: str, timestamp: str) -> str:
        """Generate index key for time-based lookup."""
        safe_tenant = tenant_id.replace(":", "_") if tenant_id else "default"
        return f"{self._index_prefix}:time:{safe_tenant}:{timestamp}"

    async def store(
        self,
        explanation: "DecisionExplanationV1",
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Store a decision explanation.

        Args:
            explanation: DecisionExplanationV1 instance to store
            ttl_seconds: Optional custom TTL (defaults to store TTL)

        Returns:
            True if stored successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.perf_counter()
        ttl = ttl_seconds or self._ttl_seconds

        try:
            # Serialize explanation
            json_data = explanation.model_dump_json()
            tenant_id = explanation.tenant_id or "default"
            decision_id = explanation.decision_id

            key = self._make_key(tenant_id, decision_id)

            if self._use_memory_fallback:
                self._memory_store[key] = json_data
                # Create message index if message_id present
                if explanation.message_id:
                    msg_key = self._make_message_index_key(tenant_id, explanation.message_id)
                    self._memory_indexes[msg_key] = decision_id
                success = True
            else:
                async with self._pool.acquire() as conn:
                    # Store explanation with TTL
                    await conn.setex(key, ttl, json_data)

                    # Create message index if message_id present
                    if explanation.message_id:
                        msg_key = self._make_message_index_key(tenant_id, explanation.message_id)
                        await conn.setex(msg_key, ttl, decision_id)

                    success = True

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics["total_stores"] += 1
            self._metrics["total_latency_ms"] += elapsed_ms

            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Stored decision {decision_id} "
                f"for tenant {tenant_id} (latency={elapsed_ms:.2f}ms)"
            )
            return success

        except (
            OSError,
            ConnectionError,
            ValueError,
            TypeError,
            RuntimeError,
            json.JSONDecodeError,
        ) as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to store decision: {e}")
            return False

    async def get(
        self,
        decision_id: str,
        tenant_id: str = "default",
    ) -> Optional["DecisionExplanationV1"]:
        """
        Retrieve a decision explanation by ID.

        Args:
            decision_id: Unique decision identifier
            tenant_id: Tenant identifier

        Returns:
            DecisionExplanationV1 if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.perf_counter()
        key = self._make_key(tenant_id, decision_id)

        try:
            if self._use_memory_fallback:
                json_data = self._memory_store.get(key)
            else:
                async with self._pool.acquire() as conn:
                    json_data = await conn.get(key)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics["total_retrievals"] += 1
            self._metrics["total_latency_ms"] += elapsed_ms

            if json_data:
                self._metrics["cache_hits"] += 1
                if DecisionExplanationV1 is not None:
                    return DecisionExplanationV1.model_validate_json(json_data)
                else:
                    # Return raw dict if schema not available
                    return json.loads(json_data)
            else:
                self._metrics["cache_misses"] += 1
                return None

        except (
            OSError,
            ConnectionError,
            ValueError,
            TypeError,
            RuntimeError,
            json.JSONDecodeError,
        ) as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get decision {decision_id}: {e}")
            return None

    async def get_by_message_id(
        self,
        message_id: str,
        tenant_id: str = "default",
    ) -> Optional["DecisionExplanationV1"]:
        """
        Retrieve a decision explanation by message ID.

        Args:
            message_id: Message identifier
            tenant_id: Tenant identifier

        Returns:
            DecisionExplanationV1 if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            msg_key = self._make_message_index_key(tenant_id, message_id)

            if self._use_memory_fallback:
                decision_id = self._memory_indexes.get(msg_key)
            else:
                async with self._pool.acquire() as conn:
                    decision_id = await conn.get(msg_key)

            if decision_id:
                return await self.get(decision_id, tenant_id)
            return None

        except (
            OSError,
            ConnectionError,
            ValueError,
            TypeError,
            RuntimeError,
            json.JSONDecodeError,
        ) as e:
            self._metrics["failed_operations"] += 1
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Failed to get decision by message {message_id}: {e}"
            )
            return None

    async def delete(
        self,
        decision_id: str,
        tenant_id: str = "default",
    ) -> bool:
        """
        Delete a decision explanation.

        Args:
            decision_id: Unique decision identifier
            tenant_id: Tenant identifier

        Returns:
            True if deleted, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.perf_counter()
        key = self._make_key(tenant_id, decision_id)

        try:
            if self._use_memory_fallback:
                if key in self._memory_store:
                    del self._memory_store[key]
                    # Clean up any message indexes pointing to this decision
                    for idx_key, idx_val in list(self._memory_indexes.items()):
                        if idx_val == decision_id:
                            del self._memory_indexes[idx_key]
                    deleted = True
                else:
                    deleted = False
            else:
                async with self._pool.acquire() as conn:
                    # Get the explanation first to find message_id
                    json_data = await conn.get(key)
                    if json_data:
                        try:
                            data = json.loads(json_data)
                            message_id = data.get("message_id")
                            if message_id:
                                msg_key = self._make_message_index_key(tenant_id, message_id)
                                await conn.delete(msg_key)
                        except json.JSONDecodeError:
                            pass

                    result = await conn.delete(key)
                    deleted = result > 0

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics["total_deletes"] += 1
            self._metrics["total_latency_ms"] += elapsed_ms

            return deleted

        except (
            OSError,
            ConnectionError,
            ValueError,
            TypeError,
            RuntimeError,
            json.JSONDecodeError,
        ) as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to delete decision {decision_id}: {e}")
            return False

    async def list_decisions(
        self,
        tenant_id: str = "default",
        limit: int = 100,
        offset: int = 0,
    ) -> list[str]:
        """
        List decision IDs for a tenant.

        Args:
            tenant_id: Tenant identifier
            limit: Maximum number of results
            offset: Starting offset

        Returns:
            List of decision IDs
        """
        if not self._initialized:
            await self.initialize()

        try:
            pattern = self._make_key(tenant_id, "*")

            if self._use_memory_fallback:
                matching_keys = [k for k in self._memory_store.keys() if k.startswith(pattern[:-1])]
                matching_keys = matching_keys[offset : offset + limit]
                # Extract decision IDs from keys
                prefix_len = len(self._make_key(tenant_id, ""))
                return [k[prefix_len:] for k in matching_keys]
            else:
                async with self._pool.acquire() as conn:
                    cursor = 0
                    decision_ids = []
                    count = 0

                    max_scan_iterations = 10_000
                    for _ in range(max_scan_iterations):
                        cursor, keys = await conn.scan(cursor=cursor, match=pattern, count=100)
                        for key in keys:
                            if count >= offset:
                                # Extract decision ID from key
                                parts = key.split(":")
                                if len(parts) >= 3:
                                    decision_ids.append(parts[-1])
                            count += 1
                            if len(decision_ids) >= limit:
                                return decision_ids

                        if cursor == 0:
                            break

                    return decision_ids

        except (OSError, ConnectionError, ValueError, TypeError, RuntimeError) as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to list decisions: {e}")
            return []

    async def exists(self, decision_id: str, tenant_id: str = "default") -> bool:
        """
        Check if a decision exists.

        Args:
            decision_id: Unique decision identifier
            tenant_id: Tenant identifier

        Returns:
            True if exists, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        key = self._make_key(tenant_id, decision_id)

        try:
            if self._use_memory_fallback:
                return key in self._memory_store
            else:
                async with self._pool.acquire() as conn:
                    return bool(await conn.exists(key) > 0)

        except (OSError, ConnectionError, ValueError, TypeError, RuntimeError) as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to check decision exists: {e}")
            return False

    async def get_ttl(self, decision_id: str, tenant_id: str = "default") -> int:
        """
        Get remaining TTL for a decision.

        Args:
            decision_id: Unique decision identifier
            tenant_id: Tenant identifier

        Returns:
            TTL in seconds, -1 if no expiry, -2 if key doesn't exist
        """
        if not self._initialized:
            await self.initialize()

        key = self._make_key(tenant_id, decision_id)

        try:
            if self._use_memory_fallback:
                # Memory fallback doesn't support TTL
                return self._ttl_seconds if key in self._memory_store else -2
            else:
                async with self._pool.acquire() as conn:
                    return int(await conn.ttl(key))

        except (OSError, ConnectionError, ValueError, TypeError, RuntimeError) as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to get TTL: {e}")
            return -2

    async def extend_ttl(
        self,
        decision_id: str,
        tenant_id: str = "default",
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Extend TTL for a decision.

        Args:
            decision_id: Unique decision identifier
            tenant_id: Tenant identifier
            ttl_seconds: New TTL (defaults to store TTL)

        Returns:
            True if extended, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        key = self._make_key(tenant_id, decision_id)
        ttl = ttl_seconds or self._ttl_seconds

        try:
            if self._use_memory_fallback:
                return key in self._memory_store
            else:
                async with self._pool.acquire() as conn:
                    return bool(await conn.expire(key, ttl))

        except (OSError, ConnectionError, ValueError, TypeError, RuntimeError) as e:
            self._metrics["failed_operations"] += 1
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to extend TTL: {e}")
            return False

    def get_metrics(self) -> JSONDict:
        """
        Get store operation metrics.

        Returns:
            Dictionary with store metrics
        """
        metrics: JSONDict = dict(self._metrics)

        if metrics["total_retrievals"] > 0:
            metrics["cache_hit_rate"] = (metrics["cache_hits"] / metrics["total_retrievals"]) * 100
        else:
            metrics["cache_hit_rate"] = 0.0

        total_ops = metrics["total_stores"] + metrics["total_retrievals"] + metrics["total_deletes"]
        if total_ops > 0:
            metrics["avg_latency_ms"] = metrics["total_latency_ms"] / total_ops
        else:
            metrics["avg_latency_ms"] = 0.0

        metrics["constitutional_hash"] = self.constitutional_hash
        return metrics

    async def health_check(self) -> JSONDict:
        """
        Check health of the decision store.

        Returns:
            Health status dictionary
        """
        health = {
            "healthy": True,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": datetime.now(UTC).isoformat(),
            "using_memory_fallback": self._use_memory_fallback,
        }

        if not self._use_memory_fallback and self._pool:
            pool_health = await self._pool.health_check()
            health["redis_healthy"] = pool_health.get("healthy", False)
            if not health["redis_healthy"]:
                health["redis_error"] = pool_health.get("error")

        return health

    async def close(self) -> None:
        """Close the decision store (does not close shared pool)."""
        self._initialized = False
        self._memory_store.clear()
        self._memory_indexes.clear()
        logger.info(f"[{CONSTITUTIONAL_HASH}] DecisionStore closed")


# Singleton instance
_decision_store: DecisionStore | None = None
_decision_store_lock = asyncio.Lock()


async def get_decision_store(
    redis_url: str = "redis://localhost:6379",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> DecisionStore:
    """
    Get or create shared DecisionStore singleton.

    Args:
        redis_url: Redis connection URL (only used for first call)
        ttl_seconds: TTL for decisions (only used for first call)

    Returns:
        Shared DecisionStore instance
    """
    global _decision_store

    if _decision_store is not None and _decision_store._initialized:
        return _decision_store

    async with _decision_store_lock:
        if _decision_store is None or not _decision_store._initialized:
            _decision_store = DecisionStore(
                redis_url=redis_url,
                ttl_seconds=ttl_seconds,
            )
            await _decision_store.initialize()

        return _decision_store


async def reset_decision_store() -> None:
    """Reset the decision store singleton (for testing)."""
    global _decision_store

    async with _decision_store_lock:
        if _decision_store is not None:
            await _decision_store.close()
            _decision_store = None


__all__ = [
    "DEFAULT_KEY_PREFIX",
    "DEFAULT_TTL_SECONDS",
    "DecisionStore",
    "get_decision_store",
    "reset_decision_store",
]
