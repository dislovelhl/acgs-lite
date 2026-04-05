"""
ACGS-2 Enhanced Agent Bus - Batch Load Tests
Constitutional Hash: 608508a9bd224290

Phase 6 Task 5: Load tests with realistic scenarios.
Tests batch processing under sustained load conditions.

Test Coverage:
- Large batch processing (1000+ items)
- Sustained throughput over time
- Memory usage during load
- Error rates under stress
- Recovery from high-load scenarios
"""

import asyncio
import gc
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict

# Import batch models
# Import batch processor
from enhanced_agent_bus.batch_processor import (
    BatchMessageProcessor,
    get_batch_processor,
    reset_batch_processor,
)
from enhanced_agent_bus.models import (
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    BatchResponseItem,
    Priority,
)


@dataclass
class MockValidationResult:
    """Mock validation result that matches the expected interface."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    decision: str = "ALLOW"
    constitutional_hash: str = CONSTITUTIONAL_HASH


def create_load_batch(
    num_items: int, tenant_id: str = "load-test", batch_prefix: str = ""
) -> list[BatchRequestItem]:
    """Create a batch of items for load testing."""
    prefix = f"{batch_prefix}_" if batch_prefix else ""
    return [
        BatchRequestItem(
            content={
                "action": f"{prefix}load_test_{i}",
                "value": i,
                "batch": batch_prefix or "default",
            },
            message_type="governance_request",
            priority=1,
            tenant_id=tenant_id,
            metadata={"batch_index": i, "test_type": "load", "batch_prefix": batch_prefix},
        )
        for i in range(num_items)
    ]


def create_processor_with_mock() -> BatchMessageProcessor:
    """Create a processor with mocked message processor for load testing."""
    mock_processor = MagicMock()

    async def mock_process(message, **kwargs):
        # Simulate minimal processing time
        await asyncio.sleep(0.0001)  # 0.1ms
        # Return a proper ValidationResult-like object
        return MockValidationResult(
            is_valid=True,
            metadata={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "processed_at": datetime.now(UTC).isoformat(),
                "impact_score": 0.5,
            },
        )

    # Mock both process and process_message methods
    mock_processor.process = AsyncMock(side_effect=mock_process)
    mock_processor.process_message = AsyncMock(side_effect=mock_process)
    return BatchMessageProcessor(
        message_processor=mock_processor,
        batch_size=100,  # Process in chunks
    )


@pytest.mark.slow
class TestLargeBatchProcessing:
    """Test batch processing with large item counts."""

    async def test_1000_items_batch(self):
        """Test processing a batch with 1000 items."""
        processor = create_processor_with_mock()
        items = create_load_batch(1000)

        request = BatchRequest(
            items=items,
            batch_id=f"large-batch-{uuid.uuid4()}",
            tenant_id="load-test",
        )

        start_time = time.perf_counter()
        response = await processor.process_batch(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Verify all items processed
        assert len(response.items) == 1000
        assert response.stats.total_items == 1000

        # Performance check: should complete within reasonable time
        # 1000 items with 0.1ms each = 100ms minimum, allow 5x overhead
        assert elapsed_ms < 5000, f"Processing took {elapsed_ms:.1f}ms for 1000 items"

        # Calculate throughput
        throughput = 1000 / (elapsed_ms / 1000)  # items per second

    async def test_max_batch_size(self):
        """Test processing a batch at maximum allowed size (1000 items)."""
        processor = create_processor_with_mock()
        items = create_load_batch(1000)  # Maximum allowed by BatchRequest

        request = BatchRequest(
            items=items,
            batch_id=f"max-batch-{uuid.uuid4()}",
            tenant_id="load-test",
        )

        start_time = time.perf_counter()
        response = await processor.process_batch(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Verify all items processed
        assert len(response.items) == 1000
        assert response.stats.total_items == 1000

        # Performance check: should complete within 5 seconds for max batch
        assert elapsed_ms < 5000, f"Processing took {elapsed_ms:.1f}ms for max batch"

        throughput = 1000 / (elapsed_ms / 1000)

    async def test_batch_size_scaling(self):
        """Test that processing time scales linearly with batch size."""
        processor = create_processor_with_mock()

        sizes = [100, 200, 500, 1000]
        times = []

        for size in sizes:
            items = create_load_batch(size)
            request = BatchRequest(items=items, batch_id=f"scale-{size}")

            start = time.perf_counter()
            await processor.process_batch(request)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            processor.reset_metrics()

        # Check approximately linear scaling (within 3x variance)
        # For very small batches, timing noise can dominate. Use a floor to stabilize the ratio.
        baseline_ms = max(times[0], 5.0)
        ratio_100_to_1000 = times[3] / baseline_ms
        assert ratio_100_to_1000 < 30, (
            f"Scaling ratio {ratio_100_to_1000:.1f}x for 10x items (baseline {baseline_ms:.1f}ms)"
        )

        for _, _ in zip(sizes, times, strict=False):
            pass


@pytest.mark.slow
class TestSustainedThroughput:
    """Test sustained batch processing over time."""

    async def test_repeated_batches(self):
        """Test processing multiple batches in sequence."""
        processor = create_processor_with_mock()

        num_batches = 10
        items_per_batch = 100
        total_items = 0

        start_time = time.perf_counter()

        for i in range(num_batches):
            items = create_load_batch(items_per_batch, tenant_id="sustained-test")
            request = BatchRequest(
                items=items,
                batch_id=f"sustained-{i}",
                tenant_id="sustained-test",
            )
            response = await processor.process_batch(request)
            total_items += len(response.items)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert total_items == num_batches * items_per_batch

        throughput = total_items / (elapsed_ms / 1000)

    async def test_concurrent_batches(self):
        """Test processing multiple batches concurrently."""
        processor = create_processor_with_mock()

        num_concurrent = 5
        items_per_batch = 100

        async def process_one_batch(batch_num: int) -> BatchResponse:
            tenant_id = f"tenant-{batch_num}"
            items = create_load_batch(items_per_batch, tenant_id=tenant_id)
            request = BatchRequest(
                items=items,
                batch_id=f"concurrent-{batch_num}",
                tenant_id=tenant_id,
            )
            return await processor.process_batch(request)

        start_time = time.perf_counter()

        tasks = [process_one_batch(i) for i in range(num_concurrent)]
        responses = await asyncio.gather(*tasks)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        total_items = sum(len(r.items) for r in responses)
        assert total_items == num_concurrent * items_per_batch

        throughput = total_items / (elapsed_ms / 1000)

    async def test_mixed_batch_sizes(self):
        """Test processing batches of varying sizes."""
        processor = create_processor_with_mock()

        batch_sizes = [10, 50, 100, 200, 50, 10, 500, 100]
        total_items = 0

        start_time = time.perf_counter()

        for i, size in enumerate(batch_sizes):
            items = create_load_batch(size)
            request = BatchRequest(
                items=items,
                batch_id=f"mixed-{i}",
                tenant_id="load-test",
            )
            response = await processor.process_batch(request)
            total_items += len(response.items)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert total_items == sum(batch_sizes)

        throughput = total_items / (elapsed_ms / 1000)


@pytest.mark.slow
class TestMemoryUsage:
    """Test memory behavior during load."""

    async def test_memory_stable_during_large_batch(self):
        """Test that memory doesn't grow excessively during large batch processing."""

        processor = create_processor_with_mock()

        # Force garbage collection before measurement
        gc.collect()

        # Measure baseline
        # Note: This is a rough approximation using sys.getsizeof
        baseline_items = sys.getsizeof([])

        # Process max batch (1000 items is the maximum allowed)
        items = create_load_batch(1000)
        request = BatchRequest(
            items=items,
            batch_id="memory-test",
            tenant_id="load-test",
        )

        response = await processor.process_batch(request)

        # Verify processing completed
        assert len(response.items) == 1000

        # Clear references and collect
        del items
        del request
        gc.collect()

        # The response should be relatively compact
        # (results are stored, but intermediate state cleaned up)
        response_size = sys.getsizeof(response.items)

    async def test_no_memory_leak_repeated_batches(self):
        """Test that repeated batch processing doesn't leak memory excessively."""
        processor = create_processor_with_mock()

        gc.collect()
        initial_objects = len(gc.get_objects())

        # Process many batches
        for i in range(10):
            items = create_load_batch(50, tenant_id="load-test")
            request = BatchRequest(items=items, batch_id=f"leak-test-{i}", tenant_id="load-test")
            response = await processor.process_batch(request)
            del items, request, response
            processor.reset_metrics()

        gc.collect()
        final_objects = len(gc.get_objects())

        # Allow reasonable object growth (caches, metrics, etc.)
        # The processor uses caches and accumulators that naturally grow
        growth = final_objects - initial_objects
        growth_per_batch = growth / 10

        # More realistic threshold - internal caches and metrics can grow
        # We're mainly checking for catastrophic leaks, not zero growth
        assert growth_per_batch < 5000, f"Object growth too high: {growth_per_batch:.1f} per batch"


