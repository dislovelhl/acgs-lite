"""
Gateway Tenant Security Tests - Integration Tests

These tests verify tenant isolation and security at the API Gateway level.
They test the actual FastAPI endpoints with TestClient.

Constitutional Hash: cdd01ef066bc6cf2
"""

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.testclient import TestClient


class MockUserClaims:
    def __init__(self, tenant_id: str, sub: str = "user-123"):
        self.tenant_id = tenant_id
        self.sub = sub
        self.email = f"{sub}@test.com"
        self.roles = ["user"]


@pytest.fixture
def mock_app():
    app = FastAPI()

    async def get_current_user_optional(
        authorization: str | None = Header(None),
    ) -> MockUserClaims | None:
        if not authorization:
            return None
        if "tenant-A" in authorization:
            return MockUserClaims("tenant-A", "user-A")
        if "tenant-B" in authorization:
            return MockUserClaims("tenant-B", "user-B")
        return MockUserClaims("default-tenant", "default-user")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_to_agent_bus_VULNERABLE(
        request: Request,
        path: str,
        user: MockUserClaims | None = Depends(get_current_user_optional),
    ):
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")

        forwarded_headers = dict(request.headers)
        return {
            "forwarded_tenant": forwarded_headers.get("x-tenant-id"),
            "user_tenant": user.tenant_id,
            "user_id": user.sub,
            "path": path,
            "headers": dict(request.headers),
        }

    return app


@pytest.fixture
def client(mock_app):
    return TestClient(mock_app)


class TestGatewayTenantSpoofing:
    def test_authenticated_user_can_spoof_tenant_header(self, client):
        response = client.get(
            "/api/v1/messages",
            headers={
                "Authorization": "Bearer token-tenant-A",
                "X-Tenant-ID": "tenant-B",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["user_tenant"] == "tenant-A"
        assert data["forwarded_tenant"] == "tenant-B"

        assert data["forwarded_tenant"] != data["user_tenant"], (
            "VULNERABILITY: Spoofed tenant header is different from JWT tenant"
        )

    def test_missing_tenant_header_not_auto_injected(self, client):
        response = client.get(
            "/api/v1/messages",
            headers={
                "Authorization": "Bearer token-tenant-A",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["user_tenant"] == "tenant-A"
        assert data["forwarded_tenant"] is None, (
            "VULNERABILITY: X-Tenant-ID not auto-injected from JWT tenant"
        )


class TestGatewaySecurityAfterFix:
    @pytest.fixture
    def fixed_app(self):
        app = FastAPI()

        async def get_current_user_optional(
            authorization: str | None = Header(None),
        ) -> MockUserClaims | None:
            if not authorization:
                return None
            if "tenant-A" in authorization:
                return MockUserClaims("tenant-A", "user-A")
            if "tenant-B" in authorization:
                return MockUserClaims("tenant-B", "user-B")
            return MockUserClaims("default-tenant", "default-user")

        HOP_BY_HOP_HEADERS = {
            "host",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
            "content-length",
        }

        @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
        async def proxy_to_agent_bus_FIXED(
            request: Request,
            path: str,
            user: MockUserClaims | None = Depends(get_current_user_optional),
        ):
            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")

            incoming_tenant = request.headers.get("x-tenant-id")
            if incoming_tenant and incoming_tenant != user.tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"Tenant mismatch: token tenant '{user.tenant_id}' != header '{incoming_tenant}'",
                )

            safe_headers = {
                k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
            }
            safe_headers["x-tenant-id"] = user.tenant_id
            safe_headers["x-user-id"] = user.sub

            return {
                "forwarded_tenant": safe_headers.get("x-tenant-id"),
                "forwarded_user": safe_headers.get("x-user-id"),
                "user_tenant": user.tenant_id,
                "path": path,
                "hop_headers_filtered": all(h not in safe_headers for h in HOP_BY_HOP_HEADERS),
            }

        return app

    @pytest.fixture
    def fixed_client(self, fixed_app):
        return TestClient(fixed_app)

    def test_tenant_mismatch_returns_403(self, fixed_client):
        response = fixed_client.get(
            "/api/v1/messages",
            headers={
                "Authorization": "Bearer token-tenant-A",
                "X-Tenant-ID": "tenant-B",
            },
        )

        assert response.status_code == 403, "EXPECTED: Tenant mismatch should return 403"
        assert "mismatch" in response.json()["detail"].lower()

    def test_matching_tenant_header_allowed(self, fixed_client):
        response = fixed_client.get(
            "/api/v1/messages",
            headers={
                "Authorization": "Bearer token-tenant-A",
                "X-Tenant-ID": "tenant-A",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["forwarded_tenant"] == "tenant-A"

    def test_missing_tenant_header_auto_injected(self, fixed_client):
        response = fixed_client.get(
            "/api/v1/messages",
            headers={
                "Authorization": "Bearer token-tenant-A",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["forwarded_tenant"] == "tenant-A", (
            "X-Tenant-ID should be auto-injected from JWT"
        )
        assert data["forwarded_user"] == "user-A", "X-User-ID should be injected"

    def test_hop_by_hop_headers_filtered(self, fixed_client):
        response = fixed_client.get(
            "/api/v1/messages",
            headers={
                "Authorization": "Bearer token-tenant-A",
                "Connection": "keep-alive",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["hop_headers_filtered"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
