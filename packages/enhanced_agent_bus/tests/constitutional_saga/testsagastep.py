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


class TestSagaStep:
    """Tests for SagaStep dataclass."""

    @pytest.fixture
    def sample_step(self):
        """Create sample saga step."""

        async def execute_fn(ctx):
            return {"result": "success"}

        async def comp_fn(ctx):
            return True

        compensation = SagaCompensation(name="rollback", execute=comp_fn)

        return SagaStep(
            name="test_step",
            execute=execute_fn,
            compensation=compensation,
            description="Test step description",
            timeout_seconds=60,
            max_retries=5,
        )

    def test_basic_creation(self, sample_step):
        """Test basic step creation."""
        assert sample_step.name == "test_step"
        assert sample_step.description == "Test step description"

    def test_default_status_pending(self, sample_step):
        """Test step starts in pending status."""
        assert sample_step.status == StepStatus.PENDING

    def test_default_result_none(self, sample_step):
        """Test step result starts as None."""
        assert sample_step.result is None

    def test_default_error_none(self, sample_step):
        """Test step error starts as None."""
        assert sample_step.error is None

    def test_custom_timeout(self, sample_step):
        """Test custom timeout setting."""
        assert sample_step.timeout_seconds == 60

    def test_custom_retries(self, sample_step):
        """Test custom retry setting."""
        assert sample_step.max_retries == 5

    def test_default_values(self):
        """Test default values for minimal step."""

        async def execute_fn(ctx):
            return True

        step = SagaStep(name="minimal", execute=execute_fn)
        assert step.timeout_seconds == 30
        assert step.max_retries == 3
        assert step.retry_delay_seconds == 1.0
        assert step.is_optional is False
        assert step.requires_previous is True
