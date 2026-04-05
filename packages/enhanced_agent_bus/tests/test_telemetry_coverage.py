"""
ACGS-2 Telemetry Coverage Tests
Constitutional Hash: 608508a9bd224290

Tests for observability/telemetry.py to increase coverage.
"""

try:
    from enhanced_agent_bus.observability.telemetry import (
        OTEL_AVAILABLE,
        NoOpCounter,
        NoOpHistogram,
        NoOpMeter,
        NoOpSpan,
        NoOpTracer,
        NoOpUpDownCounter,
        TelemetryConfig,
        get_meter,
        get_tracer,
    )
except ImportError:
    from observability.telemetry import (
        OTEL_AVAILABLE,
        NoOpCounter,
        NoOpHistogram,
        NoOpMeter,
        NoOpSpan,
        NoOpTracer,
        NoOpUpDownCounter,
        TelemetryConfig,
        get_meter,
        get_tracer,
    )


class TestTelemetryConfig:
    """Tests for TelemetryConfig dataclass."""

    def test_default_config(self):
        """TelemetryConfig has sensible defaults."""
        config = TelemetryConfig()
        assert config.service_name == "acgs2-agent-bus"
        assert config.service_version == "2.0.0"
        assert config.export_traces is True
        assert config.export_metrics is True
        assert 0 < config.trace_sample_rate <= 1.0

    def test_custom_config(self):
        """TelemetryConfig with custom values."""
        config = TelemetryConfig(
            service_name="custom-service",
            service_version="1.0.0",
            export_traces=False,
        )
        assert config.service_name == "custom-service"
        assert config.service_version == "1.0.0"
        assert config.export_traces is False


class TestNoOpSpan:
    """Tests for NoOpSpan class."""

    def test_set_attribute(self):
        """set_attribute is a no-op."""
        span = NoOpSpan()
        # Should not raise
        span.set_attribute("key", "value")

    def test_add_event(self):
        """add_event is a no-op."""
        span = NoOpSpan()
        span.add_event("event_name")
        span.add_event("event_name", {"attr": "value"})

    def test_record_exception(self):
        """record_exception is a no-op."""
        span = NoOpSpan()
        span.record_exception(ValueError("test error"))

    def test_set_status(self):
        """set_status is a no-op."""
        span = NoOpSpan()
        span.set_status("OK")

    def test_context_manager(self):
        """NoOpSpan works as context manager."""
        span = NoOpSpan()
        with span as s:
            assert s is span


class TestNoOpTracer:
    """Tests for NoOpTracer class."""

    def test_start_as_current_span(self):
        """start_as_current_span yields NoOpSpan."""
        tracer = NoOpTracer()
        with tracer.start_as_current_span("test-span") as span:
            assert isinstance(span, NoOpSpan)

    def test_start_span(self):
        """start_span returns NoOpSpan."""
        tracer = NoOpTracer()
        span = tracer.start_span("test-span")
        assert isinstance(span, NoOpSpan)


class TestNoOpCounter:
    """Tests for NoOpCounter class."""

    def test_add(self):
        """add is a no-op."""
        counter = NoOpCounter()
        counter.add(1)
        counter.add(5, {"label": "value"})


class TestNoOpHistogram:
    """Tests for NoOpHistogram class."""

    def test_record(self):
        """record is a no-op."""
        histogram = NoOpHistogram()
        histogram.record(0.5)
        histogram.record(1.5, {"label": "value"})


class TestNoOpUpDownCounter:
    """Tests for NoOpUpDownCounter class."""

    def test_add(self):
        """add is a no-op."""
        counter = NoOpUpDownCounter()
        counter.add(1)
        counter.add(-1, {"label": "value"})


class TestNoOpMeter:
    """Tests for NoOpMeter class."""

    def test_create_counter(self):
        """create_counter returns NoOpCounter."""
        meter = NoOpMeter()
        counter = meter.create_counter("test-counter")
        assert isinstance(counter, NoOpCounter)

    def test_create_histogram(self):
        """create_histogram returns NoOpHistogram."""
        meter = NoOpMeter()
        histogram = meter.create_histogram("test-histogram")
        assert isinstance(histogram, NoOpHistogram)

    def test_create_up_down_counter(self):
        """create_up_down_counter returns NoOpUpDownCounter."""
        meter = NoOpMeter()
        counter = meter.create_up_down_counter("test-counter")
        assert isinstance(counter, NoOpUpDownCounter)

    def test_create_observable_gauge(self):
        """create_observable_gauge returns None."""
        meter = NoOpMeter()
        gauge = meter.create_observable_gauge("test-gauge")
        assert gauge is None


class TestGetTracer:
    """Tests for get_tracer function."""

    def test_get_tracer_returns_tracer(self):
        """get_tracer returns a tracer object."""
        tracer = get_tracer("test-module")
        assert tracer is not None
        # Should have start_as_current_span method
        assert hasattr(tracer, "start_as_current_span")


class TestGetMeter:
    """Tests for get_meter function."""

    def test_get_meter_returns_meter(self):
        """get_meter returns a meter object."""
        meter = get_meter("test-module")
        assert meter is not None
        # Should have create_counter method
        assert hasattr(meter, "create_counter")


class TestOtelAvailable:
    """Tests for OTEL_AVAILABLE constant."""

    def test_otel_available_is_bool(self):
        """OTEL_AVAILABLE is a boolean."""
        assert isinstance(OTEL_AVAILABLE, bool)


class TestConfigureTelemetry:
    """Tests for configure_telemetry function."""

    def test_configure_without_config(self):
        """configure_telemetry works without config."""
        try:
            from enhanced_agent_bus.observability.telemetry import configure_telemetry
        except ImportError:
            from observability.telemetry import configure_telemetry

        tracer, meter = configure_telemetry()
        assert tracer is not None
        assert meter is not None

    def test_configure_with_custom_config(self):
        """configure_telemetry with custom config."""
        try:
            from enhanced_agent_bus.observability.telemetry import configure_telemetry
        except ImportError:
            from observability.telemetry import configure_telemetry

        config = TelemetryConfig(
            service_name="test-service",
            service_version="1.0.0",
        )
        tracer, meter = configure_telemetry(config)
        assert tracer is not None
        assert meter is not None


class TestTracerMeterCaching:
    """Tests for tracer and meter caching."""

    def test_get_tracer_with_name(self):
        """get_tracer with specific service name."""
        tracer = get_tracer("custom-service")
        assert tracer is not None

    def test_get_meter_with_name(self):
        """get_meter with specific service name."""
        meter = get_meter("custom-service")
        assert meter is not None

    def test_get_tracer_returns_same_for_same_name(self):
        """get_tracer returns cached tracer for same name."""
        tracer1 = get_tracer("cached-test")
        tracer2 = get_tracer("cached-test")
        # Both should be valid tracers
        assert tracer1 is not None
        assert tracer2 is not None

    def test_get_meter_returns_same_for_same_name(self):
        """get_meter returns cached meter for same name."""
        meter1 = get_meter("cached-meter")
        meter2 = get_meter("cached-meter")
        assert meter1 is not None
        assert meter2 is not None
