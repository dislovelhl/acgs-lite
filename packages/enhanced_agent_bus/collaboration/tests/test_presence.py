"""
Tests for Presence Manager.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from enhanced_agent_bus.collaboration.models import (
    CollaborationConfig,
    CursorPosition,
    PresenceStatus,
    SessionFullError,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.presence import PresenceManager


class TestPresenceManager:
    """Test Presence Manager."""

    @pytest.fixture
    def presence_manager(self):
        config = CollaborationConfig(
            idle_timeout_seconds=1,
            away_timeout_seconds=2,
        )
        return PresenceManager(config)

    async def test_join_session(self, presence_manager):
        session, collaborator = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        assert session.document_id == "doc-123"
        assert collaborator.user_id == "user-1"
        assert collaborator.name == "Test User"
        assert collaborator.tenant_id == "tenant-1"
        assert collaborator.color is not None

    async def test_join_session_max_users(self, presence_manager):
        presence_manager.config.max_users_per_document = 2

        # Add users up to capacity
        for i in range(2):
            await presence_manager.join_session(
                document_id="doc-full",
                document_type="policy",
                user_id=f"user-{i}",
                user_info={"name": f"User {i}"},
                tenant_id="tenant-1",
            )

        # Try to add one more
        with pytest.raises(SessionFullError):
            await presence_manager.join_session(
                document_id="doc-full",
                document_type="policy",
                user_id="user-extra",
                user_info={"name": "Extra User"},
                tenant_id="tenant-1",
            )

    async def test_tenant_isolation(self, presence_manager):
        await presence_manager.join_session(
            document_id="doc-tenant",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "User 1"},
            tenant_id="tenant-1",
        )

        # Try to join from different tenant
        with pytest.raises(PermissionError):
            await presence_manager.join_session(
                document_id="doc-tenant",
                document_type="policy",
                user_id="user-2",
                user_info={"name": "User 2"},
                tenant_id="tenant-2",
            )

    async def test_leave_session(self, presence_manager):
        session, collaborator = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        left = await presence_manager.leave_session("doc-123", collaborator.client_id)

        assert left is not None
        assert left.user_id == "user-1"

        # Session should be empty and removed
        session = await presence_manager.get_session("doc-123")
        assert session is None

    async def test_update_cursor(self, presence_manager):
        _, collaborator = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        cursor = CursorPosition(x=100, y=200, line=5)
        success = await presence_manager.update_cursor("doc-123", collaborator.client_id, cursor)

        assert success is True

        # Verify cursor was updated
        updated = await presence_manager.get_collaborator("doc-123", collaborator.client_id)
        assert updated.cursor.x == 100
        assert updated.cursor.y == 200
        assert updated.cursor.line == 5

    async def test_update_status(self, presence_manager):
        _, collaborator = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        success = await presence_manager.update_status(
            "doc-123", collaborator.client_id, PresenceStatus.TYPING
        )

        assert success is True

        updated = await presence_manager.get_collaborator("doc-123", collaborator.client_id)
        assert updated.status == PresenceStatus.TYPING

    async def test_set_typing(self, presence_manager):
        _, collaborator = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        await presence_manager.set_typing("doc-123", collaborator.client_id, True)

        updated = await presence_manager.get_collaborator("doc-123", collaborator.client_id)
        assert updated.status == PresenceStatus.TYPING

        await presence_manager.set_typing("doc-123", collaborator.client_id, False)

        updated = await presence_manager.get_collaborator("doc-123", collaborator.client_id)
        assert updated.status == PresenceStatus.ACTIVE

    async def test_get_active_users(self, presence_manager):
        # Add active user
        _, _active_user = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Active User"},
            tenant_id="tenant-1",
        )

        # Add away user
        _, away_user = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-2",
            user_info={"name": "Away User"},
            tenant_id="tenant-1",
        )
        await presence_manager.update_status("doc-123", away_user.client_id, PresenceStatus.AWAY)

        active_users = await presence_manager.get_active_users("doc-123")
        assert len(active_users) == 1
        assert active_users[0].user_id == "user-1"

    async def test_get_user_sessions(self, presence_manager):
        _, _collaborator = await presence_manager.join_session(
            document_id="doc-1",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        await presence_manager.join_session(
            document_id="doc-2",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        sessions = await presence_manager.get_user_sessions("user-1")
        assert len(sessions) == 2
        assert "doc-1" in sessions
        assert "doc-2" in sessions

    async def test_color_assignment(self, presence_manager):
        colors = set()

        for i in range(5):
            _, collaborator = await presence_manager.join_session(
                document_id="doc-colors",
                document_type="policy",
                user_id=f"user-{i}",
                user_info={"name": f"User {i}"},
                tenant_id="tenant-1",
            )
            colors.add(collaborator.color)

        # Should have different colors
        assert len(colors) == 5

    async def test_callback_registration(self, presence_manager):
        events = []

        def callback(event_type, document_id, data):
            events.append((event_type, document_id, data))

        presence_manager.register_callback(callback)

        _, _collaborator = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        assert len(events) == 1
        assert events[0][0] == "user_joined"

        presence_manager.unregister_callback(callback)


class TestPresenceManagerCleanup:
    """Test presence manager cleanup."""

    @pytest.fixture
    def presence_manager(self):
        config = CollaborationConfig(
            idle_timeout_seconds=1,
            away_timeout_seconds=2,
        )
        return PresenceManager(config)

    async def test_idle_user_marked_idle(self):
        config = CollaborationConfig(
            idle_timeout_seconds=0,  # Immediate
            away_timeout_seconds=10,
        )
        manager = PresenceManager(config)

        _, collaborator = await manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        # Manually set last activity to past
        collaborator.last_activity = datetime.now(UTC) - timedelta(seconds=5)

        # Check idle users
        await manager._check_idle_users()

        updated = await manager.get_collaborator("doc-123", collaborator.client_id)
        assert updated.status == PresenceStatus.IDLE

    async def test_away_user_marked_away(self):
        config = CollaborationConfig(
            idle_timeout_seconds=1,
            away_timeout_seconds=0,  # Immediate
        )
        manager = PresenceManager(config)

        _, collaborator = await manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        # Manually set last activity to past
        collaborator.last_activity = datetime.now(UTC) - timedelta(seconds=5)

        # Check idle users
        await manager._check_idle_users()

        updated = await manager.get_collaborator("doc-123", collaborator.client_id)
        assert updated.status == PresenceStatus.AWAY

    async def test_session_stats(self, presence_manager):
        await presence_manager.join_session(
            document_id="doc-stats",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "User 1"},
            tenant_id="tenant-1",
        )

        _, user2 = await presence_manager.join_session(
            document_id="doc-stats",
            document_type="policy",
            user_id="user-2",
            user_info={"name": "User 2"},
            tenant_id="tenant-1",
        )

        await presence_manager.update_status("doc-stats", user2.client_id, PresenceStatus.TYPING)

        stats = await presence_manager.get_session_stats("doc-stats")

        assert stats["exists"] is True
        assert stats["total_users"] == 2
        assert stats["status_counts"]["active"] == 1
        assert stats["status_counts"]["typing"] == 1

    async def test_is_user_active(self, presence_manager):
        _, collaborator = await presence_manager.join_session(
            document_id="doc-123",
            document_type="policy",
            user_id="user-1",
            user_info={"name": "Test User"},
            tenant_id="tenant-1",
        )

        assert await presence_manager.is_user_active("user-1", "doc-123") is True

        await presence_manager.update_status("doc-123", collaborator.client_id, PresenceStatus.AWAY)

        assert await presence_manager.is_user_active("user-1", "doc-123") is False
