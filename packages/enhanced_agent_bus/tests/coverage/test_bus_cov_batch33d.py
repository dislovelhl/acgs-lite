"""
Coverage tests for:
- src/core/shared/auth/oidc_handler.py
- enhanced_agent_bus/deliberation_layer/impact_scorer.py
- enhanced_agent_bus/llm_adapters/bedrock_adapter.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# OIDC Handler imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus._compat.auth.oidc_handler import (
    DEFAULT_SCOPES,
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCError,
    OIDCHandler,
    OIDCProviderConfig,
    OIDCProviderError,
    OIDCTokenError,
    OIDCTokenResponse,
    OIDCUserInfo,
    _normalize_secret_sentinel,
)

# ---------------------------------------------------------------------------
# Impact Scorer imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.impact_scorer import (
    CONSTITUTIONAL_HASH,
    ImpactScorer,
)
from enhanced_agent_bus.impact_scorer_infra.models import ScoringConfig

# ---------------------------------------------------------------------------
# Bedrock Adapter imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    StreamingMode,
    TokenUsage,
)
from enhanced_agent_bus.llm_adapters.bedrock_adapter import BedrockAdapter
from enhanced_agent_bus.llm_adapters.config import AWSBedrockAdapterConfig

# ===========================================================================
#  OIDC Handler Tests
# ===========================================================================


class TestNormalizeSecretSentinel:
    """Tests for _normalize_secret_sentinel utility."""

    def test_basic_normalization(self):
        assert _normalize_secret_sentinel("  Your-Secret  ") == "yoursecret"

    def test_strips_non_alnum(self):
        assert _normalize_secret_sentinel("re_place-me!") == "replaceme"

    def test_empty_string(self):
        assert _normalize_secret_sentinel("") == ""

    def test_already_normalized(self):
        assert _normalize_secret_sentinel("yoursecret") == "yoursecret"


class TestOIDCProviderConfig:
    """Tests for OIDCProviderConfig validation."""

    def test_valid_config(self):
        cfg = OIDCProviderConfig(
            name="test",
            client_id="cid",
            client_secret="real-secret-123",
            server_metadata_url="https://example.com/.well-known/openid-configuration",
        )
        assert cfg.name == "test"
        assert cfg.scopes == list(DEFAULT_SCOPES)

    def test_empty_name_raises(self):
        with pytest.raises(OIDCConfigurationError, match="Provider name"):
            OIDCProviderConfig(
                name="",
                client_id="cid",
                client_secret="s",
                server_metadata_url="https://x",
            )

    def test_empty_client_id_raises(self):
        with pytest.raises(OIDCConfigurationError, match="Client ID"):
            OIDCProviderConfig(
                name="p",
                client_id="",
                client_secret="s",
                server_metadata_url="https://x",
            )

    def test_empty_client_secret_raises(self):
        with pytest.raises(OIDCConfigurationError, match="Client secret"):
            OIDCProviderConfig(
                name="p",
                client_id="cid",
                client_secret="",
                server_metadata_url="https://x",
            )

    def test_placeholder_secret_your_secret_raises(self):
        with pytest.raises(OIDCConfigurationError, match="placeholder"):
            OIDCProviderConfig(
                name="p",
                client_id="cid",
                client_secret="your-secret",
                server_metadata_url="https://x",
            )

    def test_placeholder_secret_replace_me_raises(self):
        with pytest.raises(OIDCConfigurationError, match="placeholder"):
            OIDCProviderConfig(
                name="p",
                client_id="cid",
                client_secret="REPLACE_ME",
                server_metadata_url="https://x",
            )

    def test_empty_metadata_url_raises(self):
        with pytest.raises(OIDCConfigurationError, match="Server metadata URL"):
            OIDCProviderConfig(
                name="p",
                client_id="cid",
                client_secret="real-secret-value",
                server_metadata_url="",
            )

    def test_custom_scopes_preserved(self):
        cfg = OIDCProviderConfig(
            name="p",
            client_id="cid",
            client_secret="real-secret-value",
            server_metadata_url="https://x",
            scopes=["openid", "custom"],
        )
        assert cfg.scopes == ["openid", "custom"]

    def test_extra_params_default(self):
        cfg = OIDCProviderConfig(
            name="p",
            client_id="cid",
            client_secret="real-secret-value",
            server_metadata_url="https://x",
        )
        assert cfg.extra_params == {}


class TestOIDCTokenResponse:
    """Tests for OIDCTokenResponse.from_dict."""

    def test_from_dict_full(self):
        data = {
            "access_token": "at",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "rt",
            "id_token": "idt",
            "scope": "openid profile",
        }
        tr = OIDCTokenResponse.from_dict(data)
        assert tr.access_token == "at"
        assert tr.expires_in == 3600
        assert tr.refresh_token == "rt"
        assert tr.id_token == "idt"
        assert tr.scope == "openid profile"
        assert tr.raw_response == data

    def test_from_dict_minimal(self):
        data = {"access_token": "at"}
        tr = OIDCTokenResponse.from_dict(data)
        assert tr.access_token == "at"
        assert tr.token_type == "Bearer"
        assert tr.expires_in is None
        assert tr.refresh_token is None
        assert tr.id_token is None
        assert tr.scope is None

    def test_from_dict_empty(self):
        tr = OIDCTokenResponse.from_dict({})
        assert tr.access_token == ""


class TestOIDCUserInfo:
    """Tests for OIDCUserInfo.from_claims."""

    def test_from_claims_with_groups(self):
        claims = {"sub": "u1", "email": "a@b.com", "groups": ["admin", "user"]}
        ui = OIDCUserInfo.from_claims(claims)
        assert ui.sub == "u1"
        assert ui.groups == ["admin", "user"]

    def test_from_claims_with_roles(self):
        claims = {"sub": "u2", "roles": ["viewer"]}
        ui = OIDCUserInfo.from_claims(claims)
        assert ui.groups == ["viewer"]

    def test_from_claims_with_azure_groups(self):
        claims = {
            "sub": "u3",
            "https://schemas.microsoft.com/claims/groups": ["grp1"],
        }
        ui = OIDCUserInfo.from_claims(claims)
        assert ui.groups == ["grp1"]

    def test_from_claims_no_groups(self):
        claims = {"sub": "u4"}
        ui = OIDCUserInfo.from_claims(claims)
        assert ui.groups == []

    def test_from_claims_groups_not_list(self):
        claims = {"sub": "u5", "groups": "not-a-list"}
        ui = OIDCUserInfo.from_claims(claims)
        assert ui.groups == []

    def test_from_claims_all_fields(self):
        claims = {
            "sub": "u6",
            "email": "x@y.com",
            "email_verified": True,
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "picture": "https://pic.url",
            "locale": "en",
        }
        ui = OIDCUserInfo.from_claims(claims)
        assert ui.email_verified is True
        assert ui.name == "Test User"
        assert ui.picture == "https://pic.url"
        assert ui.locale == "en"


class TestOIDCHandler:
    """Tests for OIDCHandler core methods."""

    def _make_handler(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="test",
            client_id="cid",
            client_secret="real-secret-value-123",
            server_metadata_url="https://idp.example/.well-known/openid-configuration",
        )
        return handler

    def test_register_and_get_provider(self):
        handler = self._make_handler()
        p = handler.get_provider("test")
        assert p.name == "test"

    def test_get_provider_not_found(self):
        handler = OIDCHandler()
        with pytest.raises(OIDCConfigurationError, match="not registered"):
            handler.get_provider("missing")

    def test_list_providers(self):
        handler = self._make_handler()
        assert handler.list_providers() == ["test"]

    def test_validate_state_true(self):
        handler = OIDCHandler()
        handler._pending_states["abc"] = {"created_at": datetime.now(UTC).isoformat()}
        assert handler.validate_state("abc") is True

    def test_validate_state_false(self):
        handler = OIDCHandler()
        assert handler.validate_state("missing") is False

    def test_clear_expired_states(self):
        handler = OIDCHandler()
        old_time = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
        handler._pending_states["old"] = {"created_at": old_time}
        handler._pending_states["new"] = {"created_at": datetime.now(UTC).isoformat()}
        cleared = handler.clear_expired_states(max_age_seconds=600)
        assert cleared == 1
        assert "old" not in handler._pending_states
        assert "new" in handler._pending_states

    def test_clear_expired_states_none_expired(self):
        handler = OIDCHandler()
        handler._pending_states["new"] = {"created_at": datetime.now(UTC).isoformat()}
        cleared = handler.clear_expired_states()
        assert cleared == 0

    def test_evict_stale_pending_states(self):
        handler = OIDCHandler()
        old_time = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
        handler._pending_states["stale"] = {"created_at": old_time}
        handler._evict_stale_pending_states()
        assert "stale" not in handler._pending_states

    def test_register_provider_from_model_not_oidc(self):
        handler = OIDCHandler()
        mock_provider = MagicMock()
        mock_provider.is_oidc = False
        mock_provider.name = "saml-provider"
        with pytest.raises(OIDCConfigurationError, match="not an OIDC provider"):
            handler.register_provider_from_model(mock_provider)

    def test_register_provider_from_model_validation_errors(self):
        handler = OIDCHandler()
        mock_provider = MagicMock()
        mock_provider.is_oidc = True
        mock_provider.name = "bad-oidc"
        mock_provider.validate_oidc_config.return_value = ["missing client_id"]
        with pytest.raises(OIDCConfigurationError, match="Invalid OIDC configuration"):
            handler.register_provider_from_model(mock_provider)

    def test_register_provider_from_model_success(self):
        handler = OIDCHandler()
        mock_provider = MagicMock()
        mock_provider.is_oidc = True
        mock_provider.name = "okta"
        mock_provider.validate_oidc_config.return_value = []
        mock_provider.oidc_client_id = "cid"
        mock_provider.oidc_client_secret = "real-secret-value-abc"
        mock_provider.oidc_metadata_url = "https://okta.example/.well-known/openid-configuration"
        mock_provider.oidc_scope_list = ["openid", "profile"]
        mock_provider.get_config.return_value = {"domain": "okta.example"}
        handler.register_provider_from_model(mock_provider)
        assert "okta" in handler.list_providers()

    async def test_close(self):
        handler = OIDCHandler()
        handler._http_client = AsyncMock()
        await handler.close()
        assert handler._http_client is None

    async def test_close_no_client(self):
        handler = OIDCHandler()
        await handler.close()  # should not raise

    async def test_get_http_client_no_httpx(self):
        handler = OIDCHandler()
        with patch("src.core.shared.auth.oidc_handler.HAS_HTTPX", False):
            handler._http_client = None
            with pytest.raises(OIDCError, match="httpx library"):
                await handler._get_http_client()


class TestOIDCHandlerInitiateLogin:
    """Tests for initiate_login flow."""

    async def test_initiate_login_no_authorization_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/openid-configuration",
        )
        handler._fetch_metadata = AsyncMock(return_value={"issuer": "https://idp.example"})
        with pytest.raises(OIDCProviderError, match="Authorization endpoint not found"):
            await handler.initiate_login("p1", "https://app/callback")

    async def test_initiate_login_success_pkce(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
            use_pkce=True,
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"authorization_endpoint": "https://idp.example/auth"}
        )
        auth_url, state = await handler.initiate_login("p1", "https://app/callback")
        assert "https://idp.example/auth" in auth_url
        assert "code_challenge" in auth_url
        assert state in handler._pending_states

    async def test_initiate_login_no_pkce(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p2",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
            use_pkce=False,
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"authorization_endpoint": "https://idp.example/auth"}
        )
        auth_url, state = await handler.initiate_login("p2", "https://app/callback")
        assert "code_challenge" not in auth_url

    async def test_initiate_login_evicts_when_at_capacity(self):
        handler = OIDCHandler()
        handler._max_pending_states = 2
        handler.register_provider(
            name="p3",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"authorization_endpoint": "https://idp.example/auth"}
        )
        # Fill to capacity
        handler._pending_states["s1"] = {"created_at": datetime.now(UTC).isoformat()}
        handler._pending_states["s2"] = {"created_at": datetime.now(UTC).isoformat()}
        _, state = await handler.initiate_login("p3", "https://app/callback")
        # Oldest should be evicted
        assert "s1" not in handler._pending_states
        assert state in handler._pending_states

    async def test_initiate_login_with_nonce(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p4",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"authorization_endpoint": "https://idp.example/auth"}
        )
        auth_url, state = await handler.initiate_login(
            "p4", "https://app/callback", nonce="my-nonce"
        )
        assert handler._pending_states[state]["nonce"] == "my-nonce"


class TestOIDCHandlerCallback:
    """Tests for handle_callback flow."""

    async def test_handle_callback_invalid_state(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        with pytest.raises(OIDCAuthenticationError, match="Invalid or expired state"):
            await handler.handle_callback("p1", "code123", "bad-state")

    async def test_handle_callback_provider_mismatch(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._pending_states["state1"] = {
            "provider": "different-provider",
            "redirect_uri": "https://app/callback",
            "code_verifier": None,
            "nonce": "n",
            "created_at": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(OIDCAuthenticationError, match="Provider mismatch"):
            await handler.handle_callback("p1", "code123", "state1")

    async def test_handle_callback_success(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._pending_states["state1"] = {
            "provider": "p1",
            "redirect_uri": "https://app/callback",
            "code_verifier": "cv",
            "nonce": "n",
            "created_at": datetime.now(UTC).isoformat(),
        }
        mock_tokens = OIDCTokenResponse(access_token="at")
        mock_user = OIDCUserInfo(sub="user1", email="u@e.com")
        handler._exchange_code = AsyncMock(return_value=mock_tokens)
        handler._get_user_info = AsyncMock(return_value=mock_user)
        result = await handler.handle_callback("p1", "code123", "state1")
        assert result.sub == "user1"
        assert "state1" not in handler._pending_states


class TestOIDCHandlerExchangeCode:
    """Tests for _exchange_code."""

    async def test_exchange_code_no_token_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        provider = handler.get_provider("p1")
        with pytest.raises(OIDCTokenError, match="Token endpoint not found"):
            await handler._exchange_code(provider, "code", "https://app/callback")

    async def test_exchange_code_non_200(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"token_endpoint": "https://idp.example/token"}
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.content = b'{"error":"invalid_grant"}'
        mock_resp.json.return_value = {"error": "invalid_grant"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        handler._get_http_client = AsyncMock(return_value=mock_client)
        provider = handler.get_provider("p1")
        with pytest.raises(OIDCTokenError, match="Token exchange failed"):
            await handler._exchange_code(provider, "code", "https://app/callback")

    async def test_exchange_code_runtime_error(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"token_endpoint": "https://idp.example/token"}
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("conn refused"))
        handler._get_http_client = AsyncMock(return_value=mock_client)
        provider = handler.get_provider("p1")
        with pytest.raises(OIDCTokenError, match="Token exchange failed"):
            await handler._exchange_code(provider, "code", "https://app/callback")


class TestOIDCHandlerGetUserInfo:
    """Tests for _get_user_info and _fetch_userinfo."""

    async def test_get_user_info_from_id_token(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        provider = handler.get_provider("p1")
        tokens = OIDCTokenResponse(access_token="at", id_token="idt")
        handler._decode_id_token = AsyncMock(return_value={"sub": "u1", "email": "a@b.com"})
        result = await handler._get_user_info(provider, tokens)
        assert result.sub == "u1"

    async def test_get_user_info_id_token_fails_falls_back(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        provider = handler.get_provider("p1")
        tokens = OIDCTokenResponse(access_token="at", id_token="bad-jwt")
        handler._decode_id_token = AsyncMock(side_effect=OIDCTokenError("bad token"))
        mock_user = OIDCUserInfo(sub="u2")
        handler._fetch_userinfo = AsyncMock(return_value=mock_user)
        result = await handler._get_user_info(provider, tokens)
        assert result.sub == "u2"

    async def test_get_user_info_no_id_token_uses_userinfo(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        provider = handler.get_provider("p1")
        tokens = OIDCTokenResponse(access_token="at")
        mock_user = OIDCUserInfo(sub="u3")
        handler._fetch_userinfo = AsyncMock(return_value=mock_user)
        result = await handler._get_user_info(provider, tokens)
        assert result.sub == "u3"

    async def test_fetch_userinfo_no_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        provider = handler.get_provider("p1")
        with pytest.raises(OIDCProviderError, match="Userinfo endpoint not found"):
            await handler._fetch_userinfo(provider, "at")

    async def test_fetch_userinfo_non_200(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"userinfo_endpoint": "https://idp.example/userinfo"}
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        handler._get_http_client = AsyncMock(return_value=mock_client)
        provider = handler.get_provider("p1")
        with pytest.raises(OIDCProviderError, match="Userinfo request failed"):
            await handler._fetch_userinfo(provider, "at")

    async def test_fetch_userinfo_runtime_error(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"userinfo_endpoint": "https://idp.example/userinfo"}
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network error"))
        handler._get_http_client = AsyncMock(return_value=mock_client)
        provider = handler.get_provider("p1")
        with pytest.raises(OIDCProviderError, match="Userinfo request failed"):
            await handler._fetch_userinfo(provider, "at")


class TestOIDCHandlerRefreshToken:
    """Tests for refresh_token."""

    async def test_refresh_token_no_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        with pytest.raises(OIDCTokenError, match="Token endpoint not found"):
            await handler.refresh_token("p1", "rt")

    async def test_refresh_token_non_200(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"token_endpoint": "https://idp.example/token"}
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.content = b'{"error":"invalid_grant"}'
        mock_resp.json.return_value = {"error": "invalid_grant"}
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        handler._get_http_client = AsyncMock(return_value=mock_client)
        with pytest.raises(OIDCTokenError, match="Token refresh failed"):
            await handler.refresh_token("p1", "rt")

    async def test_refresh_token_runtime_error(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"token_endpoint": "https://idp.example/token"}
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("refused"))
        handler._get_http_client = AsyncMock(return_value=mock_client)
        with pytest.raises(OIDCTokenError, match="Token refresh failed"):
            await handler.refresh_token("p1", "rt")

    async def test_refresh_token_success(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"token_endpoint": "https://idp.example/token"}
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_at",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        handler._get_http_client = AsyncMock(return_value=mock_client)
        result = await handler.refresh_token("p1", "rt")
        assert result.access_token == "new_at"


class TestOIDCHandlerLogout:
    """Tests for logout."""

    async def test_logout_no_endpoint(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={})
        result = await handler.logout("p1")
        assert result is None

    async def test_logout_with_hints(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={"end_session_endpoint": "https://idp.example/logout"}
        )
        result = await handler.logout(
            "p1",
            id_token_hint="idt",
            post_logout_redirect_uri="https://app/logged-out",
        )
        assert result is not None
        assert "id_token_hint=idt" in result
        assert "post_logout_redirect_uri" in result


class TestOIDCHandlerDecodeIdToken:
    """Tests for _decode_id_token."""

    async def test_decode_id_token_no_authlib(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(
            return_value={
                "issuer": "https://idp.example",
                "jwks_uri": "https://idp.example/jwks",
            }
        )
        provider = handler.get_provider("p1")
        with patch("src.core.shared.auth.oidc_handler.HAS_AUTHLIB", False):
            with pytest.raises(OIDCTokenError, match="authlib library"):
                await handler._decode_id_token("token", provider)

    async def test_decode_id_token_no_jwks_uri(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        handler._fetch_metadata = AsyncMock(return_value={"issuer": "https://idp.example"})
        provider = handler.get_provider("p1")
        # jwks_uri check precedes authlib check — missing jwks_uri error takes priority
        with patch("src.core.shared.auth.oidc_handler.HAS_AUTHLIB", False):
            with pytest.raises(OIDCTokenError, match="JWKS URI not found"):
                await handler._decode_id_token("token", provider)

    async def test_decode_id_token_no_issuer(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"keys": []}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        handler._get_http_client = AsyncMock(return_value=mock_client)
        handler._fetch_metadata = AsyncMock(return_value={"jwks_uri": "https://idp.example/jwks"})
        provider = handler.get_provider("p1")
        with patch("src.core.shared.auth.oidc_handler.HAS_AUTHLIB", True):
            with patch("src.core.shared.auth.oidc_handler.jwt"):
                with patch("enhanced_agent_bus.llm_adapters.bedrock_adapter.json"):
                    pass
            # The import of JsonWebKey inside the method - mock it
            with patch.dict(
                "sys.modules",
                {
                    "authlib.jose": MagicMock(),
                },
            ):
                with pytest.raises(OIDCTokenError):
                    await handler._decode_id_token("token", provider)


class TestOIDCHandlerFetchMetadata:
    """Tests for _fetch_metadata."""

    async def test_fetch_metadata_cache_hit(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        provider = handler.get_provider("p1")
        handler._metadata_cache["p1"] = {"issuer": "cached"}
        handler._metadata_timestamps["p1"] = datetime.now(UTC)
        result = await handler._fetch_metadata(provider)
        assert result["issuer"] == "cached"

    async def test_fetch_metadata_cache_expired(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        provider = handler.get_provider("p1")
        handler._metadata_cache["p1"] = {"issuer": "old"}
        handler._metadata_timestamps["p1"] = datetime.now(UTC) - timedelta(hours=25)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"issuer": "fresh"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        handler._get_http_client = AsyncMock(return_value=mock_client)
        result = await handler._fetch_metadata(provider)
        assert result["issuer"] == "fresh"

    async def test_fetch_metadata_error_uses_cached(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        provider = handler.get_provider("p1")
        handler._metadata_cache["p1"] = {"issuer": "cached-fallback"}
        handler._metadata_timestamps["p1"] = datetime.now(UTC) - timedelta(hours=25)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network"))
        handler._get_http_client = AsyncMock(return_value=mock_client)
        result = await handler._fetch_metadata(provider)
        assert result["issuer"] == "cached-fallback"

    async def test_fetch_metadata_error_no_cache_raises(self):
        handler = OIDCHandler()
        handler.register_provider(
            name="p1",
            client_id="cid",
            client_secret="real-secret-value-xyz",
            server_metadata_url="https://idp.example/.well-known/oidc",
        )
        provider = handler.get_provider("p1")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network"))
        handler._get_http_client = AsyncMock(return_value=mock_client)
        with pytest.raises(OIDCProviderError, match="Failed to fetch OIDC metadata"):
            await handler._fetch_metadata(provider)


# ===========================================================================
#  Impact Scorer Tests
# ===========================================================================


class TestImpactScorerBasics:
    """Tests for ImpactScorer basic operations."""

    def test_init_default(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer.config is not None
        assert scorer._enable_minicpm is False

    def test_init_with_caching(self):
        scorer = ImpactScorer(enable_caching=True)
        assert scorer._embedding_cache is not None

    async def test_initialize_no_cache(self):
        scorer = ImpactScorer(enable_caching=False)
        result = await scorer.initialize()
        assert result is True

    async def test_close_no_cache(self):
        scorer = ImpactScorer(enable_caching=False)
        await scorer.close()  # should not raise

    def test_generate_cache_key(self):
        scorer = ImpactScorer(enable_caching=False)
        key = scorer._generate_cache_key("test text")
        assert key.startswith("impact:embedding:")
        assert len(key) > 20

    def test_reset_class_cache(self):
        ImpactScorer.reset_class_cache()  # should not raise

    def test_clear_tokenization_cache(self):
        scorer = ImpactScorer(enable_caching=False)
        scorer._tokenization_cache["foo"] = "bar"
        scorer.clear_tokenization_cache()
        assert scorer._tokenization_cache == {}

    def test_minicpm_enabled_property(self):
        scorer = ImpactScorer(enable_caching=False, enable_minicpm=False)
        assert scorer.minicpm_enabled is False

    def test_loco_operator_not_available(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer.loco_operator_available is False

    async def test_score_with_loco_operator_not_available(self):
        scorer = ImpactScorer(enable_caching=False)
        result = await scorer._score_with_loco_operator("action", {})
        assert result is None


class TestImpactScorerScoring:
    """Tests for impact scoring logic."""

    def test_calculate_impact_score_none_message(self):
        scorer = ImpactScorer(enable_caching=False)
        score = scorer.calculate_impact_score(None)
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_empty_dict(self):
        scorer = ImpactScorer(enable_caching=False)
        score = scorer.calculate_impact_score({})
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_critical_priority(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"content": "hello", "from_agent": "a1"}
        score = scorer.calculate_impact_score(msg, {"priority": "critical"})
        assert score >= 0.7  # IMPACT_CRITICAL_FLOOR

    def test_calculate_impact_score_high_semantic(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"content": "critical security breach detected", "from_agent": "a1"}
        score = scorer.calculate_impact_score(msg)
        assert score >= 0.5

    def test_calculate_impact_score_with_semantic_override(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"content": "normal", "from_agent": "a1"}
        score = scorer.calculate_impact_score(msg, {"semantic_override": 0.95})
        assert score >= 0.3

    def test_calculate_impact_score_priority_enum(self):
        scorer = ImpactScorer(enable_caching=False)
        prio = MagicMock()
        prio.name = "critical"
        msg = {"content": "test", "from_agent": "a1", "priority": prio}
        score = scorer.calculate_impact_score(msg)
        assert 0.0 <= score <= 1.0

    def test_calculate_impact_score_object_message(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = MagicMock()
        msg.from_agent = "a1"
        msg.priority = "normal"
        msg.content = "hello"
        msg.tools = []
        msg.payload = {}
        msg.message_type = ""
        score = scorer.calculate_impact_score(msg)
        assert 0.0 <= score <= 1.0


class TestImpactScorerSubScores:
    """Tests for sub-score calculations."""

    def test_permission_score_no_tools(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_permission_score({}) == 0.1

    def test_permission_score_high_risk_tool(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"tools": [{"name": "execute_command"}]}
        assert scorer._calculate_permission_score(msg) >= 0.7

    def test_permission_score_read_tool(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"tools": [{"name": "read_file"}]}
        assert scorer._calculate_permission_score(msg) == 0.2

    def test_permission_score_unknown_tool(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"tools": [{"name": "custom_tool"}]}
        assert scorer._calculate_permission_score(msg) == 0.3

    def test_permission_score_tool_as_string(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"tools": ["execute_shell"]}
        assert scorer._calculate_permission_score(msg) >= 0.7

    def test_permission_score_object_message(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = MagicMock()
        msg.tools = [{"name": "delete_record"}]
        assert scorer._calculate_permission_score(msg) >= 0.7

    def test_volume_score_progression(self):
        scorer = ImpactScorer(enable_caching=False)
        # First 10 calls: 0.1
        for _ in range(10):
            assert scorer._calculate_volume_score("agent1") == 0.1
        # 11-30: 0.2
        assert scorer._calculate_volume_score("agent1") == 0.2

    def test_context_score_high_amount(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"payload": {"amount": 50000}}
        assert scorer._calculate_context_score(msg, {}) >= 0.5

    def test_context_score_low_amount(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"payload": {"amount": 100}}
        assert scorer._calculate_context_score(msg, {}) == 0.1

    def test_context_score_object_message(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = MagicMock()
        msg.payload = {"amount": 50000}
        assert scorer._calculate_context_score(msg, {}) >= 0.5

    def test_drift_score_no_history(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_drift_score("new_agent", 0.4) == 0.0

    def test_drift_score_with_deviation(self):
        scorer = ImpactScorer(enable_caching=False)
        scorer._agent_score_history = {"a": [0.1, 0.1, 0.1]}
        result = scorer._calculate_drift_score("a", 0.8)
        assert result > 0.0

    def test_semantic_score_no_keywords(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_semantic_score({"content": "hello world"}) == 0.1

    def test_semantic_score_with_keyword(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_semantic_score({"content": "critical alert"}) == 0.95

    def test_semantic_score_empty(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_semantic_score({}) == 0.0


class TestImpactScorerKeywordScore:
    """Tests for _get_keyword_score."""

    def test_no_keywords(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._get_keyword_score("hello world") == 0.1

    def test_one_keyword(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._get_keyword_score("critical issue") == 0.5

    def test_two_keywords(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._get_keyword_score("critical security issue") == 0.75

    def test_three_plus_keywords(self):
        scorer = ImpactScorer(enable_caching=False)
        # "critical security breach" = 3 keywords -> 0.75 + (3-2)*0.1 = 0.85
        assert scorer._get_keyword_score("critical security breach") == 0.85


class TestImpactScorerFactors:
    """Tests for priority and type factors."""

    def test_priority_factor_critical(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_priority_factor({}, {"priority": "critical"}) == 1.0

    def test_priority_factor_high(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_priority_factor({}, {"priority": "high"}) == 0.8

    def test_priority_factor_low(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_priority_factor({}, {"priority": "low"}) == 0.2

    def test_priority_factor_unknown(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_priority_factor({}, {"priority": "weird"}) == 0.5

    def test_priority_factor_from_enum_value(self):
        scorer = ImpactScorer(enable_caching=False)
        prio = MagicMock()
        prio.value = "high"
        del prio.name  # ensure value path is taken
        assert scorer._calculate_priority_factor({"priority": prio}, {}) == 0.8

    def test_type_factor_governance(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_type_factor({"message_type": "governance"}) == 1.5

    def test_type_factor_security(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_type_factor({"message_type": "security"}) == 1.4

    def test_type_factor_financial(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_type_factor({"message_type": "financial"}) == 1.3

    def test_type_factor_default(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer._calculate_type_factor({"message_type": "info"}) == 1.0


class TestImpactScorerBatch:
    """Tests for batch scoring."""

    def test_batch_score_impact(self):
        scorer = ImpactScorer(enable_caching=False)
        messages = [
            {"content": "hello", "from_agent": "a1"},
            {"content": "critical alert", "from_agent": "a2"},
        ]
        scores = scorer.batch_score_impact(messages)
        assert len(scores) == 2

    def test_batch_score_impact_with_contexts(self):
        scorer = ImpactScorer(enable_caching=False)
        messages = [{"content": "x", "from_agent": "a1"}]
        contexts = [{"priority": "critical"}]
        scores = scorer.batch_score_impact(messages, contexts)
        assert len(scores) == 1

    def test_batch_score_impact_mismatched_lengths(self):
        scorer = ImpactScorer(enable_caching=False)
        with pytest.raises(ValueError, match="contexts length"):
            scorer.batch_score_impact(
                [{"content": "x"}], [{"priority": "low"}, {"priority": "high"}]
            )

    def test_score_messages_batch_no_onnx(self):
        scorer = ImpactScorer(enable_caching=False, use_onnx=False)
        messages = [{"content": "test", "from_agent": "a1"}]
        scores = scorer.score_messages_batch(messages)
        assert len(scores) == 1


class TestImpactScorerSpecToArtifact:
    """Tests for Spec-to-Artifact scoring."""

    def test_initial_score(self):
        scorer = ImpactScorer(enable_caching=False)
        assert scorer.spec_to_artifact_score == 1.0

    def test_score_after_evaluations(self):
        scorer = ImpactScorer(enable_caching=False)
        scorer.calculate_impact_score({"content": "a", "from_agent": "x"})
        scorer.calculate_impact_score({"content": "b", "from_agent": "x"})
        scorer.record_override()
        assert scorer.spec_to_artifact_score == 0.5

    def test_get_metrics(self):
        scorer = ImpactScorer(enable_caching=False)
        scorer.calculate_impact_score({"content": "a", "from_agent": "x"})
        scorer.record_override()
        metrics = scorer.get_spec_to_artifact_metrics()
        assert metrics["total_evaluations"] == 1
        assert metrics["overrides"] == 1
        assert metrics["override_rate"] == 1.0
        assert metrics["spec_to_artifact_score"] == 0.0

    def test_get_metrics_no_evaluations(self):
        scorer = ImpactScorer(enable_caching=False)
        metrics = scorer.get_spec_to_artifact_metrics()
        assert metrics["override_rate"] == 0.0


class TestImpactScorerResetHistory:
    """Tests for reset_history."""

    def test_reset_clears_all(self):
        scorer = ImpactScorer(enable_caching=False)
        scorer.calculate_impact_score({"content": "test", "from_agent": "a1"})
        scorer.reset_history()
        assert scorer._volume_counts == {}
        assert scorer._drift_history == {}


class TestImpactScorerExtractContent:
    """Tests for text extraction helpers."""

    def test_extract_payload_content(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {
            "payload": {"message": "payload msg"},
            "action": "deploy",
            "description": "desc",
        }
        parts = scorer._extract_payload_content(msg)
        assert "payload msg" in parts
        assert "deploy" in parts
        assert "desc" in parts

    def test_extract_tool_content_dict_tools(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"tools": [{"name": "execute"}, {"name": "read"}]}
        parts = scorer._extract_tool_content(msg)
        assert "execute" in parts
        assert "read" in parts

    def test_extract_tool_content_string_tools(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"tools": ["execute", "read"]}
        parts = scorer._extract_tool_content(msg)
        assert "execute" in parts

    def test_extract_tool_content_object(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = MagicMock()
        msg.tools = ["shell_exec"]
        parts = scorer._extract_tool_content(msg)
        assert "shell_exec" in parts

    def test_extract_basic_content_from_object(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = MagicMock()
        msg.content = "obj content"
        parts = scorer._extract_basic_content(msg)
        assert "obj content" in parts

    def test_extract_basic_content_from_dict(self):
        scorer = ImpactScorer(enable_caching=False)
        msg = {"content": "dict content"}
        parts = scorer._extract_basic_content(msg)
        assert "dict content" in parts


# ===========================================================================
#  Bedrock Adapter Tests
# ===========================================================================


def _make_bedrock_adapter(model: str = "anthropic.claude-sonnet-4-6-v1:0") -> BedrockAdapter:
    """Helper to create a BedrockAdapter with a config (no real AWS creds)."""
    config = AWSBedrockAdapterConfig.from_environment(model=model)
    return BedrockAdapter(config=config)


class TestBedrockAdapterInit:
    """Tests for BedrockAdapter initialization."""

    def test_init_with_config(self):
        adapter = _make_bedrock_adapter()
        assert adapter.model == "anthropic.claude-sonnet-4-6-v1:0"

    def test_init_default_model(self):
        adapter = BedrockAdapter()
        assert adapter.model == "anthropic.claude-sonnet-4-6-v1:0"

    def test_init_custom_model(self):
        adapter = BedrockAdapter(model="meta.llama3-8b-instruct-v1:0")
        assert adapter.model == "meta.llama3-8b-instruct-v1:0"


class TestBedrockAdapterProvider:
    """Tests for _get_provider."""

    def test_anthropic_provider(self):
        adapter = _make_bedrock_adapter("anthropic.claude-3-haiku-20240307-v1:0")
        assert adapter._get_provider() == "anthropic"

    def test_meta_provider(self):
        adapter = _make_bedrock_adapter("meta.llama3-8b-instruct-v1:0")
        assert adapter._get_provider() == "meta"

    def test_amazon_provider(self):
        adapter = _make_bedrock_adapter("amazon.titan-text-express-v1")
        assert adapter._get_provider() == "amazon"

    def test_cohere_provider(self):
        adapter = _make_bedrock_adapter("cohere.command-r-v1:0")
        assert adapter._get_provider() == "cohere"

    def test_ai21_provider(self):
        adapter = _make_bedrock_adapter("ai21.jamba-instruct-v1:0")
        assert adapter._get_provider() == "ai21"

    def test_unknown_provider_defaults_anthropic(self):
        adapter = _make_bedrock_adapter("unknown.model-v1")
        assert adapter._get_provider() == "anthropic"

    def test_provider_cached(self):
        adapter = _make_bedrock_adapter("meta.llama3-8b-instruct-v1:0")
        adapter._get_provider()
        assert adapter._provider == "meta"
        # Second call returns cached value
        assert adapter._get_provider() == "meta"


class TestBedrockAdapterBuildRequestBody:
    """Tests for _build_request_body and provider-specific builders."""

    def test_anthropic_body(self):
        adapter = _make_bedrock_adapter("anthropic.claude-sonnet-4-6-v1:0")
        messages = [
            LLMMessage(role="system", content="You are helpful."),
            LLMMessage(role="user", content="Hi"),
        ]
        body_str = adapter._build_request_body(messages, temperature=0.5, max_tokens=100)
        body = json.loads(body_str)
        assert "anthropic_version" in body
        assert body["system"] == "You are helpful."
        assert body["max_tokens"] == 100

    def test_anthropic_body_with_stop_and_top_k(self):
        adapter = _make_bedrock_adapter("anthropic.claude-sonnet-4-6-v1:0")
        messages = [LLMMessage(role="user", content="Hi")]
        body_str = adapter._build_request_body(messages, stop=["END"], top_k=10)
        body = json.loads(body_str)
        assert body["stop_sequences"] == ["END"]
        assert body["top_k"] == 10

    def test_meta_body(self):
        adapter = _make_bedrock_adapter("meta.llama3-8b-instruct-v1:0")
        messages = [LLMMessage(role="user", content="Hello")]
        body_str = adapter._build_request_body(messages)
        body = json.loads(body_str)
        assert "prompt" in body
        assert "max_gen_len" in body

    def test_amazon_body(self):
        adapter = _make_bedrock_adapter("amazon.titan-text-express-v1")
        messages = [LLMMessage(role="user", content="Hello")]
        body_str = adapter._build_request_body(messages, stop=["END"])
        body = json.loads(body_str)
        assert "inputText" in body
        assert "textGenerationConfig" in body
        assert "stopSequences" in body["textGenerationConfig"]

    def test_cohere_body_single_message(self):
        adapter = _make_bedrock_adapter("cohere.command-r-v1:0")
        messages = [LLMMessage(role="user", content="Hello")]
        body_str = adapter._build_request_body(messages)
        body = json.loads(body_str)
        assert body["message"] == "Hello"
        assert "chat_history" not in body

    def test_cohere_body_with_history(self):
        adapter = _make_bedrock_adapter("cohere.command-r-v1:0")
        messages = [
            LLMMessage(role="user", content="First"),
            LLMMessage(role="assistant", content="Response"),
            LLMMessage(role="user", content="Second"),
        ]
        body_str = adapter._build_request_body(messages)
        body = json.loads(body_str)
        assert body["message"] == "Second"
        assert len(body["chat_history"]) == 2

    def test_ai21_body(self):
        adapter = _make_bedrock_adapter("ai21.jamba-instruct-v1:0")
        messages = [LLMMessage(role="user", content="Hello")]
        body_str = adapter._build_request_body(messages, stop=["STOP"])
        body = json.loads(body_str)
        assert "prompt" in body
        assert body["stopSequences"] == ["STOP"]

    def test_generic_body_fallback(self):
        adapter = _make_bedrock_adapter("unknown.model-v1")
        adapter._provider = "unknown"  # Force unknown provider
        messages = [LLMMessage(role="user", content="Hello")]
        body_str = adapter._build_request_body(messages)
        body = json.loads(body_str)
        assert "prompt" in body


class TestBedrockAdapterParseResponse:
    """Tests for _parse_response_body."""

    def test_parse_anthropic_response(self):
        adapter = _make_bedrock_adapter("anthropic.claude-sonnet-4-6-v1:0")
        body = json.dumps(
            {
                "content": [{"type": "text", "text": "Hello!"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
        content, usage = adapter._parse_response_body(body)
        assert content == "Hello!"
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5

    def test_parse_meta_response(self):
        adapter = _make_bedrock_adapter("meta.llama3-8b-instruct-v1:0")
        body = json.dumps(
            {
                "generation": "Hi there",
                "prompt_token_count": 8,
                "generation_token_count": 3,
            }
        )
        content, usage = adapter._parse_response_body(body)
        assert content == "Hi there"
        assert usage.prompt_tokens == 8

    def test_parse_amazon_response(self):
        adapter = _make_bedrock_adapter("amazon.titan-text-express-v1")
        body = json.dumps(
            {
                "results": [{"outputText": "Titan says hi", "tokenCount": 4}],
                "inputTextTokenCount": 6,
            }
        )
        content, usage = adapter._parse_response_body(body)
        assert content == "Titan says hi"
        assert usage.completion_tokens == 4

    def test_parse_amazon_empty_results(self):
        adapter = _make_bedrock_adapter("amazon.titan-text-express-v1")
        body = json.dumps({"results": [], "inputTextTokenCount": 0})
        content, usage = adapter._parse_response_body(body)
        assert content == ""

    def test_parse_cohere_response(self):
        adapter = _make_bedrock_adapter("cohere.command-r-v1:0")
        body = json.dumps({"text": "Cohere response"})
        content, usage = adapter._parse_response_body(body)
        assert content == "Cohere response"
        assert usage.total_tokens == 0

    def test_parse_ai21_response(self):
        adapter = _make_bedrock_adapter("ai21.jamba-instruct-v1:0")
        body = json.dumps({"completions": [{"data": {"text": "AI21 response"}}]})
        content, usage = adapter._parse_response_body(body)
        assert content == "AI21 response"

    def test_parse_ai21_empty_completions(self):
        adapter = _make_bedrock_adapter("ai21.jamba-instruct-v1:0")
        body = json.dumps({"completions": []})
        content, usage = adapter._parse_response_body(body)
        assert content == ""

    def test_parse_generic_response(self):
        adapter = _make_bedrock_adapter("unknown.model-v1")
        adapter._provider = "unknown"
        body = json.dumps({"completion": "generic output"})
        content, usage = adapter._parse_response_body(body)
        assert content == "generic output"


class TestBedrockAdapterTokensAndCost:
    """Tests for count_tokens and estimate_cost."""

    def test_count_tokens_anthropic(self):
        adapter = _make_bedrock_adapter("anthropic.claude-sonnet-4-6-v1:0")
        messages = [LLMMessage(role="user", content="Hello world")]
        count = adapter.count_tokens(messages)
        assert count > 0

    def test_count_tokens_meta(self):
        adapter = _make_bedrock_adapter("meta.llama3-8b-instruct-v1:0")
        messages = [LLMMessage(role="user", content="Hello world")]
        count = adapter.count_tokens(messages)
        assert count > 0

    def test_count_tokens_generic(self):
        adapter = _make_bedrock_adapter("cohere.command-r-v1:0")
        messages = [LLMMessage(role="user", content="Hello world")]
        count = adapter.count_tokens(messages)
        assert count > 0

    def test_estimate_cost_known_model(self):
        adapter = _make_bedrock_adapter("anthropic.claude-sonnet-4-6-v1:0")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0
        assert cost.currency == "USD"

    def test_estimate_cost_unknown_model(self):
        adapter = _make_bedrock_adapter("unknown.model-v1")
        adapter._provider = "unknown"
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd > 0

    def test_estimate_cost_zero_tokens(self):
        adapter = _make_bedrock_adapter("anthropic.claude-sonnet-4-6-v1:0")
        cost = adapter.estimate_cost(0, 0)
        assert cost.total_cost_usd == 0.0


class TestBedrockAdapterStreamAndMisc:
    """Tests for streaming helpers and misc methods."""

    def test_get_streaming_mode(self):
        adapter = _make_bedrock_adapter()
        assert adapter.get_streaming_mode() == StreamingMode.SUPPORTED

    def test_get_provider_name(self):
        adapter = _make_bedrock_adapter("anthropic.claude-sonnet-4-6-v1:0")
        assert adapter.get_provider_name() == "bedrock-anthropic"

    def test_extract_anthropic_chunk_text(self):
        result = BedrockAdapter._extract_anthropic_chunk_text(
            {"delta": {"type": "content_block_delta", "delta": {"text": "chunk"}}}
        )
        assert result == "chunk"

    def test_extract_anthropic_chunk_text_none(self):
        result = BedrockAdapter._extract_anthropic_chunk_text({"delta": {"type": "other"}})
        assert result is None

    def test_extract_meta_chunk_text(self):
        result = BedrockAdapter._extract_meta_chunk_text({"generation": "meta chunk"})
        assert result == "meta chunk"

    def test_extract_amazon_chunk_text(self):
        result = BedrockAdapter._extract_amazon_chunk_text({"outputText": "titan chunk"})
        assert result == "titan chunk"

    def test_extract_generic_chunk_text(self):
        result = BedrockAdapter._extract_generic_chunk_text({"text": "generic"})
        assert result == "generic"

    def test_extract_stream_text_no_chunk(self):
        adapter = _make_bedrock_adapter()
        assert adapter._extract_stream_text({}) is None

    def test_build_streaming_params(self):
        adapter = _make_bedrock_adapter()
        messages = [LLMMessage(role="user", content="Hi")]
        params = adapter._build_streaming_params(messages, 0.7, None, 1.0, None)
        assert params["modelId"] == "anthropic.claude-sonnet-4-6-v1:0"
        assert "body" in params

    def test_build_streaming_params_with_guardrails(self):
        config = AWSBedrockAdapterConfig.from_environment(model="anthropic.claude-sonnet-4-6-v1:0")
        config.guardrails_id = "gr-123"
        config.guardrails_version = "1"
        adapter = BedrockAdapter(config=config)
        messages = [LLMMessage(role="user", content="Hi")]
        params = adapter._build_streaming_params(messages, 0.7, None, 1.0, None)
        assert params["guardrailIdentifier"] == "gr-123"
        assert params["guardrailVersion"] == "1"

    def test_format_generic_prompt(self):
        adapter = _make_bedrock_adapter()
        messages = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(role="user", content="usr"),
            LLMMessage(role="assistant", content="asst"),
        ]
        prompt = adapter._format_generic_prompt(messages, final_suffix="END")
        assert "sys" in prompt
        assert "usr" in prompt
        assert "asst" in prompt
        assert prompt.endswith("END")


class TestBedrockAdapterAsyncClient:
    """Tests for async client creation."""

    def test_get_async_client_no_aioboto3(self):
        adapter = _make_bedrock_adapter()
        with patch.dict("sys.modules", {"aioboto3": None}):
            with patch("builtins.__import__", side_effect=ImportError("no aioboto3")):
                adapter._async_client = None
                result = adapter._get_async_client()
                assert result is None


class TestBedrockAdapterHealthCheck:
    """Tests for health_check."""

    async def test_health_check_failure(self):
        adapter = _make_bedrock_adapter()
        adapter.acomplete = AsyncMock(side_effect=RuntimeError("connection refused"))
        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "failed" in result.message.lower()
