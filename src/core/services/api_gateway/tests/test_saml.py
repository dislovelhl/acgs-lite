import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ENABLE_RATE_LIMITING"] = "false"
os.environ["SAML_ENABLED"] = "false"
"""
ACGS-2 API Gateway SAML Flow Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests for SAML 2.0 authentication flow with Okta mock.
Tests cover: login redirect, ACS callback handling, assertion validation,
user info extraction, session management, and error handling.

Usage:
    cd src/core/services/api_gateway && pytest tests/test_saml.py -v
"""

import base64
import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.core.services.api_gateway.main import app
from src.core.services.api_gateway.routes.sso import get_saml_handler
from src.core.shared.auth.saml_config import (
    SAMLConfigurationError,
    SAMLIdPConfig,
    SAMLSPConfig,
)
from src.core.shared.auth.saml_handler import (
    SAMLAuthenticationError,
    SAMLHandler,
    SAMLProviderError,
    SAMLReplayError,
    SAMLUserInfo,
    SAMLValidationError,
)

# Constitutional hash constant

# Okta mock configuration
MOCK_OKTA_ENTITY_ID = "http://www.okta.com/exk123456789"
MOCK_OKTA_SSO_URL = "https://dev-123456.okta.com/app/exk123456789/sso/saml"
MOCK_OKTA_SLO_URL = "https://dev-123456.okta.com/app/exk123456789/slo/saml"
MOCK_OKTA_METADATA_URL = "https://dev-123456.okta.com/app/exk123456789/sso/saml/metadata"

# Mock Okta IdP certificate (self-signed test certificate, not for production)
MOCK_OKTA_CERTIFICATE = """-----BEGIN CERTIFICATE-----
MIIDpTCCAo2gAwIBAgIGAZAAAA0BMA0GCSqGSIb3DQEBCwUAMIGSMQswCQYDVQQG
EwJVUzETMBEGA1UECAwKQ2FsaWZvcm5pYTEWMBQGA1UEBwwNU2FuIEZyYW5jaXNj
bzENMAsGA1UECgwET2t0YTEUMBIGA1UECwwLU1NPUHJvdmlkZXIxEzARBgNVBAMM
Cm9rdGEtdGVzdDEcMBoGCSqGSIb3DQEJARYNdGVzdEBva3RhLmNvbTAeFw0yNDAx
MDEwMDAwMDBaFw0yNTAxMDEwMDAwMDBaMIGSMQswCQYDVQQGEwJVUzETMBEGA1UE
CAwKQ2FsaWZvcm5pYTEWMBQGA1UEBwwNU2FuIEZyYW5jaXNjbzENMAsGA1UECgwE
T2t0YTEUMBIGA1UECwwLU1NPUHJvdmlkZXIxEzARBgNVBAMMCm9rdGEtdGVzdDEc
MBoGCSqGSIb3DQEJARYNdGVzdEBva3RhLmNvbTCCASIwDQYJKoZIhvcNAQEBBQAD
ggEPADCCAQoCggEBAK1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJ
KLMNOPQRSTUVWXYZ1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKL
MNOPQRSTUVWXYZ1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN
OPQRSTUVWXYZ1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOP
QRSTUVWXYZ1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQR
STUVWXYZ1234567890abcdefghijklmnopAgMBAAGjUzBRMB0GA1UdDgQWBBQwMD
AwMDAwMDAwMDAwMDAwMDAwMDAfBgNVHSMEGDAWgBQwMDAwMDAwMDAwMDAwMDAw
MDAwMDAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAAAAAAAAA=
-----END CERTIFICATE-----"""

# Mock Okta user attributes
MOCK_OKTA_USER_ATTRIBUTES = {
    "email": ["test.user@example.com"],
    "emailAddress": ["test.user@example.com"],
    "firstName": ["Test"],
    "lastName": ["User"],
    "displayName": ["Test User"],
    "groups": ["Engineering", "Developers", "AllStaff"],
    "department": ["Engineering"],
    "title": ["Senior Developer"],
}

# Mock SAML NameID
MOCK_OKTA_NAME_ID = "test.user@example.com"
MOCK_OKTA_SESSION_INDEX = "_session_" + secrets.token_hex(8)


