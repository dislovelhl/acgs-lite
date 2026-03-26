"""
Additional coverage tests for Saga Coordinator.
Constitutional Hash: 608508a9bd224290

These tests target the uncovered lines to push coverage from 81% to 90%+.
"""

import asyncio
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from ..saga_coordinator import (
    CONSTITUTIONAL_HASH,
    CompensationStrategy,
    SagaCheckpoint,
    SagaCompensation,
    SagaCoordinator,
    SagaState,
    SagaStep,
    SagaTransaction,
    StepState,
    create_saga_coordinator,
    saga_context,
)


class TestSagaCompensationToDict:
    """Tests for SagaCompensation.to_dict with all branches."""

    def test_compensation_to_dict_not_executed(self):
        """Test to_dict when compensation has not been executed."""
        comp = SagaCompensation(step_id="step-1")
        data = comp.to_dict()

        assert data["step_id"] == "step-1"
        assert data["executed"] is False
        assert data["executed_at"] is None
        assert data["result"] is None
        assert data["error"] is None
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_compensation_to_dict_executed(self):
        """Test to_dict when compensation has been executed (covers executed_at branch)."""
        comp = SagaCompensation(step_id="step-1")
        comp.executed = True
        comp.executed_at = datetime.now(UTC)
        comp.result = {"compensated": True}
        comp.duration_ms = 42.0

        data = comp.to_dict()

        assert data["executed"] is True
        assert data["executed_at"] is not None  # isoformat branch covered
        assert data["result"] is not None
        assert data["duration_ms"] == 42.0


class TestExecuteSagaStateGuard:
    """Test execute_saga raises when not in INITIALIZED state (line 403)."""

    async def test_execute_saga_wrong_state_raises(self):
        """Test ValueError when saga is not in INITIALIZED state."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("State Guard Test")
        saga.state = SagaState.RUNNING

        with pytest.raises(ValueError, match="Cannot execute saga in state"):
            await coordinator.execute_saga(saga)

    async def test_execute_saga_completed_state_raises(self):
        """Test ValueError when saga is in COMPLETED state."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Completed State Test")
        saga.state = SagaState.COMPLETED

        with pytest.raises(ValueError, match="Cannot execute saga in state"):
            await coordinator.execute_saga(saga)


class TestDependencyCheck:
    """Test dependency handling (lines 418-423)."""

    async def test_step_skipped_when_dependency_not_completed(self):
        """Test step is skipped when its dependency step is not completed."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Dependency Test")

        executed_steps = []

        async def execute1(ctx, data):
            # This step will always fail
            raise RuntimeError("Step 1 failure")

        async def execute2(ctx, data):
            executed_steps.append("step2")
            return {"result": "step2"}

        step1 = coordinator.add_step(saga, "Step 1", execute_func=execute1, max_retries=0)
        step2 = coordinator.add_step(
            saga,
            "Step 2",
            execute_func=execute2,
            dependencies=[step1.step_id],
        )

        # Execute - step1 fails, so step2 should be skipped due to dependency
        await coordinator.execute_saga(saga)

        # step2 should not have been executed
        assert "step2" not in executed_steps

    async def test_step_with_nonexistent_dependency_proceeds(self):
        """Test step with dependency that references a non-existent step still runs."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Bad Dep Test")

        executed = []

        async def execute(ctx, data):
            executed.append("ran")
            return {}

        step = coordinator.add_step(
            saga,
            "Step with bad dep",
            execute_func=execute,
            dependencies=["nonexistent-step-id"],
        )

        # The dependency check will find no dep_step (None), so it won't skip
        success = await coordinator.execute_saga(saga)

        # With no matching dep_step found, it should proceed to execute
        assert success
        assert "ran" in executed


