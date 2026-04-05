"""
ACGS-2 Enhanced Agent Bus - Chaos Engineering Framework Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the chaos engineering framework including:
- Steady state validation
- Failure scenarios (network partition, latency, memory, CPU, dependency)
- Experiment lifecycle
- Rollback procedures
- Constitutional compliance

Test Markers:
    @pytest.mark.chaos - All chaos engineering tests
    @pytest.mark.constitutional - Constitutional compliance tests
"""

import asyncio
import time
from datetime import UTC, datetime, timezone

import pytest

# Import test dependencies — skip entire module if chaos imports are unavailable
try:
    try:
        from enhanced_agent_bus.chaos import (
            CONSTITUTIONAL_HASH,
            ChaosExperiment,
            CPUStressScenario,
            DependencyFailureScenario,
            ExperimentPhase,
            ExperimentResult,
            ExperimentStatus,
            LatencyInjectionScenario,
            MemoryPressureScenario,
            NetworkPartitionScenario,
            ScenarioExecutor,
            ScenarioStatus,
            SteadyStateHypothesis,
            SteadyStateValidator,
            ValidationMetric,
            ValidationResult,
            chaos_experiment,
            get_experiment_registry,
            reset_experiment_registry,
        )
        from enhanced_agent_bus.chaos.scenarios import (
            DependencyType,
            PartitionType,
        )
        from enhanced_agent_bus.chaos.steady_state import (
            InMemoryMetricCollector,
            MetricCollector,
            MetricOperator,
        )
        from enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError
    except ImportError:
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from chaos import (
            CONSTITUTIONAL_HASH,
            ChaosExperiment,
            CPUStressScenario,
            DependencyFailureScenario,
            ExperimentPhase,
            ExperimentResult,
            ExperimentStatus,
            LatencyInjectionScenario,
            MemoryPressureScenario,
            NetworkPartitionScenario,
            ScenarioExecutor,
            ScenarioStatus,
            SteadyStateHypothesis,
            SteadyStateValidator,
            ValidationMetric,
            ValidationResult,
            chaos_experiment,
            get_experiment_registry,
            reset_experiment_registry,
        )
        from chaos.scenarios import DependencyType, PartitionType
        from chaos.steady_state import InMemoryMetricCollector, MetricCollector, MetricOperator
        from exceptions import ConstitutionalHashMismatchError
except (ImportError, Exception) as _chaos_import_error:
    pytest.skip(
        f"Skipping chaos engineering tests: required modules unavailable ({_chaos_import_error})",
        allow_module_level=True,
    )


# =============================================================================
# Steady State Validation Tests
# =============================================================================


class TestValidationMetric:
    """Test ValidationMetric class."""

    def test_create_validation_metric(self):
        """Test creating a validation metric."""
        metric = ValidationMetric(
            name="latency_p99_ms",
            operator=MetricOperator.LESS_EQUAL,
            threshold=5.0,
            description="P99 latency should be under 5ms",
            unit="ms",
        )

        assert metric.name == "latency_p99_ms"
        assert metric.operator == MetricOperator.LESS_EQUAL
        assert metric.threshold == 5.0
        assert metric.description == "P99 latency should be under 5ms"

    @pytest.mark.parametrize(
        "operator,value,threshold,expected",
        [
            (MetricOperator.LESS_THAN, 4.0, 5.0, True),
            (MetricOperator.LESS_THAN, 5.0, 5.0, False),
            (MetricOperator.LESS_EQUAL, 5.0, 5.0, True),
            (MetricOperator.GREATER_THAN, 6.0, 5.0, True),
            (MetricOperator.GREATER_EQUAL, 5.0, 5.0, True),
            (MetricOperator.EQUAL, 5.0, 5.0, True),
            (MetricOperator.NOT_EQUAL, 4.0, 5.0, True),
        ],
    )
    def test_metric_validation(self, operator, value, threshold, expected):
        """Test metric validation with various operators."""
        metric = ValidationMetric(name="test", operator=operator, threshold=threshold)
        assert metric.validate(value) == expected

    def test_metric_between_operator(self):
        """Test BETWEEN operator."""
        metric = ValidationMetric(
            name="test",
            operator=MetricOperator.BETWEEN,
            threshold=10.0,
            threshold_max=20.0,
        )

        assert metric.validate(15.0) is True
        assert metric.validate(10.0) is True
        assert metric.validate(20.0) is True
        assert metric.validate(5.0) is False
        assert metric.validate(25.0) is False

    def test_metric_to_dict(self):
        """Test metric serialization."""
        metric = ValidationMetric(
            name="latency",
            operator=MetricOperator.LESS_EQUAL,
            threshold=5.0,
        )

        result = metric.to_dict()
        assert result["name"] == "latency"
        assert result["operator"] == "<="
        assert result["threshold"] == 5.0


