"""exp222: GovernanceObservabilityExporter — OpenTelemetry-compatible metrics exporter.

Produces structured governance telemetry in OpenTelemetry-compatible formats
without requiring the OTel SDK as a dependency. Outputs can be consumed by
Prometheus, Grafana, Datadog, or any OTel-compatible collector.

Key capabilities:
- Counter, histogram, and gauge metric types for governance operations.
- Pre-defined governance metrics: decision counts, latency histograms,
  violation rates, compliance scores, rule trigger counts.
- Span-like decision trace records for distributed tracing integration.
- Prometheus text exposition format export.
- OTel JSON export for collector ingestion.
- Metric aggregation windows with configurable flush intervals.
- Label/attribute support for multi-dimensional slicing.
- Resource attributes (service.name, constitution.hash, environment).

Usage::

    from acgs_lite.constitution.observability_exporter import GovernanceObservabilityExporter

    exporter = GovernanceObservabilityExporter(
        service_name="my-governance",
        constitution_hash="608508a9bd224290",
    )

    exporter.record_decision(action="deploy", outcome="allow", latency_ms=0.56)
    exporter.record_decision(action="delete data", outcome="deny", latency_ms=0.42,
                             violations=["SAFE-001"])

    print(exporter.prometheus_exposition())
    print(exporter.otel_json())
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _ts_ns() -> int:
    return int(time.time() * 1e9)


def _ts_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class MetricPoint:
    """A single metric data point with labels."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp_ns: int = 0
    metric_type: str = "counter"

    def __post_init__(self) -> None:
        if self.timestamp_ns == 0:
            self.timestamp_ns = _ts_ns()


@dataclass
class HistogramBucket:
    """A single histogram bucket boundary."""

    le: float
    count: int = 0


@dataclass
class HistogramMetric:
    """Cumulative histogram with configurable bucket boundaries."""

    name: str
    labels: dict[str, str] = field(default_factory=dict)
    buckets: list[HistogramBucket] = field(default_factory=list)
    count: int = 0
    total: float = 0.0

    def record(self, value: float) -> None:
        self.count += 1
        self.total += value
        for bucket in self.buckets:
            if value <= bucket.le:
                bucket.count += 1

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count > 0 else 0.0


@dataclass(frozen=True)
class DecisionTrace:
    """Span-like record of a governance decision for tracing integration."""

    trace_id: str
    span_id: str
    action: str
    outcome: str
    latency_ms: float
    violations: tuple[str, ...]
    labels: dict[str, str]
    start_time_ns: int
    end_time_ns: int
    resource_attributes: dict[str, str]

    def to_otel_span(self) -> dict[str, Any]:
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "name": "governance.validate",
            "kind": "SPAN_KIND_INTERNAL",
            "startTimeUnixNano": str(self.start_time_ns),
            "endTimeUnixNano": str(self.end_time_ns),
            "attributes": [
                {"key": "governance.action", "value": {"stringValue": self.action}},
                {"key": "governance.outcome", "value": {"stringValue": self.outcome}},
                {"key": "governance.latency_ms", "value": {"doubleValue": self.latency_ms}},
                {
                    "key": "governance.violation_count",
                    "value": {"intValue": str(len(self.violations))},
                },
            ]
            + [{"key": k, "value": {"stringValue": v}} for k, v in self.labels.items()],
            "status": {
                "code": "STATUS_CODE_OK" if self.outcome == "allow" else "STATUS_CODE_ERROR",
            },
        }


_DEFAULT_LATENCY_BOUNDARIES = [0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0]


