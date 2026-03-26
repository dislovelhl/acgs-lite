"""
Impact Scoring Algorithms for ACGS-2.

Constitutional Hash: 608508a9bd224290

Provides various algorithms for computing impact scores:
- Semantic: MiniCPM-based semantic understanding
- Statistical: Statistical analysis of message patterns
- Base: Abstract interfaces and ensemble combiners
"""

from .base import BaseScoringAlgorithm, WeightedEnsemble
from .minicpm_semantic import (
    DOMAIN_REFERENCE_TEXTS,
    HIGH_IMPACT_INDICATORS,
    GovernanceDomain,
    MiniCPMScorerConfig,
    MiniCPMSemanticScorer,
    create_minicpm_scorer,
)
from .semantic import SemanticScorer
from .statistical import StatisticalScorer

__all__ = [
    "DOMAIN_REFERENCE_TEXTS",
    "HIGH_IMPACT_INDICATORS",
    # Base
    "BaseScoringAlgorithm",
    "GovernanceDomain",
    "MiniCPMScorerConfig",
    # MiniCPM Semantic
    "MiniCPMSemanticScorer",
    # Semantic
    "SemanticScorer",
    # Statistical
    "StatisticalScorer",
    "WeightedEnsemble",
    "create_minicpm_scorer",
]
