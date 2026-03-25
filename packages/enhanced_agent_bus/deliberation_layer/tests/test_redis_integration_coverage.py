"""
Tests for deliberation_layer/redis_integration.py targeting ≥90% coverage.
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.deliberation_layer.redis_integration import (
    REDIS_AVAILABLE,
    RedisDeliberationQueue,
    RedisVotingSystem,
    get_redis_deliberation_queue,
    get_redis_voting_system,
    reset_all_redis_singletons,
    reset_redis_deliberation_queue,
    reset_redis_voting_system,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_redis_client():
    """Return a fully mocked async Redis client."""
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    client.close = AsyncMock()
    client.xadd = AsyncMock(return_value="1-0")
    client.hset = AsyncMock(return_value=1)
    client.hget = AsyncMock(return_value=None)
    client.hgetall = AsyncMock(return_value={})
    client.hdel = AsyncMock(return_value=1)
    client.xinfo_stream = AsyncMock(
        return_value={"length": 5, "first-entry": "a", "last-entry": "z"}
    )
    client.expire = AsyncMock(return_value=True)
    client.publish = AsyncMock(return_value=1)
    return client


def _make_message(
    message_id: str = "msg-001",
    from_agent: str = "agent-a",
    to_agent: str = "agent-b",
    content=None,
    type_value: str = "REQUEST",
):
    msg = MagicMock()
    msg.message_id = message_id
    msg.from_agent = from_agent
    msg.to_agent = to_agent
    msg.content = content or {"key": "value"}
    msg_type = MagicMock()
    msg_type.value = type_value
    msg.message_type = msg_type
    return msg


def _make_pubsub(*, messages=None):
    """Return a mocked pubsub object."""
    ps = MagicMock()
    ps.subscribe = AsyncMock()
    ps.unsubscribe = AsyncMock()
    ps.close = AsyncMock()
    _msgs = list(messages or [])

    async def _get_message(ignore_subscribe_messages=True):
        if _msgs:
            return _msgs.pop(0)
        return None

    ps.get_message = _get_message
    return ps


# ===========================================================================
# RedisDeliberationQueue - connect / disconnect
# ===========================================================================


class TestRedisDeliberationQueueConnect:
    async def test_connect_redis_not_available(self):
        q = RedisDeliberationQueue()
        with patch(
            "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
            False,
        ):
            result = await q.connect()
        assert result is False
        assert q.redis_client is None

    async def test_connect_success(self):
        q = RedisDeliberationQueue()
        mock_client = _make_mock_redis_client()
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = MagicMock(return_value=mock_client)
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.aioredis",
                mock_aioredis,
            ),
        ):
            result = await q.connect()
        assert result is True
        assert q.redis_client is mock_client

    async def test_connect_connection_error(self):
        q = RedisDeliberationQueue()
        mock_client = _make_mock_redis_client()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("refused"))
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = MagicMock(return_value=mock_client)
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.aioredis",
                mock_aioredis,
            ),
        ):
            result = await q.connect()
        assert result is False
        assert q.redis_client is None

    async def test_connect_os_error(self):
        q = RedisDeliberationQueue()
        mock_client = _make_mock_redis_client()
        mock_client.ping = AsyncMock(side_effect=OSError("network"))
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = MagicMock(return_value=mock_client)
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.aioredis",
                mock_aioredis,
            ),
        ):
            result = await q.connect()
        assert result is False

    async def test_disconnect_with_client(self):
        q = RedisDeliberationQueue()
        mock_client = _make_mock_redis_client()
        q.redis_client = mock_client
        await q.disconnect()
        mock_client.close.assert_called_once()
        assert q.redis_client is None

    async def test_disconnect_without_client(self):
        q = RedisDeliberationQueue()
        # Should not raise
        await q.disconnect()


# ===========================================================================
# RedisDeliberationQueue - enqueue
# ===========================================================================


class TestEnqueueDeliberationItem:
    async def test_enqueue_no_client(self):
        q = RedisDeliberationQueue()
        msg = _make_message()
        result = await q.enqueue_deliberation_item(msg, "item-1")
        assert result is False

    async def test_enqueue_success(self):
        q = RedisDeliberationQueue()
        q.redis_client = _make_mock_redis_client()
        msg = _make_message()
        result = await q.enqueue_deliberation_item(msg, "item-1", {"extra": "data"})
        assert result is True
        q.redis_client.xadd.assert_called_once()
        q.redis_client.hset.assert_called_once()

    async def test_enqueue_success_no_metadata(self):
        q = RedisDeliberationQueue()
        q.redis_client = _make_mock_redis_client()
        msg = _make_message()
        result = await q.enqueue_deliberation_item(msg, "item-2")
        assert result is True

    async def test_enqueue_connection_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.xadd = AsyncMock(side_effect=ConnectionError("dead"))
        q.redis_client = client
        msg = _make_message()
        result = await q.enqueue_deliberation_item(msg, "item-3")
        assert result is False

    async def test_enqueue_os_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hset = AsyncMock(side_effect=OSError("pipe"))
        q.redis_client = client
        msg = _make_message()
        result = await q.enqueue_deliberation_item(msg, "item-4")
        assert result is False

    async def test_enqueue_type_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.xadd = AsyncMock(side_effect=TypeError("bad type"))
        q.redis_client = client
        msg = _make_message()
        result = await q.enqueue_deliberation_item(msg, "item-5")
        assert result is False


# ===========================================================================
# RedisDeliberationQueue - get_deliberation_item
# ===========================================================================


class TestGetDeliberationItem:
    async def test_get_no_client(self):
        q = RedisDeliberationQueue()
        result = await q.get_deliberation_item("x")
        assert result is None

    async def test_get_found(self):
        q = RedisDeliberationQueue()
        data = {"item_id": "x", "status": "pending"}
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value=json.dumps(data))
        q.redis_client = client
        result = await q.get_deliberation_item("x")
        assert result == data

    async def test_get_not_found(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value=None)
        q.redis_client = client
        result = await q.get_deliberation_item("missing")
        assert result is None

    async def test_get_connection_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hget = AsyncMock(side_effect=ConnectionError("gone"))
        q.redis_client = client
        result = await q.get_deliberation_item("x")
        assert result is None

    async def test_get_json_decode_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value="not-valid-json{{{")
        q.redis_client = client
        result = await q.get_deliberation_item("x")
        assert result is None


# ===========================================================================
# RedisDeliberationQueue - update_deliberation_status
# ===========================================================================


class TestUpdateDeliberationStatus:
    async def test_update_no_client(self):
        q = RedisDeliberationQueue()
        result = await q.update_deliberation_status("x", "approved")
        assert result is False

    async def test_update_item_not_found(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value=None)
        q.redis_client = client
        result = await q.update_deliberation_status("missing", "approved")
        assert result is False

    async def test_update_success(self):
        q = RedisDeliberationQueue()
        data = {"item_id": "x", "status": "pending"}
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value=json.dumps(data))
        q.redis_client = client
        result = await q.update_deliberation_status("x", "approved")
        assert result is True
        client.hset.assert_called_once()

    async def test_update_with_additional_data(self):
        q = RedisDeliberationQueue()
        data = {"item_id": "x", "status": "pending"}
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value=json.dumps(data))
        q.redis_client = client
        result = await q.update_deliberation_status("x", "approved", {"reviewer": "alice"})
        assert result is True

    async def test_update_connection_error(self):
        q = RedisDeliberationQueue()
        data = {"item_id": "x", "status": "pending"}
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value=json.dumps(data))
        client.hset = AsyncMock(side_effect=ConnectionError("dead"))
        q.redis_client = client
        result = await q.update_deliberation_status("x", "approved")
        assert result is False

    async def test_update_os_error(self):
        q = RedisDeliberationQueue()
        data = {"item_id": "x"}
        client = _make_mock_redis_client()
        client.hget = AsyncMock(return_value=json.dumps(data))
        client.hset = AsyncMock(side_effect=OSError("pipe"))
        q.redis_client = client
        result = await q.update_deliberation_status("x", "done")
        assert result is False


# ===========================================================================
# RedisDeliberationQueue - remove_deliberation_item
# ===========================================================================


class TestRemoveDeliberationItem:
    async def test_remove_no_client(self):
        q = RedisDeliberationQueue()
        result = await q.remove_deliberation_item("x")
        assert result is False

    async def test_remove_success(self):
        q = RedisDeliberationQueue()
        q.redis_client = _make_mock_redis_client()
        result = await q.remove_deliberation_item("x")
        assert result is True

    async def test_remove_connection_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hdel = AsyncMock(side_effect=ConnectionError("gone"))
        q.redis_client = client
        result = await q.remove_deliberation_item("x")
        assert result is False

    async def test_remove_os_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hdel = AsyncMock(side_effect=OSError("pipe"))
        q.redis_client = client
        result = await q.remove_deliberation_item("x")
        assert result is False


# ===========================================================================
# RedisDeliberationQueue - get_pending_items
# ===========================================================================


class TestGetPendingItems:
    async def test_get_pending_no_client(self):
        q = RedisDeliberationQueue()
        result = await q.get_pending_items()
        assert result == []

    async def test_get_pending_empty(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value={})
        q.redis_client = client
        result = await q.get_pending_items()
        assert result == []

    async def test_get_pending_with_pending_items(self):
        q = RedisDeliberationQueue()
        items = {
            "a": json.dumps({"item_id": "a", "status": "pending"}),
            "b": json.dumps({"item_id": "b", "status": "approved"}),
            "c": json.dumps({"item_id": "c"}),  # no status defaults to pending
        }
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value=items)
        q.redis_client = client
        result = await q.get_pending_items()
        # "a" (pending) and "c" (no status → "pending") should be returned
        assert len(result) == 2

    async def test_get_pending_limit(self):
        q = RedisDeliberationQueue()
        items = {str(i): json.dumps({"item_id": str(i)}) for i in range(10)}
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value=items)
        q.redis_client = client
        result = await q.get_pending_items(limit=3)
        assert len(result) == 3

    async def test_get_pending_connection_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(side_effect=ConnectionError("gone"))
        q.redis_client = client
        result = await q.get_pending_items()
        assert result == []

    async def test_get_pending_json_decode_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value={"a": "bad-json{{{"})
        q.redis_client = client
        result = await q.get_pending_items()
        assert result == []


# ===========================================================================
# RedisDeliberationQueue - get_stream_info
# ===========================================================================


class TestGetStreamInfo:
    async def test_get_stream_info_no_client(self):
        q = RedisDeliberationQueue()
        result = await q.get_stream_info()
        assert "error" in result

    async def test_get_stream_info_success(self):
        q = RedisDeliberationQueue()
        q.redis_client = _make_mock_redis_client()
        result = await q.get_stream_info()
        assert "length" in result
        assert result["length"] == 5

    async def test_get_stream_info_connection_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.xinfo_stream = AsyncMock(side_effect=ConnectionError("gone"))
        q.redis_client = client
        result = await q.get_stream_info()
        assert "error" in result

    async def test_get_stream_info_os_error(self):
        q = RedisDeliberationQueue()
        client = _make_mock_redis_client()
        client.xinfo_stream = AsyncMock(side_effect=OSError("network"))
        q.redis_client = client
        result = await q.get_stream_info()
        assert "error" in result


# ===========================================================================
# RedisVotingSystem - connect / disconnect
# ===========================================================================


class TestRedisVotingSystemConnect:
    async def test_connect_redis_not_available(self):
        vs = RedisVotingSystem()
        with patch(
            "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
            False,
        ):
            result = await vs.connect()
        assert result is False

    async def test_connect_success(self):
        vs = RedisVotingSystem()
        mock_client = _make_mock_redis_client()
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = MagicMock(return_value=mock_client)
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.aioredis",
                mock_aioredis,
            ),
        ):
            result = await vs.connect()
        assert result is True

    async def test_connect_connection_error(self):
        vs = RedisVotingSystem()
        mock_client = _make_mock_redis_client()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("refused"))
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = MagicMock(return_value=mock_client)
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.aioredis",
                mock_aioredis,
            ),
        ):
            result = await vs.connect()
        assert result is False
        assert vs.redis_client is None

    async def test_connect_os_error(self):
        vs = RedisVotingSystem()
        mock_client = _make_mock_redis_client()
        mock_client.ping = AsyncMock(side_effect=OSError("net"))
        mock_aioredis = MagicMock()
        mock_aioredis.from_url = MagicMock(return_value=mock_client)
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.redis_integration.aioredis",
                mock_aioredis,
            ),
        ):
            result = await vs.connect()
        assert result is False

    async def test_disconnect_with_pubsub_and_client(self):
        vs = RedisVotingSystem()
        ps = _make_pubsub()
        vs._pubsub = ps
        mock_client = _make_mock_redis_client()
        vs.redis_client = mock_client
        await vs.disconnect()
        ps.unsubscribe.assert_called_once()
        ps.close.assert_called_once()
        mock_client.close.assert_called_once()
        assert vs._pubsub is None
        assert vs.redis_client is None

    async def test_disconnect_no_pubsub_no_client(self):
        vs = RedisVotingSystem()
        # Should not raise
        await vs.disconnect()

    async def test_disconnect_with_client_only(self):
        vs = RedisVotingSystem()
        mock_client = _make_mock_redis_client()
        vs.redis_client = mock_client
        await vs.disconnect()
        mock_client.close.assert_called_once()


# ===========================================================================
# RedisVotingSystem - submit_vote
# ===========================================================================


class TestSubmitVote:
    async def test_submit_no_client(self):
        vs = RedisVotingSystem()
        result = await vs.submit_vote("item-1", "agent-a", "approve", "good", 0.9)
        assert result is False

    async def test_submit_success(self):
        vs = RedisVotingSystem()
        vs.redis_client = _make_mock_redis_client()
        result = await vs.submit_vote("item-1", "agent-a", "approve", "looks good", 0.95)
        assert result is True
        vs.redis_client.hset.assert_called_once()
        vs.redis_client.expire.assert_called_once()
        vs.redis_client.publish.assert_called_once()

    async def test_submit_connection_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.hset = AsyncMock(side_effect=ConnectionError("gone"))
        vs.redis_client = client
        result = await vs.submit_vote("item-1", "agent-a", "reject", "bad", 0.1)
        assert result is False

    async def test_submit_os_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.expire = AsyncMock(side_effect=OSError("net"))
        vs.redis_client = client
        result = await vs.submit_vote("item-1", "agent-a", "abstain", "unsure", 0.5)
        assert result is False

    async def test_submit_type_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.publish = AsyncMock(side_effect=TypeError("bad"))
        vs.redis_client = client
        result = await vs.submit_vote("item-1", "agent-a", "approve", "ok", 1.0)
        assert result is False


# ===========================================================================
# RedisVotingSystem - get_votes_pubsub_instance
# ===========================================================================


class TestGetVotesPubsubInstance:
    async def test_get_pubsub_no_client(self):
        vs = RedisVotingSystem()
        result = await vs.get_votes_pubsub_instance("item-1")
        assert result is None

    async def test_get_pubsub_success(self):
        vs = RedisVotingSystem()
        ps = _make_pubsub()
        mock_client = _make_mock_redis_client()
        mock_client.pubsub = MagicMock(return_value=ps)
        vs.redis_client = mock_client
        result = await vs.get_votes_pubsub_instance("item-1")
        assert result is ps
        ps.subscribe.assert_called_once()

    async def test_get_pubsub_error(self):
        vs = RedisVotingSystem()
        mock_client = _make_mock_redis_client()
        ps = MagicMock()
        ps.subscribe = AsyncMock(side_effect=RuntimeError("broken"))
        mock_client.pubsub = MagicMock(return_value=ps)
        vs.redis_client = mock_client
        result = await vs.get_votes_pubsub_instance("item-1")
        assert result is None


# ===========================================================================
# RedisVotingSystem - get_votes
# ===========================================================================


class TestGetVotes:
    async def test_get_votes_no_client(self):
        vs = RedisVotingSystem()
        result = await vs.get_votes("item-1")
        assert result == []

    async def test_get_votes_success(self):
        vs = RedisVotingSystem()
        vote_data = {"agent_id": "a", "vote": "approve"}
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value={"a": json.dumps(vote_data)})
        vs.redis_client = client
        result = await vs.get_votes("item-1")
        assert len(result) == 1
        assert result[0]["vote"] == "approve"

    async def test_get_votes_empty(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value={})
        vs.redis_client = client
        result = await vs.get_votes("item-1")
        assert result == []

    async def test_get_votes_connection_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(side_effect=ConnectionError("dead"))
        vs.redis_client = client
        result = await vs.get_votes("item-1")
        assert result == []

    async def test_get_votes_json_decode_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value={"a": "bad-json{{{"})
        vs.redis_client = client
        result = await vs.get_votes("item-1")
        assert result == []


# ===========================================================================
# RedisVotingSystem - get_vote_count
# ===========================================================================


class TestGetVoteCount:
    async def test_vote_count_empty(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value={})
        vs.redis_client = client
        counts = await vs.get_vote_count("item-1")
        assert counts["total"] == 0
        assert counts["approve"] == 0

    async def test_vote_count_mixed(self):
        vs = RedisVotingSystem()
        votes = {
            "a": json.dumps({"vote": "approve"}),
            "b": json.dumps({"vote": "reject"}),
            "c": json.dumps({"vote": "abstain"}),
            "d": json.dumps({"vote": "approve"}),
        }
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value=votes)
        vs.redis_client = client
        counts = await vs.get_vote_count("item-1")
        assert counts["total"] == 4
        assert counts["approve"] == 2
        assert counts["reject"] == 1
        assert counts["abstain"] == 1

    async def test_vote_count_unknown_vote_type(self):
        """Unknown vote types are counted in total but not in any bucket."""
        vs = RedisVotingSystem()
        votes = {"a": json.dumps({"vote": "maybe"})}
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value=votes)
        vs.redis_client = client
        counts = await vs.get_vote_count("item-1")
        assert counts["total"] == 1
        assert counts["approve"] == 0


# ===========================================================================
# RedisVotingSystem - check_consensus
# ===========================================================================


class TestCheckConsensus:
    async def _setup_votes(self, vs, vote_list):
        """Helper: configure redis_client to return given vote_list."""
        raw = {str(i): json.dumps(v) for i, v in enumerate(vote_list)}
        client = _make_mock_redis_client()
        client.hgetall = AsyncMock(return_value=raw)
        vs.redis_client = client

    async def test_insufficient_votes(self):
        vs = RedisVotingSystem()
        await self._setup_votes(vs, [{"vote": "approve"}])
        result = await vs.check_consensus("item-1", required_votes=3)
        assert result["consensus_reached"] is False
        assert result["reason"] == "insufficient_votes"

    async def test_consensus_approved(self):
        vs = RedisVotingSystem()
        await self._setup_votes(
            vs,
            [{"vote": "approve"}, {"vote": "approve"}, {"vote": "reject"}],
        )
        result = await vs.check_consensus("item-1", required_votes=3, threshold=0.66)
        assert result["consensus_reached"] is True
        assert result["decision"] == "approved"

    async def test_consensus_rejected(self):
        vs = RedisVotingSystem()
        await self._setup_votes(
            vs,
            [{"vote": "reject"}, {"vote": "reject"}, {"vote": "approve"}],
        )
        result = await vs.check_consensus("item-1", required_votes=3, threshold=0.66)
        assert result["consensus_reached"] is True
        assert result["decision"] == "rejected"

    async def test_no_threshold_met(self):
        vs = RedisVotingSystem()
        await self._setup_votes(
            vs,
            [
                {"vote": "approve"},
                {"vote": "reject"},
                {"vote": "abstain"},
            ],
        )
        result = await vs.check_consensus("item-1", required_votes=3, threshold=0.66)
        assert result["consensus_reached"] is False
        assert result["reason"] == "threshold_not_met"


# ===========================================================================
# RedisVotingSystem - publish_vote_event
# ===========================================================================


class TestPublishVoteEvent:
    async def test_publish_no_client(self):
        vs = RedisVotingSystem()
        result = await vs.publish_vote_event("item-1", "agent-a", "approve", "ok")
        assert result is False

    async def test_publish_success(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        vs.redis_client = client
        result = await vs.publish_vote_event("item-1", "agent-a", "approve", "ok", 1.0)
        assert result is True
        # publish called once for the event, plus submit_vote calls publish again
        assert client.publish.call_count >= 1

    async def test_publish_connection_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.publish = AsyncMock(side_effect=ConnectionError("gone"))
        vs.redis_client = client
        result = await vs.publish_vote_event("item-1", "agent-a", "approve", "ok")
        assert result is False

    async def test_publish_os_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.publish = AsyncMock(side_effect=OSError("network"))
        vs.redis_client = client
        result = await vs.publish_vote_event("item-1", "agent-a", "approve", "ok")
        assert result is False

    async def test_publish_type_error(self):
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        client.publish = AsyncMock(side_effect=TypeError("bad"))
        vs.redis_client = client
        result = await vs.publish_vote_event("item-1", "agent-a", "approve", "ok")
        assert result is False


# ===========================================================================
# RedisVotingSystem - subscribe_to_votes / unsubscribe_from_votes
# ===========================================================================


class TestSubscribeUnsubscribe:
    async def test_subscribe_no_client(self):
        vs = RedisVotingSystem()
        result = await vs.subscribe_to_votes("item-1")
        assert result is False

    async def test_subscribe_creates_pubsub(self):
        vs = RedisVotingSystem()
        ps = _make_pubsub()
        client = _make_mock_redis_client()
        client.pubsub = MagicMock(return_value=ps)
        vs.redis_client = client
        result = await vs.subscribe_to_votes("item-1")
        assert result is True
        assert vs._pubsub is ps

    async def test_subscribe_reuses_pubsub(self):
        vs = RedisVotingSystem()
        ps = _make_pubsub()
        vs._pubsub = ps
        client = _make_mock_redis_client()
        vs.redis_client = client
        result = await vs.subscribe_to_votes("item-1")
        assert result is True
        # pubsub() factory should not be called again
        client.pubsub.assert_not_called()

    async def test_subscribe_connection_error(self):
        vs = RedisVotingSystem()
        ps = MagicMock()
        ps.subscribe = AsyncMock(side_effect=ConnectionError("gone"))
        client = _make_mock_redis_client()
        client.pubsub = MagicMock(return_value=ps)
        vs.redis_client = client
        result = await vs.subscribe_to_votes("item-1")
        assert result is False

    async def test_unsubscribe_no_pubsub(self):
        vs = RedisVotingSystem()
        result = await vs.unsubscribe_from_votes("item-1")
        assert result is True  # returns True when no pubsub

    async def test_unsubscribe_success(self):
        vs = RedisVotingSystem()
        ps = _make_pubsub()
        vs._pubsub = ps
        result = await vs.unsubscribe_from_votes("item-1")
        assert result is True
        ps.unsubscribe.assert_called_once()

    async def test_unsubscribe_connection_error(self):
        vs = RedisVotingSystem()
        ps = MagicMock()
        ps.unsubscribe = AsyncMock(side_effect=ConnectionError("gone"))
        vs._pubsub = ps
        result = await vs.unsubscribe_from_votes("item-1")
        assert result is False

    async def test_unsubscribe_os_error(self):
        vs = RedisVotingSystem()
        ps = MagicMock()
        ps.unsubscribe = AsyncMock(side_effect=OSError("net"))
        vs._pubsub = ps
        result = await vs.unsubscribe_from_votes("item-1")
        assert result is False


# ===========================================================================
# RedisVotingSystem - get_vote_event
# ===========================================================================


class TestGetVoteEvent:
    async def test_get_vote_event_no_pubsub(self):
        vs = RedisVotingSystem()
        result = await vs.get_vote_event(timeout=0.1)
        assert result is None

    async def test_get_vote_event_message_received(self):
        vs = RedisVotingSystem()
        vote_data = {"item_id": "item-1", "vote": "approve"}
        message = {"type": "message", "data": json.dumps(vote_data)}
        ps = _make_pubsub(messages=[message])
        vs._pubsub = ps
        result = await vs.get_vote_event(timeout=1.0)
        assert result == vote_data

    async def test_get_vote_event_non_message_type(self):
        """Messages with type != 'message' return None."""
        vs = RedisVotingSystem()
        message = {"type": "subscribe", "data": "1"}
        ps = _make_pubsub(messages=[message])
        vs._pubsub = ps
        result = await vs.get_vote_event(timeout=1.0)
        assert result is None

    async def test_get_vote_event_no_message(self):
        vs = RedisVotingSystem()
        ps = _make_pubsub(messages=[])  # no messages
        vs._pubsub = ps
        result = await vs.get_vote_event(timeout=0.05)
        assert result is None

    async def test_get_vote_event_timeout(self):
        """Simulate asyncio.TimeoutError from wait_for."""
        vs = RedisVotingSystem()

        async def _slow_get(ignore_subscribe_messages=True):
            await asyncio.sleep(10)

        ps = MagicMock()
        ps.get_message = _slow_get
        vs._pubsub = ps
        result = await vs.get_vote_event(timeout=0.01)
        assert result is None

    async def test_get_vote_event_connection_error(self):
        vs = RedisVotingSystem()

        async def _boom(ignore_subscribe_messages=True):
            raise ConnectionError("gone")

        ps = MagicMock()
        ps.get_message = _boom
        vs._pubsub = ps
        result = await vs.get_vote_event(timeout=1.0)
        assert result is None

    async def test_get_vote_event_json_decode_error(self):
        vs = RedisVotingSystem()
        message = {"type": "message", "data": "not-json{{{"}
        ps = _make_pubsub(messages=[message])
        vs._pubsub = ps
        result = await vs.get_vote_event(timeout=1.0)
        assert result is None


# ===========================================================================
# RedisVotingSystem - collect_votes_event_driven
# ===========================================================================


class TestCollectVotesEventDriven:
    async def test_collect_no_client(self):
        vs = RedisVotingSystem()
        result = await vs.collect_votes_event_driven("item-1", required_votes=2, timeout_seconds=1)
        assert result == []

    async def test_collect_success(self):
        """Collect exactly required_votes unique votes."""
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        vs.redis_client = client

        # Override subscribe_to_votes and unsubscribe_from_votes
        votes_to_emit = [
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "agent_id": "a", "vote": "approve"}),
            },
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "agent_id": "b", "vote": "reject"}),
            },
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "agent_id": "c", "vote": "approve"}),
            },
        ]
        ps = _make_pubsub(messages=votes_to_emit)
        client.pubsub = MagicMock(return_value=ps)

        result = await vs.collect_votes_event_driven("item-1", required_votes=2, timeout_seconds=5)
        assert len(result) == 2

    async def test_collect_deduplicates_votes(self):
        """Same agent voting twice should only count once."""
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        vs.redis_client = client

        votes_to_emit = [
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "agent_id": "a", "vote": "approve"}),
            },
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "agent_id": "a", "vote": "approve"}),
            },
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "agent_id": "b", "vote": "reject"}),
            },
        ]
        ps = _make_pubsub(messages=votes_to_emit)
        client.pubsub = MagicMock(return_value=ps)

        result = await vs.collect_votes_event_driven("item-1", required_votes=3, timeout_seconds=1)
        # Only 2 unique agents; timeout should stop collection
        assert len(result) <= 2

    async def test_collect_ignores_wrong_item_id(self):
        """Events for a different item_id are skipped."""
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        vs.redis_client = client

        votes_to_emit = [
            {
                "type": "message",
                "data": json.dumps({"item_id": "other-item", "agent_id": "a", "vote": "approve"}),
            },
        ]
        ps = _make_pubsub(messages=votes_to_emit)
        client.pubsub = MagicMock(return_value=ps)

        result = await vs.collect_votes_event_driven("item-1", required_votes=1, timeout_seconds=0)
        assert result == []

    async def test_collect_timeout(self):
        """Times out before collecting required_votes."""
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        vs.redis_client = client

        ps = _make_pubsub(messages=[])
        client.pubsub = MagicMock(return_value=ps)

        result = await vs.collect_votes_event_driven("item-1", required_votes=5, timeout_seconds=0)
        assert result == []

    async def test_collect_exception_returns_partial(self):
        """On error, returns whatever was collected so far."""
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        vs.redis_client = client

        ps = _make_pubsub()
        ps.subscribe = AsyncMock(side_effect=RuntimeError("boom"))
        client.pubsub = MagicMock(return_value=ps)

        result = await vs.collect_votes_event_driven("item-1", required_votes=3, timeout_seconds=1)
        # Should return [] or partial on error
        assert isinstance(result, list)

    async def test_collect_event_without_agent_id(self):
        """Events with no agent_id are skipped (not added to seen_agents)."""
        vs = RedisVotingSystem()
        client = _make_mock_redis_client()
        vs.redis_client = client

        votes_to_emit = [
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "vote": "approve"}),
            },  # no agent_id
            {
                "type": "message",
                "data": json.dumps({"item_id": "item-1", "agent_id": "b", "vote": "reject"}),
            },
        ]
        ps = _make_pubsub(messages=votes_to_emit)
        client.pubsub = MagicMock(return_value=ps)

        result = await vs.collect_votes_event_driven("item-1", required_votes=3, timeout_seconds=1)
        # Only "b" counted; no timeout so returns 1
        assert len(result) <= 1


# ===========================================================================
# Module-level singletons and reset functions
# ===========================================================================


class TestSingletons:
    def setup_method(self):
        reset_all_redis_singletons()

    def teardown_method(self):
        reset_all_redis_singletons()

    def test_get_redis_deliberation_queue_creates_instance(self):
        q = get_redis_deliberation_queue()
        assert isinstance(q, RedisDeliberationQueue)

    def test_get_redis_deliberation_queue_returns_same(self):
        q1 = get_redis_deliberation_queue()
        q2 = get_redis_deliberation_queue()
        assert q1 is q2

    def test_get_redis_voting_system_creates_instance(self):
        vs = get_redis_voting_system()
        assert isinstance(vs, RedisVotingSystem)

    def test_get_redis_voting_system_returns_same(self):
        vs1 = get_redis_voting_system()
        vs2 = get_redis_voting_system()
        assert vs1 is vs2

    def test_reset_redis_deliberation_queue(self):
        q1 = get_redis_deliberation_queue()
        reset_redis_deliberation_queue()
        q2 = get_redis_deliberation_queue()
        assert q1 is not q2

    def test_reset_redis_voting_system(self):
        vs1 = get_redis_voting_system()
        reset_redis_voting_system()
        vs2 = get_redis_voting_system()
        assert vs1 is not vs2

    def test_reset_all_redis_singletons(self):
        q1 = get_redis_deliberation_queue()
        vs1 = get_redis_voting_system()
        reset_all_redis_singletons()
        q2 = get_redis_deliberation_queue()
        vs2 = get_redis_voting_system()
        assert q1 is not q2
        assert vs1 is not vs2

    def test_redis_available_flag(self):
        # REDIS_AVAILABLE is a bool; exact value depends on env
        assert isinstance(REDIS_AVAILABLE, bool)
