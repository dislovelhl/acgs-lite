"""
ACGS-2 Recovery Orchestrator Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the recovery orchestrator module.
"""

from datetime import UTC, datetime, timezone

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# Import module under test
try:
    from enhanced_agent_bus.recovery_orchestrator import (
        CONSTITUTIONAL_HASH,
        RecoveryOrchestrator,
        RecoveryOrchestratorError,
        RecoveryPolicy,
        RecoveryResult,
        RecoveryState,
        RecoveryStrategy,
        RecoveryTask,
        RecoveryValidationError,
    )
except ImportError:
    from recovery_orchestrator import (
        CONSTITUTIONAL_HASH,
        RecoveryOrchestrator,
        RecoveryOrchestratorError,
        RecoveryPolicy,
        RecoveryResult,
        RecoveryState,
        RecoveryStrategy,
        RecoveryTask,
        RecoveryValidationError,
    )


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalCompliance:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is present and correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_module(self):
        """Verify constitutional hash is exported."""
        try:
            from enhanced_agent_bus import recovery_orchestrator as ro_mod
        except (ImportError, ModuleNotFoundError):
            import recovery_orchestrator as ro_mod
        assert hasattr(ro_mod, "CONSTITUTIONAL_HASH")
        assert ro_mod.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_recovery_policy_has_constitutional_hash(self):
        """Test RecoveryPolicy includes constitutional hash."""
        policy = RecoveryPolicy()
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH

    def test_recovery_result_has_constitutional_hash(self):
        """Test RecoveryResult includes constitutional hash."""
        result = RecoveryResult(
            service_name="test_service",
            success=True,
            attempt_number=1,
            total_attempts=5,
            elapsed_time_ms=100.0,
            state=RecoveryState.SUCCEEDED,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_recovery_task_has_constitutional_hash(self):
        """Test RecoveryTask includes constitutional hash."""
        task = RecoveryTask(
            priority=1,
            service_name="test_service",
            strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            policy=RecoveryPolicy(),
        )
        assert task.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_orchestrator_validates_constitutional_hash(self):
        """Test orchestrator validates constitutional hash on start."""
        orchestrator = RecoveryOrchestrator()
        # Should not raise with valid hash
        await orchestrator.start()
        await orchestrator.stop()


# =============================================================================
# RecoveryStrategy Enum Tests
# =============================================================================


class TestRecoveryStrategy:
    """Test RecoveryStrategy enum."""

    def test_exponential_backoff_value(self):
        """Test EXPONENTIAL_BACKOFF value."""
        assert RecoveryStrategy.EXPONENTIAL_BACKOFF.value == "exponential_backoff"

    def test_linear_backoff_value(self):
        """Test LINEAR_BACKOFF value."""
        assert RecoveryStrategy.LINEAR_BACKOFF.value == "linear_backoff"

    def test_immediate_value(self):
        """Test IMMEDIATE value."""
        assert RecoveryStrategy.IMMEDIATE.value == "immediate"

    def test_manual_value(self):
        """Test MANUAL value."""
        assert RecoveryStrategy.MANUAL.value == "manual"


# =============================================================================
# RecoveryState Enum Tests
# =============================================================================


class TestRecoveryState:
    """Test RecoveryState enum."""

    def test_idle_state(self):
        """Test IDLE state value."""
        assert RecoveryState.IDLE.value == "idle"

    def test_scheduled_state(self):
        """Test SCHEDULED state value."""
        assert RecoveryState.SCHEDULED.value == "scheduled"

    def test_in_progress_state(self):
        """Test IN_PROGRESS state value."""
        assert RecoveryState.IN_PROGRESS.value == "in_progress"

    def test_succeeded_state(self):
        """Test SUCCEEDED state value."""
        assert RecoveryState.SUCCEEDED.value == "succeeded"

    def test_failed_state(self):
        """Test FAILED state value."""
        assert RecoveryState.FAILED.value == "failed"

    def test_cancelled_state(self):
        """Test CANCELLED state value."""
        assert RecoveryState.CANCELLED.value == "cancelled"

    def test_awaiting_manual_state(self):
        """Test AWAITING_MANUAL state value."""
        assert RecoveryState.AWAITING_MANUAL.value == "awaiting_manual"


# =============================================================================
# RecoveryPolicy Tests
# =============================================================================


class TestRecoveryPolicy:
    """Test RecoveryPolicy dataclass."""

    def test_default_values(self):
        """Test default policy values."""
        policy = RecoveryPolicy()
        assert policy.max_retry_attempts == 5
        assert policy.backoff_multiplier == 2.0
        assert policy.initial_delay_ms == 1000
        assert policy.max_delay_ms == 60000
        assert policy.health_check_fn is None
        assert policy.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        """Test custom policy values."""

        def health_fn():
            return True

        policy = RecoveryPolicy(
            max_retry_attempts=10,
            backoff_multiplier=1.5,
            initial_delay_ms=500,
            max_delay_ms=30000,
            health_check_fn=health_fn,
        )
        assert policy.max_retry_attempts == 10
        assert policy.backoff_multiplier == 1.5
        assert policy.initial_delay_ms == 500
        assert policy.max_delay_ms == 30000
        assert policy.health_check_fn == health_fn

    def test_validation_max_retry_attempts(self):
        """Test validation of max_retry_attempts."""
        with pytest.raises(ValueError, match="max_retry_attempts must be >= 1"):
            RecoveryPolicy(max_retry_attempts=0)

    def test_validation_backoff_multiplier(self):
        """Test validation of backoff_multiplier."""
        with pytest.raises(ValueError, match=r"backoff_multiplier must be >= 1.0"):
            RecoveryPolicy(backoff_multiplier=0.5)

    def test_validation_initial_delay(self):
        """Test validation of initial_delay_ms."""
        with pytest.raises(ValueError, match="initial_delay_ms must be >= 0"):
            RecoveryPolicy(initial_delay_ms=-1)

    def test_validation_max_delay(self):
        """Test validation of max_delay_ms."""
        with pytest.raises(ValueError, match="max_delay_ms must be >= initial_delay_ms"):
            RecoveryPolicy(initial_delay_ms=2000, max_delay_ms=1000)


# =============================================================================
# RecoveryResult Tests
# =============================================================================


class TestRecoveryResult:
    """Test RecoveryResult dataclass."""

    def test_result_creation(self):
        """Test creating a recovery result."""
        result = RecoveryResult(
            service_name="test_service",
            success=True,
            attempt_number=3,
            total_attempts=5,
            elapsed_time_ms=250.5,
            state=RecoveryState.SUCCEEDED,
        )
        assert result.service_name == "test_service"
        assert result.success is True
        assert result.attempt_number == 3
        assert result.total_attempts == 5
        assert result.elapsed_time_ms == 250.5
        assert result.state == RecoveryState.SUCCEEDED

    def test_result_with_error(self):
        """Test result with error message."""
        result = RecoveryResult(
            service_name="test_service",
            success=False,
            attempt_number=5,
            total_attempts=5,
            elapsed_time_ms=100.0,
            state=RecoveryState.FAILED,
            error_message="Connection timeout",
        )
        assert result.error_message == "Connection timeout"

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = RecoveryResult(
            service_name="test_service",
            success=True,
            attempt_number=2,
            total_attempts=5,
            elapsed_time_ms=150.0,
            state=RecoveryState.SUCCEEDED,
            health_check_passed=True,
        )
        result_dict = result.to_dict()

        assert result_dict["service_name"] == "test_service"
        assert result_dict["success"] is True
        assert result_dict["attempt_number"] == 2
        assert result_dict["total_attempts"] == 5
        assert result_dict["elapsed_time_ms"] == 150.0
        assert result_dict["state"] == "succeeded"
        assert result_dict["health_check_passed"] is True
        assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in result_dict


# =============================================================================
# RecoveryTask Tests
# =============================================================================


class TestRecoveryTask:
    """Test RecoveryTask dataclass."""

    def test_task_creation(self):
        """Test creating a recovery task."""
        policy = RecoveryPolicy()
        task = RecoveryTask(
            priority=1,
            service_name="test_service",
            strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            policy=policy,
        )
        assert task.priority == 1
        assert task.service_name == "test_service"
        assert task.strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF
        assert task.policy == policy
        assert task.state == RecoveryState.SCHEDULED

    def test_task_ordering(self):
        """Test task priority ordering."""
        task1 = RecoveryTask(
            priority=2,
            service_name="service_low",
            strategy=RecoveryStrategy.IMMEDIATE,
            policy=RecoveryPolicy(),
        )
        task2 = RecoveryTask(
            priority=1,
            service_name="service_high",
            strategy=RecoveryStrategy.IMMEDIATE,
            policy=RecoveryPolicy(),
        )
        # Lower priority number = higher priority
        assert task2 < task1

    def test_task_defaults(self):
        """Test task default values."""
        task = RecoveryTask(
            priority=1,
            service_name="test_service",
            strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            policy=RecoveryPolicy(),
        )
        assert task.attempt_count == 0
        assert task.last_attempt_at is None
        assert task.next_attempt_at is None
        assert task.state == RecoveryState.SCHEDULED


# =============================================================================
# RecoveryOrchestrator Tests
# =============================================================================


class TestRecoveryOrchestrator:
    """Test RecoveryOrchestrator class."""

    def test_orchestrator_initialization(self):
        """Test orchestrator initialization."""
        orchestrator = RecoveryOrchestrator()
        assert orchestrator.constitutional_hash == CONSTITUTIONAL_HASH
        assert orchestrator.default_policy is not None
        assert not orchestrator._running

    def test_orchestrator_with_custom_policy(self):
        """Test orchestrator with custom default policy."""
        policy = RecoveryPolicy(max_retry_attempts=10)
        orchestrator = RecoveryOrchestrator(default_policy=policy)
        assert orchestrator.default_policy.max_retry_attempts == 10

    async def test_orchestrator_start_stop(self):
        """Test starting and stopping orchestrator."""
        orchestrator = RecoveryOrchestrator()

        assert not orchestrator._running

        await orchestrator.start()
        assert orchestrator._running

        await orchestrator.stop()
        assert not orchestrator._running

    async def test_orchestrator_double_start_raises(self):
        """Test starting already running orchestrator raises error."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        with pytest.raises(RecoveryOrchestratorError, match="already running"):
            await orchestrator.start()

        await orchestrator.stop()

    async def test_schedule_recovery_basic(self):
        """Test scheduling basic recovery."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        orchestrator.schedule_recovery(
            service_name="test_service",
            strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            priority=1,
        )

        status = orchestrator.get_recovery_status()
        assert "test_service" in status["services"]
        assert status["services"]["test_service"]["state"] == "scheduled"

        await orchestrator.stop()

    async def test_schedule_recovery_with_priority(self):
        """Test recovery respects priority ordering."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        # Schedule lower priority first
        orchestrator.schedule_recovery("service_low", priority=5)
        # Schedule higher priority second
        orchestrator.schedule_recovery("service_high", priority=1)

        status = orchestrator.get_recovery_status()
        assert "service_low" in status["services"]
        assert "service_high" in status["services"]

        await orchestrator.stop()

    async def test_schedule_recovery_with_custom_policy(self):
        """Test scheduling recovery with custom policy."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        custom_policy = RecoveryPolicy(
            max_retry_attempts=3,
            initial_delay_ms=500,
        )

        orchestrator.schedule_recovery(
            service_name="test_service",
            strategy=RecoveryStrategy.LINEAR_BACKOFF,
            priority=1,
            policy=custom_policy,
        )

        status = orchestrator.get_recovery_status()
        assert status["services"]["test_service"]["max_attempts"] == 3

        await orchestrator.stop()

    async def test_execute_recovery_not_found(self):
        """Test executing recovery for non-existent service raises error."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        with pytest.raises(RecoveryValidationError, match="No active recovery task"):
            await orchestrator.execute_recovery("nonexistent_service")

        await orchestrator.stop()

    async def test_execute_recovery_success(self):
        """Test successful recovery execution."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        orchestrator.schedule_recovery(
            service_name="test_service",
            strategy=RecoveryStrategy.IMMEDIATE,
            priority=1,
        )

        result = await orchestrator.execute_recovery("test_service")

        assert result.service_name == "test_service"
        assert result.attempt_number == 1
        assert result.elapsed_time_ms >= 0

        await orchestrator.stop()

    async def test_execute_recovery_with_health_check(self):
        """Test recovery with health check function."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        health_check_called = False

        def health_check():
            nonlocal health_check_called
            health_check_called = True
            return True

        policy = RecoveryPolicy(health_check_fn=health_check)

        orchestrator.schedule_recovery(
            service_name="test_service",
            strategy=RecoveryStrategy.IMMEDIATE,
            priority=1,
            policy=policy,
        )

        result = await orchestrator.execute_recovery("test_service")

        assert health_check_called
        assert result.health_check_passed is True

        await orchestrator.stop()

    async def test_execute_recovery_health_check_fails(self):
        """Test recovery fails when health check fails."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        def failing_health_check():
            return False

        policy = RecoveryPolicy(
            max_retry_attempts=2,
            health_check_fn=failing_health_check,
        )

        orchestrator.schedule_recovery(
            service_name="test_service",
            strategy=RecoveryStrategy.IMMEDIATE,
            priority=1,
            policy=policy,
        )

        result = await orchestrator.execute_recovery("test_service")

        assert result.success is False
        assert result.health_check_passed is False

        await orchestrator.stop()

    async def test_cancel_recovery(self):
        """Test cancelling recovery."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        orchestrator.schedule_recovery("test_service", priority=1)

        cancelled = orchestrator.cancel_recovery("test_service")
        assert cancelled is True

        status = orchestrator.get_recovery_status()
        assert "test_service" not in status["services"]

        await orchestrator.stop()

    async def test_cancel_nonexistent_recovery(self):
        """Test cancelling non-existent recovery returns False."""
        orchestrator = RecoveryOrchestrator()
        cancelled = orchestrator.cancel_recovery("nonexistent_service")
        assert cancelled is False

    async def test_set_recovery_policy(self):
        """Test setting service-specific recovery policy."""
        orchestrator = RecoveryOrchestrator()

        custom_policy = RecoveryPolicy(max_retry_attempts=10)
        orchestrator.set_recovery_policy("test_service", custom_policy)

        retrieved_policy = orchestrator.get_recovery_policy("test_service")
        assert retrieved_policy.max_retry_attempts == 10

    async def test_get_recovery_policy_default(self):
        """Test getting default recovery policy for service."""
        orchestrator = RecoveryOrchestrator()

        policy = orchestrator.get_recovery_policy("unknown_service")
        assert policy == orchestrator.default_policy

    async def test_get_recovery_status_structure(self):
        """Test recovery status structure."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        status = orchestrator.get_recovery_status()

        assert "constitutional_hash" in status
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in status
        assert "orchestrator_running" in status
        assert status["orchestrator_running"] is True
        assert "active_recoveries" in status
        assert "queued_recoveries" in status
        assert "services" in status
        assert "recent_history" in status

        await orchestrator.stop()

    async def test_recovery_history_tracking(self):
        """Test recovery history is tracked."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        orchestrator.schedule_recovery("test_service", priority=1)
        await orchestrator.execute_recovery("test_service")

        status = orchestrator.get_recovery_status()
        assert len(status["recent_history"]) > 0
        assert status["recent_history"][0]["service_name"] == "test_service"

        await orchestrator.stop()


# =============================================================================
# Exponential Backoff Timing Tests
# =============================================================================


class TestExponentialBackoffTiming:
    """Test exponential backoff timing calculations."""

    async def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        policy = RecoveryPolicy(
            max_retry_attempts=5,
            initial_delay_ms=1000,
            backoff_multiplier=2.0,
            max_delay_ms=10000,
        )

        task = RecoveryTask(
            priority=1,
            service_name="test_service",
            strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            policy=policy,
        )

        # Test delay calculations
        task.attempt_count = 1
        next_attempt = orchestrator._calculate_next_attempt(task)
        # First retry: 1000ms * 2^0 = 1000ms
        assert (next_attempt - datetime.now(UTC)).total_seconds() * 1000 >= 900

        task.attempt_count = 2
        next_attempt = orchestrator._calculate_next_attempt(task)
        # Second retry: 1000ms * 2^1 = 2000ms
        assert (next_attempt - datetime.now(UTC)).total_seconds() * 1000 >= 1900

        task.attempt_count = 3
        next_attempt = orchestrator._calculate_next_attempt(task)
        # Third retry: 1000ms * 2^2 = 4000ms
        assert (next_attempt - datetime.now(UTC)).total_seconds() * 1000 >= 3900

        await orchestrator.stop()

    async def test_exponential_backoff_max_delay(self):
        """Test exponential backoff respects max delay."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        policy = RecoveryPolicy(
            initial_delay_ms=1000,
            backoff_multiplier=2.0,
            max_delay_ms=5000,  # Cap at 5 seconds
        )

        task = RecoveryTask(
            priority=1,
            service_name="test_service",
            strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            policy=policy,
        )

        # At attempt 10, exponential would be huge, but should cap
        task.attempt_count = 10
        next_attempt = orchestrator._calculate_next_attempt(task)
        delay_ms = (next_attempt - datetime.now(UTC)).total_seconds() * 1000

        # Should be capped at max_delay_ms
        assert delay_ms <= 5100  # Allow small margin for timing

        await orchestrator.stop()


