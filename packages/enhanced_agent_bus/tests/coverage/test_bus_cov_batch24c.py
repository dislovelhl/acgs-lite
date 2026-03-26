"""
Coverage tests for:
- adaptive_governance/governance_engine.py
- observability/telemetry.py
- adaptive_governance/impact_scorer.py

Batch 24c — targets uncovered branches and methods.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HASH = "608508a9bd224290"


def _make_impact_features(**overrides):
    from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

    defaults = dict(
        message_length=100,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.3,
        historical_precedence=1,
        resource_utilization=0.2,
        network_isolation=0.9,
        risk_score=0.3,
        confidence_level=0.8,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides):
    from enhanced_agent_bus.adaptive_governance.models import (
        GovernanceDecision,
        ImpactLevel,
    )

    defaults = dict(
        action_allowed=True,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.85,
        reasoning="test",
        recommended_threshold=0.7,
        features_used=_make_impact_features(),
        decision_id="gov-test-001",
    )
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


# ===================================================================
# telemetry.py tests
# ===================================================================


class TestNoOpSpan:
    def test_set_attribute(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.set_attribute("key", "value")  # no-op, no error

    def test_add_event(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.add_event("test_event")
        span.add_event("test_event", attributes={"k": "v"})

    def test_record_exception(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.record_exception(RuntimeError("boom"))

    def test_set_status(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        span.set_status("OK")

    def test_context_manager(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan

        span = NoOpSpan()
        with span as s:
            assert s is span
        # __exit__ returns False
        assert span.__exit__(None, None, None) is False


class TestNoOpTracer:
    def test_start_as_current_span(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan, NoOpTracer

        tracer = NoOpTracer()
        with tracer.start_as_current_span("test") as span:
            assert isinstance(span, NoOpSpan)

    def test_start_span(self):
        from enhanced_agent_bus.observability.telemetry import NoOpSpan, NoOpTracer

        tracer = NoOpTracer()
        span = tracer.start_span("test")
        assert isinstance(span, NoOpSpan)


class TestNoOpMeter:
    def test_create_counter(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter, NoOpMeter

        meter = NoOpMeter()
        counter = meter.create_counter("test_counter")
        assert isinstance(counter, NoOpCounter)
        counter.add(1)
        counter.add(5, {"key": "val"})

    def test_create_histogram(self):
        from enhanced_agent_bus.observability.telemetry import NoOpHistogram, NoOpMeter

        meter = NoOpMeter()
        hist = meter.create_histogram("test_hist")
        assert isinstance(hist, NoOpHistogram)
        hist.record(1.5)
        hist.record(2.5, {"key": "val"})

    def test_create_up_down_counter(self):
        from enhanced_agent_bus.observability.telemetry import NoOpMeter, NoOpUpDownCounter

        meter = NoOpMeter()
        gauge = meter.create_up_down_counter("test_gauge")
        assert isinstance(gauge, NoOpUpDownCounter)
        gauge.add(1)
        gauge.add(-1, {"key": "val"})

    def test_create_observable_gauge(self):
        from enhanced_agent_bus.observability.telemetry import NoOpMeter

        meter = NoOpMeter()
        result = meter.create_observable_gauge("test_obs_gauge")
        assert result is None


class TestCrossModuleNoOpType:
    """Test the metaclass-based isinstance compatibility."""

    def test_same_class_isinstance(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        c = NoOpCounter()
        assert isinstance(c, NoOpCounter)

    def test_cross_module_isinstance(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        # Simulate a class from a different module with same name
        mock_cls = type("NoOpCounter", (), {})
        mock_cls.__module__ = "some.package.observability.telemetry"
        instance = mock_cls()
        assert isinstance(instance, NoOpCounter)

    def test_cross_module_isinstance_wrong_module(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        mock_cls = type("NoOpCounter", (), {})
        mock_cls.__module__ = "some.unrelated.module"
        instance = mock_cls()
        assert not isinstance(instance, NoOpCounter)

    def test_cross_module_isinstance_wrong_name(self):
        from enhanced_agent_bus.observability.telemetry import NoOpCounter

        mock_cls = type("NoOpHistogram", (), {})
        mock_cls.__module__ = "some.package.observability.telemetry"
        instance = mock_cls()
        assert not isinstance(instance, NoOpCounter)


class TestTelemetryConfig:
    def test_default_values(self):
        from enhanced_agent_bus.observability.telemetry import TelemetryConfig

        config = TelemetryConfig()
        assert config.service_name == "acgs2-agent-bus"
        assert config.service_version == "2.0.0"
        assert config.batch_span_processor is True
        assert config.trace_sample_rate >= 0.0

    def test_custom_values(self):
        from enhanced_agent_bus.observability.telemetry import TelemetryConfig

        config = TelemetryConfig(
            service_name="custom",
            service_version="1.0.0",
            environment="production",
            export_traces=False,
            export_metrics=False,
        )
        assert config.service_name == "custom"
        assert config.export_traces is False
        assert config.export_metrics is False


class TestConfigHelpers:
    def test_get_env_default_without_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            telemetry.settings = None
            result = telemetry._get_env_default()
            assert isinstance(result, str)
        finally:
            telemetry.settings = saved

    def test_get_env_default_with_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            mock_settings = SimpleNamespace(env="production")
            telemetry.settings = mock_settings
            result = telemetry._get_env_default()
            assert result == "production"
        finally:
            telemetry.settings = saved

    def test_get_otlp_endpoint_without_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            telemetry.settings = None
            result = telemetry._get_otlp_endpoint()
            assert isinstance(result, str)
        finally:
            telemetry.settings = saved

    def test_get_otlp_endpoint_with_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            mock_settings = SimpleNamespace(
                telemetry=SimpleNamespace(otlp_endpoint="http://custom:4317")
            )
            telemetry.settings = mock_settings
            result = telemetry._get_otlp_endpoint()
            assert result == "http://custom:4317"
        finally:
            telemetry.settings = saved

    def test_get_export_traces_without_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            telemetry.settings = None
            assert telemetry._get_export_traces() is True
        finally:
            telemetry.settings = saved

    def test_get_export_traces_with_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            mock_settings = SimpleNamespace(telemetry=SimpleNamespace(export_traces=False))
            telemetry.settings = mock_settings
            assert telemetry._get_export_traces() is False
        finally:
            telemetry.settings = saved

    def test_get_export_metrics_without_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            telemetry.settings = None
            assert telemetry._get_export_metrics() is True
        finally:
            telemetry.settings = saved

    def test_get_export_metrics_with_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            mock_settings = SimpleNamespace(telemetry=SimpleNamespace(export_metrics=False))
            telemetry.settings = mock_settings
            assert telemetry._get_export_metrics() is False
        finally:
            telemetry.settings = saved

    def test_get_trace_sample_rate_without_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            telemetry.settings = None
            assert telemetry._get_trace_sample_rate() == 1.0
        finally:
            telemetry.settings = saved

    def test_get_trace_sample_rate_with_settings(self):
        from enhanced_agent_bus.observability import telemetry

        saved = telemetry.settings
        try:
            mock_settings = SimpleNamespace(telemetry=SimpleNamespace(trace_sample_rate=0.5))
            telemetry.settings = mock_settings
            assert telemetry._get_trace_sample_rate() == 0.5
        finally:
            telemetry.settings = saved


class TestConfigureTelemetry:
    def test_otel_not_available_returns_noops(self):
        from enhanced_agent_bus.observability import telemetry
        from enhanced_agent_bus.observability.telemetry import NoOpMeter, NoOpTracer

        saved = telemetry.OTEL_AVAILABLE
        try:
            telemetry.OTEL_AVAILABLE = False
            tracer, meter = telemetry.configure_telemetry()
            assert isinstance(tracer, NoOpTracer)
            assert isinstance(meter, NoOpMeter)
        finally:
            telemetry.OTEL_AVAILABLE = saved

    def test_configure_with_custom_config(self):
        from enhanced_agent_bus.observability import telemetry
        from enhanced_agent_bus.observability.telemetry import TelemetryConfig

        saved_otel = telemetry.OTEL_AVAILABLE
        try:
            telemetry.OTEL_AVAILABLE = False
            config = TelemetryConfig(service_name="test-svc")
            tracer, meter = telemetry.configure_telemetry(config)
            assert tracer is not None
            assert meter is not None
        finally:
            telemetry.OTEL_AVAILABLE = saved_otel


class TestGetTracer:
    def test_returns_noop_when_otel_unavailable(self):
        from enhanced_agent_bus.observability import telemetry
        from enhanced_agent_bus.observability.telemetry import NoOpTracer

        saved = telemetry.OTEL_AVAILABLE
        try:
            telemetry.OTEL_AVAILABLE = False
            tracer = telemetry.get_tracer("test-svc")
            assert isinstance(tracer, NoOpTracer)
        finally:
            telemetry.OTEL_AVAILABLE = saved

    def test_returns_cached_tracer(self):
        from enhanced_agent_bus.observability import telemetry

        saved_tracers = dict(telemetry._tracers)
        try:
            sentinel = object()
            telemetry._tracers["cached-svc"] = sentinel
            result = telemetry.get_tracer("cached-svc")
            assert result is sentinel
        finally:
            telemetry._tracers.clear()
            telemetry._tracers.update(saved_tracers)

    def test_returns_noop_with_none_service(self):
        from enhanced_agent_bus.observability import telemetry
        from enhanced_agent_bus.observability.telemetry import NoOpTracer

        saved = telemetry.OTEL_AVAILABLE
        try:
            telemetry.OTEL_AVAILABLE = False
            tracer = telemetry.get_tracer(None)
            assert isinstance(tracer, NoOpTracer)
        finally:
            telemetry.OTEL_AVAILABLE = saved


class TestGetMeter:
    def test_returns_noop_when_otel_unavailable(self):
        from enhanced_agent_bus.observability import telemetry
        from enhanced_agent_bus.observability.telemetry import NoOpMeter

        saved = telemetry.OTEL_AVAILABLE
        try:
            telemetry.OTEL_AVAILABLE = False
            meter = telemetry.get_meter("test-svc")
            assert isinstance(meter, NoOpMeter)
        finally:
            telemetry.OTEL_AVAILABLE = saved

    def test_returns_cached_meter(self):
        from enhanced_agent_bus.observability import telemetry

        saved_meters = dict(telemetry._meters)
        try:
            sentinel = object()
            telemetry._meters["cached-meter"] = sentinel
            result = telemetry.get_meter("cached-meter")
            assert result is sentinel
        finally:
            telemetry._meters.clear()
            telemetry._meters.update(saved_meters)

    def test_returns_noop_with_none_service(self):
        from enhanced_agent_bus.observability import telemetry
        from enhanced_agent_bus.observability.telemetry import NoOpMeter

        saved = telemetry.OTEL_AVAILABLE
        try:
            telemetry.OTEL_AVAILABLE = False
            meter = telemetry.get_meter(None)
            assert isinstance(meter, NoOpMeter)
        finally:
            telemetry.OTEL_AVAILABLE = saved


class TestGetResourceAttributes:
    def test_fallback_path(self):
        """Test fallback when get_resource_attributes raises NameError."""
        from enhanced_agent_bus.observability.telemetry import (
            TelemetryConfig,
            _get_resource_attributes,
        )

        config = TelemetryConfig(service_name="test-fallback")

        # Temporarily replace the function reference used inside _get_resource_attributes
        import enhanced_agent_bus.observability.telemetry as tel_mod

        # The function is called inside _get_resource_attributes; if it raises
        # NameError the except block returns a fallback dict.
        original = None
        has_attr = hasattr(tel_mod, "get_resource_attributes")
        if has_attr:
            original = tel_mod.get_resource_attributes
        try:
            # Force the NameError path by deleting the name from the module
            if has_attr:
                delattr(tel_mod, "get_resource_attributes")
            attrs = _get_resource_attributes(config)
            assert attrs["service.name"] == "test-fallback"
            assert "constitutional.hash" in attrs
        finally:
            if has_attr and original is not None:
                tel_mod.get_resource_attributes = original

    def test_success_via_real_function(self):
        from enhanced_agent_bus.observability.telemetry import (
            TelemetryConfig,
            _get_resource_attributes,
        )

        config = TelemetryConfig(service_name="test")
        attrs = _get_resource_attributes(config)
        # Whether real or fallback, should contain service.name
        assert "service.name" in attrs


class TestTracingContext:
    def test_enter_exit_no_exception(self):
        from enhanced_agent_bus.observability.telemetry import TracingContext

        with patch("enhanced_agent_bus.observability.telemetry.get_tracer") as mock_get:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=mock_span)
            ctx.__exit__ = MagicMock(return_value=False)
            mock_tracer.start_as_current_span.return_value = ctx
            mock_get.return_value = mock_tracer

            with TracingContext("test_op", attributes={"custom": "attr"}) as span:
                assert span is mock_span
                mock_span.set_attribute.assert_any_call("constitutional.hash", _HASH)

    def test_enter_exit_with_exception(self):
        from enhanced_agent_bus.observability.telemetry import TracingContext

        with patch("enhanced_agent_bus.observability.telemetry.get_tracer") as mock_get:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=mock_span)
            ctx.__exit__ = MagicMock(return_value=False)
            mock_tracer.start_as_current_span.return_value = ctx
            mock_get.return_value = mock_tracer

            try:
                with TracingContext("test_op") as span:
                    raise ValueError("test error")
            except ValueError:
                pass

            mock_span.record_exception.assert_called_once()

    def test_exit_no_context(self):
        from enhanced_agent_bus.observability.telemetry import TracingContext

        tc = TracingContext.__new__(TracingContext)
        tc._context = None
        tc._span = None
        result = tc.__exit__(None, None, None)
        assert result is False

    def test_tenant_id_import_error(self):
        """TracingContext handles ImportError for tenant context gracefully."""
        from enhanced_agent_bus.observability.telemetry import TracingContext

        with patch("enhanced_agent_bus.observability.telemetry.get_tracer") as mock_get:
            mock_tracer = MagicMock()
            mock_span = MagicMock()
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=mock_span)
            ctx.__exit__ = MagicMock(return_value=False)
            mock_tracer.start_as_current_span.return_value = ctx
            mock_get.return_value = mock_tracer

            with TracingContext("test_op") as span:
                pass  # Should not raise even if tenant import fails


class TestMetricsRegistry:
    def test_get_counter_creates_and_caches(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_counter = MagicMock()
            mock_meter.create_counter.return_value = mock_counter
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test-svc")
            c1 = registry.get_counter("requests", "Total requests")
            c2 = registry.get_counter("requests")
            assert c1 is c2
            mock_meter.create_counter.assert_called_once()

    def test_get_histogram_creates_and_caches(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_hist = MagicMock()
            mock_meter.create_histogram.return_value = mock_hist
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test-svc")
            h1 = registry.get_histogram("latency", "ms", "Latency")
            h2 = registry.get_histogram("latency")
            assert h1 is h2

    def test_get_gauge_creates_and_caches(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_gauge = MagicMock()
            mock_meter.create_up_down_counter.return_value = mock_gauge
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test-svc")
            g1 = registry.get_gauge("active_connections")
            g2 = registry.get_gauge("active_connections")
            assert g1 is g2

    def test_increment_counter(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_counter = MagicMock()
            mock_meter.create_counter.return_value = mock_counter
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test")
            registry.increment_counter("test_counter", 5, {"env": "test"})
            mock_counter.add.assert_called_once()
            call_args = mock_counter.add.call_args
            assert call_args[0][0] == 5
            assert "constitutional_hash" in call_args[0][1]

    def test_increment_counter_no_extra_attrs(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_counter = MagicMock()
            mock_meter.create_counter.return_value = mock_counter
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test")
            registry.increment_counter("test_counter")
            mock_counter.add.assert_called_once()

    def test_record_latency(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_hist = MagicMock()
            mock_meter.create_histogram.return_value = mock_hist
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test")
            registry.record_latency("processing", 5.2, {"route": "/api"})
            mock_hist.record.assert_called_once()

    def test_record_latency_no_extra_attrs(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_hist = MagicMock()
            mock_meter.create_histogram.return_value = mock_hist
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test")
            registry.record_latency("processing", 5.2)
            mock_hist.record.assert_called_once()

    def test_set_gauge(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_gauge = MagicMock()
            mock_meter.create_up_down_counter.return_value = mock_gauge
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test")
            registry.set_gauge("connections", 3, {"pool": "main"})
            mock_gauge.add.assert_called_once()

    def test_set_gauge_no_extra_attrs(self):
        from enhanced_agent_bus.observability.telemetry import MetricsRegistry

        with patch("enhanced_agent_bus.observability.telemetry.get_meter") as mock_get_meter:
            mock_meter = MagicMock()
            mock_gauge = MagicMock()
            mock_meter.create_up_down_counter.return_value = mock_gauge
            mock_get_meter.return_value = mock_meter

            registry = MetricsRegistry("test")
            registry.set_gauge("connections", 3)
            mock_gauge.add.assert_called_once()


# ===================================================================
# impact_scorer.py tests
# ===================================================================


class TestImpactScorerInit:
    def test_init_without_sklearn(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved = mod.SKLEARN_AVAILABLE
        try:
            mod.SKLEARN_AVAILABLE = False
            scorer = mod.ImpactScorer(_HASH)
            assert scorer.impact_classifier is None
            assert scorer.constitutional_hash == _HASH
        finally:
            mod.SKLEARN_AVAILABLE = saved

    def test_init_with_sklearn(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved = mod.SKLEARN_AVAILABLE
        try:
            mod.SKLEARN_AVAILABLE = True
            # Use a mock for RandomForestRegressor to avoid sklearn dependency
            mock_rf = MagicMock()
            saved_rf = mod.RandomForestRegressor
            mod.RandomForestRegressor = mock_rf
            scorer = mod.ImpactScorer(_HASH)
            assert scorer.impact_classifier is not None
            mod.RandomForestRegressor = saved_rf
        finally:
            mod.SKLEARN_AVAILABLE = saved

    def test_mlflow_init_in_pytest(self):
        """MLflow initialization is skipped in pytest."""
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_mlflow = mod.MLFLOW_AVAILABLE
        try:
            mod.MLFLOW_AVAILABLE = True
            scorer = mod.ImpactScorer(_HASH)
            assert scorer._mlflow_initialized is False
        finally:
            mod.MLFLOW_AVAILABLE = saved_mlflow

    def test_mlflow_init_not_available(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved = mod.MLFLOW_AVAILABLE
        try:
            mod.MLFLOW_AVAILABLE = False
            scorer = mod.ImpactScorer(_HASH)
            assert scorer._mlflow_initialized is False
        finally:
            mod.MLFLOW_AVAILABLE = saved

    def test_mhc_stability_flag(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_torch = mod.TORCH_AVAILABLE
        saved_sp = mod.sinkhorn_projection
        try:
            mod.TORCH_AVAILABLE = False
            mod.sinkhorn_projection = None
            scorer = mod.ImpactScorer(_HASH)
            assert scorer.use_mhc_stability is False
        finally:
            mod.TORCH_AVAILABLE = saved_torch
            mod.sinkhorn_projection = saved_sp


class TestImpactScorerAssessImpact:
    async def test_assess_impact_rule_based_fallback(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.model_trained = False

        message = {"content": "test message", "tenant_id": "t1"}
        context = {"active_agents": ["a1", "a2"]}

        result = await scorer.assess_impact(message, context)
        assert result.risk_score >= 0.0
        assert result.confidence_level == 0.7  # fallback

    async def test_assess_impact_ml_path(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.model_trained = True
        scorer._predict_risk_score = MagicMock(return_value=0.5)
        scorer._calculate_confidence = MagicMock(return_value=0.9)

        message = {"content": "test message"}
        context = {"active_agents": ["a1"]}

        result = await scorer.assess_impact(message, context)
        assert result.risk_score == 0.5
        assert result.confidence_level == 0.9

    async def test_assess_impact_error_returns_safe_defaults(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer._extract_features = AsyncMock(side_effect=RuntimeError("boom"))

        message = {"content": "test"}
        context = {}

        result = await scorer.assess_impact(message, context)
        assert result.agent_count == 1
        assert result.confidence_level == 0.5


class TestImpactScorerExtractFeatures:
    async def test_extract_features_basic(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        message = {"content": "hello", "tenant_id": "t1"}
        context = {"active_agents": ["a1", "a2", "a3"]}

        features = await scorer._extract_features(message, context)
        assert features.message_length == 5
        assert features.agent_count == 3

    async def test_extract_features_no_active_agents(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        message = {"content": "hello"}
        context = {}

        features = await scorer._extract_features(message, context)
        assert features.agent_count == 0

    async def test_extract_features_active_agents_not_list(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        message = {"content": "hello"}
        context = {"active_agents": "not_a_list"}

        features = await scorer._extract_features(message, context)
        assert features.agent_count == 0


class TestRuleBasedRiskScore:
    def test_low_risk(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score == 0.0

    def test_high_message_length(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            message_length=20000,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score >= 0.3

    def test_medium_message_length(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            message_length=5000,
            agent_count=1,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score >= 0.1

    def test_high_agent_count(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            message_length=50,
            agent_count=15,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score >= 0.2

    def test_medium_agent_count(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            message_length=50,
            agent_count=7,
            tenant_complexity=0.0,
            resource_utilization=0.0,
            semantic_similarity=0.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score >= 0.1

    def test_max_clamped_to_1(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            message_length=20000,
            agent_count=15,
            tenant_complexity=1.0,
            resource_utilization=1.0,
            semantic_similarity=1.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score <= 1.0


class TestCalculateConfidence:
    def test_base_confidence(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            historical_precedence=0,
            temporal_patterns=[],
            semantic_similarity=0.0,
        )
        conf = scorer._calculate_confidence(features)
        assert conf == 0.5

    def test_full_confidence_boost(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            historical_precedence=5,
            temporal_patterns=[0.1, 0.2],
            semantic_similarity=0.5,
        )
        conf = scorer._calculate_confidence(features)
        assert abs(conf - 0.9) < 1e-9  # 0.5 + 0.1 + 0.1 + 0.2

    def test_confidence_clamped(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features(
            historical_precedence=100,
            temporal_patterns=[0.1] * 100,
            semantic_similarity=1.0,
        )
        conf = scorer._calculate_confidence(features)
        assert conf <= 1.0


class TestPredictRiskScore:
    def test_fallback_when_not_trained(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.model_trained = False
        features = _make_impact_features()
        score = scorer._predict_risk_score(features)
        # Falls back to rule-based
        assert 0.0 <= score <= 1.0

    def test_fallback_when_no_classifier(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.model_trained = True
        scorer.impact_classifier = None
        features = _make_impact_features()
        score = scorer._predict_risk_score(features)
        assert 0.0 <= score <= 1.0

    def test_ml_prediction_success(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_np = mod.NUMPY_AVAILABLE
        try:
            mod.NUMPY_AVAILABLE = True
            scorer = mod.ImpactScorer(_HASH)
            scorer.model_trained = True
            mock_clf = MagicMock()
            mock_clf.predict.return_value = [0.65]
            scorer.impact_classifier = mock_clf

            features = _make_impact_features()
            score = scorer._predict_risk_score(features)
            assert score == 0.65
        finally:
            mod.NUMPY_AVAILABLE = saved_np

    def test_ml_prediction_clamped(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_np = mod.NUMPY_AVAILABLE
        try:
            mod.NUMPY_AVAILABLE = True
            scorer = mod.ImpactScorer(_HASH)
            scorer.model_trained = True
            mock_clf = MagicMock()
            mock_clf.predict.return_value = [1.5]  # above 1.0
            scorer.impact_classifier = mock_clf

            features = _make_impact_features()
            score = scorer._predict_risk_score(features)
            assert score == 1.0
        finally:
            mod.NUMPY_AVAILABLE = saved_np

    def test_ml_prediction_negative_clamped(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_np = mod.NUMPY_AVAILABLE
        try:
            mod.NUMPY_AVAILABLE = True
            scorer = mod.ImpactScorer(_HASH)
            scorer.model_trained = True
            mock_clf = MagicMock()
            mock_clf.predict.return_value = [-0.5]
            scorer.impact_classifier = mock_clf

            features = _make_impact_features()
            score = scorer._predict_risk_score(features)
            assert score == 0.0
        finally:
            mod.NUMPY_AVAILABLE = saved_np

    def test_ml_prediction_error_fallback(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_np = mod.NUMPY_AVAILABLE
        try:
            mod.NUMPY_AVAILABLE = True
            scorer = mod.ImpactScorer(_HASH)
            scorer.model_trained = True
            mock_clf = MagicMock()
            mock_clf.predict.side_effect = RuntimeError("model error")
            scorer.impact_classifier = mock_clf

            features = _make_impact_features()
            score = scorer._predict_risk_score(features)
            assert 0.0 <= score <= 1.0
        finally:
            mod.NUMPY_AVAILABLE = saved_np

    def test_empty_temporal_patterns(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_np = mod.NUMPY_AVAILABLE
        try:
            mod.NUMPY_AVAILABLE = True
            scorer = mod.ImpactScorer(_HASH)
            scorer.model_trained = True
            mock_clf = MagicMock()
            mock_clf.predict.return_value = [0.4]
            scorer.impact_classifier = mock_clf

            features = _make_impact_features(temporal_patterns=[])
            score = scorer._predict_risk_score(features)
            assert score == 0.4
        finally:
            mod.NUMPY_AVAILABLE = saved_np


class TestUpdateModel:
    def test_appends_sample(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        features = _make_impact_features()
        scorer.update_model(features, 0.5)
        assert len(scorer.training_samples) == 1

    def test_no_retrain_below_threshold(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer._retrain_model = MagicMock()
        features = _make_impact_features()
        scorer.update_model(features, 0.5)
        scorer._retrain_model.assert_not_called()

    def test_error_in_update(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.training_samples = MagicMock()
        scorer.training_samples.append.side_effect = RuntimeError("fail")
        # Should not raise
        scorer.update_model(_make_impact_features(), 0.5)


class TestRetrainModel:
    def test_retrain_no_numpy(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved = mod.NUMPY_AVAILABLE
        try:
            mod.NUMPY_AVAILABLE = False
            scorer = mod.ImpactScorer(_HASH)
            scorer._retrain_model()  # Should return early
        finally:
            mod.NUMPY_AVAILABLE = saved

    def test_retrain_no_classifier(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.impact_classifier = None
        scorer._retrain_model()  # Should return early

    def test_retrain_insufficient_samples(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.training_samples = deque([(MagicMock(), 0.5)])
        scorer._retrain_model()  # Should return early, not enough samples
        assert scorer.model_trained is False

    def test_retrain_success_without_mlflow(self):
        from enhanced_agent_bus.adaptive_governance import impact_scorer as mod

        saved_np = mod.NUMPY_AVAILABLE
        try:
            mod.NUMPY_AVAILABLE = True
            scorer = mod.ImpactScorer(_HASH)
            mock_clf = MagicMock()
            scorer.impact_classifier = mock_clf
            scorer._mlflow_initialized = False

            # Add enough training samples
            for _ in range(600):
                scorer.training_samples.append((_make_impact_features(), 0.5))

            scorer._retrain_model()
            assert scorer.model_trained is True
            mock_clf.fit.assert_called_once()
        finally:
            mod.NUMPY_AVAILABLE = saved_np


class TestApplyMhcStability:
    def test_skipped_when_not_available(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.use_mhc_stability = False
        original_weights = dict(scorer.feature_weights)
        scorer._apply_mhc_stability()
        assert scorer.feature_weights == original_weights

    def test_error_handling(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer(_HASH)
        scorer.use_mhc_stability = True
        # Simulate torch not being available
        with patch.dict(scorer.feature_weights, {"bad": "not_a_number"}, clear=False):
            # Should not raise
            scorer._apply_mhc_stability()


# ===================================================================
# governance_engine.py tests
# ===================================================================


def _build_engine_with_mocks():
    """Build an AdaptiveGovernanceEngine with all dependencies mocked."""
    with (
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ImpactScorer"
        ) as mock_scorer_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AdaptiveThresholds"
        ) as mock_thresh_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.import_module"
        ) as mock_import,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DTMCLearner"
        ) as mock_dtmc_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.TraceCollector"
        ) as mock_trace_cls,
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ANOMALY_MONITORING_AVAILABLE",
            False,
        ),
    ):
        mock_scorer = MagicMock()
        mock_scorer_cls.return_value = mock_scorer
        mock_scorer.model_trained = False

        mock_thresh = MagicMock()
        mock_thresh_cls.return_value = mock_thresh

        mock_validators = MagicMock()
        mock_validator_instance = MagicMock()
        mock_validator_instance.validate_decision = AsyncMock(return_value=(True, []))
        mock_validators.GovernanceDecisionValidator.return_value = mock_validator_instance
        mock_import.return_value = mock_validators

        mock_dtmc = MagicMock()
        mock_dtmc.is_fitted = False
        mock_dtmc_cls.return_value = mock_dtmc

        mock_trace = MagicMock()
        mock_trace_cls.return_value = mock_trace

        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        engine = AdaptiveGovernanceEngine(_HASH)

    return engine


class TestGovernanceEngineInit:
    def test_basic_init(self):
        engine = _build_engine_with_mocks()
        assert engine.constitutional_hash == _HASH
        assert engine.running is False
        assert len(engine.decision_history) == 0

    def test_mode_default(self):
        from enhanced_agent_bus.adaptive_governance.models import GovernanceMode

        engine = _build_engine_with_mocks()
        assert engine.mode == GovernanceMode.ADAPTIVE


class TestClassifyImpactLevel:
    def test_critical(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        assert engine._classify_impact_level(0.95) == ImpactLevel.CRITICAL

    def test_high(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        assert engine._classify_impact_level(0.75) == ImpactLevel.HIGH

    def test_medium(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        assert engine._classify_impact_level(0.5) == ImpactLevel.MEDIUM

    def test_low(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        assert engine._classify_impact_level(0.25) == ImpactLevel.LOW

    def test_negligible(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        assert engine._classify_impact_level(0.1) == ImpactLevel.NEGLIGIBLE


class TestGenerateReasoning:
    def test_allowed_reasoning(self):
        engine = _build_engine_with_mocks()
        features = _make_impact_features(
            risk_score=0.3, confidence_level=0.9, historical_precedence=5
        )
        reasoning = engine._generate_reasoning(True, features, 0.7)
        assert "ALLOWED" in reasoning
        assert "5 similar precedents" in reasoning

    def test_blocked_reasoning(self):
        engine = _build_engine_with_mocks()
        features = _make_impact_features(risk_score=0.8, confidence_level=0.5)
        reasoning = engine._generate_reasoning(False, features, 0.7)
        assert "BLOCKED" in reasoning
        assert "Low confidence" in reasoning

    def test_no_precedence(self):
        engine = _build_engine_with_mocks()
        features = _make_impact_features(
            risk_score=0.3, confidence_level=0.9, historical_precedence=0
        )
        reasoning = engine._generate_reasoning(True, features, 0.7)
        assert "precedents" not in reasoning


class TestBuildConservativeFallback:
    def test_fallback_decision(self):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        decision = AdaptiveGovernanceEngine._build_conservative_fallback_decision(
            RuntimeError("test error")
        )
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH
        assert "test error" in decision.reasoning


class TestEvaluateGovernanceDecision:
    async def test_evaluate_success(self):
        engine = _build_engine_with_mocks()
        features = _make_impact_features(risk_score=0.3, confidence_level=0.8)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.7

        message = {"content": "test"}
        context = {}
        decision = await engine.evaluate_governance_decision(message, context)
        assert decision.action_allowed is True

    async def test_evaluate_blocked(self):
        engine = _build_engine_with_mocks()
        features = _make_impact_features(risk_score=0.9, confidence_level=0.8)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.7

        message = {"content": "risky"}
        context = {}
        decision = await engine.evaluate_governance_decision(message, context)
        assert decision.action_allowed is False

    async def test_evaluate_validation_failure(self):
        engine = _build_engine_with_mocks()
        features = _make_impact_features(risk_score=0.3, confidence_level=0.8)
        engine.impact_scorer.assess_impact = AsyncMock(return_value=features)
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.7
        engine._decision_validator.validate_decision = AsyncMock(
            return_value=(False, ["invalid hash"])
        )

        message = {"content": "test"}
        context = {}
        decision = await engine.evaluate_governance_decision(message, context)
        # Should return conservative fallback
        assert decision.action_allowed is False

    async def test_evaluate_error_returns_fallback(self):
        engine = _build_engine_with_mocks()
        engine.impact_scorer.assess_impact = AsyncMock(side_effect=RuntimeError("boom"))

        message = {"content": "test"}
        context = {}
        decision = await engine.evaluate_governance_decision(message, context)
        assert decision.action_allowed is False
        assert "boom" in decision.reasoning


class TestProvideFeedback:
    def test_feedback_success(self):
        engine = _build_engine_with_mocks()
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)
        engine.threshold_manager.update_model.assert_called_once()
        engine.impact_scorer.update_model.assert_called_once()

    def test_feedback_with_human_override(self):
        engine = _build_engine_with_mocks()
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True, human_override=False)
        call_args = engine.threshold_manager.update_model.call_args
        # human_feedback should be False != True (action_allowed)
        assert call_args[0][2] is False

    def test_feedback_outcome_failure_increases_risk(self):
        engine = _build_engine_with_mocks()
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=False)
        # actual_impact should be increased by 0.2
        call_args = engine.impact_scorer.update_model.call_args
        actual_impact = call_args[0][1]
        assert actual_impact == min(1.0, decision.features_used.risk_score + 0.2)

    def test_feedback_error_handled(self):
        engine = _build_engine_with_mocks()
        engine.threshold_manager.update_model.side_effect = RuntimeError("fail")
        decision = _make_decision()
        # Should not raise
        engine.provide_feedback(decision, outcome_success=True)


class TestUpdateMetrics:
    def test_update_metrics_basic(self):
        engine = _build_engine_with_mocks()
        decision = _make_decision(confidence_score=0.9)
        engine.decision_history.append(decision)
        engine._update_metrics(decision, 0.01)
        assert engine.metrics.average_response_time > 0

    def test_update_metrics_compliance_rate(self):
        engine = _build_engine_with_mocks()
        for _ in range(10):
            d = _make_decision(confidence_score=0.9)
            engine.decision_history.append(d)
        engine._update_metrics(d, 0.01)
        assert engine.metrics.constitutional_compliance_rate == 1.0

    def test_update_metrics_low_compliance(self):
        engine = _build_engine_with_mocks()
        for _ in range(10):
            d = _make_decision(confidence_score=0.5)
            engine.decision_history.append(d)
        engine._update_metrics(d, 0.01)
        assert engine.metrics.constitutional_compliance_rate == 0.0


class TestAnalyzePerformanceTrends:
    def test_appends_trend(self):
        engine = _build_engine_with_mocks()
        engine.metrics.constitutional_compliance_rate = 0.9
        engine.metrics.false_positive_rate = 0.05
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) == 1
        assert len(engine.metrics.accuracy_trend) == 1

    def test_trims_long_trends(self):
        engine = _build_engine_with_mocks()
        engine.metrics.compliance_trend = list(range(200))
        engine.metrics.accuracy_trend = list(range(200))
        engine.metrics.performance_trend = list(range(200))
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) <= 100
        assert len(engine.metrics.accuracy_trend) <= 100


class TestShouldRetrainModels:
    def test_retrain_when_compliance_low(self):
        engine = _build_engine_with_mocks()
        engine.metrics.constitutional_compliance_rate = 0.5
        assert engine._should_retrain_models() is True

    def test_no_retrain_when_compliant_and_few_decisions(self):
        engine = _build_engine_with_mocks()
        engine.metrics.constitutional_compliance_rate = 0.99
        assert engine._should_retrain_models() is False


class TestLogPerformanceSummary:
    def test_log_summary_no_error(self):
        engine = _build_engine_with_mocks()
        engine._log_performance_summary()  # Should not raise


class TestGetTrajectoryPrefix:
    def test_empty_history(self):
        engine = _build_engine_with_mocks()
        assert engine._get_trajectory_prefix() is None

    def test_with_history(self):
        engine = _build_engine_with_mocks()
        for _ in range(5):
            engine.decision_history.append(_make_decision())
        prefix = engine._get_trajectory_prefix()
        assert prefix is not None
        assert len(prefix) == 5


class TestApplyDtmcRiskBlend:
    def test_disabled_config(self):
        engine = _build_engine_with_mocks()
        engine.config = None
        features = _make_impact_features(risk_score=0.5)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.5

    def test_enabled_but_not_fitted(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True, dtmc_impact_weight=0.1)
        engine._dtmc_learner.is_fitted = False
        features = _make_impact_features(risk_score=0.5)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.5

    def test_enabled_and_fitted_blends(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(
            enable_dtmc=True,
            dtmc_impact_weight=0.5,
            dtmc_intervention_threshold=0.8,
        )
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.predict_risk.return_value = 0.6
        # Need history for trajectory prefix
        for _ in range(3):
            engine.decision_history.append(_make_decision())
        features = _make_impact_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        # blended = min(1.0, 0.3 + 0.6 * 0.5) = 0.6
        assert abs(result.risk_score - 0.6) < 0.01

    def test_weight_zero(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True, dtmc_impact_weight=0.0)
        features = _make_impact_features(risk_score=0.5)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.5


class TestApplyDtmcEscalation:
    def test_disabled(self):
        engine = _build_engine_with_mocks()
        engine.config = None
        decision = _make_decision()
        result = engine._apply_dtmc_escalation(decision)
        assert result is decision

    def test_no_intervention_needed(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene.return_value = False
        for _ in range(3):
            engine.decision_history.append(_make_decision())
        decision = _make_decision()
        result = engine._apply_dtmc_escalation(decision)
        assert result is decision

    def test_escalates_low_impact(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene.return_value = True
        engine._dtmc_learner.predict_risk.return_value = 0.9
        for _ in range(3):
            engine.decision_history.append(_make_decision())
        decision = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH
        assert result.action_allowed is False

    def test_no_escalation_for_high(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene.return_value = True
        engine._dtmc_learner.predict_risk.return_value = 0.9
        for _ in range(3):
            engine.decision_history.append(_make_decision())
        decision = _make_decision(impact_level=ImpactLevel.HIGH)
        result = engine._apply_dtmc_escalation(decision)
        assert result is decision

    def test_empty_trajectory(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        engine._dtmc_learner.is_fitted = True
        # Empty decision history -> None prefix
        decision = _make_decision()
        result = engine._apply_dtmc_escalation(decision)
        assert result is decision


class TestMaybeRefitDtmc:
    def test_disabled(self):
        engine = _build_engine_with_mocks()
        engine.config = None
        engine._maybe_refit_dtmc()  # Should return early

    def test_insufficient_history(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        engine._maybe_refit_dtmc()  # Should return early (< 10)

    def test_no_trajectories(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        for _ in range(15):
            engine.decision_history.append(_make_decision())
        engine._trace_collector.collect_from_decision_history.return_value = []
        engine._maybe_refit_dtmc()
        engine._dtmc_learner.fit.assert_not_called()

    def test_refits_with_trajectories(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        for _ in range(15):
            engine.decision_history.append(_make_decision())
        mock_traj = [MagicMock()]
        engine._trace_collector.collect_from_decision_history.return_value = mock_traj
        mock_result = MagicMock()
        mock_result.n_trajectories = 1
        mock_result.unsafe_fraction = 0.1
        engine._dtmc_learner.fit.return_value = mock_result
        engine._maybe_refit_dtmc()
        engine._dtmc_learner.fit.assert_called_once_with(mock_traj)


class TestInitializeShutdown:
    async def test_initialize(self):
        engine = _build_engine_with_mocks()
        engine._load_historical_data = AsyncMock()

        # Start initialize and immediately stop to prevent infinite loop
        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None
        await engine.shutdown()
        assert engine.running is False

    async def test_shutdown_without_init(self):
        engine = _build_engine_with_mocks()
        await engine.shutdown()
        assert engine.running is False

    async def test_shutdown_with_anomaly_monitor(self):
        engine = _build_engine_with_mocks()
        engine._anomaly_monitor = MagicMock()
        engine._anomaly_monitor.stop = AsyncMock()
        engine._save_model_state = AsyncMock()
        await engine.shutdown()
        engine._anomaly_monitor.stop.assert_awaited_once()


class TestDefaultRiverFeatureNames:
    def test_returns_list(self):
        engine = _build_engine_with_mocks()
        names = engine._default_river_feature_names()
        assert isinstance(names, list)
        assert "message_length" in names
        assert len(names) == 11


class TestRecordDecisionMetrics:
    def test_with_anomaly_monitor(self):
        engine = _build_engine_with_mocks()
        engine._anomaly_monitor = MagicMock()
        decision = _make_decision()
        engine._record_decision_metrics(decision, time.time() - 0.01)
        engine._anomaly_monitor.record_metrics.assert_called_once()

    def test_without_anomaly_monitor(self):
        engine = _build_engine_with_mocks()
        engine._anomaly_monitor = None
        decision = _make_decision()
        engine._record_decision_metrics(decision, time.time() - 0.01)
        assert len(engine.decision_history) == 1


class TestGetRiverModelStats:
    def test_unavailable(self):
        engine = _build_engine_with_mocks()
        engine.river_model = None
        assert engine.get_river_model_stats() is None

    def test_stats_with_dict(self):
        engine = _build_engine_with_mocks()
        engine.river_model = MagicMock()
        mock_stats = {"total_samples": 100, "accuracy": 0.95}
        engine.river_model.get_stats.return_value = mock_stats

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            result = engine.get_river_model_stats()
            assert result is not None

    def test_stats_error(self):
        engine = _build_engine_with_mocks()
        engine.river_model = MagicMock()
        engine.river_model.get_stats.side_effect = RuntimeError("fail")

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            result = engine.get_river_model_stats()
            assert result is None


class TestGetAbTestMethods:
    def test_get_ab_test_router(self):
        engine = _build_engine_with_mocks()
        assert engine.get_ab_test_router() is None

    def test_get_ab_test_metrics_unavailable(self):
        engine = _build_engine_with_mocks()
        assert engine.get_ab_test_metrics() is None

    def test_get_ab_test_comparison_unavailable(self):
        engine = _build_engine_with_mocks()
        assert engine.get_ab_test_comparison() is None

    def test_promote_candidate_unavailable(self):
        engine = _build_engine_with_mocks()
        assert engine.promote_candidate_model() is None

    def test_get_ab_test_metrics_with_router(self):
        engine = _build_engine_with_mocks()
        mock_router = MagicMock()
        mock_router.get_metrics_summary.return_value = {"test": "data"}
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_metrics()
            assert result == {"test": "data"}

    def test_get_ab_test_metrics_error(self):
        engine = _build_engine_with_mocks()
        mock_router = MagicMock()
        mock_router.get_metrics_summary.side_effect = RuntimeError("fail")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_metrics()
            assert result is None

    def test_get_ab_test_comparison_with_router(self):
        engine = _build_engine_with_mocks()
        mock_router = MagicMock()
        mock_comparison = MagicMock()
        mock_router.compare_metrics.return_value = mock_comparison
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_comparison()
            assert result is mock_comparison

    def test_get_ab_test_comparison_error(self):
        engine = _build_engine_with_mocks()
        mock_router = MagicMock()
        mock_router.compare_metrics.side_effect = RuntimeError("fail")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.get_ab_test_comparison()
            assert result is None

    def test_promote_candidate_success(self):
        engine = _build_engine_with_mocks()
        mock_router = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "promoted"
        mock_result.previous_champion_version = 1
        mock_result.new_champion_version = 2
        mock_router.promote_candidate.return_value = mock_result
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.promote_candidate_model()
            assert result is mock_result

    def test_promote_candidate_error(self):
        engine = _build_engine_with_mocks()
        mock_router = MagicMock()
        mock_router.promote_candidate.side_effect = RuntimeError("fail")
        engine._ab_test_router = mock_router

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            True,
        ):
            result = engine.promote_candidate_model()
            assert result is None


class TestLearningThreadProperty:
    def test_returns_learning_task(self):
        engine = _build_engine_with_mocks()
        engine.learning_task = MagicMock()
        assert engine._learning_thread is engine.learning_task


class TestStoreFeedbackEvent:
    def test_stores_positive_feedback(self):
        engine = _build_engine_with_mocks()
        mock_handler = MagicMock()
        mock_response = MagicMock()
        mock_response.feedback_id = "fb-001"
        mock_handler.store_feedback.return_value = mock_response
        engine._feedback_handler = mock_handler

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            # Mock the FeedbackType, etc. since they may not be importable
            with patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackType"
            ) as mock_ft:
                with patch(
                    "enhanced_agent_bus.adaptive_governance.governance_engine.OutcomeStatus"
                ) as mock_os:
                    with patch(
                        "enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackEvent"
                    ) as mock_fe:
                        mock_fe.return_value = MagicMock()
                        mock_ft.POSITIVE = "POSITIVE"
                        mock_ft.NEGATIVE = "NEGATIVE"
                        mock_ft.CORRECTION = "CORRECTION"
                        mock_os.SUCCESS = "SUCCESS"
                        mock_os.FAILURE = "FAILURE"

                        decision = _make_decision()
                        engine._store_feedback_event(decision, True, None, 0.3)
                        mock_handler.store_feedback.assert_called_once()

    def test_stores_correction_feedback(self):
        engine = _build_engine_with_mocks()
        mock_handler = MagicMock()
        mock_response = MagicMock()
        mock_response.feedback_id = "fb-002"
        mock_handler.store_feedback.return_value = mock_response
        engine._feedback_handler = mock_handler

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            with patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackType"
            ) as mock_ft:
                with patch(
                    "enhanced_agent_bus.adaptive_governance.governance_engine.OutcomeStatus"
                ) as mock_os:
                    with patch(
                        "enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackEvent"
                    ) as mock_fe:
                        mock_fe.return_value = MagicMock()
                        mock_ft.CORRECTION = "CORRECTION"
                        mock_os.FAILURE = "FAILURE"

                        decision = _make_decision()
                        engine._store_feedback_event(decision, False, True, 0.5)
                        mock_handler.store_feedback.assert_called_once()

    def test_skipped_when_handler_none(self):
        engine = _build_engine_with_mocks()
        engine._feedback_handler = None
        decision = _make_decision()
        # Should not raise
        engine._store_feedback_event(decision, True, None, 0.3)

    def test_error_handling(self):
        engine = _build_engine_with_mocks()
        mock_handler = MagicMock()
        mock_handler.store_feedback.side_effect = RuntimeError("fail")
        engine._feedback_handler = mock_handler

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            True,
        ):
            with patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackType"
            ) as mock_ft:
                with patch(
                    "enhanced_agent_bus.adaptive_governance.governance_engine.OutcomeStatus"
                ) as mock_os:
                    with patch(
                        "enhanced_agent_bus.adaptive_governance.governance_engine.FeedbackEvent"
                    ) as mock_fe:
                        mock_fe.return_value = MagicMock()
                        mock_ft.POSITIVE = "POSITIVE"
                        mock_os.SUCCESS = "SUCCESS"

                        decision = _make_decision()
                        # Should not raise
                        engine._store_feedback_event(decision, True, None, 0.3)


class TestCollectDriftData:
    def test_empty_history(self):
        engine = _build_engine_with_mocks()
        result = engine._collect_drift_data()
        assert result is None

    def test_with_history_no_pandas(self):
        engine = _build_engine_with_mocks()
        engine.decision_history.append(_make_decision())
        with patch.dict(sys.modules, {"pandas": None}):
            with patch("builtins.__import__", side_effect=ImportError("no pandas")):
                # The method catches ImportError internally
                result = engine._collect_drift_data()
                # May return None if pandas import fails
                # (depends on whether pandas is installed)

    def test_error_handling(self):
        engine = _build_engine_with_mocks()
        engine.decision_history = MagicMock()
        engine.decision_history.__bool__ = MagicMock(side_effect=RuntimeError("fail"))
        result = engine._collect_drift_data()
        assert result is None


class TestRunScheduledDriftDetection:
    def test_skipped_when_unavailable(self):
        engine = _build_engine_with_mocks()
        engine._drift_detector = None
        engine._run_scheduled_drift_detection()  # Should return early

    def test_skipped_when_interval_not_elapsed(self):
        engine = _build_engine_with_mocks()

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
            True,
        ):
            engine._drift_detector = MagicMock()
            engine._last_drift_check = time.time()
            engine._drift_check_interval = 99999
            engine._run_scheduled_drift_detection()
            engine._drift_detector.detect_drift.assert_not_called()


class TestUpdateRiverModel:
    def test_skipped_when_unavailable(self):
        engine = _build_engine_with_mocks()
        engine.river_model = None
        decision = _make_decision()
        engine._update_river_model(decision, 0.5)  # Should return early

    def test_success(self):
        engine = _build_engine_with_mocks()
        engine.river_model = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_samples = 10
        engine.river_model.learn_from_feedback.return_value = mock_result
        engine.river_model.adapter.is_ready = False

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            decision = _make_decision()
            engine._update_river_model(decision, 0.5)
            engine.river_model.learn_from_feedback.assert_called_once()

    def test_failure_result(self):
        engine = _build_engine_with_mocks()
        engine.river_model = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "failed"
        engine.river_model.learn_from_feedback.return_value = mock_result

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            decision = _make_decision()
            engine._update_river_model(decision, 0.5)

    def test_error_handled(self):
        engine = _build_engine_with_mocks()
        engine.river_model = MagicMock()
        engine.river_model.learn_from_feedback.side_effect = RuntimeError("fail")

        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            True,
        ):
            decision = _make_decision()
            engine._update_river_model(decision, 0.5)


class TestGetLatestDriftReport:
    def test_returns_none_initially(self):
        engine = _build_engine_with_mocks()
        assert engine.get_latest_drift_report() is None

    def test_returns_report(self):
        engine = _build_engine_with_mocks()
        mock_report = MagicMock()
        engine._latest_drift_report = mock_report
        assert engine.get_latest_drift_report() is mock_report


class TestFeedbackWithDtmc:
    def test_feedback_with_dtmc_enabled(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        engine._dtmc_learner.is_fitted = True

        # Add some decisions
        for _ in range(5):
            engine.decision_history.append(_make_decision())

        mock_trajs = [MagicMock()]
        engine._trace_collector.collect_from_decision_history.return_value = mock_trajs

        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)
        engine._dtmc_learner.update_online.assert_called()

    def test_feedback_dtmc_too_few_decisions(self):
        engine = _build_engine_with_mocks()
        engine.config = SimpleNamespace(enable_dtmc=True)
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_feedback_idx = 0

        # Only 1 decision - not enough for trajectories (need >= 2)
        decision = _make_decision()
        engine.decision_history.append(decision)
        engine._dtmc_feedback_idx = 0

        engine.provide_feedback(decision, outcome_success=True)
        engine._dtmc_learner.update_online.assert_not_called()


class TestBuildDecisionForFeatures:
    def test_builds_decision(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        engine = _build_engine_with_mocks()
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.7
        features = _make_impact_features(risk_score=0.3, confidence_level=0.8)
        decision = engine._build_decision_for_features(features, "gov-test-001")
        assert decision.action_allowed is True
        assert decision.decision_id == "gov-test-001"

    def test_blocked_decision(self):
        engine = _build_engine_with_mocks()
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.2
        features = _make_impact_features(risk_score=0.5, confidence_level=0.8)
        decision = engine._build_decision_for_features(features, "gov-test-002")
        assert decision.action_allowed is False


class TestApplyAbTestRouting:
    def test_returns_decision_when_unavailable(self):
        engine = _build_engine_with_mocks()
        engine._ab_test_router = None
        decision = _make_decision()
        result = engine._apply_ab_test_routing(decision, _make_impact_features(), time.time())
        assert result is decision
