"""
ACGS-2 Enhanced Agent Bus - Health Aggregation Service
Constitutional Hash: 608508a9bd224290

Real-time health monitoring and aggregation across all circuit breakers.
Designed to maintain P99 latency < 1.31ms by using fire-and-forget patterns.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        SupportsCircuitBreaker,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    SupportsCircuitBreaker = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import pybreaker

    from enhanced_agent_bus._compat.circuit_breaker import CircuitBreakerRegistry

    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    CircuitBreakerRegistry = None  # type: ignore[misc, assignment]
    pybreaker = None  # type: ignore[misc, assignment]

logger = get_logger(__name__)
_HEALTH_AGGREGATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class SystemHealthStatus(Enum):
    """System health status levels."""

    HEALTHY = "healthy"  # All circuits closed, system operating normally
    DEGRADED = "degraded"  # Some circuits open, reduced capacity
    CRITICAL = "critical"  # Multiple circuits open, service impaired
    UNKNOWN = "unknown"  # Unable to determine health status


@dataclass
class HealthSnapshot:
    """Point-in-time health snapshot."""

    timestamp: datetime
    status: SystemHealthStatus
    health_score: float  # 0.0 - 1.0
    total_breakers: int
    closed_breakers: int
    half_open_breakers: int
    open_breakers: int
    circuit_states: dict[str, str]
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "health_score": round(self.health_score, 3),
            "total_breakers": self.total_breakers,
            "closed_breakers": self.closed_breakers,
            "half_open_breakers": self.half_open_breakers,
            "open_breakers": self.open_breakers,
            "circuit_states": self.circuit_states,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SystemHealthReport:
    """
    Comprehensive system health report.

    Includes current status, health score, and detailed circuit breaker states.
    """

    status: SystemHealthStatus
    health_score: float  # 0.0 - 1.0
    timestamp: datetime
    total_breakers: int
    closed_breakers: int
    half_open_breakers: int
    open_breakers: int
    circuit_details: dict[str, JSONDict]
    degraded_services: list[str] = field(default_factory=list)
    critical_services: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "health_score": round(self.health_score, 3),
            "timestamp": self.timestamp.isoformat(),
            "total_breakers": self.total_breakers,
            "closed_breakers": self.closed_breakers,
            "half_open_breakers": self.half_open_breakers,
            "open_breakers": self.open_breakers,
            "circuit_details": self.circuit_details,
            "degraded_services": self.degraded_services,
            "critical_services": self.critical_services,
            "constitutional_hash": self.constitutional_hash,
        }


class HealthAggregatorConfig:
    """Configuration for health aggregator."""

    def __init__(
        self,
        enabled: bool = True,
        history_window_minutes: int = 5,
        max_history_size: int = 300,  # 5 min at 1 sample/sec
        health_check_interval_seconds: float = 1.0,
        degraded_threshold: float = 0.7,  # <70% circuits closed = degraded
        critical_threshold: float = 0.5,  # <50% circuits closed = critical
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.enabled = enabled
        self.history_window_minutes = history_window_minutes
        self.max_history_size = max_history_size
        self.health_check_interval_seconds = health_check_interval_seconds
        self.degraded_threshold = degraded_threshold
        self.critical_threshold = critical_threshold
        self.constitutional_hash = constitutional_hash


class HealthAggregator:
    """
    Health aggregator for monitoring circuit breakers and system health.

    Uses fire-and-forget pattern to ensure zero impact on P99 latency.
    Collects health snapshots and provides real-time health scoring.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: HealthAggregatorConfig | None = None,
        registry: CircuitBreakerRegistry | None = None,
    ):
        self.config = config or HealthAggregatorConfig()
        self._registry = registry or (
            CircuitBreakerRegistry() if CIRCUIT_BREAKER_AVAILABLE else None
        )
        self._custom_breakers: JSONDict = {}
        self._health_history: deque = deque(maxlen=self.config.max_history_size)
        self._running = False
        self._health_check_task: asyncio.Task | None = None
        self._health_change_callbacks: list[Callable[[SystemHealthReport], None]] = []
        self._last_status: SystemHealthStatus | None = None
        self._snapshots_collected = 0
        self._callbacks_fired = 0
        self._background_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the health aggregator."""
        if not self.config.enabled:
            logger.info("Health aggregator disabled")
            return

        if not CIRCUIT_BREAKER_AVAILABLE:
            logger.warning("Circuit breaker support not available, health aggregator disabled")
            return

        if self._running:
            return

        self._running = True

        # Start background health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info(
            f"HealthAggregator started (constitutional_hash: {self.config.constitutional_hash})"
        )

    async def stop(self) -> None:
        """Stop the health aggregator."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        logger.info(
            f"HealthAggregator stopped - snapshots: {self._snapshots_collected}, "
            f"callbacks fired: {self._callbacks_fired}"
        )

    def register_circuit_breaker(self, name: str, breaker: SupportsCircuitBreaker | object) -> None:
        """
        Register a custom circuit breaker for monitoring.

        Args:
            name: Unique name for the circuit breaker
            breaker: Circuit breaker instance (must have 'current_state' attribute)
        """
        self._custom_breakers[name] = breaker

    def unregister_circuit_breaker(self, name: str) -> None:
        """Unregister a custom circuit breaker."""
        if name in self._custom_breakers:
            del self._custom_breakers[name]
            logger.debug(
                f"[{self.config.constitutional_hash}] Unregistered circuit breaker: {name}"
            )

    def on_health_change(self, callback: Callable[[SystemHealthReport], None]) -> None:
        """
        Register a callback to be invoked when health status changes.

        Args:
            callback: Function to call with SystemHealthReport when status changes

        Example:
            def alert_on_degraded(report: SystemHealthReport):
                if report.status == SystemHealthStatus.DEGRADED:
                    send_alert(f"System degraded: {report.degraded_services}")

            aggregator.on_health_change(alert_on_degraded)
        """
        self._health_change_callbacks.append(callback)
        logger.debug(
            f"[{self.config.constitutional_hash}] Registered health change callback: "
            f"{callback.__name__}"
        )

    def _collect_breaker_state(
        self,
        name: str,
        state: object,
        fail_counter: int,
        success_counter: int,
        circuit_details: dict,
        counts: list[int],
    ) -> None:
        """Record one circuit breaker's state into *circuit_details* and increment *counts*.

        Args:
            name: Breaker name used as the dict key.
            state: Current pybreaker state constant.
            fail_counter: Number of consecutive failures.
            success_counter: Number of consecutive successes.
            circuit_details: Mutable dict to update in-place.
            counts: Mutable list [closed, half_open, open] to increment in-place.
        """
        circuit_details[name] = {
            "state": state,
            "fail_counter": fail_counter,
            "success_counter": success_counter,
        }
        if state == pybreaker.STATE_CLOSED:
            counts[0] += 1
        elif state == pybreaker.STATE_HALF_OPEN:
            counts[1] += 1
        elif state == pybreaker.STATE_OPEN:
            counts[2] += 1

    def get_system_health(self) -> SystemHealthReport:
        """
        Get current system health report.

        Returns:
            SystemHealthReport with current health status and details
        """
        if not CIRCUIT_BREAKER_AVAILABLE:
            return SystemHealthReport(
                status=SystemHealthStatus.UNKNOWN,
                health_score=0.0,
                timestamp=datetime.now(UTC),
                total_breakers=0,
                closed_breakers=0,
                half_open_breakers=0,
                open_breakers=0,
                circuit_details={},
                constitutional_hash=self.config.constitutional_hash,
            )

        # Collect circuit breaker states — counts: [closed, half_open, open]
        circuit_details: dict = {}
        counts = [0, 0, 0]

        # Get states from registry
        if self._registry:
            registry_states = self._registry.get_all_states()
            for name, state_info in registry_states.items():
                self._collect_breaker_state(
                    name,
                    state_info["state"],
                    state_info.get("fail_counter", 0),
                    state_info.get("success_counter", 0),
                    circuit_details,
                    counts,
                )

        # Get states from custom breakers
        for name, breaker in self._custom_breakers.items():
            if hasattr(breaker, "current_state"):
                self._collect_breaker_state(
                    name,
                    breaker.current_state,
                    getattr(breaker, "fail_counter", 0),
                    getattr(breaker, "success_counter", 0),
                    circuit_details,
                    counts,
                )

        closed_count, half_open_count, open_count = counts
        total_breakers = len(circuit_details)

        # Calculate health score
        health_score = self._calculate_health_score(
            total_breakers, closed_count, half_open_count, open_count
        )

        # Determine overall status
        status = self._determine_health_status(health_score)

        # Identify degraded and critical services
        degraded_services = [
            name
            for name, info in circuit_details.items()
            if info["state"] == pybreaker.STATE_HALF_OPEN
        ]
        critical_services = [
            name for name, info in circuit_details.items() if info["state"] == pybreaker.STATE_OPEN
        ]

        return SystemHealthReport(
            status=status,
            health_score=health_score,
            timestamp=datetime.now(UTC),
            total_breakers=total_breakers,
            closed_breakers=closed_count,
            half_open_breakers=half_open_count,
            open_breakers=open_count,
            circuit_details=circuit_details,
            degraded_services=degraded_services,
            critical_services=critical_services,
            constitutional_hash=self.config.constitutional_hash,
        )

    def get_health_history(self, window_minutes: int | None = None) -> list[HealthSnapshot]:
        """
        Get health history snapshots.

        Args:
            window_minutes: Number of minutes of history to return (default: configured window)

        Returns:
            List of HealthSnapshot objects in chronological order
        """
        if window_minutes is None:
            window_minutes = self.config.history_window_minutes

        cutoff_time = datetime.now(UTC).timestamp() - (window_minutes * 60)

        # Filter snapshots within window
        filtered_snapshots = [
            snapshot
            for snapshot in self._health_history
            if snapshot.timestamp.timestamp() >= cutoff_time
        ]

        return list(filtered_snapshots)

    def get_metrics(self) -> JSONDict:
        """Get aggregator metrics."""
        current_health = self.get_system_health()
        return {
            "snapshots_collected": self._snapshots_collected,
            "callbacks_fired": self._callbacks_fired,
            "history_size": len(self._health_history),
            "running": self._running,
            "enabled": self.config.enabled,
            "current_status": current_health.status.value,
            "current_health_score": current_health.health_score,
            "total_breakers": current_health.total_breakers,
            "constitutional_hash": self.config.constitutional_hash,
        }

    async def _health_check_loop(self) -> None:
        """Background loop to collect health snapshots."""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval_seconds)
                await self._collect_health_snapshot()
            except asyncio.CancelledError:
                break
            except _HEALTH_AGGREGATOR_OPERATION_ERRORS as e:
                logger.error(f"Health check error: {e}")

    async def _collect_health_snapshot(self) -> None:
        """Collect a health snapshot and fire callbacks if status changed."""
        if not CIRCUIT_BREAKER_AVAILABLE:
            return

        # Get current health
        health_report = self.get_system_health()

        # Create snapshot
        snapshot = HealthSnapshot(
            timestamp=health_report.timestamp,
            status=health_report.status,
            health_score=health_report.health_score,
            total_breakers=health_report.total_breakers,
            closed_breakers=health_report.closed_breakers,
            half_open_breakers=health_report.half_open_breakers,
            open_breakers=health_report.open_breakers,
            circuit_states={
                name: info["state"] for name, info in health_report.circuit_details.items()
            },
            constitutional_hash=self.config.constitutional_hash,
        )

        # Add to history
        self._health_history.append(snapshot)
        self._snapshots_collected += 1

        # Fire callbacks if status changed (fire-and-forget)
        if self._last_status != health_report.status:
            logger.info(
                f"[{self.config.constitutional_hash}] Health status changed: "
                f"{self._last_status.value if self._last_status else 'unknown'} -> "
                f"{health_report.status.value}"
            )
            self._last_status = health_report.status

            # Fire callbacks without blocking
            for callback in self._health_change_callbacks:
                try:
                    # Fire-and-forget: don't wait for callback completion
                    task = asyncio.create_task(self._invoke_callback(callback, health_report))
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
                    self._callbacks_fired += 1
                except _HEALTH_AGGREGATOR_OPERATION_ERRORS as e:
                    logger.error(f"Failed to fire health change callback {callback.__name__}: {e}")

    async def _invoke_callback(
        self, callback: Callable[[SystemHealthReport], object], report: SystemHealthReport
    ) -> None:
        """Invoke a callback (handles both sync and async callbacks)."""
        try:
            result = callback(report)
            if asyncio.iscoroutine(result):
                await result
        except _HEALTH_AGGREGATOR_OPERATION_ERRORS as e:
            logger.error(f"Health change callback error: {e}")

    def _calculate_health_score(
        self,
        total: int,
        closed: int,
        half_open: int,
        open: int,
    ) -> float:
        """
        Calculate health score (0.0 - 1.0).

        Score calculation:
        - Closed circuits: 1.0 weight
        - Half-open circuits: 0.5 weight (recovering)
        - Open circuits: 0.0 weight (failed)
        """
        if total == 0:
            return 1.0  # No breakers = healthy

        weighted_score = (closed * 1.0) + (half_open * 0.5) + (open * 0.0)
        return weighted_score / total

    def _determine_health_status(self, health_score: float) -> SystemHealthStatus:
        """
        Determine health status from health score.

        Thresholds:
        - >= degraded_threshold (default 0.7): HEALTHY
        - >= critical_threshold (default 0.5): DEGRADED
        - < critical_threshold: CRITICAL
        """
        if health_score >= self.config.degraded_threshold:
            return SystemHealthStatus.HEALTHY
        elif health_score >= self.config.critical_threshold:
            return SystemHealthStatus.DEGRADED
        else:
            return SystemHealthStatus.CRITICAL


# Global health aggregator instance (lazy initialized)
_health_aggregator: HealthAggregator | None = None


def get_health_aggregator(
    config: HealthAggregatorConfig | None = None,
) -> HealthAggregator:
    """Get or create the global health aggregator singleton."""
    global _health_aggregator
    if _health_aggregator is None:
        _health_aggregator = HealthAggregator(config or HealthAggregatorConfig())
    return _health_aggregator


def reset_health_aggregator() -> None:
    """Reset health aggregator singleton (for testing)."""
    global _health_aggregator
    _health_aggregator = None


__all__ = [
    "CIRCUIT_BREAKER_AVAILABLE",
    "CONSTITUTIONAL_HASH",
    "HealthAggregator",
    "HealthAggregatorConfig",
    "HealthSnapshot",
    "SystemHealthReport",
    "SystemHealthStatus",
    "get_health_aggregator",
    "reset_health_aggregator",
]
