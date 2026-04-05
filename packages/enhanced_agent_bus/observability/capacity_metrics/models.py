"""
ACGS-2 Capacity Metrics Data Models
Constitutional Hash: 608508a9bd224290

Contains all data models for capacity metrics including:
- CapacityStatus enum for scaling decisions
- LatencyPercentiles for latency measurements
- ThroughputMetrics for throughput tracking
- QueueMetrics for queue depth monitoring
- ResourceUtilization for system resource tracking
- CapacitySnapshot for complete capacity state

This module is part of the capacity_metrics refactoring to improve maintainability
by splitting the original 1478-line file into focused, cohesive modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class CapacityStatus(str, Enum):
    """Capacity status indicators for scaling decisions."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    DEGRADED = "degraded"


@dataclass
class LatencyPercentiles:
    """Container for latency percentile measurements."""

    p50_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
    min_ms: float = 0.0
    avg_ms: float = 0.0
    sample_count: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def is_compliant(self) -> bool:
        """Check if P99 meets constitutional target (<5ms)."""
        return self.p99_ms < 5.0


@dataclass
class ThroughputMetrics:
    """Container for throughput measurements."""

    current_rps: float = 0.0
    peak_rps: float = 0.0
    avg_rps: float = 0.0
    total_requests: int = 0
    window_seconds: int = 60
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def is_compliant(self) -> bool:
        """Check if throughput meets constitutional target (>100 RPS)."""
        return self.current_rps > 100.0


@dataclass
class QueueMetrics:
    """Container for queue depth measurements."""

    current_depth: int = 0
    max_depth: int = 0
    avg_depth: float = 0.0
    enqueue_rate: float = 0.0
    dequeue_rate: float = 0.0
    pending_messages: int = 0
    dlq_depth: int = 0  # Dead letter queue
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ResourceUtilization:
    """Container for resource utilization measurements."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_bytes: int = 0
    thread_count: int = 0
    open_connections: int = 0
    gc_collections: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class CapacitySnapshot:
    """Complete capacity snapshot for planning decisions."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    latency: LatencyPercentiles = field(default_factory=LatencyPercentiles)
    throughput: ThroughputMetrics = field(default_factory=ThroughputMetrics)
    queue: QueueMetrics = field(default_factory=QueueMetrics)
    resources: ResourceUtilization = field(default_factory=ResourceUtilization)
    status: CapacityStatus = CapacityStatus.HEALTHY
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert snapshot to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "latency": {
                "p50_ms": self.latency.p50_ms,
                "p90_ms": self.latency.p90_ms,
                "p95_ms": self.latency.p95_ms,
                "p99_ms": self.latency.p99_ms,
                "max_ms": self.latency.max_ms,
                "min_ms": self.latency.min_ms,
                "avg_ms": self.latency.avg_ms,
                "sample_count": self.latency.sample_count,
                "compliant": self.latency.is_compliant(),
            },
            "throughput": {
                "current_rps": self.throughput.current_rps,
                "peak_rps": self.throughput.peak_rps,
                "avg_rps": self.throughput.avg_rps,
                "total_requests": self.throughput.total_requests,
                "compliant": self.throughput.is_compliant(),
            },
            "queue": {
                "current_depth": self.queue.current_depth,
                "max_depth": self.queue.max_depth,
                "avg_depth": self.queue.avg_depth,
                "enqueue_rate": self.queue.enqueue_rate,
                "dequeue_rate": self.queue.dequeue_rate,
                "pending_messages": self.queue.pending_messages,
                "dlq_depth": self.queue.dlq_depth,
            },
            "resources": {
                "cpu_percent": self.resources.cpu_percent,
                "memory_percent": self.resources.memory_percent,
                "memory_bytes": self.resources.memory_bytes,
                "thread_count": self.resources.thread_count,
                "open_connections": self.resources.open_connections,
            },
            "constitutional_hash": self.constitutional_hash,
        }

    def get_scaling_recommendation(self) -> JSONDict:
        """Generate scaling recommendation based on current metrics."""
        reasons: list[str] = []
        direction = "maintain"
        urgency = "normal"

        # Check latency compliance
        if self.latency.p99_ms > 5.0:
            direction = "scale_up"
            urgency = "immediate"
            reasons.append(
                f"P99 latency {self.latency.p99_ms:.2f}ms exceeds 5ms constitutional target"
            )
        elif self.latency.p99_ms > 3.0:
            direction = "scale_up"
            urgency = "soon"
            reasons.append(f"P99 latency {self.latency.p99_ms:.2f}ms approaching limit")

        # Check queue depth
        if self.queue.current_depth > 500:
            direction = "scale_up"
            urgency = "immediate"
            reasons.append(f"Queue depth {self.queue.current_depth} exceeds critical threshold")
        elif self.queue.current_depth > 100:
            if direction != "scale_up":
                direction = "scale_up"
                urgency = "soon"
            reasons.append(f"Queue depth {self.queue.current_depth} elevated")

        # Check resource utilization
        if self.resources.cpu_percent > 85:
            direction = "scale_up"
            urgency = "immediate"
            reasons.append(f"CPU utilization {self.resources.cpu_percent:.1f}% critical")
        elif self.resources.cpu_percent > 70:
            if urgency != "immediate":
                direction = "scale_up"
                urgency = "soon"
            reasons.append(f"CPU utilization {self.resources.cpu_percent:.1f}% elevated")

        # Check for scale down opportunity
        if (
            direction == "maintain"
            and self.resources.cpu_percent < 30
            and self.queue.current_depth < 10
            and self.latency.p99_ms < 1.0
        ):
            direction = "scale_down"
            urgency = "planned"
            reasons.append("Resources underutilized, scale down possible")

        return {
            "direction": direction,
            "urgency": urgency,
            "reasons": reasons,
            "status": self.status.value,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


__all__ = [
    "CapacitySnapshot",
    "CapacityStatus",
    "LatencyPercentiles",
    "QueueMetrics",
    "ResourceUtilization",
    "ThroughputMetrics",
]
