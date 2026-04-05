"""
Tests for Saga Enums and Data Classes.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enterprise_sso.saga_orchestration import (
    CONSTITUTIONAL_HASH,
    CompensationStrategy,
    SagaContext,
    SagaEvent,
    SagaEventType,
    SagaExecutionResult,
    SagaStatus,
    SagaStepDefinition,
    SagaStepResult,
    SagaStepStatus,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaEnums:
    """Tests for saga enumerations."""

    def test_saga_status_values(self):
        """Test SagaStatus enum values."""
        assert SagaStatus.PENDING == "pending"
        assert SagaStatus.RUNNING == "running"
        assert SagaStatus.COMPLETED == "completed"
        assert SagaStatus.COMPENSATING == "compensating"
        assert SagaStatus.COMPENSATED == "compensated"
        assert SagaStatus.FAILED == "failed"
        assert SagaStatus.PARTIALLY_COMPENSATED == "partially_compensated"

    def test_saga_step_status_values(self):
        """Test SagaStepStatus enum values."""
        assert SagaStepStatus.PENDING == "pending"
        assert SagaStepStatus.EXECUTING == "executing"
        assert SagaStepStatus.COMPLETED == "completed"
        assert SagaStepStatus.FAILED == "failed"
        assert SagaStepStatus.COMPENSATING == "compensating"
        assert SagaStepStatus.COMPENSATED == "compensated"
        assert SagaStepStatus.COMPENSATION_FAILED == "compensation_failed"
        assert SagaStepStatus.SKIPPED == "skipped"

    def test_compensation_strategy_values(self):
        """Test CompensationStrategy enum values."""
        assert CompensationStrategy.RETRY == "retry"
        assert CompensationStrategy.SKIP == "skip"
        assert CompensationStrategy.FAIL == "fail"
        assert CompensationStrategy.MANUAL == "manual"

    def test_saga_event_type_values(self):
        """Test SagaEventType enum values."""
        assert SagaEventType.SAGA_STARTED == "saga_started"
        assert SagaEventType.SAGA_COMPLETED == "saga_completed"
        assert SagaEventType.STEP_STARTED == "step_started"
        assert SagaEventType.STEP_COMPLETED == "step_completed"


class TestSagaDataClasses:
    """Tests for saga data classes."""

    def test_saga_step_result_creation(self):
        """Test SagaStepResult creation."""
        result = SagaStepResult(
            success=True,
            data={"key": "value"},
            execution_time_ms=50.0,
        )

        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None
        assert result.execution_time_ms == 50.0

    def test_saga_context_creation(self):
        """Test SagaContext creation."""
        context = SagaContext(
            saga_id="saga-001",
            tenant_id="tenant-001",
            correlation_id="corr-001",
            data={"key": "value"},
        )

        assert context.saga_id == "saga-001"
        assert context.tenant_id == "tenant-001"
        assert context.data["key"] == "value"
        assert context.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_event_creation(self):
        """Test SagaEvent creation."""
        event = SagaEvent(
            event_id="event-001",
            saga_id="saga-001",
            event_type=SagaEventType.SAGA_STARTED,
            step_name="step1",
            details={"key": "value"},
        )

        assert event.event_id == "event-001"
        assert event.saga_id == "saga-001"
        assert event.event_type == SagaEventType.SAGA_STARTED
        assert event.step_name == "step1"
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_step_definition_defaults(self):
        """Test SagaStepDefinition default values."""

        async def action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def compensation(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        step = SagaStepDefinition(
            name="test_step",
            description="Test step",
            action=action,
            compensation=compensation,
        )

        assert step.timeout_seconds == 300
        assert step.max_retries == 3
        assert step.retry_delay_seconds == 5
        assert step.compensation_strategy == CompensationStrategy.RETRY
        assert step.required is True
        assert step.order == 0

    def test_saga_execution_result_creation(self):
        """Test SagaExecutionResult creation."""
        result = SagaExecutionResult(
            saga_id="saga-001",
            success=True,
            status=SagaStatus.COMPLETED,
            completed_steps=["step1", "step2"],
            execution_time_ms=100.0,
        )

        assert result.saga_id == "saga-001"
        assert result.success is True
        assert result.status == SagaStatus.COMPLETED
        assert len(result.completed_steps) == 2
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
