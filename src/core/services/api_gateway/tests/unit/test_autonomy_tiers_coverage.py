"""
Tests for autonomy_tiers.py route coverage.
Constitutional Hash: 608508a9bd224290

Covers: CRUD endpoints, _require_tenant_admin, _to_response helpers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.services.api_gateway.models.tier_assignment import (
    AgentTierAssignment,
    AutonomyTier,
)
from src.core.services.api_gateway.repositories.tier_assignment import NotFoundError
from src.core.services.api_gateway.routes.autonomy_tiers import (
    _require_tenant_admin,
    _to_response,
    autonomy_tiers_router,
    get_tier_repo,
)
from src.core.shared.security.auth import UserClaims, get_current_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user(roles: list[str] | None = None) -> UserClaims:
    now = int(datetime.now(UTC).timestamp())
    return UserClaims(
        sub="admin-1",
        tenant_id="tenant-1",
        roles=roles or ["tenant_admin"],
        permissions=["admin"],
        exp=now + 3600,
        iat=now,
    )


_ADMIN_USER = _make_user(["tenant_admin"])
_NON_ADMIN_USER = _make_user(["user"])

_ASSIGNMENT_ID = uuid.uuid4()
_NOW = datetime.now(UTC)


def _make_assignment(
    agent_id: str = "agent-1",
    tier: AutonomyTier = AutonomyTier.BOUNDED,
    boundaries: list[str] | None = None,
) -> AgentTierAssignment:
    return AgentTierAssignment(
        id=_ASSIGNMENT_ID,
        agent_id=agent_id,
        tenant_id="tenant-1",
        tier=tier,
        action_boundaries=boundaries or ["read:*"],
        assigned_by="admin-1",
        assigned_at=_NOW,
        created_at=_NOW,
    )


def _build_app(user: UserClaims, repo: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(autonomy_tiers_router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_tier_repo] = lambda: repo
    return app


@pytest.fixture()
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create = AsyncMock(return_value=_make_assignment())
    repo.get_by_agent = AsyncMock(return_value=_make_assignment())
    repo.update = AsyncMock(return_value=_make_assignment())
    repo.delete = AsyncMock()
    repo.list_by_tenant = AsyncMock(return_value=[_make_assignment()])
    return repo


@pytest.fixture()
def client(mock_repo: AsyncMock) -> TestClient:
    return TestClient(_build_app(_ADMIN_USER, mock_repo))


@pytest.fixture()
def non_admin_client(mock_repo: AsyncMock) -> TestClient:
    return TestClient(_build_app(_NON_ADMIN_USER, mock_repo))


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for _require_tenant_admin and _to_response."""

    def test_require_tenant_admin_passes(self):
        _require_tenant_admin(_ADMIN_USER)  # Should not raise

    def test_require_tenant_admin_raises_403(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _require_tenant_admin(_NON_ADMIN_USER)
        assert exc_info.value.status_code == 403

    def test_to_response_converts_orm(self):
        assignment = _make_assignment()
        resp = _to_response(assignment)
        assert resp.agent_id == "agent-1"
        assert resp.tier == AutonomyTier.BOUNDED
        assert resp.action_boundaries == ["read:*"]
        assert resp.id == _ASSIGNMENT_ID


# ---------------------------------------------------------------------------
# POST /autonomy-tiers (create)
# ---------------------------------------------------------------------------


class TestCreateTierAssignment:
    """POST /autonomy-tiers"""

    def test_create_success(self, client: TestClient):
        resp = client.post(
            "/autonomy-tiers",
            json={
                "agent_id": "agent-1",
                "tier": "BOUNDED",
                "action_boundaries": ["read:*"],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["agent_id"] == "agent-1"
        assert body["tier"] == "BOUNDED"

    def test_create_forbidden_for_non_admin(self, non_admin_client: TestClient):
        resp = non_admin_client.post(
            "/autonomy-tiers",
            json={"agent_id": "agent-1", "tier": "ADVISORY"},
        )
        assert resp.status_code == 403

    def test_create_validation_error(self, client: TestClient):
        resp = client.post(
            "/autonomy-tiers",
            json={"agent_id": "agent-1", "tier": "INVALID_TIER"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


class TestGetTierAssignment:
    """GET /autonomy-tiers/{agent_id}"""

    def test_get_success(self, client: TestClient):
        resp = client.get("/autonomy-tiers/agent-1")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent-1"

    def test_get_not_found(self, mock_repo: AsyncMock):
        mock_repo.get_by_agent = AsyncMock(return_value=None)
        cl = TestClient(_build_app(_ADMIN_USER, mock_repo))
        resp = cl.get("/autonomy-tiers/agent-missing")
        assert resp.status_code == 404

    def test_get_forbidden_for_non_admin(self, non_admin_client: TestClient):
        resp = non_admin_client.get("/autonomy-tiers/agent-1")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


class TestUpdateTierAssignment:
    """PUT /autonomy-tiers/{agent_id}"""

    def test_update_success(self, client: TestClient):
        resp = client.put(
            "/autonomy-tiers/agent-1",
            json={"tier": "ADVISORY", "action_boundaries": None},
        )
        assert resp.status_code == 200

    def test_update_not_found(self, mock_repo: AsyncMock):
        mock_repo.update = AsyncMock(side_effect=NotFoundError("not found"))
        cl = TestClient(_build_app(_ADMIN_USER, mock_repo))
        resp = cl.put(
            "/autonomy-tiers/agent-missing",
            json={"tier": "BOUNDED"},
        )
        assert resp.status_code == 404

    def test_update_forbidden_for_non_admin(self, non_admin_client: TestClient):
        resp = non_admin_client.put(
            "/autonomy-tiers/agent-1",
            json={"tier": "BOUNDED"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


class TestDeleteTierAssignment:
    """DELETE /autonomy-tiers/{agent_id}"""

    def test_delete_success(self, client: TestClient):
        resp = client.delete("/autonomy-tiers/agent-1")
        assert resp.status_code == 204

    def test_delete_not_found(self, mock_repo: AsyncMock):
        mock_repo.delete = AsyncMock(side_effect=NotFoundError("not found"))
        cl = TestClient(_build_app(_ADMIN_USER, mock_repo))
        resp = cl.delete("/autonomy-tiers/agent-missing")
        assert resp.status_code == 404

    def test_delete_forbidden_for_non_admin(self, non_admin_client: TestClient):
        resp = non_admin_client.delete("/autonomy-tiers/agent-1")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /autonomy-tiers (list)
# ---------------------------------------------------------------------------


class TestListTierAssignments:
    """GET /autonomy-tiers"""

    def test_list_success(self, client: TestClient):
        resp = client.get("/autonomy-tiers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

    def test_list_empty(self, mock_repo: AsyncMock):
        mock_repo.list_by_tenant = AsyncMock(return_value=[])
        cl = TestClient(_build_app(_ADMIN_USER, mock_repo))
        resp = cl.get("/autonomy-tiers")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_forbidden_for_non_admin(self, non_admin_client: TestClient):
        resp = non_admin_client.get("/autonomy-tiers")
        assert resp.status_code == 403

    def test_list_multiple_assignments(self, mock_repo: AsyncMock):
        mock_repo.list_by_tenant = AsyncMock(
            return_value=[
                _make_assignment("agent-1"),
                _make_assignment("agent-2", AutonomyTier.ADVISORY),
            ]
        )
        cl = TestClient(_build_app(_ADMIN_USER, mock_repo))
        resp = cl.get("/autonomy-tiers")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2
