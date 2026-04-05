"""Integration tests for admin-mounted self-evolution operator-control routes."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from enhanced_agent_bus.data_flywheel.models import DatasetSnapshot

_operator_control = pytest.importorskip("src.core.self_evolution.research.operator_control")

ResearchRuntimeState = _operator_control.ResearchRuntimeState
create_research_operator_control_plane = _operator_control.create_research_operator_control_plane
from src.core.services.api_gateway.main import app
from src.core.services.api_gateway.routes.evolution_control import get_run_orchestrator
from src.core.shared.security.auth import UserClaims, get_current_user

pytestmark = [pytest.mark.integration]


def _claims(*, roles: list[str], sub: str = "gateway-admin-user") -> UserClaims:
    return UserClaims(
        sub=sub,
        tenant_id="tenant-admin",
        roles=roles,
        permissions=[],
        exp=4_102_444_800,
        iat=1_700_000_000,
    )


@pytest.fixture(autouse=True)
def _cleanup_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    mock_saga = AsyncMock()
    mock_saga.aclose = AsyncMock()
    with patch(
        "src.core.services.api_gateway.lifespan.create_saga_repository",
        AsyncMock(return_value=mock_saga),
    ):
        with TestClient(app) as client:
            client.app.state.research_operator_control_plane = (
                create_research_operator_control_plane()
            )
            yield client
            asyncio.run(client.app.state.research_operator_control_plane.aclose())


class TestGatewayAdminOperatorControlMount:
    def test_admin_operator_control_routes_are_mounted(self) -> None:
        paths = {route.path for route in app.routes}
        assert "/api/v1/admin/evolution/operator-control" in paths
        assert "/api/v1/admin/evolution/operator-control/pause" in paths
        assert "/api/v1/admin/evolution/operator-control/resume" in paths
        assert "/api/v1/admin/evolution/operator-control/stop" in paths
        assert "/api/v1/admin/evolution/operator-control/dataset-build" in paths

    def test_admin_can_pause_and_resume_operator_control(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(roles=["admin"])

        pause_response = client.post(
            "/api/v1/admin/evolution/operator-control/pause",
            json={"reason": "maintenance window"},
        )

        assert pause_response.status_code == 200
        paused = pause_response.json()
        assert paused["mode"] == "pause_requested"
        assert paused["requested_by"] == "gateway-admin-user"
        assert paused["reason"] == "maintenance window"

        status_response = client.get("/api/v1/admin/evolution/operator-control")
        assert status_response.status_code == 200
        assert status_response.json()["mode"] == "pause_requested"

        resume_response = client.post(
            "/api/v1/admin/evolution/operator-control/resume",
            json={"reason": "clear maintenance"},
        )

        assert resume_response.status_code == 200
        resumed = resume_response.json()
        assert resumed["mode"] == "running"
        assert resumed["requested_by"] == "gateway-admin-user"
        assert resumed["reason"] == "clear maintenance"

    def test_admin_status_includes_runtime_liveness_metadata(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(roles=["admin"])

        asyncio.run(
            client.app.state.research_operator_control_plane.record_runtime_heartbeat(
                instance_id="runtime-a",
                runtime_state=ResearchRuntimeState.RUNNING,
                run_id="evo-runtime-20260312",
                generation_index=4,
                pid=4321,
            )
        )

        response = client.get("/api/v1/admin/evolution/operator-control")

        assert response.status_code == 200
        data = response.json()
        assert data["runtime_instance_id"] == "runtime-a"
        assert data["runtime_state"] == "running"
        assert data["runtime_last_run_id"] == "evo-runtime-20260312"
        assert data["runtime_generation_index"] == 4
        assert data["runtime_pid"] == 4321
        assert data["runtime_online"] is True

    def test_admin_can_stop_operator_control(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(
            roles=["admin"],
            sub="ops-admin",
        )

        response = client.post(
            "/api/v1/admin/evolution/operator-control/stop",
            json={"reason": "incident containment"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "stop_requested"
        assert data["requested_by"] == "ops-admin"
        assert data["reason"] == "incident containment"

    def test_admin_can_start_dataset_build(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(roles=["admin"])
        mock_orchestrator = AsyncMock()
        mock_orchestrator.run_dataset_build_step = AsyncMock(
            return_value=DatasetSnapshot(
                snapshot_id="snapshot-002",
                tenant_id="tenant-admin",
                workload_key="tenant-admin/enhanced_agent_bus/message_processor/policy/608508a9bd224290",
                constitutional_hash="608508a9bd224290",
                record_count=5,
                redaction_status="redacted",
                artifact_manifest_uri="file:///tmp/snapshot-002/manifest.json",
                created_at=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
            )
        )
        app.dependency_overrides[get_run_orchestrator] = lambda: mock_orchestrator

        response = client.post(
            "/api/v1/admin/evolution/operator-control/dataset-build",
            json={"run_id": "run-123", "limit": 250, "reason": "live traffic replay"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "run-123"
        assert data["requested_by"] == "gateway-admin-user"
        assert data["snapshot"]["snapshot_id"] == "snapshot-002"
        mock_orchestrator.run_dataset_build_step.assert_awaited_once_with("run-123", limit=250)

    def test_non_admin_is_rejected(self, client: TestClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(roles=["user"])

        response = client.post(
            "/api/v1/admin/evolution/operator-control/pause",
            json={"reason": "unauthorized"},
        )

        assert response.status_code == 403
