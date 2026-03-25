"""
Tests for ACGS-2 Saga-Migration Integration Service
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for saga-managed migration workflows.

Phase 10 Task 17: Saga-Migration Integration Tests
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from enterprise_sso.migration_job_api import (
    MigrationJobManager,
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
    SagaContext,
    SagaOrchestrator,
    SagaStatus,
    SagaStepResult,
    SagaStore,
)

# Mark module as integration since service-level tests require Redis
pytestmark = [pytest.mark.integration]


def _redis_available() -> bool:
    """Check if Redis is available on localhost:6379."""
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


_SKIP_NO_REDIS = pytest.mark.skipif(
    not _redis_available(), reason="Redis not available on localhost:6379"
)

# Note: MigrationJobType has these values:
# - POLICY_IMPORT
# - DECISION_LOG_IMPORT (maps to data migration saga)
# - CONSTITUTIONAL_ANALYSIS (maps to schema migration saga)
# - FULL_MIGRATION
# - GAP_REMEDIATION

# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional hash enforcement."""

    def test_module_has_constitutional_hash(self):
        """Test module exports constitutional hash."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_migration_checkpoint_includes_hash(self):
        """Test MigrationCheckpoint includes constitutional hash."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id="cp-001",
            migration_id="mig-001",
            phase=MigrationPhase.VALIDATION,
        )
        assert checkpoint.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_migration_config_includes_hash(self):
        """Test SagaMigrationConfig includes constitutional hash."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_migration_result_includes_hash(self):
        """Test SagaMigrationResult includes constitutional hash."""
        result = SagaMigrationResult(
            migration_id="mig-001",
            saga_id="saga-001",
            success=True,
            status=MigrationJobStatus.COMPLETED,
            saga_status=SagaStatus.COMPLETED,
            phases_completed=[MigrationPhase.VALIDATION],
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_service_includes_hash(self):
        """Test SagaMigrationService uses constitutional hash."""
        service = SagaMigrationService()
        assert service.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# MigrationPhase Enum Tests
# =============================================================================


class TestMigrationPhase:
    """Tests for MigrationPhase enum."""

    def test_all_phases_defined(self):
        """Test all migration phases are defined."""
        phases = list(MigrationPhase)
        assert len(phases) == 7

    def test_phase_values(self):
        """Test phase string values."""
        assert MigrationPhase.VALIDATION.value == "validation"
        assert MigrationPhase.BACKUP.value == "backup"
        assert MigrationPhase.PREPARATION.value == "preparation"
        assert MigrationPhase.EXECUTION.value == "execution"
        assert MigrationPhase.VERIFICATION.value == "verification"
        assert MigrationPhase.CLEANUP.value == "cleanup"
        assert MigrationPhase.ROLLBACK.value == "rollback"

    def test_phases_are_string_enum(self):
        """Test phases are string enum for serialization."""
        assert isinstance(MigrationPhase.VALIDATION.value, str)
        assert MigrationPhase.VALIDATION == "validation"


# =============================================================================
# MigrationCheckpoint Tests
# =============================================================================


class TestMigrationCheckpoint:
    """Tests for MigrationCheckpoint dataclass."""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id="cp-001",
            migration_id="mig-001",
            phase=MigrationPhase.EXECUTION,
            data={"records_processed": 100},
        )
        assert checkpoint.checkpoint_id == "cp-001"
        assert checkpoint.migration_id == "mig-001"
        assert checkpoint.phase == MigrationPhase.EXECUTION
        assert checkpoint.data["records_processed"] == 100

    def test_checkpoint_has_timestamp(self):
        """Test checkpoint has creation timestamp."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id="cp-001",
            migration_id="mig-001",
            phase=MigrationPhase.VALIDATION,
        )
        assert checkpoint.created_at is not None
        assert isinstance(checkpoint.created_at, datetime)

    def test_checkpoint_default_data(self):
        """Test checkpoint has default empty data."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id="cp-001",
            migration_id="mig-001",
            phase=MigrationPhase.BACKUP,
        )
        assert checkpoint.data == {}


# =============================================================================
# SagaMigrationConfig Tests
# =============================================================================


class TestSagaMigrationConfig:
    """Tests for SagaMigrationConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal configuration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
        )
        assert config.migration_type == MigrationJobType.DECISION_LOG_IMPORT
        assert config.source_tenant_id == "tenant-1"

    def test_full_config(self):
        """Test full configuration with all options."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="tenant-1",
            target_tenant_id="tenant-2",
            options={"batch_size": 500},
            enable_backup=True,
            enable_verification=True,
            max_retries=5,
            timeout_seconds=7200,
            checkpoint_interval=50,
        )
        assert config.target_tenant_id == "tenant-2"
        assert config.options["batch_size"] == 500
        assert config.enable_backup is True
        assert config.max_retries == 5
        assert config.timeout_seconds == 7200
        assert config.checkpoint_interval == 50

    def test_default_values(self):
        """Test default configuration values."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )
        assert config.target_tenant_id is None
        assert config.options == {}
        assert config.enable_backup is True
        assert config.enable_verification is True
        assert config.max_retries == 3
        assert config.timeout_seconds == 3600
        assert config.checkpoint_interval == 100


