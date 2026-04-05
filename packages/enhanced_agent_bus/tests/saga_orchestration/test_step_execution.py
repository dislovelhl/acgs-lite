"""
Tests for Saga Step Execution.
Constitutional Hash: 608508a9bd224290
"""

import asyncio

import pytest

from enterprise_sso.saga_orchestration import (
    SagaContext,
    SagaDefinition,
    SagaOrchestrator,
    SagaStepDefinition,
    SagaStepResult,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaStepExecution:
    """Tests for individual saga step execution."""

    async def test_step_with_timeout(self, orchestrator: SagaOrchestrator):
        """Test step execution with timeout."""

        async def slow_action(ctx: SagaContext) -> SagaStepResult:
            await asyncio.sleep(2)  # Longer than timeout
            return SagaStepResult(success=True)

        async def compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="timeout_saga",
            description="Saga with timeout",
            steps=[
                SagaStepDefinition(
                    name="slow_step",
                    description="Slow step",
                    action=slow_action,
                    compensation=compensation,
                    timeout_seconds=1,
                    max_retries=0,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("timeout_saga", "tenant-001")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is False
        assert "timed out" in result.error.lower()

    async def test_step_with_retries(self, orchestrator: SagaOrchestrator):
        """Test step execution with retries."""
        attempt_count = 0

        async def flaky_action(ctx: SagaContext) -> SagaStepResult:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return SagaStepResult(success=False, error="Temporary failure")
            return SagaStepResult(success=True)

        async def compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="retry_saga",
            description="Saga with retries",
            steps=[
                SagaStepDefinition(
                    name="flaky_step",
                    description="Flaky step",
                    action=flaky_action,
                    compensation=compensation,
                    max_retries=3,
                    retry_delay_seconds=0,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("retry_saga", "tenant-001")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        assert attempt_count == 3

    async def test_step_exception_triggers_compensation(self, orchestrator: SagaOrchestrator):
        """Test that step exceptions trigger compensation."""

        async def step1_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step1_compensation(ctx: SagaContext) -> SagaStepResult:
            ctx.data["step1_compensated"] = True
            return SagaStepResult(success=True)

        async def step2_action(ctx: SagaContext) -> SagaStepResult:
            raise ValueError("Unexpected error")

        async def step2_compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="exception_saga",
            description="Saga with exception",
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
                    description="Exception step",
                    action=step2_action,
                    compensation=step2_compensation,
                    max_retries=0,
                    order=1,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("exception_saga", "tenant-001")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is False
        assert "step1" in result.compensated_steps
