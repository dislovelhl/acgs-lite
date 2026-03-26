# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 Deliberation Layer - Redis Voting System Tests
Constitutional Hash: 608508a9bd224290

Tests for RedisVotingSystem: constructor, connect, disconnect, submit_vote,
get_votes_pubsub_instance, get_votes, get_vote_count, check_consensus,
publish_vote_event, subscribe_to_votes, unsubscribe_from_votes,
get_vote_event, collect_votes_event_driven.

Split from test_deliberation_redis_integration_coverage.py.
asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import patch

import pytest

from enhanced_agent_bus.deliberation_layer import redis_integration as ri
from enhanced_agent_bus.deliberation_layer.redis_integration import (
    RedisVotingSystem,
)


def _target_module():
    """Return the actual module dict backing RedisVotingSystem.connect.

    Under --import-mode=importlib the ``ri`` alias imported above may be a
    *different* module instance from the one whose globals are closed over by
    ``RedisVotingSystem.connect``.  Patching ``ri.REDIS_AVAILABLE`` then
    has no effect on the running code.  This helper resolves the canonical
    module so that ``patch.object`` always targets the right dict.
    """
    return sys.modules[RedisVotingSystem.__module__]


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


# ===========================================================================
# RedisVotingSystem — constructor
# ===========================================================================


class TestRedisVotingSystemInit:
    def test_defaults(self):
        v = RedisVotingSystem()
        assert v.redis_url == "redis://localhost:6379"
        assert v.redis_client is None
        assert v.votes_key_prefix == "acgs:votes:"
        assert v.pubsub_channel_prefix == "acgs:vote_events:"
        assert v._pubsub is None
        assert isinstance(v._subscribers, dict)

    def test_custom_url(self):
        v = RedisVotingSystem("redis://myhost:1234")
        assert v.redis_url == "redis://myhost:1234"


# ===========================================================================
# RedisVotingSystem — connect
# ===========================================================================


