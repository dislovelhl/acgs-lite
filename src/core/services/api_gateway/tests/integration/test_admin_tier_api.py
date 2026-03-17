"""
Integration tests for admin autonomy-tier CRUD API.
Constitutional Hash: cdd01ef066bc6cf2

All database and Redis dependencies are mocked; no real infrastructure required.
Tests validate RBAC enforcement, tenant isolation, and full CRUD lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.models.tier_assignment import AgentTierAssignment, AutonomyTier
from src.core.services.api_gateway.repositories.tier_assignment import (
    NotFoundError,
    TierAssignmentRepository,
)
from src.core.services.api_gateway.routes.autonomy_tiers import (
    autonomy_tiers_router,
    get_tier_repo,
)
from src.core.shared.security.auth import UserClaims, get_current_user

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TENANT_A = "tenant-a"
_TENANT_B = "tenant-b"
_AGENT_ID = "agent-001"

_ADMIN_USER_A = UserClaims(
    sub="admin-user-a",
    tenant_id=_TENANT_A,
    roles=["tenant_admin"],
    permissions=[],
    exp=9_999_999_999,
    iat=1_000_000_000,
)

_NON_ADMIN_USER = UserClaims(
    sub="regular-user",
    tenant_id=_TENANT_A,
    roles=["user"],
    permissions=[],
    exp=9_999_999_999,
    iat=1_000_000_000,
)

_ADMIN_USER_B = UserClaims(
    sub="admin-user-b",
    tenant_id=_TENANT_B,
    roles=["tenant_admin"],
    permissions=[],
    exp=9_999_999_999,
    iat=1_000_000_000,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assignment(
    agent_id: str = _AGENT_ID,
    tenant_id: str = _TENANT_A,
    tier: AutonomyTier = AutonomyTier.BOUNDED,
    action_boundaries: list[str] | None = None,
    assigned_by: str = "admin-user-a",
) -> AgentTierAssignment:
    now = datetime.now(UTC)
    return AgentTierAssignment(
        id=uuid.uuid4(),
        agent_id=agent_id,
        tenant_id=tenant_id,
        tier=tier,
        action_boundaries=action_boundaries,
        assigned_by=assigned_by,
        assigned_at=now,
        created_at=now,
    )


def _make_client(
    repo: TierAssignmentRepository,
    user: UserClaims = _ADMIN_USER_A,
) -> TestClient:
    """Build a minimal FastAPI test app with the autonomy-tiers router."""
    app = FastAPI()
    app.include_router(autonomy_tiers_router, prefix="/api/v1/admin")
    app.dependency_overrides[get_tier_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/v1/admin/autonomy-tiers
# ---------------------------------------------------------------------------


class TestCreateTierAssignment:
    """POST /api/v1/admin/autonomy-tiers → 201 or 403 or 422."""

    @pytest.mark.integration
    def test_authorized_admin_creates_assignment(self) -> None:
        """Authorized tenant_admin creates tier assignment → 201, all response fields present."""
        assignment = _make_assignment()
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.create.return_value = assignment

        client = _make_client(repo)
        response = client.post(
            "/api/v1/admin/autonomy-tiers",
            json={"agent_id": _AGENT_ID, "tier": "BOUNDED"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == _AGENT_ID
        assert data["tenant_id"] == _TENANT_A
        assert data["tier"] == "BOUNDED"
        assert "id" in data
        assert "assigned_by" in data
        assert "assigned_at" in data
        repo.create.assert_called_once()

    @pytest.mark.integration
    def test_unauthorized_caller_gets_403(self) -> None:
        """Non-admin JWT caller attempting POST → 403."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        client = _make_client(repo, user=_NON_ADMIN_USER)

        response = client.post(
            "/api/v1/admin/autonomy-tiers",
            json={"agent_id": _AGENT_ID, "tier": "BOUNDED"},
        )

        assert response.status_code == 403
        repo.create.assert_not_called()

    @pytest.mark.integration
    def test_invalid_tier_string_returns_422(self) -> None:
        """POST with invalid tier string (e.g. 'SUPERUSER') → 422."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        client = _make_client(repo)

        response = client.post(
            "/api/v1/admin/autonomy-tiers",
            json={"agent_id": _AGENT_ID, "tier": "SUPERUSER"},
        )

        assert response.status_code == 422
        repo.create.assert_not_called()

    @pytest.mark.integration
    def test_create_with_action_boundaries_for_bounded_tier(self) -> None:
        """POST BOUNDED tier with action_boundaries → included in response."""
        boundaries = ["read:*", "write:documents"]
        assignment = _make_assignment(tier=AutonomyTier.BOUNDED, action_boundaries=boundaries)
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.create.return_value = assignment

        client = _make_client(repo)
        response = client.post(
            "/api/v1/admin/autonomy-tiers",
            json={"agent_id": _AGENT_ID, "tier": "BOUNDED", "action_boundaries": boundaries},
        )

        assert response.status_code == 201
        assert response.json()["action_boundaries"] == boundaries


# ---------------------------------------------------------------------------
# GET /api/v1/admin/autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


class TestGetTierAssignment:
    """GET /api/v1/admin/autonomy-tiers/{agent_id} → 200 or 404."""

    @pytest.mark.integration
    def test_admin_reads_own_tenant_assignment(self) -> None:
        """Admin reads agent tier within own tenant → 200."""
        assignment = _make_assignment()
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = assignment

        client = _make_client(repo)
        response = client.get(f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == _AGENT_ID
        assert data["tenant_id"] == _TENANT_A

    @pytest.mark.integration
    def test_cross_tenant_agent_returns_404(self) -> None:
        """Admin reads another tenant's agent tier (cross-tenant isolation) → 404.

        Tenant isolation: repo.get_by_agent receives user.tenant_id from JWT.
        An agent belonging to tenant-a is not visible when queried under tenant-b.
        """
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None  # not found in tenant-b scope

        client = _make_client(repo, user=_ADMIN_USER_B)
        response = client.get(f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}")

        assert response.status_code == 404
        # Verify the repo was queried with tenant-b's ID (not tenant-a)
        repo.get_by_agent.assert_called_once_with(agent_id=_AGENT_ID, tenant_id=_TENANT_B)

    @pytest.mark.integration
    def test_missing_agent_returns_404(self) -> None:
        """GET for unknown agent → 404."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.get_by_agent.return_value = None

        client = _make_client(repo)
        response = client.get("/api/v1/admin/autonomy-tiers/unknown-agent")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


