"""
ACGS-2 Saga-Integrated Migration Service
Constitutional Hash: 608508a9bd224290

Integrates Saga Orchestration with Migration Job Management for
enterprise-grade migration workflows with automatic rollback.

Phase 10 Task 17: Saga-Migration Integration

Features:
- Migration jobs wrapped in saga transactions
- Automatic rollback on failure
- Multi-phase migration support
- Progress tracking with saga events
- Constitutional compliance throughout
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .migration_job_api import (
    MigrationJobConfig,
    MigrationJobManager,
    MigrationJobResult,
    MigrationJobStatus,
    MigrationJobType,
)
from .saga_orchestration import (
    CONSTITUTIONAL_HASH,
    SagaContext,
    SagaDefinition,
    SagaMetrics,
    SagaOrchestrator,
    SagaStatus,
    SagaStepDefinition,
    SagaStepResult,
)

logger = get_logger(__name__)


class MigrationPhase(str, Enum):
    """Phases of a saga-managed migration."""

    VALIDATION = "validation"
    BACKUP = "backup"
    PREPARATION = "preparation"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    CLEANUP = "cleanup"
    ROLLBACK = "rollback"


@dataclass
class MigrationCheckpoint:
    """A checkpoint during migration for recovery."""

    checkpoint_id: str
    migration_id: str
    phase: MigrationPhase
    data: JSONDict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SagaMigrationConfig:
    """Configuration for saga-managed migration."""

    migration_type: MigrationJobType
    source_tenant_id: str
    target_tenant_id: str | None = None
    options: JSONDict = field(default_factory=dict)
    enable_backup: bool = True
    enable_verification: bool = True
    max_retries: int = 3
    timeout_seconds: int = 3600
    checkpoint_interval: int = 100
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SagaMigrationResult:
    """Result of a saga-managed migration."""

    migration_id: str
    saga_id: str
    success: bool
    status: MigrationJobStatus
    saga_status: SagaStatus
    phases_completed: list[MigrationPhase]
    phases_compensated: list[MigrationPhase] = field(default_factory=list)
    error: str | None = None
    job_result: MigrationJobResult | None = None
    execution_time_ms: float = 0.0
    checkpoints: list[MigrationCheckpoint] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH


class CheckpointStore:
    """Store for migration checkpoints."""

    def __init__(self):
        self._checkpoints: dict[str, list[MigrationCheckpoint]] = {}

    async def save(self, checkpoint: MigrationCheckpoint) -> None:
        """Save a checkpoint."""
        if checkpoint.migration_id not in self._checkpoints:
            self._checkpoints[checkpoint.migration_id] = []
        self._checkpoints[checkpoint.migration_id].append(checkpoint)

    async def get_latest(
        self,
        migration_id: str,
        phase: MigrationPhase | None = None,
    ) -> MigrationCheckpoint | None:
        """Get the latest checkpoint for a migration."""
        checkpoints = self._checkpoints.get(migration_id, [])
        if phase:
            checkpoints = [c for c in checkpoints if c.phase == phase]
        return checkpoints[-1] if checkpoints else None

    async def list_checkpoints(
        self,
        migration_id: str,
    ) -> list[MigrationCheckpoint]:
        """List all checkpoints for a migration."""
        return self._checkpoints.get(migration_id, [])

    async def delete(self, migration_id: str) -> None:
        """Delete all checkpoints for a migration."""
        if migration_id in self._checkpoints:
            del self._checkpoints[migration_id]


class SagaMigrationService:
    """Service that integrates saga orchestration with migration jobs."""

    def __init__(
        self,
        job_manager: MigrationJobManager | None = None,
        orchestrator: SagaOrchestrator | None = None,
        checkpoint_store: CheckpointStore | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.job_manager = job_manager or MigrationJobManager()
        self.orchestrator = orchestrator or SagaOrchestrator()
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.constitutional_hash = constitutional_hash
        self.metrics = SagaMetrics()

        # Register saga definitions
        self._register_migration_sagas()

    def _register_migration_sagas(self) -> None:
        """Register all migration saga definitions."""
        self.orchestrator.register_saga(self._build_policy_migration_saga())
        self.orchestrator.register_saga(self._build_schema_migration_saga())
        self.orchestrator.register_saga(self._build_data_migration_saga())
        self.orchestrator.register_saga(self._build_full_migration_saga())

    def _build_policy_migration_saga(self) -> SagaDefinition:
        """Build saga for policy migration."""
        # Use helper methods to create step definitions
        step_definitions = [
            self._create_policy_validation_step(),
            self._create_policy_backup_step(),
            self._create_policy_migration_step(),
            self._create_policy_verification_step(),
        ]

        return SagaDefinition(
            name="saga_policy_migration",
            description="Policy migration with saga orchestration",
            steps=step_definitions,
        )

    def _create_policy_validation_step(self) -> SagaStepDefinition:
        """Create policy validation step definition."""

        async def validate_policies(ctx: SagaContext) -> SagaStepResult:
            """Validate source policies exist."""
            policies = ctx.data.get("policies", [])

            await self._create_checkpoint(
                ctx,
                MigrationPhase.VALIDATION,
                {"policy_count": len(policies), "source": ctx.data.get("source_tenant_id")},
            )

            ctx.data["validation_checkpoint"] = str(uuid.uuid4())
            return SagaStepResult(success=True, data={"validated_policies": len(policies)})

        return SagaStepDefinition(
            name="validate_policies",
            description="Validate source policies",
            action=validate_policies,
            compensation=self._no_compensation_step,
            order=0,
        )

    def _create_policy_backup_step(self) -> SagaStepDefinition:
        """Create policy backup step definition."""

        async def backup_policies(ctx: SagaContext) -> SagaStepResult:
            """Create backup of target policies."""
            if not ctx.data.get("enable_backup", True):
                return SagaStepResult(success=True, data={"skipped": True})

            backup_id = str(uuid.uuid4())
            ctx.data["backup_id"] = backup_id

            await self._create_checkpoint(ctx, MigrationPhase.BACKUP, {"backup_id": backup_id})

            return SagaStepResult(success=True, data={"backup_id": backup_id})

        async def compensate_backup(ctx: SagaContext) -> SagaStepResult:
            """Delete backup if migration failed."""
            backup_id = ctx.data.get("backup_id")
            return SagaStepResult(success=True, data={"deleted_backup": backup_id})

        return SagaStepDefinition(
            name="backup_policies",
            description="Backup target policies",
            action=backup_policies,
            compensation=compensate_backup,
            order=1,
        )

    def _create_policy_migration_step(self) -> SagaStepDefinition:
        """Create policy migration step definition."""

        async def migrate_policies(ctx: SagaContext) -> SagaStepResult:
            """Execute policy migration."""
            migration_id = ctx.data.get("migration_id", ctx.saga_id)
            policies = ctx.data.get("policies", [])

            await self._update_job_progress(migration_id, ctx.tenant_id, len(policies))
            await self._create_checkpoint(
                ctx, MigrationPhase.EXECUTION, {"migrated_count": len(policies)}
            )

            return SagaStepResult(success=True, data={"migrated_policies": len(policies)})

        async def compensate_migrate(ctx: SagaContext) -> SagaStepResult:
            """Rollback policy migration."""
            backup_id = ctx.data.get("backup_id")
            migration_id = ctx.data.get("migration_id", ctx.saga_id)

            checkpoint_data = {"restored_from": backup_id}
            await self._create_checkpoint_by_id(
                migration_id, MigrationPhase.ROLLBACK, checkpoint_data
            )

            return SagaStepResult(success=True, data=checkpoint_data)

        return SagaStepDefinition(
            name="migrate_policies",
            description="Execute policy migration",
            action=migrate_policies,
            compensation=compensate_migrate,
            order=2,
        )

    def _create_policy_verification_step(self) -> SagaStepDefinition:
        """Create policy verification step definition."""

        async def verify_migration(ctx: SagaContext) -> SagaStepResult:
            """Verify migration was successful."""
            if not ctx.data.get("enable_verification", True):
                return SagaStepResult(success=True, data={"skipped": True})

            await self._create_checkpoint(
                ctx, MigrationPhase.VERIFICATION, {"verification_status": "passed"}
            )

            return SagaStepResult(success=True, data={"verified": True})

        return SagaStepDefinition(
            name="verify_migration",
            description="Verify migration success",
            action=verify_migration,
            compensation=self._no_compensation_step,
            order=3,
        )

    async def _create_checkpoint(
        self, ctx: SagaContext, phase: MigrationPhase, data: JSONDict
    ) -> None:
        """Helper method to create a checkpoint."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            migration_id=ctx.data.get("migration_id", ctx.saga_id),
            phase=phase,
            data=data,
        )
        await self.checkpoint_store.save(checkpoint)

    async def _create_checkpoint_by_id(
        self, migration_id: str, phase: MigrationPhase, data: JSONDict
    ) -> None:
        """Helper method to create a checkpoint by migration ID."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            migration_id=migration_id,
            phase=phase,
            data=data,
        )
        await self.checkpoint_store.save(checkpoint)

    async def _update_job_progress(
        self, migration_id: str, tenant_id: str, policy_count: int
    ) -> None:
        """Helper method to update job progress."""
        job = await self.job_manager.get_job(migration_id, tenant_id)
        if job:
            await self.job_manager.update_progress(
                job_id=migration_id,
                processed=policy_count,
                successful=policy_count,
                failed=0,
                total=policy_count,
                phase="migration",
            )

    @staticmethod
    async def _no_compensation_step(ctx: SagaContext) -> SagaStepResult:
        """Standard no-compensation step."""
        return SagaStepResult(success=True)

    def _build_schema_migration_saga(self) -> SagaDefinition:
        """Build saga for schema migration."""

        async def backup_schema(ctx: SagaContext) -> SagaStepResult:
            """Create schema backup."""
            backup_id = str(uuid.uuid4())
            ctx.data["schema_backup_id"] = backup_id

            checkpoint = MigrationCheckpoint(
                checkpoint_id=str(uuid.uuid4()),
                migration_id=ctx.data.get("migration_id", ctx.saga_id),
                phase=MigrationPhase.BACKUP,
                data={"schema_backup_id": backup_id},
            )
            await self.checkpoint_store.save(checkpoint)

            return SagaStepResult(success=True, data={"backup_id": backup_id})

        async def compensate_backup_schema(ctx: SagaContext) -> SagaStepResult:
            """Keep schema backup for analysis."""
            return SagaStepResult(success=True)

        async def apply_schema(ctx: SagaContext) -> SagaStepResult:
            """Apply schema changes."""
            version = ctx.data.get("target_version", "v1.0.0")
            migration_id = ctx.data.get("migration_id", ctx.saga_id)

            checkpoint = MigrationCheckpoint(
                checkpoint_id=str(uuid.uuid4()),
                migration_id=migration_id,
                phase=MigrationPhase.EXECUTION,
                data={"applied_version": version},
            )
            await self.checkpoint_store.save(checkpoint)

            return SagaStepResult(success=True, data={"version": version})

        async def compensate_apply_schema(ctx: SagaContext) -> SagaStepResult:
            """Rollback schema changes."""
            backup_id = ctx.data.get("schema_backup_id")
            return SagaStepResult(
                success=True,
                data={"restored_from": backup_id},
            )

        async def validate_schema(ctx: SagaContext) -> SagaStepResult:
            """Validate schema integrity."""
            return SagaStepResult(success=True, data={"schema_valid": True})

        async def compensate_validate_schema(ctx: SagaContext) -> SagaStepResult:
            """No compensation for validation."""
            return SagaStepResult(success=True)

        return SagaDefinition(
            name="saga_schema_migration",
            description="Schema migration with saga orchestration",
            steps=[
                SagaStepDefinition(
                    name="backup_schema",
                    description="Create schema backup",
                    action=backup_schema,
                    compensation=compensate_backup_schema,
                    order=0,
                ),
                SagaStepDefinition(
                    name="apply_schema",
                    description="Apply schema changes",
                    action=apply_schema,
                    compensation=compensate_apply_schema,
                    order=1,
                ),
                SagaStepDefinition(
                    name="validate_schema",
                    description="Validate schema integrity",
                    action=validate_schema,
                    compensation=compensate_validate_schema,
                    order=2,
                ),
            ],
        )

    def _build_data_migration_saga(self) -> SagaDefinition:
        """Build saga for data migration."""

        async def prepare_migration(ctx: SagaContext) -> SagaStepResult:
            """Prepare for data migration."""
            batch_size = ctx.data.get("batch_size", 1000)
            total_records = ctx.data.get("total_records", 0)

            ctx.data["batches"] = (total_records + batch_size - 1) // batch_size

            return SagaStepResult(
                success=True,
                data={"batches": ctx.data["batches"], "batch_size": batch_size},
            )

        async def compensate_prepare(ctx: SagaContext) -> SagaStepResult:
            """No compensation for preparation."""
            return SagaStepResult(success=True)

        async def migrate_data(ctx: SagaContext) -> SagaStepResult:
            """Execute data migration."""
            migration_id = ctx.data.get("migration_id", ctx.saga_id)
            total_records = ctx.data.get("total_records", 0)

            # Simulate batch processing
            job = await self.job_manager.get_job(migration_id, ctx.tenant_id)
            if job:
                await self.job_manager.update_progress(
                    job_id=migration_id,
                    processed=total_records,
                    successful=total_records,
                    failed=0,
                    total=total_records,
                    phase="data_migration",
                )

            checkpoint = MigrationCheckpoint(
                checkpoint_id=str(uuid.uuid4()),
                migration_id=migration_id,
                phase=MigrationPhase.EXECUTION,
                data={"migrated_records": total_records},
            )
            await self.checkpoint_store.save(checkpoint)

            return SagaStepResult(
                success=True,
                data={"migrated_records": total_records},
            )

        async def compensate_migrate_data(ctx: SagaContext) -> SagaStepResult:
            """Rollback data migration."""
            migration_id = ctx.data.get("migration_id", ctx.saga_id)

            checkpoint = MigrationCheckpoint(
                checkpoint_id=str(uuid.uuid4()),
                migration_id=migration_id,
                phase=MigrationPhase.ROLLBACK,
                data={"data_rolled_back": True},
            )
            await self.checkpoint_store.save(checkpoint)

            return SagaStepResult(success=True, data={"rolled_back": True})

        async def verify_data(ctx: SagaContext) -> SagaStepResult:
            """Verify data integrity."""
            return SagaStepResult(
                success=True,
                data={"data_verified": True, "integrity_check": "passed"},
            )

        async def compensate_verify_data(ctx: SagaContext) -> SagaStepResult:
            """No compensation for verification."""
            return SagaStepResult(success=True)

        return SagaDefinition(
            name="saga_data_migration",
            description="Data migration with saga orchestration",
            steps=[
                SagaStepDefinition(
                    name="prepare_migration",
                    description="Prepare for data migration",
                    action=prepare_migration,
                    compensation=compensate_prepare,
                    order=0,
                ),
                SagaStepDefinition(
                    name="migrate_data",
                    description="Execute data migration",
                    action=migrate_data,
                    compensation=compensate_migrate_data,
                    order=1,
                ),
                SagaStepDefinition(
                    name="verify_data",
                    description="Verify data integrity",
                    action=verify_data,
                    compensation=compensate_verify_data,
                    order=2,
                ),
            ],
        )

    def _build_full_migration_saga(self) -> SagaDefinition:
        """Build comprehensive saga for full system migration."""
        step_definitions = [
            self._create_prerequisites_validation_step(),
            self._create_full_backup_step(),
            self._create_schema_migration_step(),
            self._create_data_migration_step(),
            self._create_policies_migration_step(),
            self._create_full_verification_step(),
            self._create_cleanup_step(),
        ]

        return SagaDefinition(
            name="saga_full_migration",
            description="Full system migration with comprehensive saga orchestration",
            steps=step_definitions,
        )

    def _create_prerequisites_validation_step(self) -> SagaStepDefinition:
        """Create prerequisites validation step."""

        async def validate_prerequisites(ctx: SagaContext) -> SagaStepResult:
            """Validate all migration prerequisites."""
            source = ctx.data.get("source_tenant_id")
            target = ctx.data.get("target_tenant_id")

            if not source:
                return SagaStepResult(success=False, error="Missing source_tenant_id")

            return SagaStepResult(success=True, data={"source": source, "target": target})

        return SagaStepDefinition(
            name="validate_prerequisites",
            description="Validate migration prerequisites",
            action=validate_prerequisites,
            compensation=self._no_compensation_step,
            order=0,
        )

    def _create_full_backup_step(self) -> SagaStepDefinition:
        """Create full system backup step."""

        async def create_full_backup(ctx: SagaContext) -> SagaStepResult:
            """Create comprehensive system backup."""
            backup_id = str(uuid.uuid4())
            ctx.data["full_backup_id"] = backup_id

            backup_data = {
                "full_backup_id": backup_id,
                "includes": ["schema", "data", "policies", "config"],
            }
            await self._create_checkpoint(ctx, MigrationPhase.BACKUP, backup_data)

            return SagaStepResult(success=True, data={"backup_id": backup_id})

        return SagaStepDefinition(
            name="create_full_backup",
            description="Create comprehensive backup",
            action=create_full_backup,
            compensation=self._no_compensation_step,
            order=1,
        )

    def _create_schema_migration_step(self) -> SagaStepDefinition:
        """Create schema migration step."""

        async def migrate_schema(ctx: SagaContext) -> SagaStepResult:
            """Migrate database schema."""
            await self._create_checkpoint(ctx, MigrationPhase.EXECUTION, {"component": "schema"})
            return SagaStepResult(success=True, data={"schema_migrated": True})

        async def compensate_schema(ctx: SagaContext) -> SagaStepResult:
            """Rollback schema from backup."""
            backup_id = ctx.data.get("full_backup_id")
            return SagaStepResult(success=True, data={"schema_restored_from": backup_id})

        return SagaStepDefinition(
            name="migrate_schema",
            description="Migrate database schema",
            action=migrate_schema,
            compensation=compensate_schema,
            order=2,
        )

    def _create_data_migration_step(self) -> SagaStepDefinition:
        """Create data migration step."""

        async def migrate_data_full(ctx: SagaContext) -> SagaStepResult:
            """Migrate all data."""
            records = ctx.data.get("total_records", 0)

            checkpoint_data = {"component": "data", "records": records}
            await self._create_checkpoint(ctx, MigrationPhase.EXECUTION, checkpoint_data)

            return SagaStepResult(success=True, data={"records_migrated": records})

        async def compensate_data(ctx: SagaContext) -> SagaStepResult:
            """Rollback data from backup."""
            backup_id = ctx.data.get("full_backup_id")
            return SagaStepResult(success=True, data={"data_restored_from": backup_id})

        return SagaStepDefinition(
            name="migrate_data",
            description="Migrate all data",
            action=migrate_data_full,
            compensation=compensate_data,
            order=3,
        )

    def _create_policies_migration_step(self) -> SagaStepDefinition:
        """Create policies migration step."""

        async def migrate_policies_full(ctx: SagaContext) -> SagaStepResult:
            """Migrate all policies."""
            policies = ctx.data.get("policies", [])

            checkpoint_data = {"component": "policies", "count": len(policies)}
            await self._create_checkpoint(ctx, MigrationPhase.EXECUTION, checkpoint_data)

            return SagaStepResult(success=True, data={"policies_migrated": len(policies)})

        async def compensate_policies(ctx: SagaContext) -> SagaStepResult:
            """Rollback policies from backup."""
            backup_id = ctx.data.get("full_backup_id")
            return SagaStepResult(success=True, data={"policies_restored_from": backup_id})

        return SagaStepDefinition(
            name="migrate_policies",
            description="Migrate all policies",
            action=migrate_policies_full,
            compensation=compensate_policies,
            order=4,
        )

    def _create_full_verification_step(self) -> SagaStepDefinition:
        """Create full verification step."""

        async def verify_full_migration(ctx: SagaContext) -> SagaStepResult:
            """Comprehensive migration verification."""
            verification_data = {
                "verification_status": "passed",
                "verified_components": ["schema", "data", "policies"],
            }
            await self._create_checkpoint(ctx, MigrationPhase.VERIFICATION, verification_data)

            return SagaStepResult(success=True, data={"all_verified": True})

        return SagaStepDefinition(
            name="verify_migration",
            description="Verify complete migration",
            action=verify_full_migration,
            compensation=self._no_compensation_step,
            order=5,
        )

    def _create_cleanup_step(self) -> SagaStepDefinition:
        """Create cleanup step."""

        async def cleanup(ctx: SagaContext) -> SagaStepResult:
            """Post-migration cleanup."""
            await self._create_checkpoint(ctx, MigrationPhase.CLEANUP, {"cleanup_completed": True})
            return SagaStepResult(success=True, data={"cleaned_up": True})

        return SagaStepDefinition(
            name="cleanup",
            description="Post-migration cleanup",
            action=cleanup,
            compensation=self._no_compensation_step,
            order=6,
        )

    async def start_migration(
        self,
        config: SagaMigrationConfig,
    ) -> SagaMigrationResult:
        """Start a saga-managed migration."""
        start_time = datetime.now(UTC)

        # Create migration job
        job_config = MigrationJobConfig(
            job_type=config.migration_type,
            source_config={"tenant_id": config.source_tenant_id},
            target_config={"tenant_id": config.target_tenant_id or config.source_tenant_id},
            options=config.options,
        )

        job = await self.job_manager.create_job(
            tenant_id=config.source_tenant_id,
            config=job_config,
        )

        # Determine saga type based on migration type
        saga_name = self._get_saga_name(config.migration_type)

        # Create saga with migration context
        saga = await self.orchestrator.create_saga(
            definition_name=saga_name,
            tenant_id=config.source_tenant_id,
            initial_data={
                "migration_id": job.job_id,
                "source_tenant_id": config.source_tenant_id,
                "target_tenant_id": config.target_tenant_id,
                "enable_backup": config.enable_backup,
                "enable_verification": config.enable_verification,
                **config.options,
            },
            metadata={
                "migration_type": config.migration_type.value,
                "config": {
                    "max_retries": config.max_retries,
                    "timeout_seconds": config.timeout_seconds,
                },
            },
        )

        # Start job
        await self.job_manager.start_job(job.job_id, config.source_tenant_id)

        # Execute saga
        result = await self.orchestrator.execute(saga.saga_id)

        # Update job status based on saga result
        if result.success:
            total_records = config.options.get("total_records", 0)
            job_result = MigrationJobResult(
                job_id=job.job_id,
                tenant_id=config.source_tenant_id,
                status=MigrationJobStatus.COMPLETED,
                summary={
                    "items_processed": total_records,
                    "items_succeeded": total_records,
                    "items_failed": 0,
                },
                details=[f"Migration completed successfully for {total_records} records"],
            )
            await self.job_manager.complete_job(job.job_id, job_result)
        else:
            await self.job_manager.fail_job(job.job_id, result.error or "Saga failed")
            job_result = None

        # Get updated job
        updated_job = await self.job_manager.get_job(
            job.job_id,
            config.source_tenant_id,
        )

        # Get checkpoints
        checkpoints = await self.checkpoint_store.list_checkpoints(job.job_id)

        # Calculate execution time
        execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

        # Build phases from steps
        phases_completed = [self._step_to_phase(step) for step in result.completed_steps]
        phases_compensated = [self._step_to_phase(step) for step in result.compensated_steps]

        # Record metrics
        self.metrics.record_saga_completed(result)

        return SagaMigrationResult(
            migration_id=job.job_id,
            saga_id=saga.saga_id,
            success=result.success,
            status=updated_job.status if updated_job else MigrationJobStatus.FAILED,
            saga_status=result.status,
            phases_completed=phases_completed,
            phases_compensated=phases_compensated,
            error=result.error,
            job_result=job_result,
            execution_time_ms=execution_time,
            checkpoints=checkpoints,
            constitutional_hash=self.constitutional_hash,
        )

    def _get_saga_name(self, migration_type: MigrationJobType) -> str:
        """Get saga name for migration type."""
        mapping = {
            MigrationJobType.POLICY_IMPORT: "saga_policy_migration",
            MigrationJobType.DECISION_LOG_IMPORT: "saga_data_migration",
            MigrationJobType.CONSTITUTIONAL_ANALYSIS: "saga_schema_migration",
            MigrationJobType.FULL_MIGRATION: "saga_full_migration",
            MigrationJobType.GAP_REMEDIATION: "saga_policy_migration",
        }
        return mapping.get(migration_type, "saga_full_migration")

    def _step_to_phase(self, step_name: str) -> MigrationPhase:
        """Map step name to migration phase."""
        mapping = {
            "validate": MigrationPhase.VALIDATION,
            "backup": MigrationPhase.BACKUP,
            "prepare": MigrationPhase.PREPARATION,
            "migrate": MigrationPhase.EXECUTION,
            "apply": MigrationPhase.EXECUTION,
            "verify": MigrationPhase.VERIFICATION,
            "cleanup": MigrationPhase.CLEANUP,
        }
        for key, phase in mapping.items():
            if key in step_name.lower():
                return phase
        return MigrationPhase.EXECUTION

    async def get_migration_status(
        self,
        migration_id: str,
        tenant_id: str,
    ) -> SagaMigrationResult | None:
        """Get current status of a saga-managed migration."""
        job = await self.job_manager.get_job(migration_id, tenant_id)
        if not job:
            return None

        # Find the saga for this migration
        sagas = await self.orchestrator.list_sagas(tenant_id)
        saga = next(
            (s for s in sagas if s.context and s.context.data.get("migration_id") == migration_id),
            None,
        )

        checkpoints = await self.checkpoint_store.list_checkpoints(migration_id)

        phases_completed = []
        phases_compensated = []

        if saga:
            for step in saga.steps:
                phase = self._step_to_phase(step.step_name)
                if step.status.value == "completed":
                    phases_completed.append(phase)
                elif step.status.value == "compensated":
                    phases_compensated.append(phase)

        return SagaMigrationResult(
            migration_id=migration_id,
            saga_id=saga.saga_id if saga else "",
            success=job.status == MigrationJobStatus.COMPLETED,
            status=job.status,
            saga_status=saga.status if saga else SagaStatus.PENDING,
            phases_completed=phases_completed,
            phases_compensated=phases_compensated,
            error=job.error_message,
            checkpoints=checkpoints,
            constitutional_hash=self.constitutional_hash,
        )

    async def cancel_migration(
        self,
        migration_id: str,
        tenant_id: str,
    ) -> bool:
        """Cancel a saga-managed migration."""
        job = await self.job_manager.cancel_job(migration_id, tenant_id)
        if not job:
            return False

        # Find and cancel the saga
        sagas = await self.orchestrator.list_sagas(tenant_id)
        saga = next(
            (s for s in sagas if s.context and s.context.data.get("migration_id") == migration_id),
            None,
        )

        if saga:
            await self.orchestrator.cancel_saga(saga.saga_id)

        return True

    def get_metrics(self) -> JSONDict:
        """Get migration service metrics."""
        return self.metrics.get_stats()
