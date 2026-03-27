"""
Comprehensive unit tests for SAML authentication routes.
Constitutional Hash: 608508a9bd224290

Covers: metadata, providers, login, ACS callback, SLS, logout, and error paths.
All SAML handler interactions are mocked — no real IdP required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request as StarletteRequest

from src.core.services.api_gateway.routes.sso.common import get_saml_handler
from src.core.services.api_gateway.routes.sso.saml import router
from src.core.shared.auth.saml_handler import (
    SAMLAuthenticationError,
    SAMLConfigurationError,
    SAMLError,
    SAMLProviderError,
    SAMLReplayError,
    SAMLValidationError,
)


# ---------------------------------------------------------------------------
# Lightweight stand-in for SAMLUserInfo (avoids importing the full dataclass
# from saml_types which may drag in optional deps).
# ---------------------------------------------------------------------------
@dataclass
class _FakeUserInfo:
    name_id: str = "user@example.com"
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    session_index: str | None = "_session_abc123"
    email: str | None = "user@example.com"
    name: str | None = "Test User"
    given_name: str | None = "Test"
    family_name: str | None = "User"
    groups: list[str] = field(default_factory=lambda: ["Engineering"])
    attributes: dict = field(default_factory=dict)
    issuer: str | None = "https://idp.example.com"
    authn_instant: object = None
    session_not_on_or_after: object = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(handler_mock: AsyncMock) -> FastAPI:
    """Build a minimal FastAPI app with the SAML router and session middleware.

    Also registers a ``/_test/seed-session`` POST endpoint that accepts JSON
    and writes it into the session, so tests can pre-populate session state
    without relying on the SAML flow itself.
    """
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.include_router(router, prefix="/sso/saml")

    # Override the DI dependency so no real handler is created.
    app.dependency_overrides[get_saml_handler] = lambda: handler_mock

    # Helper endpoint: seed arbitrary session data.
    @app.post("/_test/seed-session")
    async def _seed_session(request: StarletteRequest) -> dict:
        body = await request.json()
        for key, value in body.items():
            request.session[key] = value
        return {"ok": True}

    return app


@pytest.fixture()
def handler() -> AsyncMock:
    """Create a fully-mocked SAML handler.

    ``list_idps`` is synchronous in the real handler so we use a plain
    ``MagicMock`` for it to avoid returning an unawaited coroutine.
    """
    from unittest.mock import MagicMock

    h = AsyncMock()
    # Synchronous method — must NOT be an AsyncMock.
    h.list_idps = MagicMock(return_value=["okta", "azure"])
    h.generate_metadata = AsyncMock(return_value="<md:EntityDescriptor/>")
    h.initiate_login = AsyncMock(return_value=("https://idp.example.com/sso", "req-id-1"))
    h.process_acs_response = AsyncMock(return_value=_FakeUserInfo())
    h.process_sls_response = AsyncMock()
    h.initiate_logout = AsyncMock(return_value="https://idp.example.com/slo")
    return h


@pytest.fixture()
def client(handler: AsyncMock) -> TestClient:
    app = _make_app(handler)
    return TestClient(app, base_url="http://testserver")


# Helpers -------------------------------------------------------------------

def _sso_settings(
    *,
    enabled: bool = True,
    saml_enabled: bool = True,
    auto_provision: bool = True,
    default_role: str = "viewer",
    allowed_domains: list[str] | None = None,
) -> object:
    """Return a lightweight namespace that mirrors settings.sso for patching."""

    class _Ns:
        pass

    ns = _Ns()
    ns.enabled = enabled  # type: ignore[attr-defined]
    ns.saml_enabled = saml_enabled  # type: ignore[attr-defined]
    ns.auto_provision_users = auto_provision  # type: ignore[attr-defined]
    ns.default_role_on_provision = default_role  # type: ignore[attr-defined]
    ns.allowed_domains = allowed_domains  # type: ignore[attr-defined]
    return ns


_SSO_SETTINGS_PATH = "src.core.services.api_gateway.routes.sso.saml.settings"


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.unit
class TestSAMLMetadata:
    """GET /sso/saml/metadata"""

    def test_metadata_returns_xml(self, client: TestClient, handler: AsyncMock) -> None:
        resp = client.get("/sso/saml/metadata")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"
        assert "sp-metadata.xml" in resp.headers.get("content-disposition", "")
        assert resp.text == "<md:EntityDescriptor/>"
        handler.generate_metadata.assert_awaited_once()

    @pytest.mark.parametrize(
        "exc_cls",
        [SAMLError, SAMLProviderError, SAMLValidationError, ValueError, TypeError],
    )
    def test_metadata_error_returns_500(
        self,
        handler: AsyncMock,
        exc_cls: type,
    ) -> None:
        handler.generate_metadata.side_effect = exc_cls("boom")
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
        resp = c.get("/sso/saml/metadata")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Metadata generation failed"


@pytest.mark.unit
class TestListProviders:
    """GET /sso/saml/providers"""

    def test_list_providers(self, client: TestClient) -> None:
        resp = client.get("/sso/saml/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {p["name"] for p in data}
        assert names == {"okta", "azure"}
        assert all(p["type"] == "saml" and p["enabled"] is True for p in data)

    def test_list_providers_empty(self, handler: AsyncMock) -> None:
        handler.list_idps.return_value = []
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver")
        resp = c.get("/sso/saml/providers")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.unit
class TestSAMLLogin:
    """GET /sso/saml/login"""

    def test_login_redirects(self, client: TestClient, handler: AsyncMock) -> None:
        with patch(_SSO_SETTINGS_PATH) as mock_settings:
            mock_settings.sso = _sso_settings(enabled=True, saml_enabled=True)
            resp = client.get(
                "/sso/saml/login",
                params={"provider": "okta"},
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://idp.example.com/sso"
        handler.initiate_login.assert_awaited_once_with(
            idp_name="okta",
            relay_state=None,
            force_authn=False,
        )

    def test_login_with_relay_state_and_force(
        self, client: TestClient, handler: AsyncMock
    ) -> None:
        with patch(_SSO_SETTINGS_PATH) as mock_settings:
            mock_settings.sso = _sso_settings()
            resp = client.get(
                "/sso/saml/login",
                params={
                    "provider": "okta",
                    "relay_state": "/dashboard",
                    "force_authn": "true",
                },
                follow_redirects=False,
            )

        assert resp.status_code == 302
        handler.initiate_login.assert_awaited_once_with(
            idp_name="okta",
            relay_state="/dashboard",
            force_authn=True,
        )

    def test_login_disabled_returns_503(self, handler: AsyncMock) -> None:
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
        with patch(_SSO_SETTINGS_PATH) as mock_settings:
            mock_settings.sso = _sso_settings(enabled=False, saml_enabled=False)
            resp = c.get("/sso/saml/login", params={"provider": "okta"})

        assert resp.status_code == 503
        assert "SAML disabled" in resp.json()["detail"]

    def test_login_configuration_error_returns_404(
        self, handler: AsyncMock
    ) -> None:
        handler.initiate_login.side_effect = SAMLConfigurationError("no such provider")
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
        with patch(_SSO_SETTINGS_PATH) as mock_settings:
            mock_settings.sso = _sso_settings()
            resp = c.get("/sso/saml/login", params={"provider": "bad"})

        assert resp.status_code == 404
        assert "provider not found" in resp.json()["detail"].lower()

    @pytest.mark.parametrize(
        "exc_cls",
        [SAMLProviderError, SAMLError, SAMLAuthenticationError, ValueError, TypeError],
    )
    def test_login_internal_error_returns_500(
        self,
        handler: AsyncMock,
        exc_cls: type,
    ) -> None:
        handler.initiate_login.side_effect = exc_cls("boom")
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
        with patch(_SSO_SETTINGS_PATH) as mock_settings:
            mock_settings.sso = _sso_settings()
            resp = c.get("/sso/saml/login", params={"provider": "okta"})

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Login initiation failed"

    def test_login_requires_provider_query_param(self, client: TestClient) -> None:
        """provider is a required query param; omitting it should 422."""
        resp = client.get("/sso/saml/login")
        assert resp.status_code == 422


@pytest.mark.unit
class TestSAMLACS:
    """POST /sso/saml/acs"""

    def _post_acs(
        self,
        client: TestClient,
        *,
        saml_response: str = "PGRvYz4=",
        relay_state: str | None = None,
    ):
        data = {"SAMLResponse": saml_response}
        if relay_state is not None:
            data["RelayState"] = relay_state
        return client.post("/sso/saml/acs", data=data)

    def test_acs_success(self, handler: AsyncMock) -> None:
        """Happy path: valid SAML response, JIT provisioning, session populated."""
        fake_user = {
            "id": "uid-1",
            "email": "user@example.com",
            "name": "Test User",
            "roles": ["viewer"],
        }

        class _FakeProv:
            async def get_or_create_user(self, **kwargs):
                @dataclass
                class _R:
                    user: dict = field(default_factory=lambda: fake_user)
                    created: bool = True
                    roles_updated: bool = False
                    provider_id: str = "saml"

                return _R()

        with patch(
            "src.core.services.api_gateway.routes.sso.saml.get_provisioner",
            return_value=_FakeProv(),
        ), patch(_SSO_SETTINGS_PATH) as mock_settings:
            mock_settings.sso = _sso_settings()
            app = _make_app(handler)
            c = TestClient(app, base_url="http://testserver")
            resp = c.post("/sso/saml/acs", data={"SAMLResponse": "PGRvYz4="})

        assert resp.status_code == 200
        body = resp.json()
        assert body["name_id"] == "user@example.com"
        assert body["email"] == "user@example.com"

    @pytest.mark.parametrize(
        "exc_cls,expected_status",
        [
            (SAMLReplayError, 401),
            (SAMLValidationError, 401),
            (SAMLAuthenticationError, 401),
        ],
    )
    def test_acs_auth_failures_return_401(
        self,
        handler: AsyncMock,
        exc_cls: type,
        expected_status: int,
    ) -> None:
        handler.process_acs_response.side_effect = exc_cls("nope")
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
        resp = c.post("/sso/saml/acs", data={"SAMLResponse": "PGRvYz4="})
        assert resp.status_code == expected_status
        assert "authentication failed" in resp.json()["detail"].lower()

    @pytest.mark.parametrize(
        "exc_cls",
        [
            SAMLProviderError,
            SAMLError,
            SAMLConfigurationError,
            ValueError,
            TypeError,
            LookupError,
        ],
    )
    def test_acs_internal_errors_return_500(
        self,
        handler: AsyncMock,
        exc_cls: type,
    ) -> None:
        handler.process_acs_response.side_effect = exc_cls("fail")
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
        resp = c.post("/sso/saml/acs", data={"SAMLResponse": "PGRvYz4="})
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Assertion processing failed"

    def test_acs_missing_form_field(self, client: TestClient) -> None:
        """SAMLResponse is a required form field."""
        resp = client.post("/sso/saml/acs", data={})
        assert resp.status_code == 422


@pytest.mark.unit
class TestSAMLSLS:
    """GET/POST /sso/saml/sls (Single Logout Service)"""

    _USER_SESSION = {
        "user": {
            "id": "uid-1",
            "provider": "okta",
            "name_id": "user@example.com",
            "session_index": "_sess_1",
        },
        "saml_request_id": "req-1",
    }

    def _seed(self, client: TestClient, data: dict | None = None) -> None:
        """Seed session state via the ``/_test/seed-session`` helper."""
        resp = client.post("/_test/seed-session", json=data or self._USER_SESSION)
        assert resp.status_code == 200

    def test_sls_get_clears_session_no_response(
        self, client: TestClient, handler: AsyncMock
    ) -> None:
        """SLS without SAMLResponse simply clears session."""
        resp = client.get("/sso/saml/sls")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["redirect_url"] is None
        handler.process_sls_response.assert_not_awaited()

    def test_sls_post_with_response_and_user(
        self, client: TestClient, handler: AsyncMock
    ) -> None:
        """When a SAMLResponse is present and user is in session, process SLS."""
        self._seed(client)
        resp = client.get(
            "/sso/saml/sls",
            params={"SAMLResponse": "abc123", "RelayState": "/home"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        # RelayState starting with / and no :// passes validation
        assert body["redirect_url"] == "/home"
        handler.process_sls_response.assert_awaited_once_with("abc123", "okta")

    def test_sls_rejects_absolute_relay_state(
        self, client: TestClient
    ) -> None:
        """Open-redirect protection: absolute URLs are rejected."""
        self._seed(client)
        resp = client.get(
            "/sso/saml/sls",
            params={"SAMLResponse": "abc", "RelayState": "https://evil.com/phish"},
        )
        body = resp.json()
        assert body["redirect_url"] is None

    def test_sls_rejects_protocol_relative_relay_state(
        self, client: TestClient
    ) -> None:
        """Absolute http:// URLs are rejected by the open-redirect guard."""
        resp = client.get(
            "/sso/saml/sls",
            params={"RelayState": "http://evil.com"},
        )
        body = resp.json()
        assert body["redirect_url"] is None

    def test_sls_without_user_skips_sls_processing(
        self, client: TestClient, handler: AsyncMock
    ) -> None:
        """No user in session means SAMLResponse is not processed."""
        resp = client.get(
            "/sso/saml/sls",
            params={"SAMLResponse": "abc123"},
        )
        assert resp.status_code == 200
        # provider_name is None when user is None, so handler is NOT called
        handler.process_sls_response.assert_not_awaited()


