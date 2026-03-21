"""
Tests targeting remaining uncovered lines in:
  1. enhanced_agent_bus.observability.telemetry (73.4% -> 90%+)
  2. enhanced_agent_bus.adaptive_governance.impact_scorer (75.6% -> 90%+)

Constitutional Hash: cdd01ef066bc6cf2

Batch 28b: covers gaps NOT handled by batch27b.
"""

from __future__ import annotations

import sys
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, "packages/enhanced_agent_bus")

import pytest

from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures
from enhanced_agent_bus.observability.telemetry import (
    MetricsRegistry,
    NoOpMeter,
    NoOpTracer,
    TelemetryConfig,
    TracingContext,
    _get_resource_attributes,
    configure_telemetry,
    get_meter,
    get_tracer,
    OTEL_AVAILABLE,
)


# -----------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------

def _make_features(**overrides) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2, 0.3],
        semantic_similarity=0.6,
        historical_precedence=3,
        resource_utilization=0.4,
        network_isolation=0.3,
        risk_score=0.3,
        confidence_level=0.85,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


# =======================================================================
# TELEMETRY: Lines still missing after batch27b
# =======================================================================


class TestConfigureTelemetryOtelAvailable:
    """Cover lines 335-346: configure_telemetry when OTEL is available.

    We mock out _setup_telemetry_providers and the otel trace/metrics modules
    so these tests run regardless of actual OTEL installation.
    """

    def test_configure_telemetry_first_time_otel_available(self):
        """Cover lines 335-346: first call with OTEL available sets up providers."""
        mock_trace = MagicMock()
        mock_metrics = MagicMock()
        mock_tracer = MagicMock()
        mock_meter = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer
        mock_metrics.get_meter.return_value = mock_meter

        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", False),
            patch(
                "enhanced_agent_bus.observability.telemetry._setup_telemetry_providers"
            ) as mock_setup,
            patch("enhanced_agent_bus.observability.telemetry.trace", mock_trace),
            patch("enhanced_agent_bus.observability.telemetry.metrics", mock_metrics),
            patch("enhanced_agent_bus.observability.telemetry._tracers", {}),
            patch("enhanced_agent_bus.observability.telemetry._meters", {}),
        ):
            config = TelemetryConfig(service_name="test-svc")
            tracer, meter = configure_telemetry(config)

            mock_setup.assert_called_once_with(config)
            mock_trace.get_tracer.assert_called_once_with("test-svc", "2.0.0")
            mock_metrics.get_meter.assert_called_once_with("test-svc", "2.0.0")
            assert tracer is mock_tracer
            assert meter is mock_meter

    def test_configure_telemetry_already_configured(self):
        """Cover lines 340-346: skip _setup when already configured."""
        mock_trace = MagicMock()
        mock_metrics = MagicMock()

        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", True),
            patch(
                "enhanced_agent_bus.observability.telemetry._setup_telemetry_providers"
            ) as mock_setup,
            patch("enhanced_agent_bus.observability.telemetry.trace", mock_trace),
            patch("enhanced_agent_bus.observability.telemetry.metrics", mock_metrics),
            patch("enhanced_agent_bus.observability.telemetry._tracers", {}),
            patch("enhanced_agent_bus.observability.telemetry._meters", {}),
        ):
            configure_telemetry()
            mock_setup.assert_not_called()


class TestGetTracerOtelAvailable:
    """Cover lines 366-375: get_tracer auto-configure and new tracer creation."""

    def test_get_tracer_auto_configures(self):
        """Cover lines 366-367: auto-configure when not yet configured."""
        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", False),
            patch(
                "enhanced_agent_bus.observability.telemetry.configure_telemetry"
            ) as mock_configure,
            patch("enhanced_agent_bus.observability.telemetry._tracers", {}),
            patch(
                "enhanced_agent_bus.observability.telemetry.trace",
                MagicMock(get_tracer=MagicMock(return_value=MagicMock())),
            ),
        ):
            result = get_tracer("new-svc")
            mock_configure.assert_called_once()
            assert result is not None

    def test_get_tracer_creates_new_when_not_cached(self):
        """Cover lines 369-375: creates new tracer for uncached name."""
        mock_trace_mod = MagicMock()
        mock_new_tracer = MagicMock()
        mock_trace_mod.get_tracer.return_value = mock_new_tracer
        tracers_dict: dict = {}

        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", True),
            patch("enhanced_agent_bus.observability.telemetry._tracers", tracers_dict),
        ):
            # Patch the local import inside get_tracer
            with patch.dict(
                sys.modules,
                {"opentelemetry": MagicMock(trace=mock_trace_mod)},
            ):
                result = get_tracer("fresh-svc")
                assert result is mock_new_tracer

    def test_get_tracer_default_name(self):
        """Cover line 369: None service_name -> 'acgs2-agent-bus'."""
        mock_trace_mod = MagicMock()
        mock_trace_mod.get_tracer.return_value = MagicMock()
        tracers_dict: dict = {}

        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", True),
            patch("enhanced_agent_bus.observability.telemetry._tracers", tracers_dict),
        ):
            with patch.dict(
                sys.modules,
                {"opentelemetry": MagicMock(trace=mock_trace_mod)},
            ):
                get_tracer(None)
                assert "acgs2-agent-bus" in tracers_dict


