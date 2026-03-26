"""
ACGS-2 LLM Failover - Health Scoring Module
Constitutional Hash: 608508a9bd224290

Provider health scoring based on latency, errors, quality, and availability.
"""

from __future__ import annotations

import asyncio
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.circuit_breaker import CONSTITUTIONAL_HASH


@dataclass
class HealthMetrics:
    """Metrics for provider health scoring."""

    # Latency metrics (in milliseconds)
    latency_samples: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Error metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_count: int = 0
    rate_limit_count: int = 0
    error_rate: float = 0.0

    # Quality metrics (0.0 - 1.0)
    response_quality_scores: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    avg_quality_score: float = 1.0

    # Availability
    last_success_time: datetime | None = None
    last_failure_time: datetime | None = None
    consecutive_failures: int = 0
    uptime_percentage: float = 100.0

    # Overall health score (0.0 - 1.0)
    health_score: float = 1.0

    # Constitutional hash
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ProviderHealthScore:
    """
    Health score for an LLM provider.

    Constitutional Hash: 608508a9bd224290
    """

    provider_id: str
    health_score: float  # 0.0 - 1.0
    latency_score: float  # Based on latency percentiles
    error_score: float  # Based on error rate
    quality_score: float  # Based on response quality
    availability_score: float  # Based on uptime

    is_healthy: bool
    is_degraded: bool
    is_unhealthy: bool

    metrics: HealthMetrics
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "provider_id": self.provider_id,
            "health_score": round(self.health_score, 3),
            "latency_score": round(self.latency_score, 3),
            "error_score": round(self.error_score, 3),
            "quality_score": round(self.quality_score, 3),
            "availability_score": round(self.availability_score, 3),
            "is_healthy": self.is_healthy,
            "is_degraded": self.is_degraded,
            "is_unhealthy": self.is_unhealthy,
            "metrics": {
                "avg_latency_ms": round(self.metrics.avg_latency_ms, 2),
                "p95_latency_ms": round(self.metrics.p95_latency_ms, 2),
                "error_rate": round(self.metrics.error_rate, 4),
                "total_requests": self.metrics.total_requests,
                "consecutive_failures": self.metrics.consecutive_failures,
            },
            "last_updated": self.last_updated.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


