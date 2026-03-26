# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 Deliberation Layer - Redis Deliberation Queue Tests
Constitutional Hash: 608508a9bd224290

Tests for RedisDeliberationQueue: constructor, connect, disconnect, enqueue,
get, update_status, remove, get_pending_items, get_stream_info.

Split from test_deliberation_redis_integration_coverage.py.
asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from enhanced_agent_bus.deliberation_layer import redis_integration as ri
from enhanced_agent_bus.deliberation_layer.redis_integration import (
    RedisDeliberationQueue,
)


def _target_module():
    """Return the actual module dict backing RedisDeliberationQueue.connect.

    Under --import-mode=importlib the ``ri`` alias imported above may be a
    *different* module instance from the one whose globals are closed over by
    ``RedisDeliberationQueue.connect``.  Patching ``ri.REDIS_AVAILABLE`` then
    has no effect on the running code.  This helper resolves the canonical
    module so that ``patch.object`` always targets the right dict.
    """
    return sys.modules[RedisDeliberationQueue.__module__]


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
# RedisDeliberationQueue — constructor
# ===========================================================================


class TestRedisDeliberationQueueInit:
    def test_default_values(self):
        q = RedisDeliberationQueue()
        assert q.redis_url == "redis://localhost:6379"
        assert q.redis_client is None
        assert q.stream_key == "acgs:deliberation:stream"
        assert q.queue_key == "acgs:deliberation:queue"

    def test_custom_url(self):
        q = RedisDeliberationQueue("redis://custom:9999")
        assert q.redis_url == "redis://custom:9999"


# ===========================================================================
# RedisDeliberationQueue — connect
# ===========================================================================


