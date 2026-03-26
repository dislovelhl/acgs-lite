"""
Comprehensive tests for Constitutional Saga workflow module.
Constitutional Hash: 608508a9bd224290

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
from datetime import UTC, datetime, timezone
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
    create_constitutional_validation_saga,
)


class TestCreateConstitutionalValidationSaga:
    """Tests for create_constitutional_validation_saga factory."""

    def test_creates_saga_with_correct_steps(self):
        """Test factory creates saga with all required steps."""
        saga = create_constitutional_validation_saga("factory-test")

        step_names = [step.name for step in saga._steps]

        assert "reserve_capacity" in step_names
        assert "validate_compliance" in step_names
        assert "audit_reasoning" in step_names
        assert "apply_policy" in step_names
        assert "record_audit" in step_names

    def test_steps_have_compensations(self):
        """Test that non-optional steps have compensations."""
        saga = create_constitutional_validation_saga("comp-test")

        for step in saga._steps:
            if not step.is_optional:
                assert step.compensation is not None, f"Step {step.name} missing compensation"

    def test_audit_reasoning_is_optional(self):
        """Test that audit_reasoning step is optional."""
        saga = create_constitutional_validation_saga("optional-test")

        audit_step = next(s for s in saga._steps if s.name == "audit_reasoning")
        assert audit_step.is_optional is True

    async def test_full_saga_execution_success(self):
        """Test full saga execution with default activities."""
        saga = create_constitutional_validation_saga("full-exec-test")

        context = SagaContext(saga_id="full-exec-test")
        context.set_step_result("constitutional_hash", CONSTITUTIONAL_HASH)

        result = await saga.execute(context)

        assert result.status == SagaStatus.COMPLETED
        assert len(result.completed_steps) >= 4  # At least 4 non-optional steps

    async def test_saga_with_custom_activities(self):
        """Test saga with custom activities."""
        custom_activities = MagicMock(spec=DefaultSagaActivities)
        custom_activities.reserve_capacity = AsyncMock(
            return_value={
                "reservation_id": "custom-123",
                "resource_type": "custom",
                "amount": 1,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        custom_activities.validate_constitutional_compliance = AsyncMock(
            return_value={
                "validation_id": "val-custom",
                "is_valid": True,
                "errors": [],
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        custom_activities.audit_llm_reasoning = AsyncMock(
            return_value={
                "audit_id": "audit-custom",
                "is_safe": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        custom_activities.apply_policy_decision = AsyncMock(
            return_value={
                "decision_id": "dec-custom",
                "policy_path": "test",
                "applied": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        custom_activities.record_audit_entry = AsyncMock(return_value="audit-entry-id")
        custom_activities.release_capacity = AsyncMock(return_value=True)
        custom_activities.log_validation_failure = AsyncMock(return_value=True)
        custom_activities.revert_policy_decision = AsyncMock(return_value=True)
        custom_activities.mark_audit_failed = AsyncMock(return_value=True)

        saga = create_constitutional_validation_saga(
            "custom-activities-test",
            activities=custom_activities,
        )

        result = await saga.execute()

        assert result.status == SagaStatus.COMPLETED
        custom_activities.reserve_capacity.assert_called_once()
