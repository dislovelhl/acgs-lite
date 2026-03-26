"""
Batch Pipeline Context for ACGS-2 Middleware.

Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field

from enhanced_agent_bus.models import AgentMessage

from ...batch_models import (
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
)
from ...pipeline.context import PipelineContext


@dataclass
class BatchPipelineContext(PipelineContext):
    """Extended pipeline context for batch processing.

    Contains all data necessary for batch request processing, including:
    - Batch request and response objects
    - Item lists for processing tracking
    - Batch-specific metadata (tenant, size, latency)
    - Error aggregation for failed items

    Constitutional Hash: 608508a9bd224290
    """

    # Override message with optional for batch contexts created without single message
    message: AgentMessage = field(
        default_factory=lambda: AgentMessage(
            message_id="batch",
            from_agent="batch_processor",
            content={},
        )
    )

    # Batch request/response objects
    batch_request: BatchRequest | None = None
    batch_response: BatchResponse | None = None

    # Item tracking
    batch_items: list[BatchRequestItem] = field(default_factory=list)
    processed_items: list[BatchResponseItem] = field(default_factory=list)
    failed_items: list[tuple[BatchRequestItem, str]] = field(default_factory=list)

    # Batch metadata
    batch_tenant_id: str | None = None
    batch_size: int = 0
    max_concurrency: int = 100
    batch_latency_ms: float = 0.0

    # Processing options
    fail_fast: bool = False
    deduplicate: bool = True

    # Auto-tuning data
    latency_history: list[float] = field(default_factory=list)
    current_batch_size: int = 100
    target_p99_ms: float = 100.0

    # Deduplication tracking
    deduplicated_count: int = 0
    seen_message_ids: set = field(default_factory=set)

    # Warnings collection
    warnings: list[str] = field(default_factory=list)

    # Governance and validation metadata
    metadata: dict = field(default_factory=dict)

    def add_processed_item(self, item: BatchResponseItem) -> None:
        """Add a successfully processed item."""
        self.processed_items.append(item)

    def add_failed_item(self, item: BatchRequestItem, error: str) -> None:
        """Add a failed item with error message."""
        self.failed_items.append((item, error))

    def record_latency(self, latency_ms: float) -> None:
        """Record item processing latency for auto-tuning."""
        self.latency_history.append(latency_ms)
        # Keep last 100 measurements
        if len(self.latency_history) > 100:
            self.latency_history = self.latency_history[-100:]

    def get_p99_latency(self) -> float:
        """Calculate P99 latency from history."""
        if not self.latency_history:
            return 0.0
        sorted_latencies = sorted(self.latency_history)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def should_adjust_batch_size(self) -> bool:
        """Check if enough data to adjust batch size."""
        return len(self.latency_history) >= 10

    def to_batch_response(self) -> BatchResponse:
        """Convert context to batch response."""
        if self.batch_response:
            return self.batch_response

        # Build response from processed items
        from ...batch_models import BatchResponseStats

        total_items = len(self.batch_items)
        successful = len([i for i in self.processed_items if i.success])
        failed = len(self.failed_items)

        stats = BatchResponseStats(
            total_items=total_items,
            successful_items=successful,
            failed_items=failed,
            skipped=total_items - successful - failed,
            deduplicated_count=self.deduplicated_count,
            processing_time_ms=self.batch_latency_ms,
        )

        self.batch_response = BatchResponse(
            batch_id=self.batch_request.batch_id if self.batch_request else "unknown",
            success=failed == 0,
            items=self.processed_items,
            stats=stats,
            errors=[err for _, err in self.failed_items],
        )

        return self.batch_response