class GovernanceObservabilityExporter:
    """Exports governance telemetry in OpenTelemetry-compatible formats.

    Collects decision counters, latency histograms, violation rates, and
    compliance gauges. Exports to Prometheus text format or OTel JSON.

    Args:
        service_name: Service identifier in resource attributes.
        constitution_hash: Constitutional hash for provenance.
        environment: Deployment environment label.
        latency_boundaries_ms: Histogram bucket boundaries in milliseconds.
    """

    def __init__(
        self,
        service_name: str = "acgs-lite",
        constitution_hash: str = "",
        environment: str = "production",
        latency_boundaries_ms: list[float] | None = None,
    ) -> None:
        self._resource = {
            "service.name": service_name,
            "constitution.hash": constitution_hash,
            "deployment.environment": environment,
        }
        boundaries = latency_boundaries_ms or _DEFAULT_LATENCY_BOUNDARIES

        self._decisions_total: dict[str, int] = {}
        self._violations_total: dict[str, int] = {}
        self._rule_triggers: dict[str, int] = {}
        self._latency_histogram = HistogramMetric(
            name="governance_decision_latency_ms",
            buckets=[HistogramBucket(le=b) for b in sorted(boundaries)]
            + [HistogramBucket(le=math.inf)],
        )
        self._traces: list[DecisionTrace] = []
        self._compliance_gauge: float = 1.0
        self._start_time_ns = _ts_ns()
        self._span_counter = 0

    def record_decision(
        self,
        action: str,
        outcome: str,
        latency_ms: float = 0.0,
        violations: list[str] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a governance decision as telemetry."""
        self._decisions_total[outcome] = self._decisions_total.get(outcome, 0) + 1
        self._latency_histogram.record(latency_ms)

        viols = violations or []
        for vid in viols:
            self._violations_total[vid] = self._violations_total.get(vid, 0) + 1
            self._rule_triggers[vid] = self._rule_triggers.get(vid, 0) + 1

        total = sum(self._decisions_total.values())
        denied = self._decisions_total.get("deny", 0) + self._decisions_total.get("block", 0)
        self._compliance_gauge = 1.0 - (denied / total) if total > 0 else 1.0

        self._span_counter += 1
        now_ns = _ts_ns()
        start_ns = now_ns - int(latency_ms * 1e6)
        trace = DecisionTrace(
            trace_id=f"{self._span_counter:032x}",
            span_id=f"{self._span_counter:016x}",
            action=action,
            outcome=outcome,
            latency_ms=latency_ms,
            violations=tuple(viols),
            labels=labels or {},
            start_time_ns=start_ns,
            end_time_ns=now_ns,
            resource_attributes=dict(self._resource),
        )
        self._traces.append(trace)

    def prometheus_exposition(self) -> str:
        """Export metrics in Prometheus text exposition format."""
        lines: list[str] = []

        lines.append("# HELP governance_decisions_total Total governance decisions by outcome")
        lines.append("# TYPE governance_decisions_total counter")
        for outcome, count in sorted(self._decisions_total.items()):
            lines.append(f'governance_decisions_total{{outcome="{outcome}"}} {count}')

        lines.append("")
        lines.append("# HELP governance_violations_total Total violations by rule ID")
        lines.append("# TYPE governance_violations_total counter")
        for vid, count in sorted(self._violations_total.items()):
            lines.append(f'governance_violations_total{{rule_id="{vid}"}} {count}')

        lines.append("")
        lines.append("# HELP governance_decision_latency_ms Decision latency histogram")
        lines.append("# TYPE governance_decision_latency_ms histogram")
        h = self._latency_histogram
        for bucket in h.buckets:
            le_str = "+Inf" if math.isinf(bucket.le) else str(bucket.le)
            lines.append(f'governance_decision_latency_ms_bucket{{le="{le_str}"}} {bucket.count}')
        lines.append(f"governance_decision_latency_ms_count {h.count}")
        lines.append(f"governance_decision_latency_ms_sum {h.total:.6f}")

        lines.append("")
        lines.append("# HELP governance_compliance_rate Current compliance rate")
        lines.append("# TYPE governance_compliance_rate gauge")
        lines.append(f"governance_compliance_rate {self._compliance_gauge:.6f}")

        lines.append("")
        return "\n".join(lines)

    def otel_json(self) -> dict[str, Any]:
        """Export metrics and traces in OTel JSON format for collector ingestion."""
        now_ns = _ts_ns()
        resource = {
            "attributes": [
                {"key": k, "value": {"stringValue": v}} for k, v in self._resource.items()
            ]
        }

        metric_data: list[dict[str, Any]] = []

        for outcome, count in self._decisions_total.items():
            metric_data.append(
                {
                    "name": "governance.decisions.total",
                    "unit": "1",
                    "sum": {
                        "dataPoints": [
                            {
                                "asInt": str(count),
                                "startTimeUnixNano": str(self._start_time_ns),
                                "timeUnixNano": str(now_ns),
                                "attributes": [
                                    {"key": "outcome", "value": {"stringValue": outcome}},
                                ],
                            }
                        ],
                        "aggregationTemporality": "AGGREGATION_TEMPORALITY_CUMULATIVE",
                        "isMonotonic": True,
                    },
                }
            )

        metric_data.append(
            {
                "name": "governance.compliance.rate",
                "unit": "1",
                "gauge": {
                    "dataPoints": [
                        {
                            "asDouble": self._compliance_gauge,
                            "timeUnixNano": str(now_ns),
                        }
                    ],
                },
            }
        )

        h = self._latency_histogram
        bucket_counts = [b.count for b in h.buckets if not math.isinf(b.le)]
        explicit_bounds = [b.le for b in h.buckets if not math.isinf(b.le)]
        metric_data.append(
            {
                "name": "governance.decision.latency",
                "unit": "ms",
                "histogram": {
                    "dataPoints": [
                        {
                            "startTimeUnixNano": str(self._start_time_ns),
                            "timeUnixNano": str(now_ns),
                            "count": str(h.count),
                            "sum": h.total,
                            "bucketCounts": [str(c) for c in bucket_counts] + [str(h.count)],
                            "explicitBounds": explicit_bounds,
                        }
                    ],
                    "aggregationTemporality": "AGGREGATION_TEMPORALITY_CUMULATIVE",
                },
            }
        )

        spans = [t.to_otel_span() for t in self._traces[-100:]]

        return {
            "resourceMetrics": [
                {
                    "resource": resource,
                    "scopeMetrics": [
                        {
                            "scope": {"name": "acgs_lite.governance", "version": "1.0.0"},
                            "metrics": metric_data,
                        }
                    ],
                }
            ],
            "resourceSpans": [
                {
                    "resource": resource,
                    "scopeSpans": [
                        {
                            "scope": {"name": "acgs_lite.governance", "version": "1.0.0"},
                            "spans": spans,
                        }
                    ],
                }
            ]
            if spans
            else [],
        }

    def reset(self) -> None:
        """Reset all counters and histograms."""
        self._decisions_total.clear()
        self._violations_total.clear()
        self._rule_triggers.clear()
        self._latency_histogram = HistogramMetric(
            name="governance_decision_latency_ms",
            buckets=[HistogramBucket(le=b.le) for b in self._latency_histogram.buckets],
        )
        self._traces.clear()
        self._compliance_gauge = 1.0
        self._start_time_ns = _ts_ns()
        self._span_counter = 0

    @property
    def traces(self) -> list[DecisionTrace]:
        return list(self._traces)

    @property
    def rule_trigger_counts(self) -> dict[str, int]:
        return dict(self._rule_triggers)

    @property
    def decision_counts(self) -> dict[str, int]:
        return dict(self._decisions_total)

    @property
    def compliance_gauge(self) -> float:
        return self._compliance_gauge

    def summary(self) -> dict[str, Any]:
        return {
            "resource": self._resource,
            "total_decisions": sum(self._decisions_total.values()),
            "decisions_by_outcome": dict(self._decisions_total),
            "total_violations": sum(self._violations_total.values()),
            "compliance_rate": round(self._compliance_gauge, 6),
            "latency_mean_ms": round(self._latency_histogram.mean, 4),
            "latency_count": self._latency_histogram.count,
            "trace_count": len(self._traces),
            "generated_at": _ts_iso(),
        }
