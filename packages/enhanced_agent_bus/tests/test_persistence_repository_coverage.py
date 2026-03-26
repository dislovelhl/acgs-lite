# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/persistence/repository.py

Covers WorkflowRepository (abstract) and InMemoryWorkflowRepository (concrete),
including all CRUD operations, edge cases, and list/filter behaviours.
No real infrastructure required — InMemoryWorkflowRepository is pure in-memory.
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

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
from enhanced_agent_bus.persistence.repository import (
    InMemoryWorkflowRepository,
    WorkflowRepository,
)

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def make_workflow(
    *,
    workflow_type: str = "test_wf",
    workflow_id: str | None = None,
    tenant_id: str = "tenant-a",
    status: WorkflowStatus = WorkflowStatus.PENDING,
    created_at: datetime | None = None,
) -> WorkflowInstance:
    kwargs: dict = {
        "workflow_type": workflow_type,
        "workflow_id": workflow_id or str(uuid4()),
        "tenant_id": tenant_id,
        "status": status,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return WorkflowInstance(**kwargs)


def make_step(
    workflow_instance_id: UUID,
    *,
    step_name: str = "step1",
    step_type: StepType = StepType.ACTIVITY,
    idempotency_key: str | None = None,
    created_at: datetime | None = None,
) -> WorkflowStep:
    kwargs: dict = {
        "workflow_instance_id": workflow_instance_id,
        "step_name": step_name,
        "step_type": step_type,
        "idempotency_key": idempotency_key,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return WorkflowStep(**kwargs)


def make_event(
    workflow_instance_id: UUID,
    *,
    event_type: EventType = EventType.WORKFLOW_STARTED,
    sequence_number: int = 1,
    event_data: dict | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        workflow_instance_id=workflow_instance_id,
        event_type=event_type,
        event_data=event_data or {},
        sequence_number=sequence_number,
    )


def make_compensation(
    workflow_instance_id: UUID,
    step_id: UUID,
    *,
    compensation_name: str = "rollback",
) -> WorkflowCompensation:
    return WorkflowCompensation(
        workflow_instance_id=workflow_instance_id,
        step_id=step_id,
        compensation_name=compensation_name,
    )


def make_checkpoint(
    workflow_instance_id: UUID,
    *,
    step_index: int = 0,
    state: dict | None = None,
    created_at: datetime | None = None,
) -> CheckpointData:
    kwargs: dict = {
        "workflow_instance_id": workflow_instance_id,
        "step_index": step_index,
        "state": state or {},
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return CheckpointData(**kwargs)


# ---------------------------------------------------------------------------
# Abstract interface: WorkflowRepository cannot be instantiated directly
# ---------------------------------------------------------------------------


class TestWorkflowRepositoryAbstract:
    """Verify the ABC contract is enforced."""

    def test_abstract_class_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            WorkflowRepository()  # type: ignore[abstract]

    def test_concrete_subclass_without_all_methods_is_rejected(self):
        """A partial concrete subclass must also be rejected."""

        class Partial(WorkflowRepository):
            async def save_workflow(self, instance):
                pass

        with pytest.raises(TypeError):
            Partial()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# InMemoryWorkflowRepository — workflow CRUD
# ---------------------------------------------------------------------------


class TestInMemoryRepositoryWorkflow:
    """Tests for workflow save / get / list operations."""

    async def test_save_and_get_workflow(self):
        repo = InMemoryWorkflowRepository()
        wf = make_workflow()
        await repo.save_workflow(wf)

        result = await repo.get_workflow(wf.id)
        assert result is not None
        assert result.id == wf.id

    async def test_get_workflow_missing_returns_none(self):
        repo = InMemoryWorkflowRepository()
        result = await repo.get_workflow(uuid4())
        assert result is None

    async def test_save_workflow_overwrites_existing(self):
        repo = InMemoryWorkflowRepository()
        wf = make_workflow(status=WorkflowStatus.PENDING)
        await repo.save_workflow(wf)

        # Update status in-place (pydantic model is mutable via copy)
        wf_updated = wf.model_copy(update={"status": WorkflowStatus.RUNNING})
        await repo.save_workflow(wf_updated)

        result = await repo.get_workflow(wf.id)
        assert result is not None
        assert result.status == WorkflowStatus.RUNNING

    async def test_get_workflow_by_business_id_found(self):
        repo = InMemoryWorkflowRepository()
        wf = make_workflow(workflow_id="biz-123", tenant_id="t1")
        await repo.save_workflow(wf)

        result = await repo.get_workflow_by_business_id("biz-123", "t1")
        assert result is not None
        assert result.id == wf.id

    async def test_get_workflow_by_business_id_wrong_tenant(self):
        repo = InMemoryWorkflowRepository()
        wf = make_workflow(workflow_id="biz-123", tenant_id="t1")
        await repo.save_workflow(wf)

        result = await repo.get_workflow_by_business_id("biz-123", "t2")
        assert result is None

    async def test_get_workflow_by_business_id_wrong_id(self):
        repo = InMemoryWorkflowRepository()
        wf = make_workflow(workflow_id="biz-123", tenant_id="t1")
        await repo.save_workflow(wf)

        result = await repo.get_workflow_by_business_id("biz-999", "t1")
        assert result is None

    async def test_get_workflow_by_business_id_empty_repo(self):
        repo = InMemoryWorkflowRepository()
        result = await repo.get_workflow_by_business_id("any", "any")
        assert result is None


# ---------------------------------------------------------------------------
# InMemoryWorkflowRepository — list_workflows
# ---------------------------------------------------------------------------


class TestInMemoryRepositoryListWorkflows:
    """Tests for list_workflows filtering and limiting."""

    async def test_list_workflows_returns_all_for_tenant(self):
        repo = InMemoryWorkflowRepository()
        for _ in range(3):
            await repo.save_workflow(make_workflow(tenant_id="t1"))
        await repo.save_workflow(make_workflow(tenant_id="t2"))

        results = await repo.list_workflows("t1")
        assert len(results) == 3

    async def test_list_workflows_empty_for_unknown_tenant(self):
        repo = InMemoryWorkflowRepository()
        await repo.save_workflow(make_workflow(tenant_id="t1"))

        results = await repo.list_workflows("t-unknown")
        assert results == []

    async def test_list_workflows_filter_by_status(self):
        repo = InMemoryWorkflowRepository()
        await repo.save_workflow(make_workflow(tenant_id="t1", status=WorkflowStatus.PENDING))
        await repo.save_workflow(make_workflow(tenant_id="t1", status=WorkflowStatus.RUNNING))
        await repo.save_workflow(make_workflow(tenant_id="t1", status=WorkflowStatus.COMPLETED))

        pending = await repo.list_workflows("t1", status=WorkflowStatus.PENDING)
        running = await repo.list_workflows("t1", status=WorkflowStatus.RUNNING)
        completed = await repo.list_workflows("t1", status=WorkflowStatus.COMPLETED)

        assert len(pending) == 1
        assert len(running) == 1
        assert len(completed) == 1

    async def test_list_workflows_no_status_filter_returns_all(self):
        repo = InMemoryWorkflowRepository()
        await repo.save_workflow(make_workflow(tenant_id="t1", status=WorkflowStatus.PENDING))
        await repo.save_workflow(make_workflow(tenant_id="t1", status=WorkflowStatus.FAILED))

        results = await repo.list_workflows("t1", status=None)
        assert len(results) == 2

    async def test_list_workflows_respects_limit(self):
        repo = InMemoryWorkflowRepository()
        for _ in range(10):
            await repo.save_workflow(make_workflow(tenant_id="t1"))

        results = await repo.list_workflows("t1", limit=3)
        assert len(results) == 3

    async def test_list_workflows_sorted_newest_first(self):
        repo = InMemoryWorkflowRepository()
        base = datetime(2025, 1, 1, tzinfo=UTC)
        for i in range(3):
            wf = make_workflow(tenant_id="t1", created_at=base + timedelta(hours=i))
            await repo.save_workflow(wf)

        results = await repo.list_workflows("t1")
        # Newest first — last created (i=2) should come first
        assert results[0].created_at >= results[1].created_at
        assert results[1].created_at >= results[2].created_at

    async def test_list_workflows_with_none_created_at_does_not_crash(self):
        """WorkflowInstance with no created_at uses fallback datetime.now()."""
        repo = InMemoryWorkflowRepository()
        wf = WorkflowInstance(
            workflow_type="wt",
            workflow_id="w1",
            tenant_id="t1",
        )
        # Manually set created_at to None to test the fallback branch
        object.__setattr__(wf, "created_at", None)
        await repo.save_workflow(wf)

        results = await repo.list_workflows("t1")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# InMemoryWorkflowRepository — step operations
# ---------------------------------------------------------------------------


class TestInMemoryRepositorySteps:
    """Tests for workflow step save / get operations."""

    async def test_save_and_get_steps(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()

        s1 = make_step(wf_id, step_name="a")
        s2 = make_step(wf_id, step_name="b")
        await repo.save_step(s1)
        await repo.save_step(s2)

        steps = await repo.get_steps(wf_id)
        assert len(steps) == 2

    async def test_get_steps_empty(self):
        repo = InMemoryWorkflowRepository()
        steps = await repo.get_steps(uuid4())
        assert steps == []

    async def test_get_steps_only_for_given_workflow(self):
        repo = InMemoryWorkflowRepository()
        wf_a = uuid4()
        wf_b = uuid4()

        await repo.save_step(make_step(wf_a, step_name="x"))
        await repo.save_step(make_step(wf_b, step_name="y"))

        steps_a = await repo.get_steps(wf_a)
        assert len(steps_a) == 1
        assert steps_a[0].workflow_instance_id == wf_a

    async def test_get_steps_sorted_by_created_at(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        base = datetime(2025, 1, 1, tzinfo=UTC)

        s2 = make_step(wf_id, step_name="s2", created_at=base + timedelta(seconds=2))
        s1 = make_step(wf_id, step_name="s1", created_at=base + timedelta(seconds=1))
        s3 = make_step(wf_id, step_name="s3", created_at=base + timedelta(seconds=3))

        await repo.save_step(s2)
        await repo.save_step(s1)
        await repo.save_step(s3)

        steps = await repo.get_steps(wf_id)
        assert steps[0].step_name == "s1"
        assert steps[1].step_name == "s2"
        assert steps[2].step_name == "s3"

    async def test_save_step_overwrites_by_id(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        step = make_step(wf_id, step_name="orig")
        await repo.save_step(step)

        updated = step.model_copy(update={"step_name": "updated"})
        await repo.save_step(updated)

        steps = await repo.get_steps(wf_id)
        assert len(steps) == 1
        assert steps[0].step_name == "updated"

    async def test_get_step_by_idempotency_key_found(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        step = make_step(wf_id, idempotency_key="idem-1")
        await repo.save_step(step)

        result = await repo.get_step_by_idempotency_key(wf_id, "idem-1")
        assert result is not None
        assert result.id == step.id

    async def test_get_step_by_idempotency_key_wrong_workflow(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        step = make_step(wf_id, idempotency_key="idem-1")
        await repo.save_step(step)

        result = await repo.get_step_by_idempotency_key(uuid4(), "idem-1")
        assert result is None

    async def test_get_step_by_idempotency_key_wrong_key(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        step = make_step(wf_id, idempotency_key="idem-1")
        await repo.save_step(step)

        result = await repo.get_step_by_idempotency_key(wf_id, "idem-99")
        assert result is None

    async def test_get_step_by_idempotency_key_no_steps(self):
        repo = InMemoryWorkflowRepository()
        result = await repo.get_step_by_idempotency_key(uuid4(), "any")
        assert result is None


# ---------------------------------------------------------------------------
# InMemoryWorkflowRepository — event operations
# ---------------------------------------------------------------------------


class TestInMemoryRepositoryEvents:
    """Tests for event sourcing append / retrieve / sequence."""

    async def test_save_and_get_events(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()

        e1 = make_event(wf_id, sequence_number=1)
        e2 = make_event(wf_id, event_type=EventType.STEP_STARTED, sequence_number=2)
        await repo.save_event(e1)
        await repo.save_event(e2)

        events = await repo.get_events(wf_id)
        assert len(events) == 2

    async def test_get_events_empty(self):
        repo = InMemoryWorkflowRepository()
        events = await repo.get_events(uuid4())
        assert events == []

    async def test_get_events_sorted_by_sequence_number(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()

        await repo.save_event(make_event(wf_id, sequence_number=3))
        await repo.save_event(make_event(wf_id, sequence_number=1))
        await repo.save_event(make_event(wf_id, sequence_number=2))

        events = await repo.get_events(wf_id)
        assert [e.sequence_number for e in events] == [1, 2, 3]

    async def test_get_events_only_for_given_workflow(self):
        repo = InMemoryWorkflowRepository()
        wf_a = uuid4()
        wf_b = uuid4()

        await repo.save_event(make_event(wf_a, sequence_number=1))
        await repo.save_event(make_event(wf_b, sequence_number=1))

        events_a = await repo.get_events(wf_a)
        assert len(events_a) == 1
        assert events_a[0].workflow_instance_id == wf_a

    async def test_get_next_sequence_no_events(self):
        repo = InMemoryWorkflowRepository()
        seq = await repo.get_next_sequence(uuid4())
        assert seq == 1

    async def test_get_next_sequence_with_events(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        await repo.save_event(make_event(wf_id, sequence_number=1))
        await repo.save_event(make_event(wf_id, sequence_number=5))

        seq = await repo.get_next_sequence(wf_id)
        assert seq == 6

    async def test_get_next_sequence_single_event(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        await repo.save_event(make_event(wf_id, sequence_number=3))

        seq = await repo.get_next_sequence(wf_id)
        assert seq == 4

    async def test_multiple_workflows_independent_sequences(self):
        repo = InMemoryWorkflowRepository()
        wf_a = uuid4()
        wf_b = uuid4()

        await repo.save_event(make_event(wf_a, sequence_number=1))
        await repo.save_event(make_event(wf_a, sequence_number=2))
        await repo.save_event(make_event(wf_b, sequence_number=1))

        assert await repo.get_next_sequence(wf_a) == 3
        assert await repo.get_next_sequence(wf_b) == 2


# ---------------------------------------------------------------------------
# InMemoryWorkflowRepository — compensation operations
# ---------------------------------------------------------------------------


class TestInMemoryRepositoryCompensations:
    """Tests for saga compensation save / update / list."""

    async def test_save_and_get_compensations(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        step_id = uuid4()

        comp = make_compensation(wf_id, step_id)
        await repo.save_compensation(comp)

        results = await repo.get_compensations(wf_id)
        assert len(results) == 1
        assert results[0].id == comp.id

    async def test_get_compensations_empty(self):
        repo = InMemoryWorkflowRepository()
        results = await repo.get_compensations(uuid4())
        assert results == []

    async def test_save_compensation_updates_existing(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        step_id = uuid4()

        comp = make_compensation(wf_id, step_id)
        await repo.save_compensation(comp)

        updated = comp.model_copy(update={"status": StepStatus.COMPLETED})
        await repo.save_compensation(updated)

        results = await repo.get_compensations(wf_id)
        assert len(results) == 1
        assert results[0].status == StepStatus.COMPLETED

    async def test_save_compensation_appends_new_compensation(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()

        comp1 = make_compensation(wf_id, uuid4(), compensation_name="rollback-a")
        comp2 = make_compensation(wf_id, uuid4(), compensation_name="rollback-b")
        await repo.save_compensation(comp1)
        await repo.save_compensation(comp2)

        results = await repo.get_compensations(wf_id)
        assert len(results) == 2

    async def test_save_compensation_creates_list_for_new_workflow(self):
        """First compensation for a workflow creates a new internal list."""
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        comp = make_compensation(wf_id, uuid4())

        assert wf_id not in repo._compensations
        await repo.save_compensation(comp)
        assert wf_id in repo._compensations

    async def test_get_compensations_only_for_given_workflow(self):
        repo = InMemoryWorkflowRepository()
        wf_a = uuid4()
        wf_b = uuid4()

        await repo.save_compensation(make_compensation(wf_a, uuid4()))
        await repo.save_compensation(make_compensation(wf_b, uuid4()))

        results_a = await repo.get_compensations(wf_a)
        assert len(results_a) == 1


# ---------------------------------------------------------------------------
# InMemoryWorkflowRepository — checkpoint operations
# ---------------------------------------------------------------------------


class TestInMemoryRepositoryCheckpoints:
    """Tests for checkpoint save / latest retrieval."""

    async def test_save_and_get_latest_checkpoint(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        cp = make_checkpoint(wf_id, step_index=2, state={"key": "value"})
        await repo.save_checkpoint(cp)

        result = await repo.get_latest_checkpoint(wf_id)
        assert result is not None
        assert result.checkpoint_id == cp.checkpoint_id

    async def test_get_latest_checkpoint_empty(self):
        repo = InMemoryWorkflowRepository()
        result = await repo.get_latest_checkpoint(uuid4())
        assert result is None

    async def test_get_latest_checkpoint_returns_newest(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        base = datetime(2025, 1, 1, tzinfo=UTC)

        cp_old = make_checkpoint(wf_id, step_index=1, created_at=base)
        cp_new = make_checkpoint(wf_id, step_index=5, created_at=base + timedelta(hours=2))
        cp_mid = make_checkpoint(wf_id, step_index=3, created_at=base + timedelta(hours=1))

        await repo.save_checkpoint(cp_old)
        await repo.save_checkpoint(cp_new)
        await repo.save_checkpoint(cp_mid)

        result = await repo.get_latest_checkpoint(wf_id)
        assert result is not None
        assert result.step_index == 5

    async def test_save_checkpoint_creates_list_for_new_workflow(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        cp = make_checkpoint(wf_id)

        assert wf_id not in repo._checkpoints
        await repo.save_checkpoint(cp)
        assert wf_id in repo._checkpoints

    async def test_multiple_checkpoints_accumulated(self):
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()

        for i in range(4):
            await repo.save_checkpoint(make_checkpoint(wf_id, step_index=i))

        assert len(repo._checkpoints[wf_id]) == 4

    async def test_get_latest_checkpoint_only_for_given_workflow(self):
        repo = InMemoryWorkflowRepository()
        wf_a = uuid4()
        wf_b = uuid4()

        await repo.save_checkpoint(make_checkpoint(wf_a, step_index=10))
        result = await repo.get_latest_checkpoint(wf_b)
        assert result is None


# ---------------------------------------------------------------------------
# Integration: end-to-end saga scenario
# ---------------------------------------------------------------------------


class TestInMemoryRepositorySagaScenario:
    """Integration-style tests using multiple repository methods together."""

    async def test_full_workflow_lifecycle(self):
        repo = InMemoryWorkflowRepository()

        # 1. Create workflow
        wf = make_workflow(tenant_id="saga-tenant")
        await repo.save_workflow(wf)

        # 2. Add first event
        seq = await repo.get_next_sequence(wf.id)
        assert seq == 1
        await repo.save_event(make_event(wf.id, sequence_number=seq))

        # 3. Add a step
        step = make_step(wf.id, idempotency_key="step-1")
        await repo.save_step(step)

        # 4. Idempotent step check
        found = await repo.get_step_by_idempotency_key(wf.id, "step-1")
        assert found is not None
        assert found.id == step.id

        # 5. Checkpoint
        cp = make_checkpoint(wf.id, step_index=1, state={"counter": 42})
        await repo.save_checkpoint(cp)

        latest = await repo.get_latest_checkpoint(wf.id)
        assert latest is not None
        assert latest.state["counter"] == 42

        # 6. Compensation
        comp = make_compensation(wf.id, step.id)
        await repo.save_compensation(comp)

        comps = await repo.get_compensations(wf.id)
        assert len(comps) == 1

        # 7. Mark workflow completed
        wf_done = wf.model_copy(update={"status": WorkflowStatus.COMPLETED})
        await repo.save_workflow(wf_done)

        final = await repo.get_workflow(wf.id)
        assert final is not None
        assert final.status == WorkflowStatus.COMPLETED

    async def test_tenant_isolation_across_all_methods(self):
        repo = InMemoryWorkflowRepository()

        wf_t1 = make_workflow(tenant_id="t1")
        wf_t2 = make_workflow(tenant_id="t2")
        await repo.save_workflow(wf_t1)
        await repo.save_workflow(wf_t2)

        t1_list = await repo.list_workflows("t1")
        t2_list = await repo.list_workflows("t2")
        all_ids_t1 = {w.id for w in t1_list}
        all_ids_t2 = {w.id for w in t2_list}

        assert all_ids_t1.isdisjoint(all_ids_t2)
        assert wf_t1.id in all_ids_t1
        assert wf_t2.id in all_ids_t2

    async def test_compensation_update_idempotency(self):
        """Saving the same compensation ID twice should update, not duplicate."""
        repo = InMemoryWorkflowRepository()
        wf_id = uuid4()
        step_id = uuid4()

        comp = make_compensation(wf_id, step_id)
        await repo.save_compensation(comp)
        await repo.save_compensation(comp)  # save identical again

        comps = await repo.get_compensations(wf_id)
        assert len(comps) == 1

    async def test_list_with_all_statuses(self):
        repo = InMemoryWorkflowRepository()
        statuses = [
            WorkflowStatus.PENDING,
            WorkflowStatus.RUNNING,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.COMPENSATING,
            WorkflowStatus.COMPENSATED,
        ]
        for s in statuses:
            await repo.save_workflow(make_workflow(tenant_id="t1", status=s))

        for s in statuses:
            results = await repo.list_workflows("t1", status=s)
            assert len(results) == 1

        all_results = await repo.list_workflows("t1")
        assert len(all_results) == len(statuses)
