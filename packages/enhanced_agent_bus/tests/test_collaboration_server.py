"""
Tests for enhanced_agent_bus.collaboration.server module.

Covers: CollaborationServer, RateLimiter, handler methods, lifecycle.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.collaboration.models import (
    ActivityEventType,
    CollaborationConfig,
    CollaborationSession,
    CollaborationValidationError,
    Collaborator,
    ConflictError,
    CursorPosition,
    DocumentType,
    EditOperation,
    EditOperationType,
    PermissionDeniedError,
    SessionFullError,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.server import (
    CollaborationServer,
    RateLimiter,
)

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_collaborator(**overrides) -> Collaborator:
    defaults = {
        "user_id": "user-1",
        "name": "Alice",
        "email": "alice@test.com",
        "avatar": "https://avatar.test/alice.png",
        "color": "#FF5733",
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "permissions": UserPermissions.WRITE,
    }
    defaults.update(overrides)
    return Collaborator(**defaults)


def _make_session(**overrides) -> CollaborationSession:
    defaults = {
        "document_id": "doc-1",
        "document_type": DocumentType.POLICY,
        "tenant_id": "tenant-1",
        "version": 5,
    }
    defaults.update(overrides)
    return CollaborationSession(**defaults)


def _make_sio_mock() -> MagicMock:
    """Create a mock that satisfies SocketServerProtocol."""
    sio = MagicMock()
    sio.save_session = AsyncMock()
    sio.get_session = AsyncMock(return_value=None)
    sio.leave_room = AsyncMock()
    sio.enter_room = AsyncMock()
    sio.emit = AsyncMock()
    # .event is used as a decorator; return the function unchanged
    sio.event = lambda fn: fn
    return sio


def _auth_validator_ok(token: str):
    if token == "valid-token":
        return {
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "permissions": ["read", "write"],
        }
    return None


@pytest.fixture()
def config() -> CollaborationConfig:
    return CollaborationConfig()


@pytest.fixture()
def audit_client() -> AsyncMock:
    client = AsyncMock()
    client.log_event = AsyncMock()
    return client


@pytest.fixture()
def server(config, audit_client) -> CollaborationServer:
    srv = CollaborationServer(
        config=config,
        audit_client=audit_client,
        auth_validator=_auth_validator_ok,
    )
    srv.sio = _make_sio_mock()
    srv._started = True
    return srv


# ===========================================================================
# RateLimiter
# ===========================================================================


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_is_allowed_within_limit(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        assert await rl.is_allowed("client-a") is True

    @pytest.mark.asyncio
    async def test_get_remaining_decreases(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        initial = await rl.get_remaining("client-b")
        assert initial == 3
        await rl.is_allowed("client-b")
        remaining = await rl.get_remaining("client-b")
        assert remaining == 2

    @pytest.mark.asyncio
    async def test_reset_prefix_clears_keys(self):
        rl = RateLimiter(max_requests=10, window_seconds=60)
        await rl.is_allowed("sid-123")
        await rl.is_allowed("sid-123:edit")
        await rl.reset_prefix("sid-123")
        # After reset, remaining should be back to max
        assert await rl.get_remaining("sid-123") == 10
        assert await rl.get_remaining("sid-123:edit") == 10

    @pytest.mark.asyncio
    async def test_reset_prefix_no_match(self):
        rl = RateLimiter(max_requests=10, window_seconds=60)
        await rl.is_allowed("other-key")
        # Should not fail when prefix doesn't match any keys
        await rl.reset_prefix("nonexistent")
        assert await rl.get_remaining("other-key") == 9


# ===========================================================================
# CollaborationServer — Construction & Lifecycle
# ===========================================================================


class TestServerLifecycle:
    def test_default_construction(self):
        srv = CollaborationServer()
        assert srv.config is not None
        assert srv.sio is None
        assert srv._started is False

    def test_construction_with_config(self, config, audit_client):
        srv = CollaborationServer(
            config=config,
            audit_client=audit_client,
            auth_validator=_auth_validator_ok,
        )
        assert srv.config is config
        assert srv.audit_client is audit_client

    @pytest.mark.asyncio
    async def test_shutdown_when_started(self, server):
        server._started = True
        server.presence = AsyncMock()
        server.presence.stop = AsyncMock()
        await server.shutdown()
        server.presence.stop.assert_awaited_once()
        assert server._started is False

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started(self, server):
        server._started = False
        server.presence = AsyncMock()
        await server.shutdown()
        server.presence.stop.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_health_check_started(self, server):
        server._started = True
        server.presence._sessions = {"doc-1": "s"}
        result = await server.health_check()
        assert result["status"] == "healthy"
        assert result["active_sessions"] == 1

    @pytest.mark.asyncio
    async def test_health_check_not_started(self, server):
        server._started = False
        result = await server.health_check()
        assert result["status"] == "not_started"

    def test_get_asgi_app_not_initialized(self):
        srv = CollaborationServer()
        with pytest.raises(RuntimeError, match="not initialized"):
            srv.get_asgi_app()


# ===========================================================================
# Document Handlers — join / leave
# ===========================================================================


class TestJoinDocument:
    @pytest.mark.asyncio
    async def test_join_rate_limited(self, server):
        server.rate_limiter.is_allowed = AsyncMock(return_value=False)
        result = await server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "RATE_LIMITED"

    @pytest.mark.asyncio
    async def test_join_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "NO_SESSION"

    @pytest.mark.asyncio
    async def test_join_missing_doc_id(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": "t1"})
        result = await server._handle_join_document("sid-1", {})
        assert result["code"] == "MISSING_DOC_ID"

    @pytest.mark.asyncio
    async def test_join_missing_tenant(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": None})
        result = await server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "MISSING_TENANT"

    @pytest.mark.asyncio
    async def test_join_session_full(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": "t1"})
        server.presence.join_session = AsyncMock(side_effect=SessionFullError("Session is full"))
        server.permissions.get_document_permissions = MagicMock(return_value={})
        result = await server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "SESSION_FULL"

    @pytest.mark.asyncio
    async def test_join_success(self, server, audit_client):
        collaborator = _make_collaborator()
        collab_session = _make_session()

        server.sio.get_session = AsyncMock(
            return_value={"user_id": "user-1", "tenant_id": "tenant-1"}
        )
        server.presence.join_session = AsyncMock(return_value=(collab_session, collaborator))
        server.presence.get_all_users = AsyncMock(return_value=[collaborator])
        server.sync.get_document = AsyncMock(return_value={"title": "Test"})
        server.permissions.get_document_permissions = MagicMock(return_value={})

        result = await server._handle_join_document(
            "sid-1",
            {"document_id": "doc-1", "name": "Alice"},
        )

        assert result["success"] is True
        assert result["client_id"] == collaborator.client_id
        assert result["version"] == collab_session.version
        server.sio.enter_room.assert_awaited_once_with("sid-1", "doc-1")
        server.sio.emit.assert_awaited()  # user-joined broadcast
        audit_client.log_event.assert_awaited()

    @pytest.mark.asyncio
    async def test_join_internal_error_caught(self, server):
        """Unexpected errors in handler return INTERNAL_ERROR, not raise."""
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": "t1"})
        server.permissions.get_document_permissions = MagicMock(side_effect=KeyError("boom"))
        result = await server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "INTERNAL_ERROR"


class TestLeaveDocument:
    @pytest.mark.asyncio
    async def test_leave_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_leave_document("sid-1")
        assert result == {"success": False}

    @pytest.mark.asyncio
    async def test_leave_not_in_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1"})
        result = await server._handle_leave_document("sid-1")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_leave_broadcasts_user_left(self, server):
        collaborator = _make_collaborator()
        server.sio.get_session = AsyncMock(
            return_value={
                "user_id": "user-1",
                "document_id": "doc-1",
                "client_id": "client-1",
            }
        )
        server.presence.leave_session = AsyncMock(return_value=collaborator)

        result = await server._handle_leave_document("sid-1")
        assert result["success"] is True
        server.sio.leave_room.assert_awaited_once_with("sid-1", "doc-1")
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "user-left"

    @pytest.mark.asyncio
    async def test_leave_no_collaborator_found(self, server):
        """When leave_session returns None, no broadcast."""
        server.sio.get_session = AsyncMock(
            return_value={
                "user_id": "user-1",
                "document_id": "doc-1",
                "client_id": "client-1",
            }
        )
        server.presence.leave_session = AsyncMock(return_value=None)

        result = await server._handle_leave_document("sid-1")
        assert result["success"] is True
        server.sio.emit.assert_not_awaited()


# ===========================================================================
# Cursor / Edit handlers
# ===========================================================================


class TestCursorMove:
    @pytest.mark.asyncio
    async def test_cursor_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_cursor_move("sid-1", {"cursor": {"x": 10, "y": 20}})
        assert result == {"error": "No session"}

    @pytest.mark.asyncio
    async def test_cursor_not_in_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1"})
        result = await server._handle_cursor_move("sid-1", {"cursor": {"x": 10, "y": 20}})
        assert result == {"error": "Not in document"}

    @pytest.mark.asyncio
    async def test_cursor_success(self, server):
        server.sio.get_session = AsyncMock(
            return_value={
                "user_id": "u1",
                "document_id": "doc-1",
                "client_id": "client-1",
            }
        )
        server.presence.update_cursor = AsyncMock(return_value=True)
        collaborator = _make_collaborator()
        server.presence.get_collaborator = AsyncMock(return_value=collaborator)

        result = await server._handle_cursor_move(
            "sid-1",
            {"cursor": {"x": 10, "y": 20, "line": 5, "column": 3}},
        )
        assert result["success"] is True
        server.sio.emit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cursor_update_fails(self, server):
        server.sio.get_session = AsyncMock(
            return_value={
                "user_id": "u1",
                "document_id": "doc-1",
                "client_id": "client-1",
            }
        )
        server.presence.update_cursor = AsyncMock(return_value=False)

        result = await server._handle_cursor_move("sid-1", {"cursor": {"x": 0, "y": 0}})
        assert result["success"] is False
        server.sio.emit.assert_not_awaited()


class TestEditOperation:
    def _session_data(self):
        return {
            "user_id": "user-1",
            "document_id": "doc-1",
            "client_id": "client-1",
        }

    @pytest.mark.asyncio
    async def test_edit_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_edit_operation("sid-1", {})
        assert result["code"] == "NO_SESSION"

    @pytest.mark.asyncio
    async def test_edit_not_in_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1"})
        result = await server._handle_edit_operation("sid-1", {})
        assert result["code"] == "NOT_IN_DOCUMENT"

    @pytest.mark.asyncio
    async def test_edit_rate_limited(self, server):
        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.rate_limiter.is_allowed = AsyncMock(return_value=False)
        result = await server._handle_edit_operation("sid-1", {})
        assert result["code"] == "RATE_LIMITED"

    @pytest.mark.asyncio
    async def test_edit_permission_denied(self, server):
        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock(
            side_effect=PermissionDeniedError("No write access")
        )
        result = await server._handle_edit_operation("sid-1", {})
        assert result["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_edit_session_not_found(self, server):
        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock()
        server.presence.get_session = AsyncMock(return_value=None)
        result = await server._handle_edit_operation("sid-1", {})
        assert result["code"] == "SESSION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_edit_document_locked(self, server):
        collab_session = _make_session(is_locked=True, locked_by="other-user")
        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock()
        server.presence.get_session = AsyncMock(return_value=collab_session)
        result = await server._handle_edit_operation("sid-1", {})
        assert result["code"] == "DOCUMENT_LOCKED"
        assert result["locked_by"] == "other-user"

    @pytest.mark.asyncio
    async def test_edit_locked_by_same_user_allowed(self, server, audit_client):
        """User who locked the document can still edit."""
        collab_session = _make_session(is_locked=True, locked_by="user-1")
        applied_op = SimpleNamespace(
            operation_id="op-1",
            to_dict=lambda: {"operation_id": "op-1"},
        )

        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock()
        server.presence.get_session = AsyncMock(return_value=collab_session)
        server.permissions.validate_operation = AsyncMock()
        server.sync.apply_operation = AsyncMock(return_value=applied_op)

        result = await server._handle_edit_operation(
            "sid-1",
            {"type": "replace", "path": "/title", "value": "New"},
        )
        assert result["success"] is True
        assert result["operation_id"] == "op-1"

    @pytest.mark.asyncio
    async def test_edit_validation_failed(self, server):
        collab_session = _make_session()
        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock()
        server.presence.get_session = AsyncMock(return_value=collab_session)
        server.permissions.validate_operation = AsyncMock(
            side_effect=CollaborationValidationError("Invalid op")
        )
        result = await server._handle_edit_operation(
            "sid-1",
            {"type": "replace", "path": "/x"},
        )
        assert result["code"] == "VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_edit_conflict_error(self, server):
        collab_session = _make_session()
        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock()
        server.presence.get_session = AsyncMock(return_value=collab_session)
        server.permissions.validate_operation = AsyncMock()
        server.sync.apply_operation = AsyncMock(side_effect=ConflictError("Version mismatch"))
        result = await server._handle_edit_operation(
            "sid-1",
            {"type": "replace", "path": "/x"},
        )
        assert result["code"] == "CONFLICT"

    @pytest.mark.asyncio
    async def test_edit_success_broadcasts(self, server, audit_client):
        collab_session = _make_session()
        applied_op = SimpleNamespace(
            operation_id="op-42",
            to_dict=lambda: {"operation_id": "op-42"},
        )

        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock()
        server.presence.get_session = AsyncMock(return_value=collab_session)
        server.permissions.validate_operation = AsyncMock()
        server.sync.apply_operation = AsyncMock(return_value=applied_op)

        result = await server._handle_edit_operation(
            "sid-1",
            {"type": "replace", "path": "/title", "value": "Updated"},
        )

        assert result["success"] is True
        assert result["operation_id"] == "op-42"
        # Broadcast should have been sent
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "document-update"
        assert call_args[1]["skip_sid"] == "sid-1"
        # Audit logged
        audit_client.log_event.assert_awaited()

    @pytest.mark.asyncio
    async def test_edit_internal_error(self, server):
        server.sio.get_session = AsyncMock(return_value=self._session_data())
        server.permissions.require_edit_permission = AsyncMock()
        server.presence.get_session = AsyncMock(side_effect=RuntimeError("unexpected"))
        result = await server._handle_edit_operation("sid-1", {"type": "replace", "path": "/x"})
        assert result["code"] == "INTERNAL_ERROR"


# ===========================================================================
# Social handlers — chat, typing, comments, presence
# ===========================================================================


class TestChatMessage:
    @pytest.mark.asyncio
    async def test_chat_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_chat_message("sid-1", {"text": "hi"})
        assert result == {"error": "No session"}

    @pytest.mark.asyncio
    async def test_chat_not_in_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1"})
        result = await server._handle_chat_message("sid-1", {"text": "hi"})
        assert result == {"error": "Not in document"}

    @pytest.mark.asyncio
    async def test_chat_disabled(self, server):
        server.config.enable_chat = False
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        result = await server._handle_chat_message("sid-1", {"text": "hi"})
        assert result == {"error": "Chat disabled"}

    @pytest.mark.asyncio
    async def test_chat_success(self, server):
        collaborator = _make_collaborator()
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        server.presence.get_collaborator = AsyncMock(return_value=collaborator)

        result = await server._handle_chat_message("sid-1", {"text": "hello world"})
        assert result["success"] is True
        assert "message_id" in result
        server.sio.emit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_no_collaborator(self, server):
        """When collaborator lookup returns None, name falls back to Unknown."""
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        server.presence.get_collaborator = AsyncMock(return_value=None)

        result = await server._handle_chat_message("sid-1", {"text": "hello"})
        assert result["success"] is True
        emit_data = server.sio.emit.call_args[0][1]
        assert emit_data["user_name"] == "Unknown"


class TestTypingIndicator:
    @pytest.mark.asyncio
    async def test_typing_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_typing_indicator("sid-1", {"is_typing": True})
        assert result == {"error": "No session"}

    @pytest.mark.asyncio
    async def test_typing_not_in_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1"})
        result = await server._handle_typing_indicator("sid-1", {"is_typing": True})
        assert result == {"error": "Not in document"}

    @pytest.mark.asyncio
    async def test_typing_success(self, server):
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        server.presence.set_typing = AsyncMock(return_value=True)
        collaborator = _make_collaborator()
        server.presence.get_collaborator = AsyncMock(return_value=collaborator)

        result = await server._handle_typing_indicator("sid-1", {"is_typing": True})
        assert result["success"] is True
        server.sio.emit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_typing_set_fails(self, server):
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        server.presence.set_typing = AsyncMock(return_value=False)

        result = await server._handle_typing_indicator("sid-1", {"is_typing": False})
        assert result["success"] is False
        server.sio.emit.assert_not_awaited()


class TestAddComment:
    @pytest.mark.asyncio
    async def test_comment_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_add_comment("sid-1", {"text": "Note"})
        assert result == {"error": "No session"}

    @pytest.mark.asyncio
    async def test_comment_not_in_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1"})
        result = await server._handle_add_comment("sid-1", {"text": "Note"})
        assert result == {"error": "Not in document"}

    @pytest.mark.asyncio
    async def test_comment_disabled(self, server):
        server.config.enable_comments = False
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        result = await server._handle_add_comment("sid-1", {"text": "Note"})
        assert result == {"error": "Comments disabled"}

    @pytest.mark.asyncio
    async def test_comment_success(self, server, audit_client):
        collaborator = _make_collaborator()
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        server.presence.get_collaborator = AsyncMock(return_value=collaborator)

        result = await server._handle_add_comment(
            "sid-1",
            {
                "text": "Important note",
                "position": {"x": 10, "y": 20, "line": 5, "column": 3},
                "mentions": ["user-2"],
            },
        )

        assert result["success"] is True
        assert "comment_id" in result
        server.sio.emit.assert_awaited_once()
        audit_client.log_event.assert_awaited()

    @pytest.mark.asyncio
    async def test_comment_without_position(self, server):
        collaborator = _make_collaborator()
        server.sio.get_session = AsyncMock(
            return_value={"user_id": "u1", "document_id": "doc-1", "client_id": "c1"}
        )
        server.presence.get_collaborator = AsyncMock(return_value=collaborator)

        result = await server._handle_add_comment("sid-1", {"text": "General comment"})
        assert result["success"] is True


class TestGetPresence:
    @pytest.mark.asyncio
    async def test_presence_no_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        result = await server._handle_get_presence("sid-1")
        assert result == {"error": "No session"}

    @pytest.mark.asyncio
    async def test_presence_not_in_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1"})
        result = await server._handle_get_presence("sid-1")
        assert result == {"error": "Not in document"}

    @pytest.mark.asyncio
    async def test_presence_success(self, server):
        collaborator = _make_collaborator()
        server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "document_id": "doc-1"})
        server.presence.get_all_users = AsyncMock(return_value=[collaborator])

        result = await server._handle_get_presence("sid-1")
        assert len(result["users"]) == 1
        assert result["users"][0]["user_id"] == "user-1"


# ===========================================================================
# Internal helper methods
# ===========================================================================


class TestHelperMethods:
    def test_create_cursor_position(self, server):
        cursor = server._create_cursor_position(
            {"x": 1.5, "y": 2.5, "line": 10, "column": 5, "node_id": "n1"}
        )
        assert isinstance(cursor, CursorPosition)
        assert cursor.x == 1.5
        assert cursor.line == 10
        assert cursor.node_id == "n1"

    def test_create_cursor_position_defaults(self, server):
        cursor = server._create_cursor_position({})
        assert cursor.x == 0
        assert cursor.y == 0
        assert cursor.line is None

    def test_check_document_lock_not_locked(self, server):
        session = _make_session(is_locked=False)
        assert server._check_document_lock(session, "any-user") is None

    def test_check_document_lock_locked_by_other(self, server):
        session = _make_session(is_locked=True, locked_by="other")
        result = server._check_document_lock(session, "user-1")
        assert result["code"] == "DOCUMENT_LOCKED"

    def test_check_document_lock_locked_by_self(self, server):
        session = _make_session(is_locked=True, locked_by="user-1")
        assert server._check_document_lock(session, "user-1") is None

    def test_create_edit_operation(self, server):
        session = _make_session(version=7)
        op = server._create_edit_operation(
            {"type": "insert", "path": "/items", "value": "new", "position": 3},
            "user-1",
            "client-1",
            session,
        )
        assert isinstance(op, EditOperation)
        assert op.type == EditOperationType.INSERT
        assert op.path == "/items"
        assert op.user_id == "user-1"
        assert op.version == 7  # from session

    @pytest.mark.asyncio
    async def test_check_edit_rate_limit_allowed(self, server):
        server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        assert await server._check_edit_rate_limit("sid-1") is None

    @pytest.mark.asyncio
    async def test_check_edit_rate_limit_denied(self, server):
        server.rate_limiter.is_allowed = AsyncMock(return_value=False)
        result = await server._check_edit_rate_limit("sid-1")
        assert result["code"] == "RATE_LIMITED"

    @pytest.mark.asyncio
    async def test_check_edit_permissions_allowed(self, server):
        server.permissions.require_edit_permission = AsyncMock()
        assert await server._check_edit_permissions("u1", "doc-1") is None

    @pytest.mark.asyncio
    async def test_check_edit_permissions_denied(self, server):
        server.permissions.require_edit_permission = AsyncMock(
            side_effect=PermissionDeniedError("No")
        )
        result = await server._check_edit_permissions("u1", "doc-1")
        assert result["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_validate_edit_operation_ok(self, server):
        server.permissions.validate_operation = AsyncMock()
        op = EditOperation(type="replace", path="/x", user_id="u1", client_id="c1", version=1)
        assert await server._validate_edit_operation("u1", "doc-1", op, {}) is None

    @pytest.mark.asyncio
    async def test_validate_edit_operation_denied(self, server):
        server.permissions.validate_operation = AsyncMock(side_effect=PermissionDeniedError("Nope"))
        op = EditOperation(type="replace", path="/x", user_id="u1", client_id="c1", version=1)
        result = await server._validate_edit_operation("u1", "doc-1", op, {})
        assert result["code"] == "VALIDATION_FAILED"


# ===========================================================================
# Activity logging
# ===========================================================================


class TestActivityLogging:
    @pytest.mark.asyncio
    async def test_log_activity_with_audit_client(self, server, audit_client):
        await server._log_activity(
            ActivityEventType.USER_JOINED,
            "user-1",
            "doc-1",
            {"extra": "data"},
        )
        audit_client.log_event.assert_awaited_once()
        call_kwargs = audit_client.log_event.call_args[1]
        assert call_kwargs["event_type"] == "collaboration.user_joined"
        assert call_kwargs["details"]["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_log_activity_no_audit_client(self, server):
        server.audit_client = None
        # Should not raise
        await server._log_activity(ActivityEventType.DOCUMENT_EDITED, "u1", "d1", {})

    @pytest.mark.asyncio
    async def test_log_activity_error_swallowed(self, server, audit_client):
        audit_client.log_event = AsyncMock(side_effect=RuntimeError("audit down"))
        # Should not raise
        await server._log_activity(ActivityEventType.COMMENT_ADDED, "u1", "d1", {})


# ===========================================================================
# Presence event callback
# ===========================================================================


class TestPresenceCallback:
    @pytest.mark.asyncio
    async def test_on_presence_event_broadcast(self, server):
        """Broadcast events are acknowledged but no-op."""
        await server._on_presence_event("broadcast", "doc-1", {"info": "x"})

    @pytest.mark.asyncio
    async def test_on_presence_event_unknown(self, server):
        """Unknown event types are silently ignored."""
        await server._on_presence_event("unknown_type", "doc-1", {})


# ===========================================================================
# Cleanup
# ===========================================================================


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_rate_limiter(self, server):
        server.rate_limiter.reset_prefix = AsyncMock()
        await server._cleanup_rate_limiter("sid-1")
        server.rate_limiter.reset_prefix.assert_awaited_once_with("sid-1")