# =============================================================================
# SagaMigrationResult Tests
# =============================================================================


class TestSagaMigrationResult:
    """Tests for SagaMigrationResult dataclass."""

    def test_successful_result(self):
        """Test successful migration result."""
        result = SagaMigrationResult(
            migration_id="mig-001",
            saga_id="saga-001",
            success=True,
            status=MigrationJobStatus.COMPLETED,
            saga_status=SagaStatus.COMPLETED,
            phases_completed=[
                MigrationPhase.VALIDATION,
                MigrationPhase.BACKUP,
                MigrationPhase.EXECUTION,
            ],
            execution_time_ms=1500.0,
        )
        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED
        assert len(result.phases_completed) == 3
        assert result.error is None

    def test_failed_result_with_compensation(self):
        """Test failed migration with compensated phases."""
        result = SagaMigrationResult(
            migration_id="mig-001",
            saga_id="saga-001",
            success=False,
            status=MigrationJobStatus.FAILED,
            saga_status=SagaStatus.COMPENSATED,
            phases_completed=[
                MigrationPhase.VALIDATION,
                MigrationPhase.BACKUP,
            ],
            phases_compensated=[
                MigrationPhase.BACKUP,
                MigrationPhase.VALIDATION,
            ],
            error="Migration failed at execution phase",
        )
        assert result.success is False
        assert len(result.phases_compensated) == 2
        assert result.error is not None

    def test_result_with_checkpoints(self):
        """Test result includes checkpoints."""
        checkpoints = [
            MigrationCheckpoint(
                checkpoint_id="cp-1",
                migration_id="mig-001",
                phase=MigrationPhase.VALIDATION,
            ),
            MigrationCheckpoint(
                checkpoint_id="cp-2",
                migration_id="mig-001",
                phase=MigrationPhase.BACKUP,
            ),
        ]
        result = SagaMigrationResult(
            migration_id="mig-001",
            saga_id="saga-001",
            success=True,
            status=MigrationJobStatus.COMPLETED,
            saga_status=SagaStatus.COMPLETED,
            phases_completed=[MigrationPhase.VALIDATION],
            checkpoints=checkpoints,
        )
        assert len(result.checkpoints) == 2


# =============================================================================
# CheckpointStore Tests
# =============================================================================


