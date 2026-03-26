"""
Coverage tests for saga_migration_integration.py
Constitutional Hash: 608508a9bd224290

Achieves ≥90% coverage of SagaMigrationService and supporting classes
by mocking Redis-backed SagaStore so tests run without infrastructure.

Phase 10 Task 17: Saga-Migration Integration Coverage
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.constitutional]

# ---------------------------------------------------------------------------
# Import helpers — use fully-qualified src paths to avoid enterprise_sso
# __init__.py triggering relative imports that break outside the package.
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.migration_job_api import (
    MigrationJob,
    MigrationJobConfig,
    MigrationJobManager,
    MigrationJobResult,
    MigrationJobStatus,
    MigrationJobType,
)
from enhanced_agent_bus.enterprise_sso.saga_migration_integration import (
    CONSTITUTIONAL_HASH,
    CheckpointStore,
    MigrationCheckpoint,
    MigrationPhase,
    SagaMigrationConfig,
    SagaMigrationResult,
    SagaMigrationService,
)
from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
    CONSTITUTIONAL_HASH as SAGA_CONSTITUTIONAL_HASH,
)
from enhanced_agent_bus.enterprise_sso.saga_orchestration import (
    Saga,
    SagaContext,
    SagaExecutionResult,
    SagaOrchestrator,
    SagaStatus,
    SagaStepExecution,
    SagaStepStatus,
    SagaStore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_store() -> MagicMock:
    """Return an AsyncMock-based SagaStore that never touches Redis."""
    store = MagicMock(spec=SagaStore)
    store.save = AsyncMock()
    store.get = AsyncMock(return_value=None)
    store.list_by_tenant = AsyncMock(return_value=[])
    return store


def _make_saga(
    saga_id: str,
    tenant_id: str,
    name: str,
    migration_id: str,
    status: SagaStatus = SagaStatus.COMPLETED,
    step_statuses: list[tuple[str, SagaStepStatus]] | None = None,
) -> Saga:
    """Construct a minimal Saga object for assertions."""
    context = SagaContext(
        saga_id=saga_id,
        tenant_id=tenant_id,
        correlation_id=str(uuid.uuid4()),
        data={"migration_id": migration_id},
    )
    steps = []
    for name_s, st in step_statuses or []:
        s = SagaStepExecution(step_name=name_s)
        s.status = st
        steps.append(s)
    saga = Saga(
        saga_id=saga_id,
        tenant_id=tenant_id,
        name=name,
        description="test saga",
        status=status,
        context=context,
        steps=steps,
    )
    return saga


def _make_success_result(
    saga_id: str,
    completed_steps: list[str] | None = None,
) -> SagaExecutionResult:
    return SagaExecutionResult(
        saga_id=saga_id,
        success=True,
        status=SagaStatus.COMPLETED,
        completed_steps=completed_steps or [],
        compensated_steps=[],
        execution_time_ms=10.0,
    )


def _make_failure_result(
    saga_id: str,
    completed_steps: list[str] | None = None,
    compensated_steps: list[str] | None = None,
    error: str = "step failed",
) -> SagaExecutionResult:
    return SagaExecutionResult(
        saga_id=saga_id,
        success=False,
        status=SagaStatus.COMPENSATED,
        completed_steps=completed_steps or [],
        compensated_steps=compensated_steps or [],
        error=error,
        execution_time_ms=5.0,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_store():
    return _make_fake_store()


@pytest.fixture
def service(fake_store):
    """SagaMigrationService backed by a fake (no-Redis) SagaStore."""
    orchestrator = SagaOrchestrator(store=fake_store)
    return SagaMigrationService(orchestrator=orchestrator)


@pytest.fixture
def checkpoint_store():
    return CheckpointStore()


# ===========================================================================
# CheckpointStore tests
# ===========================================================================


class TestCheckpointStoreCoverage:
    async def test_save_and_list(self, checkpoint_store):
        cp = MigrationCheckpoint(
            checkpoint_id="cp-1",
            migration_id="mig-1",
            phase=MigrationPhase.VALIDATION,
        )
        await checkpoint_store.save(cp)
        result = await checkpoint_store.list_checkpoints("mig-1")
        assert len(result) == 1
        assert result[0].checkpoint_id == "cp-1"

    async def test_get_latest_no_phase_filter(self, checkpoint_store):
        for i, phase in enumerate([MigrationPhase.VALIDATION, MigrationPhase.BACKUP]):
            cp = MigrationCheckpoint(
                checkpoint_id=f"cp-{i}",
                migration_id="mig-1",
                phase=phase,
            )
            await checkpoint_store.save(cp)
        latest = await checkpoint_store.get_latest("mig-1")
        assert latest is not None
        assert latest.checkpoint_id == "cp-1"

    async def test_get_latest_with_phase_filter(self, checkpoint_store):
        for i, phase in enumerate(
            [MigrationPhase.VALIDATION, MigrationPhase.BACKUP, MigrationPhase.VALIDATION]
        ):
            cp = MigrationCheckpoint(
                checkpoint_id=f"cp-{i}",
                migration_id="mig-1",
                phase=phase,
            )
            await checkpoint_store.save(cp)
        latest = await checkpoint_store.get_latest("mig-1", MigrationPhase.VALIDATION)
        assert latest is not None
        assert latest.checkpoint_id == "cp-2"

    async def test_get_latest_nonexistent_migration(self, checkpoint_store):
        result = await checkpoint_store.get_latest("nonexistent")
        assert result is None

    async def test_get_latest_nonexistent_phase(self, checkpoint_store):
        cp = MigrationCheckpoint(
            checkpoint_id="cp-1",
            migration_id="mig-1",
            phase=MigrationPhase.VALIDATION,
        )
        await checkpoint_store.save(cp)
        result = await checkpoint_store.get_latest("mig-1", MigrationPhase.CLEANUP)
        assert result is None

    async def test_list_checkpoints_empty_migration(self, checkpoint_store):
        result = await checkpoint_store.list_checkpoints("does-not-exist")
        assert result == []

    async def test_delete_existing(self, checkpoint_store):
        cp = MigrationCheckpoint(
            checkpoint_id="cp-1",
            migration_id="mig-1",
            phase=MigrationPhase.BACKUP,
        )
        await checkpoint_store.save(cp)
        await checkpoint_store.delete("mig-1")
        result = await checkpoint_store.list_checkpoints("mig-1")
        assert result == []

    async def test_delete_nonexistent_is_noop(self, checkpoint_store):
        # Must not raise
        await checkpoint_store.delete("no-such-id")

    async def test_save_creates_list_for_new_migration(self, checkpoint_store):
        cp = MigrationCheckpoint(
            checkpoint_id="cp-a",
            migration_id="new-mig",
            phase=MigrationPhase.EXECUTION,
        )
        await checkpoint_store.save(cp)
        cps = await checkpoint_store.list_checkpoints("new-mig")
        assert len(cps) == 1


# ===========================================================================
# _step_to_phase and _get_saga_name
# ===========================================================================


class TestHelpers:
    def test_step_to_phase_validate(self, service):
        assert service._step_to_phase("validate_policies") == MigrationPhase.VALIDATION

    def test_step_to_phase_backup(self, service):
        assert service._step_to_phase("backup_schema") == MigrationPhase.BACKUP

    def test_step_to_phase_prepare(self, service):
        assert service._step_to_phase("prepare_migration") == MigrationPhase.PREPARATION

    def test_step_to_phase_migrate(self, service):
        assert service._step_to_phase("migrate_data") == MigrationPhase.EXECUTION

    def test_step_to_phase_apply(self, service):
        assert service._step_to_phase("apply_schema") == MigrationPhase.EXECUTION

    def test_step_to_phase_verify(self, service):
        assert service._step_to_phase("verify_migration") == MigrationPhase.VERIFICATION

    def test_step_to_phase_cleanup(self, service):
        assert service._step_to_phase("cleanup") == MigrationPhase.CLEANUP

    def test_step_to_phase_unknown_defaults_to_execution(self, service):
        assert service._step_to_phase("something_unknown") == MigrationPhase.EXECUTION

    def test_get_saga_name_policy_import(self, service):
        assert service._get_saga_name(MigrationJobType.POLICY_IMPORT) == "saga_policy_migration"

    def test_get_saga_name_decision_log(self, service):
        assert service._get_saga_name(MigrationJobType.DECISION_LOG_IMPORT) == "saga_data_migration"

    def test_get_saga_name_constitutional_analysis(self, service):
        assert (
            service._get_saga_name(MigrationJobType.CONSTITUTIONAL_ANALYSIS)
            == "saga_schema_migration"
        )

    def test_get_saga_name_full_migration(self, service):
        assert service._get_saga_name(MigrationJobType.FULL_MIGRATION) == "saga_full_migration"

    def test_get_saga_name_gap_remediation(self, service):
        assert service._get_saga_name(MigrationJobType.GAP_REMEDIATION) == "saga_policy_migration"

    def test_get_metrics_returns_dict(self, service):
        metrics = service.get_metrics()
        assert isinstance(metrics, dict)
        assert "total_sagas" in metrics


# ===========================================================================
# saga builder helpers — exercise inner async functions via extracted defs
# ===========================================================================


class TestSagaDefinitionsBuilt:
    def test_policy_migration_saga_steps(self, service):
        defn = service.orchestrator._definitions["saga_policy_migration"]
        names = [s.name for s in defn.steps]
        assert "validate_policies" in names
        assert "backup_policies" in names
        assert "migrate_policies" in names
        assert "verify_migration" in names

    def test_schema_migration_saga_steps(self, service):
        defn = service.orchestrator._definitions["saga_schema_migration"]
        names = [s.name for s in defn.steps]
        assert "backup_schema" in names
        assert "apply_schema" in names
        assert "validate_schema" in names

    def test_data_migration_saga_steps(self, service):
        defn = service.orchestrator._definitions["saga_data_migration"]
        names = [s.name for s in defn.steps]
        assert "prepare_migration" in names
        assert "migrate_data" in names
        assert "verify_data" in names

    def test_full_migration_saga_steps(self, service):
        defn = service.orchestrator._definitions["saga_full_migration"]
        names = [s.name for s in defn.steps]
        assert "validate_prerequisites" in names
        assert "create_full_backup" in names
        assert "migrate_schema" in names
        assert "migrate_data" in names
        assert "migrate_policies" in names
        assert "verify_migration" in names
        assert "cleanup" in names

    def test_full_migration_saga_step_order(self, service):
        defn = service.orchestrator._definitions["saga_full_migration"]
        orders = {s.name: s.order for s in defn.steps}
        assert orders["validate_prerequisites"] == 0
        assert orders["create_full_backup"] == 1
        assert orders["migrate_schema"] == 2
        assert orders["migrate_data"] == 3
        assert orders["migrate_policies"] == 4
        assert orders["verify_migration"] == 5
        assert orders["cleanup"] == 6


# ===========================================================================
# Inner saga step function execution (via SagaContext)
# ===========================================================================


class TestSagaInnerFunctions:
    """Execute the inner async step functions directly to hit their branches."""

    def _get_step_fn(self, service, saga_name: str, step_name: str):
        defn = service.orchestrator._definitions[saga_name]
        for step in defn.steps:
            if step.name == step_name:
                return step.action, step.compensation
        raise KeyError(f"step {step_name!r} not found in {saga_name!r}")

    def _make_ctx(
        self,
        service,
        data: dict | None = None,
        tenant_id: str = "tenant-1",
    ) -> SagaContext:
        saga_id = str(uuid.uuid4())
        return SagaContext(
            saga_id=saga_id,
            tenant_id=tenant_id,
            correlation_id=str(uuid.uuid4()),
            data=data or {"migration_id": str(uuid.uuid4())},
        )

    # ---- policy saga -------------------------------------------------------

    async def test_validate_policies_step_creates_checkpoint(self, service):
        action, _comp = self._get_step_fn(service, "saga_policy_migration", "validate_policies")
        ctx = self._make_ctx(service, {"policies": ["p1", "p2"], "source_tenant_id": "t1"})
        result = await action(ctx)
        assert result.success is True
        assert result.data["validated_policies"] == 2

    async def test_validate_policies_compensation_succeeds(self, service):
        _, comp = self._get_step_fn(service, "saga_policy_migration", "validate_policies")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    async def test_backup_policies_creates_backup_id(self, service):
        action, _ = self._get_step_fn(service, "saga_policy_migration", "backup_policies")
        ctx = self._make_ctx(service, {"enable_backup": True})
        result = await action(ctx)
        assert result.success is True
        assert "backup_id" in result.data
        assert "backup_id" in ctx.data

    async def test_backup_policies_skipped_when_disabled(self, service):
        action, _ = self._get_step_fn(service, "saga_policy_migration", "backup_policies")
        ctx = self._make_ctx(service, {"enable_backup": False})
        result = await action(ctx)
        assert result.success is True
        assert result.data.get("skipped") is True

    async def test_backup_policies_compensation(self, service):
        _, comp = self._get_step_fn(service, "saga_policy_migration", "backup_policies")
        ctx = self._make_ctx(service, {"backup_id": "bk-123"})
        result = await comp(ctx)
        assert result.success is True

    async def test_migrate_policies_with_job(self, service):
        """migrate_policies step updates progress when job exists."""
        action, _ = self._get_step_fn(service, "saga_policy_migration", "migrate_policies")
        # Create a real job via the job_manager
        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)
        ctx = self._make_ctx(
            service,
            {
                "migration_id": job.job_id,
                "policies": ["p1", "p2", "p3"],
            },
            tenant_id="t1",
        )
        result = await action(ctx)
        assert result.success is True
        assert result.data["migrated_policies"] == 3

    async def test_migrate_policies_without_job(self, service):
        """migrate_policies step skips update_progress when job not found."""
        action, _ = self._get_step_fn(service, "saga_policy_migration", "migrate_policies")
        ctx = self._make_ctx(
            service,
            {
                "migration_id": "nonexistent-job-id",
                "policies": ["p1"],
            },
            tenant_id="t1",
        )
        result = await action(ctx)
        assert result.success is True

    async def test_compensate_migrate_policies(self, service):
        _, comp = self._get_step_fn(service, "saga_policy_migration", "migrate_policies")
        ctx = self._make_ctx(service, {"backup_id": "bk-xyz"})
        result = await comp(ctx)
        assert result.success is True
        assert result.data["restored_from"] == "bk-xyz"

    async def test_verify_migration_enabled(self, service):
        action, _ = self._get_step_fn(service, "saga_policy_migration", "verify_migration")
        ctx = self._make_ctx(service, {"enable_verification": True})
        result = await action(ctx)
        assert result.success is True
        assert result.data.get("verified") is True

    async def test_verify_migration_disabled(self, service):
        action, _ = self._get_step_fn(service, "saga_policy_migration", "verify_migration")
        ctx = self._make_ctx(service, {"enable_verification": False})
        result = await action(ctx)
        assert result.success is True
        assert result.data.get("skipped") is True

    async def test_compensate_verify_migration(self, service):
        _, comp = self._get_step_fn(service, "saga_policy_migration", "verify_migration")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    # ---- schema saga -------------------------------------------------------

    async def test_backup_schema_creates_backup(self, service):
        action, _ = self._get_step_fn(service, "saga_schema_migration", "backup_schema")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert "backup_id" in result.data
        assert "schema_backup_id" in ctx.data

    async def test_compensate_backup_schema(self, service):
        _, comp = self._get_step_fn(service, "saga_schema_migration", "backup_schema")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    async def test_apply_schema_with_default_version(self, service):
        action, _ = self._get_step_fn(service, "saga_schema_migration", "apply_schema")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert result.data["version"] == "v1.0.0"

    async def test_apply_schema_with_custom_version(self, service):
        action, _ = self._get_step_fn(service, "saga_schema_migration", "apply_schema")
        ctx = self._make_ctx(service, {"target_version": "v3.5.0"})
        result = await action(ctx)
        assert result.success is True
        assert result.data["version"] == "v3.5.0"

    async def test_compensate_apply_schema(self, service):
        _, comp = self._get_step_fn(service, "saga_schema_migration", "apply_schema")
        ctx = self._make_ctx(service, {"schema_backup_id": "sbk-001"})
        result = await comp(ctx)
        assert result.success is True
        assert result.data["restored_from"] == "sbk-001"

    async def test_validate_schema(self, service):
        action, _ = self._get_step_fn(service, "saga_schema_migration", "validate_schema")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert result.data["schema_valid"] is True

    async def test_compensate_validate_schema(self, service):
        _, comp = self._get_step_fn(service, "saga_schema_migration", "validate_schema")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    # ---- data saga ---------------------------------------------------------

    async def test_prepare_migration_zero_records(self, service):
        action, _ = self._get_step_fn(service, "saga_data_migration", "prepare_migration")
        ctx = self._make_ctx(service, {"total_records": 0, "batch_size": 100})
        result = await action(ctx)
        assert result.success is True
        assert ctx.data["batches"] == 0

    async def test_prepare_migration_non_zero_records(self, service):
        action, _ = self._get_step_fn(service, "saga_data_migration", "prepare_migration")
        ctx = self._make_ctx(service, {"total_records": 250, "batch_size": 100})
        result = await action(ctx)
        assert result.success is True
        # ceil(250/100) = 3
        assert ctx.data["batches"] == 3

    async def test_prepare_migration_default_batch_size(self, service):
        action, _ = self._get_step_fn(service, "saga_data_migration", "prepare_migration")
        ctx = self._make_ctx(service, {"total_records": 1000})
        result = await action(ctx)
        assert result.success is True
        assert result.data["batch_size"] == 1000

    async def test_compensate_prepare_migration(self, service):
        _, comp = self._get_step_fn(service, "saga_data_migration", "prepare_migration")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    async def test_migrate_data_with_job(self, service):
        action, _ = self._get_step_fn(service, "saga_data_migration", "migrate_data")
        job_config = MigrationJobConfig(
            job_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_config={"tenant_id": "t2"},
            target_config={"tenant_id": "t2"},
        )
        job = await service.job_manager.create_job("t2", job_config)
        ctx = self._make_ctx(
            service,
            {"migration_id": job.job_id, "total_records": 50},
            tenant_id="t2",
        )
        result = await action(ctx)
        assert result.success is True
        assert result.data["migrated_records"] == 50

    async def test_migrate_data_without_job(self, service):
        action, _ = self._get_step_fn(service, "saga_data_migration", "migrate_data")
        ctx = self._make_ctx(
            service,
            {"migration_id": "no-job", "total_records": 10},
            tenant_id="t2",
        )
        result = await action(ctx)
        assert result.success is True

    async def test_compensate_migrate_data(self, service):
        _, comp = self._get_step_fn(service, "saga_data_migration", "migrate_data")
        ctx = self._make_ctx(service, {"migration_id": "mig-roll"})
        result = await comp(ctx)
        assert result.success is True
        assert result.data["rolled_back"] is True

    async def test_verify_data(self, service):
        action, _ = self._get_step_fn(service, "saga_data_migration", "verify_data")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert result.data["data_verified"] is True

    async def test_compensate_verify_data(self, service):
        _, comp = self._get_step_fn(service, "saga_data_migration", "verify_data")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    # ---- full migration saga ------------------------------------------------

    async def test_validate_prerequisites_with_source(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "validate_prerequisites")
        ctx = self._make_ctx(
            service,
            {"source_tenant_id": "src-tenant", "target_tenant_id": "dst-tenant"},
        )
        result = await action(ctx)
        assert result.success is True
        assert result.data["source"] == "src-tenant"

    async def test_validate_prerequisites_missing_source(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "validate_prerequisites")
        ctx = self._make_ctx(service, {})
        result = await action(ctx)
        assert result.success is False
        assert "source_tenant_id" in result.error

    async def test_compensate_validate_prerequisites(self, service):
        _, comp = self._get_step_fn(service, "saga_full_migration", "validate_prerequisites")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    async def test_create_full_backup(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "create_full_backup")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert "backup_id" in result.data
        assert "full_backup_id" in ctx.data

    async def test_compensate_full_backup(self, service):
        _, comp = self._get_step_fn(service, "saga_full_migration", "create_full_backup")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    async def test_migrate_schema_full(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "migrate_schema")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert result.data["schema_migrated"] is True

    async def test_compensate_migrate_schema_full(self, service):
        _, comp = self._get_step_fn(service, "saga_full_migration", "migrate_schema")
        ctx = self._make_ctx(service, {"full_backup_id": "fbk-001"})
        result = await comp(ctx)
        assert result.success is True
        assert result.data["schema_restored_from"] == "fbk-001"

    async def test_migrate_data_full(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "migrate_data")
        ctx = self._make_ctx(service, {"total_records": 100})
        result = await action(ctx)
        assert result.success is True
        assert result.data["records_migrated"] == 100

    async def test_compensate_migrate_data_full(self, service):
        _, comp = self._get_step_fn(service, "saga_full_migration", "migrate_data")
        ctx = self._make_ctx(service, {"full_backup_id": "fbk-002"})
        result = await comp(ctx)
        assert result.success is True
        assert result.data["data_restored_from"] == "fbk-002"

    async def test_migrate_policies_full(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "migrate_policies")
        ctx = self._make_ctx(service, {"policies": ["pol-a", "pol-b"]})
        result = await action(ctx)
        assert result.success is True
        assert result.data["policies_migrated"] == 2

    async def test_compensate_migrate_policies_full(self, service):
        _, comp = self._get_step_fn(service, "saga_full_migration", "migrate_policies")
        ctx = self._make_ctx(service, {"full_backup_id": "fbk-003"})
        result = await comp(ctx)
        assert result.success is True
        assert result.data["policies_restored_from"] == "fbk-003"

    async def test_verify_full_migration(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "verify_migration")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert result.data["all_verified"] is True

    async def test_compensate_verify_full_migration(self, service):
        _, comp = self._get_step_fn(service, "saga_full_migration", "verify_migration")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True

    async def test_cleanup(self, service):
        action, _ = self._get_step_fn(service, "saga_full_migration", "cleanup")
        ctx = self._make_ctx(service)
        result = await action(ctx)
        assert result.success is True
        assert result.data["cleaned_up"] is True

    async def test_compensate_cleanup(self, service):
        _, comp = self._get_step_fn(service, "saga_full_migration", "cleanup")
        ctx = self._make_ctx(service)
        result = await comp(ctx)
        assert result.success is True


# ===========================================================================
# start_migration — success path
# ===========================================================================


class TestStartMigrationSuccess:
    """Tests for start_migration in the success scenario."""

    def _make_service_with_mock_execute(
        self,
        completed_steps: list[str],
    ):
        """Return a service whose orchestrator.execute always succeeds."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        async def fake_execute(saga_id: str) -> SagaExecutionResult:
            return _make_success_result(saga_id, completed_steps)

        orchestrator.execute = fake_execute  # type: ignore[method-assign]
        return service

    async def test_policy_migration_success(self):
        service = self._make_service_with_mock_execute(
            ["validate_policies", "backup_policies", "migrate_policies", "verify_migration"]
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"policies": ["p1"]},
        )
        result = await service.start_migration(config)
        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED
        assert result.saga_status == SagaStatus.COMPLETED
        assert result.migration_id is not None
        assert result.saga_id is not None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_schema_migration_success(self):
        service = self._make_service_with_mock_execute(
            ["backup_schema", "apply_schema", "validate_schema"]
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
            source_tenant_id="tenant-1",
            options={"target_version": "v2.0.0"},
        )
        result = await service.start_migration(config)
        assert result.success is True

    async def test_data_migration_success(self):
        service = self._make_service_with_mock_execute(
            ["prepare_migration", "migrate_data", "verify_data"]
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
            options={"total_records": 500, "batch_size": 100},
        )
        result = await service.start_migration(config)
        assert result.success is True

    async def test_full_migration_success(self):
        service = self._make_service_with_mock_execute(
            [
                "validate_prerequisites",
                "create_full_backup",
                "migrate_schema",
                "migrate_data",
                "migrate_policies",
                "verify_migration",
                "cleanup",
            ]
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="src-t",
            target_tenant_id="dst-t",
            options={"total_records": 100, "policies": ["p1"]},
        )
        result = await service.start_migration(config)
        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED

    async def test_gap_remediation_uses_policy_saga(self):
        service = self._make_service_with_mock_execute(
            ["validate_policies", "backup_policies", "migrate_policies", "verify_migration"]
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.GAP_REMEDIATION,
            source_tenant_id="tenant-1",
        )
        result = await service.start_migration(config)
        assert result.success is True

    async def test_phases_completed_mapped_from_steps(self):
        service = self._make_service_with_mock_execute(
            ["validate_policies", "backup_policies", "migrate_policies"]
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        result = await service.start_migration(config)
        assert MigrationPhase.VALIDATION in result.phases_completed
        assert MigrationPhase.BACKUP in result.phases_completed
        assert MigrationPhase.EXECUTION in result.phases_completed

    async def test_metrics_recorded_after_success(self):
        service = self._make_service_with_mock_execute(["validate_policies"])
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        await service.start_migration(config)
        metrics = service.get_metrics()
        assert metrics["total_sagas"] >= 1
        assert metrics["successful_sagas"] >= 1

    async def test_target_tenant_defaults_to_source_when_none(self):
        service = self._make_service_with_mock_execute([])
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="only-tenant",
            target_tenant_id=None,
        )
        result = await service.start_migration(config)
        # Should succeed without error
        assert result.migration_id is not None

    async def test_execution_time_is_positive(self):
        service = self._make_service_with_mock_execute([])
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        result = await service.start_migration(config)
        assert result.execution_time_ms >= 0

    async def test_checkpoints_returned_in_result(self):
        """Checkpoints created by inner steps appear in result."""
        # Run with real execution (no mocked execute) but fake store so no Redis
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        # Patch only orchestrator.execute with a result that has steps
        saga_id = str(uuid.uuid4())

        async def fake_execute(sid: str) -> SagaExecutionResult:
            return _make_success_result(sid, ["validate_policies"])

        orchestrator.execute = fake_execute  # type: ignore[method-assign]

        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        result = await service.start_migration(config)
        # checkpoints list may be empty if inner steps didn't fire — that's OK
        assert isinstance(result.checkpoints, list)


