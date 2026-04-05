"""
ACGS-2 Enhanced Agent Bus - Governance Quality Metrics Collector
Constitutional Hash: 608508a9bd224290

Service to collect and analyze governance quality metrics (violations, latency,
throughput) for constitutional amendment monitoring and automated rollback.
"""

import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timezone

from pydantic import BaseModel, Field

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

try:
    from acgs2_perf import compute_percentiles_floor_index

    PERF_KERNELS_AVAILABLE = True
except ImportError:
    PERF_KERNELS_AVAILABLE = False

try:
    from enhanced_agent_bus._compat.config import settings
except ImportError:
    # Fallback settings for standalone usage
    class _FallbackSettings:
        class redis:
            url = "redis://localhost:6379"

    settings = _FallbackSettings()  # type: ignore[assignment]

logger = get_logger(__name__)

_module = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.constitutional.metrics_collector", _module)
sys.modules.setdefault("packages.enhanced_agent_bus.constitutional.metrics_collector", _module)


class GovernanceMetricsSnapshot(BaseModel):
    """Snapshot of governance quality metrics at a point in time.

    Constitutional Hash: 608508a9bd224290

    Attributes:
        timestamp: When this snapshot was captured
        constitutional_hash: Hash of the constitutional version being measured
        constitutional_version: Semantic version of the constitution
        violations_rate: Rate of constitutional violations (0.0-1.0, target: 0.0)
        governance_latency_p50: 50th percentile governance decision latency (ms)
        governance_latency_p95: 95th percentile governance decision latency (ms)
        governance_latency_p99: 99th percentile governance decision latency (ms, target: <5ms)
        deliberation_success_rate: Success rate of deliberation layer (0.0-1.0, target: >0.95)
        maci_violations_count: Count of MACI enforcement violations
        throughput_rps: Requests per second throughput
        total_requests: Total governance requests in measurement window
        approved_requests: Number of approved requests
        denied_requests: Number of denied requests
        escalated_requests: Number of escalated to HITL requests
        error_rate: Rate of governance errors (0.0-1.0)
        window_duration_seconds: Duration of measurement window in seconds
    """

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    constitutional_version: str | None = Field(None, pattern=r"^\d+\.\d+\.\d+$")

    # Core governance quality metrics
    violations_rate: float = Field(
        0.0, ge=0.0, le=1.0, description="Constitutional violations rate (target: 0.0)"
    )
    governance_latency_p50: float = Field(0.0, ge=0.0, description="P50 latency in milliseconds")
    governance_latency_p95: float = Field(0.0, ge=0.0, description="P95 latency in milliseconds")
    governance_latency_p99: float = Field(
        0.0, ge=0.0, description="P99 latency in milliseconds (target: <5ms)"
    )
    deliberation_success_rate: float = Field(
        0.0, ge=0.0, le=1.0, description="Deliberation success rate (target: >0.95)"
    )
    maci_violations_count: int = Field(0, ge=0, description="MACI enforcement violations")

    # Throughput metrics
    throughput_rps: float = Field(0.0, ge=0.0, description="Requests per second")
    total_requests: int = Field(0, ge=0)
    approved_requests: int = Field(0, ge=0)
    denied_requests: int = Field(0, ge=0)
    escalated_requests: int = Field(0, ge=0)

    # Error tracking
    error_rate: float = Field(0.0, ge=0.0, le=1.0, description="Governance error rate")

    # Measurement window
    window_duration_seconds: int = Field(60, ge=1, description="Measurement window duration")

    @property
    def meets_targets(self) -> bool:
        """Check if all metrics meet their targets."""
        return (
            self.violations_rate == 0.0
            and self.governance_latency_p99 < 5.0
            and self.deliberation_success_rate > 0.95
            and self.maci_violations_count == 0
        )

    @property
    def health_score(self) -> float:
        """Compute overall health score (0.0-1.0) based on metrics.

        Returns:
            Health score where 1.0 is perfect health
        """
        # Violations penalty (max 0.3 penalty)
        violations_penalty = min(0.3, self.violations_rate * 0.3)

        # Latency penalty (max 0.3 penalty) - exponential penalty after 5ms
        latency_penalty = 0.0
        if self.governance_latency_p99 > 5.0:
            latency_penalty = min(0.3, (self.governance_latency_p99 - 5.0) / 50.0 * 0.3)

        # Deliberation penalty (max 0.2 penalty)
        deliberation_penalty = 0.0
        if self.deliberation_success_rate < 0.95:
            deliberation_penalty = min(0.2, (0.95 - self.deliberation_success_rate) * 0.2)

        # MACI violations penalty (max 0.1 penalty)
        maci_penalty = min(0.1, self.maci_violations_count * 0.01)

        # Error rate penalty (max 0.1 penalty)
        error_penalty = min(0.1, self.error_rate * 0.1)

        # Compute final score
        health_score = 1.0 - (
            violations_penalty
            + latency_penalty
            + deliberation_penalty
            + maci_penalty
            + error_penalty
        )

        return max(0.0, health_score)


