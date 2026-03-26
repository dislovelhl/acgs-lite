"""
Tests for Migration Saga Builder.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enterprise_sso.saga_orchestration import (
    MigrationSagaBuilder,
    SagaOrchestrator,
    SagaStatus,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMigrationSagaBuilder:
    """Tests for migration-specific saga builders."""

    def test_build_policy_migration_saga(self, orchestrator: SagaOrchestrator):
        """Test building policy migration saga."""
        builder = MigrationSagaBuilder(orchestrator)
        definition = builder.build_policy_migration_saga()

        assert definition.name == "policy_migration"
        assert len(definition.steps) == 5
        step_names = [s.name for s in definition.steps]
        assert "validate_source" in step_names
        assert "export_policies" in step_names
        assert "transform_policies" in step_names
        assert "import_policies" in step_names
        assert "verify_migration" in step_names

    def test_build_database_migration_saga(self, orchestrator: SagaOrchestrator):
        """Test building database migration saga."""
        builder = MigrationSagaBuilder(orchestrator)
        definition = builder.build_database_migration_saga()

        assert definition.name == "database_migration"
        assert len(definition.steps) == 4
        step_names = [s.name for s in definition.steps]
        assert "backup_database" in step_names
        assert "apply_schema_changes" in step_names
        assert "migrate_data" in step_names
        assert "validate_migration" in step_names

    async def test_execute_policy_migration_saga(self, orchestrator: SagaOrchestrator):
        """Test executing policy migration saga."""
        builder = MigrationSagaBuilder(orchestrator)
        definition = builder.build_policy_migration_saga()
        orchestrator.register_saga(definition)

        saga = await orchestrator.create_saga(
            definition_name="policy_migration",
            tenant_id="tenant-001",
            initial_data={
                "source_tenant_id": "source-tenant",
                "target_tenant_id": "target-tenant",
                "policies": ["policy1", "policy2"],
            },
        )

        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        assert result.status == SagaStatus.COMPLETED
        assert len(result.completed_steps) == 5

    async def test_execute_database_migration_saga(self, orchestrator: SagaOrchestrator):
        """Test executing database migration saga."""
        builder = MigrationSagaBuilder(orchestrator)
        definition = builder.build_database_migration_saga()
        orchestrator.register_saga(definition)

        saga = await orchestrator.create_saga(
            definition_name="database_migration",
            tenant_id="tenant-001",
            initial_data={
                "target_version": "v2.0.0",
                "expected_records": 1000,
            },
        )

        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        assert result.status == SagaStatus.COMPLETED
