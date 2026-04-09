"""SLA tracking for governance operations.

Defines service-level objectives per governance operation type (validation,
audit, escalation, etc.) and tracks actual performance against targets —
latency budgets, throughput floors, breach detection, and SLA compliance
reporting.

Example::

    from acgs_lite.constitution.sla import (
        SLAManager, SLATarget, SLAMetricType,
    )

    mgr = SLAManager()
    mgr.define("validation", SLATarget(
        metric=SLAMetricType.LATENCY_P99,
        threshold_ms=10.0,
        description="Validation p99 under 10ms",
    ))
    mgr.record("validation", latency_ms=4.2)
    mgr.record("validation", latency_ms=12.5)
    report = mgr.compliance_report()
    assert report["operations"]["validation"]["breach_count"] >= 1
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class SLAMetricType(str, enum.Enum):
    LATENCY_P50 = "latency_p50"
    LATENCY_P95 = "latency_p95"
    LATENCY_P99 = "latency_p99"
    THROUGHPUT_MIN = "throughput_min"
    ERROR_RATE_MAX = "error_rate_max"
    AVAILABILITY = "availability"


@dataclass
class SLATarget:
    """A single SLA objective for a governance operation."""

    metric: SLAMetricType
    threshold_ms: float = 0.0
    threshold_rate: float = 0.0
    description: str = ""


@dataclass
class SLAObservation:
    """A recorded measurement against an SLA target."""

    operation: str
    latency_ms: float = 0.0
    success: bool = True
    timestamp: float = field(default_factory=time.time)


@dataclass
class SLABreach:
    """Record of an SLA threshold violation."""

    operation: str
    metric: SLAMetricType
    target_value: float
    actual_value: float
    timestamp: float


class SLAManager:
    """Track SLA compliance for governance operations.

    Define per-operation SLA targets, record observations, detect breaches
    in real time, and generate compliance reports with breach counts and
    percentile latencies.

    Example::

        mgr = SLAManager()
        mgr.define("audit_write", SLATarget(
            metric=SLAMetricType.LATENCY_P99, threshold_ms=50.0,
        ))
        for ms in [10, 20, 30, 55]:
            mgr.record("audit_write", latency_ms=ms)
        breaches = mgr.breaches("audit_write")
    """

    def __init__(self) -> None:
        self._targets: dict[str, list[SLATarget]] = {}
        self._observations: dict[str, list[SLAObservation]] = {}
        self._breaches: list[SLABreach] = []

    def define(self, operation: str, target: SLATarget) -> None:
        self._targets.setdefault(operation, []).append(target)

    def remove_targets(self, operation: str) -> bool:
        return self._targets.pop(operation, None) is not None

    def get_targets(self, operation: str) -> list[SLATarget]:
        return list(self._targets.get(operation, []))

    def list_operations(self) -> list[str]:
        return list(self._targets.keys())

    def record(
        self,
        operation: str,
        latency_ms: float = 0.0,
        success: bool = True,
        timestamp: float | None = None,
    ) -> list[SLABreach]:
        """Record an observation and return any breaches triggered."""
        ts = timestamp if timestamp is not None else time.time()
        obs = SLAObservation(
            operation=operation,
            latency_ms=latency_ms,
            success=success,
            timestamp=ts,
        )
        self._observations.setdefault(operation, []).append(obs)

        new_breaches: list[SLABreach] = []
        for target in self._targets.get(operation, []):
            breach = self._check_breach(operation, target, obs)
            if breach is not None:
                self._breaches.append(breach)
                new_breaches.append(breach)
        return new_breaches

    def record_batch(
        self,
        operation: str,
        latencies: list[float],
        timestamp: float | None = None,
    ) -> list[SLABreach]:
        all_breaches: list[SLABreach] = []
        for ms in latencies:
            all_breaches.extend(self.record(operation, latency_ms=ms, timestamp=timestamp))
        return all_breaches

    def breaches(self, operation: str | None = None) -> list[SLABreach]:
        if operation is None:
            return list(self._breaches)
        return [b for b in self._breaches if b.operation == operation]

    def observations(self, operation: str) -> list[SLAObservation]:
        return list(self._observations.get(operation, []))

    def percentile_latency(self, operation: str, pct: float) -> float | None:
        """Compute the *pct*-th percentile latency for *operation*."""
        obs_list = self._observations.get(operation, [])
        if not obs_list:
            return None
        latencies = sorted(o.latency_ms for o in obs_list)
        idx = int(len(latencies) * pct / 100.0)
        idx = min(idx, len(latencies) - 1)
        return latencies[idx]

    def error_rate(self, operation: str) -> float:
        obs_list = self._observations.get(operation, [])
        if not obs_list:
            return 0.0
        failures = sum(1 for o in obs_list if not o.success)
        return failures / len(obs_list)

    def compliance_report(self) -> dict[str, object]:
        """Generate SLA compliance summary across all operations."""
        operations: dict[str, dict[str, object]] = {}
        for op in self._targets:
            obs_list = self._observations.get(op, [])
            op_breaches = [b for b in self._breaches if b.operation == op]
            p50 = self.percentile_latency(op, 50)
            p95 = self.percentile_latency(op, 95)
            p99 = self.percentile_latency(op, 99)
            operations[op] = {
                "total_observations": len(obs_list),
                "breach_count": len(op_breaches),
                "error_rate": self.error_rate(op),
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99,
                "targets": len(self._targets.get(op, [])),
            }

        total_obs = sum(len(v) for v in self._observations.values())
        return {
            "operations": operations,
            "total_observations": total_obs,
            "total_breaches": len(self._breaches),
            "tracked_operations": len(self._targets),
        }

    def _check_breach(
        self, operation: str, target: SLATarget, obs: SLAObservation
    ) -> SLABreach | None:
        if target.metric in (
            SLAMetricType.LATENCY_P50,
            SLAMetricType.LATENCY_P95,
            SLAMetricType.LATENCY_P99,
        ):
            if obs.latency_ms > target.threshold_ms:
                return SLABreach(
                    operation=operation,
                    metric=target.metric,
                    target_value=target.threshold_ms,
                    actual_value=obs.latency_ms,
                    timestamp=obs.timestamp,
                )
        elif target.metric == SLAMetricType.ERROR_RATE_MAX:
            rate = self.error_rate(operation)
            if rate > target.threshold_rate:
                return SLABreach(
                    operation=operation,
                    metric=target.metric,
                    target_value=target.threshold_rate,
                    actual_value=rate,
                    timestamp=obs.timestamp,
                )
        return None
