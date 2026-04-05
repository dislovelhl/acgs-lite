"""
Targeted coverage tests for persistence/executor.py

Constitutional Hash: 608508a9bd224290

Covers previously uncovered lines:
- WorkflowContext properties (tenant_id, input)
- start_workflow: unknown type, already-running dedup
- execute_workflow: hash mismatch, unknown type, span=None branches
- resume_workflow: not found, terminal state, checkpoint_id, checkpoint log
- execute_activity: Redis-cached result, repo-cached result (with/without output),
  custom idempotency_key, cancel-before-execution, cancel-during-execution,
  span=None branches, timeout + retry exhaustion
- _run_compensations: skip non-PENDING, no handler, compensation failure
- create_checkpoint
- get_workflow_status
- cancel_workflow: not found, non-cancellable status
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from enhanced_agent_bus.persistence.executor import (
    DurableWorkflowExecutor,
    WorkflowContext,
)
from enhanced_agent_bus.persistence.models import (
    CONSTITUTIONAL_HASH,
    CheckpointData,
    StepStatus,
    StepType,
    WorkflowCompensation,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from enhanced_agent_bus.persistence.repository import InMemoryWorkflowRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repository():
    return InMemoryWorkflowRepository()


@pytest.fixture
def executor(repository):
    return DurableWorkflowExecutor(repository, max_retries=1, retry_delay=0.0)


@pytest.fixture
def executor_no_retry(repository):
    """Executor with zero retries for faster timeout tests."""
    return DurableWorkflowExecutor(repository, max_retries=0, retry_delay=0.0)


async def _simple_activity(ctx, input_data):
    return {"done": True}


# ---------------------------------------------------------------------------
# WorkflowContext properties
# ---------------------------------------------------------------------------


class TestWorkflowContextProperties:
    async def test_tenant_id_property(self, repository, executor):
        """WorkflowContext.tenant_id returns the tenant from the instance."""
        instance = WorkflowInstance(
            workflow_type="wf",
            workflow_id="wf-1",
            tenant_id="tenant-abc",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        ctx = WorkflowContext(instance, repository, executor)
        assert ctx.tenant_id == "tenant-abc"

    async def test_input_property_with_data(self, repository, executor):
        """WorkflowContext.input returns input data from the instance."""
        instance = WorkflowInstance(
            workflow_type="wf",
            workflow_id="wf-2",
            tenant_id="t1",
            input={"key": "value"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        ctx = WorkflowContext(instance, repository, executor)
        assert ctx.input == {"key": "value"}

    async def test_input_property_none(self, repository, executor):
        """WorkflowContext.input returns None when no input provided."""
        instance = WorkflowInstance(
            workflow_type="wf",
            workflow_id="wf-3",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        ctx = WorkflowContext(instance, repository, executor)
        assert ctx.input is None


# ---------------------------------------------------------------------------
# start_workflow error paths
# ---------------------------------------------------------------------------


class TestStartWorkflow:
    async def test_unknown_workflow_type_raises(self, executor):
        """start_workflow raises ValueError for unregistered workflow type."""
        with pytest.raises(ValueError, match="Unknown workflow type: no-such-type"):
            await executor.start_workflow("no-such-type", "wf-x", "t1")

    async def test_already_running_returns_existing(self, executor, repository):
        """start_workflow returns the existing instance when it is PENDING/RUNNING."""

        @executor.workflow("dup-wf")
        async def dup(ctx):
            return {}

        # Start once to create the instance
        instance = await executor.start_workflow("dup-wf", "wf-dup", "t1")
        assert instance.status == WorkflowStatus.PENDING

        # Starting again with same IDs must return the same instance (dedup)
        instance2 = await executor.start_workflow("dup-wf", "wf-dup", "t1")
        assert instance2.id == instance.id

    async def test_already_running_status_running(self, executor, repository):
        """start_workflow also deduplicates when existing status is RUNNING."""

        @executor.workflow("run-wf")
        async def run(ctx):
            return {}

        instance = await executor.start_workflow("run-wf", "wf-run", "t1")
        instance.status = WorkflowStatus.RUNNING
        await repository.save_workflow(instance)

        instance2 = await executor.start_workflow("run-wf", "wf-run", "t1")
        assert instance2.id == instance.id


# ---------------------------------------------------------------------------
# execute_workflow error paths
# ---------------------------------------------------------------------------


class TestExecuteWorkflow:
    async def test_constitutional_hash_mismatch_raises(self, executor):
        """execute_workflow raises ValueError on hash mismatch."""

        @executor.workflow("hash-wf")
        async def wf(ctx):
            return {}

        instance = WorkflowInstance(
            workflow_type="hash-wf",
            workflow_id="wf-hash",
            tenant_id="t1",
            constitutional_hash="bad-hash",
        )
        with pytest.raises(ValueError, match="Constitutional hash mismatch"):
            await executor.execute_workflow(instance)

    async def test_unknown_workflow_func_raises(self, executor):
        """execute_workflow raises ValueError when workflow_type not in registry."""
        instance = WorkflowInstance(
            workflow_type="ghost-wf",
            workflow_id="wf-ghost",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        with pytest.raises(ValueError, match="Unknown workflow type: ghost-wf"):
            await executor.execute_workflow(instance)

    async def test_execute_workflow_cancelled_error(self, executor):
        """execute_workflow handles asyncio.CancelledError and marks CANCELLED."""

        @executor.workflow("cancel-wf")
        async def wf(ctx):
            raise asyncio.CancelledError("cancelled by test")

        instance = await executor.start_workflow("cancel-wf", "wf-c", "t1")
        result = await executor.execute_workflow(instance)

        assert result.status == WorkflowStatus.CANCELLED
        assert "cancelled by test" in result.error

    async def test_execute_workflow_runtime_error(self, executor):
        """execute_workflow handles RuntimeError and runs compensations."""

        @executor.workflow("error-wf")
        async def wf(ctx):
            raise RuntimeError("runtime problem")

        instance = await executor.start_workflow("error-wf", "wf-e", "t1")
        result = await executor.execute_workflow(instance)

        assert result.status == WorkflowStatus.FAILED
        assert "runtime problem" in result.error


# ---------------------------------------------------------------------------
# resume_workflow error paths
# ---------------------------------------------------------------------------


class TestResumeWorkflow:
    async def test_resume_not_found_raises(self, executor):
        """resume_workflow raises ValueError when workflow does not exist."""
        with pytest.raises(ValueError, match="Workflow not found: wf-missing"):
            await executor.resume_workflow("wf-missing", "t1")

    async def test_resume_completed_workflow_returns_immediately(self, executor, repository):
        """resume_workflow returns instance unchanged when status is COMPLETED."""

        @executor.workflow("done-wf")
        async def wf(ctx):
            return {"ok": True}

        instance = await executor.start_workflow("done-wf", "wf-done", "t1")
        result = await executor.execute_workflow(instance)
        assert result.status == WorkflowStatus.COMPLETED

        # resume should NOT re-execute
        resumed = await executor.resume_workflow("wf-done", "t1")
        assert resumed.status == WorkflowStatus.COMPLETED

    async def test_resume_cancelled_workflow_returns_immediately(self, executor, repository):
        """resume_workflow returns instance unchanged when status is CANCELLED."""

        @executor.workflow("cancel-resume-wf")
        async def wf(ctx):
            raise asyncio.CancelledError("test")

        instance = await executor.start_workflow("cancel-resume-wf", "wf-cr", "t1")
        result = await executor.execute_workflow(instance)
        assert result.status == WorkflowStatus.CANCELLED

        resumed = await executor.resume_workflow("wf-cr", "t1")
        assert resumed.status == WorkflowStatus.CANCELLED

    async def test_resume_with_checkpoint_id(self, executor, repository):
        """resume_workflow accepts a checkpoint_id without error (no-op branch)."""

        @executor.workflow("ckpt-id-wf")
        async def wf(ctx):
            return {"resumed": True}

        instance = await executor.start_workflow("ckpt-id-wf", "wf-cid", "t1")
        # Set to FAILED so it can be resumed
        instance.status = WorkflowStatus.FAILED
        await repository.save_workflow(instance)

        result = await executor.resume_workflow("wf-cid", "t1", checkpoint_id="some-checkpoint-id")
        assert result.status == WorkflowStatus.COMPLETED

    async def test_resume_with_existing_checkpoint_logs(self, executor, repository):
        """resume_workflow logs checkpoint info when a checkpoint exists."""

        @executor.workflow("log-ckpt-wf")
        async def wf(ctx):
            return {"done": True}

        instance = await executor.start_workflow("log-ckpt-wf", "wf-lc", "t1")
        ctx = WorkflowContext(instance, repository, executor)

        # Create a checkpoint so the resume branch hits the logging path
        await executor.create_checkpoint(ctx, step_index=1)

        # Reset status to FAILED so resume will re-execute
        instance.status = WorkflowStatus.FAILED
        await repository.save_workflow(instance)

        result = await executor.resume_workflow("wf-lc", "t1")
        assert result.status == WorkflowStatus.COMPLETED


# ---------------------------------------------------------------------------
# execute_activity: caching paths
# ---------------------------------------------------------------------------


class TestExecuteActivityCaching:
    async def test_redis_cache_hit_returns_early(self, executor, repository):
        """execute_activity returns cached result from Redis without calling activity."""
        instance = WorkflowInstance(
            workflow_type="cache-wf",
            workflow_id="wf-redis",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        ctx = WorkflowContext(instance, repository, executor)

        cached_value = {"from": "redis"}

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=cached_value)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            call_count = 0

            async def activity(ctx, data):
                nonlocal call_count
                call_count += 1
                return {"should": "not be called"}

            result = await executor.execute_activity(ctx, "step-x", activity)

        assert result == cached_value
        assert call_count == 0  # Activity was NOT called

    async def test_repo_cache_hit_with_output(self, executor, repository):
        """execute_activity returns repo-cached result and updates Redis."""
        instance = WorkflowInstance(
            workflow_type="repo-cache-wf",
            workflow_id="wf-repo",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        # Pre-populate a completed step in the repository
        from enhanced_agent_bus.persistence.models import StepStatus

        idempotency_key = ctx.get_idempotency_key("pre-step")
        existing_step = WorkflowStep(
            workflow_instance_id=instance.id,
            step_name="pre-step",
            step_type=StepType.ACTIVITY,
            idempotency_key=idempotency_key,
            status=StepStatus.COMPLETED,
            output={"cached": "value"},
        )
        await repository.save_step(existing_step)

        call_count = 0

        async def activity(ctx, data):
            nonlocal call_count
            call_count += 1
            return {"should": "not be called"}

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)  # No Redis hit
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            result = await executor.execute_activity(ctx, "pre-step", activity)

        assert result == {"cached": "value"}
        assert call_count == 0

    async def test_repo_cache_hit_without_output(self, executor, repository):
        """execute_activity handles repo-cached step with no output (None output)."""
        instance = WorkflowInstance(
            workflow_type="no-output-wf",
            workflow_id="wf-noout",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        from enhanced_agent_bus.persistence.models import StepStatus

        idempotency_key = ctx.get_idempotency_key("null-step")
        existing_step = WorkflowStep(
            workflow_instance_id=instance.id,
            step_name="null-step",
            step_type=StepType.ACTIVITY,
            idempotency_key=idempotency_key,
            status=StepStatus.COMPLETED,
            output=None,  # No output stored
        )
        await repository.save_step(existing_step)

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            result = await executor.execute_activity(ctx, "null-step", _simple_activity)

        # Returns None (the stored output), set_step_result NOT called because output is None
        assert result is None

    async def test_custom_idempotency_key(self, executor, repository):
        """execute_activity uses the caller-supplied idempotency_key."""
        instance = WorkflowInstance(
            workflow_type="custom-key-wf",
            workflow_id="wf-ck",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            result = await executor.execute_activity(
                ctx,
                "custom-step",
                _simple_activity,
                idempotency_key="my-custom-key",
            )

        assert result == {"done": True}


# ---------------------------------------------------------------------------
# execute_activity: cancellation paths
# ---------------------------------------------------------------------------


class TestExecuteActivityCancellation:
    async def test_cancel_before_execution_raises(self, executor_no_retry, repository):
        """execute_activity raises CancelledError when workflow is cancelled before step."""
        instance = WorkflowInstance(
            workflow_type="pre-cancel-wf",
            workflow_id="wf-precancel",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
            status=WorkflowStatus.CANCELLED,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor_no_retry)

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            with pytest.raises(asyncio.CancelledError):
                await executor_no_retry.execute_activity(ctx, "some-step", _simple_activity)

    async def test_cancel_during_execution(self, executor_no_retry, repository):
        """execute_activity raises CancelledError when cancelled mid-execution."""
        instance = WorkflowInstance(
            workflow_type="mid-cancel-wf",
            workflow_id="wf-midcancel",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor_no_retry)

        async def cancel_during(ctx, data):
            # Mark instance as cancelled so post-execution check triggers
            instance.status = WorkflowStatus.CANCELLED
            await repository.save_workflow(instance)
            return {"done": True}

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            with pytest.raises(asyncio.CancelledError):
                await executor_no_retry.execute_activity(ctx, "mid-step", cancel_during)

    async def test_cancelled_error_in_activity_breaks_retry(self, executor, repository):
        """execute_activity stops retrying on asyncio.CancelledError."""
        instance = WorkflowInstance(
            workflow_type="cancel-retry-wf",
            workflow_id="wf-cancelretry",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        call_count = 0

        async def raise_cancelled(ctx, data):
            nonlocal call_count
            call_count += 1
            raise asyncio.CancelledError("hard cancel")

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            with pytest.raises(asyncio.CancelledError):
                await executor.execute_activity(ctx, "cancel-step", raise_cancelled)

        # CancelledError breaks the retry loop immediately - only called once
        assert call_count == 1


# ---------------------------------------------------------------------------
# execute_activity: timeout path
# ---------------------------------------------------------------------------


class TestExecuteActivityTimeout:
    async def test_timeout_exhaust_retries_raises(self, executor_no_retry, repository):
        """execute_activity raises TimeoutError after exhausting retries on timeout."""
        instance = WorkflowInstance(
            workflow_type="timeout-wf",
            workflow_id="wf-tout",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor_no_retry)

        async def slow_activity(ctx, data):
            await asyncio.sleep(10)
            return {"slow": True}

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            with pytest.raises(TimeoutError):
                await executor_no_retry.execute_activity(
                    ctx, "slow-step", slow_activity, timeout=0.01
                )

    async def test_timeout_with_retry_succeeds_on_second_attempt(self, repository):
        """execute_activity retries after timeout and succeeds on second attempt."""
        executor_with_retry = DurableWorkflowExecutor(repository, max_retries=2, retry_delay=0.0)
        instance = WorkflowInstance(
            workflow_type="retry-wf",
            workflow_id="wf-retry",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor_with_retry)

        attempts = []

        async def flaky_activity(ctx, data):
            attempts.append(1)
            if len(attempts) < 2:
                await asyncio.sleep(5)  # Will timeout first time
            return {"ok": True}

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            result = await executor_with_retry.execute_activity(
                ctx, "flaky-step", flaky_activity, timeout=0.05
            )

        assert result == {"ok": True}
        assert len(attempts) == 2


# ---------------------------------------------------------------------------
# execute_activity: non-dict result wrapping
# ---------------------------------------------------------------------------


class TestExecuteActivityResultWrapping:
    async def test_non_dict_result_wrapped_in_result_key(self, executor_no_retry, repository):
        """execute_activity wraps non-dict results in {'result': value}."""
        instance = WorkflowInstance(
            workflow_type="wrap-wf",
            workflow_id="wf-wrap",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor_no_retry)

        async def returns_string(ctx, data):
            return "a string value"

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            result = await executor_no_retry.execute_activity(ctx, "str-step", returns_string)

        assert result == "a string value"

        # Verify the step output was stored as a wrapped dict
        step = await repository.get_step_by_idempotency_key(
            instance.id, ctx.get_idempotency_key("str-step")
        )
        assert step is not None
        assert step.output == {"result": "a string value"}


# ---------------------------------------------------------------------------
# _run_compensations edge cases
# ---------------------------------------------------------------------------


class TestRunCompensations:
    async def test_skip_non_pending_compensation(self, executor, repository):
        """_run_compensations skips compensations not in PENDING status."""
        instance = WorkflowInstance(
            workflow_type="skip-comp-wf",
            workflow_id="wf-sc",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        # Register a compensation that is already COMPENSATED
        already_done = WorkflowCompensation(
            workflow_instance_id=instance.id,
            step_id=uuid4(),
            compensation_name="already-done",
            status=StepStatus.COMPENSATED,
        )
        await repository.save_compensation(already_done)

        call_count = 0

        async def should_not_run(ctx, data):
            nonlocal call_count
            call_count += 1

        ctx._compensation_handlers["already-done"] = should_not_run

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.invalidate_workflow_state = AsyncMock()
            await executor._run_compensations(ctx)

        assert call_count == 0  # Handler was not called

    async def test_compensation_with_no_handler(self, executor, repository):
        """_run_compensations logs warning and continues when handler is missing."""
        instance = WorkflowInstance(
            workflow_type="nohandler-comp-wf",
            workflow_id="wf-nh",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        # Register compensation but do NOT register a handler
        comp = WorkflowCompensation(
            workflow_instance_id=instance.id,
            step_id=uuid4(),
            compensation_name="missing-handler",
            status=StepStatus.PENDING,
        )
        await repository.save_compensation(comp)
        # Deliberately leave ctx._compensation_handlers empty

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.invalidate_workflow_state = AsyncMock()
            # Should not raise; logs a warning instead
            await executor._run_compensations(ctx)

        comps = await repository.get_compensations(instance.id)
        assert comps[0].status == StepStatus.COMPENSATED

    async def test_compensation_handler_failure(self, executor, repository):
        """_run_compensations marks compensation as COMPENSATION_FAILED on handler error."""
        instance = WorkflowInstance(
            workflow_type="fail-comp-wf",
            workflow_id="wf-fc",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        comp = WorkflowCompensation(
            workflow_instance_id=instance.id,
            step_id=uuid4(),
            compensation_name="fail-comp",
            status=StepStatus.PENDING,
        )
        await repository.save_compensation(comp)

        async def failing_handler(ctx, data):
            raise RuntimeError("Compensation failed badly")

        ctx._compensation_handlers["fail-comp"] = failing_handler

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.invalidate_workflow_state = AsyncMock()
            await executor._run_compensations(ctx)

        comps = await repository.get_compensations(instance.id)
        assert comps[0].status == StepStatus.COMPENSATION_FAILED
        assert "Compensation failed badly" in comps[0].error

    async def test_compensation_non_dict_result(self, executor, repository):
        """_run_compensations wraps non-dict handler result in {'result': value}."""
        instance = WorkflowInstance(
            workflow_type="non-dict-comp-wf",
            workflow_id="wf-ndc",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        comp = WorkflowCompensation(
            workflow_instance_id=instance.id,
            step_id=uuid4(),
            compensation_name="non-dict-comp",
            status=StepStatus.PENDING,
        )
        await repository.save_compensation(comp)

        async def string_handler(ctx, data):
            return "string result"

        ctx._compensation_handlers["non-dict-comp"] = string_handler

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.invalidate_workflow_state = AsyncMock()
            await executor._run_compensations(ctx)

        comps = await repository.get_compensations(instance.id)
        assert comps[0].status == StepStatus.COMPENSATED
        assert comps[0].output == {"result": "string result"}


# ---------------------------------------------------------------------------
# create_checkpoint
# ---------------------------------------------------------------------------


class TestCreateCheckpoint:
    async def test_create_checkpoint_persists(self, executor, repository):
        """create_checkpoint saves snapshot and records event."""
        instance = WorkflowInstance(
            workflow_type="ckpt-wf",
            workflow_id="wf-ckpt",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        checkpoint = await executor.create_checkpoint(ctx, step_index=3)

        assert checkpoint is not None
        assert checkpoint.step_index == 3
        assert checkpoint.state["workflow_input"] == instance.input

        # Verify checkpoint stored in repository
        stored = await repository.get_latest_checkpoint(instance.id)
        assert stored is not None
        assert stored.checkpoint_id == checkpoint.checkpoint_id

        # Verify event recorded
        events = await repository.get_events(instance.id)
        event_types = [e.event_type for e in events]
        from enhanced_agent_bus.persistence.models import EventType

        assert EventType.CHECKPOINT_CREATED in event_types


# ---------------------------------------------------------------------------
# get_workflow_status
# ---------------------------------------------------------------------------


class TestGetWorkflowStatus:
    async def test_get_workflow_status_returns_instance(self, executor, repository):
        """get_workflow_status returns the running instance by business ID."""

        @executor.workflow("status-wf")
        async def wf(ctx):
            return {}

        instance = await executor.start_workflow("status-wf", "wf-status", "t1")
        found = await executor.get_workflow_status("wf-status", "t1")

        assert found is not None
        assert found.id == instance.id

    async def test_get_workflow_status_returns_none_when_missing(self, executor):
        """get_workflow_status returns None for non-existent workflow."""
        result = await executor.get_workflow_status("no-such-wf", "t1")
        assert result is None


# ---------------------------------------------------------------------------
# cancel_workflow edge cases
# ---------------------------------------------------------------------------


class TestCancelWorkflow:
    async def test_cancel_not_found_returns_none(self, executor):
        """cancel_workflow returns None when workflow does not exist."""
        result = await executor.cancel_workflow("wf-ghost", "t1")
        assert result is None

    async def test_cancel_completed_workflow_returns_unchanged(self, executor, repository):
        """cancel_workflow returns instance unchanged when already COMPLETED."""

        @executor.workflow("done-cancel-wf")
        async def wf(ctx):
            return {"done": True}

        instance = await executor.start_workflow("done-cancel-wf", "wf-dc", "t1")
        await executor.execute_workflow(instance)

        result = await executor.cancel_workflow("wf-dc", "t1")
        assert result is not None
        assert result.status == WorkflowStatus.COMPLETED  # Unchanged

    async def test_cancel_failed_workflow_returns_unchanged(self, executor, repository):
        """cancel_workflow returns instance unchanged when already FAILED."""

        @executor.workflow("failed-cancel-wf")
        async def wf(ctx):
            raise ValueError("always fails")

        instance = await executor.start_workflow("failed-cancel-wf", "wf-fcw", "t1")
        result = await executor.execute_workflow(instance)
        assert result.status == WorkflowStatus.FAILED

        cancelled_result = await executor.cancel_workflow("wf-fcw", "t1")
        assert cancelled_result is not None
        assert cancelled_result.status == WorkflowStatus.FAILED

    async def test_cancel_pending_workflow_succeeds(self, executor, repository):
        """cancel_workflow sets CANCELLED status on a PENDING workflow."""

        @executor.workflow("pending-cancel-wf")
        async def wf(ctx):
            return {}

        instance = await executor.start_workflow("pending-cancel-wf", "wf-pc", "t1")
        assert instance.status == WorkflowStatus.PENDING

        result = await executor.cancel_workflow("wf-pc", "t1", reason="Manual cancel")
        assert result is not None
        assert result.status == WorkflowStatus.CANCELLED
        assert result.error == "Manual cancel"

    async def test_cancel_workflow_with_default_reason(self, executor, repository):
        """cancel_workflow uses default reason when none provided."""

        @executor.workflow("default-reason-wf")
        async def wf(ctx):
            return {}

        instance = await executor.start_workflow("default-reason-wf", "wf-dr", "t1")
        result = await executor.cancel_workflow("wf-dr", "t1")

        assert result is not None
        assert result.status == WorkflowStatus.CANCELLED
        assert result.error == "User cancelled"


# ---------------------------------------------------------------------------
# register_compensation via WorkflowContext
# ---------------------------------------------------------------------------


class TestRegisterCompensation:
    async def test_register_compensation_stores_handler(self, executor, repository):
        """register_compensation stores the handler and saves to repository."""
        instance = WorkflowInstance(
            workflow_type="reg-comp-wf",
            workflow_id="wf-rc",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        await repository.save_workflow(instance)
        ctx = WorkflowContext(instance, repository, executor)

        step_id = uuid4()

        async def my_handler(ctx, data):
            return {"reverted": True}

        await ctx.register_compensation(step_id, "my-comp", my_handler, {"key": "val"})

        assert len(ctx._compensation_stack) == 1
        assert "my-comp" in ctx._compensation_handlers
        assert ctx._compensation_handlers["my-comp"] is my_handler

        comps = await repository.get_compensations(instance.id)
        assert len(comps) == 1
        assert comps[0].compensation_name == "my-comp"


# ---------------------------------------------------------------------------
# get_idempotency_key with extra args
# ---------------------------------------------------------------------------


class TestGetIdempotencyKey:
    def test_idempotency_key_with_args(self, executor, repository):
        """get_idempotency_key includes extra args in hash computation."""
        instance = WorkflowInstance(
            workflow_type="key-wf",
            workflow_id="wf-key",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        ctx = WorkflowContext(instance, repository, executor)

        key_no_args = ctx.get_idempotency_key("step-name")
        key_with_args = ctx.get_idempotency_key("step-name", "arg1", 42)

        # Keys differ when extra args provided
        assert key_no_args != key_with_args

        # Keys are deterministic
        assert ctx.get_idempotency_key("step-name", "arg1", 42) == key_with_args

    def test_idempotency_key_length(self, executor, repository):
        """get_idempotency_key returns 32-character hex string."""
        instance = WorkflowInstance(
            workflow_type="key-len-wf",
            workflow_id="wf-kl",
            tenant_id="t1",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        ctx = WorkflowContext(instance, repository, executor)
        key = ctx.get_idempotency_key("step")
        assert len(key) == 32


# ---------------------------------------------------------------------------
# Full workflow: with compensation + result wrapping via execute_activity
# ---------------------------------------------------------------------------


class TestFullWorkflowIntegration:
    async def test_workflow_with_compensation_registered_via_activity(self, executor, repository):
        """Full workflow: activity with compensation registers and runs on failure."""
        comp_called = False

        @executor.workflow("full-comp-wf")
        async def wf(ctx):
            async def step1(ctx, data):
                return {"s1": "done"}

            async def comp_step1(ctx, data):
                nonlocal comp_called
                comp_called = True
                return {"reverted": True}

            async def step2_fail(ctx, data):
                raise ValueError("step2 always fails")

            await ctx.executor.execute_activity(ctx, "step1", step1, compensation=comp_step1)
            await ctx.executor.execute_activity(ctx, "step2", step2_fail)
            return {}

        with patch("enhanced_agent_bus.persistence.executor.workflow_cache") as mock_cache:
            mock_cache.get_step_result = AsyncMock(return_value=None)
            mock_cache.set_step_result = AsyncMock()
            mock_cache.invalidate_workflow_state = AsyncMock()

            instance = await executor.start_workflow("full-comp-wf", "wf-full", "t1")
            result = await executor.execute_workflow(instance)

        assert result.status == WorkflowStatus.FAILED
        assert comp_called is True