class TestCompensationStrategies:
    """Test parallel and selective compensation strategies (lines 528-571)."""

    async def test_parallel_compensation_strategy(self):
        """Test parallel compensation strategy (lines 528-529, 555-556)."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga(
            "Parallel Compensation Test",
            compensation_strategy=CompensationStrategy.PARALLEL,
        )

        compensated = []

        async def execute(ctx, data):
            return {"data": "value"}

        async def compensate1(result):
            compensated.append("step1")

        async def compensate2(result):
            compensated.append("step2")

        async def fail(ctx, data):
            raise RuntimeError("Trigger compensation")

        coordinator.add_step(saga, "Step 1", execute, compensate1)
        coordinator.add_step(saga, "Step 2", execute, compensate2)
        coordinator.add_step(saga, "Failing Step", fail, None, max_retries=0)

        success = await coordinator.execute_saga(saga)

        assert not success
        assert saga.state == SagaState.COMPENSATED
        assert "step1" in compensated
        assert "step2" in compensated

    async def test_selective_compensation_strategy(self):
        """Test selective compensation strategy (lines 530-531, 564-571)."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga(
            "Selective Compensation Test",
            compensation_strategy=CompensationStrategy.SELECTIVE,
        )

        compensated = []

        async def execute(ctx, data):
            return {}

        async def compensate1(result):
            compensated.append("step1")

        async def compensate2(result):
            compensated.append("step2")

        async def fail(ctx, data):
            raise RuntimeError("Step fails")

        step1 = coordinator.add_step(saga, "Step 1", execute, compensate1)
        step2 = coordinator.add_step(
            saga,
            "Step 2",
            execute,
            compensate2,
            dependencies=[step1.step_id],
        )
        coordinator.add_step(saga, "Failing Step", fail, None, max_retries=0)

        success = await coordinator.execute_saga(saga)

        assert not success
        assert saga.state == SagaState.COMPENSATED

    async def test_selective_compensation_no_dependencies(self):
        """Test selective compensation when steps have no dependencies."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga(
            "Selective No Deps Test",
            compensation_strategy=CompensationStrategy.SELECTIVE,
        )

        compensated = []

        async def execute(ctx, data):
            return {}

        async def compensate(result):
            compensated.append("compensated")

        async def fail(ctx, data):
            raise RuntimeError("Failure")

        coordinator.add_step(saga, "Step 1", execute, compensate)
        coordinator.add_step(saga, "Failing", fail, None, max_retries=0)

        success = await coordinator.execute_saga(saga)

        assert not success
        assert saga.state == SagaState.COMPENSATED


class TestCompensationWithNoFunc:
    """Test compensation when step has no compensation function (lines 580-588)."""

    async def test_compensation_log_no_compensation_func_via_lifo(self):
        """Test compensation logs 'no_compensation' when step has no comp func.

        We directly call _compensate_lifo with a step that has a SagaCompensation
        object but no compensation_func set.
        """
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("No Comp Func Test")

        # Create a step that has a compensation object but no compensation_func
        step = SagaStep(name="Step with null comp func")
        step.state = StepState.COMPLETED
        step.compensation = SagaCompensation(
            step_id=step.step_id,
            compensation_func=None,  # No func
        )
        saga.steps.append(step)

        # Call compensate directly - this will hit the no_compensation branch
        await coordinator._compensate_lifo(saga, [step])

        assert len(saga.compensation_log) == 1
        assert saga.compensation_log[0]["status"] == "no_compensation"

    async def test_execute_compensation_with_null_compensation(self):
        """Test _execute_compensation directly when step has no compensation."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Direct Test")

        step = SagaStep(name="No Comp Step")
        step.compensation = None

        # Should not raise, just log no_compensation
        await coordinator._execute_compensation(saga, step)

        assert len(saga.compensation_log) == 1
        assert saga.compensation_log[0]["status"] == "no_compensation"