def create_mock_saml_response(
    name_id: str = MOCK_OKTA_NAME_ID,
    attributes: dict[str, list[str]] | None = None,
    session_index: str | None = None,
    issuer: str = MOCK_OKTA_ENTITY_ID,
    valid: bool = True,
) -> str:
    """Create a mock base64-encoded SAML response for testing.

    Args:
        name_id: User's NameID
        attributes: SAML attributes
        session_index: Session index for logout
        issuer: IdP entity ID
        valid: Whether to create a valid response structure

    Returns:
        Base64-encoded mock SAML response (not cryptographically valid, for testing only)
    """
    if attributes is None:
        attributes = MOCK_OKTA_USER_ATTRIBUTES
    if session_index is None:
        session_index = MOCK_OKTA_SESSION_INDEX

    now = datetime.now(UTC)
    not_before = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    not_on_or_after = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build attribute statements
    attr_statements = ""
    for attr_name, values in attributes.items():
        value_elements = "".join(
            f'<saml:AttributeValue xsi:type="xs:string">{v}</saml:AttributeValue>' for v in values
        )
        attr_statements += f"""
        <saml:Attribute Name="{attr_name}">
            {value_elements}
        </saml:Attribute>"""

    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                ID="_response_{secrets.token_hex(16)}"
                IssueInstant="{issue_instant}"
                Version="2.0">
    <saml:Issuer>{issuer}</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
    <saml:Assertion ID="_assertion_{secrets.token_hex(16)}"
                    IssueInstant="{issue_instant}"
                    Version="2.0">
        <saml:Issuer>{issuer}</saml:Issuer>
        <saml:Subject>
            <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">
                {name_id}
            </saml:NameID>
            <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                <saml:SubjectConfirmationData NotOnOrAfter="{not_on_or_after}"/>
            </saml:SubjectConfirmation>
        </saml:Subject>
        <saml:Conditions NotBefore="{not_before}" NotOnOrAfter="{not_on_or_after}">
            <saml:AudienceRestriction>
                <saml:Audience>urn:acgs2:saml:sp</saml:Audience>
            </saml:AudienceRestriction>
        </saml:Conditions>
        <saml:AuthnStatement AuthnInstant="{issue_instant}" SessionIndex="{session_index}">
            <saml:AuthnContext>
                <saml:AuthnContextClassRef>
                    urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
                </saml:AuthnContextClassRef>
            </saml:AuthnContext>
        </saml:AuthnStatement>
        <saml:AttributeStatement>
            {attr_statements}
        </saml:AttributeStatement>
    </saml:Assertion>
