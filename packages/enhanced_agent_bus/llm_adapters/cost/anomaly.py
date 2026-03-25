"""
ACGS-2 Cost Anomaly Detection
Constitutional Hash: 608508a9bd224290

Detects cost anomalies in LLM usage using statistical methods.
"""

from __future__ import annotations

import asyncio
import statistics
from collections.abc import Callable
from datetime import UTC, datetime

from enhanced_agent_bus.llm_adapters.cost.models import CostAnomaly
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
ANOMALY_CALLBACK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class CostAnomalyDetector:
    """
    Detects cost anomalies in LLM usage.

    Constitutional Hash: 608508a9bd224290

    Uses statistical methods to detect:
    - Cost spikes (sudden increases)
    - Unusual patterns (deviation from baseline)
    - Budget warnings (approaching limits)
    """

    def __init__(
        self,
        window_size: int = 100,
        spike_threshold: float = 3.0,  # Standard deviations
        warning_threshold: float = 0.8,  # % of budget
    ) -> None:
        """Initialize anomaly detector."""
        self._window_size = window_size
        self._spike_threshold = spike_threshold
        self._warning_threshold = warning_threshold
        self._cost_history: dict[str, list[tuple[datetime, float]]] = {}
        self._anomalies: list[CostAnomaly] = []
        self._callbacks: list[Callable[[CostAnomaly], None]] = []
        self._lock = asyncio.Lock()
        self._anomaly_counter = 0

    def register_callback(self, callback: Callable[[CostAnomaly], None]) -> None:
        """Register callback for anomaly notifications."""
        self._callbacks.append(callback)

    async def record_cost(
        self,
        tenant_id: str,
        provider_id: str,
        cost: float,
        timestamp: datetime | None = None,
    ) -> CostAnomaly | None:
        """Record a cost and check for anomalies."""
        async with self._lock:
            key = f"{tenant_id}:{provider_id}"
            ts = timestamp or datetime.now(UTC)

            if key not in self._cost_history:
                self._cost_history[key] = []

            history = self._cost_history[key]
            history.append((ts, cost))

            # Keep window size
            if len(history) > self._window_size:
                history.pop(0)

            # Check for anomalies (need at least 10 data points)
            if len(history) >= 10:
                anomaly = self._detect_spike(tenant_id, provider_id, cost, history)
                if anomaly:
                    self._anomalies.append(anomaly)
                    for callback in self._callbacks:
                        try:
                            callback(anomaly)
                        except ANOMALY_CALLBACK_ERRORS as e:
                            logger.error(f"Anomaly callback failed: {e}")
                    return anomaly

            return None

    def _detect_spike(
        self,
        tenant_id: str,
        provider_id: str,
        current_cost: float,
        history: list[tuple[datetime, float]],
    ) -> CostAnomaly | None:
        """Detect cost spike using z-score."""
        costs = [c for _, c in history[:-1]]  # Exclude current

        if len(costs) < 5:
            return None

        mean = statistics.mean(costs)
        if mean == 0:
            return None

        stdev = statistics.stdev(costs) if len(costs) > 1 else 0

        # Avoid division by zero
        if stdev == 0:
            stdev = mean * 0.1  # Use 10% of mean as minimum

        z_score = (current_cost - mean) / stdev
        deviation_pct = ((current_cost - mean) / mean) * 100

        if z_score > self._spike_threshold:
            self._anomaly_counter += 1
            severity = "low"
            if z_score > self._spike_threshold * 2:
                severity = "medium"
            if z_score > self._spike_threshold * 3:
                severity = "high"
            if z_score > self._spike_threshold * 4:
                severity = "critical"

            return CostAnomaly(
                anomaly_id=f"anomaly-{self._anomaly_counter}",
                tenant_id=tenant_id,
                provider_id=provider_id,
                detected_at=datetime.now(UTC),
                anomaly_type="spike",
                severity=severity,
                description=f"Cost spike detected: ${current_cost:.4f} vs expected ${mean:.4f} (z-score: {z_score:.2f})",
                expected_cost=mean,
                actual_cost=current_cost,
                deviation_percentage=deviation_pct,
            )

        return None

    def check_budget_warning(
        self,
        tenant_id: str,
        current_usage: float,
        limit: float,
    ) -> CostAnomaly | None:
        """Check for budget warning."""
        if limit <= 0:
            return None

        usage_ratio = current_usage / limit

        if usage_ratio >= self._warning_threshold:
            self._anomaly_counter += 1
            severity = "low" if usage_ratio < 0.9 else "medium" if usage_ratio < 0.95 else "high"

            return CostAnomaly(
                anomaly_id=f"anomaly-{self._anomaly_counter}",
                tenant_id=tenant_id,
                provider_id="all",
                detected_at=datetime.now(UTC),
                anomaly_type="budget_warning",
                severity=severity,
                description=f"Budget warning: {usage_ratio * 100:.1f}% of limit used (${current_usage:.2f}/${limit:.2f})",
                expected_cost=limit * self._warning_threshold,
                actual_cost=current_usage,
                deviation_percentage=(usage_ratio - self._warning_threshold) * 100,
            )

        return None

    def get_recent_anomalies(
        self,
        tenant_id: str | None = None,
        since: datetime | None = None,
        severity: str | None = None,
    ) -> list[CostAnomaly]:
        """Get recent anomalies with optional filters."""
        results = self._anomalies.copy()

        if tenant_id:
            results = [a for a in results if a.tenant_id == tenant_id]

        if since:
            results = [a for a in results if a.detected_at >= since]

        if severity:
            results = [a for a in results if a.severity == severity]

        return results


__all__ = [
    "CostAnomalyDetector",
]
