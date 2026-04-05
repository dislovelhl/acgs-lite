# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 Deliberation Layer - Redis Integration Protocol & Singleton Tests
Constitutional Hash: 608508a9bd224290

Tests for global singleton functions (get/reset), module-level constants
(VOTE_SUBSCRIPTION_ERRORS, VOTE_COLLECTION_ERRORS, REDIS_AVAILABLE, __all__),
and DeliberationMessageProtocol.

Split from test_deliberation_redis_integration_coverage.py.
asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from enhanced_agent_bus.deliberation_layer import redis_integration as ri
from enhanced_agent_bus.deliberation_layer.redis_integration import (
    REDIS_AVAILABLE,
    VOTE_COLLECTION_ERRORS,
    VOTE_SUBSCRIPTION_ERRORS,
    DeliberationMessageProtocol,
    RedisDeliberationQueue,
    RedisVotingSystem,
    get_redis_deliberation_queue,
    get_redis_voting_system,
    reset_all_redis_singletons,
    reset_redis_deliberation_queue,
    reset_redis_voting_system,
)

# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------


class MockRedisClient:
    """Full-featured async mock of a Redis client."""

    def __init__(self):
        self._data: dict = {}
        self._streams: dict = {}
        self._expiry: dict = {}
        self._published: dict = {}
        self._should_raise: type | None = None

    def _maybe_raise(self):
        if self._should_raise:
            raise self._should_raise("mock error")

    async def ping(self):
        self._maybe_raise()
        return True

    async def close(self):
        pass

    async def hset(self, key, field, value):
        self._maybe_raise()
        self._data.setdefault(key, {})[field] = value
        return 1

    async def hget(self, key, field):
        self._maybe_raise()
        return self._data.get(key, {}).get(field)

    async def hgetall(self, key):
        self._maybe_raise()
        return dict(self._data.get(key, {}))

    async def hdel(self, key, field):
        self._maybe_raise()
        removed = self._data.get(key, {}).pop(field, None)
        return 1 if removed is not None else 0

    async def xadd(self, stream_key, fields):
        self._maybe_raise()
        entry_id = f"{len(self._streams.get(stream_key, []))}-0"
        self._streams.setdefault(stream_key, []).append((entry_id, fields))
        return entry_id

    async def xinfo_stream(self, stream_key):
        self._maybe_raise()
        stream = self._streams.get(stream_key, [])
        return {
            "length": len(stream),
            "first-entry": stream[0] if stream else None,
            "last-entry": stream[-1] if stream else None,
        }

    async def expire(self, key, seconds):
        self._maybe_raise()
        self._expiry[key] = seconds
        return True

    async def publish(self, channel, message):
        self._maybe_raise()
        self._published.setdefault(channel, []).append(message)
        return 1

    def pubsub(self):
        return MockPubSub()


class MockPubSub:
    """Mock Redis pub/sub object."""

    def __init__(self):
        self._subscriptions: list[str] = []
        self._messages: list[dict] = []
        self._raise_on_get: type | None = None

    async def subscribe(self, channel: str):
        self._subscriptions.append(channel)

    async def unsubscribe(self, channel: str | None = None):
        if channel:
            self._subscriptions = [c for c in self._subscriptions if c != channel]
        else:
            self._subscriptions.clear()

    async def close(self):
        pass

    async def get_message(self, ignore_subscribe_messages: bool = True):
        if self._raise_on_get:
            raise self._raise_on_get("mock error")
        if self._messages:
            return self._messages.pop(0)
        return None


# ---------------------------------------------------------------------------
# Minimal DeliberationMessageProtocol implementation
# ---------------------------------------------------------------------------


class _FakeMsgType:
    def __init__(self, value: str = "COMMAND"):
        self.value = value


class _FakeMessage:
    def __init__(self):
        self.message_id = "msg-001"
        self.from_agent = "sender_agent"
        self.to_agent = "receiver_agent"
        self.content: dict = {"action": "test", "data": 42}
        self.message_type = _FakeMsgType("COMMAND")


# ===========================================================================
# Global singleton functions
# ===========================================================================