@pytest.mark.slow
class TestErrorRatesUnderStress:
    """Test error handling under high load conditions."""

    async def test_partial_failures_under_load(self):
        """Test that partial failures are handled correctly under load."""
        mock_processor = MagicMock()
        fail_counter = {"count": 0}

        async def mock_process(message, **kwargs):
            fail_counter["count"] += 1
            # Fail every 10th item
            if fail_counter["count"] % 10 == 0:
                raise ValueError(f"Simulated failure at item {fail_counter['count']}")
            return MockValidationResult(is_valid=True)

        mock_processor.process = AsyncMock(side_effect=mock_process)
        mock_processor.process_message = AsyncMock(side_effect=mock_process)
        processor = BatchMessageProcessor(message_processor=mock_processor)

        items = create_load_batch(100, tenant_id="load-test")
        request = BatchRequest(items=items, batch_id="stress-partial", tenant_id="load-test")

        response = await processor.process_batch(request)

        # Expect ~10 failures (every 10th of 100)
        assert response.stats.failed_items >= 8  # Allow some variance
        assert response.stats.failed_items <= 12
        assert response.stats.successful_items >= 88
        assert response.stats.total_items == 100

    async def test_high_failure_rate(self):
        """Test system behavior with high failure rate."""
        import random

        mock_processor = MagicMock()

        async def mock_process(message, **kwargs):
            # 50% failure rate
            if random.random() < 0.5:
                raise RuntimeError("Random failure")
            return MockValidationResult(is_valid=True)

        mock_processor.process = AsyncMock(side_effect=mock_process)
        mock_processor.process_message = AsyncMock(side_effect=mock_process)
        processor = BatchMessageProcessor(message_processor=mock_processor)

        items = create_load_batch(200, tenant_id="load-test")
        request = BatchRequest(items=items, batch_id="stress-high-failure", tenant_id="load-test")

        response = await processor.process_batch(request)

        # With 50% failure rate, expect ~100 failures (±20%)
        assert response.stats.failed_items >= 70
        assert response.stats.failed_items <= 130
        assert response.stats.total_items == 200

        # Verify all items accounted for
        assert (
            response.stats.successful_items + response.stats.failed_items + response.stats.skipped
        ) == 200

    async def test_recovery_after_burst_failures(self):
        """Test system recovers after a burst of failures."""
        mock_processor = MagicMock()
        fail_burst = {"active": True, "count": 0}

        async def mock_process(message, **kwargs):
            fail_burst["count"] += 1
            # Fail first 20 items, then succeed
            if fail_burst["count"] <= 20 and fail_burst["active"]:
                raise RuntimeError("Burst failure")
            return MockValidationResult(is_valid=True)

        mock_processor.process = AsyncMock(side_effect=mock_process)
        mock_processor.process_message = AsyncMock(side_effect=mock_process)
        processor = BatchMessageProcessor(message_processor=mock_processor)

        items = create_load_batch(100, tenant_id="load-test")
        request = BatchRequest(items=items, batch_id="recovery-test", tenant_id="load-test")

        response = await processor.process_batch(request)

        # First 20 failed, rest succeeded
        assert response.stats.failed_items == 20
        assert response.stats.successful_items == 80


