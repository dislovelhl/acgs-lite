"""
Batch Processor Orchestrator for ACGS-2 Enhanced Agent Bus.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import (
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseStats,
)
from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.validators import ValidationResult

from .governance import BatchGovernanceManager
from .metrics import BatchMetrics
from .queue import BatchRequestQueue
from .tuning import BatchAutoTuner
from .workers import WorkerPool

logger = get_logger(__name__)


class BatchProcessorOrchestrator:
    def __init__(
        self,
        max_concurrency: int = 100,
        item_timeout_ms: int = 30000,
        max_retries: int = 0,
        retry_base_delay: float = 0.1,
        retry_exponential_base: float = 2.0,
    ):
        self.queue = BatchRequestQueue()
        self.metrics = BatchMetrics()
        self.workers = WorkerPool(
            max_concurrency=max_concurrency,
            item_timeout_ms=item_timeout_ms,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            retry_exponential_base=retry_exponential_base,
        )
        self.governance = BatchGovernanceManager()
        self.tuner = BatchAutoTuner(initial_batch_size=max_concurrency)

    async def process_batch(
        self,
        batch_request: BatchRequest,
        process_func: Callable[[BatchRequestItem], Awaitable[ValidationResult]],
    ) -> BatchResponse:
        start_time = time.time()

        gov_result = self.governance.validate_batch_context(batch_request)
        if not gov_result.is_valid:
            logger.warning(f"Batch governance validation failed: {gov_result.errors}")
            # Determine error code based on error message
            error_msg = (
                gov_result.errors[0] if gov_result.errors else "Governance validation failed"
            )
            error_code = (
                "CONSTITUTIONAL_HASH_MISMATCH"
                if "hash" in error_msg.lower()
                else "GOVERNANCE_FAILURE"
            )
            return BatchResponse(
                batch_id=batch_request.batch_id,
                success=False,
                error_code=error_code,
                items=[],
                stats=BatchResponseStats(
                    total_items=len(batch_request.items),
                    failed_items=len(batch_request.items),
                    processing_time_ms=(time.time() - start_time) * 1000.0,
                ),
                errors=[error_msg],
            )

        unique_items, index_mapping = self.queue.deduplicate_requests(batch_request)
        deduplicated_count = len(batch_request.items) - len(unique_items)

        if not unique_items:
            # All items were deduplicated - create placeholder results
            # This happens when all items have been seen in previous batches
            from enhanced_agent_bus.models import BatchItemStatus, BatchResponseItem

            final_items = [
                BatchResponseItem(
                    request_id=item.request_id,
                    status=BatchItemStatus.SUCCESS.value,
                    valid=True,
                    validation_result={"deduplicated": True, "cached": True},
                    constitutional_validated=True,
                )
                for item in batch_request.items
            ]
        else:
            tasks = [self.workers.process_item(item, process_func) for item in unique_items]
            unique_results = await asyncio.gather(*tasks)

            final_items = []
            for orig_idx in range(len(batch_request.items)):
                unique_idx = index_mapping[orig_idx]
                final_items.append(unique_results[unique_idx])

        processing_time_ms = (time.time() - start_time) * 1000.0
        stats = self.metrics.calculate_batch_stats(
            total_items=len(batch_request.items),
            results=final_items,
            processing_time_ms=processing_time_ms,
            deduplicated_count=deduplicated_count,
        )

        self.metrics.record_batch_processed(stats, processing_time_ms)
        self.tuner.adjust_from_stats(
            success_rate=(
                (stats.successful_items / stats.total_items * 100) if stats.total_items > 0 else 100
            ),
            avg_latency_ms=stats.average_item_time_ms or 0,
        )

        return BatchResponse(batch_id=batch_request.batch_id, items=final_items, stats=stats)

    def get_metrics(self) -> JSONDict:
        return self.metrics.get_cumulative_metrics()

    def reset_metrics(self) -> None:
        self.metrics.reset()

    def clear_cache(self) -> None:
        self.queue.clear_cache()

    def get_cache_size(self) -> int:
        return self.queue.get_cache_size()
