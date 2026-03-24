"""
ACGS-2 Cost Optimizer
Constitutional Hash: cdd01ef066bc6cf2

Main cost optimization engine integrating cost modeling, budget management,
anomaly detection, batch optimization, and cost-aware provider selection.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CONSTITUTIONAL_HASH,
    CapabilityRegistry,
    CapabilityRequirement,
    LatencyClass,
    ProviderCapabilityProfile,
    get_capability_registry,
)
from enhanced_agent_bus.llm_adapters.cost.models import (
    CostAnomaly,
    CostEstimate,
    CostModel,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

from .anomaly import CostAnomalyDetector
from .batch import BatchOptimizer
from .budget import BudgetManager
from .enums import CostTier, QualityLevel, UrgencyLevel

logger = get_logger(__name__)


class CostOptimizer:
    """
    Main cost optimization engine.

    Constitutional Hash: cdd01ef066bc6cf2

    Integrates:
    - Cost modeling
    - Budget management
    - Anomaly detection
    - Batch optimization
    - Cost-aware provider selection
    """

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        """Initialize cost optimizer."""
        self.registry = registry or get_capability_registry()
        self.budget_manager = BudgetManager()
        self.anomaly_detector = CostAnomalyDetector()
        self.batch_optimizer = BatchOptimizer()

        # Cost models
        self._cost_models: dict[str, CostModel] = {}
        self._lock = asyncio.Lock()

        # Initialize default cost models
        self._initialize_default_cost_models()

    def _initialize_default_cost_models(self) -> None:
        """Initialize cost models from capability registry."""
        for profile in self.registry.get_all_profiles():
            cost_model = CostModel(
                provider_id=profile.provider_id,
                model_id=profile.model_id,
                input_cost_per_1k=profile.input_cost_per_1k,
                output_cost_per_1k=profile.output_cost_per_1k,
                cached_input_cost_per_1k=profile.cached_input_cost_per_1k,
                tier=self._classify_tier(profile),
            )
            self._cost_models[profile.provider_id] = cost_model

    def _classify_tier(self, profile: ProviderCapabilityProfile) -> CostTier:
        """Classify provider into cost tier."""
        total_cost = profile.input_cost_per_1k + profile.output_cost_per_1k

        if total_cost == 0:
            return CostTier.FREE
        if total_cost < 0.005:
            return CostTier.BUDGET
        if total_cost < 0.02:
            return CostTier.STANDARD
        if total_cost < 0.1:
            return CostTier.PREMIUM
        return CostTier.ENTERPRISE

    def register_cost_model(self, model: CostModel) -> None:
        """Register a custom cost model."""
        self._cost_models[model.provider_id] = model
        logger.info(f"Registered cost model for: {model.provider_id}")

    def get_cost_model(self, provider_id: str) -> CostModel | None:
        """Get cost model for a provider."""
        return self._cost_models.get(provider_id)

    def estimate_cost(
        self,
        provider_id: str,
        input_tokens: int,
        estimated_output_tokens: int,
        cached_tokens: int = 0,
    ) -> CostEstimate | None:
        """Estimate cost for a request."""
        cost_model = self._cost_models.get(provider_id)
        if not cost_model:
            return None

        cost = cost_model.calculate_cost(
            input_tokens=input_tokens,
            output_tokens=estimated_output_tokens,
            cached_tokens=cached_tokens,
        )

        breakdown = {
            "input": (input_tokens - cached_tokens) / 1000 * cost_model.input_cost_per_1k,
            "cached_input": cached_tokens / 1000 * cost_model.cached_input_cost_per_1k,
            "output": estimated_output_tokens / 1000 * cost_model.output_cost_per_1k,
        }

        return CostEstimate(
            provider_id=provider_id,
            model_id=cost_model.model_id,
            estimated_cost=cost,
            input_tokens=input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            confidence=0.85,  # Default confidence
            breakdown=breakdown,
        )

    async def select_optimal_provider(
        self,
        requirements: list[CapabilityRequirement],
        tenant_id: str,
        urgency: UrgencyLevel = UrgencyLevel.NORMAL,
        quality: QualityLevel = QualityLevel.STANDARD,
        estimated_input_tokens: int = 1000,
        estimated_output_tokens: int = 500,
        max_cost: float | None = None,
    ) -> tuple[ProviderCapabilityProfile | None, CostEstimate | None]:
        """
        Select optimal provider based on requirements, cost, and constraints.

        Returns:
            Tuple of (selected_profile, cost_estimate)
        """
        # Get capable providers
        capable = self.registry.find_capable_providers(requirements)
        if not capable:
            return None, None

        candidates = []

        for profile, score in capable:
            cost_model = self._cost_models.get(profile.provider_id)
            if not cost_model:
                continue

            # Calculate cost
            cost = cost_model.calculate_cost(
                input_tokens=estimated_input_tokens,
                output_tokens=estimated_output_tokens,
            )

            # Check max cost constraint
            if max_cost and cost > max_cost:
                continue

            # Check budget
            within_budget, _ = await self.budget_manager.check_budget(tenant_id, cost)
            if not within_budget:
                continue

            # Calculate composite score
            # Weight factors based on urgency and quality
            cost_weight = 0.5 if urgency == UrgencyLevel.BATCH else 0.3
            latency_weight = 0.1 if urgency == UrgencyLevel.BATCH else 0.4
            quality_weight = 0.4 if quality == QualityLevel.MAXIMUM else 0.3

            # Normalize cost (lower is better)
            max_cost_observed = max(
                (
                    self._cost_models.get(p.provider_id).calculate_cost(
                        estimated_input_tokens, estimated_output_tokens
                    )
                    if self._cost_models.get(p.provider_id)
                    else float("inf")
                )
                for p, _ in capable
            )
            cost_score = 1 - (cost / max_cost_observed) if max_cost_observed > 0 else 0

            # Latency score (lower latency class is better)
            latency_order = {
                LatencyClass.ULTRA_LOW: 1.0,
                LatencyClass.LOW: 0.8,
                LatencyClass.MEDIUM: 0.5,
                LatencyClass.HIGH: 0.2,
                LatencyClass.VARIABLE: 0.3,
            }
            latency_score = latency_order.get(profile.latency_class, 0.5)

            # Composite score
            composite_score = (
                cost_weight * cost_score + latency_weight * latency_score + quality_weight * score
            )

            candidates.append((profile, cost, composite_score))

        if not candidates:
            return None, None

        # Sort by composite score (descending)
        candidates.sort(key=lambda x: x[2], reverse=True)

        # Select best candidate
        selected, cost, _ = candidates[0]

        estimate = CostEstimate(
            provider_id=selected.provider_id,
            model_id=selected.model_id,
            estimated_cost=cost,
            input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            confidence=0.85,
        )

        return selected, estimate

    async def record_actual_cost(
        self,
        tenant_id: str,
        provider_id: str,
        actual_cost: float,
        operation_type: str | None = None,
    ) -> CostAnomaly | None:
        """Record actual cost and check for anomalies."""
        # Record against budget
        await self.budget_manager.record_cost(tenant_id, actual_cost, operation_type)

        # Check for anomalies
        anomaly = await self.anomaly_detector.record_cost(tenant_id, provider_id, actual_cost)

        return anomaly

    def get_cost_comparison(
        self,
        requirements: list[CapabilityRequirement],
        estimated_input_tokens: int = 1000,
        estimated_output_tokens: int = 500,
    ) -> list[JSONDict]:
        """Get cost comparison across all capable providers."""
        capable = self.registry.find_capable_providers(requirements)

        comparisons = []
        for profile, score in capable:
            cost_model = self._cost_models.get(profile.provider_id)
            if not cost_model:
                continue

            cost = cost_model.calculate_cost(
                input_tokens=estimated_input_tokens,
                output_tokens=estimated_output_tokens,
            )

            comparisons.append(
                {
                    "provider_id": profile.provider_id,
                    "model_id": profile.model_id,
                    "display_name": profile.display_name,
                    "estimated_cost": cost,
                    "cost_tier": cost_model.tier.value,
                    "latency_class": profile.latency_class.value,
                    "capability_score": score,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }
            )

        # Sort by cost
        comparisons.sort(key=lambda x: x["estimated_cost"])  # type: ignore[arg-type, return-value]

        return comparisons

    def get_cost_analytics(
        self,
        tenant_id: str,
    ) -> JSONDict:
        """Get cost analytics for a tenant."""
        usage = self.budget_manager.get_usage_summary(tenant_id)
        anomalies = self.anomaly_detector.get_recent_anomalies(
            tenant_id=tenant_id,
            since=datetime.now(UTC) - timedelta(days=7),
        )

        return {
            "tenant_id": tenant_id,
            "usage": usage,
            "recent_anomalies": [
                {
                    "anomaly_id": a.anomaly_id,
                    "type": a.anomaly_type,
                    "severity": a.severity,
                    "description": a.description,
                    "detected_at": a.detected_at.isoformat(),
                }
                for a in anomalies
            ],
            "pending_batches": self.batch_optimizer.get_pending_count(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# =============================================================================
# Global Instances
# =============================================================================

_cost_optimizer: CostOptimizer | None = None


def get_cost_optimizer() -> CostOptimizer:
    """Get the global cost optimizer."""
    global _cost_optimizer
    if _cost_optimizer is None:
        _cost_optimizer = CostOptimizer()
    return _cost_optimizer


async def initialize_cost_optimizer() -> None:
    """Initialize the cost optimizer."""
    get_cost_optimizer()
    logger.info("Cost optimizer initialized")


__all__ = [
    "CostOptimizer",
    "get_cost_optimizer",
    "initialize_cost_optimizer",
]
