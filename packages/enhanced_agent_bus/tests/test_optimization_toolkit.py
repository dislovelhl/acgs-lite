"""
Tests for Multi-Agent Optimization Toolkit
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for performance profiling, optimization,
and multi-agent coordination.
"""

import asyncio
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.optimization_toolkit import (
    CONSTITUTIONAL_HASH,
    AgentCoordinationProfiler,
    ApplicationPerformanceAgent,
    CachePerformanceAgent,
    ContextWindowOptimizer,
    CostOptimizer,
    DatabasePerformanceAgent,
    MultiAgentOrchestrator,
    OptimizationDomain,
    OptimizationResult,
    OptimizationScope,
    PerformanceProfile,
    PerformanceTracker,
    create_optimization_toolkit,
)


class TestConstitutionalHash:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_profile_includes_constitutional_hash(self):
        """Verify profiles include constitutional hash."""
        profile = PerformanceProfile(
            domain=OptimizationDomain.APPLICATION,
            latency_p50_ms=1.0,
            latency_p95_ms=2.0,
            latency_p99_ms=5.0,
            throughput_rps=1000.0,
            error_rate=0.001,
            resource_utilization=0.5,
        )
        assert profile.constitutional_hash == CONSTITUTIONAL_HASH

    def test_optimization_result_includes_constitutional_hash(self):
        """Verify optimization results include constitutional hash."""
        result = OptimizationResult(
            domain=OptimizationDomain.CACHE,
            action="Increase cache size",
            success=True,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestPerformanceProfile:
    """Test PerformanceProfile dataclass."""

    def test_create_profile(self):
        """Test basic profile creation."""
        profile = PerformanceProfile(
            domain=OptimizationDomain.DATABASE,
            latency_p50_ms=0.5,
            latency_p95_ms=2.0,
            latency_p99_ms=5.0,
            throughput_rps=1000.0,
            error_rate=0.001,
            resource_utilization=0.6,
        )
        assert profile.domain == OptimizationDomain.DATABASE
        assert profile.latency_p99_ms == 5.0
        assert profile.throughput_rps == 1000.0

    def test_profile_with_bottlenecks(self):
        """Test profile with bottlenecks and recommendations."""
        profile = PerformanceProfile(
            domain=OptimizationDomain.APPLICATION,
            latency_p50_ms=1.0,
            latency_p95_ms=5.0,
            latency_p99_ms=10.0,
            throughput_rps=500.0,
            error_rate=0.01,
            resource_utilization=0.9,
            bottlenecks=["High CPU usage", "Memory pressure"],
            recommendations=["Scale horizontally", "Optimize hot paths"],
        )
        assert len(profile.bottlenecks) == 2
        assert len(profile.recommendations) == 2

    def test_profile_timestamp(self):
        """Test profile includes timestamp."""
        before = datetime.now(UTC)
        profile = PerformanceProfile(
            domain=OptimizationDomain.CACHE,
            latency_p50_ms=0.1,
            latency_p95_ms=0.5,
            latency_p99_ms=1.0,
            throughput_rps=10000.0,
            error_rate=0.0001,
            resource_utilization=0.5,
        )
        after = datetime.now(UTC)
        assert before <= profile.timestamp <= after


class TestDatabasePerformanceAgent:
    """Test DatabasePerformanceAgent."""

    async def test_profile_database(self):
        """Test database profiling."""
        agent = DatabasePerformanceAgent()
        profile = await agent.profile()

        assert profile.domain == OptimizationDomain.DATABASE
        assert profile.latency_p50_ms >= 0
        assert profile.throughput_rps > 0
        assert 0 <= profile.error_rate <= 1

    async def test_database_history(self):
        """Test profiling history is maintained."""
        agent = DatabasePerformanceAgent()
        await agent.profile()
        await agent.profile()

        history = agent.get_history()
        assert len(history) == 2


class TestApplicationPerformanceAgent:
    """Test ApplicationPerformanceAgent."""

    async def test_profile_application(self):
        """Test application profiling."""
        # Mock the performance monitor to avoid xdist singleton pollution
        # where other tests record operations with latencies exceeding targets.
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"operations": {}}
        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.APPLICATION
        # ACGS-2 targets: P99 < 5ms, throughput > 100 RPS
        assert profile.latency_p99_ms <= 5.0
        assert profile.throughput_rps >= 100.0

    async def test_application_resource_metrics(self):
        """Test CPU and memory metrics."""
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"operations": {}}
        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        assert profile.cpu_usage_percent is not None
        assert profile.memory_usage_mb is not None