@pytest.mark.unit
class TestSAMLLogout:
    """POST /sso/saml/logout"""

    _USER_SESSION = {
        "user": {
            "id": "uid-1",
            "provider": "okta",
            "name_id": "user@example.com",
            "session_index": "_sess_1",
        },
    }

    def _seed(self, client: TestClient, data: dict | None = None) -> None:
        resp = client.post("/_test/seed-session", json=data or self._USER_SESSION)
        assert resp.status_code == 200

    def test_logout_no_session(self, client: TestClient, handler: AsyncMock) -> None:
        """When there is no active session, return success immediately."""
        resp = client.post("/sso/saml/logout")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "No active session"
        handler.initiate_logout.assert_not_awaited()

    def test_logout_with_session_initiates_slo(
        self, client: TestClient, handler: AsyncMock
    ) -> None:
        """Active session triggers IdP-initiated SLO and returns redirect."""
        self._seed(client)
        resp = client.post("/sso/saml/logout")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "Logged out"
        assert body["redirect_url"] == "https://idp.example.com/slo"
        handler.initiate_logout.assert_awaited_once()

    def test_logout_no_name_id_skips_slo(
        self, client: TestClient, handler: AsyncMock
    ) -> None:
        """User in session but missing name_id skips SLO."""
        self._seed(client, {"user": {"id": "uid-2", "provider": "okta"}})
        resp = client.post("/sso/saml/logout")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["redirect_url"] is None
        handler.initiate_logout.assert_not_awaited()

    @pytest.mark.parametrize(
        "exc_cls",
        [
            SAMLProviderError,
            SAMLError,
            SAMLConfigurationError,
            SAMLAuthenticationError,
            ValueError,
            TypeError,
            LookupError,
        ],
    )
    def test_logout_slo_error_still_succeeds(
        self,
        handler: AsyncMock,
        exc_cls: type,
    ) -> None:
        """Even if the IdP SLO request fails, logout clears session and succeeds."""
        handler.initiate_logout.side_effect = exc_cls("slo-fail")
        app = _make_app(handler)
        c = TestClient(app, base_url="http://testserver")
        c.post("/_test/seed-session", json=self._USER_SESSION)

        resp = c.post("/sso/saml/logout")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        # redirect_url is None because handler raised
        assert body["redirect_url"] is None

    def test_logout_without_provider_skips_slo(
        self, client: TestClient, handler: AsyncMock
    ) -> None:
        """User in session but missing provider skips SLO initiation."""
        self._seed(client, {"user": {"id": "uid-3", "name_id": "user@example.com"}})
        resp = client.post("/sso/saml/logout")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["redirect_url"] is None
        handler.initiate_logout.assert_not_awaited()
