"""
ACGS-2 Observability Module
Constitutional Hash: 608508a9bd224290

Keep package imports lightweight. Many callers import leaf modules such as
``enhanced_agent_bus.observability.structured_logging``; eager package-level
imports make those imports pay for the entire observability surface and can
trigger circular/heavy initialization during tests.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, str] = {
    "BatchMetrics": ".batch_metrics",
    "BatchRequestTimer": ".batch_metrics",
    "ItemTimer": ".batch_metrics",
    "get_batch_metrics": ".batch_metrics",
    "reset_batch_metrics": ".batch_metrics",
    "CacheLayer": ".capacity_metrics",
    "CacheMissReason": ".capacity_metrics",
    "CapacitySnapshot": ".capacity_metrics",
    "CapacityStatus": ".capacity_metrics",
    "EnhancedAgentBusCapacityMetrics": ".capacity_metrics",
    "LatencyPercentiles": ".capacity_metrics",
    "PerformanceMetricsRegistry": ".capacity_metrics",
    "QueueMetrics": ".capacity_metrics",
    "ResourceUtilization": ".capacity_metrics",
    "ThroughputMetrics": ".capacity_metrics",
    "adaptive_threshold_timer": ".capacity_metrics",
    "batch_overhead_timer": ".capacity_metrics",
    "deliberation_layer_timer": ".capacity_metrics",
    "get_capacity_metrics": ".capacity_metrics",
    "get_performance_metrics": ".capacity_metrics",
    "maci_enforcement_timer": ".capacity_metrics",
    "opa_policy_timer": ".capacity_metrics",
    "record_adaptive_threshold_decision": ".capacity_metrics",
    "record_batch_processing_overhead": ".capacity_metrics",
    "record_cache_miss": ".capacity_metrics",
    "record_constitutional_validation": ".capacity_metrics",
    "record_deliberation_layer_duration": ".capacity_metrics",
    "record_maci_enforcement_latency": ".capacity_metrics",
    "record_opa_policy_evaluation": ".capacity_metrics",
    "record_z3_solver_latency": ".capacity_metrics",
    "reset_capacity_metrics": ".capacity_metrics",
    "reset_performance_metrics": ".capacity_metrics",
    "track_async_request_latency": ".capacity_metrics",
    "track_request_latency": ".capacity_metrics",
    "z3_solver_timer": ".capacity_metrics",
    "CapacityValidationResult": ".capacity_metrics",
    "metered": ".decorators",
    "timed": ".decorators",
    "traced": ".decorators",
    "CRITICAL_ALERTS": ".prometheus_metrics",
    "HIGH_ALERTS": ".prometheus_metrics",
    "WARNING_ALERTS": ".prometheus_metrics",
    "CacheOperation": ".prometheus_metrics",
    "CacheTier": ".prometheus_metrics",
    "MetricsCollector": ".prometheus_metrics",
    "PolicyDecision": ".prometheus_metrics",
    "ValidationResult": ".prometheus_metrics",
    "create_metrics_endpoint": ".prometheus_metrics",
    "generate_prometheus_alert_rules": ".prometheus_metrics",
    "get_metrics_collector": ".prometheus_metrics",
    "reset_metrics_collector": ".prometheus_metrics",
    "LogLevel": ".structured_logging",
    "StructuredJSONFormatter": ".structured_logging",
    "StructuredLogger": ".structured_logging",
    "clear_trace_context": ".structured_logging",
    "configure_structured_logging": ".structured_logging",
    "get_structured_logger": ".structured_logging",
    "get_trace_context": ".structured_logging",
    "redact_dict": ".structured_logging",
    "redact_sensitive_data": ".structured_logging",
    "reset_structured_logger": ".structured_logging",
    "set_trace_context": ".structured_logging",
    "CONSTITUTIONAL_HASH": ".telemetry",
    "OTEL_AVAILABLE": ".telemetry",
    "MetricsRegistry": ".telemetry",
    "TracingContext": ".telemetry",
    "configure_telemetry": ".telemetry",
    "get_meter": ".telemetry",
    "get_tracer": ".telemetry",
    "LayerTimeoutBudget": ".timeout_budget",
    "LayerTimeoutError": ".timeout_budget",
    "TimeoutBudgetManager": ".timeout_budget",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = importlib.import_module(module_name, __name__)
    if name == "CapacityValidationResult":
        value = module.ValidationResult
    else:
        value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
