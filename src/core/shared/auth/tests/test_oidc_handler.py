"""Tests for OIDC handler."""

import pytest

from src.core.shared.auth.oidc_handler import (
    OIDCConfigurationError,
    OIDCHandler,
    OIDCProviderConfig,
    OIDCTokenResponse,
    OIDCUserInfo,
)


def test_oidc_handler_initialization():
    """Test OIDCHandler can be instantiated.

    Constitutional Hash: cdd01ef066bc6cf2
    """
    handler = OIDCHandler()
    assert handler is not None
    assert handler.list_providers() == []


def test_oidc_provider_config():
    """Test OIDCProviderConfig dataclass."""
    config = OIDCProviderConfig(
        name="test",
        client_id="test-client-id",
        client_secret="test-secret",
        server_metadata_url="https://example.com/.well-known/openid-configuration",
    )
    assert config.name == "test"
    assert config.use_pkce is True
    assert "openid" in config.scopes


def test_oidc_provider_config_validation():
    """Test OIDCProviderConfig validation."""
    with pytest.raises(OIDCConfigurationError):
        OIDCProviderConfig(
            name="",
            client_id="test",
            client_secret="secret",
            server_metadata_url="https://example.com",
        )


def test_oidc_provider_config_rejects_placeholder_secret():
    """Test placeholder client secret is rejected."""
    with pytest.raises(OIDCConfigurationError, match="Client secret uses placeholder value"):
        OIDCProviderConfig(
            name="test",
            client_id="test-client-id",
            client_secret="REPLACE_ME",  # pragma: allowlist secret
            server_metadata_url="https://example.com/.well-known/openid-configuration",
        )


def test_oidc_provider_config_rejects_placeholder_secret_variants():
    with pytest.raises(OIDCConfigurationError, match="Client secret uses placeholder value"):
        OIDCProviderConfig(
            name="test",
            client_id="test-client-id",
            client_secret=" replace-me ",
            server_metadata_url="https://example.com/.well-known/openid-configuration",
        )


def test_register_provider():
    """Test registering an OIDC provider."""
    handler = OIDCHandler()
    handler.register_provider(
        name="google",
        client_id="test-client-id",
        client_secret="test-secret",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    )
    assert "google" in handler.list_providers()


def test_oidc_token_response_from_dict():
    """Test OIDCTokenResponse.from_dict."""
    data = {
        "access_token": "test-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "test-refresh-token",
        "id_token": "test-id-token",
    }
    response = OIDCTokenResponse.from_dict(data)
    assert response.access_token == "test-access-token"
    assert response.expires_in == 3600


def test_oidc_user_info_from_claims():
    """Test OIDCUserInfo.from_claims."""
    claims = {
        "sub": "user-123",
        "email": "user@example.com",
        "email_verified": True,
        "name": "Test User",
        "groups": ["admin", "users"],
    }
    user_info = OIDCUserInfo.from_claims(claims)
    assert user_info.sub == "user-123"
    assert user_info.email == "user@example.com"
    assert "admin" in user_info.groups


if __name__ == "__main__":
    test_oidc_handler_initialization()
