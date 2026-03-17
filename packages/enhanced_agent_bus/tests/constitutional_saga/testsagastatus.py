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


class TestSagaStatus:
    """Tests for SagaStatus enum."""

    def test_all_statuses_exist(self):
        """Test all saga statuses are defined."""
        statuses = list(SagaStatus)
        assert len(statuses) == 7

    def test_pending_value(self):
        """Test pending status value."""
        assert SagaStatus.PENDING.value == "pending"

    def test_executing_value(self):
        """Test executing status value."""
        assert SagaStatus.EXECUTING.value == "executing"

    def test_completed_value(self):
        """Test completed status value."""
        assert SagaStatus.COMPLETED.value == "completed"

    def test_compensating_value(self):
        """Test compensating status value."""
        assert SagaStatus.COMPENSATING.value == "compensating"

    def test_compensated_value(self):
        """Test compensated status value."""
        assert SagaStatus.COMPENSATED.value == "compensated"

    def test_failed_value(self):
        """Test failed status value."""
        assert SagaStatus.FAILED.value == "failed"

    def test_partially_compensated_value(self):
        """Test partially_compensated status value."""
        assert SagaStatus.PARTIALLY_COMPENSATED.value == "partially_compensated"
