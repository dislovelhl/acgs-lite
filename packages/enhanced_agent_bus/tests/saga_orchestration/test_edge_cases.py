"""
Tests for Edge Cases in Saga Orchestration.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enterprise_sso.saga_orchestration import (
    SagaContext,
    SagaDefinition,
    SagaOrchestrator,
    SagaStatus,
    SagaStepDefinition,
    SagaStepResult,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    async def test_empty_saga_definition(self, orchestrator: SagaOrchestrator):
        """Test saga with no steps."""
        definition = SagaDefinition(
            name="empty_saga",
            description="Empty saga",
            steps=[],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("empty_saga", "tenant-001")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        assert result.status == SagaStatus.COMPLETED
        assert len(result.completed_steps) == 0

    async def test_saga_with_metadata(
        self,
        orchestrator: SagaOrchestrator,
        simple_saga_definition: SagaDefinition,
    ):
        """Test saga creation with metadata."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
            initial_data={"key": "value"},
            metadata={"source": "test", "priority": "high"},
        )

        assert saga.context is not None
        assert saga.context.metadata["source"] == "test"
        assert saga.context.metadata["priority"] == "high"

    async def test_cancel_nonexistent_saga(self, orchestrator: SagaOrchestrator):
        """Test cancelling a non-existent saga."""
        result = await orchestrator.cancel_saga("nonexistent")
        assert result is False

    async def test_step_order_sorting(self, orchestrator: SagaOrchestrator):
        """Test that steps are sorted by order."""

        async def action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        # Define steps out of order
        definition = SagaDefinition(
            name="order_saga",
            description="Test order",
            steps=[
                SagaStepDefinition(
                    name="step3",
                    description="Third",
                    action=action,
                    compensation=compensation,
                    order=2,
                ),
                SagaStepDefinition(
                    name="step1",
                    description="First",
                    action=action,
                    compensation=compensation,
                    order=0,
                ),
                SagaStepDefinition(
                    name="step2",
                    description="Second",
                    action=action,
                    compensation=compensation,
                    order=1,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        retrieved = orchestrator.get_definition("order_saga")

        assert retrieved is not None
        assert [s.name for s in retrieved.steps] == ["step1", "step2", "step3"]
