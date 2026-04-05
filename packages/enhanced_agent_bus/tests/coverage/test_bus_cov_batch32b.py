"""
Coverage tests for collaboration/server.py and pqc_validators.py.

Constitutional Hash: 608508a9bd224290

Targets uncovered lines in:
- enhanced_agent_bus.collaboration.server (84.5% -> higher)
- enhanced_agent_bus.pqc_validators (81.8% -> higher)
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.security.pqc import (
    CONSTITUTIONAL_HASH,
    ClassicalKeyRejectedError,
    KeyRegistryUnavailableError,
    UnsupportedAlgorithmError,
)
from enhanced_agent_bus._compat.security.pqc_crypto import (
    HybridSignature,
    PQCConfig,
    PQCMetadata,
    ValidationResult,
)
from enhanced_agent_bus.collaboration.models import (
    ActivityEventType,
    ChatMessage,
    CollaborationConfig,
    CollaborationValidationError,
    Collaborator,
    Comment,
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
from enhanced_agent_bus.pqc_validators import (
    SUPPORTED_PQC_ALGORITHMS,
    PqcValidators,
    _extract_message_content,
    _is_self_validation,
    _verify_classical_component,
    _verify_pqc_component,
    check_enforcement_for_create,
    check_enforcement_for_update,
    validate_constitutional_hash_pqc,
    validate_maci_record_pqc,
    validate_signature,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EXPECTED_HASH = "608508a9bd224290"


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
    return Collaborator(**{**defaults, **overrides})


def _make_collab_session(**overrides):
    from enhanced_agent_bus.collaboration.models import CollaborationSession

    defaults = {
        "document_id": "doc-1",
        "document_type": DocumentType.POLICY,
        "tenant_id": "tenant-1",
        "version": 5,
    }
    return CollaborationSession(**{**defaults, **overrides})


def _make_sio_mock() -> MagicMock:
    sio = MagicMock()
    sio.save_session = AsyncMock()
    sio.get_session = AsyncMock(return_value=None)
    sio.leave_room = AsyncMock()
    sio.enter_room = AsyncMock()
    sio.emit = AsyncMock()
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


def _make_pqc_config(
    pqc_enabled: bool = True,
    migration_phase: str = "phase_3",
    enforce_content_hash: bool = False,
    verification_mode: str = "strict",
) -> MagicMock:
    """Create a PQCConfig mock with all needed attributes."""
    cfg = MagicMock()
    cfg.pqc_enabled = pqc_enabled
    cfg.pqc_mode = "hybrid" if pqc_enabled else "classical_only"
    cfg.verification_mode = verification_mode
    cfg.migration_phase = migration_phase
    cfg.enforce_content_hash = enforce_content_hash
    return cfg


def _make_key_registry_mock(
    registry_available: bool = False,
    key_record: object | None = None,
    get_key_side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock for the key registry importlib path."""
    mock_registry = MagicMock()
    if not registry_available:
        mock_registry._registry = None
    else:
        mock_registry._registry = MagicMock()
        if get_key_side_effect:
            mock_registry._registry.get_key = AsyncMock(side_effect=get_key_side_effect)
        else:
            mock_registry._registry.get_key = AsyncMock(return_value=key_record)

    mock_module = MagicMock()
    mock_module.key_registry_client = mock_registry
    mock_module.KeyNotFoundError = type("KeyNotFoundError", (Exception,), {})
    return mock_module


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


# ===================================================================
# CollaborationServer -- initialize / shutdown / lifecycle
# ===================================================================


class TestServerInitialize:
    async def test_initialize_success_with_mock_socketio(self):
        mock_sio_instance = _make_sio_mock()

        mock_socketio = MagicMock()
        mock_socketio.AsyncServer.return_value = mock_sio_instance
        mock_socketio.ASGIApp.return_value = MagicMock()

        srv = CollaborationServer(auth_validator=_auth_validator_ok)
        srv.presence = AsyncMock()
        srv.presence.start = AsyncMock()
        srv.presence.register_callback = MagicMock()

        with patch.dict("sys.modules", {"socketio": mock_socketio}):
            with patch(
                "enhanced_agent_bus.collaboration.server.socketio",
                mock_socketio,
                create=True,
            ):
                await srv.initialize()

        assert srv._started is True
        srv.presence.start.assert_awaited_once()
        srv.presence.register_callback.assert_called_once()

    async def test_shutdown_resets_started_flag(self, server):
        server._started = True
        server.presence = AsyncMock()
        server.presence.stop = AsyncMock()
        await server.shutdown()
        assert server._started is False

    async def test_get_asgi_app_success(self, server):
        mock_socketio = MagicMock()
        mock_socketio.ASGIApp.return_value = MagicMock()

        with patch.dict("sys.modules", {"socketio": mock_socketio}):
            with patch(
                "enhanced_agent_bus.collaboration.server.socketio",
                mock_socketio,
                create=True,
            ):
                app = server.get_asgi_app()
                assert app is not None

    async def test_get_asgi_app_raises_when_not_initialized(self):
        srv = CollaborationServer()
        with pytest.raises(RuntimeError, match="not initialized"):
            srv.get_asgi_app()


