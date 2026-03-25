"""
ACGS-2 Enhanced Agent Bus - Redis Integration Tests
Constitutional Hash: 608508a9bd224290

Tests Redis integration components with mocking.
"""

import json
import os
import sys
import types
from unittest.mock import patch

import pytest

# Add enhanced_agent_bus directory to path
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

# Import using direct module loading
import importlib.util


def _load_module(name, path):
    """Load a module directly from path."""
    if "enhanced_agent_bus" not in sys.modules:
        pkg = types.ModuleType("enhanced_agent_bus")
        pkg.__path__ = [enhanced_agent_bus_dir]
        pkg.__file__ = os.path.join(enhanced_agent_bus_dir, "__init__.py")
        pkg.__package__ = "enhanced_agent_bus"
        sys.modules["enhanced_agent_bus"] = pkg
    qualified_name = f"enhanced_agent_bus.{name}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "enhanced_agent_bus"
    sys.modules[qualified_name] = module
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load models
_models = _load_module("_redis_test_models", os.path.join(enhanced_agent_bus_dir, "models.py"))

AgentMessage = _models.AgentMessage
MessageType = _models.MessageType
Priority = _models.Priority
CONSTITUTIONAL_HASH = _models.CONSTITUTIONAL_HASH


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self._data = {}
        self._streams = {}
        self._expiry = {}
        self._pubsub = {}  # Store published messages

    async def publish(self, channel, message):
        """Mock publish method."""
        if channel not in self._pubsub:
            self._pubsub[channel] = []
        self._pubsub[channel].append(message)
        return 1  # Return valid subscriber count

    async def ping(self):
        return True

    async def close(self):
        pass

    async def hset(self, key, field, value):
        if key not in self._data:
            self._data[key] = {}
        self._data[key][field] = value
        return 1

    async def hget(self, key, field):
        return self._data.get(key, {}).get(field)

    async def hgetall(self, key):
        return self._data.get(key, {})

    async def hdel(self, key, field):
        if key in self._data and field in self._data[key]:
            del self._data[key][field]
            return 1
        return 0

    async def xadd(self, stream_key, fields):
        if stream_key not in self._streams:
            self._streams[stream_key] = []
        entry_id = f"{len(self._streams[stream_key])}-0"
        self._streams[stream_key].append((entry_id, fields))
        return entry_id

    async def xinfo_stream(self, stream_key):
        stream = self._streams.get(stream_key, [])
        return {
            "length": len(stream),
            "first-entry": stream[0] if stream else None,
            "last-entry": stream[-1] if stream else None,
        }

    async def expire(self, key, seconds):
        self._expiry[key] = seconds
        return True


