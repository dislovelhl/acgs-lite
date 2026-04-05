"""
Cost Optimization for Multi-Agent Systems
Constitutional Hash: 608508a9bd224290

Reference: SPEC_ACGS2_ENHANCED_v2.3 Section 16.4 (Cost Management)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

# Constitutional Hash - immutable reference
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


@dataclass
class UsageRecord:
    """Record of model usage."""

    model: str
    tokens: int
    cost: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    task_complexity: int | None = None
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


class CostOptimizer:
    """
    Manages token budgets and model selection strategies.

    Implements intelligent model selection based on task complexity,
    quality requirements, and budget constraints.
    """

    # Model costs per 1M tokens (as of 2024)
    MODEL_COSTS_PER_1M: ClassVar[dict] = {
        # Claude models
        "claude-opus-4": 15.0,
        "claude-sonnet-4": 3.0,
        "claude-haiku-4": 0.25,
        # Legacy compatibility
        "claude-3-5-sonnet": 3.0,
        "claude-3-5-haiku": 0.25,
        # OpenAI models
        "gpt-4o": 5.0,
        "gpt-4o-mini": 0.15,
    }

    def __init__(
        self,
        monthly_budget: float = 100.0,
        daily_budget: float | None = None,
    ) -> None:
        """
        Initialize cost optimizer.

        Args:
            monthly_budget: Total budget for the month
            daily_budget: Optional daily budget limit (defaults to monthly/30)
        """
        self.monthly_budget = monthly_budget
        self.daily_budget = daily_budget or (monthly_budget / 30)
        self.total_cost = 0.0
        self.usage_history: list[UsageRecord] = []
        self.model_costs = self.MODEL_COSTS_PER_1M.copy()

    def select_optimal_model(
        self,
        task_complexity: int,
        quality_threshold: float = 0.8,
        cost_sensitive: bool = True,
    ) -> str:
        """
        Select the optimal model based on task complexity and constraints.

        Args:
            task_complexity: 1-5 scale (1=trivial, 5=expert-level)
            quality_threshold: Minimum quality requirement (0.0-1.0)
            cost_sensitive: Whether to optimize for cost

        Returns:
            Model identifier string
        """
        budget_ratio = self._get_budget_remaining_ratio()

        # High quality requirements always use best model
        if quality_threshold >= 0.95:
            return "claude-opus-4"

        # Emergency budget mode
        if budget_ratio < 0.1:
            return "claude-haiku-4"

        # Expert-level tasks
        if task_complexity >= 5:
            return "claude-opus-4"

        # Complex tasks
        if task_complexity >= 4:
            if cost_sensitive and budget_ratio < 0.5:
                return "claude-sonnet-4"
            return "claude-opus-4"

        # Medium complexity
        if task_complexity >= 3:
            return "claude-sonnet-4"

        # Simple tasks
        if task_complexity >= 2:
            if cost_sensitive:
                return "claude-haiku-4"
            return "claude-sonnet-4"

        # Trivial tasks
        return "claude-haiku-4"

    def estimate_cost(self, model: str, token_count: int) -> float:
        """
        Estimate cost for a given model and token count.

        Args:
            model: Model identifier
            token_count: Number of tokens

        Returns:
            Estimated cost in dollars
        """
        cost_per_1m = self.model_costs.get(model, 3.0)
        return float((token_count / 1_000_000) * cost_per_1m)

    def track_usage(self, model: str, tokens: int) -> JSONDict:
        """
        Track model usage and update costs.

        Args:
            model: Model identifier
            tokens: Number of tokens used

        Returns:
            Usage record with cost and budget info
        """
        cost = self.estimate_cost(model, tokens)
        self.total_cost += cost

        record = UsageRecord(
            model=model,
            tokens=tokens,
            cost=cost,
        )
        self.usage_history.append(record)

        return {
            "model": model,
            "tokens": tokens,
            "cost": cost,
            "total_cost": self.total_cost,
            "budget_remaining": self.monthly_budget - self.total_cost,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def record_usage(self, model: str, tokens: int) -> None:
        """
        Legacy method: Records token usage and updates current spend.

        Args:
            model: Model identifier
            tokens: Number of tokens used
        """
        self.track_usage(model, tokens)

    def is_within_budget(self) -> bool:
        """Check if current session is within budget."""
        return self.total_cost < self.monthly_budget

    def get_budget_status(self) -> JSONDict:
        """Get comprehensive budget status."""
        return {
            "total_cost": self.total_cost,
            "monthly_budget": self.monthly_budget,
            "daily_budget": self.daily_budget,
            "remaining": self.monthly_budget - self.total_cost,
            "utilization_percent": (self.total_cost / self.monthly_budget) * 100,
            "usage_records": len(self.usage_history),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def _get_budget_remaining_ratio(self) -> float:
        """Calculate remaining budget ratio."""
        if self.monthly_budget <= 0:
            return 0.0
        return max(0.0, (self.monthly_budget - self.total_cost) / self.monthly_budget)

    # Legacy compatibility
    def select_model(self, task_complexity: float, urgency: bool = False) -> str:
        """
        Legacy method for model selection.

        Args:
            task_complexity: 0.0-1.0 scale
            urgency: Whether task is urgent
        """
        # Convert 0-1 scale to 1-5 scale
        complexity_int = max(1, min(5, int(task_complexity * 5) + 1))
        quality = 0.95 if urgency else 0.8
        return self.select_optimal_model(complexity_int, quality)