class MetricsComparison(BaseModel):
    """Comparison between two governance metrics snapshots.

    Constitutional Hash: 608508a9bd224290

    Used to compare baseline metrics (before amendment) with current metrics
    (after amendment) to detect degradation.
    """

    baseline: GovernanceMetricsSnapshot
    current: GovernanceMetricsSnapshot

    # Delta calculations (current - baseline)
    violations_rate_delta: float = 0.0
    latency_p99_delta: float = 0.0
    deliberation_success_rate_delta: float = 0.0
    maci_violations_delta: int = 0
    throughput_delta: float = 0.0
    error_rate_delta: float = 0.0
    health_score_delta: float = 0.0

    # Degradation flags
    has_degradation: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)

    def __init__(self, **data):
        """Initialize comparison and compute deltas."""
        super().__init__(**data)
        self._compute_deltas()
        self._check_degradation()

    def _compute_deltas(self) -> None:
        """Compute metric deltas between baseline and current."""
        self.violations_rate_delta = self.current.violations_rate - self.baseline.violations_rate
        self.latency_p99_delta = (
            self.current.governance_latency_p99 - self.baseline.governance_latency_p99
        )
        self.deliberation_success_rate_delta = (
            self.current.deliberation_success_rate - self.baseline.deliberation_success_rate
        )
        self.maci_violations_delta = (
            self.current.maci_violations_count - self.baseline.maci_violations_count
        )
        self.throughput_delta = self.current.throughput_rps - self.baseline.throughput_rps
        self.error_rate_delta = self.current.error_rate - self.baseline.error_rate
        self.health_score_delta = self.current.health_score - self.baseline.health_score

    def _check_degradation(self) -> None:
        """Check for degradation and populate reasons."""
        reasons = []

        # Check violations rate increase
        if self.violations_rate_delta > 0.01:  # More than 1% increase
            reasons.append(
                f"Constitutional violations increased by {self.violations_rate_delta:.2%} "
                f"({self.baseline.violations_rate:.2%} -> {self.current.violations_rate:.2%})"
            )

        # Check latency degradation (>20% increase or above 5ms target)
        if self.latency_p99_delta > max(1.0, self.baseline.governance_latency_p99 * 0.2):
            reasons.append(
                f"P99 latency increased by {self.latency_p99_delta:.2f}ms "
                f"({self.baseline.governance_latency_p99:.2f}ms -> {self.current.governance_latency_p99:.2f}ms)"
            )

        # Check deliberation success rate decrease
        if self.deliberation_success_rate_delta < -0.05:  # More than 5% decrease
            reasons.append(
                f"Deliberation success rate decreased by {abs(self.deliberation_success_rate_delta):.2%} "
                f"({self.baseline.deliberation_success_rate:.2%} -> {self.current.deliberation_success_rate:.2%})"
            )

        # Check MACI violations increase
        if self.maci_violations_delta > 0:
            reasons.append(
                f"MACI violations increased by {self.maci_violations_delta} "
                f"({self.baseline.maci_violations_count} -> {self.current.maci_violations_count})"
            )

        # Check error rate increase
        if self.error_rate_delta > 0.05:  # More than 5% increase
            reasons.append(
                f"Error rate increased by {self.error_rate_delta:.2%} "
                f"({self.baseline.error_rate:.2%} -> {self.current.error_rate:.2%})"
            )

        # Check overall health score decrease
        if self.health_score_delta < -0.1:  # More than 10% decrease
            reasons.append(
                f"Overall health score decreased by {abs(self.health_score_delta):.2%} "
                f"({self.baseline.health_score:.2%} -> {self.current.health_score:.2%})"
            )

        self.degradation_reasons = reasons
        self.has_degradation = len(reasons) > 0


