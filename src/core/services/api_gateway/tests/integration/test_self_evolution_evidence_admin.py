"""Integration tests for admin-mounted self-evolution evidence routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

_evidence_api = pytest.importorskip("src.core.self_evolution.api.evidence")
_evidence_store = pytest.importorskip(
    "src.core.self_evolution.research.experiment_evidence_store"
)

set_evidence_store_path = _evidence_api.set_evidence_store_path
DEFAULT_BOUNDED_EXPERIMENT_EVIDENCE_PATH = _evidence_store.DEFAULT_BOUNDED_EXPERIMENT_EVIDENCE_PATH
BoundedExperimentEvidenceRecord = _evidence_store.BoundedExperimentEvidenceRecord
BoundedExperimentEvidenceStore = _evidence_store.BoundedExperimentEvidenceStore

from src.core.services.api_gateway.main import app
from src.core.shared.security.auth import UserClaims, get_current_user

pytestmark = [pytest.mark.integration]


def _claims(*, roles: list[str]) -> UserClaims:
    return UserClaims(
        sub="gateway-admin-user",
        tenant_id="tenant-admin",
        roles=roles,
        permissions=[],
        exp=4_102_444_800,
        iat=1_700_000_000,
    )


@pytest.fixture(autouse=True)
def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    set_evidence_store_path(DEFAULT_BOUNDED_EXPERIMENT_EVIDENCE_PATH)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def seeded_evidence(tmp_path: Path) -> BoundedExperimentEvidenceRecord:
    path = tmp_path / "gateway-evidence"
    set_evidence_store_path(path)
    record = BoundedExperimentEvidenceRecord(
        experiment_id=uuid4(),
        hypothesis_id=uuid4(),
        cycle_id=uuid4(),
        proposal_id=uuid4(),
        metric_name="p99_latency_ms",
        baseline=1.0,
        observed=0.9,
        delta_percent=10.0,
        kept=True,
        reason="improved",
        lower_is_better=True,
        recorded_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
    )
    store = BoundedExperimentEvidenceStore(path=path)
    import asyncio

    asyncio.run(store.append(record))
    return record


class TestGatewayAdminEvidenceMount:
    def test_admin_evidence_routes_are_mounted(self) -> None:
        paths = {route.path for route in app.routes}
        assert "/api/v1/admin/evolution/bounded-experiments" in paths
        assert "/api/v1/admin/evolution/bounded-experiments/{evidence_id}" in paths

    def test_admin_can_query_bounded_experiment_evidence(
        self,
        client: TestClient,
        seeded_evidence: BoundedExperimentEvidenceRecord,
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(roles=["admin"])

        response = client.get("/api/v1/admin/evolution/bounded-experiments")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["records"][0]["evidence_id"] == str(seeded_evidence.evidence_id)

    def test_non_admin_is_rejected(
        self,
        client: TestClient,
        seeded_evidence: BoundedExperimentEvidenceRecord,
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(roles=["user"])

        response = client.get("/api/v1/admin/evolution/bounded-experiments")

        assert response.status_code == 403