class TestRedisDeliberationQueueConnect:
    async def test_connect_success(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", True):
            with patch.object(mod, "aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                result = await q.connect()
        assert result is True
        assert q.redis_client is mock_client

    async def test_connect_redis_not_available(self):
        q = RedisDeliberationQueue()
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", False):
            result = await q.connect()
        assert result is False
        assert q.redis_client is None

    async def test_connect_connection_error(self):
        q = RedisDeliberationQueue()

        async def _fail():
            raise ConnectionError("refused")

        mock_client = MockRedisClient()
        mock_client.ping = _fail  # type: ignore[method-assign]
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", True):
            with patch.object(mod, "aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                result = await q.connect()
        assert result is False
        assert q.redis_client is None

    async def test_connect_os_error(self):
        q = RedisDeliberationQueue()

        async def _fail():
            raise OSError("network unreachable")

        mock_client = MockRedisClient()
        mock_client.ping = _fail  # type: ignore[method-assign]
        mod = _target_module()
        with patch.object(mod, "REDIS_AVAILABLE", True):
            with patch.object(mod, "aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                result = await q.connect()
        assert result is False
        assert q.redis_client is None


# ===========================================================================
# RedisDeliberationQueue — disconnect
# ===========================================================================


class TestRedisDeliberationQueueDisconnect:
    async def test_disconnect_with_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = MockRedisClient()
        await q.disconnect()
        assert q.redis_client is None

    async def test_disconnect_without_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = None
        await q.disconnect()  # must not raise
        assert q.redis_client is None


# ===========================================================================
# RedisDeliberationQueue — enqueue_deliberation_item
# ===========================================================================


class TestRedisDeliberationQueueEnqueue:
    async def test_enqueue_no_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = None
        result = await q.enqueue_deliberation_item(_FakeMessage(), "item-001")
        assert result is False

    async def test_enqueue_success_without_metadata(self):
        q = RedisDeliberationQueue()
        q.redis_client = MockRedisClient()
        result = await q.enqueue_deliberation_item(_FakeMessage(), "item-002")
        assert result is True

    async def test_enqueue_success_with_metadata(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        result = await q.enqueue_deliberation_item(
            _FakeMessage(), "item-003", metadata={"priority": "high"}
        )
        assert result is True
        assert "item-003" in mock_client._data.get(q.queue_key, {})

    async def test_enqueue_stores_in_stream(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        await q.enqueue_deliberation_item(_FakeMessage(), "item-stream")
        assert q.stream_key in mock_client._streams
        assert len(mock_client._streams[q.stream_key]) == 1

    async def test_enqueue_connection_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        q.redis_client = mock_client
        result = await q.enqueue_deliberation_item(_FakeMessage(), "item-004")
        assert result is False

    async def test_enqueue_os_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        q.redis_client = mock_client
        result = await q.enqueue_deliberation_item(_FakeMessage(), "item-005")
        assert result is False

    async def test_enqueue_type_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = TypeError
        q.redis_client = mock_client
        result = await q.enqueue_deliberation_item(_FakeMessage(), "item-006")
        assert result is False

    async def test_enqueue_stores_message_fields(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        msg = _FakeMessage()
        await q.enqueue_deliberation_item(msg, "item-fields")
        stored_raw = mock_client._data[q.queue_key]["item-fields"]
        stored = json.loads(stored_raw)
        assert stored["message_id"] == "msg-001"
        assert stored["from_agent"] == "sender_agent"
        assert stored["to_agent"] == "receiver_agent"
        assert stored["message_type"] == "COMMAND"


# ===========================================================================
# RedisDeliberationQueue — get_deliberation_item
# ===========================================================================


class TestRedisDeliberationQueueGet:
    async def test_get_no_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = None
        result = await q.get_deliberation_item("anything")
        assert result is None

    async def test_get_existing_item(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        item = {"item_id": "x", "status": "pending"}
        await mock_client.hset(q.queue_key, "x", json.dumps(item))
        result = await q.get_deliberation_item("x")
        assert result is not None
        assert result["item_id"] == "x"

    async def test_get_nonexistent_item(self):
        q = RedisDeliberationQueue()
        q.redis_client = MockRedisClient()
        result = await q.get_deliberation_item("no_such_key")
        assert result is None

    async def test_get_connection_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        q.redis_client = mock_client
        result = await q.get_deliberation_item("x")
        assert result is None

    async def test_get_os_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        q.redis_client = mock_client
        result = await q.get_deliberation_item("x")
        assert result is None

    async def test_get_json_decode_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        mock_client._data[q.queue_key] = {"bad": "not-valid-json{{{"}
        result = await q.get_deliberation_item("bad")
        assert result is None


# ===========================================================================
# RedisDeliberationQueue — update_deliberation_status
# ===========================================================================


class TestRedisDeliberationQueueUpdateStatus:
    async def test_update_no_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = None
        result = await q.update_deliberation_status("item-x", "approved")
        assert result is False

    async def test_update_item_not_found(self):
        q = RedisDeliberationQueue()
        q.redis_client = MockRedisClient()
        result = await q.update_deliberation_status("ghost-item", "approved")
        assert result is False

    async def test_update_success_no_additional_data(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        item = {"item_id": "item-1", "status": "pending"}
        await mock_client.hset(q.queue_key, "item-1", json.dumps(item))
        result = await q.update_deliberation_status("item-1", "approved")
        assert result is True
        updated = json.loads(mock_client._data[q.queue_key]["item-1"])
        assert updated["status"] == "approved"
        assert "updated_at" in updated

    async def test_update_success_with_additional_data(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        item = {"item_id": "item-2", "status": "pending"}
        await mock_client.hset(q.queue_key, "item-2", json.dumps(item))
        result = await q.update_deliberation_status(
            "item-2", "rejected", {"reviewer": "human_1", "reason": "policy violation"}
        )
        assert result is True
        updated = json.loads(mock_client._data[q.queue_key]["item-2"])
        assert updated["status"] == "rejected"
        assert updated["reviewer"] == "human_1"

    async def test_update_connection_error_on_hset(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        item = {"item_id": "item-3", "status": "pending"}
        mock_client._data[q.queue_key] = {"item-3": json.dumps(item)}

        _call_count = 0
        original_hset = mock_client.hset

        async def _failing_hset(key, field, value):
            nonlocal _call_count
            _call_count += 1
            raise ConnectionError("hset failed")

        mock_client.hset = _failing_hset  # type: ignore[method-assign]
        result = await q.update_deliberation_status("item-3", "approved")
        assert result is False


# ===========================================================================
# RedisDeliberationQueue — remove_deliberation_item
# ===========================================================================


class TestRedisDeliberationQueueRemove:
    async def test_remove_no_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = None
        result = await q.remove_deliberation_item("item-x")
        assert result is False

    async def test_remove_existing_item(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        item = {"item_id": "item-x", "status": "pending"}
        await mock_client.hset(q.queue_key, "item-x", json.dumps(item))
        result = await q.remove_deliberation_item("item-x")
        assert result is True
        assert (await q.get_deliberation_item("item-x")) is None

    async def test_remove_connection_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        q.redis_client = mock_client
        result = await q.remove_deliberation_item("item-x")
        assert result is False

    async def test_remove_os_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        q.redis_client = mock_client
        result = await q.remove_deliberation_item("item-x")
        assert result is False


# ===========================================================================
# RedisDeliberationQueue — get_pending_items
# ===========================================================================


class TestRedisDeliberationQueueGetPending:
    async def test_get_pending_no_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = None
        result = await q.get_pending_items()
        assert result == []

    async def test_get_pending_empty_queue(self):
        q = RedisDeliberationQueue()
        q.redis_client = MockRedisClient()
        result = await q.get_pending_items()
        assert result == []

    async def test_get_pending_mixed_statuses(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        items = [
            {"item_id": "a", "status": "pending"},
            {"item_id": "b", "status": "approved"},
            {"item_id": "c", "status": "pending"},
            {"item_id": "d", "status": "rejected"},
        ]
        for it in items:
            await mock_client.hset(q.queue_key, it["item_id"], json.dumps(it))
        result = await q.get_pending_items()
        assert len(result) == 2
        assert all(r["status"] == "pending" for r in result)

    async def test_get_pending_items_without_status_field(self):
        """Items missing 'status' key default to 'pending' via .get('status', 'pending')."""
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        item = {"item_id": "no-status"}
        await mock_client.hset(q.queue_key, "no-status", json.dumps(item))
        result = await q.get_pending_items()
        assert len(result) == 1

    async def test_get_pending_respects_limit(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        for i in range(10):
            item = {"item_id": f"item-{i}", "status": "pending"}
            await mock_client.hset(q.queue_key, f"item-{i}", json.dumps(item))
        result = await q.get_pending_items(limit=3)
        assert len(result) == 3

    async def test_get_pending_limit_default(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        for i in range(5):
            item = {"item_id": f"item-{i}", "status": "pending"}
            await mock_client.hset(q.queue_key, f"item-{i}", json.dumps(item))
        result = await q.get_pending_items()
        assert len(result) == 5

    async def test_get_pending_all_items_iterated_without_hitting_limit(self):
        """All pending items are returned when limit is higher than count.

        This covers the branch where the for loop finishes naturally (194->200)
        without the break at line 199 being triggered.
        """
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        # Store 3 pending items but use limit=100 — loop finishes without break
        for i in range(3):
            item = {"item_id": f"item-nat-{i}", "status": "pending"}
            await mock_client.hset(q.queue_key, f"item-nat-{i}", json.dumps(item))
        result = await q.get_pending_items(limit=100)
        assert len(result) == 3

    async def test_get_pending_connection_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        q.redis_client = mock_client
        result = await q.get_pending_items()
        assert result == []

    async def test_get_pending_os_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        q.redis_client = mock_client
        result = await q.get_pending_items()
        assert result == []

    async def test_get_pending_json_decode_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        mock_client._data[q.queue_key] = {"bad": "not-valid{{{"}
        result = await q.get_pending_items()
        assert result == []


# ===========================================================================
# RedisDeliberationQueue — get_stream_info
# ===========================================================================


class TestRedisDeliberationQueueStreamInfo:
    async def test_get_stream_info_no_client(self):
        q = RedisDeliberationQueue()
        q.redis_client = None
        result = await q.get_stream_info()
        assert "error" in result
        assert result["error"] == "Redis not connected"

    async def test_get_stream_info_success(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        await mock_client.xadd(q.stream_key, {"field": "value"})
        result = await q.get_stream_info()
        assert result["length"] == 1
        assert result["first_entry"] is not None

    async def test_get_stream_info_empty_stream(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        q.redis_client = mock_client
        result = await q.get_stream_info()
        assert result["length"] == 0
        assert result["last_entry"] is None

    async def test_get_stream_info_connection_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = ConnectionError
        q.redis_client = mock_client
        result = await q.get_stream_info()
        assert "error" in result

    async def test_get_stream_info_os_error(self):
        q = RedisDeliberationQueue()
        mock_client = MockRedisClient()
        mock_client._should_raise = OSError
        q.redis_client = mock_client
        result = await q.get_stream_info()
        assert "error" in result
