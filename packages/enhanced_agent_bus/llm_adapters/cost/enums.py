"""
ACGS-2 Cost Optimizer Enums
Constitutional Hash: cdd01ef066bc6cf2

Cost-related enumerations for LLM provider cost management.
"""

from enum import Enum


class CostTier(str, Enum):  # noqa: UP042
    """Cost tier classification for providers."""

    FREE = "free"  # No cost (free tier)
    BUDGET = "budget"  # Very low cost
    STANDARD = "standard"  # Normal pricing
    PREMIUM = "premium"  # High cost, premium features
    ENTERPRISE = "enterprise"  # Enterprise pricing


class QualityLevel(str, Enum):  # noqa: UP042
    """Quality level for output requirements."""

    MINIMAL = "minimal"  # Fastest, cheapest
    BASIC = "basic"  # Good enough for simple tasks
    STANDARD = "standard"  # Standard quality
    HIGH = "high"  # High quality output
    MAXIMUM = "maximum"  # Best possible quality


class UrgencyLevel(str, Enum):  # noqa: UP042
    """Urgency level for request prioritization."""

    BATCH = "batch"  # Can be batched, very low priority
    LOW = "low"  # Can wait for optimal pricing
    NORMAL = "normal"  # Standard processing
    HIGH = "high"  # Should be processed quickly
    CRITICAL = "critical"  # Process immediately, cost secondary


__all__ = [
    "CostTier",
    "QualityLevel",
    "UrgencyLevel",
]