class TestRedisDeliberationQueue:
    """Tests for RedisDeliberationQueue class."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return MockRedisClient()

    @pytest.fixture
    def test_message(self):
        """Create a test message."""
        return AgentMessage(
            from_agent="test_sender",
            to_agent="test_receiver",
            sender_id="sender_id",
            message_type=MessageType.COMMAND,
            content={"action": "test_action"},
        )

    async def test_connect_success(self, mock_redis):
        """Test successful Redis connection."""
        # Load redis_integration module
        redis_int = _load_module(
            "_redis_int_test",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()

        # Patch the aioredis module
        with patch.object(redis_int, "REDIS_AVAILABLE", True):
            with patch.object(redis_int, "aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_redis
                result = await queue.connect()

        assert result is True

    async def test_connect_redis_unavailable(self):
        """Test connection when Redis is not available."""
        redis_int = _load_module(
            "_redis_int_test2",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()

        with patch.object(redis_int, "REDIS_AVAILABLE", False):
            result = await queue.connect()

        assert result is False

    async def test_enqueue_deliberation_item(self, mock_redis, test_message):
        """Test enqueueing a deliberation item."""
        redis_int = _load_module(
            "_redis_int_test3",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = mock_redis

        result = await queue.enqueue_deliberation_item(
            message=test_message, item_id="test_item_123", metadata={"priority": "high"}
        )

        assert result is True
        assert "test_item_123" in mock_redis._data.get(queue.queue_key, {})

    async def test_enqueue_without_connection(self, test_message):
        """Test enqueueing fails without Redis connection."""
        redis_int = _load_module(
            "_redis_int_test4",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = None

        result = await queue.enqueue_deliberation_item(
            message=test_message, item_id="test_item_123"
        )

        assert result is False

    async def test_get_deliberation_item(self, mock_redis):
        """Test retrieving a deliberation item."""
        redis_int = _load_module(
            "_redis_int_test5",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = mock_redis

        # Store test item
        test_item = {"item_id": "test_123", "status": "pending"}
        await mock_redis.hset(queue.queue_key, "test_123", json.dumps(test_item))

        result = await queue.get_deliberation_item("test_123")

        assert result is not None
        assert result["item_id"] == "test_123"

    async def test_get_nonexistent_item(self, mock_redis):
        """Test retrieving nonexistent item returns None."""
        redis_int = _load_module(
            "_redis_int_test6",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = mock_redis

        result = await queue.get_deliberation_item("nonexistent_id")

        assert result is None

    async def test_update_deliberation_status(self, mock_redis):
        """Test updating deliberation status."""
        redis_int = _load_module(
            "_redis_int_test7",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = mock_redis

        # Store initial item
        test_item = {"item_id": "test_123", "status": "pending"}
        await mock_redis.hset(queue.queue_key, "test_123", json.dumps(test_item))

        result = await queue.update_deliberation_status(
            "test_123", "approved", {"reviewer": "human_1"}
        )

        assert result is True

        updated_item = await queue.get_deliberation_item("test_123")
        assert updated_item["status"] == "approved"
        assert updated_item["reviewer"] == "human_1"

    async def test_remove_deliberation_item(self, mock_redis):
        """Test removing a deliberation item."""
        redis_int = _load_module(
            "_redis_int_test8",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = mock_redis

        # Store item
        await mock_redis.hset(queue.queue_key, "test_123", json.dumps({"item_id": "test_123"}))

        result = await queue.remove_deliberation_item("test_123")

        assert result is True
        assert await queue.get_deliberation_item("test_123") is None

    async def test_get_pending_items(self, mock_redis):
        """Test getting pending items."""
        redis_int = _load_module(
            "_redis_int_test9",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = mock_redis

        # Store items with different statuses
        items = [
            {"item_id": "item_1", "status": "pending"},
            {"item_id": "item_2", "status": "approved"},
            {"item_id": "item_3", "status": "pending"},
        ]
        for item in items:
            await mock_redis.hset(queue.queue_key, item["item_id"], json.dumps(item))

        pending = await queue.get_pending_items()

        assert len(pending) == 2
        assert all(item["status"] == "pending" for item in pending)

    async def test_get_stream_info(self, mock_redis):
        """Test getting stream info."""
        redis_int = _load_module(
            "_redis_int_test10",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        queue = redis_int.RedisDeliberationQueue()
        queue.redis_client = mock_redis

        # Add entries to stream
        await mock_redis.xadd(queue.stream_key, {"test": "data"})

        info = await queue.get_stream_info()

        assert info["length"] == 1


class TestRedisVotingSystem:
    """Tests for RedisVotingSystem class."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        return MockRedisClient()

    async def test_submit_vote(self, mock_redis):
        """Test submitting a vote."""
        redis_int = _load_module(
            "_redis_vote_test1",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = mock_redis

        result = await voting.submit_vote(
            item_id="item_123",
            agent_id="agent_1",
            vote="approve",
            reasoning="Looks good",
            confidence=0.9,
        )

        assert result is True

        votes_key = f"{voting.votes_key_prefix}item_123"
        assert "agent_1" in mock_redis._data.get(votes_key, {})

    async def test_submit_vote_without_connection(self):
        """Test vote submission fails without Redis."""
        redis_int = _load_module(
            "_redis_vote_test2",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = None

        result = await voting.submit_vote(
            item_id="item_123", agent_id="agent_1", vote="approve", reasoning="test"
        )

        assert result is False

    async def test_get_votes(self, mock_redis):
        """Test getting votes for an item."""
        redis_int = _load_module(
            "_redis_vote_test3",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = mock_redis

        # Submit votes
        await voting.submit_vote("item_123", "agent_1", "approve", "reason1")
        await voting.submit_vote("item_123", "agent_2", "reject", "reason2")

        votes = await voting.get_votes("item_123")

        assert len(votes) == 2

    async def test_get_vote_count(self, mock_redis):
        """Test getting vote counts."""
        redis_int = _load_module(
            "_redis_vote_test4",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = mock_redis

        # Submit votes
        await voting.submit_vote("item_123", "agent_1", "approve", "r1")
        await voting.submit_vote("item_123", "agent_2", "approve", "r2")
        await voting.submit_vote("item_123", "agent_3", "reject", "r3")

        counts = await voting.get_vote_count("item_123")

        assert counts["approve"] == 2
        assert counts["reject"] == 1
        assert counts["total"] == 3

    async def test_check_consensus_approved(self, mock_redis):
        """Test consensus check with approval."""
        redis_int = _load_module(
            "_redis_vote_test5",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = mock_redis

        # Submit votes (3/4 = 75% approve)
        await voting.submit_vote("item_123", "agent_1", "approve", "r1")
        await voting.submit_vote("item_123", "agent_2", "approve", "r2")
        await voting.submit_vote("item_123", "agent_3", "approve", "r3")
        await voting.submit_vote("item_123", "agent_4", "reject", "r4")

        result = await voting.check_consensus("item_123", required_votes=3, threshold=0.66)

        assert result["consensus_reached"] is True
        assert result["decision"] == "approved"

    async def test_check_consensus_rejected(self, mock_redis):
        """Test consensus check with rejection."""
        redis_int = _load_module(
            "_redis_vote_test6",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = mock_redis

        # Submit votes (3/4 = 75% reject)
        await voting.submit_vote("item_123", "agent_1", "reject", "r1")
        await voting.submit_vote("item_123", "agent_2", "reject", "r2")
        await voting.submit_vote("item_123", "agent_3", "reject", "r3")
        await voting.submit_vote("item_123", "agent_4", "approve", "r4")

        result = await voting.check_consensus("item_123", required_votes=3, threshold=0.66)

        assert result["consensus_reached"] is True
        assert result["decision"] == "rejected"

    async def test_check_consensus_insufficient_votes(self, mock_redis):
        """Test consensus check with insufficient votes."""
        redis_int = _load_module(
            "_redis_vote_test7",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = mock_redis

        # Submit only 2 votes
        await voting.submit_vote("item_123", "agent_1", "approve", "r1")
        await voting.submit_vote("item_123", "agent_2", "approve", "r2")

        result = await voting.check_consensus("item_123", required_votes=3)

        assert result["consensus_reached"] is False
        assert result["reason"] == "insufficient_votes"

    async def test_check_consensus_threshold_not_met(self, mock_redis):
        """Test consensus check when threshold is not met."""
        redis_int = _load_module(
            "_redis_vote_test8",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        voting = redis_int.RedisVotingSystem()
        voting.redis_client = mock_redis

        # Submit votes (2/4 = 50% each)
        await voting.submit_vote("item_123", "agent_1", "approve", "r1")
        await voting.submit_vote("item_123", "agent_2", "approve", "r2")
        await voting.submit_vote("item_123", "agent_3", "reject", "r3")
        await voting.submit_vote("item_123", "agent_4", "reject", "r4")

        result = await voting.check_consensus("item_123", required_votes=3, threshold=0.66)

        assert result["consensus_reached"] is False
        assert result["reason"] == "threshold_not_met"


class TestGlobalInstances:
    """Tests for global instance factories."""

    def test_get_redis_deliberation_queue(self):
        """Test getting global deliberation queue instance."""
        redis_int = _load_module(
            "_redis_global_test1",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        # Reset global
        redis_int._redis_deliberation_queue = None

        queue1 = redis_int.get_redis_deliberation_queue()
        queue2 = redis_int.get_redis_deliberation_queue()

        assert queue1 is queue2

    def test_get_redis_voting_system(self):
        """Test getting global voting system instance."""
        redis_int = _load_module(
            "_redis_global_test2",
            os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "redis_integration.py"),
        )

        # Reset global
        redis_int._redis_voting_system = None

        voting1 = redis_int.get_redis_voting_system()
        voting2 = redis_int.get_redis_voting_system()

        assert voting1 is voting2


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
