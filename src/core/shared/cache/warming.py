"""
ACGS-2 Cache Warming Module
Constitutional Hash: cdd01ef066bc6cf2

Provides cache pre-population at service startup to prevent cold start performance
degradation with rate limiting to avoid thundering herd.

Warming Strategy:
- Load top 100 most-accessed keys from L3 into L2 (Redis)
- Load top 10 most-accessed keys into L1 (in-process)
- Rate limited to 100 keys/second to avoid overwhelming the system
- Staggered loading to prevent connection pool exhaustion

Usage:
    from src.core.shared.cache_warming import CacheWarmer, get_cache_warmer

    # Direct usage
    warmer = CacheWarmer(rate_limit=100)
    await warmer.warm_cache(source_keys=['key1', 'key2'])

    # FastAPI startup event
    @app.on_event("startup")
    async def startup_event():
        warmer = get_cache_warmer()
        await warmer.warm_cache()

Example:
    warmer = CacheWarmer(
        rate_limit=100,
        l1_count=10,
        l2_count=100,
    )
    result = await warmer.warm_cache()

"""

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

# Constitutional Hash for governance validation
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict, JSONValue

logger = get_logger(__name__)


class WarmingStatus(Enum):
    """Cache warming status."""

    IDLE = "idle"
    WARMING = "warming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WarmingConfig:
    """Configuration for cache warming."""

    # Rate limiting
    rate_limit: int = 100  # Keys per second
    batch_size: int = 10  # Keys per batch for efficient loading

    # Tier allocation
    l1_count: int = 10  # Top N keys to warm into L1
    l2_count: int = 100  # Top N keys to warm into L2

    # Timeouts
    key_timeout: float = 1.0  # Timeout per key load in seconds
    total_timeout: float = 300.0  # Maximum warming duration in seconds

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 0.5

    # Priority loading
    priority_keys: list[str] = field(default_factory=list)


@dataclass
class WarmingResult:
    """Result of cache warming operation."""

    status: WarmingStatus
    keys_warmed: int = 0
    keys_failed: int = 0
    l1_keys: int = 0
    l2_keys: int = 0
    duration_seconds: float = 0.0
    error_message: str | None = None
    details: JSONDict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if warming was successful."""
        return self.status == WarmingStatus.COMPLETED

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.keys_warmed + self.keys_failed
        return self.keys_warmed / total if total > 0 else 0.0


@dataclass
class WarmingProgress:
    """Progress tracking for cache warming."""

    total_keys: int = 0
    processed_keys: int = 0
    current_batch: int = 0
    total_batches: int = 0
    elapsed_seconds: float = 0.0
    estimated_remaining: float = 0.0

    @property
    def percent_complete(self) -> float:
        """Calculate completion percentage."""
        return (self.processed_keys / self.total_keys * 100) if self.total_keys > 0 else 0.0


class RateLimiter:
    """
    Token bucket rate limiter for controlling cache warming speed.

    .. deprecated::
        Use ``src.core.shared.security.rate_limiter.SlidingWindowRateLimiter`` (or
        ``RateLimitMiddleware``) instead.
        This local implementation in the cache warming utility exists for
        historical reasons and is not maintained as the canonical version.

    Thread-safe implementation that allows bursting up to max_tokens
    while maintaining average rate of tokens_per_second.
    """

    def __init__(
        self,
        tokens_per_second: float = 100.0,
        max_tokens: int | None = None,
    ):
        """
        Initialize rate limiter.

        Args:
            tokens_per_second: Target rate (keys per second)
            max_tokens: Maximum burst capacity (defaults to tokens_per_second)
        """
        self.tokens_per_second = tokens_per_second
        self.max_tokens = max_tokens or int(tokens_per_second)
        self.tokens = float(self.max_tokens)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()
        self._lock_async: asyncio.Lock | None = None  # Lazy-initialized for async methods

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(
            self.max_tokens,
            self.tokens + elapsed * self.tokens_per_second,
        )
        self.last_update = now

    def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens, returning wait time if needed.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Time to wait in seconds (0 if tokens available)
        """
        with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            # Calculate wait time
            needed = tokens - self.tokens
            wait_time = needed / self.tokens_per_second
            return wait_time

    async def acquire_async(self, tokens: int = 1) -> None:
        """
        Async version of acquire that waits if needed.

        Args:
            tokens: Number of tokens to acquire
        """
        # Lazy initialize async lock
        if self._lock_async is None:
            self._lock_async = asyncio.Lock()

        async with self._lock_async:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return

            # Calculate wait time
            needed = tokens - self.tokens
            wait_time = needed / self.tokens_per_second

        # Wait outside the lock
        if wait_time > 0:
            await asyncio.sleep(wait_time)

            # After waiting, actually consume the tokens
            async with self._lock_async:
                self._refill()
                self.tokens -= tokens


