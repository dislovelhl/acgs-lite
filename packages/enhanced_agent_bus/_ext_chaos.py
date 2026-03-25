"""
Optional Chaos Engineering Framework (T003).
Constitutional Hash: 608508a9bd224290
"""

try:
    from .chaos import CONSTITUTIONAL_HASH as CHAOS_CONSTITUTIONAL_HASH  # noqa: F401
    from .chaos import (
        ChaosExperiment,
        CPUStressScenario,
        DependencyFailureScenario,
        ExperimentPhase,
        ExperimentResult,
        ExperimentStatus,
        InMemoryMetricCollector,
        LatencyInjectionScenario,
        MemoryPressureScenario,
        NetworkPartitionScenario,
        ScenarioExecutor,
        ScenarioStatus,
        SteadyStateHypothesis,
        SteadyStateValidator,
        ValidationMetric,
        chaos_experiment,
        get_experiment_registry,
        reset_experiment_registry,
    )
    from .chaos import ValidationResult as ChaosValidationResult

    CHAOS_ENGINEERING_AVAILABLE = True
except ImportError:
    CHAOS_ENGINEERING_AVAILABLE = False
    ChaosExperiment = object  # type: ignore[assignment, misc]
    CPUStressScenario = object  # type: ignore[assignment, misc]
    DependencyFailureScenario = object  # type: ignore[assignment, misc]
    ExperimentPhase = object  # type: ignore[assignment, misc]
    ExperimentResult = object  # type: ignore[assignment, misc]
    ExperimentStatus = object  # type: ignore[assignment, misc]
    LatencyInjectionScenario = object  # type: ignore[assignment, misc]
    MemoryPressureScenario = object  # type: ignore[assignment, misc]
    InMemoryMetricCollector = object  # type: ignore[assignment, misc]
    NetworkPartitionScenario = object  # type: ignore[assignment, misc]
    ScenarioExecutor = object  # type: ignore[assignment, misc]
    ScenarioStatus = object  # type: ignore[assignment, misc]
    SteadyStateHypothesis = object  # type: ignore[assignment, misc]
    SteadyStateValidator = object  # type: ignore[assignment, misc]
    ValidationMetric = object  # type: ignore[assignment, misc]
    ChaosValidationResult = object  # type: ignore[assignment, misc]
    chaos_experiment = object  # type: ignore[assignment, misc]
    get_experiment_registry = object  # type: ignore[assignment, misc]
    reset_experiment_registry = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "CHAOS_ENGINEERING_AVAILABLE",
    "CHAOS_CONSTITUTIONAL_HASH",
    "ChaosExperiment",
    "CPUStressScenario",
    "DependencyFailureScenario",
    "ExperimentPhase",
    "ExperimentResult",
    "ExperimentStatus",
    "LatencyInjectionScenario",
    "MemoryPressureScenario",
    "InMemoryMetricCollector",
    "NetworkPartitionScenario",
    "ScenarioExecutor",
    "ScenarioStatus",
    "SteadyStateHypothesis",
    "SteadyStateValidator",
    "ValidationMetric",
    "ChaosValidationResult",
    "chaos_experiment",
    "get_experiment_registry",
    "reset_experiment_registry",
]