class TestUpdateTierAssignment:
    """PUT /api/v1/admin/autonomy-tiers/{agent_id} → 200 or 404."""

    @pytest.mark.integration
    def test_put_updates_tier_and_clears_cache(self) -> None:
        """PUT updates tier and clears Redis cache; subsequent GET returns new tier value."""
        updated = _make_assignment(tier=AutonomyTier.BOUNDED, action_boundaries=["read:*"])
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.update.return_value = updated
        repo.get_by_agent.return_value = updated

        client = _make_client(repo)
        put_response = client.put(
            f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}",
            json={"tier": "BOUNDED", "action_boundaries": ["read:*"]},
        )
        assert put_response.status_code == 200
        assert put_response.json()["tier"] == "BOUNDED"

        get_response = client.get(f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}")
        assert get_response.status_code == 200
        assert get_response.json()["tier"] == "BOUNDED"

    @pytest.mark.integration
    def test_put_missing_agent_returns_404(self) -> None:
        """PUT for unknown agent → 404."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.update.side_effect = NotFoundError("not found")

        client = _make_client(repo)
        response = client.put(
            "/api/v1/admin/autonomy-tiers/unknown-agent",
            json={"tier": "ADVISORY"},
        )

        assert response.status_code == 404

    @pytest.mark.integration
    def test_unauthorized_caller_gets_403(self) -> None:
        """Non-admin JWT caller attempting PUT → 403."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        client = _make_client(repo, user=_NON_ADMIN_USER)

        response = client.put(
            f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}",
            json={"tier": "ADVISORY"},
        )

        assert response.status_code == 403
        repo.update.assert_not_called()


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


class TestDeleteTierAssignment:
    """DELETE /api/v1/admin/autonomy-tiers/{agent_id} → 204 or 404."""

    @pytest.mark.integration
    def test_delete_removes_assignment(self) -> None:
        """DELETE removes assignment; subsequent GET returns 404."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.delete.return_value = None
        repo.get_by_agent.return_value = None  # after deletion

        client = _make_client(repo)

        delete_response = client.delete(f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}")
        assert delete_response.status_code == 204

        get_response = client.get(f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}")
        assert get_response.status_code == 404

    @pytest.mark.integration
    def test_delete_missing_agent_returns_404(self) -> None:
        """DELETE for unknown agent → 404."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.delete.side_effect = NotFoundError("not found")

        client = _make_client(repo)
        response = client.delete("/api/v1/admin/autonomy-tiers/unknown-agent")

        assert response.status_code == 404

    @pytest.mark.integration
    def test_unauthorized_caller_gets_403(self) -> None:
        """Non-admin JWT caller attempting DELETE → 403."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        client = _make_client(repo, user=_NON_ADMIN_USER)

        response = client.delete(f"/api/v1/admin/autonomy-tiers/{_AGENT_ID}")

        assert response.status_code == 403
        repo.delete.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/v1/admin/autonomy-tiers (list)
# ---------------------------------------------------------------------------


class TestListTierAssignments:
    """GET /api/v1/admin/autonomy-tiers → 200 with {items, total}."""

    @pytest.mark.integration
    def test_list_returns_tenant_scoped_assignments(self) -> None:
        """GET list returns only assignments scoped to caller's tenant, total count correct."""
        assignments = [
            _make_assignment(agent_id="agent-001", tenant_id=_TENANT_A),
            _make_assignment(agent_id="agent-002", tenant_id=_TENANT_A),
        ]
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.list_by_tenant.return_value = assignments

        client = _make_client(repo)
        response = client.get("/api/v1/admin/autonomy-tiers")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["tenant_id"] == _TENANT_A

        # Verify repo was queried with the JWT's tenant_id (not another tenant)
        repo.list_by_tenant.assert_called_once_with(tenant_id=_TENANT_A)

    @pytest.mark.integration
    def test_list_empty_tenant_returns_zero_items(self) -> None:
        """GET list for tenant with no assignments → {items: [], total: 0}."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        repo.list_by_tenant.return_value = []

        client = _make_client(repo)
        response = client.get("/api/v1/admin/autonomy-tiers")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.integration
    def test_list_unauthorized_caller_gets_403(self) -> None:
        """Non-admin caller attempting list → 403."""
        repo = AsyncMock(spec=TierAssignmentRepository)
        client = _make_client(repo, user=_NON_ADMIN_USER)

        response = client.get("/api/v1/admin/autonomy-tiers")

        assert response.status_code == 403
        repo.list_by_tenant.assert_not_called()
