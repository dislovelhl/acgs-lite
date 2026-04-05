"""
Multi-Agent Orchestrator for Performance Optimization
Constitutional Hash: 608508a9bd224290

Reference: SPEC_ACGS2_ENHANCED_v2.3 Section 16 (Performance Engineering)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Constitutional Hash - immutable reference
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .agents import (
    AgentCoordinationProfiler,
    ApplicationPerformanceAgent,
    CachePerformanceAgent,
    DatabasePerformanceAgent,
    FrontendPerformanceAgent,
    OptimizationDomain,
    PerformanceProfile,
    PerformanceProfiler,
)
from .context import ContextWindowOptimizer
from .cost import CostOptimizer


class OptimizationScope(Enum):
    """Defines the scope/depth of optimization."""

    QUICK_WIN = "quick_win"  # Fast, low-risk optimizations
    MODERATE = "moderate"  # Standard optimization cycle
    COMPREHENSIVE = "comprehensive"  # Deep analysis and optimization


@dataclass
class OptimizationResult:
    """Result of an optimization action."""

    domain: OptimizationDomain
    action: str
    success: bool
    before_metrics: JSONDict = field(default_factory=dict)
    after_metrics: JSONDict = field(default_factory=dict)
    improvement_percent: float = 0.0
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)


class PerformanceTracker:
    """Tracks performance optimization history and metrics."""

    def __init__(self) -> None:
        self._history: dict[str, list[JSONDict]] = {}

    def log(self, agent_name: str, metrics: JSONDict) -> None:
        """Log metrics for an agent."""
        if agent_name not in self._history:
            self._history[agent_name] = []
        self._history[agent_name].append(
            {
                "metrics": metrics,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    def get_summary(self) -> JSONDict:
        """Get summary of tracked performance."""
        return {
            name: {
                "total_runs": len(entries),
                "latest": entries[-1] if entries else None,
            }
            for name, entries in self._history.items()
        }


class MultiAgentOrchestrator:
    """
    Facade for the Multi-Agent Optimization Toolkit.

    Coordinates multiple specialized profiling agents to provide
    comprehensive performance optimization capabilities.
    """

    def __init__(
        self,
        scope: OptimizationScope = OptimizationScope.MODERATE,
        max_workers: int = 4,
        target_system: str = "acgs2",
    ) -> None:
        """
        Initialize the multi-agent orchestrator.

        Args:
            scope: Optimization scope/depth
            max_workers: Maximum parallel profiling workers
            target_system: System being optimized
        """
        self.scope = scope
        self.max_workers = max_workers
        self.target_system = target_system

        # Initialize profiling agents
        self.agents: dict[OptimizationDomain, PerformanceProfiler] = {
            OptimizationDomain.DATABASE: DatabasePerformanceAgent(target_system),
            OptimizationDomain.APPLICATION: ApplicationPerformanceAgent(target_system),
            OptimizationDomain.CACHE: CachePerformanceAgent(target_system),
            OptimizationDomain.AGENT_COORDINATION: AgentCoordinationProfiler(),
        }

        # Add frontend agent for comprehensive scope
        if scope == OptimizationScope.COMPREHENSIVE:
            self.agents[OptimizationDomain.NETWORK] = FrontendPerformanceAgent(target_system)

        # Initialize optimizers
        self.context_optimizer = ContextWindowOptimizer()
        self.cost_optimizer = CostOptimizer()
        self.tracker = PerformanceTracker()

        # Storage for latest profiles
        self._latest_profiles: dict[OptimizationDomain, PerformanceProfile] = {}

    async def profile_all(self) -> dict[OptimizationDomain, PerformanceProfile]:
        """
        Profile all components in parallel.

        Returns:
            Dictionary mapping domains to their performance profiles
        """
        tasks = [agent.profile() for agent in self.agents.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        profiles: dict[OptimizationDomain, PerformanceProfile] = {}
        for agent, result in zip(self.agents.values(), results, strict=False):
            if isinstance(result, BaseException):
                # Log error but continue with other profiles
                self.tracker.log(
                    agent.__class__.__name__,
                    {"error": str(result)},
                )
            else:
                profile = result  # type: PerformanceProfile
                profiles[profile.domain] = profile
                self.tracker.log(
                    agent.__class__.__name__,
                    {
                        "latency_p99_ms": profile.latency_p99_ms,
                        "throughput_rps": profile.throughput_rps,
                        "error_rate": profile.error_rate,
                    },
                )

        self._latest_profiles = profiles
        return profiles

    async def optimize(
        self,
        target_domains: list[OptimizationDomain] | None = None,
    ) -> list[OptimizationResult]:
        """
        Run optimization cycle.

        Args:
            target_domains: Specific domains to optimize (None = all)

        Returns:
            List of optimization results
        """
        # First profile if needed
        if not self._latest_profiles:
            await self.profile_all()

        results = []
        domains = target_domains or list(self._latest_profiles.keys())

        for domain in domains:
            profile = self._latest_profiles.get(domain)
            if not profile:
                continue

            # Generate recommendations based on profile
            recommendations = self._generate_recommendations(profile)

            for recommendation in recommendations:
                result = OptimizationResult(
                    domain=domain,
                    action=recommendation,
                    success=True,  # Simulated success
                    before_metrics={
                        "latency_p99_ms": profile.latency_p99_ms,
                        "throughput_rps": profile.throughput_rps,
                    },
                )
                results.append(result)

        return results

    def _generate_recommendations(
        self,
        profile: PerformanceProfile,
    ) -> list[str]:
        """Generate recommendations based on profile."""
        recommendations = []

        # ACGS-2 targets: P99 < 5ms, throughput > 100 RPS, cache > 85%
        if profile.latency_p99_ms > 5.0:
            recommendations.append(
                f"High latency detected ({profile.latency_p99_ms}ms). "
                "Consider enabling cache warming or optimizing hot paths."
            )

        if profile.throughput_rps < 100.0:
            recommendations.append(
                f"Low throughput ({profile.throughput_rps} RPS). "
                "Consider horizontal scaling or connection pooling."
            )

        if profile.error_rate > 0.01:
            recommendations.append(
                f"Elevated error rate ({profile.error_rate * 100:.2f}%). "
                "Review error patterns and implement circuit breakers."
            )

        if profile.cache_hit_rate and profile.cache_hit_rate < 0.85:
            recommendations.append(
                f"Low cache hit rate ({profile.cache_hit_rate * 100:.1f}%). "
                "Review cache key patterns and TTL settings."
            )

        if profile.resource_utilization > 0.8:
            recommendations.append(
                f"High resource utilization ({profile.resource_utilization * 100:.1f}%). "
                "Consider scaling or optimizing resource-intensive operations."
            )

        return recommendations

    def get_optimization_report(self) -> JSONDict:
        """Generate comprehensive optimization report."""
        return {
            "scope": self.scope.value,
            "agents": list(self.agents.keys()),
            "profiles": {
                domain.value: {
                    "latency_p99_ms": profile.latency_p99_ms,
                    "throughput_rps": profile.throughput_rps,
                    "error_rate": profile.error_rate,
                    "resource_utilization": profile.resource_utilization,
                }
                for domain, profile in self._latest_profiles.items()
            },
            "tracker_summary": self.tracker.get_summary(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def run_optimization_cycle(self) -> JSONDict:
        """
        Run a full optimization cycle (legacy compatibility).

        Returns:
            Dictionary with profiles and recommendations
        """
        profiles = await self.profile_all()
        results = await self.optimize()

        return {
            "profiles": {
                domain.value: {
                    "latency_p99_ms": profile.latency_p99_ms,
                    "throughput_rps": profile.throughput_rps,
                }
                for domain, profile in profiles.items()
            },
            "recommendations": [r.action for r in results],
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def compress_context(self, context: str, max_tokens: int = 4000) -> str:
        """Expose context compression as a toolkit feature."""
        return self.context_optimizer.compress_context(context, max_tokens)


def create_optimization_toolkit(
    scope: OptimizationScope = OptimizationScope.MODERATE,
    target_system: str = "acgs2",
) -> MultiAgentOrchestrator:
    """
    Factory function to create optimization toolkit.

    Args:
        scope: Optimization scope/depth
        target_system: System being optimized

    Returns:
        Configured MultiAgentOrchestrator instance
    """
    return MultiAgentOrchestrator(scope=scope, target_system=target_system)
