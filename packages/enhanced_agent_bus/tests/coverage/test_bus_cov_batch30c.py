"""
Coverage tests for observability fixtures, chaos extension, and JSON utilities.
Constitutional Hash: 608508a9bd224290

Targets:
  - packages/enhanced_agent_bus/specs/fixtures/observability.py (68.6% -> ~95%)
  - packages/enhanced_agent_bus/_ext_chaos.py (22.2% -> ~95%)
  - src/core/shared/json_utils.py (55.6% -> ~95%)
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Section 1: Observability fixtures
# ---------------------------------------------------------------------------
from enhanced_agent_bus.specs.fixtures.observability import (
    _OBSERVABILITY_AVAILABLE,
    LatencyMeasurement,
    Layer,
    LayerTimeoutBudget,
    MetricsRegistry,
    SpecMetricsRegistry,
    SpecTimeoutBudgetManager,
    TimeoutBudgetManager,
    TracingContext,
)


class TestLayerEnum:
    """Tests for the Layer enum (real or fallback)."""

    def test_layer_has_four_members(self):
        members = list(Layer)
        assert len(members) == 4

    def test_layer1_validation_value(self):
        assert Layer.LAYER1_VALIDATION.value == "layer1_validation"

    def test_layer2_deliberation_value(self):
        assert Layer.LAYER2_DELIBERATION.value == "layer2_deliberation"

    def test_layer3_policy_value(self):
        assert Layer.LAYER3_POLICY.value == "layer3_policy"

    def test_layer4_audit_value(self):
        assert Layer.LAYER4_AUDIT.value == "layer4_audit"

    def test_layer_is_enum(self):
        assert hasattr(Layer, "__members__")


class TestLayerTimeoutBudget:
    """Tests for LayerTimeoutBudget dataclass."""

    def test_default_soft_limit(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=5.0)
        assert b.soft_limit_pct == 0.8

    def test_default_strict_enforcement(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=5.0)
        assert b.strict_enforcement is True

    def test_custom_soft_limit(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER2_DELIBERATION, budget_ms=20.0, soft_limit_pct=0.5)
        assert b.soft_limit_pct == 0.5

    def test_custom_strict_enforcement(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER3_POLICY, budget_ms=10.0, strict_enforcement=False)
        assert b.strict_enforcement is False

    def test_budget_stores_layer(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER4_AUDIT, budget_ms=15.0)
        assert b.layer == Layer.LAYER4_AUDIT

    def test_budget_stores_ms(self):
        b = LayerTimeoutBudget(layer=Layer.LAYER1_VALIDATION, budget_ms=42.0)
        assert b.budget_ms == 42.0


class TestTimeoutBudgetManager:
    """Tests for TimeoutBudgetManager (real or fallback)."""

    def test_default_total_budget(self):
        mgr = TimeoutBudgetManager()
        assert mgr.total_budget_ms == 50.0

    def test_custom_total_budget(self):
        mgr = TimeoutBudgetManager(total_budget_ms=100.0)
        assert mgr.total_budget_ms == 100.0

    def test_get_layer_budget_validation(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER1_VALIDATION)
        assert isinstance(b, LayerTimeoutBudget)
        assert b.budget_ms == 5.0

    def test_get_layer_budget_deliberation(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER2_DELIBERATION)
        assert b.budget_ms == 20.0

    def test_get_layer_budget_policy(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER3_POLICY)
        assert b.budget_ms == 10.0

    def test_get_layer_budget_audit(self):
        mgr = TimeoutBudgetManager()
        b = mgr.get_layer_budget(Layer.LAYER4_AUDIT)
        assert b.budget_ms == 15.0

    def test_has_layer_budgets(self):
        mgr = TimeoutBudgetManager()
        # Real class uses layer_budgets attr, fallback uses _budgets
        if hasattr(mgr, "_budgets"):
            assert len(mgr._budgets) == 4
        elif hasattr(mgr, "layer_budgets"):
            assert len(mgr.layer_budgets) == 4
        else:
            # At minimum, get_layer_budget should work for all layers
            for layer in Layer:
                assert mgr.get_layer_budget(layer) is not None


class TestMetricsRegistry:
    """Tests for MetricsRegistry (real or fallback)."""

    def test_default_service_name(self):
        reg = MetricsRegistry()
        assert isinstance(reg.service_name, str)
        assert len(reg.service_name) > 0

    def test_custom_service_name(self):
        reg = MetricsRegistry(service_name="my-svc")
        assert reg.service_name == "my-svc"

    def test_increment_counter_does_not_raise(self):
        reg = MetricsRegistry()
        reg.increment_counter("req")
        # Real impl stores NoOpCounter objects; fallback stores ints
        assert "req" in reg._counters

    def test_increment_counter_twice_no_error(self):
        reg = MetricsRegistry()
        reg.increment_counter("req", 3)
        reg.increment_counter("req", 7)
        assert "req" in reg._counters

    def test_increment_counter_with_attributes(self):
        reg = MetricsRegistry()
        reg.increment_counter("req", 1, attributes={"env": "test"})
        assert "req" in reg._counters

    def test_record_latency_does_not_raise(self):
        reg = MetricsRegistry()
        reg.record_latency("lat", 1.5, attributes={"layer": "l1"})

    def test_counters_dict_exists(self):
        reg = MetricsRegistry()
        assert isinstance(reg._counters, dict)


class TestTracingContext:
    """Tests for TracingContext (real or fallback)."""

    def test_init_accepts_name(self):
        ctx = TracingContext("my-op")
        # Real class stores as .name, fallback as .operation_name
        has_name = hasattr(ctx, "name") or hasattr(ctx, "operation_name")
        assert has_name

    def test_context_manager_protocol(self):
        ctx = TracingContext("op")
        result = ctx.__enter__()
        assert result is not None
        ctx.__exit__(None, None, None)

    def test_with_statement(self):
        with TracingContext("op") as span:
            # Real returns NoOpSpan with set_attribute; fallback returns self
            if hasattr(span, "set_attribute"):
                span.set_attribute("key", "value")

    def test_enter_returns_span_like(self):
        with TracingContext("op") as span:
            assert span is not None

    def test_multiple_contexts(self):
        with TracingContext("op1") as s1:
            with TracingContext("op2") as s2:
                assert s1 is not None
                assert s2 is not None


class TestLatencyMeasurement:
    """Tests for LatencyMeasurement dataclass."""

    def test_basic_construction(self):
        m = LatencyMeasurement(layer="l1", operation="op", latency_ms=2.5)
        assert m.layer == "l1"
        assert m.operation == "op"
        assert m.latency_ms == 2.5
        assert m.within_budget is True
        assert m.budget_ms is None

    def test_timestamp_auto_populated(self):
        m = LatencyMeasurement(layer="l1", operation="op", latency_ms=1.0)
        assert isinstance(m.timestamp, datetime)

    def test_to_dict_keys(self):
        m = LatencyMeasurement(layer="l1", operation="op", latency_ms=1.0)
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

    def test_to_dict_values(self):
        m = LatencyMeasurement(
            layer="l1",
            operation="op",
            latency_ms=3.0,
            within_budget=False,
            budget_ms=2.0,
        )
        d = m.to_dict()
        assert d["layer"] == "l1"
        assert d["latency_ms"] == 3.0
        assert d["within_budget"] is False
        assert d["budget_ms"] == 2.0


class TestSpecTimeoutBudgetManager:
    """Tests for SpecTimeoutBudgetManager."""

    def test_inherits_timeout_budget_manager(self):
        mgr = SpecTimeoutBudgetManager()
        assert isinstance(mgr, TimeoutBudgetManager)

    def test_measurements_initially_empty(self):
        mgr = SpecTimeoutBudgetManager()
        assert mgr.measurements == []

    def test_record_measurement_within_budget(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 3.0)
        assert m.within_budget is True
        assert m.budget_ms == 5.0

    def test_record_measurement_exceeds_budget(self):
        mgr = SpecTimeoutBudgetManager()
        m = mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 999.0)
        assert m.within_budget is False

    def test_record_measurement_appended(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "a", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "b", 2.0)
        assert len(mgr.measurements) == 2

    def test_get_measurements_by_layer(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "a", 1.0)
        mgr.record_measurement(Layer.LAYER2_DELIBERATION, "b", 2.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "c", 3.0)
        result = mgr.get_measurements_by_layer(Layer.LAYER1_VALIDATION)
        assert len(result) == 2

    def test_get_measurements_by_layer_empty(self):
        mgr = SpecTimeoutBudgetManager()
        result = mgr.get_measurements_by_layer(Layer.LAYER4_AUDIT)
        assert result == []

    def test_get_budget_violations(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "ok", 3.0)
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "bad", 999.0)
        violations = mgr.get_budget_violations()
        assert len(violations) == 1
        assert violations[0].operation == "bad"

    def test_get_budget_violations_empty(self):
        mgr = SpecTimeoutBudgetManager()
        assert mgr.get_budget_violations() == []

    def test_calculate_percentile_no_data(self):
        mgr = SpecTimeoutBudgetManager()
        assert mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50) is None

    def test_calculate_percentile_single(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "a", 3.0)
        p50 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        assert p50 == 3.0

    def test_calculate_percentile_multiple(self):
        mgr = SpecTimeoutBudgetManager()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", v)
        p50 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 50)
        assert p50 is not None
        assert 2.0 <= p50 <= 4.0

    def test_calculate_percentile_99(self):
        mgr = SpecTimeoutBudgetManager()
        for v in range(1, 101):
            mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", float(v))
        p99 = mgr.calculate_percentile(Layer.LAYER1_VALIDATION, 99)
        assert p99 is not None
        assert p99 >= 90.0

    def test_verify_budget_compliance_all_compliant(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is True
        assert report["violations"] == 0
        assert "constitutional_hash" in report

    def test_verify_budget_compliance_with_violation(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "bad", 999.0)
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is False
        assert report["violations"] == 1

    def test_verify_budget_compliance_empty(self):
        mgr = SpecTimeoutBudgetManager()
        report = mgr.verify_budget_compliance()
        assert report["compliant"] is True
        assert report["total_measurements"] == 0

    def test_verify_budget_compliance_layer_report_fields(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 2.0)
        report = mgr.verify_budget_compliance()
        layer_report = report["layers"]["layer1_validation"]
        assert "count" in layer_report
        assert "violations" in layer_report
        assert "p50_ms" in layer_report
        assert "p99_ms" in layer_report
        assert "budget_ms" in layer_report
        assert "compliant" in layer_report

    def test_clear_measurements(self):
        mgr = SpecTimeoutBudgetManager()
        mgr.record_measurement(Layer.LAYER1_VALIDATION, "op", 1.0)
        mgr.clear_measurements()
        assert mgr.measurements == []

    def test_custom_total_budget_kwarg(self):
        mgr = SpecTimeoutBudgetManager(total_budget_ms=200.0)
        assert mgr.total_budget_ms == 200.0


class TestSpecMetricsRegistry:
    """Tests for SpecMetricsRegistry."""

    def test_inherits_metrics_registry(self):
        reg = SpecMetricsRegistry()
        assert isinstance(reg, MetricsRegistry)

    def test_default_service_name(self):
        reg = SpecMetricsRegistry()
        assert reg.service_name == "acgs2-specs"

    def test_events_initially_empty(self):
        reg = SpecMetricsRegistry()
        assert reg.metric_events == []

    def test_increment_counter_records_event(self):
        reg = SpecMetricsRegistry()
        reg.increment_counter("req")
        assert len(reg.metric_events) == 1
        assert reg.metric_events[0]["type"] == "counter"

    def test_record_latency_records_event(self):
        reg = SpecMetricsRegistry()
        reg.record_latency("lat", 5.0)
        assert len(reg.metric_events) == 1
        assert reg.metric_events[0]["type"] == "histogram"

    def test_record_event_fields(self):
        reg = SpecMetricsRegistry()
        reg.record_event("metric", 42.0, "gauge", {"env": "test"})
        ev = reg.metric_events[0]
        assert ev["metric_name"] == "metric"
        assert ev["value"] == 42.0
        assert ev["type"] == "gauge"
        assert ev["attributes"] == {"env": "test"}
        assert "timestamp" in ev
        assert "constitutional_hash" in ev

    def test_record_event_default_attributes(self):
        reg = SpecMetricsRegistry()
        reg.record_event("metric", 1.0, "counter")
        assert reg.metric_events[0]["attributes"] == {}

    def test_get_events_by_name(self):
        reg = SpecMetricsRegistry()
        reg.increment_counter("a")
        reg.increment_counter("b")
        reg.increment_counter("a")
        assert len(reg.get_events_by_name("a")) == 2

    def test_get_events_by_name_empty(self):
        reg = SpecMetricsRegistry()
        assert reg.get_events_by_name("nonexistent") == []

    def test_get_counter_total(self):
        reg = SpecMetricsRegistry()
        reg.increment_counter("req", 3)
        reg.increment_counter("req", 7)
        assert reg.get_counter_total("req") == 10

    def test_get_counter_total_zero(self):
        reg = SpecMetricsRegistry()
        assert reg.get_counter_total("nope") == 0

    def test_clear_events(self):
        reg = SpecMetricsRegistry()
        reg.increment_counter("a")
        reg.clear_events()
        assert reg.metric_events == []

    def test_increment_also_updates_base_counters(self):
        reg = SpecMetricsRegistry()
        reg.increment_counter("req", 5)
        assert "req" in reg._counters

    def test_record_latency_with_attributes(self):
        reg = SpecMetricsRegistry()
        reg.record_latency("lat", 2.0, attributes={"layer": "l1"})
        ev = reg.metric_events[0]
        assert ev["attributes"] == {"layer": "l1"}


# ---------------------------------------------------------------------------
# Section 2: Chaos extension module
# ---------------------------------------------------------------------------
import enhanced_agent_bus._ext_chaos as ext_chaos


class TestExtChaos:
    """Tests for _ext_chaos module."""

    def test_module_has_availability_flag(self):
        assert hasattr(ext_chaos, "CHAOS_ENGINEERING_AVAILABLE")
        assert isinstance(ext_chaos.CHAOS_ENGINEERING_AVAILABLE, bool)

    def test_ext_all_list_exists(self):
        assert hasattr(ext_chaos, "_EXT_ALL")
        assert isinstance(ext_chaos._EXT_ALL, list)
        assert len(ext_chaos._EXT_ALL) > 0

    def test_all_ext_all_names_are_accessible(self):
        for name in ext_chaos._EXT_ALL:
            assert hasattr(ext_chaos, name), f"{name} not found on _ext_chaos"

    def test_chaos_experiment_attr(self):
        assert hasattr(ext_chaos, "ChaosExperiment")

    def test_cpu_stress_scenario_attr(self):
        assert hasattr(ext_chaos, "CPUStressScenario")

    def test_dependency_failure_scenario_attr(self):
        assert hasattr(ext_chaos, "DependencyFailureScenario")

    def test_experiment_phase_attr(self):
        assert hasattr(ext_chaos, "ExperimentPhase")

    def test_experiment_result_attr(self):
        assert hasattr(ext_chaos, "ExperimentResult")

    def test_experiment_status_attr(self):
        assert hasattr(ext_chaos, "ExperimentStatus")

    def test_latency_injection_scenario_attr(self):
        assert hasattr(ext_chaos, "LatencyInjectionScenario")

    def test_memory_pressure_scenario_attr(self):
        assert hasattr(ext_chaos, "MemoryPressureScenario")

    def test_in_memory_metric_collector_attr(self):
        assert hasattr(ext_chaos, "InMemoryMetricCollector")

    def test_network_partition_scenario_attr(self):
        assert hasattr(ext_chaos, "NetworkPartitionScenario")

    def test_scenario_executor_attr(self):
        assert hasattr(ext_chaos, "ScenarioExecutor")

    def test_scenario_status_attr(self):
        assert hasattr(ext_chaos, "ScenarioStatus")

    def test_steady_state_hypothesis_attr(self):
        assert hasattr(ext_chaos, "SteadyStateHypothesis")

    def test_steady_state_validator_attr(self):
        assert hasattr(ext_chaos, "SteadyStateValidator")

    def test_validation_metric_attr(self):
        assert hasattr(ext_chaos, "ValidationMetric")

    def test_chaos_validation_result_attr(self):
        assert hasattr(ext_chaos, "ChaosValidationResult")

    def test_get_experiment_registry_attr(self):
        assert hasattr(ext_chaos, "get_experiment_registry")

    def test_reset_experiment_registry_attr(self):
        assert hasattr(ext_chaos, "reset_experiment_registry")


class TestExtChaosAvailableBranch:
    """Test behavior depending on availability."""

    @pytest.mark.skipif(
        not ext_chaos.CHAOS_ENGINEERING_AVAILABLE,
        reason="chaos module not available",
    )
    def test_real_classes_are_not_object(self):
        assert ext_chaos.ChaosExperiment is not object
        assert ext_chaos.ExperimentPhase is not object

    @pytest.mark.skipif(
        ext_chaos.CHAOS_ENGINEERING_AVAILABLE,
        reason="chaos module IS available",
    )
    def test_fallback_classes_are_object(self):
        assert ext_chaos.ChaosExperiment is object
        assert ext_chaos.CPUStressScenario is object
        assert ext_chaos.DependencyFailureScenario is object
        assert ext_chaos.ExperimentPhase is object
        assert ext_chaos.ExperimentResult is object
        assert ext_chaos.ExperimentStatus is object
        assert ext_chaos.LatencyInjectionScenario is object
        assert ext_chaos.MemoryPressureScenario is object
        assert ext_chaos.InMemoryMetricCollector is object
        assert ext_chaos.NetworkPartitionScenario is object
        assert ext_chaos.ScenarioExecutor is object
        assert ext_chaos.ScenarioStatus is object
        assert ext_chaos.SteadyStateHypothesis is object
        assert ext_chaos.SteadyStateValidator is object
        assert ext_chaos.ValidationMetric is object
        assert ext_chaos.ChaosValidationResult is object
        assert ext_chaos.chaos_experiment is object
        assert ext_chaos.get_experiment_registry is object
        assert ext_chaos.reset_experiment_registry is object

    @pytest.mark.skipif(
        not ext_chaos.CHAOS_ENGINEERING_AVAILABLE,
        reason="chaos module not available",
    )
    def test_chaos_constitutional_hash_present(self):
        assert hasattr(ext_chaos, "CHAOS_CONSTITUTIONAL_HASH")


# ---------------------------------------------------------------------------
# Section 3: JSON utilities
# ---------------------------------------------------------------------------
from enhanced_agent_bus._compat.json_utils import (
    dump_bytes,
    dump_compact,
    dump_pretty,
    dumps,
    loads,
)


class TestJsonDumps:
    """Tests for json_utils.dumps."""

    def test_dumps_empty_dict(self):
        result = dumps({})
        assert result == "{}"

    def test_dumps_simple_dict(self):
        result = dumps({"key": "val"})
        parsed = json.loads(result)
        assert parsed == {"key": "val"}

    def test_dumps_nested_dict(self):
        obj = {"a": {"b": [1, 2, 3]}}
        result = dumps(obj)
        assert json.loads(result) == obj

    def test_dumps_list(self):
        result = dumps([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_dumps_string(self):
        result = dumps("hello")
        assert json.loads(result) == "hello"

    def test_dumps_number(self):
        result = dumps(42)
        assert json.loads(result) == 42

    def test_dumps_boolean(self):
        result = dumps(True)
        assert json.loads(result)

    def test_dumps_null(self):
        result = dumps(None)
        assert json.loads(result) is None

    def test_dumps_returns_str(self):
        assert isinstance(dumps({}), str)

    def test_dumps_with_default_kwarg(self):
        class Custom:
            pass

        result = dumps({"c": Custom()}, default=lambda x: "custom")
        parsed = json.loads(result)
        assert parsed["c"] == "custom"

    def test_dumps_non_serializable_falls_back(self):
        """Non-serializable objects should use str() fallback."""
        result = dumps({"s": {1, 2, 3}})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert "s" in parsed

    def test_dumps_unicode(self):
        result = dumps({"emoji": "hello"})
        parsed = json.loads(result)
        assert parsed["emoji"] == "hello"

    def test_dumps_empty_list(self):
        assert dumps([]) == "[]"

    def test_dumps_float(self):
        result = dumps(3.14)
        assert abs(json.loads(result) - 3.14) < 0.001


class TestJsonLoads:
    """Tests for json_utils.loads."""

    def test_loads_dict_from_str(self):
        result = loads('{"key": "val"}')
        assert result == {"key": "val"}

    def test_loads_dict_from_bytes(self):
        result = loads(b'{"key": "val"}')
        assert result == {"key": "val"}

    def test_loads_list(self):
        result = loads("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_loads_string(self):
        result = loads('"hello"')
        assert result == "hello"

    def test_loads_number(self):
        result = loads("42")
        assert result == 42

    def test_loads_null(self):
        result = loads("null")
        assert result is None

    def test_loads_boolean(self):
        result = loads("true")
        assert result is True

    def test_loads_nested(self):
        s = '{"a": {"b": [1, 2]}}'
        result = loads(s)
        assert result == {"a": {"b": [1, 2]}}

    def test_loads_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            loads("{invalid")

    def test_loads_empty_object(self):
        assert loads("{}") == {}

    def test_loads_empty_list(self):
        assert loads("[]") == []

    def test_loads_unicode(self):
        result = loads('{"k": "hello"}')
        assert result["k"] == "hello"


class TestDumpBytes:
    """Tests for json_utils.dump_bytes."""

    def test_returns_bytes(self):
        result = dump_bytes({"a": 1})
        assert isinstance(result, bytes)

    def test_valid_json(self):
        result = dump_bytes({"key": "val"})
        parsed = json.loads(result)
        assert parsed == {"key": "val"}

    def test_empty_dict(self):
        result = dump_bytes({})
        assert json.loads(result) == {}

    def test_list(self):
        result = dump_bytes([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]


class TestDumpCompact:
    """Tests for json_utils.dump_compact."""

    def test_returns_str(self):
        result = dump_compact({"a": 1})
        assert isinstance(result, str)

    def test_no_extra_whitespace(self):
        result = dump_compact({"a": 1, "b": 2})
        # Compact format should have no spaces after separators
        assert "  " not in result

    def test_valid_json(self):
        result = dump_compact({"key": "val"})
        parsed = json.loads(result)
        assert parsed == {"key": "val"}

    def test_empty_dict(self):
        result = dump_compact({})
        assert json.loads(result) == {}


class TestDumpPretty:
    """Tests for json_utils.dump_pretty."""

    def test_returns_str(self):
        result = dump_pretty({"a": 1})
        assert isinstance(result, str)

    def test_contains_newlines(self):
        result = dump_pretty({"a": 1})
        assert "\n" in result

    def test_default_indent_2(self):
        result = dump_pretty({"a": 1})
        # With indent=2, lines should start with 2-space indentation
        assert "  " in result

    def test_custom_indent(self):
        result = dump_pretty({"a": 1}, indent=4)
        assert "    " in result

    def test_valid_json(self):
        result = dump_pretty({"key": "val"})
        parsed = json.loads(result)
        assert parsed == {"key": "val"}

    def test_empty_dict(self):
        result = dump_pretty({})
        assert json.loads(result) == {}


class TestJsonRoundtrip:
    """Roundtrip tests for dumps/loads."""

    @pytest.mark.parametrize(
        "obj",
        [
            {},
            {"a": 1},
            [1, 2, 3],
            "hello",
            42,
            3.14,
            True,
            None,
            {"nested": {"deep": [1, {"x": "y"}]}},
        ],
    )
    def test_roundtrip(self, obj):
        assert loads(dumps(obj)) == obj

    def test_bytes_roundtrip(self):
        obj = {"key": "value", "num": 42}
        result = dump_bytes(obj)
        assert loads(result) == obj