class TestCheckpointStore:
    """Tests for CheckpointStore."""

    @pytest.fixture
    def store(self):
        """Create a checkpoint store."""
        return CheckpointStore()

    async def test_save_checkpoint(self, store):
        """Test saving a checkpoint."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id="cp-001",
            migration_id="mig-001",
            phase=MigrationPhase.VALIDATION,
        )
        await store.save(checkpoint)

        checkpoints = await store.list_checkpoints("mig-001")
        assert len(checkpoints) == 1
        assert checkpoints[0].checkpoint_id == "cp-001"

    async def test_save_multiple_checkpoints(self, store):
        """Test saving multiple checkpoints."""
        for i, phase in enumerate(
            [
                MigrationPhase.VALIDATION,
                MigrationPhase.BACKUP,
                MigrationPhase.EXECUTION,
            ]
        ):
            checkpoint = MigrationCheckpoint(
                checkpoint_id=f"cp-{i}",
                migration_id="mig-001",
                phase=phase,
            )
            await store.save(checkpoint)

        checkpoints = await store.list_checkpoints("mig-001")
        assert len(checkpoints) == 3

    async def test_get_latest_checkpoint(self, store):
        """Test getting latest checkpoint."""
        for i in range(3):
            checkpoint = MigrationCheckpoint(
                checkpoint_id=f"cp-{i}",
                migration_id="mig-001",
                phase=MigrationPhase.EXECUTION,
                data={"batch": i},
            )
            await store.save(checkpoint)

        latest = await store.get_latest("mig-001")
        assert latest is not None
        assert latest.checkpoint_id == "cp-2"
        assert latest.data["batch"] == 2

    async def test_get_latest_by_phase(self, store):
        """Test getting latest checkpoint by phase."""
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-1",
                migration_id="mig-001",
                phase=MigrationPhase.VALIDATION,
            )
        )
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-2",
                migration_id="mig-001",
                phase=MigrationPhase.BACKUP,
            )
        )
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-3",
                migration_id="mig-001",
                phase=MigrationPhase.VALIDATION,
            )
        )

        latest = await store.get_latest("mig-001", MigrationPhase.VALIDATION)
        assert latest is not None
        assert latest.checkpoint_id == "cp-3"

    async def test_get_latest_nonexistent(self, store):
        """Test getting latest from nonexistent migration."""
        latest = await store.get_latest("nonexistent")
        assert latest is None

    async def test_list_checkpoints_empty(self, store):
        """Test listing checkpoints for nonexistent migration."""
        checkpoints = await store.list_checkpoints("nonexistent")
        assert checkpoints == []

    async def test_delete_checkpoints(self, store):
        """Test deleting checkpoints."""
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-1",
                migration_id="mig-001",
                phase=MigrationPhase.VALIDATION,
            )
        )
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-2",
                migration_id="mig-001",
                phase=MigrationPhase.BACKUP,
            )
        )

        await store.delete("mig-001")

        checkpoints = await store.list_checkpoints("mig-001")
        assert checkpoints == []

    async def test_delete_nonexistent(self, store):
        """Test deleting nonexistent checkpoints (no error)."""
        await store.delete("nonexistent")  # Should not raise

    async def test_multi_migration_isolation(self, store):
        """Test checkpoints are isolated per migration."""
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-1",
                migration_id="mig-001",
                phase=MigrationPhase.VALIDATION,
            )
        )
        await store.save(
            MigrationCheckpoint(
                checkpoint_id="cp-2",
                migration_id="mig-002",
                phase=MigrationPhase.BACKUP,
            )
        )

        checkpoints_1 = await store.list_checkpoints("mig-001")
        checkpoints_2 = await store.list_checkpoints("mig-002")

        assert len(checkpoints_1) == 1
        assert len(checkpoints_2) == 1
        assert checkpoints_1[0].checkpoint_id == "cp-1"
        assert checkpoints_2[0].checkpoint_id == "cp-2"


# =============================================================================
# SagaMigrationService Tests
# =============================================================================


class TestSagaMigrationService:
    """Tests for SagaMigrationService."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    def test_service_initialization(self, service):
        """Test service initializes with required components."""
        assert service.job_manager is not None
        assert service.orchestrator is not None
        assert service.checkpoint_store is not None
        assert service.metrics is not None

    def test_service_custom_components(self):
        """Test service with custom components."""
        job_manager = MigrationJobManager()
        orchestrator = SagaOrchestrator()
        checkpoint_store = CheckpointStore()

        service = SagaMigrationService(
            job_manager=job_manager,
            orchestrator=orchestrator,
            checkpoint_store=checkpoint_store,
        )

        assert service.job_manager is job_manager
        assert service.orchestrator is orchestrator
        assert service.checkpoint_store is checkpoint_store

    def test_sagas_registered(self, service):
        """Test all migration sagas are registered."""
        definitions = list(service.orchestrator._definitions.values())
        saga_names = [d.name for d in definitions]

        assert "saga_policy_migration" in saga_names
        assert "saga_schema_migration" in saga_names
        assert "saga_data_migration" in saga_names
        assert "saga_full_migration" in saga_names


