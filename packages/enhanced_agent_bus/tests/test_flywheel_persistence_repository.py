from __future__ import annotations

import sys
import types
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

if "asyncpg" not in sys.modules:
    _asyncpg_stub = types.ModuleType("asyncpg")

    class _PostgresError(Exception):
        pass

    _asyncpg_stub.PostgresError = _PostgresError  # type: ignore[attr-defined]
    _asyncpg_stub.Record = dict  # type: ignore[attr-defined]
    _asyncpg_stub.Pool = MagicMock  # type: ignore[attr-defined]
    _asyncpg_stub.Connection = MagicMock  # type: ignore[attr-defined]
    sys.modules["asyncpg"] = _asyncpg_stub
else:
    _PostgresError = sys.modules["asyncpg"].PostgresError  # type: ignore[attr-defined]

from enhanced_agent_bus.data_flywheel.models import (
    CandidateArtifact,
    DatasetSnapshot,
    DecisionEvent,
    EvaluationMode,
    EvaluationRun,
    EvidenceBundle,
)
from enhanced_agent_bus.persistence.postgres_repository import PostgresWorkflowRepository
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository

NOW = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)


def make_decision_event(**kwargs: Any) -> DecisionEvent:
    defaults: dict[str, Any] = {
        "decision_id": "decision-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "constitutional_hash": "608508a9bd224290",
        "decision_kind": "policy",
        "outcome": "approved",
        "request_context": {"request_id": "req-1"},
        "decision_payload": {"score": 0.92},
        "created_at": NOW,
    }
    defaults.update(kwargs)
    return DecisionEvent(**defaults)


def make_dataset_snapshot(**kwargs: Any) -> DatasetSnapshot:
    defaults: dict[str, Any] = {
        "snapshot_id": "snapshot-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "constitutional_hash": "608508a9bd224290",
        "record_count": 12,
        "redaction_status": "redacted",
        "artifact_manifest_uri": "s3://flywheel/snapshots/snapshot-001.json",
        "window_started_at": NOW.replace(hour=11),
        "window_ended_at": NOW.replace(hour=13),
        "source_counts": {"decision_events": 8, "feedback_events": 4},
        "created_at": NOW,
    }
    defaults.update(kwargs)
    return DatasetSnapshot(**defaults)


def make_candidate(**kwargs: Any) -> CandidateArtifact:
    defaults: dict[str, Any] = {
        "candidate_id": "candidate-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "constitutional_hash": "608508a9bd224290",
        "candidate_type": "thresholds",
        "candidate_spec": {"max_risk": 0.25},
        "status": "draft",
        "created_at": NOW,
    }
    defaults.update(kwargs)
    return CandidateArtifact(**defaults)


def make_evaluation_run(**kwargs: Any) -> EvaluationRun:
    defaults: dict[str, Any] = {
        "run_id": "run-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "candidate_id": "candidate-001",
        "constitutional_hash": "608508a9bd224290",
        "evaluation_mode": EvaluationMode.OFFLINE_REPLAY,
        "status": "completed",
        "summary_metrics": {"pass_rate": 0.95},
        "started_at": NOW,
        "ended_at": NOW,
        "created_at": NOW,
    }
    defaults.update(kwargs)
    return EvaluationRun(**defaults)


def make_evidence_bundle(**kwargs: Any) -> EvidenceBundle:
    defaults: dict[str, Any] = {
        "evidence_id": "evidence-001",
        "tenant_id": "tenant-a",
        "workload_key": "tenant-a/api/tool/policy/608508a9bd224290",
        "candidate_id": "candidate-001",
        "dataset_snapshot_id": "snapshot-001",
        "constitutional_hash": "608508a9bd224290",
        "approval_state": "pending_review",
        "validator_records": [{"validator": "agent-validator"}],
        "rollback_plan": {"action": "restore-thresholds"},
        "artifact_manifest_uri": "s3://flywheel/evidence/evidence-001.json",
        "created_at": NOW,
    }
    defaults.update(kwargs)
    return EvidenceBundle(**defaults)


