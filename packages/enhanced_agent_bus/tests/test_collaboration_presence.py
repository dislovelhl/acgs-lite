"""Tests for collaboration.presence.PresenceManager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from enhanced_agent_bus.collaboration.models import (
    CollaborationConfig,
    CollaborationSession,
    Collaborator,
    CursorPosition,
    PresenceStatus,
    SessionFullError,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.presence import PresenceManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager() -> PresenceManager:
    return PresenceManager(config=CollaborationConfig(max_users_per_document=3))


@pytest.fixture()
def user_info() -> dict:
    return {
        "name": "Alice",
        "email": "alice@example.com",
        "color": "#FF6B6B",
    }


async def _join(manager, doc_id="doc-1", user_id="u1", tenant_id="t1", user_info=None):
    info = user_info or {"name": "User"}
    return await manager.join_session(doc_id, "policy", user_id, info, tenant_id)


# ---------------------------------------------------------------------------
# join_session
# ---------------------------------------------------------------------------


class TestJoinSession:
    @pytest.mark.asyncio
    async def test_join_creates_session(self, manager):
        session, collab = await _join(manager)

        assert session.document_id == "doc-1"
        assert collab.user_id == "u1"
        assert collab.name == "User"
        assert len(session.users) == 1

    @pytest.mark.asyncio
    async def test_join_same_doc_twice(self, manager):
        await _join(manager, user_id="u1")
        session, _ = await _join(manager, user_id="u2")
        assert len(session.users) == 2

    @pytest.mark.asyncio
    async def test_join_full_session_raises(self, manager):
        await _join(manager, user_id="u1")
        await _join(manager, user_id="u2")
        await _join(manager, user_id="u3")

        with pytest.raises(SessionFullError):
            await _join(manager, user_id="u4")

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, manager):
        await _join(manager, user_id="u1", tenant_id="t1")

        with pytest.raises(PermissionError, match="Tenant mismatch"):
            await _join(manager, user_id="u2", tenant_id="t2")

    @pytest.mark.asyncio
    async def test_user_sessions_tracking(self, manager):
        await _join(manager, doc_id="d1", user_id="u1")
        await _join(manager, doc_id="d2", user_id="u1", tenant_id="t1")

        sessions = await manager.get_user_sessions("u1")
        assert set(sessions) == {"d1", "d2"}


# ---------------------------------------------------------------------------
# leave_session
# ---------------------------------------------------------------------------


class TestLeaveSession:
    @pytest.mark.asyncio
    async def test_leave_removes_user(self, manager):
        _, collab = await _join(manager)
        removed = await manager.leave_session("doc-1", collab.client_id)

        assert removed is not None
        assert removed.user_id == "u1"
        # session should be cleaned up (empty)
        assert await manager.get_session("doc-1") is None

    @pytest.mark.asyncio
    async def test_leave_nonexistent_session(self, manager):
        result = await manager.leave_session("nope", "fake-client")
        assert result is None

    @pytest.mark.asyncio
    async def test_leave_nonexistent_client(self, manager):
        await _join(manager)
        result = await manager.leave_session("doc-1", "wrong-client-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_leave_cleans_user_sessions(self, manager):
        _, collab = await _join(manager)
        await manager.leave_session("doc-1", collab.client_id)

        sessions = await manager.get_user_sessions("u1")
        assert sessions == []

    @pytest.mark.asyncio
    async def test_leave_keeps_session_with_other_users(self, manager):
        _, c1 = await _join(manager, user_id="u1")
        _, c2 = await _join(manager, user_id="u2")

        await manager.leave_session("doc-1", c1.client_id)
        session = await manager.get_session("doc-1")
        assert session is not None
        assert len(session.users) == 1


# ---------------------------------------------------------------------------
# update_cursor
# ---------------------------------------------------------------------------


class TestUpdateCursor:
    @pytest.mark.asyncio
    async def test_update_cursor_success(self, manager):
        _, collab = await _join(manager)
        cursor = CursorPosition(x=10.0, y=20.0)
        result = await manager.update_cursor("doc-1", collab.client_id, cursor)

        assert result is True
        updated = await manager.get_collaborator("doc-1", collab.client_id)
        assert updated.cursor.x == 10.0

    @pytest.mark.asyncio
    async def test_update_cursor_no_session(self, manager):
        cursor = CursorPosition(x=0.0, y=0.0)
        assert await manager.update_cursor("nope", "fake", cursor) is False

    @pytest.mark.asyncio
    async def test_update_cursor_no_user(self, manager):
        await _join(manager)
        cursor = CursorPosition(x=0.0, y=0.0)
        assert await manager.update_cursor("doc-1", "wrong", cursor) is False


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_update_status(self, manager):
        _, collab = await _join(manager)
        result = await manager.update_status("doc-1", collab.client_id, PresenceStatus.IDLE)

        assert result is True
        updated = await manager.get_collaborator("doc-1", collab.client_id)
        assert updated.status == PresenceStatus.IDLE

    @pytest.mark.asyncio
    async def test_update_status_no_change_no_callback(self, manager):
        cb = MagicMock()
        manager.register_callback(cb)
        _, collab = await _join(manager)
        cb.reset_mock()

        # status is already ACTIVE
        await manager.update_status("doc-1", collab.client_id, PresenceStatus.ACTIVE)
        # callback called for no status_changed event (same status)
        status_calls = [c for c in cb.call_args_list if c[0][0] == "status_changed"]
        assert len(status_calls) == 0


# ---------------------------------------------------------------------------
# set_typing
# ---------------------------------------------------------------------------


class TestSetTyping:
    @pytest.mark.asyncio
    async def test_set_typing_true(self, manager):
        _, collab = await _join(manager)
        result = await manager.set_typing("doc-1", collab.client_id, True)
        assert result is True
        updated = await manager.get_collaborator("doc-1", collab.client_id)
        assert updated.status == PresenceStatus.TYPING

    @pytest.mark.asyncio
    async def test_set_typing_false(self, manager):
        _, collab = await _join(manager)
        await manager.set_typing("doc-1", collab.client_id, True)
        await manager.set_typing("doc-1", collab.client_id, False)
        updated = await manager.get_collaborator("doc-1", collab.client_id)
        assert updated.status == PresenceStatus.ACTIVE


# ---------------------------------------------------------------------------
# get helpers
# ---------------------------------------------------------------------------


class TestGetHelpers:
    @pytest.mark.asyncio
    async def test_get_active_users(self, manager):
        _, c1 = await _join(manager, user_id="u1")
        _, c2 = await _join(manager, user_id="u2")
        await manager.update_status("doc-1", c2.client_id, PresenceStatus.AWAY)

        active = await manager.get_active_users("doc-1")
        assert len(active) == 1

    @pytest.mark.asyncio
    async def test_get_active_users_empty_session(self, manager):
        assert await manager.get_active_users("nope") == []

    @pytest.mark.asyncio
    async def test_get_all_users(self, manager):
        await _join(manager, user_id="u1")
        await _join(manager, user_id="u2")
        users = await manager.get_all_users("doc-1")
        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_get_all_users_empty(self, manager):
        assert await manager.get_all_users("nope") == []

    @pytest.mark.asyncio
    async def test_get_collaborator_not_found(self, manager):
        assert await manager.get_collaborator("nope", "fake") is None


# ---------------------------------------------------------------------------
# callbacks
# ---------------------------------------------------------------------------


class TestCallbacks:
    @pytest.mark.asyncio
    async def test_sync_callback_called(self, manager):
        events = []
        manager.register_callback(lambda et, did, d: events.append((et, did)))
        await _join(manager)
        assert any(et == "user_joined" for et, _ in events)

    @pytest.mark.asyncio
    async def test_async_callback_called(self, manager):
        events = []

        async def cb(et, did, d):
            events.append(et)

        manager.register_callback(cb)
        await _join(manager)
        assert "user_joined" in events

    @pytest.mark.asyncio
    async def test_unregister_callback(self, manager):
        cb = MagicMock()
        manager.register_callback(cb)
        manager.unregister_callback(cb)
        await _join(manager)
        cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_error_does_not_propagate(self, manager):
        def bad_cb(et, did, d):
            raise RuntimeError("boom")

        manager.register_callback(bad_cb)
        # Should not raise
        await _join(manager)


# ---------------------------------------------------------------------------
# broadcast_to_session
# ---------------------------------------------------------------------------


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_counts_recipients(self, manager):
        _, c1 = await _join(manager, user_id="u1")
        _, c2 = await _join(manager, user_id="u2")

        count = await manager.broadcast_to_session("doc-1", "test", {"msg": "hi"})
        assert count == 2

    @pytest.mark.asyncio
    async def test_broadcast_excludes_client(self, manager):
        _, c1 = await _join(manager, user_id="u1")
        _, c2 = await _join(manager, user_id="u2")

        count = await manager.broadcast_to_session(
            "doc-1", "test", {"msg": "hi"}, exclude_client=c1.client_id
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_no_session(self, manager):
        count = await manager.broadcast_to_session("nope", "test", {})
        assert count == 0


# ---------------------------------------------------------------------------
# is_user_active
# ---------------------------------------------------------------------------


class TestIsUserActive:
    @pytest.mark.asyncio
    async def test_active_user(self, manager):
        await _join(manager)
        assert await manager.is_user_active("u1", "doc-1") is True

    @pytest.mark.asyncio
    async def test_away_user(self, manager):
        _, collab = await _join(manager)
        await manager.update_status("doc-1", collab.client_id, PresenceStatus.AWAY)
        assert await manager.is_user_active("u1", "doc-1") is False

    @pytest.mark.asyncio
    async def test_no_session(self, manager):
        assert await manager.is_user_active("u1", "nope") is False


# ---------------------------------------------------------------------------
# get_session_stats
# ---------------------------------------------------------------------------


class TestSessionStats:
    @pytest.mark.asyncio
    async def test_stats_for_session(self, manager):
        await _join(manager, user_id="u1")
        stats = await manager.get_session_stats("doc-1")

        assert stats["exists"] is True
        assert stats["total_users"] == 1
        assert "active" in stats["status_counts"]

    @pytest.mark.asyncio
    async def test_stats_no_session(self, manager):
        stats = await manager.get_session_stats("nope")
        assert stats["exists"] is False

    @pytest.mark.asyncio
    async def test_get_all_sessions(self, manager):
        await _join(manager, doc_id="d1", user_id="u1")
        await _join(manager, doc_id="d2", user_id="u2", tenant_id="t1")

        all_stats = await manager.get_all_sessions()
        assert len(all_stats) == 2


# ---------------------------------------------------------------------------
# _assign_color
# ---------------------------------------------------------------------------


class TestAssignColor:
    @pytest.mark.asyncio
    async def test_assigns_unique_colors(self, manager):
        _, c1 = await _join(manager, user_id="u1")
        _, c2 = await _join(manager, user_id="u2")
        assert c1.color != c2.color


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, manager):
        await manager.start()
        assert manager._cleanup_task is not None
        await manager.stop()
        assert manager._cleanup_task.cancelled() or manager._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_stop_without_start(self, manager):
        await manager.stop()  # should not raise


# ---------------------------------------------------------------------------
# _check_idle_users
# ---------------------------------------------------------------------------


class TestCheckIdleUsers:
    @pytest.mark.asyncio
    async def test_marks_idle_users(self, manager):
        config = CollaborationConfig(
            max_users_per_document=5,
            idle_timeout_seconds=1,
            away_timeout_seconds=3600,
        )
        mgr = PresenceManager(config=config)
        _, collab = await _join(mgr)

        # Manually set last_activity in the past
        session = await mgr.get_session("doc-1")
        session.users[collab.client_id].last_activity = datetime.now(UTC) - timedelta(seconds=5)

        await mgr._check_idle_users()

        updated = await mgr.get_collaborator("doc-1", collab.client_id)
        assert updated.status == PresenceStatus.IDLE

    @pytest.mark.asyncio
    async def test_marks_away_users(self, manager):
        config = CollaborationConfig(
            max_users_per_document=5,
            idle_timeout_seconds=1,
            away_timeout_seconds=2,
        )
        mgr = PresenceManager(config=config)
        _, collab = await _join(mgr)

        session = await mgr.get_session("doc-1")
        session.users[collab.client_id].last_activity = datetime.now(UTC) - timedelta(seconds=10)

        await mgr._check_idle_users()

        updated = await mgr.get_collaborator("doc-1", collab.client_id)
        assert updated.status == PresenceStatus.AWAY