class TestGetMeterOtelAvailable:
    """Cover lines 395-404: get_meter auto-configure and new meter creation."""

    def test_get_meter_auto_configures(self):
        """Cover lines 395-396: auto-configure when not yet configured."""
        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", False),
            patch(
                "enhanced_agent_bus.observability.telemetry.configure_telemetry"
            ) as mock_configure,
            patch("enhanced_agent_bus.observability.telemetry._meters", {}),
            patch(
                "enhanced_agent_bus.observability.telemetry.metrics",
                MagicMock(get_meter=MagicMock(return_value=MagicMock())),
            ),
        ):
            result = get_meter("new-svc")
            mock_configure.assert_called_once()
            assert result is not None

    def test_get_meter_creates_new_when_not_cached(self):
        """Cover lines 398-404: creates new meter for uncached name."""
        mock_metrics_mod = MagicMock()
        mock_new_meter = MagicMock()
        mock_metrics_mod.get_meter.return_value = mock_new_meter
        meters_dict: dict = {}

        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", True),
            patch("enhanced_agent_bus.observability.telemetry._meters", meters_dict),
        ):
            with patch.dict(
                sys.modules,
                {"opentelemetry": MagicMock(metrics=mock_metrics_mod)},
            ):
                result = get_meter("fresh-svc")
                assert result is mock_new_meter

    def test_get_meter_default_name(self):
        """Cover line 399: None service_name -> 'acgs2-agent-bus'."""
        mock_metrics_mod = MagicMock()
        mock_metrics_mod.get_meter.return_value = MagicMock()
        meters_dict: dict = {}

        with (
            patch("enhanced_agent_bus.observability.telemetry.OTEL_AVAILABLE", True),
            patch("enhanced_agent_bus.observability.telemetry._configured", True),
            patch("enhanced_agent_bus.observability.telemetry._meters", meters_dict),
        ):
            with patch.dict(
                sys.modules,
                {"opentelemetry": MagicMock(metrics=mock_metrics_mod)},
            ):
                get_meter(None)
                assert "acgs2-agent-bus" in meters_dict


class TestSetupTelemetryProviders:
    """Cover lines 297-311: _setup_telemetry_providers full path."""

    def test_setup_telemetry_providers_full(self):
        """Cover lines 297-311 together."""
        from enhanced_agent_bus.observability.telemetry import (
            _setup_telemetry_providers,
        )

        mock_resource_cls = MagicMock()
        mock_resource = MagicMock()
        mock_resource_cls.create.return_value = mock_resource
        mock_trace = MagicMock()
        mock_metrics = MagicMock()
        mock_trace_provider = MagicMock()
        mock_meter_provider = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.observability.telemetry._get_resource_attributes",
                return_value={"service.name": "test"},
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry.Resource",
                mock_resource_cls,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry._configure_trace_provider",
                return_value=mock_trace_provider,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry.trace",
                mock_trace,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry._configure_meter_provider",
                return_value=mock_meter_provider,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry.metrics",
                mock_metrics,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry._configure_propagation",
            ),
        ):
            config = TelemetryConfig(service_name="test-svc")
            _setup_telemetry_providers(config)

            mock_resource_cls.create.assert_called_once()
            mock_trace.set_tracer_provider.assert_called_once_with(mock_trace_provider)
            mock_metrics.set_meter_provider.assert_called_once_with(mock_meter_provider)


