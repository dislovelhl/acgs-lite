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


class TestSagaState:
    """Tests for SagaState dataclass."""

    @pytest.fixture
    def sample_state(self):
        """Create sample saga state."""
        return SagaState(
            saga_id="test-saga-001",
            status=SagaStatus.EXECUTING,
            completed_steps=["step1"],
            failed_step=None,
            compensated_steps=[],
            failed_compensations=[],
            context={"key": "value"},
        )

    def test_basic_creation(self, sample_state):
        """Test basic state creation."""
        assert sample_state.saga_id == "test-saga-001"
        assert sample_state.status == SagaStatus.EXECUTING

    def test_default_version(self, sample_state):
        """Test default version."""
        assert sample_state.version == "1.0.0"

    def test_updated_at_auto_set(self, sample_state):
        """Test updated_at is automatically set."""
        assert sample_state.updated_at is not None

    def test_to_json_serialization(self, sample_state):
        """Test JSON serialization."""
        json_str = sample_state.to_json()
        assert isinstance(json_str, str)

        data = json.loads(json_str)
        assert data["saga_id"] == "test-saga-001"
        assert data["status"] == "executing"

    def test_from_json_deserialization(self, sample_state):
        """Test JSON deserialization."""
        json_str = sample_state.to_json()
        restored = SagaState.from_json(json_str)

        assert restored.saga_id == sample_state.saga_id
        assert restored.status == sample_state.status
        assert restored.completed_steps == sample_state.completed_steps
