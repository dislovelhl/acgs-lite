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


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_saga_with_none_context(self):
        """Test saga creates context if None provided."""
        saga = ConstitutionalSagaWorkflow(saga_id="none-ctx")

        async def step(ctx):
            return "result"

        saga.add_step(SagaStep(name="step", execute=step))

        result = await saga.execute(None)

        assert result.context is not None
        assert result.context.saga_id == "none-ctx"

    @pytest.mark.asyncio
    async def test_saga_exception_during_execution(self):
        """Test saga handles unexpected exceptions."""
        saga = ConstitutionalSagaWorkflow(saga_id="exception-test")

        async def step(ctx):
            return "result"

        saga.add_step(SagaStep(name="step", execute=step))

        # Mock _execute_step to raise unexpected exception
        original_execute = saga._execute_step

        async def raising_execute(*args, **kwargs):
            raise RuntimeError("Unexpected error")

        saga._execute_step = raising_execute

        result = await saga.execute()

        # After exception, saga attempts compensations, so status is COMPENSATING
        # (not FAILED) because _run_compensations sets status to COMPENSATING
        assert result.status in (SagaStatus.COMPENSATING, SagaStatus.COMPENSATED)
        assert len(result.errors) > 0
        assert "Unexpected error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_compensation_receives_correct_context(self):
        """Test compensations receive correct context data."""
        received_comp_ctx = {}

        async def step1(ctx):
            return {"key1": "value1"}

        async def step2(ctx):
            raise ValueError("Trigger compensation")

        async def comp1(ctx):
            received_comp_ctx.update(ctx)
            return True

        saga = ConstitutionalSagaWorkflow(saga_id="comp-ctx-test")
        saga.add_step(
            SagaStep(
                name="step1",
                execute=step1,
                compensation=SagaCompensation(name="comp1", execute=comp1),
                max_retries=1,
            )
        )
        saga.add_step(SagaStep(name="step2", execute=step2, max_retries=1))

        await saga.execute()

        assert "saga_id" in received_comp_ctx
        assert "idempotency_key" in received_comp_ctx
        assert received_comp_ctx["context"]["step1"]["key1"] == "value1"

    @pytest.mark.asyncio
    async def test_idempotency_key_in_compensation(self):
        """Test idempotency key is passed to compensation."""
        received_key = {"key": None}

        async def step(ctx):
            raise ValueError("Fail")

        async def comp(ctx):
            received_key["key"] = ctx.get("idempotency_key")
            return True

        saga = ConstitutionalSagaWorkflow(saga_id="idem-test")
        saga.add_step(
            SagaStep(
                name="step",
                execute=step,
                compensation=SagaCompensation(
                    name="comp",
                    execute=comp,
                    idempotency_key="custom-idem-key",
                ),
                max_retries=1,
            )
        )

        await saga.execute()

        assert received_key["key"] == "custom-idem-key"

    @pytest.mark.asyncio
    async def test_default_idempotency_key_format(self):
        """Test default idempotency key format."""
        received_key = {"key": None}

        async def step(ctx):
            raise ValueError("Fail")

        async def comp(ctx):
            received_key["key"] = ctx.get("idempotency_key")
            return True

        saga = ConstitutionalSagaWorkflow(saga_id="default-idem-test")
        saga.add_step(
            SagaStep(
                name="step",
                execute=step,
                compensation=SagaCompensation(name="comp", execute=comp),
                max_retries=1,
            )
        )

        await saga.execute()

        assert received_key["key"] == "default-idem-test:comp"

    @pytest.mark.asyncio
    async def test_result_to_dict_with_errors(self):
        """Test result to_dict includes errors."""

        async def failing_step(ctx):
            raise ValueError("Test error")

        saga = ConstitutionalSagaWorkflow(saga_id="error-dict-test")
        saga.add_step(SagaStep(name="fail", execute=failing_step, max_retries=1))

        result = await saga.execute()
        result_dict = result.to_dict()

        assert "errors" in result_dict
        assert len(result_dict["errors"]) > 0
