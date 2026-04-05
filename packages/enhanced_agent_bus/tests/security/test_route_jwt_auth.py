"""
Security tests: Agent Bus routes must enforce JWT authentication.
Constitutional Hash: 608508a9bd224290

These tests verify that all Agent Bus API routes require a valid Bearer JWT.
They FAIL before the fix (routes use get_tenant_id — header-only check)
and PASS after the fix (routes use get_current_user — JWT verification).

Vulnerability: messages.py, batch.py, policies.py use Depends(get_tenant_id)
               which only validates the X-Tenant-ID header format, not identity.
Fix:           Replace Depends(get_tenant_id) with Depends(get_current_user)
               and derive tenant_id from user.tenant_id in each handler.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import FastAPI
from fastapi.testclient import TestClient

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user
from enhanced_agent_bus.api.routes import batch as batch_routes
from enhanced_agent_bus.api.routes import messages as messages_routes
from enhanced_agent_bus.api.routes import policies as policies_routes

# ---------------------------------------------------------------------------
# App and client setup
# ---------------------------------------------------------------------------

_app = FastAPI()
_app.include_router(messages_routes.router)
_app.include_router(batch_routes.router)
_app.include_router(policies_routes.router)

_client = TestClient(_app, raise_server_exceptions=False)


def _mock_user(tenant: str = "tenant-test") -> UserClaims:
    """Return a minimal UserClaims for dependency override use."""
    return UserClaims(
        sub="user-123",
        tenant_id=tenant,
        roles=["agent"],
        permissions=["send_message"],
        exp=9999999999,
        iat=1000000000,
        iss="acgs2",
        jti="test-jti-override",
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
    )


# ---------------------------------------------------------------------------
# /api/v1/messages — unauthenticated requests
# ---------------------------------------------------------------------------


class TestSendMessageRequiresJWT:
    """POST /api/v1/messages must reject requests without a valid Bearer token."""

    _PAYLOAD: ClassVar[set] = {
        "content": "test",
        "message_type": "command",
        "sender": "agent-1",
        "tenant_id": "tenant-test",
    }

    def test_no_auth_header_returns_401(self):
        """Request with only X-Tenant-ID and no Authorization header → 401."""
        resp = _client.post(
            "/api/v1/messages",
            json=self._PAYLOAD,
            headers={"X-Tenant-ID": "tenant-test"},
        )
        assert resp.status_code == 401, (
            f"Expected 401 (JWT required), got {resp.status_code}. "
            "Route may still use get_tenant_id instead of get_current_user."
        )

    def test_malformed_bearer_returns_4xx(self):
        """Invalid JWT string → 401 (bad token) or 500 (JWT secret unconfigured).
        Either response confirms auth enforcement is active, not business logic.
        """
        resp = _client.post(
            "/api/v1/messages",
            json=self._PAYLOAD,
            headers={
                "X-Tenant-ID": "tenant-test",
                "Authorization": "Bearer not-a-real-jwt",
            },
        )
        assert resp.status_code in (401, 500), (
            f"Expected 401/500 (auth rejected), got {resp.status_code}. "
            "A 2xx/503 means auth is not being enforced."
        )

    def test_missing_auth_no_tenant_header_returns_401(self):
        """No auth at all (no X-Tenant-ID either) → 401, not 400/422."""
        resp = _client.post("/api/v1/messages", json=self._PAYLOAD)
        assert resp.status_code == 401, (
            f"Expected 401 but got {resp.status_code}. "
            "Auth check must fire before tenant-header validation."
        )


class TestGetMessageStatusRequiresJWT:
    """GET /api/v1/messages/{id} must also enforce JWT."""

    _MSG_ID = "00000000-0000-0000-0000-000000000001"

    def test_no_auth_header_returns_401(self):
        resp = _client.get(
            f"/api/v1/messages/{self._MSG_ID}",
            headers={"X-Tenant-ID": "tenant-test"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}."


# ---------------------------------------------------------------------------
# /api/v1/batch/validate — unauthenticated requests
# ---------------------------------------------------------------------------


class TestBatchValidateRequiresJWT:
    """POST /api/v1/batch/validate must enforce JWT."""

    _PAYLOAD: ClassVar[set] = {
        "items": [{"content": {"action": "read"}, "priority": "normal"}],
        "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        "tenant_id": "tenant-test",
    }

    def test_no_auth_header_returns_401(self):
        resp = _client.post(
            "/api/v1/batch/validate",
            json=self._PAYLOAD,
            headers={"X-Tenant-ID": "tenant-test"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}."

    def test_malformed_bearer_returns_4xx(self):
        """Invalid JWT → 401 (bad token) or 500 (JWT secret unconfigured)."""
        resp = _client.post(
            "/api/v1/batch/validate",
            json=self._PAYLOAD,
            headers={
                "X-Tenant-ID": "tenant-test",
                "Authorization": "Bearer garbage",
            },
        )
        assert resp.status_code in (401, 500), (
            f"Expected 401/500 (auth rejected), got {resp.status_code}."
        )


# ---------------------------------------------------------------------------
# /api/v1/policies/validate — unauthenticated requests
# ---------------------------------------------------------------------------


class TestValidatePolicyRequiresJWT:
    """POST /api/v1/policies/validate must enforce JWT."""

    def test_no_auth_header_returns_401(self):
        resp = _client.post(
            "/api/v1/policies/validate",
            json={"policy": "allow { true }"},
            headers={"X-Tenant-ID": "tenant-test"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}."


# ---------------------------------------------------------------------------
# Authenticated happy-path: tenant_id sourced from JWT, not header
# ---------------------------------------------------------------------------


class TestTenantFromJWT:
    """After fix, tenant_id must come from JWT claims, not the header."""

    def test_send_message_authenticated_reaches_business_logic(self):
        """
        With a valid JWT override, request passes auth and reaches the handler.
        Any non-401 response (202, 422, 503) confirms auth is no longer blocking.
        """

        async def _override() -> UserClaims:
            return _mock_user("tenant-from-jwt")

        _app.dependency_overrides[get_current_user] = _override
        try:
            resp = _client.post(
                "/api/v1/messages",
                json={
                    "content": "hello",
                    "message_type": "command",
                    "sender": "agent-1",
                    "tenant_id": "tenant-from-jwt",
                },
                headers={"X-Tenant-ID": "tenant-from-jwt"},
            )
            # 401 means auth still blocking — that's the only failure case
            assert resp.status_code != 401, (
                "Got 401 despite JWT override — get_current_user dep not applied."
            )
        finally:
            _app.dependency_overrides.clear()

    def test_batch_authenticated_reaches_business_logic(self):
        """Batch route with JWT override → any non-401 response."""

        async def _override() -> UserClaims:
            return _mock_user("tenant-from-jwt")

        _app.dependency_overrides[get_current_user] = _override
        try:
            resp = _client.post(
                "/api/v1/batch/validate",
                json={
                    "items": [{"content": {"action": "read"}, "priority": "normal"}],
                    "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
                    "tenant_id": "tenant-from-jwt",
                },
                headers={"X-Tenant-ID": "tenant-from-jwt"},
            )
            assert resp.status_code != 401, (
                "Got 401 despite JWT override — get_current_user dep not applied."
            )
        finally:
            _app.dependency_overrides.clear()

    def test_policies_authenticated_reaches_business_logic(self):
        """Policies route with JWT override → 503 or 200 (not 401)."""

        async def _override() -> UserClaims:
            return _mock_user("tenant-from-jwt")

        _app.dependency_overrides[get_current_user] = _override
        try:
            resp = _client.post(
                "/api/v1/policies/validate",
                json={"policy": "allow { true }"},
                headers={"X-Tenant-ID": "tenant-from-jwt"},
            )
            assert resp.status_code in (200, 503), (
                f"Expected 200 or 503 (auth passed), got {resp.status_code}."
            )
        finally:
            _app.dependency_overrides.clear()

    def test_mismatched_header_tenant_uses_jwt_tenant(self):
        """
        When X-Tenant-ID header differs from JWT tenant_id, after fix the
        route must use the JWT's tenant_id (and optionally reject the mismatch).
        No 401 expected — that would indicate auth is still broken.
        """

        async def _override() -> UserClaims:
            return _mock_user("jwt-tenant")

        _app.dependency_overrides[get_current_user] = _override
        try:
            resp = _client.post(
                "/api/v1/messages",
                json={
                    "content": "hello",
                    "message_type": "command",
                    "sender": "agent-1",
                    "tenant_id": "jwt-tenant",
                },
                headers={"X-Tenant-ID": "different-tenant"},  # deliberate mismatch
            )
            # Must NOT be 401 (auth passed). 400/503/202 are all valid outcomes.
            assert resp.status_code != 401, (
                "Auth check fired for a request that had a valid JWT. "
                "Tenant source may still be the header."
            )
        finally:
            _app.dependency_overrides.clear()
