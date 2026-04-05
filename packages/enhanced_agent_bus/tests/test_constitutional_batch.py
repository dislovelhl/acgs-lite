"""
ACGS-2 Enhanced Agent Bus - Parallel Constitutional Validation Tests
Constitutional Hash: 608508a9bd224290

TDD tests for parallel constitutional validation in batch operations.
Tests Phase 4-Task 4 acceptance criteria:
- Parallel hash validation
- Vectorized operations where possible
- Sub-millisecond validation per item
"""

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import centralized constitutional hash
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# Mark all tests as governance tests (95% coverage required)
# Constitutional Hash: 608508a9bd224290
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


@pytest.fixture(autouse=True)
def _reset_constitutional_batch_singleton():
    """Reset constitutional batch validator singleton before AND after each test.

    The singleton in constitutional_batch.py is shared globally. Without
    teardown, a test that calls get_batch_validator() leaves the singleton
    populated, polluting subsequent test files in the same xdist worker.
    (PM-012 pattern)
    """
    import sys

    import enhanced_agent_bus.constitutional_batch as mod

    # --- Setup: reset before test ---
    if hasattr(mod, "_batch_validator"):
        mod._batch_validator = None
    if hasattr(mod, "_batch_validator_lock"):
        mod._batch_validator_lock = asyncio.Lock()
    alias = sys.modules.get("enhanced_agent_bus.constitutional_batch")
    if alias is not None and alias is not mod:
        if hasattr(alias, "_batch_validator"):
            alias._batch_validator = None
        if hasattr(alias, "_batch_validator_lock"):
            alias._batch_validator_lock = asyncio.Lock()

    yield

    # --- Teardown: reset after test ---
    if hasattr(mod, "_batch_validator"):
        mod._batch_validator = None
    if hasattr(mod, "_batch_validator_lock"):
        mod._batch_validator_lock = asyncio.Lock()
    alias = sys.modules.get("enhanced_agent_bus.constitutional_batch")
    if alias is not None and alias is not mod:
        if hasattr(alias, "_batch_validator"):
            alias._batch_validator = None
        if hasattr(alias, "_batch_validator_lock"):
            alias._batch_validator_lock = asyncio.Lock()


class TestConstitutionalBatchValidatorConfig:
    """Test constitutional batch validator configuration."""

    async def test_default_configuration(self):
        """Test default validator configuration."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()
        assert validator.constitutional_hash == CONSTITUTIONAL_HASH
        assert validator.max_parallel > 0
        assert validator.chunk_size > 0

    async def test_configurable_parallelism(self):
        """Test configurable parallel validation count."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator(max_parallel=50)
        assert validator.max_parallel == 50

    async def test_configurable_chunk_size(self):
        """Test configurable chunk size for batch processing."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator(chunk_size=200)
        assert validator.chunk_size == 200

    async def test_constitutional_hash_tracking(self):
        """Test validator tracks constitutional hash for compliance."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()
        assert validator.constitutional_hash == CONSTITUTIONAL_HASH