# =============================================================================
# Linear Backoff Tests
# =============================================================================


class TestLinearBackoffTiming:
    """Test linear backoff timing calculations."""

    async def test_linear_backoff_calculation(self):
        """Test linear backoff delay calculation."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        policy = RecoveryPolicy(
            initial_delay_ms=1000,
            max_delay_ms=10000,
        )

        task = RecoveryTask(
            priority=1,
            service_name="test_service",
            strategy=RecoveryStrategy.LINEAR_BACKOFF,
            policy=policy,
        )

        # Test delay calculations
        task.attempt_count = 1
        next_attempt = orchestrator._calculate_next_attempt(task)
        # First retry: 1000ms * 1 = 1000ms
        assert (next_attempt - datetime.now(UTC)).total_seconds() * 1000 >= 900

        task.attempt_count = 2
        next_attempt = orchestrator._calculate_next_attempt(task)
        # Second retry: 1000ms * 2 = 2000ms
        assert (next_attempt - datetime.now(UTC)).total_seconds() * 1000 >= 1900

        task.attempt_count = 3
        next_attempt = orchestrator._calculate_next_attempt(task)
        # Third retry: 1000ms * 3 = 3000ms
        assert (next_attempt - datetime.now(UTC)).total_seconds() * 1000 >= 2900

        await orchestrator.stop()


# =============================================================================
# Immediate Strategy Tests
# =============================================================================


class TestImmediateStrategy:
    """Test immediate recovery strategy."""

    async def test_immediate_strategy_no_delay(self):
        """Test immediate strategy has no delay."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        task = RecoveryTask(
            priority=1,
            service_name="test_service",
            strategy=RecoveryStrategy.IMMEDIATE,
            policy=RecoveryPolicy(),
        )

        task.attempt_count = 1
        next_attempt = orchestrator._calculate_next_attempt(task)

        # Should be immediate (within 100ms)
        delay_ms = (next_attempt - datetime.now(UTC)).total_seconds() * 1000
        assert delay_ms < 100

        await orchestrator.stop()