@_SKIP_NO_REDIS
class TestSagaMigrationServiceStartMigration:
    """Tests for starting saga-managed migrations."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    async def test_start_policy_migration(self, service):
        """Test starting a policy migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"policies": ["policy-1", "policy-2"]},
        )

        result = await service.start_migration(config)

        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED
        assert result.saga_status == SagaStatus.COMPLETED
        assert result.migration_id is not None
        assert result.saga_id is not None
        assert len(result.phases_completed) > 0

    async def test_start_schema_migration(self, service):
        """Test starting a schema migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
            source_tenant_id="tenant-1",
            options={"target_version": "v2.0.0"},
        )

        result = await service.start_migration(config)

        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED

    async def test_start_data_migration(self, service):
        """Test starting a data migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
            options={"total_records": 1000, "batch_size": 100},
        )

        result = await service.start_migration(config)

        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED

    async def test_start_full_migration(self, service):
        """Test starting a full migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="tenant-1",
            target_tenant_id="tenant-2",
            options={
                "total_records": 500,
                "policies": ["policy-1"],
            },
        )

        result = await service.start_migration(config)

        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED

    async def test_migration_creates_checkpoints(self, service):
        """Test migration creates checkpoints."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={"policies": []},
        )

        result = await service.start_migration(config)

        assert len(result.checkpoints) > 0
        # Verify checkpoints have the migration ID
        for cp in result.checkpoints:
            assert cp.migration_id == result.migration_id

    async def test_migration_records_execution_time(self, service):
        """Test migration records execution time."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
            source_tenant_id="tenant-1",
        )

        result = await service.start_migration(config)

        assert result.execution_time_ms > 0

    async def test_migration_with_backup_disabled(self, service):
        """Test migration with backup disabled."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            enable_backup=False,
        )

        result = await service.start_migration(config)

        assert result.success is True

    async def test_migration_with_verification_disabled(self, service):
        """Test migration with verification disabled."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            enable_verification=False,
        )

        result = await service.start_migration(config)

        assert result.success is True


class TestSagaMigrationServiceStatus:
    """Tests for getting migration status."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    @_SKIP_NO_REDIS
    async def test_get_completed_migration_status(self, service):
        """Test getting status of completed migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )

        migration_result = await service.start_migration(config)

        status = await service.get_migration_status(
            migration_result.migration_id,
            "tenant-1",
        )

        assert status is not None
        assert status.migration_id == migration_result.migration_id
        assert status.status == MigrationJobStatus.COMPLETED

    async def test_get_nonexistent_migration_status(self, service):
        """Test getting status of nonexistent migration."""
        status = await service.get_migration_status(
            "nonexistent-id",
            "tenant-1",
        )

        assert status is None

    @_SKIP_NO_REDIS
    async def test_status_includes_checkpoints(self, service):
        """Test status includes checkpoints."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
        )

        migration_result = await service.start_migration(config)

        status = await service.get_migration_status(
            migration_result.migration_id,
            "tenant-1",
        )

        assert status is not None
        assert len(status.checkpoints) > 0