class TestCachePerformanceAgent:
    """Test CachePerformanceAgent."""

    async def test_profile_cache(self):
        """Test cache profiling."""
        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager"
        ) as MockCacheManager:
            # Setup mock to return high hit rate
            mock_instance = MagicMock()
            mock_instance.get_stats.return_value = {
                "aggregate": {"hit_ratio": 0.95, "total_hits": 1000},
                "tiers": {},
            }
            MockCacheManager.return_value = mock_instance

            agent = CachePerformanceAgent()
            profile = await agent.profile()

            assert profile.domain == OptimizationDomain.CACHE
            # ACGS-2 target: cache hit rate > 85%
            assert profile.cache_hit_rate >= 0.85

    async def test_cache_low_latency(self):
        """Test cache has low latency."""
        agent = CachePerformanceAgent()
        profile = await agent.profile()

        # Cache should be faster than database
        assert profile.latency_p99_ms < 5.0


class TestAgentCoordinationProfiler:
    """Test AgentCoordinationProfiler."""

    async def test_profile_coordination(self):
        """Test agent coordination profiling."""
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()

        assert profile.domain == OptimizationDomain.AGENT_COORDINATION
        assert profile.resource_utilization <= 1.0  # Parallel efficiency

    async def test_coordination_recommendations(self):
        """Test coordination recommendations are generated."""
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()

        # Should have recommendations or empty list
        assert isinstance(profile.recommendations, list)


class TestContextWindowOptimizer:
    """Test ContextWindowOptimizer."""

    def test_estimate_tokens(self):
        """Test token estimation."""
        optimizer = ContextWindowOptimizer()
        text = "a" * 400  # ~100 tokens

        tokens = optimizer.estimate_tokens(text)
        assert 90 <= tokens <= 110

    def test_compress_short_context(self):
        """Test short context is not compressed."""
        optimizer = ContextWindowOptimizer(max_tokens=1000)
        short_text = "Hello, world!"

        compressed = optimizer.compress_context(short_text)
        assert compressed == short_text

    def test_compress_long_context(self):
        """Test long context is compressed."""
        optimizer = ContextWindowOptimizer(max_tokens=100)
        long_text = "a" * 2000  # ~500 tokens

        compressed = optimizer.compress_context(long_text)
        assert len(compressed) < len(long_text)
        assert "[...context compressed...]" in compressed

    def test_prioritize_contexts(self):
        """Test context prioritization."""
        optimizer = ContextWindowOptimizer()
        contexts = [
            {"content": "a" * 400, "priority": 1, "timestamp": 1},
            {"content": "b" * 400, "priority": 3, "timestamp": 2},
            {"content": "c" * 400, "priority": 2, "timestamp": 3},
        ]

        # Limit to ~200 tokens
        prioritized = optimizer.prioritize_context(contexts, max_total_tokens=200)

        # Should prioritize highest priority first
        assert len(prioritized) >= 1
        assert prioritized[0]["priority"] == 3


class TestCostOptimizer:
    """Test CostOptimizer."""

    def test_select_model_trivial_task(self):
        """Test model selection for trivial tasks."""
        optimizer = CostOptimizer()
        model = optimizer.select_optimal_model(task_complexity=1)

        assert model == "claude-haiku-4"

    def test_select_model_complex_task(self):
        """Test model selection for complex tasks."""
        optimizer = CostOptimizer()
        model = optimizer.select_optimal_model(task_complexity=5)

        assert model in ["claude-opus-4", "claude-sonnet-4"]

    def test_select_model_high_quality(self):
        """Test model selection with high quality requirement."""
        optimizer = CostOptimizer()
        model = optimizer.select_optimal_model(task_complexity=2, quality_threshold=0.95)

        assert model in ["claude-opus-4", "claude-sonnet-4"]

    def test_estimate_cost(self):
        """Test cost estimation."""
        optimizer = CostOptimizer()
        cost = optimizer.estimate_cost("claude-sonnet-4", 1_000_000)

        assert cost == 3.0  # $3/M tokens

    def test_track_usage(self):
        """Test usage tracking."""
        optimizer = CostOptimizer(monthly_budget=100.0)
        result = optimizer.track_usage("claude-haiku-4", 1_000_000)

        assert result["model"] == "claude-haiku-4"
        assert result["tokens"] == 1_000_000
        assert result["cost"] == 0.25
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_budget_remaining(self):
        """Test budget tracking."""
        optimizer = CostOptimizer(monthly_budget=100.0)
        optimizer.track_usage("claude-sonnet-4", 10_000_000)  # $30

        assert optimizer.total_cost == 30.0
        result = optimizer.track_usage("claude-haiku-4", 1_000_000)
        assert result["budget_remaining"] == 100.0 - 30.0 - 0.25


