"""
ACGS-2 Enhanced Agent Bus - Chaos Engineering Framework
Constitutional Hash: 608508a9bd224290

This package provides a comprehensive chaos engineering framework for validating
system resilience under failure conditions while maintaining constitutional compliance.

Based on principles from:
- Michael Nygard (Release It!)
- Netflix Chaos Engineering
- Principles of Chaos Engineering (https://principlesofchaos.org)

Components:
- experiments.py: Chaos experiment definitions and lifecycle management
- scenarios.py: Predefined failure scenarios (network partition, latency, etc.)
- steady_state.py: Steady state hypothesis validation

Usage:
    from enhanced_agent_bus.chaos import (
        ChaosExperiment,
        SteadyStateValidator,
        NetworkPartitionScenario,
        LatencyInjectionScenario,
    )

    # Define steady state
    validator = SteadyStateValidator(
        name="message_processing_steady_state",
        metrics={
            "latency_p99_ms": ("<=", 5.0),
            "error_rate": ("<=", 0.01),
            "throughput_rps": (">=", 100),
        },
    )

    # Create experiment
    experiment = ChaosExperiment(
        name="network_partition_test",
        hypothesis="System maintains availability during network partition",
        steady_state=validator,
        scenario=NetworkPartitionScenario(
            target_service="redis",
            duration_s=30.0,
            partition_type="partial",
        ),
    )

    # Run experiment
    async with experiment:
        await run_workload()
        result = experiment.get_result()
"""

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__version__ = "1.0.0"
__constitutional_hash__ = CONSTITUTIONAL_HASH

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .experiments import (
    ChaosExperiment,
    ExperimentPhase,
    ExperimentResult,
    ExperimentStatus,
    chaos_experiment,
    get_experiment_registry,
    reset_experiment_registry,
)
from .scenarios import (
    CPUStressScenario,
    DependencyFailureScenario,
    LatencyInjectionScenario,
    MemoryPressureScenario,
    NetworkPartitionScenario,
    ScenarioExecutor,
    ScenarioStatus,
)
from .steady_state import (
    InMemoryMetricCollector,
    SteadyStateHypothesis,
    SteadyStateValidator,
    ValidationMetric,
    ValidationResult,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "CPUStressScenario",
    # Experiments
    "ChaosExperiment",
    "DependencyFailureScenario",
    "ExperimentPhase",
    "ExperimentResult",
    "ExperimentStatus",
    "InMemoryMetricCollector",
    "LatencyInjectionScenario",
    "MemoryPressureScenario",
    # Scenarios
    "NetworkPartitionScenario",
    "ScenarioExecutor",
    "ScenarioStatus",
    "SteadyStateHypothesis",
    # Steady State
    "SteadyStateValidator",
    "ValidationMetric",
    "ValidationResult",
    "chaos_experiment",
    "get_experiment_registry",
    "reset_experiment_registry",
]
