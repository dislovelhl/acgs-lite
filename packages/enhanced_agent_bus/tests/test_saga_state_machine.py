"""
Tests for persistence/models.py and persistence/repository.py

Note: The originally requested source file `saga_state_machine.py` does not exist.
This test file covers `persistence/models.py` (workflow state models) and
`persistence/repository.py` (InMemoryWorkflowRepository) which implement
the saga state machine persistence layer.

Covers:
- WorkflowStatus, StepStatus, StepType, EventType enums
- WorkflowInstance, WorkflowStep, WorkflowEvent, WorkflowCompensation, CheckpointData models
- InMemoryWorkflowRepository: full CRUD coverage
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

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
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_workflow_status_values(self):
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.COMPENSATING == "compensating"
        assert WorkflowStatus.COMPENSATED == "compensated"

    def test_step_status_values(self):
        assert StepStatus.PENDING == "pending"
        assert StepStatus.EXECUTING == "executing"
        assert StepStatus.COMPENSATION_FAILED == "compensation_failed"

    def test_step_type_values(self):
        assert StepType.ACTIVITY == "activity"
        assert StepType.DECISION == "decision"
        assert StepType.COMPENSATION == "compensation"
        assert StepType.CHECKPOINT == "checkpoint"

    def test_event_type_values(self):
        assert EventType.WORKFLOW_STARTED == "workflow_started"
        assert EventType.STEP_COMPLETED == "step_completed"
        assert EventType.COMPENSATION_FAILED == "compensation_failed"


# ---------------------------------------------------------------------------
# Model construction tests
# ---------------------------------------------------------------------------


class TestWorkflowInstance:
    def test_defaults(self):
        wf = WorkflowInstance(
            workflow_type="saga",
            workflow_id="wf-1",
            tenant_id="t-1",
        )
        assert wf.status == WorkflowStatus.PENDING
        assert wf.input is None
        assert wf.output is None
        assert wf.error is None
        assert wf.id is not None
        assert wf.created_at is not None

    def test_with_all_fields(self):
        wf = WorkflowInstance(
            workflow_type="saga",
            workflow_id="wf-1",
            tenant_id="t-1",
            status=WorkflowStatus.RUNNING,
            input={"key": "value"},
            started_at=datetime.now(UTC),
        )
        assert wf.status == WorkflowStatus.RUNNING
        assert wf.input == {"key": "value"}


class TestWorkflowStep:
    def test_defaults(self):
        wf_id = uuid4()
        step = WorkflowStep(
            workflow_instance_id=wf_id,
            step_name="process_payment",
            step_type=StepType.ACTIVITY,
        )
        assert step.status == StepStatus.PENDING
        assert step.attempt_count == 0
        assert step.idempotency_key is None

    def test_with_idempotency_key(self):
        step = WorkflowStep(
            workflow_instance_id=uuid4(),
            step_name="debit",
            step_type=StepType.ACTIVITY,
            idempotency_key="debit-abc-123",
        )
        assert step.idempotency_key == "debit-abc-123"


class TestWorkflowEvent:
    def test_construction(self):
        event = WorkflowEvent(
            workflow_instance_id=uuid4(),
            event_type=EventType.WORKFLOW_STARTED,
            event_data={"trigger": "manual"},
            sequence_number=1,
        )
        assert event.sequence_number == 1
        assert event.event_data["trigger"] == "manual"


class TestWorkflowCompensation:
    def test_construction(self):
        comp = WorkflowCompensation(
            workflow_instance_id=uuid4(),
            step_id=uuid4(),
            compensation_name="refund_payment",
        )
        assert comp.status == StepStatus.PENDING
        assert comp.executed_at is None


class TestCheckpointData:
    def test_construction(self):
        cp = CheckpointData(
            workflow_instance_id=uuid4(),
            step_index=5,
            state={"balance": 100},
        )
        assert cp.step_index == 5
        assert cp.state["balance"] == 100
        assert cp.checkpoint_id is not None


# ---------------------------------------------------------------------------
# InMemoryWorkflowRepository tests
# ---------------------------------------------------------------------------


class TestInMemoryWorkflowRepository:
    @pytest.fixture
    def repo(self):
        return InMemoryWorkflowRepository()

    @pytest.fixture
    def sample_workflow(self):
        return WorkflowInstance(
            workflow_type="payment_saga",
            workflow_id="order-42",
            tenant_id="tenant-a",
            status=WorkflowStatus.RUNNING,
            input={"amount": 100},
        )

    # -- Workflow CRUD --

    @pytest.mark.asyncio
    async def test_save_and_get_workflow(self, repo, sample_workflow):
        await repo.save_workflow(sample_workflow)
        retrieved = await repo.get_workflow(sample_workflow.id)
        assert retrieved is not None
        assert retrieved.workflow_id == "order-42"

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, repo):
        result = await repo.get_workflow(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_workflow_by_business_id(self, repo, sample_workflow):
        await repo.save_workflow(sample_workflow)
        result = await repo.get_workflow_by_business_id("order-42", "tenant-a")
        assert result is not None
        assert result.id == sample_workflow.id

    @pytest.mark.asyncio
    async def test_get_workflow_by_business_id_not_found(self, repo):
        result = await repo.get_workflow_by_business_id("nonexistent", "tenant-a")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_workflows(self, repo):
        for i in range(3):
            wf = WorkflowInstance(
                workflow_type="saga",
                workflow_id=f"wf-{i}",
                tenant_id="tenant-a",
            )
            await repo.save_workflow(wf)
        # Different tenant
        other = WorkflowInstance(
            workflow_type="saga",
            workflow_id="wf-other",
            tenant_id="tenant-b",
        )
        await repo.save_workflow(other)

        results = await repo.list_workflows("tenant-a")
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_list_workflows_filter_by_status(self, repo):
        wf_running = WorkflowInstance(
            workflow_type="saga",
            workflow_id="wf-r",
            tenant_id="t",
            status=WorkflowStatus.RUNNING,
        )
        wf_done = WorkflowInstance(
            workflow_type="saga",
            workflow_id="wf-d",
            tenant_id="t",
            status=WorkflowStatus.COMPLETED,
        )
        await repo.save_workflow(wf_running)
        await repo.save_workflow(wf_done)

        running = await repo.list_workflows("t", status=WorkflowStatus.RUNNING)
        assert len(running) == 1

    @pytest.mark.asyncio
    async def test_list_workflows_with_limit(self, repo):
        for i in range(5):
            await repo.save_workflow(
                WorkflowInstance(workflow_type="s", workflow_id=f"w-{i}", tenant_id="t")
            )
        results = await repo.list_workflows("t", limit=2)
        assert len(results) == 2

    # -- Step CRUD --

    @pytest.mark.asyncio
    async def test_save_and_get_steps(self, repo, sample_workflow):
        await repo.save_workflow(sample_workflow)
        wf_id = sample_workflow.id

        step1 = WorkflowStep(
            workflow_instance_id=wf_id,
            step_name="debit",
            step_type=StepType.ACTIVITY,
        )
        step2 = WorkflowStep(
            workflow_instance_id=wf_id,
            step_name="credit",
            step_type=StepType.ACTIVITY,
        )
        await repo.save_step(step1)
        await repo.save_step(step2)

        steps = await repo.get_steps(wf_id)
        assert len(steps) == 2

    @pytest.mark.asyncio
    async def test_get_step_by_idempotency_key(self, repo):
        wf_id = uuid4()
        step = WorkflowStep(
            workflow_instance_id=wf_id,
            step_name="debit",
            step_type=StepType.ACTIVITY,
            idempotency_key="idem-123",
        )
        await repo.save_step(step)

        found = await repo.get_step_by_idempotency_key(wf_id, "idem-123")
        assert found is not None
        assert found.step_name == "debit"

    @pytest.mark.asyncio
    async def test_get_step_by_idempotency_key_not_found(self, repo):
        result = await repo.get_step_by_idempotency_key(uuid4(), "nope")
        assert result is None

    # -- Event sourcing --

    @pytest.mark.asyncio
    async def test_save_and_get_events(self, repo):
        wf_id = uuid4()
        e1 = WorkflowEvent(
            workflow_instance_id=wf_id,
            event_type=EventType.WORKFLOW_STARTED,
            event_data={},
            sequence_number=1,
        )
        e2 = WorkflowEvent(
            workflow_instance_id=wf_id,
            event_type=EventType.STEP_STARTED,
            event_data={"step": "debit"},
            sequence_number=2,
        )
        await repo.save_event(e1)
        await repo.save_event(e2)

        events = await repo.get_events(wf_id)
        assert len(events) == 2
        assert events[0].sequence_number == 1
        assert events[1].sequence_number == 2

    @pytest.mark.asyncio
    async def test_get_events_empty(self, repo):
        events = await repo.get_events(uuid4())
        assert events == []

    @pytest.mark.asyncio
    async def test_get_next_sequence_empty(self, repo):
        seq = await repo.get_next_sequence(uuid4())
        assert seq == 1

    @pytest.mark.asyncio
    async def test_get_next_sequence_after_events(self, repo):
        wf_id = uuid4()
        await repo.save_event(
            WorkflowEvent(
                workflow_instance_id=wf_id,
                event_type=EventType.WORKFLOW_STARTED,
                event_data={},
                sequence_number=1,
            )
        )
        await repo.save_event(
            WorkflowEvent(
                workflow_instance_id=wf_id,
                event_type=EventType.STEP_STARTED,
                event_data={},
                sequence_number=2,
            )
        )
        seq = await repo.get_next_sequence(wf_id)
        assert seq == 3

    # -- Compensation --

    @pytest.mark.asyncio
    async def test_save_and_get_compensations(self, repo):
        wf_id = uuid4()
        comp = WorkflowCompensation(
            workflow_instance_id=wf_id,
            step_id=uuid4(),
            compensation_name="refund",
        )
        await repo.save_compensation(comp)

        comps = await repo.get_compensations(wf_id)
        assert len(comps) == 1
        assert comps[0].compensation_name == "refund"

    @pytest.mark.asyncio
    async def test_update_compensation(self, repo):
        wf_id = uuid4()
        comp = WorkflowCompensation(
            workflow_instance_id=wf_id,
            step_id=uuid4(),
            compensation_name="refund",
            status=StepStatus.PENDING,
        )
        await repo.save_compensation(comp)

        # Update status
        comp.status = StepStatus.COMPLETED
        comp.executed_at = datetime.now(UTC)
        await repo.save_compensation(comp)

        comps = await repo.get_compensations(wf_id)
        assert len(comps) == 1
        assert comps[0].status == StepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_compensations_empty(self, repo):
        comps = await repo.get_compensations(uuid4())
        assert comps == []

    # -- Checkpoints --

    @pytest.mark.asyncio
    async def test_save_and_get_checkpoint(self, repo):
        wf_id = uuid4()
        cp = CheckpointData(
            workflow_instance_id=wf_id,
            step_index=3,
            state={"balance": 50},
        )
        await repo.save_checkpoint(cp)

        latest = await repo.get_latest_checkpoint(wf_id)
        assert latest is not None
        assert latest.step_index == 3
        assert latest.state["balance"] == 50

    @pytest.mark.asyncio
    async def test_get_latest_checkpoint_returns_newest(self, repo):
        wf_id = uuid4()
        cp1 = CheckpointData(
            workflow_instance_id=wf_id,
            step_index=1,
            state={"v": 1},
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        cp2 = CheckpointData(
            workflow_instance_id=wf_id,
            step_index=5,
            state={"v": 2},
            created_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
        await repo.save_checkpoint(cp1)
        await repo.save_checkpoint(cp2)

        latest = await repo.get_latest_checkpoint(wf_id)
        assert latest.step_index == 5

    @pytest.mark.asyncio
    async def test_get_latest_checkpoint_not_found(self, repo):
        result = await repo.get_latest_checkpoint(uuid4())
        assert result is None
