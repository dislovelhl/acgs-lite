# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for persistence/models.py

Targets ≥95% line coverage of the 84-statement module.
Covers all enums, models, fields, validators, defaults, and edge cases.
"""

import os
import sys
from datetime import UTC, datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

# Ensure the enhanced_agent_bus package is importable
_eab_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _eab_dir not in sys.path:
    sys.path.insert(0, _eab_dir)

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.persistence.models import (
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
# WorkflowStatus enum
# ---------------------------------------------------------------------------
class TestWorkflowStatus:
    def test_all_values_exist(self):
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"
        assert WorkflowStatus.CANCELLED == "cancelled"
        assert WorkflowStatus.COMPENSATING == "compensating"
        assert WorkflowStatus.COMPENSATED == "compensated"

    def test_is_str_enum(self):
        for member in WorkflowStatus:
            assert isinstance(member.value, str)

    def test_count(self):
        assert len(WorkflowStatus) == 7

    def test_string_comparison(self):
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING != "completed"

    def test_iteration(self):
        values = [s.value for s in WorkflowStatus]
        assert "pending" in values
        assert "compensated" in values

    def test_from_value(self):
        assert WorkflowStatus("pending") == WorkflowStatus.PENDING
        assert WorkflowStatus("compensating") == WorkflowStatus.COMPENSATING

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            WorkflowStatus("invalid_status")


# ---------------------------------------------------------------------------
# StepStatus enum
# ---------------------------------------------------------------------------
class TestStepStatus:
    def test_all_values_exist(self):
        assert StepStatus.PENDING == "pending"
        assert StepStatus.EXECUTING == "executing"
        assert StepStatus.COMPLETED == "completed"
        assert StepStatus.FAILED == "failed"
        assert StepStatus.SKIPPED == "skipped"
        assert StepStatus.COMPENSATING == "compensating"
        assert StepStatus.COMPENSATED == "compensated"
        assert StepStatus.COMPENSATION_FAILED == "compensation_failed"

    def test_count(self):
        assert len(StepStatus) == 8

    def test_is_str_enum(self):
        for member in StepStatus:
            assert isinstance(member.value, str)

    def test_from_value(self):
        assert StepStatus("executing") == StepStatus.EXECUTING
        assert StepStatus("compensation_failed") == StepStatus.COMPENSATION_FAILED

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            StepStatus("unknown")


# ---------------------------------------------------------------------------
# StepType enum
# ---------------------------------------------------------------------------
class TestStepType:
    def test_all_values_exist(self):
        assert StepType.ACTIVITY == "activity"
        assert StepType.DECISION == "decision"
        assert StepType.COMPENSATION == "compensation"
        assert StepType.CHECKPOINT == "checkpoint"
        assert StepType.WAIT == "wait"

    def test_count(self):
        assert len(StepType) == 5

    def test_is_str_enum(self):
        for member in StepType:
            assert isinstance(member.value, str)

    def test_from_value(self):
        assert StepType("activity") == StepType.ACTIVITY
        assert StepType("wait") == StepType.WAIT

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            StepType("not_a_type")


# ---------------------------------------------------------------------------
# EventType enum
# ---------------------------------------------------------------------------
class TestEventType:
    def test_all_values_exist(self):
        assert EventType.WORKFLOW_STARTED == "workflow_started"
        assert EventType.WORKFLOW_COMPLETED == "workflow_completed"
        assert EventType.WORKFLOW_FAILED == "workflow_failed"
        assert EventType.WORKFLOW_CANCELLED == "workflow_cancelled"
        assert EventType.STEP_STARTED == "step_started"
        assert EventType.STEP_COMPLETED == "step_completed"
        assert EventType.STEP_FAILED == "step_failed"
        assert EventType.COMPENSATION_STARTED == "compensation_started"
        assert EventType.COMPENSATION_COMPLETED == "compensation_completed"
        assert EventType.COMPENSATION_FAILED == "compensation_failed"
        assert EventType.CHECKPOINT_CREATED == "checkpoint_created"
        assert EventType.CHECKPOINT_RESTORED == "checkpoint_restored"
        assert EventType.TIMER_FIRED == "timer_fired"
        assert EventType.SIGNAL_RECEIVED == "signal_received"

    def test_count(self):
        assert len(EventType) == 14

    def test_is_str_enum(self):
        for member in EventType:
            assert isinstance(member.value, str)

    def test_from_value(self):
        assert EventType("timer_fired") == EventType.TIMER_FIRED
        assert EventType("signal_received") == EventType.SIGNAL_RECEIVED

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            EventType("bad_event")


# ---------------------------------------------------------------------------
# WorkflowInstance model
# ---------------------------------------------------------------------------
class TestWorkflowInstance:
    def _make(self, **kwargs):
        defaults = dict(
            workflow_type="order_processing",
            workflow_id="wf-001",
            tenant_id="tenant-42",
        )
        defaults.update(kwargs)
        return WorkflowInstance(**defaults)

    def test_minimal_creation(self):
        inst = self._make()
        assert inst.workflow_type == "order_processing"
        assert inst.workflow_id == "wf-001"
        assert inst.tenant_id == "tenant-42"

    def test_id_is_uuid(self):
        inst = self._make()
        assert isinstance(inst.id, UUID)

    def test_id_is_unique(self):
        a = self._make()
        b = self._make()
        assert a.id != b.id

    def test_custom_id(self):
        uid = uuid4()
        inst = self._make(id=uid)
        assert inst.id == uid

    def test_default_status_is_pending(self):
        inst = self._make()
        # use_enum_values=True so status is a string
        assert inst.status == "pending"

    def test_status_enum_value(self):
        inst = self._make(status=WorkflowStatus.RUNNING)
        assert inst.status == "running"

    def test_status_string_directly(self):
        inst = self._make(status="completed")
        assert inst.status == "completed"

    def test_all_status_values_accepted(self):
        for status in WorkflowStatus:
            inst = self._make(status=status)
            assert inst.status == status.value

    def test_input_none_by_default(self):
        inst = self._make()
        assert inst.input is None

    def test_input_dict(self):
        inst = self._make(input={"key": "value"})
        assert inst.input == {"key": "value"}

    def test_output_none_by_default(self):
        inst = self._make()
        assert inst.output is None

    def test_output_dict(self):
        inst = self._make(output={"result": 42})
        assert inst.output == {"result": 42}

    def test_error_none_by_default(self):
        inst = self._make()
        assert inst.error is None

    def test_error_string(self):
        inst = self._make(error="something went wrong")
        assert inst.error == "something went wrong"

    def test_started_at_none_by_default(self):
        inst = self._make()
        assert inst.started_at is None

    def test_started_at_set(self):
        now = datetime.now(UTC)
        inst = self._make(started_at=now)
        assert inst.started_at == now

    def test_completed_at_none_by_default(self):
        inst = self._make()
        assert inst.completed_at is None

    def test_completed_at_set(self):
        now = datetime.now(UTC)
        inst = self._make(completed_at=now)
        assert inst.completed_at == now

    def test_constitutional_hash_default(self):
        inst = self._make()
        assert inst.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_custom(self):
        inst = self._make(constitutional_hash="custom-hash")
        assert inst.constitutional_hash == "custom-hash"

    def test_created_at_is_datetime(self):
        inst = self._make()
        assert isinstance(inst.created_at, datetime)

    def test_updated_at_is_datetime(self):
        inst = self._make()
        assert isinstance(inst.updated_at, datetime)

    def test_created_at_custom(self):
        ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        inst = self._make(created_at=ts)
        assert inst.created_at == ts

    def test_model_dump(self):
        inst = self._make()
        d = inst.model_dump()
        assert "id" in d
        assert d["workflow_type"] == "order_processing"
        assert d["status"] == "pending"

    def test_model_json(self):
        inst = self._make()
        j = inst.model_dump_json()
        assert "order_processing" in j
        assert "pending" in j

    def test_missing_workflow_type_raises(self):
        with pytest.raises(ValidationError):
            WorkflowInstance(workflow_id="wf-1", tenant_id="t-1")

    def test_missing_workflow_id_raises(self):
        with pytest.raises(ValidationError):
            WorkflowInstance(workflow_type="t", tenant_id="t-1")

    def test_missing_tenant_id_raises(self):
        with pytest.raises(ValidationError):
            WorkflowInstance(workflow_type="t", workflow_id="wf-1")

    def test_full_construction(self):
        uid = uuid4()
        now = datetime.now(UTC)
        inst = WorkflowInstance(
            id=uid,
            workflow_type="saga",
            workflow_id="saga-999",
            tenant_id="t-999",
            status=WorkflowStatus.COMPLETED,
            input={"a": 1},
            output={"b": 2},
            error=None,
            started_at=now,
            completed_at=now,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        assert inst.id == uid
        assert inst.status == "completed"
        assert inst.input == {"a": 1}
        assert inst.output == {"b": 2}


# ---------------------------------------------------------------------------
# WorkflowStep model
# ---------------------------------------------------------------------------
class TestWorkflowStep:
    def _make(self, **kwargs):
        defaults = dict(
            workflow_instance_id=uuid4(),
            step_name="process_payment",
            step_type=StepType.ACTIVITY,
        )
        defaults.update(kwargs)
        return WorkflowStep(**defaults)

    def test_minimal_creation(self):
        step = self._make()
        assert step.step_name == "process_payment"

    def test_id_is_uuid(self):
        step = self._make()
        assert isinstance(step.id, UUID)

    def test_id_is_unique(self):
        a = self._make()
        b = self._make()
        assert a.id != b.id

    def test_custom_id(self):
        uid = uuid4()
        step = self._make(id=uid)
        assert step.id == uid

    def test_workflow_instance_id(self):
        wid = uuid4()
        step = self._make(workflow_instance_id=wid)
        assert step.workflow_instance_id == wid

    def test_default_status_is_pending(self):
        step = self._make()
        assert step.status == "pending"

    def test_all_step_statuses_accepted(self):
        for status in StepStatus:
            step = self._make(status=status)
            assert step.status == status.value

    def test_all_step_types_accepted(self):
        for stype in StepType:
            step = self._make(step_type=stype)
            assert step.step_type == stype.value

    def test_input_none_by_default(self):
        step = self._make()
        assert step.input is None

    def test_input_dict(self):
        step = self._make(input={"amount": 100})
        assert step.input == {"amount": 100}

    def test_output_none_by_default(self):
        step = self._make()
        assert step.output is None

    def test_output_dict(self):
        step = self._make(output={"tx_id": "abc"})
        assert step.output == {"tx_id": "abc"}

    def test_error_none_by_default(self):
        step = self._make()
        assert step.error is None

    def test_error_string(self):
        step = self._make(error="payment declined")
        assert step.error == "payment declined"

    def test_idempotency_key_none_by_default(self):
        step = self._make()
        assert step.idempotency_key is None

    def test_idempotency_key_string(self):
        step = self._make(idempotency_key="idem-key-123")
        assert step.idempotency_key == "idem-key-123"

    def test_attempt_count_default_zero(self):
        step = self._make()
        assert step.attempt_count == 0

    def test_attempt_count_custom(self):
        step = self._make(attempt_count=3)
        assert step.attempt_count == 3

    def test_started_at_none_by_default(self):
        step = self._make()
        assert step.started_at is None

    def test_completed_at_none_by_default(self):
        step = self._make()
        assert step.completed_at is None

    def test_timestamps_set(self):
        now = datetime.now(UTC)
        step = self._make(started_at=now, completed_at=now)
        assert step.started_at == now
        assert step.completed_at == now

    def test_created_at_is_datetime(self):
        step = self._make()
        assert isinstance(step.created_at, datetime)

    def test_model_dump(self):
        step = self._make()
        d = step.model_dump()
        assert "id" in d
        assert d["step_name"] == "process_payment"
        assert d["attempt_count"] == 0

    def test_missing_workflow_instance_id_raises(self):
        with pytest.raises(ValidationError):
            WorkflowStep(step_name="s", step_type=StepType.ACTIVITY)

    def test_missing_step_name_raises(self):
        with pytest.raises(ValidationError):
            WorkflowStep(
                workflow_instance_id=uuid4(),
                step_type=StepType.ACTIVITY,
            )

    def test_missing_step_type_raises(self):
        with pytest.raises(ValidationError):
            WorkflowStep(
                workflow_instance_id=uuid4(),
                step_name="s",
            )

    def test_decision_step_type(self):
        step = self._make(step_type=StepType.DECISION)
        assert step.step_type == "decision"

    def test_compensation_step_type(self):
        step = self._make(step_type=StepType.COMPENSATION)
        assert step.step_type == "compensation"

    def test_checkpoint_step_type(self):
        step = self._make(step_type=StepType.CHECKPOINT)
        assert step.step_type == "checkpoint"

    def test_wait_step_type(self):
        step = self._make(step_type=StepType.WAIT)
        assert step.step_type == "wait"


# ---------------------------------------------------------------------------
# WorkflowEvent model
# ---------------------------------------------------------------------------
class TestWorkflowEvent:
    def _make(self, **kwargs):
        defaults = dict(
            workflow_instance_id=uuid4(),
            event_type=EventType.WORKFLOW_STARTED,
            event_data={"action": "start"},
            sequence_number=1,
        )
        defaults.update(kwargs)
        return WorkflowEvent(**defaults)

    def test_minimal_creation(self):
        evt = self._make()
        assert evt.sequence_number == 1

    def test_id_is_none_by_default(self):
        evt = self._make()
        assert evt.id is None

    def test_id_can_be_set(self):
        evt = self._make(id=42)
        assert evt.id == 42

    def test_workflow_instance_id(self):
        wid = uuid4()
        evt = self._make(workflow_instance_id=wid)
        assert evt.workflow_instance_id == wid

    def test_event_type_stored_as_string(self):
        evt = self._make(event_type=EventType.STEP_COMPLETED)
        assert evt.event_type == "step_completed"

    def test_all_event_types_accepted(self):
        for et in EventType:
            evt = self._make(event_type=et)
            assert evt.event_type == et.value

    def test_event_data_dict(self):
        data = {"key": "val", "num": 99}
        evt = self._make(event_data=data)
        assert evt.event_data == data

    def test_sequence_number(self):
        evt = self._make(sequence_number=100)
        assert evt.sequence_number == 100

    def test_timestamp_is_datetime(self):
        evt = self._make()
        assert isinstance(evt.timestamp, datetime)

    def test_timestamp_custom(self):
        ts = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)
        evt = self._make(timestamp=ts)
        assert evt.timestamp == ts

    def test_model_dump(self):
        evt = self._make()
        d = evt.model_dump()
        assert d["sequence_number"] == 1
        assert d["event_data"] == {"action": "start"}

    def test_missing_workflow_instance_id_raises(self):
        with pytest.raises(ValidationError):
            WorkflowEvent(
                event_type=EventType.STEP_STARTED,
                event_data={},
                sequence_number=1,
            )

    def test_missing_event_type_raises(self):
        with pytest.raises(ValidationError):
            WorkflowEvent(
                workflow_instance_id=uuid4(),
                event_data={},
                sequence_number=1,
            )

    def test_missing_event_data_raises(self):
        with pytest.raises(ValidationError):
            WorkflowEvent(
                workflow_instance_id=uuid4(),
                event_type=EventType.STEP_STARTED,
                sequence_number=1,
            )

    def test_missing_sequence_number_raises(self):
        with pytest.raises(ValidationError):
            WorkflowEvent(
                workflow_instance_id=uuid4(),
                event_type=EventType.STEP_STARTED,
                event_data={},
            )

    def test_workflow_failed_event(self):
        evt = self._make(event_type=EventType.WORKFLOW_FAILED, event_data={"reason": "timeout"})
        assert evt.event_type == "workflow_failed"

    def test_compensation_events(self):
        for et in [
            EventType.COMPENSATION_STARTED,
            EventType.COMPENSATION_COMPLETED,
            EventType.COMPENSATION_FAILED,
        ]:
            evt = self._make(event_type=et)
            assert evt.event_type == et.value

    def test_checkpoint_events(self):
        for et in [EventType.CHECKPOINT_CREATED, EventType.CHECKPOINT_RESTORED]:
            evt = self._make(event_type=et)
            assert evt.event_type == et.value

    def test_timer_and_signal_events(self):
        timer = self._make(event_type=EventType.TIMER_FIRED)
        sig = self._make(event_type=EventType.SIGNAL_RECEIVED)
        assert timer.event_type == "timer_fired"
        assert sig.event_type == "signal_received"


# ---------------------------------------------------------------------------
# WorkflowCompensation model
# ---------------------------------------------------------------------------
class TestWorkflowCompensation:
    def _make(self, **kwargs):
        defaults = dict(
            workflow_instance_id=uuid4(),
            step_id=uuid4(),
            compensation_name="rollback_payment",
        )
        defaults.update(kwargs)
        return WorkflowCompensation(**defaults)

    def test_minimal_creation(self):
        comp = self._make()
        assert comp.compensation_name == "rollback_payment"

    def test_id_is_uuid(self):
        comp = self._make()
        assert isinstance(comp.id, UUID)

    def test_id_is_unique(self):
        a = self._make()
        b = self._make()
        assert a.id != b.id

    def test_custom_id(self):
        uid = uuid4()
        comp = self._make(id=uid)
        assert comp.id == uid

    def test_workflow_instance_id(self):
        wid = uuid4()
        comp = self._make(workflow_instance_id=wid)
        assert comp.workflow_instance_id == wid

    def test_step_id(self):
        sid = uuid4()
        comp = self._make(step_id=sid)
        assert comp.step_id == sid

    def test_default_status_is_pending(self):
        comp = self._make()
        assert comp.status == "pending"

    def test_all_step_statuses_accepted(self):
        for status in StepStatus:
            comp = self._make(status=status)
            assert comp.status == status.value

    def test_input_none_by_default(self):
        comp = self._make()
        assert comp.input is None

    def test_input_dict(self):
        comp = self._make(input={"tx_id": "tx-001"})
        assert comp.input == {"tx_id": "tx-001"}

    def test_output_none_by_default(self):
        comp = self._make()
        assert comp.output is None

    def test_output_dict(self):
        comp = self._make(output={"refunded": True})
        assert comp.output == {"refunded": True}

    def test_error_none_by_default(self):
        comp = self._make()
        assert comp.error is None

    def test_error_string(self):
        comp = self._make(error="refund failed")
        assert comp.error == "refund failed"

    def test_executed_at_none_by_default(self):
        comp = self._make()
        assert comp.executed_at is None

    def test_executed_at_set(self):
        now = datetime.now(UTC)
        comp = self._make(executed_at=now)
        assert comp.executed_at == now

    def test_created_at_is_datetime(self):
        comp = self._make()
        assert isinstance(comp.created_at, datetime)

    def test_model_dump(self):
        comp = self._make()
        d = comp.model_dump()
        assert d["compensation_name"] == "rollback_payment"
        assert d["status"] == "pending"

    def test_missing_workflow_instance_id_raises(self):
        with pytest.raises(ValidationError):
            WorkflowCompensation(
                step_id=uuid4(),
                compensation_name="rollback",
            )

    def test_missing_step_id_raises(self):
        with pytest.raises(ValidationError):
            WorkflowCompensation(
                workflow_instance_id=uuid4(),
                compensation_name="rollback",
            )

    def test_missing_compensation_name_raises(self):
        with pytest.raises(ValidationError):
            WorkflowCompensation(
                workflow_instance_id=uuid4(),
                step_id=uuid4(),
            )

    def test_executing_status(self):
        comp = self._make(status=StepStatus.EXECUTING)
        assert comp.status == "executing"

    def test_compensation_failed_status(self):
        comp = self._make(status=StepStatus.COMPENSATION_FAILED)
        assert comp.status == "compensation_failed"


# ---------------------------------------------------------------------------
# CheckpointData model
# ---------------------------------------------------------------------------
class TestCheckpointData:
    def _make(self, **kwargs):
        defaults = dict(
            workflow_instance_id=uuid4(),
            step_index=5,
            state={"current_step": "payment", "completed": ["init", "auth"]},
        )
        defaults.update(kwargs)
        return CheckpointData(**defaults)

    def test_minimal_creation(self):
        cp = self._make()
        assert cp.step_index == 5

    def test_workflow_instance_id(self):
        wid = uuid4()
        cp = self._make(workflow_instance_id=wid)
        assert cp.workflow_instance_id == wid

    def test_checkpoint_id_is_uuid(self):
        cp = self._make()
        assert isinstance(cp.checkpoint_id, UUID)

    def test_checkpoint_id_is_unique(self):
        a = self._make()
        b = self._make()
        assert a.checkpoint_id != b.checkpoint_id

    def test_custom_checkpoint_id(self):
        uid = uuid4()
        cp = self._make(checkpoint_id=uid)
        assert cp.checkpoint_id == uid

    def test_step_index(self):
        cp = self._make(step_index=0)
        assert cp.step_index == 0

    def test_step_index_large(self):
        cp = self._make(step_index=9999)
        assert cp.step_index == 9999

    def test_state_dict(self):
        state = {"key": "val", "nested": {"a": 1}}
        cp = self._make(state=state)
        assert cp.state == state

    def test_state_empty_dict(self):
        cp = self._make(state={})
        assert cp.state == {}

    def test_created_at_is_datetime(self):
        cp = self._make()
        assert isinstance(cp.created_at, datetime)

    def test_created_at_custom(self):
        ts = datetime(2025, 3, 10, 8, 30, 0, tzinfo=UTC)
        cp = self._make(created_at=ts)
        assert cp.created_at == ts

    def test_model_dump(self):
        cp = self._make()
        d = cp.model_dump()
        assert d["step_index"] == 5
        assert "checkpoint_id" in d
        assert "state" in d

    def test_model_json(self):
        cp = self._make()
        j = cp.model_dump_json()
        assert "checkpoint_id" in j

    def test_missing_workflow_instance_id_raises(self):
        with pytest.raises(ValidationError):
            CheckpointData(step_index=1, state={})

    def test_missing_step_index_raises(self):
        with pytest.raises(ValidationError):
            CheckpointData(workflow_instance_id=uuid4(), state={})

    def test_missing_state_raises(self):
        with pytest.raises(ValidationError):
            CheckpointData(workflow_instance_id=uuid4(), step_index=1)

    def test_full_construction(self):
        wid = uuid4()
        cid = uuid4()
        ts = datetime.now(UTC)
        cp = CheckpointData(
            workflow_instance_id=wid,
            checkpoint_id=cid,
            step_index=7,
            state={"x": 1},
            created_at=ts,
        )
        assert cp.workflow_instance_id == wid
        assert cp.checkpoint_id == cid
        assert cp.step_index == 7
        assert cp.state == {"x": 1}
        assert cp.created_at == ts


# ---------------------------------------------------------------------------
# Cross-model integration checks
# ---------------------------------------------------------------------------
class TestCrossModel:
    def test_workflow_instance_and_step_link(self):
        wi = WorkflowInstance(
            workflow_type="saga",
            workflow_id="saga-1",
            tenant_id="t-1",
        )
        step = WorkflowStep(
            workflow_instance_id=wi.id,
            step_name="step1",
            step_type=StepType.ACTIVITY,
        )
        assert step.workflow_instance_id == wi.id

    def test_workflow_instance_and_event_link(self):
        wi = WorkflowInstance(
            workflow_type="saga",
            workflow_id="saga-2",
            tenant_id="t-1",
        )
        evt = WorkflowEvent(
            workflow_instance_id=wi.id,
            event_type=EventType.WORKFLOW_STARTED,
            event_data={},
            sequence_number=1,
        )
        assert evt.workflow_instance_id == wi.id

    def test_step_and_compensation_link(self):
        step = WorkflowStep(
            workflow_instance_id=uuid4(),
            step_name="pay",
            step_type=StepType.ACTIVITY,
        )
        comp = WorkflowCompensation(
            workflow_instance_id=step.workflow_instance_id,
            step_id=step.id,
            compensation_name="refund",
        )
        assert comp.step_id == step.id

    def test_checkpoint_matches_instance(self):
        wi = WorkflowInstance(
            workflow_type="saga",
            workflow_id="saga-3",
            tenant_id="t-2",
        )
        cp = CheckpointData(
            workflow_instance_id=wi.id,
            step_index=2,
            state={"done": ["a"]},
        )
        assert cp.workflow_instance_id == wi.id

    def test_constitutional_hash_constant(self):
        """Ensure the CONSTITUTIONAL_HASH used in models matches the project constant."""
        wi = WorkflowInstance(
            workflow_type="t",
            workflow_id="w",
            tenant_id="t",
        )
        assert wi.constitutional_hash == CONSTITUTIONAL_HASH

    def test_use_enum_values_true_for_all_models(self):
        """Models with use_enum_values=True store strings, not enum members."""
        wi = WorkflowInstance(
            workflow_type="t",
            workflow_id="w",
            tenant_id="t",
            status=WorkflowStatus.CANCELLED,
        )
        assert wi.status == "cancelled"
        assert not isinstance(wi.status, WorkflowStatus)

        step = WorkflowStep(
            workflow_instance_id=uuid4(),
            step_name="s",
            step_type=StepType.WAIT,
            status=StepStatus.SKIPPED,
        )
        assert step.status == "skipped"
        assert step.step_type == "wait"

        evt = WorkflowEvent(
            workflow_instance_id=uuid4(),
            event_type=EventType.TIMER_FIRED,
            event_data={},
            sequence_number=99,
        )
        assert evt.event_type == "timer_fired"

        comp = WorkflowCompensation(
            workflow_instance_id=uuid4(),
            step_id=uuid4(),
            compensation_name="c",
            status=StepStatus.COMPENSATED,
        )
        assert comp.status == "compensated"