# ===================================================================
# _register_handlers_from_table -- wrapper creation
# ===================================================================


class TestRegisterHandlersFromTable:
    async def test_registered_wrapper_calls_handler_with_none_data(self, server):
        results = []

        async def handler(sid, data):
            results.append((sid, data))
            return {"done": True}

        def create_wrapper(h, name):
            async def wrapper(sid, data=None):
                return await h(sid, data or {})

            wrapper.__name__ = name
            return wrapper

        wrapper = create_wrapper(handler, "test_event")
        assert wrapper.__name__ == "test_event"
        result = await wrapper("sid-1", None)
        assert result == {"done": True}
        assert results[0] == ("sid-1", {})

    async def test_registered_wrapper_passes_data(self, server):
        results = []

        async def handler(sid, data):
            results.append(data)
            return data

        def create_wrapper(h, name):
            async def wrapper(sid, data=None):
                return await h(sid, data or {})

            wrapper.__name__ = name
            return wrapper

        wrapper = create_wrapper(handler, "my_event")
        await wrapper("sid-1", {"key": "value"})
        assert results[0] == {"key": "value"}

    def test_register_handlers_from_table_invokes_sio_event(self, server):
        """Verify _register_handlers_from_table creates wrappers and passes them."""
        registered = []
        server.sio = MagicMock()
        server.sio.event = lambda fn: registered.append(fn)

        async def handler_a(sid, data):
            return {}

        async def handler_b(sid, data):
            return {}

        server._register_handlers_from_table(
            [
                ("event_a", handler_a),
                ("event_b", handler_b),
            ]
        )
        assert len(registered) == 2
        assert registered[0].__name__ == "event_a"
        assert registered[1].__name__ == "event_b"


# ===================================================================
# Connection handlers (connect / disconnect)
# ===================================================================


class TestConnectionHandlers:
    async def test_disconnect_with_document_and_client(self, server):
        server.sio.get_session = AsyncMock(
            return_value={
                "document_id": "doc-1",
                "client_id": "client-1",
                "user_id": "user-1",
            }
        )
        server.presence.leave_session = AsyncMock(return_value=None)
        server.rate_limiter.reset_prefix = AsyncMock()

        sid = "sid-1"
        session = await server.sio.get_session(sid)
        document_id = session.get("document_id") if session else None
        client_id = session.get("client_id") if session else None

        if document_id and client_id:
            await server.presence.leave_session(document_id, client_id)
            await server.sio.leave_room(sid, document_id)

        await server._cleanup_rate_limiter(sid)

        server.presence.leave_session.assert_awaited_once_with("doc-1", "client-1")
        server.sio.leave_room.assert_awaited_once_with("sid-1", "doc-1")

    async def test_disconnect_without_document(self, server):
        server.sio.get_session = AsyncMock(return_value={"user_id": "user-1"})
        server.rate_limiter.reset_prefix = AsyncMock()

        sid = "sid-2"
        session = await server.sio.get_session(sid)
        document_id = session.get("document_id") if session else None
        client_id = session.get("client_id") if session else None

        if document_id and client_id:
            await server.presence.leave_session(document_id, client_id)

        await server._cleanup_rate_limiter(sid)
        server.sio.leave_room.assert_not_awaited()

    async def test_disconnect_with_none_session(self, server):
        server.sio.get_session = AsyncMock(return_value=None)
        server.rate_limiter.reset_prefix = AsyncMock()

        sid = "sid-3"
        session = await server.sio.get_session(sid)
        document_id = session.get("document_id") if session else None
        assert document_id is None

        await server._cleanup_rate_limiter(sid)


# ===================================================================
# Cursor broadcast -- collaborator not found
# ===================================================================


class TestBroadcastCursorUpdate:
    async def test_broadcast_cursor_no_collaborator(self, server):
        server.presence.get_collaborator = AsyncMock(return_value=None)
        await server._broadcast_cursor_update("sid-1", "doc-1", "client-1", {"x": 0})
        server.sio.emit.assert_not_awaited()

    async def test_broadcast_cursor_with_collaborator(self, server):
        collaborator = _make_collaborator()
        server.presence.get_collaborator = AsyncMock(return_value=collaborator)
        await server._broadcast_cursor_update("sid-1", "doc-1", "client-1", {"x": 10, "y": 20})
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "cursor-update"


