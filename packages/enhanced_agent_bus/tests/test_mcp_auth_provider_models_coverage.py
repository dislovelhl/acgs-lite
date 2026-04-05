# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/mcp_integration/auth/mcp_auth_provider/models.py

Targets ≥90% coverage on ProviderConfig, ManagedProviderToken,
MCPAuthProviderConfig, and AuthResult dataclasses.
"""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.enums import (
    ProviderType,
    TokenState,
)
from enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models import (
    AuthResult,
    ManagedProviderToken,
    MCPAuthProviderConfig,
    ProviderConfig,
)
from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import (
    OAuth2Config,
    OAuth2Token,
    TokenStatus,
)
from enhanced_agent_bus.mcp_integration.auth.oidc_provider import (
    OIDCConfig,
    OIDCTokens,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_oauth2_token(
    *,
    access_token: str = "test-access-token",
    expires_in: int | None = None,
    refresh_token: str | None = None,
) -> OAuth2Token:
    return OAuth2Token(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh_token,
    )


def _make_managed_token(
    *,
    token: OAuth2Token | None = None,
    state: TokenState = TokenState.VALID,
) -> ManagedProviderToken:
    if token is None:
        token = _make_oauth2_token()
    return ManagedProviderToken(
        token_id="tok-001",
        provider_name="test-provider",
        tool_name="my-tool",
        tenant_id="tenant-abc",
        token=token,
        state=state,
    )


# ---------------------------------------------------------------------------
# ProviderConfig - construction and defaults
# ---------------------------------------------------------------------------


class TestProviderConfigDefaults:
    def test_required_fields_only(self):
        cfg = ProviderConfig(provider_type=ProviderType.GENERIC, name="generic")
        assert cfg.provider_type == ProviderType.GENERIC
        assert cfg.name == "generic"
        assert cfg.client_id == ""
        assert cfg.client_secret == ""
        assert cfg.default_scopes == []
        assert cfg.issuer_url is None
        assert cfg.discovery_enabled is True
        assert cfg.token_endpoint is None
        assert cfg.authorization_endpoint is None
        assert cfg.revocation_endpoint is None
        assert cfg.introspection_endpoint is None
        assert cfg.userinfo_endpoint is None
        assert cfg.jwks_uri is None
        assert cfg.tenant_id is None
        assert cfg.okta_domain is None
        assert cfg.timeout_seconds == 30
        assert cfg.verify_ssl is True
        assert cfg.use_pkce is True
        assert cfg.token_cache_enabled is True
        assert cfg.token_refresh_threshold_seconds == 300
        assert cfg.metadata == {}
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_fields(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.AZURE_AD,
            name="azure",
            client_id="cid",
            client_secret="csecret",  # pragma: allowlist secret
            default_scopes=["openid", "profile"],
            tenant_id="tenant-xyz",
            timeout_seconds=60,
            verify_ssl=False,
            use_pkce=False,
        )
        assert cfg.client_id == "cid"
        assert cfg.client_secret == "csecret"  # pragma: allowlist secret
        assert cfg.default_scopes == ["openid", "profile"]
        assert cfg.tenant_id == "tenant-xyz"
        assert cfg.timeout_seconds == 60
        assert cfg.verify_ssl is False
        assert cfg.use_pkce is False


# ---------------------------------------------------------------------------
# ProviderConfig._get_issuer_url
# ---------------------------------------------------------------------------


class TestProviderConfigGetIssuerUrl:
    def test_explicit_issuer_url_wins(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.GOOGLE,
            name="g",
            issuer_url="https://custom.issuer.example.com",
        )
        assert cfg._get_issuer_url() == "https://custom.issuer.example.com"

    def test_azure_ad_with_tenant(self):
        cfg = ProviderConfig(provider_type=ProviderType.AZURE_AD, name="az", tenant_id="my-tenant")
        assert cfg._get_issuer_url() == ("https://login.microsoftonline.com/my-tenant/v2.0")

    def test_azure_ad_default_tenant(self):
        cfg = ProviderConfig(provider_type=ProviderType.AZURE_AD, name="az")
        assert cfg._get_issuer_url() == ("https://login.microsoftonline.com/common/v2.0")

    def test_okta_with_domain(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.OKTA, name="okta", okta_domain="my.okta.com"
        )
        assert cfg._get_issuer_url() == "https://my.okta.com"

    def test_okta_missing_domain_raises(self):
        cfg = ProviderConfig(provider_type=ProviderType.OKTA, name="okta")
        with pytest.raises((ValueError, ACGSValidationError), match="Okta domain required"):
            cfg._get_issuer_url()

    def test_google(self):
        cfg = ProviderConfig(provider_type=ProviderType.GOOGLE, name="google")
        assert cfg._get_issuer_url() == "https://accounts.google.com"

    def test_auth0_with_domain(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.AUTH0,
            name="auth0",
            metadata={"auth0_domain": "my.auth0.com"},
        )
        assert cfg._get_issuer_url() == "https://my.auth0.com"

    def test_auth0_missing_domain_raises(self):
        cfg = ProviderConfig(provider_type=ProviderType.AUTH0, name="auth0")
        with pytest.raises((ValueError, ACGSValidationError), match="Auth0 domain required"):
            cfg._get_issuer_url()

    def test_keycloak_with_realm_default_url(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.KEYCLOAK,
            name="kc",
            metadata={"keycloak_realm": "myrealm"},
        )
        assert cfg._get_issuer_url() == "http://localhost:8080/realms/myrealm"

    def test_keycloak_with_realm_and_custom_url(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.KEYCLOAK,
            name="kc",
            metadata={
                "keycloak_realm": "myrealm",
                "keycloak_url": "https://keycloak.example.com",
            },
        )
        assert cfg._get_issuer_url() == "https://keycloak.example.com/realms/myrealm"

    def test_keycloak_missing_realm_raises(self):
        cfg = ProviderConfig(provider_type=ProviderType.KEYCLOAK, name="kc")
        with pytest.raises((ValueError, ACGSValidationError), match="Keycloak realm required"):
            cfg._get_issuer_url()

    def test_unknown_provider_raises(self):
        cfg = ProviderConfig(provider_type=ProviderType.GITHUB, name="gh")
        with pytest.raises((ValueError, ACGSValidationError), match="Cannot determine issuer URL"):
            cfg._get_issuer_url()


# ---------------------------------------------------------------------------
# ProviderConfig._get_token_endpoint
# ---------------------------------------------------------------------------


class TestProviderConfigGetTokenEndpoint:
    def test_explicit_token_endpoint_wins(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.GITHUB,
            name="gh",
            token_endpoint="https://custom.token.example.com/token",
        )
        assert cfg._get_token_endpoint() == "https://custom.token.example.com/token"

    def test_azure_ad_with_tenant(self):
        cfg = ProviderConfig(provider_type=ProviderType.AZURE_AD, name="az", tenant_id="t1")
        assert cfg._get_token_endpoint() == (
            "https://login.microsoftonline.com/t1/oauth2/v2.0/token"
        )

    def test_azure_ad_default_tenant(self):
        cfg = ProviderConfig(provider_type=ProviderType.AZURE_AD, name="az")
        assert cfg._get_token_endpoint() == (
            "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        )

    def test_okta_with_domain(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.OKTA, name="okta", okta_domain="my.okta.com"
        )
        assert cfg._get_token_endpoint() == "https://my.okta.com/oauth2/v1/token"

    def test_okta_missing_domain_raises(self):
        cfg = ProviderConfig(provider_type=ProviderType.OKTA, name="okta")
        with pytest.raises((ValueError, ACGSValidationError), match="Okta domain required"):
            cfg._get_token_endpoint()

    def test_google(self):
        cfg = ProviderConfig(provider_type=ProviderType.GOOGLE, name="google")
        assert cfg._get_token_endpoint() == "https://oauth2.googleapis.com/token"

    def test_github(self):
        cfg = ProviderConfig(provider_type=ProviderType.GITHUB, name="gh")
        assert cfg._get_token_endpoint() == ("https://github.com/login/oauth/access_token")

    def test_fallback_raises(self):
        cfg = ProviderConfig(provider_type=ProviderType.GENERIC, name="gen")
        with pytest.raises((ValueError, ACGSValidationError), match="Token endpoint required"):
            cfg._get_token_endpoint()


# ---------------------------------------------------------------------------
# ProviderConfig._get_authorization_endpoint
# ---------------------------------------------------------------------------


class TestProviderConfigGetAuthorizationEndpoint:
    def test_explicit_authorization_endpoint_wins(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.GITHUB,
            name="gh",
            authorization_endpoint="https://custom.auth.example.com/auth",
        )
        assert cfg._get_authorization_endpoint() == ("https://custom.auth.example.com/auth")

    def test_azure_ad_with_tenant(self):
        cfg = ProviderConfig(provider_type=ProviderType.AZURE_AD, name="az", tenant_id="t2")
        assert cfg._get_authorization_endpoint() == (
            "https://login.microsoftonline.com/t2/oauth2/v2.0/authorize"
        )

    def test_azure_ad_default_tenant(self):
        cfg = ProviderConfig(provider_type=ProviderType.AZURE_AD, name="az")
        assert cfg._get_authorization_endpoint() == (
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        )

    def test_okta_with_domain(self):
        cfg = ProviderConfig(provider_type=ProviderType.OKTA, name="okta", okta_domain="x.okta.com")
        assert cfg._get_authorization_endpoint() == ("https://x.okta.com/oauth2/v1/authorize")

    def test_okta_without_domain_returns_none(self):
        cfg = ProviderConfig(provider_type=ProviderType.OKTA, name="okta")
        # No okta_domain, no explicit endpoint -- falls through to None
        assert cfg._get_authorization_endpoint() is None

    def test_google(self):
        cfg = ProviderConfig(provider_type=ProviderType.GOOGLE, name="google")
        assert cfg._get_authorization_endpoint() == ("https://accounts.google.com/o/oauth2/v2/auth")

    def test_github(self):
        cfg = ProviderConfig(provider_type=ProviderType.GITHUB, name="gh")
        assert cfg._get_authorization_endpoint() == ("https://github.com/login/oauth/authorize")

    def test_generic_returns_none(self):
        cfg = ProviderConfig(provider_type=ProviderType.GENERIC, name="gen")
        assert cfg._get_authorization_endpoint() is None


# ---------------------------------------------------------------------------
# ProviderConfig.to_oauth2_config
# ---------------------------------------------------------------------------


class TestProviderConfigToOAuth2Config:
    def test_google_produces_valid_oauth2_config(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.GOOGLE,
            name="google",
            client_id="cid",
            client_secret="csecret",  # pragma: allowlist secret
            default_scopes=["email"],
            revocation_endpoint="https://oauth2.googleapis.com/revoke",
            introspection_endpoint=None,
        )
        result = cfg.to_oauth2_config()
        assert isinstance(result, OAuth2Config)
        assert result.token_endpoint == "https://oauth2.googleapis.com/token"
        assert result.client_id == "cid"
        assert result.default_scopes == ["email"]
        assert result.revocation_endpoint == "https://oauth2.googleapis.com/revoke"

    def test_github_produces_valid_oauth2_config(self):
        cfg = ProviderConfig(provider_type=ProviderType.GITHUB, name="gh")
        result = cfg.to_oauth2_config()
        assert result.token_endpoint == "https://github.com/login/oauth/access_token"

    def test_explicit_token_endpoint_used(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.CUSTOM,
            name="custom",
            token_endpoint="https://custom.example.com/token",
        )
        result = cfg.to_oauth2_config()
        assert result.token_endpoint == "https://custom.example.com/token"


# ---------------------------------------------------------------------------
# ProviderConfig.to_oidc_config
# ---------------------------------------------------------------------------


class TestProviderConfigToOIDCConfig:
    def test_google_produces_valid_oidc_config(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.GOOGLE,
            name="google",
            client_id="cid",
            client_secret="csecret",  # pragma: allowlist secret
            default_scopes=["openid", "email"],
        )
        result = cfg.to_oidc_config()
        assert isinstance(result, OIDCConfig)
        assert result.issuer_url == "https://accounts.google.com"
        assert result.client_id == "cid"
        assert "openid" in result.default_scopes
        assert result.cache_discovery is True

    def test_empty_scopes_defaults_to_openid_profile_email(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.GOOGLE,
            name="google",
            default_scopes=[],  # empty
        )
        result = cfg.to_oidc_config()
        assert result.default_scopes == ["openid", "profile", "email"]

    def test_azure_ad_oidc_config(self):
        cfg = ProviderConfig(
            provider_type=ProviderType.AZURE_AD,
            name="az",
            tenant_id="tenantX",
        )
        result = cfg.to_oidc_config()
        assert "tenantX" in result.issuer_url


# ---------------------------------------------------------------------------
# ManagedProviderToken - construction and defaults
# ---------------------------------------------------------------------------


class TestManagedProviderTokenDefaults:
    def test_basic_construction(self):
        token = _make_oauth2_token()
        mpt = ManagedProviderToken(
            token_id="tok-1",
            provider_name="prov",
            tool_name=None,
            tenant_id=None,
            token=token,
        )
        assert mpt.token_id == "tok-1"
        assert mpt.tool_name is None
        assert mpt.tenant_id is None
        assert mpt.state == TokenState.VALID
        assert mpt.oidc_tokens is None
        assert mpt.refresh_count == 0
        assert mpt.error_count == 0
        assert mpt.metadata == {}
        assert mpt.constitutional_hash == CONSTITUTIONAL_HASH
        assert mpt.last_used is None

    def test_created_at_is_utc_aware(self):
        mpt = _make_managed_token()
        assert mpt.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# ManagedProviderToken.update_state
# ---------------------------------------------------------------------------


class TestManagedProviderTokenUpdateState:
    def test_revoked_state_immutable(self):
        mpt = _make_managed_token(state=TokenState.REVOKED)
        result = mpt.update_state()
        assert result == TokenState.REVOKED
        assert mpt.state == TokenState.REVOKED

    def test_valid_token_stays_valid(self):
        token = _make_oauth2_token(
            expires_in=3600,  # 1 hour -- not expired, not expiring soon
        )
        # Override expires_at to far future
        token.expires_at = datetime.now(UTC) + timedelta(hours=2)
        mpt = _make_managed_token(token=token)
        result = mpt.update_state(threshold_seconds=300)
        assert result == TokenState.VALID

    def test_expired_token_becomes_expired(self):
        token = _make_oauth2_token(expires_in=1)
        # Force it to be expired
        token.expires_at = datetime.now(UTC) - timedelta(seconds=10)
        mpt = _make_managed_token(token=token)
        result = mpt.update_state()
        assert result == TokenState.EXPIRED

    def test_expiring_soon_token(self):
        token = _make_oauth2_token(expires_in=60)
        # Set expires_at to 60s from now -- within threshold of 300s
        token.expires_at = datetime.now(UTC) + timedelta(seconds=60)
        mpt = _make_managed_token(token=token)
        result = mpt.update_state(threshold_seconds=300)
        assert result == TokenState.EXPIRING_SOON

    def test_no_expiry_token_stays_valid(self):
        token = _make_oauth2_token()  # no expires_in
        mpt = _make_managed_token(token=token)
        result = mpt.update_state()
        assert result == TokenState.VALID


# ---------------------------------------------------------------------------
# ManagedProviderToken.to_dict
# ---------------------------------------------------------------------------


class TestManagedProviderTokenToDict:
    def test_to_dict_keys_present(self):
        token = _make_oauth2_token()
        mpt = ManagedProviderToken(
            token_id="tok-dict",
            provider_name="prov",
            tool_name="tool",
            tenant_id="ten",
            token=token,
        )
        d = mpt.to_dict()
        assert d["token_id"] == "tok-dict"
        assert d["provider_name"] == "prov"
        assert d["tool_name"] == "tool"
        assert d["tenant_id"] == "ten"
        assert d["state"] == TokenState.VALID.value
        assert d["has_oidc_tokens"] is False
        assert d["refresh_count"] == 0
        assert d["error_count"] == 0
        assert d["last_used"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "token" in d
        assert "created_at" in d

    def test_to_dict_with_last_used(self):
        token = _make_oauth2_token()
        last_used = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        mpt = ManagedProviderToken(
            token_id="tok-lu",
            provider_name="prov",
            tool_name=None,
            tenant_id=None,
            token=token,
            last_used=last_used,
        )
        d = mpt.to_dict()
        assert d["last_used"] == last_used.isoformat()

    def test_to_dict_with_oidc_tokens(self):
        token = _make_oauth2_token()
        oidc = OIDCTokens(oauth2_token=token)
        mpt = ManagedProviderToken(
            token_id="tok-oidc",
            provider_name="prov",
            tool_name=None,
            tenant_id=None,
            token=token,
            oidc_tokens=oidc,
        )
        d = mpt.to_dict()
        assert d["has_oidc_tokens"] is True

    def test_to_dict_state_values(self):
        token = _make_oauth2_token()
        for state in TokenState:
            mpt = _make_managed_token(token=token, state=state)
            d = mpt.to_dict()
            assert d["state"] == state.value


# ---------------------------------------------------------------------------
# MCPAuthProviderConfig - construction and defaults
# ---------------------------------------------------------------------------


class TestMCPAuthProviderConfigDefaults:
    def test_defaults(self):
        cfg = MCPAuthProviderConfig()
        assert cfg.providers == {}
        assert cfg.default_provider is None
        assert cfg.credential_config is None
        assert cfg.refresh_config is None
        assert cfg.auto_refresh_enabled is True
        assert cfg.audit_config is None
        assert cfg.enable_audit is True
        assert cfg.fail_on_auth_error is True
        assert cfg.retry_on_401 is True
        assert cfg.max_retries == 3
        assert cfg.token_cache_ttl_seconds == 3600
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_fields(self):
        prov_cfg = ProviderConfig(provider_type=ProviderType.GITHUB, name="gh")
        cfg = MCPAuthProviderConfig(
            providers={"gh": prov_cfg},
            default_provider="gh",
            auto_refresh_enabled=False,
            enable_audit=False,
            fail_on_auth_error=False,
            retry_on_401=False,
            max_retries=5,
            token_cache_ttl_seconds=7200,
        )
        assert cfg.providers["gh"] == prov_cfg
        assert cfg.default_provider == "gh"
        assert cfg.auto_refresh_enabled is False
        assert cfg.enable_audit is False
        assert cfg.fail_on_auth_error is False
        assert cfg.retry_on_401 is False
        assert cfg.max_retries == 5
        assert cfg.token_cache_ttl_seconds == 7200


# ---------------------------------------------------------------------------
# AuthResult - construction and defaults
# ---------------------------------------------------------------------------


class TestAuthResultDefaults:
    def test_success_result_defaults(self):
        result = AuthResult(success=True)
        assert result.success is True
        assert result.token is None
        assert result.oidc_tokens is None
        assert result.error is None
        assert result.provider_name is None
        assert result.token_id is None
        assert result.duration_ms == 0.0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_failure_result(self):
        result = AuthResult(
            success=False,
            error="authentication failed",
            provider_name="my-provider",
            duration_ms=12.5,
        )
        assert result.success is False
        assert result.error == "authentication failed"
        assert result.provider_name == "my-provider"
        assert result.duration_ms == 12.5


# ---------------------------------------------------------------------------
# AuthResult.to_dict
# ---------------------------------------------------------------------------


class TestAuthResultToDict:
    def test_to_dict_success_no_tokens(self):
        result = AuthResult(success=True, provider_name="prov", token_id="tok")
        d = result.to_dict()
        assert d["success"] is True
        assert d["has_token"] is False
        assert d["has_oidc_tokens"] is False
        assert d["error"] is None
        assert d["provider_name"] == "prov"
        assert d["token_id"] == "tok"
        assert d["duration_ms"] == 0.0
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_token(self):
        token = _make_oauth2_token()
        result = AuthResult(success=True, token=token)
        d = result.to_dict()
        assert d["has_token"] is True

    def test_to_dict_with_oidc_tokens(self):
        token = _make_oauth2_token()
        oidc = OIDCTokens(oauth2_token=token)
        result = AuthResult(success=True, oidc_tokens=oidc)
        d = result.to_dict()
        assert d["has_oidc_tokens"] is True

    def test_to_dict_failure(self):
        result = AuthResult(
            success=False,
            error="some error",
            duration_ms=99.9,
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "some error"
        assert d["duration_ms"] == 99.9


# ---------------------------------------------------------------------------
# Module-level __all__
# ---------------------------------------------------------------------------


class TestModuleAll:
    def test_all_exports_present(self):
        import enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models as m

        for name in m.__all__:
            assert hasattr(m, name)

    def test_all_contains_expected_names(self):
        import enhanced_agent_bus.mcp_integration.auth.mcp_auth_provider.models as m

        expected = {"ProviderConfig", "ManagedProviderToken", "MCPAuthProviderConfig", "AuthResult"}
        assert set(m.__all__) == expected


# ---------------------------------------------------------------------------
# Edge cases - default_factory isolation
# ---------------------------------------------------------------------------


class TestDefaultFactoryIsolation:
    def test_provider_config_default_scopes_independent(self):
        a = ProviderConfig(provider_type=ProviderType.GENERIC, name="a")
        b = ProviderConfig(provider_type=ProviderType.GENERIC, name="b")
        a.default_scopes.append("openid")
        assert b.default_scopes == []

    def test_provider_config_metadata_independent(self):
        a = ProviderConfig(provider_type=ProviderType.GENERIC, name="a")
        b = ProviderConfig(provider_type=ProviderType.GENERIC, name="b")
        a.metadata["key"] = "val"
        assert b.metadata == {}

    def test_managed_provider_token_metadata_independent(self):
        t = _make_oauth2_token()
        a = ManagedProviderToken(
            token_id="a",
            provider_name="p",
            tool_name=None,
            tenant_id=None,
            token=t,
        )
        b = ManagedProviderToken(
            token_id="b",
            provider_name="p",
            tool_name=None,
            tenant_id=None,
            token=t,
        )
        a.metadata["x"] = 1
        assert b.metadata == {}

    def test_mcp_auth_provider_config_providers_independent(self):
        a = MCPAuthProviderConfig()
        b = MCPAuthProviderConfig()
        prov = ProviderConfig(provider_type=ProviderType.GENERIC, name="g")
        a.providers["p"] = prov
        assert b.providers == {}


# ---------------------------------------------------------------------------
# AuthResult with all fields populated
# ---------------------------------------------------------------------------


class TestAuthResultFull:
    def test_all_fields(self):
        token = _make_oauth2_token()
        oidc = OIDCTokens(oauth2_token=token)
        result = AuthResult(
            success=True,
            token=token,
            oidc_tokens=oidc,
            error=None,
            provider_name="prov",
            token_id="tok-123",
            duration_ms=3.14,
        )
        assert result.token is token
        assert result.oidc_tokens is oidc
        assert result.provider_name == "prov"
        assert result.token_id == "tok-123"
        assert result.duration_ms == 3.14
        d = result.to_dict()
        assert d["has_token"] is True
        assert d["has_oidc_tokens"] is True