class TestInMemoryMetricCollector:
    """Test InMemoryMetricCollector class."""

    @pytest.fixture
    def collector(self):
        """Create a fresh collector."""
        return InMemoryMetricCollector()

    async def test_record_and_collect(self, collector):
        """Test recording and collecting metrics."""
        collector.record("latency", 5.0)
        collector.record("latency", 6.0)
        collector.record("latency", 7.0)

        result = await collector.collect("latency")
        assert result == 7.0  # Latest value

    def test_get_average(self, collector):
        """Test getting average value."""
        for i in range(10):
            collector.record("metric", float(i))

        avg = collector.get_average("metric")
        assert avg == 4.5  # Average of 0-9

    def test_get_percentile(self, collector):
        """Test getting percentile value."""
        for i in range(100):
            collector.record("metric", float(i))

        p99 = collector.get_percentile("metric", 99)
        assert p99 >= 98

    def test_available_metrics(self, collector):
        """Test getting available metrics."""
        collector.record("metric1", 1.0)
        collector.record("metric2", 2.0)

        metrics = collector.get_available_metrics()
        assert "metric1" in metrics
        assert "metric2" in metrics

    def test_clear(self, collector):
        """Test clearing metrics."""
        collector.record("metric", 1.0)
        collector.clear()

        assert len(collector.get_available_metrics()) == 0