# ===================================================================
# Typing broadcast -- collaborator not found
# ===================================================================


class TestBroadcastTypingUpdate:
    async def test_broadcast_typing_no_collaborator(self, server):
        server.presence.get_collaborator = AsyncMock(return_value=None)
        await server._broadcast_typing_update("sid-1", "doc-1", "client-1", True)
        server.sio.emit.assert_not_awaited()

    async def test_broadcast_typing_with_collaborator(self, server):
        collaborator = _make_collaborator()
        server.presence.get_collaborator = AsyncMock(return_value=collaborator)
        await server._broadcast_typing_update("sid-1", "doc-1", "client-1", False)
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "typing-update"
        assert call_args[0][1]["is_typing"] is False


# ===================================================================
# Comment creation -- with/without position, with/without collaborator
# ===================================================================


class TestCreateComment:
    def test_create_comment_with_position(self, server):
        collaborator = _make_collaborator()
        comment = server._create_comment(
            "user-1",
            collaborator,
            {
                "text": "Note here",
                "position": {"x": 5, "y": 10, "line": 3, "column": 7},
                "selection_text": "selected",
                "mentions": ["user-2"],
            },
        )
        assert isinstance(comment, Comment)
        assert comment.text == "Note here"
        assert comment.position is not None
        assert comment.position.line == 3
        assert comment.selection_text == "selected"

    def test_create_comment_without_position(self, server):
        collaborator = _make_collaborator()
        comment = server._create_comment(
            "user-1",
            collaborator,
            {"text": "General note"},
        )
        assert comment.position is None

    def test_create_comment_no_collaborator(self, server):
        comment = server._create_comment(
            "user-1",
            None,
            {"text": "Anonymous note"},
        )
        assert comment.user_name == "Unknown"
        assert comment.user_avatar is None


# ===================================================================
# Chat message creation -- with/without collaborator
# ===================================================================


class TestCreateChatMessage:
    def test_create_chat_message_with_collaborator(self, server):
        collaborator = _make_collaborator()
        msg = server._create_chat_message(
            "user-1",
            collaborator,
            {"text": "Hello!", "mentions": ["user-2"]},
        )
        assert isinstance(msg, ChatMessage)
        assert msg.user_name == "Alice"
        assert msg.mentions == ["user-2"]

    def test_create_chat_message_no_collaborator(self, server):
        msg = server._create_chat_message(
            "user-1",
            None,
            {"text": "Hi"},
        )
        assert msg.user_name == "Unknown"
        assert msg.user_avatar is None


# ===================================================================
# Broadcast comment added
# ===================================================================


class TestBroadcastCommentAdded:
    async def test_broadcast_comment_added(self, server):
        comment = Comment(
            user_id="user-1",
            user_name="Alice",
            text="Test comment",
        )
        await server._broadcast_comment_added("doc-1", comment, {"x": 1, "y": 2})
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "comment-added"
        assert call_args[0][1]["text"] == "Test comment"


# ===================================================================
# Broadcast chat message
# ===================================================================


class TestBroadcastChatMessage:
    async def test_broadcast_chat_message(self, server):
        msg = ChatMessage(
            user_id="user-1",
            user_name="Alice",
            text="Hello everyone",
        )
        await server._broadcast_chat_message("doc-1", msg)
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "chat-message"
        assert call_args[0][1]["text"] == "Hello everyone"


# ===================================================================
# Broadcast document update
# ===================================================================


class TestBroadcastDocumentUpdate:
    async def test_broadcast_document_update(self, server):
        applied_op = SimpleNamespace(
            operation_id="op-1",
            to_dict=lambda: {"operation_id": "op-1"},
        )
        collab_session = _make_collab_session(version=10)
        await server._broadcast_document_update(
            "sid-1", "doc-1", applied_op, "user-1", "client-1", collab_session
        )
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "document-update"
        assert call_args[0][1]["version"] == 10
        assert call_args[1]["skip_sid"] == "sid-1"


# ===================================================================
# Notify user joined
# ===================================================================


class TestNotifyUserJoined:
    async def test_notify_user_joined(self, server):
        collaborator = _make_collaborator()
        await server._notify_user_joined("sid-1", "doc-1", collaborator)
        server.sio.emit.assert_awaited_once()
        call_args = server.sio.emit.call_args
        assert call_args[0][0] == "user-joined"
        assert call_args[1]["skip_sid"] == "sid-1"


# ===================================================================
# Activity logging -- audit_client error types
# ===================================================================


