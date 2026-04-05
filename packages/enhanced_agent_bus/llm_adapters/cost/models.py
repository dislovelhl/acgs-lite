"""
ACGS-2 Cost Optimizer Models
Constitutional Hash: 608508a9bd224290

Data models for cost management, budgets, anomalies, and batch processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CONSTITUTIONAL_HASH,
    CapabilityRequirement,
)

from .enums import CostTier, QualityLevel, UrgencyLevel

# =============================================================================
# Cost Models
# =============================================================================


@dataclass
class CostModel:
    """
    Cost model for an LLM provider.

    Constitutional Hash: 608508a9bd224290
    """

    provider_id: str
    model_id: str

    # Per-token costs (USD per 1K tokens)
    input_cost_per_1k: float
    output_cost_per_1k: float
    cached_input_cost_per_1k: float = 0.0

    # Additional costs
    image_cost_per_image: float = 0.0  # For vision models
    audio_cost_per_minute: float = 0.0  # For audio models
    video_cost_per_minute: float = 0.0  # For video models

    # Volume discounts (threshold, discount_percentage)
    volume_discounts: list[tuple[int, float]] = field(default_factory=list)

    # Minimum charges
    minimum_cost_per_request: float = 0.0

    # Cost tier
    tier: CostTier = CostTier.STANDARD

    # Quality mapping (quality level -> capability requirements)
    quality_mapping: dict[QualityLevel, list[CapabilityRequirement]] = field(default_factory=dict)

    # Metadata
    currency: str = "USD"
    effective_date: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        images: int = 0,
        audio_minutes: float = 0.0,
        video_minutes: float = 0.0,
    ) -> float:
        """Calculate total cost for a request."""
        # Base token costs
        non_cached_input = max(0, input_tokens - cached_tokens)
        input_cost = (non_cached_input / 1000) * self.input_cost_per_1k
        cached_cost = (cached_tokens / 1000) * self.cached_input_cost_per_1k
        output_cost = (output_tokens / 1000) * self.output_cost_per_1k

        # Additional media costs
        image_cost = images * self.image_cost_per_image
        audio_cost = audio_minutes * self.audio_cost_per_minute
        video_cost = video_minutes * self.video_cost_per_minute

        total = input_cost + cached_cost + output_cost + image_cost + audio_cost + video_cost

        # Apply volume discounts
        total_tokens = input_tokens + output_tokens
        for threshold, discount in sorted(self.volume_discounts, reverse=True):
            if total_tokens >= threshold:
                total *= 1 - discount
                break

        # Apply minimum charge
        return max(total, self.minimum_cost_per_request)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "input_cost_per_1k": self.input_cost_per_1k,
            "output_cost_per_1k": self.output_cost_per_1k,
            "cached_input_cost_per_1k": self.cached_input_cost_per_1k,
            "tier": self.tier.value,
            "currency": self.currency,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class CostEstimate:
    """
    Cost estimate for a request.

    Constitutional Hash: 608508a9bd224290
    """

    provider_id: str
    model_id: str
    estimated_cost: float
    input_tokens: int
    estimated_output_tokens: int
    confidence: float  # 0.0 to 1.0
    currency: str = "USD"
    breakdown: dict[str, float] = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "estimated_cost": self.estimated_cost,
            "input_tokens": self.input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "confidence": self.confidence,
            "currency": self.currency,
            "breakdown": self.breakdown,
            "constitutional_hash": self.constitutional_hash,
        }


# =============================================================================
# Budget Models
# =============================================================================


@dataclass
class BudgetLimit:
    """
    Budget limit configuration.

    Constitutional Hash: 608508a9bd224290
    """

    limit_id: str
    tenant_id: str | None  # None for global limits
    operation_type: str | None  # None for all operations

    # Limits
    daily_limit: float | None = None
    monthly_limit: float | None = None
    per_request_limit: float | None = None

    # Actions when exceeded
    action_on_exceed: str = "block"  # block, warn, throttle, downgrade

    # Current usage
    daily_usage: float = 0.0
    monthly_usage: float = 0.0
    last_reset: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def check_limit(self, cost: float) -> tuple[bool, str | None]:
        """Check if cost would exceed limits."""
        # Check per-request limit
        if self.per_request_limit and cost > self.per_request_limit:
            return False, f"Per-request limit exceeded: ${cost:.4f} > ${self.per_request_limit:.4f}"

        # Check daily limit
        if self.daily_limit and (self.daily_usage + cost) > self.daily_limit:
            return (
                False,
                f"Daily limit exceeded: ${self.daily_usage + cost:.4f} > ${self.daily_limit:.4f}",
            )

        # Check monthly limit
        if self.monthly_limit and (self.monthly_usage + cost) > self.monthly_limit:
            return (
                False,
                f"Monthly limit exceeded: ${self.monthly_usage + cost:.4f} > ${self.monthly_limit:.4f}",
            )

        return True, None

    def record_usage(self, cost: float) -> None:
        """Record usage against this budget."""
        now = datetime.now(UTC)

        # Reset daily usage if new day
        if now.date() > self.last_reset.date():
            self.daily_usage = 0.0

        # Reset monthly usage if new month
        if now.month != self.last_reset.month or now.year != self.last_reset.year:
            self.monthly_usage = 0.0

        self.daily_usage += cost
        self.monthly_usage += cost
        self.last_reset = now


# =============================================================================
# Anomaly Models
# =============================================================================


@dataclass
class CostAnomaly:
    """
    Detected cost anomaly.

    Constitutional Hash: 608508a9bd224290
    """

    anomaly_id: str
    tenant_id: str
    provider_id: str
    detected_at: datetime
    anomaly_type: str  # spike, unusual_pattern, budget_warning
    severity: str  # low, medium, high, critical
    description: str
    expected_cost: float
    actual_cost: float
    deviation_percentage: float
    constitutional_hash: str = CONSTITUTIONAL_HASH


# =============================================================================
# Batch Models
# =============================================================================


@dataclass
class BatchRequest:
    """
    Request to be batched for cost optimization.

    Constitutional Hash: 608508a9bd224290
    """

    request_id: str
    tenant_id: str
    content: str
    requirements: list[CapabilityRequirement]
    urgency: UrgencyLevel
    quality: QualityLevel
    max_wait_time: timedelta | None  # Maximum time to wait for batching
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    estimated_tokens: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class BatchResult:
    """
    Result of batch processing.

    Constitutional Hash: 608508a9bd224290
    """

    batch_id: str
    requests: list[str]  # Request IDs
    provider_id: str
    total_cost: float
    cost_per_request: float
    savings_percentage: float
    processed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


__all__ = [
    "BatchRequest",
    "BatchResult",
    "BudgetLimit",
    "CostAnomaly",
    "CostEstimate",
    "CostModel",
]