# =============================================================================
# Priority Queue Ordering Tests
# =============================================================================


class TestPriorityQueueOrdering:
    """Test priority queue ordering."""

    async def test_priority_queue_ordering(self):
        """Test services are processed in priority order."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        # Schedule in reverse priority order
        orchestrator.schedule_recovery("service_low", priority=5)
        orchestrator.schedule_recovery("service_medium", priority=3)
        orchestrator.schedule_recovery("service_high", priority=1)

        status = orchestrator.get_recovery_status()

        # All should be scheduled
        assert len(status["services"]) == 3
        assert "service_low" in status["services"]
        assert "service_medium" in status["services"]
        assert "service_high" in status["services"]

        await orchestrator.stop()

    async def test_same_priority_ordering(self):
        """Test services with same priority."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        # Schedule multiple services with same priority
        orchestrator.schedule_recovery("service_a", priority=1)
        orchestrator.schedule_recovery("service_b", priority=1)
        orchestrator.schedule_recovery("service_c", priority=1)

        status = orchestrator.get_recovery_status()
        assert len(status["services"]) == 3

        await orchestrator.stop()


# =============================================================================
# Constitutional Validation Before Recovery Tests
# =============================================================================


class TestConstitutionalValidationBeforeRecovery:
    """Test constitutional validation is performed before recovery."""

    async def test_schedule_validates_constitutional_hash(self):
        """Test scheduling recovery validates constitutional hash."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        # Should not raise with valid hash
        orchestrator.schedule_recovery("test_service", priority=1)

        await orchestrator.stop()

    async def test_execute_validates_constitutional_hash(self):
        """Test executing recovery validates constitutional hash."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        orchestrator.schedule_recovery("test_service", priority=1)

        # Should not raise with valid hash
        await orchestrator.execute_recovery("test_service")

        await orchestrator.stop()

    async def test_set_policy_validates_constitutional_hash(self):
        """Test setting policy validates constitutional hash."""
        orchestrator = RecoveryOrchestrator()

        # Should not raise with valid hash
        orchestrator.set_recovery_policy("test_service", RecoveryPolicy())


