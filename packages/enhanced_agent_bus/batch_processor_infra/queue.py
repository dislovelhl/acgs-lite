"""
Batch Request Queue for ACGS-2 Enhanced Agent Bus
Constitutional Hash: 608508a9bd224290

Manages batch request deduplication, priority sorting, and queue operations.
"""

import hashlib

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from acgs2_perf import fast_hash

    PERF_KERNELS_AVAILABLE = True
except ImportError:
    PERF_KERNELS_AVAILABLE = False

from enhanced_agent_bus.models import BatchRequest, BatchRequestItem

logger = get_logger(__name__)


class BatchRequestQueue:
    def __init__(self, enable_deduplication: bool = True, max_cache_size: int = 10000):
        self.enable_deduplication = enable_deduplication
        self.max_cache_size = max_cache_size
        self._dedup_cache: dict[str, int] = {}
        self._seen_hashes: set[str] = set()

    def deduplicate_requests(
        self, batch_request: BatchRequest
    ) -> tuple[list[BatchRequestItem], dict[int, int]]:
        # Check both queue-level and batch-level deduplication settings
        if not self.enable_deduplication or not getattr(batch_request, "deduplicate", True):
            # Return identity mapping when deduplication is disabled
            return list(batch_request.items), {i: i for i in range(len(batch_request.items))}

        unique_items: list[BatchRequestItem] = []
        index_mapping: dict[int, int] = {}

        # Self-cleaning cache if it grows too large
        if len(self._dedup_cache) > self.max_cache_size:
            logger.info(f"Deduplication cache reached limit ({self.max_cache_size}), clearing...")
            self.clear_cache()

        for idx, item in enumerate(batch_request.items):
            content_hash = self._compute_content_hash(item)

            if content_hash in self._dedup_cache:
                index_mapping[idx] = self._dedup_cache[content_hash]
                logger.debug(
                    f"Duplicate item at index {idx}, mapped to {self._dedup_cache[content_hash]}"
                )
            else:
                self._dedup_cache[content_hash] = len(unique_items)
                index_mapping[idx] = len(unique_items)
                unique_items.append(item)

        logger.info(
            f"Deduplicated {len(batch_request.items)} items to {len(unique_items)} unique items"
        )
        return unique_items, index_mapping

    def _compute_content_hash(self, item: BatchRequestItem) -> str:
        hash_input = (
            f"{item.tenant_id}:{item.from_agent}:{item.message_type}:{item.content}:{item.priority}"
        )
        if PERF_KERNELS_AVAILABLE:
            return f"{fast_hash(hash_input):x}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    def clear_cache(self) -> None:
        self._dedup_cache.clear()
        self._seen_hashes.clear()

    def get_cache_size(self) -> int:
        return len(self._dedup_cache)
