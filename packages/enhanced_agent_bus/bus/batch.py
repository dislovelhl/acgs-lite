"""
Batch processing for EnhancedAgentBus.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..interfaces import ValidationStrategy
from ..models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    BatchRequest,
    BatchResponse,
    BatchResponseStats,
    MessageType,
)
from ..security_helpers import normalize_tenant_id

if TYPE_CHECKING:
    from ..maci_enforcement import MACIEnforcer, MACIRoleRegistry
    from ..message_processor import MessageProcessor

logger = get_logger(__name__)


class BatchProcessor:
    """
    Handles batch message processing for EnhancedAgentBus.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        processor: MessageProcessor,
        validator: ValidationStrategy,
        enable_maci: bool,
        maci_registry: MACIRoleRegistry | None,
        maci_enforcer: MACIEnforcer | None,
        maci_strict_mode: bool,
        metering_manager: object,
        metrics: JSONDict,
    ) -> None:
        """
        Initialize batch processor.

        Args:
            processor: MessageProcessor for individual message processing.
            validator: Validation strategy.
            enable_maci: Whether MACI is enabled.
            maci_registry: MACI role registry.
            maci_enforcer: MACI enforcer.
            maci_strict_mode: Whether MACI strict mode is enabled.
            metering_manager: Metering manager for recording batch operations.
            metrics: Metrics dictionary reference.
        """
        self._processor = processor
        self._validator = validator
        self._enable_maci = enable_maci
        self._maci_registry = maci_registry
        self._maci_enforcer = maci_enforcer
        self._maci_strict_mode = maci_strict_mode
        self._metering_manager = metering_manager
        self._metrics = metrics

    async def process_batch(self, batch_request: BatchRequest) -> BatchResponse:
        """
        Process a batch of messages through the agent bus with constitutional validation.

        This method provides high-throughput batch processing with:
        1. Tenant isolation validation across all batch items
        2. Constitutional compliance verification (hash: cdd01ef066bc6cf2)
        3. Parallel processing via BatchMessageProcessor
        4. Metering for batch operations
        5. MACI role validation support

        Performance targets:
        - P99 latency < 10ms for batch of 100 items
        - Throughput > 10,000 RPS in batch mode
        - Success rate > 99%

        Args:
            batch_request: BatchRequest containing multiple items to process

        Returns:
            BatchResponse with individual results and statistics

        Raises:
            ValueError: If batch request validation fails
        """
        start_time = time.perf_counter()

        # Lazy import to avoid circular dependency
        from ..batch_processor import BatchMessageProcessor

        # Step 1: Normalize tenant IDs in batch request
        batch_request.tenant_id = normalize_tenant_id(batch_request.tenant_id)
        for item in batch_request.items:
            item.tenant_id = normalize_tenant_id(item.tenant_id)

        # Step 2: Validate tenant consistency across batch
        if batch_request.tenant_id:
            tenant_errors = []
            for item in batch_request.items:
                if item.tenant_id and item.tenant_id != batch_request.tenant_id:
                    tenant_errors.append(
                        f"Item {item.request_id} tenant mismatch: "
                        f"expected {batch_request.tenant_id}, got {item.tenant_id}"
                    )

            if tenant_errors:
                return BatchResponse(
                    batch_id=batch_request.batch_id,
                    items=[],
                    stats=BatchResponseStats(
                        total_items=len(batch_request.items),
                        successful_items=0,
                        failed_items=len(batch_request.items),
                        skipped=0,
                        processing_time_ms=0.0,
                    ),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                    errors=["Tenant isolation violation: Not all items belong to the same tenant"]  # noqa: RUF005
                    + tenant_errors[:5],
                    completed_at=datetime.now(UTC),
                )

        # Step 3: Create BatchMessageProcessor
        batch_processor = BatchMessageProcessor(
            message_processor=self._processor,  # type: ignore[arg-type]
            max_concurrency=batch_request.options.get("max_concurrency", 100),
            enable_deduplication=batch_request.options.get("enable_deduplication", True),
            cache_results=batch_request.options.get("cache_results", True),
            validation_strategy=self._validator,
            enable_maci=self._enable_maci,
            maci_registry=self._maci_registry,
            maci_enforcer=self._maci_enforcer,
            maci_strict_mode=self._maci_strict_mode,
            item_timeout=batch_request.options.get("item_timeout", 30.0),
            slow_item_threshold=batch_request.options.get("slow_item_threshold", 5.0),
        )

        # Step 4: Process batch
        response = await batch_processor.process_batch(batch_request)

        # Step 5: Record metering for batch operation
        processing_time_ms = (time.perf_counter() - start_time) * 1000
        if self._metering_manager and self._metering_manager.is_enabled:
            self._record_batch_metering(batch_request, response, processing_time_ms)

        # Step 6: Update bus-level metrics
        self._metrics["messages_sent"] += response.stats.successful
        self._metrics["messages_failed"] += response.stats.failed
        self._metrics["sent"] += response.stats.successful
        self._metrics["failed"] += response.stats.failed

        logger.info(
            f"Batch processed: batch_id={batch_request.batch_id}, "
            f"items={response.stats.total_items}, "
            f"success_rate={response.success_rate:.1f}%, "
            f"p99_latency={response.stats.p99_latency_ms:.2f}ms, "
            f"total_time={processing_time_ms:.2f}ms"
        )

        return response

    def _record_batch_metering(
        self,
        batch_request: BatchRequest,
        response: BatchResponse,
        processing_time_ms: float,
    ) -> None:
        """
        Record metering data for batch operations.

        This is a fire-and-forget method that records batch processing
        metrics for billing and monitoring purposes.

        Args:
            batch_request: Original batch request
            response: Batch processing response
            processing_time_ms: Total processing time in milliseconds
        """
        if not self._metering_manager or not self._metering_manager.hooks:
            return

        try:
            metadata = {
                "batch_id": batch_request.batch_id,
                "total_items": response.stats.total_items,
                "successful": response.stats.successful,
                "failed": response.stats.failed,
                "skipped": response.stats.skipped,
                "success_rate": response.success_rate,
                "processing_time_ms": processing_time_ms,
                "p50_latency_ms": response.stats.p50_latency_ms,
                "p95_latency_ms": response.stats.p95_latency_ms,
                "p99_latency_ms": response.stats.p99_latency_ms,
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "batch_size": len(batch_request.items),
                "deduplication_enabled": batch_request.options.get("enable_deduplication", True),
            }

            if hasattr(self._metering_manager.hooks, "on_batch_processed"):
                self._metering_manager.hooks.on_batch_processed(
                    tenant_id=batch_request.tenant_id or "default",
                    batch_id=batch_request.batch_id,
                    total_items=response.stats.total_items,
                    successful=response.stats.successful,
                    failed=response.stats.failed,
                    processing_time_ms=processing_time_ms,
                    metadata=metadata,
                )
            else:
                # Fallback: Record as individual agent message events
                for item in batch_request.items:
                    message = AgentMessage(
                        from_agent=item.from_agent,
                        to_agent=item.to_agent or "",
                        message_type=(
                            MessageType(item.message_type)
                            if item.message_type
                            else MessageType.GOVERNANCE_REQUEST
                        ),
                        content=item.content,
                        tenant_id=item.tenant_id,
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    )

                    response_item = next(
                        (r for r in response.items if r.request_id == item.request_id),
                        None,
                    )

                    is_valid = response_item.valid if response_item else False
                    latency_ms = response_item.processing_time_ms if response_item else 0.0

                    self._metering_manager.record_agent_message(
                        message=message,
                        is_valid=is_valid,
                        latency_ms=latency_ms,
                    )

        except (
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
        ) as e:
            # Never let metering errors affect the critical path
            logger.warning(f"Batch metering recording failed: {e}")
