"""
Tests for Saga Compensation.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enterprise_sso.saga_orchestration import (
    CompensationStrategy,
    SagaContext,
    SagaDefinition,
    SagaOrchestrator,
    SagaStatus,
    SagaStepDefinition,
    SagaStepResult,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaCompensation:
    """Tests for saga compensation logic."""

    async def test_compensation_in_reverse_order(self, orchestrator: SagaOrchestrator):
        """Test that compensation happens in reverse order."""
        compensation_order: list[str] = []

        async def step1_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step1_compensation(ctx: SagaContext) -> SagaStepResult:
            compensation_order.append("step1")
            return SagaStepResult(success=True)

        async def step2_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step2_compensation(ctx: SagaContext) -> SagaStepResult:
            compensation_order.append("step2")
            return SagaStepResult(success=True)

        async def step3_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=False, error="Failure")

        async def step3_compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="order_saga",
            description="Test compensation order",
            steps=[
                SagaStepDefinition(
                    name="step1",
                    description="First step",
                    action=step1_action,
                    compensation=step1_compensation,
                    max_retries=0,
                    order=0,
                ),
                SagaStepDefinition(
                    name="step2",
                    description="Second step",
                    action=step2_action,
                    compensation=step2_compensation,
                    max_retries=0,
                    order=1,
                ),
                SagaStepDefinition(
                    name="step3",
                    description="Failing step",
                    action=step3_action,
                    compensation=step3_compensation,
                    max_retries=0,
                    order=2,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("order_saga", "tenant-001")
        await orchestrator.execute(saga.saga_id)

        # Compensation should be in reverse order
        assert compensation_order == ["step2", "step1"]

    async def test_compensation_with_skip_strategy(self, orchestrator: SagaOrchestrator):
        """Test compensation with SKIP strategy for failed compensations."""

        async def step1_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step1_compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=False, error="Compensation failed")

        async def step2_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=False, error="Failure")

        async def step2_compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="skip_saga",
            description="Test skip strategy",
            steps=[
                SagaStepDefinition(
                    name="step1",
                    description="First step",
                    action=step1_action,
                    compensation=step1_compensation,
                    compensation_strategy=CompensationStrategy.SKIP,
                    max_retries=0,
                    order=0,
                ),
                SagaStepDefinition(
                    name="step2",
                    description="Failing step",
                    action=step2_action,
                    compensation=step2_compensation,
                    max_retries=0,
                    order=1,
                ),
            ],
            max_compensation_retries=0,
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("skip_saga", "tenant-001")
        result = await orchestrator.execute(saga.saga_id)

        # With SKIP strategy, saga should be marked as compensated
        assert result.status == SagaStatus.COMPENSATED

    async def test_partial_compensation(self, orchestrator: SagaOrchestrator):
        """Test partial compensation when some compensations fail."""

        async def step1_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step1_compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=False, error="Failed")

        async def step2_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step2_compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step3_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=False, error="Failure")

        async def step3_compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="partial_saga",
            description="Test partial compensation",
            steps=[
                SagaStepDefinition(
                    name="step1",
                    description="First step",
                    action=step1_action,
                    compensation=step1_compensation,
                    compensation_strategy=CompensationStrategy.FAIL,
                    max_retries=0,
                    order=0,
                ),
                SagaStepDefinition(
                    name="step2",
                    description="Second step",
                    action=step2_action,
                    compensation=step2_compensation,
                    max_retries=0,
                    order=1,
                ),
                SagaStepDefinition(
                    name="step3",
                    description="Failing step",
                    action=step3_action,
                    compensation=step3_compensation,
                    max_retries=0,
                    order=2,
                ),
            ],
            max_compensation_retries=0,
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("partial_saga", "tenant-001")
        result = await orchestrator.execute(saga.saga_id)

        assert result.status == SagaStatus.PARTIALLY_COMPENSATED
        assert "step2" in result.compensated_steps
        assert "step1" not in result.compensated_steps