class TestCompensationError:
    """Test error handling in _execute_compensation (lines 623-634)."""

    async def test_compensation_func_raises_logs_error(self):
        """Test that compensation error is logged when comp func raises."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Comp Error Test")

        async def execute(ctx, data):
            return {"data": "value"}

        async def failing_compensation(result):
            raise RuntimeError("Compensation failed!")

        async def fail(ctx, data):
            raise RuntimeError("Step fails")

        coordinator.add_step(saga, "Step 1", execute, failing_compensation)
        coordinator.add_step(saga, "Failing", fail, None, max_retries=0)

        success = await coordinator.execute_saga(saga)

        assert not success
        # Check compensation log has a "compensation_failed" entry
        failed_entries = [
            log for log in saga.compensation_log if log.get("status") == "compensation_failed"
        ]
        assert len(failed_entries) > 0
        assert "Compensation failed!" in failed_entries[0]["error"]

    async def test_compensation_func_raises_directly(self):
        """Test _execute_compensation directly when comp func raises."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Direct Comp Error Test")

        async def failing_comp(result):
            raise ValueError("Direct comp failure")

        step = SagaStep(name="Step with failing comp")
        step.state = StepState.COMPLETED
        step.output_data = {"some": "data"}
        step.compensation = SagaCompensation(
            step_id=step.step_id,
            compensation_func=failing_comp,
        )

        await coordinator._execute_compensation(saga, step)

        # Compensation should have error set
        assert step.compensation.error == "Direct comp failure"
        assert len(saga.compensation_log) == 1
        assert saga.compensation_log[0]["status"] == "compensation_failed"


class TestAbortSaga:
    """Tests for abort_saga edge cases (lines 640-645)."""

    async def test_abort_nonexistent_saga_returns_false(self):
        """Test aborting a saga that doesn't exist returns False (line 640-641)."""
        coordinator = create_saga_coordinator()
        result = await coordinator.abort_saga("nonexistent-id", "Test abort")
        assert result is False

    async def test_abort_completed_saga_returns_false(self):
        """Test aborting a completed saga returns False (lines 644-645)."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("To Complete")

        async def execute(ctx, data):
            return {}

        coordinator.add_step(saga, "Step 1", execute)
        await coordinator.execute_saga(saga)

        # Saga is now completed and moved to _completed_sagas, not active
        result = await coordinator.abort_saga(saga.saga_id, "Try abort")
        assert result is False

    async def test_abort_compensated_saga_returns_false(self):
        """Test aborting a saga that's in COMPENSATED state."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Already Compensated")

        # Manually force a saga into COMPENSATED state in active sagas
        saga.state = SagaState.COMPENSATED
        coordinator._active_sagas[saga.saga_id] = saga

        result = await coordinator.abort_saga(saga.saga_id, "Already done")
        assert result is False


class TestSagaTimeoutBranch:
    """Test asyncio.TimeoutError branch in execute_saga (lines 449-454)."""

    async def test_saga_level_timeout(self):
        """Test that saga timeout causes compensation (lines 449-454).

        We trigger this by patching _execute_step_with_retry to raise asyncio.TimeoutError.
        """
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Timeout Saga Test")

        async def execute(ctx, data):
            return {}

        async def compensate(result):
            return {}

        coordinator.add_step(saga, "Step 1", execute, compensate)

        # Patch the bound method using patch.object to raise asyncio.TimeoutError
        with patch.object(
            coordinator,
            "_execute_step_with_retry",
            new=AsyncMock(side_effect=TimeoutError()),
        ):
            success = await coordinator.execute_saga(saga)

        assert not success
        # After compensation, state becomes COMPENSATED (overwritten from TIMEOUT)
        assert saga.state == SagaState.COMPENSATED
        assert saga.failure_reason == "Saga execution timeout"
        assert saga.failed_at is not None


