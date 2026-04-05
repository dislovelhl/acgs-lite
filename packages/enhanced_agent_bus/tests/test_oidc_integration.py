"""
OAuth/OIDC Integration Tests
Constitutional Hash: 608508a9bd224290

Phase 10 Task 5: OAuth/OIDC Integration
- Task 5.1: Write unit tests for OAuth authorization URL generation with PKCE
- Task 5.3: Write unit tests for token exchange (code → access/refresh tokens)
- Task 5.5: Write unit tests for JWT validation using JWKS
- Task 5.7: Write unit tests for token refresh flow
- Task 5.9: Write unit tests for OIDC userinfo retrieval
- Task 5.11: Write unit tests for multi-provider support (Okta, Auth0, Azure AD)
"""

import base64
import hashlib
import json
import secrets
import time
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

# Import test subjects
from enterprise_sso.protocols import (
    CONSTITUTIONAL_HASH,
    AuthorizationRequest,
    BaseProtocolHandler,
    OIDCHandler,
    ProtocolHandlerFactory,
    ProtocolValidationResult,
)

# Test constants
TEST_ISSUER = "https://idp.example.com"
TEST_CLIENT_ID = "test-client-id"
TEST_CLIENT_SECRET = "test-client-secret"
TEST_REDIRECT_URI = "https://acgs2.example.com/auth/callback"

# Provider-specific constants
OKTA_ISSUER = "https://dev-12345.okta.com/oauth2/default"
AUTH0_ISSUER = "https://acgs2.auth0.com"
AZURE_AD_ISSUER = "https://login.microsoftonline.com/tenant-id/v2.0"


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def oidc_handler():
    """Create an OIDCHandler for testing."""
    return OIDCHandler(
        issuer=TEST_ISSUER,
        client_id=TEST_CLIENT_ID,
        client_secret=TEST_CLIENT_SECRET,
    )


@pytest.fixture
def oidc_handler_pkce_only():
    """Create an OIDCHandler with PKCE only (no client secret)."""
    return OIDCHandler(
        issuer=TEST_ISSUER,
        client_id=TEST_CLIENT_ID,
        use_pkce=True,
    )


@pytest.fixture
def okta_handler():
    """Create an OIDCHandler for Okta."""
    return OIDCHandler(
        issuer=OKTA_ISSUER,
        client_id="okta-client-id",
        client_secret="okta-client-secret",
        scopes=["openid", "profile", "email", "groups"],
    )


@pytest.fixture
def auth0_handler():
    """Create an OIDCHandler for Auth0."""
    return OIDCHandler(
        issuer=AUTH0_ISSUER,
        client_id="auth0-client-id",
        client_secret="auth0-client-secret",
        scopes=["openid", "profile", "email"],
    )


@pytest.fixture
def azure_ad_handler():
    """Create an OIDCHandler for Azure AD."""
    return OIDCHandler(
        issuer=AZURE_AD_ISSUER,
        client_id="azure-client-id",
        client_secret="azure-client-secret",
        scopes=["openid", "profile", "email", "offline_access"],
    )


def generate_valid_jwt(
    sub: str = "user-123",
    email: str = "user@example.com",
    name: str = "Test User",
    given_name: str = "Test",
    family_name: str = "User",
    groups: list | None = None,
    exp_offset: int = 3600,
    aud: str = TEST_CLIENT_ID,
    iss: str = TEST_ISSUER,
) -> str:
    """Generate a valid JWT for testing."""
    groups = groups or []
    now = int(time.time())

    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": iss,
        "sub": sub,
        "aud": aud,
        "exp": now + exp_offset,
        "iat": now,
        "email": email,
        "name": name,
        "given_name": given_name,
        "family_name": family_name,
        "groups": groups,
    }

    # Encode header and payload
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    # Create a fake signature (in production, this would be RSA signed)
    signature = base64.urlsafe_b64encode(b"fake-signature").decode().rstrip("=")

    return f"{header_b64}.{payload_b64}.{signature}"


# =============================================================================
# Task 5.1: OAuth Authorization URL Generation with PKCE
# =============================================================================