class CacheWarmer:
    """
    Cache warming manager for pre-populating caches at startup.

    Implements rate-limited cache warming to prevent thundering herd
    during cold starts. Prioritizes hot data for L1 and distributes
    remaining data to L2.

    Features:
    - Rate limited warming (default 100 keys/second)
    - Batch loading for efficiency
    - Priority key support
    - Progress tracking
    - Graceful error handling

    Thread Safety:
    - Uses RateLimiter with internal locking
    - Progress tracking is thread-safe
    - Supports concurrent warming cancellation
    """

    def __init__(
        self,
        rate_limit: int = 100,
        config: WarmingConfig | None = None,
        cache_manager: object | None = None,
    ):
        """
        Initialize cache warmer.

        Args:
            rate_limit: Maximum keys per second (overrides config if provided)
            config: Optional WarmingConfig for detailed configuration
            cache_manager: Optional TieredCacheManager instance (lazy loaded if None)
        """
        self.config = config or WarmingConfig(rate_limit=rate_limit)
        if rate_limit != 100:  # Explicit override
            self.config.rate_limit = rate_limit

        self._rate_limiter = RateLimiter(
            tokens_per_second=self.config.rate_limit,
            max_tokens=self.config.batch_size * 2,  # Allow 2x batch burst
        )

        self._cache_manager = cache_manager
        self._status = WarmingStatus.IDLE
        self._progress = WarmingProgress()
        self._lock = threading.Lock()
        self._lock_async: asyncio.Lock | None = None  # Lazy-initialized for async methods
        self._cancel_event: asyncio.Event = asyncio.Event()

        # Callbacks for progress updates
        self._progress_callbacks: list[Callable[[WarmingProgress], None]] = []

        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] CacheWarmer initialized: "
            f"rate_limit={self.config.rate_limit}/s, "
            f"l1_count={self.config.l1_count}, l2_count={self.config.l2_count}"
        )

    @property
    def status(self) -> WarmingStatus:
        """Get current warming status."""
        return self._status

    @property
    def progress(self) -> WarmingProgress:
        """Get current warming progress."""
        return self._progress

    @property
    def is_warming(self) -> bool:
        """Check if warming is in progress."""
        return self._status == WarmingStatus.WARMING

    def _get_cache_manager(self) -> object:
        """
        Get or lazily initialize the cache manager.

        Returns:
            TieredCacheManager instance
        """
        if self._cache_manager is None:
            # Lazy import to avoid circular dependencies
            from src.core.shared.tiered_cache import get_tiered_cache

            self._cache_manager = get_tiered_cache()
        return self._cache_manager

    async def warm_cache(
        self,
        source_keys: list[str] | None = None,
        key_loader: Callable[[str], JSONValue | object] | None = None,
    ) -> WarmingResult:
        """
        Warm the cache with rate limiting.

        Loads keys into L1 and L2 tiers based on priority (hot keys to L1,
        remaining to L2).

        Args:
            source_keys: Optional list of keys to warm (uses L3 keys if not provided)
            key_loader: Optional function to load key values (uses cache_manager if not provided)

        Returns:
            WarmingResult with statistics and status
        """
        # Lazy initialize async lock and cancel event
        if self._lock_async is None:
            self._lock_async = asyncio.Lock()

        start_time = time.monotonic()

        async with self._lock_async:
            if self._status == WarmingStatus.WARMING:
                logger.warning(f"[{CONSTITUTIONAL_HASH}] Cache warming already in progress")
                return WarmingResult(
                    status=WarmingStatus.FAILED,
                    error_message="Warming already in progress",
                )

            self._status = WarmingStatus.WARMING
            self._cancel_event.clear()

        try:
            # Get cache manager
            cache_manager = self._get_cache_manager()

            # Determine keys to warm
            keys_to_warm = await self._get_keys_to_warm(source_keys)

            if not keys_to_warm:
                logger.info(f"[{CONSTITUTIONAL_HASH}] No keys to warm")
                async with self._lock_async:
                    self._status = WarmingStatus.COMPLETED
                return WarmingResult(
                    status=WarmingStatus.COMPLETED,
                    duration_seconds=time.monotonic() - start_time,
                )

            # Initialize progress tracking
            total_keys = len(keys_to_warm)
            self._progress = WarmingProgress(
                total_keys=total_keys,
                total_batches=(total_keys + self.config.batch_size - 1) // self.config.batch_size,
            )

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Starting cache warming: "
                f"{total_keys} keys, rate={self.config.rate_limit}/s"
            )

            # Warm cache in batches
            result = await self._warm_in_batches(
                keys_to_warm,
                cache_manager,
                key_loader,
                start_time,
            )

            # Update final status
            async with self._lock_async:
                self._status = result.status

            result.duration_seconds = time.monotonic() - start_time

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Cache warming completed: "
                f"warmed={result.keys_warmed}, failed={result.keys_failed}, "
                f"L1={result.l1_keys}, L2={result.l2_keys}, "
                f"duration={result.duration_seconds:.2f}s"
            )

            return result

        except asyncio.CancelledError:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Cache warming cancelled")
            async with self._lock_async:
                self._status = WarmingStatus.CANCELLED
            return WarmingResult(
                status=WarmingStatus.CANCELLED,
                duration_seconds=time.monotonic() - start_time,
            )

        except Exception as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Cache warming failed: {e}")
            async with self._lock_async:
                self._status = WarmingStatus.FAILED
            return WarmingResult(
                status=WarmingStatus.FAILED,
                error_message=str(e),
                duration_seconds=time.monotonic() - start_time,
            )

    async def _get_keys_to_warm(
        self,
        source_keys: list[str] | None = None,
    ) -> list[str]:
        """
        Get the list of keys to warm.

        Priority order:
        1. Explicit source_keys if provided
        2. Priority keys from config
        3. Keys from L3 cache (top accessed)

        Args:
            source_keys: Optional explicit list of keys

        Returns:
            List of keys to warm, ordered by priority
        """
        if source_keys:
            return source_keys[: self.config.l2_count]

        keys = []

        # Add priority keys first
        if self.config.priority_keys:
            keys.extend(self.config.priority_keys)

        # Try to get keys from L3 cache
        try:
            cache_manager = self._get_cache_manager()

            # Access L3 cache keys (in-memory simulation)
            if hasattr(cache_manager, "_l3_cache"):
                with cache_manager._l3_lock:
                    l3_keys = list(cache_manager._l3_cache.keys())

                # Sort by access frequency if available
                if hasattr(cache_manager, "_access_records"):
                    with cache_manager._access_lock:
                        sorted_keys = sorted(
                            l3_keys,
                            key=lambda k: (
                                cache_manager._access_records.get(
                                    k, type("obj", (object,), {"accesses_per_minute": 0})()
                                ).accesses_per_minute
                            ),
                            reverse=True,
                        )
                        keys.extend(sorted_keys)
                else:
                    keys.extend(l3_keys)

        except Exception as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Failed to get L3 keys for warming: {e}")

        # Remove duplicates while preserving order
        seen = set()
        unique_keys = []
        for key in keys:
            if key not in seen:
                seen.add(key)
                unique_keys.append(key)

        return unique_keys[: self.config.l2_count]

    async def _warm_in_batches(
        self,
        keys: list[str],
        cache_manager: object,
        key_loader: Callable[[str], object] | None,
        start_time: float,
    ) -> WarmingResult:
        """
        Warm cache keys in rate-limited batches.

        Args:
            keys: Keys to warm
            cache_manager: TieredCacheManager instance
            key_loader: Optional custom key loader
            start_time: Warming start time

        Returns:
            WarmingResult with statistics
        """
        # Import CacheTier for tier specification
        from src.core.shared.tiered_cache import CacheTier

        result = WarmingResult(status=WarmingStatus.COMPLETED)
        processed = 0
        batch_num = 0

        # Identify hot keys for L1 (top N most accessed)
        l1_keys = keys[: self.config.l1_count]

        # Create batches
        batches = [
            keys[i : i + self.config.batch_size]
            for i in range(0, len(keys), self.config.batch_size)
        ]

        for batch in batches:
            # Check cancellation
            if self._cancel_event.is_set():
                result.status = WarmingStatus.CANCELLED
                break

            # Check timeout
            elapsed = time.monotonic() - start_time
            if elapsed >= self.config.total_timeout:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Cache warming timeout after "
                    f"{elapsed:.1f}s (limit: {self.config.total_timeout}s)"
                )
                result.status = WarmingStatus.COMPLETED
                result.details["timeout"] = True
                break

            batch_num += 1

            # Rate limit: acquire tokens for this batch
            await self._rate_limiter.acquire_async(len(batch))

            # Process batch
            for key in batch:
                try:
                    # Load value
                    value = await self._load_key_value(key, cache_manager, key_loader)

                    if value is not None:
                        # Determine target tier
                        if key in l1_keys:
                            await cache_manager.set(key, value, tier=CacheTier.L1)
                            result.l1_keys += 1
                        else:
                            await cache_manager.set(key, value, tier=CacheTier.L2)
                            result.l2_keys += 1

                        result.keys_warmed += 1
                    else:
                        result.keys_failed += 1

                except (RuntimeError, ValueError, ConnectionError):
                    result.keys_failed += 1

                processed += 1

            # Update progress
            elapsed = time.monotonic() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = len(keys) - processed

            self._progress = WarmingProgress(
                total_keys=len(keys),
                processed_keys=processed,
                current_batch=batch_num,
                total_batches=len(batches),
                elapsed_seconds=elapsed,
                estimated_remaining=remaining / rate if rate > 0 else 0,
            )

            # Notify progress callbacks
            for callback in self._progress_callbacks:
                try:
                    callback(self._progress)
                except Exception as e:
                    logger.warning(f"Progress callback error: {e}")

            # Yield to event loop periodically
            await asyncio.sleep(0)

        return result

    async def _load_key_value(
        self,
        key: str,
        cache_manager: object,
        key_loader: Callable[[str], object] | None,
    ) -> JSONValue | None:
        """
        Load value for a key during warming.

        Args:
            key: Key to load
            cache_manager: TieredCacheManager instance
            key_loader: Optional custom loader function

        Returns:
            Value or None if not found
        """
        retries = 0

        while retries < self.config.max_retries:
            try:
                if key_loader:
                    # Use custom loader
                    value = key_loader(key)
                    if asyncio.iscoroutine(value):
                        value = await asyncio.wait_for(
                            value,
                            timeout=self.config.key_timeout,
                        )
                    return value

                # Try to get from L3 cache
                if hasattr(cache_manager, "_l3_cache"):
                    with cache_manager._l3_lock:
                        if key in cache_manager._l3_cache:
                            cached = cache_manager._l3_cache[key]
                            return cached.get("data")

                # Try to get from existing tiers
                value = cache_manager.get(key)
                if value is not None:
                    return value

                return None

            except TimeoutError:
                retries += 1
                if retries < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay)

            except (RuntimeError, ValueError, ConnectionError):
                retries += 1
                if retries < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay)

        return None

    def cancel(self) -> None:
        """Cancel ongoing cache warming."""
        self._cancel_event.set()
        logger.info(f"[{CONSTITUTIONAL_HASH}] Cache warming cancellation requested")

    def on_progress(self, callback: Callable[[WarmingProgress], None]) -> None:
        """
        Register a progress callback.

        Args:
            callback: Function called with WarmingProgress on each batch
        """
        self._progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: Callable[[WarmingProgress], None]) -> bool:
        """
        Remove a progress callback.

        Args:
            callback: Callback to remove

        Returns:
            True if callback was removed
        """
        try:
            self._progress_callbacks.remove(callback)
            return True
        except ValueError:
            return False

    def get_stats(self) -> JSONDict:
        """
        Get cache warmer statistics.

        Returns:
            Dictionary with warmer configuration and status
        """
        return {
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "status": self._status.value,
            "config": {
                "rate_limit": self.config.rate_limit,
                "batch_size": self.config.batch_size,
                "l1_count": self.config.l1_count,
                "l2_count": self.config.l2_count,
            },
            "progress": {
                "total_keys": self._progress.total_keys,
                "processed_keys": self._progress.processed_keys,
                "percent_complete": self._progress.percent_complete,
                "elapsed_seconds": self._progress.elapsed_seconds,
            },
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"CacheWarmer(rate_limit={self.config.rate_limit}, status={self._status.value})"


# -----------------------------------------------------------------------------
# Singleton pattern for shared usage
# -----------------------------------------------------------------------------

_default_warmer: CacheWarmer | None = None
_singleton_lock = threading.Lock()


def get_cache_warmer(
    rate_limit: int = 100,
    config: WarmingConfig | None = None,
) -> CacheWarmer:
    """
    Get or create the singleton CacheWarmer instance.

    Thread-safe singleton pattern for shared warmer access.

    Args:
        rate_limit: Maximum keys per second (used only on first call)
        config: Optional WarmingConfig (used only on first call)

    Returns:
        CacheWarmer singleton instance
    """
    global _default_warmer

    if _default_warmer is None:
        with _singleton_lock:
            if _default_warmer is None:
                _default_warmer = CacheWarmer(rate_limit=rate_limit, config=config)
                logger.info(
                    f"[{CONSTITUTIONAL_HASH}] CacheWarmer singleton created: "
                    f"rate_limit={rate_limit}"
                )

    return _default_warmer


def reset_cache_warmer() -> None:
    """
    Reset the singleton CacheWarmer instance.

    Useful for testing or when configuration needs to change.
    """
    global _default_warmer

    with _singleton_lock:
        if _default_warmer is not None:
            # Cancel any ongoing warming
            _default_warmer.cancel()
            _default_warmer = None
            logger.info(f"[{CONSTITUTIONAL_HASH}] CacheWarmer singleton reset")


async def warm_cache_on_startup(
    source_keys: list[str] | None = None,
    priority_keys: list[str] | None = None,
    rate_limit: int = 100,
) -> WarmingResult:
    """
    Convenience function for FastAPI startup event.

    Usage:
        @app.on_event("startup")
        async def startup_event():
            result = await warm_cache_on_startup()
            if not result.success:
                logger.warning(f"Cache warming failed: {result.error_message}")

    Args:
        source_keys: Optional list of keys to warm
        priority_keys: Optional list of priority keys (warmed first)
        rate_limit: Maximum keys per second

    Returns:
        WarmingResult with statistics
    """
    config = WarmingConfig(
        rate_limit=rate_limit,
        priority_keys=priority_keys or [],
    )

    warmer = get_cache_warmer(rate_limit=rate_limit, config=config)
    return await warmer.warm_cache(source_keys=source_keys)


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Classes
    "CacheWarmer",
    "RateLimiter",
    "WarmingConfig",
    "WarmingProgress",
    "WarmingResult",
    # Enums
    "WarmingStatus",
    # Functions
    "get_cache_warmer",
    "reset_cache_warmer",
    "warm_cache_on_startup",
]
