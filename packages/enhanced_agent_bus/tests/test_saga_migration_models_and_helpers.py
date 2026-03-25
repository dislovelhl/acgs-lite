# Constitutional Hash: 608508a9bd224290
"""
Tests for saga_migration_integration models, enums, checkpoint store,
service init, saga names, step-to-phase mapping, and saga definitions.

Split from test_saga_migration_integration_coverage.py (Group A + B).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
# MigrationPhase enum
# ---------------------------------------------------------------------------


class TestMigrationPhaseEnum:
    def test_all_phases_count(self):
        assert len(list(MigrationPhase)) == 7

    def test_phase_values(self):
        assert MigrationPhase.VALIDATION == "validation"
        assert MigrationPhase.BACKUP == "backup"
        assert MigrationPhase.PREPARATION == "preparation"
        assert MigrationPhase.EXECUTION == "execution"
        assert MigrationPhase.VERIFICATION == "verification"
        assert MigrationPhase.CLEANUP == "cleanup"
        assert MigrationPhase.ROLLBACK == "rollback"

    def test_phase_is_str_enum(self):
        assert isinstance(MigrationPhase.VALIDATION, str)


# ---------------------------------------------------------------------------
# MigrationCheckpoint dataclass
# ---------------------------------------------------------------------------


class TestMigrationCheckpoint:
    def test_defaults(self):
        cp = MigrationCheckpoint(
            checkpoint_id="id1",
            migration_id="mig1",
            phase=MigrationPhase.VALIDATION,
        )
        assert cp.data == {}
        assert cp.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(cp.created_at, datetime)

    def test_custom_data(self):
        cp = MigrationCheckpoint(
            checkpoint_id="id2",
            migration_id="mig2",
            phase=MigrationPhase.EXECUTION,
            data={"records": 42},
        )
        assert cp.data["records"] == 42


# ---------------------------------------------------------------------------
# SagaMigrationConfig dataclass
# ---------------------------------------------------------------------------


class TestSagaMigrationConfig:
    def test_minimal(self):
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="t1",
        )
        assert cfg.target_tenant_id is None
        assert cfg.enable_backup is True
        assert cfg.enable_verification is True
        assert cfg.max_retries == 3
        assert cfg.timeout_seconds == 3600
        assert cfg.checkpoint_interval == 100
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_full(self):
        cfg = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="src",
            target_tenant_id="tgt",
            options={"key": "val"},
            enable_backup=False,
            enable_verification=False,
            max_retries=5,
            timeout_seconds=7200,
            checkpoint_interval=50,
        )
        assert cfg.target_tenant_id == "tgt"
        assert cfg.enable_backup is False
        assert cfg.enable_verification is False
        assert cfg.options == {"key": "val"}


# ---------------------------------------------------------------------------
# SagaMigrationResult dataclass
# ---------------------------------------------------------------------------


class TestSagaMigrationResult:
    def test_success(self):
        r = SagaMigrationResult(
            migration_id="m1",
            saga_id="s1",
            success=True,
            status=MigrationJobStatus.COMPLETED,
            saga_status=SagaStatus.COMPLETED,
            phases_completed=[MigrationPhase.VALIDATION],
        )
        assert r.success is True
        assert r.error is None
        assert r.constitutional_hash == CONSTITUTIONAL_HASH
        assert r.phases_compensated == []

    def test_failure(self):
        r = SagaMigrationResult(
            migration_id="m2",
            saga_id="s2",
            success=False,
            status=MigrationJobStatus.FAILED,
            saga_status=SagaStatus.COMPENSATED,
            phases_completed=[],
            phases_compensated=[MigrationPhase.BACKUP],
            error="boom",
        )
        assert r.success is False
        assert r.error == "boom"


# ---------------------------------------------------------------------------
# CheckpointStore
# ---------------------------------------------------------------------------


class TestCheckpointStore:
    @pytest.fixture
    def store(self):
        return CheckpointStore()

    async def test_save_and_list(self, store):
        cp = MigrationCheckpoint(
            checkpoint_id="cp1",
            migration_id="mig1",
            phase=MigrationPhase.VALIDATION,
        )
        await store.save(cp)
        checkpoints = await store.list_checkpoints("mig1")
        assert len(checkpoints) == 1
        assert checkpoints[0].checkpoint_id == "cp1"

    async def test_list_empty(self, store):
        assert await store.list_checkpoints("no-such-migration") == []

    async def test_save_multiple_same_migration(self, store):
        for i, phase in enumerate([MigrationPhase.VALIDATION, MigrationPhase.BACKUP]):
            await store.save(
                MigrationCheckpoint(
                    checkpoint_id=f"cp-{i}",
                    migration_id="mig1",
                    phase=phase,
                )
            )
        assert len(await store.list_checkpoints("mig1")) == 2

    async def test_get_latest_no_phase_filter(self, store):
        for i in range(3):
            await store.save(
                MigrationCheckpoint(
                    checkpoint_id=f"cp-{i}",
                    migration_id="mig1",
                    phase=MigrationPhase.EXECUTION,
                    data={"batch": i},
                )
            )
        latest = await store.get_latest("mig1")
        assert latest is not None
        assert latest.data["batch"] == 2

    async def test_get_latest_with_phase_filter(self, store):
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="val-1",
                migration_id="mig1",
                phase=MigrationPhase.VALIDATION,
            )
        )
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="bak-1",
                migration_id="mig1",
                phase=MigrationPhase.BACKUP,
            )
        )
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="val-2",
                migration_id="mig1",
                phase=MigrationPhase.VALIDATION,
            )
        )
        result = await store.get_latest("mig1", phase=MigrationPhase.VALIDATION)
        assert result is not None
        assert result.checkpoint_id == "val-2"

    async def test_get_latest_nonexistent_migration(self, store):
        assert await store.get_latest("nope") is None

    async def test_get_latest_no_checkpoints_for_phase(self, store):
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="bak-1",
                migration_id="mig1",
                phase=MigrationPhase.BACKUP,
            )
        )
        result = await store.get_latest("mig1", phase=MigrationPhase.VALIDATION)
        assert result is None

    async def test_delete_existing(self, store):
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp1",
                migration_id="mig1",
                phase=MigrationPhase.VALIDATION,
            )
        )
        await store.delete("mig1")
        assert await store.list_checkpoints("mig1") == []

    async def test_delete_nonexistent(self, store):
        # Must not raise
        await store.delete("ghost-migration")

    async def test_isolation_between_migrations(self, store):
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-a",
                migration_id="mig-a",
                phase=MigrationPhase.VALIDATION,
            )
        )
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-b",
                migration_id="mig-b",
                phase=MigrationPhase.BACKUP,
            )
        )
        assert len(await store.list_checkpoints("mig-a")) == 1
        assert len(await store.list_checkpoints("mig-b")) == 1


# ---------------------------------------------------------------------------
# SagaMigrationService -- initialisation
# ---------------------------------------------------------------------------


class TestServiceInit:
    def test_default_construction(self):
        svc = SagaMigrationService()
        assert svc.job_manager is not None
        assert svc.orchestrator is not None
        assert svc.checkpoint_store is not None
        assert svc.metrics is not None
        assert svc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_components(self):
        jm = MigrationJobManager()
        orch = SagaOrchestrator(store=InMemorySagaStore())
        cs = CheckpointStore()
        svc = SagaMigrationService(job_manager=jm, orchestrator=orch, checkpoint_store=cs)
        assert svc.job_manager is jm
        assert svc.orchestrator is orch
        assert svc.checkpoint_store is cs

    def test_custom_constitutional_hash(self):
        svc = SagaMigrationService(constitutional_hash="deadbeef")
        assert svc.constitutional_hash == "deadbeef"

    def test_saga_definitions_registered(self):
        svc = make_service()
        defs = svc.orchestrator._definitions
        assert "saga_policy_migration" in defs
        assert "saga_schema_migration" in defs
        assert "saga_data_migration" in defs
        assert "saga_full_migration" in defs


# ---------------------------------------------------------------------------
# _get_saga_name helper
# ---------------------------------------------------------------------------


class TestGetSagaName:
    @pytest.fixture(autouse=True)
    def svc(self):
        self.svc = make_service()

    def test_policy_import(self):
        assert self.svc._get_saga_name(MigrationJobType.POLICY_IMPORT) == "saga_policy_migration"

    def test_decision_log_import(self):
        assert (
            self.svc._get_saga_name(MigrationJobType.DECISION_LOG_IMPORT) == "saga_data_migration"
        )

    def test_constitutional_analysis(self):
        assert (
            self.svc._get_saga_name(MigrationJobType.CONSTITUTIONAL_ANALYSIS)
            == "saga_schema_migration"
        )

    def test_full_migration(self):
        assert self.svc._get_saga_name(MigrationJobType.FULL_MIGRATION) == "saga_full_migration"

    def test_gap_remediation(self):
        assert self.svc._get_saga_name(MigrationJobType.GAP_REMEDIATION) == "saga_policy_migration"


# ---------------------------------------------------------------------------
# _step_to_phase helper
# ---------------------------------------------------------------------------


class TestStepToPhase:
    @pytest.fixture(autouse=True)
    def svc(self):
        self.svc = make_service()

    def test_validate_keyword(self):
        assert self.svc._step_to_phase("validate_policies") == MigrationPhase.VALIDATION

    def test_backup_keyword(self):
        assert self.svc._step_to_phase("backup_schema") == MigrationPhase.BACKUP

    def test_prepare_keyword(self):
        assert self.svc._step_to_phase("prepare_migration") == MigrationPhase.PREPARATION

    def test_migrate_keyword(self):
        assert self.svc._step_to_phase("migrate_data") == MigrationPhase.EXECUTION

    def test_apply_keyword(self):
        assert self.svc._step_to_phase("apply_schema") == MigrationPhase.EXECUTION

    def test_verify_keyword(self):
        assert self.svc._step_to_phase("verify_migration") == MigrationPhase.VERIFICATION

    def test_cleanup_keyword(self):
        assert self.svc._step_to_phase("cleanup") == MigrationPhase.CLEANUP

    def test_unknown_defaults_to_execution(self):
        assert self.svc._step_to_phase("unknown_random_step") == MigrationPhase.EXECUTION

    def test_uppercase_step_name(self):
        # lower() is applied in the method so upper-case still matches
        assert self.svc._step_to_phase("VALIDATE_POLICIES") == MigrationPhase.VALIDATION


# ---------------------------------------------------------------------------
# Saga definition structure tests (no network I/O)
# ---------------------------------------------------------------------------


class TestPolicySagaDefinition:
    def test_steps(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        names = [s.name for s in defn.steps]
        assert "validate_policies" in names
        assert "backup_policies" in names
        assert "migrate_policies" in names
        assert "verify_migration" in names

    def test_step_order(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_policy_migration"]
        order = {s.name: s.order for s in defn.steps}
        assert order["validate_policies"] < order["backup_policies"]
        assert order["backup_policies"] < order["migrate_policies"]
        assert order["migrate_policies"] < order["verify_migration"]


class TestSchemaSagaDefinition:
    def test_steps(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        names = [s.name for s in defn.steps]
        assert "backup_schema" in names
        assert "apply_schema" in names
        assert "validate_schema" in names

    def test_step_count(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_schema_migration"]
        assert len(defn.steps) == 3


class TestDataSagaDefinition:
    def test_steps(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_data_migration"]
        names = [s.name for s in defn.steps]
        assert "prepare_migration" in names
        assert "migrate_data" in names
        assert "verify_data" in names


class TestFullSagaDefinition:
    def test_steps(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        names = [s.name for s in defn.steps]
        assert "validate_prerequisites" in names
        assert "create_full_backup" in names
        assert "migrate_schema" in names
        assert "migrate_data" in names
        assert "migrate_policies" in names
        assert "verify_migration" in names
        assert "cleanup" in names

    def test_step_order(self):
        svc = make_service()
        defn = svc.orchestrator._definitions["saga_full_migration"]
        order = {s.name: s.order for s in defn.steps}
        assert order["validate_prerequisites"] == 0
        assert order["create_full_backup"] == 1
        assert order["migrate_schema"] == 2
        assert order["migrate_data"] == 3
        assert order["migrate_policies"] == 4
        assert order["verify_migration"] == 5
        assert order["cleanup"] == 6