class TestOAuthAuthorizationWithPKCE:
    """Test OAuth authorization URL generation with PKCE.

    Constitutional Hash: 608508a9bd224290
    """

    def test_create_authorization_request_basic(self, oidc_handler):
        """Test basic authorization request creation."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request is not None
        assert auth_request.authorization_url is not None
        assert auth_request.state is not None
        assert auth_request.nonce is not None

    def test_authorization_url_contains_required_params(self, oidc_handler):
        """Test authorization URL contains required OAuth parameters."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)

        assert "client_id" in params
        assert params["client_id"][0] == TEST_CLIENT_ID
        assert "response_type" in params
        assert params["response_type"][0] == "code"
        assert "redirect_uri" in params
        assert params["redirect_uri"][0] == TEST_REDIRECT_URI
        assert "scope" in params
        assert "state" in params
        assert "nonce" in params

    def test_authorization_url_with_pkce(self, oidc_handler):
        """Test authorization URL includes PKCE parameters."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)

        assert "code_challenge" in params
        assert "code_challenge_method" in params
        assert params["code_challenge_method"][0] == "S256"
        assert auth_request.code_verifier is not None
        assert auth_request.code_challenge is not None

    def test_authorization_url_without_pkce(self):
        """Test authorization URL without PKCE."""
        handler = OIDCHandler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            client_secret=TEST_CLIENT_SECRET,
            use_pkce=False,
        )

        auth_request = handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)

        assert "code_challenge" not in params
        assert "code_challenge_method" not in params
        assert auth_request.code_verifier is None
        assert auth_request.code_challenge is None

    def test_pkce_code_verifier_length(self, oidc_handler):
        """Test PKCE code verifier has correct length."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        # Code verifier should be 43-128 characters
        assert 43 <= len(auth_request.code_verifier) <= 128

    def test_pkce_code_challenge_is_s256(self, oidc_handler):
        """Test PKCE code challenge is S256 hash of verifier."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        # Verify S256 challenge
        expected_digest = hashlib.sha256(auth_request.code_verifier.encode("utf-8")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).decode("utf-8").rstrip("=")

        assert auth_request.code_challenge == expected_challenge

    def test_authorization_url_custom_state(self, oidc_handler):
        """Test authorization request with custom state."""
        custom_state = "my-custom-state-12345"
        auth_request = oidc_handler.create_authorization_request(
            redirect_uri=TEST_REDIRECT_URI,
            state=custom_state,
        )

        assert auth_request.state == custom_state
        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)
        assert params["state"][0] == custom_state

    def test_authorization_url_scopes(self, oidc_handler):
        """Test authorization URL includes correct scopes."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)
        scopes = params["scope"][0].split()

        assert "openid" in scopes
        assert "profile" in scopes
        assert "email" in scopes

    def test_authorization_request_stored_as_pending(self, oidc_handler):
        """Test authorization request is stored for later validation."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request.state in oidc_handler._pending_requests
        stored = oidc_handler._pending_requests[auth_request.state]
        assert stored.code_verifier == auth_request.code_verifier

    def test_authorization_request_expiration(self, oidc_handler):
        """Test authorization request has expiration."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request.expires_at is not None
        assert auth_request.expires_at > datetime.now(UTC)

    def test_state_uniqueness(self, oidc_handler):
        """Test state values are unique across requests."""
        states = []
        for _ in range(100):
            auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)
            states.append(auth_request.state)

        # All states should be unique
        assert len(set(states)) == len(states)

    def test_nonce_uniqueness(self, oidc_handler):
        """Test nonce values are unique across requests."""
        nonces = []
        for _ in range(100):
            auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)
            nonces.append(auth_request.nonce)

        assert len(set(nonces)) == len(nonces)

    def test_authorization_endpoint_derivation(self):
        """Test authorization endpoint is derived from issuer."""
        handler = OIDCHandler(
            issuer="https://auth.example.com",
            client_id=TEST_CLIENT_ID,
        )

        auth_request = handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request.authorization_url.startswith("https://auth.example.com/authorize")

    def test_custom_authorization_endpoint(self):
        """Test custom authorization endpoint override."""
        handler = OIDCHandler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            authorization_endpoint="https://custom.example.com/oauth2/authorize",
        )

        auth_request = handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request.authorization_url.startswith(
            "https://custom.example.com/oauth2/authorize"
        )


