"""
Unit tests for Batch Processor Metrics.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics
from enhanced_agent_bus.models import BatchItemStatus, BatchResponseStats


class TestBatchMetrics:
    def test_initialization(self):
        metrics = BatchMetrics()
        cumulative = metrics.get_cumulative_metrics()
        assert cumulative["total_batches"] == 0
        assert cumulative["total_items"] == 0
        assert cumulative["total_succeeded"] == 0

    def test_record_batch_processed(self):
        metrics = BatchMetrics()
        stats = BatchResponseStats(
            total_items=10, successful_items=8, failed_items=2, processing_time_ms=100.0
        )
        metrics.record_batch_processed(stats, 100.0)

        cumulative = metrics.get_cumulative_metrics()
        assert cumulative["total_batches"] == 1
        assert cumulative["total_items"] == 10
        assert cumulative["total_succeeded"] == 8
        assert cumulative["total_failed"] == 2

    def test_record_item_latency(self):
        metrics = BatchMetrics()
        metrics.record_item_latency(50.0)
        metrics.record_item_latency(150.0)
        # Internal buffer is private, but we can check via calculate_batch_stats later
        assert len(metrics._latencies) == 2

    def test_calculate_batch_stats(self):
        metrics = BatchMetrics()

        class MockResult:
            def __init__(self, status, latency_ms):
                self.status = status
                self.processing_time_ms = latency_ms

        results = [
            MockResult(BatchItemStatus.SUCCESS.value, 10.0),
            MockResult(BatchItemStatus.SUCCESS.value, 20.0),
            MockResult(BatchItemStatus.FAILED.value, 30.0),
            MockResult(BatchItemStatus.SKIPPED.value, 0.0),
        ]

        stats = metrics.calculate_batch_stats(
            total_items=4, results=results, processing_time_ms=50.0, deduplicated_count=1
        )

        assert stats.total_items == 4
        assert stats.successful_items == 2
        assert stats.failed_items == 1
        assert stats.skipped == 1
        assert stats.average_item_time_ms == 15.0  # (10+20+30+0)/4
        assert stats.p50_latency_ms == 20.0
        assert stats.deduplicated_count == 1

    def test_record_retry_and_slow_item(self):
        metrics = BatchMetrics()
        metrics.record_retry()
        metrics.record_slow_item()

        cumulative = metrics.get_cumulative_metrics()
        assert cumulative["total_retries"] == 1
        assert cumulative["total_slow_items"] == 1

    def test_reset(self):
        metrics = BatchMetrics()
        metrics.record_slow_item()
        metrics.reset()

        cumulative = metrics.get_cumulative_metrics()
        assert cumulative["total_slow_items"] == 0
        assert len(metrics._latencies) == 0
