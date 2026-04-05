"""
ACGS-2 Production-Ready Redis Rate Limiter
Constitutional Hash: 608508a9bd224290

Distributed rate limiter using Redis with sliding window algorithm.
Includes automatic fallback to in-memory limiting when Redis is unavailable.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
REDIS_CONNECTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    ConnectionError,
    OSError,
    Exception,
)
REDIS_CLOSE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    ConnectionError,
    OSError,
)
REDIS_RATE_CHECK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
    Exception,
)
REDIS_COUNT_QUERY_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
    Exception,
)
REDIS_RESET_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
    Exception,
)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    current_count: int
    limit: int
    window_seconds: int
    remaining: int
    retry_after_seconds: float | None = None
    using_fallback: bool = False


@dataclass
class InMemoryWindow:
    """In-memory sliding window data structure."""

    timestamps: list[float] = field(default_factory=list)

    def add_request(self, now: float, window_seconds: int) -> int:
        """Add a request and return current count within window."""
        window_start = now - window_seconds
        # Remove expired entries
        self.timestamps = [ts for ts in self.timestamps if ts > window_start]
        # Add current request
        self.timestamps.append(now)
        return len(self.timestamps)


class InMemoryRateLimiter:
    """Fallback in-memory rate limiter for single-instance deployments.

    WARNING: This does not provide distributed rate limiting.
    Only use as a fallback when Redis is unavailable.
    """

    def __init__(self) -> None:
        self._windows: dict[str, InMemoryWindow] = defaultdict(InMemoryWindow)
        self._cleanup_interval = 60.0  # seconds
        self._last_cleanup = time.monotonic()

    def _maybe_cleanup(self) -> None:
        """Periodically clean up expired windows to prevent memory leaks."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        # Find windows with no recent activity
        expired_keys = []
        for key, window in self._windows.items():
            if not window.timestamps:
                expired_keys.append(key)
            elif window.timestamps[-1] < now - 3600:  # 1 hour stale
                expired_keys.append(key)

        for key in expired_keys:
            del self._windows[key]

        self._last_cleanup = now

    async def is_allowed(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """Check if request is within rate limit."""
        self._maybe_cleanup()
        now = time.monotonic()
        count = self._windows[key].add_request(now, window_seconds)
        allowed = count <= limit

        retry_after = None
        if not allowed and self._windows[key].timestamps:
            oldest_in_window = min(self._windows[key].timestamps)
            retry_after = oldest_in_window + window_seconds - now

        return RateLimitResult(
            allowed=allowed,
            current_count=count,
            limit=limit,
            window_seconds=window_seconds,
            remaining=max(0, limit - count),
            retry_after_seconds=retry_after if not allowed else None,
            using_fallback=True,
        )


class RedisRateLimiter:
    """Distributed rate limiter using Redis sliding window algorithm.

    Uses sorted sets (ZSET) for efficient sliding window implementation:
    - Each request is stored with its timestamp as both member and score
    - Expired entries are removed on each check
    - Atomic operations via pipeline ensure consistency

    Falls back to in-memory limiting if Redis connection fails.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "acgs:ratelimit:",
        fallback_enabled: bool = True,
    ) -> None:
        self._redis: object | None = None
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._fallback_enabled = fallback_enabled
        self._fallback_limiter: InMemoryRateLimiter | None = None
        self._connected = False
        self._fallback_active = False

    @property
    def is_connected(self) -> bool:
        """Check if Redis connection is active."""
        return self._connected and self._redis is not None

    @property
    def using_fallback(self) -> bool:
        """Check if currently using fallback in-memory limiter."""
        return self._fallback_active

    async def connect(self) -> None:
        """Establish connection to Redis."""
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Verify connection
            await self._redis.ping()
            self._connected = True
            self._fallback_active = False
            logger.info("Redis rate limiter connected successfully")
        except ImportError:
            logger.warning("redis.asyncio not installed. Install with: pip install redis[hiredis]")
            self._activate_fallback("redis package not installed")
        except REDIS_CONNECTION_ERRORS as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            self._activate_fallback(str(e))

    def _activate_fallback(self, reason: str) -> None:
        """Activate the in-memory fallback limiter."""
        if not self._fallback_enabled:
            raise RuntimeError(f"Redis unavailable and fallback disabled: {reason}")

        if self._fallback_limiter is None:
            self._fallback_limiter = InMemoryRateLimiter()

        self._fallback_active = True
        self._connected = False
        logger.warning(
            f"Rate limiter falling back to in-memory mode: {reason}. "
            "WARNING: Rate limits will not be distributed across instances!"
        )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except REDIS_CLOSE_ERRORS as e:
                logger.debug(f"Error closing Redis connection: {e}")
            finally:
                self._redis = None
                self._connected = False

    def _make_key(self, key: str) -> str:
        """Create a namespaced Redis key."""
        return f"{self._key_prefix}{key}"

    async def is_allowed(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """Check if request is within rate limit using sliding window.

        Args:
            key: Unique identifier for the rate limit bucket (e.g., user_id, ip)
            limit: Maximum number of requests allowed in the window
            window_seconds: Size of the sliding window in seconds

        Returns:
            RateLimitResult with allowed status and metadata
        """
        # Use fallback if active
        if self._fallback_active and self._fallback_limiter:
            return await self._fallback_limiter.is_allowed(key, limit, window_seconds)

        if not self._connected or self._redis is None:
            if self._fallback_enabled:
                self._activate_fallback("not connected")
                return await self._fallback_limiter.is_allowed(key, limit, window_seconds)
            raise RuntimeError("Redis rate limiter not connected")

        redis_key = self._make_key(key)
        now = time.time()
        window_start = now - window_seconds

        try:
            # Use pipeline for atomic operations
            pipe = self._redis.pipeline()

            # Remove entries outside the window
            pipe.zremrangebyscore(redis_key, 0, window_start)

            # Add current request with timestamp as both member and score
            # Using precise timestamp as member ensures uniqueness
            member = f"{now}:{id(asyncio.current_task())}"
            pipe.zadd(redis_key, {member: now})

            # Get count of entries in window
            pipe.zcard(redis_key)

            # Set expiry to auto-cleanup old keys
            pipe.expire(redis_key, window_seconds + 1)

            results = await pipe.execute()
            count = results[2]
            allowed = count <= limit

            # Calculate retry-after if rate limited
            retry_after = None
            if not allowed:
                # Get oldest entry to determine when it will expire
                oldest = await self._redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    oldest_score = oldest[0][1]
                    retry_after = (oldest_score + window_seconds) - now

            return RateLimitResult(
                allowed=allowed,
                current_count=count,
                limit=limit,
                window_seconds=window_seconds,
                remaining=max(0, limit - count),
                retry_after_seconds=max(0, retry_after) if retry_after else None,
                using_fallback=False,
            )

        except REDIS_RATE_CHECK_ERRORS as e:
            logger.error(f"Redis rate limit check failed: {e}")
            if self._fallback_enabled:
                self._activate_fallback(str(e))
                return await self._fallback_limiter.is_allowed(key, limit, window_seconds)
            raise

    async def get_current_count(self, key: str, window_seconds: int) -> int:
        """Get current request count for a key without incrementing.

        Args:
            key: Rate limit bucket identifier
            window_seconds: Size of the sliding window

        Returns:
            Current count of requests in the window
        """
        if self._fallback_active and self._fallback_limiter:
            window = self._fallback_limiter._windows.get(key)
            if window:
                now = time.monotonic()
                window_start = now - window_seconds
                return len([ts for ts in window.timestamps if ts > window_start])
            return 0

        if not self._connected or self._redis is None:
            return 0

        redis_key = self._make_key(key)
        now = time.time()
        window_start = now - window_seconds

        try:
            # Clean up and count in one pipeline
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            results = await pipe.execute()
            return results[1]  # type: ignore[no-any-return]
        except REDIS_COUNT_QUERY_ERRORS as e:
            logger.error(f"Failed to get rate limit count: {e}")
            return 0

    async def reset(self, key: str) -> bool:
        """Reset the rate limit counter for a key.

        Args:
            key: Rate limit bucket identifier

        Returns:
            True if reset successful
        """
        if self._fallback_active and self._fallback_limiter:
            if key in self._fallback_limiter._windows:
                del self._fallback_limiter._windows[key]
            return True

        if not self._connected or self._redis is None:
            return False

        redis_key = self._make_key(key)
        try:
            await self._redis.delete(redis_key)
            return True
        except REDIS_RESET_ERRORS as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False


class MultiTierRateLimiter:
    """Rate limiter supporting multiple tiers with different limits.

    Useful for implementing tiered rate limiting (e.g., per-second, per-minute,
    per-hour limits that all must pass).
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "acgs:ratelimit:",
        fallback_enabled: bool = True,
    ) -> None:
        self._limiter = RedisRateLimiter(
            redis_url=redis_url,
            key_prefix=key_prefix,
            fallback_enabled=fallback_enabled,
        )
        self._tiers: dict[str, list[tuple[int, int]]] = {}

    async def connect(self) -> None:
        """Connect to Redis."""
        await self._limiter.connect()

    async def close(self) -> None:
        """Close Redis connection."""
        await self._limiter.close()

    def configure_tiers(self, tier_name: str, limits: list[tuple[int, int]]) -> None:
        """Configure rate limit tiers.

        Args:
            tier_name: Name of the tier configuration (e.g., "default", "premium")
            limits: List of (limit, window_seconds) tuples
                    e.g., [(10, 1), (100, 60), (1000, 3600)]
                    for 10/sec, 100/min, 1000/hour
        """
        self._tiers[tier_name] = limits

    async def is_allowed(
        self, key: str, tier_name: str = "default"
    ) -> tuple[bool, list[RateLimitResult]]:
        """Check if request passes all tier limits.

        Args:
            key: Rate limit bucket identifier
            tier_name: Name of tier configuration to use

        Returns:
            Tuple of (all_allowed, list of results for each tier)
        """
        if tier_name not in self._tiers:
            raise ValueError(f"Unknown tier: {tier_name}")

        results = []
        all_allowed = True

        for limit, window in self._tiers[tier_name]:
            tier_key = f"{key}:{window}s"
            result = await self._limiter.is_allowed(tier_key, limit, window)
            results.append(result)
            if not result.allowed:
                all_allowed = False
                # Don't break - check all tiers for complete status

        return all_allowed, results