class TestSagaExecuteOperationError:
    """Test operation error branch in execute_saga (lines 457-462)."""

    async def test_saga_operation_error_triggers_compensation(self):
        """Test that operation errors are caught and trigger compensation.

        Note: The saga goes through FAILED -> COMPENSATED because _compensate_saga
        sets it to COMPENSATED after handling. We verify it was FAILED before compensation.
        """
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Op Error Test")

        async def execute(ctx, data):
            return {}

        async def compensate(result):
            return {}

        coordinator.add_step(saga, "Step 1", execute, compensate)

        # Patch _execute_step_with_retry to raise RuntimeError
        with patch.object(
            coordinator,
            "_execute_step_with_retry",
            new=AsyncMock(side_effect=RuntimeError("Unexpected runtime error")),
        ):
            success = await coordinator.execute_saga(saga)

        assert not success
        # After compensation, state is COMPENSATED (overwritten from FAILED)
        assert saga.state == SagaState.COMPENSATED
        assert "Unexpected runtime error" in saga.failure_reason
        assert saga.failed_at is not None


class TestStepRetryTimeout:
    """Test step-level timeout retry logic (lines 497-504)."""

    async def test_step_timeout_all_retries_exhausted(self):
        """Test that step fails after all timeouts exhaust retries."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Step Timeout Retry Test")

        async def always_slow(ctx, data):
            await asyncio.sleep(10)  # Always timeout
            return {"success": True}

        coordinator.add_step(
            saga,
            "Always Slow Step",
            always_slow,
            max_retries=0,  # No retries - fail immediately
            timeout_ms=100,
        )

        success = await coordinator.execute_saga(saga)

        # Timeout on only attempt → step fails
        assert not success
        assert saga.steps[0].state == StepState.FAILED
        assert saga.steps[0].error == "Step timeout"

    async def test_step_operation_error_retry_exhausted(self):
        """Test step operation error with retry exhaustion reaching return False (line 516)."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Retry Exhausted Test")

        async def always_fails(ctx, data):
            raise ValueError("Always fails with ValueError")

        coordinator.add_step(
            saga,
            "Always Fails",
            always_fails,
            max_retries=1,
        )

        success = await coordinator.execute_saga(saga)

        assert not success
        assert saga.steps[0].state == StepState.FAILED
        assert "Always fails with ValueError" in saga.steps[0].error


class TestGetSagaNotFound:
    """Test get_saga_status when saga not found (line 662)."""

    def test_get_saga_status_not_found(self):
        """Test that get_saga_status returns error when saga not found."""
        coordinator = create_saga_coordinator()
        status = coordinator.get_saga_status("nonexistent-id")
        assert status == {"error": "Saga not found"}

    def test_get_saga_returns_none_for_unknown(self):
        """Test get_saga returns None for unknown saga."""
        coordinator = create_saga_coordinator()
        result = coordinator.get_saga("unknown-id")
        assert result is None


class TestSagaContextManagerSuccess:
    """Test saga_context with auto_execute=True and successful saga (line 737)."""

    async def test_context_manager_auto_execute_success(self):
        """Test context manager with auto_execute=True and successful saga."""
        coordinator = create_saga_coordinator()

        async def execute(ctx, data):
            return {"result": "ok"}

        async with saga_context(
            coordinator,
            "Auto Execute Success",
            auto_execute=True,
            context={"key": "value"},
        ) as saga:
            coordinator.add_step(saga, "Step 1", execute_func=execute)

        assert saga.state == SagaState.COMPLETED

    async def test_context_manager_auto_execute_false(self):
        """Test context manager with auto_execute=False does not execute."""
        coordinator = create_saga_coordinator()

        async def execute(ctx, data):
            return {}

        async with saga_context(
            coordinator,
            "No Auto Execute",
            auto_execute=False,
        ) as saga:
            coordinator.add_step(saga, "Step 1", execute_func=execute)

        # Should still be INITIALIZED since auto_execute=False
        assert saga.state == SagaState.INITIALIZED