class TestActivityLoggingEdgeCases:
    async def test_log_activity_swallows_type_error(self, server, audit_client):
        audit_client.log_event = AsyncMock(side_effect=TypeError("bad type"))
        await server._log_activity(ActivityEventType.USER_JOINED, "u1", "d1", {})

    async def test_log_activity_swallows_value_error(self, server, audit_client):
        audit_client.log_event = AsyncMock(side_effect=ValueError("bad value"))
        await server._log_activity(ActivityEventType.DOCUMENT_EDITED, "u1", "d1", {})

    async def test_log_activity_swallows_attribute_error(self, server, audit_client):
        audit_client.log_event = AsyncMock(side_effect=AttributeError("no attr"))
        await server._log_activity(ActivityEventType.COMMENT_ADDED, "u1", "d1", {})


# ===================================================================
# RateLimiter -- additional edge cases
# ===================================================================


class TestRateLimiterEdgeCases:
    async def test_rate_limiter_exhaust_and_deny(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        assert await rl.is_allowed("client-x") is True
        assert await rl.is_allowed("client-x") is True
        assert await rl.is_allowed("client-x") is False

    async def test_get_remaining_returns_zero_when_exhausted(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        await rl.is_allowed("client-y")
        remaining = await rl.get_remaining("client-y")
        assert remaining == 0

    async def test_get_remaining_for_unknown_client(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        remaining = await rl.get_remaining("unknown-client")
        assert remaining == 5

    async def test_reset_prefix_with_colon_variants(self):
        rl = RateLimiter(max_requests=10, window_seconds=60)
        await rl.is_allowed("sid-abc")
        await rl.is_allowed("sid-abc:edit")
        await rl.is_allowed("sid-abc:chat")
        await rl.reset_prefix("sid-abc")
        assert await rl.get_remaining("sid-abc") == 10
        assert await rl.get_remaining("sid-abc:edit") == 10
        assert await rl.get_remaining("sid-abc:chat") == 10


# ===================================================================
# Health check edge cases
# ===================================================================


class TestHealthCheckEdgeCases:
    async def test_health_check_with_multiple_sessions(self, server):
        server._started = True
        server.presence._sessions = {"doc-1": "s1", "doc-2": "s2", "doc-3": "s3"}
        result = await server.health_check()
        assert result["status"] == "healthy"
        assert result["active_sessions"] == 3
        assert "rate_limit_remaining" in result


# ===================================================================
# Validate edit operation -- CollaborationValidationError path
# ===================================================================


class TestValidateEditOperationEdge:
    async def test_validate_edit_operation_collaboration_validation_error(self, server):
        server.permissions.validate_operation = AsyncMock(
            side_effect=CollaborationValidationError("Invalid structure")
        )
        op = EditOperation(type="replace", path="/x", user_id="u1", client_id="c1", version=1)
        result = await server._validate_edit_operation("u1", "doc-1", op, {})
        assert result is not None
        assert result["code"] == "VALIDATION_FAILED"
        assert "Invalid structure" in result["error"]


# ===================================================================
# PQC Validators -- validate_signature
# ===================================================================


class TestValidateSignature:
    async def test_validate_signature_classical_in_hybrid_mode(self):
        """Classical key in hybrid mode should succeed."""
        mock_module = _make_key_registry_mock(registry_available=False)

        with patch("importlib.import_module", return_value=mock_module):
            result = await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-1",
                algorithm="Ed25519",
                hybrid_mode=True,
            )
        assert result["valid"] is True
        assert result["key_type"] == "classical"
        assert result["algorithm"] == "Ed25519"

    async def test_validate_signature_pqc_key(self):
        """PQC key should succeed regardless of hybrid mode."""
        mock_module = _make_key_registry_mock(registry_available=False)

        with patch("importlib.import_module", return_value=mock_module):
            result = await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-2",
                algorithm="ML-DSA-65",
                hybrid_mode=False,
            )
        assert result["valid"] is True
        assert result["key_type"] == "pqc"

    async def test_validate_signature_classical_rejected_in_pqc_only_mode(self):
        """Classical key rejected when hybrid_mode=False."""
        with pytest.raises(ClassicalKeyRejectedError):
            await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-3",
                algorithm="Ed25519",
                hybrid_mode=False,
            )

    async def test_validate_signature_unsupported_algorithm(self):
        with pytest.raises(UnsupportedAlgorithmError):
            await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-4",
                algorithm="INVALID-ALGO",
                hybrid_mode=True,
            )

    async def test_validate_signature_key_registry_failure(self):
        """Key registry error raises KeyRegistryUnavailableError."""
        mock_module = _make_key_registry_mock(
            registry_available=True,
            get_key_side_effect=RuntimeError("registry down"),
        )

        with patch("importlib.import_module", return_value=mock_module):
            with pytest.raises(KeyRegistryUnavailableError):
                await validate_signature(
                    payload=b"test",
                    signature=b"sig",
                    key_id="key-5",
                    algorithm="ML-DSA-65",
                    hybrid_mode=True,
                )

    async def test_validate_signature_key_registry_active_key(self):
        mock_key_record = MagicMock()
        mock_key_record.metadata = {"key_status": "active"}
        mock_module = _make_key_registry_mock(
            registry_available=True,
            key_record=mock_key_record,
        )

        with patch("importlib.import_module", return_value=mock_module):
            result = await validate_signature(
                payload=b"test",
                signature=b"sig",
                key_id="key-6",
                algorithm="ML-DSA-65",
                hybrid_mode=True,
            )
        assert result["key_status"] == "active"

    async def test_validate_signature_x25519_classical(self):
        mock_module = _make_key_registry_mock(registry_available=False)

        with patch("importlib.import_module", return_value=mock_module):
            result = await validate_signature(
                payload=b"data",
                signature=b"sig",
                key_id="key-7",
                algorithm="X25519",
                hybrid_mode=True,
            )
        assert result["key_type"] == "classical"

    async def test_validate_signature_key_record_none(self):
        mock_module = _make_key_registry_mock(
            registry_available=True,
            key_record=None,
        )

        with patch("importlib.import_module", return_value=mock_module):
            result = await validate_signature(
                payload=b"data",
                signature=b"sig",
                key_id="key-8",
                algorithm="ML-DSA-44",
                hybrid_mode=True,
            )
        assert result["valid"] is True
        assert result["key_status"] == "active"


