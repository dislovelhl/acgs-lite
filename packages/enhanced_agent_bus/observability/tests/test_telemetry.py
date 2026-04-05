from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

"""
ACGS-2 Telemetry Tests
Constitutional Hash: 608508a9bd224290
"""

import pytest

try:
    from ..telemetry import (
        CONSTITUTIONAL_HASH,
        OTEL_AVAILABLE,
        MetricsRegistry,
        NoOpCounter,
        NoOpHistogram,
        NoOpMeter,
        NoOpSpan,
        NoOpTracer,
        NoOpUpDownCounter,
        TelemetryConfig,
        TracingContext,
        get_meter,
        get_tracer,
    )
except ImportError:
    from observability.telemetry import (
        CONSTITUTIONAL_HASH,  # type: ignore
        OTEL_AVAILABLE,
        MetricsRegistry,
        NoOpCounter,
        NoOpHistogram,
        NoOpMeter,
        NoOpSpan,
        NoOpTracer,
        NoOpUpDownCounter,
        TelemetryConfig,
        TracingContext,
        get_meter,
        get_tracer,
    )


class TestTelemetryConfig:
    """Tests for TelemetryConfig."""

    def test_default_values(self):
        """Config has sensible defaults."""
        config = TelemetryConfig()

        assert config.service_name == "acgs2-agent-bus"
        assert config.service_version == "2.0.0"
        assert config.export_traces is True
        assert config.export_metrics is True
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        """Config accepts custom values."""
        config = TelemetryConfig(
            service_name="custom-service",
            service_version="1.0.0",
            trace_sample_rate=0.5,
        )

        assert config.service_name == "custom-service"
        assert config.service_version == "1.0.0"
        assert config.trace_sample_rate == 0.5


class TestNoOpImplementations:
    """Tests for no-op fallback implementations."""

    def test_noop_span(self):
        """NoOpSpan methods work without error."""
        span = NoOpSpan()

        # All methods should be callable
        span.set_attribute("key", "value")
        span.add_event("event", {"attr": "value"})
        span.record_exception(Exception("test"))
        span.set_status("ok")

        # Context manager works
        with span as s:
            assert s is span

    def test_noop_tracer(self):
        """NoOpTracer creates NoOpSpans."""
        tracer = NoOpTracer()

        # Context manager method
        with tracer.start_as_current_span("test_span") as span:
            assert isinstance(span, NoOpSpan)

        # Direct span creation
        span = tracer.start_span("another_span")
        assert isinstance(span, NoOpSpan)

    def test_noop_counter(self):
        """NoOpCounter accepts additions."""
        counter = NoOpCounter()
        counter.add(1)
        counter.add(5, {"attr": "value"})

    def test_noop_histogram(self):
        """NoOpHistogram accepts recordings."""
        histogram = NoOpHistogram()
        histogram.record(1.5)
        histogram.record(2.5, {"attr": "value"})

    def test_noop_updown_counter(self):
        """NoOpUpDownCounter accepts additions."""
        counter = NoOpUpDownCounter()
        counter.add(1)
        counter.add(-1, {"attr": "value"})

    def test_noop_meter(self):
        """NoOpMeter creates no-op instruments."""
        meter = NoOpMeter()

        counter = meter.create_counter("test_counter")
        assert isinstance(counter, NoOpCounter)

        histogram = meter.create_histogram("test_histogram")
        assert isinstance(histogram, NoOpHistogram)

        updown = meter.create_up_down_counter("test_updown")
        assert isinstance(updown, NoOpUpDownCounter)

        gauge = meter.create_observable_gauge("test_gauge")
        assert gauge is None


class TestTracingContext:
    """Tests for TracingContext."""

    def test_basic_context(self):
        """TracingContext works as context manager."""
        with TracingContext("test_operation") as span:
            span.set_attribute("test.attr", "value")

    def test_with_attributes(self):
        """TracingContext accepts initial attributes."""
        attrs = {"key1": "value1", "key2": 42}
        with TracingContext("test_op", attributes=attrs) as span:
            span.set_attribute("key3", "value3")

    def test_with_service_name(self):
        """TracingContext accepts service name."""
        with TracingContext("test_op", service_name="test-service") as span:
            assert span is not None

    def test_exception_handling(self):
        """TracingContext handles exceptions gracefully."""
        with pytest.raises(ValueError):
            with TracingContext("failing_op") as span:
                raise ValueError("test error")


class TestMetricsRegistry:
    """Tests for MetricsRegistry."""

    def test_registry_creation(self):
        """MetricsRegistry initializes correctly."""
        registry = MetricsRegistry("test-service")

        assert registry.service_name == "test-service"
        assert registry.meter is not None

    def test_counter_creation(self):
        """Registry creates and caches counters."""
        registry = MetricsRegistry()

        counter1 = registry.get_counter("test_counter", "A test counter")
        counter2 = registry.get_counter("test_counter")

        # Should be same instance
        assert counter1 is counter2

    def test_histogram_creation(self):
        """Registry creates and caches histograms."""
        registry = MetricsRegistry()

        hist1 = registry.get_histogram("test_latency", "ms", "Test latency")
        hist2 = registry.get_histogram("test_latency")

        assert hist1 is hist2

    def test_gauge_creation(self):
        """Registry creates and caches gauges."""
        registry = MetricsRegistry()

        gauge1 = registry.get_gauge("active_connections")
        gauge2 = registry.get_gauge("active_connections")

        assert gauge1 is gauge2

    def test_increment_counter(self):
        """increment_counter works correctly."""
        registry = MetricsRegistry()
        registry.increment_counter("requests", 1)
        registry.increment_counter("requests", 5, {"endpoint": "/api"})

    def test_record_latency(self):
        """record_latency works correctly."""
        registry = MetricsRegistry()
        registry.record_latency("request_latency", 5.5)
        registry.record_latency("request_latency", 10.2, {"endpoint": "/api"})

    def test_set_gauge(self):
        """set_gauge works correctly."""
        registry = MetricsRegistry()
        registry.set_gauge("queue_size", 10)
        registry.set_gauge("queue_size", -5, {"queue": "main"})


class TestGetTracer:
    """Tests for get_tracer function."""

    def test_get_default_tracer(self):
        """get_tracer returns a tracer."""
        tracer = get_tracer()
        assert tracer is not None

    def test_get_named_tracer(self):
        """get_tracer with service name works."""
        tracer = get_tracer("my-service")
        assert tracer is not None


class TestGetMeter:
    """Tests for get_meter function."""

    def test_get_default_meter(self):
        """get_meter returns a meter."""
        meter = get_meter()
        assert meter is not None

    def test_get_named_meter(self):
        """get_meter with service name works."""
        meter = get_meter("my-service")
        assert meter is not None


class TestConstitutionalHash:
    """Tests for constitutional hash inclusion."""

    def test_hash_exported(self):
        """CONSTITUTIONAL_HASH is exported."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_otel_available_flag(self):
        """OTEL_AVAILABLE is a boolean."""
        assert isinstance(OTEL_AVAILABLE, bool)