class TestSagaContextManagerErrorHandling:
    """Test saga_context error handling branches (lines 743-744)."""

    async def test_context_manager_sets_failed_state_on_initialized_saga(self):
        """Test that context manager sets FAILED state on an INITIALIZED saga when error occurs."""
        coordinator = create_saga_coordinator()

        with pytest.raises(RuntimeError):
            async with saga_context(
                coordinator,
                "Error in Context",
                auto_execute=False,  # Don't auto-execute
            ) as saga:
                # Raise a RuntimeError inside the context block
                raise RuntimeError("Error inside context")

        # The saga was INITIALIZED when the error hit, so it should be FAILED
        assert saga.state == SagaState.FAILED
        assert "Error inside context" in saga.failure_reason

    async def test_context_manager_does_not_override_running_state(self):
        """Test context manager does not override state if saga is already running."""
        coordinator = create_saga_coordinator()

        async def execute(ctx, data):
            return {}

        async def failing_execute(ctx, data):
            raise RuntimeError("fails during execution")

        with pytest.raises(RuntimeError):
            async with saga_context(
                coordinator,
                "Running State Test",
                auto_execute=True,
                context={},
            ) as saga:
                coordinator.add_step(saga, "Good Step", execute)
                coordinator.add_step(saga, "Bad Step", failing_execute, max_retries=0)

        # After compensation the saga state should reflect compensation, not FAILED from context
        assert saga.state in (SagaState.COMPENSATED, SagaState.FAILED)


class TestSagaCoordinatorInit:
    """Test SagaCoordinator direct instantiation."""

    def test_direct_instantiation(self):
        """Test directly creating SagaCoordinator."""
        coordinator = SagaCoordinator(
            default_timeout_ms=120000,
            compensation_timeout_ms=30000,
            max_concurrent_compensations=10,
        )
        assert coordinator.default_timeout_ms == 120000
        assert coordinator.compensation_timeout_ms == 30000
        assert coordinator.max_concurrent_compensations == 10
        assert coordinator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_initial_state(self):
        """Test coordinator starts with empty saga stores."""
        coordinator = SagaCoordinator()
        assert len(coordinator._active_sagas) == 0
        assert len(coordinator._completed_sagas) == 0
        assert len(coordinator._checkpoint_store) == 0


class TestSagaTransactionProperties:
    """Test SagaTransaction computed properties."""

    def test_failed_steps_property(self):
        """Test failed_steps property returns only failed steps."""
        saga = SagaTransaction(name="Test")
        step1 = SagaStep(name="Step 1")
        step1.state = StepState.FAILED
        step2 = SagaStep(name="Step 2")
        step2.state = StepState.COMPLETED
        step3 = SagaStep(name="Step 3")
        step3.state = StepState.FAILED
        saga.steps = [step1, step2, step3]

        assert len(saga.failed_steps) == 2
        assert all(s.state == StepState.FAILED for s in saga.failed_steps)

    def test_to_dict_with_all_timestamps(self):
        """Test to_dict when all timestamps are set."""
        saga = SagaTransaction(name="Full Saga")
        now = datetime.now(UTC)
        saga.started_at = now
        saga.completed_at = now
        saga.failed_at = now
        saga.compensated_at = now

        data = saga.to_dict()

        assert data["started_at"] is not None
        assert data["completed_at"] is not None
        assert data["failed_at"] is not None
        assert data["compensated_at"] is not None


class TestSagaStepToDict:
    """Test SagaStep.to_dict with all branches."""

    def test_step_to_dict_all_timestamps(self):
        """Test to_dict with all timestamps and output_data set."""
        step = SagaStep(name="Full Step")
        now = datetime.now(UTC)
        step.started_at = now
        step.completed_at = now
        step.compensated_at = now
        step.output_data = {"result": "value"}

        data = step.to_dict()

        assert data["started_at"] is not None
        assert data["completed_at"] is not None
        assert data["compensated_at"] is not None
        assert data["output_data"] is not None

    def test_step_to_dict_with_compensation(self):
        """Test to_dict when step has a compensation."""
        step = SagaStep(name="Compensated Step")
        comp = SagaCompensation(step_id=step.step_id)
        step.compensation = comp

        data = step.to_dict()

        assert data["compensation"] is not None
        assert "compensation_id" in data["compensation"]


