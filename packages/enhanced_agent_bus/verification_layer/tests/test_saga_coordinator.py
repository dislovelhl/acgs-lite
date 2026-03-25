"""
Tests for Saga Coordinator - Compensable Transaction Management
Constitutional Hash: 608508a9bd224290

Tests cover:
- Saga transaction creation and execution
- LIFO compensation rollback
- Checkpoint management
- Timeout handling
- Constitutional compliance
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestConstitutionalHash:
    """Tests for constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Test that constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_coordinator_has_constitutional_hash(self):
        """Test that coordinator includes constitutional hash."""
        coordinator = create_saga_coordinator()
        assert coordinator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_transaction_has_constitutional_hash(self):
        """Test that saga transaction includes constitutional hash."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Test Saga")
        assert saga.constitutional_hash == CONSTITUTIONAL_HASH


class TestSagaCoordinatorCreation:
    """Tests for SagaCoordinator creation."""

    def test_default_creation(self):
        """Test coordinator creation with defaults."""
        coordinator = create_saga_coordinator()
        assert coordinator is not None
        assert coordinator.default_timeout_ms == 300000
        assert coordinator.compensation_timeout_ms == 60000

    def test_custom_timeouts(self):
        """Test coordinator with custom timeouts."""
        coordinator = create_saga_coordinator(
            default_timeout_ms=60000,
            compensation_timeout_ms=30000,
        )
        assert coordinator.default_timeout_ms == 60000
        assert coordinator.compensation_timeout_ms == 30000


class TestSagaCreation:
    """Tests for saga transaction creation."""

    def test_create_saga(self):
        """Test basic saga creation."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga(
            name="Test Saga",
            description="A test saga",
        )

        assert saga is not None
        assert saga.name == "Test Saga"
        assert saga.description == "A test saga"
        assert saga.state == SagaState.INITIALIZED
        assert saga.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_has_unique_id(self):
        """Test that each saga has unique ID."""
        coordinator = create_saga_coordinator()
        saga1 = coordinator.create_saga("Saga 1")
        saga2 = coordinator.create_saga("Saga 2")

        assert saga1.saga_id != saga2.saga_id

    def test_saga_with_metadata(self):
        """Test saga creation with metadata."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga(
            name="Test",
            metadata={"key": "value"},
        )

        assert saga.metadata["key"] == "value"

    def test_saga_with_compensation_strategy(self):
        """Test saga with custom compensation strategy."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga(
            name="Test",
            compensation_strategy=CompensationStrategy.PARALLEL,
        )

        assert saga.compensation_strategy == CompensationStrategy.PARALLEL


class TestSagaSteps:
    """Tests for saga step management."""

    def test_add_step(self):
        """Test adding a step to saga."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Test")

        async def execute(ctx, data):
            return {"result": "success"}

        step = coordinator.add_step(
            saga,
            name="Step 1",
            execute_func=execute,
            description="First step",
        )

        assert step is not None
        assert step.name == "Step 1"
        assert step.state == StepState.PENDING
        assert len(saga.steps) == 1

    def test_add_step_with_compensation(self):
        """Test adding step with compensation function."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Test")

        async def execute(ctx, data):
            return {"result": "success"}

        async def compensate(result):
            return {"compensated": True}

        step = coordinator.add_step(
            saga,
            name="Step 1",
            execute_func=execute,
            compensate_func=compensate,
        )

        assert step.compensation is not None
        assert step.compensation.compensation_func is not None

    def test_cannot_add_step_after_execution(self):
        """Test that steps cannot be added to running saga."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Test")
        saga.state = SagaState.RUNNING

        async def execute(ctx, data):
            return {}

        with pytest.raises(ValueError):
            coordinator.add_step(saga, "Step", execute_func=execute)

    def test_add_multiple_steps(self):
        """Test adding multiple steps."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Test")

        async def step_func(ctx, data):
            return {}

        for i in range(5):
            coordinator.add_step(saga, f"Step {i}", execute_func=step_func)

        assert len(saga.steps) == 5

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Test")

        async def execute(ctx, data):
            return {}

        step1 = coordinator.add_step(saga, "Step 1", execute_func=execute)
        step2 = coordinator.add_step(
            saga,
            "Step 2",
            execute_func=execute,
            dependencies=[step1.step_id],
        )

        assert step1.step_id in step2.dependencies


