"""
ACGS-2 Enhanced Agent Bus - Steady State Validation
Constitutional Hash: cdd01ef066bc6cf2

Implements steady state hypothesis validation for chaos engineering experiments.
The steady state represents normal system behavior that should be maintained
even under chaos conditions.

Principles:
1. Define measurable steady state before experiments
2. Continuously validate during chaos injection
3. Verify recovery after chaos ends
4. Report deviations with constitutional compliance

Expert Reference: Michael Nygard (Release It!)
"""

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
STEADY_STATE_COLLECTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)


class MetricOperator(str, Enum):  # noqa: UP042
    """Operators for metric comparison."""

    LESS_THAN = "<"
    LESS_EQUAL = "<="
    EQUAL = "=="
    GREATER_EQUAL = ">="
    GREATER_THAN = ">"
    NOT_EQUAL = "!="
    BETWEEN = "between"


@dataclass
class ValidationMetric:
    """
    A metric to validate in steady state.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    name: str
    operator: MetricOperator
    threshold: float
    threshold_max: float | None = None  # For BETWEEN operator
    description: str = ""
    unit: str = ""
    weight: float = 1.0  # Importance weight for composite scoring

    def validate(self, value: float) -> bool:
        """Validate a value against this metric's threshold."""
        if self.operator == MetricOperator.LESS_THAN:
            return value < self.threshold
        elif self.operator == MetricOperator.LESS_EQUAL:
            return value <= self.threshold
        elif self.operator == MetricOperator.EQUAL:
            return abs(value - self.threshold) < 0.0001  # Float comparison
        elif self.operator == MetricOperator.GREATER_EQUAL:
            return value >= self.threshold
        elif self.operator == MetricOperator.GREATER_THAN:
            return value > self.threshold
        elif self.operator == MetricOperator.NOT_EQUAL:
            return abs(value - self.threshold) >= 0.0001
        elif self.operator == MetricOperator.BETWEEN:
            if self.threshold_max is None:
                raise ValueError("BETWEEN operator requires threshold_max")
            return self.threshold <= value <= self.threshold_max
        else:
            raise ValueError(f"Unknown operator: {self.operator}")

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "operator": self.operator.value,
            "threshold": self.threshold,
            "threshold_max": self.threshold_max,
            "description": self.description,
            "unit": self.unit,
            "weight": self.weight,
        }


@dataclass
class ValidationResult:
    """
    Result of a steady state validation check.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    valid: bool
    metric_name: str
    expected_value: str  # Human-readable expectation
    actual_value: float
    deviation: float | None = None  # Percentage deviation from threshold
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str = ""
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "metric_name": self.metric_name,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "deviation": self.deviation,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "constitutional_hash": self.constitutional_hash,
        }


class InMemoryMetricCollector:
    """
    In-memory metric collector for testing and simple scenarios.

    Stores metric values that can be updated programmatically.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, deque[tuple[float, float]]] = {}  # name -> [(timestamp, value)]
        self._window_size = 100  # Keep last 100 samples per metric

    def record(self, metric_name: str, value: float) -> None:
        """Record a metric value."""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = deque(maxlen=self._window_size)
        self._metrics[metric_name].append((time.time(), value))

    async def collect(self, metric_name: str) -> float:
        """Get the latest value for a metric."""
        if metric_name not in self._metrics or not self._metrics[metric_name]:
            raise KeyError(f"Metric '{metric_name}' not found")
        return self._metrics[metric_name][-1][1]

    def get_average(self, metric_name: str, window_seconds: float = 60.0) -> float:
        """Get average value over a time window."""
        if metric_name not in self._metrics:
            raise KeyError(f"Metric '{metric_name}' not found")

        now = time.time()
        cutoff = now - window_seconds
        values = [v for t, v in self._metrics[metric_name] if t >= cutoff]

        if not values:
            raise ValueError(f"No values for metric '{metric_name}' in the last {window_seconds}s")

        return statistics.mean(values)

    def get_percentile(
        self, metric_name: str, percentile: float, window_seconds: float = 60.0
    ) -> float:
        """Get percentile value over a time window."""
        if metric_name not in self._metrics:
            raise KeyError(f"Metric '{metric_name}' not found")

        now = time.time()
        cutoff = now - window_seconds
        values = sorted([v for t, v in self._metrics[metric_name] if t >= cutoff])

        if not values:
            raise ValueError(f"No values for metric '{metric_name}' in the last {window_seconds}s")

        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]

    def get_available_metrics(self) -> list[str]:
        """Get list of available metrics."""
        return list(self._metrics.keys())

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()


