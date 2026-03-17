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


class TestSagaCompensation:
    """Tests for SagaCompensation dataclass."""

    @pytest.fixture
    def sample_compensation(self):
        """Create sample compensation."""

        async def execute_fn(ctx):
            return True

        return SagaCompensation(
            name="test_compensation",
            execute=execute_fn,
            description="Test compensation action",
            idempotency_key="test-key-123",
            max_retries=5,
            retry_delay_seconds=2.0,
        )

    def test_basic_creation(self, sample_compensation):
        """Test basic compensation creation."""
        assert sample_compensation.name == "test_compensation"
        assert sample_compensation.description == "Test compensation action"

    def test_default_values(self):
        """Test default values."""

        async def execute_fn(ctx):
            return True

        comp = SagaCompensation(name="minimal", execute=execute_fn)
        assert comp.description == ""
        assert comp.idempotency_key is None
        assert comp.max_retries == 3
        assert comp.retry_delay_seconds == 1.0

    def test_custom_retry_settings(self, sample_compensation):
        """Test custom retry settings."""
        assert sample_compensation.max_retries == 5
        assert sample_compensation.retry_delay_seconds == 2.0
