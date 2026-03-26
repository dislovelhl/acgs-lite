"""Tests for RedisElectionStore.

Constitutional Hash: 608508a9bd224290

Tests Redis-backed election and vote storage with full mock coverage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.deliberation_layer.redis_election_store import (
    RedisElectionStore,
    get_election_store,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    """Patch settings to avoid real config lookups."""
    with patch("enhanced_agent_bus.deliberation_layer.redis_election_store.settings") as mock_s:
        mock_s.redis.url = "redis://localhost:6379/0"
        mock_s.voting.redis_election_prefix = "election:"
        mock_s.voting.default_timeout_seconds = 300
        yield mock_s


@pytest.fixture
def store(mock_settings) -> RedisElectionStore:
    """Create a store with mocked settings."""
    return RedisElectionStore()


@pytest.fixture
def connected_store(store) -> RedisElectionStore:
    """Create a store with a mocked redis client already attached."""
    mock_redis = AsyncMock()
    store.redis_client = mock_redis
    return store


# ---------------------------------------------------------------------------
# Init and connection
# ---------------------------------------------------------------------------


class TestRedisElectionStoreInit:
    def test_init_defaults(self, mock_settings) -> None:
        s = RedisElectionStore()
        assert s.redis_url == "redis://localhost:6379/0"
        assert s.election_prefix == "election:"
        assert s.redis_client is None

    def test_init_custom(self, mock_settings) -> None:
        s = RedisElectionStore(redis_url="redis://custom:1234", election_prefix="vote:")
        assert s.redis_url == "redis://custom:1234"
        assert s.election_prefix == "vote:"


class TestConnect:
    @patch(
        "enhanced_agent_bus.deliberation_layer.redis_election_store.REDIS_AVAILABLE",
        False,
    )
    async def test_connect_redis_unavailable(self, store) -> None:
        result = await store.connect()
        assert result is False

    @patch(
        "enhanced_agent_bus.deliberation_layer.redis_election_store.REDIS_AVAILABLE",
        True,
    )
    @patch("enhanced_agent_bus.deliberation_layer.redis_election_store.aioredis")
    async def test_connect_success(self, mock_aioredis, store) -> None:
        mock_client = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client
        result = await store.connect()
        assert result is True
        assert store.redis_client is mock_client
        mock_client.ping.assert_awaited_once()

    @patch(
        "enhanced_agent_bus.deliberation_layer.redis_election_store.REDIS_AVAILABLE",
        True,
    )
    @patch("enhanced_agent_bus.deliberation_layer.redis_election_store.aioredis")
    async def test_connect_failure(self, mock_aioredis, store) -> None:
        mock_client = AsyncMock()
        mock_client.ping.side_effect = ConnectionError("refused")
        mock_aioredis.from_url.return_value = mock_client
        result = await store.connect()
        assert result is False
        assert store.redis_client is None


class TestDisconnect:
    async def test_disconnect_with_client(self, connected_store) -> None:
        mock_redis = connected_store.redis_client
        await connected_store.disconnect()
        mock_redis.close.assert_awaited_once()
        assert connected_store.redis_client is None

    async def test_disconnect_without_client(self, store) -> None:
        await store.disconnect()  # Should not raise
        assert store.redis_client is None


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


class TestGetElectionKey:
    def test_key_format(self, store) -> None:
        key = store._get_election_key("elec-123")
        assert key == "election:elec-123"


# ---------------------------------------------------------------------------
# save_election
# ---------------------------------------------------------------------------


class TestSaveElection:
    async def test_save_no_client(self, store) -> None:
        result = await store.save_election("e1", {"topic": "test"}, ttl=60)
        assert result is False

    async def test_save_success(self, connected_store) -> None:
        data = {"topic": "governance", "status": "OPEN"}
        result = await connected_store.save_election("e1", data, ttl=120)
        assert result is True
        connected_store.redis_client.setex.assert_awaited_once()
        call_args = connected_store.redis_client.setex.call_args
        assert call_args[0][0] == "election:e1"
        assert call_args[0][1] == 120
        parsed = json.loads(call_args[0][2])
        assert parsed["topic"] == "governance"

    async def test_save_with_datetime(self, connected_store) -> None:
        data = {"created_at": datetime(2025, 1, 1, tzinfo=timezone.utc)}
        result = await connected_store.save_election("e1", data, ttl=60)
        assert result is True
        call_args = connected_store.redis_client.setex.call_args
        parsed = json.loads(call_args[0][2])
        assert "2025-01-01" in parsed["created_at"]

    async def test_save_connection_error(self, connected_store) -> None:
        connected_store.redis_client.setex.side_effect = ConnectionError("lost")
        result = await connected_store.save_election("e1", {}, ttl=60)
        assert result is False


# ---------------------------------------------------------------------------
# get_election
# ---------------------------------------------------------------------------


class TestGetElection:
    async def test_get_no_client(self, store) -> None:
        result = await store.get_election("e1")
        assert result is None

    async def test_get_not_found(self, connected_store) -> None:
        connected_store.redis_client.get.return_value = None
        result = await connected_store.get_election("e1")
        assert result is None

    async def test_get_success(self, connected_store) -> None:
        data = {"topic": "test", "status": "OPEN", "votes": {}}
        connected_store.redis_client.get.return_value = json.dumps(data)
        result = await connected_store.get_election("e1")
        assert result is not None
        assert result["topic"] == "test"

    async def test_get_deserializes_datetimes(self, connected_store) -> None:
        data = {"created_at": "2025-01-01T00:00:00+00:00", "status": "OPEN"}
        connected_store.redis_client.get.return_value = json.dumps(data)
        result = await connected_store.get_election("e1")
        assert isinstance(result["created_at"], datetime)

    async def test_get_connection_error(self, connected_store) -> None:
        connected_store.redis_client.get.side_effect = ConnectionError("lost")
        result = await connected_store.get_election("e1")
        assert result is None

    async def test_get_invalid_json(self, connected_store) -> None:
        connected_store.redis_client.get.return_value = "not-json"
        result = await connected_store.get_election("e1")
        assert result is None


# ---------------------------------------------------------------------------
# add_vote
# ---------------------------------------------------------------------------


class TestAddVote:
    async def test_add_vote_no_client(self, store) -> None:
        result = await store.add_vote("e1", {"agent_id": "a1", "choice": "yes"})
        assert result is False

    async def test_add_vote_election_not_found(self, connected_store) -> None:
        connected_store.redis_client.get.return_value = None
        result = await connected_store.add_vote("e1", {"agent_id": "a1"})
        assert result is False

    async def test_add_vote_missing_agent_id(self, connected_store) -> None:
        data = {"topic": "test", "votes": {}}
        connected_store.redis_client.get.return_value = json.dumps(data)
        result = await connected_store.add_vote("e1", {"choice": "yes"})
        assert result is False

    async def test_add_vote_success(self, connected_store, mock_settings) -> None:
        data = {"topic": "test", "votes": {}}
        connected_store.redis_client.get.return_value = json.dumps(data)
        connected_store.redis_client.ttl.return_value = 200

        result = await connected_store.add_vote("e1", {"agent_id": "agent-1", "choice": "yes"})
        assert result is True
        connected_store.redis_client.setex.assert_awaited_once()

    async def test_add_vote_expired_ttl_uses_default(self, connected_store, mock_settings) -> None:
        data = {"topic": "test", "votes": {}}
        connected_store.redis_client.get.return_value = json.dumps(data)
        connected_store.redis_client.ttl.return_value = -1

        result = await connected_store.add_vote("e1", {"agent_id": "agent-1", "choice": "yes"})
        assert result is True
        call_args = connected_store.redis_client.setex.call_args
        assert call_args[0][1] == 300  # default_timeout_seconds

    async def test_add_vote_initializes_votes_dict(self, connected_store, mock_settings) -> None:
        data = {"topic": "test"}  # No "votes" key
        connected_store.redis_client.get.return_value = json.dumps(data)
        connected_store.redis_client.ttl.return_value = 100

        result = await connected_store.add_vote("e1", {"agent_id": "agent-1", "choice": "yes"})
        assert result is True

    async def test_add_vote_connection_error(self, connected_store) -> None:
        data = {"topic": "test", "votes": {}}
        connected_store.redis_client.get.return_value = json.dumps(data)
        connected_store.redis_client.ttl.side_effect = ConnectionError("lost")
        result = await connected_store.add_vote("e1", {"agent_id": "a1"})
        assert result is False


# ---------------------------------------------------------------------------
# get_votes
# ---------------------------------------------------------------------------


class TestGetVotes:
    async def test_get_votes_no_election(self, connected_store) -> None:
        connected_store.redis_client.get.return_value = None
        result = await connected_store.get_votes("e1")
        assert result == []

    async def test_get_votes_success(self, connected_store) -> None:
        data = {
            "votes": {
                "agent-1": {"agent_id": "agent-1", "choice": "yes"},
                "agent-2": {"agent_id": "agent-2", "choice": "no"},
            }
        }
        connected_store.redis_client.get.return_value = json.dumps(data)
        result = await connected_store.get_votes("e1")
        assert len(result) == 2

    async def test_get_votes_empty(self, connected_store) -> None:
        data = {"votes": {}}
        connected_store.redis_client.get.return_value = json.dumps(data)
        result = await connected_store.get_votes("e1")
        assert result == []


# ---------------------------------------------------------------------------
# delete_election
# ---------------------------------------------------------------------------


class TestDeleteElection:
    async def test_delete_no_client(self, store) -> None:
        result = await store.delete_election("e1")
        assert result is False

    async def test_delete_success(self, connected_store) -> None:
        connected_store.redis_client.delete.return_value = 1
        result = await connected_store.delete_election("e1")
        assert result is True

    async def test_delete_not_found(self, connected_store) -> None:
        connected_store.redis_client.delete.return_value = 0
        result = await connected_store.delete_election("e1")
        assert result is False

    async def test_delete_connection_error(self, connected_store) -> None:
        connected_store.redis_client.delete.side_effect = ConnectionError("lost")
        result = await connected_store.delete_election("e1")
        assert result is False


# ---------------------------------------------------------------------------
# update_election_status
# ---------------------------------------------------------------------------


class TestUpdateElectionStatus:
    async def test_update_no_client(self, store) -> None:
        result = await store.update_election_status("e1", "CLOSED")
        assert result is False

    async def test_update_not_found(self, connected_store) -> None:
        connected_store.redis_client.get.return_value = None
        result = await connected_store.update_election_status("e1", "CLOSED")
        assert result is False

    async def test_update_success(self, connected_store, mock_settings) -> None:
        data = {"topic": "test", "status": "OPEN"}
        connected_store.redis_client.get.return_value = json.dumps(data)
        connected_store.redis_client.ttl.return_value = 100

        result = await connected_store.update_election_status("e1", "CLOSED")
        assert result is True
        call_args = connected_store.redis_client.setex.call_args
        parsed = json.loads(call_args[0][2])
        assert parsed["status"] == "CLOSED"

    async def test_update_expired_ttl_uses_default(self, connected_store, mock_settings) -> None:
        data = {"status": "OPEN"}
        connected_store.redis_client.get.return_value = json.dumps(data)
        connected_store.redis_client.ttl.return_value = 0

        result = await connected_store.update_election_status("e1", "EXPIRED")
        assert result is True
        call_args = connected_store.redis_client.setex.call_args
        assert call_args[0][1] == 300

    async def test_update_connection_error(self, connected_store) -> None:
        data = {"status": "OPEN"}
        connected_store.redis_client.get.return_value = json.dumps(data)
        connected_store.redis_client.ttl.side_effect = ConnectionError("lost")
        result = await connected_store.update_election_status("e1", "CLOSED")
        assert result is False


# ---------------------------------------------------------------------------
# scan_elections
# ---------------------------------------------------------------------------


class TestScanElections:
    async def test_scan_no_client(self, store) -> None:
        result = await store.scan_elections()
        assert result == []

    async def test_scan_success(self, connected_store) -> None:
        async def mock_scan_iter(match=None):
            for key in ["election:e1", "election:e2", "election:e3"]:
                yield key

        connected_store.redis_client.scan_iter = mock_scan_iter
        result = await connected_store.scan_elections()
        assert result == ["e1", "e2", "e3"]

    async def test_scan_custom_pattern(self, connected_store) -> None:
        async def mock_scan_iter(match=None):
            assert match == "custom:*"
            for key in ["election:x1"]:
                yield key

        connected_store.redis_client.scan_iter = mock_scan_iter
        result = await connected_store.scan_elections(pattern="custom:*")
        assert len(result) == 1

    async def test_scan_connection_error(self, connected_store) -> None:
        async def mock_scan_iter(match=None):
            raise ConnectionError("lost")
            yield  # make it a generator  # noqa: unreachable

        connected_store.redis_client.scan_iter = mock_scan_iter
        result = await connected_store.scan_elections()
        assert result == []


# ---------------------------------------------------------------------------
# Serialization / deserialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_serialize_datetime(self, store) -> None:
        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        data = {"created_at": dt, "title": "test"}
        result = store._serialize_election_data(data)
        assert result["created_at"] == dt.isoformat()
        assert result["title"] == "test"

    def test_serialize_nested_dict(self, store) -> None:
        data = {"outer": {"inner_dt": datetime(2025, 1, 1, tzinfo=timezone.utc)}}
        result = store._serialize_election_data(data)
        assert isinstance(result["outer"]["inner_dt"], str)

    def test_serialize_list_with_dicts(self, store) -> None:
        data = {
            "items": [
                {"dt": datetime(2025, 1, 1, tzinfo=timezone.utc)},
                "plain_string",
            ]
        }
        result = store._serialize_election_data(data)
        assert isinstance(result["items"][0]["dt"], str)
        assert result["items"][1] == "plain_string"

    def test_deserialize_datetime_fields(self, store) -> None:
        data = {"created_at": "2025-01-01T00:00:00+00:00", "title": "test"}
        result = store._deserialize_election_data(data)
        assert isinstance(result["created_at"], datetime)
        assert result["title"] == "test"

    def test_deserialize_invalid_datetime(self, store) -> None:
        data = {"created_at": "not-a-datetime"}
        result = store._deserialize_election_data(data)
        assert result["created_at"] == "not-a-datetime"  # unchanged

    def test_deserialize_nested(self, store) -> None:
        data = {"nested": {"expires_at": "2025-06-01T00:00:00+00:00"}}
        result = store._deserialize_election_data(data)
        assert isinstance(result["nested"]["expires_at"], datetime)

    def test_deserialize_list_with_dicts(self, store) -> None:
        data = {
            "items": [
                {"timestamp": "2025-01-01T00:00:00+00:00"},
                "plain",
            ]
        }
        result = store._deserialize_election_data(data)
        assert isinstance(result["items"][0]["timestamp"], datetime)
        assert result["items"][1] == "plain"

    def test_serialize_does_not_mutate_original(self, store) -> None:
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        original = {"created_at": dt}
        store._serialize_election_data(original)
        assert original["created_at"] is dt  # Original unchanged


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    @patch(
        "enhanced_agent_bus.deliberation_layer.redis_election_store._election_store",
        None,
    )
    @patch(
        "enhanced_agent_bus.deliberation_layer.redis_election_store.REDIS_AVAILABLE",
        True,
    )
    @patch("enhanced_agent_bus.deliberation_layer.redis_election_store.aioredis")
    async def test_get_election_store_creates_singleton(self, mock_aioredis, mock_settings) -> None:
        mock_client = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client
        s = await get_election_store()
        assert s is not None
        assert isinstance(s, RedisElectionStore)
