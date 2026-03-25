"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- collaboration/server.py (CollaborationServer, RateLimiter)
- ai_assistant/mamba_hybrid_processor.py (MambaSSM, SharedAttention, Manager)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# mamba_hybrid_processor imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import (
    TORCH_AVAILABLE,
    ConstitutionalMambaHybrid,
    MambaConfig,
    MambaHybridManager,
    MambaSSM,
    SharedAttentionLayer,
    get_mamba_hybrid_processor,
    initialize_mamba_processor,
)

# ---------------------------------------------------------------------------
# collaboration/server imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.collaboration.models import (
    ActivityEventType,
    ChatMessage,
    CollaborationConfig,
    CollaborationValidationError,
    Collaborator,
    Comment,
    ConflictError,
    CursorPosition,
    EditOperation,
    PermissionDeniedError,
    SessionFullError,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.server import (
    CollaborationServer,
    RateLimiter,
)

if TORCH_AVAILABLE:
    import torch


# ===================================================================
# Fixtures & helpers
# ===================================================================


def _make_sio_mock() -> MagicMock:
    """Create a mock SocketServerProtocol."""
    sio = MagicMock()
    sio.event = MagicMock(side_effect=lambda fn: fn)
    sio.save_session = AsyncMock()
    sio.get_session = AsyncMock(return_value=None)
    sio.leave_room = AsyncMock()
    sio.enter_room = AsyncMock()
    sio.emit = AsyncMock()
    return sio


