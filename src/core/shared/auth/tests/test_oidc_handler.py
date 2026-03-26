"""Comprehensive tests for OIDC handler.

Constitutional Hash: 608508a9bd224290

Covers:
- Dataclass construction and validation (OIDCProviderConfig, OIDCTokenResponse, OIDCUserInfo)
- OIDCHandler registration, lookup, listing
- Async flows: initiate_login, handle_callback, refresh_token, logout
- PKCE code challenge generation
- Pending state management and eviction (H-4 DoS fix)
- Error paths: missing provider, invalid state, provider mismatch, network errors
- Edge cases: empty claims, Azure AD group claims, metadata caching
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shared.auth.oidc_handler import (
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
# Fixtures
# ---------------------------------------------------------------------------

MOCK_METADATA: dict = {
    "issuer": "https://accounts.google.com",
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
    "end_session_endpoint": "https://accounts.google.com/logout",
}

VALID_PROVIDER_KWARGS: dict = {
    "name": "google",
    "client_id": "test-client-id",
    "client_secret": "real-production-secret-abc123",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


@pytest.fixture()
def handler() -> OIDCHandler:
    return OIDCHandler()


@pytest.fixture()
def registered_handler(handler: OIDCHandler) -> OIDCHandler:
    handler.register_provider(**VALID_PROVIDER_KWARGS)
    return handler


def _mock_http_response(*, status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b'{"ok":true}' if json_data else b""
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# _normalize_secret_sentinel
# ---------------------------------------------------------------------------


class TestNormalizeSecretSentinel:
    def test_strips_and_lowercases(self):
        assert _normalize_secret_sentinel("  Replace-Me ") == "replaceme"

    def test_removes_non_alnum(self):
        assert _normalize_secret_sentinel("your--secret!!") == "yoursecret"

    def test_empty_string(self):
        assert _normalize_secret_sentinel("") == ""


# ---------------------------------------------------------------------------
# OIDCError hierarchy
# ---------------------------------------------------------------------------


class TestOIDCErrors:
    def test_base_error_status(self):
        assert OIDCError.http_status_code == 500

    def test_config_error_status(self):
        assert OIDCConfigurationError.http_status_code == 500

    def test_auth_error_status(self):
        assert OIDCAuthenticationError.http_status_code == 401

    def test_token_error_status(self):
        assert OIDCTokenError.http_status_code == 401

    def test_provider_error_status(self):
        assert OIDCProviderError.http_status_code == 502

    def test_inheritance(self):
        err = OIDCConfigurationError("bad config")
        assert isinstance(err, OIDCError)


# ---------------------------------------------------------------------------
# OIDCProviderConfig
# ---------------------------------------------------------------------------


class TestOIDCProviderConfig:
    def test_valid_config(self):
        config = OIDCProviderConfig(**VALID_PROVIDER_KWARGS)
        assert config.name == "google"
        assert config.use_pkce is True
        assert config.scopes == list(DEFAULT_SCOPES)
        assert config.extra_params == {}

    def test_custom_scopes(self):
        config = OIDCProviderConfig(**{**VALID_PROVIDER_KWARGS, "scopes": ["openid", "custom"]})
        assert config.scopes == ["openid", "custom"]

    def test_empty_name_rejected(self):
        with pytest.raises(OIDCConfigurationError, match="Provider name is required"):
            OIDCProviderConfig(
                name="",
                client_id="cid",
                client_secret="secret-value-ok",
                server_metadata_url="https://example.com",
            )

    def test_empty_client_id_rejected(self):
        with pytest.raises(OIDCConfigurationError, match="Client ID is required"):
            OIDCProviderConfig(
                name="test",
                client_id="",
                client_secret="secret-value-ok",
                server_metadata_url="https://example.com",
            )

    def test_empty_client_secret_rejected(self):
        with pytest.raises(OIDCConfigurationError, match="Client secret is required"):
            OIDCProviderConfig(
                name="test",
                client_id="cid",
                client_secret="",
                server_metadata_url="https://example.com",
            )

    def test_empty_metadata_url_rejected(self):
        with pytest.raises(OIDCConfigurationError, match="Server metadata URL is required"):
            OIDCProviderConfig(
                name="test",
                client_id="cid",
                client_secret="secret-value-ok",
                server_metadata_url="",
            )

    def test_placeholder_replace_me_rejected(self):
        with pytest.raises(OIDCConfigurationError, match="placeholder value"):
            OIDCProviderConfig(
                name="t",
                client_id="c",
                client_secret="REPLACE_ME",  # pragma: allowlist secret
                server_metadata_url="https://x.com",
            )

    def test_placeholder_your_secret_rejected(self):
        with pytest.raises(OIDCConfigurationError, match="placeholder value"):
            OIDCProviderConfig(
                name="t",
                client_id="c",
                client_secret="your-secret",  # pragma: allowlist secret
                server_metadata_url="https://x.com",
            )

    def test_placeholder_variant_with_spaces(self):
        with pytest.raises(OIDCConfigurationError, match="placeholder value"):
            OIDCProviderConfig(
                name="t",
                client_id="c",
                client_secret=" replace-me ",
                server_metadata_url="https://x.com",
            )


# ---------------------------------------------------------------------------
# OIDCTokenResponse
# ---------------------------------------------------------------------------


class TestOIDCTokenResponse:
    def test_from_dict_full(self):
        data = {
            "access_token": "at-123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "rt-456",
            "id_token": "idt-789",
            "scope": "openid profile",
        }
        resp = OIDCTokenResponse.from_dict(data)
        assert resp.access_token == "at-123"
        assert resp.token_type == "Bearer"
        assert resp.expires_in == 3600
        assert resp.refresh_token == "rt-456"
        assert resp.id_token == "idt-789"
        assert resp.scope == "openid profile"
        assert resp.raw_response is data

    def test_from_dict_minimal(self):
        data = {"access_token": "at"}
        resp = OIDCTokenResponse.from_dict(data)
        assert resp.access_token == "at"
        assert resp.token_type == "Bearer"
        assert resp.expires_in is None
        assert resp.refresh_token is None
        assert resp.id_token is None
        assert resp.scope is None

    def test_from_dict_empty_access_token(self):
        resp = OIDCTokenResponse.from_dict({})
        assert resp.access_token == ""


# ---------------------------------------------------------------------------
# OIDCUserInfo
# ---------------------------------------------------------------------------


class TestOIDCUserInfo:
    def test_from_claims_full(self):
        claims = {
            "sub": "user-1",
            "email": "u@e.com",
            "email_verified": True,
            "name": "User One",
            "given_name": "User",
            "family_name": "One",
            "picture": "https://pic.png",
            "locale": "en",
            "groups": ["admin"],
        }
        info = OIDCUserInfo.from_claims(claims)
        assert info.sub == "user-1"
        assert info.email == "u@e.com"
        assert info.email_verified is True
        assert info.name == "User One"
        assert info.groups == ["admin"]
        assert info.raw_claims is claims

    def test_from_claims_minimal(self):
        info = OIDCUserInfo.from_claims({"sub": "x"})
        assert info.sub == "x"
        assert info.email is None
        assert info.groups == []

    def test_from_claims_roles_fallback(self):
        info = OIDCUserInfo.from_claims({"sub": "x", "roles": ["editor"]})
        assert info.groups == ["editor"]

    def test_from_claims_azure_ad_groups(self):
        info = OIDCUserInfo.from_claims(
            {
                "sub": "x",
                "https://schemas.microsoft.com/claims/groups": ["g1", "g2"],
            }
        )
        assert info.groups == ["g1", "g2"]

    def test_from_claims_non_list_groups_ignored(self):
        info = OIDCUserInfo.from_claims({"sub": "x", "groups": "not-a-list"})
        assert info.groups == []

    def test_from_claims_empty(self):
        info = OIDCUserInfo.from_claims({})
        assert info.sub == ""


# ---------------------------------------------------------------------------
# OIDCHandler — sync methods
# ---------------------------------------------------------------------------


class TestOIDCHandlerSync:
    def test_init(self, handler: OIDCHandler):
        assert handler.list_providers() == []

    def test_register_provider(self, handler: OIDCHandler):
        handler.register_provider(**VALID_PROVIDER_KWARGS)
        assert "google" in handler.list_providers()

    def test_register_multiple_providers(self, handler: OIDCHandler):
        handler.register_provider(**VALID_PROVIDER_KWARGS)
        handler.register_provider(**{**VALID_PROVIDER_KWARGS, "name": "azure"})
        assert sorted(handler.list_providers()) == ["azure", "google"]

    def test_get_provider_success(self, registered_handler: OIDCHandler):
        config = registered_handler.get_provider("google")
        assert config.name == "google"
        assert config.client_id == "test-client-id"

    def test_get_provider_not_found(self, handler: OIDCHandler):
        with pytest.raises(OIDCConfigurationError, match="not registered"):
            handler.get_provider("missing")

    def test_validate_state_false(self, handler: OIDCHandler):
        assert handler.validate_state("nonexistent") is False

    def test_generate_state_is_url_safe(self, handler: OIDCHandler):
        state = handler._generate_state()
        assert len(state) > 20
        # URL-safe base64 chars only
        assert all(c.isalnum() or c in "-_" for c in state)

    def test_generate_code_verifier(self, handler: OIDCHandler):
        verifier = handler._generate_code_verifier()
        assert len(verifier) > 40

    def test_generate_code_challenge_s256(self, handler: OIDCHandler):
        verifier = "test-verifier-value"
        challenge = handler._generate_code_challenge(verifier)
        # Verify it matches expected SHA256 + base64url
        expected_digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_clear_expired_states_removes_old(self, handler: OIDCHandler):
        old_time = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
        handler._pending_states["old-state"] = {
            "provider": "test",
            "redirect_uri": "https://cb",
            "code_verifier": None,
            "nonce": "n",
            "created_at": old_time,
        }
        handler._pending_states["fresh-state"] = {
            "provider": "test",
            "redirect_uri": "https://cb",
            "code_verifier": None,
            "nonce": "n",
            "created_at": datetime.now(UTC).isoformat(),
        }
        removed = handler.clear_expired_states(max_age_seconds=600)
        assert removed == 1
        assert "old-state" not in handler._pending_states
        assert "fresh-state" in handler._pending_states

    def test_clear_expired_states_returns_zero_when_none_expired(self, handler: OIDCHandler):
        assert handler.clear_expired_states() == 0

    def test_evict_stale_pending_states(self, handler: OIDCHandler):
        old_time = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
        handler._pending_states["stale"] = {
            "provider": "p",
            "redirect_uri": "u",
            "code_verifier": None,
            "nonce": "n",
            "created_at": old_time,
        }
        handler._evict_stale_pending_states()
        assert "stale" not in handler._pending_states


# ---------------------------------------------------------------------------
# OIDCHandler — register_provider_from_model
# ---------------------------------------------------------------------------


class TestRegisterProviderFromModel:
    def test_non_oidc_provider_rejected(self, handler: OIDCHandler):
        model = MagicMock()
        model.is_oidc = False
        model.name = "saml-only"
        with pytest.raises(OIDCConfigurationError, match="not an OIDC provider"):
            handler.register_provider_from_model(model)

    def test_invalid_config_rejected(self, handler: OIDCHandler):
        model = MagicMock()
        model.is_oidc = True
        model.name = "bad"
        model.validate_oidc_config.return_value = ["missing client_id"]
        with pytest.raises(OIDCConfigurationError, match="missing client_id"):
            handler.register_provider_from_model(model)

    def test_valid_model_registers(self, handler: OIDCHandler):
        model = MagicMock()
        model.is_oidc = True
        model.name = "okta"
        model.validate_oidc_config.return_value = []
        model.oidc_client_id = "cid"
        model.oidc_client_secret = "real-secret-value-xyz"
        model.oidc_metadata_url = "https://okta.example.com/.well-known/openid-configuration"
        model.oidc_scope_list = ["openid", "profile"]
        model.get_config.return_value = {"prompt": "consent"}
        handler.register_provider_from_model(model)
        assert "okta" in handler.list_providers()


# ---------------------------------------------------------------------------
# OIDCHandler — async methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOIDCHandlerAsync:
    async def test_initiate_login_builds_url(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client

        auth_url, state = await registered_handler.initiate_login(
            "google", "https://app.test/callback"
        )

        assert "https://accounts.google.com/o/oauth2/v2/auth?" in auth_url
        assert "client_id=test-client-id" in auth_url
        assert "response_type=code" in auth_url
        assert "redirect_uri=https" in auth_url
        assert "state=" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url
        assert len(state) > 20
        assert registered_handler.validate_state(state) is True

    async def test_initiate_login_without_pkce(self, handler: OIDCHandler):
        handler.register_provider(**{**VALID_PROVIDER_KWARGS, "use_pkce": False})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        handler._http_client = mock_client

        auth_url, state = await handler.initiate_login("google", "https://cb")
        assert "code_challenge" not in auth_url
        registered_state = handler._pending_states.get(state)
        assert registered_state is not None
        assert registered_state["code_verifier"] is None

    async def test_initiate_login_unknown_provider(self, handler: OIDCHandler):
        with pytest.raises(OIDCConfigurationError, match="not registered"):
            await handler.initiate_login("unknown", "https://cb")

    async def test_initiate_login_no_auth_endpoint(self, registered_handler: OIDCHandler):
        meta_no_auth = {k: v for k, v in MOCK_METADATA.items() if k != "authorization_endpoint"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=meta_no_auth))
        registered_handler._http_client = mock_client

        with pytest.raises(OIDCProviderError, match="Authorization endpoint not found"):
            await registered_handler.initiate_login("google", "https://cb")

    async def test_initiate_login_evicts_at_capacity(self, registered_handler: OIDCHandler):
        """H-4: when pending states hit max, oldest is evicted."""
        registered_handler._max_pending_states = 2
        now = datetime.now(UTC).isoformat()
        registered_handler._pending_states["oldest"] = {
            "provider": "google",
            "redirect_uri": "https://cb",
            "code_verifier": None,
            "nonce": "n",
            "created_at": now,
        }
        registered_handler._pending_states["second"] = {
            "provider": "google",
            "redirect_uri": "https://cb",
            "code_verifier": None,
            "nonce": "n",
            "created_at": now,
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client

        _, state = await registered_handler.initiate_login("google", "https://cb")
        # oldest should have been evicted to make room
        assert "oldest" not in registered_handler._pending_states
        assert state in registered_handler._pending_states

    async def test_handle_callback_invalid_state(self, registered_handler: OIDCHandler):
        with pytest.raises(OIDCAuthenticationError, match="Invalid or expired state"):
            await registered_handler.handle_callback("google", "code", "bad-state")

    async def test_handle_callback_provider_mismatch(self, registered_handler: OIDCHandler):
        state = "test-state-123"
        registered_handler._pending_states[state] = {
            "provider": "azure",
            "redirect_uri": "https://cb",
            "code_verifier": None,
            "nonce": "nonce",
            "created_at": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(OIDCAuthenticationError, match="Provider mismatch"):
            await registered_handler.handle_callback("google", "code", state)

    async def test_handle_callback_success(self, registered_handler: OIDCHandler):
        """Full callback flow: state validation -> code exchange -> user info."""
        state = "valid-state"
        registered_handler._pending_states[state] = {
            "provider": "google",
            "redirect_uri": "https://app/callback",
            "code_verifier": "verifier-abc",
            "nonce": "nonce-123",
            "created_at": datetime.now(UTC).isoformat(),
        }

        token_response_data = {
            "access_token": "at-ok",
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": None,
        }
        userinfo_data = {
            "sub": "u-42",
            "email": "u@example.com",
            "email_verified": True,
            "name": "Test",
        }

        mock_client = AsyncMock()

        async def mock_get(url, **kwargs):
            if "well-known" in url or "openid-configuration" in url:
                return _mock_http_response(json_data=MOCK_METADATA)
            if "userinfo" in url:
                return _mock_http_response(json_data=userinfo_data)
            return _mock_http_response(json_data=MOCK_METADATA)

        async def mock_post(url, **kwargs):
            return _mock_http_response(json_data=token_response_data)

        mock_client.get = mock_get
        mock_client.post = mock_post
        registered_handler._http_client = mock_client

        user = await registered_handler.handle_callback("google", "auth-code", state)

        assert user.sub == "u-42"
        assert user.email == "u@example.com"
        # State should be consumed
        assert state not in registered_handler._pending_states

    async def test_handle_callback_uses_redirect_uri_param(self, registered_handler: OIDCHandler):
        """When redirect_uri is passed explicitly it takes precedence."""
        state = "s1"
        registered_handler._pending_states[state] = {
            "provider": "google",
            "redirect_uri": "https://stored-uri/cb",
            "code_verifier": None,
            "nonce": "n",
            "created_at": datetime.now(UTC).isoformat(),
        }

        captured_data: dict = {}

        async def mock_post(url, data=None, **kwargs):
            captured_data.update(data or {})
            return _mock_http_response(json_data={"access_token": "at"})

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        mock_client.post = mock_post
        registered_handler._http_client = mock_client

        # Patch _get_user_info to shortcut the full flow
        registered_handler._get_user_info = AsyncMock(return_value=OIDCUserInfo(sub="u1"))

        await registered_handler.handle_callback(
            "google", "code", state, redirect_uri="https://override/cb"
        )
        assert captured_data.get("redirect_uri") == "https://override/cb"

    async def test_exchange_code_no_token_endpoint(self, registered_handler: OIDCHandler):
        meta_no_token = {k: v for k, v in MOCK_METADATA.items() if k != "token_endpoint"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=meta_no_token))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        with pytest.raises(OIDCTokenError, match="Token endpoint not found"):
            await registered_handler._exchange_code(provider, "code", "https://cb")

    async def test_exchange_code_non_200(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        error_resp = _mock_http_response(
            status_code=400,
            json_data={"error": "invalid_grant", "error_description": "Code expired"},
        )
        # Override raise_for_status to not raise (exchange_code checks status_code directly)
        error_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=error_resp)
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        with pytest.raises(OIDCTokenError, match="Code expired"):
            await registered_handler._exchange_code(provider, "code", "https://cb")

    async def test_exchange_code_network_error(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        mock_client.post = AsyncMock(side_effect=RuntimeError("connection reset"))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        with pytest.raises(OIDCTokenError, match="connection reset"):
            await registered_handler._exchange_code(provider, "code", "https://cb")

    async def test_refresh_token_success(self, registered_handler: OIDCHandler):
        token_data = {"access_token": "new-at", "expires_in": 7200}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        mock_client.post = AsyncMock(return_value=_mock_http_response(json_data=token_data))
        registered_handler._http_client = mock_client

        result = await registered_handler.refresh_token("google", "old-rt")
        assert result.access_token == "new-at"
        assert result.expires_in == 7200

    async def test_refresh_token_no_endpoint(self, registered_handler: OIDCHandler):
        meta_no_token = {k: v for k, v in MOCK_METADATA.items() if k != "token_endpoint"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=meta_no_token))
        registered_handler._http_client = mock_client

        with pytest.raises(OIDCTokenError, match="Token endpoint not found"):
            await registered_handler.refresh_token("google", "rt")

    async def test_refresh_token_non_200(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        error_resp = _mock_http_response(status_code=400, json_data={"error": "invalid_grant"})
        error_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=error_resp)
        registered_handler._http_client = mock_client

        with pytest.raises(OIDCTokenError, match="Token refresh failed"):
            await registered_handler.refresh_token("google", "rt")

    async def test_refresh_token_unknown_provider(self, handler: OIDCHandler):
        with pytest.raises(OIDCConfigurationError, match="not registered"):
            await handler.refresh_token("missing", "rt")

    async def test_logout_with_session_endpoint(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client

        url = await registered_handler.logout(
            "google",
            id_token_hint="idt-hint",
            post_logout_redirect_uri="https://app/logged-out",
        )
        assert url is not None
        assert "https://accounts.google.com/logout?" in url
        assert "id_token_hint=idt-hint" in url
        assert "post_logout_redirect_uri=" in url
        assert "client_id=test-client-id" in url

    async def test_logout_no_session_endpoint(self, registered_handler: OIDCHandler):
        meta_no_logout = {k: v for k, v in MOCK_METADATA.items() if k != "end_session_endpoint"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=meta_no_logout))
        registered_handler._http_client = mock_client

        url = await registered_handler.logout("google")
        assert url is None

    async def test_logout_minimal_params(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client

        url = await registered_handler.logout("google")
        assert url is not None
        assert "id_token_hint" not in url

    async def test_close(self, handler: OIDCHandler):
        mock_client = AsyncMock()
        handler._http_client = mock_client
        await handler.close()
        mock_client.aclose.assert_awaited_once()
        assert handler._http_client is None

    async def test_close_when_no_client(self, handler: OIDCHandler):
        # Should not raise
        await handler.close()
        assert handler._http_client is None

    async def test_fetch_metadata_caching(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        # First call fetches
        meta1 = await registered_handler._fetch_metadata(provider)
        assert meta1["issuer"] == "https://accounts.google.com"
        assert mock_client.get.await_count == 1

        # Second call uses cache
        meta2 = await registered_handler._fetch_metadata(provider)
        assert meta2 == meta1
        assert mock_client.get.await_count == 1  # no additional call

    async def test_fetch_metadata_force_refresh(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        await registered_handler._fetch_metadata(provider)
        await registered_handler._fetch_metadata(provider, force_refresh=True)
        assert mock_client.get.await_count == 2

    async def test_fetch_metadata_error_uses_cache(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        # Prime the cache
        await registered_handler._fetch_metadata(provider)

        # Next fetch fails but cache is available
        mock_client.get = AsyncMock(side_effect=RuntimeError("network down"))
        meta = await registered_handler._fetch_metadata(provider, force_refresh=True)
        assert meta["issuer"] == "https://accounts.google.com"

    async def test_fetch_metadata_error_no_cache_raises(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("network down"))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        with pytest.raises(OIDCProviderError, match="Failed to fetch OIDC metadata"):
            await registered_handler._fetch_metadata(provider)

    async def test_decode_id_token_missing_jwks_uri_precedes_authlib_requirement(
        self, registered_handler: OIDCHandler
    ):
        provider = registered_handler.get_provider("google")
        registered_handler._fetch_metadata = AsyncMock(
            return_value={"issuer": MOCK_METADATA["issuer"]}
        )

        with patch("src.core.shared.auth.oidc_handler.HAS_AUTHLIB", False):
            with pytest.raises(OIDCTokenError, match="JWKS URI not found"):
                await registered_handler._decode_id_token("token", provider)

    async def test_decode_id_token_no_authlib_with_valid_metadata(
        self, registered_handler: OIDCHandler
    ):
        provider = registered_handler.get_provider("google")
        registered_handler._fetch_metadata = AsyncMock(return_value=MOCK_METADATA)

        with patch("src.core.shared.auth.oidc_handler.HAS_AUTHLIB", False):
            with pytest.raises(OIDCTokenError, match="authlib library"):
                await registered_handler._decode_id_token("token", provider)

    async def test_fetch_userinfo_success(self, registered_handler: OIDCHandler):
        userinfo = {"sub": "u1", "email": "a@b.com"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=MOCK_METADATA))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        # Prime metadata cache
        await registered_handler._fetch_metadata(provider)

        # Now mock the userinfo call
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=userinfo))
        result = await registered_handler._fetch_userinfo(provider, "access-token")
        assert result.sub == "u1"
        assert result.email == "a@b.com"

    async def test_fetch_userinfo_no_endpoint(self, registered_handler: OIDCHandler):
        meta_no_ui = {k: v for k, v in MOCK_METADATA.items() if k != "userinfo_endpoint"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=meta_no_ui))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        with pytest.raises(OIDCProviderError, match="Userinfo endpoint not found"):
            await registered_handler._fetch_userinfo(provider, "at")

    async def test_fetch_userinfo_non_200(self, registered_handler: OIDCHandler):
        mock_client = AsyncMock()
        # First call: metadata (cached already or fetched fresh)
        registered_handler._metadata_cache["google"] = MOCK_METADATA
        registered_handler._metadata_timestamps["google"] = datetime.now(UTC)

        error_resp = _mock_http_response(status_code=401, json_data={})
        error_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=error_resp)
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        with pytest.raises(OIDCProviderError, match="Userinfo request failed"):
            await registered_handler._fetch_userinfo(provider, "bad-at")

    async def test_get_user_info_fallback_to_userinfo_endpoint(
        self, registered_handler: OIDCHandler
    ):
        """When id_token decoding fails, falls back to userinfo endpoint."""
        registered_handler._metadata_cache["google"] = MOCK_METADATA
        registered_handler._metadata_timestamps["google"] = datetime.now(UTC)

        tokens = OIDCTokenResponse(
            access_token="at",
            id_token="invalid-jwt",
        )
        userinfo_data = {"sub": "fallback-user", "email": "fb@x.com"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=userinfo_data))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        # _decode_id_token will fail since we don't have real keys
        with patch.object(
            registered_handler,
            "_decode_id_token",
            new_callable=AsyncMock,
            side_effect=OIDCTokenError("invalid token"),
        ):
            result = await registered_handler._get_user_info(provider, tokens)

        assert result.sub == "fallback-user"

    async def test_get_user_info_from_id_token(self, registered_handler: OIDCHandler):
        """When id_token decoding succeeds, returns claims directly."""
        tokens = OIDCTokenResponse(access_token="at", id_token="valid-jwt")
        provider = registered_handler.get_provider("google")

        claims = {"sub": "jwt-user", "email": "jwt@x.com", "email_verified": True}
        with patch.object(
            registered_handler,
            "_decode_id_token",
            new_callable=AsyncMock,
            return_value=claims,
        ):
            result = await registered_handler._get_user_info(provider, tokens)

        assert result.sub == "jwt-user"

    async def test_get_user_info_no_id_token(self, registered_handler: OIDCHandler):
        """When no id_token, goes straight to userinfo endpoint."""
        registered_handler._metadata_cache["google"] = MOCK_METADATA
        registered_handler._metadata_timestamps["google"] = datetime.now(UTC)

        tokens = OIDCTokenResponse(access_token="at", id_token=None)
        userinfo_data = {"sub": "endpoint-user"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_http_response(json_data=userinfo_data))
        registered_handler._http_client = mock_client
        provider = registered_handler.get_provider("google")

        result = await registered_handler._get_user_info(provider, tokens)
        assert result.sub == "endpoint-user"

    async def test_get_http_client_creates_once(self, handler: OIDCHandler):
        client = await handler._get_http_client()
        assert client is not None
        client2 = await handler._get_http_client()
        assert client is client2
        # Cleanup
        await handler.close()