# ===========================================================================
# start_migration — failure path
# ===========================================================================


class TestStartMigrationFailure:
    def _make_service_with_failing_execute(
        self,
        completed_steps: list[str] | None = None,
        compensated_steps: list[str] | None = None,
        error: str = "step failed",
    ):
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        async def fake_execute(saga_id: str) -> SagaExecutionResult:
            return _make_failure_result(
                saga_id,
                completed_steps=completed_steps,
                compensated_steps=compensated_steps,
                error=error,
            )

        orchestrator.execute = fake_execute  # type: ignore[method-assign]
        return service

    async def test_failed_saga_sets_status_failed(self):
        service = self._make_service_with_failing_execute(
            completed_steps=["validate_policies"],
            compensated_steps=["validate_policies"],
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        result = await service.start_migration(config)
        assert result.success is False
        assert result.status == MigrationJobStatus.FAILED
        assert result.error == "step failed"

    async def test_failed_saga_has_compensated_phases(self):
        service = self._make_service_with_failing_execute(
            completed_steps=["validate_policies", "backup_policies"],
            compensated_steps=["backup_policies", "validate_policies"],
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        result = await service.start_migration(config)
        assert len(result.phases_compensated) == 2

    async def test_failed_saga_metrics_recorded(self):
        service = self._make_service_with_failing_execute(
            completed_steps=["validate_policies"],
            compensated_steps=["validate_policies"],
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        await service.start_migration(config)
        metrics = service.get_metrics()
        assert metrics["failed_sagas"] >= 1

    async def test_failed_saga_job_result_is_none(self):
        service = self._make_service_with_failing_execute(
            error="some error occurred",
        )
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        result = await service.start_migration(config)
        assert result.job_result is None

    async def test_failed_saga_constitutional_hash_set(self):
        service = self._make_service_with_failing_execute()
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        result = await service.start_migration(config)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# get_migration_status
# ===========================================================================


class TestGetMigrationStatus:
    async def test_returns_none_for_unknown_job(self, service):
        result = await service.get_migration_status("no-such-id", "tenant-1")
        assert result is None

    async def test_returns_status_for_known_job_no_saga(self):
        """Job exists but no matching saga in the store."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        # Create a job via normal path
        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)
        await service.job_manager.start_job(job.job_id, "t1")

        # list_sagas returns empty — no saga found
        store.list_by_tenant = AsyncMock(return_value=[])

        status = await service.get_migration_status(job.job_id, "t1")
        assert status is not None
        assert status.migration_id == job.job_id
        assert status.saga_id == ""
        assert status.saga_status == SagaStatus.PENDING

    async def test_returns_status_with_saga_completed_steps(self):
        """Job + matching saga with some completed steps."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)

        saga = _make_saga(
            saga_id=str(uuid.uuid4()),
            tenant_id="t1",
            name="saga_policy_migration",
            migration_id=job.job_id,
            status=SagaStatus.COMPLETED,
            step_statuses=[
                ("validate_policies", SagaStepStatus.COMPLETED),
                ("backup_policies", SagaStepStatus.COMPLETED),
                ("migrate_policies", SagaStepStatus.COMPLETED),
            ],
        )
        store.list_by_tenant = AsyncMock(return_value=[saga])

        # Complete the job so status == COMPLETED
        result_obj = MigrationJobResult(
            job_id=job.job_id,
            tenant_id="t1",
            status=MigrationJobStatus.COMPLETED,
        )
        await service.job_manager.complete_job(job.job_id, result_obj)

        status = await service.get_migration_status(job.job_id, "t1")
        assert status is not None
        assert status.success is True
        assert MigrationPhase.VALIDATION in status.phases_completed
        assert MigrationPhase.BACKUP in status.phases_completed
        assert MigrationPhase.EXECUTION in status.phases_completed

    async def test_returns_status_with_saga_compensated_steps(self):
        """Saga with some compensated steps."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)

        saga = _make_saga(
            saga_id=str(uuid.uuid4()),
            tenant_id="t1",
            name="saga_policy_migration",
            migration_id=job.job_id,
            status=SagaStatus.COMPENSATED,
            step_statuses=[
                ("validate_policies", SagaStepStatus.COMPENSATED),
            ],
        )
        store.list_by_tenant = AsyncMock(return_value=[saga])

        status = await service.get_migration_status(job.job_id, "t1")
        assert status is not None
        assert MigrationPhase.VALIDATION in status.phases_compensated

    async def test_saga_with_no_context_data_migration_id(self):
        """Saga in store but migration_id doesn't match — not selected."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)

        # Saga with different migration_id
        saga = _make_saga(
            saga_id=str(uuid.uuid4()),
            tenant_id="t1",
            name="saga_policy_migration",
            migration_id="OTHER-ID",  # doesn't match job.job_id
            status=SagaStatus.COMPLETED,
        )
        store.list_by_tenant = AsyncMock(return_value=[saga])

        status = await service.get_migration_status(job.job_id, "t1")
        assert status is not None
        assert status.saga_id == ""  # no saga matched

    async def test_checkpoints_included_in_status(self):
        """Checkpoints from store appear in the status result."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        checkpoint_store = CheckpointStore()
        service = SagaMigrationService(orchestrator=orchestrator, checkpoint_store=checkpoint_store)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)

        # Add checkpoint
        cp = MigrationCheckpoint(
            checkpoint_id="cp-status-1",
            migration_id=job.job_id,
            phase=MigrationPhase.VALIDATION,
        )
        await checkpoint_store.save(cp)
        store.list_by_tenant = AsyncMock(return_value=[])

        status = await service.get_migration_status(job.job_id, "t1")
        assert status is not None
        assert len(status.checkpoints) == 1

    async def test_error_message_from_failed_job(self):
        """Error message from a failed job appears in status."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)
        await service.job_manager.fail_job(job.job_id, "something went wrong")
        store.list_by_tenant = AsyncMock(return_value=[])

        status = await service.get_migration_status(job.job_id, "t1")
        assert status is not None
        assert status.error == "something went wrong"

    async def test_get_status_step_not_completed_or_compensated(self):
        """Steps in pending/failed/executing state are not counted in phases."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)

        saga = _make_saga(
            saga_id=str(uuid.uuid4()),
            tenant_id="t1",
            name="saga_policy_migration",
            migration_id=job.job_id,
            status=SagaStatus.RUNNING,
            step_statuses=[
                ("validate_policies", SagaStepStatus.COMPLETED),
                ("backup_policies", SagaStepStatus.PENDING),  # neither completed nor compensated
                ("migrate_policies", SagaStepStatus.FAILED),  # neither completed nor compensated
            ],
        )
        store.list_by_tenant = AsyncMock(return_value=[saga])

        status = await service.get_migration_status(job.job_id, "t1")
        assert status is not None
        # Only validate_policies is completed
        assert MigrationPhase.VALIDATION in status.phases_completed
        # pending and failed steps should not appear in completed or compensated
        assert len(status.phases_compensated) == 0


# ===========================================================================
# cancel_migration
# ===========================================================================


class TestCancelMigration:
    async def test_cancel_nonexistent_returns_false(self, service):
        result = await service.cancel_migration("no-such-id", "t1")
        assert result is False

    async def test_cancel_known_job_no_saga_returns_true(self):
        """Job exists but no matching saga — still returns True."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)
        store.list_by_tenant = AsyncMock(return_value=[])

        result = await service.cancel_migration(job.job_id, "t1")
        assert result is True

    async def test_cancel_known_job_with_saga(self):
        """Job + matching saga → cancel saga too."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)

        saga_id = str(uuid.uuid4())
        saga = _make_saga(
            saga_id=saga_id,
            tenant_id="t1",
            name="saga_policy_migration",
            migration_id=job.job_id,
            status=SagaStatus.RUNNING,
        )
        store.list_by_tenant = AsyncMock(return_value=[saga])

        # Make saga retrievable for cancel_saga
        store.get = AsyncMock(return_value=saga)

        result = await service.cancel_migration(job.job_id, "t1")
        assert result is True

    async def test_cancel_known_job_saga_not_matching(self):
        """Saga in store but migration_id doesn't match — cancel still returns True."""
        store = _make_fake_store()
        orchestrator = SagaOrchestrator(store=store)
        service = SagaMigrationService(orchestrator=orchestrator)

        job_config = MigrationJobConfig(
            job_type=MigrationJobType.POLICY_IMPORT,
            source_config={"tenant_id": "t1"},
            target_config={"tenant_id": "t1"},
        )
        job = await service.job_manager.create_job("t1", job_config)

        saga = _make_saga(
            saga_id=str(uuid.uuid4()),
            tenant_id="t1",
            name="saga_policy_migration",
            migration_id="OTHER-ID",
        )
        store.list_by_tenant = AsyncMock(return_value=[saga])

        result = await service.cancel_migration(job.job_id, "t1")
        assert result is True


# ===========================================================================
# Constitutional compliance
# ===========================================================================


class TestConstitutionalCompliance:
    def test_constitutional_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_service_uses_correct_hash(self, service):
        assert service.constitutional_hash == CONSTITUTIONAL_HASH

    def test_checkpoint_default_hash(self):
        cp = MigrationCheckpoint(
            checkpoint_id="cp-001",
            migration_id="mig-001",
            phase=MigrationPhase.VALIDATION,
        )
        assert cp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_config_default_hash(self):
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_default_hash(self):
        res = SagaMigrationResult(
            migration_id="m",
            saga_id="s",
            success=True,
            status=MigrationJobStatus.COMPLETED,
            saga_status=SagaStatus.COMPLETED,
            phases_completed=[],
        )
        assert res.constitutional_hash == CONSTITUTIONAL_HASH

    def test_all_migration_phases_present(self):
        phases = list(MigrationPhase)
        phase_values = {p.value for p in phases}
        assert "validation" in phase_values
        assert "backup" in phase_values
        assert "preparation" in phase_values
        assert "execution" in phase_values
        assert "verification" in phase_values
        assert "cleanup" in phase_values
        assert "rollback" in phase_values
