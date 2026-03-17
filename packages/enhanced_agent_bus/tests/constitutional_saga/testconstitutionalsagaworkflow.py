"""
Comprehensive tests for Constitutional Saga workflow module.
Constitutional Hash: cdd01ef066bc6cf2

Coverage targets:
- SagaStatus and StepStatus enums
- SagaCompensation, SagaStep, SagaContext, SagaResult, SagaState dataclasses
- FileSagaPersistenceProvider
- DefaultSagaActivities
- Saga execution and compensation flow
"""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.deliberation_layer.workflows.constitutional_saga import (
    CONSTITUTIONAL_HASH,
    ConstitutionalSagaWorkflow,
    DefaultSagaActivities,
    FileSagaPersistenceProvider,
    SagaCompensation,
    SagaContext,
    SagaResult,
    SagaState,
    SagaStatus,
    SagaStep,
    StepStatus,
)


class TestConstitutionalSagaWorkflow:
    """Tests for ConstitutionalSagaWorkflow."""

    @pytest.fixture
    def activities(self):
        """Create activities instance."""
        return DefaultSagaActivities()

    @pytest.fixture
    def saga(self, activities):
        """Create saga workflow instance."""
        return ConstitutionalSagaWorkflow(
            saga_id="test-saga",
            activities=activities,
        )

    def test_initialization(self, saga):
        """Test saga initialization."""
        assert saga.saga_id == "test-saga"
        assert saga.version == "1.0.0"
        assert saga._status == SagaStatus.PENDING
        assert saga._steps == []
        assert saga._compensations == []
        assert saga._completed_steps == []
        assert saga._failed_step is None

    def test_add_step_returns_self(self, saga):
        """Test add_step returns self for chaining."""

        async def execute(ctx):
            return "result"

        step = SagaStep(name="step1", execute=execute)
        result = saga.add_step(step)

        assert result is saga
        assert len(saga._steps) == 1

    def test_add_multiple_steps(self, saga):
        """Test adding multiple steps via chaining."""

        async def execute1(ctx):
            return "result1"

        async def execute2(ctx):
            return "result2"

        saga.add_step(SagaStep(name="step1", execute=execute1)).add_step(
            SagaStep(name="step2", execute=execute2)
        )

        assert len(saga._steps) == 2
        assert saga._steps[0].name == "step1"
        assert saga._steps[1].name == "step2"

    def test_get_status(self, saga):
        """Test get_status method."""
        assert saga.get_status() == SagaStatus.PENDING

        saga._status = SagaStatus.EXECUTING
        assert saga.get_status() == SagaStatus.EXECUTING

    @pytest.mark.asyncio
    async def test_execute_empty_saga(self, saga):
        """Test executing saga with no steps."""
        result = await saga.execute()

        assert result.saga_id == "test-saga"
        assert result.status == SagaStatus.COMPLETED
        assert result.completed_steps == []
        assert result.failed_step is None

    @pytest.mark.asyncio
    async def test_execute_single_step_success(self, saga):
        """Test executing saga with single successful step."""

        async def execute(ctx):
            return {"data": "success"}

        saga.add_step(SagaStep(name="single_step", execute=execute))

        result = await saga.execute()

        assert result.status == SagaStatus.COMPLETED
        assert "single_step" in result.completed_steps
        assert result.context.get_step_result("single_step") == {"data": "success"}

    @pytest.mark.asyncio
    async def test_execute_multiple_steps_success(self, saga):
        """Test executing saga with multiple successful steps."""

        async def step1(ctx):
            return "step1_result"

        async def step2(ctx):
            return "step2_result"

        async def step3(ctx):
            return "step3_result"

        saga.add_step(SagaStep(name="step1", execute=step1))
        saga.add_step(SagaStep(name="step2", execute=step2))
        saga.add_step(SagaStep(name="step3", execute=step3))

        result = await saga.execute()

        assert result.status == SagaStatus.COMPLETED
        assert result.completed_steps == ["step1", "step2", "step3"]
        assert result.context.get_step_result("step1") == "step1_result"
        assert result.context.get_step_result("step2") == "step2_result"
        assert result.context.get_step_result("step3") == "step3_result"

    @pytest.mark.asyncio
    async def test_execute_step_failure_triggers_compensation(self, saga):
        """Test that step failure triggers compensation."""
        compensation_called = {"count": 0}

        async def step1(ctx):
            return "success"

        async def step2(ctx):
            raise ValueError("Step 2 failed")

        async def compensate1(ctx):
            compensation_called["count"] += 1
            return True

        saga.add_step(
            SagaStep(
                name="step1",
                execute=step1,
                compensation=SagaCompensation(name="comp1", execute=compensate1),
                max_retries=1,
            )
        )
        saga.add_step(
            SagaStep(
                name="step2",
                execute=step2,
                max_retries=1,
            )
        )

        result = await saga.execute()

        assert result.status == SagaStatus.COMPENSATED
        assert result.failed_step == "step2"
        assert "comp1" in result.compensated_steps
        assert compensation_called["count"] == 1

    @pytest.mark.asyncio
    async def test_compensation_lifo_order(self, saga):
        """Test that compensations run in LIFO order."""
        compensation_order = []

        async def step1(ctx):
            return "s1"

        async def step2(ctx):
            return "s2"

        async def step3(ctx):
            raise ValueError("Failed")

        async def comp1(ctx):
            compensation_order.append("comp1")
            return True

        async def comp2(ctx):
            compensation_order.append("comp2")
            return True

        saga.add_step(
            SagaStep(
                name="step1",
                execute=step1,
                compensation=SagaCompensation(name="comp1", execute=comp1),
                max_retries=1,
            )
        )
        saga.add_step(
            SagaStep(
                name="step2",
                execute=step2,
                compensation=SagaCompensation(name="comp2", execute=comp2),
                max_retries=1,
            )
        )
        saga.add_step(SagaStep(name="step3", execute=step3, max_retries=1))

        await saga.execute()

        # LIFO: comp2 should run before comp1
        assert compensation_order == ["comp2", "comp1"]

    @pytest.mark.asyncio
    async def test_optional_step_failure_continues(self, saga):
        """Test that optional step failure doesn't stop saga."""

        async def step1(ctx):
            return "s1"

        async def optional_step(ctx):
            raise ValueError("Optional failed")

        async def step3(ctx):
            return "s3"

        saga.add_step(SagaStep(name="step1", execute=step1, max_retries=1))
        saga.add_step(
            SagaStep(
                name="optional",
                execute=optional_step,
                is_optional=True,
                max_retries=1,
            )
        )
        saga.add_step(SagaStep(name="step3", execute=step3, max_retries=1))

        result = await saga.execute()

        assert result.status == SagaStatus.COMPLETED
        assert "step1" in result.completed_steps
        assert "step3" in result.completed_steps
        assert "optional" not in result.completed_steps

    @pytest.mark.asyncio
    async def test_step_timeout(self, saga):
        """Test step timeout handling."""

        async def slow_step(ctx):
            await asyncio.sleep(5)  # Longer than timeout
            return "never_reached"

        saga.add_step(
            SagaStep(
                name="slow_step",
                execute=slow_step,
                timeout_seconds=0.1,
                max_retries=1,
            )
        )

        result = await saga.execute()

        assert result.status == SagaStatus.COMPENSATED
        assert result.failed_step == "slow_step"

    @pytest.mark.asyncio
    async def test_step_retries_before_failure(self, saga):
        """Test step retries before marking as failed."""
        attempt_count = {"count": 0}

        async def flaky_step(ctx):
            attempt_count["count"] += 1
            if attempt_count["count"] < 3:
                raise ValueError(f"Attempt {attempt_count['count']} failed")
            return "success"

        saga.add_step(
            SagaStep(
                name="flaky",
                execute=flaky_step,
                max_retries=3,
                retry_delay_seconds=0.01,
            )
        )

        result = await saga.execute()

        assert result.status == SagaStatus.COMPLETED
        assert attempt_count["count"] == 3

    @pytest.mark.asyncio
    async def test_compensation_retries(self, saga):
        """Test compensation retries."""
        comp_attempts = {"count": 0}

        async def step(ctx):
            raise ValueError("Always fails")

        async def flaky_comp(ctx):
            comp_attempts["count"] += 1
            if comp_attempts["count"] < 2:
                raise ValueError("Compensation failed")
            return True

        saga.add_step(
            SagaStep(
                name="step",
                execute=step,
                compensation=SagaCompensation(
                    name="flaky_comp",
                    execute=flaky_comp,
                    max_retries=3,
                    retry_delay_seconds=0.01,
                ),
                max_retries=1,
            )
        )

        result = await saga.execute()

        assert "flaky_comp" in result.compensated_steps
        assert comp_attempts["count"] == 2

    @pytest.mark.asyncio
    async def test_compensation_failure(self, saga):
        """Test compensation failure handling."""

        async def step(ctx):
            raise ValueError("Step fails")

        async def failing_comp(ctx):
            raise ValueError("Compensation always fails")

        saga.add_step(
            SagaStep(
                name="step",
                execute=step,
                compensation=SagaCompensation(
                    name="failing_comp",
                    execute=failing_comp,
                    max_retries=1,
                ),
                max_retries=1,
            )
        )

        result = await saga.execute()

        assert result.status == SagaStatus.PARTIALLY_COMPENSATED
        assert "failing_comp" in result.failed_compensations

    @pytest.mark.asyncio
    async def test_context_passed_to_steps(self, saga):
        """Test that context is passed to steps."""
        received_context = {}

        async def capturing_step(ctx):
            received_context.update(ctx)
            return "captured"

        saga.add_step(SagaStep(name="capture", execute=capturing_step))

        context = SagaContext(
            saga_id="test-saga",
            constitutional_hash="custom_hash",
            tenant_id="tenant-123",
        )
        context.metadata["custom_key"] = "custom_value"

        await saga.execute(context)

        assert received_context["saga_id"] == "test-saga"
        assert received_context["constitutional_hash"] == "custom_hash"
        assert received_context["metadata"]["custom_key"] == "custom_value"

    @pytest.mark.asyncio
    async def test_execution_time_measurement(self, saga):
        """Test execution time measurement."""

        async def slow_step(ctx):
            await asyncio.sleep(0.05)
            return "done"

        saga.add_step(SagaStep(name="slow", execute=slow_step))

        result = await saga.execute()

        assert result.total_execution_time_ms >= 50
        assert result.total_execution_time_ms < 500  # Sanity check

    @pytest.mark.asyncio
    async def test_persistence_during_execution(self, tmp_path):
        """Test state persistence during execution."""
        provider = FileSagaPersistenceProvider(str(tmp_path))
        saga = ConstitutionalSagaWorkflow(
            saga_id="persist-test",
            persistence_provider=provider,
        )

        async def step1(ctx):
            return "s1"

        async def step2(ctx):
            return "s2"

        saga.add_step(SagaStep(name="step1", execute=step1))
        saga.add_step(SagaStep(name="step2", execute=step2))

        await saga.execute()

        # Verify state was persisted
        state = await provider.load_state("persist-test")
        assert state is not None
        assert state.status == SagaStatus.COMPLETED
        assert "step1" in state.completed_steps
        assert "step2" in state.completed_steps
