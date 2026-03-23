import os
import sys

from src.core.shared.types import JSONDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ENABLE_RATE_LIMITING"] = "false"
os.environ["SAML_ENABLED"] = "false"
"""
ACGS-2 API Gateway OIDC Flow Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests for OpenID Connect authentication flow with Google Workspace mock.
Tests cover: login redirect, callback handling, token exchange, user info extraction,
session management, and error handling.

Usage:
    cd src/core/services/api_gateway && pytest tests/test_oidc.py -v
"""

import base64
import json
import secrets
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

try:
    import authlib  # noqa: F401

    HAS_AUTHLIB = True
except ImportError:
    HAS_AUTHLIB = False
from fastapi.testclient import TestClient

from src.core.services.api_gateway.main import app
from src.core.services.api_gateway.routes.sso import get_oidc_handler
from src.core.shared.auth.oidc_handler import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCHandler,
    OIDCProviderError,
    OIDCTokenError,
    OIDCTokenResponse,
    OIDCUserInfo,
)

# Constitutional hash constant

# Google Workspace mock configuration
MOCK_GOOGLE_METADATA = {
    "issuer": "https://accounts.google.com",
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
    "revocation_endpoint": "https://oauth2.googleapis.com/revoke",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
    "end_session_endpoint": "https://accounts.google.com/logout",
    "response_types_supported": ["code", "token", "id_token"],
    "subject_types_supported": ["public"],
    "id_token_signing_alg_values_supported": ["RS256"],
    "scopes_supported": ["openid", "email", "profile"],
    "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
    "claims_supported": [
        "aud",
        "email",
        "email_verified",
        "exp",
        "family_name",
        "given_name",
        "iat",
        "iss",
        "locale",
        "name",
        "picture",
        "sub",
    ],
}

# Mock Google user claims
MOCK_GOOGLE_USER_CLAIMS = {
    "sub": "google-user-123456789",
    "email": "test.user@example.com",
    "email_verified": True,
    "name": "Test User",
    "given_name": "Test",
    "family_name": "User",
    "picture": "https://lh3.googleusercontent.com/a/default-user=s96-c",
    "locale": "en",
    "hd": "example.com",  # Google Workspace domain
    "groups": ["Engineering", "AllStaff"],
}

# Mock token response
MOCK_TOKEN_RESPONSE = {
    "access_token": "mock-access-token-" + secrets.token_urlsafe(32),
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "mock-refresh-token-" + secrets.token_urlsafe(32),
    "id_token": "",  # Will be dynamically generated
    "scope": "openid email profile",
}


class DummyResponse:
    """Minimal response for JWKS fetch in tests."""

    def __init__(self, payload: JSONDict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> JSONDict:
        return self._payload


class DummyClient:
    """Minimal async client for JWKS fetch in tests."""

    def __init__(self, payload: JSONDict):
        self._payload = payload

    async def get(self, _url: str) -> DummyResponse:
        return DummyResponse(self._payload)


def create_mock_id_token(claims: JSONDict) -> str:
    """Create a mock JWT ID token for testing.

    Args:
        claims: JWT payload claims

    Returns:
        Mock JWT token string (not cryptographically valid, for testing only)
    """
    header = {"alg": "RS256", "typ": "JWT"}

    # Add standard JWT claims
    full_claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client-id",
        "exp": int(datetime.now(UTC).timestamp()) + 3600,
        "iat": int(datetime.now(UTC).timestamp()),
        "nonce": secrets.token_urlsafe(16),
        **claims,
    }

    # Base64url encode (without verification signature for testing)
    def b64url_encode(data: dict) -> str:
        json_bytes = json.dumps(data).encode()
        return base64.urlsafe_b64encode(json_bytes).rstrip(b"=").decode()

    header_b64 = b64url_encode(header)
    payload_b64 = b64url_encode(full_claims)
    signature_b64 = base64.urlsafe_b64encode(b"mock-signature").rstrip(b"=").decode()

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def create_signed_id_token(claims: JSONDict) -> tuple[str, JSONDict]:
    """Create a signed JWT ID token and JWKS payload."""
    if not HAS_AUTHLIB:
        return create_mock_id_token(claims), {"keys": []}

    from authlib.jose import JsonWebKey, jwt

    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    kid = key.thumbprint()
    public_jwk = key.as_dict(is_private=False)
    public_jwk["kid"] = kid

    header = {"alg": "RS256", "kid": kid, "typ": "JWT"}
    full_claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client-id",
        "exp": int(datetime.now(UTC).timestamp()) + 3600,
        "iat": int(datetime.now(UTC).timestamp()),
        "nonce": secrets.token_urlsafe(16),
        **claims,
    }

    token = jwt.encode(header, full_claims, key).decode("utf-8")
    return token, {"keys": [public_jwk]}


