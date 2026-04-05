"""Tests for persistence.models module.

Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from enhanced_agent_bus.persistence.models import (
    CONSTITUTIONAL_HASH,
    CheckpointData,
    EventType,
    StepStatus,
    StepType,
    WorkflowCompensation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_workflow_status_values(self):
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"
        assert WorkflowStatus.CANCELLED == "cancelled"
        assert WorkflowStatus.COMPENSATING == "compensating"
        assert WorkflowStatus.COMPENSATED == "compensated"

    def test_step_status_values(self):
        assert StepStatus.PENDING == "pending"
        assert StepStatus.EXECUTING == "executing"
        assert StepStatus.COMPLETED == "completed"
        assert StepStatus.COMPENSATION_FAILED == "compensation_failed"

    def test_step_type_values(self):
        assert StepType.ACTIVITY == "activity"
        assert StepType.DECISION == "decision"
        assert StepType.COMPENSATION == "compensation"
        assert StepType.CHECKPOINT == "checkpoint"
        assert StepType.WAIT == "wait"

    def test_event_type_values(self):
        assert EventType.WORKFLOW_STARTED == "workflow_started"
        assert EventType.WORKFLOW_COMPLETED == "workflow_completed"
        assert EventType.STEP_STARTED == "step_started"
        assert EventType.COMPENSATION_STARTED == "compensation_started"
        assert EventType.CHECKPOINT_CREATED == "checkpoint_created"


# ---------------------------------------------------------------------------
# WorkflowInstance
# ---------------------------------------------------------------------------


class TestWorkflowInstance:
    def test_defaults(self):
        instance = WorkflowInstance(
            workflow_type="order",
            workflow_id="ord-1",
            tenant_id="t1",
        )
        assert instance.status == WorkflowStatus.PENDING
        assert isinstance(instance.id, UUID)
        assert instance.input is None
        assert instance.output is None
        assert instance.error is None
        assert instance.started_at is None
        assert instance.completed_at is None
        assert instance.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_input(self):
        instance = WorkflowInstance(
            workflow_type="deploy",
            workflow_id="dep-1",
            tenant_id="t1",
            input={"env": "prod"},
        )
        assert instance.input == {"env": "prod"}

    def test_custom_status(self):
        instance = WorkflowInstance(
            workflow_type="deploy",
            workflow_id="dep-1",
            tenant_id="t1",
            status=WorkflowStatus.RUNNING,
        )
        assert instance.status == WorkflowStatus.RUNNING

    def test_timestamps_auto_set(self):
        instance = WorkflowInstance(
            workflow_type="order",
            workflow_id="ord-1",
            tenant_id="t1",
        )
        assert instance.created_at is not None
        assert instance.updated_at is not None

    def test_model_dump(self):
        instance = WorkflowInstance(
            workflow_type="order",
            workflow_id="ord-1",
            tenant_id="t1",
        )
        d = instance.model_dump()
        assert d["workflow_type"] == "order"
        assert d["status"] == "pending"  # use_enum_values


# ---------------------------------------------------------------------------
# WorkflowStep
# ---------------------------------------------------------------------------


class TestWorkflowStep:
    def test_defaults(self):
        wf_id = uuid4()
        step = WorkflowStep(
            workflow_instance_id=wf_id,
            step_name="validate",
            step_type=StepType.ACTIVITY,
        )
        assert step.status == StepStatus.PENDING
        assert step.attempt_count == 0
        assert step.idempotency_key is None

    def test_with_idempotency_key(self):
        wf_id = uuid4()
        step = WorkflowStep(
            workflow_instance_id=wf_id,
            step_name="charge",
            step_type=StepType.ACTIVITY,
            idempotency_key="key-123",
        )
        assert step.idempotency_key == "key-123"

    def test_model_dump(self):
        wf_id = uuid4()
        step = WorkflowStep(
            workflow_instance_id=wf_id,
            step_name="reserve",
            step_type=StepType.ACTIVITY,
        )
        d = step.model_dump()
        assert d["step_type"] == "activity"
        assert d["status"] == "pending"


# ---------------------------------------------------------------------------
# WorkflowEvent
# ---------------------------------------------------------------------------


class TestWorkflowEvent:
    def test_creation(self):
        wf_id = uuid4()
        event = WorkflowEvent(
            workflow_instance_id=wf_id,
            event_type=EventType.WORKFLOW_STARTED,
            event_data={"workflow_type": "order"},
            sequence_number=1,
        )
        assert event.event_type == EventType.WORKFLOW_STARTED
        assert event.sequence_number == 1
        assert event.id is None

    def test_model_dump(self):
        wf_id = uuid4()
        event = WorkflowEvent(
            workflow_instance_id=wf_id,
            event_type=EventType.STEP_COMPLETED,
            event_data={"step": "reserve"},
            sequence_number=2,
        )
        d = event.model_dump()
        assert d["event_type"] == "step_completed"


# ---------------------------------------------------------------------------
# WorkflowCompensation
# ---------------------------------------------------------------------------


class TestWorkflowCompensation:
    def test_defaults(self):
        wf_id = uuid4()
        step_id = uuid4()
        comp = WorkflowCompensation(
            workflow_instance_id=wf_id,
            step_id=step_id,
            compensation_name="refund_payment",
        )
        assert comp.status == StepStatus.PENDING
        assert comp.input is None
        assert comp.output is None
        assert comp.error is None
        assert comp.executed_at is None

    def test_model_dump(self):
        wf_id = uuid4()
        step_id = uuid4()
        comp = WorkflowCompensation(
            workflow_instance_id=wf_id,
            step_id=step_id,
            compensation_name="release_inventory",
            input={"order_id": "o1"},
        )
        d = comp.model_dump()
        assert d["compensation_name"] == "release_inventory"
        assert d["status"] == "pending"


# ---------------------------------------------------------------------------
# CheckpointData
# ---------------------------------------------------------------------------


class TestCheckpointData:
    def test_creation(self):
        wf_id = uuid4()
        cp = CheckpointData(
            workflow_instance_id=wf_id,
            step_index=3,
            state={"key": "value"},
        )
        assert cp.step_index == 3
        assert isinstance(cp.checkpoint_id, UUID)
        assert cp.state == {"key": "value"}

    def test_model_dump(self):
        wf_id = uuid4()
        cp = CheckpointData(
            workflow_instance_id=wf_id,
            step_index=0,
            state={},
        )
        d = cp.model_dump()
        assert "checkpoint_id" in d
        assert "created_at" in d
