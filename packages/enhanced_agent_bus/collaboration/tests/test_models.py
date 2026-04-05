"""
Tests for Collaboration Models.

Constitutional Hash: 608508a9bd224290
"""

from datetime import datetime, timezone

import pytest

from enhanced_agent_bus.collaboration.models import (
    CollaborationConfig,
    CollaborationSession,
    Collaborator,
    Comment,
    CommentReply,
    CursorPosition,
    DocumentType,
    EditOperation,
    EditOperationType,
    PermissionDeniedError,
    PresenceStatus,
    SessionFullError,
    UserPermissions,
)


class TestCursorPosition:
    """Test CursorPosition model."""

    def test_create_cursor_position(self):
        cursor = CursorPosition(x=100, y=200, line=5, column=10)
        assert cursor.x == 100
        assert cursor.y == 200
        assert cursor.line == 5
        assert cursor.column == 10

    def test_cursor_position_optional_fields(self):
        cursor = CursorPosition(x=50, y=75)
        assert cursor.line is None
        assert cursor.column is None
        assert cursor.selection_start is None
        assert cursor.selection_end is None

    def test_cursor_position_with_selection(self):
        cursor = CursorPosition(x=0, y=0, selection_start=10, selection_end=25)
        assert cursor.selection_start == 10
        assert cursor.selection_end == 25


class TestCollaborator:
    """Test Collaborator model."""

    def test_create_collaborator(self):
        collaborator = Collaborator(
            user_id="user-123",
            name="Test User",
            email="test@example.com",
            color="#FF6B6B",
            tenant_id="tenant-1",
        )
        assert collaborator.user_id == "user-123"
        assert collaborator.name == "Test User"
        assert collaborator.color == "#FF6B6B"
        assert collaborator.status == PresenceStatus.ACTIVE
        assert collaborator.permissions == UserPermissions.READ

    def test_collaborator_default_values(self):
        collaborator = Collaborator(
            user_id="user-456",
            name="Anonymous",
            color="#4ECDC4",
            tenant_id="tenant-1",
        )
        assert collaborator.status == PresenceStatus.ACTIVE
        assert collaborator.permissions == UserPermissions.READ
        assert collaborator.is_anonymous is False
        assert collaborator.client_id is not None

    def test_collaborator_to_dict(self):
        collaborator = Collaborator(
            user_id="user-789",
            name="Test",
            color="#45B7D1",
            tenant_id="tenant-1",
            status=PresenceStatus.TYPING,
        )
        data = collaborator.to_dict()
        assert data["user_id"] == "user-789"
        assert data["name"] == "Test"
        assert data["status"] == "typing"
        assert "client_id" in data

    def test_invalid_color_raises_error(self):
        with pytest.raises(ValueError, match="valid hex color"):
            Collaborator(
                user_id="user-123",
                name="Test",
                color="not-a-color",
                tenant_id="tenant-1",
            )


class TestCollaborationSession:
    """Test CollaborationSession model."""

    def test_create_session(self):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )
        assert session.document_id == "doc-123"
        assert session.document_type == DocumentType.POLICY
        assert session.version == 0
        assert session.is_locked is False

    def test_session_can_join(self):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
            max_users=3,
        )
        assert session.can_join() is True

        # Add users up to capacity
        for i in range(3):
            session.users[f"client-{i}"] = Collaborator(
                user_id=f"user-{i}",
                name=f"User {i}",
                color="#FF6B6B",
                tenant_id="tenant-1",
            )

        assert session.can_join() is False

    def test_session_locked_cannot_join(self):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
            is_locked=True,
            locked_by="admin",
        )
        assert session.can_join() is False

    def test_get_active_users(self):
        session = CollaborationSession(
            document_id="doc-123",
            document_type=DocumentType.POLICY,
            tenant_id="tenant-1",
        )

        # Add active user
        active = Collaborator(
            user_id="user-1",
            name="Active",
            color="#FF6B6B",
            tenant_id="tenant-1",
            status=PresenceStatus.ACTIVE,
        )
        session.users["client-1"] = active

        # Add away user
        away = Collaborator(
            user_id="user-2",
            name="Away",
            color="#4ECDC4",
            tenant_id="tenant-1",
            status=PresenceStatus.AWAY,
        )
        session.users["client-2"] = away

        active_users = session.get_active_users()
        assert len(active_users) == 1
        assert active_users[0].user_id == "user-1"


class TestEditOperation:
    """Test EditOperation model."""

    def test_create_operation(self):
        op = EditOperation(
            type=EditOperationType.REPLACE,
            path="/title",
            value="New Title",
            old_value="Old Title",
            user_id="user-123",
            client_id="client-456",
            version=5,
        )
        assert op.type == EditOperationType.REPLACE
        assert op.path == "/title"
        assert op.value == "New Title"
        assert op.version == 5

    def test_operation_to_dict(self):
        op = EditOperation(
            type=EditOperationType.INSERT,
            path="/items",
            value="new item",
            position=3,
            user_id="user-123",
            client_id="client-456",
            version=10,
        )
        data = op.to_dict()
        assert data["type"] == "insert"
        assert data["path"] == "/items"
        assert data["position"] == 3
        assert data["version"] == 10
        assert "operation_id" in data
        assert "timestamp" in data


class TestComment:
    """Test Comment model."""

    def test_create_comment(self):
        comment = Comment(
            user_id="user-123",
            user_name="Test User",
            text="This is a comment",
        )
        assert comment.user_id == "user-123"
        assert comment.text == "This is a comment"
        assert comment.resolved is False
        assert len(comment.replies) == 0

    def test_resolve_comment(self):
        comment = Comment(
            user_id="user-123",
            user_name="Test User",
            text="Comment to resolve",
        )
        comment.resolve("user-456")
        assert comment.resolved is True
        assert comment.resolved_by == "user-456"
        assert comment.resolved_at is not None

    def test_add_reply(self):
        comment = Comment(
            user_id="user-123",
            user_name="Test User",
            text="Original comment",
        )
        reply = CommentReply(
            user_id="user-456",
            user_name="Replier",
            text="This is a reply",
        )
        comment.add_reply(reply)
        assert len(comment.replies) == 1
        assert comment.replies[0].text == "This is a reply"


class TestCollaborationConfig:
    """Test CollaborationConfig model."""

    def test_default_config(self):
        config = CollaborationConfig()
        assert config.max_users_per_document == 50
        assert config.cursor_sync_interval_ms == 50
        assert config.enable_chat is True
        assert config.enable_comments is True

    def test_custom_config(self):
        config = CollaborationConfig(
            max_users_per_document=10,
            cursor_sync_interval_ms=100,
            enable_chat=False,
        )
        assert config.max_users_per_document == 10
        assert config.cursor_sync_interval_ms == 100
        assert config.enable_chat is False
        assert config.enable_comments is True  # Default


class TestExceptions:
    """Test collaboration exceptions."""

    def test_permission_denied_error(self):
        error = PermissionDeniedError("Custom message")
        assert error.message == "Custom message"
        assert error.code == "PERMISSION_DENIED"
        assert str(error) == "Custom message"

    def test_session_full_error(self):
        error = SessionFullError()
        assert error.message == "Session is full"
        assert error.code == "SESSION_FULL"