class ProviderHealthScorer:
    """
    Scores provider health based on multiple factors.

    Constitutional Hash: 608508a9bd224290

    Health score components:
    - Latency (30%): Based on P95 latency vs expected
    - Errors (35%): Based on error rate
    - Quality (15%): Based on response quality feedback
    - Availability (20%): Based on uptime and consecutive failures
    """

    # Weight factors for health score components
    LATENCY_WEIGHT = 0.30
    ERROR_WEIGHT = 0.35
    QUALITY_WEIGHT = 0.15
    AVAILABILITY_WEIGHT = 0.20

    # Thresholds
    HEALTHY_THRESHOLD = 0.8
    DEGRADED_THRESHOLD = 0.5

    def __init__(self) -> None:
        """Initialize health scorer."""
        self._metrics: dict[str, HealthMetrics] = {}
        self._expected_latency: dict[str, float] = {}  # provider -> expected P95 ms
        self._lock = asyncio.Lock()

    def set_expected_latency(self, provider_id: str, latency_ms: float) -> None:
        """Set expected P95 latency for a provider."""
        self._expected_latency[provider_id] = latency_ms

    async def record_request(
        self,
        provider_id: str,
        latency_ms: float,
        success: bool,
        error_type: str | None = None,
        quality_score: float | None = None,
    ) -> None:
        """Record a request result for health scoring."""
        async with self._lock:
            if provider_id not in self._metrics:
                self._metrics[provider_id] = HealthMetrics()

            metrics = self._metrics[provider_id]

            # Update request counts
            metrics.total_requests += 1
            if success:
                metrics.successful_requests += 1
                metrics.last_success_time = datetime.now(UTC)
                metrics.consecutive_failures = 0
            else:
                metrics.failed_requests += 1
                metrics.last_failure_time = datetime.now(UTC)
                metrics.consecutive_failures += 1

                if error_type == "timeout":
                    metrics.timeout_count += 1
                elif error_type == "rate_limit":
                    metrics.rate_limit_count += 1

            # Update latency
            metrics.latency_samples.append(latency_ms)
            self._update_latency_stats(metrics)

            # Update error rate
            metrics.error_rate = (
                metrics.failed_requests / metrics.total_requests
                if metrics.total_requests > 0
                else 0.0
            )

            # Update quality score
            if quality_score is not None:
                metrics.response_quality_scores.append(quality_score)
                metrics.avg_quality_score = (
                    statistics.mean(metrics.response_quality_scores)
                    if metrics.response_quality_scores
                    else 1.0
                )

            # Update uptime
            self._update_uptime(metrics)

            # Recalculate health score
            metrics.health_score = self._calculate_health_score(provider_id, metrics)

    def _update_latency_stats(self, metrics: HealthMetrics) -> None:
        """Update latency statistics."""
        if not metrics.latency_samples:
            return

        samples = list(metrics.latency_samples)
        metrics.avg_latency_ms = statistics.mean(samples)
        metrics.p50_latency_ms = statistics.median(samples)

        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        metrics.p95_latency_ms = sorted_samples[int(n * 0.95)] if n > 0 else 0
        metrics.p99_latency_ms = sorted_samples[int(n * 0.99)] if n > 0 else 0

    def _update_uptime(self, metrics: HealthMetrics) -> None:
        """Update uptime percentage."""
        if metrics.total_requests == 0:
            metrics.uptime_percentage = 100.0
        else:
            metrics.uptime_percentage = (metrics.successful_requests / metrics.total_requests) * 100

    def _calculate_health_score(self, provider_id: str, metrics: HealthMetrics) -> float:
        """Calculate overall health score."""
        # Latency score
        expected_latency = self._expected_latency.get(provider_id, 500.0)  # Default 500ms
        latency_score = max(0, 1 - (metrics.p95_latency_ms / (expected_latency * 2)))

        # Error score
        error_score = max(0, 1 - (metrics.error_rate * 5))  # 20% error rate = 0 score

        # Quality score
        quality_score = metrics.avg_quality_score

        # Availability score
        availability_score = metrics.uptime_percentage / 100
        # Penalize consecutive failures
        if metrics.consecutive_failures > 0:
            penalty = min(0.5, metrics.consecutive_failures * 0.1)
            availability_score = max(0, availability_score - penalty)

        # Weighted combination
        health_score = (
            self.LATENCY_WEIGHT * latency_score
            + self.ERROR_WEIGHT * error_score
            + self.QUALITY_WEIGHT * quality_score
            + self.AVAILABILITY_WEIGHT * availability_score
        )

        return max(0.0, min(1.0, health_score))

    def get_health_score(self, provider_id: str) -> ProviderHealthScore:
        """Get current health score for a provider."""
        metrics = self._metrics.get(provider_id, HealthMetrics())

        # Calculate component scores
        expected_latency = self._expected_latency.get(provider_id, 500.0)
        latency_score = max(0, 1 - (metrics.p95_latency_ms / (expected_latency * 2)))
        error_score = max(0, 1 - (metrics.error_rate * 5))
        quality_score = metrics.avg_quality_score
        availability_score = metrics.uptime_percentage / 100

        health_score = metrics.health_score

        return ProviderHealthScore(
            provider_id=provider_id,
            health_score=health_score,
            latency_score=latency_score,
            error_score=error_score,
            quality_score=quality_score,
            availability_score=availability_score,
            is_healthy=health_score >= self.HEALTHY_THRESHOLD,
            is_degraded=self.DEGRADED_THRESHOLD <= health_score < self.HEALTHY_THRESHOLD,
            is_unhealthy=health_score < self.DEGRADED_THRESHOLD,
            metrics=metrics,
        )

    def get_all_scores(self) -> dict[str, ProviderHealthScore]:
        """Get health scores for all tracked providers."""
        return {provider_id: self.get_health_score(provider_id) for provider_id in self._metrics}

    def reset(self, provider_id: str | None = None) -> None:
        """Reset health metrics."""
        if provider_id:
            if provider_id in self._metrics:
                self._metrics[provider_id] = HealthMetrics()
        else:
            self._metrics.clear()


__all__ = [
    "HealthMetrics",
    "ProviderHealthScore",
    "ProviderHealthScorer",
]
