"""
Tests for Durable Execution Engine.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import os
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ..durable_execution import (
    CONSTITUTIONAL_HASH,
    CheckpointStore,
    DurableExecutor,
    DurableStep,
    DurableWorkflow,
    ExecutionCheckpoint,
    ExecutionStatus,
    RecoveryStrategy,
    WorkflowState,
    create_durable_executor,
)

RUN_DURABLE_EXECUTION_TESTS = (
    os.getenv("RUN_EAB_DURABLE_EXECUTION_TESTS", "false").lower() == "true"
)
pytestmark = [
    pytest.mark.skipif(
        not RUN_DURABLE_EXECUTION_TESTS,
        reason=(
            "Skipping durable execution tests by default in this runtime. "
            "Set RUN_EAB_DURABLE_EXECUTION_TESTS=true to run."
        ),
    )
]

# =============================================================================
# Constitutional Hash Tests
# =============================================================================


class TestConstitutionalHash:
    """Test constitutional hash compliance."""

    def test_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_hash_in_checkpoint(self):
        state = WorkflowState(workflow_id="test")
        checkpoint = ExecutionCheckpoint(
            id="cp-1",
            workflow_id="test",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )
        assert checkpoint.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# ExecutionStatus Tests
# =============================================================================


class TestExecutionStatus:
    """Test execution status enum."""

    def test_all_statuses_exist(self):
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.PAUSED.value == "paused"
        assert ExecutionStatus.CHECKPOINTED.value == "checkpointed"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.RECOVERING.value == "recovering"


class TestRecoveryStrategy:
    """Test recovery strategy enum."""

    def test_all_strategies_exist(self):
        assert RecoveryStrategy.RETRY_STEP.value == "retry_step"
        assert RecoveryStrategy.SKIP_STEP.value == "skip_step"
        assert RecoveryStrategy.ROLLBACK.value == "rollback"
        assert RecoveryStrategy.RESTART.value == "restart"
        assert RecoveryStrategy.MANUAL.value == "manual"


# =============================================================================
# WorkflowState Tests
# =============================================================================


class TestWorkflowState:
    """Test workflow state."""

    def test_basic_creation(self):
        state = WorkflowState(workflow_id="wf-1")
        assert state.workflow_id == "wf-1"
        assert state.current_step == 0
        assert state.total_steps == 0

    def test_with_results(self):
        state = WorkflowState(
            workflow_id="wf-1",
            current_step=2,
            total_steps=5,
            step_results={0: "result0", 1: "result1"},
        )
        assert state.step_results[0] == "result0"
        assert state.step_results[1] == "result1"

    def test_with_variables(self):
        state = WorkflowState(
            workflow_id="wf-1",
            variables={"key": "value", "count": 42},
        )
        assert state.variables["key"] == "value"
        assert state.variables["count"] == 42

    def test_to_dict(self):
        state = WorkflowState(
            workflow_id="wf-1",
            current_step=1,
            variables={"x": 1},
        )
        d = state.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["current_step"] == 1
        assert d["variables"] == {"x": 1}

    def test_from_dict(self):
        data = {
            "workflow_id": "wf-2",
            "current_step": 3,
            "total_steps": 10,
            "step_results": {},
            "variables": {"y": 2},
            "metadata": {},
            "started_at": None,
            "updated_at": None,
            "error": None,
        }
        state = WorkflowState.from_dict(data)
        assert state.workflow_id == "wf-2"
        assert state.current_step == 3
        assert state.variables["y"] == 2

    def test_roundtrip_serialization(self):
        original = WorkflowState(
            workflow_id="wf-roundtrip",
            current_step=5,
            total_steps=10,
            variables={"test": True},
            started_at=datetime.now(UTC),
        )
        restored = WorkflowState.from_dict(original.to_dict())
        assert restored.workflow_id == original.workflow_id
        assert restored.current_step == original.current_step


# =============================================================================
# ExecutionCheckpoint Tests
# =============================================================================


class TestExecutionCheckpoint:
    """Test execution checkpoint."""

    def test_basic_creation(self):
        state = WorkflowState(workflow_id="wf-1")
        checkpoint = ExecutionCheckpoint(
            id="cp-1",
            workflow_id="wf-1",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )
        assert checkpoint.id == "cp-1"
        assert checkpoint.step_index == 0
        assert checkpoint.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict(self):
        state = WorkflowState(workflow_id="wf-1")
        checkpoint = ExecutionCheckpoint(
            id="cp-1",
            workflow_id="wf-1",
            step_index=2,
            state=state,
            status=ExecutionStatus.COMPLETED,
        )
        d = checkpoint.to_dict()
        assert d["id"] == "cp-1"
        assert d["step_index"] == 2
        assert d["status"] == "completed"

    def test_from_dict(self):
        state = WorkflowState(workflow_id="wf-1")
        original = ExecutionCheckpoint(
            id="cp-2",
            workflow_id="wf-1",
            step_index=3,
            state=state,
            status=ExecutionStatus.FAILED,
        )
        restored = ExecutionCheckpoint.from_dict(original.to_dict())
        assert restored.id == "cp-2"
        assert restored.step_index == 3
        assert restored.status == ExecutionStatus.FAILED


# =============================================================================
# CheckpointStore Tests
# =============================================================================


class TestCheckpointStore:
    """Test checkpoint store."""

    async def test_initialize(self):
        store = CheckpointStore()
        await store.initialize()
        assert store._initialized
        await store.close()

    async def test_save_and_get_checkpoint(self):
        store = CheckpointStore()
        await store.initialize()

        state = WorkflowState(workflow_id="wf-1")
        checkpoint = ExecutionCheckpoint(
            id="cp-1",
            workflow_id="wf-1",
            step_index=0,
            state=state,
            status=ExecutionStatus.CHECKPOINTED,
        )

        await store.save_checkpoint(checkpoint)
        retrieved = await store.get_checkpoint("cp-1")

        assert retrieved is not None
        assert retrieved.id == "cp-1"
        await store.close()

    async def test_get_latest_checkpoint(self):
        store = CheckpointStore()
        await store.initialize()

        state = WorkflowState(workflow_id="wf-1")

        # Create multiple checkpoints
        for i in range(3):
            checkpoint = ExecutionCheckpoint(
                id=f"cp-{i}",
                workflow_id="wf-1",
                step_index=i,
                state=state,
                status=ExecutionStatus.CHECKPOINTED,
            )
            await store.save_checkpoint(checkpoint)

        latest = await store.get_latest_checkpoint("wf-1")
        assert latest is not None
        assert latest.step_index == 2
        await store.close()

    async def test_get_all_checkpoints(self):
        store = CheckpointStore()
        await store.initialize()

        state = WorkflowState(workflow_id="wf-2")
        for i in range(5):
            checkpoint = ExecutionCheckpoint(
                id=f"cp-{i}",
                workflow_id="wf-2",
                step_index=i,
                state=state,
                status=ExecutionStatus.CHECKPOINTED,
            )
            await store.save_checkpoint(checkpoint)

        checkpoints = await store.get_checkpoints("wf-2")
        assert len(checkpoints) == 5
        await store.close()

    async def test_delete_checkpoints(self):
        store = CheckpointStore()
        await store.initialize()

        state = WorkflowState(workflow_id="wf-3")
        for i in range(3):
            checkpoint = ExecutionCheckpoint(
                id=f"cp-del-{i}",
                workflow_id="wf-3",
                step_index=i,
                state=state,
                status=ExecutionStatus.CHECKPOINTED,
            )
            await store.save_checkpoint(checkpoint)

        deleted = await store.delete_checkpoints("wf-3")
        assert deleted == 3

        checkpoints = await store.get_checkpoints("wf-3")
        assert len(checkpoints) == 0
        await store.close()

    async def test_checkpoint_not_found(self):
        store = CheckpointStore()
        await store.initialize()

        result = await store.get_checkpoint("nonexistent")
        assert result is None
        await store.close()


# =============================================================================
# DurableStep Tests
# =============================================================================


class TestDurableStep:
    """Test durable step."""

    def test_basic_step(self):
        async def my_func(state):
            return "result"

        step = DurableStep(
            id="step-1",
            name="My Step",
            func=my_func,
        )
        assert step.name == "My Step"
        assert step.max_retries == 3

    def test_step_with_config(self):
        async def my_func(state):
            return "result"

        step = DurableStep(
            id="step-2",
            name="Configured Step",
            func=my_func,
            max_retries=5,
            retry_delay=2.0,
            timeout=30.0,
            skip_on_failure=True,
        )
        assert step.max_retries == 5
        assert step.retry_delay == 2.0
        assert step.timeout == 30.0
        assert step.skip_on_failure


# =============================================================================
# DurableWorkflow Tests
# =============================================================================


class TestDurableWorkflow:
    """Test durable workflow."""

    def test_basic_workflow(self):
        workflow = DurableWorkflow("wf-1", "Test Workflow")
        assert workflow.id == "wf-1"
        assert workflow.name == "Test Workflow"
        assert len(workflow) == 0

    def test_add_steps(self):
        workflow = DurableWorkflow("wf-2", "Multi-Step")

        async def step1(state):
            return 1

        async def step2(state):
            return 2

        workflow.add_step("Step 1", step1)
        workflow.add_step("Step 2", step2)

        assert len(workflow) == 2
        assert workflow.steps[0].name == "Step 1"
        assert workflow.steps[1].name == "Step 2"

    def test_step_decorator(self):
        workflow = DurableWorkflow("wf-3", "Decorated")

        @workflow.step("Decorated Step")
        async def my_step(state):
            return "decorated"

        assert len(workflow) == 1
        assert workflow.steps[0].name == "Decorated Step"

    def test_method_chaining(self):
        workflow = DurableWorkflow("wf-4", "Chained")

        async def step_func(state):
            return True

        result = (
            workflow.add_step("Step A", step_func)
            .add_step("Step B", step_func)
            .add_step("Step C", step_func)
        )

        assert result is workflow
        assert len(workflow) == 3

    def test_workflow_with_recovery_strategy(self):
        workflow = DurableWorkflow(
            "wf-5",
            "Recovery Test",
            recovery_strategy=RecoveryStrategy.SKIP_STEP,
        )
        assert workflow.recovery_strategy == RecoveryStrategy.SKIP_STEP


# =============================================================================
# DurableExecutor Tests
# =============================================================================


class TestDurableExecutor:
    """Test durable executor."""

    async def test_basic_initialization(self):
        executor = DurableExecutor()
        await executor.initialize()
        assert executor._initialized
        await executor.close()

    async def test_execute_simple_workflow(self):
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("simple-wf", "Simple")

        async def step1(state):
            state.variables["count"] = 1
            return "step1_done"

        async def step2(state):
            state.variables["count"] += 1
            return "step2_done"

        workflow.add_step("Step 1", step1)
        workflow.add_step("Step 2", step2)

        success, state = await executor.execute(workflow)

        assert success
        assert state.variables["count"] == 2
        assert state.step_results[0] == "step1_done"
        assert state.step_results[1] == "step2_done"

        await executor.close()

    async def test_execute_with_initial_context(self):
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("context-wf", "Context")

        async def step1(state):
            return state.variables["input"] * 2

        workflow.add_step("Double", step1)

        success, state = await executor.execute(workflow, initial_context={"input": 21})

        assert success
        assert state.step_results[0] == 42

        await executor.close()

    async def test_execute_with_failure(self):
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("fail-wf", "Failure")

        async def failing_step(state):
            raise ValueError("Intentional failure")

        workflow.add_step("Fail", failing_step, max_retries=0)

        success, state = await executor.execute(workflow)

        assert not success
        assert state.error is not None
        assert "Intentional failure" in state.error

        await executor.close()

    async def test_step_retry(self):
        executor = DurableExecutor()
        await executor.initialize()

        call_count = 0

        async def flaky_step(state):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Flaky failure")
            return "success"

        workflow = DurableWorkflow("retry-wf", "Retry")
        workflow.add_step("Flaky", flaky_step, max_retries=5, retry_delay=0.01)

        success, _state = await executor.execute(workflow)

        assert success
        assert call_count == 3  # Failed twice, succeeded on third

        await executor.close()

    async def test_skip_on_failure(self):
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("skip-wf", "Skip")

        async def failing_step(state):
            raise ValueError("Skip me")

        async def next_step(state):
            return "continued"

        workflow.add_step("Fail", failing_step, max_retries=0, skip_on_failure=True)
        workflow.add_step("Continue", next_step)

        success, state = await executor.execute(workflow)

        assert success
        assert state.step_results[0]["skipped"]
        assert state.step_results[1] == "continued"

        await executor.close()

    async def test_checkpointing(self):
        store = CheckpointStore()
        executor = DurableExecutor(
            checkpoint_store=store,
            checkpoint_interval=1,
        )
        await executor.initialize()

        workflow = DurableWorkflow("checkpoint-wf", "Checkpoint")

        async def step(state):
            return "done"

        workflow.add_step("Step 1", step)
        workflow.add_step("Step 2", step)
        workflow.add_step("Step 3", step)

        await executor.execute(workflow)

        # Check that checkpoints were created
        checkpoints = await store.get_checkpoints("checkpoint-wf")
        assert len(checkpoints) > 0

        await executor.close()

    async def test_resume_from_checkpoint(self):
        store = CheckpointStore()
        executor = DurableExecutor(checkpoint_store=store)
        await executor.initialize()

        step_calls = []

        async def step1(state):
            step_calls.append("step1")
            return "s1"

        async def step2(state):
            step_calls.append("step2")
            return "s2"

        async def step3(state):
            step_calls.append("step3")
            return "s3"

        # First execution
        workflow1 = DurableWorkflow("resume-wf", "Resume")
        workflow1.add_step("S1", step1)
        workflow1.add_step("S2", step2)
        workflow1.add_step("S3", step3)

        await executor.execute(workflow1)

        # Get checkpoint after step 1
        checkpoints = await store.get_checkpoints("resume-wf")
        assert len(checkpoints) > 0

        # Create new workflow with same ID for resume
        step_calls.clear()
        workflow2 = DurableWorkflow("resume-wf", "Resume")
        workflow2.add_step("S1", step1)
        workflow2.add_step("S2", step2)
        workflow2.add_step("S3", step3)

        # Resume from first checkpoint
        first_checkpoint = checkpoints[0]
        success, _state = await executor.execute(workflow2, resume_from=first_checkpoint.id)

        assert success
        # Should have skipped step 0 (already completed)
        assert "step1" not in step_calls

        await executor.close()

    async def test_get_stats(self):
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("stats-wf", "Stats")

        async def step(state):
            return "done"

        workflow.add_step("Step", step)
        await executor.execute(workflow)

        stats = executor.get_stats()

        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["metrics"]["workflows_started"] >= 1
        assert stats["metrics"]["workflows_completed"] >= 1

        await executor.close()

    async def test_workflow_status(self):
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("status-wf", "Status")

        async def step(state):
            return "done"

        workflow.add_step("Step", step)
        await executor.execute(workflow)

        status = await executor.get_workflow_status("status-wf")

        assert status is not None
        assert status["workflow_id"] == "status-wf"
        assert status["status"] == "completed"

        await executor.close()

    async def test_cancel_workflow(self):
        executor = DurableExecutor()
        await executor.initialize()

        # Manually add to active workflows
        state = WorkflowState(workflow_id="cancel-wf")
        executor._active_workflows["cancel-wf"] = state

        result = await executor.cancel("cancel-wf")
        assert result

        # Should no longer be active
        assert "cancel-wf" not in executor._active_workflows

        await executor.close()

    async def test_sync_step_function(self):
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("sync-wf", "Sync")

        def sync_step(state):  # Synchronous function
            return "sync_result"

        workflow.add_step("Sync Step", sync_step)

        success, state = await executor.execute(workflow)

        assert success
        assert state.step_results[0] == "sync_result"

        await executor.close()


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateDurableExecutor:
    """Test factory function."""

    def test_create_with_defaults(self):
        executor = create_durable_executor()
        assert executor is not None
        assert executor._constitutional_hash == CONSTITUTIONAL_HASH
        assert executor._auto_checkpoint

    def test_create_with_db_path(self):
        executor = create_durable_executor(db_path=":memory:")
        assert executor._store._db_path == ":memory:"

    def test_create_with_custom_hash(self):
        executor = create_durable_executor(constitutional_hash="custom123")
        assert executor._constitutional_hash == "custom123"

    def test_create_with_disabled_checkpoint(self):
        executor = create_durable_executor(auto_checkpoint=False)
        assert not executor._auto_checkpoint

    def test_create_with_interval(self):
        executor = create_durable_executor(checkpoint_interval=5)
        assert executor._checkpoint_interval == 5


# =============================================================================
# Integration Tests
# =============================================================================


class TestDurableExecutionIntegration:
    """Integration tests for durable execution."""

    async def test_multi_step_data_flow(self):
        """Test data flows correctly between steps."""
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("dataflow-wf", "Data Flow")

        async def init(state):
            state.variables["numbers"] = []
            return "init"

        async def add_one(state):
            state.variables["numbers"].append(1)
            return "added_1"

        async def add_two(state):
            state.variables["numbers"].append(2)
            return "added_2"

        async def sum_all(state):
            total = sum(state.variables["numbers"])
            state.variables["total"] = total
            return total

        workflow.add_step("Init", init)
        workflow.add_step("Add One", add_one)
        workflow.add_step("Add Two", add_two)
        workflow.add_step("Sum", sum_all)

        success, state = await executor.execute(workflow)

        assert success
        assert state.variables["numbers"] == [1, 2]
        assert state.variables["total"] == 3
        assert state.step_results[3] == 3

        await executor.close()

    async def test_workflow_with_timeout(self):
        """Test step timeout handling."""
        executor = DurableExecutor()
        await executor.initialize()

        workflow = DurableWorkflow("timeout-wf", "Timeout")

        async def slow_step(state):
            await asyncio.sleep(10)  # Very slow
            return "done"

        workflow.add_step("Slow", slow_step, timeout=0.1, max_retries=0)

        success, state = await executor.execute(workflow)

        assert not success
        assert "TimeoutError" in state.error or "timed out" in state.error.lower()

        await executor.close()

    async def test_metrics_accuracy(self):
        """Test metrics are accurately tracked."""
        executor = DurableExecutor()
        await executor.initialize()

        # Execute successful workflow
        workflow1 = DurableWorkflow("metrics-1", "Metrics 1")

        async def step(state):
            return "ok"

        workflow1.add_step("S1", step)
        workflow1.add_step("S2", step)
        await executor.execute(workflow1)

        # Execute failing workflow
        workflow2 = DurableWorkflow("metrics-2", "Metrics 2")

        async def fail(state):
            raise ValueError("fail")

        workflow2.add_step("Fail", fail, max_retries=0)
        await executor.execute(workflow2)

        stats = executor.get_stats()

        assert stats["metrics"]["workflows_started"] == 2
        assert stats["metrics"]["workflows_completed"] == 1
        assert stats["metrics"]["workflows_failed"] == 1
        assert stats["metrics"]["steps_executed"] == 2

        await executor.close()

    async def test_constitutional_hash_in_checkpoints(self):
        """Verify constitutional hash is stored in all checkpoints."""
        store = CheckpointStore()
        executor = DurableExecutor(checkpoint_store=store)
        await executor.initialize()

        workflow = DurableWorkflow("hash-wf", "Hash Test")

        async def step(state):
            return "done"

        workflow.add_step("Step", step)
        await executor.execute(workflow)

        checkpoints = await store.get_checkpoints("hash-wf")

        for checkpoint in checkpoints:
            assert checkpoint.constitutional_hash == CONSTITUTIONAL_HASH

        await executor.close()