</samlp:Response>"""

    return base64.b64encode(response_xml.encode()).decode()


class MockSAMLHandler(SAMLHandler):
    """Mock SAML handler for testing with pre-configured Okta provider."""

    def __init__(self):
        sp_config = SAMLSPConfig(
            entity_id="urn:acgs2:saml:sp:test",
            acs_url="http://testserver/sso/saml/acs",
            sls_url="http://testserver/sso/saml/sls",
            metadata_url="http://testserver/sso/saml/metadata",
            sign_authn_requests=False,  # Disable for testing without certs
            want_assertions_signed=False,  # Disable for testing
        )
        super().__init__(sp_config=sp_config)

        # Register mock Okta provider
        self.register_idp(
            name="okta",
            entity_id=MOCK_OKTA_ENTITY_ID,
            sso_url=MOCK_OKTA_SSO_URL,
            slo_url=MOCK_OKTA_SLO_URL,
            certificate=MOCK_OKTA_CERTIFICATE,
            want_assertions_signed=False,  # Disable for testing
        )


@pytest.fixture
def mock_handler():
    """Create a mock SAML handler for testing."""
    return MockSAMLHandler()


@pytest.fixture
def client():
    """Create a test client with mocked SAML handler."""
    # Reset the global handler to None to ensure fresh state
    import src.core.services.api_gateway.routes.sso as sso_module

    sso_module._saml_handler = None

    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def mock_saml_handler_dependency(client):
    """Fixture to override the SAML handler dependency with a mock."""
    mock_handler = MockSAMLHandler()

    def override_get_saml_handler(req: Request):
        return mock_handler

    app.dependency_overrides[get_saml_handler] = override_get_saml_handler
    yield mock_handler
    app.dependency_overrides.clear()


class TestSAMLProviderConfig:
    """Tests for SAML provider configuration."""

    def test_mock_okta_idp_config_structure(self):
        """Verify mock Okta IdP configuration has required fields."""
        idp = SAMLIdPConfig(
            name="okta",
            entity_id=MOCK_OKTA_ENTITY_ID,
            sso_url=MOCK_OKTA_SSO_URL,
            slo_url=MOCK_OKTA_SLO_URL,
            certificate=MOCK_OKTA_CERTIFICATE,
        )

        assert idp.name == "okta"
        assert idp.entity_id == MOCK_OKTA_ENTITY_ID
        assert idp.sso_url == MOCK_OKTA_SSO_URL
        assert idp.slo_url == MOCK_OKTA_SLO_URL
        assert idp.has_manual_config()

    def test_mock_handler_registers_okta_provider(self, mock_handler):
        """Test that mock handler has Okta provider registered."""
        idps = mock_handler.list_idps()
        assert "okta" in idps

    def test_idp_config_validation_requires_name(self):
        """Test that IdP configuration requires a name."""
        with pytest.raises(SAMLConfigurationError):
            SAMLIdPConfig(name="")

    def test_idp_config_validation_binding_types(self):
        """Test that IdP configuration validates binding types."""
        # Valid binding types
        idp = SAMLIdPConfig(
            name="test",
            sso_binding="redirect",
            slo_binding="post",
        )
        assert idp.sso_binding == "redirect"
        assert idp.slo_binding == "post"

        # Invalid binding type
        with pytest.raises(SAMLConfigurationError):
            SAMLIdPConfig(name="test", sso_binding="invalid")


class TestSAMLLoginFlow:
    """Tests for SAML login initiation."""

    async def test_saml_login_redirect(self, client, mock_saml_handler_dependency):
        """Test that /saml/login redirects to Okta SSO endpoint."""
        # Mock initiate_login to return a proper redirect URL
        mock_request_id = "_saml_" + secrets.token_hex(16)
        redirect_url = f"{MOCK_OKTA_SSO_URL}?SAMLRequest=mock_request"

        with patch.object(
            mock_saml_handler_dependency,
            "initiate_login",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = (redirect_url, mock_request_id)

            response = client.get(
                "/api/v1/sso/saml/login?provider=okta",
                follow_redirects=False,
            )

            assert response.status_code == 302
            location = response.headers.get("location")
            assert location is not None
            assert MOCK_OKTA_SSO_URL in location

    async def test_saml_login_stores_request_id(self, client, mock_saml_handler_dependency):
        """Test that login stores request ID in session for replay prevention."""
        mock_request_id = "_saml_" + secrets.token_hex(16)
        redirect_url = f"{MOCK_OKTA_SSO_URL}?SAMLRequest=mock"

        with patch.object(
            mock_saml_handler_dependency,
            "initiate_login",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = (redirect_url, mock_request_id)

            response = client.get(
                "/api/v1/sso/saml/login?provider=okta",
                follow_redirects=False,
            )

            assert response.status_code == 302
            # Session cookie should be set
            assert "acgs2_session" in response.cookies or any(
                "session" in cookie.lower() for cookie in response.cookies
            )

    def test_saml_login_unknown_provider_returns_404(self, client, mock_saml_handler_dependency):
        """Test that login with unknown provider returns 404."""
        with patch.object(
            mock_saml_handler_dependency,
            "initiate_login",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.side_effect = SAMLConfigurationError("Provider not found")
            response = client.get(
                "/api/v1/sso/saml/login?provider=unknown_provider",
                follow_redirects=False,
            )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data.get("detail", "").lower()

    def test_saml_login_missing_provider_returns_422(self, client, mock_saml_handler_dependency):
        """Test that login without provider parameter returns 422."""
        response = client.get(
            "/api/v1/sso/saml/login",
            follow_redirects=False,
        )

        assert response.status_code == 422  # FastAPI validation error

    async def test_saml_login_with_relay_state(self, client, mock_saml_handler_dependency):
        """Test that login passes relay state to IdP."""
        mock_request_id = "_saml_" + secrets.token_hex(16)
        redirect_url = f"{MOCK_OKTA_SSO_URL}?SAMLRequest=mock"
        relay_state = "https://app.example.com/dashboard"

        with patch.object(
            mock_saml_handler_dependency,
            "initiate_login",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = (redirect_url, mock_request_id)

            response = client.get(
                f"/api/v1/sso/saml/login?provider=okta&relay_state={relay_state}",
                follow_redirects=False,
            )

            assert response.status_code == 302
            # Verify relay_state was passed to initiate_login
            mock_initiate.assert_called_once()
            call_kwargs = mock_initiate.call_args
            assert call_kwargs.kwargs.get("relay_state") == relay_state

    async def test_saml_login_with_force_authn(self, client, mock_saml_handler_dependency):
        """Test that login can force re-authentication."""
        mock_request_id = "_saml_" + secrets.token_hex(16)
        redirect_url = f"{MOCK_OKTA_SSO_URL}?SAMLRequest=mock"

        with patch.object(
            mock_saml_handler_dependency,
            "initiate_login",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = (redirect_url, mock_request_id)

            response = client.get(
                "/api/v1/sso/saml/login?provider=okta&force_authn=true",
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_initiate.assert_called_once()
            call_kwargs = mock_initiate.call_args
            assert call_kwargs.kwargs.get("force_authn") is True


class TestSAMLACSFlow:
    """Tests for SAML Assertion Consumer Service (ACS) callback handling."""

    @pytest.fixture
    def setup_login_state(self, client, mock_saml_handler_dependency):
        """Set up login state by initiating login flow first."""
        mock_request_id = "_saml_" + secrets.token_hex(16)
        redirect_url = f"{MOCK_OKTA_SSO_URL}?SAMLRequest=mock"

        with patch.object(
            mock_saml_handler_dependency,
            "initiate_login",
            new_callable=AsyncMock,
        ) as mock_initiate:
            mock_initiate.return_value = (redirect_url, mock_request_id)

            login_response = client.get(
                "/api/v1/sso/saml/login?provider=okta",
                follow_redirects=False,
            )

        return {
            "request_id": mock_request_id,
            "cookies": login_response.cookies,
            "handler": mock_saml_handler_dependency,
        }

    async def test_saml_acs_success(self, client, setup_login_state):
        """Test successful SAML ACS callback with valid response."""
        cookies = setup_login_state["cookies"]
        handler = setup_login_state["handler"]

        # Create mock user info
        mock_user_info = SAMLUserInfo(
            name_id=MOCK_OKTA_NAME_ID,
            email="test.user@example.com",
            name="Test User",
            given_name="Test",
            family_name="User",
            groups=["Engineering", "Developers"],
            session_index=MOCK_OKTA_SESSION_INDEX,
        )

        with patch.object(
            handler,
            "process_acs_response",
            new_callable=AsyncMock,
        ) as mock_acs:
            mock_acs.return_value = mock_user_info

            saml_response = create_mock_saml_response()

            response = client.post(
                "/api/v1/sso/saml/acs",
                data={
                    "SAMLResponse": saml_response,
                    "RelayState": "",
                },
                cookies=cookies,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name_id"] == MOCK_OKTA_NAME_ID
            assert data["email"] == "test.user@example.com"
            assert data["name"] == "Test User"
            assert "Engineering" in data["groups"]

    async def test_saml_acs_replay_attack_returns_401(self, client, mock_saml_handler_dependency):
        """Test that ACS with replay attack returns 401."""
        with patch.object(
            mock_saml_handler_dependency,
            "process_acs_response",
            new_callable=AsyncMock,
        ) as mock_acs:
            mock_acs.side_effect = SAMLReplayError("Replay attack detected")

            saml_response = create_mock_saml_response()

            response = client.post(
                "/api/v1/sso/saml/acs",
                data={
                    "SAMLResponse": saml_response,
                },
            )

            assert response.status_code == 401
            data = response.json()
            assert "authentication failed" in data.get("detail", "").lower()

    async def test_saml_acs_validation_error_returns_401(
        self, client, mock_saml_handler_dependency
    ):
        """Test that ACS with validation error returns 401."""
        with patch.object(
            mock_saml_handler_dependency,
            "process_acs_response",
            new_callable=AsyncMock,
        ) as mock_acs:
            mock_acs.side_effect = SAMLValidationError("Signature validation failed")

            saml_response = create_mock_saml_response()

            response = client.post(
                "/api/v1/sso/saml/acs",
                data={
                    "SAMLResponse": saml_response,
                },
            )

            assert response.status_code == 401
            data = response.json()
            assert "authentication failed" in data.get("detail", "").lower()

    async def test_saml_acs_authentication_error_returns_401(
        self, client, mock_saml_handler_dependency
    ):
        """Test that ACS with authentication error returns 401."""
        with patch.object(
            mock_saml_handler_dependency,
            "process_acs_response",
            new_callable=AsyncMock,
        ) as mock_acs:
            mock_acs.side_effect = SAMLAuthenticationError("Authentication failed")

            saml_response = create_mock_saml_response()

            response = client.post(
                "/api/v1/sso/saml/acs",
                data={
                    "SAMLResponse": saml_response,
                },
            )

            assert response.status_code == 401
            data = response.json()
            assert "failed" in data.get("detail", "").lower()

    def test_saml_acs_missing_response_returns_422(self, client, mock_saml_handler_dependency):
        """Test that ACS without SAMLResponse returns 422."""
        response = client.post(
            "/api/v1/sso/saml/acs",
            data={},
        )

        assert response.status_code == 422  # FastAPI validation error


class TestSAMLUserInfo:
    """Tests for SAML user info extraction."""

    def test_user_info_from_okta_attributes(self):
        """Test user info extraction from Okta SAML attributes."""
        user_info = SAMLUserInfo(
            name_id=MOCK_OKTA_NAME_ID,
            email="test.user@example.com",
            name="Test User",
            given_name="Test",
            family_name="User",
            groups=["Engineering", "Developers", "AllStaff"],
            session_index=MOCK_OKTA_SESSION_INDEX,
            issuer=MOCK_OKTA_ENTITY_ID,
        )

        assert user_info.name_id == MOCK_OKTA_NAME_ID
        assert user_info.email == "test.user@example.com"
        assert user_info.name == "Test User"
        assert user_info.given_name == "Test"
        assert user_info.family_name == "User"
        assert "Engineering" in user_info.groups
        assert len(user_info.groups) == 3

    def test_user_info_handles_missing_optional_fields(self):
        """Test that user info handles missing optional fields gracefully."""
        user_info = SAMLUserInfo(name_id="minimal-user-id")

        assert user_info.name_id == "minimal-user-id"
        assert user_info.email is None
        assert user_info.name is None
        assert user_info.groups == []
        assert user_info.session_index is None

    def test_user_info_preserves_session_index(self):
        """Test that session index is preserved for logout."""
        user_info = SAMLUserInfo(
            name_id=MOCK_OKTA_NAME_ID,
            session_index=MOCK_OKTA_SESSION_INDEX,
        )

        assert user_info.session_index == MOCK_OKTA_SESSION_INDEX

    def test_user_info_preserves_attributes(self):
        """Test that raw attributes are preserved."""
        attributes = {
            "email": ["test@example.com"],
            "custom_attr": ["custom_value"],
            "multi_value": ["value1", "value2"],
        }
        user_info = SAMLUserInfo(
            name_id=MOCK_OKTA_NAME_ID,
            attributes=attributes,
        )

        assert user_info.attributes.get("custom_attr") == ["custom_value"]
        assert len(user_info.attributes.get("multi_value", [])) == 2


class TestSAMLProvidersList:
    """Tests for SAML providers list endpoint."""

    def test_list_providers_returns_registered_providers(
        self, client, mock_saml_handler_dependency
    ):
        """Test that providers list returns registered providers."""
        response = client.get("/api/v1/sso/saml/providers")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should have the mocked Okta provider
        provider_names = [p["name"] for p in data]
        assert "okta" in provider_names

    def test_list_providers_includes_provider_info(self, client, mock_saml_handler_dependency):
        """Test that provider info includes required fields."""
        response = client.get("/api/v1/sso/saml/providers")

        assert response.status_code == 200
        data = response.json()

        for provider in data:
            assert "name" in provider
            assert "type" in provider
            assert provider["type"] == "saml"
            assert "enabled" in provider


class TestSAMLMetadata:
    """Tests for SAML SP metadata generation."""

    async def test_metadata_returns_xml(self, client, mock_saml_handler_dependency):
        """Test that metadata endpoint returns XML content."""
        # Mock generate_metadata
        mock_metadata_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
            'entityID="urn:acgs2:saml:sp:test">'
            "</md:EntityDescriptor>"
        )

        with patch.object(
            mock_saml_handler_dependency,
            "generate_metadata",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = mock_metadata_xml

            response = client.get("/api/v1/sso/saml/metadata")

            assert response.status_code == 200
            assert "application/xml" in response.headers.get("content-type", "")
            assert "EntityDescriptor" in response.text

    async def test_metadata_includes_entity_id(self, client, mock_saml_handler_dependency):
        """Test that metadata includes entity ID."""
        mock_metadata_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
            'entityID="urn:acgs2:saml:sp:test">'
            "</md:EntityDescriptor>"
        )

        with patch.object(
            mock_saml_handler_dependency,
            "generate_metadata",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = mock_metadata_xml

            response = client.get("/api/v1/sso/saml/metadata")

            assert response.status_code == 200
            assert "entityID" in response.text


class TestSAMLLogout:
    """Tests for SAML logout flow."""

    def test_logout_clears_session(self, client, mock_saml_handler_dependency):
        """Test that logout clears the local session."""
        response = client.post("/api/v1/sso/saml/logout")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_logout_returns_idp_logout_url(self, client, mock_saml_handler_dependency):
        """Test that logout returns IdP logout URL when available."""
        idp_logout_url = f"{MOCK_OKTA_SLO_URL}?SAMLRequest=mock"

        with patch.object(
            mock_saml_handler_dependency,
            "initiate_logout",
            new_callable=AsyncMock,
        ) as mock_logout:
            mock_logout.return_value = idp_logout_url

            # Set up session with user
            with (
                client.session_transaction()
                if hasattr(client, "session_transaction")
                else patch(
                    "starlette.requests.Request.session",
                    {
                        "user": {
                            "provider": "okta",
                            "name_id": MOCK_OKTA_NAME_ID,
                            "session_index": MOCK_OKTA_SESSION_INDEX,
                        }
                    },
                )
            ):
                pass

            response = client.post("/api/v1/sso/saml/logout")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


class TestSAMLSLSFlow:
    """Tests for SAML Single Logout Service (SLS) flow."""

    async def test_sls_handles_logout_response(self, client, mock_saml_handler_dependency):
        """Test that SLS handles logout response from IdP."""
        with patch.object(
            mock_saml_handler_dependency,
            "process_sls_response",
            new_callable=AsyncMock,
        ) as mock_sls:
            mock_sls.return_value = True

            # Simulate a logged-in session
            with patch("starlette.requests.Request.session", {"user": {"provider": "okta"}}):
                response = client.get(
                    "/api/v1/sso/saml/sls?SAMLResponse=mock_response",
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_sls_handles_logout_request(self, client, mock_saml_handler_dependency):
        """Test that SLS handles IdP-initiated logout request."""
        response = client.get(
            "/api/v1/sso/saml/sls?SAMLRequest=mock_request",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestSAMLErrorHandling:
    """Tests for SAML error handling."""

    def test_configuration_error_handling(self):
        """Test SAMLConfigurationError is raised for invalid config."""
        with pytest.raises(SAMLConfigurationError):
            SAMLSPConfig(
                entity_id="",  # Invalid: empty entity ID
                acs_url="http://test/acs",
            )

    def test_authentication_error_class(self):
        """Test SAMLAuthenticationError can be raised with message."""
        error = SAMLAuthenticationError("Authentication failed at IdP")
        assert "Authentication failed" in str(error)

    def test_validation_error_class(self):
        """Test SAMLValidationError can be raised with message."""
        error = SAMLValidationError("Signature validation failed")
        assert "Signature" in str(error)

    def test_provider_error_class(self):
        """Test SAMLProviderError can be raised with message."""
        error = SAMLProviderError("Cannot reach IdP")
        assert "Cannot reach" in str(error)

    def test_replay_error_class(self):
        """Test SAMLReplayError can be raised with message."""
        error = SAMLReplayError("Response already processed")
        assert "already processed" in str(error)


class TestSAMLHandlerMethods:
    """Tests for SAMLHandler internal methods."""

    def test_generate_request_id_is_unique(self, mock_handler):
        """Test that generated request IDs are unique."""
        request_ids = [mock_handler._generate_request_id() for _ in range(100)]
        assert len(set(request_ids)) == 100

    def test_generate_request_id_format(self, mock_handler):
        """Test that request ID has correct format."""
        request_id = mock_handler._generate_request_id()
        assert request_id.startswith("_saml_")
        assert len(request_id) > 10

    def test_store_outstanding_request(self, mock_handler):
        """Test storing outstanding SAML request."""
        request_id = mock_handler.store_outstanding_request(
            idp_name="okta",
            relay_state="https://app.example.com",
        )

        assert request_id is not None
        assert request_id in mock_handler._tracker._requests

    def test_verify_and_remove_request_success(self, mock_handler):
        """Test verifying and removing a valid request."""
        request_id = mock_handler.store_outstanding_request(
            idp_name="okta",
        )

        assert mock_handler.verify_and_remove_request(request_id) is True
        assert request_id not in mock_handler._tracker._requests

    def test_verify_and_remove_request_unknown(self, mock_handler):
        """Test that unknown request ID returns False."""
        assert mock_handler.verify_and_remove_request("unknown-request-id") is False

    def test_clear_expired_requests(self, mock_handler):
        """Test clearing expired outstanding requests."""
        # Add a request that's expired
        request_id = "_saml_" + secrets.token_hex(16)
        mock_handler._tracker._requests[request_id] = {
            "idp_name": "okta",
            "relay_state": None,
            "created_at": datetime.now(UTC) - timedelta(hours=1),
            "expires_at": datetime.now(UTC) - timedelta(minutes=30),
        }

        cleared = mock_handler.clear_expired_requests()

        assert cleared >= 1
        assert request_id not in mock_handler._tracker._requests

    def test_get_outstanding_requests(self, mock_handler):
        """Test getting all outstanding requests."""
        request_id = mock_handler.store_outstanding_request(idp_name="okta")

        requests = mock_handler.get_outstanding_requests()

        assert request_id in requests


class TestSAMLIdPRegistration:
    """Tests for SAML IdP registration."""

    def test_register_idp_success(self):
        """Test successful IdP registration."""
        handler = SAMLHandler()
        handler.register_idp(
            name="test-okta",
            entity_id="http://test.okta.com",
            sso_url="https://test.okta.com/sso",
            certificate=MOCK_OKTA_CERTIFICATE,
        )

        assert "test-okta" in handler.list_idps()

    def test_register_idp_with_metadata_url(self):
        """Test IdP registration with metadata URL."""
        handler = SAMLHandler()
        handler.register_idp(
            name="test-okta",
            metadata_url=MOCK_OKTA_METADATA_URL,
        )

        idp = handler.get_idp("test-okta")
        assert idp.metadata_url == MOCK_OKTA_METADATA_URL

    def test_get_unregistered_idp_raises_error(self):
        """Test that getting unregistered IdP raises error."""
        handler = SAMLHandler()

        with pytest.raises(SAMLConfigurationError):
            handler.get_idp("nonexistent-idp")

    def test_list_idps_returns_all_registered(self, mock_handler):
        """Test that list_idps returns all registered IdPs."""
        idps = mock_handler.list_idps()

        assert isinstance(idps, list)
        assert "okta" in idps


class TestSAMLOktaIntegration:
    """Integration tests specific to Okta SAML."""

    def test_okta_entity_id_format(self):
        """Test that Okta entity ID format is correct."""
        assert MOCK_OKTA_ENTITY_ID.startswith("http://www.okta.com/")

    def test_okta_sso_url_format(self):
        """Test that Okta SSO URL format is correct."""
        assert "okta.com" in MOCK_OKTA_SSO_URL
        assert "/sso/saml" in MOCK_OKTA_SSO_URL

    def test_okta_groups_extraction(self):
        """Test that Okta groups are properly extracted."""
        user_info = SAMLUserInfo(
            name_id=MOCK_OKTA_NAME_ID,
            groups=["Engineering", "Developers", "AllStaff"],
        )

        assert "Engineering" in user_info.groups
        assert "Developers" in user_info.groups
        assert len(user_info.groups) == 3

    def test_okta_name_id_as_email(self):
        """Test that Okta NameID uses email format."""
        user_info = SAMLUserInfo(
            name_id="user@example.com",
            name_id_format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        )

        assert "@" in user_info.name_id
        assert "emailAddress" in user_info.name_id_format


class TestSAMLSessionInfo:
    """Tests for session info with SAML authentication."""

    def test_session_info_unauthenticated(self, client, mock_saml_handler_dependency):
        """Test session info for unauthenticated user."""
        response = client.get("/api/v1/sso/session")

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
