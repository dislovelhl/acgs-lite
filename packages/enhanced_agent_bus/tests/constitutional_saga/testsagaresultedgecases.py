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


class TestSagaResultEdgeCases:
    """Tests for SagaResult edge cases."""

    def test_failed_saga_result(self):
        """Test result for failed saga."""
        context = SagaContext(saga_id="failed-saga")
        result = SagaResult(
            saga_id="failed-saga",
            status=SagaStatus.FAILED,
            completed_steps=["step1"],
            failed_step="step2",
            compensated_steps=["step1"],
            failed_compensations=[],
            total_execution_time_ms=50.0,
            context=context,
            errors=["Step 2 failed due to timeout"],
        )

        assert result.status == SagaStatus.FAILED
        assert result.failed_step == "step2"
        assert len(result.compensated_steps) == 1

        dict_result = result.to_dict()
        assert dict_result["status"] == "failed"
        assert dict_result["failed_step"] == "step2"

    def test_partially_compensated_result(self):
        """Test result for partially compensated saga."""
        context = SagaContext(saga_id="partial-saga")
        result = SagaResult(
            saga_id="partial-saga",
            status=SagaStatus.PARTIALLY_COMPENSATED,
            completed_steps=["step1", "step2", "step3"],
            failed_step="step3",
            compensated_steps=["step2"],
            failed_compensations=["step1"],
            total_execution_time_ms=75.0,
            context=context,
        )

        assert result.status == SagaStatus.PARTIALLY_COMPENSATED
        assert "step1" in result.failed_compensations