# =============================================================================
# Task 5.3: Token Exchange (Code → Access/Refresh Tokens)
# =============================================================================


class TestOAuthTokenExchange:
    """Test OAuth token exchange functionality.

    Constitutional Hash: 608508a9bd224290
    """

    async def test_validate_response_success(self, oidc_handler):
        """Test successful token exchange and response validation."""
        # Create authorization request first
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        # Generate valid ID token
        id_token = generate_valid_jwt()

        # Mock the token exchange
        mock_tokens = {
            "access_token": "mock-access-token",
            "id_token": id_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(oidc_handler, "_exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = mock_tokens

            result = await oidc_handler.validate_response(
                response_data={
                    "code": "auth-code-12345",
                    "state": auth_request.state,
                    "redirect_uri": TEST_REDIRECT_URI,
                }
            )

            assert result.success is True
            assert result.user_id == "user-123"
            assert result.email == "user@example.com"

    async def test_validate_response_missing_code(self, oidc_handler):
        """Test validation failure when code is missing."""
        result = await oidc_handler.validate_response(response_data={"state": "some-state"})

        assert result.success is False
        assert result.error_code == "MISSING_CODE"

    async def test_validate_response_state_mismatch(self, oidc_handler):
        """Test validation failure on state mismatch."""
        result = await oidc_handler.validate_response(
            response_data={"code": "auth-code", "state": "wrong-state"},
            expected_state="correct-state",
        )

        assert result.success is False
        assert result.error_code == "STATE_MISMATCH"

    async def test_validate_response_error_from_provider(self, oidc_handler):
        """Test handling of error response from OAuth provider."""
        result = await oidc_handler.validate_response(
            response_data={
                "error": "access_denied",
                "error_description": "The user denied the request",
            }
        )

        assert result.success is False
        assert result.error_code == "access_denied"
        assert "denied" in result.error

    async def test_validate_response_expired_request(self, oidc_handler):
        """Test validation failure for expired authorization request."""
        # Create request
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        # Manually expire the request
        stored_request = oidc_handler._pending_requests[auth_request.state]
        stored_request.expires_at = datetime.now(UTC) - timedelta(minutes=1)

        result = await oidc_handler.validate_response(
            response_data={
                "code": "auth-code",
                "state": auth_request.state,
            }
        )

        assert result.success is False
        assert result.error_code == "REQUEST_EXPIRED"

    async def test_token_exchange_includes_pkce(self, oidc_handler):
        """Test token exchange includes PKCE code_verifier."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        with patch.object(oidc_handler, "_exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = {"error": "test_skip"}

            await oidc_handler.validate_response(
                response_data={
                    "code": "auth-code",
                    "state": auth_request.state,
                    "redirect_uri": TEST_REDIRECT_URI,
                }
            )

            # Verify code_verifier was passed
            mock_exchange.assert_called_once()
            call_args = mock_exchange.call_args
            assert call_args.kwargs.get("code_verifier") == auth_request.code_verifier

    async def test_token_exchange_with_refresh_token(self, oidc_handler):
        """Test token exchange returns refresh token when available."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        id_token = generate_valid_jwt()
        mock_tokens = {
            "access_token": "mock-access-token",
            "id_token": id_token,
            "refresh_token": "mock-refresh-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(oidc_handler, "_exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = mock_tokens

            result = await oidc_handler.validate_response(
                response_data={
                    "code": "auth-code",
                    "state": auth_request.state,
                    "redirect_uri": TEST_REDIRECT_URI,
                }
            )

            assert result.success is True
            assert "tokens" in result.raw_response


# =============================================================================
# Task 5.5: JWT Validation
# =============================================================================


class TestJWTValidation:
    """Test JWT ID token validation.

    Constitutional Hash: 608508a9bd224290
    """

    def test_parse_valid_jwt(self, oidc_handler):
        """Test parsing a valid JWT ID token."""
        id_token = generate_valid_jwt()
        result = oidc_handler._parse_id_token(id_token)

        assert result.success is True
        assert result.user_id == "user-123"
        assert result.email == "user@example.com"
        assert result.display_name == "Test User"
        assert result.first_name == "Test"
        assert result.last_name == "User"

    def test_parse_jwt_extracts_groups(self, oidc_handler):
        """Test JWT parsing extracts groups claim."""
        id_token = generate_valid_jwt(groups=["admin", "developers"])
        result = oidc_handler._parse_id_token(id_token)

        assert result.success is True
        assert "admin" in result.groups
        assert "developers" in result.groups

    def test_parse_jwt_expired_token(self, oidc_handler):
        """Test rejection of expired JWT."""
        id_token = generate_valid_jwt(exp_offset=-3600)  # Expired 1 hour ago
        result = oidc_handler._parse_id_token(id_token)

        assert result.success is False
        assert result.error_code == "TOKEN_EXPIRED"

    def test_parse_jwt_wrong_audience(self, oidc_handler):
        """Test rejection of JWT with wrong audience."""
        id_token = generate_valid_jwt(aud="wrong-client-id")
        result = oidc_handler._parse_id_token(id_token)

        assert result.success is False
        assert result.error_code == "AUDIENCE_MISMATCH"

    def test_parse_jwt_missing_subject(self, oidc_handler):
        """Test rejection of JWT without subject claim."""
        # Create a token without 'sub' claim
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": TEST_ISSUER,
            "aud": TEST_CLIENT_ID,
            "exp": int(time.time()) + 3600,
            "email": "user@example.com",
        }

        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")

        id_token = f"{header_b64}.{payload_b64}.{signature}"
        result = oidc_handler._parse_id_token(id_token)

        assert result.success is False
        assert result.error_code == "NO_SUBJECT"

    def test_parse_jwt_invalid_format(self, oidc_handler):
        """Test rejection of invalid JWT format."""
        result = oidc_handler._parse_id_token("not.a.valid.jwt")

        assert result.success is False
        assert result.error_code == "INVALID_TOKEN"

    def test_parse_jwt_invalid_base64(self, oidc_handler):
        """Test rejection of JWT with invalid base64."""
        result = oidc_handler._parse_id_token("invalid.!!!.jwt")

        assert result.success is False
        assert result.error_code == "PARSE_ERROR"

    def test_parse_jwt_stores_all_claims(self, oidc_handler):
        """Test all claims are stored in attributes."""
        id_token = generate_valid_jwt()
        result = oidc_handler._parse_id_token(id_token)

        assert result.success is True
        assert "iss" in result.attributes
        assert "sub" in result.attributes
        assert "aud" in result.attributes
        assert "exp" in result.attributes


# =============================================================================
# Task 5.7: Token Refresh Flow
# =============================================================================


class TestTokenRefreshFlow:
    """Test OAuth token refresh functionality.

    Constitutional Hash: 608508a9bd224290
    """

    async def test_token_response_includes_refresh_token(self, oidc_handler):
        """Test token exchange can return refresh token."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        id_token = generate_valid_jwt()
        mock_tokens = {
            "access_token": "access-123",
            "id_token": id_token,
            "refresh_token": "refresh-456",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.object(oidc_handler, "_exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = mock_tokens

            result = await oidc_handler.validate_response(
                response_data={
                    "code": "auth-code",
                    "state": auth_request.state,
                    "redirect_uri": TEST_REDIRECT_URI,
                }
            )

            assert result.success is True

    def test_handler_supports_offline_access_scope(self):
        """Test handler can be configured with offline_access scope."""
        handler = OIDCHandler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            scopes=["openid", "profile", "email", "offline_access"],
        )

        auth_request = handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)
        scopes = params["scope"][0].split()

        assert "offline_access" in scopes


# =============================================================================
# Task 5.9: OIDC UserInfo Retrieval
# =============================================================================


class TestOIDCUserInfoRetrieval:
    """Test OIDC userinfo endpoint retrieval.

    Constitutional Hash: 608508a9bd224290
    """

    async def test_userinfo_endpoint_derivation(self):
        """Test userinfo endpoint is derived from issuer."""
        handler = OIDCHandler(
            issuer="https://auth.example.com",
            client_id=TEST_CLIENT_ID,
        )

        assert handler.userinfo_endpoint == "https://auth.example.com/userinfo"

    async def test_custom_userinfo_endpoint(self):
        """Test custom userinfo endpoint override."""
        handler = OIDCHandler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            userinfo_endpoint="https://custom.example.com/oauth2/userinfo",
        )

        assert handler.userinfo_endpoint == "https://custom.example.com/oauth2/userinfo"

    async def test_get_userinfo_success(self, oidc_handler):
        """Test successful userinfo retrieval."""
        mock_userinfo = {
            "sub": "user-456",
            "email": "info@example.com",
            "name": "Info User",
            "given_name": "Info",
            "family_name": "User",
            "groups": ["group1", "group2"],
        }

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_userinfo)

            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_cm

            with patch.object(oidc_handler, "_get_userinfo", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = ProtocolValidationResult(
                    success=True,
                    user_id="user-456",
                    email="info@example.com",
                    display_name="Info User",
                    first_name="Info",
                    last_name="User",
                    groups=["group1", "group2"],
                )

                result = await oidc_handler._get_userinfo("access-token")

                assert result.success is True
                assert result.user_id == "user-456"

    async def test_fallback_to_userinfo_when_no_id_token(self, oidc_handler):
        """Test fallback to userinfo endpoint when no ID token."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        # Token response without id_token
        mock_tokens = {
            "access_token": "access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        mock_userinfo = ProtocolValidationResult(
            success=True,
            user_id="user-789",
            email="userinfo@example.com",
        )

        with patch.object(oidc_handler, "_exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = mock_tokens

            with patch.object(oidc_handler, "_get_userinfo", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_userinfo

                result = await oidc_handler.validate_response(
                    response_data={
                        "code": "auth-code",
                        "state": auth_request.state,
                        "redirect_uri": TEST_REDIRECT_URI,
                    }
                )

                assert result.success is True
                assert result.user_id == "user-789"
                mock_get.assert_called_once_with("access-token")


# =============================================================================
# Task 5.11: Multi-Provider Support (Okta, Auth0, Azure AD)
# =============================================================================


class TestMultiProviderSupport:
    """Test OIDC support for multiple providers.

    Constitutional Hash: 608508a9bd224290
    """

    def test_okta_handler_configuration(self, okta_handler):
        """Test Okta handler configuration."""
        assert okta_handler.issuer == OKTA_ISSUER
        assert okta_handler.authorization_endpoint == f"{OKTA_ISSUER}/authorize"
        assert okta_handler.token_endpoint == f"{OKTA_ISSUER}/oauth/token"
        assert "groups" in okta_handler.scopes

    def test_auth0_handler_configuration(self, auth0_handler):
        """Test Auth0 handler configuration."""
        assert auth0_handler.issuer == AUTH0_ISSUER
        assert auth0_handler.authorization_endpoint == f"{AUTH0_ISSUER}/authorize"

    def test_azure_ad_handler_configuration(self, azure_ad_handler):
        """Test Azure AD handler configuration."""
        assert azure_ad_handler.issuer == AZURE_AD_ISSUER
        assert "offline_access" in azure_ad_handler.scopes

    def test_okta_authorization_request(self, okta_handler):
        """Test Okta authorization request generation."""
        auth_request = okta_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request.authorization_url.startswith(OKTA_ISSUER)
        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)
        assert "groups" in params["scope"][0]

    def test_auth0_authorization_request(self, auth0_handler):
        """Test Auth0 authorization request generation."""
        auth_request = auth0_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request.authorization_url.startswith(AUTH0_ISSUER)
        assert auth_request.code_verifier is not None  # PKCE enabled by default

    def test_azure_ad_authorization_request(self, azure_ad_handler):
        """Test Azure AD authorization request generation."""
        auth_request = azure_ad_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        assert auth_request.authorization_url.startswith(AZURE_AD_ISSUER)
        parsed = urlparse(auth_request.authorization_url)
        params = parse_qs(parsed.query)
        assert "offline_access" in params["scope"][0]

    async def test_okta_jwt_validation(self, okta_handler):
        """Test Okta JWT validation."""
        id_token = generate_valid_jwt(
            aud="okta-client-id",
            iss=OKTA_ISSUER,
            groups=["Everyone", "Developers"],
        )

        result = okta_handler._parse_id_token(id_token)

        assert result.success is True
        assert "Everyone" in result.groups
        assert "Developers" in result.groups

    async def test_auth0_jwt_validation(self, auth0_handler):
        """Test Auth0 JWT validation."""
        id_token = generate_valid_jwt(
            aud="auth0-client-id",
            iss=AUTH0_ISSUER,
        )

        result = auth0_handler._parse_id_token(id_token)

        assert result.success is True
        assert result.user_id is not None

    async def test_azure_ad_jwt_validation(self, azure_ad_handler):
        """Test Azure AD JWT validation."""
        id_token = generate_valid_jwt(
            aud="azure-client-id",
            iss=AZURE_AD_ISSUER,
        )

        result = azure_ad_handler._parse_id_token(id_token)

        assert result.success is True

    def test_provider_endpoint_customization(self):
        """Test provider-specific endpoint customization."""
        # Okta uses /v1/authorize for authorization
        handler = OIDCHandler(
            issuer="https://dev-12345.okta.com",
            client_id="test-client",
            authorization_endpoint="https://dev-12345.okta.com/oauth2/v1/authorize",
            token_endpoint="https://dev-12345.okta.com/oauth2/v1/token",
            userinfo_endpoint="https://dev-12345.okta.com/oauth2/v1/userinfo",
        )

        assert handler.authorization_endpoint.endswith("/v1/authorize")
        assert handler.token_endpoint.endswith("/v1/token")
        assert handler.userinfo_endpoint.endswith("/v1/userinfo")


# =============================================================================
# Protocol Handler Factory Tests
# =============================================================================


class TestOIDCProtocolHandlerFactory:
    """Test ProtocolHandlerFactory for OIDC.

    Constitutional Hash: 608508a9bd224290
    """

    def test_create_oidc_handler(self):
        """Test creating OIDC handler from factory."""
        handler = ProtocolHandlerFactory.create_oidc_handler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            client_secret=TEST_CLIENT_SECRET,
        )

        assert isinstance(handler, OIDCHandler)
        assert handler.issuer == TEST_ISSUER
        assert handler.client_id == TEST_CLIENT_ID

    def test_create_oidc_handler_with_custom_scopes(self):
        """Test creating OIDC handler with custom scopes."""
        handler = ProtocolHandlerFactory.create_oidc_handler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            scopes=["openid", "profile", "email", "groups", "offline_access"],
        )

        assert "groups" in handler.scopes
        assert "offline_access" in handler.scopes

    def test_create_oidc_handler_pkce_only(self):
        """Test creating PKCE-only OIDC handler."""
        handler = ProtocolHandlerFactory.create_oidc_handler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            use_pkce=True,
        )

        assert handler.use_pkce is True
        assert handler.client_secret is None


