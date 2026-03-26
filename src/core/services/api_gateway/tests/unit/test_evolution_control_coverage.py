"""
Tests for evolution_control.py route coverage.
Constitutional Hash: 608508a9bd224290

Covers: status, pause, resume, stop endpoints plus dependency resolution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from src.core.services.api_gateway.routes.evolution_control import (
    get_operator_control_plane,
)
from src.core.services.api_gateway.routes.evolution_control import (
    router as evolution_router,
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
        roles=roles or ["admin"],
        permissions=["admin"],
        exp=now + 3600,
        iat=now,
    )


_ADMIN_USER = _make_user(["admin"])

_SNAPSHOT = {
    "paused": False,
    "stop_requested": False,
    "status": "running",
    "updated_by": None,
    "reason": None,
}

_PAUSED_SNAPSHOT = {
    "paused": True,
    "stop_requested": False,
    "status": "paused",
    "updated_by": "admin-1",
    "reason": "maintenance",
}

_STOPPED_SNAPSHOT = {
    "paused": False,
    "stop_requested": True,
    "status": "stopped",
    "updated_by": "admin-1",
    "reason": "emergency",
}


def _build_app(control_plane=None) -> FastAPI:
    app = FastAPI()
    app.include_router(evolution_router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
    if control_plane is not None:
        app.dependency_overrides[get_operator_control_plane] = lambda: control_plane
        app.state.research_operator_control_plane = control_plane
    return app


@pytest.fixture()
def mock_control_plane() -> AsyncMock:
    cp = AsyncMock()
    cp.snapshot = AsyncMock(return_value=dict(_SNAPSHOT))
    cp.request_pause = AsyncMock(return_value=dict(_PAUSED_SNAPSHOT))
    cp.request_resume = AsyncMock(return_value=dict(_SNAPSHOT))
    cp.request_stop = AsyncMock(return_value=dict(_STOPPED_SNAPSHOT))
    return cp


@pytest.fixture()
def client(mock_control_plane: AsyncMock) -> TestClient:
    return TestClient(_build_app(mock_control_plane))


# ---------------------------------------------------------------------------
# GET /evolution/operator-control (status)
# ---------------------------------------------------------------------------


class TestOperatorControlStatus:
    """GET /evolution/operator-control"""

    def test_status_returns_200(self, client: TestClient):
        resp = client.get("/evolution/operator-control")
        assert resp.status_code == 200
        body = resp.json()
        assert body["paused"] is False
        assert body["status"] == "running"

    def test_status_redis_error_returns_503(self, mock_control_plane: AsyncMock):
        mock_control_plane.snapshot = AsyncMock(side_effect=RedisError("conn refused"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.get("/evolution/operator-control")
        assert resp.status_code == 503

    def test_status_runtime_error_returns_503(self, mock_control_plane: AsyncMock):
        mock_control_plane.snapshot = AsyncMock(side_effect=RuntimeError("oops"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.get("/evolution/operator-control")
        assert resp.status_code == 503

    def test_status_value_error_returns_503(self, mock_control_plane: AsyncMock):
        mock_control_plane.snapshot = AsyncMock(side_effect=ValueError("bad"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.get("/evolution/operator-control")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /evolution/operator-control/pause
# ---------------------------------------------------------------------------


class TestOperatorControlPause:
    """POST /evolution/operator-control/pause"""

    def test_pause_success(self, client: TestClient):
        resp = client.post(
            "/evolution/operator-control/pause",
            json={"reason": "maintenance"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["paused"] is True
        assert body["status"] == "paused"

    def test_pause_no_reason(self, client: TestClient):
        resp = client.post(
            "/evolution/operator-control/pause",
            json={},
        )
        assert resp.status_code == 200

    def test_pause_redis_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_pause = AsyncMock(side_effect=RedisError("fail"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/pause", json={"reason": "test"})
        assert resp.status_code == 503

    def test_pause_runtime_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_pause = AsyncMock(side_effect=RuntimeError("fail"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/pause", json={})
        assert resp.status_code == 503

    def test_pause_value_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_pause = AsyncMock(side_effect=ValueError("bad"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/pause", json={})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /evolution/operator-control/resume
# ---------------------------------------------------------------------------


class TestOperatorControlResume:
    """POST /evolution/operator-control/resume"""

    def test_resume_success(self, client: TestClient):
        resp = client.post(
            "/evolution/operator-control/resume",
            json={"reason": "maintenance done"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["paused"] is False

    def test_resume_no_reason(self, client: TestClient):
        resp = client.post("/evolution/operator-control/resume", json={})
        assert resp.status_code == 200

    def test_resume_redis_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_resume = AsyncMock(side_effect=RedisError("fail"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/resume", json={})
        assert resp.status_code == 503

    def test_resume_runtime_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_resume = AsyncMock(side_effect=RuntimeError("fail"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/resume", json={})
        assert resp.status_code == 503

    def test_resume_value_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_resume = AsyncMock(side_effect=ValueError("bad"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/resume", json={})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /evolution/operator-control/stop
# ---------------------------------------------------------------------------


class TestOperatorControlStop:
    """POST /evolution/operator-control/stop"""

    def test_stop_success(self, client: TestClient):
        resp = client.post(
            "/evolution/operator-control/stop",
            json={"reason": "emergency"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["stop_requested"] is True

    def test_stop_no_reason(self, client: TestClient):
        resp = client.post("/evolution/operator-control/stop", json={})
        assert resp.status_code == 200

    def test_stop_redis_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_stop = AsyncMock(side_effect=RedisError("fail"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/stop", json={})
        assert resp.status_code == 503

    def test_stop_runtime_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_stop = AsyncMock(side_effect=RuntimeError("fail"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/stop", json={})
        assert resp.status_code == 503

    def test_stop_value_error(self, mock_control_plane: AsyncMock):
        mock_control_plane.request_stop = AsyncMock(side_effect=ValueError("bad"))
        cl = TestClient(_build_app(mock_control_plane))
        resp = cl.post("/evolution/operator-control/stop", json={})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Dependency: get_operator_control_plane
# ---------------------------------------------------------------------------


class TestGetOperatorControlPlane:
    """Test the dependency that resolves the control plane from app state."""

    def test_503_when_not_configured(self):
        app = FastAPI()
        app.include_router(evolution_router)
        app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER
        # Do NOT set app.state.research_operator_control_plane
        cl = TestClient(app)
        resp = cl.get("/evolution/operator-control")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]
