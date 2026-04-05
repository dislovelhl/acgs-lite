"""
Batch Metrics Middleware for ACGS-2 Pipeline.

Records batch-level metrics.
Extracted from: batch_processor_infra/metrics.py

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time
from typing import cast

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_BATCH_METRICS_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

from ...batch_models import BatchResponseItem
from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchMetricsException


class BatchMetricsMiddleware(BaseMiddleware):
    """Records batch-level metrics.

    Collects and emits comprehensive metrics for batch processing:
    - Batch size and throughput
    - Success/failure rates
    - Latency percentiles
    - Per-item metrics
    - Tenant-level aggregations

    Example:
        middleware = BatchMetricsMiddleware(
            metrics_registry=my_metrics_registry,
        )
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        metrics_registry: object | None = None,
    ):
        """Initialize batch metrics middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
            metrics_registry: Optional metrics registry for recording
        """
        super().__init__(config)
        self._metrics_registry = metrics_registry
        self._recorded_metrics: list[JSONDict] = []
        self._background_tasks: set[asyncio.Task] = set()

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process batch metrics recording.

        Steps:
        1. Record batch-level metrics
        2. Record per-item metrics
        3. Emit to registry (async, non-blocking)
        4. Update context with metrics summary

        Args:
            context: Batch pipeline context with results

        Returns:
            Context with metrics recorded

        Raises:
            BatchMetricsException: If metrics recording fails
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        try:
            # Record batch-level metrics
            self._record_batch_metrics(context)

            # Record per-item metrics
            for item in context.processed_items:
                self._record_item_metrics(item, context)

            # Emit metrics asynchronously (fire-and-forget)
            if self._metrics_registry and self.config.metrics_enabled:
                task = asyncio.create_task(self._emit_metrics(context))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

        except _BATCH_METRICS_OPERATION_ERRORS as e:
            error_msg = f"Metrics recording failed: {e}"
            if self.config.fail_closed:
                raise BatchMetricsException(
                    message=error_msg,
                ) from e
            # Non-fatal: just log warning
            context.warnings.append(error_msg)

        # Record metrics collection time
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

        context = await self._call_next(context)
        return context

    def _record_batch_metrics(self, context: BatchPipelineContext) -> None:
        """Record batch-level metrics.

        Args:
            context: Batch pipeline context
        """
        tenant_id = context.batch_tenant_id or "default"
        batch_id = context.batch_request.batch_id if context.batch_request else "unknown"

        total_items = len(context.batch_items)
        processed = len(context.processed_items)
        failed = len(context.failed_items)
        deduplicated = context.deduplicated_count

        # Calculate success rate
        success_rate = 0.0
        if processed > 0:
            successful = len([i for i in context.processed_items if i.success])
            success_rate = successful / processed

        metrics = {
            "metric_type": "batch_summary",
            "timestamp": time.time(),
            "tenant_id": tenant_id,
            "batch_id": batch_id,
            "total_items": total_items,
            "processed_items": processed,
            "failed_items": failed,
            "deduplicated_count": deduplicated,
            "success_rate": success_rate,
            "batch_latency_ms": context.batch_latency_ms,
            "max_concurrency": context.max_concurrency,
            "impact_score": context.impact_score,
        }

        self._recorded_metrics.append(metrics)

    def _record_item_metrics(
        self,
        item: BatchResponseItem,
        context: BatchPipelineContext,
    ) -> None:
        """Record metrics for a single item.

        Args:
            item: Batch response item
            context: Batch pipeline context
        """
        tenant_id = context.batch_tenant_id or "default"

        metrics = {
            "metric_type": "item_detail",
            "timestamp": time.time(),
            "tenant_id": tenant_id,
            "request_id": item.request_id,
            "status": item.status,
            "valid": item.valid,
            "processing_time_ms": item.processing_time_ms,
            "error_code": item.error_code,
            "constitutional_validated": item.constitutional_validated,
        }

        self._recorded_metrics.append(metrics)

    async def _emit_metrics(self, context: BatchPipelineContext) -> None:
        """Emit metrics to registry.

        Args:
            context: Batch pipeline context
        """
        if not self._metrics_registry:
            return

        try:
            # Emit batch summary
            summary_metrics = [
                m for m in self._recorded_metrics if m.get("metric_type") == "batch_summary"
            ]
            for metric in summary_metrics:
                await self._emit_metric("batch_processing", metric)

            # Emit item metrics (sampled if too many)
            item_metrics = [
                m for m in self._recorded_metrics if m.get("metric_type") == "item_detail"
            ]
            sample_rate = 1.0
            if len(item_metrics) > 100:
                sample_rate = 100.0 / len(item_metrics)

            import random

            for metric in item_metrics:
                if random.random() <= sample_rate:
                    await self._emit_metric("batch_item_processing", metric)

        except _BATCH_METRICS_OPERATION_ERRORS as e:
            # Metrics emission failure is non-fatal
            logger.debug("Metrics emission failed: %s", e)

    async def _emit_metric(self, name: str, data: JSONDict) -> None:
        """Emit a single metric.

        Args:
            name: Metric name
            data: Metric data
        """
        if not self._metrics_registry:
            return

        try:
            # Try different registry interfaces
            if hasattr(self._metrics_registry, "emit"):
                await self._metrics_registry.emit(name, data)
            elif hasattr(self._metrics_registry, "record"):
                await self._metrics_registry.record(name, data)
            elif hasattr(self._metrics_registry, "gauge"):
                self._metrics_registry.gauge(name, data.get("value", 1), data)
            elif hasattr(self._metrics_registry, "counter"):
                self._metrics_registry.counter(name, 1, data)
        except _BATCH_METRICS_OPERATION_ERRORS as e:
            # Emission failure is non-fatal
            logger.debug("Metrics emission failed: %s", e)

    @property
    def recorded_metrics(self) -> list[JSONDict]:
        """Return recorded metrics (copy)."""
        return self._recorded_metrics.copy()

    def clear_recorded_metrics(self) -> None:
        """Clear recorded metrics buffer."""
        self._recorded_metrics.clear()

    def get_summary(self) -> JSONDict:
        """Get metrics summary.

        Returns:
            Dictionary with metrics summary
        """
        batch_metrics = [
            m for m in self._recorded_metrics if m.get("metric_type") == "batch_summary"
        ]
        item_metrics = [m for m in self._recorded_metrics if m.get("metric_type") == "item_detail"]

        return {
            "total_metrics": len(self._recorded_metrics),
            "batch_summaries": len(batch_metrics),
            "item_details": len(item_metrics),
            "tenants": list(set(m.get("tenant_id", "unknown") for m in batch_metrics)),
        }