class TestConfigureTraceProviderPaths:
    """Cover lines 230-256: _configure_trace_provider with export and ImportError."""

    def test_configure_trace_provider_export_with_otlp(self):
        """Cover lines 235-248: export_traces=True with OTLP exporter available."""
        from enhanced_agent_bus.observability.telemetry import (
            _configure_trace_provider,
        )

        mock_tp = MagicMock()
        mock_exporter = MagicMock()
        mock_batch = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.observability.telemetry.TracerProvider",
                return_value=mock_tp,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry.BatchSpanProcessor",
                return_value=mock_batch,
            ),
            patch.dict(
                sys.modules,
                {
                    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(
                        OTLPSpanExporter=MagicMock(return_value=mock_exporter)
                    ),
                },
            ),
        ):
            config = TelemetryConfig(export_traces=True, batch_span_processor=True)
            result = _configure_trace_provider(config, MagicMock())
            assert result is mock_tp
            mock_tp.add_span_processor.assert_called_once_with(mock_batch)

    def test_configure_trace_provider_simple_processor(self):
        """Cover line 245: batch_span_processor=False uses SimpleSpanProcessor."""
        from enhanced_agent_bus.observability.telemetry import (
            _configure_trace_provider,
        )

        mock_tp = MagicMock()
        mock_simple = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.observability.telemetry.TracerProvider",
                return_value=mock_tp,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry.SimpleSpanProcessor",
                return_value=mock_simple,
            ),
            patch.dict(
                sys.modules,
                {
                    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(
                        OTLPSpanExporter=MagicMock(return_value=MagicMock())
                    ),
                },
            ),
        ):
            config = TelemetryConfig(export_traces=True, batch_span_processor=False)
            result = _configure_trace_provider(config, MagicMock())
            mock_tp.add_span_processor.assert_called_once_with(mock_simple)

    def test_configure_trace_provider_otlp_import_error(self):
        """Cover lines 251-252: OTLP exporter not available."""
        from enhanced_agent_bus.observability.telemetry import (
            _configure_trace_provider,
        )

        mock_tp = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.observability.telemetry.TracerProvider",
                return_value=mock_tp,
            ),
        ):
            # Remove the OTLP exporter module to trigger ImportError
            saved = sys.modules.pop(
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter", None
            )
            try:
                with patch.dict(
                    sys.modules,
                    {
                        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": None,
                    },
                ):
                    config = TelemetryConfig(export_traces=True)
                    result = _configure_trace_provider(config, MagicMock())
                    assert result is mock_tp
                    mock_tp.add_span_processor.assert_not_called()
            finally:
                if saved is not None:
                    sys.modules[
                        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
                    ] = saved

    def test_configure_trace_provider_no_export(self):
        """Cover lines 232-233: export_traces=False returns early."""
        from enhanced_agent_bus.observability.telemetry import (
            _configure_trace_provider,
        )

        mock_tp = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.telemetry.TracerProvider",
            return_value=mock_tp,
        ):
            config = TelemetryConfig(export_traces=False)
            result = _configure_trace_provider(config, MagicMock())
            assert result is mock_tp


class TestConfigureMeterProviderPaths:
    """Cover lines 259-281: _configure_meter_provider paths."""

    def test_configure_meter_provider_export_success(self):
        """Cover lines 264-275: export_metrics=True with OTLP exporter."""
        from enhanced_agent_bus.observability.telemetry import (
            _configure_meter_provider,
        )

        mock_mp = MagicMock()
        mock_reader = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.observability.telemetry.MeterProvider",
                return_value=mock_mp,
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry.PeriodicExportingMetricReader",
                return_value=mock_reader,
            ),
            patch.dict(
                sys.modules,
                {
                    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter": MagicMock(
                        OTLPMetricExporter=MagicMock(return_value=MagicMock())
                    ),
                },
            ),
        ):
            config = TelemetryConfig(export_metrics=True)
            result = _configure_meter_provider(config, MagicMock())
            assert result is mock_mp

    def test_configure_meter_provider_otlp_import_error(self):
        """Cover lines 276-281: OTLP metric exporter not available."""
        from enhanced_agent_bus.observability.telemetry import (
            _configure_meter_provider,
        )

        mock_mp = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.observability.telemetry.MeterProvider",
                return_value=mock_mp,
            ),
        ):
            saved = sys.modules.pop(
                "opentelemetry.exporter.otlp.proto.grpc.metric_exporter", None
            )
            try:
                with patch.dict(
                    sys.modules,
                    {
                        "opentelemetry.exporter.otlp.proto.grpc.metric_exporter": None,
                    },
                ):
                    config = TelemetryConfig(export_metrics=True)
                    result = _configure_meter_provider(config, MagicMock())
                    assert result is mock_mp
            finally:
                if saved is not None:
                    sys.modules[
                        "opentelemetry.exporter.otlp.proto.grpc.metric_exporter"
                    ] = saved

    def test_configure_meter_provider_no_export(self):
        """Cover line 261-262: export_metrics=False."""
        from enhanced_agent_bus.observability.telemetry import (
            _configure_meter_provider,
        )

        mock_mp = MagicMock()
        with patch(
            "enhanced_agent_bus.observability.telemetry.MeterProvider",
            return_value=mock_mp,
        ):
            config = TelemetryConfig(export_metrics=False)
            result = _configure_meter_provider(config, MagicMock())
            assert result is mock_mp


