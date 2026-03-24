"""
ACGS-2 Tiered Cache Manager Implementation
Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import contextlib
import json
import random
import threading
import time
from typing import cast

from src.core.shared.cache.metrics import (
    record_cache_hit,
    record_cache_latency,
    record_cache_miss,
    record_fallback,
    record_promotion,
    set_tier_health,
    update_cache_size,
)
from src.core.shared.metrics import _get_or_create_counter, _get_or_create_gauge
from src.core.shared.redis_config import (
    CONSTITUTIONAL_HASH,
    RedisConfig,
    RedisHealthState,
    get_redis_config,
)
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict, JSONValue

from .l1 import L1Cache
from .models import AccessRecord, CacheTier, T, TieredCacheConfig, TieredCacheStats

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

logger = get_logger(__name__)
# Redis failure counter
TIERED_CACHE_REDIS_FAILURES = _get_or_create_counter(
    "tiered_cache_redis_failures_total",
    "Total Redis failures in tiered cache",
    ["cache_name"],
)

# Degraded mode gauge (1 = degraded, 0 = normal)
TIERED_CACHE_DEGRADED = _get_or_create_gauge(
    "tiered_cache_degraded",
    "Whether tiered cache is running in degraded mode (1=degraded, 0=normal)",
    ["cache_name"],
)


class TieredCacheManager:
    """
    Multi-tier cache manager coordinating L1, L2, and L3 caches.
    """

    def __init__(
        self,
        config: TieredCacheConfig | None = None,
        name: str = "default",
    ):
        self.config = config or TieredCacheConfig()
        self.name = name

        if self.config.l1_ttl > self.config.l2_ttl:
            self.config.l1_ttl = self.config.l2_ttl
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] L1 TTL adjusted to {self.config.l1_ttl}s "
                f"to not exceed L2 TTL"
            )

        self._l1_cache = L1Cache(
            maxsize=self.config.l1_maxsize,
            ttl=self.config.l1_ttl,
            serialize=self.config.serialize,
        )

        self._l2_client: object | None = None
        self._redis_config: RedisConfig = get_redis_config()
        self._l3_cache: dict[str, JSONDict] = {}
        self._l3_lock = threading.Lock()
        self._l3_lock_async: asyncio.Lock | None = None  # Lazy-initialized for async methods
        self._access_records: dict[str, AccessRecord] = {}
        # Use RLock for re-entrant locking (needed because _check_and_promote
        # calls _set_in_l1 which calls _update_tier while already holding the lock)
        self._access_lock = threading.RLock()
        self._stats = TieredCacheStats()
        self._stats_lock = threading.Lock()
        self._l2_degraded = False
        self._last_l2_failure: float = 0.0
        self._l2_recovery_interval: float = 30.0

        self._redis_config.register_health_callback(self._on_redis_health_change)
        set_tier_health("L1", True)
        if self.config.l3_enabled:
            set_tier_health("L3", True)

        logger.info(f"[{CONSTITUTIONAL_HASH}] TieredCacheManager '{name}' initialized")

    async def initialize(self) -> bool:
        """Initialize the L2 Redis tier; return True if Redis is reachable."""
        l2_ready = await self._initialize_l2()
        if not l2_ready:
            self._l2_degraded = True
            set_tier_health("L2", False)
            TIERED_CACHE_DEGRADED.labels(cache_name=self.name).set(1)
        else:
            set_tier_health("L2", True)
            TIERED_CACHE_DEGRADED.labels(cache_name=self.name).set(0)
        return l2_ready

    async def _initialize_l2(self) -> bool:
        if aioredis is None:
            return False
        try:
            redis_url = self.config.redis_url or RedisConfig.get_url()
            self._l2_client = aioredis.from_url(redis_url, decode_responses=True)
            await self._l2_client.ping()
            return True
        except (RuntimeError, ConnectionError, OSError):
            self._l2_client = None
            return False

    async def close(self) -> None:
        """Close the Redis connection and release resources."""
        if self._l2_client:
            with contextlib.suppress(RuntimeError, ConnectionError, OSError):
                await self._l2_client.close()
            self._l2_client = None

    def _on_redis_health_change(self, old_state, new_state) -> None:
        if new_state == RedisHealthState.UNHEALTHY:
            self._l2_degraded = True
            self._last_l2_failure = time.time()
            TIERED_CACHE_DEGRADED.labels(cache_name=self.name).set(1)
            set_tier_health("L2", False)
            record_fallback("L2", "L3", self.name)
        elif new_state == RedisHealthState.HEALTHY and self._l2_degraded:
            self._l2_degraded = False
            TIERED_CACHE_DEGRADED.labels(cache_name=self.name).set(0)
            set_tier_health("L2", True)

    def get(self, key: str, default: T | None = None) -> T | None:
        """Return a cached value from L1 or L3, or default if not found."""
        self._record_access(key)
        value = self._get_from_l1(key)
        if value is not None:
            self._check_and_promote(key, value)
            return cast(T, value)
        value = self._get_from_l3(key)
        if value is not None:
            self._check_and_promote(key, value)
            return cast(T, value)
        self._check_and_promote_tier_only(key)
        return default

    async def get_async(self, key: str, default: JSONValue | None = None) -> JSONValue | None:
        """Return a cached value from L1, L2 (Redis), or L3, or default if not found."""
        self._record_access(key)
        value = self._get_from_l1(key)
        if value is not None:
            self._check_and_promote(key, value)
            return value
        value = await self._get_from_l2(key)
        if value is not None:
            self._check_and_promote(key, value)
            return value
        value = self._get_from_l3(key)
        if value is not None:
            self._check_and_promote(key, value)
            return value
        self._check_and_promote_tier_only(key)
        return default

    async def set(
        self,
        key: str,
        value: JSONValue,
        ttl: int | None = None,
        tier: CacheTier | None = None,
    ) -> None:
        """Store a value in the specified cache tier, or L2/L1 by default."""
        self._record_access(key)
        serialized = self._serialize(value)
        if tier == CacheTier.L1:
            self._set_in_l1(key, serialized)
        elif tier == CacheTier.L2:
            await self._set_in_l2(key, serialized, ttl)
        elif tier == CacheTier.L3:
            self._set_in_l3(key, serialized, ttl)
        else:
            await self._set_in_l2(key, serialized, ttl)
            if self._should_promote_to_l1(key):
                self._set_in_l1(key, serialized)
                self._update_tier(key, CacheTier.L1)

    async def delete(self, key: str) -> bool:
        """Delete a key from all cache tiers; return True if found in any tier."""
        # Lazy initialize async lock
        if self._l3_lock_async is None:
            self._l3_lock_async = asyncio.Lock()

        deleted = False
        if self._l1_cache.delete(key):
            deleted = True
        if self._l2_client and not self._l2_degraded:
            try:
                if await self._l2_client.delete(key):
                    deleted = True
            except (RuntimeError, ConnectionError, OSError):
                self._handle_l2_failure()
        async with self._l3_lock_async:
            if key in self._l3_cache:
                del self._l3_cache[key]
                deleted = True
        with self._access_lock:
            self._access_records.pop(key, None)
        return deleted

    async def exists(self, key: str) -> bool:
        """Return True if the key exists in any cache tier."""
        # Lazy initialize async lock
        if self._l3_lock_async is None:
            self._l3_lock_async = asyncio.Lock()

        if self._l1_cache.exists(key):
            return True
        if self._l2_client and not self._l2_degraded:
            try:
                if await self._l2_client.exists(key):
                    return True
            except (RuntimeError, ConnectionError, OSError):
                self._handle_l2_failure()
        async with self._l3_lock_async:
            if key in self._l3_cache:
                if time.time() - self._l3_cache[key].get("timestamp", 0) < self.config.l3_ttl:
                    return True
        return False

    def _handle_l2_failure(self):
        with self._stats_lock:
            self._stats.redis_failures += 1
        TIERED_CACHE_REDIS_FAILURES.labels(cache_name=self.name).inc()
        self._l2_degraded = True
        self._last_l2_failure = time.time()
        TIERED_CACHE_DEGRADED.labels(cache_name=self.name).set(1)
        set_tier_health("L2", False)
        record_fallback("L2", "L3", self.name)

    def _record_access(self, key: str) -> None:
        with self._access_lock:
            if key not in self._access_records:
                self._access_records[key] = AccessRecord(key=key)
            self._access_records[key].record_access()
            # Periodic cleanup with low probability
            # Low-probability maintenance sampling; security properties are not required here.
            if random.random() < 0.01:
                self._cleanup_old_records()

    def _cleanup_old_records(self) -> None:
        """Clean up old access records and L3 cache entries."""
        now = time.time()
        ttl_seconds = 3600  # 1 hour TTL
        with self._access_lock:
            expired_keys = [
                k for k, r in self._access_records.items() if now - r.last_access > ttl_seconds
            ]
            for k in expired_keys:
                del self._access_records[k]
        with self._l3_lock:
            expired_l3 = [
                k for k, v in self._l3_cache.items() if now - v.get("timestamp", 0) > ttl_seconds
            ]
            for k in expired_l3:
                del self._l3_cache[k]

    def _get_from_l1(self, key: str) -> JSONValue | None:
        start = time.perf_counter()
        value = self._l1_cache.get(key)
        record_cache_latency("L1", self.name, "get", time.perf_counter() - start)
        with self._stats_lock:
            if value is not None:
                self._stats.l1_hits += 1
                self._update_tier(key, CacheTier.L1)
                record_cache_hit("L1", self.name, "get")
            else:
                self._stats.l1_misses += 1
                record_cache_miss("L1", self.name, "get")
        update_cache_size("L1", self.name, 0, self._l1_cache.size)
        return self._deserialize(value) if value is not None else None

    async def _get_from_l2(self, key: str) -> object | None:
        if not self._l2_client:
            return None
        if self._l2_degraded:
            if time.time() - self._last_l2_failure >= self._l2_recovery_interval:
                await self._initialize_l2()  # Simplification for brevity
            if self._l2_degraded:
                return None
        start = time.perf_counter()
        try:
            cached_json = await self._l2_client.get(key)
            record_cache_latency("L2", self.name, "get", time.perf_counter() - start)
            if cached_json:
                with self._stats_lock:
                    self._stats.l2_hits += 1
                self._update_tier(key, CacheTier.L2)
                record_cache_hit("L2", self.name, "get")
                return json.loads(cached_json).get("data")
            with self._stats_lock:
                self._stats.l2_misses += 1
            record_cache_miss("L2", self.name, "get")
        except (RuntimeError, ConnectionError, OSError):
            self._handle_l2_failure()
        return None

    def _get_from_l3(self, key: str) -> object | None:
        if not self.config.l3_enabled:
            return None
        start = time.perf_counter()
        with self._l3_lock:
            if key in self._l3_cache:
                cached = self._l3_cache[key]
                if time.time() - cached.get("timestamp", 0) < self.config.l3_ttl:
                    record_cache_latency("L3", self.name, "get", time.perf_counter() - start)
                    with self._stats_lock:
                        self._stats.l3_hits += 1
                    self._update_tier(key, CacheTier.L3)
                    record_cache_hit("L3", self.name, "get")
                    return cached.get("data")
                del self._l3_cache[key]
            record_cache_latency("L3", self.name, "get", time.perf_counter() - start)
            with self._stats_lock:
                self._stats.l3_misses += 1
            record_cache_miss("L3", self.name, "get")
        return None

    def _set_in_l1(self, key: str, value: JSONValue) -> None:
        start = time.perf_counter()
        self._l1_cache.set(key, value)
        record_cache_latency("L1", self.name, "set", time.perf_counter() - start)
        update_cache_size("L1", self.name, 0, self._l1_cache.size)
        self._update_tier(key, CacheTier.L1)

    async def _set_in_l2(self, key: str, value: JSONValue, ttl: int | None = None) -> None:
        if not self._l2_client or self._l2_degraded:
            self._set_in_l3(key, value, ttl)
            return
        start = time.perf_counter()
        try:
            await self._l2_client.setex(
                key,
                ttl or self.config.l2_ttl,
                json.dumps({"data": value, "timestamp": time.time()}),
            )
            record_cache_latency("L2", self.name, "set", time.perf_counter() - start)
            self._update_tier(key, CacheTier.L2)
        except (RuntimeError, ConnectionError, OSError):
            self._handle_l2_failure()
            self._set_in_l3(key, value, ttl)

    def _set_in_l3(self, key: str, value: JSONValue, ttl: int | None = None) -> None:
        if not self.config.l3_enabled:
            return
        start = time.perf_counter()
        with self._l3_lock:
            self._l3_cache[key] = {
                "data": value,
                "timestamp": time.time(),
                "ttl": ttl or self.config.l3_ttl,
            }
            l3_size = len(self._l3_cache)
        record_cache_latency("L3", self.name, "set", time.perf_counter() - start)
        update_cache_size("L3", self.name, 0, l3_size)
        self._update_tier(key, CacheTier.L3)

    def _should_promote_to_l1(self, key: str) -> bool:
        with self._access_lock:
            record = self._access_records.get(key)
            return (
                record.accesses_per_minute >= self.config.promotion_threshold if record else False
            )

    def _check_and_promote(self, key: str, value: JSONValue) -> None:
        with self._access_lock:
            record = self._access_records.get(key)
            if (
                record
                and record.accesses_per_minute >= self.config.promotion_threshold
                and record.current_tier != CacheTier.L1
            ):
                from_tier = record.current_tier.value
                self._set_in_l1(key, self._serialize(value))
                record.current_tier = CacheTier.L1
                with self._stats_lock:
                    self._stats.promotions += 1
                record_promotion(from_tier, "L1", self.name)

    def _check_and_promote_tier_only(self, key: str) -> None:
        with self._access_lock:
            record = self._access_records.get(key)
            if (
                record
                and record.accesses_per_minute >= self.config.promotion_threshold
                and record.current_tier != CacheTier.L1
            ):
                from_tier = record.current_tier.value
                record.current_tier = CacheTier.L1
                with self._stats_lock:
                    self._stats.promotions += 1
                record_promotion(from_tier, "L1", self.name)

    def _update_tier(self, key: str, tier: CacheTier) -> None:
        with self._access_lock:
            if key in self._access_records:
                self._access_records[key].current_tier = tier
            else:
                self._access_records[key] = AccessRecord(key=key, current_tier=tier)

    def _serialize(self, value: JSONValue) -> JSONValue:
        """Serialize a value for cache storage.

        Args:
            value: Value to serialize (JSONValue)

        Returns:
            Serialized value as string or original value
        """
        if self.config.serialize and not isinstance(value, str):
            try:
                return json.dumps(value)
            except (TypeError, ValueError):
                return value
        return value

    def _deserialize(self, value: JSONValue) -> JSONValue:
        """Deserialize a value from cache storage.

        Args:
            value: Value to deserialize (typically string from cache)

        Returns:
            Deserialized value or original value
        """
        if self.config.serialize and isinstance(value, str):
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return value
        return value

    def get_stats(self) -> JSONDict:
        """Return a snapshot of cache hit/miss statistics for all tiers."""
        with self._stats_lock:
            return {
                "name": self.name,
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "tiers": {
                    "l1": {
                        "hits": self._stats.l1_hits,
                        "misses": self._stats.l1_misses,
                        "size": self._l1_cache.size,
                    },
                    "l2": {
                        "hits": self._stats.l2_hits,
                        "misses": self._stats.l2_misses,
                        "available": self._l2_client is not None,
                    },
                    "l3": {
                        "hits": self._stats.l3_hits,
                        "misses": self._stats.l3_misses,
                        "size": len(self._l3_cache),
                    },
                },
                "aggregate": {
                    "total_hits": self._stats.total_hits,
                    "total_misses": self._stats.total_misses,
                    "hit_ratio": self._stats.hit_ratio,
                },
            }