class TestSteadyStateValidator:
    """Test SteadyStateValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a fresh validator."""
        return SteadyStateValidator(
            name="test_validator",
            metrics={
                "latency_ms": ("<=", 5.0),
                "error_rate": ("<=", 0.01),
                "throughput": (">=", 100.0),
            },
        )

    def test_create_validator(self, validator):
        """Test creating a validator."""
        assert validator.name == "test_validator"
        assert validator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_invalid_constitutional_hash(self):
        """Test rejection of invalid constitutional hash."""
        with pytest.raises(ConstitutionalHashMismatchError):
            SteadyStateValidator(
                name="test",
                constitutional_hash="invalid_hash",
            )

    async def test_validate_passing(self, validator):
        """Test validation when metrics pass."""
        validator.record_metric("latency_ms", 3.0)
        validator.record_metric("error_rate", 0.005)
        validator.record_metric("throughput", 150.0)

        results = await validator.validate()
        assert all(r.valid for r in results)
        assert validator.is_valid()

    async def test_validate_failing(self, validator):
        """Test validation when metrics fail."""
        validator.record_metric("latency_ms", 10.0)  # Exceeds threshold
        validator.record_metric("error_rate", 0.005)
        validator.record_metric("throughput", 150.0)

        results = await validator.validate(consecutive_failures_allowed=0)
        violations = [r for r in results if not r.valid]
        assert len(violations) > 0
        assert not validator.is_valid()

    async def test_consecutive_failures_tolerance(self, validator):
        """Test tolerance for consecutive failures."""
        validator.record_metric("latency_ms", 10.0)  # Exceeds threshold
        validator.record_metric("error_rate", 0.005)
        validator.record_metric("throughput", 150.0)

        # First failure should be tolerated
        results = await validator.validate(consecutive_failures_allowed=2)
        # With tolerance, initial failures are forgiven
        assert validator.is_valid()

    def test_get_summary(self, validator):
        """Test getting validation summary."""
        summary = validator.get_summary()

        assert summary["name"] == "test_validator"
        assert "metrics" in summary
        assert summary["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_hypothesis(self, validator):
        """Test converting to hypothesis."""
        hypothesis = validator.to_hypothesis()

        assert isinstance(hypothesis, SteadyStateHypothesis)
        assert hypothesis.name == validator.name
        assert len(hypothesis.metrics) == 3


# =============================================================================
# Scenario Tests
# =============================================================================


class TestNetworkPartitionScenario:
    """Test NetworkPartitionScenario class."""

    def test_create_scenario(self):
        """Test creating a network partition scenario."""
        scenario = NetworkPartitionScenario(
            target_service="redis",
            duration_s=10.0,
            partition_type=PartitionType.FULL,
        )

        assert scenario.target_service == "redis"
        assert scenario.partition_type == PartitionType.FULL
        assert scenario.duration_s == 10.0
        assert scenario.status == ScenarioStatus.PENDING

    def test_invalid_constitutional_hash(self):
        """Test rejection of invalid constitutional hash."""
        with pytest.raises(ConstitutionalHashMismatchError):
            NetworkPartitionScenario(
                target_service="redis",
                constitutional_hash="invalid",
            )

    async def test_execute_scenario(self):
        """Test executing a network partition scenario."""
        scenario = NetworkPartitionScenario(
            target_service="redis",
            duration_s=0.5,  # Short duration for testing
            partition_type=PartitionType.FULL,
        )

        result = await scenario.execute()

        assert result.status in (ScenarioStatus.COMPLETED, ScenarioStatus.CANCELLED)
        assert result.scenario_name == scenario.name
        assert len(result.events) > 0

    def test_partition_check_full(self):
        """Test partition check for full partition."""
        scenario = NetworkPartitionScenario(
            target_service="redis",
            partition_type=PartitionType.FULL,
        )
        scenario._partitioned = True

        # Should block communication with redis
        assert scenario.is_partitioned("app", "redis") is True
        assert scenario.is_partitioned("redis", "app") is True

        # Other services should work
        assert scenario.is_partitioned("app", "other") is False

    def test_partition_check_one_way(self):
        """Test partition check for one-way partition."""
        scenario = NetworkPartitionScenario(
            target_service="redis",
            partition_type=PartitionType.ONE_WAY,
        )
        scenario._partitioned = True

        # Should block requests TO redis
        assert scenario.is_partitioned("app", "redis") is True
        # Should allow requests FROM redis
        assert scenario.is_partitioned("redis", "app") is False

    async def test_rollback(self):
        """Test scenario rollback."""
        scenario = NetworkPartitionScenario(
            target_service="redis",
            duration_s=10.0,
        )
        scenario._partitioned = True

        await scenario.rollback()

        assert scenario._partitioned is False


class TestLatencyInjectionScenario:
    """Test LatencyInjectionScenario class."""

    def test_create_scenario(self):
        """Test creating a latency injection scenario."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=100,
            duration_s=10.0,
        )

        assert scenario.target_service == "api"
        assert scenario.latency_ms == 100
        assert scenario.duration_s == 10.0

    def test_max_latency_enforcement(self):
        """Test max latency limit enforcement."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=10000,  # Exceeds max
            duration_s=10.0,
        )

        assert scenario.latency_ms == 5000  # Capped to max

    def test_get_latency_active(self):
        """Test getting latency when active."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=100,
        )
        scenario._active = True

        latency = scenario.get_latency()
        assert latency == 100

    def test_get_latency_inactive(self):
        """Test getting latency when inactive."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=100,
        )

        latency = scenario.get_latency()
        assert latency == 0

    async def test_execute_scenario(self):
        """Test executing a latency injection scenario."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=50,
            duration_s=0.5,
        )

        result = await scenario.execute()

        assert result.status == ScenarioStatus.COMPLETED
        assert scenario._active is False


class TestMemoryPressureScenario:
    """Test MemoryPressureScenario class."""

    def test_create_scenario(self):
        """Test creating a memory pressure scenario."""
        scenario = MemoryPressureScenario(
            target_percent=70.0,
            duration_s=10.0,
            ramp_up_s=2.0,
        )

        assert scenario.target_percent == 70.0
        assert scenario.ramp_up_s == 2.0

    def test_max_pressure_enforcement(self):
        """Test max pressure limit enforcement."""
        scenario = MemoryPressureScenario(
            target_percent=95.0,  # Exceeds max
            duration_s=10.0,
        )

        assert scenario.target_percent == 80.0  # Capped to max

    async def test_execute_scenario(self):
        """Test executing a memory pressure scenario."""
        scenario = MemoryPressureScenario(
            target_percent=50.0,
            duration_s=0.5,
            ramp_up_s=0.2,
        )

        result = await scenario.execute()

        assert result.status == ScenarioStatus.COMPLETED
        assert "peak_pressure_percent" in result.metrics


class TestCPUStressScenario:
    """Test CPUStressScenario class."""

    def test_create_scenario(self):
        """Test creating a CPU stress scenario."""
        scenario = CPUStressScenario(
            target_percent=80.0,
            duration_s=10.0,
            cores_affected=2,
        )

        assert scenario.target_percent == 80.0
        assert scenario.cores_affected == 2

    def test_max_cpu_enforcement(self):
        """Test max CPU limit enforcement."""
        scenario = CPUStressScenario(
            target_percent=100.0,  # Exceeds max
            duration_s=10.0,
        )

        assert scenario.target_percent == 90.0  # Capped to max

    async def test_execute_scenario(self):
        """Test executing a CPU stress scenario."""
        scenario = CPUStressScenario(
            target_percent=50.0,
            duration_s=0.5,
        )

        result = await scenario.execute()

        assert result.status == ScenarioStatus.COMPLETED


class TestDependencyFailureScenario:
    """Test DependencyFailureScenario class."""

    def test_create_scenario(self):
        """Test creating a dependency failure scenario."""
        scenario = DependencyFailureScenario(
            dependency=DependencyType.REDIS,
            failure_mode="complete",
            duration_s=10.0,
        )

        assert scenario.dependency == DependencyType.REDIS
        assert scenario.failure_mode == "complete"

    def test_should_fail_complete(self):
        """Test should_fail for complete failure mode."""
        scenario = DependencyFailureScenario(
            dependency=DependencyType.REDIS,
            failure_mode="complete",
        )
        scenario._active = True

        assert scenario.should_fail() is True

    def test_should_fail_inactive(self):
        """Test should_fail when inactive."""
        scenario = DependencyFailureScenario(
            dependency=DependencyType.REDIS,
            failure_mode="complete",
        )

        assert scenario.should_fail() is False

    def test_get_failure_error(self):
        """Test getting failure error."""
        scenario = DependencyFailureScenario(
            dependency=DependencyType.REDIS,
            error_message="Connection refused",
        )

        error = scenario.get_failure_error()
        assert isinstance(error, ConnectionError)
        assert "redis" in str(error).lower()

    async def test_execute_scenario(self):
        """Test executing a dependency failure scenario."""
        scenario = DependencyFailureScenario(
            dependency=DependencyType.OPA,
            failure_mode="intermittent",
            duration_s=0.5,
        )

        result = await scenario.execute()

        assert result.status == ScenarioStatus.COMPLETED
        assert "total_calls" in result.metrics


class TestScenarioExecutor:
    """Test ScenarioExecutor class."""

    @pytest.fixture
    def executor(self):
        """Create a fresh executor."""
        return ScenarioExecutor()

    async def test_execute_scenario(self, executor):
        """Test executing a scenario through executor."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=50,
            duration_s=0.3,
        )

        result = await executor.execute(scenario)

        assert result.status == ScenarioStatus.COMPLETED
        assert len(executor.get_results()) == 1

    async def test_rollback_all(self, executor):
        """Test rolling back all scenarios."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=50,
            duration_s=10.0,
        )
        scenario._active = True

        # Manually add to active scenarios
        executor._active_scenarios[scenario.name] = scenario

        await executor.rollback_all()

        assert scenario._active is False

    def test_cancel_all(self, executor):
        """Test cancelling all scenarios."""
        scenario = LatencyInjectionScenario(
            target_service="api",
            latency_ms=50,
            duration_s=10.0,
        )

        executor._active_scenarios[scenario.name] = scenario

        executor.cancel_all()

        assert scenario.status == ScenarioStatus.CANCELLED


# =============================================================================
# Experiment Tests
# =============================================================================


@pytest.mark.chaos
class TestChaosExperiment:
    """Test ChaosExperiment class."""

    @pytest.fixture
    def validator(self):
        """Create a steady state validator."""
        validator = SteadyStateValidator(
            name="test_steady_state",
            metrics={
                "latency_ms": ("<=", 10.0),
                "error_rate": ("<=", 0.1),
            },
        )
        # Pre-populate with good metrics
        validator.record_metric("latency_ms", 5.0)
        validator.record_metric("error_rate", 0.01)
        return validator

    @pytest.fixture
    def scenario(self):
        """Create a chaos scenario."""
        return LatencyInjectionScenario(
            target_service="api",
            latency_ms=50,
            duration_s=0.5,
        )

    def test_create_experiment(self, validator, scenario):
        """Test creating a chaos experiment."""
        experiment = ChaosExperiment(
            name="test_experiment",
            hypothesis="System handles latency gracefully",
            steady_state=validator,
            scenario=scenario,
        )

        assert experiment.name == "test_experiment"
        assert experiment.phase == ExperimentPhase.INITIALIZED
        assert experiment.status == ExperimentStatus.PENDING

    def test_invalid_constitutional_hash(self, validator, scenario):
        """Test rejection of invalid constitutional hash."""
        with pytest.raises(ConstitutionalHashMismatchError):
            ChaosExperiment(
                name="test",
                hypothesis="test",
                steady_state=validator,
                scenario=scenario,
                constitutional_hash="invalid",
            )

    async def test_run_experiment(self, validator, scenario):
        """Test running a complete experiment."""
        experiment = ChaosExperiment(
            name="test_experiment",
            hypothesis="System handles latency gracefully",
            steady_state=validator,
            scenario=scenario,
            baseline_check_duration_s=0.2,
            recovery_check_duration_s=0.2,
            validation_interval_s=0.1,
        )

        result = await experiment.run()

        assert result.status in (
            ExperimentStatus.PASSED,
            ExperimentStatus.FAILED,
        )
        assert result.phase == ExperimentPhase.COMPLETED
        assert len(result.observations) > 0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_experiment_abort(self, validator, scenario):
        """Test aborting an experiment."""
        experiment = ChaosExperiment(
            name="test_experiment",
            hypothesis="Test abort",
            steady_state=validator,
            scenario=scenario,
            baseline_check_duration_s=5.0,  # Long baseline
        )

        # Start experiment and abort after short delay
        run_task = asyncio.create_task(experiment.run())
        await asyncio.sleep(0.1)
        experiment.abort()

        result = await run_task

        assert result.status == ExperimentStatus.ABORTED

    def test_experiment_to_dict(self, validator, scenario):
        """Test experiment serialization."""
        experiment = ChaosExperiment(
            name="test_experiment",
            hypothesis="Test hypothesis",
            steady_state=validator,
            scenario=scenario,
        )

        result = experiment.to_dict()

        assert result["name"] == "test_experiment"
        assert result["hypothesis"] == "Test hypothesis"
        assert "scenario" in result
        assert "steady_state" in result


@pytest.mark.chaos
class TestExperimentRegistry:
    """Test experiment registry functions."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_experiment_registry()

    def test_get_empty_registry(self):
        """Test getting empty registry."""
        registry = get_experiment_registry()
        assert len(registry) == 0

    def test_reset_registry(self):
        """Test resetting registry."""
        # Add something to registry
        from enhanced_agent_bus.chaos.experiments import register_experiment

        validator = SteadyStateValidator(name="test")
        scenario = LatencyInjectionScenario(target_service="api", latency_ms=50)
        experiment = ChaosExperiment(
            name="test",
            hypothesis="test",
            steady_state=validator,
            scenario=scenario,
        )
        register_experiment(experiment)

        # Reset
        reset_experiment_registry()

        registry = get_experiment_registry()
        assert len(registry) == 0


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