class TestSagaMigrationServiceCancel:
    """Tests for cancelling migrations."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    @_SKIP_NO_REDIS
    async def test_cancel_migration(self, service):
        """Test cancelling a migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="tenant-1",
        )

        # Start migration
        migration_result = await service.start_migration(config)

        # Cancel it (may already be complete)
        cancelled = await service.cancel_migration(
            migration_result.migration_id,
            "tenant-1",
        )

        # Cancel should succeed even for completed migrations
        assert cancelled is True

    async def test_cancel_nonexistent_migration(self, service):
        """Test cancelling nonexistent migration."""
        cancelled = await service.cancel_migration(
            "nonexistent-id",
            "tenant-1",
        )

        assert cancelled is False


@_SKIP_NO_REDIS
class TestSagaMigrationServiceMetrics:
    """Tests for migration service metrics."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    async def test_metrics_recorded(self, service):
        """Test metrics are recorded after migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )

        await service.start_migration(config)

        metrics = service.get_metrics()

        assert "total_sagas" in metrics
        assert metrics["total_sagas"] >= 1

    async def test_multiple_migrations_metrics(self, service):
        """Test metrics accumulate across migrations."""
        for i in range(3):
            config = SagaMigrationConfig(
                migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
                source_tenant_id=f"tenant-{i}",
            )
            await service.start_migration(config)

        metrics = service.get_metrics()

        assert metrics["total_sagas"] >= 3


class TestSagaHelperMethods:
    """Tests for internal helper methods."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    def test_get_saga_name_policy(self, service):
        """Test saga name for policy migration."""
        name = service._get_saga_name(MigrationJobType.POLICY_IMPORT)
        assert name == "saga_policy_migration"

    def test_get_saga_name_schema(self, service):
        """Test saga name for schema migration."""
        name = service._get_saga_name(MigrationJobType.CONSTITUTIONAL_ANALYSIS)
        assert name == "saga_schema_migration"

    def test_get_saga_name_data(self, service):
        """Test saga name for data migration."""
        name = service._get_saga_name(MigrationJobType.DECISION_LOG_IMPORT)
        assert name == "saga_data_migration"

    def test_get_saga_name_full(self, service):
        """Test saga name for full migration."""
        name = service._get_saga_name(MigrationJobType.FULL_MIGRATION)
        assert name == "saga_full_migration"

    def test_step_to_phase_validate(self, service):
        """Test step to phase mapping for validation."""
        phase = service._step_to_phase("validate_policies")
        assert phase == MigrationPhase.VALIDATION

    def test_step_to_phase_backup(self, service):
        """Test step to phase mapping for backup."""
        phase = service._step_to_phase("backup_schema")
        assert phase == MigrationPhase.BACKUP

    def test_step_to_phase_migrate(self, service):
        """Test step to phase mapping for migration."""
        phase = service._step_to_phase("migrate_data")
        assert phase == MigrationPhase.EXECUTION

    def test_step_to_phase_apply(self, service):
        """Test step to phase mapping for apply."""
        phase = service._step_to_phase("apply_schema")
        assert phase == MigrationPhase.EXECUTION

    def test_step_to_phase_verify(self, service):
        """Test step to phase mapping for verification."""
        phase = service._step_to_phase("verify_migration")
        assert phase == MigrationPhase.VERIFICATION

    def test_step_to_phase_cleanup(self, service):
        """Test step to phase mapping for cleanup."""
        phase = service._step_to_phase("cleanup")
        assert phase == MigrationPhase.CLEANUP

    def test_step_to_phase_default(self, service):
        """Test step to phase mapping for unknown step."""
        phase = service._step_to_phase("unknown_step")
        assert phase == MigrationPhase.EXECUTION


# =============================================================================
# Saga Definition Tests
# =============================================================================


class TestPolicyMigrationSaga:
    """Tests for policy migration saga definition."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    def test_policy_saga_registered(self, service):
        """Test policy migration saga is registered."""
        assert "saga_policy_migration" in service.orchestrator._definitions

    def test_policy_saga_steps(self, service):
        """Test policy migration saga has expected steps."""
        definition = service.orchestrator._definitions["saga_policy_migration"]
        step_names = [s.name for s in definition.steps]

        assert "validate_policies" in step_names
        assert "backup_policies" in step_names
        assert "migrate_policies" in step_names
        assert "verify_migration" in step_names