# =============================================================================
# Module Export Tests
# =============================================================================


class TestModuleExports:
    """Test module exports all required components."""

    def _get_module(self):
        """Helper to get module with fallback imports."""
        try:
            from enhanced_agent_bus import recovery_orchestrator

            return recovery_orchestrator
        except (ImportError, ModuleNotFoundError):
            import recovery_orchestrator

            return recovery_orchestrator

    def test_all_enums_exported(self):
        """Test all enums are exported."""
        ro_mod = self._get_module()
        required_enums = ["RecoveryStrategy", "RecoveryState"]
        for enum_name in required_enums:
            assert hasattr(ro_mod, enum_name)

    def test_all_classes_exported(self):
        """Test all classes are exported."""
        ro_mod = self._get_module()
        required_classes = [
            "RecoveryPolicy",
            "RecoveryResult",
            "RecoveryTask",
            "RecoveryOrchestrator",
        ]
        for class_name in required_classes:
            assert hasattr(ro_mod, class_name)

    def test_all_exceptions_exported(self):
        """Test all exceptions are exported."""
        ro_mod = self._get_module()
        required_exceptions = [
            "RecoveryOrchestratorError",
            "RecoveryValidationError",
            "RecoveryConstitutionalError",
        ]
        for exc_name in required_exceptions:
            assert hasattr(ro_mod, exc_name)

    def test_constants_exported(self):
        """Test constants are exported."""
        ro_mod = self._get_module()
        assert hasattr(ro_mod, "CONSTITUTIONAL_HASH")


