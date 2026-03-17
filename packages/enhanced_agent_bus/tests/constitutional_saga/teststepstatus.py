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


class TestStepStatus:
    """Tests for StepStatus enum."""

    def test_all_statuses_exist(self):
        """Test all step statuses are defined."""
        statuses = list(StepStatus)
        assert len(statuses) == 7

    def test_pending_value(self):
        assert StepStatus.PENDING.value == "pending"

    def test_executing_value(self):
        assert StepStatus.EXECUTING.value == "executing"

    def test_completed_value(self):
        assert StepStatus.COMPLETED.value == "completed"

    def test_failed_value(self):
        assert StepStatus.FAILED.value == "failed"

    def test_compensating_value(self):
        assert StepStatus.COMPENSATING.value == "compensating"

    def test_compensated_value(self):
        assert StepStatus.COMPENSATED.value == "compensated"

    def test_compensation_failed_value(self):
        assert StepStatus.COMPENSATION_FAILED.value == "compensation_failed"
