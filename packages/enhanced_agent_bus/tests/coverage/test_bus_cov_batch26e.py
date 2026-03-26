"""
Coverage tests for:
1. mcp_integration/auth/auth_injector.py
2. constitutional/metrics_collector.py
3. adaptive_governance/threshold_manager.py

asyncio_mode = "auto" -- no @pytest.mark.asyncio decorator needed.
"""

import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# 1. auth_injector.py
# ---------------------------------------------------------------------------


class TestAuthContextAndInjectionResult:
    """Test AuthContext helpers and InjectionResult properties/to_dict."""

    def test_auth_context_get_tool_name_from_tool_name(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(tool_name="my_tool")
        assert ctx.get_tool_name() == "my_tool"

    def test_auth_context_get_tool_name_from_tool_id(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(tool_id="id_tool")
        assert ctx.get_tool_name() == "id_tool"

    def test_auth_context_get_tool_name_fallback(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext()
        assert ctx.get_tool_name() == "unknown"

    def test_auth_context_get_scopes_required(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(required_scopes=["read", "write"])
        assert ctx.get_scopes() == ["read", "write"]

    def test_auth_context_get_scopes_alias(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(scopes=["admin"])
        assert ctx.get_scopes() == ["admin"]

    def test_auth_context_get_scopes_empty(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext()
        assert ctx.get_scopes() == []

    def test_injection_result_success_property(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthMethod,
            InjectionResult,
            InjectionStatus,
        )

        r = InjectionResult(status=InjectionStatus.SUCCESS, auth_method=AuthMethod.OAUTH2)
        assert r.success is True

    def test_injection_result_failed_not_success(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthMethod,
            InjectionResult,
            InjectionStatus,
        )

        r = InjectionResult(status=InjectionStatus.FAILED, auth_method=AuthMethod.NONE)
        assert r.success is False

    def test_injection_result_aliases(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthMethod,
            InjectionResult,
            InjectionStatus,
        )

        r = InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.API_KEY,
            modified_headers={"Authorization": "***"},
            modified_params={"key": "***"},
            modified_body={"token": "***"},
        )
        assert r.injected_headers == {"Authorization": "***"}
        assert r.injected_params == {"key": "***"}
        assert r.injected_body == {"token": "***"}

    def test_injection_result_to_dict(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthMethod,
            InjectionResult,
            InjectionStatus,
        )

        r = InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.BEARER_TOKEN,
            modified_headers={"Authorization": "***"},
            credentials_used=["cred1"],
            error=None,
            duration_ms=12.5,
        )
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["success"] is True
        assert d["auth_method"] == "bearer_token"
        assert d["has_modified_headers"] is True
        assert d["has_modified_params"] is False
        assert d["has_modified_body"] is False
        assert d["credentials_used"] == ["cred1"]
        assert d["duration_ms"] == 12.5


class TestAuthInjector:
    """Test AuthInjector methods."""

    def _make_injector(self, **kwargs):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthInjector,
            AuthInjectorConfig,
        )

        config = AuthInjectorConfig(**kwargs)
        return AuthInjector(config)

    def test_init_default(self):
        injector = self._make_injector()
        assert injector._stats["injections_attempted"] == 0

    def test_init_audit_disabled(self):
        injector = self._make_injector(enable_audit=False)
        assert injector._audit_logger is None

    def test_configure_tool_auth(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        injector = self._make_injector()
        injector.configure_tool_auth("tool_a", AuthMethod.OAUTH2, scopes=["read"])
        assert "tool_a" in injector._tool_auth_configs
        assert injector._tool_auth_configs["tool_a"]["auth_method"] == AuthMethod.OAUTH2

    async def test_inject_auth_none_method_skips(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.NONE)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SKIPPED

    async def test_inject_auth_unsupported_method(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.CUSTOM)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "Unsupported" in result.error

    async def test_inject_auth_oauth2_no_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.OAUTH2)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "not found" in result.error

    async def test_inject_auth_oidc_no_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.OIDC)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "not found" in result.error

    async def test_inject_auth_api_key_credentials(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        # Mock credential manager inject_credentials
        injector._credential_manager.inject_credentials = AsyncMock(
            return_value={
                "headers": {"X-API-Key": "secret"},
                "params": {},
                "body": {},
            }
        )
        ctx = AuthContext(tool_name="tool_x", auth_method=AuthMethod.API_KEY)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS
        assert result.credentials_used == ["tool_x"]

    async def test_inject_auth_bearer_token_no_credentials(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        injector._credential_manager.inject_credentials = AsyncMock(
            return_value={
                "headers": {},
                "params": {},
                "body": {},
            }
        )
        ctx = AuthContext(tool_name="tool_y", auth_method=AuthMethod.BEARER_TOKEN)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.NO_CREDENTIALS

    async def test_inject_auth_basic_auth(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        injector._credential_manager.inject_credentials = AsyncMock(
            return_value={
                "headers": {"Authorization": "Basic abc"},
                "params": {},
                "body": {},
            }
        )
        ctx = AuthContext(tool_name="tool_z", auth_method=AuthMethod.BASIC_AUTH)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS

    async def test_inject_auth_exception_handling(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        injector._credential_manager.inject_credentials = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        ctx = AuthContext(tool_name="tool_err", auth_method=AuthMethod.API_KEY)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "boom" in result.error

    async def test_inject_auth_with_audit_logging(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=True)
        injector._audit_logger.log_event = AsyncMock()
        injector._credential_manager.inject_credentials = AsyncMock(
            return_value={
                "headers": {"Authorization": "Bearer x"},
                "params": {},
                "body": {},
            }
        )
        ctx = AuthContext(
            tool_name="t",
            auth_method=AuthMethod.BEARER_TOKEN,
            agent_id="a1",
            tenant_id="ten1",
            session_id="s1",
            request_id="r1",
            source_ip="127.0.0.1",
        )
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS
        injector._audit_logger.log_event.assert_called_once()

    async def test_inject_auth_stats_tracking(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
        )

        injector = self._make_injector(enable_audit=False)
        injector._credential_manager.inject_credentials = AsyncMock(
            return_value={
                "headers": {"X-Key": "val"},
                "params": {},
                "body": {},
            }
        )
        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.API_KEY)
        await injector.inject_auth(ctx)
        assert injector._stats["injections_attempted"] == 1
        assert injector._stats["injections_successful"] == 1

    async def test_inject_oauth2_success(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )
        from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Token

        injector = self._make_injector(enable_audit=False)

        # Add mock provider
        mock_provider = MagicMock()
        mock_token = MagicMock(spec=OAuth2Token)
        mock_token.access_token = "tok123"
        mock_token.token_type = "Bearer"
        mock_token.is_expired.return_value = False
        mock_provider.acquire_token = AsyncMock(return_value=mock_token)
        injector._oauth2_providers["my_oauth"] = mock_provider

        # Mock token refresher
        injector._token_refresher.get_token = MagicMock(return_value=None)
        injector._token_refresher.register_token = AsyncMock()

        ctx = AuthContext(
            tool_name="t",
            auth_method=AuthMethod.OAUTH2,
            provider_name="my_oauth",
        )
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS
        assert "oauth2:my_oauth" in result.credentials_used
        assert injector._stats["oauth2_tokens_acquired"] == 1

    async def test_inject_oauth2_cached_token(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        mock_provider = MagicMock()
        injector._oauth2_providers["cached_p"] = mock_provider

        mock_token = MagicMock()
        mock_token.is_expired.return_value = False
        mock_token.access_token = "cached_tok"
        mock_token.token_type = "Bearer"
        injector._token_refresher.get_token = MagicMock(return_value=mock_token)

        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.OAUTH2, provider_name="cached_p")
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS
        # Should not have acquired new token
        mock_provider.acquire_token.assert_not_called()

    async def test_inject_oauth2_token_acquisition_fails(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        mock_provider = MagicMock()
        mock_provider.acquire_token = AsyncMock(return_value=None)
        injector._oauth2_providers["fail_p"] = mock_provider
        injector._token_refresher.get_token = MagicMock(return_value=None)

        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.OAUTH2, provider_name="fail_p")
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "Failed to acquire OAuth2 token" in result.error

    async def test_inject_oidc_success(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)

        mock_provider = MagicMock()
        mock_oauth2_token = MagicMock()
        mock_oauth2_token.access_token = "oidc_tok"
        mock_oauth2_token.is_expired.return_value = False
        mock_oidc_tokens = MagicMock()
        mock_oidc_tokens.oauth2_token = mock_oauth2_token
        mock_provider.acquire_tokens = AsyncMock(return_value=mock_oidc_tokens)
        mock_provider._oauth2_provider = MagicMock()
        injector._oidc_providers["my_oidc"] = mock_provider

        injector._token_refresher.get_managed_token = MagicMock(return_value=None)
        injector._token_refresher.register_token = AsyncMock()

        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.OIDC, provider_name="my_oidc")
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS
        assert "oidc:my_oidc" in result.credentials_used
        assert injector._stats["oidc_tokens_acquired"] == 1

    async def test_inject_oidc_cached_managed_token(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        mock_provider = MagicMock()
        injector._oidc_providers["cached_oidc"] = mock_provider

        mock_managed = MagicMock()
        mock_managed.token.is_expired.return_value = False
        mock_managed.token.access_token = "cached_oidc_tok"
        injector._token_refresher.get_managed_token = MagicMock(return_value=mock_managed)

        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.OIDC, provider_name="cached_oidc")
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SUCCESS

    async def test_inject_oidc_token_acquisition_fails(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector(enable_audit=False)
        mock_provider = MagicMock()
        mock_provider.acquire_tokens = AsyncMock(return_value=None)
        injector._oidc_providers["fail_oidc"] = mock_provider
        injector._token_refresher.get_managed_token = MagicMock(return_value=None)

        ctx = AuthContext(tool_name="t", auth_method=AuthMethod.OIDC, provider_name="fail_oidc")
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "Failed to acquire OIDC token" in result.error

    async def test_start_and_stop(self):
        injector = self._make_injector(enable_audit=False)
        injector._token_refresher.start = AsyncMock()
        injector._token_refresher.stop = AsyncMock()
        injector._credential_manager.load_credentials = AsyncMock()
        await injector.start()
        injector._token_refresher.start.assert_called_once()
        injector._credential_manager.load_credentials.assert_called_once()
        await injector.stop()
        injector._token_refresher.stop.assert_called_once()

    async def test_start_oidc_discovery_failure(self):
        injector = self._make_injector(enable_audit=False)
        injector._token_refresher.start = AsyncMock()
        injector._credential_manager.load_credentials = AsyncMock()
        mock_provider = MagicMock()
        mock_provider.discover = AsyncMock(side_effect=RuntimeError("discovery fail"))
        injector._oidc_providers["bad"] = mock_provider
        await injector.start()  # Should not raise

    async def test_acquire_oauth2_token_not_found(self):
        injector = self._make_injector()
        result = await injector.acquire_oauth2_token("nonexistent")
        assert result is None

    async def test_acquire_oauth2_token_found(self):
        injector = self._make_injector()
        mock_provider = MagicMock()
        mock_provider.acquire_token = AsyncMock(return_value="token_obj")
        injector._oauth2_providers["p1"] = mock_provider
        result = await injector.acquire_oauth2_token("p1", scopes=["s"])
        assert result == "token_obj"

    async def test_get_oidc_authorization_url_not_found(self):
        injector = self._make_injector()
        result = await injector.get_oidc_authorization_url("nope", "http://cb")
        assert result is None

    async def test_get_oidc_authorization_url_found(self):
        injector = self._make_injector()
        mock_provider = MagicMock()
        mock_provider.build_authorization_url.return_value = ("url", "state", "nonce")
        injector._oidc_providers["o1"] = mock_provider
        result = await injector.get_oidc_authorization_url("o1", "http://cb")
        assert result == ("url", "state", "nonce")

    async def test_handle_oidc_callback_not_found(self):
        injector = self._make_injector()
        result = await injector.handle_oidc_callback("nope", "code", "http://cb")
        assert result is None

    async def test_handle_oidc_callback_success_with_audit(self):
        injector = self._make_injector(enable_audit=True)
        mock_provider = MagicMock()
        mock_tokens = MagicMock()
        mock_tokens.subject = "user1"
        mock_tokens.validated = True
        mock_provider.acquire_tokens = AsyncMock(return_value=mock_tokens)
        injector._oidc_providers["o2"] = mock_provider
        injector._audit_logger.log_event = AsyncMock()
        result = await injector.handle_oidc_callback("o2", "code", "http://cb")
        assert result == mock_tokens
        injector._audit_logger.log_event.assert_called_once()

    async def test_store_api_key(self):
        injector = self._make_injector()
        injector._credential_manager.store_credential = AsyncMock(return_value="cred_obj")
        result = await injector.store_api_key("k1", "secret", ["tool1"])
        assert result == "cred_obj"

    async def test_store_bearer_token(self):
        injector = self._make_injector()
        injector._credential_manager.store_credential = AsyncMock(return_value="cred_obj")
        result = await injector.store_bearer_token("bt1", "tok", ["tool2"])
        assert result == "cred_obj"

    async def test_store_basic_auth(self):
        injector = self._make_injector()
        injector._credential_manager.store_credential = AsyncMock(return_value="cred_obj")
        result = await injector.store_basic_auth("ba1", "user", "pass", ["tool3"])
        assert result == "cred_obj"

    def test_add_oauth2_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Config

        injector = self._make_injector()
        config = OAuth2Config(
            client_id="cid",
            client_secret="csec",
            token_endpoint="http://tok",
        )
        injector.add_oauth2_provider("new_p", config)
        assert "new_p" in injector._oauth2_providers

    async def test_add_oidc_provider(self):
        from enhanced_agent_bus.mcp_integration.auth.oidc_provider import OIDCConfig

        injector = self._make_injector()
        config = OIDCConfig(
            issuer_url="http://issuer",
            client_id="cid",
            client_secret="csec",
        )
        with patch.object(
            injector.__class__,
            "add_oidc_provider",
            new=injector.__class__.add_oidc_provider,
        ):
            mock_provider_cls = MagicMock()
            mock_instance = MagicMock()
            mock_instance.discover = AsyncMock()
            with patch(
                "enhanced_agent_bus.mcp_integration.auth.auth_injector.OIDCProvider",
                return_value=mock_instance,
            ):
                await injector.add_oidc_provider("new_oidc", config, discover=True)
                assert "new_oidc" in injector._oidc_providers
                mock_instance.discover.assert_called_once()

    async def test_add_oidc_provider_no_discover(self):
        from enhanced_agent_bus.mcp_integration.auth.oidc_provider import OIDCConfig

        injector = self._make_injector()
        config = OIDCConfig(
            issuer_url="http://issuer",
            client_id="cid",
            client_secret="csec",
        )
        mock_instance = MagicMock()
        mock_instance.discover = AsyncMock()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.auth_injector.OIDCProvider",
            return_value=mock_instance,
        ):
            await injector.add_oidc_provider("no_disc", config, discover=False)
            assert "no_disc" in injector._oidc_providers
            mock_instance.discover.assert_not_called()

    def test_remove_provider_oauth2(self):
        injector = self._make_injector()
        injector._oauth2_providers["rm_p"] = MagicMock()
        assert injector.remove_provider("rm_p") is True
        assert "rm_p" not in injector._oauth2_providers

    def test_remove_provider_oidc(self):
        injector = self._make_injector()
        injector._oidc_providers["rm_o"] = MagicMock()
        assert injector.remove_provider("rm_o") is True

    def test_remove_provider_not_found(self):
        injector = self._make_injector()
        assert injector.remove_provider("nope") is False

    def test_get_stats(self):
        injector = self._make_injector()
        injector._credential_manager.get_stats = MagicMock(return_value={})
        injector._token_refresher.get_stats = MagicMock(return_value={})
        stats = injector.get_stats()
        assert "injections_attempted" in stats
        assert "oauth2_providers" in stats
        assert "constitutional_hash" in stats

    async def test_get_health(self):
        injector = self._make_injector()
        injector._token_refresher.list_tokens = MagicMock(return_value=[])
        injector._credential_manager.list_credentials = MagicMock(return_value=[])
        health = await injector.get_health()
        assert health["healthy"] is True

    async def test_get_health_with_providers(self):
        injector = self._make_injector()
        mock_oauth = MagicMock()
        mock_oauth.get_stats.return_value = {"calls": 1}
        injector._oauth2_providers["op"] = mock_oauth

        mock_oidc = MagicMock()
        mock_oidc.get_metadata.return_value = {"issuer": "x"}
        mock_oidc.get_stats.return_value = {"calls": 2}
        injector._oidc_providers["oidcp"] = mock_oidc

        injector._token_refresher.list_tokens = MagicMock(return_value=[])
        injector._credential_manager.list_credentials = MagicMock(return_value=[])
        health = await injector.get_health()
        assert "op" in health["oauth2_providers"]
        assert health["oidc_providers"]["oidcp"]["discovered"] is True

    async def test_get_tool_auth_status_unconfigured(self):
        injector = self._make_injector()
        injector._token_refresher.list_tokens = MagicMock(return_value=[])
        injector._credential_manager.list_credentials = MagicMock(return_value=[])
        status = await injector.get_tool_auth_status("tool_x")
        assert status["configured"] is False
        assert status["auth_method"] == "none"

    async def test_get_tool_auth_status_configured(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        injector = self._make_injector()
        injector.configure_tool_auth("tool_c", AuthMethod.OAUTH2, provider_name="p1", scopes=["r"])
        injector._token_refresher.list_tokens = MagicMock(
            return_value=[
                {"token_id": "oauth2:p1:tool_c:default", "status": "active"},
            ]
        )
        mock_cred = MagicMock()
        mock_cred.name = "cred1"
        mock_cred.credential_type.value = "api_key"
        mock_cred.status.value = "active"
        injector._credential_manager.list_credentials = MagicMock(return_value=[mock_cred])
        status = await injector.get_tool_auth_status("tool_c")
        assert status["configured"] is True
        assert status["tokens_managed"] == 1
        assert status["credentials_available"] == 1

    async def test_revoke_auth_by_tool_id(self):
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        injector = self._make_injector(enable_audit=True)
        injector.configure_tool_auth("rev_tool", AuthMethod.API_KEY)
        injector._token_refresher.list_tokens = MagicMock(
            return_value=[
                {"token_id": "oauth2:p:rev_tool:default"},
            ]
        )
        injector._token_refresher.unregister_token = AsyncMock()
        injector._credential_manager.revoke_tool_credentials = AsyncMock()
        injector._audit_logger.log_event = AsyncMock()

        result = await injector.revoke_auth(tool_id="rev_tool")
        assert result["success"] is True
        assert result["revoked_tokens"] == 1
        assert result["revoked_configs"] == 1
        injector._audit_logger.log_event.assert_called_once()

    async def test_revoke_auth_by_agent_id(self):
        injector = self._make_injector(enable_audit=False)
        injector._token_refresher.list_tokens = MagicMock(
            return_value=[
                {"token_id": "oidc:p:t:agent_abc"},
            ]
        )
        injector._token_refresher.unregister_token = AsyncMock()
        result = await injector.revoke_auth(agent_id="agent_abc")
        assert result["revoked_tokens"] == 1

    async def test_revoke_auth_no_match(self):
        injector = self._make_injector(enable_audit=False)
        injector._token_refresher.list_tokens = MagicMock(return_value=[])
        result = await injector.revoke_auth(tool_id="nonexistent")
        assert result["revoked_tokens"] == 0


# ---------------------------------------------------------------------------
# 2. metrics_collector.py
# ---------------------------------------------------------------------------


class TestGovernanceMetricsSnapshot:
    """Test GovernanceMetricsSnapshot properties."""

    def test_meets_targets_true(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=4.0,
            deliberation_success_rate=0.96,
            maci_violations_count=0,
        )
        assert s.meets_targets is True

    def test_meets_targets_false_violations(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(violations_rate=0.01)
        assert s.meets_targets is False

    def test_meets_targets_false_latency(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=6.0,
            deliberation_success_rate=0.96,
            maci_violations_count=0,
        )
        assert s.meets_targets is False

    def test_meets_targets_false_deliberation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=4.0,
            deliberation_success_rate=0.90,
            maci_violations_count=0,
        )
        assert s.meets_targets is False

    def test_meets_targets_false_maci(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=4.0,
            deliberation_success_rate=0.96,
            maci_violations_count=1,
        )
        assert s.meets_targets is False

    def test_health_score_perfect(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(
            violations_rate=0.0,
            governance_latency_p99=1.0,
            deliberation_success_rate=1.0,
            maci_violations_count=0,
            error_rate=0.0,
        )
        assert s.health_score == 1.0

    def test_health_score_degraded(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(
            violations_rate=0.5,
            governance_latency_p99=30.0,
            deliberation_success_rate=0.5,
            maci_violations_count=5,
            error_rate=0.5,
        )
        score = s.health_score
        assert 0.0 <= score < 1.0

    def test_health_score_minimum_zero(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        s = GovernanceMetricsSnapshot(
            violations_rate=1.0,
            governance_latency_p99=100.0,
            deliberation_success_rate=0.0,
            maci_violations_count=100,
            error_rate=1.0,
        )
        assert s.health_score >= 0.0


class TestMetricsComparison:
    """Test MetricsComparison delta computation and degradation detection."""

    def _make_snapshot(self, **kwargs):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        defaults = {
            "violations_rate": 0.0,
            "governance_latency_p99": 2.0,
            "deliberation_success_rate": 0.98,
            "maci_violations_count": 0,
            "throughput_rps": 100.0,
            "error_rate": 0.0,
        }
        defaults.update(kwargs)
        return GovernanceMetricsSnapshot(**defaults)

    def test_no_degradation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import MetricsComparison

        baseline = self._make_snapshot()
        current = self._make_snapshot()
        cmp = MetricsComparison(baseline=baseline, current=current)
        assert cmp.has_degradation is False
        assert len(cmp.degradation_reasons) == 0

    def test_violations_rate_degradation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import MetricsComparison

        baseline = self._make_snapshot(violations_rate=0.0)
        current = self._make_snapshot(violations_rate=0.05)
        cmp = MetricsComparison(baseline=baseline, current=current)
        assert cmp.has_degradation is True
        assert any("violations" in r.lower() for r in cmp.degradation_reasons)

    def test_latency_degradation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import MetricsComparison

        baseline = self._make_snapshot(governance_latency_p99=2.0)
        current = self._make_snapshot(governance_latency_p99=5.0)
        cmp = MetricsComparison(baseline=baseline, current=current)
        assert cmp.has_degradation is True
        assert any("latency" in r.lower() for r in cmp.degradation_reasons)

    def test_deliberation_degradation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import MetricsComparison

        baseline = self._make_snapshot(deliberation_success_rate=0.98)
        current = self._make_snapshot(deliberation_success_rate=0.80)
        cmp = MetricsComparison(baseline=baseline, current=current)
        assert cmp.has_degradation is True
        assert any("deliberation" in r.lower() for r in cmp.degradation_reasons)

    def test_maci_violations_degradation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import MetricsComparison

        baseline = self._make_snapshot(maci_violations_count=0)
        current = self._make_snapshot(maci_violations_count=3)
        cmp = MetricsComparison(baseline=baseline, current=current)
        assert cmp.has_degradation is True
        assert any("maci" in r.lower() for r in cmp.degradation_reasons)

    def test_error_rate_degradation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import MetricsComparison

        baseline = self._make_snapshot(error_rate=0.0)
        current = self._make_snapshot(error_rate=0.10)
        cmp = MetricsComparison(baseline=baseline, current=current)
        assert cmp.has_degradation is True
        assert any("error" in r.lower() for r in cmp.degradation_reasons)

    def test_health_score_degradation(self):
        from enhanced_agent_bus.constitutional.metrics_collector import MetricsComparison

        baseline = self._make_snapshot()
        current = self._make_snapshot(
            violations_rate=0.5,
            governance_latency_p99=50.0,
            deliberation_success_rate=0.5,
            maci_violations_count=5,
            error_rate=0.5,
        )
        cmp = MetricsComparison(baseline=baseline, current=current)
        assert cmp.health_score_delta < 0


class TestGovernanceMetricsCollector:
    """Test GovernanceMetricsCollector methods."""

    def _make_collector(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsCollector

        return GovernanceMetricsCollector(
            redis_url="redis://localhost:6379",
            snapshot_retention_hours=24,
            measurement_window_seconds=60,
        )

    async def test_connect_redis_not_available(self):
        import enhanced_agent_bus.constitutional.metrics_collector as mod

        old = mod.REDIS_AVAILABLE
        try:
            mod.REDIS_AVAILABLE = False
            collector = self._make_collector()
            await collector.connect()
            assert collector.redis_client is None
        finally:
            mod.REDIS_AVAILABLE = old

    async def test_connect_redis_error(self):
        import enhanced_agent_bus.constitutional.metrics_collector as mod

        old = mod.REDIS_AVAILABLE
        old_aioredis = mod.aioredis
        try:
            mod.REDIS_AVAILABLE = True
            mock_redis = MagicMock()
            mock_redis.from_url = AsyncMock(side_effect=RuntimeError("conn fail"))
            mod.aioredis = mock_redis
            collector = self._make_collector()
            await collector.connect()
            assert collector.redis_client is None
        finally:
            mod.REDIS_AVAILABLE = old
            mod.aioredis = old_aioredis

    async def test_connect_redis_success(self):
        import enhanced_agent_bus.constitutional.metrics_collector as mod

        old = mod.REDIS_AVAILABLE
        old_aioredis = mod.aioredis
        try:
            mod.REDIS_AVAILABLE = True
            mock_client = AsyncMock()
            mock_redis = MagicMock()
            mock_redis.from_url = AsyncMock(return_value=mock_client)
            mod.aioredis = mock_redis
            collector = self._make_collector()
            await collector.connect()
            assert collector.redis_client is mock_client
        finally:
            mod.REDIS_AVAILABLE = old
            mod.aioredis = old_aioredis

    async def test_disconnect_no_client(self):
        collector = self._make_collector()
        collector.redis_client = None
        await collector.disconnect()  # Should not raise

    async def test_disconnect_with_client(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.disconnect()
        mock_client.close.assert_called_once()

    async def test_disconnect_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock(side_effect=RuntimeError("close fail"))
        collector.redis_client = mock_client
        await collector.disconnect()  # Should not raise

    async def test_record_governance_decision_no_client(self):
        collector = self._make_collector()
        collector.redis_client = None
        await collector.record_governance_decision(1.0, True)  # Should not raise

    async def test_record_governance_decision_approved(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.record_governance_decision(2.5, approved=True, escalated=False)
        assert mock_client.zadd.call_count >= 1
        assert mock_client.hincrby.call_count >= 2  # total + approved

    async def test_record_governance_decision_denied_escalated_violation(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.record_governance_decision(
            5.0,
            approved=False,
            escalated=True,
            constitutional_violation=True,
        )
        # total + denied + escalated = 3 hincrby calls
        assert mock_client.hincrby.call_count >= 3
        # 2 zadd calls: latencies + violations
        assert mock_client.zadd.call_count >= 2

    async def test_record_governance_decision_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zadd = AsyncMock(side_effect=RuntimeError("redis err"))
        collector.redis_client = mock_client
        await collector.record_governance_decision(1.0, True)  # Should not raise

    async def test_record_maci_violation_no_client(self):
        collector = self._make_collector()
        collector.redis_client = None
        await collector.record_maci_violation("a1", "write", "VALIDATOR")

    async def test_record_maci_violation_success(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.record_maci_violation("a1", "write", "VALIDATOR")
        mock_client.zadd.assert_called_once()
        mock_client.zremrangebyscore.assert_called_once()

    async def test_record_maci_violation_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zadd = AsyncMock(side_effect=ValueError("bad"))
        collector.redis_client = mock_client
        await collector.record_maci_violation("a1", "act", "role")

    async def test_record_deliberation_outcome_no_client(self):
        collector = self._make_collector()
        collector.redis_client = None
        await collector.record_deliberation_outcome(True)

    async def test_record_deliberation_outcome_success(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.record_deliberation_outcome(success=True)
        assert mock_client.hincrby.call_count == 2  # total + success

    async def test_record_deliberation_outcome_failure(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.record_deliberation_outcome(success=False)
        assert mock_client.hincrby.call_count == 2  # total + failed

    async def test_record_deliberation_outcome_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.hincrby = AsyncMock(side_effect=TypeError("type err"))
        collector.redis_client = mock_client
        await collector.record_deliberation_outcome(True)

    async def test_collect_snapshot_no_client(self):
        collector = self._make_collector()
        collector.redis_client = None
        snapshot = await collector.collect_snapshot()
        assert snapshot.total_requests == 0
        assert snapshot.violations_rate == 0.0

    async def test_collect_snapshot_with_data(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client

        # Mock internal methods
        collector._get_latencies = AsyncMock(return_value=[1.0, 2.0, 3.0, 4.0, 5.0])
        collector._get_request_counters = AsyncMock(
            return_value={
                "total": 100,
                "approved": 80,
                "denied": 15,
                "escalated": 5,
            }
        )
        collector._get_violations_count = AsyncMock(return_value=2)
        collector._get_maci_violations_count = AsyncMock(return_value=1)
        collector._get_deliberation_metrics = AsyncMock(
            return_value={
                "total": 50,
                "success": 48,
                "failed": 2,
                "success_rate": 0.96,
            }
        )
        collector._store_snapshot = AsyncMock()

        snapshot = await collector.collect_snapshot(constitutional_version="1.0.0")
        assert snapshot.total_requests == 100
        assert snapshot.violations_rate == 2 / 100
        assert snapshot.maci_violations_count == 1
        assert snapshot.deliberation_success_rate == 0.96
        collector._store_snapshot.assert_called_once()

    async def test_collect_snapshot_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        collector._get_latencies = AsyncMock(side_effect=RuntimeError("snap err"))
        snapshot = await collector.collect_snapshot()
        assert snapshot.total_requests == 0

    async def test_compare_snapshots_both_provided(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0, governance_latency_p99=2.0)
        current = GovernanceMetricsSnapshot(violations_rate=0.05, governance_latency_p99=3.0)
        cmp = await collector.compare_snapshots(baseline, current)
        assert cmp.violations_rate_delta == pytest.approx(0.05)

    async def test_compare_snapshots_collects_current(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        collector.redis_client = None  # Will produce empty snapshot
        baseline = GovernanceMetricsSnapshot(violations_rate=0.0)
        cmp = await collector.compare_snapshots(baseline)
        assert cmp.current is not None

    async def test_get_baseline_snapshot_no_client(self):
        collector = self._make_collector()
        collector.redis_client = None
        result = await collector.get_baseline_snapshot("1.0.0")
        assert result is None

    async def test_get_baseline_snapshot_found(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        mock_client = AsyncMock()
        snap = GovernanceMetricsSnapshot(violations_rate=0.01)
        mock_client.get = AsyncMock(return_value=snap.model_dump_json())
        collector.redis_client = mock_client
        result = await collector.get_baseline_snapshot("1.0.0")
        assert result is not None
        assert result.violations_rate == pytest.approx(0.01)

    async def test_get_baseline_snapshot_not_found(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        collector.redis_client = mock_client
        result = await collector.get_baseline_snapshot("2.0.0")
        assert result is None

    async def test_get_baseline_snapshot_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("err"))
        collector.redis_client = mock_client
        result = await collector.get_baseline_snapshot("1.0.0")
        assert result is None

    async def test_store_baseline_snapshot_no_client(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        collector.redis_client = None
        await collector.store_baseline_snapshot(GovernanceMetricsSnapshot(), "1.0.0")

    async def test_store_baseline_snapshot_success(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        await collector.store_baseline_snapshot(GovernanceMetricsSnapshot(), "1.0.0")
        mock_client.set.assert_called_once()

    async def test_store_baseline_snapshot_error(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(side_effect=ValueError("store err"))
        collector.redis_client = mock_client
        await collector.store_baseline_snapshot(GovernanceMetricsSnapshot(), "1.0.0")

    def test_compute_percentiles_empty(self):
        collector = self._make_collector()
        assert collector._compute_percentiles([]) == (0.0, 0.0, 0.0)

    def test_compute_percentiles_single(self):
        collector = self._make_collector()
        p50, p95, p99 = collector._compute_percentiles([5.0])
        assert p50 == 5.0

    def test_compute_percentiles_many(self):
        collector = self._make_collector()
        values = list(range(1, 101))  # 1..100
        p50, p95, p99 = collector._compute_percentiles(values)
        # floor index: int(100 * 0.50) = 50 -> values[50] = 51
        assert p50 == 51
        assert p95 == 96
        assert p99 == 100

    async def test_get_latencies_success(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zrangebyscore = AsyncMock(return_value=["1.5", "2.5", "3.5"])
        collector.redis_client = mock_client
        result = await collector._get_latencies(0.0, 999.0)
        assert result == [1.5, 2.5, 3.5]

    async def test_get_latencies_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zrangebyscore = AsyncMock(side_effect=RuntimeError("err"))
        collector.redis_client = mock_client
        result = await collector._get_latencies(0.0, 999.0)
        assert result == []

    async def test_get_request_counters_success(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.hgetall = AsyncMock(
            return_value={
                "total": "50",
                "approved": "40",
                "denied": "8",
                "escalated": "2",
            }
        )
        collector.redis_client = mock_client
        result = await collector._get_request_counters()
        assert result == {"total": 50, "approved": 40, "denied": 8, "escalated": 2}

    async def test_get_request_counters_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.hgetall = AsyncMock(side_effect=TypeError("err"))
        collector.redis_client = mock_client
        result = await collector._get_request_counters()
        assert result == {"total": 0, "approved": 0, "denied": 0, "escalated": 0}

    async def test_get_violations_count_success(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zcount = AsyncMock(return_value=5)
        collector.redis_client = mock_client
        result = await collector._get_violations_count(0.0, 999.0)
        assert result == 5

    async def test_get_violations_count_none(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zcount = AsyncMock(return_value=None)
        collector.redis_client = mock_client
        result = await collector._get_violations_count(0.0, 999.0)
        assert result == 0

    async def test_get_violations_count_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zcount = AsyncMock(side_effect=RuntimeError("err"))
        collector.redis_client = mock_client
        result = await collector._get_violations_count(0.0, 999.0)
        assert result == 0

    async def test_get_maci_violations_count_success(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zcount = AsyncMock(return_value=3)
        collector.redis_client = mock_client
        result = await collector._get_maci_violations_count(0.0, 999.0)
        assert result == 3

    async def test_get_maci_violations_count_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.zcount = AsyncMock(side_effect=ValueError("err"))
        collector.redis_client = mock_client
        result = await collector._get_maci_violations_count(0.0, 999.0)
        assert result == 0

    async def test_get_deliberation_metrics_success(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.hgetall = AsyncMock(
            return_value={
                "total": "10",
                "success": "8",
                "failed": "2",
            }
        )
        collector.redis_client = mock_client
        result = await collector._get_deliberation_metrics()
        assert result["success_rate"] == 0.8

    async def test_get_deliberation_metrics_no_data(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.hgetall = AsyncMock(return_value={})
        collector.redis_client = mock_client
        result = await collector._get_deliberation_metrics()
        assert result["success_rate"] == 1.0  # default when no data

    async def test_get_deliberation_metrics_error(self):
        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.hgetall = AsyncMock(side_effect=RuntimeError("err"))
        collector.redis_client = mock_client
        result = await collector._get_deliberation_metrics()
        assert result["success_rate"] == 1.0

    async def test_store_snapshot_success(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        mock_client = AsyncMock()
        collector.redis_client = mock_client
        snap = GovernanceMetricsSnapshot()
        await collector._store_snapshot(snap)
        mock_client.set.assert_called_once()
        mock_client.zadd.assert_called_once()
        mock_client.zremrangebyscore.assert_called_once()

    async def test_store_snapshot_error(self):
        from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsSnapshot

        collector = self._make_collector()
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(side_effect=RuntimeError("store err"))
        collector.redis_client = mock_client
        await collector._store_snapshot(GovernanceMetricsSnapshot())  # Should not raise


# ---------------------------------------------------------------------------
# 3. threshold_manager.py
# ---------------------------------------------------------------------------


def _make_impact_features(**kwargs):
    from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

    defaults = {
        "message_length": 100,
        "agent_count": 2,
        "tenant_complexity": 0.5,
        "temporal_patterns": [0.1, 0.2, 0.3],
        "semantic_similarity": 0.8,
        "historical_precedence": 5,
        "resource_utilization": 0.4,
        "network_isolation": 0.6,
        "risk_score": 0.3,
        "confidence_level": 0.9,
    }
    defaults.update(kwargs)
    return ImpactFeatures(**defaults)


def _make_governance_decision(**kwargs):
    from enhanced_agent_bus.adaptive_governance.models import (
        GovernanceDecision,
        ImpactLevel,
    )

    defaults = {
        "action_allowed": True,
        "impact_level": ImpactLevel.MEDIUM,
        "confidence_score": 0.85,
        "reasoning": "test",
        "recommended_threshold": 0.65,
        "features_used": _make_impact_features(),
    }
    defaults.update(kwargs)
    return GovernanceDecision(**defaults)


class TestAdaptiveThresholds:
    """Test AdaptiveThresholds methods."""

    def _make_thresholds(self):
        from enhanced_agent_bus.adaptive_governance.threshold_manager import AdaptiveThresholds

        return AdaptiveThresholds(constitutional_hash="test_hash")

    def test_init(self):
        at = self._make_thresholds()
        assert at.constitutional_hash == "test_hash"
        assert at.model_trained is False
        assert at._mlflow_initialized is False  # pytest in sys.modules

    def test_get_adaptive_threshold_untrained(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        at = self._make_thresholds()
        features = _make_impact_features()
        result = at.get_adaptive_threshold(ImpactLevel.MEDIUM, features)
        assert result == 0.6  # base threshold

    def test_get_adaptive_threshold_trained(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        at = self._make_thresholds()
        at.model_trained = True

        # Mock the model predict
        at.threshold_model = MagicMock()
        at.threshold_model.predict.return_value = np.array([0.05])

        features = _make_impact_features(confidence_level=0.9)
        result = at.get_adaptive_threshold(ImpactLevel.MEDIUM, features)
        # base=0.6 + (0.05 * 0.9) = 0.645
        assert 0.0 <= result <= 1.0

    def test_get_adaptive_threshold_trained_clamp_high(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        at = self._make_thresholds()
        at.model_trained = True
        at.threshold_model = MagicMock()
        at.threshold_model.predict.return_value = np.array([5.0])  # Very large adjustment
        features = _make_impact_features(confidence_level=1.0)
        result = at.get_adaptive_threshold(ImpactLevel.CRITICAL, features)
        assert result <= 1.0

    def test_get_adaptive_threshold_trained_clamp_low(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        at = self._make_thresholds()
        at.model_trained = True
        at.threshold_model = MagicMock()
        at.threshold_model.predict.return_value = np.array([-5.0])  # Very negative
        features = _make_impact_features(confidence_level=1.0)
        result = at.get_adaptive_threshold(ImpactLevel.NEGLIGIBLE, features)
        assert result >= 0.0

    def test_get_adaptive_threshold_error_fallback(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        at = self._make_thresholds()
        at.model_trained = True
        at.threshold_model = MagicMock()
        at.threshold_model.predict.side_effect = RuntimeError("predict fail")
        features = _make_impact_features()
        result = at.get_adaptive_threshold(ImpactLevel.HIGH, features)
        assert result == 0.8  # base threshold fallback

    def test_extract_feature_vector(self):
        at = self._make_thresholds()
        features = _make_impact_features(
            temporal_patterns=[1.0, 2.0, 3.0],
        )
        vec = at._extract_feature_vector(features)
        assert len(vec) == 11
        assert vec[0] == 100  # message_length
        assert vec[3] == pytest.approx(2.0)  # mean of temporal
        assert vec[4] == pytest.approx(float(np.std([1.0, 2.0, 3.0])))  # std

    def test_extract_feature_vector_empty_temporal(self):
        at = self._make_thresholds()
        features = _make_impact_features(temporal_patterns=[])
        vec = at._extract_feature_vector(features)
        assert vec[3] == 0.0  # mean fallback
        assert vec[4] == 0.0  # std fallback

    def test_update_model_positive_reinforcement(self):
        at = self._make_thresholds()
        decision = _make_governance_decision()
        at.update_model(decision, outcome_success=True, human_feedback=True)
        assert len(at.training_data) == 1
        assert at.training_data[0]["outcome_success"] is True

    def test_update_model_negative_reinforcement(self):
        at = self._make_thresholds()
        decision = _make_governance_decision()
        at.update_model(decision, outcome_success=False, human_feedback=False)
        assert len(at.training_data) == 1
        sample = at.training_data[0]
        assert sample["outcome_success"] is False

    def test_update_model_neutral(self):
        """When outcome_success=True but human_feedback=None (neutral path)."""
        at = self._make_thresholds()
        decision = _make_governance_decision()
        at.update_model(decision, outcome_success=True, human_feedback=None)
        assert len(at.training_data) == 1

    def test_update_model_error_handling(self):
        at = self._make_thresholds()
        decision = _make_governance_decision()
        # Corrupt features to trigger error
        decision.features_used = None  # type: ignore[assignment]
        at.update_model(decision, outcome_success=True)
        # Should not raise, training_data should remain empty
        assert len(at.training_data) == 0

    def test_update_model_triggers_retrain(self):
        at = self._make_thresholds()
        # Set last_retraining far in the past
        at.last_retraining = time.time() - 7200
        at._retrain_model = MagicMock()
        decision = _make_governance_decision()
        at.update_model(decision, outcome_success=True)
        at._retrain_model.assert_called_once()

    def test_retrain_model_insufficient_data(self):
        at = self._make_thresholds()
        # Less than 100 samples
        for _ in range(50):
            at.training_data.append(
                {
                    "features": [0.0] * 11,
                    "target": 0.1,
                    "timestamp": time.time(),
                }
            )
        at._retrain_model()
        assert at.model_trained is False

    def test_retrain_model_insufficient_recent_data(self):
        at = self._make_thresholds()
        # 100+ samples but all old
        for _ in range(150):
            at.training_data.append(
                {
                    "features": [0.0] * 11,
                    "target": 0.1,
                    "timestamp": time.time() - 100000,  # old
                }
            )
        at._retrain_model()
        assert at.model_trained is False

    def test_retrain_model_success_no_mlflow(self):
        at = self._make_thresholds()
        at._mlflow_initialized = False
        # Add enough recent training data
        for _i in range(150):
            at.training_data.append(
                {
                    "features": list(np.random.rand(11)),
                    "target": np.random.rand() * 0.1,
                    "timestamp": time.time() - np.random.randint(0, 3600),
                }
            )
        at._retrain_model()
        assert at.model_trained is True

    def test_retrain_model_error(self):
        at = self._make_thresholds()
        at._mlflow_initialized = False
        # Add enough recent data
        for _i in range(150):
            at.training_data.append(
                {
                    "features": list(np.random.rand(11)),
                    "target": np.random.rand(),
                    "timestamp": time.time(),
                }
            )
        # Mock fit to raise
        at.threshold_model = MagicMock()
        at.threshold_model.fit.side_effect = RuntimeError("fit err")
        at._retrain_model()
        assert at.model_trained is False

    def test_log_training_run_to_mlflow_fallback_on_known_error(self):
        at = self._make_thresholds()
        X = np.random.rand(60, 11)
        y = np.random.rand(60)
        recent_data = [{"outcome_success": True, "human_feedback": None}] * 60

        import enhanced_agent_bus.adaptive_governance.threshold_manager as mod

        old_available = mod.MLFLOW_AVAILABLE
        old_mlflow = mod.mlflow
        try:
            mod.MLFLOW_AVAILABLE = True
            mock_mlflow = MagicMock()
            mock_mlflow.start_run.side_effect = RuntimeError("mlflow err")
            mod.mlflow = mock_mlflow

            # Replace model with mock to verify fallback training
            mock_model = MagicMock()
            mock_anomaly = MagicMock()
            at.threshold_model = mock_model
            at.anomaly_detector = mock_anomaly

            at._mlflow_initialized = True
            at._log_training_run_to_mlflow(X, y, recent_data)
            # Should have fallen back to direct training
            mock_model.fit.assert_called()
            mock_anomaly.fit.assert_called()
        finally:
            mod.MLFLOW_AVAILABLE = old_available
            mod.mlflow = old_mlflow

    def test_log_training_run_to_mlflow_fallback_on_generic_error(self):
        at = self._make_thresholds()
        X = np.random.rand(60, 11)
        y = np.random.rand(60)
        recent_data = [{"outcome_success": True, "human_feedback": None}] * 60

        import enhanced_agent_bus.adaptive_governance.threshold_manager as mod

        old_available = mod.MLFLOW_AVAILABLE
        old_mlflow = mod.mlflow
        try:
            mod.MLFLOW_AVAILABLE = True
            mock_mlflow = MagicMock()
            mock_mlflow.start_run.side_effect = Exception("generic mlflow err")
            mod.mlflow = mock_mlflow

            at._mlflow_initialized = True
            at._log_training_run_to_mlflow(X, y, recent_data)
        finally:
            mod.MLFLOW_AVAILABLE = old_available
            mod.mlflow = old_mlflow

    def test_initialize_mlflow_not_available(self):
        import enhanced_agent_bus.adaptive_governance.threshold_manager as mod

        old_available = mod.MLFLOW_AVAILABLE
        try:
            mod.MLFLOW_AVAILABLE = False
            at = self._make_thresholds()
            at._mlflow_initialized = False
            at._initialize_mlflow()
            assert at._mlflow_initialized is False
        finally:
            mod.MLFLOW_AVAILABLE = old_available

    def test_all_impact_levels_have_base_thresholds(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        at = self._make_thresholds()
        for level in ImpactLevel:
            assert level in at.base_thresholds
