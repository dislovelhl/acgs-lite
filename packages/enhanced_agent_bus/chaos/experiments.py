"""
ACGS-2 Enhanced Agent Bus - Chaos Experiments
Constitutional Hash: 608508a9bd224290

Defines chaos experiment lifecycle and execution framework.
Experiments combine scenarios with steady state validation to
verify system resilience under failure conditions.

Principles of Chaos Engineering:
1. Build a hypothesis around steady state behavior
2. Vary real-world events
3. Run experiments in production (safely)
4. Automate experiments to run continuously
5. Minimize blast radius

Expert Reference: Michael Nygard (Release It!)
"""

import asyncio
import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import wraps
from typing import TypeVar

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .scenarios import BaseScenario, ScenarioResult
from .steady_state import SteadyStateValidator, ValidationResult

logger = get_logger(__name__)
CHAOS_ROLLBACK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)
CHAOS_EXPERIMENT_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

F = TypeVar("F", bound=Callable[..., object])


class ExperimentPhase(str, Enum):
    """Phases of a chaos experiment."""

    INITIALIZED = "initialized"
    VALIDATING_BASELINE = "validating_baseline"
    INJECTING_CHAOS = "injecting_chaos"
    VALIDATING_DURING_CHAOS = "validating_during_chaos"
    ROLLING_BACK = "rolling_back"
    VALIDATING_RECOVERY = "validating_recovery"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ExperimentStatus(str, Enum):
    """Status of a chaos experiment."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class ExperimentResult:
    """
    Result of a chaos experiment.

    Constitutional Hash: 608508a9bd224290
    """

    experiment_name: str
    hypothesis: str
    status: ExperimentStatus
    phase: ExperimentPhase
    started_at: datetime
    ended_at: datetime | None = None
    duration_s: float = 0.0

    # Validation results
    baseline_valid: bool = True
    during_chaos_valid: bool = True
    recovery_valid: bool = True
    steady_state_violations: list[ValidationResult] = field(default_factory=list)

    # Scenario results
    scenario_results: list[ScenarioResult] = field(default_factory=list)

    # Observations
    observations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Constitutional compliance
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "experiment_name": self.experiment_name,
            "hypothesis": self.hypothesis,
            "status": self.status.value,
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_s": self.duration_s,
            "baseline_valid": self.baseline_valid,
            "during_chaos_valid": self.during_chaos_valid,
            "recovery_valid": self.recovery_valid,
            "steady_state_violations": [v.to_dict() for v in self.steady_state_violations],
            "scenario_results": [s.to_dict() for s in self.scenario_results],
            "observations": self.observations,
            "errors": self.errors,
            "constitutional_hash": self.constitutional_hash,
        }


class ChaosExperiment:
    """
    A chaos engineering experiment with full lifecycle management.

    Constitutional Hash: 608508a9bd224290

    Lifecycle:
    1. Validate baseline steady state
    2. Inject chaos (execute scenario)
    3. Validate steady state during chaos
    4. Rollback chaos
    5. Validate recovery
    6. Report results

    Usage:
        experiment = ChaosExperiment(
            name="redis_partition_test",
            hypothesis="System handles Redis partition gracefully",
            steady_state=validator,
            scenario=NetworkPartitionScenario("redis", duration_s=30),
        )

        async with experiment:
            await run_workload()
            result = experiment.get_result()
    """

    def __init__(
        self,
        name: str,
        hypothesis: str,
        steady_state: SteadyStateValidator,
        scenario: BaseScenario,
        baseline_check_duration_s: float = 5.0,
        recovery_check_duration_s: float = 10.0,
        validation_interval_s: float = 1.0,
        abort_on_violation: bool = False,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """
        Initialize a chaos experiment.

        Args:
            name: Experiment name
            hypothesis: What we expect to observe
            steady_state: Steady state validator
            scenario: Chaos scenario to execute
            baseline_check_duration_s: How long to validate baseline
            recovery_check_duration_s: How long to validate recovery
            validation_interval_s: How often to validate during chaos
            abort_on_violation: Abort experiment on steady state violation
            constitutional_hash: Constitutional hash for validation
        """
        if constitutional_hash != CONSTITUTIONAL_HASH:
            from enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

            raise ConstitutionalHashMismatchError(
                expected_hash=CONSTITUTIONAL_HASH,
                actual_hash=constitutional_hash,
                context=f"ChaosExperiment '{name}'",
            )

        self.name = name
        self.hypothesis = hypothesis
        self.steady_state = steady_state
        self.scenario = scenario
        self.baseline_check_duration_s = baseline_check_duration_s
        self.recovery_check_duration_s = recovery_check_duration_s
        self.validation_interval_s = validation_interval_s
        self.abort_on_violation = abort_on_violation
        self.constitutional_hash = constitutional_hash

        self._phase = ExperimentPhase.INITIALIZED
        self._status = ExperimentStatus.PENDING
        self._result: ExperimentResult | None = None
        self._started_at: datetime | None = None
        self._aborted = False
        self._validation_task: asyncio.Task | None = None
        self._lock = threading.Lock()

    @property
    def phase(self) -> ExperimentPhase:
        """Get current experiment phase."""
        return self._phase

    @property
    def status(self) -> ExperimentStatus:
        """Get experiment status."""
        return self._status

    @property
    def result(self) -> ExperimentResult | None:
        """Get experiment result."""
        return self._result

    def abort(self) -> None:
        """Abort the experiment."""
        self._aborted = True
        self._status = ExperimentStatus.ABORTED
        self._phase = ExperimentPhase.ABORTED
        self.scenario.cancel()
        logger.warning(f"[{self.constitutional_hash}] Experiment '{self.name}' aborted")

    async def run(self) -> ExperimentResult:
        """
        Run the complete experiment lifecycle.

        Returns:
            ExperimentResult with all observations
        """
        self._started_at = datetime.now(UTC)
        observations: list[str] = []
        errors: list[str] = []
        violations: list[ValidationResult] = []
        scenario_results: list[ScenarioResult] = []

        baseline_valid = True
        during_chaos_valid = True
        recovery_valid = True

        try:
            self._status = ExperimentStatus.RUNNING

            # Phase 1: Validate baseline
            baseline_valid, observations, violations = await self._execute_baseline_validation(
                observations, violations
            )

            # Phase 2-3: Inject chaos and validate during chaos
            if not self._aborted:
                (
                    during_chaos_valid,
                    observations,
                    violations,
                    scenario_results,
                ) = await self._execute_chaos_injection_and_validation(
                    observations, violations, scenario_results
                )

            # Phase 4: Rollback
            if not self._aborted:
                errors = await self._execute_rollback(observations, errors)

            # Phase 5: Validate recovery
            if not self._aborted:
                recovery_valid, observations, violations = await self._execute_recovery_validation(
                    observations, violations
                )

            # Determine final status
            self._determine_final_status(
                baseline_valid, during_chaos_valid, recovery_valid, observations
            )

        except CHAOS_EXPERIMENT_ERRORS as e:
            await self._handle_experiment_error(e, errors)

        return self._create_experiment_result(
            baseline_valid,
            during_chaos_valid,
            recovery_valid,
            violations,
            scenario_results,
            observations,
            errors,
        )

    async def _execute_baseline_validation(
        self, observations: list[str], violations: list[ValidationResult]
    ) -> tuple[bool, list[str], list[ValidationResult]]:
        """Execute baseline validation phase."""
        self._phase = ExperimentPhase.VALIDATING_BASELINE
        observations.append(f"Starting baseline validation ({self.baseline_check_duration_s}s)")
        logger.info(f"[{self.constitutional_hash}] Experiment '{self.name}': validating baseline")

        baseline_results = await self._validate_steady_state(self.baseline_check_duration_s)
        baseline_valid = all(r.valid for r in baseline_results)
        violations.extend([r for r in baseline_results if not r.valid])

        if not baseline_valid:
            observations.append("WARNING: Baseline steady state not valid")
            if self.abort_on_violation:
                raise Exception("Baseline steady state validation failed")

        observations.append(f"Baseline valid: {baseline_valid}")
        return baseline_valid, observations, violations

    async def _execute_chaos_injection_and_validation(
        self,
        observations: list[str],
        violations: list[ValidationResult],
        scenario_results: list[ScenarioResult],
    ) -> tuple[bool, list[str], list[ValidationResult], list[ScenarioResult]]:
        """Execute chaos injection and validation during chaos phases."""
        # Phase 2: Inject chaos
        self._phase = ExperimentPhase.INJECTING_CHAOS
        observations.append(f"Injecting chaos: {self.scenario.name}")
        logger.info(f"[{self.constitutional_hash}] Experiment '{self.name}': injecting chaos")

        # Start scenario execution in background
        scenario_task = asyncio.create_task(self.scenario.execute())

        # Phase 3: Validate during chaos
        during_chaos_valid = await self._validate_during_chaos_execution(observations, violations)

        # Wait for scenario to complete
        await self._await_scenario_completion(scenario_task, scenario_results, observations)

        return during_chaos_valid, observations, violations, scenario_results

    async def _validate_during_chaos_execution(
        self, observations: list[str], violations: list[ValidationResult]
    ) -> bool:
        """Validate steady state during chaos execution."""
        self._phase = ExperimentPhase.VALIDATING_DURING_CHAOS
        observations.append("Validating steady state during chaos")

        during_chaos_valid = True
        chaos_duration = self.scenario.duration_s
        elapsed = 0.0

        while elapsed < chaos_duration and not self._aborted:
            chaos_results = await self._validate_steady_state(
                min(self.validation_interval_s, chaos_duration - elapsed)
            )
            for r in chaos_results:
                if not r.valid:
                    during_chaos_valid = False
                    violations.append(r)
                    observations.append(
                        f"Violation during chaos: {r.metric_name} = {r.actual_value}"
                    )

                    if self.abort_on_violation:
                        self.abort()
                        break

            elapsed += self.validation_interval_s

        return during_chaos_valid

    async def _await_scenario_completion(
        self,
        scenario_task: asyncio.Task,
        scenario_results: list[ScenarioResult],
        observations: list[str],
    ) -> None:
        """Wait for scenario execution to complete."""
        try:
            scenario_result = await asyncio.wait_for(scenario_task, timeout=10.0)
            scenario_results.append(scenario_result)
        except TimeoutError:
            observations.append("Scenario execution timed out")
            self.scenario.cancel()

    async def _execute_rollback(self, observations: list[str], errors: list[str]) -> list[str]:
        """Execute rollback phase."""
        self._phase = ExperimentPhase.ROLLING_BACK
        observations.append("Rolling back chaos")
        logger.info(f"[{self.constitutional_hash}] Experiment '{self.name}': rolling back")

        try:
            await self.scenario.rollback()
            observations.append("Rollback completed")
        except CHAOS_ROLLBACK_ERRORS as e:
            errors.append(f"Rollback error: {e!s}")

        return errors

    async def _execute_recovery_validation(
        self, observations: list[str], violations: list[ValidationResult]
    ) -> tuple[bool, list[str], list[ValidationResult]]:
        """Execute recovery validation phase."""
        self._phase = ExperimentPhase.VALIDATING_RECOVERY
        observations.append(f"Validating recovery ({self.recovery_check_duration_s}s)")
        logger.info(f"[{self.constitutional_hash}] Experiment '{self.name}': validating recovery")

        recovery_results = await self._validate_steady_state(self.recovery_check_duration_s)
        recovery_valid = all(r.valid for r in recovery_results)
        violations.extend([r for r in recovery_results if not r.valid])
        observations.append(f"Recovery valid: {recovery_valid}")

        return recovery_valid, observations, violations

    def _determine_final_status(
        self,
        baseline_valid: bool,
        during_chaos_valid: bool,
        recovery_valid: bool,
        observations: list[str],
    ) -> None:
        """Determine the final experiment status."""
        self._phase = ExperimentPhase.COMPLETED
        if self._aborted:
            self._status = ExperimentStatus.ABORTED
        elif not during_chaos_valid:
            self._status = ExperimentStatus.FAILED
            observations.append("FAILED: Steady state violated during chaos")
        elif not recovery_valid:
            self._status = ExperimentStatus.FAILED
            observations.append("FAILED: System did not recover properly")
        else:
            self._status = ExperimentStatus.PASSED
            observations.append("PASSED: System maintained steady state")

    async def _handle_experiment_error(self, error: Exception, errors: list[str]) -> None:
        """Handle experiment execution errors."""
        self._phase = ExperimentPhase.FAILED
        self._status = ExperimentStatus.ERROR
        errors.append(f"Experiment error: {error!s}")
        logger.error(f"[{self.constitutional_hash}] Experiment '{self.name}' error: {error}")

        # Attempt rollback on error
        try:
            await self.scenario.rollback()
        except (RuntimeError, ValueError, TypeError, OSError):
            pass

    def _create_experiment_result(
        self,
        baseline_valid: bool,
        during_chaos_valid: bool,
        recovery_valid: bool,
        violations: list[ValidationResult],
        scenario_results: list[ScenarioResult],
        observations: list[str],
        errors: list[str],
    ) -> ExperimentResult:
        """Create the final experiment result."""
        ended_at = datetime.now(UTC)
        self._result = ExperimentResult(
            experiment_name=self.name,
            hypothesis=self.hypothesis,
            status=self._status,
            phase=self._phase,
            started_at=self._started_at,
            ended_at=ended_at,
            duration_s=(ended_at - self._started_at).total_seconds(),
            baseline_valid=baseline_valid,
            during_chaos_valid=during_chaos_valid,
            recovery_valid=recovery_valid,
            steady_state_violations=violations,
            scenario_results=scenario_results,
            observations=observations,
            errors=errors,
        )

        logger.info(
            f"[{self.constitutional_hash}] Experiment '{self.name}' completed: {self._status.value}"
        )

        return self._result

    async def _validate_steady_state(self, duration_s: float) -> list[ValidationResult]:
        """Validate steady state for a duration."""
        results: list[ValidationResult] = []
        elapsed = 0.0
        interval = min(0.5, duration_s)

        while elapsed < duration_s and not self._aborted:
            batch_results = await self.steady_state.validate()
            results.extend(batch_results)
            await asyncio.sleep(interval)
            elapsed += interval

        return results

    async def __aenter__(self) -> "ChaosExperiment":
        """Async context manager entry."""
        # Start the experiment in background
        self._experiment_task = asyncio.create_task(self.run())
        # Wait a bit for baseline validation
        await asyncio.sleep(self.baseline_check_duration_s + 0.5)
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Async context manager exit."""
        if exc_type:
            self.abort()
        # Wait for experiment to complete
        if hasattr(self, "_experiment_task"):
            try:
                await asyncio.wait_for(self._experiment_task, timeout=30.0)
            except TimeoutError:
                self.abort()

    def get_result(self) -> ExperimentResult | None:
        """Get the experiment result."""
        return self._result

    def to_dict(self) -> JSONDict:
        """Convert experiment to dictionary."""
        return {
            "name": self.name,
            "hypothesis": self.hypothesis,
            "phase": self._phase.value,
            "status": self._status.value,
            "scenario": self.scenario.to_dict(),
            "steady_state": self.steady_state.get_summary(),
            "constitutional_hash": self.constitutional_hash,
        }


