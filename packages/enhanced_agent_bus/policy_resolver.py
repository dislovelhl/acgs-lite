"""
ACGS-2 Enhanced Agent Bus - Policy Resolver
Constitutional Hash: 608508a9bd224290

PolicyResolver for querying Policy Registry based on session context
with Redis caching for sub-millisecond performance.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Literal

import httpx

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import redis.asyncio as aioredis
    from redis.exceptions import (
        ConnectionError as RedisConnectionError,
    )
    from redis.exceptions import (
        RedisError,
    )
    from redis.exceptions import (
        TimeoutError as RedisTimeoutError,
    )

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

    class _RedisUnavailableError(Exception):
        """Fallback exception type when redis is not installed."""

    RedisError = _RedisUnavailableError
    RedisConnectionError = _RedisUnavailableError
    RedisTimeoutError = _RedisUnavailableError

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .models import RiskLevel, SessionGovernanceConfig

logger = get_logger(__name__)
DEFAULT_CACHE_HASH_MODE: Literal["sha256", "fast"] = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    fast_hash = None
    FAST_HASH_AVAILABLE = False


@functools.lru_cache(maxsize=512)
def _cached_policy_key_hash(key_str: str, cache_hash_mode: Literal["sha256", "fast"]) -> str:
    """Cache policy resolutions; cleared on policy update/invalidation."""
    # Keep cache keys short and stable for Redis + in-memory lookups.
    if cache_hash_mode == "fast" and FAST_HASH_AVAILABLE and fast_hash is not None:
        return f"policy:{fast_hash(key_str):016x}"
    return f"policy:{hashlib.sha256(key_str.encode()).hexdigest()[:16]}"


class PolicyResolutionResult:
    """Result of policy resolution with metadata and reasoning"""

    def __init__(
        self,
        policy: JSONDict | None,
        source: str,
        reasoning: str,
        risk_level: RiskLevel,
        tenant_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        resolution_metadata: JSONDict | None = None,
    ):
        self.policy = policy
        self.source = source  # 'session', 'tenant', 'global', 'none', 'cache'
        self.reasoning = reasoning
        self.risk_level = risk_level
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.session_id = session_id
        self.resolution_metadata = resolution_metadata or {}
        self.timestamp = datetime.now(UTC)
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization"""
        return {
            "policy": self.policy,
            "source": self.source,
            "reasoning": self.reasoning,
            "risk_level": (
                self.risk_level.value if isinstance(self.risk_level, RiskLevel) else self.risk_level
            ),
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "resolution_metadata": self.resolution_metadata,
            "timestamp": self.timestamp.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


class PolicyResolver:
    """
    Policy resolution service that queries Policy Registry based on session context.

    Implements high-performance policy resolution with:
    - Integration with PolicySelector service from Policy Registry
    - Two-tier caching: in-memory LRU + Redis for persistence
    - Sub-millisecond P99 latency for cached lookups
    - Cache invalidation on policy changes
    - Constitutional hash validation

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        policy_selector_url: str = "http://localhost:8003",
        redis_url: str | None = None,
        cache_ttl: int = 300,  # 5 minutes
        cache_size: int = 1000,
        enable_metrics: bool = True,
        isolated_mode: bool = False,
        cache_hash_mode: Literal["sha256", "fast"] = DEFAULT_CACHE_HASH_MODE,
    ):
        """
        Initialize PolicyResolver

        Args:
            policy_selector_url: URL of Policy Registry service
            redis_url: Redis connection URL (None for isolated mode)
            cache_ttl: Cache time-to-live in seconds (default: 300)
            cache_size: Maximum number of cached entries (default: 1000)
            enable_metrics: Enable metrics tracking (default: True)
            isolated_mode: Run without external dependencies (default: False)
            cache_hash_mode: Cache key hash mode ("sha256" default, "fast" optional)
        """
        self.policy_selector_url = policy_selector_url
        self.redis_url = redis_url
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self.enable_metrics = enable_metrics
        self.isolated_mode = isolated_mode
        if cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self.cache_hash_mode = cache_hash_mode

        # In-memory LRU cache for sub-millisecond lookups
        self._cache: OrderedDict[str, tuple[PolicyResolutionResult, float]] = OrderedDict()
        self._cache_lock = asyncio.Lock()

        # Lazy clients
        self._redis_client: aioredis.Redis | None = None
        self._http_client: httpx.AsyncClient | None = None

        # Metrics
        self._metrics = {
            "resolutions": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "redis_hits": 0,
            "redis_misses": 0,
            "policy_selector_calls": 0,
            "errors": 0,
            "cache_invalidations": 0,
        }
        self._metrics_lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task] = set()

        if self.cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] PolicyResolver initialized "
            f"(cache_ttl={cache_ttl}s, cache_size={cache_size}, isolated_mode={isolated_mode})"
        )

    async def _get_redis_client(self) -> aioredis.Redis | None:
        """Get or create Redis client (lazy initialization)"""
        if self.isolated_mode or not REDIS_AVAILABLE or not self.redis_url:
            return None

        if self._redis_client is None:
            try:
                self._redis_client = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                logger.info(f"[{CONSTITUTIONAL_HASH}] Redis client connected: {self.redis_url}")
            except (RedisConnectionError, RedisTimeoutError, RedisError, OSError, ValueError) as e:
                logger.warning(f"Failed to connect to Redis: {e}. Running in isolated mode.")
                self._redis_client = None

        return self._redis_client

    async def resolve_policy(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
        risk_level: RiskLevel | None = None,
        session_id: str | None = None,
        session_context: SessionGovernanceConfig | None = None,
        policy_name_filter: str | None = None,
        force_refresh: bool = False,
    ) -> PolicyResolutionResult:
        """
        Resolve the most appropriate policy based on session context.

        Implements three-tier resolution:
        1. In-memory LRU cache (sub-millisecond)
        2. Redis cache (few milliseconds)
        3. PolicySelector service (fallback)

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            risk_level: Risk level for filtering policies
            session_id: Session identifier
            session_context: Full session governance configuration
            policy_name_filter: Optional filter by policy name
            force_refresh: Force bypass cache and fetch fresh policy

        Returns:
            PolicyResolutionResult with selected policy and metadata

        Constitutional Hash: 608508a9bd224290
        """
        # Normalize parameters
        normalized_params = self._normalize_resolution_parameters(
            tenant_id, user_id, risk_level, session_id, session_context, policy_name_filter
        )
        tenant_id, user_id, risk_level, session_id, policy_name_filter = normalized_params

        # Initialize metrics and timing
        start_time = self._start_resolution_metrics()

        # Generate cache key
        cache_key = self._generate_cache_key(
            tenant_id, user_id, risk_level, session_id, policy_name_filter
        )

        # Try cache resolution first
        if not force_refresh:
            cached_result = await self._try_cache_resolution(cache_key, start_time)
            if cached_result:
                return cached_result

        # Fallback to service resolution
        return await self._resolve_from_service(
            tenant_id,
            user_id,
            risk_level,
            session_id,
            session_context,
            policy_name_filter,
            cache_key,
            start_time,
        )

    def _normalize_resolution_parameters(
        self,
        tenant_id: str | None,
        user_id: str | None,
        risk_level: RiskLevel | None,
        session_id: str | None,
        session_context: SessionGovernanceConfig | None,
        policy_name_filter: str | None,
    ) -> tuple[str | None, str | None, RiskLevel, str | None, str | None]:
        """Normalize and extract resolution parameters from session context."""
        # Extract values from session_context if provided
        if session_context:
            tenant_id = tenant_id or session_context.tenant_id
            user_id = user_id or session_context.user_id
            risk_level = risk_level or session_context.risk_level

        # Set default risk level if not provided
        if risk_level is None:
            risk_level = RiskLevel.MEDIUM

        return tenant_id, user_id, risk_level, session_id, policy_name_filter

    def _start_resolution_metrics(self) -> float:
        """Initialize resolution metrics and return start time."""
        if self.enable_metrics:
            task = asyncio.create_task(self._increment_metric("resolutions"))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        return time.perf_counter()

    async def _increment_metric(self, metric_name: str) -> None:
        """Safely increment a metric counter."""
        async with self._metrics_lock:
            self._metrics[metric_name] += 1

    async def _try_cache_resolution(
        self, cache_key: str, start_time: float
    ) -> PolicyResolutionResult | None:
        """Try to resolve policy from cache layers."""
        # Step 1: Check in-memory cache
        cached_result = await self._get_from_memory_cache(cache_key)
        if cached_result:
            await self._increment_metric("cache_hits")
            self._log_cache_hit("Memory", cache_key, start_time)
            return cached_result

        # Step 2: Check Redis cache
        if not self.isolated_mode:
            cached_result = await self._get_from_redis_cache(cache_key)
            if cached_result:
                # Also add to memory cache for faster subsequent lookups
                await self._add_to_memory_cache(cache_key, cached_result)
                await self._increment_metric("redis_hits")
                self._log_cache_hit("Redis", cache_key, start_time)
                return cached_result

        return None

    def _log_cache_hit(self, cache_type: str, cache_key: str, start_time: float) -> None:
        """Log cache hit with timing information."""
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"{cache_type} cache hit for policy resolution: {cache_key} ({elapsed_ms:.3f}ms)"
        )

    async def _resolve_from_service(
        self,
        tenant_id: str | None,
        user_id: str | None,
        risk_level: RiskLevel,
        session_id: str | None,
        session_context: SessionGovernanceConfig | None,
        policy_name_filter: str | None,
        cache_key: str,
        start_time: float,
    ) -> PolicyResolutionResult:
        """Resolve policy from PolicySelector service with error handling."""
        # Track cache miss
        await self._increment_metric("cache_misses")

        try:
            result = await self._query_policy_selector(
                tenant_id, user_id, risk_level, session_id, session_context, policy_name_filter
            )

            # Store in both caches
            await self._add_to_memory_cache(cache_key, result)
            await self._add_to_redis_cache(cache_key, result)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"Policy resolved via PolicySelector: {result.source} "
                f"(tenant={tenant_id}, risk={risk_level.value}, {elapsed_ms:.3f}ms)"
            )

            return result

        except (
            httpx.HTTPError,
            json.JSONDecodeError,
            KeyError,
            OSError,
            RuntimeError,
            ValueError,
        ) as e:
            await self._increment_metric("errors")
            logger.error(f"Error resolving policy: {e}", exc_info=True)

            # Return empty result on error
            return PolicyResolutionResult(
                policy=None,
                source="none",
                reasoning=f"Error resolving policy: {e!s}",
                risk_level=risk_level,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                resolution_metadata={"error": str(e)},
            )

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http_client

    async def _query_policy_selector(
        self,
        tenant_id: str | None,
        user_id: str | None,
        risk_level: RiskLevel,
        session_id: str | None,
        session_context: SessionGovernanceConfig | None,
        policy_name_filter: str | None,
    ) -> PolicyResolutionResult:
        """
        Query PolicySelector service from Policy Registry via HTTP.
        """
        if self.enable_metrics:
            async with self._metrics_lock:
                self._metrics["policy_selector_calls"] += 1

        if self.isolated_mode:
            logger.info("Isolated mode: returning default policy")
            return self._get_default_mock_policy(
                tenant_id, user_id, risk_level, session_id, session_context, policy_name_filter
            )

        try:
            client = await self._get_http_client()

            payload = {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "risk_level": risk_level.value if isinstance(risk_level, RiskLevel) else risk_level,
                "session_id": session_id,
                "policy_name_filter": policy_name_filter,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

            response = await client.post(
                f"{self.policy_selector_url}/v1/policies/resolve", json=payload
            )

            if response.status_code == 200:
                data = response.json()
                return PolicyResolutionResult(
                    policy=data.get("policy"),
                    source=data.get("source", "service"),
                    reasoning=data.get("reasoning", "Resolved via PolicySelector service"),
                    risk_level=risk_level,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id,
                    resolution_metadata=data.get("metadata", {}),
                )
            else:
                logger.warning(
                    f"PolicySelector returned status {response.status_code}: {response.text}"
                )
                return self._get_default_mock_policy(
                    tenant_id, user_id, risk_level, session_id, session_context, policy_name_filter
                )

        except (httpx.HTTPError, json.JSONDecodeError, KeyError, OSError, ValueError) as e:
            logger.error(f"Failed to query PolicySelector: {e}")
            return self._get_default_mock_policy(
                tenant_id, user_id, risk_level, session_id, session_context, policy_name_filter
            )

    def _get_default_mock_policy(
        self, tenant_id, user_id, risk_level, session_id, session_context, policy_name_filter
    ) -> PolicyResolutionResult:
        """Fallback mock policy result."""
        policy = {
            "policy_id": f"policy-{tenant_id or 'global'}-{risk_level.value if hasattr(risk_level, 'value') else risk_level}",
            "name": f"Fallback Policy for {tenant_id or 'global'}",
            "tenant_id": tenant_id,
            "risk_level": risk_level.value if hasattr(risk_level, "value") else risk_level,
            "rules": {"max_retries": 3, "timeout_ms": 5000},
            "status": "active",
        }

        if session_context and session_context.policy_overrides:
            source = "session"
            reasoning = "Session-specific policy override (Fallback)"
        elif tenant_id:
            source = "tenant"
            reasoning = f"Tenant-specific fallback policy for {tenant_id}"
        else:
            source = "global"
            reasoning = "Global fallback policy"

        metadata = {
            "fallback": True,
            "policy_selector_url": self.policy_selector_url,
        }
        if policy_name_filter:
            metadata["policy_name_filter"] = policy_name_filter

        return PolicyResolutionResult(
            policy=policy,
            source=source,
            reasoning=reasoning,
            risk_level=risk_level,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            resolution_metadata=metadata,
        )

    def _generate_cache_key(
        self,
        tenant_id: str | None,
        user_id: str | None,
        risk_level: RiskLevel,
        session_id: str | None,
        policy_name_filter: str | None,
    ) -> str:
        """Generate cache key from resolution parameters"""
        key_parts = [
            "policy",
            tenant_id or "global",
            user_id or "anonymous",
            risk_level.value if isinstance(risk_level, RiskLevel) else risk_level,
            session_id or "no-session",
            policy_name_filter or "any",
        ]
        key_str = ":".join(key_parts)
        return _cached_policy_key_hash(key_str, self.cache_hash_mode)

    async def _get_from_memory_cache(self, cache_key: str) -> PolicyResolutionResult | None:
        """Get result from in-memory cache if not expired"""
        async with self._cache_lock:
            if cache_key not in self._cache:
                return None

            result, timestamp = self._cache[cache_key]
            current_time = time.time()

            # Check if expired
            if current_time - timestamp > self.cache_ttl:
                del self._cache[cache_key]
                return None

            # Move to end (LRU)
            self._cache.move_to_end(cache_key)
            return result

    async def _add_to_memory_cache(self, cache_key: str, result: PolicyResolutionResult) -> None:
        """Add result to in-memory cache with LRU eviction"""
        async with self._cache_lock:
            current_time = time.time()

            # Evict oldest if at capacity
            if len(self._cache) >= self.cache_size:
                self._cache.popitem(last=False)  # Remove oldest (FIFO)

            self._cache[cache_key] = (result, current_time)

    async def _get_from_redis_cache(self, cache_key: str) -> PolicyResolutionResult | None:
        """Get result from Redis cache if not expired"""
        redis_client = await self._get_redis_client()
        if not redis_client:
            return None

        try:
            data = await redis_client.get(cache_key)
            if not data:
                if self.enable_metrics:
                    async with self._metrics_lock:
                        self._metrics["redis_misses"] += 1
                return None

            # Deserialize
            result_dict = json.loads(data)

            # Reconstruct PolicyResolutionResult
            risk_level_str = result_dict.get("risk_level", "medium")
            risk_level = RiskLevel(risk_level_str)

            result = PolicyResolutionResult(
                policy=result_dict.get("policy"),
                source=result_dict.get("source", "cache"),
                reasoning=result_dict.get("reasoning", "From Redis cache"),
                risk_level=risk_level,
                tenant_id=result_dict.get("tenant_id"),
                user_id=result_dict.get("user_id"),
                session_id=result_dict.get("session_id"),
                resolution_metadata=result_dict.get("resolution_metadata", {}),
            )

            return result

        except (
            RedisConnectionError,
            RedisTimeoutError,
            RedisError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as e:
            logger.warning(f"Error reading from Redis cache: {e}")
            if self.enable_metrics:
                async with self._metrics_lock:
                    self._metrics["redis_misses"] += 1
            return None

    async def _add_to_redis_cache(self, cache_key: str, result: PolicyResolutionResult) -> None:
        """Add result to Redis cache with TTL"""
        redis_client = await self._get_redis_client()
        if not redis_client:
            return

        try:
            # Serialize result
            data = json.dumps(result.to_dict())
            await redis_client.setex(cache_key, self.cache_ttl, data)

        except (
            RedisConnectionError,
            RedisTimeoutError,
            RedisError,
            TypeError,
            ValueError,
        ) as e:
            logger.warning(f"Error writing to Redis cache: {e}")

    async def invalidate_cache(
        self,
        tenant_id: str | None = None,
        session_id: str | None = None,
        clear_all: bool = False,
    ) -> int:
        """
        Invalidate cache entries.

        Args:
            tenant_id: Invalidate all entries for this tenant
            session_id: Invalidate all entries for this session
            clear_all: Clear entire cache

        Returns:
            Number of entries invalidated
        """
        if self.enable_metrics:
            async with self._metrics_lock:
                self._metrics["cache_invalidations"] += 1

        # Cache policy resolutions; cleared on policy update.
        _cached_policy_key_hash.cache_clear()

        # Invalidate memory cache
        memory_count = await self._invalidate_memory_cache(tenant_id, session_id, clear_all)

        # Invalidate Redis cache
        redis_count = await self._invalidate_redis_cache(tenant_id, session_id, clear_all)

        return memory_count + redis_count

    async def _invalidate_memory_cache(
        self, tenant_id: str | None, session_id: str | None, clear_all: bool
    ) -> int:
        """Invalidate entries from in-memory cache."""
        invalidated_count = 0

        async with self._cache_lock:
            if clear_all:
                count = len(self._cache)
                self._cache.clear()
                invalidated_count += count
                logger.info(f"Cleared all {count} entries from memory cache")
            else:
                keys_to_remove = self._find_memory_cache_keys_to_remove(tenant_id, session_id)

                for key in keys_to_remove:
                    del self._cache[key]
                    invalidated_count += 1

                logger.info(
                    f"Invalidated {len(keys_to_remove)} entries from memory cache "
                    f"(tenant={tenant_id}, session={session_id})"
                )

        return invalidated_count

    def _find_memory_cache_keys_to_remove(
        self, tenant_id: str | None, session_id: str | None
    ) -> list[str]:
        """Find cache keys that match the invalidation criteria."""
        keys_to_remove = []
        for cache_key, (result, _) in self._cache.items():
            if tenant_id and result.tenant_id == tenant_id:
                keys_to_remove.append(cache_key)
            elif session_id and result.session_id == session_id:
                keys_to_remove.append(cache_key)
        return keys_to_remove

    async def _invalidate_redis_cache(
        self, tenant_id: str | None, session_id: str | None, clear_all: bool
    ) -> int:
        """Invalidate entries from Redis cache."""
        redis_client = await self._get_redis_client()
        if not redis_client:
            return 0

        invalidated_count = 0

        try:
            if clear_all:
                invalidated_count = await self._clear_all_redis_cache(redis_client)
            else:
                await self._warn_targeted_redis_invalidation(tenant_id, session_id)

        except (
            RedisConnectionError,
            RedisTimeoutError,
            RedisError,
            OSError,
            RuntimeError,
        ) as e:
            logger.warning(f"Error clearing Redis cache: {e}")

        return invalidated_count

    async def _clear_all_redis_cache(self, redis_client: aioredis.Redis) -> int:
        """Clear all policy keys from Redis cache."""
        invalidated_count = 0
        pattern = "policy:*"
        cursor = 0
        max_scan_iterations = 10_000

        for _ in range(max_scan_iterations):
            cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                await redis_client.delete(*keys)
                invalidated_count += len(keys)
            if cursor == 0:
                break

        logger.info("Cleared policy cache from Redis")
        return invalidated_count

    async def _warn_targeted_redis_invalidation(
        self, tenant_id: str | None, session_id: str | None
    ) -> None:
        """Log warning about targeted Redis invalidation limitations."""
        logger.warning(
            "Targeted Redis cache invalidation not yet implemented. "
            "Use clear_all=True to clear entire Redis cache."
        )

    def get_metrics(self) -> JSONDict:
        """Get policy resolution metrics"""
        total_requests = self._metrics["cache_hits"] + self._metrics["cache_misses"]
        cache_hit_rate = self._metrics["cache_hits"] / total_requests if total_requests > 0 else 0.0

        redis_requests = self._metrics["redis_hits"] + self._metrics["redis_misses"]
        redis_hit_rate = self._metrics["redis_hits"] / redis_requests if redis_requests > 0 else 0.0

        return {
            **self._metrics,
            "cache_hit_rate": cache_hit_rate,
            "redis_hit_rate": redis_hit_rate,
            "memory_cache_size": len(self._cache),
            "memory_cache_capacity": self.cache_size,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def reset_metrics(self) -> None:
        """Reset all metrics counters"""
        for key in self._metrics:
            self._metrics[key] = 0
        logger.info("Policy resolver metrics reset")

    async def close(self) -> None:
        """Close connections and cleanup resources"""
        if self._http_client:
            try:
                await self._http_client.aclose()
                logger.info("HTTP client closed")
            except (httpx.HTTPError, OSError, RuntimeError) as e:
                logger.warning(f"Error closing HTTP client: {e}")

        if self._redis_client:
            try:
                await self._redis_client.close()
                logger.info("Redis client closed")
            except (
                RedisConnectionError,
                RedisTimeoutError,
                RedisError,
                OSError,
                RuntimeError,
            ) as e:
                logger.warning(f"Error closing Redis client: {e}")