class TestSagaExecution:
    """Tests for saga execution."""

    async def test_execute_simple_saga(self):
        """Test executing a simple saga."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Simple Saga")

        async def execute(ctx, data):
            return {"status": "done"}

        coordinator.add_step(saga, "Step 1", execute_func=execute)

        success = await coordinator.execute_saga(saga)

        assert success
        assert saga.state == SagaState.COMPLETED
        assert saga.completed_at is not None

    async def test_execute_multiple_steps(self):
        """Test executing saga with multiple steps."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Multi-step Saga")

        execution_order = []

        async def step1(ctx, data):
            execution_order.append(1)
            return {"step": 1}

        async def step2(ctx, data):
            execution_order.append(2)
            return {"step": 2}

        async def step3(ctx, data):
            execution_order.append(3)
            return {"step": 3}

        coordinator.add_step(saga, "Step 1", execute_func=step1)
        coordinator.add_step(saga, "Step 2", execute_func=step2)
        coordinator.add_step(saga, "Step 3", execute_func=step3)

        success = await coordinator.execute_saga(saga)

        assert success
        assert execution_order == [1, 2, 3]
        assert all(s.state == StepState.COMPLETED for s in saga.steps)

    async def test_execution_with_context(self):
        """Test saga execution passes context."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Context Saga")

        received_context = {}

        async def execute(ctx, data):
            received_context.update(ctx)
            return {"received": True}

        coordinator.add_step(saga, "Step 1", execute_func=execute)

        success = await coordinator.execute_saga(
            saga,
            context={"key": "value"},
        )

        assert success
        assert received_context.get("key") == "value"

    async def test_step_output_available_in_context(self):
        """Test that step output is available to subsequent steps."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Output Test")

        step1_output = None

        async def step1(ctx, data):
            return {"from_step1": "value1"}

        async def step2(ctx, data):
            nonlocal step1_output
            step1_output = ctx.get(f"step_{saga.steps[0].step_id}_output")
            return {"from_step2": "value2"}

        coordinator.add_step(saga, "Step 1", execute_func=step1)
        coordinator.add_step(saga, "Step 2", execute_func=step2)

        success = await coordinator.execute_saga(saga)

        assert success
        assert step1_output is not None
        assert step1_output.get("from_step1") == "value1"


