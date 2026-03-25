"""
Tests for MCP Auth Injector.
Constitutional Hash: 608508a9bd224290
"""

import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.mcp_integration.auth.auth_audit import AuditLoggerConfig
from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
    AuthContext,
    AuthInjector,
    AuthInjectorConfig,
    AuthMethod,
    InjectionResult,
    InjectionStatus,
)
from enhanced_agent_bus.mcp_integration.auth.credential_manager import CredentialManagerConfig

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestAuthMethod:
    """Tests for AuthMethod enum."""

    def test_values(self):
        assert AuthMethod.NONE.value == "none"
        assert AuthMethod.API_KEY.value == "api_key"
        assert AuthMethod.OAUTH2.value == "oauth2"
        assert AuthMethod.OIDC.value == "oidc"
        assert AuthMethod.BEARER_TOKEN.value == "bearer_token"
        assert AuthMethod.BASIC_AUTH.value == "basic_auth"
        assert AuthMethod.CUSTOM.value == "custom"


class TestInjectionStatus:
    """Tests for InjectionStatus enum."""

    def test_values(self):
        assert InjectionStatus.SUCCESS.value == "success"
        assert InjectionStatus.FAILED.value == "failed"
        assert InjectionStatus.NO_CREDENTIALS.value == "no_credentials"
        assert InjectionStatus.SKIPPED.value == "skipped"
        assert InjectionStatus.EXPIRED.value == "expired"


# ---------------------------------------------------------------------------
# AuthContext tests
# ---------------------------------------------------------------------------


class TestAuthContext:
    """Tests for AuthContext dataclass."""

    def test_defaults(self):
        ctx = AuthContext()
        assert ctx.tool_name is None
        assert ctx.tool_id is None
        assert ctx.agent_id is None
        assert ctx.auth_method == AuthMethod.NONE
        assert ctx.required_scopes == []
        assert ctx.scopes == []

    def test_get_tool_name_from_tool_name(self):
        ctx = AuthContext(tool_name="my_tool")
        assert ctx.get_tool_name() == "my_tool"

    def test_get_tool_name_from_tool_id(self):
        ctx = AuthContext(tool_id="tool_123")
        assert ctx.get_tool_name() == "tool_123"

    def test_get_tool_name_fallback(self):
        ctx = AuthContext()
        assert ctx.get_tool_name() == "unknown"

    def test_get_scopes_from_required(self):
        ctx = AuthContext(required_scopes=["read", "write"])
        assert ctx.get_scopes() == ["read", "write"]

    def test_get_scopes_from_alias(self):
        ctx = AuthContext(scopes=["admin"])
        assert ctx.get_scopes() == ["admin"]

    def test_get_scopes_empty(self):
        ctx = AuthContext()
        assert ctx.get_scopes() == []

    def test_metadata(self):
        ctx = AuthContext(metadata={"key": "value"})
        assert ctx.metadata == {"key": "value"}

    def test_constitutional_hash(self):
        ctx = AuthContext()
        assert ctx.constitutional_hash is not None


# ---------------------------------------------------------------------------
# InjectionResult tests
# ---------------------------------------------------------------------------