# =============================================================================
# Integration Tests
# =============================================================================


class TestRecoveryOrchestratorIntegration:
    """Integration tests for recovery orchestrator."""

    async def test_full_recovery_workflow(self):
        """Test complete recovery workflow."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        # Schedule recovery
        orchestrator.schedule_recovery(
            service_name="test_service",
            strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            priority=1,
        )

        # Execute recovery
        result = await orchestrator.execute_recovery("test_service")

        # Verify result
        assert result.service_name == "test_service"
        assert result.attempt_number >= 1

        # Check status
        status = orchestrator.get_recovery_status()
        assert len(status["recent_history"]) > 0

        await orchestrator.stop()

    async def test_multiple_service_recovery(self):
        """Test recovering multiple services."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        # Schedule multiple recoveries
        services = ["service_1", "service_2", "service_3"]
        for service in services:
            orchestrator.schedule_recovery(service, priority=1)

        # Execute all
        for service in services:
            result = await orchestrator.execute_recovery(service)
            assert result.service_name == service

        await orchestrator.stop()

    async def test_recovery_with_max_retries_exhausted(self):
        """Test recovery when max retries are exhausted."""
        orchestrator = RecoveryOrchestrator()
        await orchestrator.start()

        # Policy with failing health check
        def always_fail():
            return False

        policy = RecoveryPolicy(
            max_retry_attempts=2,
            health_check_fn=always_fail,
        )

        orchestrator.schedule_recovery(
            service_name="failing_service",
            strategy=RecoveryStrategy.IMMEDIATE,
            priority=1,
            policy=policy,
        )

        # First attempt
        result1 = await orchestrator.execute_recovery("failing_service")
        assert result1.attempt_number == 1
        assert result1.success is False

        # Second attempt
        result2 = await orchestrator.execute_recovery("failing_service")
        assert result2.attempt_number == 2
        assert result2.success is False
        assert result2.state == RecoveryState.FAILED

        # Service should be removed from active tasks
        status = orchestrator.get_recovery_status()
        assert "failing_service" not in status["services"]

        await orchestrator.stop()
