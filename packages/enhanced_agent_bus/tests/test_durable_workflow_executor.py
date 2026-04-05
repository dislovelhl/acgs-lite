"""
Tests for Durable Workflow Executor
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from enhanced_agent_bus.persistence.executor import (
    DurableWorkflowExecutor,
    WorkflowContext,
)
from enhanced_agent_bus.persistence.models import (
    StepStatus,
    WorkflowInstance,
    WorkflowStatus,
)
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository


@pytest.fixture
def repository():
    return InMemoryWorkflowRepository()


@pytest.fixture
def executor(repository):
    return DurableWorkflowExecutor(repository, max_retries=1, retry_delay=0.1)


async def test_workflow_execution(executor, repository):
    @executor.workflow("test-workflow")
    async def my_workflow(ctx: WorkflowContext):
        async def step1(ctx, input_data):
            return {"status": "step1_done"}

        async def step2(ctx, input_data):
            return {"status": "step2_done"}

        res1 = await ctx.executor.execute_activity(ctx, "step1", step1, {"input": "test"})
        res2 = await ctx.executor.execute_activity(ctx, "step2", step2, res1)

        await ctx.executor.create_checkpoint(ctx, 2)
        return res2

    instance = await executor.start_workflow(
        workflow_type="test-workflow", workflow_id="wf-123", tenant_id="tenant-1"
    )

    assert instance.status == WorkflowStatus.PENDING

    result_instance = await executor.execute_workflow(instance)

    assert result_instance.status == WorkflowStatus.COMPLETED
    assert result_instance.output == {"status": "step2_done"}

    # Check if steps were recorded
    events = await repository.get_events(instance.id)
    assert len(events) > 0


async def test_workflow_timeout(executor, repository):
    @executor.workflow("timeout-workflow")
    async def my_workflow(ctx: WorkflowContext):
        async def slow_step(ctx, input_data):
            await asyncio.sleep(0.5)
            return {"status": "done"}

        # Setting timeout smaller than sleep
        return await ctx.executor.execute_activity(
            ctx, "slow_step", slow_step, {"input": "test"}, timeout=0.1
        )

    instance = await executor.start_workflow(
        workflow_type="timeout-workflow", workflow_id="wf-timeout", tenant_id="tenant-1"
    )

    result_instance = await executor.execute_workflow(instance)

    assert result_instance.status == WorkflowStatus.FAILED
    assert "timed out after 0.1 seconds" in result_instance.error


async def test_workflow_compensation(executor, repository):
    compensation_called = False

    @executor.workflow("compensation-workflow")
    async def my_workflow(ctx: WorkflowContext):
        async def step1(ctx, input_data):
            return {"status": "step1_done"}

        async def compensate_step1(ctx, input_data):
            nonlocal compensation_called
            compensation_called = True
            return {"compensated": True}

        async def failing_step(ctx, input_data):
            raise ValueError("Intentional failure")

        await ctx.executor.execute_activity(
            ctx, "step1", step1, {"input": "test"}, compensation=compensate_step1
        )

        await ctx.executor.execute_activity(ctx, "fail", failing_step, {"input": "fail"})

        return {"status": "success"}

    instance = await executor.start_workflow(
        workflow_type="compensation-workflow", workflow_id="wf-comp", tenant_id="tenant-1"
    )

    result_instance = await executor.execute_workflow(instance)

    assert result_instance.status == WorkflowStatus.FAILED
    assert "Intentional failure" in result_instance.error
    assert compensation_called is True

    compensations = await repository.get_compensations(instance.id)
    assert len(compensations) == 1
    assert compensations[0].status == StepStatus.COMPENSATED


async def test_workflow_cancellation(executor, repository):
    @executor.workflow("cancellation-workflow")
    async def my_workflow(ctx: WorkflowContext):
        async def normal_step(ctx, input_data):
            # simulate work
            await asyncio.sleep(0.2)
            return {"status": "step_done"}

        # The execution will be cancelled
        res = await ctx.executor.execute_activity(ctx, "step1", normal_step, {})
        return res

    instance = await executor.start_workflow(
        workflow_type="cancellation-workflow", workflow_id="wf-cancel", tenant_id="tenant-1"
    )

    # We need to simulate cancelling the workflow mid-execution
    # In a real scenario, another request would call `cancel_workflow`

    async def run_and_cancel():
        # Start executing
        exec_task = asyncio.create_task(executor.execute_workflow(instance))

        # Wait a bit then cancel
        await asyncio.sleep(0.1)
        await executor.cancel_workflow("wf-cancel", "tenant-1")

        return await exec_task

    result_instance = await run_and_cancel()

    assert result_instance.status == WorkflowStatus.CANCELLED


async def test_idempotent_execution(executor, repository):
    execution_count = 0

    @executor.workflow("idempotent-workflow")
    async def my_workflow(ctx: WorkflowContext):
        async def step1(ctx, input_data):
            nonlocal execution_count
            execution_count += 1
            return {"status": "step1_done"}

        return await ctx.executor.execute_activity(ctx, "step1", step1, {"input": "test"})

    instance = await executor.start_workflow(
        workflow_type="idempotent-workflow", workflow_id="wf-idempotent", tenant_id="tenant-1"
    )

    # First execution
    res1 = await executor.execute_workflow(instance)
    assert res1.output == {"status": "step1_done"}
    assert execution_count == 1

    # Second execution (resume) - should use cached output and NOT increment execution_count
    # Manually reset status to PENDING to simulate resumption
    instance.status = WorkflowStatus.PENDING
    res2 = await executor.resume_workflow("wf-idempotent", "tenant-1")

    assert res2.output == {"status": "step1_done"}
    assert execution_count == 1  # Still 1 because of idempotency key cached result