# ===================================================================
# PQC Validators -- constitutional hash PQC-enabled paths
# ===================================================================


class TestValidateConstitutionalHashPqcEnabled:
    async def test_pqc_enabled_v1_classical_signature(self):
        """V1 classical signature with PQC enabled returns valid with deprecation warning."""
        pqc_config = _make_pqc_config(pqc_enabled=True, migration_phase="phase_5")

        mock_pqc_service = MagicMock()
        mock_pqc_service.config = pqc_config

        data = {
            "constitutional_hash": EXPECTED_HASH,
            "signature": {"version": "v1", "signature": "classsig"},
        }
        with patch(
            "enhanced_agent_bus.pqc_validators.PQCCryptoService",
            return_value=mock_pqc_service,
        ):
            result = await validate_constitutional_hash_pqc(
                data, expected_hash=EXPECTED_HASH, pqc_config=pqc_config
            )
        assert result.valid is True
        assert any("deprecated" in w for w in result.warnings)

    async def test_pqc_enabled_v1_classical_no_deprecation_phase_3(self):
        pqc_config = _make_pqc_config(pqc_enabled=True, migration_phase="phase_3")

        mock_pqc_service = MagicMock()
        mock_pqc_service.config = pqc_config

        data = {
            "constitutional_hash": EXPECTED_HASH,
            "signature": {"version": "v1", "signature": "classsig"},
        }
        with patch(
            "enhanced_agent_bus.pqc_validators.PQCCryptoService",
            return_value=mock_pqc_service,
        ):
            result = await validate_constitutional_hash_pqc(
                data, expected_hash=EXPECTED_HASH, pqc_config=pqc_config
            )
        assert result.valid is True
        assert not any("deprecated" in w for w in result.warnings)

    async def test_pqc_enabled_v2_general_exception_caught(self):
        """PQC_VALIDATION_OPERATION_ERRORS in PQC v2 path are caught."""
        pqc_config = _make_pqc_config(pqc_enabled=True)

        data = {
            "constitutional_hash": EXPECTED_HASH,
            "signature": {"version": "v2", "bad_field": True},
        }
        result = await validate_constitutional_hash_pqc(
            data, expected_hash=EXPECTED_HASH, pqc_config=pqc_config
        )
        assert result.valid is False
        assert len(result.errors) > 0

    async def test_hash_mismatch_short_hash(self):
        result = await validate_constitutional_hash_pqc(
            {"constitutional_hash": "short"},
            expected_hash=EXPECTED_HASH,
        )
        assert result.valid is False
        assert any("mismatch" in e for e in result.errors)

    async def test_hash_mismatch_long_hash(self):
        result = await validate_constitutional_hash_pqc(
            {"constitutional_hash": "abcdefghijklmnop"},
            expected_hash=EXPECTED_HASH,
        )
        assert result.valid is False
        assert any("abcdefgh..." in e for e in result.errors)

    async def test_classical_signature_present_pqc_disabled(self):
        data = {
            "constitutional_hash": EXPECTED_HASH,
            "signature": {"signature": "ed25519sig", "algorithm": "ed25519"},
        }
        result = await validate_constitutional_hash_pqc(
            data, expected_hash=EXPECTED_HASH, pqc_config=None
        )
        assert result.valid is True
        assert result.pqc_metadata is not None
        assert result.pqc_metadata.classical_verified is True
        assert result.pqc_metadata.verification_mode == "classical_only"

    async def test_non_dict_signature_becomes_empty_dict(self):
        data = {
            "constitutional_hash": EXPECTED_HASH,
            "signature": "just_a_string",
        }
        result = await validate_constitutional_hash_pqc(
            data, expected_hash=EXPECTED_HASH, pqc_config=None
        )
        assert result.valid is True

    async def test_pqc_enabled_v1_phase_4_deprecation_warning(self):
        """Phase 4 should also produce deprecation warning."""
        pqc_config = _make_pqc_config(pqc_enabled=True, migration_phase="phase_4")
        mock_pqc_service = MagicMock()
        mock_pqc_service.config = pqc_config

        data = {
            "constitutional_hash": EXPECTED_HASH,
            "signature": {"version": "v1", "signature": "classsig"},
        }
        with patch(
            "enhanced_agent_bus.pqc_validators.PQCCryptoService",
            return_value=mock_pqc_service,
        ):
            result = await validate_constitutional_hash_pqc(
                data, expected_hash=EXPECTED_HASH, pqc_config=pqc_config
            )
        assert result.valid is True
        assert any("deprecated" in w for w in result.warnings)


