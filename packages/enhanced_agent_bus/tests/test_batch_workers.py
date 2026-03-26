"""
Unit tests for Batch Processor Worker Pool.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from enhanced_agent_bus.batch_processor_infra.workers import WorkerPool
from enhanced_agent_bus.models import (
    BatchItemStatus,
    BatchRequestItem,
    MessageStatus,
    MessageType,
)
from enhanced_agent_bus.validators import ValidationResult


class TestWorkerPool:
    async def test_process_item_success(self):
        pool = WorkerPool(max_concurrency=2)
        item = BatchRequestItem(
            from_agent="a", to_agent="b", content={}, message_type=MessageType.EVENT
        )

        async def mock_process(it):
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED, decision="ALLOW")

        result = await pool.process_item(item, mock_process)

        assert result.valid
        # Workers map valid results to BatchItemStatus.SUCCESS for metrics compatibility
        assert result.status == BatchItemStatus.SUCCESS.value
        assert result.processing_time_ms > 0

    async def test_process_item_retry_success(self):
        pool = WorkerPool(max_concurrency=2)
        item = BatchRequestItem(
            from_agent="a", to_agent="b", content={}, message_type=MessageType.EVENT
        )

        call_count = 0

        async def mock_process(it):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Transient failure")
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        result = await pool.process_item(item, mock_process)

        assert result.valid
        assert call_count == 2

    async def test_circuit_breaker_trip(self):
        pool = WorkerPool(max_concurrency=1)
        # Lower max failures for test
        pool._max_failures = 2
        item = BatchRequestItem(
            from_agent="a", to_agent="b", content={}, message_type=MessageType.EVENT
        )

        async def mock_fail(it):
            raise RuntimeError("Persistent failure")

        # First failure
        await pool.process_item(item, mock_fail)
        assert not pool._circuit_breaker_tripped

        # Second failure -> trip
        await pool.process_item(item, mock_fail)
        assert pool._circuit_breaker_tripped

        # Subsequent calls should return immediately
        result = await pool.process_item(item, mock_fail)
        assert "Circuit breaker tripped" in result.error_message

    async def test_concurrency_limit(self):
        pool = WorkerPool(max_concurrency=1)
        item = BatchRequestItem(
            from_agent="a", to_agent="b", content={}, message_type=MessageType.EVENT
        )

        running_tasks = 0

        async def mock_slow_process(it):
            nonlocal running_tasks
            running_tasks += 1
            await asyncio.sleep(0.1)
            running_tasks -= 1
            return ValidationResult(is_valid=True)

        # Run two tasks concurrently
        t1 = asyncio.create_task(pool.process_item(item, mock_slow_process))
        t2 = asyncio.create_task(pool.process_item(item, mock_slow_process))

        # Wait a bit
        await asyncio.sleep(0.05)
        # Only one should be running due to semaphore
        assert running_tasks == 1

        await asyncio.gather(t1, t2)
        assert running_tasks == 0
