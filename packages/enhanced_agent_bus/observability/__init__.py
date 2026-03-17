"""
ACGS-2 Observability Module
Constitutional Hash: cdd01ef066bc6cf2

Unified OpenTelemetry instrumentation for the enhanced agent bus
and breakthrough architecture layers.

Components:
- telemetry: Core OpenTelemetry integration
- prometheus_metrics: Prometheus metrics per SPEC Section 6.1
- structured_logging: Structured JSON logging per SPEC Section 6.2
- batch_metrics: Batch processing metrics
- timeout_budget: Timeout management
- capacity_metrics: Capacity planning metrics for scaling decisions
"""

from .batch_metrics import (
    BatchMetrics,
    BatchRequestTimer,
    ItemTimer,
    get_batch_metrics,
    reset_batch_metrics,
)

# Capacity planning metrics
from .capacity_metrics import (
    # Performance metrics
    CacheLayer,
    CacheMissReason,
    CapacitySnapshot,
    CapacityStatus,
    EnhancedAgentBusCapacityMetrics,
    LatencyPercentiles,
    PerformanceMetricsRegistry,
    QueueMetrics,
    ResourceUtilization,
    ThroughputMetrics,
    adaptive_threshold_timer,
    batch_overhead_timer,
    deliberation_layer_timer,
    get_capacity_metrics,
    get_performance_metrics,
    maci_enforcement_timer,
    opa_policy_timer,
    record_adaptive_threshold_decision,
    record_batch_processing_overhead,
    record_cache_miss,
    record_constitutional_validation,
    record_deliberation_layer_duration,
    record_maci_enforcement_latency,
    record_opa_policy_evaluation,
    record_z3_solver_latency,
    reset_capacity_metrics,
    reset_performance_metrics,
    track_async_request_latency,
    track_request_latency,
    z3_solver_timer,
)
from .capacity_metrics import (
    ValidationResult as CapacityValidationResult,
)
from .decorators import metered, timed, traced

# Prometheus metrics per SPEC_ACGS2_ENHANCED.md Section 6.1
from .prometheus_metrics import (
    CRITICAL_ALERTS,
    HIGH_ALERTS,
    WARNING_ALERTS,
    CacheOperation,
    CacheTier,
    MetricsCollector,
    PolicyDecision,
    ValidationResult,
    create_metrics_endpoint,
    generate_prometheus_alert_rules,
    get_metrics_collector,
    reset_metrics_collector,
)

# Structured logging per SPEC_ACGS2_ENHANCED.md Section 6.2
from .structured_logging import (
    LogLevel,
    StructuredJSONFormatter,
    StructuredLogger,
    clear_trace_context,
    configure_structured_logging,
    get_structured_logger,
    get_trace_context,
    redact_dict,
    redact_sensitive_data,
    reset_structured_logger,
    set_trace_context,
)
from .telemetry import (
    CONSTITUTIONAL_HASH,
    OTEL_AVAILABLE,
    MetricsRegistry,
    TracingContext,
    configure_telemetry,
    get_meter,
    get_tracer,
)
from .timeout_budget import LayerTimeoutBudget, LayerTimeoutError, TimeoutBudgetManager

__all__ = [
    "CONSTITUTIONAL_HASH",
    "CRITICAL_ALERTS",
    "HIGH_ALERTS",
    "OTEL_AVAILABLE",
    "WARNING_ALERTS",
    # Batch metrics
    "BatchMetrics",
    "BatchRequestTimer",
    # Performance metrics
    "CacheLayer",
    "CacheMissReason",
    "CacheOperation",
    "CacheTier",
    "CapacitySnapshot",
    "CapacityStatus",
    "CapacityValidationResult",
    # Capacity metrics
    "EnhancedAgentBusCapacityMetrics",
    "ItemTimer",
    "LatencyPercentiles",
    # Timeout management
    "LayerTimeoutBudget",
    "LayerTimeoutError",
    "LogLevel",
    # Prometheus metrics (Section 6.1)
    "MetricsCollector",
    "MetricsRegistry",
    "PerformanceMetricsRegistry",
    "PolicyDecision",
    "QueueMetrics",
    "ResourceUtilization",
    "StructuredJSONFormatter",
    # Structured logging (Section 6.2)
    "StructuredLogger",
    "ThroughputMetrics",
    "TimeoutBudgetManager",
    "TracingContext",
    "ValidationResult",
    "adaptive_threshold_timer",
    "batch_overhead_timer",
    "clear_trace_context",
    "configure_structured_logging",
    # Core telemetry
    "configure_telemetry",
    "create_metrics_endpoint",
    "deliberation_layer_timer",
    "generate_prometheus_alert_rules",
    "get_batch_metrics",
    "get_capacity_metrics",
    "get_meter",
    "get_metrics_collector",
    "get_performance_metrics",
    "get_structured_logger",
    "get_trace_context",
    "get_tracer",
    "maci_enforcement_timer",
    "metered",
    "opa_policy_timer",
    "record_adaptive_threshold_decision",
    "record_batch_processing_overhead",
    "record_cache_miss",
    "record_constitutional_validation",
    "record_deliberation_layer_duration",
    "record_maci_enforcement_latency",
    "record_opa_policy_evaluation",
    "record_z3_solver_latency",
    "redact_dict",
    "redact_sensitive_data",
    "reset_batch_metrics",
    "reset_capacity_metrics",
    "reset_metrics_collector",
    "reset_performance_metrics",
    "reset_structured_logger",
    "set_trace_context",
    "timed",
    # Decorators
    "traced",
    "track_async_request_latency",
    "track_request_latency",
    "z3_solver_timer",
]
