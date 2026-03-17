"""
OpenTelemetry Configuration for ACGS-2 Services
Constitutional Hash: cdd01ef066bc6cf2

Supports exporting telemetry to configurable OTLP endpoints via environment
variables OTEL_EXPORTER_OTLP_HTTP_ENDPOINT and OTEL_EXPORTER_OTLP_GRPC_ENDPOINT.
"""

import os

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.otel_attributes import get_resource_attributes, validate_resource_attributes
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
from src.core.shared.constants import CONSTITUTIONAL_HASH

# OTLP endpoints — configure via environment variables
GITLAB_OTEL_HTTP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_HTTP_ENDPOINT", "http://localhost:4318"
)
GITLAB_OTEL_GRPC_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_GRPC_ENDPOINT", "http://localhost:4317"
)

try:
    from opentelemetry import metrics, trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

# Global state
_tracer_provider = None
_meter_provider = None
_initialized = False


def init_otel(
    service_name: str,
    app: object | None = None,
    export_to_console: bool = False,
    otlp_endpoint: str | None = None,
    use_http: bool = True,
    enable_metrics: bool = True,
) -> None:
    """
    Initialize OpenTelemetry tracing with ACGS-2 standards.

    Exports to GitLab Observability endpoints by default.

    Args:
        service_name: Name of the service.
        app: Optional FastAPI application to instrument.
        export_to_console: Whether to export spans to console.
        otlp_endpoint: Optional OTLP collector endpoint (uses GitLab default if not set).
        use_http: Use HTTP protocol instead of gRPC (better for GitLab).
        enable_metrics: Enable metrics export alongside traces.
    """
    global _tracer_provider, _meter_provider, _initialized

    if not HAS_OTEL:
        logger.warning("OpenTelemetry packages not installed, skipping initialization")
        return

    if _initialized:
        logger.debug("OpenTelemetry already initialized")
        return

    from src.core.shared.config import settings

    # Determine endpoint - prefer environment variable, then settings, then GitLab default
    endpoint = otlp_endpoint or settings.telemetry.otlp_endpoint
    if not endpoint or endpoint == "http://localhost:4317":
        # Use GitLab endpoint if local endpoint or not configured
        endpoint = GITLAB_OTEL_HTTP_ENDPOINT if use_http else GITLAB_OTEL_GRPC_ENDPOINT

    # Build resource attributes using standardized helper
    resource_attrs = get_resource_attributes(
        service_name=service_name,
        service_version="2.2.0",
    )
    resource_attrs["acgs2.constitutional_hash"] = CONSTITUTIONAL_HASH

    # Validate mandatory attributes
    is_valid, missing = validate_resource_attributes(resource_attrs)
    if not is_valid:
        raise ConfigurationError(
            f"Missing mandatory resource attributes: {missing}",
            error_code="OTEL_MISSING_ATTRIBUTES",
        )

    resource = Resource(attributes=resource_attrs)
    _tracer_provider = TracerProvider(resource=resource)

    if export_to_console:
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        _tracer_provider.add_span_processor(processor)

    # Add OTLP exporter if endpoint is available
    if endpoint:
        if use_http:
            _add_http_trace_exporter(endpoint, _tracer_provider)
        else:
            _add_grpc_trace_exporter(endpoint, _tracer_provider)

    trace.set_tracer_provider(_tracer_provider)

    # Initialize metrics if enabled
    if enable_metrics and settings.telemetry.export_metrics:
        _init_metrics(endpoint, resource, use_http)

    if app:
        FastAPIInstrumentor().instrument_app(app)

    _initialized = True
    logger.info(f"OpenTelemetry initialized for {service_name} -> {endpoint}")


def _add_http_trace_exporter(endpoint: str, provider: object) -> None:
    """Add HTTP-based OTLP trace exporter."""
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        # Ensure endpoint has /v1/traces suffix for HTTP
        trace_endpoint = endpoint if "/v1/traces" in endpoint else f"{endpoint}/v1/traces"
        otlp_exporter = OTLPSpanExporter(endpoint=trace_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.debug(f"HTTP trace exporter configured: {trace_endpoint}")
    except ImportError:
        logger.warning("HTTP OTLP exporter not available, trying gRPC")
        _add_grpc_trace_exporter(endpoint, provider)


def _add_grpc_trace_exporter(endpoint: str, provider: object) -> None:
    """Add gRPC-based OTLP trace exporter."""
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.debug(f"gRPC trace exporter configured: {endpoint}")
    except ImportError:
        logger.warning("gRPC OTLP exporter not available")


def _init_metrics(endpoint: str, resource: object, use_http: bool) -> None:
    """Initialize metrics export."""
    global _meter_provider

    try:
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        if use_http:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

            metric_endpoint = endpoint if "/v1/metrics" in endpoint else f"{endpoint}/v1/metrics"
            metric_exporter = OTLPMetricExporter(endpoint=metric_endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

            metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)

        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter, export_interval_millis=60000
        )
        _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(_meter_provider)
        logger.debug("Metrics exporter configured")
    except ImportError:
        logger.debug("Metrics export not available")


def shutdown_otel() -> None:
    """Shutdown OpenTelemetry and flush pending telemetry."""
    global _tracer_provider, _meter_provider, _initialized

    if not _initialized:
        return

    try:
        if _tracer_provider:
            _tracer_provider.shutdown()
        if _meter_provider:
            _meter_provider.shutdown()
        _initialized = False
        logger.info("OpenTelemetry shutdown complete")
    except Exception as e:
        logger.error(f"Error during OpenTelemetry shutdown: {e}")


def get_current_trace_id() -> str | None:
    """Get the current trace ID if a span is active."""
    if not HAS_OTEL:
        return None

    span = trace.get_current_span()
    if span and span.is_recording():
        return format(span.get_span_context().trace_id, "032x")
    return None


def get_tracer(name: str = "acgs2") -> object:
    """Get a tracer instance for manual instrumentation."""
    if not HAS_OTEL:
        return None
    return trace.get_tracer(name)


def get_meter(name: str = "acgs2") -> object:
    """Get a meter instance for custom metrics."""
    if not HAS_OTEL:
        return None
    return metrics.get_meter(name)