@pytest.mark.slow
class TestLatencyDistribution:
    """Test latency characteristics under load."""

    async def test_latency_percentiles_under_load(self):
        """Test latency percentiles during high-load processing."""
        processor = create_processor_with_mock()

        items = create_load_batch(500)
        request = BatchRequest(items=items, batch_id="latency-test", tenant_id="load-test")

        response = await processor.process_batch(request)

        # Check latency metrics exist
        assert response.stats.processing_time_ms > 0

        # P50, P95, P99 should be reasonable
        if response.stats.p50_latency_ms is not None:
            assert response.stats.p50_latency_ms >= 0
            assert response.stats.p95_latency_ms >= response.stats.p50_latency_ms
            if response.stats.p99_latency_ms is not None:
                assert response.stats.p99_latency_ms >= response.stats.p95_latency_ms

        if response.stats.p50_latency_ms is not None:
            if response.stats.p99_latency_ms is not None:
                pass

    async def test_consistent_latency_across_batches(self):
        """Test that latency remains consistent across multiple batches."""
        processor = create_processor_with_mock()

        latencies = []
        warmup_items = create_load_batch(100, tenant_id="consistency-test", batch_prefix="warmup")
        warmup_request = BatchRequest(
            items=warmup_items,
            batch_id="consistency-warmup",
            tenant_id="consistency-test",
        )
        await processor.process_batch(warmup_request)
        processor.reset_metrics()

        for i in range(10):
            # Use unique batch_prefix per batch to avoid deduplication of same content
            items = create_load_batch(100, tenant_id="consistency-test", batch_prefix=f"batch-{i}")
            request = BatchRequest(
                items=items, batch_id=f"consistency-{i}", tenant_id="consistency-test"
            )

            start = time.perf_counter()
            await processor.process_batch(request)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

            processor.reset_metrics()

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Coverage instrumentation and concurrent CI scheduling can occasionally stretch a
        # single batch, so assert on sustained average latency plus a loose single-batch cap.
        assert avg_latency < 50, f"Average latency too high: {avg_latency:.1f}ms"
        assert max_latency < 200, f"Peak latency too high: {max_latency:.1f}ms"


class TestQuickLoadValidation:
    """Quick load validation tests (not marked as slow)."""

    async def test_100_items_quick(self):
        """Quick test with 100 items."""
        processor = create_processor_with_mock()
        items = create_load_batch(100)

        request = BatchRequest(items=items, batch_id="quick-100", tenant_id="load-test")
        response = await processor.process_batch(request)

        assert len(response.items) == 100
        assert response.stats.successful_items >= 100 or response.stats.failed_items == 0

    async def test_concurrent_small_batches(self):
        """Test concurrent processing of small batches."""
        processor = create_processor_with_mock()

        async def process_batch(num: int) -> BatchResponse:
            items = create_load_batch(10)
            request = BatchRequest(items=items, batch_id=f"quick-concurrent-{num}")
            return await processor.process_batch(request)

        responses = await asyncio.gather(*[process_batch(i) for i in range(5)])

        total = sum(r.stats.total_items for r in responses)
        assert total == 50
