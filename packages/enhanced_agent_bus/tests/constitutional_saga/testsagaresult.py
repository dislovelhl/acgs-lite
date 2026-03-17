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


class TestSagaResult:
    """Tests for SagaResult dataclass."""

    @pytest.fixture
    def sample_result(self):
        """Create sample saga result."""
        context = SagaContext(saga_id="test-saga-001")
        return SagaResult(
            saga_id="test-saga-001",
            status=SagaStatus.COMPLETED,
            completed_steps=["step1", "step2"],
            failed_step=None,
            compensated_steps=[],
            failed_compensations=[],
            total_execution_time_ms=150.5,
            context=context,
        )

    def test_basic_creation(self, sample_result):
        """Test basic result creation."""
        assert sample_result.saga_id == "test-saga-001"
        assert sample_result.status == SagaStatus.COMPLETED

    def test_completed_steps_tracked(self, sample_result):
        """Test completed steps are tracked."""
        assert sample_result.completed_steps == ["step1", "step2"]

    def test_default_version(self, sample_result):
        """Test default version is set."""
        assert sample_result.version == "1.0.0"

    def test_constitutional_hash_set(self, sample_result):
        """Test constitutional hash is set."""
        assert sample_result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict_structure(self, sample_result):
        """Test to_dict returns correct structure."""
        result = sample_result.to_dict()

        assert "saga_id" in result
        assert "status" in result
        assert "completed_steps" in result
        assert "failed_step" in result
        assert "compensated_steps" in result
        assert "total_execution_time_ms" in result
        assert "version" in result
        assert "constitutional_hash" in result
        assert "step_results" in result

    def test_to_dict_status_is_string(self, sample_result):
        """Test status is serialized as string."""
        result = sample_result.to_dict()
        assert result["status"] == "completed"