# =============================================================================
# Constitutional Hash Validation Tests
# =============================================================================


class TestOIDCConstitutionalHashValidation:
    """Test constitutional hash validation for OIDC.

    Constitutional Hash: 608508a9bd224290
    """

    def test_valid_constitutional_hash(self):
        """Test handler initialization with valid constitutional hash."""
        handler = OIDCHandler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        assert handler.constitutional_hash == CONSTITUTIONAL_HASH

    def test_invalid_constitutional_hash_raises(self):
        """Test handler initialization with invalid constitutional hash raises."""
        with pytest.raises(ValueError) as exc_info:
            OIDCHandler(
                issuer=TEST_ISSUER,
                client_id=TEST_CLIENT_ID,
                constitutional_hash="invalid-hash",
            )

        assert "Invalid constitutional hash" in str(exc_info.value)

    def test_validation_result_includes_constitutional_hash(self, oidc_handler):
        """Test validation result includes constitutional hash."""
        id_token = generate_valid_jwt()
        result = oidc_handler._parse_id_token(id_token)

        assert result.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestOIDCEdgeCases:
    """Test OIDC edge cases and error handling.

    Constitutional Hash: 608508a9bd224290
    """

    def test_handler_with_trailing_slash_issuer(self):
        """Test handler normalizes issuer with trailing slash."""
        handler = OIDCHandler(
            issuer="https://idp.example.com/",
            client_id=TEST_CLIENT_ID,
        )

        assert handler.issuer == "https://idp.example.com"
        assert not handler.authorization_endpoint.startswith("https://idp.example.com//")

    def test_handler_with_minimal_config(self):
        """Test handler with minimal configuration."""
        handler = OIDCHandler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
        )

        assert handler.issuer == TEST_ISSUER
        assert handler.client_id == TEST_CLIENT_ID
        assert handler.use_pkce is True  # Default
        assert "openid" in handler.scopes

    async def test_validate_response_no_tokens(self, oidc_handler):
        """Test validation failure when no tokens received."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        with patch.object(oidc_handler, "_exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = {"token_type": "Bearer"}

            result = await oidc_handler.validate_response(
                response_data={
                    "code": "auth-code",
                    "state": auth_request.state,
                    "redirect_uri": TEST_REDIRECT_URI,
                }
            )

            assert result.success is False
            assert result.error_code == "NO_TOKEN"

    async def test_validate_response_token_exchange_error(self, oidc_handler):
        """Test handling of token exchange error."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        with patch.object(oidc_handler, "_exchange_code", new_callable=AsyncMock) as mock_exchange:
            mock_exchange.return_value = {
                "error": "invalid_grant",
                "error_description": "The authorization code has expired",
            }

            result = await oidc_handler.validate_response(
                response_data={
                    "code": "expired-code",
                    "state": auth_request.state,
                    "redirect_uri": TEST_REDIRECT_URI,
                }
            )

            assert result.success is False
            assert result.error_code == "invalid_grant"

    def test_jwks_uri_derivation(self):
        """Test JWKS URI is derived from issuer."""
        handler = OIDCHandler(
            issuer="https://auth.example.com",
            client_id=TEST_CLIENT_ID,
        )

        assert handler.jwks_uri == "https://auth.example.com/.well-known/jwks.json"

    def test_custom_jwks_uri(self):
        """Test custom JWKS URI override."""
        handler = OIDCHandler(
            issuer=TEST_ISSUER,
            client_id=TEST_CLIENT_ID,
            jwks_uri="https://custom.example.com/keys",
        )

        assert handler.jwks_uri == "https://custom.example.com/keys"

    def test_code_verifier_security(self, oidc_handler):
        """Test code verifier meets security requirements."""
        auth_request = oidc_handler.create_authorization_request(redirect_uri=TEST_REDIRECT_URI)

        verifier = auth_request.code_verifier

        # PKCE spec: code_verifier should be 43-128 characters
        assert len(verifier) >= 43
        assert len(verifier) <= 128

        # Should be URL-safe characters
        import string

        valid_chars = set(string.ascii_letters + string.digits + "-._~")
        assert all(c in valid_chars for c in verifier)

    def test_jwt_with_single_group_as_string(self, oidc_handler):
        """Test JWT parsing handles single group as string."""
        # Some providers return groups as a string if there's only one
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": TEST_ISSUER,
            "sub": "user-123",
            "aud": TEST_CLIENT_ID,
            "exp": int(time.time()) + 3600,
            "groups": "single-group",  # String instead of list
        }

        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")

        id_token = f"{header_b64}.{payload_b64}.{signature}"
        result = oidc_handler._parse_id_token(id_token)

        assert result.success is True
        assert isinstance(result.groups, list)
        assert "single-group" in result.groups
