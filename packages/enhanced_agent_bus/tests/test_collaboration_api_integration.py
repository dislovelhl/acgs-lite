"""Tests for collaboration.api_integration module.

Constitutional Hash: 608508a9bd224290
"""

import importlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The api_integration module imports CollaborationConfig from the collaboration
# __init__.py, which may not re-export it.  Patch the collaboration package to
# expose CollaborationConfig before importing the module under test.
import enhanced_agent_bus.collaboration as _collab_pkg
from enhanced_agent_bus.collaboration.models import CollaborationConfig

if not hasattr(_collab_pkg, "CollaborationConfig"):
    _collab_pkg.CollaborationConfig = CollaborationConfig  # type: ignore[attr-defined]

_api_integration = importlib.import_module("enhanced_agent_bus.collaboration.api_integration")
CollaborationAPI = _api_integration.CollaborationAPI
_ALLOWED_JWT_ALGORITHMS = _api_integration._ALLOWED_JWT_ALGORITHMS
create_collaboration_app = _api_integration.create_collaboration_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api(secret_key: str = "test-secret-key") -> CollaborationAPI:
    """Create a CollaborationAPI with mocked dependencies."""
    return CollaborationAPI(
        config=MagicMock(),
        redis_client=MagicMock(),
        audit_client=MagicMock(),
        secret_key=secret_key,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestCollaborationAPIInit:
    def test_requires_secret_key(self):
        with patch.dict(os.environ, {"COLLABORATION_SECRET_KEY": ""}, clear=False):
            with pytest.raises(ValueError, match="COLLABORATION_SECRET_KEY is required"):
                CollaborationAPI(secret_key="")

    def test_uses_explicit_secret_key(self):
        api = _make_api("explicit-key")
        assert api.secret_key == "explicit-key"

    def test_uses_env_secret_key(self):
        with patch.dict(os.environ, {"COLLABORATION_SECRET_KEY": "env-key"}, clear=False):
            api = CollaborationAPI()
            assert api.secret_key == "env-key"

    def test_server_starts_as_none(self):
        api = _make_api()
        assert api.server is None


# ---------------------------------------------------------------------------
# Initialize / Shutdown
# ---------------------------------------------------------------------------


class TestInitializeShutdown:
    @pytest.mark.asyncio
    async def test_initialize_creates_server(self):
        api = _make_api()
        with patch(
            "enhanced_agent_bus.collaboration.api_integration.CollaborationServer"
        ) as mock_cls:
            mock_server = AsyncMock()
            mock_cls.return_value = mock_server
            await api.initialize()
            assert api.server is mock_server
            mock_server.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_when_server_exists(self):
        api = _make_api()
        mock_server = AsyncMock()
        api.server = mock_server
        await api.shutdown()
        mock_server.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_when_no_server(self):
        api = _make_api()
        await api.shutdown()  # should not raise


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


class TestValidateToken:
    def test_returns_none_when_jwt_not_installed(self):
        api = _make_api()
        with patch("importlib.import_module", side_effect=ModuleNotFoundError):
            result = api._validate_token("some-token")
            assert result is None

    def test_valid_token_returns_user_data(self):
        api = _make_api()
        mock_jwt = MagicMock()
        mock_jwt.decode.return_value = {
            "sub": "user-1",
            "tenant_id": "tenant-1",
            "permissions": ["read"],
        }
        with patch("importlib.import_module", return_value=mock_jwt):
            with patch.dict(os.environ, {"JWT_ALGORITHM": "RS256"}, clear=False):
                result = api._validate_token("valid-token")
        assert result == {
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "permissions": ["read"],
        }

    def test_expired_token_returns_none(self):
        api = _make_api()
        mock_jwt = MagicMock()
        # Must be real exception classes for except clauses
        mock_jwt.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
        mock_jwt.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
        mock_jwt.decode.side_effect = mock_jwt.ExpiredSignatureError("expired")
        with patch("importlib.import_module", return_value=mock_jwt):
            with patch.dict(os.environ, {"JWT_ALGORITHM": "RS256"}, clear=False):
                result = api._validate_token("expired-token")
        assert result is None

    def test_invalid_token_returns_none(self):
        api = _make_api()
        mock_jwt = MagicMock()
        mock_jwt.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
        mock_jwt.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
        mock_jwt.decode.side_effect = mock_jwt.InvalidTokenError("bad")
        with patch("importlib.import_module", return_value=mock_jwt):
            with patch.dict(os.environ, {"JWT_ALGORITHM": "RS256"}, clear=False):
                result = api._validate_token("bad-token")
        assert result is None

    def test_unsupported_algorithm_returns_none(self):
        api = _make_api()
        mock_jwt = MagicMock()
        mock_jwt.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
        mock_jwt.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
        with patch("importlib.import_module", return_value=mock_jwt):
            with patch.dict(os.environ, {"JWT_ALGORITHM": "HS256"}, clear=False):
                result = api._validate_token("any-token")
        assert result is None

    def test_unexpected_error_returns_none(self):
        api = _make_api()
        mock_jwt = MagicMock()
        mock_jwt.decode.side_effect = RuntimeError("unexpected")
        mock_jwt.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
        mock_jwt.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
        with patch("importlib.import_module", return_value=mock_jwt):
            with patch.dict(os.environ, {"JWT_ALGORITHM": "RS256"}, clear=False):
                result = api._validate_token("any-token")
        assert result is None


# ---------------------------------------------------------------------------
# Allowed JWT algorithms constant
# ---------------------------------------------------------------------------


class TestAllowedAlgorithms:
    def test_contains_expected_algorithms(self):
        assert "RS256" in _ALLOWED_JWT_ALGORITHMS
        assert "ES256" in _ALLOWED_JWT_ALGORITHMS
        assert "EdDSA" in _ALLOWED_JWT_ALGORITHMS

    def test_rejects_symmetric_algorithms(self):
        assert "HS256" not in _ALLOWED_JWT_ALGORITHMS
        assert "HS512" not in _ALLOWED_JWT_ALGORITHMS


# ---------------------------------------------------------------------------
# Ensure server initialized helper
# ---------------------------------------------------------------------------


class TestEnsureServerInitialized:
    def test_raises_503_when_no_server(self):
        api = _make_api()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            api._ensure_server_initialized()
        assert exc_info.value.status_code == 503

    def test_passes_when_server_exists(self):
        api = _make_api()
        api.server = MagicMock()
        api._ensure_server_initialized()  # should not raise


# ---------------------------------------------------------------------------
# Handler endpoints
# ---------------------------------------------------------------------------


class TestHandlers:
    @pytest.mark.asyncio
    async def test_health_check(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.health_check.return_value = {"status": "ok"}
        result = await api._handle_health_check()
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.presence.get_all_sessions.return_value = [{"id": "s1"}]
        result = await api._handle_list_sessions({"user_id": "u1"})
        assert result == [{"id": "s1"}]

    @pytest.mark.asyncio
    async def test_get_session_found(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.presence.get_session_stats.return_value = {"exists": True, "users": 2}
        result = await api._handle_get_session("doc-1", {"user_id": "u1"})
        assert result["exists"] is True

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.presence.get_session_stats.return_value = {"exists": False}
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await api._handle_get_session("doc-missing", {"user_id": "u1"})
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_session_users(self):
        api = _make_api()
        api.server = AsyncMock()
        mock_user = MagicMock()
        mock_user.to_dict.return_value = {"user_id": "u1"}
        api.server.presence.get_all_users.return_value = [mock_user]
        result = await api._handle_get_session_users("doc-1", {"user_id": "u1"})
        assert result == [{"user_id": "u1"}]

    @pytest.mark.asyncio
    async def test_lock_document_success(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.presence.get_session.return_value = MagicMock()
        api.server.permissions.lock_document.return_value = True
        result = await api._handle_lock_document("doc-1", {"user_id": "u1"})
        assert result == {"locked": True}

    @pytest.mark.asyncio
    async def test_lock_document_session_not_found(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.presence.get_session.return_value = None
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await api._handle_lock_document("doc-missing", {"user_id": "u1"})
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_lock_document_permission_denied(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.presence.get_session.return_value = MagicMock()
        from enhanced_agent_bus.collaboration.models import CollaborationError

        api.server.permissions.lock_document.side_effect = CollaborationError("forbidden")
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await api._handle_lock_document("doc-1", {"user_id": "u1"})
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unlock_document_success(self):
        api = _make_api()
        api.server = AsyncMock()
        api.server.presence.get_session.return_value = MagicMock()
        api.server.permissions.unlock_document.return_value = True
        result = await api._handle_unlock_document("doc-1", {"user_id": "u1"})
        assert result == {"unlocked": True}

    @pytest.mark.asyncio
    async def test_get_document_history(self):
        api = _make_api()
        api.server = AsyncMock()
        mock_op = MagicMock()
        mock_op.to_dict.return_value = {"version": 1}
        api.server.sync.get_operation_history.return_value = [mock_op]
        result = await api._handle_get_document_history("doc-1", 0, {"user_id": "u1"})
        assert result == [{"version": 1}]


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------


class TestRouteHelpers:
    def test_is_history_endpoint(self):
        api = _make_api()
        assert api._is_history_endpoint("/collaboration/documents/{document_id}/history") is True
        assert api._is_history_endpoint("/collaboration/sessions/{document_id}") is False

    def test_has_document_id(self):
        api = _make_api()
        assert api._has_document_id("/collaboration/sessions/{document_id}") is True
        assert api._has_document_id("/collaboration/health") is False


# ---------------------------------------------------------------------------
# register_routes / mount_to_app
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    def test_register_routes_adds_routes(self):
        api = _make_api()
        mock_app = MagicMock()
        # Each method call returns a decorator that is then called with the route func
        mock_app.get.return_value = lambda f: f
        mock_app.post.return_value = lambda f: f
        api.register_routes(mock_app)
        # Should have called get/post multiple times
        assert mock_app.get.call_count >= 4
        assert mock_app.post.call_count >= 2

    def test_mount_to_app_registers_routes_and_lifecycle_handlers(self):
        api = _make_api()
        mock_app = MagicMock()
        mock_app.get.return_value = lambda f: f
        mock_app.post.return_value = lambda f: f
        lifecycle_handlers: dict[str, object] = {}
        mock_app.add_event_handler.side_effect = lifecycle_handlers.__setitem__
        api.mount_to_app(mock_app)
        assert mock_app.get.call_count >= 4
        assert set(lifecycle_handlers) == {"startup", "shutdown"}

    @pytest.mark.asyncio
    async def test_mount_to_app_startup_initializes_and_mounts_socket_app(self):
        api = _make_api()
        mock_app = MagicMock()
        mock_app.get.return_value = lambda f: f
        mock_app.post.return_value = lambda f: f
        lifecycle_handlers: dict[str, object] = {}
        mock_app.add_event_handler.side_effect = lifecycle_handlers.__setitem__

        socket_app = MagicMock()
        mock_server = MagicMock()
        mock_server.get_asgi_app.return_value = socket_app

        async def initialize_server() -> None:
            api.server = mock_server

        api.initialize = AsyncMock(side_effect=initialize_server)
        api.shutdown = AsyncMock()

        api.mount_to_app(mock_app, path="/embedded-collaboration")

        await lifecycle_handlers["startup"]()
        api.initialize.assert_awaited_once()
        mock_app.mount.assert_called_once_with("/embedded-collaboration", socket_app)

        await lifecycle_handlers["shutdown"]()
        api.shutdown.assert_awaited_once()


# ---------------------------------------------------------------------------
# create_collaboration_app factory
# ---------------------------------------------------------------------------


class TestCreateCollaborationApp:
    def test_returns_fastapi_app(self):
        app = create_collaboration_app(secret_key="test-key")
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)
