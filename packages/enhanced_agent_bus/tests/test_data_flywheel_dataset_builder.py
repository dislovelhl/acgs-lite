from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest

from enhanced_agent_bus.data_flywheel.dataset_builder import (
    CrossTenantDatasetError,
    DatasetSnapshotBuilder,
    InMemoryFeedbackEventSource,
    UnredactedDatasetError,
)
from enhanced_agent_bus.data_flywheel.models import DecisionEvent, FeedbackEvent
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository

NOW = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)


def make_decision_event(**kwargs: object) -> DecisionEvent:
    defaults: dict[str, object] = {
        "decision_id": "decision-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "constitutional_hash": "608508a9bd224290",
        "decision_kind": "policy",
        "request_context": {"request_id": "req-1", "email": "alice@example.com"},
        "decision_payload": {"score": 0.92, "ip_address": "192.168.1.10"},
        "outcome": "approved",
        "created_at": NOW,
    }
    defaults.update(kwargs)
    return DecisionEvent(**defaults)


def make_feedback_event(**kwargs: object) -> FeedbackEvent:
    defaults: dict[str, object] = {
        "feedback_id": "feedback-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "constitutional_hash": "608508a9bd224290",
        "feedback_type": "general",
        "outcome_status": "submitted",
        "comment": "Reach alice@example.com from 192.168.1.10",
        "metadata": {"authenticated_user_id": "user-123", "page": "/governance"},
        "created_at": NOW.replace(minute=5),
    }
    defaults.update(kwargs)
    return FeedbackEvent(**defaults)


@pytest.mark.asyncio
async def test_dataset_builder_persists_redacted_snapshot_with_time_window(tmp_path: Path) -> None:
    repository = InMemoryWorkflowRepository()
    decision = make_decision_event()
    await repository.save_decision_event(decision)
    feedback = make_feedback_event()
    builder = DatasetSnapshotBuilder(
        repository,
        InMemoryFeedbackEventSource([feedback]),
        artifact_root=tmp_path,
    )

    snapshot = await builder.build_snapshot(
        tenant_id="tenant-a",
        workload_key=decision.workload_key,
    )

    assert snapshot.record_count == 2
    assert snapshot.redaction_status == "redacted"
    assert snapshot.window_started_at == decision.created_at
    assert snapshot.window_ended_at == feedback.created_at
    assert snapshot.source_counts == {"decision_events": 1, "feedback_events": 1}
    assert await repository.get_dataset_snapshot(snapshot.snapshot_id) == snapshot

    manifest_path = Path(urlparse(snapshot.artifact_manifest_uri).path)
    dataset_path = manifest_path.with_name("records.jsonl")
    assert manifest_path.exists()
    assert dataset_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_counts"] == {"decision_events": 1, "feedback_events": 1}
    assert manifest["window_started_at"] == decision.created_at.isoformat()
    assert manifest["window_ended_at"] == feedback.created_at.isoformat()

    exported = dataset_path.read_text(encoding="utf-8")
    assert "alice@example.com" not in exported
    assert "192.168.1.10" not in exported
    assert "[REDACTED]" in exported


@pytest.mark.asyncio
async def test_dataset_builder_blocks_cross_tenant_joins(tmp_path: Path) -> None:
    repository = InMemoryWorkflowRepository()
    decision = make_decision_event()
    feedback = make_feedback_event(
        tenant_id="tenant-b",
        workload_key="tenant-b/api/tool/policy/608508a9bd224290",
    )
    builder = DatasetSnapshotBuilder(
        repository,
        InMemoryFeedbackEventSource([]),
        artifact_root=tmp_path,
    )

    with pytest.raises(CrossTenantDatasetError):
        await builder.build_snapshot(
            tenant_id="tenant-a",
            workload_key=decision.workload_key,
            decision_events=[decision],
            feedback_events=[feedback],
        )


@pytest.mark.asyncio
async def test_dataset_builder_rejects_unredacted_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryWorkflowRepository()
    decision = make_decision_event()
    builder = DatasetSnapshotBuilder(
        repository,
        InMemoryFeedbackEventSource([]),
        artifact_root=tmp_path,
    )

    monkeypatch.setattr(
        "enhanced_agent_bus.data_flywheel.dataset_builder.redact_for_dataset_export",
        lambda value: value,
    )

    with pytest.raises(UnredactedDatasetError):
        await builder.build_snapshot(
            tenant_id="tenant-a",
            workload_key=decision.workload_key,
            decision_events=[decision],
            feedback_events=[],
        )
