"""
Unit tests for Batch Processor Orchestrator.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.batch_processor_infra.orchestrator import (
    BatchProcessorOrchestrator,
)
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    BatchRequest,
    BatchRequestItem,
    MessageStatus,
    MessageType,
)
from enhanced_agent_bus.validators import ValidationResult


class TestBatchProcessorOrchestrator:
    async def test_process_batch_full_flow(self):
        orchestrator = BatchProcessorOrchestrator(max_concurrency=5)

        items = [
            BatchRequestItem(
                from_agent="a", to_agent="b", content={"i": i}, message_type=MessageType.EVENT
            )
            for i in range(3)
        ]
        batch = BatchRequest(batch_id="b1", items=items, constitutional_hash=CONSTITUTIONAL_HASH)

        async def mock_process(it):
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        response = await orchestrator.process_batch(batch, mock_process)

        assert response.batch_id == "b1"
        assert len(response.items) == 3
        assert response.stats.total_items == 3
        assert response.stats.successful_items == 3
        assert response.stats.processing_time_ms > 0

    async def test_process_batch_governance_fail(self):
        orchestrator = BatchProcessorOrchestrator()

        # Create a valid batch first, then modify the hash to bypass model validation
        item = BatchRequestItem(
            from_agent="a", to_agent="b", content={}, message_type=MessageType.EVENT
        )
        batch = BatchRequest(batch_id="b1", items=[item], constitutional_hash=CONSTITUTIONAL_HASH)
        # Modify hash after creation to test governance layer
        object.__setattr__(batch, "constitutional_hash", "invalid")

        response = await orchestrator.process_batch(batch, AsyncMock())

        assert response.error is not None
        assert response.stats.failed_items == 1  # One item that failed governance

    async def test_process_batch_with_deduplication(self):
        orchestrator = BatchProcessorOrchestrator()

        # Two identical items
        item = BatchRequestItem(
            from_agent="a", to_agent="b", content={"x": 1}, message_type=MessageType.EVENT
        )
        items = [item, item]
        batch = BatchRequest(batch_id="b1", items=items, constitutional_hash=CONSTITUTIONAL_HASH)

        process_call_count = 0

        async def mock_process(it):
            nonlocal process_call_count
            process_call_count += 1
            return ValidationResult(is_valid=True, status=MessageStatus.VALIDATED)

        response = await orchestrator.process_batch(batch, mock_process)

        assert len(response.items) == 2
        # Should only call process once due to deduplication
        assert process_call_count == 1
        assert response.stats.deduplicated_count == 1

    def test_metrics_and_cache_management(self):
        orchestrator = BatchProcessorOrchestrator()

        # Just verifying methods exist and work as expected
        orchestrator.reset_metrics()
        metrics = orchestrator.get_metrics()
        assert metrics["total_batches"] == 0

        orchestrator.clear_cache()
        assert orchestrator.get_cache_size() == 0
