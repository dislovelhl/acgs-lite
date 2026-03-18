"""
Metrics Collection for Batch Processing in ACGS-2.

Constitutional Hash: cdd01ef066bc6cf2
"""

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, BatchResponseStats
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
try:
    from acgs2_perf import compute_percentiles

    PERF_KERNELS_AVAILABLE = True
except ImportError:
    PERF_KERNELS_AVAILABLE = False


class BatchMetricsState:
    total_batches: int = 0
    total_items: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    total_timed_out: int = 0
    total_slow_items: int = 0
    total_constitutional_violations: int = 0
    total_maci_violations: int = 0
    total_retries: int = 0


class BatchMetrics:
    def __init__(self):
        self._state = BatchMetricsState()
        self._latencies: list[float] = []
        self._batch_durations: list[float] = []

    def record_batch_processed(self, stats: BatchResponseStats, duration_ms: float) -> None:
        self._state.total_batches += 1
        self._state.total_items += stats.total_items
        self._state.total_succeeded += stats.successful_items
        self._state.total_failed += stats.failed_items
        self._state.total_timed_out += getattr(stats, "timeout_count", 0)
        self._state.total_constitutional_violations += getattr(
            stats, "constitutional_violations", 0
        )
        self._state.total_maci_violations += getattr(stats, "maci_violations", 0)

        self._batch_durations.append(duration_ms / 1000.0)

    def record_item_latency(self, latency_ms: float) -> None:
        self._latencies.append(latency_ms)
        if len(self._latencies) > 10000:
            self._latencies = self._latencies[-10000:]

    def record_retry(self) -> None:
        self._state.total_retries += 1

    def record_slow_item(self) -> None:
        self._state.total_slow_items += 1

    def calculate_batch_stats(
        self,
        total_items: int,
        results: list,
        processing_time_ms: float,
        deduplicated_count: int = 0,
    ) -> BatchResponseStats:
        from enhanced_agent_bus.models import BatchItemStatus

        successful = sum(1 for r in results if r.status == BatchItemStatus.SUCCESS.value)
        failed = sum(1 for r in results if r.status == BatchItemStatus.FAILED.value)
        skipped = sum(1 for r in results if r.status == BatchItemStatus.SKIPPED.value)

        item_latencies = [
            r.processing_time_ms
            for r in results
            if hasattr(r, "processing_time_ms")
            and r.processing_time_ms is not None
            and r.processing_time_ms >= 0
        ]

        p50 = p95 = p99 = avg = 0.0
        if item_latencies:
            if PERF_KERNELS_AVAILABLE:
                percentiles = compute_percentiles(item_latencies, [50.0, 95.0, 99.0])
                p50, p95, p99 = percentiles[0], percentiles[1], percentiles[2]
            else:
                item_latencies.sort()
                n = len(item_latencies)
                p50 = item_latencies[int(n * 0.50)]
                p95 = item_latencies[int(n * 0.95)] if n > 1 else p50
                p99 = item_latencies[int(n * 0.99)] if n > 1 else p50

            avg = sum(item_latencies) / len(item_latencies)

        return BatchResponseStats(
            total_items=total_items,
            successful_items=successful,
            failed_items=failed,
            skipped=skipped,
            processing_time_ms=processing_time_ms,
            average_item_time_ms=avg,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            deduplicated_count=deduplicated_count,
        )

    def get_cumulative_metrics(self) -> JSONDict:
        total = self._state.total_succeeded + self._state.total_failed
        success_rate = (self._state.total_succeeded / total * 100) if total > 0 else 0.0

        return {
            "total_batches": self._state.total_batches,
            "total_items": self._state.total_items,
            "total_succeeded": self._state.total_succeeded,
            "total_items_succeeded": self._state.total_succeeded,  # Alias for test compatibility
            "total_failed": self._state.total_failed,
            "total_items_failed": self._state.total_failed,  # Alias for test compatibility
            "total_errors": self._state.total_failed,  # Alias for test compatibility
            "total_retries": self._state.total_retries,
            "success_rate": success_rate,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "total_constitutional_violations": self._state.total_constitutional_violations,
            "total_maci_violations": self._state.total_maci_violations,
            "total_slow_items": self._state.total_slow_items,
        }

    def reset(self) -> None:
        self._state = BatchMetricsState()
        self._latencies.clear()
        self._batch_durations.clear()
