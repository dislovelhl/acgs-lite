"""
Semantic impact scoring implementation.
Constitutional Hash: cdd01ef066bc6cf2
"""

from enhanced_agent_bus.impact_scorer_infra.models import (
    ImpactVector,
    ScoringMethod,
    ScoringResult,
)

from .base import BaseScoringAlgorithm

HIGH_IMPACT_KEYWORDS = {
    "security",
    "breach",
    "unauthorized",
    "attack",
    "threat",
    "vulnerability",
    "exploit",
    "critical",
    "emergency",
    "danger",
    "suspicious",
    "intrusion",
    "compromise",
    "exfiltration",
    "violation",
    "malicious",
}


class SemanticScorer(BaseScoringAlgorithm):
    def score(self, context: dict) -> ScoringResult:
        text_parts = []
        for key in ("content", "action", "details", "description", "text"):
            if key in context:
                text_parts.append(str(context[key]))
        text = " ".join(text_parts).lower()

        matched_keywords = sum(1 for kw in HIGH_IMPACT_KEYWORDS if kw in text)
        keyword_score = min(1.0, matched_keywords * 0.25) if matched_keywords else 0.1

        security_score = (
            keyword_score
            if any(kw in text for kw in ("security", "breach", "unauthorized", "attack"))
            else 0.1
        )
        safety_score = (
            keyword_score
            if any(kw in text for kw in ("danger", "emergency", "critical", "threat"))
            else 0.1
        )

        vector = ImpactVector(
            safety=safety_score,
            security=security_score,
            privacy=context.get("privacy_sentiment", 0.1),
            fairness=context.get("fairness_sentiment", 0.1),
            reliability=context.get("reliability_sentiment", 0.1),
            transparency=context.get("transparency_sentiment", 0.1),
            efficiency=context.get("efficiency_sentiment", 0.1),
        )

        aggregate = max(keyword_score, sum(vector.to_dict().values()) / 7.0)

        return ScoringResult(
            vector=vector,
            aggregate_score=aggregate,
            method=ScoringMethod.SEMANTIC,
            confidence=0.8 if matched_keywords > 0 else 0.5,
        )