def _make_collaborator(**overrides) -> SimpleNamespace:
    """Create a minimal collaborator-like object."""
    defaults = {
        "user_id": "user-1",
        "client_id": "client-1",
        "name": "Alice",
        "color": "#FF0000",
        "avatar": "https://example.com/avatar.png",
        "to_dict": lambda: {
            "user_id": "user-1",
            "client_id": "client-1",
            "name": "Alice",
            "color": "#FF0000",
        },
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_session_obj(**overrides) -> SimpleNamespace:
    """Create a minimal CollaborationSession-like object."""
    defaults = {
        "version": 1,
        "is_locked": False,
        "locked_by": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_edit_op(**overrides) -> SimpleNamespace:
    """Create a minimal EditOperation-like result object."""
    defaults = {
        "operation_id": "op-1",
        "to_dict": lambda: {"operation_id": "op-1", "type": "replace"},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture()
def collab_server():
    """Create a CollaborationServer with mocked dependencies."""
    config = CollaborationConfig()
    audit = AsyncMock()
    audit.log_event = AsyncMock()
    auth_validator = MagicMock(
        return_value={"user_id": "user-1", "tenant_id": "tenant-1", "permissions": ["write"]}
    )
    server = CollaborationServer(
        config=config,
        audit_client=audit,
        auth_validator=auth_validator,
    )
    server.sio = _make_sio_mock()
    server.presence = AsyncMock()
    server.presence._sessions = {}
    server.sync = AsyncMock()
    server.permissions = MagicMock()
    server.permissions.get_document_permissions = MagicMock(return_value={})
    server.permissions.require_edit_permission = AsyncMock()
    server.permissions.validate_operation = AsyncMock()
    return server


# ===================================================================
# RateLimiter tests
# ===================================================================


class TestRateLimiter:
    """Tests for the RateLimiter adapter."""

    async def test_is_allowed_returns_bool(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        result = await limiter.is_allowed("client-a")
        assert isinstance(result, bool)
        assert result is True

    async def test_is_allowed_exhausts_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert await limiter.is_allowed("client-b") is True
        assert await limiter.is_allowed("client-b") is False

    async def test_get_remaining_initial(self):
        limiter = RateLimiter(max_requests=50, window_seconds=60)
        remaining = await limiter.get_remaining("fresh-client")
        assert remaining == 50

    async def test_get_remaining_after_requests(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        await limiter.is_allowed("c1")
        await limiter.is_allowed("c1")
        remaining = await limiter.get_remaining("c1")
        assert remaining == 8

    async def test_get_remaining_never_negative(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        for _ in range(5):
            await limiter.is_allowed("c2")
        remaining = await limiter.get_remaining("c2")
        assert remaining >= 0

    async def test_reset_prefix_exact_match(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        await limiter.is_allowed("sid-123")
        await limiter.reset_prefix("sid-123")
        remaining = await limiter.get_remaining("sid-123")
        assert remaining == 10

    async def test_reset_prefix_with_subkeys(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        await limiter.is_allowed("sid-abc")
        await limiter.is_allowed("sid-abc:edit")
        await limiter.reset_prefix("sid-abc")
        remaining_base = await limiter.get_remaining("sid-abc")
        remaining_edit = await limiter.get_remaining("sid-abc:edit")
        assert remaining_base == 10
        assert remaining_edit == 10

    async def test_reset_prefix_no_matching_keys(self):
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        await limiter.is_allowed("other-key")
        await limiter.reset_prefix("nonexistent")
        remaining = await limiter.get_remaining("other-key")
        assert remaining == 9

    async def test_custom_key_prefix(self):
        limiter = RateLimiter(key_prefix="custom_prefix")
        assert limiter._limiter.key_prefix == "custom_prefix"


# ===================================================================
# CollaborationServer — join document
# ===================================================================


class TestHandleJoinDocument:
    """Tests for _handle_join_document."""

    async def test_join_rate_limited(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=False)
        result = await collab_server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "RATE_LIMITED"

    async def test_join_no_session(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "NO_SESSION"

    async def test_join_missing_document_id(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": "t1"})
        result = await collab_server._handle_join_document("sid-1", {})
        assert result["code"] == "MISSING_DOC_ID"

    async def test_join_missing_tenant(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": None})
        result = await collab_server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "MISSING_TENANT"

    async def test_join_session_full(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": "t1"})
        collab_server.presence.join_session = AsyncMock(
            side_effect=SessionFullError("Session is full")
        )
        result = await collab_server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "SESSION_FULL"

    async def test_join_success(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.sio.get_session = AsyncMock(return_value={"user_id": "u1", "tenant_id": "t1"})
        collab_obj = _make_collaborator()
        session_obj = _make_session_obj(version=5)
        collab_server.presence.join_session = AsyncMock(return_value=(session_obj, collab_obj))
        collab_server.sync.get_document = AsyncMock(return_value={"content": "hello"})
        users = [_make_collaborator()]
        collab_server.presence.get_all_users = AsyncMock(return_value=users)

        result = await collab_server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["success"] is True
        assert result["version"] == 5
        assert result["client_id"] == "client-1"

    async def test_join_internal_error(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.sio.get_session = AsyncMock(side_effect=RuntimeError("boom"))
        result = await collab_server._handle_join_document("sid-1", {"document_id": "doc-1"})
        assert result["code"] == "INTERNAL_ERROR"


# ===================================================================
# CollaborationServer — leave document
# ===================================================================


class TestHandleLeaveDocument:
    """Tests for _handle_leave_document."""

    async def test_leave_no_session(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_leave_document("sid-1")
        assert result == {"success": False}

    async def test_leave_no_document(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": None, "client_id": None}
        )
        result = await collab_server._handle_leave_document("sid-1")
        assert result["success"] is True

    async def test_leave_with_collaborator(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "client_id": "c-1"}
        )
        collab = _make_collaborator()
        collab_server.presence.leave_session = AsyncMock(return_value=collab)
        result = await collab_server._handle_leave_document("sid-1")
        assert result["success"] is True
        collab_server.sio.emit.assert_called_once()

    async def test_leave_no_collaborator_returned(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "client_id": "c-1"}
        )
        collab_server.presence.leave_session = AsyncMock(return_value=None)
        result = await collab_server._handle_leave_document("sid-1")
        assert result["success"] is True
        collab_server.sio.emit.assert_not_called()


# ===================================================================
# CollaborationServer — cursor move
# ===================================================================


class TestHandleCursorMove:
    """Tests for _handle_cursor_move."""

    async def test_cursor_no_session(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_cursor_move("sid-1", {"cursor": {"x": 1, "y": 2}})
        assert result == {"error": "No session"}

    async def test_cursor_not_in_document(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": None, "client_id": None}
        )
        result = await collab_server._handle_cursor_move("sid-1", {"cursor": {"x": 1, "y": 2}})
        assert result == {"error": "Not in document"}

    async def test_cursor_move_success(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "client_id": "c-1"}
        )
        collab_server.presence.update_cursor = AsyncMock(return_value=True)
        collab_server.presence.get_collaborator = AsyncMock(return_value=_make_collaborator())
        result = await collab_server._handle_cursor_move("sid-1", {"cursor": {"x": 10, "y": 20}})
        assert result["success"] is True

    async def test_cursor_move_failure(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "client_id": "c-1"}
        )
        collab_server.presence.update_cursor = AsyncMock(return_value=False)
        result = await collab_server._handle_cursor_move("sid-1", {"cursor": {}})
        assert result["success"] is False

    async def test_cursor_broadcast_no_collaborator(self, collab_server):
        """When collaborator lookup returns None, no emit happens."""
        collab_server.presence.get_collaborator = AsyncMock(return_value=None)
        await collab_server._broadcast_cursor_update("sid-1", "doc-1", "c-1", {"x": 0, "y": 0})
        collab_server.sio.emit.assert_not_called()


# ===================================================================
# CollaborationServer — edit operation
# ===================================================================


class TestHandleEditOperation:
    """Tests for _handle_edit_operation."""

    def _session_data(self):
        return {"document_id": "doc-1", "client_id": "c-1", "user_id": "u-1"}

    async def test_edit_no_session(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_edit_operation("sid-1", {})
        assert result["code"] == "NO_SESSION"

    async def test_edit_not_in_document(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": None, "client_id": None, "user_id": "u-1"}
        )
        result = await collab_server._handle_edit_operation("sid-1", {})
        assert result["code"] == "NOT_IN_DOCUMENT"

    async def test_edit_rate_limited(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=False)
        result = await collab_server._handle_edit_operation("sid-1", {})
        assert result["code"] == "RATE_LIMITED"

    async def test_edit_permission_denied(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.permissions.require_edit_permission = AsyncMock(
            side_effect=PermissionDeniedError("no access")
        )
        result = await collab_server._handle_edit_operation("sid-1", {})
        assert result["code"] == "PERMISSION_DENIED"

    async def test_edit_session_not_found(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.presence.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_edit_operation("sid-1", {})
        assert result["code"] == "SESSION_NOT_FOUND"

    async def test_edit_document_locked(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        locked_session = _make_session_obj(is_locked=True, locked_by="other-user")
        collab_server.presence.get_session = AsyncMock(return_value=locked_session)
        result = await collab_server._handle_edit_operation("sid-1", {})
        assert result["code"] == "DOCUMENT_LOCKED"

    async def test_edit_document_locked_by_self_allowed(self, collab_server):
        """User who locked the document can still edit."""
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        locked_session = _make_session_obj(is_locked=True, locked_by="u-1", version=3)
        collab_server.presence.get_session = AsyncMock(return_value=locked_session)
        applied = _make_edit_op()
        collab_server.sync.apply_operation = AsyncMock(return_value=applied)
        result = await collab_server._handle_edit_operation(
            "sid-1", {"type": "replace", "path": "/x", "value": "y"}
        )
        assert result["success"] is True

    async def test_edit_validation_failed(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.presence.get_session = AsyncMock(return_value=_make_session_obj())
        collab_server.permissions.validate_operation = AsyncMock(
            side_effect=CollaborationValidationError("bad op")
        )
        result = await collab_server._handle_edit_operation(
            "sid-1", {"type": "replace", "path": "/x"}
        )
        assert result["code"] == "VALIDATION_FAILED"

    async def test_edit_conflict_error(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        collab_server.presence.get_session = AsyncMock(return_value=_make_session_obj())
        collab_server.sync.apply_operation = AsyncMock(
            side_effect=ConflictError("version conflict")
        )
        result = await collab_server._handle_edit_operation(
            "sid-1", {"type": "replace", "path": "/x"}
        )
        assert result["code"] == "CONFLICT"

    async def test_edit_success(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=self._session_data())
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.is_allowed = AsyncMock(return_value=True)
        session_obj = _make_session_obj(version=7)
        collab_server.presence.get_session = AsyncMock(return_value=session_obj)
        applied = _make_edit_op()
        collab_server.sync.apply_operation = AsyncMock(return_value=applied)
        result = await collab_server._handle_edit_operation(
            "sid-1", {"type": "replace", "path": "/title", "value": "New Title"}
        )
        assert result["success"] is True
        assert result["operation_id"] == "op-1"

    async def test_edit_internal_error(self, collab_server):
        collab_server.sio.get_session = AsyncMock(side_effect=TypeError("unexpected"))
        result = await collab_server._handle_edit_operation("sid-1", {})
        assert result["code"] == "INTERNAL_ERROR"


# ===================================================================
# CollaborationServer — social handlers
# ===================================================================


class TestHandleChatMessage:
    """Tests for _handle_chat_message."""

    async def test_chat_no_session(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_chat_message("sid-1", {"text": "hi"})
        assert result == {"error": "No session"}

    async def test_chat_not_in_document(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": None, "user_id": "u-1"}
        )
        result = await collab_server._handle_chat_message("sid-1", {"text": "hi"})
        assert result == {"error": "Not in document"}

    async def test_chat_disabled(self, collab_server):
        collab_server.config.enable_chat = False
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "user_id": "u-1", "client_id": "c-1"}
        )
        result = await collab_server._handle_chat_message("sid-1", {"text": "hi"})
        assert result == {"error": "Chat disabled"}

    async def test_chat_success(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "user_id": "u-1", "client_id": "c-1"}
        )
        collab_server.presence.get_collaborator = AsyncMock(return_value=_make_collaborator())
        result = await collab_server._handle_chat_message("sid-1", {"text": "hello world"})
        assert result["success"] is True
        assert "message_id" in result

    async def test_chat_no_collaborator_uses_unknown(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "user_id": "u-1", "client_id": "c-1"}
        )
        collab_server.presence.get_collaborator = AsyncMock(return_value=None)
        result = await collab_server._handle_chat_message("sid-1", {"text": "anon msg"})
        assert result["success"] is True


class TestHandleTypingIndicator:
    """Tests for _handle_typing_indicator."""

    async def test_typing_no_session(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_typing_indicator("sid-1", {"is_typing": True})
        assert result == {"error": "No session"}

    async def test_typing_not_in_document(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": None, "client_id": None}
        )
        result = await collab_server._handle_typing_indicator("sid-1", {"is_typing": True})
        assert result == {"error": "Not in document"}

    async def test_typing_success(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "client_id": "c-1"}
        )
        collab_server.presence.set_typing = AsyncMock(return_value=True)
        collab_server.presence.get_collaborator = AsyncMock(return_value=_make_collaborator())
        result = await collab_server._handle_typing_indicator("sid-1", {"is_typing": True})
        assert result["success"] is True

    async def test_typing_failure(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "client_id": "c-1"}
        )
        collab_server.presence.set_typing = AsyncMock(return_value=False)
        result = await collab_server._handle_typing_indicator("sid-1", {"is_typing": False})
        assert result["success"] is False

    async def test_typing_broadcast_no_collaborator(self, collab_server):
        collab_server.presence.get_collaborator = AsyncMock(return_value=None)
        await collab_server._broadcast_typing_update("sid-1", "doc-1", "c-1", True)
        collab_server.sio.emit.assert_not_called()


class TestHandleAddComment:
    """Tests for _handle_add_comment."""

    async def test_comment_no_session(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_add_comment("sid-1", {"text": "note"})
        assert result == {"error": "No session"}

    async def test_comment_not_in_document(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": None, "user_id": "u-1"}
        )
        result = await collab_server._handle_add_comment("sid-1", {"text": "note"})
        assert result == {"error": "Not in document"}

    async def test_comment_disabled(self, collab_server):
        collab_server.config.enable_comments = False
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "user_id": "u-1", "client_id": "c-1"}
        )
        result = await collab_server._handle_add_comment("sid-1", {"text": "note"})
        assert result == {"error": "Comments disabled"}

    async def test_comment_success_with_position(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "user_id": "u-1", "client_id": "c-1"}
        )
        collab_server.presence.get_collaborator = AsyncMock(return_value=_make_collaborator())
        result = await collab_server._handle_add_comment(
            "sid-1",
            {"text": "looks good", "position": {"x": 10, "y": 20, "line": 5, "column": 3}},
        )
        assert result["success"] is True
        assert "comment_id" in result

    async def test_comment_success_no_position(self, collab_server):
        collab_server.sio.get_session = AsyncMock(
            return_value={"document_id": "doc-1", "user_id": "u-1", "client_id": "c-1"}
        )
        collab_server.presence.get_collaborator = AsyncMock(return_value=None)
        result = await collab_server._handle_add_comment("sid-1", {"text": "general comment"})
        assert result["success"] is True


class TestHandleGetPresence:
    """Tests for _handle_get_presence."""

    async def test_presence_no_session(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value=None)
        result = await collab_server._handle_get_presence("sid-1")
        assert result == {"error": "No session"}

    async def test_presence_not_in_document(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value={"document_id": None})
        result = await collab_server._handle_get_presence("sid-1")
        assert result == {"error": "Not in document"}

    async def test_presence_success(self, collab_server):
        collab_server.sio.get_session = AsyncMock(return_value={"document_id": "doc-1"})
        collab_server.presence.get_all_users = AsyncMock(return_value=[_make_collaborator()])
        result = await collab_server._handle_get_presence("sid-1")
        assert "users" in result
        assert len(result["users"]) == 1


# ===================================================================
# CollaborationServer — utility / lifecycle methods
# ===================================================================


class TestServerLifecycle:
    """Tests for server lifecycle and utility methods."""

    async def test_shutdown_not_started(self, collab_server):
        collab_server._started = False
        await collab_server.shutdown()
        # Should not call presence.stop
        collab_server.presence.stop.assert_not_called()

    async def test_shutdown_started(self, collab_server):
        collab_server._started = True
        collab_server.presence.stop = AsyncMock()
        await collab_server.shutdown()
        collab_server.presence.stop.assert_called_once()
        assert collab_server._started is False

    async def test_health_check_not_started(self, collab_server):
        collab_server._started = False
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.get_remaining = AsyncMock(return_value=50)
        result = await collab_server.health_check()
        assert result["status"] == "not_started"

    async def test_health_check_started(self, collab_server):
        collab_server._started = True
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.get_remaining = AsyncMock(return_value=42)
        result = await collab_server.health_check()
        assert result["status"] == "healthy"
        assert result["active_sessions"] == 0

    def test_get_asgi_app_not_initialized(self, collab_server):
        collab_server.sio = None
        with pytest.raises(RuntimeError, match="not initialized"):
            collab_server.get_asgi_app()

    async def test_log_activity_with_audit_client(self, collab_server):
        await collab_server._log_activity(
            ActivityEventType.USER_JOINED,
            "u-1",
            "doc-1",
            {"info": "test"},
        )
        collab_server.audit_client.log_event.assert_called_once()

    async def test_log_activity_no_audit_client(self, collab_server):
        collab_server.audit_client = None
        # Should not raise
        await collab_server._log_activity(
            ActivityEventType.USER_JOINED,
            "u-1",
            "doc-1",
            {},
        )

    async def test_log_activity_audit_error_swallowed(self, collab_server):
        collab_server.audit_client.log_event = AsyncMock(side_effect=RuntimeError("audit down"))
        # Should not raise
        await collab_server._log_activity(
            ActivityEventType.DOCUMENT_EDITED,
            "u-1",
            "doc-1",
            {},
        )

    async def test_on_presence_event_broadcast(self, collab_server):
        # Should not raise for broadcast event type
        await collab_server._on_presence_event("broadcast", "doc-1", {})

    async def test_on_presence_event_unknown(self, collab_server):
        # Should not raise for unknown event types
        await collab_server._on_presence_event("unknown", "doc-1", {})

    async def test_cleanup_rate_limiter(self, collab_server):
        collab_server.rate_limiter = AsyncMock()
        collab_server.rate_limiter.reset_prefix = AsyncMock()
        await collab_server._cleanup_rate_limiter("sid-1")
        collab_server.rate_limiter.reset_prefix.assert_called_once_with("sid-1")

    def test_create_cursor_position(self, collab_server):
        cursor = collab_server._create_cursor_position(
            {"x": 10, "y": 20, "line": 5, "column": 3, "node_id": "n-1"}
        )
        assert isinstance(cursor, CursorPosition)
        assert cursor.x == 10
        assert cursor.y == 20
        assert cursor.line == 5
        assert cursor.node_id == "n-1"

    def test_create_cursor_position_defaults(self, collab_server):
        cursor = collab_server._create_cursor_position({})
        assert cursor.x == 0
        assert cursor.y == 0
        assert cursor.line is None

    def test_create_edit_operation(self, collab_server):
        session_obj = _make_session_obj(version=3)
        op = collab_server._create_edit_operation(
            {"type": "insert", "path": "/content", "value": "new", "position": 5},
            "u-1",
            "c-1",
            session_obj,
        )
        assert isinstance(op, EditOperation)
        assert op.type.value == "insert"
        assert op.path == "/content"
        assert op.position == 5

    def test_create_comment_with_position(self, collab_server):
        collab = _make_collaborator()
        comment = collab_server._create_comment(
            "u-1",
            collab,
            {"text": "nice", "position": {"x": 1, "y": 2}, "selection_text": "hello"},
        )
        assert isinstance(comment, Comment)
        assert comment.text == "nice"
        assert comment.position is not None

    def test_create_comment_no_position(self, collab_server):
        comment = collab_server._create_comment(
            "u-1",
            None,
            {"text": "anon comment"},
        )
        assert comment.user_name == "Unknown"
        assert comment.position is None

    def test_create_chat_message(self, collab_server):
        collab = _make_collaborator()
        msg = collab_server._create_chat_message(
            "u-1",
            collab,
            {"text": "hello", "mentions": ["u-2"]},
        )
        assert isinstance(msg, ChatMessage)
        assert msg.text == "hello"
        assert msg.mentions == ["u-2"]

    def test_create_chat_message_no_collaborator(self, collab_server):
        msg = collab_server._create_chat_message("u-1", None, {"text": "msg"})
        assert msg.user_name == "Unknown"
        assert msg.user_avatar is None

    def test_register_handlers_from_table(self, collab_server):
        handler = AsyncMock()
        collab_server._register_handlers_from_table([("test_event", handler)])
        collab_server.sio.event.assert_called_once()

    def test_check_document_lock_not_locked(self, collab_server):
        session = _make_session_obj(is_locked=False)
        assert collab_server._check_document_lock(session, "u-1") is None

    def test_check_document_lock_locked_by_other(self, collab_server):
        session = _make_session_obj(is_locked=True, locked_by="u-2")
        result = collab_server._check_document_lock(session, "u-1")
        assert result["code"] == "DOCUMENT_LOCKED"

    def test_check_document_lock_locked_by_self(self, collab_server):
        session = _make_session_obj(is_locked=True, locked_by="u-1")
        assert collab_server._check_document_lock(session, "u-1") is None


# ===================================================================
# MambaConfig tests
# ===================================================================


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
class TestMambaConfig:
    """Tests for MambaConfig dataclass."""

    def test_default_config(self):
        config = MambaConfig()
        assert config.d_model == 512
        assert config.d_state == 128
        assert config.num_mamba_layers == 6
        assert config.max_context_length == 4_000_000

    def test_custom_config(self):
        config = MambaConfig(d_model=256, num_mamba_layers=3, device="cpu")
        assert config.d_model == 256
        assert config.num_mamba_layers == 3

    def test_dtype_defaults_to_float16(self):
        config = MambaConfig()
        assert config.dtype == torch.float16

    def test_post_init_sets_dtype(self):
        config = MambaConfig(dtype=None)
        assert config.dtype == torch.float16

    def test_explicit_dtype_preserved(self):
        config = MambaConfig(dtype=torch.float32)
        assert config.dtype == torch.float32


# ===================================================================
# MambaSSM tests
# ===================================================================


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
class TestMambaSSM:
    """Tests for MambaSSM layer."""

    def test_init(self):
        config = MambaConfig(d_model=64, d_state=16, dt_rank=8, device="cpu")
        ssm = MambaSSM(config)
        assert ssm.d_model == 64
        assert ssm.d_inner == 64 * config.expand

    def test_forward_shape(self):
        config = MambaConfig(d_model=64, d_state=16, dt_rank=8, device="cpu")
        ssm = MambaSSM(config)
        x = torch.randn(2, 10, 64)
        # _ssm_forward is a simplified prototype with shape constraints;
        # mock it to test the rest of the forward path
        with patch.object(ssm, "_ssm_forward", return_value=torch.randn(2, 10, 128)):
            out = ssm(x)
        assert out.shape == (2, 10, 64)

    def test_compute_dt_clamped(self):
        config = MambaConfig(d_model=64, d_state=16, dt_rank=8, device="cpu")
        ssm = MambaSSM(config)
        x = torch.randn(2, 5, 128)
        dt = torch.randn(2, 5, 128)
        result = ssm._compute_dt(x, dt)
        assert result.min() >= config.dt_min
        assert result.max() <= config.dt_max

    def test_initialize_weights(self):
        config = MambaConfig(d_model=64, d_state=16, dt_rank=8, device="cpu")
        ssm = MambaSSM(config)
        # Verify bias was zeroed
        assert torch.all(ssm.dt_proj.bias == 0)


# ===================================================================
# SharedAttentionLayer tests
# ===================================================================


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
class TestSharedAttentionLayer:
    """Tests for SharedAttentionLayer."""

    def test_init(self):
        config = MambaConfig(d_model=64, device="cpu")
        attn = SharedAttentionLayer(config)
        assert attn.num_heads == 8
        assert attn.head_dim == 8

    def test_forward_shape(self):
        config = MambaConfig(d_model=64, device="cpu")
        attn = SharedAttentionLayer(config)
        x = torch.randn(2, 10, 64)
        out = attn(x)
        assert out.shape == (2, 10, 64)

    def test_forward_with_mask(self):
        config = MambaConfig(d_model=64, device="cpu")
        attn = SharedAttentionLayer(config)
        x = torch.randn(1, 4, 64)
        mask = torch.ones(1, 1, 4, 4)
        mask[:, :, :, 3] = 0  # Mask out last position
        out = attn(x, mask=mask)
        assert out.shape == (1, 4, 64)


# ===================================================================
# ConstitutionalMambaHybrid tests
# ===================================================================


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
class TestConstitutionalMambaHybrid:
    """Tests for the hybrid processor model."""

    def _small_config(self, **kwargs):
        defaults = {
            "d_model": 64,
            "d_state": 16,
            "dt_rank": 8,
            "num_mamba_layers": 2,
            "device": "cpu",
            "max_context_length": 100,
        }
        defaults.update(kwargs)
        return MambaConfig(**defaults)

    def test_init_with_attention(self):
        config = self._small_config(use_shared_attention=True)
        model = ConstitutionalMambaHybrid(config)
        assert model.shared_attention is not None

    def test_init_without_attention(self):
        config = self._small_config(use_shared_attention=False)
        model = ConstitutionalMambaHybrid(config)
        assert model.shared_attention is None

    def _patch_ssm_forward(self, model):
        """Patch all MambaSSM layers to bypass the simplified _ssm_forward prototype."""
        patches = []
        for mamba_layer in model.mamba_layers:
            # Return identity-like tensor matching d_inner then let out_proj handle it
            def make_mock(layer):
                def mock_ssm(x, dt, B, C):
                    return torch.randn_like(x)

                return mock_ssm

            p = patch.object(mamba_layer, "_ssm_forward", side_effect=make_mock(mamba_layer))
            p.start()
            patches.append(p)
        return patches

    def _stop_patches(self, patches):
        for p in patches:
            p.stop()

    def test_forward_basic(self):
        config = self._small_config()
        model = ConstitutionalMambaHybrid(config)
        model.eval()
        x = torch.randn(1, 10, 64)
        patches = self._patch_ssm_forward(model)
        try:
            out = model(x)
            assert out.shape[0] == 1
            assert out.shape[2] == 64
        finally:
            self._stop_patches(patches)

    def test_forward_with_attention(self):
        config = self._small_config(use_shared_attention=True, num_mamba_layers=4)
        model = ConstitutionalMambaHybrid(config)
        model.eval()
        x = torch.randn(1, 8, 64)
        patches = self._patch_ssm_forward(model)
        try:
            out = model(x, use_attention=True)
            assert out.shape == (1, 8, 64)
        finally:
            self._stop_patches(patches)

    def test_forward_truncates_long_sequence(self):
        config = self._small_config(max_context_length=20)
        model = ConstitutionalMambaHybrid(config)
        model.eval()
        x = torch.randn(1, 50, 64)
        patches = self._patch_ssm_forward(model)
        try:
            out = model(x)
            assert out.shape[1] <= 20
        finally:
            self._stop_patches(patches)

    def test_forward_with_critical_positions(self):
        config = self._small_config(jrt_enabled=True)
        model = ConstitutionalMambaHybrid(config)
        model.eval()
        x = torch.randn(1, 10, 64)
        patches = self._patch_ssm_forward(model)
        try:
            out = model(x, critical_positions=[0, 5])
            assert out.shape[0] == 1
        finally:
            self._stop_patches(patches)

    def test_forward_jrt_disabled(self):
        config = self._small_config(jrt_enabled=False)
        model = ConstitutionalMambaHybrid(config)
        model.eval()
        x = torch.randn(1, 10, 64)
        patches = self._patch_ssm_forward(model)
        try:
            out = model(x, critical_positions=[0, 5])
            assert out.shape == (1, 10, 64)
        finally:
            self._stop_patches(patches)

    def test_forward_with_input_ids(self):
        config = self._small_config(jrt_enabled=True, max_context_length=1000)
        model = ConstitutionalMambaHybrid(config)
        model.eval()
        x = torch.randn(1, 20, 64)
        input_ids = torch.randint(0, 1000, (1, 20))
        patches = self._patch_ssm_forward(model)
        try:
            out = model(x, input_ids=input_ids)
            assert out.shape[0] == 1
        finally:
            self._stop_patches(patches)

    def test_identify_critical_positions(self):
        config = self._small_config()
        model = ConstitutionalMambaHybrid(config)
        input_ids = torch.zeros(1, 1100, dtype=torch.long)
        positions = model._identify_critical_positions(input_ids)
        assert 0 in positions  # First token (i%250==0)
        assert 250 in positions
        assert 500 in positions
        assert 1042 in positions  # i%1000==42

    def test_prepare_jrt_disabled(self):
        config = self._small_config(jrt_enabled=False)
        model = ConstitutionalMambaHybrid(config)
        x = torch.randn(1, 10, 64)
        result = model._prepare_jrt_context(x, critical_positions=[0])
        assert torch.equal(result, x)

    def test_prepare_jrt_no_critical(self):
        config = self._small_config(jrt_enabled=True)
        model = ConstitutionalMambaHybrid(config)
        x = torch.randn(1, 10, 64)
        result = model._prepare_jrt_context(x, critical_positions=None)
        assert torch.equal(result, x)

    def test_prepare_jrt_repeats_tokens(self):
        config = self._small_config(jrt_enabled=True, critical_sections_repeat=2)
        model = ConstitutionalMambaHybrid(config)
        x = torch.randn(1, 5, 64)
        result = model._prepare_jrt_context(x, critical_positions=[1, 3])
        # Position 1 and 3 get repeated: 5 + 2*(2-1) = 7... wait, repeat=2 means 2 copies
        # non-critical: 3 tokens, critical: 2 * 2 = 4 tokens => 7 total
        assert result.shape[1] == 7

    def test_get_memory_usage(self):
        config = self._small_config()
        model = ConstitutionalMambaHybrid(config)
        info = model.get_memory_usage()
        assert "model_memory_mb" in info
        assert info["num_mamba_layers"] == 2
        assert info["jrt_enabled"] is True

    def test_enable_memory_efficient_mode(self):
        config = self._small_config()
        model = ConstitutionalMambaHybrid(config)
        assert model.config.memory_efficient_mode is False
        model.enable_memory_efficient_mode()
        assert model.config.memory_efficient_mode is True

    def test_reset_memory_cache(self):
        config = self._small_config()
        model = ConstitutionalMambaHybrid(config)
        model.memory_cache.fill_(1.0)
        model.reset_memory_cache()
        assert torch.all(model.memory_cache == 0)

    def test_get_memory_usage_no_cache(self):
        config = self._small_config()
        model = ConstitutionalMambaHybrid(config)
        del model.memory_cache
        info = model.get_memory_usage()
        assert info["model_memory_mb"] == 0

    def test_reset_memory_cache_no_cache(self):
        config = self._small_config()
        model = ConstitutionalMambaHybrid(config)
        delattr(model, "memory_cache")
        # Should not raise
        model.reset_memory_cache()


# ===================================================================
# MambaHybridManager tests
# ===================================================================


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
class TestMambaHybridManager:
    """Tests for MambaHybridManager."""

    def _small_config(self):
        return MambaConfig(d_model=64, d_state=16, dt_rank=8, num_mamba_layers=2, device="cpu")

    def test_init_default_config(self):
        mgr = MambaHybridManager()
        assert mgr.is_loaded is False
        assert mgr.model is None

    def test_load_model_success(self):
        mgr = MambaHybridManager(self._small_config())
        assert mgr.load_model() is True
        assert mgr.is_loaded is True
        assert mgr.model is not None

    def test_load_model_failure(self):
        config = self._small_config()
        config.d_model = -1  # Will cause error during model init
        mgr = MambaHybridManager(config)
        result = mgr.load_model()
        assert result is False
        assert mgr.is_loaded is False

    def test_process_context_not_loaded(self):
        mgr = MambaHybridManager(self._small_config())
        with pytest.raises(RuntimeError, match="not loaded"):
            mgr.process_context(torch.randn(1, 10, 64))

    def _patch_model_forward(self, mgr, seq_len=10, d_model=64):
        """Patch the model forward to return a valid tensor."""
        mock_output = torch.randn(1, seq_len, d_model)
        return patch.object(mgr.model, "forward", return_value=mock_output)

    def test_process_context_success(self):
        mgr = MambaHybridManager(self._small_config())
        mgr.load_model()
        x = torch.randn(1, 10, 64)
        with self._patch_model_forward(mgr):
            out = mgr.process_context(x)
        assert out.device.type == "cpu"
        assert out.shape[0] == 1

    def test_process_context_with_input_ids(self):
        mgr = MambaHybridManager(self._small_config())
        mgr.load_model()
        x = torch.randn(1, 10, 64)
        ids = torch.randint(0, 100, (1, 10))
        with self._patch_model_forward(mgr):
            out = mgr.process_context(x, input_ids=ids)
        assert out.shape[0] == 1

    def test_process_context_with_attention(self):
        config = self._small_config()
        config.use_shared_attention = True
        config.num_mamba_layers = 4
        mgr = MambaHybridManager(config)
        mgr.load_model()
        x = torch.randn(1, 10, 64)
        with self._patch_model_forward(mgr):
            out = mgr.process_context(x, use_attention=True)
        assert out.shape[0] == 1

    def test_get_model_info_not_loaded(self):
        mgr = MambaHybridManager(self._small_config())
        info = mgr.get_model_info()
        assert info["status"] == "not_loaded"

    def test_get_model_info_loaded(self):
        mgr = MambaHybridManager(self._small_config())
        mgr.load_model()
        info = mgr.get_model_info()
        assert info["status"] == "loaded"
        assert info["architecture"] == "Constitutional Mamba Hybrid"
        assert "capabilities" in info
        assert info["capabilities"]["complexity"] == "O(n)"

    def test_unload_model(self):
        mgr = MambaHybridManager(self._small_config())
        mgr.load_model()
        assert mgr.is_loaded is True
        mgr.unload_model()
        assert mgr.is_loaded is False
        assert mgr.model is None

    def test_unload_model_when_not_loaded(self):
        mgr = MambaHybridManager(self._small_config())
        mgr.unload_model()
        assert mgr.is_loaded is False


# ===================================================================
# Module-level functions
# ===================================================================


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_get_mamba_hybrid_processor(self):
        proc = get_mamba_hybrid_processor()
        assert isinstance(proc, MambaHybridManager)

    def test_initialize_mamba_processor(self):
        config = MambaConfig(d_model=64, d_state=16, dt_rank=8, num_mamba_layers=2, device="cpu")
        result = initialize_mamba_processor(config)
        assert result is True
        proc = get_mamba_hybrid_processor()
        assert proc.is_loaded is True
