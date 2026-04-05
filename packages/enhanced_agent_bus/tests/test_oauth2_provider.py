"""Tests for OAuth2 Provider module.

Covers OAuth2Config, OAuth2Token, OAuth2Provider, PKCE, authorization URL building,
token caching, introspection, and revocation flows.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import (
    OAuth2Config,
    OAuth2GrantType,
    OAuth2Provider,
    OAuth2Token,
    PKCEChallenge,
    TokenIntrospectionResult,
    TokenStatus,
)

# ---------------------------------------------------------------------------
# OAuth2Token dataclass tests
# ---------------------------------------------------------------------------


class TestOAuth2Token:
    def test_token_creation_basic(self):
        token = OAuth2Token(access_token="abc123")
        assert token.access_token == "abc123"
        assert token.token_type == "Bearer"
        assert token.status == TokenStatus.VALID

    def test_token_expires_at_calculated_from_expires_in(self):
        token = OAuth2Token(access_token="abc", expires_in=3600)
        assert token.expires_at is not None
        # expires_at should be ~3600 seconds after issued_at
        delta = (token.expires_at - token.issued_at).total_seconds()
        assert 3599 <= delta <= 3601

    def test_is_expired_false_when_no_expiry(self):
        token = OAuth2Token(access_token="abc")
        assert token.is_expired() is False

    def test_is_expired_true_when_past(self):
        token = OAuth2Token(
            access_token="abc",
            expires_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        assert token.is_expired() is True

    def test_is_expired_false_when_future(self):
        token = OAuth2Token(
            access_token="abc",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert token.is_expired() is False

    def test_needs_refresh_false_when_no_expiry(self):
        token = OAuth2Token(access_token="abc")
        assert token.needs_refresh() is False

    def test_needs_refresh_true_within_threshold(self):
        token = OAuth2Token(
            access_token="abc",
            expires_at=datetime.now(UTC) + timedelta(seconds=100),
        )
        assert token.needs_refresh(threshold_seconds=200) is True

    def test_needs_refresh_false_outside_threshold(self):
        token = OAuth2Token(
            access_token="abc",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert token.needs_refresh(threshold_seconds=300) is False

    def test_to_dict_truncates_long_token(self):
        long_token = "a" * 50
        token = OAuth2Token(access_token=long_token)
        d = token.to_dict()
        assert d["access_token"].endswith("...")
        assert len(d["access_token"]) == 23  # 20 + "..."

    def test_to_dict_preserves_short_token(self):
        token = OAuth2Token(access_token="short")
        d = token.to_dict()
        assert d["access_token"] == "short"

    def test_to_dict_fields(self):
        token = OAuth2Token(
            access_token="abc",
            refresh_token="ref",
            scope="openid",
            id_token="idt",
        )
        d = token.to_dict()
        assert d["has_refresh_token"] is True
        assert d["has_id_token"] is True
        assert d["scope"] == "openid"
        assert d["status"] == "valid"
        assert "constitutional_hash" in d


# ---------------------------------------------------------------------------
# OAuth2Config tests
# ---------------------------------------------------------------------------


class TestOAuth2Config:
    def test_defaults(self):
        cfg = OAuth2Config(token_endpoint="https://auth.example.com/token")
        assert cfg.timeout_seconds == 30
        assert cfg.use_pkce is True
        assert cfg.pkce_method == "S256"
        assert cfg.token_cache_enabled is True

    def test_custom_fields(self):
        cfg = OAuth2Config(
            token_endpoint="https://auth.example.com/token",
            client_id="cid",
            client_secret="csec",
            default_scopes=["read", "write"],
        )
        assert cfg.client_id == "cid"
        assert cfg.default_scopes == ["read", "write"]


# ---------------------------------------------------------------------------
# TokenIntrospectionResult tests
# ---------------------------------------------------------------------------


class TestTokenIntrospectionResult:
    def test_creation(self):
        result = TokenIntrospectionResult(active=True, scope="openid profile")
        assert result.active is True
        assert result.scope == "openid profile"

    def test_defaults(self):
        result = TokenIntrospectionResult(active=False)
        assert result.client_id is None
        assert result.extra == {}


# ---------------------------------------------------------------------------
# PKCEChallenge tests
# ---------------------------------------------------------------------------


class TestPKCEChallenge:
    def test_creation(self):
        challenge = PKCEChallenge(
            code_verifier="verifier",
            code_challenge="challenge",
            code_challenge_method="S256",
        )
        assert challenge.code_verifier == "verifier"
        assert challenge.created_at is not None


# ---------------------------------------------------------------------------
# OAuth2Provider tests
# ---------------------------------------------------------------------------


class TestOAuth2Provider:
    def _make_config(self, **overrides):
        defaults = {
            "token_endpoint": "https://auth.example.com/token",
            "client_id": "test-client",
            "client_secret": "test-secret",
        }
        defaults.update(overrides)
        return OAuth2Config(**defaults)

    def _make_provider(self, **overrides):
        return OAuth2Provider(self._make_config(**overrides))

    # --- PKCE ---

    def test_generate_pkce_challenge_s256(self):
        provider = self._make_provider()
        challenge = provider.generate_pkce_challenge()
        assert len(challenge.code_verifier) > 40
        assert challenge.code_challenge_method == "S256"
        assert challenge.code_challenge != challenge.code_verifier

    def test_generate_pkce_challenge_plain(self):
        provider = self._make_provider(pkce_method="plain")
        challenge = provider.generate_pkce_challenge()
        assert challenge.code_challenge == challenge.code_verifier

    def test_generate_pkce_with_state_stores(self):
        provider = self._make_provider()
        challenge = provider.generate_pkce_challenge(state="s1")
        assert "s1" in provider._pkce_challenges

    def test_get_pkce_verifier(self):
        provider = self._make_provider()
        challenge = provider.generate_pkce_challenge(state="s1")
        verifier = provider.get_pkce_verifier("s1")
        assert verifier == challenge.code_verifier
        # Should be consumed
        assert provider.get_pkce_verifier("s1") is None

    def test_get_pkce_verifier_unknown_state(self):
        provider = self._make_provider()
        assert provider.get_pkce_verifier("unknown") is None

    # --- Authorization URL ---

    def test_build_authorization_url(self):
        provider = self._make_provider(
            authorization_endpoint="https://auth.example.com/authorize",
        )
        url, state, pkce = provider.build_authorization_url(
            redirect_uri="https://app.example.com/callback",
            scopes=["openid", "profile"],
        )
        assert "https://auth.example.com/authorize?" in url
        assert "response_type=code" in url
        assert "client_id=test-client" in url
        assert state is not None
        assert pkce is not None

    def test_build_authorization_url_no_endpoint_raises(self):
        provider = self._make_provider()
        with pytest.raises(ValueError, match="Authorization endpoint not configured"):
            provider.build_authorization_url(redirect_uri="https://app/callback")

    def test_build_authorization_url_no_pkce(self):
        provider = self._make_provider(
            authorization_endpoint="https://auth.example.com/authorize",
            use_pkce=False,
        )
        url, state, pkce = provider.build_authorization_url(
            redirect_uri="https://app/callback",
        )
        assert pkce is None

    def test_build_authorization_url_extra_params(self):
        provider = self._make_provider(
            authorization_endpoint="https://auth.example.com/authorize",
        )
        url, _, _ = provider.build_authorization_url(
            redirect_uri="https://app/callback",
            extra_params={"prompt": "consent"},
        )
        assert "prompt=consent" in url

    def test_build_authorization_url_nonce(self):
        provider = self._make_provider(
            authorization_endpoint="https://auth.example.com/authorize",
        )
        url, _, _ = provider.build_authorization_url(
            redirect_uri="https://app/callback",
            nonce="test-nonce",
        )
        assert "nonce=test-nonce" in url

    # --- Cache ---

    def test_clear_cache(self):
        provider = self._make_provider()
        provider._token_cache["k1"] = OAuth2Token(access_token="t1")
        provider.generate_pkce_challenge(state="s1")
        provider.clear_cache()
        assert len(provider._token_cache) == 0
        assert len(provider._pkce_challenges) == 0

    # --- Stats ---

    def test_get_stats(self):
        provider = self._make_provider()
        stats = provider.get_stats()
        assert stats["tokens_acquired"] == 0
        assert stats["cached_tokens"] == 0
        assert "constitutional_hash" in stats

    # --- Token cache ---

    @pytest.mark.asyncio
    async def test_check_token_cache_miss(self):
        provider = self._make_provider()
        result = await provider._check_token_cache("key1")
        assert result is None
        assert provider._stats["cache_misses"] == 1

    @pytest.mark.asyncio
    async def test_check_token_cache_disabled(self):
        provider = self._make_provider(token_cache_enabled=False)
        result = await provider._check_token_cache("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_token_cache_hit(self):
        provider = self._make_provider()
        token = OAuth2Token(
            access_token="cached",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        provider._token_cache["key1"] = token
        result = await provider._check_token_cache("key1")
        assert result is not None
        assert result.access_token == "cached"
        assert provider._stats["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_check_token_cache_expired_removed(self):
        provider = self._make_provider()
        token = OAuth2Token(
            access_token="old",
            expires_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        provider._token_cache["key1"] = token
        result = await provider._check_token_cache("key1")
        assert result is None
        assert "key1" not in provider._token_cache

    @pytest.mark.asyncio
    async def test_store_token_in_cache(self):
        provider = self._make_provider()
        token = OAuth2Token(access_token="new")
        await provider._store_token_in_cache(token, "key1")
        assert "key1" in provider._token_cache

    @pytest.mark.asyncio
    async def test_store_token_in_cache_no_key(self):
        provider = self._make_provider()
        token = OAuth2Token(access_token="new")
        await provider._store_token_in_cache(token, None)
        assert len(provider._token_cache) == 0

    # --- Request data building ---

    def test_build_base_request_data(self):
        provider = self._make_provider()
        data = provider._build_base_request_data(["openid"])
        assert data["client_id"] == "test-client"
        assert data["client_secret"] == "test-secret"
        assert data["scope"] == "openid"

    def test_build_base_request_data_no_secret(self):
        provider = self._make_provider(client_secret="")
        data = provider._build_base_request_data(None)
        assert "client_secret" not in data
        assert "scope" not in data

    def test_build_grant_specific_client_credentials(self):
        provider = self._make_provider()
        data = provider._build_grant_specific_data(
            OAuth2GrantType.CLIENT_CREDENTIALS, None, None, None, None, None, None
        )
        assert data["grant_type"] == "client_credentials"

    def test_build_grant_specific_auth_code(self):
        provider = self._make_provider()
        data = provider._build_grant_specific_data(
            OAuth2GrantType.AUTHORIZATION_CODE,
            "code123",
            "https://app/cb",
            None,
            None,
            None,
            "verifier",
        )
        assert data["code"] == "code123"
        assert data["redirect_uri"] == "https://app/cb"
        assert data["code_verifier"] == "verifier"

    def test_build_grant_specific_auth_code_missing(self):
        provider = self._make_provider()
        result = provider._build_grant_specific_data(
            OAuth2GrantType.AUTHORIZATION_CODE, None, None, None, None, None, None
        )
        assert result is None

    def test_build_grant_specific_refresh(self):
        provider = self._make_provider()
        data = provider._build_grant_specific_data(
            OAuth2GrantType.REFRESH_TOKEN, None, None, "ref123", None, None, None
        )
        assert data["refresh_token"] == "ref123"

    def test_build_grant_specific_refresh_missing(self):
        provider = self._make_provider()
        result = provider._build_grant_specific_data(
            OAuth2GrantType.REFRESH_TOKEN, None, None, None, None, None, None
        )
        assert result is None

    def test_build_grant_specific_password(self):
        provider = self._make_provider()
        data = provider._build_grant_specific_data(
            OAuth2GrantType.PASSWORD, None, None, None, "user", "pass", None
        )
        assert data["username"] == "user"
        assert data["password"] == "pass"

    def test_build_grant_specific_password_missing(self):
        provider = self._make_provider()
        result = provider._build_grant_specific_data(
            OAuth2GrantType.PASSWORD, None, None, None, None, None, None
        )
        assert result is None

    def test_build_token_request_data_full(self):
        provider = self._make_provider()
        data = provider._build_token_request_data(
            OAuth2GrantType.CLIENT_CREDENTIALS,
            ["openid"],
            None,
            None,
            None,
            None,
            None,
            None,
        )
        assert data is not None
        assert data["grant_type"] == "client_credentials"
        assert data["scope"] == "openid"

    # --- parse_token_response ---

    def test_parse_token_response_success(self):
        provider = self._make_provider()
        token = provider._parse_token_response(
            {
                "access_token": "tok123",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "ref",
                "scope": "openid",
            }
        )
        assert token is not None
        assert token.access_token == "tok123"
        assert token.expires_in == 3600

    def test_parse_token_response_missing_access_token(self):
        provider = self._make_provider()
        token = provider._parse_token_response({"token_type": "Bearer"})
        assert token is None

    # --- acquire_token (mocked httpx) ---

    @pytest.mark.asyncio
    async def test_acquire_token_no_httpx(self):
        provider = self._make_provider()
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oauth2_provider.HTTPX_AVAILABLE", False
        ):
            result = await provider.acquire_token()
            assert result is None

    @pytest.mark.asyncio
    async def test_acquire_token_with_cache_hit(self):
        provider = self._make_provider()
        cached = OAuth2Token(
            access_token="cached",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        provider._token_cache["mykey"] = cached
        result = await provider.acquire_token(cache_key="mykey")
        assert result is not None
        assert result.access_token == "cached"

    # --- refresh_token ---

    @pytest.mark.asyncio
    async def test_refresh_token_no_refresh_token(self):
        provider = self._make_provider()
        token = OAuth2Token(access_token="abc")
        result = await provider.refresh_token(token)
        assert result is None

    # --- revoke_token ---

    @pytest.mark.asyncio
    async def test_revoke_token_no_endpoint(self):
        provider = self._make_provider()
        result = await provider.revoke_token("tok123")
        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_token_no_httpx(self):
        provider = self._make_provider(revocation_endpoint="https://auth/revoke")
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oauth2_provider.HTTPX_AVAILABLE", False
        ):
            result = await provider.revoke_token("tok123")
            assert result is False

    # --- introspect_token ---

    @pytest.mark.asyncio
    async def test_introspect_token_no_endpoint(self):
        provider = self._make_provider()
        result = await provider.introspect_token("tok123")
        assert result is None

    @pytest.mark.asyncio
    async def test_introspect_token_no_httpx(self):
        provider = self._make_provider(introspection_endpoint="https://auth/introspect")
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oauth2_provider.HTTPX_AVAILABLE", False
        ):
            result = await provider.introspect_token("tok123")
            assert result is None


# ---------------------------------------------------------------------------
# OAuth2GrantType enum
# ---------------------------------------------------------------------------


class TestOAuth2GrantType:
    def test_values(self):
        assert OAuth2GrantType.CLIENT_CREDENTIALS.value == "client_credentials"
        assert OAuth2GrantType.AUTHORIZATION_CODE.value == "authorization_code"
        assert OAuth2GrantType.REFRESH_TOKEN.value == "refresh_token"
        assert OAuth2GrantType.PASSWORD.value == "password"
        assert OAuth2GrantType.DEVICE_CODE.value == "device_code"


class TestTokenStatus:
    def test_values(self):
        assert TokenStatus.VALID.value == "valid"
        assert TokenStatus.EXPIRED.value == "expired"
        assert TokenStatus.REVOKED.value == "revoked"
