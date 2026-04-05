"""
ACGS-2 Batch Optimization
Constitutional Hash: 608508a9bd224290

Optimizes costs through request batching for non-urgent operations.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import UrgencyLevel
from .models import BatchRequest, BatchResult

logger = get_logger(__name__)


class BatchOptimizer:
    """
    Optimizes costs through request batching.

    Constitutional Hash: 608508a9bd224290

    Groups non-urgent requests together for batch processing
    to achieve volume discounts and reduce per-request overhead.
    """

    def __init__(
        self,
        min_batch_size: int = 5,
        max_batch_size: int = 50,
        max_wait_time: timedelta = timedelta(minutes=5),
    ) -> None:
        """Initialize batch optimizer."""
        self._min_batch_size = min_batch_size
        self._max_batch_size = max_batch_size
        self._max_wait_time = max_wait_time
        self._pending_requests: dict[str, BatchRequest] = {}
        self._batches: dict[str, list[str]] = {}  # batch_key -> request_ids
        self._results: dict[str, BatchResult] = {}
        self._lock = asyncio.Lock()
        self._batch_counter = 0

    def _get_batch_key(self, request: BatchRequest) -> str:
        """Generate batch key for grouping similar requests."""
        # Group by tenant, urgency, quality, and capability requirements
        req_hash = hash(tuple(r.dimension.value for r in request.requirements))
        return f"{request.tenant_id}:{request.urgency.value}:{request.quality.value}:{req_hash}"

    async def add_request(self, request: BatchRequest) -> str | None:
        """
        Add request to batch queue.

        Returns batch_id if batch is ready, None otherwise.
        """
        async with self._lock:
            # Only batch non-urgent requests
            if request.urgency in (UrgencyLevel.HIGH, UrgencyLevel.CRITICAL):
                return None  # Process immediately

            self._pending_requests[request.request_id] = request
            batch_key = self._get_batch_key(request)

            if batch_key not in self._batches:
                self._batches[batch_key] = []

            self._batches[batch_key].append(request.request_id)

            # Check if batch is ready
            batch_requests = self._batches[batch_key]
            if len(batch_requests) >= self._max_batch_size:
                return await self._execute_batch(batch_key)

            # Check if oldest request has waited too long
            oldest_time = min(
                self._pending_requests[rid].created_at
                for rid in batch_requests
                if rid in self._pending_requests
            )
            if datetime.now(UTC) - oldest_time > self._max_wait_time:
                if len(batch_requests) >= self._min_batch_size:
                    return await self._execute_batch(batch_key)

            return None

    async def _execute_batch(self, batch_key: str) -> str:
        """Execute a batch and return batch_id."""
        self._batch_counter += 1
        batch_id = f"batch-{self._batch_counter}"

        request_ids = self._batches.pop(batch_key, [])
        requests = [
            self._pending_requests.pop(rid) for rid in request_ids if rid in self._pending_requests
        ]

        if not requests:
            return batch_id

        # Calculate batch result
        total_tokens = sum(r.estimated_tokens for r in requests)
        individual_cost = sum(
            (r.estimated_tokens / 1000) * 0.01
            for r in requests  # Assume standard pricing
        )
        batch_cost = (total_tokens / 1000) * 0.008  # Assume 20% batch discount

        result = BatchResult(
            batch_id=batch_id,
            requests=request_ids,
            provider_id="batch-provider",
            total_cost=batch_cost,
            cost_per_request=batch_cost / len(requests) if requests else 0,
            savings_percentage=(
                ((individual_cost - batch_cost) / individual_cost * 100)
                if individual_cost > 0
                else 0
            ),
        )

        self._results[batch_id] = result
        logger.info(
            f"Batch {batch_id} executed: {len(requests)} requests, "
            f"${batch_cost:.4f} total, {result.savings_percentage:.1f}% savings"
        )

        return batch_id

    async def flush_batches(self) -> list[str]:
        """Flush all pending batches."""
        async with self._lock:
            batch_keys = list(self._batches.keys())
            batch_ids = []
            for key in batch_keys:
                if len(self._batches.get(key, [])) >= self._min_batch_size:
                    batch_ids.append(await self._execute_batch(key))
            return batch_ids

    def get_result(self, batch_id: str) -> BatchResult | None:
        """Get batch result."""
        return self._results.get(batch_id)

    def get_pending_count(self) -> int:
        """Get count of pending requests."""
        return len(self._pending_requests)


__all__ = [
    "BatchOptimizer",
]