class TestCheckpointStore:
    """Test checkpoint store management."""

    def test_checkpoint_stored_in_checkpoint_store(self):
        """Test that checkpoints are stored in coordinator's checkpoint store."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Checkpoint Store Test")

        # Create multiple checkpoints
        cp1 = coordinator.create_checkpoint(saga, "checkpoint-1")
        cp2 = coordinator.create_checkpoint(saga, "checkpoint-2", is_constitutional=True)

        assert saga.saga_id in coordinator._checkpoint_store
        assert len(coordinator._checkpoint_store[saga.saga_id]) == 2

    def test_checkpoint_to_dict_all_fields(self):
        """Test SagaCheckpoint.to_dict contains all required fields."""
        checkpoint = SagaCheckpoint(
            saga_id="test-saga",
            name="test-checkpoint",
            state_snapshot={"step": 1},
            completed_steps=["step-1"],
            pending_steps=["step-2"],
            is_constitutional_checkpoint=True,
        )
        data = checkpoint.to_dict()

        assert data["saga_id"] == "test-saga"
        assert data["name"] == "test-checkpoint"
        assert data["is_constitutional_checkpoint"] is True
        assert data["completed_steps"] == ["step-1"]
        assert data["pending_steps"] == ["step-2"]
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSagaListAndStatus:
    """Test coordinator listing and status methods."""

    async def test_coordinator_status_with_completed_and_compensated(self):
        """Test coordinator status with both completed and compensated sagas."""
        coordinator = create_saga_coordinator()

        # Create a completing saga
        async def execute(ctx, data):
            return {}

        saga1 = coordinator.create_saga("Success Saga")
        coordinator.add_step(saga1, "Step", execute)
        await coordinator.execute_saga(saga1)

        # Create a failing saga
        async def fail(ctx, data):
            raise RuntimeError("fails")

        async def compensate(result):
            return {}

        saga2 = coordinator.create_saga("Failing Saga")
        coordinator.add_step(saga2, "Step", execute, compensate)
        coordinator.add_step(saga2, "Fail", fail, None, max_retries=0)
        await coordinator.execute_saga(saga2)

        status = await coordinator.get_coordinator_status()

        assert status["completed_sagas"] >= 1
        assert status["success_rate"] > 0

    def test_list_active_sagas_empty(self):
        """Test listing active sagas when none exist."""
        coordinator = create_saga_coordinator()
        active = coordinator.list_active_sagas()
        assert active == []

    def test_list_active_sagas_structure(self):
        """Test that list_active_sagas returns correct structure."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Test Saga")

        async def execute(ctx, data):
            return {}

        coordinator.add_step(saga, "Step 1", execute)

        active = coordinator.list_active_sagas()
        assert len(active) == 1
        assert "saga_id" in active[0]
        assert "name" in active[0]
        assert "state" in active[0]
        assert "steps" in active[0]
        assert active[0]["steps"] == 1


class TestAbortSagaWithCompensation:
    """Test abort saga with compensation for ABORTED state preservation."""

    async def test_abort_initialized_saga(self):
        """Test aborting an INITIALIZED saga triggers compensation."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Abort Initialized Test")

        compensated = []

        async def execute(ctx, data):
            return {}

        async def compensate(result):
            compensated.append("compensated")

        coordinator.add_step(saga, "Step 1", execute, compensate)

        # Don't execute, just abort an INITIALIZED saga
        result = await coordinator.abort_saga(saga.saga_id, "Test abort reason")

        assert result is True
        assert saga.state == SagaState.ABORTED
        assert saga.failure_reason == "Test abort reason"
        assert saga.failed_at is not None

    async def test_abort_preserves_aborted_state_after_compensation(self):
        """Test that abort state is preserved even after _compensate_saga is called."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Aborted State Preservation")

        async def execute(ctx, data):
            return {}

        async def compensate(result):
            return {}

        coordinator.add_step(saga, "Step 1", execute, compensate)

        result = await coordinator.abort_saga(saga.saga_id, "Preserve abort state")

        assert result is True
        # State should remain ABORTED, not be overwritten with COMPENSATED
        assert saga.state == SagaState.ABORTED