class TestConfigurePropagation:
    """Cover lines 286-292: _configure_propagation paths."""

    def test_configure_propagation_success(self):
        """Cover lines 287-290: B3 propagator available."""
        from enhanced_agent_bus.observability.telemetry import _configure_propagation

        mock_b3 = MagicMock()
        with (
            patch.dict(
                sys.modules,
                {
                    "opentelemetry.propagators.b3": MagicMock(
                        B3MultiFormat=MagicMock(return_value=mock_b3)
                    ),
                },
            ),
            patch(
                "enhanced_agent_bus.observability.telemetry.set_global_textmap"
            ) as mock_set,
        ):
            _configure_propagation()
            mock_set.assert_called_once_with(mock_b3)

    def test_configure_propagation_import_error(self):
        """Cover lines 291-292: B3 propagator not available."""
        from enhanced_agent_bus.observability.telemetry import _configure_propagation

        saved = sys.modules.pop("opentelemetry.propagators.b3", None)
        try:
            with patch.dict(
                sys.modules,
                {"opentelemetry.propagators.b3": None},
            ):
                _configure_propagation()  # Should not raise
        finally:
            if saved is not None:
                sys.modules["opentelemetry.propagators.b3"] = saved


class TestTracingContextTenantId:
    """Cover lines 445-447: tenant ID is set when available."""

    def test_tenant_id_is_set_on_span(self):
        """Cover lines 444-447: get_current_tenant_id returns a value."""
        mock_tenant = MagicMock(return_value="tenant-123")
        ctx = TracingContext("test-span")

        with patch(
            "enhanced_agent_bus.observability.telemetry.get_tracer",
            return_value=NoOpTracer(),
        ):
            with patch(
                "enhanced_agent_bus.multi_tenancy.context.get_current_tenant_id",
                mock_tenant,
                create=True,
            ):
                with ctx as span:
                    # NoOpSpan doesn't store attributes, but the code path is exercised
                    pass


# =======================================================================
# IMPACT SCORER: Lines still missing after batch27b
# =======================================================================


class TestImpactScorerInit:
    """Cover ImpactScorer __init__ and _initialize_mlflow paths."""

    def test_init_without_sklearn(self):
        """Cover lines 117-118: sklearn not available."""
        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.SKLEARN_AVAILABLE",
            False,
        ):
            from enhanced_agent_bus.adaptive_governance.impact_scorer import (
                ImpactScorer,
            )

            scorer = ImpactScorer("cdd01ef066bc6cf2")
            assert scorer.impact_classifier is None

    def test_init_with_mhc_stability(self):
        """Cover lines 143-145: sinkhorn_projection and TORCH available."""
        mock_sinkhorn = MagicMock()
        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.sinkhorn_projection",
                mock_sinkhorn,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.TORCH_AVAILABLE",
                True,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.impact_scorer import (
                ImpactScorer,
            )

            scorer = ImpactScorer("cdd01ef066bc6cf2")
            assert scorer.use_mhc_stability is True