class TestInMemoryFlywheelPersistence:
    async def test_round_trips_all_flywheel_metadata_records(self) -> None:
        repo = InMemoryWorkflowRepository()
        decision = make_decision_event()
        snapshot = make_dataset_snapshot()
        candidate = make_candidate()
        run = make_evaluation_run()
        evidence = make_evidence_bundle()

        await repo.save_decision_event(decision)
        await repo.save_dataset_snapshot(snapshot)
        await repo.save_candidate_artifact(candidate)
        await repo.save_evaluation_run(run)
        await repo.save_evidence_bundle(evidence)

        assert await repo.list_decision_events("tenant-a", decision.workload_key) == [decision]
        assert await repo.get_dataset_snapshot(snapshot.snapshot_id) == snapshot
        assert await repo.get_candidate_artifact(candidate.candidate_id) == candidate
        assert await repo.get_evaluation_run(run.run_id) == run
        assert await repo.get_evidence_bundle(evidence.evidence_id) == evidence

    async def test_list_evidence_bundles_filters_by_tenant_and_workload(self) -> None:
        repo = InMemoryWorkflowRepository()
        keep = make_evidence_bundle()
        other_workload = make_evidence_bundle(
            evidence_id="evidence-002",
            workload_key="tenant-a/api/tool/review/608508a9bd224290",
        )
        other_tenant = make_evidence_bundle(
            evidence_id="evidence-003",
            tenant_id="tenant-b",
            workload_key="tenant-b/api/tool/policy/608508a9bd224290",
        )

        await repo.save_evidence_bundle(keep)
        await repo.save_evidence_bundle(other_workload)
        await repo.save_evidence_bundle(other_tenant)

        assert await repo.list_evidence_bundles("tenant-a", keep.workload_key) == [keep]

    async def test_list_candidate_artifacts_returns_newest_first(self) -> None:
        repo = InMemoryWorkflowRepository()
        older = make_candidate(candidate_id="candidate-old", created_at=NOW.replace(hour=11))
        newer = make_candidate(candidate_id="candidate-new", created_at=NOW.replace(hour=13))

        await repo.save_candidate_artifact(older)
        await repo.save_candidate_artifact(newer)

        results = await repo.list_candidate_artifacts("tenant-a", older.workload_key)
        assert [item.candidate_id for item in results] == ["candidate-new", "candidate-old"]


def _make_conn(fetchrow_return: Any = None, fetch_return: Any = None) -> tuple[Any, AsyncMock]:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return if fetch_return is not None else [])
    conn.execute = AsyncMock(return_value="OK")
    return conn, conn


def _make_repo(conn: AsyncMock) -> PostgresWorkflowRepository:
    repo = PostgresWorkflowRepository.__new__(PostgresWorkflowRepository)
    repo._pool = object()

    @asynccontextmanager
    async def _connection():
        yield conn

    repo._connection = _connection  # type: ignore[method-assign]
    return repo


def _decision_row(event: DecisionEvent) -> dict[str, Any]:
    return {
        "decision_id": event.decision_id,
        "tenant_id": event.tenant_id,
        "workload_key": event.workload_key,
        "constitutional_hash": event.constitutional_hash,
        "from_agent": event.from_agent,
        "validated_by_agent": event.validated_by_agent,
        "decision_kind": event.decision_kind,
        "request_context": event.request_context,
        "decision_payload": event.decision_payload,
        "latency_ms": event.latency_ms,
        "outcome": event.outcome,
        "created_at": event.created_at,
    }


def _dataset_row(snapshot: DatasetSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "tenant_id": snapshot.tenant_id,
        "workload_key": snapshot.workload_key,
        "constitutional_hash": snapshot.constitutional_hash,
        "record_count": snapshot.record_count,
        "redaction_status": snapshot.redaction_status,
        "artifact_manifest_uri": snapshot.artifact_manifest_uri,
        "window_started_at": snapshot.window_started_at,
        "window_ended_at": snapshot.window_ended_at,
        "source_counts": snapshot.source_counts,
        "created_at": snapshot.created_at,
    }


def _candidate_row(candidate: CandidateArtifact) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "tenant_id": candidate.tenant_id,
        "workload_key": candidate.workload_key,
        "constitutional_hash": candidate.constitutional_hash,
        "candidate_type": candidate.candidate_type,
        "candidate_spec": candidate.candidate_spec,
        "parent_version": candidate.parent_version,
        "status": candidate.status,
        "created_at": candidate.created_at,
    }