class TestInjectionResult:
    """Tests for InjectionResult dataclass."""

    def test_success_property(self):
        result = InjectionResult(status=InjectionStatus.SUCCESS, auth_method=AuthMethod.API_KEY)
        assert result.success is True

    def test_failure_property(self):
        result = InjectionResult(status=InjectionStatus.FAILED, auth_method=AuthMethod.API_KEY)
        assert result.success is False

    def test_aliases(self):
        result = InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.API_KEY,
            modified_headers={"Authorization": "***"},
            modified_params={"key": "***"},
            modified_body={"token": "***"},
        )
        assert result.injected_headers == {"Authorization": "***"}
        assert result.injected_params == {"key": "***"}
        assert result.injected_body == {"token": "***"}

    def test_to_dict(self):
        result = InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.OAUTH2,
            modified_headers={"Authorization": "Bearer ***"},
            credentials_used=["oauth2:provider1"],
            duration_ms=5.0,
        )
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["success"] is True
        assert d["auth_method"] == "oauth2"
        assert d["has_modified_headers"] is True
        assert d["credentials_used"] == ["oauth2:provider1"]
        assert d["duration_ms"] == 5.0

    def test_to_dict_with_error(self):
        result = InjectionResult(
            status=InjectionStatus.FAILED,
            auth_method=AuthMethod.OIDC,
            error="Provider not found",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Provider not found"


# ---------------------------------------------------------------------------
# AuthInjectorConfig tests
# ---------------------------------------------------------------------------


class TestAuthInjectorConfig:
    """Tests for AuthInjectorConfig."""

    def test_defaults(self):
        config = AuthInjectorConfig()
        assert config.credential_config is None
        assert config.oauth2_providers == {}
        assert config.oidc_providers == {}
        assert config.enable_audit is True
        assert config.fail_on_auth_error is True
        assert config.retry_on_401 is True
        assert config.auto_refresh_enabled is True
        assert config.default_oauth2_provider is None
        assert config.default_oidc_provider is None


# ---------------------------------------------------------------------------
# AuthInjector tests
# ---------------------------------------------------------------------------


def _make_injector(tmp_path: str, enable_audit: bool = False) -> AuthInjector:
    """Create an AuthInjector with temp storage paths to avoid PermissionError."""
    config = AuthInjectorConfig(
        credential_config=CredentialManagerConfig(storage_path=f"{tmp_path}/creds"),
        audit_config=AuditLoggerConfig(storage_path=f"{tmp_path}/audit") if enable_audit else None,
        enable_audit=enable_audit,
    )
    return AuthInjector(config=config)


class TestAuthInjector:
    """Tests for AuthInjector."""

    @pytest.fixture
    def tmp_dir(self, tmp_path):
        return str(tmp_path)

    def test_init_defaults(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        assert injector._stats["injections_attempted"] == 0
        assert injector._stats["injections_successful"] == 0
        assert injector._stats["injections_failed"] == 0

    def test_init_with_config(self, tmp_dir):
        injector = _make_injector(tmp_dir, enable_audit=False)
        assert injector._audit_logger is None

    def test_configure_tool_auth(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector.configure_tool_auth(
            tool_name="my_tool",
            auth_method=AuthMethod.API_KEY,
            scopes=["read"],
        )
        assert "my_tool" in injector._tool_auth_configs
        config = injector._tool_auth_configs["my_tool"]
        assert config["auth_method"] == AuthMethod.API_KEY
        assert config["scopes"] == ["read"]

    @pytest.mark.asyncio
    async def test_inject_auth_none(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        ctx = AuthContext(tool_name="my_tool", auth_method=AuthMethod.NONE)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SKIPPED
        assert result.auth_method == AuthMethod.NONE

    @pytest.mark.asyncio
    async def test_inject_auth_unsupported_method(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        ctx = AuthContext(tool_name="my_tool", auth_method=AuthMethod.CUSTOM)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "Unsupported" in (result.error or "")

    @pytest.mark.asyncio
    async def test_inject_auth_oauth2_no_provider(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        ctx = AuthContext(
            tool_name="my_tool",
            auth_method=AuthMethod.OAUTH2,
            provider_name="nonexistent",
        )
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_inject_auth_oidc_no_provider(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        ctx = AuthContext(
            tool_name="my_tool",
            auth_method=AuthMethod.OIDC,
            provider_name="nonexistent",
        )
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_inject_auth_stats_updated(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        ctx = AuthContext(tool_name="tool", auth_method=AuthMethod.NONE)
        await injector.inject_auth(ctx)
        assert injector._stats["injections_attempted"] == 1

    @pytest.mark.asyncio
    async def test_inject_auth_credentials_no_creds(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector._credential_manager.inject_credentials = AsyncMock(
            return_value={"headers": {}, "params": {}, "body": {}}
        )
        ctx = AuthContext(tool_name="my_tool", auth_method=AuthMethod.API_KEY)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.NO_CREDENTIALS

    @pytest.mark.asyncio
    async def test_inject_auth_credentials_success(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector._credential_manager.inject_credentials = AsyncMock(
            return_value={
                "headers": {"Authorization": "Bearer token"},
                "params": {},
                "body": {},
            }
        )
        ctx = AuthContext(tool_name="my_tool", auth_method=AuthMethod.BEARER_TOKEN)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_inject_auth_exception_handled(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector._credential_manager.inject_credentials = AsyncMock(
            side_effect=RuntimeError("cred fail")
        )
        ctx = AuthContext(tool_name="my_tool", auth_method=AuthMethod.API_KEY)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert result.error is not None

    def test_get_stats(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        stats = injector.get_stats()
        assert "injections_attempted" in stats
        assert "oauth2_providers" in stats
        assert "constitutional_hash" in stats

    def test_add_oauth2_provider(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        mock_config = MagicMock()
        injector.add_oauth2_provider("test_provider", mock_config)
        assert "test_provider" in injector._oauth2_providers

    def test_remove_provider_oauth2(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        mock_config = MagicMock()
        injector.add_oauth2_provider("test_provider", mock_config)
        assert injector.remove_provider("test_provider") is True
        assert "test_provider" not in injector._oauth2_providers

    def test_remove_provider_not_found(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        assert injector.remove_provider("nonexistent") is False

    @pytest.mark.asyncio
    async def test_acquire_oauth2_token_no_provider(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        result = await injector.acquire_oauth2_token("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_oidc_authorization_url_no_provider(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        result = await injector.get_oidc_authorization_url(
            "nonexistent", "https://example.com/callback"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_oidc_callback_no_provider(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        result = await injector.handle_oidc_callback(
            "nonexistent", "code", "https://example.com/callback"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_tool_auth_status_unconfigured(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector._token_refresher.list_tokens = MagicMock(return_value=[])
        injector._credential_manager.list_credentials = MagicMock(return_value=[])
        status = await injector.get_tool_auth_status("unknown_tool")
        assert status["configured"] is False
        assert status["auth_method"] == "none"

    @pytest.mark.asyncio
    async def test_get_tool_auth_status_configured(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector.configure_tool_auth("my_tool", AuthMethod.OAUTH2, scopes=["read"])
        injector._token_refresher.list_tokens = MagicMock(return_value=[])
        injector._credential_manager.list_credentials = MagicMock(return_value=[])
        status = await injector.get_tool_auth_status("my_tool")
        assert status["configured"] is True
        assert status["auth_method"] == "oauth2"

    @pytest.mark.asyncio
    async def test_revoke_auth(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector.configure_tool_auth("my_tool", AuthMethod.API_KEY)
        injector._token_refresher.list_tokens = MagicMock(return_value=[])
        injector._token_refresher.unregister_token = AsyncMock()
        injector._credential_manager.revoke_tool_credentials = AsyncMock()

        result = await injector.revoke_auth(tool_id="my_tool")
        assert result["success"] is True
        assert result["revoked_configs"] == 1
        assert "my_tool" not in injector._tool_auth_configs

    @pytest.mark.asyncio
    async def test_revoke_auth_with_tokens(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector._token_refresher.list_tokens = MagicMock(
            return_value=[{"token_id": "oauth2:provider:my_tool:default"}]
        )
        injector._token_refresher.unregister_token = AsyncMock()
        injector._credential_manager.revoke_tool_credentials = AsyncMock()

        result = await injector.revoke_auth(tool_id="my_tool")
        assert result["revoked_tokens"] == 1

    @pytest.mark.asyncio
    async def test_start_and_stop(self, tmp_dir):
        injector = _make_injector(tmp_dir)
        injector._token_refresher.start = AsyncMock()
        injector._token_refresher.stop = AsyncMock()
        injector._credential_manager.load_credentials = AsyncMock()

        await injector.start()
        injector._token_refresher.start.assert_awaited_once()
        injector._credential_manager.load_credentials.assert_awaited_once()

        await injector.stop()
        injector._token_refresher.stop.assert_awaited_once()
