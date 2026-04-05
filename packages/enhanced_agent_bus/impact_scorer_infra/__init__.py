"""
Impact Scoring Infrastructure for ACGS-2.

Constitutional Hash: 608508a9bd224290

Provides comprehensive impact scoring with multiple algorithms:
- Semantic: Basic keyword-based scoring
- MiniCPM Semantic: Advanced 7-dimensional governance scoring
- Statistical: Statistical pattern analysis
- Ensemble: Weighted combination of scorers
"""

from .models import (
    ImpactVector,
    ScoringConfig,
    ScoringMethod,
    ScoringResult,
)
from .service import (
    CONSTITUTIONAL_HASH,
    ImpactScoringConfig,
    ImpactScoringService,
    calculate_message_impact,
    configure_impact_scorer,
    cosine_similarity_fallback,
    get_gpu_decision_matrix,
    get_impact_scorer,
    get_impact_scorer_service,
    get_profiling_report,
    reset_impact_scorer,
    reset_profiling,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Service
    "ImpactScoringConfig",
    "ImpactScoringService",
    # Models
    "ImpactVector",
    "ScoringConfig",
    "ScoringMethod",
    "ScoringResult",
    # Utility functions
    "calculate_message_impact",
    # Factory functions
    "configure_impact_scorer",
    "cosine_similarity_fallback",
    "get_gpu_decision_matrix",
    "get_impact_scorer",
    "get_impact_scorer_service",
    "get_profiling_report",
    "reset_impact_scorer",
    "reset_profiling",
]
