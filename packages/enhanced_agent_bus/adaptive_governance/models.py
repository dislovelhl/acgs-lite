"""
ACGS-2 Adaptive Governance Data Models
Constitutional Hash: 608508a9bd224290

Defines core data structures for adaptive governance including enums,
dataclasses for governance metrics, impact features, and decisions.

This module contains:
- GovernanceMode: Enum for governance operation modes
- ImpactLevel: Enum for impact severity levels
- GovernanceMetrics: Metrics tracking governance performance
- ImpactFeatures: Feature extraction for ML impact scoring
- GovernanceDecision: Decision output from governance evaluation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any


class GovernanceMode(Enum):
    """Adaptive governance modes."""

    STRICT = "strict"  # Fixed constitutional thresholds
    ADAPTIVE = "adaptive"  # ML-adjusted thresholds
    EVOLVING = "evolving"  # Self-learning governance
    DEGRADED = "degraded"  # Fallback mode


class ImpactLevel(Enum):
    """Impact assessment levels."""

    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GovernanceMetrics:
    """Real-time governance performance metrics."""

    constitutional_compliance_rate: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    average_response_time: float = 0.0
    throughput_rps: float = 0.0
    human_override_rate: float = 0.0

    # Historical trends
    compliance_trend: list[float] = field(default_factory=list)
    accuracy_trend: list[float] = field(default_factory=list)
    performance_trend: list[float] = field(default_factory=list)


@dataclass
class ImpactFeatures:
    """Features for ML-based impact assessment."""

    message_length: int
    agent_count: int
    tenant_complexity: float
    temporal_patterns: list[float]
    semantic_similarity: float
    historical_precedence: int
    resource_utilization: float
    network_isolation: float

    # Derived features
    risk_score: float = 0.0
    confidence_level: float = 0.0


@dataclass
class GovernanceDecision:
    """ML-enhanced governance decision."""

    action_allowed: bool
    impact_level: ImpactLevel
    confidence_score: float
    reasoning: str
    recommended_threshold: float
    features_used: ImpactFeatures
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    decision_id: str = field(
        default_factory=lambda: f"gov-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    )
    # A/B testing cohort assignment (champion or candidate)
    cohort: str | None = None
    model_version: int | None = None

    def to_decision_record(self) -> dict[str, Any]:
        """Convert to canonical decision record dict.

        Returns a dict matching the ``GovernanceDecisionRecord`` schema.
        Uses a plain dict to avoid cross-package import from ``acgs_lite``.
        """
        return {
            "decision": "allow" if self.action_allowed else "deny",
            "triggered_rules": [],
            "violations": [],
            "confidence": self.confidence_score,
            "model_id": f"adaptive-v{self.model_version or 0}",
            "latency_ms": 0.0,
            "constitutional_hash": "",
            "audit_entry_id": self.decision_id,
            "action": "",
            "agent_id": "",
            "rules_checked": 0,
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
        }


__all__ = [
    "GovernanceDecision",
    "GovernanceMetrics",
    "GovernanceMode",
    "ImpactFeatures",
    "ImpactLevel",
]
