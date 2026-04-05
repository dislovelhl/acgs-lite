"""
Unit tests for Batch Processor Queue.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.batch_processor_infra.queue import BatchRequestQueue
from enhanced_agent_bus.models import BatchRequest, BatchRequestItem, MessageType


class TestBatchRequestQueue:
    def test_deduplication_enabled(self):
        queue = BatchRequestQueue(enable_deduplication=True)

        items = [
            BatchRequestItem(
                from_agent="a1",
                to_agent="b1",
                content={"data": 1},
                message_type=MessageType.EVENT,
                tenant_id="t1",
            ),
            BatchRequestItem(
                from_agent="a1",
                to_agent="b1",
                content={"data": 1},
                message_type=MessageType.EVENT,
                tenant_id="t1",
            ),
            BatchRequestItem(
                from_agent="a2",
                to_agent="b1",
                content={"data": 1},
                message_type=MessageType.EVENT,
                tenant_id="t1",
            ),
        ]
        batch = BatchRequest(batch_id="b1", items=items)

        unique_items, mapping = queue.deduplicate_requests(batch)

        assert len(unique_items) == 2
        assert mapping[0] == 0
        assert mapping[1] == 0  # Duplicate of index 0
        assert mapping[2] == 1
        assert queue.get_cache_size() == 2

    def test_deduplication_disabled(self):
        queue = BatchRequestQueue(enable_deduplication=False)

        items = [
            BatchRequestItem(
                from_agent="a", to_agent="b", content={}, message_type=MessageType.EVENT
            )
            for _ in range(3)
        ]
        batch = BatchRequest(batch_id="b1", items=items)

        unique_items, mapping = queue.deduplicate_requests(batch)

        assert len(unique_items) == 3
        # Mapping is identity when dedup disabled (for orchestrator compatibility)
        assert mapping == {0: 0, 1: 1, 2: 2}
        assert queue.get_cache_size() == 0

    def test_clear_cache(self):
        queue = BatchRequestQueue()
        item = BatchRequestItem(
            from_agent="a", to_agent="b", content={"x": 1}, message_type=MessageType.EVENT
        )
        batch = BatchRequest(batch_id="b1", items=[item])

        queue.deduplicate_requests(batch)
        assert queue.get_cache_size() == 1

        queue.clear_cache()
        assert queue.get_cache_size() == 0