@dataclass
class SteadyStateHypothesis:
    """
    A hypothesis about the system's steady state.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    name: str
    description: str
    metrics: list[ValidationMetric]
    tolerance_window_s: float = 5.0  # How long a violation is tolerated
    consecutive_failures_allowed: int = 2  # Allow brief spikes
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "metrics": [m.to_dict() for m in self.metrics],
            "tolerance_window_s": self.tolerance_window_s,
            "consecutive_failures_allowed": self.consecutive_failures_allowed,
            "constitutional_hash": self.constitutional_hash,
        }


class SteadyStateValidator:
    """
    Validates system steady state during chaos experiments.

    Constitutional Hash: cdd01ef066bc6cf2

    Features:
    - Continuous metric validation
    - Tolerance for brief deviations
    - Detailed violation reporting
    - Constitutional compliance tracking
    """

    def __init__(
        self,
        name: str,
        metrics: dict[str, tuple[str, float]] | None = None,
        collector: InMemoryMetricCollector | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """
        Initialize steady state validator.

        Args:
            name: Validator name
            metrics: Dict of metric_name -> (operator_str, threshold)
                     e.g., {"latency_p99": ("<=", 5.0)}
            collector: Metric collector to use
            constitutional_hash: Constitutional hash for validation
        """
        if constitutional_hash != CONSTITUTIONAL_HASH:
            from enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

            raise ConstitutionalHashMismatchError(
                expected_hash=CONSTITUTIONAL_HASH,
                actual_hash=constitutional_hash,
                context="SteadyStateValidator",
            )

        self.name = name
        self.constitutional_hash = constitutional_hash
        self._collector = collector or InMemoryMetricCollector()
        self._validation_metrics: list[ValidationMetric] = []
        self._validation_results: list[ValidationResult] = []
        self._consecutive_failures: dict[str, int] = {}
        self._is_valid = True

        # Convert simple metric definitions to ValidationMetric objects
        if metrics:
            for metric_name, (operator_str, threshold) in metrics.items():
                operator = self._parse_operator(operator_str)
                self._validation_metrics.append(
                    ValidationMetric(
                        name=metric_name,
                        operator=operator,
                        threshold=threshold,
                    )
                )

    def _parse_operator(self, operator_str: str) -> MetricOperator:
        """Parse operator string to MetricOperator enum."""
        operator_map = {
            "<": MetricOperator.LESS_THAN,
            "<=": MetricOperator.LESS_EQUAL,
            "==": MetricOperator.EQUAL,
            ">=": MetricOperator.GREATER_EQUAL,
            ">": MetricOperator.GREATER_THAN,
            "!=": MetricOperator.NOT_EQUAL,
        }
        if operator_str not in operator_map:
            raise ValueError(f"Unknown operator: {operator_str}")
        return operator_map[operator_str]

    def add_metric(self, metric: ValidationMetric) -> None:
        """Add a validation metric."""
        self._validation_metrics.append(metric)
        self._consecutive_failures[metric.name] = 0

    async def validate(self, consecutive_failures_allowed: int = 2) -> list[ValidationResult]:
        """
        Validate all metrics against their thresholds.

        Args:
            consecutive_failures_allowed: How many consecutive failures to tolerate

        Returns:
            List of validation results
        """
        results: list[ValidationResult] = []
        all_valid = True

        for metric in self._validation_metrics:
            try:
                value = await self._collector.collect(metric.name)
                valid = metric.validate(value)

                # Track consecutive failures
                if valid:
                    self._consecutive_failures[metric.name] = 0
                else:
                    self._consecutive_failures[metric.name] = (
                        self._consecutive_failures.get(metric.name, 0) + 1
                    )

                    # Only fail if exceeded consecutive failure threshold
                    if self._consecutive_failures[metric.name] <= consecutive_failures_allowed:
                        valid = True  # Tolerate brief spike

                # Calculate deviation
                deviation = None
                if metric.threshold != 0:
                    deviation = ((value - metric.threshold) / abs(metric.threshold)) * 100

                expected = f"{metric.operator.value} {metric.threshold}"
                if metric.unit:
                    expected += f" {metric.unit}"

                result = ValidationResult(
                    valid=valid,
                    metric_name=metric.name,
                    expected_value=expected,
                    actual_value=value,
                    deviation=deviation,
                    message=f"Metric '{metric.name}' = {value:.4f} ({expected})",
                )
                results.append(result)
                self._validation_results.append(result)

                if not valid:
                    all_valid = False
                    logger.warning(
                        f"[{self.constitutional_hash}] Steady state violation: "
                        f"{metric.name} = {value:.4f} (expected {expected})"
                    )

            except KeyError:
                # Metric not available yet
                result = ValidationResult(
                    valid=True,  # Don't fail on missing metrics
                    metric_name=metric.name,
                    expected_value=f"{metric.operator.value} {metric.threshold}",
                    actual_value=0.0,
                    message=f"Metric '{metric.name}' not yet available",
                )
                results.append(result)

            except STEADY_STATE_COLLECTION_ERRORS as e:
                result = ValidationResult(
                    valid=False,
                    metric_name=metric.name,
                    expected_value=f"{metric.operator.value} {metric.threshold}",
                    actual_value=0.0,
                    message=f"Error collecting metric '{metric.name}': {e}",
                )
                results.append(result)
                all_valid = False

        self._is_valid = all_valid
        return results

    def record_metric(self, name: str, value: float) -> None:
        """Record a metric value (convenience method for InMemoryMetricCollector)."""
        if isinstance(self._collector, InMemoryMetricCollector):
            self._collector.record(name, value)
        else:
            raise TypeError("record_metric only works with InMemoryMetricCollector")

    def is_valid(self) -> bool:
        """Check if steady state is currently valid."""
        return self._is_valid

    def get_violations(self) -> list[ValidationResult]:
        """Get all validation violations."""
        return [r for r in self._validation_results if not r.valid]

    def get_summary(self) -> JSONDict:
        """Get summary of validation state."""
        total_checks = len(self._validation_results)
        violations = self.get_violations()

        return {
            "name": self.name,
            "is_valid": self._is_valid,
            "total_checks": total_checks,
            "violations_count": len(violations),
            "metrics_count": len(self._validation_metrics),
            "metrics": [m.name for m in self._validation_metrics],
            "recent_violations": [v.to_dict() for v in violations[-10:]],
            "constitutional_hash": self.constitutional_hash,
        }

    def reset(self) -> None:
        """Reset validation state."""
        self._validation_results.clear()
        self._consecutive_failures.clear()
        self._is_valid = True

    def to_hypothesis(self, tolerance_window_s: float = 5.0) -> SteadyStateHypothesis:
        """Convert validator configuration to a hypothesis."""
        return SteadyStateHypothesis(
            name=self.name,
            description=f"Steady state hypothesis for {self.name}",
            metrics=self._validation_metrics.copy(),
            tolerance_window_s=tolerance_window_s,
            constitutional_hash=self.constitutional_hash,
        )


# Pre-defined steady state configurations for common scenarios
def create_message_bus_steady_state() -> SteadyStateValidator:
    """Create steady state validator for Enhanced Agent Bus."""
    validator = SteadyStateValidator(
        name="enhanced_agent_bus_steady_state",
        metrics={
            "latency_p99_ms": ("<=", 5.0),
            "latency_p95_ms": ("<=", 3.0),
            "error_rate": ("<=", 0.01),
            "throughput_rps": (">=", 100.0),
            "message_queue_size": ("<=", 1000.0),
            "cpu_usage_percent": ("<=", 80.0),
            "memory_usage_percent": ("<=", 85.0),
        },
    )
    return validator


def create_constitutional_validation_steady_state() -> SteadyStateValidator:
    """Create steady state validator for constitutional validation."""
    validator = SteadyStateValidator(
        name="constitutional_validation_steady_state",
        metrics={
            "validation_latency_ms": ("<=", 10.0),
            "validation_success_rate": (">=", 0.999),
            "opa_response_time_ms": ("<=", 50.0),
            "cache_hit_rate": (">=", 0.85),
        },
    )
    return validator


def create_maci_enforcement_steady_state() -> SteadyStateValidator:
    """Create steady state validator for MACI enforcement."""
    validator = SteadyStateValidator(
        name="maci_enforcement_steady_state",
        metrics={
            "role_validation_latency_ms": ("<=", 5.0),
            "authorization_success_rate": (">=", 0.95),
            "cross_role_validation_time_ms": ("<=", 20.0),
        },
    )
    return validator


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Classes
    "InMemoryMetricCollector",
    # Enums
    "MetricOperator",
    "SteadyStateHypothesis",
    "SteadyStateValidator",
    # Data classes
    "ValidationMetric",
    "ValidationResult",
    "create_constitutional_validation_steady_state",
    "create_maci_enforcement_steady_state",
    # Factory functions
    "create_message_bus_steady_state",
]
