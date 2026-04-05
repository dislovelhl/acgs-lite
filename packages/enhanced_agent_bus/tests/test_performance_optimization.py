"""
ACGS-2 Enhanced Agent Bus - Performance Optimization Tests
Constitutional Hash: 608508a9bd224290

Unit tests for Phase 6: Performance Optimization components.
Tests cover:
- AsyncPipelineOptimizer
- ResourcePool and PooledResource
- MemoryOptimizer
- LatencyReducer
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

try:
    from enhanced_agent_bus.performance_optimization import (
        PERFORMANCE_OPTIMIZATION_AVAILABLE,
        AsyncPipelineOptimizer,
        BatchConfig,
        BatchFlushResult,
        CacheEntry,
        LatencyReducer,
        MemoryOptimizer,
        PipelineResult,
        PipelineStage,
        PooledResource,
        ResourcePool,
        create_async_pipeline,
        create_latency_reducer,
        create_memory_optimizer,
        create_resource_pool,
    )

    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Import failed: {e}")
    IMPORTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE, reason="Performance optimization module not available"
)


# =============================================================================
# AsyncPipelineOptimizer Tests
# =============================================================================


class TestAsyncPipelineOptimizer:
    """Tests for AsyncPipelineOptimizer."""

    @pytest.fixture
    def pipeline(self) -> AsyncPipelineOptimizer:
        return AsyncPipelineOptimizer(max_concurrency=4)

    async def test_single_stage_execution(self, pipeline: AsyncPipelineOptimizer):
        """Single stage should execute correctly."""

        async def handler(data: dict) -> dict:
            return {"result": data.get("input", 0) * 2}

        stage = PipelineStage(
            name="double",
            handler=handler,
            timeout=5.0,
            parallel=False,
        )
        pipeline.add_stage(stage)

        results = await pipeline.run({"input": 5})

        assert len(results) >= 1
        assert results[0].success is True

    async def test_multiple_parallel_stages(self, pipeline: AsyncPipelineOptimizer):
        """Parallel stages should execute concurrently."""
        execution_times = []

        async def slow_handler(data: dict) -> dict:
            start = time.time()
            await asyncio.sleep(0.05)
            execution_times.append(time.time() - start)
            return data

        for i in range(3):
            pipeline.add_stage(
                PipelineStage(
                    name=f"stage_{i}",
                    handler=slow_handler,
                    timeout=5.0,
                    parallel=True,
                )
            )

        start = time.time()
        results = await pipeline.run({"data": "test"})
        total_time = time.time() - start

        assert all(r.success for r in results)
        # Parallel execution should be faster than sequential
        assert total_time < 0.3

    async def test_stage_error_handling(self, pipeline: AsyncPipelineOptimizer):
        """Errors in stages should be captured."""

        async def failing_handler(data: dict) -> dict:
            raise ValueError("Intentional failure")

        pipeline.add_stage(
            PipelineStage(
                name="failing",
                handler=failing_handler,
                timeout=5.0,
                parallel=False,
            )
        )

        results = await pipeline.run({"data": "test"})

        assert len(results) >= 1
        assert results[0].success is False
        assert "Intentional failure" in (results[0].error or "")

    async def test_constitutional_hash_present(self, pipeline: AsyncPipelineOptimizer):
        """Pipeline should include constitutional hash."""
        assert pipeline.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_stats_tracking(self, pipeline: AsyncPipelineOptimizer):
        """Pipeline should track execution stats."""

        async def handler(data: dict) -> dict:
            return data

        pipeline.add_stage(
            PipelineStage(
                name="passthrough",
                handler=handler,
                timeout=5.0,
                parallel=False,
            )
        )

        await pipeline.run({"data": "test"})
        await pipeline.run({"data": "test2"})

        stats = pipeline.get_stats()
        assert stats["runs"] == 2
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# ResourcePool Tests
# =============================================================================


class TestResourcePool:
    """Tests for ResourcePool."""

    @pytest.fixture
    def pool(self) -> ResourcePool:
        async def create_resource():
            return MagicMock()

        return ResourcePool(
            factory=create_resource,
            max_size=5,
            min_size=1,
        )

    async def test_acquire_release(self, pool: ResourcePool):
        """Resources should be acquired and released correctly."""
        resource = await pool.acquire()
        assert resource is not None
        assert isinstance(resource, PooledResource)

        await pool.release(resource)
        await pool.close()

    async def test_pool_limit(self, pool: ResourcePool):
        """Pool should respect max size."""
        resources = []
        for _ in range(5):
            r = await pool.acquire()
            resources.append(r)

        assert len(resources) == 5

        for r in resources:
            await pool.release(r)

        await pool.close()

    async def test_context_manager(self, pool: ResourcePool):
        """Pool should work as async context manager."""
        async with pool.resource() as resource:
            assert resource is not None

        await pool.close()


# =============================================================================
# MemoryOptimizer Tests
# =============================================================================


class TestMemoryOptimizer:
    """Tests for MemoryOptimizer."""

    @pytest.fixture
    def optimizer(self) -> MemoryOptimizer:
        return MemoryOptimizer(
            max_entries=100,
            default_ttl_seconds=60,
        )

    async def test_cache_put_get(self, optimizer: MemoryOptimizer):
        """Cache should store and retrieve values."""
        await optimizer.put("key1", {"data": "value1"})
        result = await optimizer.get("key1")

        assert result is not None
        assert result["data"] == "value1"

    async def test_cache_miss(self, optimizer: MemoryOptimizer):
        """Cache miss should return None."""
        result = await optimizer.get("nonexistent")
        assert result is None

    async def test_cache_eviction(self, optimizer: MemoryOptimizer):
        """Cache should evict old entries."""
        for i in range(150):
            await optimizer.put(f"key_{i}", {"data": i})

        stats = optimizer.get_stats()
        assert stats["cache_entries"] <= 100

    async def test_cache_clear(self, optimizer: MemoryOptimizer):
        """Cache should clear all entries."""
        await optimizer.put("key1", "value1")
        await optimizer.put("key2", "value2")

        cleared = await optimizer.clear()
        assert cleared == 2

        result = await optimizer.get("key1")
        assert result is None


# =============================================================================
# LatencyReducer Tests
# =============================================================================


class TestLatencyReducer:
    """Tests for LatencyReducer."""

    @pytest.fixture
    def reducer(self) -> LatencyReducer:
        config = BatchConfig(
            max_batch_size=10,
            max_wait_seconds=0.1,
        )
        return LatencyReducer(batch_config=config)

    async def test_submit_items(self, reducer: LatencyReducer):
        """Items should be submitted to batches."""
        await reducer.submit("test-topic", {"id": 1})
        await reducer.submit("test-topic", {"id": 2})

        stats = reducer.get_stats()
        assert "topics_tracked" in stats
        assert stats["items_submitted"] == 2

        await reducer.close()

    async def test_flush_batch(self, reducer: LatencyReducer):
        """Batches should flush correctly."""
        await reducer.submit("test-topic", {"id": 1})
        await reducer.submit("test-topic", {"id": 2})

        result = await reducer.flush("test-topic")
        assert isinstance(result, BatchFlushResult)
        assert result.items_flushed == 2

        await reducer.close()

    async def test_flush_all(self, reducer: LatencyReducer):
        """All batches should flush together."""
        await reducer.submit("topic-1", {"id": 1})
        await reducer.submit("topic-2", {"id": 2})

        results = await reducer.flush_all()
        assert len(results) == 2

        await reducer.close()


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_async_pipeline(self):
        """Factory should create configured pipeline."""
        pipeline = create_async_pipeline(max_concurrency=8)
        assert pipeline.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_create_resource_pool(self):
        """Factory should create configured pool."""

        async def factory():
            return MagicMock()

        pool = create_resource_pool(factory=factory, max_size=10)
        await pool.close()

    def test_create_memory_optimizer(self):
        """Factory should create configured optimizer."""
        optimizer = create_memory_optimizer(max_entries=50)
        assert optimizer is not None

    def test_create_latency_reducer(self):
        """Factory should create configured reducer."""
        config = BatchConfig(max_batch_size=20)
        reducer = create_latency_reducer(batch_config=config)
        assert reducer is not None


# =============================================================================
# Integration Tests
# =============================================================================


class TestPerformanceOptimizationIntegration:
    """Integration tests for performance optimization components."""

    async def test_pipeline_with_memory_optimizer(self):
        """Pipeline should work with memory optimizer."""
        optimizer = create_memory_optimizer(max_entries=100)
        pipeline = create_async_pipeline(max_concurrency=4)

        async def caching_stage(data: dict) -> dict:
            key = f"result_{data.get('id')}"
            cached = await optimizer.get(key)
            if cached:
                return cached
            result = {**data, "processed": True}
            await optimizer.put(key, result)
            return result

        pipeline.add_stage(
            PipelineStage(
                name="cache_stage",
                handler=caching_stage,
                timeout=5.0,
                parallel=False,
            )
        )

        results = await pipeline.run({"id": 1})
        assert len(results) >= 1
        assert results[0].success is True

    async def test_reducer_with_optimizer(self):
        """Latency reducer should work with memory optimizer."""
        optimizer = create_memory_optimizer(max_entries=100)
        config = BatchConfig(max_batch_size=5)
        reducer = create_latency_reducer(batch_config=config)

        for i in range(5):
            await reducer.submit("cache-topic", {"key": f"item_{i}"})
            await optimizer.put(f"item_{i}", {"cached": True})

        stats = optimizer.get_stats()
        assert stats["cache_entries"] == 5

        await reducer.close()