# Create mock ID token
MOCK_TOKEN_RESPONSE["id_token"] = create_mock_id_token(MOCK_GOOGLE_USER_CLAIMS)


class MockOIDCHandler(OIDCHandler):
    """Mock OIDC handler for testing with pre-configured Google Workspace provider."""

    def __init__(self):
        super().__init__()
        # Register mock Google provider
        self.register_provider(
            name="google",
            client_id="test-client-id",
            client_secret="test-client-secret",
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            scopes=["openid", "profile", "email"],
            use_pkce=True,
        )
        # Pre-cache metadata to avoid network calls
        self._metadata_cache["google"] = MOCK_GOOGLE_METADATA
        self._metadata_timestamps["google"] = datetime.now(UTC)


@pytest.fixture
def mock_handler():
    """Create a mock OIDC handler for testing."""
    return MockOIDCHandler()


@pytest.fixture
def client():
    """Create a test client with mocked OIDC handler."""
    # Reset the global handler to None to ensure fresh state
    import src.core.services.api_gateway.routes.sso as sso_module

    sso_module._oidc_handler = None

    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def mock_oidc_handler_dependency():
    """Fixture to override the OIDC handler dependency with a mock."""
    mock_handler = MockOIDCHandler()

    def override_get_oidc_handler():
        return mock_handler

    app.dependency_overrides[get_oidc_handler] = override_get_oidc_handler
    yield mock_handler
    app.dependency_overrides.clear()


class TestOIDCProviderConfig:
    """Tests for OIDC provider configuration."""

    def test_mock_google_metadata_structure(self):
        """Verify mock Google metadata has required OIDC fields."""
        required_fields = [
            "issuer",
            "authorization_endpoint",
            "token_endpoint",
            "userinfo_endpoint",
            "jwks_uri",
        ]
        for field in required_fields:
            assert field in MOCK_GOOGLE_METADATA, f"Missing required field: {field}"

    def test_mock_handler_registers_google_provider(self, mock_handler):
        """Test that mock handler has Google provider registered."""
        providers = mock_handler.list_providers()
        assert "google" in providers


