# Constitutional Hash: cdd01ef066bc6cf2
"""
Comprehensive coverage tests for deliberation_layer/vote_collector.py.
Target: bring coverage to >=98%.

Covers previously uncovered branches:
- Line 169: NUMPY_AVAILABLE=False raises ImportError inside _stabilize_weights
- Lines 184-187: Rust sinkhorn success normalization (total > 0 branch)
- Line 185: stabilized_vector /= total (in-place division when total > 0)
- Line 197: final return self.agent_weights (sinkhorn_projection+torch path)
- Lines 504-506: in-memory vote append when message_id already exists
- Line 567: get_current_votes in-memory fallback when redis_client is None
- Lines 593-594: outer exception handler in _subscriber_loop
- Lines 633, 636: loop continuation branches in _process_vote_event
- Lines 644-648: completion_event.set() when consensus reached
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from packages.enhanced_agent_bus.deliberation_layer.vote_collector import (
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
    session_id: str = "sess-1",
    message_id: str = "msg-1",
) -> VoteSession:
    return VoteSession(
        session_id=session_id,
        message_id=message_id,
        required_votes=required_votes,
        consensus_threshold=threshold,
        timeout_seconds=timeout,
        agent_weights=agent_weights or {},
        completion_event=asyncio.Event(),
    )


def _collector(**kwargs) -> EventDrivenVoteCollector:
    return EventDrivenVoteCollector(**kwargs)


# ---------------------------------------------------------------------------
# VoteEvent serialization
# ---------------------------------------------------------------------------


class TestVoteEventSerialization:
    def test_to_dict_includes_all_fields(self) -> None:
        v = _vote("a1", decision="reject")
        d = v.to_dict()
        assert d["vote_id"] == "v-a1"
        assert d["agent_id"] == "a1"
        assert d["decision"] == "reject"
        assert "timestamp" in d
        assert "metadata" in d

    def test_from_dict_roundtrip(self) -> None:
        v = _vote("a2", decision="abstain", weight=2.5)
        v2 = VoteEvent.from_dict(v.to_dict())
        assert v2.agent_id == "a2"
        assert v2.decision == "abstain"
        assert v2.weight == 2.5

    def test_from_dict_missing_vote_id_generates_uuid(self) -> None:
        data = {"message_id": "m", "agent_id": "a", "decision": "approve"}
        v = VoteEvent.from_dict(data)
        assert len(v.vote_id) > 0

    def test_from_dict_with_explicit_timestamp(self) -> None:
        data = {
            "message_id": "m",
            "agent_id": "a",
            "decision": "approve",
            "timestamp": "2025-03-15T10:30:00+00:00",
        }
        v = VoteEvent.from_dict(data)
        assert v.timestamp.year == 2025
        assert v.timestamp.month == 3

    def test_from_dict_without_timestamp_uses_current_time(self) -> None:
        before = datetime.now(UTC)
        v = VoteEvent.from_dict({"message_id": "m", "agent_id": "a", "decision": "reject"})
        after = datetime.now(UTC)
        assert before <= v.timestamp <= after

    def test_default_metadata_empty(self) -> None:
        v = VoteEvent(
            vote_id="v1",
            message_id="m",
            agent_id="a",
            decision="approve",
            reasoning="t",
            confidence=1.0,
        )
        assert v.metadata == {}


# ---------------------------------------------------------------------------
# VoteSession comprehensive
# ---------------------------------------------------------------------------


class TestVoteSessionComprehensive:
    def test_add_vote_applies_agent_weight_override(self) -> None:
        sess = _session(agent_weights={"a1": 5.0})
        v = _vote("a1", weight=1.0)
        sess.add_vote(v)
        assert sess.votes[0].weight == 5.0

    def test_add_vote_no_weight_override_keeps_original(self) -> None:
        sess = _session(agent_weights={"other": 5.0})
        v = _vote("a1", weight=2.0)
        sess.add_vote(v)
        assert sess.votes[0].weight == 2.0

    def test_add_duplicate_vote_returns_false(self) -> None:
        sess = _session()
        sess.add_vote(_vote("a1"))
        assert sess.add_vote(_vote("a1")) is False
        assert len(sess.votes) == 1

    def test_check_consensus_insufficient_votes(self) -> None:
        sess = _session(required_votes=3)
        sess.add_vote(_vote("a1"))
        result = sess.check_consensus()
        assert result["consensus_reached"] is False
        assert result["reason"] == "insufficient_votes"

    def test_check_consensus_approved(self) -> None:
        sess = _session(required_votes=2, threshold=0.5)
        sess.add_vote(_vote("a1", decision="approve"))
        sess.add_vote(_vote("a2", decision="approve"))
        result = sess.check_consensus()
        assert result["consensus_reached"] is True
        assert result["decision"] == "approved"

    def test_check_consensus_rejected(self) -> None:
        sess = _session(required_votes=2, threshold=0.66)
        sess.add_vote(_vote("a1", decision="reject"))
        sess.add_vote(_vote("a2", decision="reject"))
        result = sess.check_consensus()
        assert result["consensus_reached"] is True
        assert result["decision"] == "rejected"
        assert "rejection_rate" in result

    def test_check_consensus_threshold_not_met(self) -> None:
        sess = _session(required_votes=4, threshold=0.75)
        for agent, dec in [
            ("a1", "approve"),
            ("a2", "approve"),
            ("a3", "reject"),
            ("a4", "reject"),
        ]:
            sess.add_vote(_vote(agent, decision=dec))
        result = sess.check_consensus()
        assert result["consensus_reached"] is False
        assert result["reason"] == "threshold_not_met"

    def test_check_consensus_zero_total_weight(self) -> None:
        sess = VoteSession(
            session_id="sz",
            message_id="mz",
            required_votes=1,
            consensus_threshold=0.5,
            timeout_seconds=300,
            agent_weights={"a1": 0.0},
        )
        vote = VoteEvent(
            vote_id="v1",
            message_id="mz",
            agent_id="a1",
            decision="approve",
            reasoning="",
            confidence=1.0,
            weight=0.0,
        )
        sess.votes.append(vote)
        result = sess.check_consensus()
        assert result["consensus_reached"] is False
        assert result["reason"] == "zero_total_weight"

    def test_is_timed_out_false_for_fresh(self) -> None:
        assert _session(timeout=300).is_timed_out() is False

    def test_is_timed_out_true_for_expired(self) -> None:
        sess = _session(timeout=10)
        sess.created_at = datetime.now(UTC) - timedelta(seconds=20)
        assert sess.is_timed_out() is True

    def test_completion_event_none_by_default(self) -> None:
        sess = VoteSession(
            session_id="s1",
            message_id="m1",
            required_votes=3,
            consensus_threshold=0.66,
            timeout_seconds=300,
        )
        assert sess.completion_event is None


# ---------------------------------------------------------------------------
# _stabilize_weights branches
# ---------------------------------------------------------------------------


class TestStabilizeWeights:
    def _get_vc_module(self):
        """Return the exact module object that VoteSession._stabilize_weights uses.

        With --import-mode=importlib, 'import src.core...' can return a different
        module object than the one loaded for the VoteSession class.  The correct
        approach is to look up VoteSession's module in sys.modules.
        """
        import sys

        return sys.modules[VoteSession.__module__]

    def test_empty_agent_weights_returns_empty(self) -> None:
        assert _session(agent_weights={})._stabilize_weights() == {}

    def test_rust_false_sinkhorn_none_torch_false(self) -> None:
        """Lines 193-194: return agent_weights when all paths unavailable."""
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 1.5, "a2": 0.5})
        saved = (m.RUST_AVAILABLE, m.sinkhorn_projection, m.TORCH_AVAILABLE)
        try:
            m.RUST_AVAILABLE = False
            m.sinkhorn_projection = None
            m.TORCH_AVAILABLE = False
            assert sess._stabilize_weights() == {"a1": 1.5, "a2": 0.5}
        finally:
            m.RUST_AVAILABLE, m.sinkhorn_projection, m.TORCH_AVAILABLE = saved

    def test_rust_false_sinkhorn_present_torch_true_hits_line_197(self) -> None:
        """Line 197: RUST=False, sinkhorn not None, TORCH=True -> last return."""
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 2.0})
        saved = (m.RUST_AVAILABLE, m.sinkhorn_projection, m.TORCH_AVAILABLE)
        try:
            m.RUST_AVAILABLE = False
            m.sinkhorn_projection = MagicMock()
            m.TORCH_AVAILABLE = True
            assert sess._stabilize_weights() == {"a1": 2.0}
        finally:
            m.RUST_AVAILABLE, m.sinkhorn_projection, m.TORCH_AVAILABLE = saved

    def test_rust_true_numpy_false_raises_import_error(self) -> None:
        """Line 169: NUMPY=False inside RUST block raises ImportError (not caught by except clause)."""  # noqa: E501
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 2.0})
        saved = (m.RUST_AVAILABLE, m.NUMPY_AVAILABLE, m.sinkhorn_projection, m.TORCH_AVAILABLE)
        try:
            m.RUST_AVAILABLE = True
            m.NUMPY_AVAILABLE = False
            m.sinkhorn_projection = None
            m.TORCH_AVAILABLE = False
            # ImportError is raised on line 169; the except only catches (ValueError, TypeError, RuntimeError)  # noqa: E501
            # so it propagates out of _stabilize_weights
            with pytest.raises(ImportError, match="numpy is required"):
                sess._stabilize_weights()
        finally:
            m.RUST_AVAILABLE, m.NUMPY_AVAILABLE, m.sinkhorn_projection, m.TORCH_AVAILABLE = saved

    def test_rust_true_sinkhorn_raises_value_error(self) -> None:
        """Lines 188-191: ValueError in Rust falls through, log warning issued."""
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 2.0, "a2": 1.0})
        mock_rust = MagicMock()
        mock_rust.sinkhorn_knopp_stabilize.side_effect = ValueError("bad")
        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()
        mock_np.float32 = float
        saved = (
            m.RUST_AVAILABLE,
            m.NUMPY_AVAILABLE,
            m.rust_opt,
            m.np,
            m.sinkhorn_projection,
            m.TORCH_AVAILABLE,
        )
        try:
            m.RUST_AVAILABLE = True
            m.NUMPY_AVAILABLE = True
            m.rust_opt = mock_rust
            m.np = mock_np
            m.sinkhorn_projection = None
            m.TORCH_AVAILABLE = False
            assert sess._stabilize_weights() == {"a1": 2.0, "a2": 1.0}
        finally:
            (
                m.RUST_AVAILABLE,
                m.NUMPY_AVAILABLE,
                m.rust_opt,
                m.np,
                m.sinkhorn_projection,
                m.TORCH_AVAILABLE,
            ) = saved

    def test_rust_true_sinkhorn_raises_runtime_error(self) -> None:
        """RuntimeError in Rust falls through, log warning issued."""
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 3.0, "a2": 1.0})
        mock_rust = MagicMock()
        mock_rust.sinkhorn_knopp_stabilize.side_effect = RuntimeError("fail")
        mock_np = MagicMock()
        mock_np.array.return_value = MagicMock()
        mock_np.float32 = float
        saved = (
            m.RUST_AVAILABLE,
            m.NUMPY_AVAILABLE,
            m.rust_opt,
            m.np,
            m.sinkhorn_projection,
            m.TORCH_AVAILABLE,
        )
        try:
            m.RUST_AVAILABLE = True
            m.NUMPY_AVAILABLE = True
            m.rust_opt = mock_rust
            m.np = mock_np
            m.sinkhorn_projection = None
            m.TORCH_AVAILABLE = False
            assert sess._stabilize_weights() == {"a1": 3.0, "a2": 1.0}
        finally:
            (
                m.RUST_AVAILABLE,
                m.NUMPY_AVAILABLE,
                m.rust_opt,
                m.np,
                m.sinkhorn_projection,
                m.TORCH_AVAILABLE,
            ) = saved

    def test_rust_true_sinkhorn_raises_type_error(self) -> None:
        """TypeError in np.array is caught, log warning issued."""
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 2.0})
        mock_rust = MagicMock()
        mock_np = MagicMock()
        mock_np.array.side_effect = TypeError("bad")
        mock_np.float32 = float
        saved = (
            m.RUST_AVAILABLE,
            m.NUMPY_AVAILABLE,
            m.rust_opt,
            m.np,
            m.sinkhorn_projection,
            m.TORCH_AVAILABLE,
        )
        try:
            m.RUST_AVAILABLE = True
            m.NUMPY_AVAILABLE = True
            m.rust_opt = mock_rust
            m.np = mock_np
            m.sinkhorn_projection = None
            m.TORCH_AVAILABLE = False
            assert sess._stabilize_weights() == {"a1": 2.0}
        finally:
            (
                m.RUST_AVAILABLE,
                m.NUMPY_AVAILABLE,
                m.rust_opt,
                m.np,
                m.sinkhorn_projection,
                m.TORCH_AVAILABLE,
            ) = saved

    def test_rust_success_nonzero_total_normalizes(self) -> None:
        """Lines 184-187: sinkhorn succeeds, total > 0, weights normalized."""
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 3.0, "a2": 1.0})
        mock_rust = MagicMock()
        mock_np = MagicMock()
        mock_np.float32 = float

        class FakeVec:
            def sum(self):
                return 4.0

            def __itruediv__(self, other):
                return self

            def __getitem__(self, i):
                return 0.75 if i == 0 else 0.25

        fv = FakeVec()
        mock_mat = MagicMock()
        mock_mat.__getitem__ = MagicMock(return_value=fv)
        mock_rust.sinkhorn_knopp_stabilize.return_value = mock_mat
        mock_np.array.return_value = MagicMock()

        saved = (m.RUST_AVAILABLE, m.NUMPY_AVAILABLE, m.rust_opt, m.np)
        try:
            m.RUST_AVAILABLE = True
            m.NUMPY_AVAILABLE = True
            m.rust_opt = mock_rust
            m.np = mock_np
            result = sess._stabilize_weights()
            assert result["a1"] == pytest.approx(0.75)
            assert result["a2"] == pytest.approx(0.25)
        finally:
            m.RUST_AVAILABLE, m.NUMPY_AVAILABLE, m.rust_opt, m.np = saved

    def test_rust_success_zero_total_skips_division(self) -> None:
        """Line 184: total == 0 means /= is skipped."""
        m = self._get_vc_module()
        sess = _session(agent_weights={"a1": 1.0})
        mock_rust = MagicMock()
        mock_np = MagicMock()
        mock_np.float32 = float

        class FakeVecZero:
            def sum(self):
                return 0.0

            def __getitem__(self, i):
                return 0.0

        fv = FakeVecZero()
        mock_mat = MagicMock()
        mock_mat.__getitem__ = MagicMock(return_value=fv)
        mock_rust.sinkhorn_knopp_stabilize.return_value = mock_mat
        mock_np.array.return_value = MagicMock()

        saved = (m.RUST_AVAILABLE, m.NUMPY_AVAILABLE, m.rust_opt, m.np)
        try:
            m.RUST_AVAILABLE = True
            m.NUMPY_AVAILABLE = True
            m.rust_opt = mock_rust
            m.np = mock_np
            result = sess._stabilize_weights()
            assert result["a1"] == pytest.approx(0.0)
        finally:
            m.RUST_AVAILABLE, m.NUMPY_AVAILABLE, m.rust_opt, m.np = saved


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestCollectorConnect:
    async def test_connect_redis_unavailable(self) -> None:
        c = _collector()
        with patch(
            "packages.enhanced_agent_bus.deliberation_layer.vote_collector.REDIS_AVAILABLE", False
        ):
            assert await c.connect() is False

    async def test_connect_redis_success(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_pubsub = AsyncMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_aioredis = MagicMock()
        mock_aioredis.from_url.return_value = mock_redis

        with (
            patch(
                "packages.enhanced_agent_bus.deliberation_layer.vote_collector.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "packages.enhanced_agent_bus.deliberation_layer.vote_collector.aioredis",
                mock_aioredis,
            ),
        ):
            result = await c.connect()
        assert result is True
        assert c._running is True
        c._subscriber_task.cancel()
        try:  # noqa: SIM105
            await c._subscriber_task
        except (asyncio.CancelledError, Exception):  # noqa: S110
            pass

    async def test_connect_connection_error(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = ConnectionError("refused")
        mock_aioredis = MagicMock()
        mock_aioredis.from_url.return_value = mock_redis
        with (
            patch(
                "packages.enhanced_agent_bus.deliberation_layer.vote_collector.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "packages.enhanced_agent_bus.deliberation_layer.vote_collector.aioredis",
                mock_aioredis,
            ),
        ):
            result = await c.connect()
        assert result is False
        assert c.redis_client is None

    async def test_connect_os_error(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = OSError("net error")
        mock_aioredis = MagicMock()
        mock_aioredis.from_url.return_value = mock_redis
        with (
            patch(
                "packages.enhanced_agent_bus.deliberation_layer.vote_collector.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "packages.enhanced_agent_bus.deliberation_layer.vote_collector.aioredis",
                mock_aioredis,
            ),
        ):
            result = await c.connect()
        assert result is False


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


class TestCollectorDisconnect:
    async def test_disconnect_no_connections(self) -> None:
        c = _collector()
        await c.disconnect()
        assert c._running is False

    async def test_disconnect_cancels_subscriber_task(self) -> None:
        c = _collector()
        finished = False

        async def fake_sub():
            nonlocal finished
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                finished = True
                raise

        task = asyncio.create_task(fake_sub())
        await asyncio.sleep(0)
        c._subscriber_task = task
        c._running = True
        await c.disconnect()
        assert finished is True
        assert c._subscriber_task is None

    async def test_disconnect_with_pubsub_and_redis(self) -> None:
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
# create_vote_session()
# ---------------------------------------------------------------------------


class TestCreateVoteSession:
    async def test_basic_creation(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("msg-1", required_votes=3)
        assert "msg-1" in sid
        assert c.get_session_count() == 1

    async def test_creates_completion_event(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("msg-ev")
        assert isinstance(c._sessions[sid].completion_event, asyncio.Event)

    async def test_subscribes_pubsub(self) -> None:
        c = _collector()
        mock_pubsub = AsyncMock()
        c.pubsub = mock_pubsub
        await c.create_vote_session("msg-sub")
        mock_pubsub.subscribe.assert_called_once_with("acgs:votes:msg-sub")

    async def test_persists_to_redis(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        c.redis_client = mock_redis
        await c.create_vote_session("msg-r", timeout_seconds=120)
        mock_redis.hset.assert_called_once()
        args = mock_redis.expire.call_args[0]
        assert args[1] == 180  # 120 + 60

    async def test_redis_error_does_not_raise(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.hset.side_effect = ConnectionError("lost")
        c.redis_client = mock_redis
        sid = await c.create_vote_session("msg-err")
        assert sid is not None

    async def test_max_sessions_cleanup_frees_space(self) -> None:
        c = _collector(max_concurrent_sessions=2)
        sid1 = await c.create_vote_session("msg-a")
        sid2 = await c.create_vote_session("msg-b")
        c._sessions[sid1].created_at = datetime.now(UTC) - timedelta(seconds=9999)
        c._sessions[sid2].created_at = datetime.now(UTC) - timedelta(seconds=9999)
        sid3 = await c.create_vote_session("msg-c")
        assert sid3 is not None

    async def test_max_sessions_no_cleanup_raises(self) -> None:
        c = _collector(max_concurrent_sessions=2)
        await c.create_vote_session("msg-x")
        await c.create_vote_session("msg-y")
        with pytest.raises(RuntimeError, match="Maximum concurrent sessions"):
            await c.create_vote_session("msg-z")

    async def test_redis_timeout_error_caught(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.hset.side_effect = TimeoutError("timeout")
        c.redis_client = mock_redis
        assert await c.create_vote_session("msg-to") is not None


# ---------------------------------------------------------------------------
# submit_vote()
# ---------------------------------------------------------------------------


class TestSubmitVote:
    async def test_invalid_decision_raises(self) -> None:
        c = _collector()
        with pytest.raises(ValueError, match="Invalid decision"):
            await c.submit_vote("m", "a", "maybe")

    async def test_approve_in_memory(self) -> None:
        c = _collector()
        await c.create_vote_session("msg-1", required_votes=5)
        assert await c.submit_vote("msg-1", "a1", "approve") is True
        assert "msg-1" in c._in_memory_votes

    async def test_appends_to_existing_list(self) -> None:
        """Lines 504-506: message_id already in _in_memory_votes -> append."""
        c = _collector()
        await c.create_vote_session("msg-a", required_votes=5)
        await c.submit_vote("msg-a", "a1", "approve")
        await c.submit_vote("msg-a", "a2", "reject")
        assert len(c._in_memory_votes["msg-a"]) == 2

    async def test_with_metadata(self) -> None:
        c = _collector()
        await c.submit_vote("m", "a", "approve", metadata={"k": "v"})
        assert c._in_memory_votes["m"][0].metadata == {"k": "v"}

    async def test_redis_success(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        c.redis_client = mock_redis
        assert await c.submit_vote("m", "a", "approve") is True
        mock_redis.publish.assert_called_once()

    async def test_redis_error_fallback(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = ConnectionError("err")
        c.redis_client = mock_redis
        assert await c.submit_vote("msg-err", "a", "approve") is True
        assert "msg-err" in c._in_memory_votes

    async def test_abstain_valid(self) -> None:
        assert await _collector().submit_vote("m", "a", "abstain") is True

    async def test_reject_valid(self) -> None:
        assert await _collector().submit_vote("m", "a", "reject") is True

    async def test_redis_timeout_fallback(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = TimeoutError("timeout")
        c.redis_client = mock_redis
        assert await c.submit_vote("m-to", "a", "approve") is True


# ---------------------------------------------------------------------------
# wait_for_consensus()
# ---------------------------------------------------------------------------


class TestWaitForConsensus:
    async def test_session_not_found(self) -> None:
        c = _collector()
        result = await c.wait_for_consensus("no-such")
        assert "error" in result
        assert result["session_id"] == "no-such"

    async def test_consensus_reached_returns_votes(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=1, consensus_threshold=0.5)
        await c.submit_vote("m", "a1", "approve")
        result = await asyncio.wait_for(c.wait_for_consensus(sid), timeout=5.0)
        assert result["consensus_reached"] is True
        assert isinstance(result["votes"], list)

    async def test_timeout_sets_timed_out_flag(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=99, timeout_seconds=60)
        await c.submit_vote("m", "a1", "approve")
        result = await c.wait_for_consensus(sid, timeout_override=0.001)
        assert result.get("timed_out") is True
        assert sid not in c._sessions

    async def test_timeout_override_used(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=10, timeout_seconds=9999)
        result = await c.wait_for_consensus(sid, timeout_override=0.001)
        assert result.get("timed_out") is True

    async def test_session_cleaned_up_after_consensus(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=1, consensus_threshold=0.5)
        await c.submit_vote("m", "a1", "approve")
        await asyncio.wait_for(c.wait_for_consensus(sid), timeout=5.0)
        assert sid not in c._sessions


# ---------------------------------------------------------------------------
# get_current_votes()
# ---------------------------------------------------------------------------


class TestGetCurrentVotes:
    async def test_in_memory_fallback_no_redis(self) -> None:
        """Line 567: redis_client is None -> return in-memory."""
        c = _collector()
        c._in_memory_votes["m"] = [_vote("a1", message_id="m")]
        result = await c.get_current_votes("m")
        assert len(result) == 1

    async def test_empty_in_memory(self) -> None:
        c = _collector()
        assert await c.get_current_votes("no-msg") == []

    async def test_from_redis(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {"a1": json.dumps(_vote("a1").to_dict())}
        c.redis_client = mock_redis
        result = await c.get_current_votes("m")
        assert len(result) == 1

    async def test_redis_error_fallback(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.hgetall.side_effect = ConnectionError("err")
        c.redis_client = mock_redis
        c._in_memory_votes["m-fb"] = [_vote("a1", message_id="m-fb")]
        result = await c.get_current_votes("m-fb")
        assert len(result) == 1

    async def test_redis_timeout_fallback(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.hgetall.side_effect = TimeoutError("timeout")
        c.redis_client = mock_redis
        assert await c.get_current_votes("m") == []


# ---------------------------------------------------------------------------
# _subscriber_loop()
# ---------------------------------------------------------------------------


class TestSubscriberLoop:
    async def test_exits_when_not_running(self) -> None:
        c = _collector()
        c._running = False
        await c._subscriber_loop()

    async def test_processes_message_then_exits(self) -> None:
        c = _collector()
        c._running = True
        await c.create_vote_session("msg-loop", required_votes=5)
        vote_data = _vote("a1", message_id="msg-loop").to_dict()
        n = 0

        async def fake_get(ignore_subscribe_messages=True):
            nonlocal n
            n += 1
            if n == 1:
                return {
                    "type": "message",
                    "channel": "acgs:votes:msg-loop",
                    "data": json.dumps(vote_data),
                }
            c._running = False
            return None

        mock_pub = MagicMock()
        mock_pub.get_message = fake_get
        c.pubsub = mock_pub
        await c._subscriber_loop()
        assert len(list(c._sessions.values())[0].votes) == 1

    async def test_timeout_error_continues(self) -> None:
        c = _collector()
        c._running = True
        n = 0

        async def fake_get(ignore_subscribe_messages=True):
            nonlocal n
            n += 1
            if n <= 2:
                raise TimeoutError()
            c._running = False

        mock_pub = MagicMock()
        mock_pub.get_message = fake_get
        c.pubsub = mock_pub
        await c._subscriber_loop()
        assert n == 3

    async def test_cancelled_error_breaks_inner(self) -> None:
        c = _collector()
        c._running = True

        async def fake_get(ignore_subscribe_messages=True):
            raise asyncio.CancelledError()

        mock_pub = MagicMock()
        mock_pub.get_message = fake_get
        c.pubsub = mock_pub
        await c._subscriber_loop()

    async def test_runtime_error_sleeps_and_continues(self) -> None:
        c = _collector()
        c._running = True
        n = 0

        async def fake_get(ignore_subscribe_messages=True):
            nonlocal n
            n += 1
            if n == 1:
                raise RuntimeError("err")
            c._running = False

        mock_pub = MagicMock()
        mock_pub.get_message = fake_get
        c.pubsub = mock_pub
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._subscriber_loop()

    async def test_outer_os_error_exits(self) -> None:
        """Lines 593-594: outer OSError exits gracefully."""
        c = _collector()
        c._running = True
        n = 0

        async def fake_get(ignore_subscribe_messages=True):
            nonlocal n
            n += 1
            if n == 1:
                raise OSError("broken")
            c._running = False

        mock_pub = MagicMock()
        mock_pub.get_message = fake_get
        c.pubsub = mock_pub
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._subscriber_loop()

    async def test_outer_value_error_exits(self) -> None:
        """Lines 593-594: outer ValueError exits gracefully."""
        c = _collector()
        c._running = True
        n = 0

        async def fake_get(ignore_subscribe_messages=True):
            nonlocal n
            n += 1
            if n == 1:
                raise ValueError("bad")
            c._running = False

        mock_pub = MagicMock()
        mock_pub.get_message = fake_get
        c.pubsub = mock_pub
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await c._subscriber_loop()

    async def test_outer_exception_via_sleep_raising(self) -> None:
        """Lines 593-594: outer except fires when asyncio.sleep raises after inner error."""
        c = _collector()
        c._running = True

        async def fake_get(ignore_subscribe_messages=True):
            raise RuntimeError("inner error")

        mock_pub = MagicMock()
        mock_pub.get_message = fake_get
        c.pubsub = mock_pub

        # Make asyncio.sleep raise to escape the inner handler and hit the outer except
        sleep_mock = AsyncMock(side_effect=OSError("sleep failure"))
        with patch("asyncio.sleep", sleep_mock):
            await c._subscriber_loop()


# ---------------------------------------------------------------------------
# _handle_pubsub_message()
# ---------------------------------------------------------------------------


class TestHandlePubsubMessage:
    async def test_valid_message(self) -> None:
        c = _collector()
        await c.create_vote_session("msg-ps", required_votes=3)
        vote_data = _vote("a1", message_id="msg-ps").to_dict()
        await c._handle_pubsub_message(
            {"type": "message", "channel": "acgs:votes:msg-ps", "data": json.dumps(vote_data)}
        )
        assert len(list(c._sessions.values())[0].votes) == 1

    async def test_empty_data_skips(self) -> None:
        await _collector()._handle_pubsub_message({"type": "message", "channel": "ch", "data": ""})

    async def test_empty_channel_skips(self) -> None:
        await _collector()._handle_pubsub_message({"type": "message", "channel": "", "data": "{}"})

    async def test_invalid_json(self) -> None:
        await _collector()._handle_pubsub_message(
            {"type": "message", "channel": "ch", "data": "bad{{{"}
        )

    async def test_missing_required_keys(self) -> None:
        await _collector()._handle_pubsub_message(
            {"type": "message", "channel": "ch", "data": json.dumps({"vote_id": "v1"})}
        )

    async def test_no_data_key(self) -> None:
        await _collector()._handle_pubsub_message({"type": "message"})


# ---------------------------------------------------------------------------
# _process_vote_event()
# ---------------------------------------------------------------------------


class TestProcessVoteEvent:
    async def test_different_message_id_skipped(self) -> None:
        c = _collector()
        await c.create_vote_session("msg-A", required_votes=3)
        await c._process_vote_event(_vote("a1", message_id="msg-B"))
        assert len(list(c._sessions.values())[0].votes) == 0

    async def test_completed_session_skipped(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=1, consensus_threshold=0.5)
        c._sessions[sid].completed = True
        await c._process_vote_event(_vote("a1", message_id="m"))
        assert len(c._sessions[sid].votes) == 0

    async def test_consensus_reached_sets_completed_and_event(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=1, consensus_threshold=0.5)
        sess = c._sessions[sid]
        await c._process_vote_event(_vote("a1", message_id="m"))
        assert sess.completed is True
        assert sess.completion_event.is_set()

    async def test_duplicate_vote_not_added(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=2)
        vote = _vote("a1", message_id="m")
        c._sessions[sid].votes.append(vote)
        await c._process_vote_event(vote)
        assert c._sessions[sid].completed is False

    async def test_multiple_sessions_same_message(self) -> None:
        c = _collector()
        sid1 = await c.create_vote_session("m", required_votes=3)
        sid2 = await c.create_vote_session("m", required_votes=3)
        await c._process_vote_event(_vote("a1", message_id="m"))
        assert len(c._sessions[sid1].votes) == 1
        assert len(c._sessions[sid2].votes) == 1

    async def test_no_lock_skips(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=3)
        c._session_locks[sid] = None
        await c._process_vote_event(_vote("a1", message_id="m"))
        assert len(c._sessions[sid].votes) == 0

    async def test_completion_event_none_does_not_raise(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=1, consensus_threshold=0.5)
        c._sessions[sid].completion_event = None
        await c._process_vote_event(_vote("a1", message_id="m"))
        assert c._sessions[sid].completed is True

    async def test_no_sessions_does_not_crash(self) -> None:
        c = _collector()
        await c._process_vote_event(_vote("a1", message_id="no-session"))


# ---------------------------------------------------------------------------
# _cleanup_session()
# ---------------------------------------------------------------------------


class TestCleanupSession:
    async def test_removes_session_and_lock(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m")
        await c._cleanup_session(sid)
        assert sid not in c._sessions
        assert sid not in c._session_locks

    async def test_nonexistent_no_error(self) -> None:
        await _collector()._cleanup_session("nonexistent")

    async def test_unsubscribes_pubsub(self) -> None:
        c = _collector()
        mock_pub = AsyncMock()
        c.pubsub = mock_pub
        sid = await c.create_vote_session("msg-unsub")
        await c._cleanup_session(sid)
        mock_pub.unsubscribe.assert_called_once_with("acgs:votes:msg-unsub")

    async def test_deletes_from_redis(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        c.redis_client = mock_redis
        sid = await c.create_vote_session("m")
        await c._cleanup_session(sid)
        mock_redis.hdel.assert_called_once()

    async def test_pubsub_error_not_raised(self) -> None:
        c = _collector()
        mock_pub = AsyncMock()
        mock_pub.unsubscribe.side_effect = ConnectionError("lost")
        c.pubsub = mock_pub
        sid = await c.create_vote_session("m")
        await c._cleanup_session(sid)

    async def test_redis_error_not_raised(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.hdel.side_effect = ConnectionError("lost")
        c.redis_client = mock_redis
        sid = await c.create_vote_session("m")
        await c._cleanup_session(sid)

    async def test_timeout_error_pubsub_not_raised(self) -> None:
        c = _collector()
        mock_pub = AsyncMock()
        mock_pub.unsubscribe.side_effect = TimeoutError("timeout")
        c.pubsub = mock_pub
        sid = await c.create_vote_session("m")
        await c._cleanup_session(sid)

    async def test_timeout_error_redis_not_raised(self) -> None:
        c = _collector()
        mock_redis = AsyncMock()
        mock_redis.hdel.side_effect = TimeoutError("timeout")
        c.redis_client = mock_redis
        sid = await c.create_vote_session("m")
        await c._cleanup_session(sid)


# ---------------------------------------------------------------------------
# _cleanup_expired_sessions()
# ---------------------------------------------------------------------------


class TestCleanupExpiredSessions:
    async def test_removes_expired(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", timeout_seconds=10)
        c._sessions[sid].created_at = datetime.now(UTC) - timedelta(seconds=20)
        await c._cleanup_expired_sessions()
        assert sid not in c._sessions

    async def test_keeps_fresh(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", timeout_seconds=300)
        await c._cleanup_expired_sessions()
        assert sid in c._sessions

    async def test_mixed(self) -> None:
        c = _collector()
        sid_e = await c.create_vote_session("m-e", timeout_seconds=10)
        sid_f = await c.create_vote_session("m-f", timeout_seconds=300)
        c._sessions[sid_e].created_at = datetime.now(UTC) - timedelta(seconds=20)
        await c._cleanup_expired_sessions()
        assert sid_e not in c._sessions
        assert sid_f in c._sessions


# ---------------------------------------------------------------------------
# get_session_count() / get_session_info()
# ---------------------------------------------------------------------------


class TestSessionInfo:
    async def test_count_zero_initially(self) -> None:
        assert _collector().get_session_count() == 0

    async def test_count_increases(self) -> None:
        c = _collector()
        await c.create_vote_session("m1")
        assert c.get_session_count() == 1
        await c.create_vote_session("m2")
        assert c.get_session_count() == 2

    async def test_info_none_for_unknown(self) -> None:
        assert await _collector().get_session_info("x") is None

    async def test_info_all_fields(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=3, consensus_threshold=0.75)
        info = await c.get_session_info(sid)
        assert info["session_id"] == sid
        assert info["message_id"] == "m"
        assert info["required_votes"] == 3
        assert info["votes_received"] == 0
        assert "is_timed_out" in info
        assert "consensus" in info

    async def test_info_vote_count(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", required_votes=5)
        await c.submit_vote("m", "a1", "approve")
        info = await c.get_session_info(sid)
        assert info["votes_received"] == 1

    async def test_info_timed_out(self) -> None:
        c = _collector()
        sid = await c.create_vote_session("m", timeout_seconds=10)
        c._sessions[sid].created_at = datetime.now(UTC) - timedelta(seconds=20)
        info = await c.get_session_info(sid)
        assert info["is_timed_out"] is True


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


class TestGlobalSingleton:
    def setup_method(self) -> None:
        reset_vote_collector()

    def teardown_method(self) -> None:
        reset_vote_collector()

    def test_get_returns_instance(self) -> None:
        assert isinstance(get_vote_collector(), EventDrivenVoteCollector)

    def test_singleton_same_object(self) -> None:
        assert get_vote_collector() is get_vote_collector()

    def test_reset_creates_new_instance(self) -> None:
        c1 = get_vote_collector()
        reset_vote_collector()
        c2 = get_vote_collector()
        assert c1 is not c2

    def test_custom_channel_prefix(self) -> None:
        assert EventDrivenVoteCollector(channel_prefix="x:y").channel_prefix == "x:y"

    def test_custom_max_sessions(self) -> None:
        assert EventDrivenVoteCollector(max_concurrent_sessions=50).max_concurrent_sessions == 50


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_abstain_only_threshold_not_met(self) -> None:
        sess = _session(required_votes=2, threshold=0.5)
        sess.add_vote(_vote("a1", decision="abstain"))
        sess.add_vote(_vote("a2", decision="abstain"))
        result = sess.check_consensus()
        assert result["consensus_reached"] is False
        assert result["reason"] == "threshold_not_met"
        assert result["approval_rate"] == 0.0

    async def test_weighted_voting_overrides_outcome(self) -> None:
        sess = _session(
            required_votes=2,
            threshold=0.66,
            agent_weights={"heavy": 5.0, "light": 1.0},
        )
        sess.add_vote(_vote("heavy", decision="approve", weight=1.0))
        sess.add_vote(_vote("light", decision="reject", weight=1.0))
        result = sess.check_consensus()
        assert result["consensus_reached"] is True
        assert result["decision"] == "approved"