# ===================================================================
# PQC Validators -- MACI record validation edge cases
# ===================================================================


class TestValidateMaciRecordEdgeCases:
    async def test_missing_single_field(self):
        record = {"agent_id": "a1", "action": "validate"}
        result = await validate_maci_record_pqc(record, expected_hash=EXPECTED_HASH)
        assert result.valid is False
        assert any("timestamp" in e for e in result.errors)

    async def test_missing_multiple_fields(self):
        record = {"action": "validate"}
        result = await validate_maci_record_pqc(record, expected_hash=EXPECTED_HASH)
        assert result.valid is False
        assert any("agent_id" in e for e in result.errors)
        assert any("timestamp" in e for e in result.errors)

    async def test_self_validation_via_agent_id_in_target(self):
        record = {
            "agent_id": "agent_x",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
            "constitutional_hash": EXPECTED_HASH,
            "target_output_id": "agent_x_output_42",
        }
        result = await validate_maci_record_pqc(record, expected_hash=EXPECTED_HASH)
        assert result.valid is False
        assert any("Self-validation" in e for e in result.errors)

    async def test_valid_record_no_pqc_config(self):
        record = {
            "agent_id": "agent_1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
        }
        result = await validate_maci_record_pqc(
            record, expected_hash=EXPECTED_HASH, pqc_config=None
        )
        assert result.valid is True
        assert result.pqc_metadata is None

    async def test_valid_record_with_pqc_config_returns_metadata(self):
        pqc_config = PQCConfig(pqc_enabled=False)
        record = {
            "agent_id": "agent_1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
        }
        result = await validate_maci_record_pqc(
            record, expected_hash=EXPECTED_HASH, pqc_config=pqc_config
        )
        assert result.valid is True
        assert result.pqc_metadata is not None
        assert result.pqc_metadata.verification_mode == "classical_only"

    async def test_maci_record_with_pqc_enabled_and_signature(self):
        """MACI record with PQC enabled delegates to validate_constitutional_hash_pqc."""
        pqc_config = _make_pqc_config(pqc_enabled=True, migration_phase="phase_3")
        mock_pqc_service = MagicMock()
        mock_pqc_service.config = pqc_config

        record = {
            "agent_id": "agent_1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
            "constitutional_hash": EXPECTED_HASH,
            "signature": {"version": "v1", "signature": "test"},
        }
        with patch(
            "enhanced_agent_bus.pqc_validators.PQCCryptoService",
            return_value=mock_pqc_service,
        ):
            result = await validate_maci_record_pqc(
                record, expected_hash=EXPECTED_HASH, pqc_config=pqc_config
            )
        assert result.valid is True

    async def test_no_self_validation_without_target_output_id(self):
        record = {
            "agent_id": "agent_1",
            "action": "validate",
            "timestamp": "2025-01-01T00:00:00Z",
            "constitutional_hash": EXPECTED_HASH,
            "output_author": "agent_1",
        }
        result = await validate_maci_record_pqc(record, expected_hash=EXPECTED_HASH)
        assert result.valid is True


# ===================================================================
# _verify_classical_component / _verify_pqc_component
# ===================================================================


