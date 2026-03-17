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


class TestFileSagaPersistenceProvider:
    """Tests for FileSagaPersistenceProvider."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def provider(self, temp_dir):
        """Create provider with temp directory."""
        return FileSagaPersistenceProvider(base_path=temp_dir)

    @pytest.fixture
    def sample_state(self):
        """Create sample state for testing."""
        return SagaState(
            saga_id="persist-test-001",
            status=SagaStatus.COMPLETED,
            completed_steps=["step1", "step2"],
            failed_step=None,
            compensated_steps=[],
            failed_compensations=[],
            context={"data": "test"},
        )

    @pytest.mark.asyncio
    async def test_save_state(self, provider, sample_state, temp_dir):
        """Test saving saga state."""
        await provider.save_state(sample_state)

        file_path = Path(temp_dir) / f"{sample_state.saga_id}.json"
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_load_state(self, provider, sample_state, temp_dir):
        """Test loading saga state."""
        await provider.save_state(sample_state)
        loaded = await provider.load_state(sample_state.saga_id)

        assert loaded is not None
        assert loaded.saga_id == sample_state.saga_id
        assert loaded.status == sample_state.status

    @pytest.mark.asyncio
    async def test_load_state_nonexistent(self, provider):
        """Test loading nonexistent state returns None."""
        loaded = await provider.load_state("nonexistent-saga")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_state(self, provider, sample_state, temp_dir):
        """Test deleting saga state."""
        await provider.save_state(sample_state)
        await provider.delete_state(sample_state.saga_id)

        file_path = Path(temp_dir) / f"{sample_state.saga_id}.json"
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_state_nonexistent(self, provider):
        """Test deleting nonexistent state doesn't error."""
        await provider.delete_state("nonexistent")  # Should not raise

    def test_directory_creation(self, temp_dir):
        """Test directory is created if it doesn't exist."""
        new_path = Path(temp_dir) / "nested" / "dir"
        provider = FileSagaPersistenceProvider(base_path=new_path)
        assert new_path.exists()