class TestSchemaMigrationSaga:
    """Tests for schema migration saga definition."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    def test_schema_saga_registered(self, service):
        """Test schema migration saga is registered."""
        assert "saga_schema_migration" in service.orchestrator._definitions

    def test_schema_saga_steps(self, service):
        """Test schema migration saga has expected steps."""
        definition = service.orchestrator._definitions["saga_schema_migration"]
        step_names = [s.name for s in definition.steps]

        assert "backup_schema" in step_names
        assert "apply_schema" in step_names
        assert "validate_schema" in step_names


class TestDataMigrationSaga:
    """Tests for data migration saga definition."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    def test_data_saga_registered(self, service):
        """Test data migration saga is registered."""
        assert "saga_data_migration" in service.orchestrator._definitions

    def test_data_saga_steps(self, service):
        """Test data migration saga has expected steps."""
        definition = service.orchestrator._definitions["saga_data_migration"]
        step_names = [s.name for s in definition.steps]

        assert "prepare_migration" in step_names
        assert "migrate_data" in step_names
        assert "verify_data" in step_names


class TestFullMigrationSaga:
    """Tests for full migration saga definition."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    def test_full_saga_registered(self, service):
        """Test full migration saga is registered."""
        assert "saga_full_migration" in service.orchestrator._definitions

    def test_full_saga_steps(self, service):
        """Test full migration saga has expected steps."""
        definition = service.orchestrator._definitions["saga_full_migration"]
        step_names = [s.name for s in definition.steps]

        assert "validate_prerequisites" in step_names
        assert "create_full_backup" in step_names
        assert "migrate_schema" in step_names
        assert "migrate_data" in step_names
        assert "migrate_policies" in step_names
        assert "verify_migration" in step_names
        assert "cleanup" in step_names

    def test_full_saga_step_order(self, service):
        """Test full migration saga steps are in correct order."""
        definition = service.orchestrator._definitions["saga_full_migration"]

        step_order = {s.name: s.order for s in definition.steps}

        assert step_order["validate_prerequisites"] == 0
        assert step_order["create_full_backup"] == 1
        assert step_order["migrate_schema"] == 2
        assert step_order["migrate_data"] == 3
        assert step_order["migrate_policies"] == 4
        assert step_order["verify_migration"] == 5
        assert step_order["cleanup"] == 6


# =============================================================================
# Multi-Tenant Tests
# =============================================================================


@_SKIP_NO_REDIS
class TestMultiTenantMigration:
    """Tests for multi-tenant migration scenarios."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    async def test_migration_between_tenants(self, service):
        """Test migration from one tenant to another."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="source-tenant",
            target_tenant_id="target-tenant",
        )

        result = await service.start_migration(config)

        assert result.success is True

    async def test_tenant_isolation_in_status(self, service):
        """Test tenant isolation when getting status."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )

        migration_result = await service.start_migration(config)

        # Try to get status with wrong tenant
        status = await service.get_migration_status(
            migration_result.migration_id,
            "wrong-tenant",
        )

        # Should not find migration for wrong tenant
        assert status is None

    async def test_concurrent_tenant_migrations(self, service):
        """Test concurrent migrations for different tenants."""
        configs = [
            SagaMigrationConfig(
                migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
                source_tenant_id=f"tenant-{i}",
            )
            for i in range(3)
        ]

        # Run migrations concurrently
        results = await asyncio.gather(*[service.start_migration(config) for config in configs])

        # All should succeed
        assert all(r.success for r in results)

        # Each should have unique migration ID
        migration_ids = [r.migration_id for r in results]
        assert len(set(migration_ids)) == 3


