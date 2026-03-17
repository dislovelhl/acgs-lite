"""
Comprehensive tests for Constitutional Saga workflow module.
Constitutional Hash: cdd01ef066bc6cf2

Coverage targets:
- SagaStatus and StepStatus enums
- SagaCompensation, SagaStep, SagaContext, SagaResult, SagaState dataclasses
- FileSagaPersistenceProvider
- DefaultSagaActivities
- Saga execution and compensation flow
- Async compensation execution functionality
- Error handling and edge cases
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


class TestAsyncCompensationExecution:
    """Tests for async compensation execution."""

    @pytest.mark.asyncio
    async def test_compensation_execution(self):
        """Test compensation can be executed."""
        execution_tracker = {"called": False}

        async def comp_fn(ctx):
            execution_tracker["called"] = True
            return True

        compensation = SagaCompensation(
            name="test_comp",
            execute=comp_fn,
        )

        result = await compensation.execute({})
        assert result is True
        assert execution_tracker["called"] is True

    @pytest.mark.asyncio
    async def test_step_execution(self):
        """Test step can be executed."""

        async def exec_fn(ctx):
            return {"status": "success"}

        step = SagaStep(name="test_step", execute=exec_fn)
        result = await step.execute({})

        assert result["status"] == "success"
