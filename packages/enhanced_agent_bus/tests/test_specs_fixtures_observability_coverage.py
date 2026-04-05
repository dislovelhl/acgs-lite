# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/specs/fixtures/observability.py

Targets ≥95% line coverage of the observability fixtures module.
"""

import importlib
import sys
from datetime import UTC, datetime, timezone

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Import the module under test and introspect actual classes in use
# ---------------------------------------------------------------------------

_MOD_NAME = "enhanced_agent_bus.specs.fixtures.observability"
if _MOD_NAME in sys.modules:
    _mod = sys.modules[_MOD_NAME]
else:
    _mod = importlib.import_module(_MOD_NAME)

# Check whether the real observability packages were available
_OBSERVABILITY_AVAILABLE = _mod._OBSERVABILITY_AVAILABLE  # type: ignore[attr-defined]

# Resolve the actual Layer / budget classes in use (real or fallback)
Layer = _mod.Layer  # type: ignore[attr-defined]
LayerTimeoutBudget = _mod.LayerTimeoutBudget  # type: ignore[attr-defined]
TimeoutBudgetManager = _mod.TimeoutBudgetManager  # type: ignore[attr-defined]
MetricsRegistry = _mod.MetricsRegistry  # type: ignore[attr-defined]
TracingContext = _mod.TracingContext  # type: ignore[attr-defined]

# Import the public fixtures and classes
from enhanced_agent_bus.specs.fixtures.observability import (
    LatencyMeasurement,
    SpecMetricsRegistry,
    SpecTimeoutBudgetManager,
    metrics_registry,
    timeout_budget_manager,
    tracing_context,
)

# ===========================================================================
# LatencyMeasurement
# ===========================================================================


class TestLatencyMeasurement:
    def test_default_construction(self):
        m = LatencyMeasurement(layer="layer1", operation="op", latency_ms=3.5)
        assert m.layer == "layer1"
        assert m.operation == "op"
        assert m.latency_ms == 3.5
        assert m.within_budget is True
        assert m.budget_ms is None
        assert isinstance(m.timestamp, datetime)

    def test_explicit_timestamp(self):
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=1.0, timestamp=ts)
        assert m.timestamp == ts

    def test_within_budget_false(self):
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=10.0, within_budget=False)
        assert m.within_budget is False

    def test_budget_ms_set(self):
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=5.0, budget_ms=20.0)
        assert m.budget_ms == 20.0

    def test_to_dict_keys(self):
        m = LatencyMeasurement(layer="layer1", operation="validate", latency_ms=2.5, budget_ms=5.0)
        d = m.to_dict()
        assert d["layer"] == "layer1"
        assert d["operation"] == "validate"
        assert d["latency_ms"] == 2.5
        assert d["within_budget"] is True
        assert d["budget_ms"] == 5.0
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in d

    def test_to_dict_timestamp_is_iso(self):
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=1.0)
        d = m.to_dict()
        datetime.fromisoformat(d["timestamp"])

    def test_to_dict_none_budget(self):
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=1.0)
        d = m.to_dict()
        assert d["budget_ms"] is None

    def test_to_dict_constitutional_hash_correct(self):
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=1.0)
        assert m.to_dict()["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_default_timestamp_is_utc(self):
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=1.0)
        assert m.timestamp.tzinfo is not None

    def test_all_fields_in_to_dict(self):
        m = LatencyMeasurement(layer="l", operation="op", latency_ms=1.0)
        d = m.to_dict()
        expected_keys = {
            "layer",
            "operation",
            "latency_ms",
            "timestamp",
            "within_budget",
            "budget_ms",
            "constitutional_hash",
        }
        assert set(d.keys()) == expected_keys


# ===========================================================================
# Layer enum (works for both real and fallback)
# ===========================================================================


class TestLayerEnum:
    def test_layer_values_exist(self):
        assert hasattr(Layer, "LAYER1_VALIDATION")
        assert hasattr(Layer, "LAYER2_DELIBERATION")
        assert hasattr(Layer, "LAYER3_POLICY")
        assert hasattr(Layer, "LAYER4_AUDIT")

    def test_layer_string_values(self):
        assert Layer.LAYER1_VALIDATION.value == "layer1_validation"
        assert Layer.LAYER2_DELIBERATION.value == "layer2_deliberation"
        assert Layer.LAYER3_POLICY.value == "layer3_policy"
        assert Layer.LAYER4_AUDIT.value == "layer4_audit"

    def test_all_layers_iterable(self):
        layers = list(Layer)
        assert len(layers) == 4


# ===========================================================================
# LayerTimeoutBudget (works for both real and fallback)
# ===========================================================================


class TestLayerTimeoutBudget:
    def test_construction(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=5.0)
        assert b.layer == Layer.LAYER1_VALIDATION
        assert b.budget_ms == 5.0

    def test_default_soft_limit(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=10.0)
        assert b.soft_limit_pct == 0.8

    def test_default_strict_enforcement(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=10.0)
        assert b.strict_enforcement is True


# ===========================================================================
# TimeoutBudgetManager (adapted for real vs. fallback)
# ===========================================================================


class TestTimeoutBudgetManager:
    def test_default_total_budget(self):
        mgr = TimeoutBudgetManager()
        assert mgr.total_budget_ms == 50.0

    def test_custom_total_budget(self):
        mgr = TimeoutBudgetManager(total_budget_ms=100.0)
        assert mgr.total_budget_ms == 100.0

    def test_get_layer_budget_layer1(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER1_VALIDATION)
        assert isinstance(b, LayerTimeoutBudget)
        assert b.budget_ms == 5.0

    def test_get_layer_budget_layer2(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER2_DELIBERATION)
        assert b.budget_ms == 20.0

    def test_get_layer_budget_layer3(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER3_POLICY)
        assert b.budget_ms == 10.0

    def test_get_layer_budget_layer4(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER4_AUDIT)
        assert b.budget_ms == 15.0

    @pytest.mark.skipif(
        _OBSERVABILITY_AVAILABLE,
        reason="Fallback-only test: real manager uses layer_budgets not _budgets",
    )
    def test_fallback_get_layer_budget_unknown_returns_default(self):
        """The fallback path: _budgets.get(layer, default) with a layer not in dict."""
        mgr = TimeoutBudgetManager()
        mgr._budgets.clear()
        b = mgr.get_layer_budget(Layer.LAYER1_VALIDATION)
        assert b.budget_ms == 10.0


# ===========================================================================
# MetricsRegistry (adapted for real vs. fallback)
# ===========================================================================


class TestMetricsRegistry:
    def test_service_name_stored(self):
        r = MetricsRegistry()
        assert hasattr(r, "service_name")
        assert isinstance(r.service_name, str)

    def test_custom_service_name(self):
        r = MetricsRegistry(service_name="my-svc")
        assert r.service_name == "my-svc"

    def test_increment_counter_does_not_raise(self):
        r = MetricsRegistry()
        r.increment_counter("req")  # Should not raise

    def test_increment_counter_with_amount(self):
        r = MetricsRegistry()
        r.increment_counter("req", 3)

    def test_increment_counter_with_attributes(self):
        r = MetricsRegistry()
        r.increment_counter("req", 1, {"env": "test"})

    def test_record_latency_does_not_raise(self):
        r = MetricsRegistry()
        r.record_latency("latency", 5.0)
        r.record_latency("latency", 5.0, {"op": "test"})

    @pytest.mark.skipif(
        _OBSERVABILITY_AVAILABLE,
        reason="Fallback-specific: _counters stores int",
    )
    def test_fallback_counter_accumulates(self):
        r = MetricsRegistry()
        r.increment_counter("req", 3)
        r.increment_counter("req", 2)
        assert r._counters["req"] == 5


# ===========================================================================
# TracingContext (adapted for real vs. fallback)
# ===========================================================================


class TestTracingContext:
    @pytest.mark.skipif(
        _OBSERVABILITY_AVAILABLE,
        reason="Real TracingContext uses .name not .operation_name",
    )
    def test_fallback_construction(self):
        tc = TracingContext("my_operation")
        assert tc.operation_name == "my_operation"

    @pytest.mark.skipif(
        not _OBSERVABILITY_AVAILABLE,
        reason="Real TracingContext uses .name attribute",
    )
    def test_real_construction(self):
        tc = TracingContext("my_operation")
        assert tc.name == "my_operation"

    def test_context_manager_no_exception(self):
        tc = TracingContext("op")
        with tc:
            pass  # Should not raise

    def test_context_manager_returns_span(self):
        tc = TracingContext("op")
        with tc as span:
            assert span is not None

    def test_set_attribute_no_exception(self):
        tc = TracingContext("op")
        with tc as span:
            span.set_attribute("key", "value")

    @pytest.mark.skipif(
        _OBSERVABILITY_AVAILABLE,
        reason="Fallback __exit__ returns None; real returns context result",
    )
    def test_fallback_exit_returns_none(self):
        tc = TracingContext("op")
        result = tc.__exit__(None, None, None)
        assert result is None

    @pytest.mark.skipif(
        not _OBSERVABILITY_AVAILABLE,
        reason="Real __exit__ delegates to context which may return bool",
    )
    def test_real_exit_no_exception(self):
        tc = TracingContext("op")
        result = tc.__exit__(None, None, None)
        # May return False or None; either is acceptable
        assert not result


# ===========================================================================
# SpecTimeoutBudgetManager
# ===========================================================================


class TestSpecTimeoutBudgetManager:
    def test_initial_measurements_empty(self):
        mgr = SpecTimeoutBudgetManager()
        assert mgr.measurements == []

    def test_inherits_from_timeout_budget_manager(self):
        mgr = SpecTimeoutBudgetManager()
        assert isinstance(mgr, TimeoutBudgetManager)

    def test_record_measurement_within_budget(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "validate", 3.0)
        assert m.within_budget is True
        assert m.layer == Layer.LAYER1_VALIDATION.value
        assert m.operation == "validate"
        assert m.latency_ms == 3.0

    def test_record_measurement_exceeds_budget(self):
        mgr = SpecTimeoutBudgetManager()
        # Layer1 budget is 5ms; record 10ms
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "slow_op", 10.0)
        assert m.within_budget is False

    def test_record_measurement_sets_budget_ms(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 3.0)
        assert m.budget_ms == 5.0

    def test_record_measurement_appends(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 1.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op2", 2.0)
        assert len(mgr.measurements) == 2

    def test_record_measurement_returns_latency_measurement(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER2_DELIBERATION, "deliberate", 15.0)
        assert isinstance(m, LatencyMeasurement)

    def test_get_measurements_by_layer_filters(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op2", 2.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op3", 3.0)

        layer1 = mgr.get_measurements_by_layer(Layer.LAYER1_VALIDATION)
        assert len(layer1) == 2
        assert all(m.layer == Layer.LAYER1_VALIDATION.value for m in layer1)

    def test_get_measurements_by_layer_empty(self):
        mgr = SpecTimeoutBudgetManager()
        result = mgr.get_measurements_by_layer(Layer.LAYER3_POLICY)
        assert result == []

    def test_get_budget_violations_empty_when_all_within(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        assert mgr.get_budget_violations() == []

    def test_get_budget_violations_returns_violations(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "fast", 1.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "slow", 100.0)
        violations = mgr.get_budget_violations()
        assert len(violations) == 1
        assert violations[0].operation == "slow"

    def test_get_budget_violations_multiple(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "s1", 100.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "s2", 200.0)
        assert len(mgr.get_budget_violations()) == 2

    def test_calculate_percentile_no_measurements(self):
        mgr = SpecTimeoutBudgetManager()
        result = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        assert result is None

    def test_calculate_percentile_single_value(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 3.5)
        p50 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        assert p50 == 3.5

    def test_calculate_percentile_multiple_values(self):
        mgr = SpecTimeoutBudgetManager()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", v)
        p0 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 0)
        p100 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 100)
        assert p0 == 1.0
        assert p100 == 5.0

    def test_calculate_percentile_p99_clamped(self):
        """Index at p99 with 1 element should return the only element."""
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 4.0)
        p99 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 99)
        assert p99 == 4.0

    def test_verify_budget_compliance_empty(self):
        mgr = SpecTimeoutBudgetManager()
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is True
        assert report["total_measurements"] == 0
        assert report["violations"] == 0
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert report["layers"] == {}

    def test_verify_budget_compliance_all_within(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is True
        assert report["violations"] == 0

    def test_verify_budget_compliance_with_violation(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "slow", 100.0)
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is False
        assert report["violations"] == 1

    def test_verify_budget_compliance_layer_report_keys(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 2.5)
        report = mgr.verify_budget_compliance()
        layer_key = Layer.LAYER1_VALIDATION.value
        assert layer_key in report["layers"]
        layer_report = report["layers"][layer_key]
        assert "count" in layer_report
        assert "violations" in layer_report
        assert "p50_ms" in layer_report
        assert "p99_ms" in layer_report
        assert "budget_ms" in layer_report
        assert "compliant" in layer_report

    def test_verify_budget_compliance_layer_count(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 1.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op2", 2.0)
        report = mgr.verify_budget_compliance()
        assert report["layers"][Layer.LAYER1_VALIDATION.value]["count"] == 2

    def test_verify_budget_compliance_total_measurements(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op", 2.0)
        report = mgr.verify_budget_compliance()
        assert report["total_measurements"] == 2

    def test_verify_budget_compliance_multi_layer(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op", 5.0)
        mgr.record_measurement(Layer.LAYER3_POLICY, "op", 3.0)
        mgr.record_measurement(Layer.LAYER4_AUDIT, "op", 8.0)
        report = mgr.verify_budget_compliance()
        assert len(report["layers"]) == 4

    def test_verify_budget_compliance_layer_not_compliant_sets_global_false(self):
        mgr = SpecTimeoutBudgetManager()
        # Layer2 budget is 20ms, record 50ms to violate
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op", 50.0)
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is False
        assert report["layers"][Layer.LAYER2_DELIBERATION.value]["compliant"] is False

    def test_clear_measurements(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.clear_measurements()
        assert mgr.measurements == []

    def test_clear_measurements_allows_reuse(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.clear_measurements()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op2", 2.0)
        assert len(mgr.measurements) == 1

    def test_custom_kwargs_passed_to_parent(self):
        mgr = SpecTimeoutBudgetManager(total_budget_ms=200.0)
        assert mgr.total_budget_ms == 200.0

    def test_record_measurement_boundary_exactly_at_budget(self):
        """Exactly at budget should be within_budget=True (<=)."""
        mgr = SpecTimeoutBudgetManager()
        # Layer1 budget = 5.0ms
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 5.0)
        assert m.within_budget is True

    def test_record_measurement_just_over_budget(self):
        """Just over budget should be within_budget=False."""
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 5.001)
        assert m.within_budget is False

    def test_record_measurement_layer2_within_budget(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER2_DELIBERATION, "deliberate", 19.0)
        assert m.within_budget is True
        assert m.budget_ms == 20.0

    def test_record_measurement_layer3_within_budget(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER3_POLICY, "policy", 9.0)
        assert m.within_budget is True
        assert m.budget_ms == 10.0

    def test_record_measurement_layer4_within_budget(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER4_AUDIT, "audit", 14.0)
        assert m.within_budget is True
        assert m.budget_ms == 15.0

    def test_get_measurements_by_layer_multiple_layers(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op", 2.0)
        layer2 = mgr.get_measurements_by_layer(Layer.LAYER2_DELIBERATION)
        assert len(layer2) == 1
        assert layer2[0].layer == Layer.LAYER2_DELIBERATION.value

    def test_verify_compliance_layer_compliant_true_when_no_violations(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        report = mgr.verify_budget_compliance()
        assert report["layers"][Layer.LAYER1_VALIDATION.value]["compliant"] is True

    def test_calculate_percentile_p50_two_values(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 3.0)
        p50 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        assert p50 is not None

    def test_measurements_list_is_list(self):
        mgr = SpecTimeoutBudgetManager()
        assert isinstance(mgr.measurements, list)


# ===========================================================================
# SpecMetricsRegistry
# ===========================================================================


class TestSpecMetricsRegistry:
    def test_default_service_name(self):
        r = SpecMetricsRegistry()
        assert r.service_name == "acgs2-specs"

    def test_custom_service_name(self):
        r = SpecMetricsRegistry(service_name="custom")
        assert r.service_name == "custom"

    def test_initial_metric_events_empty(self):
        r = SpecMetricsRegistry()
        assert r.metric_events == []

    def test_inherits_from_metrics_registry(self):
        r = SpecMetricsRegistry()
        assert isinstance(r, MetricsRegistry)

    def test_record_event_basic(self):
        r = SpecMetricsRegistry()
        r.record_event("my_metric", 1.0, "counter")
        assert len(r.metric_events) == 1
        e = r.metric_events[0]
        assert e["metric_name"] == "my_metric"
        assert e["value"] == 1.0
        assert e["type"] == "counter"
        assert e["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_record_event_with_attributes(self):
        r = SpecMetricsRegistry()
        r.record_event("latency", 5.0, "histogram", {"layer": "l1"})
        e = r.metric_events[0]
        assert e["attributes"] == {"layer": "l1"}

    def test_record_event_no_attributes_defaults_empty_dict(self):
        r = SpecMetricsRegistry()
        r.record_event("metric", 1.0, "counter")
        assert r.metric_events[0]["attributes"] == {}

    def test_record_event_timestamp_present(self):
        r = SpecMetricsRegistry()
        r.record_event("m", 1.0, "counter")
        datetime.fromisoformat(r.metric_events[0]["timestamp"])

    def test_increment_counter_records_event(self):
        r = SpecMetricsRegistry()
        r.increment_counter("req")
        assert len(r.metric_events) == 1
        assert r.metric_events[0]["type"] == "counter"

    def test_increment_counter_with_amount(self):
        r = SpecMetricsRegistry()
        r.increment_counter("req", 5)
        assert r.metric_events[0]["value"] == 5

    def test_increment_counter_with_attributes(self):
        r = SpecMetricsRegistry()
        r.increment_counter("req", 1, {"env": "prod"})
        assert r.metric_events[0]["attributes"] == {"env": "prod"}

    def test_record_latency_records_event(self):
        r = SpecMetricsRegistry()
        r.record_latency("lat", 3.0)
        e = r.metric_events[0]
        assert e["type"] == "histogram"
        assert e["value"] == 3.0

    def test_record_latency_with_attributes(self):
        r = SpecMetricsRegistry()
        r.record_latency("lat", 2.0, {"op": "validate"})
        assert r.metric_events[0]["attributes"] == {"op": "validate"}

    def test_record_latency_appends_event(self):
        r = SpecMetricsRegistry()
        r.record_latency("lat", 3.0)
        assert len(r.metric_events) == 1

    def test_get_events_by_name_found(self):
        r = SpecMetricsRegistry()
        r.increment_counter("alpha")
        r.increment_counter("beta")
        r.increment_counter("alpha")
        events = r.get_events_by_name("alpha")
        assert len(events) == 2

    def test_get_events_by_name_not_found(self):
        r = SpecMetricsRegistry()
        r.increment_counter("alpha")
        assert r.get_events_by_name("beta") == []

    def test_get_counter_total_single(self):
        r = SpecMetricsRegistry()
        r.increment_counter("req")
        assert r.get_counter_total("req") == 1

    def test_get_counter_total_multiple(self):
        r = SpecMetricsRegistry()
        r.increment_counter("req", 3)
        r.increment_counter("req", 7)
        assert r.get_counter_total("req") == 10

    def test_get_counter_total_excludes_histogram(self):
        r = SpecMetricsRegistry()
        r.record_latency("req", 5.0)  # type=histogram
        assert r.get_counter_total("req") == 0

    def test_get_counter_total_unknown_metric(self):
        r = SpecMetricsRegistry()
        assert r.get_counter_total("nonexistent") == 0

    def test_clear_events(self):
        r = SpecMetricsRegistry()
        r.increment_counter("req")
        r.clear_events()
        assert r.metric_events == []

    def test_clear_events_allows_reuse(self):
        r = SpecMetricsRegistry()
        r.increment_counter("req")
        r.clear_events()
        r.increment_counter("req2")
        assert len(r.metric_events) == 1

    def test_multiple_event_types_coexist(self):
        r = SpecMetricsRegistry()
        r.increment_counter("c", 2)
        r.record_latency("l", 5.0)
        assert len(r.metric_events) == 2

    def test_get_events_by_name_empty_registry(self):
        r = SpecMetricsRegistry()
        assert r.get_events_by_name("anything") == []

    def test_record_event_metric_name_preserved(self):
        r = SpecMetricsRegistry()
        r.record_event("specific_name", 42.0, "gauge")
        assert r.metric_events[0]["metric_name"] == "specific_name"

    def test_record_event_value_preserved(self):
        r = SpecMetricsRegistry()
        r.record_event("m", 99.9, "histogram")
        assert r.metric_events[0]["value"] == 99.9

    def test_counter_total_sums_integer_values(self):
        r = SpecMetricsRegistry()
        r.increment_counter("c", 2)
        r.increment_counter("c", 3)
        assert r.get_counter_total("c") == 5

    def test_increment_counter_calls_super_does_not_raise(self):
        r = SpecMetricsRegistry()
        # Calling super().increment_counter should not raise regardless of impl
        r.increment_counter("req", 1)
        # Verify event was recorded (our override was called)
        assert len(r.metric_events) == 1

    def test_record_latency_calls_super_does_not_raise(self):
        r = SpecMetricsRegistry()
        r.record_latency("lat", 5.0)
        # Verify event was recorded
        assert len(r.metric_events) == 1


# ===========================================================================
# Pytest Fixtures (used as fixtures via conftest injection)
# ===========================================================================


class TestTimeoutBudgetManagerFixture:
    def test_fixture_returns_spec_manager(self, timeout_budget_manager):
        assert isinstance(timeout_budget_manager, SpecTimeoutBudgetManager)

    def test_fixture_starts_fresh(self, timeout_budget_manager):
        assert timeout_budget_manager.measurements == []

    def test_fixture_usable(self, timeout_budget_manager):
        m = timeout_budget_manager.record_measurement(Layer.LAYER1_VALIDATION, "op", 2.0)
        assert m.within_budget is True

    def test_fixture_is_isolated_between_tests(self, timeout_budget_manager):
        timeout_budget_manager.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        assert len(timeout_budget_manager.measurements) == 1


class TestMetricsRegistryFixture:
    def test_fixture_returns_spec_registry(self, metrics_registry):
        assert isinstance(metrics_registry, SpecMetricsRegistry)

    def test_fixture_starts_fresh(self, metrics_registry):
        assert metrics_registry.metric_events == []

    def test_fixture_usable(self, metrics_registry):
        metrics_registry.increment_counter("requests")
        assert metrics_registry.get_counter_total("requests") == 1

    def test_fixture_service_name(self, metrics_registry):
        assert metrics_registry.service_name == "acgs2-specs"


class TestTracingContextFixture:
    def test_fixture_returns_class(self, tracing_context):
        # tracing_context fixture returns the TracingContext class itself
        assert tracing_context is TracingContext

    def test_fixture_can_instantiate_and_use(self, tracing_context):
        tc = tracing_context("test_op")
        with tc:
            pass

    def test_fixture_context_manager_works(self, tracing_context):
        with tracing_context("my_op") as span:
            span.set_attribute("key", "value")

    def test_fixture_multiple_instances_independent(self, tracing_context):
        tc1 = tracing_context("op1")
        tc2 = tracing_context("op2")
        # Both are valid context managers
        with tc1:
            pass
        with tc2:
            pass


# ===========================================================================
# Integration / cross-class scenarios
# ===========================================================================


class TestObservabilityIntegration:
    def test_budget_manager_full_workflow(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "auth", 2.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "deliberate", 18.0)
        mgr.record_measurement(Layer.LAYER3_POLICY, "policy_check", 9.0)
        mgr.record_measurement(Layer.LAYER4_AUDIT, "audit_log", 14.0)

        report = mgr.verify_budget_compliance()
        assert report["compliant"] is True
        assert report["total_measurements"] == 4

    def test_budget_violations_tracked_in_report(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "fast", 1.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "slow1", 20.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "slow2", 30.0)

        report = mgr.verify_budget_compliance()
        layer_key = Layer.LAYER1_VALIDATION.value
        assert report["layers"][layer_key]["violations"] == 2
        assert report["compliant"] is False

    def test_metrics_and_budget_manager_combined(self):
        mgr = SpecTimeoutBudgetManager()
        reg = SpecMetricsRegistry()

        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "auth", 3.0)
        reg.increment_counter("auth_requests")
        reg.record_latency("auth_latency", m.latency_ms)

        assert reg.get_counter_total("auth_requests") == 1
        events = reg.get_events_by_name("auth_latency")
        assert len(events) == 1
        assert events[0]["value"] == 3.0

    def test_percentile_after_many_measurements(self):
        mgr = SpecTimeoutBudgetManager()
        latencies = [float(i) for i in range(1, 101)]
        for lat in latencies:
            mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", lat)

        p50 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        p99 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 99)
        assert p50 is not None
        assert p99 is not None
        assert p50 <= p99

    def test_clear_and_restart_workflow(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.clear_measurements()

        report = mgr.verify_budget_compliance()
        assert report["total_measurements"] == 0
        assert report["compliant"] is True

    def test_tracing_context_usable(self):
        tc = TracingContext("integration_test")
        with tc as span:
            span.set_attribute("test", "value")

    def test_latency_measurement_to_dict_constitutional_hash_value(self):
        m = LatencyMeasurement(layer="l1", operation="op", latency_ms=2.0)
        d = m.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_spec_metrics_record_event_constitutional_hash(self):
        r = SpecMetricsRegistry()
        r.record_event("test_metric", 1.0, "gauge")
        assert r.metric_events[0]["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_budget_compliance_report_constitutional_hash(self):
        mgr = SpecTimeoutBudgetManager()
        report = mgr.verify_budget_compliance()
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_layer_all_four_covered_in_compliance_report(self):
        mgr = SpecTimeoutBudgetManager()
        for layer in Layer:
            mgr.record_measurement(layer, "op", 1.0)
        report = mgr.verify_budget_compliance()
        for layer in Layer:
            assert layer.value in report["layers"]

    def test_spec_metrics_default_service_vs_custom(self):
        default_r = SpecMetricsRegistry()
        custom_r = SpecMetricsRegistry(service_name="test-service")
        assert default_r.service_name == "acgs2-specs"
        assert custom_r.service_name == "test-service"

    def test_measurements_preserved_across_operations(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op1", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "op2", 5.0)

        all_layer1 = mgr.get_measurements_by_layer(Layer.LAYER1_VALIDATION)
        all_layer2 = mgr.get_measurements_by_layer(Layer.LAYER2_DELIBERATION)
        assert len(all_layer1) == 1
        assert len(all_layer2) == 1

    def test_budget_manager_only_counts_violations_not_all(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "ok1", 1.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "ok2", 2.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "bad", 100.0)

        violations = mgr.get_budget_violations()
        assert len(violations) == 1
        assert violations[0].within_budget is False