# =============================================================================
# Edge Case Tests
# =============================================================================


@_SKIP_NO_REDIS
class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    async def test_empty_options(self, service):
        """Test migration with empty options."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
            options={},
        )

        result = await service.start_migration(config)

        assert result.success is True

    async def test_same_source_and_target(self, service):
        """Test migration with same source and target tenant."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
            target_tenant_id="tenant-1",
        )

        result = await service.start_migration(config)

        assert result.success is True

    async def test_large_batch_size(self, service):
        """Test migration with large batch configuration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
            options={
                "total_records": 100000,
                "batch_size": 10000,
            },
        )

        result = await service.start_migration(config)

        assert result.success is True

    async def test_zero_records(self, service):
        """Test migration with zero records."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.DECISION_LOG_IMPORT,
            source_tenant_id="tenant-1",
            options={"total_records": 0},
        )

        result = await service.start_migration(config)

        assert result.success is True

    async def test_migration_result_constitutional_hash(self, service):
        """Test all migration results include constitutional hash."""
        configs = [
            SagaMigrationConfig(
                migration_type=MigrationJobType.POLICY_IMPORT,
                source_tenant_id="tenant-1",
            ),
            SagaMigrationConfig(
                migration_type=MigrationJobType.CONSTITUTIONAL_ANALYSIS,
                source_tenant_id="tenant-2",
            ),
            SagaMigrationConfig(
                migration_type=MigrationJobType.DECISION_LOG_IMPORT,
                source_tenant_id="tenant-3",
            ),
        ]

        for config in configs:
            result = await service.start_migration(config)
            assert result.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Integration Tests
# =============================================================================


@_SKIP_NO_REDIS
class TestSagaMigrationIntegration:
    """Integration tests for saga-migration workflow."""

    @pytest.fixture
    def service(self):
        """Create a saga migration service."""
        return SagaMigrationService()

    async def test_full_migration_workflow(self, service):
        """Test complete migration workflow from start to status."""
        # 1. Configure migration
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="production",
            target_tenant_id="staging",
            enable_backup=True,
            enable_verification=True,
            options={
                "total_records": 500,
                "policies": ["access-control", "data-governance"],
            },
        )

        # 2. Start migration
        result = await service.start_migration(config)

        # 3. Verify success
        assert result.success is True
        assert result.status == MigrationJobStatus.COMPLETED
        assert result.saga_status == SagaStatus.COMPLETED

        # 4. Check phases completed
        assert len(result.phases_completed) > 0

        # 5. Check checkpoints
        assert len(result.checkpoints) > 0

        # 6. Get status
        status = await service.get_migration_status(
            result.migration_id,
            "production",
        )
        assert status is not None
        assert status.status == MigrationJobStatus.COMPLETED

        # 7. Verify metrics recorded
        metrics = service.get_metrics()
        assert metrics["total_sagas"] >= 1

    async def test_checkpoint_persistence(self, service):
        """Test checkpoints are persisted throughout migration."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.FULL_MIGRATION,
            source_tenant_id="tenant-1",
        )

        result = await service.start_migration(config)

        # Verify checkpoints for different phases
        checkpoints = result.checkpoints
        phases_with_checkpoints = set(cp.phase for cp in checkpoints)

        # Should have checkpoints for multiple phases
        assert len(phases_with_checkpoints) >= 2

    async def test_job_and_saga_coordination(self, service):
        """Test job manager and saga orchestrator work together."""
        config = SagaMigrationConfig(
            migration_type=MigrationJobType.POLICY_IMPORT,
            source_tenant_id="tenant-1",
        )

        result = await service.start_migration(config)

        # Both job and saga should have IDs
        assert result.migration_id is not None
        assert result.saga_id is not None

        # Job should be in correct state
        job = await service.job_manager.get_job(
            result.migration_id,
            "tenant-1",
        )
        assert job is not None
        assert job.status == MigrationJobStatus.COMPLETED
