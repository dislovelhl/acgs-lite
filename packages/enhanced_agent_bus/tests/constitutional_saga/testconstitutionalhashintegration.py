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


class TestConstitutionalHashIntegration:
    """Tests for constitutional hash integration."""

    def test_context_has_constitutional_hash(self):
        """Test context includes constitutional hash."""
        context = SagaContext(saga_id="hash-test")
        assert context.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_has_constitutional_hash(self):
        """Test result includes constitutional hash."""
        context = SagaContext(saga_id="hash-test")
        result = SagaResult(
            saga_id="hash-test",
            status=SagaStatus.COMPLETED,
            completed_steps=[],
            failed_step=None,
            compensated_steps=[],
            failed_compensations=[],
            total_execution_time_ms=0.0,
            context=context,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_dict_has_constitutional_hash(self):
        """Test result dict includes constitutional hash."""
        context = SagaContext(saga_id="hash-test")
        result = SagaResult(
            saga_id="hash-test",
            status=SagaStatus.COMPLETED,
            completed_steps=[],
            failed_step=None,
            compensated_steps=[],
            failed_compensations=[],
            total_execution_time_ms=0.0,
            context=context,
        )
        result_dict = result.to_dict()
        assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH
