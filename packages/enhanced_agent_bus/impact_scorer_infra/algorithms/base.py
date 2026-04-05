"""
Base interfaces for impact scoring algorithms.
Constitutional Hash: 608508a9bd224290
"""

from abc import ABC, abstractmethod

from enhanced_agent_bus.impact_scorer_infra.models import (
    ImpactVector,
    ScoringMethod,
    ScoringResult,
)


class BaseScoringAlgorithm(ABC):
    """Abstract base class for impact scoring algorithms."""

    @abstractmethod
    def score(self, context: dict) -> ScoringResult:
        """Compute impact score for the given context."""
        pass


class WeightedEnsemble:
    """Combines multiple scoring results using defined weights."""

    def __init__(self, weights: dict | None = None):
        self.weights = weights or {
            "safety": 0.2,
            "security": 0.2,
            "privacy": 0.15,
            "fairness": 0.15,
            "reliability": 0.1,
            "transparency": 0.1,
            "efficiency": 0.1,
        }

    def combine(self, results: list) -> ScoringResult:
        if not results:
            return ScoringResult(
                vector=ImpactVector(),
                aggregate_score=0.0,
                method=ScoringMethod.ENSEMBLE,
                confidence=0.0,
            )

        total_score = 0.0
        combined_vector = ImpactVector()

        for res in results:
            total_score += res.aggregate_score
            for k, v in res.vector.to_dict().items():
                current_v = getattr(combined_vector, k)
                setattr(combined_vector, k, max(current_v, v))

        return ScoringResult(
            vector=combined_vector,
            aggregate_score=total_score / len(results),
            method=ScoringMethod.ENSEMBLE,
            confidence=min(res.confidence for res in results),
        )