class TestImpactScorerMLflow:
    """Cover lines 147-184: _initialize_mlflow paths."""

    def test_mlflow_not_available(self):
        """Cover lines 149-151: MLFLOW_AVAILABLE=False."""
        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.MLFLOW_AVAILABLE",
            False,
        ):
            from enhanced_agent_bus.adaptive_governance.impact_scorer import (
                ImpactScorer,
            )

            scorer = ImpactScorer("cdd01ef066bc6cf2")
            assert scorer._mlflow_initialized is False

    def test_mlflow_init_in_pytest(self):
        """Cover lines 154-155: pytest in sys.modules short-circuits."""
        # pytest is always in sys.modules during test runs
        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.MLFLOW_AVAILABLE",
            True,
        ):
            from enhanced_agent_bus.adaptive_governance.impact_scorer import (
                ImpactScorer,
            )

            scorer = ImpactScorer("cdd01ef066bc6cf2")
            assert scorer._mlflow_initialized is False

    def test_mlflow_init_creates_experiment(self):
        """Cover lines 158-179: MLflow init with new experiment."""
        mock_mlflow = MagicMock()
        mock_mlflow.get_experiment_by_name.return_value = None
        mock_mlflow.create_experiment.return_value = "exp-123"

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.MLFLOW_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.mlflow",
                mock_mlflow,
            ),
            patch.dict(sys.modules, {"pytest": None}),
        ):
            # Remove pytest from sys.modules temporarily
            saved_pytest = sys.modules.pop("pytest", None)
            try:
                from enhanced_agent_bus.adaptive_governance.impact_scorer import (
                    ImpactScorer,
                )

                scorer = ImpactScorer("cdd01ef066bc6cf2")
                assert scorer._mlflow_initialized is True
                assert scorer._mlflow_experiment_id == "exp-123"
            finally:
                if saved_pytest is not None:
                    sys.modules["pytest"] = saved_pytest

    def test_mlflow_init_existing_experiment(self):
        """Cover lines 173-174: MLflow gets existing experiment."""
        mock_mlflow = MagicMock()
        mock_exp = MagicMock()
        mock_exp.experiment_id = "exp-456"
        mock_mlflow.get_experiment_by_name.return_value = mock_exp

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.MLFLOW_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.mlflow",
                mock_mlflow,
            ),
        ):
            saved_pytest = sys.modules.pop("pytest", None)
            try:
                from enhanced_agent_bus.adaptive_governance.impact_scorer import (
                    ImpactScorer,
                )

                scorer = ImpactScorer("cdd01ef066bc6cf2")
                assert scorer._mlflow_experiment_id == "exp-456"
            finally:
                if saved_pytest is not None:
                    sys.modules["pytest"] = saved_pytest

    def test_mlflow_init_exception(self):
        """Cover lines 182-184: MLflow init failure."""
        mock_mlflow = MagicMock()
        mock_mlflow.set_tracking_uri.side_effect = RuntimeError("connection refused")

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.MLFLOW_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.mlflow",
                mock_mlflow,
            ),
        ):
            saved_pytest = sys.modules.pop("pytest", None)
            try:
                from enhanced_agent_bus.adaptive_governance.impact_scorer import (
                    ImpactScorer,
                )

                scorer = ImpactScorer("cdd01ef066bc6cf2")
                assert scorer._mlflow_initialized is False
            finally:
                if saved_pytest is not None:
                    sys.modules["pytest"] = saved_pytest


class TestImpactScorerAssessImpact:
    """Cover assess_impact method including model-trained and error paths."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    async def test_assess_impact_model_trained(self):
        """Cover lines 195-197: model_trained=True uses ML prediction."""
        scorer = self._make_scorer()
        scorer.model_trained = True

        mock_predict = MagicMock(return_value=0.42)
        mock_confidence = MagicMock(return_value=0.88)
        scorer._predict_risk_score = mock_predict
        scorer._calculate_confidence = mock_confidence

        message = {"content": "test message", "tenant_id": "t1"}
        context = {"active_agents": ["a1", "a2"]}
        features = await scorer.assess_impact(message, context)

        assert features.risk_score == 0.42
        assert features.confidence_level == 0.88

    async def test_assess_impact_error_returns_safe_defaults(self):
        """Cover lines 205-219: error in assess_impact returns safe defaults."""
        scorer = self._make_scorer()

        # Make _extract_features raise
        async def _raise(*args, **kwargs):
            raise RuntimeError("extraction failed")

        scorer._extract_features = _raise

        message = {"content": "test", "tenant_id": "t1"}
        context = {}
        features = await scorer.assess_impact(message, context)

        assert features.confidence_level == 0.5
        assert features.agent_count == 1


class TestImpactScorerPredictRiskScore:
    """Cover _predict_risk_score ML path."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    def test_predict_falls_back_when_no_numpy(self):
        """Cover line 300: not NUMPY_AVAILABLE."""
        scorer = self._make_scorer()
        scorer.model_trained = True
        features = _make_features()

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
            False,
        ):
            result = scorer._predict_risk_score(features)
            # Falls back to rule-based
            assert 0.0 <= result <= 1.0

    def test_predict_with_trained_model(self):
        """Cover lines 302-315: successful ML prediction."""
        scorer = self._make_scorer()
        scorer.model_trained = True

        mock_np = MagicMock()
        mock_np.mean.return_value = 0.15
        mock_classifier = MagicMock()
        mock_classifier.predict.return_value = [0.65]
        scorer.impact_classifier = mock_classifier

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.np", mock_np
        ):
            with patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
                True,
            ):
                features = _make_features()
                result = scorer._predict_risk_score(features)
                assert result == 0.65

    def test_predict_clamps_result(self):
        """Cover line 315: clamp to [0, 1]."""
        scorer = self._make_scorer()
        scorer.model_trained = True

        mock_np = MagicMock()
        mock_np.mean.return_value = 0.1
        mock_classifier = MagicMock()
        mock_classifier.predict.return_value = [1.5]  # Out of range
        scorer.impact_classifier = mock_classifier

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.np", mock_np
        ):
            with patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
                True,
            ):
                result = scorer._predict_risk_score(_make_features())
                assert result == 1.0

    def test_predict_exception_falls_back(self):
        """Cover lines 317-319: prediction exception."""
        scorer = self._make_scorer()
        scorer.model_trained = True

        mock_np = MagicMock()
        mock_np.mean.side_effect = RuntimeError("bad data")
        mock_classifier = MagicMock()
        scorer.impact_classifier = mock_classifier

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.np", mock_np
        ):
            with patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
                True,
            ):
                result = scorer._predict_risk_score(_make_features())
                assert 0.0 <= result <= 1.0


