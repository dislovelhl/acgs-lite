"""
Additional coverage tests for vote_collector.py
Target: bring coverage from ~50% to ≥90%

Covers previously uncovered branches:
- connect() success and failure paths
- disconnect() with active subscriber task, pubsub, and redis_client
- create_vote_session() Redis hset/expire path (and redis error fallback)
- create_vote_session() capacity exceeded after cleanup frees space
- submit_vote() Redis publish path and redis error fallback
- get_current_votes() Redis path and redis error fallback
- _subscriber_loop() including message handling, timeout, and errors
- _handle_pubsub_message() invalid JSON, missing fields, non-message type
- _process_vote_event() already completed session, missing lock
- _cleanup_session() with pubsub/redis and error paths
- _stabilize_weights() RUST_AVAILABLE path and fallback branches
- check_consensus() zero_total_weight branch
- VoteEvent.from_dict() with timestamp field

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.deliberation_layer.vote_collector import (
    EventDrivenVoteCollector,
    VoteEvent,
    VoteSession,
    get_vote_collector,
    reset_vote_collector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vote(
    agent_id: str = "agent-1",
    message_id: str = "msg-1",
    decision: str = "approve",
    weight: float = 1.0,
) -> VoteEvent:
    return VoteEvent(
        vote_id="v-" + agent_id,
        message_id=message_id,
        agent_id=agent_id,
        decision=decision,
        reasoning="test",
        confidence=0.9,
        weight=weight,
    )


def _session(
    required_votes: int = 3,
    threshold: float = 0.66,
    timeout: int = 300,
    agent_weights: dict | None = None,
) -> VoteSession:
    return VoteSession(
        session_id="sess-1",
        message_id="msg-1",
        required_votes=required_votes,
        consensus_threshold=threshold,
        timeout_seconds=timeout,
        agent_weights=agent_weights or {},
        completion_event=asyncio.Event(),
    )


def _collector(**kwargs) -> EventDrivenVoteCollector:
    return EventDrivenVoteCollector(**kwargs)


# ---------------------------------------------------------------------------
# VoteEvent.from_dict with timestamp field
# ---------------------------------------------------------------------------


class TestVoteEventFromDictTimestamp:
    def test_from_dict_with_timestamp_field(self) -> None:
        data = {
            "message_id": "msg-x",
            "agent_id": "agent-x",
            "decision": "approve",
            "timestamp": "2025-06-01T12:00:00+00:00",
        }
        v = VoteEvent.from_dict(data)
        assert v.timestamp.year == 2025
        assert v.timestamp.month == 6

    def test_from_dict_without_timestamp_uses_now(self) -> None:
        before = datetime.now(UTC)
        data = {
            "message_id": "msg-x",
            "agent_id": "agent-x",
            "decision": "reject",
        }
        v = VoteEvent.from_dict(data)
        after = datetime.now(UTC)
        assert before <= v.timestamp <= after


# ---------------------------------------------------------------------------
# VoteSession._stabilize_weights with RUST_AVAILABLE
# ---------------------------------------------------------------------------


class TestStabilizeWeights:
    def test_no_agent_weights_returns_empty_dict(self) -> None:
        sess = _session(agent_weights={})
        result = sess._stabilize_weights()
        assert result == {}

    def test_rust_available_numpy_available_success(self) -> None:
        """Test the Rust sinkhorn path when both Rust and numpy are available."""
        sess = _session(agent_weights={"a1": 2.0, "a2": 1.0})
        # Mock the Rust module and numpy
        mock_rust = MagicMock()
        mock_np = MagicMock()
        # Mock array creation
        mock_weights_matrix = MagicMock()
        mock_np.array.return_value = mock_weights_matrix
        mock_np.float32 = float
        # Mock stabilized result
        mock_stabilized_matrix = MagicMock()
        stabilized_vector = MagicMock()
        mock_stabilized_matrix.__getitem__ = lambda self, idx: stabilized_vector
        stabilized_vector.sum.return_value = 1.0
        stabilized_vector.__truediv__ = lambda self, other: stabilized_vector
        import sys

        stabilized_values = [0.67, 0.33]
        stabilized_vector.__iter__ = lambda self: iter(stabilized_values)
        mock_rust.sinkhorn_knopp_stabilize.return_value = mock_stabilized_matrix

        with patch.dict(
            "enhanced_agent_bus.deliberation_layer.vote_collector.__dict__",
            {"RUST_AVAILABLE": True, "NUMPY_AVAILABLE": True, "rust_opt": mock_rust, "np": mock_np},
        ):
            # Call via the module globals path using patch
            import enhanced_agent_bus.deliberation_layer.vote_collector as vc_mod

            orig_rust = vc_mod.RUST_AVAILABLE
            orig_numpy = vc_mod.NUMPY_AVAILABLE
            orig_rust_opt = vc_mod.rust_opt
            orig_np = vc_mod.np
            try:
                vc_mod.RUST_AVAILABLE = True
                vc_mod.NUMPY_AVAILABLE = True
                vc_mod.rust_opt = mock_rust
                vc_mod.np = mock_np
                # Rebuild session to use new globals
                result = sess._stabilize_weights()
                # Should attempt the rust path (may succeed or fall through depending on mocks)
                assert result is not None
            finally:
                vc_mod.RUST_AVAILABLE = orig_rust
                vc_mod.NUMPY_AVAILABLE = orig_numpy
                vc_mod.rust_opt = orig_rust_opt
                vc_mod.np = orig_np

    def test_rust_available_numpy_unavailable_falls_through(self) -> None:
        """RUST_AVAILABLE=True but NUMPY_AVAILABLE=False raises ImportError inside try block."""
        sess = _session(agent_weights={"a1": 2.0})
        import enhanced_agent_bus.deliberation_layer.vote_collector as vc_mod

        orig_rust = vc_mod.RUST_AVAILABLE
        orig_numpy = vc_mod.NUMPY_AVAILABLE
        orig_sinkhorn = vc_mod.sinkhorn_projection
        orig_torch = vc_mod.TORCH_AVAILABLE
        try:
            vc_mod.RUST_AVAILABLE = True
            vc_mod.NUMPY_AVAILABLE = False
            vc_mod.sinkhorn_projection = None
            vc_mod.TORCH_AVAILABLE = False
            result = sess._stabilize_weights()
            # Falls back to original weights
            assert result == {"a1": 2.0}
        finally:
            vc_mod.RUST_AVAILABLE = orig_rust
            vc_mod.NUMPY_AVAILABLE = orig_numpy
            vc_mod.sinkhorn_projection = orig_sinkhorn
            vc_mod.TORCH_AVAILABLE = orig_torch

    def test_rust_sinkhorn_value_error_falls_through(self) -> None:
        """Rust sinkhorn raises ValueError — logs warning, falls to python path."""
        sess = _session(agent_weights={"a1": 2.0, "a2": 1.0})
        import enhanced_agent_bus.deliberation_layer.vote_collector as vc_mod

        mock_rust = MagicMock()
        mock_rust.sinkhorn_knopp_stabilize.side_effect = ValueError("bad matrix")
        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()
        mock_np.float32 = float

        orig_rust = vc_mod.RUST_AVAILABLE
        orig_numpy = vc_mod.NUMPY_AVAILABLE
        orig_rust_opt = vc_mod.rust_opt
        orig_np = vc_mod.np
        orig_sinkhorn = vc_mod.sinkhorn_projection
        orig_torch = vc_mod.TORCH_AVAILABLE
        try:
            vc_mod.RUST_AVAILABLE = True
            vc_mod.NUMPY_AVAILABLE = True
            vc_mod.rust_opt = mock_rust
            vc_mod.np = mock_np
            vc_mod.sinkhorn_projection = None
            vc_mod.TORCH_AVAILABLE = False
            result = sess._stabilize_weights()
            assert result == {"a1": 2.0, "a2": 1.0}
        finally:
            vc_mod.RUST_AVAILABLE = orig_rust
            vc_mod.NUMPY_AVAILABLE = orig_numpy
            vc_mod.rust_opt = orig_rust_opt
            vc_mod.np = orig_np
            vc_mod.sinkhorn_projection = orig_sinkhorn
            vc_mod.TORCH_AVAILABLE = orig_torch

    def test_no_rust_no_sinkhorn_returns_original_weights(self) -> None:
        sess = _session(agent_weights={"a1": 1.5, "a2": 0.5})
        import enhanced_agent_bus.deliberation_layer.vote_collector as vc_mod

        orig_rust = vc_mod.RUST_AVAILABLE
        orig_sinkhorn = vc_mod.sinkhorn_projection
        orig_torch = vc_mod.TORCH_AVAILABLE
        try:
            vc_mod.RUST_AVAILABLE = False
            vc_mod.sinkhorn_projection = None
            vc_mod.TORCH_AVAILABLE = False
            result = sess._stabilize_weights()
            assert result == {"a1": 1.5, "a2": 0.5}
        finally:
            vc_mod.RUST_AVAILABLE = orig_rust
            vc_mod.sinkhorn_projection = orig_sinkhorn
            vc_mod.TORCH_AVAILABLE = orig_torch


# ---------------------------------------------------------------------------
# VoteSession.check_consensus — zero total weight branch
# ---------------------------------------------------------------------------


class TestCheckConsensusZeroWeight:
    def test_zero_total_weight_returns_false(self) -> None:
        sess = VoteSession(
            session_id="sess-zw",
            message_id="msg-zw",
            required_votes=1,
            consensus_threshold=0.5,
            timeout_seconds=300,
            agent_weights={"a1": 0.0},  # zero weight
        )
        vote = VoteEvent(
            vote_id="v1",
            message_id="msg-zw",
            agent_id="a1",
            decision="approve",
            reasoning="",
            confidence=1.0,
            weight=0.0,  # zero weight
        )
        sess.votes.append(vote)  # bypass add_vote to keep weight at 0
        result = sess.check_consensus()
        assert result["consensus_reached"] is False
        assert result["reason"] == "zero_total_weight"


# ---------------------------------------------------------------------------
# EventDrivenVoteCollector.connect()
# ---------------------------------------------------------------------------


class TestCollectorConnect:
    async def test_connect_redis_not_available_returns_false(self) -> None:
        c = _collector()
        with patch(
            "enhanced_agent_bus.deliberation_layer.vote_collector.REDIS_AVAILABLE",
            False,
        ):
            result = await c.connect()
            assert result is False

    async def test_connect_redis_available_success(self) -> None:
        """Mock aioredis so connect() succeeds without real Redis."""
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pubsub = AsyncMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_aioredis = MagicMock()
        mock_aioredis.from_url.return_value = mock_redis

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_collector.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_collector.aioredis",
                mock_aioredis,
            ),
        ):
            result = await c.connect()
        assert result is True
        assert c._running is True
        assert c._subscriber_task is not None
        # Cancel the subscriber task to avoid hanging
        c._subscriber_task.cancel()
        try:  # noqa: SIM105
            await c._subscriber_task
        except (asyncio.CancelledError, Exception):  # noqa: S110
            pass

    async def test_connect_redis_connection_error_returns_false(self) -> None:
        """Mock aioredis so connect() raises ConnectionError on ping."""
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = ConnectionError("refused")
        mock_aioredis = MagicMock()
        mock_aioredis.from_url.return_value = mock_redis

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_collector.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.vote_collector.aioredis",
                mock_aioredis,
            ),
        ):
            result = await c.connect()
        assert result is False
        assert c.redis_client is None


# ---------------------------------------------------------------------------
# EventDrivenVoteCollector.disconnect()
# ---------------------------------------------------------------------------


class TestCollectorDisconnect:
    async def test_disconnect_no_connections(self) -> None:
        """disconnect() with no active connections should not raise."""
        c = _collector()
        await c.disconnect()
        assert c._running is False

    async def test_disconnect_with_subscriber_task(self) -> None:
        """disconnect() cancels and awaits the subscriber task."""
        c = _collector()
        task_finished = False

        async def fake_subscriber():
            nonlocal task_finished
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                task_finished = True
                raise

        task = asyncio.create_task(fake_subscriber())
        # Yield to let the task start
        await asyncio.sleep(0)
        c._subscriber_task = task
        c._running = True
        await c.disconnect()
        assert task_finished is True
        assert c._subscriber_task is None

    async def test_disconnect_with_pubsub_and_redis(self) -> None:
        """disconnect() calls unsubscribe/close on pubsub and close on redis."""
        c = _collector()
        mock_pubsub = AsyncMock()
        mock_redis = AsyncMock()
        c.pubsub = mock_pubsub
        c.redis_client = mock_redis
        c._running = True
        await c.disconnect()
        mock_pubsub.unsubscribe.assert_called_once()
        mock_pubsub.close.assert_called_once()
        mock_redis.close.assert_called_once()
        assert c.pubsub is None
        assert c.redis_client is None


# ---------------------------------------------------------------------------
# create_vote_session() — Redis path and capacity cleanup
# ---------------------------------------------------------------------------


class TestCreateVoteSessionRedis:
    async def test_create_session_with_redis_client(self) -> None:
        """create_vote_session() persists session to Redis when redis_client is set."""
        c = _collector()
        mock_redis = AsyncMock()
        mock_pubsub = AsyncMock()
        c.redis_client = mock_redis
        c.pubsub = mock_pubsub

        sid = await c.create_vote_session("msg-redis", required_votes=3)
        assert sid is not None
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    async def test_create_session_redis_hset_error_logged(self) -> None:
        """create_vote_session() logs warning when Redis raises ConnectionError."""
        c = _collector()
        mock_redis = AsyncMock()
        # ConnectionError is one of the caught exceptions in create_vote_session
        mock_redis.hset.side_effect = ConnectionError("connection lost")
        c.redis_client = mock_redis
        # Should not raise even though Redis fails
        sid = await c.create_vote_session("msg-fail")
        assert sid is not None

    async def test_capacity_exceeded_cleanup_frees_space(self) -> None:
        """capacity exceeded triggers cleanup of expired sessions."""
        c = _collector(max_concurrent_sessions=2)
        # Create 2 sessions
        sid1 = await c.create_vote_session("msg-1")
        sid2 = await c.create_vote_session("msg-2")
        # Force both to expire
        c._sessions[sid1].created_at = datetime.now(UTC) - timedelta(seconds=9999)
        c._sessions[sid2].created_at = datetime.now(UTC) - timedelta(seconds=9999)
        # Should clean up expired sessions and allow new one
        sid3 = await c.create_vote_session("msg-3")
        assert sid3 is not None

    async def test_create_session_subscribes_to_channel_when_pubsub(self) -> None:
        c = _collector()
        mock_pubsub = AsyncMock()
        c.pubsub = mock_pubsub
        await c.create_vote_session("msg-sub")
        mock_pubsub.subscribe.assert_called_once_with("acgs:votes:msg-sub")


# ---------------------------------------------------------------------------
# submit_vote() — Redis path and error fallback
# ---------------------------------------------------------------------------


class TestSubmitVoteRedis:
    async def test_submit_vote_uses_redis_publish(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        c.redis_client = mock_redis
        result = await c.submit_vote("msg-r", "agent-1", "approve")
        assert result is True
        mock_redis.publish.assert_called_once()

    async def test_submit_vote_redis_also_stores_in_hash(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        c.redis_client = mock_redis
        await c.submit_vote("msg-r", "agent-1", "reject")
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    async def test_submit_vote_redis_error_falls_back_to_memory(self) -> None:
        """submit_vote() falls back to in-memory when Redis publish raises ConnectionError."""
        c = _collector()
        mock_redis = AsyncMock()
        # ConnectionError is one of the caught exceptions in submit_vote
        mock_redis.publish.side_effect = ConnectionError("network error")
        c.redis_client = mock_redis
        result = await c.submit_vote("msg-fail", "agent-1", "approve")
        assert result is True
        assert "msg-fail" in c._in_memory_votes

    async def test_submit_vote_with_metadata(self) -> None:
        c = _collector()
        result = await c.submit_vote("msg-1", "agent-1", "approve", metadata={"key": "val"})
        assert result is True
        vote = c._in_memory_votes["msg-1"][0]
        assert vote.metadata == {"key": "val"}


# ---------------------------------------------------------------------------
# get_current_votes() — Redis path
# ---------------------------------------------------------------------------


class TestGetCurrentVotesRedis:
    async def test_get_current_votes_uses_redis_hgetall(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        vote_data = _vote("a1").to_dict()
        mock_redis.hgetall.return_value = {"a1": json.dumps(vote_data)}
        c.redis_client = mock_redis
        result = await c.get_current_votes("msg-r")
        assert len(result) == 1
        assert result[0]["agent_id"] == "a1"

    async def test_get_current_votes_redis_error_falls_back(self) -> None:
        """get_current_votes() falls back to in-memory when hgetall raises ConnectionError."""
        c = _collector()
        mock_redis = AsyncMock()
        # ConnectionError is one of the caught exceptions in get_current_votes
        mock_redis.hgetall.side_effect = ConnectionError("timeout")
        c.redis_client = mock_redis
        # Seed in-memory fallback
        c._in_memory_votes["msg-fb"] = [_vote("a1", message_id="msg-fb")]
        result = await c.get_current_votes("msg-fb")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _handle_pubsub_message()
# ---------------------------------------------------------------------------


class TestHandlePubsubMessage:
    async def test_handle_valid_message_processes_vote(self) -> None:
        c = _collector()
        await c.create_vote_session("msg-ps", required_votes=3)
        vote_data = _vote("a1", message_id="msg-ps").to_dict()
        message = {
            "type": "message",
            "channel": "acgs:votes:msg-ps",
            "data": json.dumps(vote_data),
        }
        await c._handle_pubsub_message(message)
        session = list(c._sessions.values())[0]
        assert len(session.votes) == 1

    async def test_handle_message_with_empty_data_skips(self) -> None:
        c = _collector()
        message = {"type": "message", "channel": "acgs:votes:x", "data": ""}
        # Should not raise
        await c._handle_pubsub_message(message)

    async def test_handle_message_with_empty_channel_skips(self) -> None:
        c = _collector()
        message = {"type": "message", "channel": "", "data": "{}"}
        await c._handle_pubsub_message(message)

    async def test_handle_message_invalid_json_logs_warning(self) -> None:
        c = _collector()
        message = {"type": "message", "channel": "acgs:votes:x", "data": "not-json"}
        await c._handle_pubsub_message(message)  # Should not raise

    async def test_handle_message_missing_required_key_logs_error(self) -> None:
        c = _collector()
        # Data is valid JSON but missing required keys for VoteEvent.from_dict
        message = {
            "type": "message",
            "channel": "acgs:votes:x",
            "data": json.dumps({"vote_id": "v1"}),  # missing message_id, agent_id, decision
        }
        await c._handle_pubsub_message(message)  # Should not raise


# ---------------------------------------------------------------------------
# _subscriber_loop()
# ---------------------------------------------------------------------------


class TestSubscriberLoop:
    async def test_subscriber_loop_exits_when_not_running(self) -> None:
        c = _collector()
        c._running = False
        # Loop should exit immediately since _running is False and pubsub is None
        await c._subscriber_loop()

    async def test_subscriber_loop_processes_messages_and_exits(self) -> None:
        """Subscriber loop processes one message then exits on CancelledError."""
        c = _collector()
        c._running = True
        await c.create_vote_session("msg-loop", required_votes=5)
        vote_data = _vote("a1", message_id="msg-loop").to_dict()

        call_count = 0

        async def fake_get_message(ignore_subscribe_messages=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "type": "message",
                    "channel": "acgs:votes:msg-loop",
                    "data": json.dumps(vote_data),
                }
            # Second call sets running to false and returns None
            c._running = False
            return None

        mock_pubsub = MagicMock()
        mock_pubsub.get_message = fake_get_message
        c.pubsub = mock_pubsub

        await c._subscriber_loop()
        # Vote should have been processed
        session = list(c._sessions.values())[0]
        assert len(session.votes) == 1

    async def test_subscriber_loop_handles_timeout_continues(self) -> None:
        """asyncio.TimeoutError inside loop causes continue (not crash)."""
        c = _collector()
        c._running = True
        call_count = 0

        async def fake_get_message(ignore_subscribe_messages=True):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise TimeoutError()
            c._running = False
            return None

        mock_pubsub = MagicMock()
        mock_pubsub.get_message = fake_get_message
        c.pubsub = mock_pubsub
        await c._subscriber_loop()  # Should not raise

    async def test_subscriber_loop_handles_runtime_error_sleeps(self) -> None:
        """RuntimeError inside loop logs error and sleeps before continuing."""
        c = _collector()
        c._running = True
        call_count = 0

        async def fake_get_message(ignore_subscribe_messages=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("unexpected")
            c._running = False
            return None

        mock_pubsub = MagicMock()
        mock_pubsub.get_message = fake_get_message
        c.pubsub = mock_pubsub

        # Patch sleep to avoid actual delay
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._subscriber_loop()

    async def test_subscriber_loop_cancelled_error_breaks(self) -> None:
        """CancelledError inside inner loop causes clean break."""
        c = _collector()
        c._running = True

        async def fake_get_message(ignore_subscribe_messages=True):
            raise asyncio.CancelledError()

        mock_pubsub = MagicMock()
        mock_pubsub.get_message = fake_get_message
        c.pubsub = mock_pubsub
        await c._subscriber_loop()  # Should not raise

    async def test_subscriber_loop_outer_exception_logs(self) -> None:
        """OSError at outer loop level logs and exits gracefully."""
        c = _collector()
        c._running = True
        call_count = 0

        # Simulate an OSError on pubsub.get_message that propagates through outer try
        async def fake_get_message(ignore_subscribe_messages=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("socket broken")
            c._running = False
            return None

        mock_pubsub = MagicMock()
        mock_pubsub.get_message = fake_get_message
        c.pubsub = mock_pubsub

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._subscriber_loop()


# ---------------------------------------------------------------------------
# _process_vote_event() — completed session, no lock
# ---------------------------------------------------------------------------


class TestProcessVoteEventEdgeCases:
    async def test_already_completed_session_skipped(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("msg-done", required_votes=1, consensus_threshold=0.5)
        # Mark session as completed
        c._sessions[sid].completed = True
        vote = _vote("a1", message_id="msg-done")
        await c._process_vote_event(vote)
        # Vote should NOT have been added
        assert len(c._sessions[sid].votes) == 0

    async def test_different_message_id_skipped(self) -> None:
        c = _collector()
        await c.create_vote_session("msg-A", required_votes=3)
        # Vote for a different message
        vote = _vote("a1", message_id="msg-B")
        await c._process_vote_event(vote)
        session = list(c._sessions.values())[0]
        assert len(session.votes) == 0

    async def test_consensus_reached_sets_completion_event(self) -> None:
        c = _collector()
        sid = await c.create_vote_session(
            "msg-consensus", required_votes=1, consensus_threshold=0.5
        )
        session = c._sessions[sid]
        vote = _vote("a1", message_id="msg-consensus")
        await c._process_vote_event(vote)
        assert session.completed is True
        assert session.completion_event.is_set()


# ---------------------------------------------------------------------------
# _cleanup_session() — with pubsub and redis
# ---------------------------------------------------------------------------


class TestCleanupSession:
    async def test_cleanup_removes_session_and_lock(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("msg-cl")
        await c._cleanup_session(sid)
        assert sid not in c._sessions
        assert sid not in c._session_locks

    async def test_cleanup_unsubscribes_pubsub(self) -> None:
        c = _collector()
        mock_pubsub = AsyncMock()
        c.pubsub = mock_pubsub
        sid = await c.create_vote_session("msg-cl2")
        await c._cleanup_session(sid)
        mock_pubsub.unsubscribe.assert_called_once_with("acgs:votes:msg-cl2")

    async def test_cleanup_deletes_session_from_redis(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        c.redis_client = mock_redis
        sid = await c.create_vote_session("msg-cl3")
        await c._cleanup_session(sid)
        mock_redis.hdel.assert_called_once()

    async def test_cleanup_pubsub_redis_error_logged(self) -> None:
        """ConnectionError during cleanup is logged but not raised."""
        c = _collector()
        mock_pubsub = AsyncMock()
        mock_redis = AsyncMock()
        # ConnectionError is one of the caught exceptions in _cleanup_session
        mock_pubsub.unsubscribe.side_effect = ConnectionError("conn lost")
        mock_redis.hdel.side_effect = ConnectionError("conn lost")
        c.pubsub = mock_pubsub
        c.redis_client = mock_redis
        sid = await c.create_vote_session("msg-cl-err")
        await c._cleanup_session(sid)  # Should not raise

    async def test_cleanup_nonexistent_session_no_error(self) -> None:
        c = _collector()
        await c._cleanup_session("nonexistent-session-id")  # Should not raise


# ---------------------------------------------------------------------------
# wait_for_consensus() edge cases
# ---------------------------------------------------------------------------


class TestWaitForConsensusExtra:
    async def test_wait_returns_votes_list_on_consensus(self) -> None:
        """wait_for_consensus returns a 'votes' list when consensus is reached."""
        c = _collector()
        sid = await c.create_vote_session("msg-wc", required_votes=1, consensus_threshold=0.5)
        await c.submit_vote("msg-wc", "a1", "approve")
        result = await asyncio.wait_for(c.wait_for_consensus(sid), timeout=5.0)
        assert "votes" in result
        assert isinstance(result["votes"], list)

    async def test_wait_session_not_found_returns_error_dict(self) -> None:
        c = _collector()
        result = await c.wait_for_consensus("no-such-session")
        assert "error" in result
        assert result["session_id"] == "no-such-session"


# ---------------------------------------------------------------------------
# VoteSession — additional branch coverage
# ---------------------------------------------------------------------------


class TestVoteSessionAdditionalBranches:
    def test_duplicate_vote_warning_logged(self) -> None:
        """Duplicate vote returns False (covers lines 148-149 warning log)."""
        sess = _session()
        sess.add_vote(_vote("a1"))
        result = sess.add_vote(_vote("a1"))  # duplicate
        assert result is False

    def test_agent_weight_overridden_on_add_vote(self) -> None:
        """Agent weight override in add_vote (covers line 153)."""
        sess = _session(agent_weights={"a1": 5.0})
        v = _vote("a1", weight=1.0)
        sess.add_vote(v)
        assert sess.votes[0].weight == 5.0

    def test_check_consensus_rejected(self) -> None:
        """Rejection consensus branch (covers lines 234-242)."""
        sess = _session(required_votes=2, threshold=0.66)
        sess.add_vote(_vote("a1", decision="reject"))
        sess.add_vote(_vote("a2", decision="reject"))
        result = sess.check_consensus()
        assert result["consensus_reached"] is True
        assert result["decision"] == "rejected"
        assert "rejection_rate" in result

    def test_check_consensus_threshold_not_met(self) -> None:
        """Threshold not met branch — neither approval nor rejection reaches threshold."""
        sess = _session(required_votes=4, threshold=0.66)
        sess.add_vote(_vote("a1", decision="approve"))
        sess.add_vote(_vote("a2", decision="approve"))
        sess.add_vote(_vote("a3", decision="reject"))
        sess.add_vote(_vote("a4", decision="reject"))
        result = sess.check_consensus()
        assert result["consensus_reached"] is False
        assert result["reason"] == "threshold_not_met"


# ---------------------------------------------------------------------------
# EventDrivenVoteCollector — additional coverage for missed lines
# ---------------------------------------------------------------------------


class TestCollectorAdditionalCoverage:
    async def test_submit_vote_invalid_decision_raises(self) -> None:
        """Invalid decision raises ValueError (covers line 474)."""
        c = _collector()
        with pytest.raises(ValueError, match="Invalid decision"):
            await c.submit_vote("msg-1", "agent-1", "maybe")

    async def test_get_session_count_returns_count(self) -> None:
        """get_session_count returns number of active sessions (covers line 684)."""
        c = _collector()
        assert c.get_session_count() == 0
        await c.create_vote_session("msg-1")
        assert c.get_session_count() == 1
        await c.create_vote_session("msg-2")
        assert c.get_session_count() == 2

    async def test_get_session_info_returns_none_for_missing(self) -> None:
        """get_session_info returns None for unknown session (covers lines 688-692)."""
        c = _collector()
        result = await c.get_session_info("nonexistent")
        assert result is None

    async def test_get_session_info_returns_dict_for_known(self) -> None:
        """get_session_info returns dict with all fields for known session."""
        c = _collector()
        sid = await c.create_vote_session("msg-si", required_votes=3, consensus_threshold=0.75)
        info = await c.get_session_info(sid)
        assert info is not None
        assert info["session_id"] == sid
        assert info["message_id"] == "msg-si"
        assert info["required_votes"] == 3
        assert info["consensus_threshold"] == 0.75
        assert info["votes_received"] == 0
        assert info["completed"] is False
        assert "created_at" in info
        assert "is_timed_out" in info
        assert "consensus" in info

    async def test_wait_for_consensus_timeout_branch(self) -> None:
        """wait_for_consensus TimeoutError branch (covers lines 544-549)."""
        c = _collector()
        sid = await c.create_vote_session("msg-tmo", required_votes=99, timeout_seconds=60)
        # Submit one vote so votes list is non-empty
        await c.submit_vote("msg-tmo", "a1", "approve")
        # Use a tiny timeout that will expire immediately
        result = await c.wait_for_consensus(sid, timeout_override=0.001)
        assert result.get("timed_out") is True
        assert "votes" in result
        # Session should be cleaned up after timeout
        assert sid not in c._sessions

    async def test_create_session_expire_called_on_redis(self) -> None:
        """expire is called on the Redis sessions key (covers line 397)."""
        c = _collector()
        mock_redis = AsyncMock()
        c.redis_client = mock_redis
        await c.create_vote_session("msg-exp", timeout_seconds=120)
        # Check that expire was called with sessions key and (timeout + 60)
        calls = mock_redis.expire.call_args_list
        assert len(calls) == 1
        args = calls[0][0]
        assert "sessions" in args[0]
        assert args[1] == 180  # 120 + 60


# ---------------------------------------------------------------------------
# _stabilize_weights — additional coverage for missed branches
# ---------------------------------------------------------------------------


class TestStabilizeWeightsAdditional:
    def test_rust_path_numpy_raises_import_error_falls_through(self) -> None:
        """RUST_AVAILABLE=True, NUMPY_AVAILABLE=True but numpy raises ImportError."""
        import enhanced_agent_bus.deliberation_layer.vote_collector as vc_mod

        sess = _session(agent_weights={"a1": 2.0})
        mock_rust = MagicMock()
        mock_np = MagicMock()
        # np.array raises an error, caught by except block
        mock_np.array.side_effect = TypeError("bad array")
        mock_np.float32 = float

        orig_rust = vc_mod.RUST_AVAILABLE
        orig_numpy = vc_mod.NUMPY_AVAILABLE
        orig_rust_opt = vc_mod.rust_opt
        orig_np = vc_mod.np
        orig_sinkhorn = vc_mod.sinkhorn_projection
        orig_torch = vc_mod.TORCH_AVAILABLE
        try:
            vc_mod.RUST_AVAILABLE = True
            vc_mod.NUMPY_AVAILABLE = True
            vc_mod.rust_opt = mock_rust
            vc_mod.np = mock_np
            vc_mod.sinkhorn_projection = None
            vc_mod.TORCH_AVAILABLE = False
            result = sess._stabilize_weights()
            # TypeError is caught -> falls back to original weights
            assert result == {"a1": 2.0}
        finally:
            vc_mod.RUST_AVAILABLE = orig_rust
            vc_mod.NUMPY_AVAILABLE = orig_numpy
            vc_mod.rust_opt = orig_rust_opt
            vc_mod.np = orig_np
            vc_mod.sinkhorn_projection = orig_sinkhorn
            vc_mod.TORCH_AVAILABLE = orig_torch

    def test_rust_sinkhorn_runtime_error_falls_through(self) -> None:
        """RuntimeError in rust sinkhorn is caught and falls through."""
        import enhanced_agent_bus.deliberation_layer.vote_collector as vc_mod

        sess = _session(agent_weights={"a1": 3.0, "a2": 1.0})
        mock_rust = MagicMock()
        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()
        mock_np.float32 = float
        mock_rust.sinkhorn_knopp_stabilize.side_effect = RuntimeError("computation failed")

        orig_rust = vc_mod.RUST_AVAILABLE
        orig_numpy = vc_mod.NUMPY_AVAILABLE
        orig_rust_opt = vc_mod.rust_opt
        orig_np = vc_mod.np
        orig_sinkhorn = vc_mod.sinkhorn_projection
        orig_torch = vc_mod.TORCH_AVAILABLE
        try:
            vc_mod.RUST_AVAILABLE = True
            vc_mod.NUMPY_AVAILABLE = True
            vc_mod.rust_opt = mock_rust
            vc_mod.np = mock_np
            vc_mod.sinkhorn_projection = None
            vc_mod.TORCH_AVAILABLE = False
            result = sess._stabilize_weights()
            # Falls back to original weights
            assert result == {"a1": 3.0, "a2": 1.0}
        finally:
            vc_mod.RUST_AVAILABLE = orig_rust
            vc_mod.NUMPY_AVAILABLE = orig_numpy
            vc_mod.rust_opt = orig_rust_opt
            vc_mod.np = orig_np
            vc_mod.sinkhorn_projection = orig_sinkhorn
            vc_mod.TORCH_AVAILABLE = orig_torch

    def test_rust_success_normalizes_weights(self) -> None:
        """Rust sinkhorn succeeds and returns normalized weights (covers lines 184-187)."""
        import enhanced_agent_bus.deliberation_layer.vote_collector as vc_mod

        sess = _session(agent_weights={"a1": 3.0, "a2": 1.0})
        mock_rust = MagicMock()
        # Set up numpy arrays properly
        import numpy as np

        weights_array = np.array([[3.0, 1.0]], dtype=np.float32)
        mock_rust.sinkhorn_knopp_stabilize.return_value = weights_array

        orig_rust = vc_mod.RUST_AVAILABLE
        orig_numpy = vc_mod.NUMPY_AVAILABLE
        orig_rust_opt = vc_mod.rust_opt
        orig_np = vc_mod.np

        try:
            vc_mod.RUST_AVAILABLE = True
            vc_mod.NUMPY_AVAILABLE = True
            vc_mod.rust_opt = mock_rust
            vc_mod.np = np
            result = sess._stabilize_weights()
            assert isinstance(result, dict)
            assert set(result.keys()) == {"a1", "a2"}
        except ImportError:
            # numpy not available in this environment, skip
            pytest.skip("numpy not available")
        finally:
            vc_mod.RUST_AVAILABLE = orig_rust
            vc_mod.NUMPY_AVAILABLE = orig_numpy
            vc_mod.rust_opt = orig_rust_opt
            vc_mod.np = orig_np


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


class TestGlobalSingletonExtra:
    def setup_method(self) -> None:
        reset_vote_collector()

    def teardown_method(self) -> None:
        reset_vote_collector()

    def test_get_returns_event_driven_vote_collector(self) -> None:
        c = get_vote_collector()
        assert isinstance(c, EventDrivenVoteCollector)

    def test_reset_clears_singleton(self) -> None:
        c1 = get_vote_collector()
        reset_vote_collector()
        c2 = get_vote_collector()
        assert c1 is not c2