@pytest.mark.constitutional
@pytest.mark.chaos
class TestConstitutionalCompliance:
    """Test constitutional compliance in chaos framework."""

    def test_scenario_includes_hash(self):
        """Test all scenarios include constitutional hash."""
        scenarios = [
            NetworkPartitionScenario(target_service="redis"),
            LatencyInjectionScenario(target_service="api", latency_ms=50),
            MemoryPressureScenario(target_percent=50.0),
            CPUStressScenario(target_percent=50.0),
            DependencyFailureScenario(dependency=DependencyType.REDIS),
        ]

        for scenario in scenarios:
            assert scenario.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_includes_hash(self):
        """Test scenario results include constitutional hash."""
        result = ExperimentResult(
            experiment_name="test",
            hypothesis="test",
            status=ExperimentStatus.PASSED,
            phase=ExperimentPhase.COMPLETED,
            started_at=datetime.now(UTC),
        )

        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_validator_includes_hash(self):
        """Test steady state validator includes constitutional hash."""
        validator = SteadyStateValidator(name="test")
        assert validator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_experiment_includes_hash(self):
        """Test chaos experiment includes constitutional hash."""
        validator = SteadyStateValidator(name="test")
        scenario = LatencyInjectionScenario(target_service="api", latency_ms=50)
        experiment = ChaosExperiment(
            name="test",
            hypothesis="test",
            steady_state=validator,
            scenario=scenario,
        )

        assert experiment.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.chaos