def _evaluation_row(run: EvaluationRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "tenant_id": run.tenant_id,
        "workload_key": run.workload_key,
        "candidate_id": run.candidate_id,
        "constitutional_hash": run.constitutional_hash,
        "evaluation_mode": run.evaluation_mode.value,
        "status": run.status,
        "summary_metrics": run.summary_metrics,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "created_at": run.created_at,
    }


def _evidence_row(evidence: EvidenceBundle) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "tenant_id": evidence.tenant_id,
        "workload_key": evidence.workload_key,
        "candidate_id": evidence.candidate_id,
        "dataset_snapshot_id": evidence.dataset_snapshot_id,
        "constitutional_hash": evidence.constitutional_hash,
        "approval_state": evidence.approval_state,
        "validator_records": evidence.validator_records,
        "rollback_plan": evidence.rollback_plan,
        "artifact_manifest_uri": evidence.artifact_manifest_uri,
        "created_at": evidence.created_at,
    }


class TestPostgresFlywheelPersistence:
    async def test_save_dataset_snapshot_executes_insert(self) -> None:
        snapshot = make_dataset_snapshot()
        conn, _ = _make_conn()
        repo = _make_repo(conn)

        await repo.save_dataset_snapshot(snapshot)

        conn.execute.assert_awaited_once()
        args = conn.execute.call_args.args
        assert "INSERT INTO flywheel_dataset_snapshots" in args[0]
        assert snapshot.snapshot_id in args
        assert snapshot.artifact_manifest_uri in args

    async def test_list_decision_events_returns_models(self) -> None:
        event = make_decision_event()
        conn, _ = _make_conn(fetch_return=[_decision_row(event)])
        repo = _make_repo(conn)

        result = await repo.list_decision_events(event.tenant_id, event.workload_key)

        assert result == [event]
        args = conn.fetch.call_args.args
        assert "SELECT * FROM flywheel_decision_events" in args[0]
        assert event.tenant_id in args
        assert event.workload_key in args

    async def test_get_candidate_artifact_returns_none_when_missing(self) -> None:
        conn, _ = _make_conn(fetchrow_return=None)
        repo = _make_repo(conn)

        result = await repo.get_candidate_artifact("missing")

        assert result is None

    async def test_get_candidate_artifact_returns_model(self) -> None:
        candidate = make_candidate()
        conn, _ = _make_conn(fetchrow_return=_candidate_row(candidate))
        repo = _make_repo(conn)

        result = await repo.get_candidate_artifact(candidate.candidate_id)

        assert result == candidate

    async def test_get_dataset_snapshot_returns_model(self) -> None:
        snapshot = make_dataset_snapshot()
        conn, _ = _make_conn(fetchrow_return=_dataset_row(snapshot))
        repo = _make_repo(conn)

        result = await repo.get_dataset_snapshot(snapshot.snapshot_id)

        assert result == snapshot

    async def test_get_evaluation_run_returns_model(self) -> None:
        run = make_evaluation_run()
        conn, _ = _make_conn(fetchrow_return=_evaluation_row(run))
        repo = _make_repo(conn)

        result = await repo.get_evaluation_run(run.run_id)

        assert result == run

    async def test_list_evidence_bundles_returns_models(self) -> None:
        evidence = make_evidence_bundle()
        conn, _ = _make_conn(fetch_return=[_evidence_row(evidence)])
        repo = _make_repo(conn)

        result = await repo.list_evidence_bundles(evidence.tenant_id, evidence.workload_key)

        assert result == [evidence]

    async def test_save_evidence_bundle_serializes_json_payloads(self) -> None:
        evidence = make_evidence_bundle()
        conn, _ = _make_conn()
        repo = _make_repo(conn)

        await repo.save_evidence_bundle(evidence)

        args = conn.execute.call_args.args
        assert "INSERT INTO flywheel_evidence_bundles" in args[0]
        assert evidence.evidence_id in args
        assert any(isinstance(arg, str) and "restore-thresholds" in arg for arg in args[1:])

    async def test_list_evaluation_runs_wraps_postgres_errors(self) -> None:
        conn, _ = _make_conn()
        conn.fetch = AsyncMock(side_effect=_PostgresError("db down"))
        repo = _make_repo(conn)

        with pytest.raises(Exception, match="Failed to list flywheel evaluation runs"):
            await repo.list_evaluation_runs("tenant-a")