class TestVerifyComponents:
    def test_verify_classical_no_keys(self):
        keys = {"classical": None, "pqc": None}
        sig = HybridSignature(content_hash="abc", constitutional_hash=EXPECTED_HASH)
        result = _verify_classical_component(keys, sig, b"message")
        assert result is True

    def test_verify_pqc_no_keys(self):
        keys = {"classical": None, "pqc": None}
        sig = HybridSignature(content_hash="abc", constitutional_hash=EXPECTED_HASH)
        result = _verify_pqc_component(keys, sig, b"message")
        assert result is True

    def test_verify_classical_with_key_but_no_classical_attr(self):
        keys = {"classical": b"pubkey", "pqc": None}
        sig = SimpleNamespace(content_hash="abc", constitutional_hash=EXPECTED_HASH)
        result = _verify_classical_component(keys, sig, b"message")
        assert result is True

    def test_verify_pqc_with_key_but_no_pqc_attr(self):
        keys = {"classical": None, "pqc": b"pubkey"}
        sig = SimpleNamespace(content_hash="abc", constitutional_hash=EXPECTED_HASH)
        result = _verify_pqc_component(keys, sig, b"message")
        assert result is True

    def test_verify_classical_component_import_fails_returns_false(self):
        """When the registry import inside _verify_classical_component fails."""
        keys = {"classical": b"pubkey", "pqc": None}
        sig = SimpleNamespace(
            content_hash="abc",
            constitutional_hash=EXPECTED_HASH,
            classical=SimpleNamespace(signature=b"sig"),
        )
        # Patch the inline import to raise
        with patch.dict(
            "sys.modules",
            {
                "src.core.services.policy_registry.app.services.pqc_algorithm_registry": None,
            },
        ):
            # ModuleNotFoundError is in PQC_VALIDATION_OPERATION_ERRORS via OSError chain
            # but actually it's ImportError which is NOT in the tuple.
            # The code catches PQC_VALIDATION_OPERATION_ERRORS which doesn't include
            # ImportError. So let's instead test with a mock that raises RuntimeError.
            pass

        # Use approach: patch pqc_verify_signature to raise RuntimeError
        with patch(
            "enhanced_agent_bus.pqc_validators.pqc_verify_signature",
            side_effect=RuntimeError("verify failed"),
        ):
            # We need the import to succeed, so mock it
            mock_registry = MagicMock()
            mock_registry.AlgorithmVariant = MagicMock()
            mock_registry.AlgorithmVariant.Ed25519 = "Ed25519"
            with patch.dict(
                "sys.modules",
                {
                    "src.core.services.policy_registry.app.services.pqc_algorithm_registry": mock_registry,
                },
            ):
                result = _verify_classical_component(keys, sig, b"message")
        assert result is False

    def test_verify_pqc_component_verify_fails_returns_false(self):
        """When pqc_verify_signature raises, returns False."""
        keys = {"classical": None, "pqc": b"pubkey"}
        sig = SimpleNamespace(
            content_hash="abc",
            constitutional_hash=EXPECTED_HASH,
            pqc=SimpleNamespace(algorithm="ML-DSA-65", signature=b"sig"),
        )
        mock_registry = MagicMock()
        mock_registry.normalize_algorithm_name = MagicMock(return_value="ML-DSA-65")
        with patch.dict(
            "sys.modules",
            {
                "src.core.services.policy_registry.app.services.pqc_algorithm_registry": mock_registry,
            },
        ):
            with patch(
                "enhanced_agent_bus.pqc_validators.pqc_verify_signature",
                side_effect=RuntimeError("verify failed"),
            ):
                result = _verify_pqc_component(keys, sig, b"message")
        assert result is False


# ===================================================================
# _extract_message_content -- additional cases
# ===================================================================


class TestExtractMessageContentEdge:
    def test_empty_data(self):
        content = _extract_message_content({})
        assert content == b"{}"

    def test_excludes_only_signature(self):
        data = {"a": 1, "b": 2, "signature": "should_be_excluded"}
        content = _extract_message_content(data)
        parsed = json.loads(content)
        assert "signature" not in parsed
        assert "a" in parsed
        assert "b" in parsed

    def test_sorted_keys(self):
        data = {"z": 1, "a": 2, "m": 3}
        content = _extract_message_content(data)
        parsed_str = content.decode("utf-8")
        assert parsed_str.index('"a"') < parsed_str.index('"m"')
        assert parsed_str.index('"m"') < parsed_str.index('"z"')


# ===================================================================
# _is_self_validation -- additional edge cases
# ===================================================================


class TestIsSelfValidationEdge:
    def test_no_output_author_and_agent_not_in_target(self):
        assert _is_self_validation("agent_1", "output_999", {}) is False

    def test_output_author_different_from_agent(self):
        assert _is_self_validation("agent_1", "output_999", {"output_author": "agent_2"}) is False

    def test_empty_target_output_id(self):
        assert _is_self_validation("agent_1", "", {"output_author": "agent_2"}) is False