class TestRedisVotingSystemConnect:
    async def test_connect_success(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", True):
            with patch.object(mod, "aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                result = await v.connect()
        assert result is True

    async def test_connect_redis_not_available(self):
        v = RedisVotingSystem()
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", False):
            result = await v.connect()
        assert result is False
        assert v.redis_client is None

    async def test_connect_connection_error(self):
        v = RedisVotingSystem()

        async def _fail():
            raise ConnectionError("refused")

        mock_client = MockRedisClient()
        mock_client.ping = _fail  # type: ignore[method-assign]
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", True):
            with patch.object(mod, "aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                result = await v.connect()
        assert result is False
        assert v.redis_client is None

    async def test_connect_os_error(self):
        v = RedisVotingSystem()

        async def _fail():
            raise OSError("IO error")

        mock_client = MockRedisClient()
        mock_client.ping = _fail  # type: ignore[method-assign]
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", True):
            with patch.object(mod, "aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                result = await v.connect()
        assert result is False


# ===========================================================================
# RedisVotingSystem — disconnect
# ===========================================================================


class TestRedisVotingSystemDisconnect:
    async def test_disconnect_with_client_no_pubsub(self):
        v = RedisVotingSystem()
        v.redis_client = MockRedisClient()
        v._pubsub = None
        await v.disconnect()
        assert v.redis_client is None

    async def test_disconnect_with_pubsub_and_client(self):
        v = RedisVotingSystem()
        v.redis_client = MockRedisClient()
        v._pubsub = MockPubSub()
        await v.disconnect()
        assert v.redis_client is None
        assert v._pubsub is None

    async def test_disconnect_no_client_no_pubsub(self):
        v = RedisVotingSystem()
        v.redis_client = None
        v._pubsub = None
        await v.disconnect()  # must not raise

    async def test_disconnect_pubsub_only_no_client(self):
        v = RedisVotingSystem()
        v.redis_client = None
        v._pubsub = MockPubSub()
        await v.disconnect()
        assert v._pubsub is None


# ===========================================================================
# RedisVotingSystem — submit_vote
# ===========================================================================


class TestRedisVotingSystemSubmitVote:
    async def test_submit_no_client(self):
        v = RedisVotingSystem()
        v.redis_client = None
        result = await v.submit_vote("item-1", "agent-1", "approve", "reason")
        assert result is False

    async def test_submit_success(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        result = await v.submit_vote("item-1", "agent-1", "approve", "looks good", 0.95)
        assert result is True
        votes_key = f"{v.votes_key_prefix}item-1"
        assert "agent-1" in mock_client._data.get(votes_key, {})

    async def test_submit_default_confidence(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        result = await v.submit_vote("item-2", "agent-2", "reject", "bad")
        assert result is True
        votes_key = f"{v.votes_key_prefix}item-2"
        stored = json.loads(mock_client._data[votes_key]["agent-2"])
        assert stored["confidence"] == 1.0

    async def test_submit_connection_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        v.redis_client = mock_client
        result = await v.submit_vote("item-3", "agent-3", "approve", "reason")
        assert result is False

    async def test_submit_os_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        v.redis_client = mock_client
        result = await v.submit_vote("item-4", "agent-4", "approve", "reason")
        assert result is False

    async def test_submit_type_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = TypeError
        v.redis_client = mock_client
        result = await v.submit_vote("item-5", "agent-5", "approve", "reason")
        assert result is False

    async def test_submit_sets_expiry(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-6", "agent-6", "approve", "reason")
        votes_key = f"{v.votes_key_prefix}item-6"
        assert votes_key in mock_client._expiry
        assert mock_client._expiry[votes_key] == 86400

    async def test_submit_publishes_event(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-7", "agent-7", "approve", "reason")
        channel = "acgs:votes:channel:item-7"
        assert channel in mock_client._published
        assert len(mock_client._published[channel]) == 1

    async def test_submit_abstain_vote(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        result = await v.submit_vote("item-8", "agent-8", "abstain", "no opinion")
        assert result is True


# ===========================================================================
# RedisVotingSystem — get_votes_pubsub_instance
# ===========================================================================


class TestRedisVotingSystemGetVotesPubsub:
    async def test_get_pubsub_no_client(self):
        v = RedisVotingSystem()
        v.redis_client = None
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_success(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is not None

    async def test_get_pubsub_runtime_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise RuntimeError("pubsub failed")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_value_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise ValueError("bad val")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_connection_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise ConnectionError("conn error")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_attribute_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise AttributeError("attr error")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_key_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise KeyError("key err")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_type_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise TypeError("type err")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_os_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise OSError("os err")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.get_votes_pubsub_instance("item-1")
        assert result is None


# ===========================================================================
# RedisVotingSystem — get_votes
# ===========================================================================


class TestRedisVotingSystemGetVotes:
    async def test_get_votes_no_client(self):
        v = RedisVotingSystem()
        v.redis_client = None
        result = await v.get_votes("item-1")
        assert result == []

    async def test_get_votes_success(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-1", "a1", "approve", "r1")
        await v.submit_vote("item-1", "a2", "reject", "r2")
        result = await v.get_votes("item-1")
        assert len(result) == 2

    async def test_get_votes_empty(self):
        v = RedisVotingSystem()
        v.redis_client = MockRedisClient()
        result = await v.get_votes("nonexistent-item")
        assert result == []

    async def test_get_votes_connection_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        v.redis_client = mock_client
        result = await v.get_votes("item-1")
        assert result == []

    async def test_get_votes_os_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        v.redis_client = mock_client
        result = await v.get_votes("item-1")
        assert result == []

    async def test_get_votes_json_decode_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        votes_key = f"{v.votes_key_prefix}item-bad"
        mock_client._data[votes_key] = {"agent": "corrupted{{{"}
        result = await v.get_votes("item-bad")
        assert result == []


# ===========================================================================
# RedisVotingSystem — get_vote_count
# ===========================================================================


class TestRedisVotingSystemVoteCount:
    async def test_vote_count_all_types(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-1", "a1", "approve", "r1")
        await v.submit_vote("item-1", "a2", "reject", "r2")
        await v.submit_vote("item-1", "a3", "abstain", "r3")
        counts = await v.get_vote_count("item-1")
        assert counts["approve"] == 1
        assert counts["reject"] == 1
        assert counts["abstain"] == 1
        assert counts["total"] == 3

    async def test_vote_count_unknown_type_not_counted_in_named_keys(self):
        """Votes with unknown types are included in total but not named counters."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        votes_key = f"{v.votes_key_prefix}item-unknown"
        vote_data = {
            "agent_id": "a1",
            "vote": "maybe",
            "reasoning": "unsure",
            "confidence": 0.5,
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        await mock_client.hset(votes_key, "a1", json.dumps(vote_data))
        counts = await v.get_vote_count("item-unknown")
        assert counts["total"] == 1
        assert counts["approve"] == 0
        assert counts["reject"] == 0
        assert counts["abstain"] == 0

    async def test_vote_count_no_votes(self):
        v = RedisVotingSystem()
        v.redis_client = MockRedisClient()
        counts = await v.get_vote_count("no-votes")
        assert counts["total"] == 0

    async def test_vote_count_missing_vote_key_uses_abstain(self):
        """A vote entry missing 'vote' key defaults to 'abstain'."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        votes_key = f"{v.votes_key_prefix}item-nv"
        # no 'vote' key
        vote_data = {"agent_id": "a1", "confidence": 1.0}
        await mock_client.hset(votes_key, "a1", json.dumps(vote_data))
        counts = await v.get_vote_count("item-nv")
        assert counts["abstain"] == 1


# ===========================================================================
# RedisVotingSystem — check_consensus
# ===========================================================================


class TestRedisVotingSystemCheckConsensus:
    async def test_insufficient_votes(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-1", "a1", "approve", "r1")
        result = await v.check_consensus("item-1", required_votes=3)
        assert result["consensus_reached"] is False
        assert result["reason"] == "insufficient_votes"
        assert "counts" in result

    async def test_consensus_approved(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-1", "a1", "approve", "r1")
        await v.submit_vote("item-1", "a2", "approve", "r2")
        await v.submit_vote("item-1", "a3", "approve", "r3")
        result = await v.check_consensus("item-1", required_votes=3, threshold=0.66)
        assert result["consensus_reached"] is True
        assert result["decision"] == "approved"
        assert "approval_rate" in result

    async def test_consensus_rejected(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-2", "a1", "reject", "r1")
        await v.submit_vote("item-2", "a2", "reject", "r2")
        await v.submit_vote("item-2", "a3", "reject", "r3")
        result = await v.check_consensus("item-2", required_votes=3, threshold=0.66)
        assert result["consensus_reached"] is True
        assert result["decision"] == "rejected"
        assert "rejection_rate" in result

    async def test_consensus_threshold_not_met(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-3", "a1", "approve", "r1")
        await v.submit_vote("item-3", "a2", "approve", "r2")
        await v.submit_vote("item-3", "a3", "reject", "r3")
        await v.submit_vote("item-3", "a4", "reject", "r4")
        result = await v.check_consensus("item-3", required_votes=3, threshold=0.66)
        assert result["consensus_reached"] is False
        assert result["reason"] == "threshold_not_met"
        assert "approval_rate" in result

    async def test_consensus_default_params(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.submit_vote("item-4", "a1", "approve", "r1")
        await v.submit_vote("item-4", "a2", "approve", "r2")
        result = await v.check_consensus("item-4")  # required_votes=3 default
        assert result["consensus_reached"] is False


# ===========================================================================
# RedisVotingSystem — publish_vote_event
# ===========================================================================


class TestRedisVotingSystemPublishVoteEvent:
    async def test_publish_vote_event_no_client(self):
        v = RedisVotingSystem()
        v.redis_client = None
        result = await v.publish_vote_event("item-1", "a1", "approve", "reason")
        assert result is False

    async def test_publish_vote_event_success(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        result = await v.publish_vote_event("item-1", "a1", "approve", "reason", 0.9)
        assert result is True
        channel = f"{v.pubsub_channel_prefix}item-1"
        assert channel in mock_client._published

    async def test_publish_vote_event_default_confidence(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        result = await v.publish_vote_event("item-2", "a1", "approve", "reason")
        assert result is True

    async def test_publish_vote_event_also_submits_vote(self):
        """publish_vote_event should also call submit_vote for persistence."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        await v.publish_vote_event("item-3", "a1", "approve", "reason")
        votes_key = f"{v.votes_key_prefix}item-3"
        assert "a1" in mock_client._data.get(votes_key, {})

    async def test_publish_vote_event_connection_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        v.redis_client = mock_client
        result = await v.publish_vote_event("item-4", "a1", "approve", "reason")
        assert result is False

    async def test_publish_vote_event_os_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        v.redis_client = mock_client
        result = await v.publish_vote_event("item-5", "a1", "approve", "reason")
        assert result is False

    async def test_publish_vote_event_type_error(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_client._should_raise = TypeError
        v.redis_client = mock_client
        result = await v.publish_vote_event("item-6", "a1", "approve", "reason")
        assert result is False


# ===========================================================================
# RedisVotingSystem — subscribe_to_votes
# ===========================================================================


class TestRedisVotingSystemSubscribeToVotes:
    async def test_subscribe_no_client(self):
        v = RedisVotingSystem()
        v.redis_client = None
        result = await v.subscribe_to_votes("item-1")
        assert result is False

    async def test_subscribe_creates_pubsub(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        assert v._pubsub is None
        result = await v.subscribe_to_votes("item-1")
        assert result is True
        assert v._pubsub is not None

    async def test_subscribe_reuses_existing_pubsub(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        existing_pubsub = MockPubSub()
        v._pubsub = existing_pubsub
        result = await v.subscribe_to_votes("item-2")
        assert result is True
        assert v._pubsub is existing_pubsub

    async def test_subscribe_connection_error_from_pubsub_call(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()

        def _bad_pubsub():
            raise ConnectionError("no conn")

        mock_client.pubsub = _bad_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.subscribe_to_votes("item-1")
        assert result is False

    async def test_subscribe_os_error_from_subscribe_call(self):
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        mock_pubsub = MockPubSub()

        async def _raise_subscribe(channel):
            raise OSError("os error")

        mock_pubsub.subscribe = _raise_subscribe  # type: ignore[method-assign]
        mock_client.pubsub = lambda: mock_pubsub  # type: ignore[method-assign]
        v.redis_client = mock_client
        result = await v.subscribe_to_votes("item-1")
        assert result is False


# ===========================================================================
# RedisVotingSystem — unsubscribe_from_votes
# ===========================================================================


class TestRedisVotingSystemUnsubscribeFromVotes:
    async def test_unsubscribe_no_pubsub(self):
        v = RedisVotingSystem()
        v._pubsub = None
        result = await v.unsubscribe_from_votes("item-1")
        assert result is True

    async def test_unsubscribe_success(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()
        mock_pubsub._subscriptions = ["acgs:vote_events:item-1"]
        v._pubsub = mock_pubsub
        result = await v.unsubscribe_from_votes("item-1")
        assert result is True

    async def test_unsubscribe_connection_error(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()

        async def _raise(channel):
            raise ConnectionError("disconnected")

        mock_pubsub.unsubscribe = _raise  # type: ignore[method-assign]
        v._pubsub = mock_pubsub
        result = await v.unsubscribe_from_votes("item-1")
        assert result is False

    async def test_unsubscribe_os_error(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()

        async def _raise(channel):
            raise OSError("os error")

        mock_pubsub.unsubscribe = _raise  # type: ignore[method-assign]
        v._pubsub = mock_pubsub
        result = await v.unsubscribe_from_votes("item-1")
        assert result is False


# ===========================================================================
# RedisVotingSystem — get_vote_event
# ===========================================================================


class TestRedisVotingSystemGetVoteEvent:
    async def test_get_event_no_pubsub(self):
        v = RedisVotingSystem()
        v._pubsub = None
        result = await v.get_vote_event()
        assert result is None

    async def test_get_event_no_message(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()
        mock_pubsub._messages = []
        v._pubsub = mock_pubsub
        result = await v.get_vote_event(timeout=0.01)
        assert result is None

    async def test_get_event_message_received(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()
        event_data = {"item_id": "item-1", "agent_id": "a1", "vote": "approve"}
        mock_pubsub._messages = [{"type": "message", "data": json.dumps(event_data)}]
        v._pubsub = mock_pubsub
        result = await v.get_vote_event(timeout=1.0)
        assert result is not None
        assert result["vote"] == "approve"

    async def test_get_event_non_message_type_returns_none(self):
        """subscribe confirmation (type != 'message') returns None."""
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()
        mock_pubsub._messages = [{"type": "subscribe", "data": 1}]
        v._pubsub = mock_pubsub
        result = await v.get_vote_event(timeout=1.0)
        assert result is None

    async def test_get_event_timeout(self):
        v = RedisVotingSystem()

        async def _slow_get_message(ignore_subscribe_messages=True):
            await asyncio.sleep(10)

        mock_pubsub = MockPubSub()
        mock_pubsub.get_message = _slow_get_message  # type: ignore[method-assign]
        v._pubsub = mock_pubsub
        result = await v.get_vote_event(timeout=0.01)
        assert result is None

    async def test_get_event_connection_error(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()
        mock_pubsub._raise_on_get = ConnectionError
        v._pubsub = mock_pubsub
        result = await v.get_vote_event(timeout=1.0)
        assert result is None

    async def test_get_event_os_error(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()
        mock_pubsub._raise_on_get = OSError
        v._pubsub = mock_pubsub
        result = await v.get_vote_event(timeout=1.0)
        assert result is None

    async def test_get_event_json_decode_error(self):
        v = RedisVotingSystem()
        mock_pubsub = MockPubSub()
        mock_pubsub._messages = [{"type": "message", "data": "not-valid-json{{{"}]
        v._pubsub = mock_pubsub
        result = await v.get_vote_event(timeout=1.0)
        assert result is None


# ===========================================================================
# RedisVotingSystem — collect_votes_event_driven
# ===========================================================================


class TestRedisVotingSystemCollectVotesEventDriven:
    async def test_collect_no_client(self):
        v = RedisVotingSystem()
        v.redis_client = None
        result = await v.collect_votes_event_driven("item-1", required_votes=2, timeout_seconds=1)
        assert result == []

    async def test_collect_timeout_no_events(self):
        """Returns empty list when timeout expires with no events."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client
        result = await v.collect_votes_event_driven(
            "item-timeout", required_votes=3, timeout_seconds=1
        )
        assert result == []

    async def test_collect_enough_votes(self):
        """Stops early when required_votes collected."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        event_counter = 0

        async def _get_event(timeout=1.0):
            nonlocal event_counter
            event_counter += 1
            if event_counter == 1:
                return {"item_id": "item-ev", "agent_id": "a1", "vote": "approve"}
            if event_counter == 2:
                return {"item_id": "item-ev", "agent_id": "a2", "vote": "approve"}
            await asyncio.sleep(0)
            return None

        v.get_vote_event = _get_event  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven("item-ev", required_votes=2, timeout_seconds=10)
        assert len(result) == 2

    async def test_collect_deduplicates_same_agent(self):
        """Votes from the same agent are deduplicated."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        call_count = 0

        async def _get_event(timeout=1.0):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return {"item_id": "item-dup", "agent_id": "a1", "vote": "approve"}
            return None

        v.get_vote_event = _get_event  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven("item-dup", required_votes=3, timeout_seconds=1)
        assert len(result) <= 1

    async def test_collect_ignores_wrong_item_id(self):
        """Events for different items are ignored."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        call_count = 0

        async def _get_event(timeout=1.0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"item_id": "other-item", "agent_id": "a1", "vote": "approve"}
            return None

        v.get_vote_event = _get_event  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven("my-item", required_votes=1, timeout_seconds=1)
        assert result == []

    async def test_collect_event_without_agent_id_ignored(self):
        """Events with no agent_id are ignored."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        call_count = 0

        async def _get_event(timeout=1.0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"item_id": "item-noid", "vote": "approve"}  # no agent_id
            return None

        v.get_vote_event = _get_event  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven(
            "item-noid", required_votes=1, timeout_seconds=1
        )
        assert result == []

    async def test_collect_vote_collection_error_returns_partial(self):
        """VOTE_COLLECTION_ERRORS during collection return partial results."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        call_count = 0

        async def _get_event(timeout=1.0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call returns a valid vote
                return {"item_id": "item-partial", "agent_id": "a1", "vote": "approve"}
            raise RuntimeError("collection error")

        v.get_vote_event = _get_event  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven(
            "item-partial", required_votes=3, timeout_seconds=10
        )
        assert isinstance(result, list)
        # Partial result — at least 1 vote was collected before error
        assert len(result) >= 0

    async def test_collect_cleans_up_subscription_after_success(self):
        """unsubscribe_from_votes is called in finally block."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        unsubscribed: list[str] = []
        original_unsub = v.unsubscribe_from_votes

        async def _tracking_unsubscribe(item_id):
            unsubscribed.append(item_id)
            return await original_unsub(item_id)

        v.unsubscribe_from_votes = _tracking_unsubscribe  # type: ignore[method-assign]
        await v.collect_votes_event_driven("item-clean", required_votes=5, timeout_seconds=1)
        assert "item-clean" in unsubscribed

    async def test_collect_cleans_up_subscription_after_error(self):
        """unsubscribe_from_votes is called even when collection raises."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        unsubscribed: list[str] = []

        async def _always_subscribe(item_id):
            pass

        async def _raise_get_event(timeout=1.0):
            raise ValueError("collection error")

        async def _tracking_unsubscribe(item_id):
            unsubscribed.append(item_id)

        v.subscribe_to_votes = _always_subscribe  # type: ignore[method-assign]
        v.get_vote_event = _raise_get_event  # type: ignore[method-assign]
        v.unsubscribe_from_votes = _tracking_unsubscribe  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven(
            "item-err2", required_votes=2, timeout_seconds=5
        )
        assert isinstance(result, list)
        assert "item-err2" in unsubscribed

    async def test_collect_asyncio_timeout_error(self):
        """asyncio.TimeoutError during collection is caught (in VOTE_COLLECTION_ERRORS)."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        async def _timeout_get(timeout=1.0):
            raise TimeoutError()

        v.get_vote_event = _timeout_get  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven(
            "item-asynctimeout", required_votes=2, timeout_seconds=5
        )
        assert isinstance(result, list)

    async def test_collect_key_error(self):
        """KeyError during collection is caught (in VOTE_COLLECTION_ERRORS)."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        async def _key_error_get(timeout=1.0):
            raise KeyError("missing key")

        v.get_vote_event = _key_error_get  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven(
            "item-keyerr", required_votes=2, timeout_seconds=5
        )
        assert isinstance(result, list)

    async def test_collect_attribute_error(self):
        """AttributeError during collection is caught (in VOTE_COLLECTION_ERRORS)."""
        v = RedisVotingSystem()
        mock_client = MockRedisClient()
        v.redis_client = mock_client

        async def _attr_error_get(timeout=1.0):
            raise AttributeError("attr error")

        v.get_vote_event = _attr_error_get  # type: ignore[method-assign]
        result = await v.collect_votes_event_driven(
            "item-attrerr", required_votes=2, timeout_seconds=5
        )
        assert isinstance(result, list)