async def test_full_chaos_experiment_lifecycle():
    """Test a complete chaos experiment lifecycle."""
    # Create steady state validator
    validator = SteadyStateValidator(
        name="integration_test_steady_state",
        metrics={
            "latency_ms": ("<=", 10.0),
            "success_rate": (">=", 0.95),
        },
    )

    # Simulate good metrics
    validator.record_metric("latency_ms", 5.0)
    validator.record_metric("success_rate", 0.99)

    # Create scenario
    scenario = DependencyFailureScenario(
        dependency=DependencyType.REDIS,
        failure_mode="intermittent",
        duration_s=0.5,
        intermittent_rate=0.3,
    )

    # Create and run experiment
    experiment = ChaosExperiment(
        name="redis_intermittent_failure_test",
        hypothesis="System handles intermittent Redis failures",
        steady_state=validator,
        scenario=scenario,
        baseline_check_duration_s=0.2,
        recovery_check_duration_s=0.2,
        validation_interval_s=0.1,
    )

    result = await experiment.run()

    # Verify experiment completed
    assert result.phase == ExperimentPhase.COMPLETED
    assert result.experiment_name == "redis_intermittent_failure_test"
    assert len(result.scenario_results) >= 1
    assert result.constitutional_hash == CONSTITUTIONAL_HASH


@pytest.mark.chaos
async def test_multiple_concurrent_scenarios():
    """Test running multiple scenarios concurrently."""
    executor = ScenarioExecutor()

    scenarios = [
        LatencyInjectionScenario(target_service="api", latency_ms=50, duration_s=0.3),
        DependencyFailureScenario(
            dependency=DependencyType.REDIS,
            failure_mode="intermittent",
            duration_s=0.3,
        ),
    ]

    # Execute scenarios concurrently
    tasks = [executor.execute(s) for s in scenarios]
    results = await asyncio.gather(*tasks)

    assert len(results) == 2
    assert all(r.status == ScenarioStatus.COMPLETED for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "chaos"])
