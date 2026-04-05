"""
Batch Deduplication Middleware for ACGS-2 Pipeline.

Deduplicates batch items by message_id.
Extracted from: batch_processor_infra/queue.py

Constitutional Hash: 608508a9bd224290
"""

import hashlib
import time
from collections import OrderedDict
from typing import cast

from enhanced_agent_bus.validators import ValidationResult

from ...batch_models import BatchRequestItem
from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchDeduplicationException

BATCH_DEDUPLICATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class _LRUCache:
    """Simple LRU cache for deduplication tracking.

    Thread-safe for async usage. Uses OrderedDict for O(1) operations.
    """

    def __init__(self, maxsize: int = 10000):
        self._maxsize = maxsize
        self._cache: OrderedDict[str, object] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> object | None:
        """Get item from cache, moving to end if found (LRU)."""
        if key in self._cache:
            # Move to end (most recently used)
            value = self._cache.pop(key)
            self._cache[key] = value
            self._hits += 1
            return value
        self._misses += 1
        return None

    def set(self, key: str, value: object) -> None:
        """Set item in cache, evicting oldest if at capacity."""
        if key in self._cache:
            # Update existing, move to end
            self._cache.pop(key)
        elif len(self._cache) >= self._maxsize:
            # Evict oldest (first item)
            self._cache.popitem(last=False)
        self._cache[key] = value

    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache."""
        return key in self._cache

    def __len__(self) -> int:
        """Return current cache size."""
        return len(self._cache)

    def clear(self) -> None:
        """Clear all items from cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total


class BatchDeduplicationMiddleware(BaseMiddleware):
    """Deduplicates batch items by content hash.

    Uses LRU cache to track recently seen items within a time window.
    Prevents duplicate processing of identical requests.

    Example:
        middleware = BatchDeduplicationMiddleware(
            dedup_window_sec=300,
            max_cache_size=10000,
        )
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        dedup_window_sec: int = 300,
        max_cache_size: int = 10000,
    ):
        """Initialize batch deduplication middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
            dedup_window_sec: Time window for deduplication in seconds (default: 300)
            max_cache_size: Maximum cache entries (default: 10000)
        """
        super().__init__(config)
        self._dedup_window_sec = dedup_window_sec
        self._max_cache_size = max_cache_size
        self._cache = _LRUCache(maxsize=max_cache_size)
        self._seen_timestamps: dict[str, float] = {}

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process batch deduplication.

        Steps:
        1. Check if deduplication is enabled
        2. Compute content hash for each item
        3. Filter out duplicates
        4. Update cache with new items

        Args:
            context: Batch pipeline context containing items

        Returns:
            Context with duplicates removed

        Raises:
            BatchDeduplicationException: If deduplication fails and fail_closed is True
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        # Skip if deduplication disabled
        if not context.deduplicate:
            context = await self._call_next(context)
            return context

        # Skip if no items
        if not context.batch_items:
            context = await self._call_next(context)
            return context

        try:
            # Deduplicate items
            unique_items: list[BatchRequestItem] = []
            dedup_count = 0

            for item in context.batch_items:
                message_id = self._compute_message_id(item)

                if self._is_duplicate(message_id):
                    dedup_count += 1
                    continue

                # Add to unique items and cache
                unique_items.append(item)
                self._cache.set(message_id, True)
                self._seen_timestamps[message_id] = time.time()

            # Update context
            context.batch_items = unique_items
            context.deduplicated_count = dedup_count
            context.batch_size = len(unique_items)

            # Clean old timestamps periodically
            self._clean_old_timestamps()

        except BATCH_DEDUPLICATION_ERRORS as e:
            error_msg = f"Deduplication failed: {e}"
            if self.config.fail_closed:
                raise BatchDeduplicationException(
                    message=error_msg,
                    cache_size=len(self._cache),
                ) from e

            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=[error_msg],
                    metadata={"validation_stage": "deduplication"},
                )
            )
            context = await self._call_next(context)
            return context

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

        context = await self._call_next(context)
        return context

    def _is_duplicate(self, message_id: str) -> bool:
        """Check if message ID is a duplicate.

        Args:
            message_id: Computed message identifier

        Returns:
            True if duplicate, False otherwise
        """
        # Check cache first
        if message_id in self._cache:
            # Verify it's within the time window
            timestamp = self._seen_timestamps.get(message_id, 0)
            if time.time() - timestamp <= self._dedup_window_sec:
                return True
            # Expired - remove from timestamps
            self._seen_timestamps.pop(message_id, None)

        return False

    def _compute_message_id(self, item: BatchRequestItem) -> str:
        """Compute unique message ID for an item.

        Uses content hash combining tenant, agent, type, content, and priority.

        Args:
            item: Batch request item

        Returns:
            Computed message ID (hex digest)
        """
        # Build content string
        content_parts = [
            str(item.tenant_id or "default"),
            str(item.from_agent or ""),
            str(item.message_type or ""),
            str(item.content or ""),
            str(item.priority or 1),
        ]
        content_str = "|".join(content_parts)

        # Compute SHA256 hash
        return hashlib.sha256(content_str.encode()).hexdigest()

    def _clean_old_timestamps(self) -> None:
        """Remove expired timestamps to prevent memory growth."""
        current_time = time.time()
        expired = [
            msg_id
            for msg_id, ts in self._seen_timestamps.items()
            if current_time - ts > self._dedup_window_sec
        ]
        for msg_id in expired:
            self._seen_timestamps.pop(msg_id, None)

    @property
    def cache_size(self) -> int:
        """Return current cache size."""
        return len(self._cache)

    @property
    def cache_hit_rate(self) -> float:
        """Return cache hit rate."""
        return self._cache.hit_rate

    def clear_cache(self) -> None:
        """Clear deduplication cache."""
        self._cache.clear()
        self._seen_timestamps.clear()
