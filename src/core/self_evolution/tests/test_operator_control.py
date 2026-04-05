from __future__ import annotations

from datetime import UTC, datetime

import pytest

from enhanced_agent_bus.data_flywheel.models import EvidenceBundle
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository
from src.core.self_evolution.evidence_store import SelfEvolutionEvidenceStore
from src.core.self_evolution.models import ResearchRuntimeState
from src.core.self_evolution.research.operator_control import (
    create_research_operator_control_plane,
)


@pytest.mark.asyncio
async def test_operator_control_plane_pause_resume_stop_and_runtime_heartbeat() -> None:
    plane = create_research_operator_control_plane()

    paused = await plane.request_pause("admin-user", "maintenance")
    assert paused["paused"] is True
    assert paused["mode"] == "pause_requested"
    assert paused["requested_by"] == "admin-user"

    await plane.record_runtime_heartbeat(
        instance_id="runtime-a",
        runtime_state=ResearchRuntimeState.RUNNING,
        run_id="run-1",
        generation_index=3,
        pid=1234,
    )
    status = await plane.snapshot()
    assert status["runtime_instance_id"] == "runtime-a"
    assert status["runtime_state"] == "running"
    assert status["runtime_online"] is True

    resumed = await plane.request_resume("admin-user", "done")
    assert resumed["paused"] is False
    assert resumed["mode"] == "running"

    stopped = await plane.request_stop("ops-user", "incident")
    assert stopped["stop_requested"] is True
    assert stopped["mode"] == "stop_requested"
    assert stopped["requested_by"] == "ops-user"


@pytest.mark.asyncio
async def test_self_evolution_evidence_store_scopes_to_tenant() -> None:
    repository = InMemoryWorkflowRepository()
    store = SelfEvolutionEvidenceStore(repository)
    record = EvidenceBundle(
        evidence_id="evidence-001",
        tenant_id="tenant-a",
        workload_key="tenant-a/api/tool/policy/608508a9bd224290",
        candidate_id="candidate-001",
        dataset_snapshot_id="snapshot-001",
        constitutional_hash="608508a9bd224290",
        approval_state="pending_review",
        validator_records=[{"validator": "validator-1"}],
        rollback_plan={"action": "rollback"},
        artifact_manifest_uri="file:///tmp/evidence-001.json",
        created_at=datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC),
    )

    await repository.save_evidence_bundle(record)

    records = await store.list_records(tenant_id="tenant-a")
    assert len(records) == 1
    assert records[0].evidence_id == "evidence-001"

    fetched = await store.get("evidence-001", tenant_id="tenant-a")
    assert fetched is not None
    assert fetched.candidate_id == "candidate-001"

    denied = await store.get("evidence-001", tenant_id="tenant-b")
    assert denied is None