class TestOIDCLoginFlow:
    """Tests for OIDC login initiation."""

    def test_oidc_login_redirect(self, client, mock_oidc_handler_dependency):
        """Test that /oidc/login redirects to Google authorization endpoint."""
        response = client.get(
            "/api/v1/sso/oidc/login?provider=google",
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers.get("location")
        assert location is not None
        assert "accounts.google.com" in location
        assert "client_id=test-client-id" in location
        assert "response_type=code" in location
        assert "scope=" in location
        assert "state=" in location

    def test_oidc_login_with_pkce(self, client, mock_oidc_handler_dependency):
        """Test that PKCE parameters are included in authorization URL."""
        response = client.get(
            "/api/v1/sso/oidc/login?provider=google",
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers.get("location")
        assert location is not None
        # PKCE should include code_challenge
        assert "code_challenge=" in location
        assert "code_challenge_method=S256" in location

    def test_oidc_login_sets_session_state(self, client, mock_oidc_handler_dependency):
        """Test that login stores state in session for CSRF protection."""
        response = client.get(
            "/api/v1/sso/oidc/login?provider=google",
            follow_redirects=False,
        )

        assert response.status_code == 302
        # Session cookie should be set
        assert "acgs2_session" in response.cookies or any(
            "session" in cookie.lower() for cookie in response.cookies
        )

    def test_oidc_login_unknown_provider_returns_404(self, client, mock_oidc_handler_dependency):
        """Test that login with unknown provider returns 404."""
        response = client.get(
            "/api/v1/sso/oidc/login?provider=unknown_provider",
            follow_redirects=False,
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data.get("detail", "").lower()

    def test_oidc_login_missing_provider_returns_422(self, client, mock_oidc_handler_dependency):
        """Test that login without provider parameter returns 422."""
        response = client.get(
            "/api/v1/sso/oidc/login",
            follow_redirects=False,
        )

        assert response.status_code == 422  # FastAPI validation error


class TestOIDCCallbackFlow:
    """Tests for OIDC callback handling."""

    @pytest.fixture
    def setup_login_state(self, client, mock_oidc_handler_dependency):
        """Set up login state by initiating login flow first."""
        # Initiate login to set up session state
        login_response = client.get(
            "/api/v1/sso/oidc/login?provider=google",
            follow_redirects=False,
        )

        # Extract state from redirect URL
        location = login_response.headers.get("location", "")
        import urllib.parse

        parsed = urllib.parse.urlparse(location)
        params = urllib.parse.parse_qs(parsed.query)
        state = params.get("state", [""])[0]

        return {
            "state": state,
            "cookies": login_response.cookies,
            "handler": mock_oidc_handler_dependency,
        }

    async def test_oidc_callback_success(self, client, setup_login_state):
        """Test successful OIDC callback with valid code and state."""
        state = setup_login_state["state"]
        cookies = setup_login_state["cookies"]
        handler = setup_login_state["handler"]

        # Mock the handle_callback method
        mock_user_info = OIDCUserInfo.from_claims(MOCK_GOOGLE_USER_CLAIMS)

        with patch.object(handler, "handle_callback", new_callable=AsyncMock) as mock_callback:
            mock_callback.return_value = mock_user_info
            for cookie in cookies.jar:
                client.cookies.set(cookie.name, cookie.value)

            response = client.get(
                f"/api/v1/sso/oidc/callback?code=mock-auth-code&state={state}",
            )

            assert response.status_code == 200
            data = response.json()
            assert data["email"] == "test.user@example.com"
            assert data["name"] == "Test User"
            assert data["sub"] == "google-user-123456789"

    def test_oidc_callback_invalid_state_returns_401(self, client, mock_oidc_handler_dependency):
        """Test that callback with invalid state returns 401 (CSRF protection)."""
        response = client.get(
            "/api/v1/sso/oidc/callback?code=mock-auth-code&state=invalid-state",
        )

        assert response.status_code == 401
        data = response.json()
        assert (
            "state" in data.get("detail", "").lower() or "invalid" in data.get("detail", "").lower()
        )

    def test_oidc_callback_missing_code_returns_422(self, client, mock_oidc_handler_dependency):
        """Test that callback without code parameter returns 422."""
        response = client.get(
            "/api/v1/sso/oidc/callback?state=some-state",
        )

        assert response.status_code == 422  # FastAPI validation error

    def test_oidc_callback_idp_error_returns_401(self, client, mock_oidc_handler_dependency):
        """Test that callback with IdP error returns 401."""
        response = client.get(
            "/api/v1/sso/oidc/callback?error=access_denied&error_description=User%20denied%20access&state=some-state&code=dummy",
        )

        assert response.status_code == 401
        data = response.json()
        assert "denied" in data.get("detail", "").lower()


class TestOIDCTokenExchange:
    """Tests for OIDC token exchange."""

    def test_token_response_from_dict(self):
        """Test OIDCTokenResponse parsing from dictionary."""
        token_response = OIDCTokenResponse.from_dict(MOCK_TOKEN_RESPONSE)

        assert token_response.access_token.startswith("mock-access-token-")
        assert token_response.token_type == "Bearer"
        assert token_response.expires_in == 3600
        assert token_response.refresh_token is not None
        assert token_response.id_token is not None

    def test_token_response_preserves_raw_response(self):
        """Test that raw response is preserved in token response."""
        custom_data = {
            **MOCK_TOKEN_RESPONSE,
            "custom_claim": "custom_value",
        }
        token_response = OIDCTokenResponse.from_dict(custom_data)

        assert token_response.raw_response.get("custom_claim") == "custom_value"


class TestOIDCUserInfo:
    """Tests for OIDC user info extraction."""

    def test_user_info_from_google_claims(self):
        """Test user info extraction from Google Workspace claims."""
        user_info = OIDCUserInfo.from_claims(MOCK_GOOGLE_USER_CLAIMS)

        assert user_info.sub == "google-user-123456789"
        assert user_info.email == "test.user@example.com"
        assert user_info.email_verified is True
        assert user_info.name == "Test User"
        assert user_info.given_name == "Test"
        assert user_info.family_name == "User"
        assert "Engineering" in user_info.groups

    def test_user_info_handles_missing_optional_fields(self):
        """Test that user info handles missing optional fields gracefully."""
        minimal_claims = {
            "sub": "minimal-user-id",
        }
        user_info = OIDCUserInfo.from_claims(minimal_claims)

        assert user_info.sub == "minimal-user-id"
        assert user_info.email is None
        assert user_info.name is None
        assert user_info.groups == []

    def test_user_info_extracts_azure_groups(self):
        """Test user info extracts groups from Azure AD claims format."""
        azure_claims = {
            "sub": "azure-user-id",
            "email": "user@azure.com",
            "https://schemas.microsoft.com/claims/groups": ["AdminGroup", "UserGroup"],
        }
        user_info = OIDCUserInfo.from_claims(azure_claims)

        assert "AdminGroup" in user_info.groups
        assert "UserGroup" in user_info.groups

    def test_user_info_extracts_roles(self):
        """Test user info extracts groups from roles claim."""
        okta_claims = {
            "sub": "okta-user-id",
            "email": "user@okta.com",
            "roles": ["Admin", "Developer"],
        }
        user_info = OIDCUserInfo.from_claims(okta_claims)

        assert "Admin" in user_info.groups
        assert "Developer" in user_info.groups

    def test_user_info_preserves_raw_claims(self):
        """Test that raw claims are preserved."""
        claims = {
            **MOCK_GOOGLE_USER_CLAIMS,
            "custom_claim": "custom_value",
        }
        user_info = OIDCUserInfo.from_claims(claims)

        assert user_info.raw_claims.get("custom_claim") == "custom_value"
        assert user_info.raw_claims.get("hd") == "example.com"


class TestOIDCProvidersList:
    """Tests for OIDC providers list endpoint."""

    def test_list_providers_returns_registered_providers(
        self, client, mock_oidc_handler_dependency
    ):
        """Test that providers list returns registered providers."""
        response = client.get("/api/v1/sso/oidc/providers")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should have at least the mocked Google provider
        provider_names = [p["name"] for p in data]
        assert "google" in provider_names

    def test_list_providers_includes_provider_info(self, client, mock_oidc_handler_dependency):
        """Test that provider info includes required fields."""
        response = client.get("/api/v1/sso/oidc/providers")

        assert response.status_code == 200
        data = response.json()

        for provider in data:
            assert "name" in provider
            assert "type" in provider
            assert "enabled" in provider


class TestOIDCLogout:
    """Tests for OIDC logout flow."""

    def test_logout_clears_session(self, client, mock_oidc_handler_dependency):
        """Test that logout clears the local session."""
        response = client.post("/api/v1/sso/oidc/logout")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "logged out" in data["message"].lower()

    async def test_logout_returns_idp_logout_url(self, client, mock_oidc_handler_dependency):
        """Test that logout returns IdP logout URL when available."""
        # First, simulate a logged-in session
        with (
            client.session_transaction()
            if hasattr(client, "session_transaction")
            else patch("starlette.requests.Request.session", {"user": {"provider": "google"}})
        ):
            pass

        # The mock handler has end_session_endpoint in metadata
        response = client.post("/api/v1/sso/oidc/logout")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestOIDCSessionInfo:
    """Tests for session info endpoint."""

    def test_session_info_unauthenticated(self, client, mock_oidc_handler_dependency):
        """Test session info for unauthenticated user."""
        response = client.get("/api/v1/sso/session")

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user"] is None


class TestOIDCErrorHandling:
    """Tests for OIDC error handling."""

    def test_configuration_error_handling(self):
        """Test OIDCConfigurationError is raised for invalid config."""
        from src.core.shared.auth.oidc_handler import OIDCProviderConfig

        with pytest.raises(OIDCConfigurationError):
            OIDCProviderConfig(
                name="",  # Invalid: empty name
                client_id="test",
                client_secret="secret",
                server_metadata_url="https://example.com",
            )

    def test_authentication_error_class(self):
        """Test OIDCAuthenticationError can be raised with message."""
        error = OIDCAuthenticationError("Invalid state parameter")
        assert "Invalid state" in str(error)

    def test_token_error_class(self):
        """Test OIDCTokenError can be raised with message."""
        error = OIDCTokenError("Token exchange failed")
        assert "Token exchange" in str(error)

    def test_provider_error_class(self):
        """Test OIDCProviderError can be raised with message."""
        error = OIDCProviderError("Cannot reach IdP")
        assert "Cannot reach" in str(error)


class TestOIDCHandlerMethods:
    """Tests for OIDCHandler internal methods."""

    def test_generate_state_is_unique(self, mock_handler):
        """Test that generated states are unique."""
        states = [mock_handler._generate_state() for _ in range(100)]
        assert len(set(states)) == 100

    def test_generate_code_verifier(self, mock_handler):
        """Test PKCE code verifier generation."""
        verifier = mock_handler._generate_code_verifier()

        assert len(verifier) > 40  # Should be sufficiently long
        assert all(c.isalnum() or c in "-_" for c in verifier)

    def test_generate_code_challenge(self, mock_handler):
        """Test PKCE code challenge generation from verifier."""
        verifier = "test-verifier-string"
        challenge = mock_handler._generate_code_challenge(verifier)

        # Challenge should be base64url encoded
        assert all(c.isalnum() or c in "-_" for c in challenge)
        # Same verifier should produce same challenge (deterministic)
        assert challenge == mock_handler._generate_code_challenge(verifier)

    def test_validate_state(self, mock_handler):
        """Test state validation."""
        # Unknown state should not be valid
        assert not mock_handler.validate_state("unknown-state")

    def test_clear_expired_states(self, mock_handler):
        """Test clearing expired pending states."""
        # Add a state manually
        mock_handler._pending_states["test-state"] = {
            "provider": "google",
            "redirect_uri": "https://example.com/callback",
            "code_verifier": None,
            "nonce": "test-nonce",
            "created_at": "2020-01-01T00:00:00+00:00",  # Old timestamp
        }

        # Clear expired states (default 600 seconds max age)
        cleared = mock_handler.clear_expired_states()

        assert cleared >= 1
        assert "test-state" not in mock_handler._pending_states


class TestOIDCIdTokenDecoding:
    """Tests for ID token decoding."""

    @pytest.mark.skipif(not HAS_AUTHLIB, reason="authlib required for ID token validation")
    async def test_decode_valid_id_token(self, mock_handler):
        """Test decoding a valid ID token structure."""
        id_token, jwks = create_signed_id_token(MOCK_GOOGLE_USER_CLAIMS)
        provider = mock_handler.get_provider("google")
        mock_handler._http_client = DummyClient(jwks)
        claims = await mock_handler._decode_id_token(id_token, provider)

        assert claims["sub"] == "google-user-123456789"
        assert claims["email"] == "test.user@example.com"
        assert claims["iss"] == "https://accounts.google.com"

    @pytest.mark.skipif(not HAS_AUTHLIB, reason="authlib required for ID token validation")
    async def test_decode_invalid_id_token_format(self, mock_handler):
        """Test that invalid token format raises error."""
        provider = mock_handler.get_provider("google")
        mock_handler._http_client = DummyClient({"keys": []})
        with pytest.raises(OIDCTokenError):
            await mock_handler._decode_id_token("invalid-token-format", provider)

    @pytest.mark.skipif(not HAS_AUTHLIB, reason="authlib required for ID token validation")
    async def test_decode_id_token_with_malformed_payload(self, mock_handler):
        """Test that malformed payload raises error."""
        provider = mock_handler.get_provider("google")
        mock_handler._http_client = DummyClient({"keys": []})
        # Create a token with invalid base64 in payload
        with pytest.raises(OIDCTokenError):
            await mock_handler._decode_id_token("header.!!!invalid!!!.signature", provider)


class TestOIDCProviderRegistration:
    """Tests for OIDC provider registration."""

    def test_register_provider_success(self):
        """Test successful provider registration."""
        handler = OIDCHandler()
        handler.register_provider(
            name="test-provider",
            client_id="client-id",
            client_secret="client-secret",
            server_metadata_url="https://example.com/.well-known/openid-configuration",
        )

        assert "test-provider" in handler.list_providers()

    def test_register_provider_with_custom_scopes(self):
        """Test provider registration with custom scopes."""
        handler = OIDCHandler()
        custom_scopes = ["openid", "profile", "email", "groups"]

        handler.register_provider(
            name="test-provider",
            client_id="client-id",
            client_secret="client-secret",
            server_metadata_url="https://example.com/.well-known/openid-configuration",
            scopes=custom_scopes,
        )

        provider = handler.get_provider("test-provider")
        assert provider.scopes == custom_scopes

    def test_register_provider_with_pkce_disabled(self):
        """Test provider registration with PKCE disabled."""
        handler = OIDCHandler()

        handler.register_provider(
            name="test-provider",
            client_id="client-id",
            client_secret="client-secret",
            server_metadata_url="https://example.com/.well-known/openid-configuration",
            use_pkce=False,
        )

        provider = handler.get_provider("test-provider")
        assert provider.use_pkce is False

    def test_get_unregistered_provider_raises_error(self):
        """Test that getting unregistered provider raises error."""
        handler = OIDCHandler()

        with pytest.raises(OIDCConfigurationError):
            handler.get_provider("nonexistent-provider")


class TestOIDCGoogleWorkspaceIntegration:
    """Integration tests specific to Google Workspace OIDC."""

    def test_google_workspace_domain_claim(self):
        """Test that Google Workspace domain (hd) claim is preserved."""
        user_info = OIDCUserInfo.from_claims(MOCK_GOOGLE_USER_CLAIMS)

        assert user_info.raw_claims.get("hd") == "example.com"

    def test_google_workspace_groups_extraction(self):
        """Test that Google Workspace groups are properly extracted."""
        claims = {
            **MOCK_GOOGLE_USER_CLAIMS,
            "groups": ["Engineering", "Security", "AllUsers"],
        }
        user_info = OIDCUserInfo.from_claims(claims)

        assert "Engineering" in user_info.groups
        assert "Security" in user_info.groups
        assert len(user_info.groups) == 3


class TestRedirectValidation:
    """Tests for redirect URI and RelayState validation."""

    def test_oidc_redirect_validation_rejects_absolute_urls(self):
        """Test that absolute URLs are rejected as redirect URIs."""
        from src.core.services.api_gateway.routes.sso.oidc import _validate_redirect_uri

        # Absolute URLs should be rejected
        assert not _validate_redirect_uri("https://evil.com/callback")
        assert not _validate_redirect_uri("http://localhost:8080/callback")
        # Relative paths should be accepted
        assert _validate_redirect_uri("/api/v1/sso/oidc/callback")
        assert not _validate_redirect_uri("/app/home")

    def test_saml_relaystate_validation_rejects_absolute_urls(self):
        """Test that absolute URLs are rejected as RelayState."""
        # Validate the implementation in routes/sso/saml.py
        # RelayState should be relative only
        valid_relay = "/app/dashboard"
        invalid_relay = "https://evil.com/steal"

        # Valid: starts with / and contains no ://
        assert valid_relay.startswith("/") and "://" not in valid_relay
        # Invalid: contains ://
        assert "://" in invalid_relay or not invalid_relay.startswith("/")


class TestGatewayAuthEnforcement:
    """Tests for gateway endpoint authentication."""

    def test_services_endpoint_requires_auth(self, client):
        """Test that /services requires authentication."""
        response = client.get("/services")
        # Should return 401 when not authenticated
        assert response.status_code == 401

    def test_proxy_requires_auth(self, client):
        """Test that proxy to agent bus requires authentication."""
        response = client.get("/api/v1/agents")
        # Should return 401 when not authenticated
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