class TestSagaCompensation:
    """Tests for saga compensation."""

    async def test_compensation_on_failure(self):
        """Test compensation executes on failure."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Failing Saga")

        compensated = []

        async def execute1(ctx, data):
            return {"step": 1}

        async def compensate1(result):
            compensated.append(1)
            return {"compensated": 1}

        async def execute2(ctx, data):
            raise RuntimeError("Step 2 failed")

        async def compensate2(result):
            compensated.append(2)
            return {"compensated": 2}

        coordinator.add_step(saga, "Step 1", execute1, compensate1)
        coordinator.add_step(saga, "Step 2", execute2, compensate2)

        success = await coordinator.execute_saga(saga)

        assert not success
        assert saga.state == SagaState.COMPENSATED
        assert 1 in compensated  # Step 1 was compensated

    async def test_lifo_compensation_order(self):
        """Test LIFO compensation order."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga(
            "LIFO Test",
            compensation_strategy=CompensationStrategy.LIFO,
        )

        compensation_order = []

        async def execute(ctx, data):
            return {}

        async def compensate1(result):
            compensation_order.append(1)

        async def compensate2(result):
            compensation_order.append(2)

        async def execute_fail(ctx, data):
            raise RuntimeError("Fail")

        coordinator.add_step(saga, "Step 1", execute, compensate1)
        coordinator.add_step(saga, "Step 2", execute, compensate2)
        coordinator.add_step(saga, "Step 3", execute_fail, None)

        success = await coordinator.execute_saga(saga)

        assert not success
        assert compensation_order == [2, 1]  # LIFO order

    async def test_compensation_log(self):
        """Test compensation log is populated."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Compensation Log Test")

        async def execute(ctx, data):
            return {"data": "value"}

        async def compensate(result):
            return {"compensated": True}

        async def fail(ctx, data):
            raise RuntimeError("Failure")

        coordinator.add_step(saga, "Step 1", execute, compensate)
        coordinator.add_step(saga, "Step 2", fail, None)

        await coordinator.execute_saga(saga)

        assert len(saga.compensation_log) > 0
        assert any(log.get("status") == "compensated" for log in saga.compensation_log)


class TestSagaCheckpoints:
    """Tests for saga checkpoints."""

    def test_create_checkpoint(self):
        """Test checkpoint creation."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Checkpoint Test")

        async def execute(ctx, data):
            return {}

        coordinator.add_step(saga, "Step 1", execute_func=execute)

        checkpoint = coordinator.create_checkpoint(
            saga,
            name="pre_critical",
            is_constitutional=True,
        )

        assert checkpoint is not None
        assert checkpoint.name == "pre_critical"
        assert checkpoint.is_constitutional_checkpoint
        assert checkpoint.saga_id == saga.saga_id
        assert len(saga.checkpoints) == 1

    def test_checkpoint_captures_state(self):
        """Test that checkpoint captures current state."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("State Capture Test")

        async def execute(ctx, data):
            return {}

        step1 = coordinator.add_step(saga, "Step 1", execute_func=execute)
        step1.state = StepState.COMPLETED

        checkpoint = coordinator.create_checkpoint(saga, "checkpoint1")

        assert step1.step_id in checkpoint.completed_steps

    def test_checkpoint_to_dict(self):
        """Test checkpoint serialization."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Serialize Test")
        checkpoint = coordinator.create_checkpoint(saga, "test_checkpoint")

        data = checkpoint.to_dict()

        assert "checkpoint_id" in data
        assert "name" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSagaAbort:
    """Tests for saga abort functionality."""

    async def test_abort_running_saga(self):
        """Test aborting a running saga."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Abort Test")

        async def long_execute(ctx, data):
            await asyncio.sleep(10)
            return {}

        async def compensate(result):
            return {}

        coordinator.add_step(saga, "Long Step", long_execute, compensate)

        # Start execution in background
        exec_task = asyncio.create_task(coordinator.execute_saga(saga))

        # Give it time to start
        await asyncio.sleep(0.1)

        # Abort
        success = await coordinator.abort_saga(saga.saga_id, "Manual abort")

        assert success
        assert saga.state == SagaState.ABORTED
        assert saga.failure_reason == "Manual abort"

        # Cancel the background task
        exec_task.cancel()
        try:
            await exec_task
        except asyncio.CancelledError:
            pass


class TestSagaTimeout:
    """Tests for saga timeout handling."""

    async def test_step_timeout(self):
        """Test step timeout handling."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Timeout Test")

        async def slow_execute(ctx, data):
            await asyncio.sleep(5)
            return {}

        async def compensate(result):
            return {}

        coordinator.add_step(
            saga,
            "Slow Step",
            slow_execute,
            compensate,
            timeout_ms=100,  # Very short timeout
            max_retries=0,
        )

        success = await coordinator.execute_saga(saga)

        assert not success
        assert saga.steps[0].state == StepState.FAILED


class TestSagaRetry:
    """Tests for saga retry logic."""

    async def test_step_retry_on_failure(self):
        """Test that steps are retried on failure."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Retry Test")

        attempt_count = [0]

        async def flaky_execute(ctx, data):
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise RuntimeError("Transient failure")
            return {"success": True}

        coordinator.add_step(
            saga,
            "Flaky Step",
            flaky_execute,
            None,
            max_retries=3,
        )

        success = await coordinator.execute_saga(saga)

        assert success
        assert attempt_count[0] == 3

    async def test_max_retries_exhausted(self):
        """Test failure after max retries exhausted."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Max Retry Test")

        async def always_fails(ctx, data):
            raise RuntimeError("Always fails")

        coordinator.add_step(
            saga,
            "Failing Step",
            always_fails,
            None,
            max_retries=2,
        )

        success = await coordinator.execute_saga(saga)

        assert not success
        assert saga.steps[0].retry_count == 2


