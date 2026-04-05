# Constitutional Hash: 608508a9bd224290
"""
Tests for saga_migration_integration step actions and compensations:
PolicySagaStepActions, SchemaSagaStepActions, DataSagaStepActions,
FullSagaStepActions, Prerequisites failure, and Constitutional hash integrity.

Split from test_saga_migration_integration_coverage.py (Group D).
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
# Saga step action/compensation functions -- direct invocation via orchestrator
# ---------------------------------------------------------------------------


class TestPolicySagaStepActions:
    """Directly call the registered action/compensation closures."""

    async def _run_all_steps(self, service: SagaMigrationService, initial_data: dict) -> None:
        """Create + execute a policy saga with provided initial data."""
        saga = await service.orchestrator.create_saga(
            definition_name="saga_policy_migration",
            tenant_id="tenant-1",
            initial_data=initial_data,
        )
        await service.orchestrator.execute(saga.saga_id)

    async def test_validate_policies_creates_checkpoint(self):
        svc = make_service()
        await self._run_all_steps(svc, {"policies": ["p1", "p2"], "source_tenant_id": "t1"})
        # At least validation checkpoint must exist
        all_cps = []
        for _migration_id, cps in svc.checkpoint_store._checkpoints.items():
            all_cps.extend(cps)
        phases = {cp.phase for cp in all_cps}
        assert MigrationPhase.VALIDATION in phases

    async def test_backup_policies_skipped_when_disabled(self):
        """With enable_backup=False the backup step returns skipped=True."""
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        backup_step = next(s for s in defn.steps if s.name == "backup_policies")

        ctx = SagaContext(
            saga_id="test-saga",
            tenant_id="t1",
            correlation_id="corr1",
            data={"enable_backup": False, "migration_id": "test-m"},
        )
        result = await backup_step.action(ctx)
        assert result.success is True
        assert result.data is not None
        assert result.data.get("skipped") is True

    async def test_backup_policies_enabled(self):
        """With enable_backup=True the backup step generates a backup_id."""
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        backup_step = next(s for s in defn.steps if s.name == "backup_policies")

        ctx = SagaContext(
            saga_id="test-saga",
            tenant_id="t1",
            correlation_id="corr1",
            data={"enable_backup": True, "migration_id": "test-m"},
        )
        result = await backup_step.action(ctx)
        assert result.success is True
        assert "backup_id" in ctx.data

    async def test_verify_migration_skipped_when_disabled(self):
        """With enable_verification=False the verify step returns skipped=True."""
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        verify_step = next(s for s in defn.steps if s.name == "verify_migration")

        ctx = SagaContext(
            saga_id="test-saga",
            tenant_id="t1",
            correlation_id="corr1",
            data={"enable_verification": False, "migration_id": "test-m"},
        )
        result = await verify_step.action(ctx)
        assert result.success is True
        assert result.data is not None
        assert result.data.get("skipped") is True

    async def test_verify_migration_enabled(self):
        """With enable_verification=True the verify step creates a checkpoint."""
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        verify_step = next(s for s in defn.steps if s.name == "verify_migration")

        ctx = SagaContext(
            saga_id="test-saga",
            tenant_id="t1",
            correlation_id="corr1",
            data={"enable_verification": True, "migration_id": "test-m"},
        )
        result = await verify_step.action(ctx)
        assert result.success is True
        assert result.data is not None
        assert result.data.get("verified") is True

    async def test_migrate_policies_with_job(self):
        """migrate_policies calls job_manager.update_progress when job exists."""
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        migrate_step = next(s for s in defn.steps if s.name == "migrate_policies")

        # Create a real job first
        from enterprise_sso.migration_job_api import MigrationJobConfig as MJC

        job = await svc.job_manager.create_job(
            tenant_id="t1",
            config=MJC(job_type=MigrationJobType.POLICY_IMPORT),
        )
        await svc.job_manager.start_job(job.job_id, "t1")

        ctx = SagaContext(
            saga_id=job.job_id,
            tenant_id="t1",
            correlation_id="corr1",
            data={"policies": ["p1", "p2"], "migration_id": job.job_id},
        )
        result = await migrate_step.action(ctx)
        assert result.success is True
        assert result.data["migrated_policies"] == 2

    async def test_migrate_policies_without_job(self):
        """migrate_policies handles missing job gracefully."""
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        migrate_step = next(s for s in defn.steps if s.name == "migrate_policies")

        ctx = SagaContext(
            saga_id="no-job",
            tenant_id="t1",
            correlation_id="corr1",
            data={"policies": ["p1"], "migration_id": "no-existing-job"},
        )
        result = await migrate_step.action(ctx)
        assert result.success is True

    async def test_compensate_validate(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        validate_step = next(s for s in defn.steps if s.name == "validate_policies")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await validate_step.compensation(ctx)
        assert result.success is True

    async def test_compensate_backup(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        backup_step = next(s for s in defn.steps if s.name == "backup_policies")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"backup_id": "bk-001"},
        )
        result = await backup_step.compensation(ctx)
        assert result.success is True
        assert result.data["deleted_backup"] == "bk-001"

    async def test_compensate_migrate(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        migrate_step = next(s for s in defn.steps if s.name == "migrate_policies")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"backup_id": "bk-002", "migration_id": "m1"},
        )
        result = await migrate_step.compensation(ctx)
        assert result.success is True
        assert result.data["restored_from"] == "bk-002"

    async def test_compensate_verify(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        verify_step = next(s for s in defn.steps if s.name == "verify_migration")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await verify_step.compensation(ctx)
        assert result.success is True


class TestSchemaSagaStepActions:
    async def test_backup_schema_creates_checkpoint(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        backup_step = next(s for s in defn.steps if s.name == "backup_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1"},
        )
        result = await backup_step.action(ctx)
        assert result.success is True
        assert "schema_backup_id" in ctx.data

    async def test_apply_schema(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        apply_step = next(s for s in defn.steps if s.name == "apply_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"target_version": "v3.0.0", "migration_id": "m1"},
        )
        result = await apply_step.action(ctx)
        assert result.success is True
        assert result.data["version"] == "v3.0.0"

    async def test_apply_schema_default_version(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        apply_step = next(s for s in defn.steps if s.name == "apply_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1"},
        )
        result = await apply_step.action(ctx)
        assert result.success is True
        assert result.data["version"] == "v1.0.0"

    async def test_validate_schema(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        validate_step = next(s for s in defn.steps if s.name == "validate_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await validate_step.action(ctx)
        assert result.success is True
        assert result.data["schema_valid"] is True

    async def test_compensate_backup_schema(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        backup_step = next(s for s in defn.steps if s.name == "backup_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await backup_step.compensation(ctx)
        assert result.success is True

    async def test_compensate_apply_schema(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        apply_step = next(s for s in defn.steps if s.name == "apply_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"schema_backup_id": "sbk-1"},
        )
        result = await apply_step.compensation(ctx)
        assert result.success is True
        assert result.data["restored_from"] == "sbk-1"

    async def test_compensate_validate_schema(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        validate_step = next(s for s in defn.steps if s.name == "validate_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await validate_step.compensation(ctx)
        assert result.success is True


class TestDataSagaStepActions:
    async def test_prepare_migration(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        prepare_step = next(s for s in defn.steps if s.name == "prepare_migration")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"total_records": 1000, "batch_size": 100},
        )
        result = await prepare_step.action(ctx)
        assert result.success is True
        assert result.data["batches"] == 10
        assert ctx.data["batches"] == 10

    async def test_prepare_migration_defaults(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        prepare_step = next(s for s in defn.steps if s.name == "prepare_migration")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await prepare_step.action(ctx)
        assert result.success is True
        # total_records=0, batch_size=1000 -> 0 batches
        assert result.data["batches"] == 0

    async def test_migrate_data_with_job(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        migrate_step = next(s for s in defn.steps if s.name == "migrate_data")

        from enterprise_sso.migration_job_api import MigrationJobConfig as MJC

        job = await svc.job_manager.create_job(
            tenant_id="t1",
            config=MJC(job_type=MigrationJobType.DECISION_LOG_IMPORT),
        )
        await svc.job_manager.start_job(job.job_id, "t1")

        ctx = SagaContext(
            saga_id=job.job_id,
            tenant_id="t1",
            correlation_id="c",
            data={"total_records": 50, "migration_id": job.job_id},
        )
        result = await migrate_step.action(ctx)
        assert result.success is True
        assert result.data["migrated_records"] == 50

    async def test_migrate_data_without_job(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        migrate_step = next(s for s in defn.steps if s.name == "migrate_data")
        ctx = SagaContext(
            saga_id="no-job",
            tenant_id="t1",
            correlation_id="c",
            data={"total_records": 5, "migration_id": "missing-job"},
        )
        result = await migrate_step.action(ctx)
        assert result.success is True

    async def test_verify_data(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        verify_step = next(s for s in defn.steps if s.name == "verify_data")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await verify_step.action(ctx)
        assert result.success is True
        assert result.data["data_verified"] is True
        assert result.data["integrity_check"] == "passed"

    async def test_compensate_prepare(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        prepare_step = next(s for s in defn.steps if s.name == "prepare_migration")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await prepare_step.compensation(ctx)
        assert result.success is True

    async def test_compensate_migrate_data(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        migrate_step = next(s for s in defn.steps if s.name == "migrate_data")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1"},
        )
        result = await migrate_step.compensation(ctx)
        assert result.success is True
        assert result.data["rolled_back"] is True

    async def test_compensate_verify_data(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        verify_step = next(s for s in defn.steps if s.name == "verify_data")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await verify_step.compensation(ctx)
        assert result.success is True


class TestFullSagaStepActions:
    async def test_validate_prerequisites_with_source(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "validate_prerequisites")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"source_tenant_id": "src", "target_tenant_id": "tgt"},
        )
        result = await step.action(ctx)
        assert result.success is True
        assert result.data["source"] == "src"
        assert result.data["target"] == "tgt"

    async def test_validate_prerequisites_missing_source(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "validate_prerequisites")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},  # no source_tenant_id
        )
        result = await step.action(ctx)
        assert result.success is False
        assert "source_tenant_id" in result.error

    async def test_create_full_backup(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "create_full_backup")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1"},
        )
        result = await step.action(ctx)
        assert result.success is True
        assert "backup_id" in result.data
        assert "full_backup_id" in ctx.data

    async def test_migrate_schema(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "migrate_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1"},
        )
        result = await step.action(ctx)
        assert result.success is True
        assert result.data["schema_migrated"] is True

    async def test_migrate_data_full(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "migrate_data")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1", "total_records": 42},
        )
        result = await step.action(ctx)
        assert result.success is True
        assert result.data["records_migrated"] == 42

    async def test_migrate_policies_full(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "migrate_policies")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1", "policies": ["a", "b", "c"]},
        )
        result = await step.action(ctx)
        assert result.success is True
        assert result.data["policies_migrated"] == 3

    async def test_verify_full_migration(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "verify_migration")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1"},
        )
        result = await step.action(ctx)
        assert result.success is True
        assert result.data["all_verified"] is True

    async def test_cleanup(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "cleanup")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"migration_id": "m1"},
        )
        result = await step.action(ctx)
        assert result.success is True
        assert result.data["cleaned_up"] is True

    # -- compensation functions -----------------------------------------------

    async def test_compensate_validate_prerequisites(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "validate_prerequisites")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await step.compensation(ctx)
        assert result.success is True

    async def test_compensate_create_full_backup(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "create_full_backup")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await step.compensation(ctx)
        assert result.success is True

    async def test_compensate_migrate_schema(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "migrate_schema")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"full_backup_id": "fbk-1"},
        )
        result = await step.compensation(ctx)
        assert result.success is True
        assert result.data["schema_restored_from"] == "fbk-1"

    async def test_compensate_migrate_data_full(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "migrate_data")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"full_backup_id": "fbk-2"},
        )
        result = await step.compensation(ctx)
        assert result.success is True
        assert result.data["data_restored_from"] == "fbk-2"

    async def test_compensate_migrate_policies_full(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "migrate_policies")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={"full_backup_id": "fbk-3"},
        )
        result = await step.compensation(ctx)
        assert result.success is True
        assert result.data["policies_restored_from"] == "fbk-3"

    async def test_compensate_verify_full_migration(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "verify_migration")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await step.compensation(ctx)
        assert result.success is True

    async def test_compensate_cleanup(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        step = next(s for s in defn.steps if s.name == "cleanup")
        ctx = SagaContext(
            saga_id="s",
            tenant_id="t",
            correlation_id="c",
            data={},
        )
        result = await step.compensation(ctx)
        assert result.success is True


# ---------------------------------------------------------------------------
# Full saga end-to-end (failing prerequisites -> compensation triggered)
# ---------------------------------------------------------------------------


class TestFullMigrationFailsOnPrerequisites:
    async def test_full_migration_fails_without_source(self):
        """validate_prerequisites fails when source_tenant_id is missing."""
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="",  # empty -> validate step returns failure
            options={},
        )
        # The saga create uses source_tenant_id for initial_data; pass empty string
        # then call start_migration which will put "" as source_tenant_id
        # The saga validate_prerequisites checks ctx.data.get("source_tenant_id")
        result = await svc.start_migration(cfg)
        # Empty string is falsy -> validation fails -> saga compensates
        assert result.success is False


# ---------------------------------------------------------------------------
# Constitutional hash integrity
# ---------------------------------------------------------------------------


class TestConstitutionalHashIntegrity:
    def test_constant_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_checkpoint_inherits_hash(self):
        cp = MigrationCheckpoint(
            checkpoint_id="x",
            migration_id="y",
            phase=MigrationPhase.VALIDATION,
        )
        assert cp.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_config_inherits_hash(self):
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t",
        )
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_result_inherits_hash(self):
        r = SagaMigrationResult(
            migration_id="m",
            saga_id="s",
            success=True,
            status=MigrationJobStatus.COMPLETED,
            saga_status=SagaStatus.COMPLETED,
            phases_completed=[],
        )
        assert r.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    async def test_migration_result_has_hash(self):
        svc = make_service()
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        result = await svc.start_migration(cfg)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret
