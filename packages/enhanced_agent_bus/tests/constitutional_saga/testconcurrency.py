"""
Comprehensive tests for Constitutional Saga workflow module.
Constitutional Hash: cdd01ef066bc6cf2

Coverage targets:
- SagaStatus and StepStatus enums
- SagaCompensation, SagaStep, SagaContext, SagaResult, SagaState dataclasses
- FileSagaPersistenceProvider
- DefaultSagaActivities
- Saga execution and compensation flow
- Concurrency functionality
- Error handling and edge cases
- Integration with related components
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


class TestConcurrency:
    """Tests for concurrent saga execution."""

    @pytest.mark.asyncio
    async def test_multiple_sagas_concurrent(self):
        """Test multiple sagas can execute concurrently."""

        async def step(ctx):
            await asyncio.sleep(0.01)  # Simulate work
            return f"result-{ctx['saga_id']}"

        async def run_saga(saga_id):
            saga = ConstitutionalSagaWorkflow(saga_id=saga_id)
            saga.add_step(SagaStep(name="step", execute=step))
            return await saga.execute()

        # Run 5 sagas concurrently
        tasks = [run_saga(f"concurrent-{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for i, result in enumerate(results):
            assert result.status == SagaStatus.COMPLETED
            assert result.saga_id == f"concurrent-{i}"

    @pytest.mark.asyncio
    async def test_saga_isolation(self):
        """Test sagas are isolated from each other."""
        saga1_ctx = None
        saga2_ctx = None

        async def capture_step1(ctx):
            nonlocal saga1_ctx
            saga1_ctx = ctx.copy()
            return "saga1"

        async def capture_step2(ctx):
            nonlocal saga2_ctx
            saga2_ctx = ctx.copy()
            return "saga2"

        saga1 = ConstitutionalSagaWorkflow(saga_id="isolation-1")
        saga1.add_step(SagaStep(name="step", execute=capture_step1))

        saga2 = ConstitutionalSagaWorkflow(saga_id="isolation-2")
        saga2.add_step(SagaStep(name="step", execute=capture_step2))

        await asyncio.gather(saga1.execute(), saga2.execute())

        assert saga1_ctx["saga_id"] == "isolation-1"
        assert saga2_ctx["saga_id"] == "isolation-2"