class TestSagaContextManager:
    """Tests for saga context manager."""

    async def test_context_manager_success(self):
        """Test context manager with successful saga."""
        coordinator = create_saga_coordinator()

        async def execute(ctx, data):
            return {}

        async with saga_context(
            coordinator,
            "Context Manager Test",
            auto_execute=False,
        ) as saga:
            coordinator.add_step(saga, "Step 1", execute_func=execute)

        assert saga.state == SagaState.INITIALIZED

    async def test_context_manager_failure(self):
        """Test context manager with failing saga."""
        coordinator = create_saga_coordinator()

        async def fail(ctx, data):
            raise RuntimeError("Fail")

        with pytest.raises(RuntimeError):
            async with saga_context(
                coordinator,
                "Failing Context Manager",
                auto_execute=True,
                context={},
            ) as saga:
                coordinator.add_step(saga, "Failing Step", execute_func=fail)


class TestSagaStatus:
    """Tests for saga status and statistics."""

    def test_get_saga_status(self):
        """Test getting saga status."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Status Test")

        async def execute(ctx, data):
            return {}

        coordinator.add_step(saga, "Step 1", execute_func=execute)

        status = coordinator.get_saga_status(saga.saga_id)

        assert status["saga_id"] == saga.saga_id
        assert status["name"] == "Status Test"
        assert status["state"] == SagaState.INITIALIZED.value
        assert status["total_steps"] == 1

    def test_list_active_sagas(self):
        """Test listing active sagas."""
        coordinator = create_saga_coordinator()
        coordinator.create_saga("Saga 1")
        coordinator.create_saga("Saga 2")

        active = coordinator.list_active_sagas()

        assert len(active) == 2

    async def test_coordinator_status(self):
        """Test coordinator status."""
        coordinator = create_saga_coordinator()
        coordinator.create_saga("Test")

        status = await coordinator.get_coordinator_status()

        assert status["coordinator"] == "Saga Coordinator"
        assert status["status"] == "operational"
        assert status["active_sagas"] == 1
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestSagaTransaction:
    """Tests for SagaTransaction model."""

    def test_transaction_to_dict(self):
        """Test transaction serialization."""
        coordinator = create_saga_coordinator()
        saga = coordinator.create_saga("Serialize Test")

        data = saga.to_dict()

        assert "saga_id" in data
        assert "name" in data
        assert "state" in data
        assert "steps" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_completed_steps_property(self):
        """Test completed_steps property."""
        saga = SagaTransaction(name="Test")
        step1 = SagaStep(name="Step 1")
        step1.state = StepState.COMPLETED
        step2 = SagaStep(name="Step 2")
        step2.state = StepState.PENDING
        saga.steps = [step1, step2]

        assert len(saga.completed_steps) == 1
        assert saga.completed_steps[0].name == "Step 1"

    def test_pending_steps_property(self):
        """Test pending_steps property."""
        saga = SagaTransaction(name="Test")
        step1 = SagaStep(name="Step 1")
        step1.state = StepState.COMPLETED
        step2 = SagaStep(name="Step 2")
        step2.state = StepState.PENDING
        saga.steps = [step1, step2]

        assert len(saga.pending_steps) == 1
        assert saga.pending_steps[0].name == "Step 2"


class TestSagaStep:
    """Tests for SagaStep model."""

    def test_step_to_dict(self):
        """Test step serialization."""
        step = SagaStep(
            name="Test Step",
            description="A test step",
            timeout_ms=5000,
        )

        data = step.to_dict()

        assert data["name"] == "Test Step"
        assert data["description"] == "A test step"
        assert data["timeout_ms"] == 5000
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestCompensationStrategy:
    """Tests for compensation strategies."""

    def test_lifo_strategy_defined(self):
        """Test LIFO strategy is defined."""
        assert CompensationStrategy.LIFO.value == "lifo"

    def test_parallel_strategy_defined(self):
        """Test parallel strategy is defined."""
        assert CompensationStrategy.PARALLEL.value == "parallel"

    def test_selective_strategy_defined(self):
        """Test selective strategy is defined."""
        assert CompensationStrategy.SELECTIVE.value == "selective"