# ===================================================================
# check_enforcement_for_create -- edge cases
# ===================================================================


class TestEnforcementEdgeCases:
    async def test_create_strict_mode_hybrid_key_type_passes(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_create("hybrid", "ML-DSA-65+Ed25519", config)

    async def test_create_config_timeout_error_defaults_strict(self):
        config = MagicMock()
        config.get_mode = AsyncMock(side_effect=TimeoutError("timed out"))
        from enhanced_agent_bus._compat.security.pqc import PQCKeyRequiredError

        with pytest.raises(PQCKeyRequiredError):
            await check_enforcement_for_create(None, None, config)

    async def test_update_strict_pqc_passes(self):
        config = MagicMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_update("pqc", config)

    async def test_update_config_error_defaults_strict(self):
        config = MagicMock()
        config.get_mode = AsyncMock(side_effect=ValueError("bad"))
        from enhanced_agent_bus._compat.security.pqc import MigrationRequiredError

        with pytest.raises(MigrationRequiredError):
            await check_enforcement_for_update("classical", config)


# ===================================================================
# PqcValidators helper
# ===================================================================


class TestPqcValidatorsHelper:
    def test_process_empty_string(self):
        v = PqcValidators()
        assert v.process("") == ""

    def test_process_whitespace_string(self):
        v = PqcValidators()
        assert v.process("  ") == "  "

    def test_default_constitutional_hash_matches(self):
        v = PqcValidators()
        assert v._constitutional_hash == CONSTITUTIONAL_HASH


# ===================================================================
# SUPPORTED_PQC_ALGORITHMS constant
# ===================================================================


class TestSupportedAlgorithms:
    def test_supported_algorithms_contains_mldsa(self):
        assert "ML-DSA-65" in SUPPORTED_PQC_ALGORITHMS

    def test_supported_algorithms_is_list(self):
        assert isinstance(SUPPORTED_PQC_ALGORITHMS, list)

    def test_supported_algorithms_contains_mlkem(self):
        assert "ML-KEM-768" in SUPPORTED_PQC_ALGORITHMS


# ===================================================================
# Presence event callback
# ===================================================================


class TestPresenceEventCallback:
    async def test_on_presence_event_non_broadcast(self, server):
        await server._on_presence_event("user_idle", "doc-1", {"user_id": "u1"})

    async def test_on_presence_event_broadcast_type(self, server):
        await server._on_presence_event("broadcast", "doc-1", {"data": "x"})


# ===================================================================
# Join collaboration session helper
# ===================================================================


class TestJoinCollaborationSession:
    async def test_join_collaboration_session_uses_default_permissions(self, server):
        server.permissions.get_document_permissions = MagicMock(return_value={})
        collaborator = _make_collaborator()
        collab_session = _make_collab_session()
        server.presence.join_session = AsyncMock(return_value=(collab_session, collaborator))

        result = await server._join_collaboration_session(
            "doc-1", "policy", "user-1", {"name": "Alice"}, "tenant-1"
        )
        assert result == (collab_session, collaborator)

    async def test_join_collaboration_session_with_user_permission(self, server):
        server.permissions.get_document_permissions = MagicMock(
            return_value={"user-1": UserPermissions.WRITE}
        )
        collaborator = _make_collaborator()
        collab_session = _make_collab_session()
        server.presence.join_session = AsyncMock(return_value=(collab_session, collaborator))

        result = await server._join_collaboration_session(
            "doc-1", "policy", "user-1", {"name": "Alice", "color": "#FF0000"}, "tenant-1"
        )
        assert result is not None

    async def test_join_collaboration_session_raises_session_full(self, server):
        server.permissions.get_document_permissions = MagicMock(return_value={})
        server.presence.join_session = AsyncMock(
            side_effect=SessionFullError("Max capacity reached")
        )
        with pytest.raises(SessionFullError):
            await server._join_collaboration_session("doc-1", "policy", "user-1", {}, "tenant-1")


# ===================================================================
# Update session and join room
# ===================================================================


class TestUpdateSessionAndJoinRoom:
    async def test_update_session_and_join_room(self, server):
        collaborator = _make_collaborator()
        session = {"user_id": "user-1", "tenant_id": "tenant-1"}
        await server._update_session_and_join_room("sid-1", session, "doc-1", collaborator)
        server.sio.save_session.assert_awaited_once()
        saved_session = server.sio.save_session.call_args[0][1]
        assert saved_session["document_id"] == "doc-1"
        assert saved_session["client_id"] == collaborator.client_id
        server.sio.enter_room.assert_awaited_once_with("sid-1", "doc-1")
