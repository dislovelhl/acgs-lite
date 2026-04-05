"""
ACGS-2 Observability Fixtures
Constitutional Hash: 608508a9bd224290

Fixtures for timeout budgets, metrics, and tracing in specification tests.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import pytest

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# Try to import from observability module, fallback to local definitions
try:
    from enhanced_agent_bus.observability.telemetry import (
        MetricsRegistry,
        TracingContext,
    )
    from enhanced_agent_bus.observability.timeout_budget import (
        Layer,
        LayerTimeoutBudget,
        TimeoutBudgetManager,
    )

    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False

    # Define minimal fallback classes for standalone testing
    class Layer(Enum):  # type: ignore[no-redef]
        """Fallback Layer enum for standalone testing."""

        LAYER1_VALIDATION = "layer1_validation"
        LAYER2_DELIBERATION = "layer2_deliberation"
        LAYER3_POLICY = "layer3_policy"
        LAYER4_AUDIT = "layer4_audit"

    @dataclass
    class LayerTimeoutBudget:  # type: ignore[no-redef]
        """Fallback budget dataclass."""

        layer: Layer
        budget_ms: float
        soft_limit_pct: float = 0.8
        strict_enforcement: bool = True

    class TimeoutBudgetManager:  # type: ignore[no-redef]
        """Fallback timeout budget manager."""

        def __init__(self, total_budget_ms: float = 50.0):
            self.total_budget_ms = total_budget_ms
            self._budgets = {
                Layer.LAYER1_VALIDATION: LayerTimeoutBudget(Layer.LAYER1_VALIDATION, 5.0),
                Layer.LAYER2_DELIBERATION: LayerTimeoutBudget(Layer.LAYER2_DELIBERATION, 20.0),
                Layer.LAYER3_POLICY: LayerTimeoutBudget(Layer.LAYER3_POLICY, 10.0),
                Layer.LAYER4_AUDIT: LayerTimeoutBudget(Layer.LAYER4_AUDIT, 15.0),
            }

        def get_layer_budget(self, layer: Layer) -> LayerTimeoutBudget:
            return self._budgets.get(layer, LayerTimeoutBudget(layer, 10.0))

    class MetricsRegistry:  # type: ignore[no-redef]
        """Fallback metrics registry."""

        def __init__(self, service_name: str = "acgs2"):
            self.service_name = service_name
            self._counters: dict[str, int] = {}

        def increment_counter(
            self, name: str, amount: int = 1, attributes: dict[str, str] | None = None
        ) -> None:
            self._counters[name] = self._counters.get(name, 0) + amount

        def record_latency(
            self, name: str, value_ms: float, attributes: dict[str, str] | None = None
        ) -> None:
            pass

    class TracingContext:  # type: ignore[no-redef]
        """Fallback tracing context."""

        def __init__(self, operation_name: str):
            self.operation_name = operation_name

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def set_attribute(self, key: str, value: str) -> None:
            pass


@dataclass
class LatencyMeasurement:
    """Captured latency measurement for spec verification."""

    layer: str
    operation: str
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    within_budget: bool = True
    budget_ms: float | None = None

    def to_dict(self) -> JSONDict:
        return {
            "layer": self.layer,
            "operation": self.operation,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
            "within_budget": self.within_budget,
            "budget_ms": self.budget_ms,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


class SpecTimeoutBudgetManager(TimeoutBudgetManager):
    """
    Extended timeout budget manager for specification testing.

    Captures latency measurements for verification against specs.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.measurements: list[LatencyMeasurement] = []

    def record_measurement(
        self,
        layer: Layer,
        operation: str,
        latency_ms: float,
    ) -> LatencyMeasurement:
        """
        Record a latency measurement for spec verification.

        Args:
            layer: The architectural layer
            operation: Operation name
            latency_ms: Measured latency in milliseconds

        Returns:
            LatencyMeasurement with budget comparison
        """
        budget = self.get_layer_budget(layer)
        measurement = LatencyMeasurement(
            layer=layer.value,
            operation=operation,
            latency_ms=latency_ms,
            within_budget=latency_ms <= budget.budget_ms,
            budget_ms=budget.budget_ms,
        )
        self.measurements.append(measurement)
        return measurement

    def get_measurements_by_layer(self, layer: Layer) -> list[LatencyMeasurement]:
        """Get all measurements for a specific layer."""
        return [m for m in self.measurements if m.layer == layer.value]

    def get_budget_violations(self) -> list[LatencyMeasurement]:
        """Get all measurements that exceeded their budget."""
        return [m for m in self.measurements if not m.within_budget]

    def calculate_percentile(
        self,
        layer: Layer,
        percentile: float,
    ) -> float | None:
        """
        Calculate latency percentile for a layer.

        Args:
            layer: The architectural layer
            percentile: Percentile value (0-100)

        Returns:
            Latency at the given percentile, or None if no measurements
        """
        measurements = self.get_measurements_by_layer(layer)
        if not measurements:
            return None

        latencies = sorted(m.latency_ms for m in measurements)
        index = int(len(latencies) * percentile / 100)
        return latencies[min(index, len(latencies) - 1)]

    def verify_budget_compliance(self) -> JSONDict:
        """
        Verify all layers meet their timeout budgets.

        Returns:
            Compliance report with per-layer status
        """
        report = {
            "compliant": True,
            "layers": {},
            "total_measurements": len(self.measurements),
            "violations": len(self.get_budget_violations()),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        for layer in Layer:
            measurements = self.get_measurements_by_layer(layer)
            if measurements:
                violations = [m for m in measurements if not m.within_budget]
                p50 = self.calculate_percentile(layer, 50)
                p99 = self.calculate_percentile(layer, 99)

                layer_report = {
                    "count": len(measurements),
                    "violations": len(violations),
                    "p50_ms": p50,
                    "p99_ms": p99,
                    "budget_ms": self.get_layer_budget(layer).budget_ms,
                    "compliant": len(violations) == 0,
                }
                report["layers"][layer.value] = layer_report  # type: ignore[index]

                if not layer_report["compliant"]:
                    report["compliant"] = False

        return report

    def clear_measurements(self) -> None:
        """Clear all recorded measurements."""
        self.measurements.clear()


class SpecMetricsRegistry(MetricsRegistry):
    """
    Extended metrics registry for specification testing.

    Captures metrics events for verification against specs.
    """

    def __init__(self, service_name: str = "acgs2-specs"):
        super().__init__(service_name)
        self.metric_events: list[JSONDict] = []

    def record_event(
        self,
        metric_name: str,
        value: float,
        metric_type: str,
        attributes: dict[str, str] | None = None,
    ) -> None:
        """Record a metric event for spec verification."""
        event = {
            "metric_name": metric_name,
            "value": value,
            "type": metric_type,
            "attributes": attributes or {},
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        self.metric_events.append(event)

    def increment_counter(
        self,
        name: str,
        amount: int = 1,
        attributes: dict[str, str] | None = None,
    ) -> None:
        super().increment_counter(name, amount, attributes)
        self.record_event(name, amount, "counter", attributes)

    def record_latency(
        self,
        name: str,
        value_ms: float,
        attributes: dict[str, str] | None = None,
    ) -> None:
        super().record_latency(name, value_ms, attributes)
        self.record_event(name, value_ms, "histogram", attributes)

    def get_events_by_name(self, name: str) -> list[JSONDict]:
        """Get all events for a specific metric."""
        return [e for e in self.metric_events if e["metric_name"] == name]

    def get_counter_total(self, name: str) -> int:
        """Get total count for a counter metric."""
        events = [
            e for e in self.metric_events if e["metric_name"] == name and e["type"] == "counter"
        ]
        return sum(int(e["value"]) for e in events)

    def clear_events(self) -> None:
        """Clear all recorded events."""
        self.metric_events.clear()


@pytest.fixture
def timeout_budget_manager() -> SpecTimeoutBudgetManager:
    """
    Fixture providing a timeout budget manager for spec testing.

    Use in tests verifying latency budget compliance:
        def test_layer_latency(timeout_budget_manager):
            manager = timeout_budget_manager
            measurement = manager.record_measurement(Layer.LAYER1_VALIDATION, "op", 3.5)
            assert measurement.within_budget
    """
    return SpecTimeoutBudgetManager()


@pytest.fixture
def metrics_registry() -> SpecMetricsRegistry:
    """
    Fixture providing a metrics registry for spec testing.

    Use in tests verifying metrics collection:
        def test_counter_incremented(metrics_registry):
            metrics_registry.increment_counter("requests")
            assert metrics_registry.get_counter_total("requests") == 1
    """
    return SpecMetricsRegistry()


@pytest.fixture
def tracing_context():
    """
    Fixture providing a tracing context factory.

    Use in tests verifying span creation:
        def test_span_created(tracing_context):
            with tracing_context("operation") as span:
                span.set_attribute("key", "value")
    """
    return TracingContext