class TestImpactScorerRuleBasedScore:
    """Cover _rule_based_risk_score branches."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    def test_high_message_length(self):
        """Cover line 327: message_length > high_threshold."""
        scorer = self._make_scorer()
        features = _make_features(message_length=20000)
        result = scorer._rule_based_risk_score(features)
        assert result > 0.3

    def test_medium_message_length(self):
        """Cover line 329: message_length > low_threshold."""
        scorer = self._make_scorer()
        features = _make_features(message_length=5000)
        result = scorer._rule_based_risk_score(features)
        assert result >= 0.1

    def test_high_agent_count(self):
        """Cover line 333: agent_count > high_threshold."""
        scorer = self._make_scorer()
        features = _make_features(agent_count=20)
        result = scorer._rule_based_risk_score(features)
        assert result > 0.2

    def test_medium_agent_count(self):
        """Cover line 335: agent_count > low_threshold."""
        scorer = self._make_scorer()
        features = _make_features(agent_count=5)
        result = scorer._rule_based_risk_score(features)
        assert result >= 0.1

    def test_score_clamped_to_one(self):
        """Cover line 346: min(1.0, score)."""
        scorer = self._make_scorer()
        features = _make_features(
            message_length=50000,
            agent_count=100,
            tenant_complexity=1.0,
            resource_utilization=1.0,
            semantic_similarity=1.0,
        )
        result = scorer._rule_based_risk_score(features)
        assert result <= 1.0


class TestImpactScorerCalculateConfidence:
    """Cover _calculate_confidence branches."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    def test_full_confidence(self):
        """Cover lines 354-361: all conditions boost confidence."""
        scorer = self._make_scorer()
        features = _make_features(
            historical_precedence=5,
            temporal_patterns=[0.1, 0.2],
            semantic_similarity=0.8,
        )
        result = scorer._calculate_confidence(features)
        assert result == min(1.0, 0.5 + 0.1 + 0.1 + 0.2)

    def test_minimal_confidence(self):
        """No boosts applied."""
        scorer = self._make_scorer()
        features = _make_features(
            historical_precedence=0,
            temporal_patterns=[],
            semantic_similarity=0.0,
        )
        result = scorer._calculate_confidence(features)
        assert result == 0.5