class GovernanceMetricsCollector:
    """Service to collect and analyze governance quality metrics.

    Constitutional Hash: 608508a9bd224290

    This service collects real-time governance metrics from Redis and provides
    analysis capabilities for amendment monitoring and automated rollback decisions.

    Metrics are stored in Redis with time-series data structures:
    - governance:metrics:latencies - sorted set of latency measurements
    - governance:metrics:requests - hash of request counters
    - governance:metrics:violations - sorted set of violation events
    - governance:metrics:maci_violations - sorted set of MACI violation events
    - governance:metrics:deliberations - hash of deliberation counters
    - governance:metrics:snapshots:{timestamp} - historical snapshots

    Args:
        redis_url: Redis connection URL (default from settings)
        snapshot_retention_hours: How long to retain snapshots (default: 168 hours = 7 days)
        measurement_window_seconds: Default measurement window (default: 60 seconds)
    """

    def __init__(
        self,
        redis_url: str | None = None,
        snapshot_retention_hours: int = 168,  # 7 days
        measurement_window_seconds: int = 60,
    ):
        """Initialize the metrics collector."""
        self.redis_url = redis_url or settings.redis.url
        self.snapshot_retention_hours = snapshot_retention_hours
        self.measurement_window_seconds = measurement_window_seconds
        self.redis_client: object | None = None

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Initialized GovernanceMetricsCollector with "
            f"window={measurement_window_seconds}s, retention={snapshot_retention_hours}h"
        )

    async def connect(self) -> None:
        """Connect to Redis for metrics storage."""
        if not REDIS_AVAILABLE:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Redis not available, metrics collection disabled"
            )
            return

        try:
            self.redis_client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info(f"[{CONSTITUTIONAL_HASH}] Connected to Redis for metrics collection")
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Failed to connect to Redis: {e}")
            self.redis_client = None

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis_client:
            try:
                await self.redis_client.close()
                logger.info(f"[{CONSTITUTIONAL_HASH}] Disconnected from Redis")
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Error disconnecting from Redis: {e}")

    async def record_governance_decision(
        self,
        latency_ms: float,
        approved: bool,
        escalated: bool = False,
        constitutional_violation: bool = False,
    ) -> None:
        """Record a governance decision for metrics tracking.

        Args:
            latency_ms: Decision latency in milliseconds
            approved: Whether the decision was approved
            escalated: Whether the decision was escalated to HITL
            constitutional_violation: Whether a constitutional violation was detected
        """
        if not self.redis_client:
            return

        try:
            timestamp = datetime.now(UTC).timestamp()

            # Record latency in sorted set (score = timestamp)
            await self.redis_client.zadd(
                "governance:metrics:latencies", {str(latency_ms): timestamp}
            )

            # Increment request counters
            await self.redis_client.hincrby("governance:metrics:requests", "total", 1)
            if approved:
                await self.redis_client.hincrby("governance:metrics:requests", "approved", 1)
            else:
                await self.redis_client.hincrby("governance:metrics:requests", "denied", 1)
            if escalated:
                await self.redis_client.hincrby("governance:metrics:requests", "escalated", 1)

            # Record violation if present
            if constitutional_violation:
                await self.redis_client.zadd(
                    "governance:metrics:violations", {f"violation_{timestamp}": timestamp}
                )

            # Cleanup old data (keep last hour for latencies)
            cutoff = timestamp - 3600
            await self.redis_client.zremrangebyscore("governance:metrics:latencies", "-inf", cutoff)
            await self.redis_client.zremrangebyscore(
                "governance:metrics:violations", "-inf", cutoff
            )

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error recording governance decision: {e}")

    async def record_maci_violation(self, agent_id: str, action: str, role: str) -> None:
        """Record a MACI enforcement violation.

        Args:
            agent_id: ID of the agent that violated MACI
            action: Action that was attempted
            role: Expected role for the action
        """
        if not self.redis_client:
            return

        try:
            timestamp = datetime.now(UTC).timestamp()
            violation_data = json.dumps(
                {
                    "agent_id": agent_id,
                    "action": action,
                    "role": role,
                    "timestamp": timestamp,
                }
            )

            await self.redis_client.zadd(
                "governance:metrics:maci_violations", {violation_data: timestamp}
            )

            # Cleanup old MACI violations (keep last 24 hours)
            cutoff = timestamp - 86400
            await self.redis_client.zremrangebyscore(
                "governance:metrics:maci_violations", "-inf", cutoff
            )

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error recording MACI violation: {e}")

    async def record_deliberation_outcome(self, success: bool) -> None:
        """Record a deliberation layer outcome.

        Args:
            success: Whether the deliberation completed successfully
        """
        if not self.redis_client:
            return

        try:
            await self.redis_client.hincrby("governance:metrics:deliberations", "total", 1)
            if success:
                await self.redis_client.hincrby("governance:metrics:deliberations", "success", 1)
            else:
                await self.redis_client.hincrby("governance:metrics:deliberations", "failed", 1)

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error recording deliberation outcome: {e}")

    async def collect_snapshot(
        self,
        constitutional_version: str | None = None,
        window_seconds: int | None = None,
    ) -> GovernanceMetricsSnapshot:
        """Collect a snapshot of current governance metrics.

        Args:
            constitutional_version: Version of constitution being measured
            window_seconds: Measurement window (default: self.measurement_window_seconds)

        Returns:
            GovernanceMetricsSnapshot with current metrics
        """
        window = window_seconds or self.measurement_window_seconds
        timestamp = datetime.now(UTC)

        if not self.redis_client:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Redis not available, returning empty snapshot")
            return GovernanceMetricsSnapshot(
                timestamp=timestamp,
                constitutional_version=constitutional_version,
                window_duration_seconds=window,
                violations_rate=0.0,
                governance_latency_p50=0.0,
                governance_latency_p95=0.0,
                governance_latency_p99=0.0,
                deliberation_success_rate=0.0,
                maci_violations_count=0,
                throughput_rps=0.0,
                total_requests=0,
                approved_requests=0,
                denied_requests=0,
                escalated_requests=0,
                error_rate=0.0,
            )

        try:
            # Get time window bounds
            now = timestamp.timestamp()
            window_start = now - window

            # Collect latency data
            latencies = await self._get_latencies(window_start, now)
            p50, p95, p99 = self._compute_percentiles(latencies)

            # Collect request counters
            requests = await self._get_request_counters()

            # Collect violations
            violations_count = await self._get_violations_count(window_start, now)
            violations_rate = violations_count / max(1, requests["total"])

            # Collect MACI violations
            maci_violations = await self._get_maci_violations_count(window_start, now)

            # Collect deliberation metrics
            deliberation = await self._get_deliberation_metrics()

            # Compute throughput
            throughput = requests["total"] / window if window > 0 else 0.0

            # Compute error rate (simple heuristic)
            error_rate = 0.0
            if requests["total"] > 0:
                # Errors are approximated as high latency decisions (>100ms) or violations
                high_latency_count = sum(1 for lat in latencies if lat > 100.0)
                error_rate = (high_latency_count + violations_count) / requests["total"]

            snapshot = GovernanceMetricsSnapshot(
                timestamp=timestamp,
                constitutional_version=constitutional_version,
                violations_rate=violations_rate,
                governance_latency_p50=p50,
                governance_latency_p95=p95,
                governance_latency_p99=p99,
                deliberation_success_rate=deliberation["success_rate"],
                maci_violations_count=maci_violations,
                throughput_rps=throughput,
                total_requests=requests["total"],
                approved_requests=requests["approved"],
                denied_requests=requests["denied"],
                escalated_requests=requests["escalated"],
                error_rate=error_rate,
                window_duration_seconds=window,
            )

            # Store snapshot
            await self._store_snapshot(snapshot)

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Collected metrics snapshot: "
                f"violations={violations_rate:.2%}, p99={p99:.2f}ms, "
                f"deliberation={deliberation['success_rate']:.2%}, health={snapshot.health_score:.2%}"
            )

            return snapshot

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error collecting snapshot: {e}")
            return GovernanceMetricsSnapshot(
                timestamp=timestamp,
                constitutional_version=constitutional_version,
                window_duration_seconds=window,
                violations_rate=0.0,
                governance_latency_p50=0.0,
                governance_latency_p95=0.0,
                governance_latency_p99=0.0,
                deliberation_success_rate=0.0,
                maci_violations_count=0,
                throughput_rps=0.0,
                total_requests=0,
                approved_requests=0,
                denied_requests=0,
                escalated_requests=0,
                error_rate=0.0,
            )

    async def compare_snapshots(
        self,
        baseline: GovernanceMetricsSnapshot,
        current: GovernanceMetricsSnapshot | None = None,
    ) -> MetricsComparison:
        """Compare two metrics snapshots to detect degradation.

        Args:
            baseline: Baseline snapshot (e.g., before amendment)
            current: Current snapshot (if None, collects new snapshot)

        Returns:
            MetricsComparison with delta analysis
        """
        if current is None:
            current = await self.collect_snapshot(
                constitutional_version=baseline.constitutional_version
            )

        comparison = MetricsComparison(baseline=baseline, current=current)

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Metrics comparison: "
            f"degradation={comparison.has_degradation}, "
            f"health_delta={comparison.health_score_delta:+.2%}, "
            f"reasons={len(comparison.degradation_reasons)}"
        )

        return comparison

    async def get_baseline_snapshot(
        self,
        constitutional_version: str,
    ) -> GovernanceMetricsSnapshot | None:
        """Get the baseline snapshot for a constitutional version.

        Args:
            constitutional_version: Version to get baseline for

        Returns:
            Baseline snapshot if found, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            key = f"governance:metrics:baseline:{constitutional_version}"
            data = await self.redis_client.get(key)
            if data:
                return GovernanceMetricsSnapshot.model_validate_json(data)  # type: ignore[no-any-return]
            return None
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error getting baseline snapshot: {e}")
            return None

    async def store_baseline_snapshot(
        self,
        snapshot: GovernanceMetricsSnapshot,
        constitutional_version: str,
    ) -> None:
        """Store a baseline snapshot for a constitutional version.

        Args:
            snapshot: Snapshot to store as baseline
            constitutional_version: Version this is the baseline for
        """
        if not self.redis_client:
            return

        try:
            key = f"governance:metrics:baseline:{constitutional_version}"
            await self.redis_client.set(
                key,
                snapshot.model_dump_json(),
                ex=86400
                * self.snapshot_retention_hours
                // 24,  # Retain for same period as snapshots
            )
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Stored baseline snapshot for version {constitutional_version}"
            )
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error storing baseline snapshot: {e}")

    async def _get_latencies(self, start: float, end: float) -> list[float]:
        """Get latency measurements within time window."""
        try:
            # Get latencies in time range
            latency_strs = await self.redis_client.zrangebyscore(
                "governance:metrics:latencies",
                start,
                end,
            )
            return [float(lat) for lat in latency_strs if lat]
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error getting latencies: {e}")
            return []

    async def _get_request_counters(self) -> dict[str, int]:
        """Get request counters."""
        try:
            counters_raw = await self.redis_client.hgetall("governance:metrics:requests")
            counters = counters_raw if isinstance(counters_raw, Mapping) else {}
            return {
                "total": int(counters.get("total", 0)),
                "approved": int(counters.get("approved", 0)),
                "denied": int(counters.get("denied", 0)),
                "escalated": int(counters.get("escalated", 0)),
            }
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error getting request counters: {e}")
            return {"total": 0, "approved": 0, "denied": 0, "escalated": 0}

    async def _get_violations_count(self, start: float, end: float) -> int:
        """Get count of violations in time window."""
        try:
            count = await self.redis_client.zcount(
                "governance:metrics:violations",
                start,
                end,
            )
            return count or 0
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error getting violations count: {e}")
            return 0

    async def _get_maci_violations_count(self, start: float, end: float) -> int:
        """Get count of MACI violations in time window."""
        try:
            count = await self.redis_client.zcount(
                "governance:metrics:maci_violations",
                start,
                end,
            )
            return count or 0
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error getting MACI violations count: {e}")
            return 0

    async def _get_deliberation_metrics(self) -> JSONDict:
        """Get deliberation metrics."""
        try:
            counters_raw = await self.redis_client.hgetall("governance:metrics:deliberations")
            counters = counters_raw if isinstance(counters_raw, Mapping) else {}
            total = int(counters.get("total", 0))
            success = int(counters.get("success", 0))
            failed = int(counters.get("failed", 0))

            success_rate = success / total if total > 0 else 1.0  # Default to 1.0 if no data

            return {
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": success_rate,
            }
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error getting deliberation metrics: {e}")
            return {"total": 0, "success": 0, "failed": 0, "success_rate": 1.0}

    def _compute_percentiles(self, values: list[float]) -> tuple[float, float, float]:
        """Compute p50, p95, p99 percentiles.

        Args:
            values: list of values to compute percentiles from

        Returns:
            tuple of (p50, p95, p99)
        """
        if not values:
            return (0.0, 0.0, 0.0)

        sorted_values = sorted(values)
        if PERF_KERNELS_AVAILABLE:
            p50, p95, p99 = compute_percentiles_floor_index(sorted_values, [50.0, 95.0, 99.0])
            return (p50, p95, p99)

        n = len(sorted_values)
        p50 = sorted_values[min(int(n * 0.50), n - 1)]
        p95 = sorted_values[min(int(n * 0.95), n - 1)]
        p99 = sorted_values[min(int(n * 0.99), n - 1)]

        return (p50, p95, p99)

    async def _store_snapshot(self, snapshot: GovernanceMetricsSnapshot) -> None:
        """Store a snapshot in Redis for historical tracking."""
        try:
            timestamp = snapshot.timestamp.timestamp()
            key = f"governance:metrics:snapshots:{int(timestamp)}"

            await self.redis_client.set(
                key,
                snapshot.model_dump_json(),
                ex=3600 * self.snapshot_retention_hours,
            )

            # Also add to sorted set for easy retrieval
            await self.redis_client.zadd("governance:metrics:snapshots:index", {key: timestamp})

            # Cleanup old snapshots
            cutoff = timestamp - (3600 * self.snapshot_retention_hours)
            await self.redis_client.zremrangebyscore(
                "governance:metrics:snapshots:index",
                "-inf",
                cutoff,
            )

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Error storing snapshot: {e}")


__all__ = [
    "GovernanceMetricsCollector",
    "GovernanceMetricsSnapshot",
    "MetricsComparison",
]
