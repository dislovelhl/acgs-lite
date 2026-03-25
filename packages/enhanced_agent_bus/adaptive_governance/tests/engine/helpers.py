"""
Test helpers for adaptive governance engine tests.
Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    ImpactFeatures,
    ImpactLevel,
)


def _make_features(risk_score: float = 0.3, confidence: float = 0.9):
    return ImpactFeatures(
        message_length=50,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.4,
        historical_precedence=1,
        resource_utilization=0.2,
        network_isolation=0.8,
        risk_score=risk_score,
        confidence_level=confidence,
    )


def _make_decision(risk_score: float = 0.3, action_allowed: bool = True):
    features = _make_features(risk_score=risk_score)
    return GovernanceDecision(
        action_allowed=action_allowed,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.9,
        reasoning="test reasoning",
        recommended_threshold=0.5,
        features_used=features,
    )
