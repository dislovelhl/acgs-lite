"""
ACGS-2 Enhanced Agent Bus - Chaos Framework Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the chaos testing framework including:
- Latency injection and measurement
- Error rate injection accuracy
- Automatic cleanup after chaos
- Constitutional compliance during chaos
- Safety controls validation
"""

import asyncio
import time

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# Import chaos testing framework
try:
    from enhanced_agent_bus.chaos_testing import (
        CONSTITUTIONAL_HASH,
        ChaosEngine,
        ChaosScenario,
        ChaosType,
        ResourceType,
        chaos_test,
        get_chaos_engine,
        reset_chaos_engine,
    )
    from enhanced_agent_bus.exceptions import (
        AgentBusError,
        ConstitutionalHashMismatchError,
    )
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from chaos_testing import (
        CONSTITUTIONAL_HASH,
        ChaosEngine,
        ChaosScenario,
        ChaosType,
        ResourceType,
        chaos_test,
        get_chaos_engine,
        reset_chaos_engine,
    )
    from exceptions import AgentBusError, ConstitutionalHashMismatchError


class TestChaosScenario:
    """Test ChaosScenario configuration and validation."""

    def test_create_latency_scenario(self):
        """Test creating a latency chaos scenario."""
        scenario = ChaosScenario(
            name="test_latency",
            chaos_type=ChaosType.LATENCY,
            target="message_processor",
            delay_ms=100,
            duration_s=5.0,
        )

        assert scenario.name == "test_latency"
        assert scenario.chaos_type == ChaosType.LATENCY
        assert scenario.target == "message_processor"
        assert scenario.delay_ms == 100
        assert scenario.duration_s == 5.0
        assert scenario.constitutional_hash == CONSTITUTIONAL_HASH
        assert not scenario.active

    def test_create_error_scenario(self):
        """Test creating an error injection scenario."""
        scenario = ChaosScenario(
            name="test_errors",
            chaos_type=ChaosType.ERROR,
            target="agent_bus",
            error_rate=0.5,
            error_type=ValueError,
            duration_s=10.0,
        )

        assert scenario.chaos_type == ChaosType.ERROR
        assert scenario.error_rate == 0.5
        assert scenario.error_type is ValueError
        assert scenario.duration_s == 10.0

    def test_create_circuit_breaker_scenario(self):
        """Test creating a circuit breaker scenario."""
        scenario = ChaosScenario(
            name="test_circuit",
            chaos_type=ChaosType.CIRCUIT_BREAKER,
            target="policy_service",
            duration_s=15.0,
        )

        assert scenario.chaos_type == ChaosType.CIRCUIT_BREAKER
        assert scenario.target == "policy_service"
        assert scenario.duration_s == 15.0

    def test_create_resource_exhaustion_scenario(self):
        """Test creating a resource exhaustion scenario."""
        scenario = ChaosScenario(
            name="test_resource",
            chaos_type=ChaosType.RESOURCE_EXHAUSTION,
            target="system",
            resource_type=ResourceType.CPU,
            resource_level=0.8,
            duration_s=20.0,
        )

        assert scenario.chaos_type == ChaosType.RESOURCE_EXHAUSTION
        assert scenario.resource_type == ResourceType.CPU
        assert scenario.resource_level == 0.8

    def test_constitutional_hash_validation(self):
        """Test constitutional hash validation in scenario."""
        with pytest.raises(ConstitutionalHashMismatchError) as exc_info:
            ChaosScenario(
                name="invalid_hash",
                chaos_type=ChaosType.LATENCY,
                target="test",
                constitutional_hash="invalid_hash",
                require_hash_validation=True,
            )

        # Error message shows sanitized hash prefix for security
        assert "608508a9..." in str(exc_info.value)
        # Full hash still available via property for internal use
        assert exc_info.value.expected_hash == CONSTITUTIONAL_HASH

    def test_max_duration_enforcement(self):
        """Test max duration limit enforcement."""
        scenario = ChaosScenario(
            name="long_duration",
            chaos_type=ChaosType.LATENCY,
            target="test",
            duration_s=500.0,  # Exceeds max of 300s
        )

        # Should be capped to max_duration_s
        assert scenario.duration_s == 300.0

    def test_error_rate_validation(self):
        """Test error rate must be between 0.0 and 1.0."""
        with pytest.raises(ValueError) as exc_info:
            ChaosScenario(
                name="invalid_rate",
                chaos_type=ChaosType.ERROR,
                target="test",
                error_rate=1.5,  # Invalid
            )

        assert "error_rate must be between 0.0 and 1.0" in str(exc_info.value)

    def test_resource_level_validation(self):
        """Test resource level must be between 0.0 and 1.0."""
        with pytest.raises(ValueError) as exc_info:
            ChaosScenario(
                name="invalid_level",
                chaos_type=ChaosType.RESOURCE_EXHAUSTION,
                target="test",
                resource_level=2.0,  # Invalid
            )

        assert "resource_level must be between 0.0 and 1.0" in str(exc_info.value)

    def test_blast_radius_auto_add_target(self):
        """Test target is automatically added to blast radius."""
        scenario = ChaosScenario(
            name="test",
            chaos_type=ChaosType.LATENCY,
            target="message_processor",
        )

        assert "message_processor" in scenario.blast_radius
        assert scenario.is_target_allowed("message_processor")

    def test_blast_radius_custom(self):
        """Test custom blast radius configuration."""
        allowed_targets = {"service1", "service2", "service3"}
        scenario = ChaosScenario(
            name="test",
            chaos_type=ChaosType.LATENCY,
            target="service1",
            blast_radius=allowed_targets,
        )

        assert scenario.is_target_allowed("service1")
        assert scenario.is_target_allowed("service2")
        assert not scenario.is_target_allowed("service4")

    def test_scenario_to_dict(self):
        """Test scenario serialization to dictionary."""
        scenario = ChaosScenario(
            name="test_scenario",
            chaos_type=ChaosType.LATENCY,
            target="test_target",
            delay_ms=50,
            duration_s=5.0,
        )

        scenario_dict = scenario.to_dict()

        assert scenario_dict["name"] == "test_scenario"
        assert scenario_dict["chaos_type"] == "latency"
        assert scenario_dict["target"] == "test_target"
        assert scenario_dict["delay_ms"] == 50
        assert scenario_dict["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "created_at" in scenario_dict


class TestChaosEngine:
    """Test ChaosEngine core functionality."""

    @pytest.fixture
    def engine(self):
        """Create a fresh chaos engine for each test."""
        reset_chaos_engine()
        engine = ChaosEngine()
        yield engine
        engine.reset()

    def test_engine_initialization(self, engine):
        """Test chaos engine initialization with constitutional validation."""
        assert engine.constitutional_hash == CONSTITUTIONAL_HASH
        assert not engine.is_stopped()
        assert len(engine.get_active_scenarios()) == 0

    def test_engine_invalid_hash(self):
        """Test chaos engine rejects invalid constitutional hash."""
        with pytest.raises(ConstitutionalHashMismatchError):
            ChaosEngine(constitutional_hash="invalid_hash")

    def test_emergency_stop(self, engine):
        """Test emergency stop functionality."""
        engine.emergency_stop()

        assert engine.is_stopped()
        assert len(engine.get_active_scenarios()) == 0

    def test_reset_after_emergency_stop(self, engine):
        """Test resetting engine after emergency stop."""
        engine.emergency_stop()
        assert engine.is_stopped()

        engine.reset()
        assert not engine.is_stopped()

    def test_get_metrics(self, engine):
        """Test metrics collection."""
        metrics = engine.get_metrics()

        assert "total_scenarios_run" in metrics
        assert "total_latency_injected_ms" in metrics
        assert "total_errors_injected" in metrics
        assert "active_scenarios" in metrics
        assert "constitutional_hash" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_inject_latency(self, engine):
        """Test latency injection."""
        scenario = await engine.inject_latency(
            target="test_service",
            delay_ms=100,
            duration_s=1.0,
        )

        assert scenario.active
        assert scenario.chaos_type == ChaosType.LATENCY
        assert scenario.delay_ms == 100

        active_scenarios = engine.get_active_scenarios()
        assert len(active_scenarios) == 1
        assert active_scenarios[0].name == scenario.name

    async def test_inject_errors(self, engine):
        """Test error injection."""
        scenario = await engine.inject_errors(
            target="test_service",
            error_rate=0.5,
            error_type=RuntimeError,
            duration_s=1.0,
        )

        assert scenario.active
        assert scenario.chaos_type == ChaosType.ERROR
        assert scenario.error_rate == 0.5
        assert scenario.error_type is RuntimeError

    async def test_force_circuit_open(self, engine):
        """Test forcing circuit breaker open."""
        scenario = await engine.force_circuit_open(
            breaker_name="test_breaker",
            duration_s=1.0,
        )

        assert scenario.active
        assert scenario.chaos_type == ChaosType.CIRCUIT_BREAKER
        assert scenario.target == "test_breaker"

    async def test_simulate_resource_exhaustion(self, engine):
        """Test resource exhaustion simulation."""
        scenario = await engine.simulate_resource_exhaustion(
            resource_type=ResourceType.MEMORY,
            level=0.8,
            duration_s=1.0,
        )

        assert scenario.active
        assert scenario.chaos_type == ChaosType.RESOURCE_EXHAUSTION
        assert scenario.resource_type == ResourceType.MEMORY
        assert scenario.resource_level == 0.8

    async def test_automatic_cleanup(self, engine):
        """Test automatic cleanup after scenario duration."""
        # Short duration for fast test
        scenario = await engine.inject_latency(
            target="test_service",
            delay_ms=50,
            duration_s=0.5,  # 500ms
        )

        # Scenario should be active
        assert scenario.active
        assert len(engine.get_active_scenarios()) == 1

        # Wait for auto-cleanup (with buffer)
        await asyncio.sleep(0.7)

        # Scenario should be cleaned up
        assert len(engine.get_active_scenarios()) == 0

    async def test_manual_deactivation(self, engine):
        """Test manual scenario deactivation."""
        scenario = await engine.inject_latency(
            target="test_service",
            delay_ms=100,
            duration_s=10.0,
        )

        assert scenario.active
        assert len(engine.get_active_scenarios()) == 1

        # Manually deactivate
        await engine.deactivate_scenario(scenario.name)

        assert len(engine.get_active_scenarios()) == 0

    async def test_emergency_stop_prevents_activation(self, engine):
        """Test emergency stop prevents new scenario activation."""
        engine.emergency_stop()

        with pytest.raises(AgentBusError) as exc_info:
            await engine.inject_latency(
                target="test_service",
                delay_ms=100,
                duration_s=1.0,
            )

        assert "emergency stop is active" in str(exc_info.value)

    async def test_chaos_context_manager(self, engine):
        """Test chaos context manager for automatic cleanup."""
        scenario = ChaosScenario(
            name="context_test",
            chaos_type=ChaosType.LATENCY,
            target="test_service",
            delay_ms=50,
            duration_s=10.0,
        )

        # Before context
        assert len(engine.get_active_scenarios()) == 0

        async with engine.chaos_context(scenario):
            # Inside context - should be active
            assert len(engine.get_active_scenarios()) == 1
            active = engine.get_active_scenarios()[0]
            assert active.name == "context_test"
            assert active.active

        # After context - should be cleaned up
        assert len(engine.get_active_scenarios()) == 0


class TestLatencyInjection:
    """Test latency injection and measurement."""

    @pytest.fixture
    def engine(self):
        """Create a fresh chaos engine for each test."""
        reset_chaos_engine()
        engine = ChaosEngine()
        yield engine
        engine.reset()

    async def test_latency_injection_accuracy(self, engine):
        """Test latency injection adds correct delay."""
        delay_ms = 100
        scenario = await engine.inject_latency(
            target="test_target",
            delay_ms=delay_ms,
            duration_s=2.0,
        )

        # Measure actual latency
        measurements = []
        for _ in range(5):
            start = time.time()

            # Check if latency should be injected
            injected_delay = engine.should_inject_latency("test_target")
            if injected_delay > 0:
                await asyncio.sleep(injected_delay / 1000.0)

            elapsed_ms = (time.time() - start) * 1000
            measurements.append(elapsed_ms)

        # Average should be close to delay_ms
        avg_latency = sum(measurements) / len(measurements)
        assert abs(avg_latency - delay_ms) < 20, f"Expected ~{delay_ms}ms, got {avg_latency}ms"

        await engine.deactivate_scenario(scenario.name)

    async def test_latency_not_injected_outside_blast_radius(self, engine):
        """Test latency is not injected for targets outside blast radius."""
        scenario = await engine.inject_latency(
            target="allowed_target", delay_ms=100, duration_s=2.0, blast_radius={"allowed_target"}
        )

        # Should inject for allowed target
        assert engine.should_inject_latency("allowed_target") == 100

        # Should NOT inject for other targets
        assert engine.should_inject_latency("other_target") == 0

        await engine.deactivate_scenario(scenario.name)

    async def test_latency_metrics_tracking(self, engine):
        """Test latency injection updates metrics."""
        scenario = await engine.inject_latency(
            target="test_target",
            delay_ms=100,
            duration_s=2.0,
        )

        initial_metrics = engine.get_metrics()
        initial_latency = initial_metrics["total_latency_injected_ms"]

        # Trigger latency injection multiple times
        for _ in range(10):
            engine.should_inject_latency("test_target")

        updated_metrics = engine.get_metrics()
        assert updated_metrics["total_latency_injected_ms"] > initial_latency

        await engine.deactivate_scenario(scenario.name)


class TestErrorInjection:
    """Test error injection and rate accuracy."""

    @pytest.fixture
    def engine(self):
        """Create a fresh chaos engine for each test."""
        reset_chaos_engine()
        engine = ChaosEngine()
        yield engine
        engine.reset()

    async def test_error_injection_rate(self, engine):
        """Test error injection rate accuracy."""
        error_rate = 0.5
        scenario = await engine.inject_errors(
            target="test_target",
            error_rate=error_rate,
            error_type=ValueError,
            duration_s=2.0,
        )

        # Sample error injection many times
        samples = 1000
        errors_injected = 0

        for _ in range(samples):
            if engine.should_inject_error("test_target"):
                errors_injected += 1

        actual_rate = errors_injected / samples

        # Should be close to target rate (within 10%)
        assert abs(actual_rate - error_rate) < 0.1, (
            f"Expected ~{error_rate} error rate, got {actual_rate}"
        )

        await engine.deactivate_scenario(scenario.name)

    async def test_error_type_injection(self, engine):
        """Test correct error type is injected."""
        scenario = await engine.inject_errors(
            target="test_target",
            error_rate=1.0,  # Always inject
            error_type=RuntimeError,
            duration_s=2.0,
        )

        error_type = engine.should_inject_error("test_target")
        assert error_type is RuntimeError

        await engine.deactivate_scenario(scenario.name)

    async def test_error_not_injected_outside_blast_radius(self, engine):
        """Test errors not injected outside blast radius."""
        scenario = await engine.inject_errors(
            target="allowed_target",
            error_rate=1.0,
            error_type=ValueError,
            duration_s=2.0,
            blast_radius={"allowed_target"},
        )

        # Should inject for allowed target
        assert engine.should_inject_error("allowed_target") is ValueError

        # Should NOT inject for other targets
        assert engine.should_inject_error("other_target") is None

        await engine.deactivate_scenario(scenario.name)

    async def test_error_metrics_tracking(self, engine):
        """Test error injection updates metrics."""
        scenario = await engine.inject_errors(
            target="test_target",
            error_rate=1.0,
            error_type=ValueError,
            duration_s=2.0,
        )

        initial_metrics = engine.get_metrics()
        initial_errors = initial_metrics["total_errors_injected"]

        # Trigger error injection multiple times
        for _ in range(10):
            engine.should_inject_error("test_target")

        updated_metrics = engine.get_metrics()
        assert updated_metrics["total_errors_injected"] > initial_errors

        await engine.deactivate_scenario(scenario.name)


class TestConstitutionalCompliance:
    """Test constitutional compliance during chaos."""

    @pytest.fixture
    def engine(self):
        """Create a fresh chaos engine for each test."""
        reset_chaos_engine()
        engine = ChaosEngine()
        yield engine
        engine.reset()

    async def test_constitutional_hash_in_scenario(self, engine):
        """Test all scenarios include constitutional hash."""
        scenario = await engine.inject_latency(
            target="test_target",
            delay_ms=100,
            duration_s=1.0,
        )

        assert scenario.constitutional_hash == CONSTITUTIONAL_HASH

        scenario_dict = scenario.to_dict()
        assert scenario_dict["constitutional_hash"] == CONSTITUTIONAL_HASH

        await engine.deactivate_scenario(scenario.name)

    async def test_constitutional_hash_in_metrics(self, engine):
        """Test metrics include constitutional hash."""
        metrics = engine.get_metrics()
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_chaos_maintains_constitutional_compliance(self, engine):
        """Test chaos injection maintains constitutional compliance."""
        # Inject various chaos types
        scenarios = [
            await engine.inject_latency("target1", 50, 1.0),
            await engine.inject_errors("target2", 0.5, ValueError, 1.0),
            await engine.force_circuit_open("breaker1", 1.0),
        ]

        # All scenarios should have constitutional hash
        for scenario in scenarios:
            assert scenario.constitutional_hash == CONSTITUTIONAL_HASH

        # Engine should maintain constitutional hash
        assert engine.constitutional_hash == CONSTITUTIONAL_HASH

        # Cleanup
        for scenario in scenarios:
            await engine.deactivate_scenario(scenario.name)


class TestChaosTestDecorator:
    """Test the @chaos_test decorator."""

    @chaos_test(scenario_type="latency", target="test_target", delay_ms=50, duration_s=1.0)
    async def test_decorator_latency(self):
        """Test decorator creates latency chaos scenario."""
        engine = get_chaos_engine()

        # Should have active scenario
        active = engine.get_active_scenarios()
        assert len(active) >= 1

        # Latency should be injected
        delay = engine.should_inject_latency("test_target")
        assert delay > 0

    @chaos_test(scenario_type="errors", target="test_target", error_rate=1.0, duration_s=1.0)
    async def test_decorator_errors(self):
        """Test decorator creates error chaos scenario."""
        engine = get_chaos_engine()

        # Should have active scenario
        active = engine.get_active_scenarios()
        assert len(active) >= 1

        # Errors should be injected
        error_type = engine.should_inject_error("test_target")
        assert error_type is not None


class TestSafetyControls:
    """Test safety controls and limits."""

    @pytest.fixture
    def engine(self):
        """Create a fresh chaos engine for each test."""
        reset_chaos_engine()
        engine = ChaosEngine()
        yield engine
        engine.reset()

    async def test_max_duration_limit(self, engine):
        """Test max duration is enforced."""
        scenario = ChaosScenario(
            name="long_test",
            chaos_type=ChaosType.LATENCY,
            target="test",
            duration_s=1000.0,  # Exceeds max
        )

        assert scenario.duration_s <= scenario.max_duration_s

    async def test_emergency_stop_clears_all_scenarios(self, engine):
        """Test emergency stop clears all active scenarios."""
        # Create multiple scenarios
        await engine.inject_latency("target1", 100, 10.0)
        await engine.inject_errors("target2", 0.5, ValueError, 10.0)
        await engine.force_circuit_open("breaker1", 10.0)

        assert len(engine.get_active_scenarios()) == 3

        # Emergency stop should clear all
        engine.emergency_stop()
        assert len(engine.get_active_scenarios()) == 0
        assert engine.is_stopped()

    async def test_blast_radius_enforcement(self, engine):
        """Test blast radius limits chaos injection."""
        blast_radius = {"service1", "service2"}
        scenario = await engine.inject_latency(
            target="service1", delay_ms=100, duration_s=2.0, blast_radius=blast_radius
        )

        # Should inject for allowed targets
        assert engine.should_inject_latency("service1") > 0
        assert engine.should_inject_latency("service2") > 0

        # Should NOT inject for disallowed targets
        assert engine.should_inject_latency("service3") == 0

        await engine.deactivate_scenario(scenario.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
