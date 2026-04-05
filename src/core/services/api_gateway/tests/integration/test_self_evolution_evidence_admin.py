"""Integration tests for admin-mounted self-evolution evidence routes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

_evidence_api = pytest.importorskip("src.core.self_evolution.api.evidence")
_self_evolution_store = pytest.importorskip("src.core.self_evolution.evidence_store")

SelfEvolutionEvidenceStore = _self_evolution_store.SelfEvolutionEvidenceStore

from enhanced_agent_bus.data_flywheel.models import EvidenceBundle
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository
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


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seeded_evidence(client: TestClient) -> EvidenceBundle:
    repository = InMemoryWorkflowRepository()
    client.app.state.self_evolution_evidence_store = SelfEvolutionEvidenceStore(repository)
    record = EvidenceBundle(
        evidence_id="evidence-001",
        tenant_id="tenant-admin",
        workload_key="tenant-admin/api/tool/policy/608508a9bd224290",
        candidate_id="candidate-001",
        dataset_snapshot_id="snapshot-001",
        constitutional_hash="608508a9bd224290",
        approval_state="pending_review",
        validator_records=[{"validator": "validator-1"}],
        rollback_plan={"action": "rollback"},
        artifact_manifest_uri="file:///tmp/evidence-001.json",
        created_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
    )
    import asyncio

    asyncio.run(repository.save_evidence_bundle(record))
    return record


class TestGatewayAdminEvidenceMount:
    def test_admin_evidence_routes_are_mounted(self) -> None:
        paths = {route.path for route in app.routes}
        assert "/api/v1/admin/evolution/bounded-experiments" in paths
        assert "/api/v1/admin/evolution/bounded-experiments/{evidence_id}" in paths

    def test_admin_can_query_bounded_experiment_evidence(
        self,
        client: TestClient,
        seeded_evidence: EvidenceBundle,
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
        seeded_evidence: EvidenceBundle,
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: _claims(roles=["user"])

        response = client.get("/api/v1/admin/evolution/bounded-experiments")

        assert response.status_code == 403

    def test_admin_cannot_read_evidence_from_another_tenant(
        self,
        client: TestClient,
        seeded_evidence: EvidenceBundle,
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: UserClaims(
            sub="other-admin",
            tenant_id="tenant-other",
            roles=["admin"],
            permissions=[],
            exp=4_102_444_800,
            iat=1_700_000_000,
        )

        response = client.get(f"/api/v1/admin/evolution/bounded-experiments/{seeded_evidence.evidence_id}")

        assert response.status_code == 404