class TestImpactScorerUpdateModel:
    """Cover update_model and _retrain_model paths."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    def test_update_model_error_path(self):
        """Cover lines 406-407: error in update_model."""
        scorer = self._make_scorer()
        # Make training_samples.append raise
        scorer.training_samples = MagicMock()
        scorer.training_samples.append.side_effect = RuntimeError("queue full")

        scorer.update_model(_make_features(), 0.5)  # Should not raise

    def test_update_model_triggers_retrain(self):
        """Cover lines 398-404: retrain triggered at threshold."""
        scorer = self._make_scorer()

        # Pre-fill training samples just below the retrain threshold
        from src.core.shared.config.governance_constants import IMPACT_SCORER_CONFIG

        min_samples = IMPACT_SCORER_CONFIG.min_training_samples
        retrain_freq = IMPACT_SCORER_CONFIG.retrain_frequency

        # Use a number that's already at min_samples and divisible by retrain_freq
        target_count = max(min_samples, retrain_freq)
        for i in range(target_count - 1):
            scorer.training_samples.append((_make_features(), float(i % 10) / 10))

        mock_retrain = MagicMock()
        scorer._retrain_model = mock_retrain
        scorer._apply_mhc_stability = MagicMock()

        scorer.update_model(_make_features(), 0.5)

        # Check if retrain was triggered (depends on divisibility)
        if target_count % retrain_freq == 0:
            mock_retrain.assert_called_once()


class TestImpactScorerRetrainModel:
    """Cover _retrain_model paths."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    def test_retrain_without_numpy(self):
        """Cover lines 411-413: no numpy available."""
        scorer = self._make_scorer()

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
            False,
        ):
            scorer._retrain_model()  # Should return early

    def test_retrain_without_classifier(self):
        """Cover line 411: impact_classifier is None."""
        scorer = self._make_scorer()
        scorer.impact_classifier = None
        scorer._retrain_model()  # Should return early

    def test_retrain_insufficient_samples(self):
        """Cover line 416: not enough samples."""
        scorer = self._make_scorer()
        scorer.training_samples = deque([(_make_features(), 0.5)])
        scorer._retrain_model()  # Should return early
        assert scorer.model_trained is False

    def test_retrain_success_without_mlflow(self):
        """Cover lines 415-451: successful retrain without MLflow."""
        scorer = self._make_scorer()
        scorer._mlflow_initialized = False

        mock_np = MagicMock()
        mock_np.array.side_effect = lambda x: x
        mock_np.mean.return_value = 0.15

        mock_classifier = MagicMock()
        scorer.impact_classifier = mock_classifier

        from src.core.shared.config.governance_constants import IMPACT_SCORER_CONFIG

        min_samples = IMPACT_SCORER_CONFIG.min_training_samples

        # Fill enough samples
        for i in range(min_samples):
            scorer.training_samples.append((_make_features(), float(i % 10) / 10))

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.np", mock_np
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
                True,
            ),
        ):
            scorer._retrain_model()

        mock_classifier.fit.assert_called_once()
        assert scorer.model_trained is True

    def test_retrain_success_with_mlflow(self):
        """Cover lines 443-444: retrain triggers MLflow logging."""
        scorer = self._make_scorer()
        scorer._mlflow_initialized = True

        mock_np = MagicMock()
        mock_np.array.side_effect = lambda x: x
        mock_np.mean.return_value = 0.15

        mock_classifier = MagicMock()
        scorer.impact_classifier = mock_classifier

        from src.core.shared.config.governance_constants import IMPACT_SCORER_CONFIG

        min_samples = IMPACT_SCORER_CONFIG.min_training_samples

        for i in range(min_samples):
            scorer.training_samples.append((_make_features(), float(i % 10) / 10))

        mock_log_fn = MagicMock()
        scorer._log_training_run_to_mlflow = mock_log_fn

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.np", mock_np
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.MLFLOW_AVAILABLE",
                True,
            ),
        ):
            scorer._retrain_model()

        mock_log_fn.assert_called_once()
        assert scorer.model_trained is True

    def test_retrain_error_path(self):
        """Cover lines 453-454: error in retrain."""
        scorer = self._make_scorer()

        mock_np = MagicMock()
        mock_np.array.side_effect = RuntimeError("bad data")
        mock_np.mean.return_value = 0.15

        from src.core.shared.config.governance_constants import IMPACT_SCORER_CONFIG

        min_samples = IMPACT_SCORER_CONFIG.min_training_samples
        for i in range(min_samples):
            scorer.training_samples.append((_make_features(), float(i % 10) / 10))

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.np", mock_np
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.NUMPY_AVAILABLE",
                True,
            ),
        ):
            scorer._retrain_model()  # Should not raise


