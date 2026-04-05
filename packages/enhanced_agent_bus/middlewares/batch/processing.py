"""
Batch Processing Middleware for ACGS-2 Pipeline.

Core batch item processing with error aggregation.
Extracted from: batch_processor_infra/workers.py + orchestrator.py

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import cast

from enhanced_agent_bus.validators import ValidationResult

from ...batch_models import BatchRequestItem, BatchResponse, BatchResponseItem
from ...enums import BatchItemStatus
from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchProcessingException

BATCH_PROCESSING_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    asyncio.TimeoutError,
)
BATCH_ITEM_PROCESSING_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    asyncio.TimeoutError,
)


class BatchProcessingMiddleware(BaseMiddleware):
    """Core batch item processing with error aggregation.

    Processes individual items in a batch, handling:
    - Concurrent execution with semaphore control
    - Error aggregation and categorization
    - Result collection and response building
    - Fail-fast vs continue-on-error behavior

    Example:
        middleware = BatchProcessingMiddleware(
            item_processor=my_processor_func,
        )
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        item_processor: Callable[[BatchRequestItem], Awaitable[ValidationResult]] | None = None,
    ):
        """Initialize batch processing middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
            item_processor: Async function to process individual items
        """
        super().__init__(config)
        self._item_processor = item_processor

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process all batch items.

        Steps:
        1. Validate items exist
        2. Process items concurrently (respecting max_concurrency)
        3. Aggregate results
        4. Build batch response

        Args:
            context: Batch pipeline context containing items

        Returns:
            Context with processed items and response

        Raises:
            BatchProcessingException: If processing fails catastrophically
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        # Skip if no items
        if not context.batch_items:
            context.batch_response = BatchResponse(
                batch_id=context.batch_request.batch_id if context.batch_request else "empty",
                success=True,
                items=[],
            )
            context = await self._call_next(context)
            return context

        try:
            # Create semaphore for concurrency control
            semaphore = asyncio.Semaphore(context.max_concurrency)

            # Process all items concurrently
            tasks = [
                self._process_with_semaphore(semaphore, item, context)
                for item in context.batch_items
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            for item, result in zip(context.batch_items, results, strict=False):
                if isinstance(result, Exception):
                    # Processing exception
                    error_msg = str(result)
                    context.add_failed_item(item, error_msg)

                    # Create error response item
                    response_item = BatchResponseItem.create_error(
                        request_id=item.request_id,
                        error_code="PROCESSING_ERROR",
                        error_message=error_msg,
                    )
                    context.processed_items.append(response_item)

                    # Fail-fast check
                    if context.fail_fast:
                        break
                elif isinstance(result, BatchResponseItem):
                    # Successful processing
                    context.processed_items.append(result)
                    if not result.success:
                        error_msg = result.error_message or "Unknown error"
                        context.add_failed_item(item, error_msg)
                        if context.fail_fast:
                            break

            # Build batch response
            context.batch_response = self._aggregate_results(context.processed_items)
            context.batch_response.batch_id = (
                context.batch_request.batch_id if context.batch_request else "unknown"
            )

        except BATCH_PROCESSING_ERRORS as e:
            error_msg = f"Batch processing failed: {e}"
            if self.config.fail_closed:
                raise BatchProcessingException(
                    message=error_msg,
                    error_code="BATCH_PROCESSING_ERROR",
                ) from e

            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=[error_msg],
                    metadata={"validation_stage": "batch_processing"},
                )
            )
            context = await self._call_next(context)
            return context

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

        context = await self._call_next(context)
        return context

    async def _process_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        item: BatchRequestItem,
        context: BatchPipelineContext,
    ) -> BatchResponseItem:
        """Process a single item with semaphore control and timeout enforcement.

        Args:
            semaphore: Concurrency control semaphore
            item: Batch item to process
            context: Pipeline context for metadata

        Returns:
            Batch response item
        """
        async with semaphore:
            # Get timeout from context or use default (30 seconds)
            timeout_ms = context.batch_request.timeout_ms if context.batch_request else 30000
            timeout_sec = timeout_ms / 1000.0

            try:
                # Process with timeout enforcement
                return await asyncio.wait_for(
                    self._process_item(item),
                    timeout=timeout_sec,
                )
            except TimeoutError:
                # Timeout occurred - create timeout error response
                error_msg = f"Item processing timeout after {timeout_ms}ms"

                # Track timeout metric on context
                if "timeout_count" not in context.metadata:
                    context.metadata["timeout_count"] = 0
                context.metadata["timeout_count"] += 1

                return BatchResponseItem.create_error(
                    request_id=item.request_id,
                    error_code="TIMEOUT_ERROR",
                    error_message=error_msg,
                )

    async def _process_item(self, item: BatchRequestItem) -> BatchResponseItem:
        """Process a single batch item.

        Args:
            item: Batch request item to process

        Returns:
            Batch response item
        """
        start_time = time.perf_counter()

        try:
            # Use custom processor if provided
            if self._item_processor:
                result = await self._item_processor(item)

                latency_ms = (time.perf_counter() - start_time) * 1000

                return BatchResponseItem(
                    request_id=item.request_id,
                    status=BatchItemStatus.SUCCESS.value
                    if result.is_valid
                    else BatchItemStatus.FAILED.value,
                    valid=result.is_valid,
                    validation_result={"decision": getattr(result, "decision", None)},
                    error_code=None if result.is_valid else "VALIDATION_FAILED",
                    error_message="; ".join(result.errors) if result.errors else None,
                    processing_time_ms=latency_ms,
                    constitutional_validated=True,
                )

            # Default processing: mark as success
            latency_ms = (time.perf_counter() - start_time) * 1000

            return BatchResponseItem.create_success(
                request_id=item.request_id,
                valid=True,
                processing_time_ms=latency_ms,
                details={"message": "Default processing - no custom processor configured"},
            )

        except BATCH_ITEM_PROCESSING_ERRORS as e:
            latency_ms = (time.perf_counter() - start_time) * 1000

            return BatchResponseItem.create_error(
                request_id=item.request_id,
                error_code="PROCESSING_EXCEPTION",
                error_message=str(e),
                processing_time_ms=latency_ms,
            )

    def _aggregate_results(self, results: list[BatchResponseItem]) -> BatchResponse:
        """Aggregate individual results into batch response.

        Args:
            results: List of batch response items

        Returns:
            Aggregated batch response
        """
        from ...batch_models import BatchResponseStats

        total = len(results)
        successful = len([r for r in results if r.success])
        failed = total - successful

        # Calculate latency percentiles
        latencies = [r.processing_time_ms for r in results if r.processing_time_ms is not None]
        p50 = p95 = p99 = None
        if latencies:
            sorted_latencies = sorted(latencies)
            p50 = sorted_latencies[int(len(sorted_latencies) * 0.5)]
            p95 = sorted_latencies[
                min(int(len(sorted_latencies) * 0.95), len(sorted_latencies) - 1)
            ]
            p99 = sorted_latencies[
                min(int(len(sorted_latencies) * 0.99), len(sorted_latencies) - 1)
            ]

        stats = BatchResponseStats(
            total_items=total,
            successful_items=successful,
            failed_items=failed,
            valid_items=successful,
            invalid_items=failed,
            average_item_time_ms=sum(latencies) / len(latencies) if latencies else None,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
        )

        return BatchResponse(
            batch_id="aggregated",
            success=failed == 0,
            items=results,
            stats=stats,
        )

    def set_item_processor(
        self,
        processor: Callable[[BatchRequestItem], Awaitable[ValidationResult]],
    ) -> None:
        """Set the item processor function.

        Args:
            processor: Async function to process individual items
        """
        self._item_processor = processor
