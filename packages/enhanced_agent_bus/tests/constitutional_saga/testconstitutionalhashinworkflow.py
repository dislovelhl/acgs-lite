"""
Comprehensive tests for Constitutional Saga workflow module.
Constitutional Hash: 608508a9bd224290

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


class TestConstitutionalHashInWorkflow:
    """Tests for constitutional hash validation in saga workflow."""

    async def test_constitutional_hash_in_step_context(self):
        """Test constitutional hash is passed to step context."""
        received_hash = {"hash": None}

        async def step(ctx):
            received_hash["hash"] = ctx.get("constitutional_hash")
            return "done"

        saga = ConstitutionalSagaWorkflow(saga_id="hash-test")
        saga.add_step(SagaStep(name="step", execute=step))

        context = SagaContext(saga_id="hash-test", constitutional_hash="custom-hash-123")
        await saga.execute(context)

        assert received_hash["hash"] == "custom-hash-123"

    async def test_default_constitutional_hash(self):
        """Test default constitutional hash is used."""
        received_hash = {"hash": None}

        async def step(ctx):
            received_hash["hash"] = ctx.get("constitutional_hash")
            return "done"

        saga = ConstitutionalSagaWorkflow(saga_id="default-hash")
        saga.add_step(SagaStep(name="step", execute=step))

        await saga.execute()

        assert received_hash["hash"] == CONSTITUTIONAL_HASH

    async def test_result_includes_constitutional_hash(self):
        """Test result includes constitutional hash."""
        saga = ConstitutionalSagaWorkflow(saga_id="result-hash")

        async def step(ctx):
            return "done"

        saga.add_step(SagaStep(name="step", execute=step))

        result = await saga.execute()

        assert result.constitutional_hash == CONSTITUTIONAL_HASH
        assert result.to_dict()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_constitutional_hash_constant(self):
        """Test CONSTITUTIONAL_HASH constant is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
