"""
Impact scoring data models and enums.
Constitutional Hash: cdd01ef066bc6cf2
"""

from dataclasses import dataclass, field
from enum import Enum

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class ScoringMethod(Enum):
    SEMANTIC = "semantic"
    MINICPM_SEMANTIC = "minicpm_semantic"  # MiniCPM-enhanced semantic scoring
    STATISTICAL = "statistical"
    HEURISTIC = "heuristic"
    LEARNING = "learning"
    ENSEMBLE = "ensemble"


@dataclass
class ScoringConfig:
    semantic_weight: float = 0.2
    permission_weight: float = 0.2
    volume_weight: float = 0.15
    context_weight: float = 0.15
    drift_weight: float = 0.1
    priority_weight: float = 0.1
    type_weight: float = 0.1
    high_impact_threshold: float = 0.8
    medium_impact_threshold: float = 0.4
    high_semantic_threshold: float = 0.7
    medium_semantic_threshold: float = 0.3
    max_volume_per_minute: int = 1000
    large_transaction_threshold: float = 10000.0
    small_transaction_threshold: float = 100.0
    drift_detection_window: int = 100
    drift_alert_threshold: float = 3.0
    critical_priority_boost: float = 0.9
    high_priority_boost: float = 0.5
    medium_priority_boost: float = 0.2
    governance_request_boost: float = 0.4
    command_boost: float = 0.2
    constitutional_validation_boost: float = 0.3
    high_semantic_boost: float = 0.8


@dataclass
class ImpactVector:
    """7-dimensional impact vector."""

    safety: float = 0.0
    security: float = 0.0
    privacy: float = 0.0
    fairness: float = 0.0
    reliability: float = 0.0
    transparency: float = 0.0
    efficiency: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "safety": self.safety,
            "security": self.security,
            "privacy": self.privacy,
            "fairness": self.fairness,
            "reliability": self.reliability,
            "transparency": self.transparency,
            "efficiency": self.efficiency,
        }


@dataclass
class ScoringResult:
    """Result of an impact scoring operation."""

    vector: ImpactVector
    aggregate_score: float
    method: ScoringMethod
    confidence: float
    metadata: JSONDict = field(default_factory=dict)
    version: str = "3.1.0"