class TestGlobalSingletonFunctions:
    def test_get_redis_deliberation_queue_singleton(self):
        ri._redis_deliberation_queue = None
        q1 = get_redis_deliberation_queue()
        q2 = get_redis_deliberation_queue()
        assert q1 is q2
        assert isinstance(q1, RedisDeliberationQueue)

    def test_get_redis_voting_system_singleton(self):
        ri._redis_voting_system = None
        v1 = get_redis_voting_system()
        v2 = get_redis_voting_system()
        assert v1 is v2
        assert isinstance(v1, RedisVotingSystem)

    def test_reset_redis_deliberation_queue(self):
        ri._redis_deliberation_queue = None
        q = get_redis_deliberation_queue()
        assert q is not None
        reset_redis_deliberation_queue()
        assert ri._redis_deliberation_queue is None

    def test_reset_redis_voting_system(self):
        ri._redis_voting_system = None
        v = get_redis_voting_system()
        assert v is not None
        reset_redis_voting_system()
        assert ri._redis_voting_system is None

    def test_reset_all_redis_singletons(self):
        get_redis_deliberation_queue()
        get_redis_voting_system()
        reset_all_redis_singletons()
        assert ri._redis_deliberation_queue is None
        assert ri._redis_voting_system is None

    def test_get_queue_after_reset_creates_new_instance(self):
        ri._redis_deliberation_queue = None
        q1 = get_redis_deliberation_queue()
        reset_redis_deliberation_queue()
        q2 = get_redis_deliberation_queue()
        assert q1 is not q2

    def test_get_voting_after_reset_creates_new_instance(self):
        ri._redis_voting_system = None
        v1 = get_redis_voting_system()
        reset_redis_voting_system()
        v2 = get_redis_voting_system()
        assert v1 is not v2

    def teardown_method(self):
        # Restore clean state after each test
        reset_all_redis_singletons()


# ===========================================================================
# Module-level constants and protocol
# ===========================================================================


class TestModuleConstants:
    def test_vote_subscription_errors_tuple(self):
        assert RuntimeError in VOTE_SUBSCRIPTION_ERRORS
        assert ValueError in VOTE_SUBSCRIPTION_ERRORS
        assert TypeError in VOTE_SUBSCRIPTION_ERRORS
        assert KeyError in VOTE_SUBSCRIPTION_ERRORS
        assert AttributeError in VOTE_SUBSCRIPTION_ERRORS
        assert ConnectionError in VOTE_SUBSCRIPTION_ERRORS
        assert OSError in VOTE_SUBSCRIPTION_ERRORS

    def test_vote_collection_errors_tuple(self):
        assert RuntimeError in VOTE_COLLECTION_ERRORS
        assert ValueError in VOTE_COLLECTION_ERRORS
        assert TypeError in VOTE_COLLECTION_ERRORS
        assert KeyError in VOTE_COLLECTION_ERRORS
        assert AttributeError in VOTE_COLLECTION_ERRORS
        assert ConnectionError in VOTE_COLLECTION_ERRORS
        assert OSError in VOTE_COLLECTION_ERRORS
        assert asyncio.TimeoutError in VOTE_COLLECTION_ERRORS

    def test_redis_available_flag_is_bool(self):
        assert isinstance(REDIS_AVAILABLE, bool)

    def test_dunder_all_contains_expected_names(self):
        assert "RedisDeliberationQueue" in ri.__all__
        assert "RedisVotingSystem" in ri.__all__
        assert "get_redis_deliberation_queue" in ri.__all__
        assert "get_redis_voting_system" in ri.__all__
        assert "reset_redis_deliberation_queue" in ri.__all__
        assert "reset_redis_voting_system" in ri.__all__
        assert "reset_all_redis_singletons" in ri.__all__
        assert "REDIS_AVAILABLE" in ri.__all__


class TestDeliberationMessageProtocol:
    def test_protocol_class_exists(self):
        assert DeliberationMessageProtocol is not None

    def test_fake_message_satisfies_protocol_contract(self):
        msg = _FakeMessage()
        assert hasattr(msg, "message_id")
        assert hasattr(msg, "from_agent")
        assert hasattr(msg, "to_agent")
        assert hasattr(msg, "content")
        assert hasattr(msg, "message_type")
        assert hasattr(msg.message_type, "value")

    async def test_enqueue_with_protocol_compliant_message(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        msg = _FakeMessage()
        result = await q.enqueue_deliberation_item(msg, "protocol-test-001")
        assert result is True
        stored_raw = mock_client._data[q.queue_key]["protocol-test-001"]
        stored = json.loads(stored_raw)
        assert stored["message_id"] == "msg-001"
        assert stored["from_agent"] == "sender_agent"
        assert stored["to_agent"] == "receiver_agent"
        assert stored["message_type"] == "COMMAND"
        assert json.loads(stored["content"]) == {"action": "test", "data": 42}
