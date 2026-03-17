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


class TestSagaContextOperations:
    """Tests for SagaContext advanced operations."""

    def test_multiple_step_results(self):
        """Test storing multiple step results."""
        context = SagaContext(saga_id="multi-step-saga")

        context.set_step_result("step1", {"value": 1})
        context.set_step_result("step2", {"value": 2})
        context.set_step_result("step3", {"value": 3})

        assert context.get_step_result("step1")["value"] == 1
        assert context.get_step_result("step2")["value"] == 2
        assert context.get_step_result("step3")["value"] == 3

    def test_overwrite_step_result(self):
        """Test overwriting a step result."""
        context = SagaContext(saga_id="overwrite-saga")

        context.set_step_result("step1", {"original": True})
        context.set_step_result("step1", {"updated": True})

        result = context.get_step_result("step1")
        assert "updated" in result
        assert "original" not in result

    def test_metadata_storage(self):
        """Test metadata storage."""
        context = SagaContext(
            saga_id="metadata-saga", metadata={"source": "test", "priority": "high"}
        )

        assert context.metadata["source"] == "test"
        assert context.metadata["priority"] == "high"

    def test_error_tracking(self):
        """Test error tracking."""
        context = SagaContext(saga_id="error-saga")
        context.errors.append("Error 1")
        context.errors.append("Error 2")

        assert len(context.errors) == 2
        assert "Error 1" in context.errors
