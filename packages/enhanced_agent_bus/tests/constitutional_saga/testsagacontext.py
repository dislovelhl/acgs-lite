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


class TestSagaContext:
    """Tests for SagaContext dataclass."""

    @pytest.fixture
    def sample_context(self):
        """Create sample saga context."""
        return SagaContext(
            saga_id="test-saga-001",
            tenant_id="tenant-123",
            correlation_id="corr-456",
        )

    def test_basic_creation(self, sample_context):
        """Test basic context creation."""
        assert sample_context.saga_id == "test-saga-001"
        assert sample_context.tenant_id == "tenant-123"

    def test_default_constitutional_hash(self, sample_context):
        """Test default constitutional hash is set."""
        assert sample_context.constitutional_hash == CONSTITUTIONAL_HASH

    def test_empty_step_results(self, sample_context):
        """Test empty step results at start."""
        assert sample_context.step_results == {}

    def test_get_step_result_nonexistent(self, sample_context):
        """Test getting nonexistent step result returns None."""
        result = sample_context.get_step_result("nonexistent")
        assert result is None

    def test_set_and_get_step_result(self, sample_context):
        """Test setting and getting step result."""
        sample_context.set_step_result("step1", {"data": "value"})
        result = sample_context.get_step_result("step1")
        assert result == {"data": "value"}

    def test_started_at_auto_set(self, sample_context):
        """Test started_at is automatically set."""
        assert sample_context.started_at is not None
        assert isinstance(sample_context.started_at, datetime)

    def test_errors_list_initialized(self, sample_context):
        """Test errors list is initialized empty."""
        assert sample_context.errors == []
