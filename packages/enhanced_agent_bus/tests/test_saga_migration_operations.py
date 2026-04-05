# Constitutional Hash: 608508a9bd224290
"""
Tests for saga_migration_integration operations: start_migration (success & failure),
get_migration_status, cancel_migration, and get_metrics.

Split from test_saga_migration_integration_coverage.py (Group C).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from enterprise_sso.migration_job_api import (
    MigrationJobConfig,
    MigrationJobManager,
    MigrationJobResult,
    MigrationJobStatus,
    MigrationJobType,
)
from enterprise_sso.saga_migration_integration import (
    CONSTITUTIONAL_HASH,
    CheckpointStore,
    MigrationCheckpoint,
    MigrationPhase,
    SagaMigrationConfig,
    SagaMigrationResult,
    SagaMigrationService,
)
from enterprise_sso.saga_orchestration import (
    Saga,
    SagaContext,
    SagaExecutionResult,
    SagaOrchestrator,
    SagaStatus,
    SagaStepExecution,
    SagaStepResult,
    SagaStepStatus,
    SagaStore,
)

# ---------------------------------------------------------------------------
# Helpers -- in-memory SagaStore that avoids all Redis calls
# ---------------------------------------------------------------------------


class InMemorySagaStore(SagaStore):
    """SagaStore backed by a plain dict instead of Redis."""

    def __init__(self):
        # Do NOT call super().__init__() -- it sets up Redis.
        self._sagas: dict[str, Saga] = {}
        self._tenant_index: dict[str, set[str]] = {}

    async def save(self, saga: Saga) -> None:
        self._sagas[saga.saga_id] = saga
        self._tenant_index.setdefault(saga.tenant_id, set()).add(saga.saga_id)

    async def get(self, saga_id: str) -> Saga | None:
        return self._sagas.get(saga_id)

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: SagaStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Saga]:
        ids = list(self._tenant_index.get(tenant_id, set()))
        sagas = [self._sagas[sid] for sid in ids if sid in self._sagas]
        if status is not None:
            sagas = [s for s in sagas if s.status == status]
        return sagas[offset : offset + limit]

    async def delete(self, saga_id: str) -> bool:
        saga = self._sagas.pop(saga_id, None)
        if saga is None:
            return False
        ids = self._tenant_index.get(saga.tenant_id, set())
        ids.discard(saga_id)
        return True


def make_service() -> SagaMigrationService:
    """Create SagaMigrationService wired with in-memory store."""
    store = InMemorySagaStore()
    orchestrator = SagaOrchestrator(store=store)
    return SagaMigrationService(orchestrator=orchestrator)


# ---------------------------------------------------------------------------
# start_migration -- success paths (in-memory, no Redis)
# ---------------------------------------------------------------------------


class TestStartMigrationSuccess:
    async def test_policy_import(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"policies": ["p1", "p2"]},
        )
        result = await svc.start_migration(cfg)

        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED
        assert result.saga_status == SagaStatus.COMPLETED
        assert result.migration_id != ""
        assert result.saga_id != ""
        assert len(result.phases_completed) > 0
        assert result.phases_compensated == []
        assert result.execution_time_ms >= 0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_data_migration(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
            options={"total_records": 500, "batch_size": 50},
        )
        result = await svc.start_migration(cfg)
        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED

    async def test_schema_migration(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
            source_tenant_id="tenant-1",
            options={"target_version": "v2.0.0"},
        )
        result = await svc.start_migration(cfg)
        assert result.success is True

    async def test_full_migration_with_all_options(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="src-tenant",
            target_tenant_id="tgt-tenant",
            options={"total_records": 1000, "policies": ["pol-1"]},
        )
        result = await svc.start_migration(cfg)
        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED

    async def test_gap_remediation(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.GAP_REMEDIATION,
            source_tenant_id="tenant-gap",
            options={"policies": ["pol-x"]},
        )
        result = await svc.start_migration(cfg)
        assert result.success is True

    async def test_backup_disabled(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            enable_backup=False,
        )
        result = await svc.start_migration(cfg)
        assert result.success is True

    async def test_verification_disabled(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            enable_verification=False,
        )
        result = await svc.start_migration(cfg)
        assert result.success is True

    async def test_both_disabled(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            enable_backup=False,
            enable_verification=False,
        )
        result = await svc.start_migration(cfg)
        assert result.success is True

    async def test_creates_checkpoints(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"policies": ["p1"]},
        )
        result = await svc.start_migration(cfg)
        assert len(result.checkpoints) > 0
        for cp in result.checkpoints:
            assert cp.migration_id == result.migration_id

    async def test_job_result_on_success(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"total_records": 7},
        )
        result = await svc.start_migration(cfg)
        assert result.job_result is not None
        assert result.job_result.status == MigrationJobStatus.COMPLETED

    async def test_job_result_summary_includes_record_count(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"total_records": 13},
        )
        result = await svc.start_migration(cfg)
        assert result.job_result is not None
        assert result.job_result.summary["items_processed"] == 13

    async def test_zero_records(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
            options={"total_records": 0},
        )
        result = await svc.start_migration(cfg)
        assert result.success is True

    async def test_no_target_tenant_uses_source(self):
        """When target_tenant_id is None, source is used for job target config."""
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="only-tenant",
        )
        result = await svc.start_migration(cfg)
        assert result.success is True

    async def test_metrics_incremented(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        await svc.start_migration(cfg)
        metrics = svc.get_metrics()
        assert metrics["total_sagas"] == 1
        assert metrics["successful_sagas"] == 1

    async def test_multiple_migrations_accumulate_metrics(self):
        svc = make_service()
        for i in range(3):
            cfg = SagaMigrationConfig(
                migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
                source_tenant_id=f"tenant-{i}",
            )
            await svc.start_migration(cfg)
        metrics = svc.get_metrics()
        assert metrics["total_sagas"] == 3

    async def test_full_migration_creates_backup_checkpoint(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="tenant-1",
            options={"policies": ["p1"], "total_records": 10},
        )
        result = await svc.start_migration(cfg)
        phases = {cp.phase for cp in result.checkpoints}
        assert MigrationPhase.BACKUP in phases


# ---------------------------------------------------------------------------
# start_migration -- failure path via mocked saga
# ---------------------------------------------------------------------------


class TestStartMigrationFailure:
    async def test_failed_saga_marks_job_failed(self):
        """When the saga fails, the job should be FAILED and job_result is None."""
        svc = make_service()

        # Make saga execution return a failure
        mock_result = SagaExecutionResult(
            saga_id="fake-saga",
            success=False,
            status=SagaStatus.COMPENSATED,
            completed_steps=["validate_policies"],
            compensated_steps=["validate_policies"],
            error="Deliberate test failure",
        )

        # We need a real saga to be created first, then patch execute
        real_create = svc.orchestrator.create_saga
        created_saga_holder: dict = {}

        async def capturing_create(*args, **kwargs):
            saga = await real_create(*args, **kwargs)
            created_saga_holder["saga"] = saga
            return saga

        svc.orchestrator.create_saga = capturing_create
        svc.orchestrator.execute = AsyncMock(return_value=mock_result)

        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        result = await svc.start_migration(cfg)

        assert result.success is False
        assert result.status == MigrationJobStatus.FAILED
        assert result.job_result is None
        assert result.error == "Deliberate test failure"

    async def test_failed_saga_no_error_message(self):
        """saga.error is None -- fallback message 'Saga failed' is used."""
        svc = make_service()

        mock_result = SagaExecutionResult(
            saga_id="fake-saga",
            success=False,
            status=SagaStatus.FAILED,
            completed_steps=[],
            error=None,
        )
        svc.orchestrator.execute = AsyncMock(return_value=mock_result)
        svc.orchestrator.create_saga = AsyncMock(return_value=MagicMock(saga_id="fake-saga"))
        # We also need create_job to return a real MigrationJob
        from enterprise_sso.migration_job_api import MigrationJob
        from enterprise_sso.migration_job_api import MigrationJobConfig as MJC

        fake_job = MigrationJob(
            job_id="fake-job",
            tenant_id="tenant-1",
            config=MJC(job_type=MigrationJobType.POLICY_IMPORT),
        )
        svc.job_manager.create_job = AsyncMock(return_value=fake_job)
        svc.job_manager.start_job = AsyncMock(return_value=fake_job)
        svc.job_manager.fail_job = AsyncMock(return_value=fake_job)
        svc.job_manager.get_job = AsyncMock(return_value=fake_job)

        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        result = await svc.start_migration(cfg)
        assert result.success is False
        # fail_job should have been called with "Saga failed"
        svc.job_manager.fail_job.assert_called_once()
        call_args = svc.job_manager.fail_job.call_args[0]
        assert call_args[1] == "Saga failed"

    async def test_updated_job_none_falls_back_to_failed_status(self):
        """When get_job returns None after completion, status defaults to FAILED."""
        svc = make_service()

        mock_result = SagaExecutionResult(
            saga_id="fake-saga",
            success=True,
            status=SagaStatus.COMPLETED,
            completed_steps=["validate_policies"],
        )
        svc.orchestrator.execute = AsyncMock(return_value=mock_result)

        from enterprise_sso.migration_job_api import MigrationJob
        from enterprise_sso.migration_job_api import MigrationJobConfig as MJC

        fake_job = MigrationJob(
            job_id="fake-job",
            tenant_id="tenant-1",
            config=MJC(job_type=MigrationJobType.POLICY_IMPORT),
        )
        svc.orchestrator.create_saga = AsyncMock(return_value=MagicMock(saga_id="fake-saga"))
        svc.job_manager.create_job = AsyncMock(return_value=fake_job)
        svc.job_manager.start_job = AsyncMock(return_value=fake_job)
        svc.job_manager.complete_job = AsyncMock(return_value=fake_job)
        # Return None for get_job to trigger fallback
        svc.job_manager.get_job = AsyncMock(return_value=None)

        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        result = await svc.start_migration(cfg)
        assert result.status == MigrationJobStatus.FAILED


# ---------------------------------------------------------------------------
# get_migration_status
# ---------------------------------------------------------------------------


class TestGetMigrationStatus:
    async def test_nonexistent_job(self):
        svc = make_service()
        result = await svc.get_migration_status("does-not-exist", "tenant-1")
        assert result is None

    async def test_existing_job_without_saga(self):
        """Job exists but no saga found (list_sagas returns empty)."""
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        # Replace list_sagas so it returns an empty list
        svc.orchestrator.list_sagas = AsyncMock(return_value=[])

        status = await svc.get_migration_status(migration_id, "tenant-1")
        assert status is not None
        assert status.migration_id == migration_id
        # No saga -> saga_id is ""
        assert status.saga_id == ""
        # No saga -> saga_status defaults to PENDING
        assert status.saga_status == SagaStatus.PENDING

    async def test_completed_job_status(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        status = await svc.get_migration_status(migration_id, "tenant-1")
        assert status is not None
        assert status.success is True
        assert status.status == MigrationJobStatus.COMPLETED

    async def test_status_with_saga_steps(self):
        """Saga found -- step statuses drive phases_completed/phases_compensated."""
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        # Build a mock saga with known step statuses
        completed_step = SagaStepExecution(
            step_name="validate_policies",
            status=SagaStepStatus.COMPLETED,
        )
        compensated_step = SagaStepExecution(
            step_name="backup_policies",
            status=SagaStepStatus.COMPENSATED,
        )
        pending_step = SagaStepExecution(
            step_name="migrate_policies",
            status=SagaStepStatus.PENDING,
        )

        mock_saga = MagicMock()
        mock_saga.saga_id = "saga-xxx"
        mock_saga.status = SagaStatus.COMPENSATED
        mock_saga.context = MagicMock()
        mock_saga.context.data = {"migration_id": migration_id}
        mock_saga.steps = [completed_step, compensated_step, pending_step]

        svc.orchestrator.list_sagas = AsyncMock(return_value=[mock_saga])

        status = await svc.get_migration_status(migration_id, "tenant-1")
        assert status is not None
        assert MigrationPhase.VALIDATION in status.phases_completed
        assert MigrationPhase.BACKUP in status.phases_compensated

    async def test_status_includes_checkpoints(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"policies": ["p1"]},
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        status = await svc.get_migration_status(migration_id, "tenant-1")
        assert status is not None
        assert len(status.checkpoints) > 0

    async def test_failed_job_success_is_false(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        # Manually mark job as failed
        job = await svc.job_manager.get_job(migration_id, "tenant-1")
        if job:
            await svc.job_manager.fail_job(migration_id, "post-hoc failure")

        svc.orchestrator.list_sagas = AsyncMock(return_value=[])
        status = await svc.get_migration_status(migration_id, "tenant-1")
        assert status is not None
        assert status.success is False


# ---------------------------------------------------------------------------
# cancel_migration
# ---------------------------------------------------------------------------


class TestCancelMigration:
    async def test_cancel_nonexistent(self):
        svc = make_service()
        result = await svc.cancel_migration("ghost-id", "tenant-1")
        assert result is False

    async def test_cancel_existing_migration_no_saga(self):
        """Job can be cancelled even when no matching saga is found."""
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        # list_sagas returns empty -- no saga found
        svc.orchestrator.list_sagas = AsyncMock(return_value=[])

        result = await svc.cancel_migration(migration_id, "tenant-1")
        assert result is True

    async def test_cancel_existing_migration_with_saga(self):
        """When a matching saga exists, cancel_saga is invoked."""
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        mock_saga = MagicMock()
        mock_saga.saga_id = "saga-to-cancel"
        mock_saga.context = MagicMock()
        mock_saga.context.data = {"migration_id": migration_id}

        svc.orchestrator.list_sagas = AsyncMock(return_value=[mock_saga])
        svc.orchestrator.cancel_saga = AsyncMock(return_value=True)

        result = await svc.cancel_migration(migration_id, "tenant-1")
        assert result is True
        svc.orchestrator.cancel_saga.assert_called_once_with("saga-to-cancel")

    async def test_cancel_wrong_tenant(self):
        """Cancel fails silently when job belongs to a different tenant."""
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        migration_result = await svc.start_migration(cfg)
        migration_id = migration_result.migration_id

        result = await svc.cancel_migration(migration_id, "wrong-tenant")
        assert result is False


# ---------------------------------------------------------------------------
# get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    async def test_initial_metrics(self):
        svc = make_service()
        metrics = svc.get_metrics()
        assert "total_sagas" in metrics
        assert "successful_sagas" in metrics
        assert "failed_sagas" in metrics
        assert "compensated_sagas" in metrics
        assert "success_rate" in metrics
        assert "total_steps_executed" in metrics
        assert "total_compensations" in metrics
        assert "average_execution_time_ms" in metrics
        assert metrics["total_sagas"] == 0

    async def test_metrics_after_success(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        await svc.start_migration(cfg)
        m = svc.get_metrics()
        assert m["total_sagas"] == 1
        assert m["successful_sagas"] == 1
        assert m["failed_sagas"] == 0
        assert m["success_rate"] == 100.0

    async def test_metrics_after_failure(self):
        svc = make_service()

        # Inject a failing saga result
        failed_result = SagaExecutionResult(
            saga_id="x",
            success=False,
            status=SagaStatus.COMPENSATED,
            completed_steps=["validate_policies"],
            compensated_steps=["validate_policies"],
            error="test error",
        )
        svc.orchestrator.execute = AsyncMock(return_value=failed_result)

        from enterprise_sso.migration_job_api import MigrationJob
        from enterprise_sso.migration_job_api import MigrationJobConfig as MJC

        fake_job = MigrationJob(
            job_id="fj",
            tenant_id="t1",
            config=MJC(job_type=MigrationJobType.POLICY_IMPORT),
        )
        svc.orchestrator.create_saga = AsyncMock(return_value=MagicMock(saga_id="x"))
        svc.job_manager.create_job = AsyncMock(return_value=fake_job)
        svc.job_manager.start_job = AsyncMock(return_value=fake_job)
        svc.job_manager.fail_job = AsyncMock(return_value=fake_job)
        svc.job_manager.get_job = AsyncMock(return_value=fake_job)

        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        await svc.start_migration(cfg)
        m = svc.get_metrics()
        assert m["total_sagas"] == 1
        assert m["failed_sagas"] == 1
        assert m["compensated_sagas"] == 1
        assert m["total_compensations"] == 1
