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


class TestSagaResume:
    """Tests for saga resume functionality."""

    @pytest.fixture
    def provider(self, tmp_path):
        """Create persistence provider."""
        return FileSagaPersistenceProvider(str(tmp_path))

    @pytest.mark.asyncio
    async def test_resume_nonexistent_saga(self, provider):
        """Test resuming non-existent saga returns None."""
        saga = await ConstitutionalSagaWorkflow.resume(
            saga_id="nonexistent",
            persistence_provider=provider,
        )
        assert saga is None

    @pytest.mark.asyncio
    async def test_resume_existing_saga(self, provider):
        """Test resuming existing saga."""
        # Save state first
        state = SagaState(
            saga_id="resume-test",
            status=SagaStatus.EXECUTING,
            completed_steps=["step1"],
            failed_step=None,
            compensated_steps=[],
            failed_compensations=[],
            context={"step1": "result1"},
            version="2.0.0",
        )
        await provider.save_state(state)

        # Resume
        saga = await ConstitutionalSagaWorkflow.resume(
            saga_id="resume-test",
            persistence_provider=provider,
        )

        assert saga is not None
        assert saga.saga_id == "resume-test"
        assert saga._status == SagaStatus.EXECUTING
        assert saga._completed_steps == ["step1"]
        assert saga.version == "2.0.0"