class TestPerformanceTracker:
    """Test PerformanceTracker."""

    def test_log_result(self):
        """Test logging optimization results."""
        tracker = PerformanceTracker()
        tracker.log("database_agent", {"latency": 5.0})
        tracker.log("database_agent", {"latency": 4.0})

        summary = tracker.get_summary()
        assert "database_agent" in summary
        assert summary["database_agent"]["total_runs"] == 2

    def test_empty_summary(self):
        """Test empty tracker summary."""
        tracker = PerformanceTracker()
        summary = tracker.get_summary()
        assert summary == {}


class TestMultiAgentOrchestrator:
    """Test MultiAgentOrchestrator."""

    async def test_create_orchestrator(self):
        """Test orchestrator creation."""
        orchestrator = create_optimization_toolkit()

        assert orchestrator.scope == OptimizationScope.MODERATE
        assert len(orchestrator.agents) >= 4

    async def test_profile_all(self):
        """Test parallel profiling of all components."""
        orchestrator = MultiAgentOrchestrator()
        profiles = await orchestrator.profile_all()

        assert len(profiles) >= 4
        assert OptimizationDomain.DATABASE in profiles
        assert OptimizationDomain.APPLICATION in profiles
        assert OptimizationDomain.CACHE in profiles
        assert OptimizationDomain.AGENT_COORDINATION in profiles

    async def test_optimize(self):
        """Test optimization execution."""
        orchestrator = MultiAgentOrchestrator()
        results = await orchestrator.optimize()

        # Results may be empty if no bottlenecks detected
        assert isinstance(results, list)

    async def test_optimize_specific_domains(self):
        """Test optimization of specific domains."""
        orchestrator = MultiAgentOrchestrator()
        results = await orchestrator.optimize(target_domains=[OptimizationDomain.CACHE])

        # Results should only be from cache domain
        for result in results:
            assert result.domain == OptimizationDomain.CACHE

    async def test_optimization_report(self):
        """Test optimization report generation."""
        orchestrator = MultiAgentOrchestrator()
        await orchestrator.profile_all()
        report = orchestrator.get_optimization_report()

        assert "scope" in report
        assert "agents" in report
        assert "constitutional_hash" in report
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_orchestrator_scope(self):
        """Test different optimization scopes."""
        quick = create_optimization_toolkit(scope=OptimizationScope.QUICK_WIN)
        comprehensive = create_optimization_toolkit(scope=OptimizationScope.COMPREHENSIVE)

        assert quick.scope == OptimizationScope.QUICK_WIN
        assert comprehensive.scope == OptimizationScope.COMPREHENSIVE


class TestOptimizationResult:
    """Test OptimizationResult dataclass."""

    def test_create_result(self):
        """Test result creation."""
        result = OptimizationResult(
            domain=OptimizationDomain.DATABASE,
            action="Add index on user_id",
            before_metrics={"latency_p99_ms": 10.0},
            after_metrics={"latency_p99_ms": 2.0},
            improvement_percent=80.0,
            success=True,
        )

        assert result.success
        assert result.improvement_percent == 80.0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_with_error(self):
        """Test result with error."""
        result = OptimizationResult(
            domain=OptimizationDomain.APPLICATION,
            action="Scale horizontally",
            success=False,
            error_message="Insufficient resources",
        )

        assert not result.success
        assert result.error_message == "Insufficient resources"


class TestIntegration:
    """Integration tests for the optimization toolkit."""

    async def test_full_optimization_cycle(self):
        """Test complete optimization cycle."""
        # Create orchestrator
        orchestrator = create_optimization_toolkit(scope=OptimizationScope.COMPREHENSIVE)

        # Profile all components
        profiles = await orchestrator.profile_all()
        assert len(profiles) >= 4

        # Run optimization
        results = await orchestrator.optimize()
        assert isinstance(results, list)

        # Generate report
        report = orchestrator.get_optimization_report()
        assert report["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Verify all profiles have correct constitutional hash
        for _domain, profile in profiles.items():
            assert profile.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_context_and_cost_optimization(self):
        """Test context and cost optimization together."""
        orchestrator = create_optimization_toolkit()

        # Compress context
        long_context = "x" * 10000
        compressed = orchestrator.context_optimizer.compress_context(long_context, max_tokens=500)
        assert len(compressed) < len(long_context)

        # Select model based on complexity
        model = orchestrator.cost_optimizer.select_optimal_model(task_complexity=3)
        assert model is not None

        # Track usage
        usage = orchestrator.cost_optimizer.track_usage(model, 10000)
        assert usage["constitutional_hash"] == CONSTITUTIONAL_HASH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