# Experiment registry for tracking
_experiment_registry: dict[str, ChaosExperiment] = {}
_registry_lock = threading.Lock()


def get_experiment_registry() -> dict[str, ChaosExperiment]:
    """Get the experiment registry."""
    with _registry_lock:
        return _experiment_registry.copy()


def reset_experiment_registry() -> None:
    """Reset the experiment registry."""
    global _experiment_registry
    with _registry_lock:
        _experiment_registry.clear()


def register_experiment(experiment: ChaosExperiment) -> None:
    """Register an experiment in the global registry."""
    with _registry_lock:
        _experiment_registry[experiment.name] = experiment


# Decorator for chaos tests
def chaos_experiment(
    hypothesis: str,
    scenario: BaseScenario,
    steady_state_metrics: dict[str, tuple] | None = None,
    abort_on_violation: bool = False,
) -> Callable[[F], F]:
    """
    Decorator to run a function as a chaos experiment.

    Usage:
        @chaos_experiment(
            hypothesis="System handles Redis failure",
            scenario=DependencyFailureScenario(DependencyType.REDIS, duration_s=10),
            steady_state_metrics={"latency_p99": ("<=", 5.0)},
        )
        async def test_redis_failure():
            # Test code runs during chaos
            await send_messages(100)

    Args:
        hypothesis: What we expect to observe
        scenario: Chaos scenario to execute
        steady_state_metrics: Metrics to validate
        abort_on_violation: Abort on steady state violation
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            # Create steady state validator
            validator = SteadyStateValidator(
                name=f"{func.__name__}_steady_state",
                metrics=steady_state_metrics or {},
            )

            # Create experiment
            experiment = ChaosExperiment(
                name=f"experiment_{func.__name__}",
                hypothesis=hypothesis,
                steady_state=validator,
                scenario=scenario,
                abort_on_violation=abort_on_violation,
            )

            # Register experiment
            register_experiment(experiment)

            # Run experiment
            try:
                async with experiment:
                    result = await func(*args, **kwargs)
                    return result
            finally:
                exp_result = experiment.get_result()
                if exp_result and exp_result.status == ExperimentStatus.FAILED:
                    raise AssertionError(f"Chaos experiment failed: {exp_result.observations}")

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        else:
            raise ValueError("chaos_experiment decorator only supports async functions")

    return decorator


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Classes
    "ChaosExperiment",
    # Enums
    "ExperimentPhase",
    # Data classes
    "ExperimentResult",
    "ExperimentStatus",
    # Decorators
    "chaos_experiment",
    # Functions
    "get_experiment_registry",
    "register_experiment",
    "reset_experiment_registry",
]