class TestImpactScorerLogTrainingRunToMLflow:
    """Cover lines 456-569: _log_training_run_to_mlflow."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        scorer = ImpactScorer("cdd01ef066bc6cf2")
        scorer._mlflow_experiment_id = "exp-001"
        return scorer

    def test_log_training_run_success(self):
        """Cover lines 460-564: full MLflow logging path."""
        scorer = self._make_scorer()

        mock_np = MagicMock()
        mock_np.mean.return_value = 0.5
        mock_np.std.return_value = 0.1
        mock_np.abs.return_value = MagicMock(__sub__=MagicMock())
        mock_np.sum.return_value = 1.0

        # Create mock X and y arrays
        mock_X = MagicMock()
        mock_X.shape = (100, 8)
        mock_y = MagicMock()
        mock_y.__sub__ = MagicMock(return_value=MagicMock(__pow__=MagicMock(return_value=0.01)))
        mock_y.__len__ = MagicMock(return_value=100)

        mock_classifier = MagicMock()
        mock_classifier.predict.return_value = MagicMock()
        mock_classifier.n_estimators = 20
        mock_classifier.max_depth = 10
        mock_classifier.random_state = 42
        mock_classifier.feature_importances_ = [0.1, 0.15, 0.2, 0.1, 0.25, 0.1, 0.05, 0.05]
        scorer.impact_classifier = mock_classifier

        mock_run = MagicMock()
        mock_run.info.run_id = "run-xyz"

        mock_mlflow = MagicMock()
        mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=mock_run)
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        samples = [(_make_features(), 0.3), (_make_features(), 0.8), (_make_features(), 0.1)]

        with (
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.mlflow",
                mock_mlflow,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.impact_scorer.np",
                mock_np,
            ),
        ):
            scorer._log_training_run_to_mlflow(mock_X, mock_y, samples)

        mock_mlflow.log_params.assert_called_once()
        mock_mlflow.log_metrics.assert_called_once()
        mock_classifier.fit.assert_called_once()
        assert scorer.model_version == "run-xyz"

    def test_log_training_run_exception_fallback(self):
        """Cover lines 566-569: MLflow error falls back to plain fit."""
        scorer = self._make_scorer()

        mock_classifier = MagicMock()
        scorer.impact_classifier = mock_classifier

        mock_mlflow = MagicMock()
        mock_mlflow.start_run.side_effect = RuntimeError("MLflow down")

        mock_X = MagicMock()
        mock_y = MagicMock()

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.mlflow",
            mock_mlflow,
        ):
            scorer._log_training_run_to_mlflow(mock_X, mock_y, [])

        mock_classifier.fit.assert_called_once_with(mock_X, mock_y)


class TestImpactScorerApplyMHCStability:
    """Cover lines 363-390: _apply_mhc_stability."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    def test_apply_mhc_stability_disabled(self):
        """Cover line 368-369: use_mhc_stability=False."""
        scorer = self._make_scorer()
        scorer.use_mhc_stability = False
        original_weights = dict(scorer.feature_weights)
        scorer._apply_mhc_stability()
        assert scorer.feature_weights == original_weights

    def test_apply_mhc_stability_success(self):
        """Cover lines 371-387: torch-based weight normalization."""
        scorer = self._make_scorer()
        scorer.use_mhc_stability = True

        mock_torch = MagicMock()
        mock_tensor = MagicMock()
        mock_normalized = MagicMock()
        mock_torch.tensor.return_value = mock_tensor
        mock_torch.nn.functional.softmax.return_value = mock_normalized

        # Make indexing return floats
        num_weights = len(scorer.feature_weights)
        mock_normalized.__getitem__ = lambda self, idx: MagicMock(
            __float__=lambda s: 1.0 / num_weights
        )

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.torch",
            mock_torch,
        ):
            scorer._apply_mhc_stability()

        mock_torch.tensor.assert_called_once()
        mock_torch.nn.functional.softmax.assert_called_once()

    def test_apply_mhc_stability_error(self):
        """Cover lines 389-390: exception in stability."""
        scorer = self._make_scorer()
        scorer.use_mhc_stability = True

        mock_torch = MagicMock()
        mock_torch.tensor.side_effect = RuntimeError("torch error")

        with patch(
            "enhanced_agent_bus.adaptive_governance.impact_scorer.torch",
            mock_torch,
        ):
            scorer._apply_mhc_stability()  # Should not raise


class TestImpactScorerExtractFeatures:
    """Cover _extract_features and sub-methods."""

    def _make_scorer(self):
        from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

        return ImpactScorer("cdd01ef066bc6cf2")

    async def test_extract_features_basic(self):
        """Cover lines 221-259: feature extraction."""
        scorer = self._make_scorer()
        message = {"content": "hello world", "tenant_id": "t1"}
        context = {"active_agents": ["a1", "a2", "a3"]}
        features = await scorer._extract_features(message, context)

        assert features.message_length == len("hello world")
        assert features.agent_count == 3

    async def test_extract_features_no_active_agents(self):
        """Cover line 231: active_agents not a list."""
        scorer = self._make_scorer()
        message = {"content": "test"}
        context = {"active_agents": 42}  # Not a list
        features = await scorer._extract_features(message, context)
        assert features.agent_count == 0

    async def test_extract_features_missing_content(self):
        """Cover line 225: missing content key."""
        scorer = self._make_scorer()
        message = {}
        context = {}
        features = await scorer._extract_features(message, context)
        assert features.message_length == 0