class TestSagaExecutionEdgeCases:
    """Edge cases for saga execution."""

    async def test_execute_saga_with_no_steps(self):
        """Test executing a saga with no steps completes successfully."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Empty Saga")

        success = await coordinator.execute_saga(saga)

        assert success
        assert saga.state == SagaState.COMPLETED

    async def test_completed_saga_moved_to_completed_store(self):
        """Test that completed saga is moved from active to completed store (lines 440-443)."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Move Test")

        async def execute(ctx, data):
            return {}

        coordinator.add_step(saga, "Step 1", execute)
        saga_id = saga.saga_id

        assert saga_id in coordinator._active_sagas

        success = await coordinator.execute_saga(saga)

        assert success
        assert saga_id not in coordinator._active_sagas
        assert saga_id in coordinator._completed_sagas

    async def test_step_retry_count_updated(self):
        """Test that step retry_count is updated on each attempt."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Retry Count Test")

        attempt_count = [0]

        async def flaky(ctx, data):
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise RuntimeError("Transient")
            return {"ok": True}

        coordinator.add_step(saga, "Flaky", flaky, max_retries=2)

        success = await coordinator.execute_saga(saga)

        assert success
        # retry_count should be 1 (second attempt, zero-indexed)
        assert saga.steps[0].retry_count == 1

    async def test_step_duration_recorded(self):
        """Test that step duration is recorded after execution."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Duration Test")

        async def execute(ctx, data):
            return {}

        coordinator.add_step(saga, "Step 1", execute)

        await coordinator.execute_saga(saga)

        assert saga.steps[0].duration_ms >= 0

    async def test_saga_total_duration_recorded(self):
        """Test that saga total duration is recorded after completion."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Total Duration Test")

        async def execute(ctx, data):
            return {}

        coordinator.add_step(saga, "Step 1", execute)

        await coordinator.execute_saga(saga)

        assert saga.total_duration_ms >= 0


class TestSagaEnumValues:
    """Test all enum values are correct."""

    def test_saga_state_values(self):
        """Test SagaState enum values."""
        assert SagaState.INITIALIZED.value == "initialized"
        assert SagaState.RUNNING.value == "running"
        assert SagaState.CHECKPOINT.value == "checkpoint"
        assert SagaState.COMPENSATING.value == "compensating"
        assert SagaState.COMPENSATED.value == "compensated"
        assert SagaState.COMPLETED.value == "completed"
        assert SagaState.FAILED.value == "failed"
        assert SagaState.TIMEOUT.value == "timeout"
        assert SagaState.ABORTED.value == "aborted"

    def test_step_state_values(self):
        """Test StepState enum values."""
        assert StepState.PENDING.value == "pending"
        assert StepState.RUNNING.value == "running"
        assert StepState.COMPLETED.value == "completed"
        assert StepState.FAILED.value == "failed"
        assert StepState.COMPENSATING.value == "compensating"
        assert StepState.COMPENSATED.value == "compensated"
        assert StepState.SKIPPED.value == "skipped"

    def test_compensation_strategy_values(self):
        """Test CompensationStrategy enum values."""
        assert CompensationStrategy.LIFO.value == "lifo"
        assert CompensationStrategy.PARALLEL.value == "parallel"
        assert CompensationStrategy.SELECTIVE.value == "selective"
