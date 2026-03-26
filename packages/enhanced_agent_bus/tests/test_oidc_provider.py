"""Tests for OIDC Provider module.

Covers OIDCProviderMetadata, OIDCConfig, OIDCTokens, OIDCProvider discovery,
token acquisition, ID token validation, JWKS, authorization URL, logout URL,
and statistics.
"""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import (
    OAuth2Config,
    OAuth2Provider,
    OAuth2Token,
)
from enhanced_agent_bus.mcp_integration.auth.oidc_provider import (
    JWKSCache,
    OIDCConfig,
    OIDCProvider,
    OIDCProviderMetadata,
    OIDCTokens,
)

# ---------------------------------------------------------------------------
# OIDCProviderMetadata
# ---------------------------------------------------------------------------


class TestOIDCProviderMetadata:
    def test_from_dict_minimal(self):
        data = {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
        }
        meta = OIDCProviderMetadata.from_dict(data)
        assert meta.issuer == "https://idp.example.com"
        assert meta.userinfo_endpoint is None

    def test_from_dict_full(self):
        data = {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "userinfo_endpoint": "https://idp.example.com/userinfo",
            "jwks_uri": "https://idp.example.com/jwks",
            "scopes_supported": ["openid", "profile"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "claims_supported": ["sub", "email"],
        }
        meta = OIDCProviderMetadata.from_dict(data)
        assert meta.jwks_uri == "https://idp.example.com/jwks"
        assert "openid" in meta.scopes_supported

    def test_to_dict(self):
        meta = OIDCProviderMetadata(
            issuer="https://idp.example.com",
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
        )
        d = meta.to_dict()
        assert d["issuer"] == "https://idp.example.com"
        assert "discovered_at" in d
        assert "constitutional_hash" in d


# ---------------------------------------------------------------------------
# OIDCConfig
# ---------------------------------------------------------------------------


class TestOIDCConfig:
    def test_defaults(self):
        cfg = OIDCConfig(issuer_url="https://idp.example.com")
        assert cfg.discovery_path == "/.well-known/openid-configuration"
        assert "openid" in cfg.default_scopes
        assert cfg.validate_id_token is True
        assert cfg.use_pkce is True

    def test_custom(self):
        cfg = OIDCConfig(
            issuer_url="https://idp.example.com",
            client_id="cid",
            client_secret="csec",
            clock_skew_seconds=120,
        )
        assert cfg.client_id == "cid"
        assert cfg.clock_skew_seconds == 120


# ---------------------------------------------------------------------------
# OIDCTokens
# ---------------------------------------------------------------------------


class TestOIDCTokens:
    def _make_oauth2_token(self):
        return OAuth2Token(access_token="access123")

    def test_subject(self):
        tokens = OIDCTokens(
            oauth2_token=self._make_oauth2_token(),
            id_token_claims={"sub": "user1"},
        )
        assert tokens.subject == "user1"

    def test_email_from_claims(self):
        tokens = OIDCTokens(
            oauth2_token=self._make_oauth2_token(),
            id_token_claims={"email": "user@example.com"},
        )
        assert tokens.email == "user@example.com"

    def test_email_from_userinfo(self):
        tokens = OIDCTokens(
            oauth2_token=self._make_oauth2_token(),
            id_token_claims={},
            userinfo={"email": "user@example.com"},
        )
        assert tokens.email == "user@example.com"

    def test_name_from_claims(self):
        tokens = OIDCTokens(
            oauth2_token=self._make_oauth2_token(),
            id_token_claims={"name": "John"},
        )
        assert tokens.name == "John"

    def test_name_from_userinfo(self):
        tokens = OIDCTokens(
            oauth2_token=self._make_oauth2_token(),
            id_token_claims={},
            userinfo={"name": "Jane"},
        )
        assert tokens.name == "Jane"

    def test_to_dict(self):
        tokens = OIDCTokens(
            oauth2_token=self._make_oauth2_token(),
            id_token_claims={"sub": "u1"},
            validated=True,
        )
        d = tokens.to_dict()
        assert d["subject"] == "u1"
        assert d["validated"] is True
        assert "constitutional_hash" in d


# ---------------------------------------------------------------------------
# JWKSCache
# ---------------------------------------------------------------------------


class TestJWKSCache:
    def test_creation(self):
        now = datetime.now(UTC)
        cache = JWKSCache(
            keys=[{"kty": "RSA", "kid": "k1"}],
            fetched_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert len(cache.keys) == 1
        assert cache.expires_at > now


# ---------------------------------------------------------------------------
# OIDCProvider
# ---------------------------------------------------------------------------


class TestOIDCProvider:
    def _make_config(self, **overrides):
        defaults = {
            "issuer_url": "https://idp.example.com",
            "client_id": "test-client",
            "client_secret": "test-secret",
        }
        defaults.update(overrides)
        return OIDCConfig(**defaults)

    def _make_provider(self, **overrides):
        return OIDCProvider(self._make_config(**overrides))

    # --- Discovery ---

    @pytest.mark.asyncio
    async def test_discover_no_httpx(self):
        provider = self._make_provider()
        with patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE", False):
            result = await provider.discover()
            assert result is None

    @pytest.mark.asyncio
    async def test_discover_cached(self):
        provider = self._make_provider()
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp.example.com",
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
        )
        result = await provider.discover()
        assert result is provider._metadata

    @pytest.mark.asyncio
    async def test_discover_cached_expired(self):
        provider = self._make_provider(discovery_cache_ttl_seconds=0)
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp.example.com",
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            discovered_at=datetime.now(UTC) - timedelta(hours=2),
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.httpx") as mock_httpx,
            patch("enhanced_agent_bus.mcp_integration.auth.oidc_provider.HTTPX_AVAILABLE", True),
        ):
            mock_httpx.AsyncClient.return_value = mock_client
            result = await provider.discover()
            assert result is not None
            assert provider._stats["discoveries"] == 1

    # --- acquire_tokens ---

    @pytest.mark.asyncio
    async def test_acquire_tokens_no_provider(self):
        provider = self._make_provider()
        # Mock discover to fail
        with patch.object(provider, "discover", new_callable=AsyncMock, return_value=None):
            result = await provider.acquire_tokens()
            assert result is None

    @pytest.mark.asyncio
    async def test_acquire_tokens_ensures_openid_scope(self):
        provider = self._make_provider()
        mock_oauth2 = MagicMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=None)
        mock_oauth2.get_pkce_verifier = MagicMock(return_value=None)
        provider._oauth2_provider = mock_oauth2

        await provider.acquire_tokens(scopes=["profile"])
        call_args = mock_oauth2.acquire_token.call_args
        assert "openid" in call_args.kwargs["scopes"]

    @pytest.mark.asyncio
    async def test_acquire_tokens_returns_none_on_failure(self):
        provider = self._make_provider()
        mock_oauth2 = MagicMock()
        mock_oauth2.acquire_token = AsyncMock(return_value=None)
        mock_oauth2.get_pkce_verifier = MagicMock(return_value=None)
        provider._oauth2_provider = mock_oauth2

        result = await provider.acquire_tokens()
        assert result is None

    @pytest.mark.asyncio
    async def test_acquire_tokens_success_no_id_token(self):
        provider = self._make_provider()
        mock_oauth2 = MagicMock()
        mock_token = OAuth2Token(access_token="acc123", id_token=None)
        mock_oauth2.acquire_token = AsyncMock(return_value=mock_token)
        mock_oauth2.get_pkce_verifier = MagicMock(return_value=None)
        provider._oauth2_provider = mock_oauth2

        result = await provider.acquire_tokens()
        assert result is not None
        assert result.validated is False
        assert result.id_token_claims == {}

    # --- get_userinfo ---

    @pytest.mark.asyncio
    async def test_get_userinfo_no_metadata(self):
        provider = self._make_provider()
        result = await provider.get_userinfo("token123")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_userinfo_no_endpoint(self):
        provider = self._make_provider()
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp",
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
            userinfo_endpoint=None,
        )
        result = await provider.get_userinfo("token123")
        assert result is None

    # --- _decode_jwt_payload ---

    def test_decode_jwt_payload(self):
        provider = self._make_provider()
        payload = {"sub": "user1", "email": "u@example.com"}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        token = f"header.{encoded}.signature"
        result = provider._decode_jwt_payload(token)
        assert result["sub"] == "user1"

    def test_decode_jwt_payload_invalid_format(self):
        provider = self._make_provider()
        with pytest.raises(ValueError, match="Invalid JWT format"):
            provider._decode_jwt_payload("not.a.valid.jwt.token")

    # --- _compute_at_hash ---

    def test_compute_at_hash_sha256(self):
        provider = self._make_provider()
        at_hash = provider._compute_at_hash("access_token_value", {"alg": "RS256"})
        # Manually compute expected
        h = hashlib.sha256("access_token_value".encode()).digest()
        expected = base64.urlsafe_b64encode(h[: len(h) // 2]).decode().rstrip("=")
        assert at_hash == expected

    def test_compute_at_hash_sha384(self):
        provider = self._make_provider()
        at_hash = provider._compute_at_hash("token", {"alg": "RS384"})
        h = hashlib.sha384("token".encode()).digest()
        expected = base64.urlsafe_b64encode(h[: len(h) // 2]).decode().rstrip("=")
        assert at_hash == expected

    def test_compute_at_hash_sha512(self):
        provider = self._make_provider()
        at_hash = provider._compute_at_hash("token", {"alg": "RS512"})
        h = hashlib.sha512("token".encode()).digest()
        expected = base64.urlsafe_b64encode(h[: len(h) // 2]).decode().rstrip("=")
        assert at_hash == expected

    def test_compute_at_hash_default(self):
        provider = self._make_provider()
        at_hash = provider._compute_at_hash("token", {})
        h = hashlib.sha256("token".encode()).digest()
        expected = base64.urlsafe_b64encode(h[: len(h) // 2]).decode().rstrip("=")
        assert at_hash == expected

    # --- build_authorization_url ---

    def test_build_authorization_url_no_provider(self):
        provider = self._make_provider()
        result = provider.build_authorization_url("https://app/callback")
        assert result is None

    def test_build_authorization_url_with_provider(self):
        provider = self._make_provider()
        mock_oauth2 = MagicMock()
        mock_oauth2.build_authorization_url.return_value = (
            "https://idp/authorize?client_id=test",
            "state123",
            None,
        )
        provider._oauth2_provider = mock_oauth2

        result = provider.build_authorization_url(
            "https://app/callback",
            login_hint="user@example.com",
            prompt="consent",
        )
        assert result is not None
        url, state, nonce = result
        assert url == "https://idp/authorize?client_id=test"
        assert nonce is not None

    # --- build_logout_url ---

    def test_build_logout_url_no_metadata(self):
        provider = self._make_provider()
        result = provider.build_logout_url()
        assert result is None

    def test_build_logout_url_no_end_session(self):
        provider = self._make_provider()
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp",
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
        )
        result = provider.build_logout_url()
        assert result is None

    def test_build_logout_url_with_params(self):
        provider = self._make_provider()
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp",
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
            end_session_endpoint="https://idp/logout",
        )
        result = provider.build_logout_url(
            id_token_hint="tok",
            post_logout_redirect_uri="https://app",
            state="s1",
        )
        assert "id_token_hint=tok" in result
        assert "post_logout_redirect_uri=https://app" in result

    def test_build_logout_url_no_params(self):
        provider = self._make_provider()
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp",
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
            end_session_endpoint="https://idp/logout",
        )
        result = provider.build_logout_url()
        assert result == "https://idp/logout"

    # --- Metadata & Stats ---

    def test_get_metadata_none(self):
        provider = self._make_provider()
        assert provider.get_metadata() is None

    def test_get_stats(self):
        provider = self._make_provider()
        stats = provider.get_stats()
        assert stats["discoveries"] == 0
        assert stats["metadata_cached"] is False
        assert "constitutional_hash" in stats

    # --- _fetch_jwks ---

    @pytest.mark.asyncio
    async def test_fetch_jwks_no_metadata(self):
        provider = self._make_provider()
        result = await provider._fetch_jwks()
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_jwks_no_jwks_uri(self):
        provider = self._make_provider()
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp",
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
        )
        result = await provider._fetch_jwks()
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_jwks_cache_hit(self):
        provider = self._make_provider()
        provider._metadata = OIDCProviderMetadata(
            issuer="https://idp",
            authorization_endpoint="https://idp/authorize",
            token_endpoint="https://idp/token",
            jwks_uri="https://idp/jwks",
        )
        keys = [{"kty": "RSA", "kid": "k1"}]
        provider._jwks_cache = JWKSCache(
            keys=keys,
            fetched_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        result = await provider._fetch_jwks()
        assert result == keys

    # --- _validate_id_token (validation disabled) ---

    @pytest.mark.asyncio
    async def test_validate_id_token_disabled(self):
        provider = self._make_provider(validate_id_token=False)
        payload = {"sub": "user1"}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        token = f"header.{encoded}.sig"
        claims, errors = await provider._validate_id_token(token, "access_token")
        assert claims["sub"] == "user1"
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_validate_id_token_disabled_bad_token(self):
        provider = self._make_provider(validate_id_token=False)
        claims, errors = await provider._validate_id_token("badtoken", "access_token")
        assert len(errors) > 0