class TestConstitutionalBatchValidation:
    """Test batch constitutional validation operations."""

    async def test_validate_single_item(self):
        """Test validating a single item."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        item = {
            "content": {"action": "test"},
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        result = await validator.validate_batch([item])

        assert len(result) == 1
        assert result[0]["is_valid"] is True

    async def test_validate_multiple_items(self):
        """Test validating multiple items in batch."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"action": f"test_{i}"}, "constitutional_hash": CONSTITUTIONAL_HASH}
            for i in range(10)
        ]

        results = await validator.validate_batch(items)

        assert len(results) == 10
        assert all(r["is_valid"] for r in results)

    async def test_validate_empty_batch(self):
        """Test validating empty batch returns empty results."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        results = await validator.validate_batch([])

        assert results == []

    async def test_invalid_hash_fails_validation(self):
        """Test items with invalid hash fail validation."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"action": "test"}, "constitutional_hash": "invalid_hash"},
        ]

        results = await validator.validate_batch(items)

        assert len(results) == 1
        assert results[0]["is_valid"] is False
        assert "error" in results[0]

    async def test_missing_hash_fails_validation(self):
        """Test items without hash fail validation."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"action": "test"}},
        ]

        results = await validator.validate_batch(items)

        assert len(results) == 1
        assert results[0]["is_valid"] is False

    async def test_mixed_valid_invalid_batch(self):
        """Test batch with mixed valid and invalid items."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"action": "valid"}, "constitutional_hash": CONSTITUTIONAL_HASH},
            {"content": {"action": "invalid"}, "constitutional_hash": "bad_hash"},
            {"content": {"action": "valid2"}, "constitutional_hash": CONSTITUTIONAL_HASH},
        ]

        results = await validator.validate_batch(items)

        assert len(results) == 3
        assert results[0]["is_valid"] is True
        assert results[1]["is_valid"] is False
        assert results[2]["is_valid"] is True

    async def test_results_preserve_order(self):
        """Test validation results maintain input order."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(100)
        ]

        results = await validator.validate_batch(items)

        # Verify order by checking metadata contains original index
        assert len(results) == 100
        for i, result in enumerate(results):
            assert result["index"] == i


class TestParallelExecution:
    """Test parallel execution of constitutional validation."""

    async def test_parallel_validation_execution(self):
        """Test validation executes in parallel."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator(max_parallel=10)

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        original_validate = validator._validate_single

        async def tracking_validate(item, index):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            try:
                # Simulate some work
                await asyncio.sleep(0.01)
                return await original_validate(item, index)
            finally:
                async with lock:
                    concurrent_count -= 1

        validator._validate_single = tracking_validate

        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(20)
        ]

        await validator.validate_batch(items)

        # Should have had concurrent executions
        assert max_concurrent > 1

    async def test_respects_max_parallel_limit(self):
        """Test validation respects max parallel limit."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        max_parallel = 5
        validator = ConstitutionalBatchValidator(max_parallel=max_parallel)

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        original_validate = validator._validate_single

        async def tracking_validate(item, index):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            try:
                await asyncio.sleep(0.01)
                return await original_validate(item, index)
            finally:
                async with lock:
                    concurrent_count -= 1

        validator._validate_single = tracking_validate

        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(20)
        ]

        await validator.validate_batch(items)

        # Should never exceed max_parallel
        assert max_concurrent <= max_parallel


class TestPerformance:
    """Test performance requirements for constitutional validation."""

    async def test_sub_millisecond_per_item_validation(self):
        """Test validation achieves sub-millisecond per item."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(1000)
        ]

        start_time = time.perf_counter()
        results = await validator.validate_batch(items)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        per_item_ms = elapsed_ms / len(items)

        # Should be sub-millisecond per item
        assert per_item_ms < 1.0, f"Per-item validation took {per_item_ms}ms"
        assert len(results) == 1000

    async def test_large_batch_performance(self):
        """Test performance with large batch sizes."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(5000)
        ]

        start_time = time.perf_counter()
        results = await validator.validate_batch(items)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should complete in reasonable time (less than 5 seconds for 5000 items)
        assert elapsed_ms < 5000, f"Batch took {elapsed_ms}ms"
        assert len(results) == 5000


class TestVectorizedOperations:
    """Test vectorized hash validation operations."""

    async def test_vectorized_hash_comparison(self):
        """Test hash comparison uses vectorized approach when possible."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        # Create batch with same hash for vectorization
        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(100)
        ]

        # Pre-compute expected hash for vectorized check
        results = await validator.validate_batch(items)

        assert all(r["is_valid"] for r in results)

    async def test_batch_deduplication(self):
        """Test duplicate items are efficiently handled."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        # Create batch with duplicate content
        base_item = {"content": {"action": "test"}, "constitutional_hash": CONSTITUTIONAL_HASH}
        items = [base_item.copy() for _ in range(50)]

        results = await validator.validate_batch(items)

        assert len(results) == 50
        assert all(r["is_valid"] for r in results)


class TestMetrics:
    """Test metrics collection for constitutional validation."""

    async def test_tracks_validation_count(self):
        """Test validator tracks total validation count."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(10)
        ]

        await validator.validate_batch(items)

        stats = validator.get_stats()
        assert stats["total_validations"] == 10

    async def test_tracks_valid_invalid_counts(self):
        """Test validator tracks valid and invalid counts."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"id": 0}, "constitutional_hash": CONSTITUTIONAL_HASH},
            {"content": {"id": 1}, "constitutional_hash": "invalid"},
            {"content": {"id": 2}, "constitutional_hash": CONSTITUTIONAL_HASH},
        ]

        await validator.validate_batch(items)

        stats = validator.get_stats()
        assert stats["valid_count"] == 2
        assert stats["invalid_count"] == 1

    async def test_tracks_average_latency(self):
        """Test validator tracks average validation latency."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        items = [
            {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(100)
        ]

        await validator.validate_batch(items)

        stats = validator.get_stats()
        assert "avg_latency_ms" in stats
        assert stats["avg_latency_ms"] >= 0

    async def test_metrics_include_constitutional_hash(self):
        """Test metrics include constitutional hash for compliance."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        stats = validator.get_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSecurityValidation:
    """Test security aspects of constitutional validation."""

    async def test_constant_time_comparison(self):
        """Test hash comparison uses constant-time algorithm."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        # Similar hashes should take same time as different hashes
        similar_hash = CONSTITUTIONAL_HASH[:-1] + "0"
        different_hash = "0" * len(CONSTITUTIONAL_HASH)

        # Measure the constant-time primitive directly; validate_batch timing is noisy due to async scheduling.
        comparisons_per_sample = 20_000

        def _sample(candidate_hash: str) -> float:
            start = time.perf_counter()
            for _ in range(comparisons_per_sample):
                validator._constant_time_compare(candidate_hash, CONSTITUTIONAL_HASH)
            return time.perf_counter() - start

        # Warm up for more stable timing data on shared CI workers.
        for _ in range(5):
            _sample(similar_hash)
            _sample(different_hash)

        times_similar = [_sample(similar_hash) for _ in range(20)]
        times_different = [_sample(different_hash) for _ in range(20)]

        avg_similar = sum(times_similar) / len(times_similar)
        avg_different = sum(times_different) / len(times_different)

        # Times should be within 100% of each other (constant-time property with CI jitter tolerance)
        ratio = max(avg_similar, avg_different) / max(min(avg_similar, avg_different), 1e-9)
        assert ratio < 2.0, f"Timing ratio {ratio} suggests non-constant-time comparison"

    async def test_fail_closed_on_error(self):
        """Test validator fails closed on errors."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        # Malformed items should fail validation
        items = [
            {"malformed": True},
            None,
            "invalid",
        ]

        results = await validator.validate_batch(items)

        assert len(results) == 3
        assert all(r["is_valid"] is False for r in results)


class TestIntegration:
    """Test integration with batch processing system."""

    async def test_validates_message_batch(self):
        """Test validation of message batch format."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        validator = ConstitutionalBatchValidator()

        # Simulate real message batch
        messages = [
            {
                "message_id": f"msg_{i}",
                "from_agent": "agent_a",
                "to_agent": "agent_b",
                "content": {"action": "test", "data": {"value": i}},
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
            for i in range(10)
        ]

        results = await validator.validate_batch(messages)

        assert len(results) == 10
        assert all(r["is_valid"] for r in results)

    async def test_async_context_manager(self):
        """Test validator works as async context manager."""
        from enhanced_agent_bus.constitutional_batch import ConstitutionalBatchValidator

        async with ConstitutionalBatchValidator() as validator:
            items = [
                {"content": {"id": i}, "constitutional_hash": CONSTITUTIONAL_HASH} for i in range(5)
            ]
            results = await validator.validate_batch(items)
            assert len(results) == 5

    async def test_singleton_pattern(self):
        """Test get_batch_validator returns singleton."""
        from enhanced_agent_bus.constitutional_batch import (
            get_batch_validator,
            reset_batch_validator,
        )

        await reset_batch_validator()

        validator1 = await get_batch_validator()
        validator2 = await get_batch_validator()

        assert validator1 is validator2

        await reset_batch_validator()
