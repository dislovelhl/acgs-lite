"""
Tests for Saga Orchestrator.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enterprise_sso.saga_orchestration import (
    SagaDefinition,
    SagaEventPublisher,
    SagaEventType,
    SagaOrchestrator,
    SagaStatus,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaOrchestrator:
    """Tests for saga orchestration."""

    def test_register_saga_definition(
        self, orchestrator: SagaOrchestrator, simple_saga_definition: SagaDefinition
    ):
        """Test registering a saga definition."""
        orchestrator.register_saga(simple_saga_definition)
        retrieved = orchestrator.get_definition("simple_saga")

        assert retrieved is not None
        assert retrieved.name == "simple_saga"
        assert len(retrieved.steps) == 2

    async def test_create_saga(
        self, orchestrator: SagaOrchestrator, simple_saga_definition: SagaDefinition
    ):
        """Test creating a saga instance."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
            initial_data={"key": "value"},
        )

        assert saga is not None
        assert saga.status == SagaStatus.PENDING
        assert saga.tenant_id == "tenant-001"
        assert saga.context is not None
        assert saga.context.data["key"] == "value"
        assert len(saga.steps) == 2

    async def test_create_saga_unknown_definition(self, orchestrator: SagaOrchestrator):
        """Test creating a saga with unknown definition."""
        with pytest.raises(ValueError, match="Unknown saga definition"):
            await orchestrator.create_saga(
                definition_name="unknown_saga",
                tenant_id="tenant-001",
            )

    async def test_execute_successful_saga(
        self, orchestrator: SagaOrchestrator, simple_saga_definition: SagaDefinition
    ):
        """Test executing a saga successfully."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
        )

        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        assert result.status == SagaStatus.COMPLETED
        assert len(result.completed_steps) == 2
        assert "step1" in result.completed_steps
        assert "step2" in result.completed_steps
        assert result.failed_step is None

    async def test_execute_failing_saga_with_compensation(
        self,
        orchestrator: SagaOrchestrator,
        failing_saga_definition: SagaDefinition,
    ):
        """Test executing a saga that fails and triggers compensation."""
        orchestrator.register_saga(failing_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="failing_saga",
            tenant_id="tenant-001",
        )

        result = await orchestrator.execute(saga.saga_id)

        assert result.success is False
        assert result.status == SagaStatus.COMPENSATED
        assert "step1" in result.completed_steps
        assert result.failed_step == "step2"
        assert "step1" in result.compensated_steps

    async def test_execute_nonexistent_saga(self, orchestrator: SagaOrchestrator):
        """Test executing a non-existent saga."""
        with pytest.raises(ValueError, match="Saga not found"):
            await orchestrator.execute("nonexistent-saga")

    async def test_saga_step_results_stored_in_context(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test that step results are stored in context."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
        )

        await orchestrator.execute(saga.saga_id)

        updated_saga = await orchestrator.get_saga(saga.saga_id)
        assert updated_saga is not None
        assert updated_saga.context is not None
        assert "step1" in updated_saga.context.step_results
        assert "step2" in updated_saga.context.step_results

    async def test_saga_events_recorded(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
        event_publisher: SagaEventPublisher,
    ):
        """Test that saga events are recorded."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
        )

        await orchestrator.execute(saga.saga_id)

        events = event_publisher.get_events(saga_id=saga.saga_id)
        event_types = [e.event_type for e in events]

        assert SagaEventType.SAGA_STARTED in event_types
        assert SagaEventType.SAGA_COMPLETED in event_types
        assert SagaEventType.STEP_STARTED in event_types
        assert SagaEventType.STEP_COMPLETED in event_types

    async def test_cancel_pending_saga(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test cancelling a pending saga."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
        )

        result = await orchestrator.cancel_saga(saga.saga_id)
        assert result is True

        updated_saga = await orchestrator.get_saga(saga.saga_id)
        assert updated_saga is not None
        assert updated_saga.status == SagaStatus.COMPENSATED

    async def test_cancel_completed_saga_fails(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test that cancelling a completed saga fails."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
        )

        await orchestrator.execute(saga.saga_id)

        result = await orchestrator.cancel_saga(saga.saga_id)
        assert result is False

    async def test_list_sagas(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test listing sagas for a tenant."""
        orchestrator.register_saga(simple_saga_definition)

        await orchestrator.create_saga("simple_saga", "tenant-001")
        await orchestrator.create_saga("simple_saga", "tenant-001")
        await orchestrator.create_saga("simple_saga", "tenant-002")

        tenant1_sagas = await orchestrator.list_sagas("tenant-001")
        assert len(tenant1_sagas) == 2

        tenant2_sagas = await orchestrator.list_sagas("tenant-002")
        assert len(tenant2_sagas) == 1
