"""
Batch Pipeline Router for ACGS-2.

Assembles and executes the batch middleware pipeline, transforming
the monolithic BatchProcessorOrchestrator into a composable chain.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from collections.abc import Awaitable, Callable

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.validators import ValidationResult

from ..batch_models import BatchRequest, BatchResponse
from .middleware import BaseMiddleware, MiddlewareConfig
from .router import PipelineConfig

logger = get_logger(__name__)

BATCH_PIPELINE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
)


class BatchPipelineRouter:
    """Pipeline router for batch processing.

    Integrates with the existing PipelineMessageRouter infrastructure
    while adding batch-specific middlewares.

    Example:
        router = BatchPipelineRouter()
        response = await router.process_batch(batch_request)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        item_processor: Callable[..., Awaitable[ValidationResult]] | None = None,
    ):
        """Initialize the batch pipeline router.

        Args:
            config: Pipeline configuration (uses batch defaults if None)
            item_processor: Async function to process individual batch items.
                           Injected into BatchProcessingMiddleware.
        """
        if config is None:
            config = PipelineConfig(
                middlewares=self._create_batch_middlewares(item_processor),
                max_concurrent=100,
                version="2.0.0-batch",
                use_default_middlewares=False,
            )

        config.validate()
        self._config = config
        self._chain_head = config.build_chain()
        self._item_processor = item_processor
        self._metrics_lock = asyncio.Lock()
        self._metrics: JSONDict = {
            "batches_processed": 0,
            "batches_failed": 0,
            "total_items_processed": 0,
            "total_latency_ms": 0.0,
        }

    def _create_batch_middlewares(
        self,
        item_processor: Callable[..., Awaitable[ValidationResult]] | None = None,
    ) -> list[BaseMiddleware]:
        """Create the default 8-stage batch middleware chain.

        Order:
            1. Validation     - Schema, size limits
            2. TenantIsolation - Cross-tenant checks
            3. Deduplication   - Content hash dedup
            4. Governance      - MACI roles, impact scoring
            5. Concurrency     - Semaphore control
            6. Processing      - Core item execution
            7. AutoTune        - P99 tracking, size adjustment
            8. Metrics         - Latency percentiles, throughput

        Args:
            item_processor: Async function for processing items

        Returns:
            List of middleware instances
        """
        from ..middlewares.batch.auto_tune import BatchAutoTuneMiddleware
        from ..middlewares.batch.concurrency import BatchConcurrencyMiddleware
        from ..middlewares.batch.deduplication import BatchDeduplicationMiddleware
        from ..middlewares.batch.governance import BatchGovernanceMiddleware
        from ..middlewares.batch.metrics import BatchMetricsMiddleware
        from ..middlewares.batch.processing import BatchProcessingMiddleware
        from ..middlewares.batch.tenant_isolation import BatchTenantIsolationMiddleware
        from ..middlewares.batch.validation import BatchValidationMiddleware

        return [
            BatchValidationMiddleware(
                config=MiddlewareConfig(timeout_ms=500),
                max_batch_size=1000,
                min_batch_size=1,
            ),
            BatchTenantIsolationMiddleware(
                config=MiddlewareConfig(timeout_ms=500),
            ),
            BatchDeduplicationMiddleware(
                config=MiddlewareConfig(timeout_ms=500),
            ),
            BatchGovernanceMiddleware(
                config=MiddlewareConfig(timeout_ms=1000),
            ),
            BatchConcurrencyMiddleware(
                config=MiddlewareConfig(timeout_ms=500),
            ),
            BatchProcessingMiddleware(
                config=MiddlewareConfig(timeout_ms=30000),
                item_processor=item_processor,
            ),
            BatchAutoTuneMiddleware(
                config=MiddlewareConfig(timeout_ms=500),
            ),
            BatchMetricsMiddleware(
                config=MiddlewareConfig(timeout_ms=500),
            ),
        ]

    async def process_batch(self, batch_request: BatchRequest) -> BatchResponse:
        """Process a batch request through the middleware pipeline.

        Args:
            batch_request: The batch request to process

        Returns:
            BatchResponse with per-item results and aggregate stats
        """
        from ..middlewares.batch.context import BatchPipelineContext

        context = BatchPipelineContext(
            batch_request=batch_request,
            batch_items=list(batch_request.items),
            batch_size=len(batch_request.items),
            batch_tenant_id=batch_request.tenant_id,
            fail_fast=batch_request.fail_fast,
            deduplicate=batch_request.deduplicate,
        )

        try:
            if self._chain_head:
                context = await self._chain_head.process(context)

            context.finalize()

            response = context.to_batch_response()
            async with self._metrics_lock:
                self._metrics["batches_processed"] += 1
                self._metrics["total_items_processed"] += len(batch_request.items)
                self._metrics["total_latency_ms"] += context.batch_latency_ms

            return response

        except BATCH_PIPELINE_ERRORS as e:
            async with self._metrics_lock:
                self._metrics["batches_failed"] += 1
            logger.error(
                f"Batch pipeline error: {e}",
                batch_id=batch_request.batch_id,
                item_count=len(batch_request.items),
            )
            return BatchResponse.create_batch_error(
                batch_id=batch_request.batch_id,
                error_code="PIPELINE_ERROR",
                error_message="Internal batch processing error",
                item_count=len(batch_request.items),
            )

    def set_item_processor(
        self,
        processor: Callable[..., Awaitable[ValidationResult]],
    ) -> None:
        """Set the item processor for BatchProcessingMiddleware.

        This allows injecting a processor after construction, useful
        for the backward-compatible facade pattern.

        Args:
            processor: Async function to process individual items
        """
        from ..middlewares.batch.processing import BatchProcessingMiddleware

        self._item_processor = processor
        for mw in self._config.middlewares:
            if isinstance(mw, BatchProcessingMiddleware):
                mw.set_item_processor(processor)
                break

    def get_metrics(self) -> JSONDict:
        """Get router metrics.

        Returns:
            Dictionary with batch counts, item counts, avg latency
        """
        processed = self._metrics["batches_processed"]
        return {
            "batches_processed": processed,
            "batches_failed": self._metrics["batches_failed"],
            "total_items_processed": self._metrics["total_items_processed"],
            "avg_batch_latency_ms": (
                self._metrics["total_latency_ms"] / processed if processed > 0 else 0.0
            ),
            "pipeline_version": self._config.version,
            "middleware_count": len(self._config.middlewares),
        }

    def get_middleware_info(self) -> list[JSONDict]:
        """Get information about configured middlewares.

        Returns:
            List of middleware info dictionaries
        """
        return [
            {
                "name": mw.__class__.__name__,
                "enabled": mw.config.enabled,
                "timeout_ms": mw.config.timeout_ms,
            }
            for mw in self._config.middlewares
        ]
