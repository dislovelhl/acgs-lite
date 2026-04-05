"""
Transaction Coordinator Health Check Module

Constitutional Hash: 608508a9bd224290

Health check endpoints and dashboard query helpers for
TransactionCoordinator observability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.types import (
        CONSTITUTIONAL_HASH,
        JSONDict,
    )
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"  # type: ignore[misc,assignment]
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .transaction_coordinator_metrics import HealthStatus

if TYPE_CHECKING:
    from .transaction_coordinator_metrics import TransactionMetrics

logger = get_logger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    status: HealthStatus
    consistency_ratio: float
    message: str
    details: JSONDict = field(default_factory=dict)


class HealthChecker:
    """
    Health checker for TransactionCoordinator.

    Provides health check endpoints with configurable thresholds.
    """

    def __init__(
        self,
        metrics: TransactionMetrics,
        healthy_threshold: float = 0.999,
        degraded_threshold: float = 0.99,
    ):
        """
        Initialize health checker.

        Args:
            metrics: TransactionMetrics instance
            healthy_threshold: Minimum ratio for HEALTHY status (default 99.9%)
            degraded_threshold: Minimum ratio for DEGRADED status (default 99%)
        """
        self.metrics = metrics
        self.healthy_threshold = healthy_threshold
        self.degraded_threshold = degraded_threshold

    def check_health(self) -> HealthCheckResult:
        """
        Perform a health check.

        Returns:
            HealthCheckResult with status and details
        """
        ratio = self.metrics.get_consistency_ratio()
        latency = self.metrics.get_latency_percentiles()
        concurrent = self.metrics._get_gauge_value(self.metrics.concurrent_transactions)

        # Determine status
        if ratio >= self.healthy_threshold:
            status = HealthStatus.HEALTHY
            message = f"System healthy with {ratio:.2%} consistency ratio"
        elif ratio >= self.degraded_threshold:
            status = HealthStatus.DEGRADED
            message = f"System degraded with {ratio:.2%} consistency ratio"
        else:
            status = HealthStatus.UNHEALTHY
            message = f"System unhealthy with {ratio:.2%} consistency ratio"

        details = {
            "consistency_ratio": ratio,
            "latency_percentiles_ms": latency,
            "concurrent_transactions": concurrent,
            "thresholds": {
                "healthy": self.healthy_threshold,
                "degraded": self.degraded_threshold,
            },
        }

        # Update health gauge
        self.metrics.update_health_gauge()

        return HealthCheckResult(
            status=status,
            consistency_ratio=ratio,
            message=message,
            details=details,
        )

    def is_healthy(self) -> bool:
        """
        Quick health check.

        Returns:
            True if status is HEALTHY
        """
        return self.check_health().status == HealthStatus.HEALTHY

    def to_dict(self) -> JSONDict:
        """
        Convert health check to dictionary.

        Returns:
            Dictionary representation of health status
        """
        result = self.check_health()
        return {
            "status": result.status.value,
            "consistency_ratio": result.consistency_ratio,
            "message": result.message,
            "details": result.details,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


class DashboardQueries:
    """
    PromQL query generators for Grafana/dashboard integration.

    Provides pre-built queries for common transaction metrics visualizations.
    """

    @staticmethod
    def transaction_rate(time_window: str = "5m") -> str:
        """Query for transaction rate."""
        return f'rate(acgs_transactions_total{{status="started"}}[{time_window}])'

    @staticmethod
    def success_rate(time_window: str = "5m") -> str:
        """Query for success rate percentage."""
        return (
            f"rate(acgs_transactions_success_total[{time_window}]) "
            f"/ "
            f'rate(acgs_transactions_total{{status="started"}}[{time_window}])'
        )

    @staticmethod
    def latency_percentile(percentile: float, status: str = "success") -> str:
        """Query for latency percentile."""
        p = percentile / 100
        return (
            f"histogram_quantile({p}, "
            f'sum(rate(acgs_transaction_latency_seconds_bucket{{status="{status}"}}[5m])) '
            f"by (le))"
        )

    @staticmethod
    def p50_latency(status: str = "success") -> str:
        """Query for p50 latency."""
        return DashboardQueries.latency_percentile(50, status)

    @staticmethod
    def p95_latency(status: str = "success") -> str:
        """Query for p95 latency."""
        return DashboardQueries.latency_percentile(95, status)

    @staticmethod
    def p99_latency(status: str = "success") -> str:
        """Query for p99 latency."""
        return DashboardQueries.latency_percentile(99, status)

    @staticmethod
    def compensation_rate(time_window: str = "5m") -> str:
        """Query for compensation execution rate."""
        return f"rate(acgs_compensations_total[{time_window}])"

    @staticmethod
    def checkpoint_save_rate(time_window: str = "5m") -> str:
        """Query for checkpoint save rate."""
        return f"rate(acgs_checkpoint_saves_total[{time_window}])"

    @staticmethod
    def concurrent_transactions() -> str:
        """Query for current concurrent transactions."""
        return "acgs_concurrent_transactions"

    @staticmethod
    def consistency_ratio() -> str:
        """Query for current consistency ratio."""
        return "acgs_consistency_ratio"

    @staticmethod
    def health_status() -> str:
        """Query for health status."""
        return "acgs_transaction_coordinator_health"
