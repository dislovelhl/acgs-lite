"""
ACGS-2 Context Drift Detection
Constitutional Hash: 608508a9bd224290

Detects behavioral anomalies and context drift in agent communications.
Tracks patterns over time and identifies deviations from normal behavior.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class DriftSeverity(Enum):
    """Severity levels for detected drift."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DriftType(Enum):
    """Types of context drift detected."""

    BEHAVIORAL = "behavioral"  # Change in agent behavior patterns
    TEMPORAL = "temporal"  # Unusual timing patterns
    VOLUME = "volume"  # Unusual request volume
    SEMANTIC = "semantic"  # Change in message content patterns
    PERMISSION = "permission"  # Change in permission usage patterns
    IMPACT = "impact"  # Change in impact score patterns


@dataclass
class DriftDetectionResult:
    """Result of context drift detection."""

    has_drift: bool
    severity: DriftSeverity | None = None
    drift_type: DriftType | None = None
    agent_id: str | None = None
    baseline_value: float | None = None
    current_value: float | None = None
    deviation_score: float = 0.0  # 0.0-1.0, higher = more deviation
    confidence: float = 0.0  # 0.0-1.0, confidence in detection
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class AgentProfile:
    """Profile of an agent's normal behavior."""

    agent_id: str
    impact_scores: deque = field(default_factory=lambda: deque(maxlen=100))
    request_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    message_types: dict[str, int] = field(default_factory=dict)
    permission_usage: dict[str, int] = field(default_factory=dict)
    semantic_patterns: list[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_mean_impact(self) -> float:
        """Calculate mean impact score."""
        if not self.impact_scores:
            return 0.0
        return float(sum(self.impact_scores)) / len(self.impact_scores)

    def get_std_impact(self) -> float:
        """Calculate standard deviation of impact scores."""
        if len(self.impact_scores) < 2:
            return 0.0
        mean = self.get_mean_impact()
        variance = float(sum((x - mean) ** 2 for x in self.impact_scores)) / len(self.impact_scores)
        return float(variance**0.5)

    def get_request_rate(self, window_seconds: int = 60) -> float:
        """Calculate requests per second in the last window."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=window_seconds)
        recent = [t for t in self.request_times if t > cutoff]
        return len(recent) / window_seconds if window_seconds > 0 else 0.0


class ContextDriftDetector:
    """
    Detects context drift and behavioral anomalies in agent communications.

    Features:
    - Behavioral pattern tracking
    - Statistical anomaly detection
    - Temporal pattern analysis
    - Volume anomaly detection
    - Semantic drift detection
    - Multi-dimensional drift scoring
    """

    def __init__(
        self,
        drift_threshold: float = 0.3,  # Threshold for drift detection (0.0-1.0)
        min_samples: int = 10,  # Minimum samples before detecting drift
        window_size: int = 100,  # Window size for pattern tracking
    ):
        """
        Initialize context drift detector.

        Args:
            drift_threshold: Threshold for drift detection (higher = stricter)
            min_samples: Minimum samples needed before detecting drift
            window_size: Window size for pattern tracking
        """
        self.drift_threshold = drift_threshold
        self.min_samples = min_samples
        self.window_size = window_size
        self.agent_profiles: dict[str, AgentProfile] = {}
        self.detection_history: list[DriftDetectionResult] = []

    def update_profile(
        self,
        agent_id: str,
        impact_score: float,
        message_type: str | None = None,
        permissions: list[str] | None = None,
        semantic_features: list[str] | None = None,
    ):
        """
        Update agent profile with new observation.

        Args:
            agent_id: Agent identifier
            impact_score: Impact score for this message
            message_type: Type of message
            permissions: Permissions used
            semantic_features: Semantic features extracted
        """
        if agent_id not in self.agent_profiles:
            self.agent_profiles[agent_id] = AgentProfile(agent_id=agent_id)

        profile = self.agent_profiles[agent_id]
        profile.impact_scores.append(impact_score)
        profile.request_times.append(datetime.now(UTC))
        profile.last_updated = datetime.now(UTC)

        if message_type:
            profile.message_types[message_type] = profile.message_types.get(message_type, 0) + 1

        if permissions:
            for perm in permissions:
                profile.permission_usage[perm] = profile.permission_usage.get(perm, 0) + 1

        if semantic_features:
            profile.semantic_patterns.extend(semantic_features[:10])  # Keep last 10 features

    def detect_drift(
        self,
        agent_id: str,
        current_impact: float,
        current_time: datetime | None = None,
    ) -> DriftDetectionResult:
        """
        Detect context drift for an agent.

        Args:
            agent_id: Agent identifier
            current_impact: Current impact score
            current_time: Current timestamp

        Returns:
            DriftDetectionResult with detection details
        """
        current_time = current_time or datetime.now(UTC)

        if agent_id not in self.agent_profiles:
            # No profile yet, create one
            self.agent_profiles[agent_id] = AgentProfile(agent_id=agent_id)
            return DriftDetectionResult(
                has_drift=False,
                agent_id=agent_id,
                confidence=0.0,
                metadata={"reason": "insufficient_data"},
            )

        profile = self.agent_profiles[agent_id]

        # Need minimum samples
        if len(profile.impact_scores) < self.min_samples:
            return DriftDetectionResult(
                has_drift=False,
                agent_id=agent_id,
                confidence=0.0,
                metadata={"reason": "insufficient_samples", "samples": len(profile.impact_scores)},
            )

        # Detect different types of drift
        drift_results = []

        # 1. Impact score drift (behavioral)
        impact_drift = self._detect_impact_drift(profile, current_impact)
        if impact_drift:
            drift_results.append(impact_drift)

        # 2. Volume drift
        volume_drift = self._detect_volume_drift(profile, current_time)
        if volume_drift:
            drift_results.append(volume_drift)

        # 3. Temporal drift
        temporal_drift = self._detect_temporal_drift(profile, current_time)
        if temporal_drift:
            drift_results.append(temporal_drift)

        # 4. Permission usage drift
        permission_drift = self._detect_permission_drift(profile)
        if permission_drift:
            drift_results.append(permission_drift)

        # Combine results
        if not drift_results:
            return DriftDetectionResult(
                has_drift=False,
                agent_id=agent_id,
                confidence=0.0,
            )

        # Select most severe drift
        most_severe = max(drift_results, key=lambda r: self._severity_value(r.severity))

        # Calculate overall deviation score
        avg_deviation = sum(r.deviation_score for r in drift_results) / len(drift_results)
        avg_confidence = sum(r.confidence for r in drift_results) / len(drift_results)

        result = DriftDetectionResult(
            has_drift=True,
            severity=most_severe.severity,
            drift_type=most_severe.drift_type,
            agent_id=agent_id,
            baseline_value=most_severe.baseline_value,
            current_value=most_severe.current_value,
            deviation_score=avg_deviation,
            confidence=avg_confidence,
            metadata={
                "drift_count": len(drift_results),
                "drift_types": [r.drift_type.value for r in drift_results],
            },
        )

        self.detection_history.append(result)
        return result

    def _detect_impact_drift(
        self, profile: AgentProfile, current_impact: float
    ) -> DriftDetectionResult | None:
        """Detect drift in impact scores."""
        mean = profile.get_mean_impact()
        std = profile.get_std_impact()

        if std == 0:
            return None

        # Z-score calculation
        z_score = abs(current_impact - mean) / std if std > 0 else 0.0

        # Threshold: 2 standard deviations = medium, 3 = high, 4+ = critical
        if z_score < 2.0:
            return None

        severity = DriftSeverity.MEDIUM
        if z_score >= 4.0:
            severity = DriftSeverity.CRITICAL
        elif z_score >= 3.0:
            severity = DriftSeverity.HIGH

        deviation_score = min(1.0, z_score / 4.0)  # Normalize to 0-1
        confidence = min(1.0, len(profile.impact_scores) / 50.0)  # More samples = higher confidence

        return DriftDetectionResult(
            has_drift=True,
            severity=severity,
            drift_type=DriftType.IMPACT,
            agent_id=profile.agent_id,
            baseline_value=mean,
            current_value=current_impact,
            deviation_score=deviation_score,
            confidence=confidence,
            metadata={"z_score": z_score, "std": std},
        )

    def _detect_volume_drift(
        self, profile: AgentProfile, current_time: datetime
    ) -> DriftDetectionResult | None:
        """Detect drift in request volume."""
        if len(profile.request_times) < self.min_samples:
            return None

        # Calculate current and historical rates
        current_rate = profile.get_request_rate(window_seconds=60)

        # Historical rate (last hour)
        historical_times = list(profile.request_times)[-100:]  # Last 100 requests
        if len(historical_times) < 10:
            return None

        # Calculate average rate over historical window
        if len(historical_times) >= 2:
            time_span = (historical_times[-1] - historical_times[0]).total_seconds()
            historical_rate = len(historical_times) / time_span if time_span > 0 else 0.0
        else:
            historical_rate = current_rate

        if historical_rate == 0:
            return None

        # Check for significant increase (>2x) or decrease (<0.5x)
        ratio = current_rate / historical_rate if historical_rate > 0 else 1.0

        if 0.5 <= ratio <= 2.0:
            return None

        severity = DriftSeverity.MEDIUM
        if ratio > 5.0 or ratio < 0.2:
            severity = DriftSeverity.CRITICAL
        elif ratio > 3.0 or ratio < 0.33:
            severity = DriftSeverity.HIGH

        deviation_score = min(1.0, abs(ratio - 1.0) / 4.0)
        confidence = min(1.0, len(historical_times) / 50.0)

        return DriftDetectionResult(
            has_drift=True,
            severity=severity,
            drift_type=DriftType.VOLUME,
            agent_id=profile.agent_id,
            baseline_value=historical_rate,
            current_value=current_rate,
            deviation_score=deviation_score,
            confidence=confidence,
            metadata={"ratio": ratio},
        )

    def _detect_temporal_drift(
        self, profile: AgentProfile, current_time: datetime
    ) -> DriftDetectionResult | None:
        """Detect temporal pattern anomalies."""
        if len(profile.request_times) < 20:
            return None

        # Check for unusual time-of-day patterns
        hour = current_time.hour

        # Analyze historical hour distribution
        hour_counts: dict[int, int] = {}
        for req_time in profile.request_times:
            h = req_time.hour
            hour_counts[h] = hour_counts.get(h, 0) + 1

        if not hour_counts:
            return None

        # Find most common hours
        total_requests = sum(hour_counts.values())
        hour_frequencies = {h: count / total_requests for h, count in hour_counts.items()}

        # Current hour frequency
        current_hour_freq = hour_frequencies.get(hour, 0.0)

        # If current hour is very unusual (<5% of requests), flag it
        if current_hour_freq < 0.05 and total_requests > 20:
            # Check if it's a known quiet period (e.g., 2-5 AM)
            is_quiet_period = 2 <= hour <= 5

            severity = DriftSeverity.HIGH if is_quiet_period else DriftSeverity.MEDIUM
            deviation_score = 1.0 - current_hour_freq
            confidence = min(1.0, total_requests / 100.0)

            return DriftDetectionResult(
                has_drift=True,
                severity=severity,
                drift_type=DriftType.TEMPORAL,
                agent_id=profile.agent_id,
                baseline_value=sum(hour_frequencies.values()) / len(hour_frequencies),
                current_value=current_hour_freq,
                deviation_score=deviation_score,
                confidence=confidence,
                metadata={"hour": hour, "hour_frequency": current_hour_freq},
            )

        return None

    def _detect_permission_drift(self, profile: AgentProfile) -> DriftDetectionResult | None:
        """Detect drift in permission usage patterns."""
        if len(profile.permission_usage) < 2:
            return None

        # Check for new or unusual permissions
        # This is a simplified check - in production, would track permission patterns over time
        total_permissions = sum(profile.permission_usage.values())

        # If a single permission dominates (>80%), might indicate drift
        max_perm_count = max(profile.permission_usage.values())
        if max_perm_count / total_permissions > 0.8 and total_permissions > 10:
            deviation_score = (max_perm_count / total_permissions - 0.8) / 0.2
            confidence = min(1.0, total_permissions / 50.0)

            return DriftDetectionResult(
                has_drift=True,
                severity=DriftSeverity.MEDIUM,
                drift_type=DriftType.PERMISSION,
                agent_id=profile.agent_id,
                baseline_value=total_permissions / len(profile.permission_usage),
                current_value=max_perm_count,
                deviation_score=deviation_score,
                confidence=confidence,
                metadata={"permission_distribution": dict(profile.permission_usage)},
            )

        return None

    @staticmethod
    def _severity_value(severity: DriftSeverity) -> int:
        """Get numeric value for severity comparison."""
        return {
            DriftSeverity.LOW: 1,
            DriftSeverity.MEDIUM: 2,
            DriftSeverity.HIGH: 3,
            DriftSeverity.CRITICAL: 4,
        }.get(severity, 0)

    def get_agent_profile(self, agent_id: str) -> AgentProfile | None:
        """Get profile for an agent."""
        return self.agent_profiles.get(agent_id)

    def get_drift_summary(self, agent_id: str | None = None) -> JSONDict:
        """Get summary of drift detections."""
        if agent_id:
            detections = [d for d in self.detection_history if d.agent_id == agent_id]
        else:
            detections = self.detection_history

        return {
            "total_detections": len(detections),
            "by_severity": {
                severity.value: len([d for d in detections if d.severity == severity])
                for severity in DriftSeverity
            },
            "by_type": {
                drift_type.value: len([d for d in detections if d.drift_type == drift_type])
                for drift_type in DriftType
            },
            "recent_detections": [
                {
                    "agent_id": d.agent_id,
                    "severity": d.severity.value if d.severity else None,
                    "type": d.drift_type.value if d.drift_type else None,
                    "deviation_score": d.deviation_score,
                }
                for d in detections[-10:]
            ],
        }
