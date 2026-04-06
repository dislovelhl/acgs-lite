# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for optimization_toolkit/agents.py
targeting ≥95% line coverage.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.optimization_toolkit.agents import (
    CONSTITUTIONAL_HASH,
    AgentCoordinationProfiler,
    ApplicationPerformanceAgent,
    CachePerformanceAgent,
    DatabasePerformanceAgent,
    FrontendPerformanceAgent,
    OptimizationDomain,
    PerformanceAgent,
    PerformanceMetrics,
    PerformanceProfile,
    PerformanceProfiler,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ConcreteProfiler(PerformanceProfiler):
    """Minimal concrete implementation of PerformanceProfiler for testing."""

    @property
    def domain(self) -> OptimizationDomain:
        return OptimizationDomain.APPLICATION

    async def profile(self) -> PerformanceProfile:
        p = PerformanceProfile(
            domain=self.domain,
            latency_p50_ms=1.0,
            latency_p95_ms=2.0,
            latency_p99_ms=3.0,
            throughput_rps=1000.0,
            error_rate=0.001,
            resource_utilization=0.5,
        )
        self._record_profile(p)
        return p


# ---------------------------------------------------------------------------
# Constitutional Hash
# ---------------------------------------------------------------------------


class TestConstitutionalHashConstant:
    def test_hash_value(self):
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_hash_in_profile_default(self):
        profile = PerformanceProfile(
            domain=OptimizationDomain.DATABASE,
            latency_p50_ms=1.0,
            latency_p95_ms=2.0,
            latency_p99_ms=3.0,
            throughput_rps=100.0,
            error_rate=0.001,
            resource_utilization=0.5,
        )
        assert profile.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# OptimizationDomain enum
# ---------------------------------------------------------------------------


class TestOptimizationDomain:
    def test_all_values(self):
        assert OptimizationDomain.DATABASE.value == "database"
        assert OptimizationDomain.APPLICATION.value == "application"
        assert OptimizationDomain.CACHE.value == "cache"
        assert OptimizationDomain.AGENT_COORDINATION.value == "agent_coordination"
        assert OptimizationDomain.NETWORK.value == "network"
        assert OptimizationDomain.ML_INFERENCE.value == "ml_inference"

    def test_enum_membership(self):
        domains = list(OptimizationDomain)
        assert len(domains) == 6


# ---------------------------------------------------------------------------
# PerformanceProfile dataclass
# ---------------------------------------------------------------------------


class TestPerformanceProfile:
    def test_minimal_creation(self):
        p = PerformanceProfile(
            domain=OptimizationDomain.CACHE,
            latency_p50_ms=0.1,
            latency_p95_ms=0.3,
            latency_p99_ms=0.8,
            throughput_rps=50000.0,
            error_rate=0.0001,
            resource_utilization=0.6,
        )
        assert p.domain == OptimizationDomain.CACHE
        assert p.latency_p50_ms == 0.1
        assert p.latency_p95_ms == 0.3
        assert p.latency_p99_ms == 0.8
        assert p.throughput_rps == 50000.0
        assert p.error_rate == 0.0001
        assert p.resource_utilization == 0.6

    def test_default_optional_fields(self):
        p = PerformanceProfile(
            domain=OptimizationDomain.APPLICATION,
            latency_p50_ms=0.5,
            latency_p95_ms=1.5,
            latency_p99_ms=3.0,
            throughput_rps=1000.0,
            error_rate=0.001,
            resource_utilization=0.4,
        )
        assert p.cpu_usage_percent is None
        assert p.memory_usage_mb is None
        assert p.cache_hit_rate is None
        assert p.custom_metrics == {}
        assert p.bottlenecks == []
        assert p.recommendations == []

    def test_optional_fields_set(self):
        p = PerformanceProfile(
            domain=OptimizationDomain.DATABASE,
            latency_p50_ms=0.5,
            latency_p95_ms=2.0,
            latency_p99_ms=4.5,
            throughput_rps=5000.0,
            error_rate=0.001,
            resource_utilization=0.45,
            cpu_usage_percent=10.0,
            memory_usage_mb=128.0,
            cache_hit_rate=0.9,
            custom_metrics={"key": "value"},
            bottlenecks=["slow query"],
            recommendations=["add index"],
        )
        assert p.cpu_usage_percent == 10.0
        assert p.memory_usage_mb == 128.0
        assert p.cache_hit_rate == 0.9
        assert p.custom_metrics == {"key": "value"}
        assert p.bottlenecks == ["slow query"]
        assert p.recommendations == ["add index"]

    def test_timestamp_is_utc(self):
        before = datetime.now(UTC)
        p = PerformanceProfile(
            domain=OptimizationDomain.NETWORK,
            latency_p50_ms=100.0,
            latency_p95_ms=200.0,
            latency_p99_ms=300.0,
            throughput_rps=100.0,
            error_rate=0.02,
            resource_utilization=0.3,
        )
        after = datetime.now(UTC)
        assert before <= p.timestamp <= after

    def test_constitutional_hash_default(self):
        p = PerformanceProfile(
            domain=OptimizationDomain.ML_INFERENCE,
            latency_p50_ms=10.0,
            latency_p95_ms=50.0,
            latency_p99_ms=100.0,
            throughput_rps=10.0,
            error_rate=0.005,
            resource_utilization=0.8,
        )
        assert p.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_constitutional_hash(self):
        p = PerformanceProfile(
            domain=OptimizationDomain.APPLICATION,
            latency_p50_ms=1.0,
            latency_p95_ms=2.0,
            latency_p99_ms=3.0,
            throughput_rps=1000.0,
            error_rate=0.001,
            resource_utilization=0.5,
            constitutional_hash="custom-hash-for-test",
        )
        assert p.constitutional_hash == "custom-hash-for-test"

    def test_as_dict(self):
        p = PerformanceProfile(
            domain=OptimizationDomain.DATABASE,
            latency_p50_ms=0.5,
            latency_p95_ms=2.0,
            latency_p99_ms=4.5,
            throughput_rps=5000.0,
            error_rate=0.001,
            resource_utilization=0.45,
        )
        d = asdict(p)
        assert d["domain"] == OptimizationDomain.DATABASE
        assert "constitutional_hash" in d


# ---------------------------------------------------------------------------
# PerformanceMetrics (legacy)
# ---------------------------------------------------------------------------


class TestPerformanceMetrics:
    def test_create(self):
        m = PerformanceMetrics(
            latency_ms=5.0,
            cpu_usage_percent=20.0,
            memory_usage_mb=512.0,
            throughput_rps=1000.0,
            error_rate=0.01,
        )
        assert m.latency_ms == 5.0
        assert m.cpu_usage_percent == 20.0
        assert m.memory_usage_mb == 512.0
        assert m.throughput_rps == 1000.0
        assert m.error_rate == 0.01
        assert m.custom_metrics == {}

    def test_create_with_custom_metrics(self):
        m = PerformanceMetrics(
            latency_ms=1.0,
            cpu_usage_percent=5.0,
            memory_usage_mb=256.0,
            throughput_rps=5000.0,
            error_rate=0.0001,
            custom_metrics={"pool_size": 10},
        )
        assert m.custom_metrics == {"pool_size": 10}


# ---------------------------------------------------------------------------
# PerformanceProfiler (abstract base / concrete)
# ---------------------------------------------------------------------------


class TestPerformanceProfilerBase:
    def test_get_history_empty_initially(self):
        profiler = ConcreteProfiler()
        assert profiler.get_history() == []

    async def test_record_profile_appends(self):
        profiler = ConcreteProfiler()
        await profiler.profile()
        history = profiler.get_history()
        assert len(history) == 1

    async def test_record_profile_multiple(self):
        profiler = ConcreteProfiler()
        await profiler.profile()
        await profiler.profile()
        await profiler.profile()
        history = profiler.get_history()
        assert len(history) == 3

    def test_get_history_returns_copy(self):
        profiler = ConcreteProfiler()
        h1 = profiler.get_history()
        h2 = profiler.get_history()
        assert h1 is not h2

    async def test_get_history_after_profile(self):
        profiler = ConcreteProfiler()
        p = await profiler.profile()
        history = profiler.get_history()
        assert history[0] is p

    def test_domain_property(self):
        profiler = ConcreteProfiler()
        assert profiler.domain == OptimizationDomain.APPLICATION

    def test_performance_agent_alias(self):
        assert PerformanceAgent is PerformanceProfiler


# ---------------------------------------------------------------------------
# DatabasePerformanceAgent
# ---------------------------------------------------------------------------


class TestDatabasePerformanceAgentInit:
    def test_default_target_system(self):
        agent = DatabasePerformanceAgent()
        assert agent.target_system == "postgresql"

    def test_custom_target_system(self):
        agent = DatabasePerformanceAgent(target_system="mysql")
        assert agent.target_system == "mysql"

    def test_domain(self):
        agent = DatabasePerformanceAgent()
        assert agent.domain == OptimizationDomain.DATABASE

    def test_initial_history_empty(self):
        agent = DatabasePerformanceAgent()
        assert agent.get_history() == []


class TestDatabasePerformanceAgentProfile:
    """Test DatabasePerformanceAgent.profile() — both paths."""

    async def test_profile_fallback_when_no_engine(self):
        """When engine import fails, uses fallback values."""
        with patch.dict("sys.modules", {"enhanced_agent_bus._compat.database.session": None}):
            agent = DatabasePerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.DATABASE
        assert profile.latency_p50_ms == 0.5
        assert profile.latency_p95_ms == 2.0
        assert profile.latency_p99_ms == 4.5
        assert profile.throughput_rps == 5000.0
        assert profile.error_rate == 0.001
        assert profile.resource_utilization == 0.45
        assert profile.cpu_usage_percent == 10.0
        assert profile.memory_usage_mb == 128.0
        assert "simulated" in profile.custom_metrics
        assert profile.custom_metrics["simulated"] is True

    async def test_profile_fallback_records_error(self):
        """Fallback path records the exception message."""
        with patch.dict("sys.modules", {"enhanced_agent_bus._compat.database.session": None}):
            agent = DatabasePerformanceAgent()
            profile = await agent.profile()

        assert "error" in profile.custom_metrics

    async def test_profile_fallback_recorded_in_history(self):
        with patch.dict("sys.modules", {"enhanced_agent_bus._compat.database.session": None}):
            agent = DatabasePerformanceAgent()
            profile = await agent.profile()

        assert len(agent.get_history()) == 1
        assert agent.get_history()[0] is profile

    async def test_profile_success_path_with_pool_stats(self):
        """Test successful path when SQLAlchemy engine is available."""
        mock_pool = MagicMock()
        mock_pool.size.return_value = 10
        mock_pool.checkedin.return_value = 7
        mock_pool.checkedout.return_value = 3
        mock_pool.overflow.return_value = 0

        mock_engine = MagicMock()
        mock_engine.pool = mock_pool

        mock_session_module = MagicMock()
        mock_session_module.engine = mock_engine

        with patch.dict(
            "sys.modules",
            {"enhanced_agent_bus._compat.database.session": mock_session_module},
        ):
            agent = DatabasePerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.DATABASE
        assert profile.latency_p50_ms == 0.5
        assert profile.latency_p95_ms == 2.0
        assert profile.latency_p99_ms == 4.5
        assert profile.throughput_rps == 5000.0
        assert profile.error_rate == 0.001
        # utilization = 3 / 10 = 0.3
        assert profile.resource_utilization == pytest.approx(0.3)
        assert profile.custom_metrics["real_pool_metrics"] is True
        assert profile.custom_metrics["simulated_latency"] is True
        pool_stats = profile.custom_metrics["pool_stats"]
        assert pool_stats["size"] == 10
        assert pool_stats["checkedin"] == 7
        assert pool_stats["checkedout"] == 3
        assert pool_stats["overflow"] == 0

    async def test_profile_success_path_zero_pool_size(self):
        """When pool size is 0, utilization should be 0.0."""
        mock_pool = MagicMock()
        mock_pool.size.return_value = 0
        mock_pool.checkedin.return_value = 0
        mock_pool.checkedout.return_value = 0
        mock_pool.overflow.return_value = 0

        mock_engine = MagicMock()
        mock_engine.pool = mock_pool

        mock_session_module = MagicMock()
        mock_session_module.engine = mock_engine

        with patch.dict(
            "sys.modules",
            {"enhanced_agent_bus._compat.database.session": mock_session_module},
        ):
            agent = DatabasePerformanceAgent()
            profile = await agent.profile()

        assert profile.resource_utilization == 0.0

    async def test_profile_pool_without_size_method(self):
        """When pool lacks size/checkedout methods, defaults to 0."""
        mock_pool = MagicMock(spec=[])  # no attributes
        mock_engine = MagicMock()
        mock_engine.pool = mock_pool

        mock_session_module = MagicMock()
        mock_session_module.engine = mock_engine

        with patch.dict(
            "sys.modules",
            {"enhanced_agent_bus._compat.database.session": mock_session_module},
        ):
            agent = DatabasePerformanceAgent()
            profile = await agent.profile()

        # size == 0, so utilization == 0.0
        assert profile.resource_utilization == 0.0
        pool_stats = profile.custom_metrics["pool_stats"]
        assert pool_stats["size"] == 0
        assert pool_stats["checkedin"] == 0
        assert pool_stats["checkedout"] == 0
        assert pool_stats["overflow"] == 0

    async def test_profile_success_recorded_in_history(self):
        mock_pool = MagicMock()
        mock_pool.size.return_value = 5
        mock_pool.checkedin.return_value = 2
        mock_pool.checkedout.return_value = 3
        mock_pool.overflow.return_value = 0

        mock_engine = MagicMock()
        mock_engine.pool = mock_pool

        mock_session_module = MagicMock()
        mock_session_module.engine = mock_engine

        with patch.dict(
            "sys.modules",
            {"enhanced_agent_bus._compat.database.session": mock_session_module},
        ):
            agent = DatabasePerformanceAgent()
            profile = await agent.profile()

        assert len(agent.get_history()) == 1
        assert agent.get_history()[0] is profile

    async def test_profile_multiple_calls_accumulate_history(self):
        with patch.dict("sys.modules", {"enhanced_agent_bus._compat.database.session": None}):
            agent = DatabasePerformanceAgent()
            await agent.profile()
            await agent.profile()

        assert len(agent.get_history()) == 2


# ---------------------------------------------------------------------------
# ApplicationPerformanceAgent
# ---------------------------------------------------------------------------


class TestApplicationPerformanceAgentInit:
    def test_default_target_system(self):
        agent = ApplicationPerformanceAgent()
        assert agent.target_system == "acgs2"

    def test_custom_target_system(self):
        agent = ApplicationPerformanceAgent(target_system="custom")
        assert agent.target_system == "custom"

    def test_domain(self):
        agent = ApplicationPerformanceAgent()
        assert agent.domain == OptimizationDomain.APPLICATION


class TestApplicationPerformanceAgentProfile:
    async def test_profile_fallback_when_no_op_metrics(self):
        """When no message_process ops, uses simulated fallback."""
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"operations": {}}

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.APPLICATION
        assert profile.latency_p50_ms == 0.5
        assert profile.latency_p95_ms == 1.5
        assert profile.latency_p99_ms == 3.25
        assert profile.throughput_rps == 6471.0
        assert profile.error_rate == 0.001
        assert profile.resource_utilization == 0.35
        assert profile.cpu_usage_percent == 15.0
        assert profile.memory_usage_mb == 256.0
        assert profile.custom_metrics["simulated"] is True

    async def test_profile_fallback_recorded_in_history(self):
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"operations": {}}

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        assert len(agent.get_history()) == 1
        assert agent.get_history()[0] is profile

    async def test_profile_real_metrics_path(self):
        """When op_metrics exist, uses real data."""
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {
            "timestamp": 100.0,
            "operations": {
                "message_process": {
                    "count": 1000,
                    "last_updated": 90.0,
                    "p50_ms": 0.4,
                    "p95_ms": 1.2,
                    "p99_ms": 2.8,
                    "error_rate": 0.5,  # 0.5% → 0.005
                }
            },
        }

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.APPLICATION
        assert profile.latency_p50_ms == 0.4
        assert profile.latency_p95_ms == 1.2
        assert profile.latency_p99_ms == 2.8
        assert profile.error_rate == pytest.approx(0.005)
        assert profile.custom_metrics["simulated"] is False
        assert profile.custom_metrics["real_monitor"] is True
        assert profile.custom_metrics["total_count"] == 1000

    async def test_profile_real_metrics_throughput_computed(self):
        """Throughput is computed from count/elapsed, floored at 100."""
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {
            "timestamp": 200.0,
            "operations": {
                "message_process": {
                    "count": 500,
                    "last_updated": 100.0,  # elapsed = 100s
                    "p50_ms": 0.5,
                    "p95_ms": 1.5,
                    "p99_ms": 3.0,
                    "error_rate": 0.0,
                }
            },
        }

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        # throughput = 500 / 100 = 5.0, but floored at 100.0
        assert profile.throughput_rps == pytest.approx(100.0)

    async def test_profile_real_metrics_throughput_high(self):
        """High throughput case."""
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {
            "timestamp": 110.0,
            "operations": {
                "message_process": {
                    "count": 50000,
                    "last_updated": 100.0,  # elapsed = 10s
                    "p50_ms": 0.5,
                    "p95_ms": 1.5,
                    "p99_ms": 3.0,
                    "error_rate": 0.0,
                }
            },
        }

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        # 50000 / 10 = 5000, max(5000, 100) = 5000
        assert profile.throughput_rps == pytest.approx(5000.0)

    async def test_profile_real_metrics_zero_count_uses_default_throughput(self):
        """When count=0 elapsed>0, throughput defaults to 6471.0."""
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {
            "timestamp": 200.0,
            "operations": {
                "message_process": {
                    "count": 0,
                    "last_updated": 100.0,
                    "p50_ms": 0.5,
                    "p95_ms": 1.5,
                    "p99_ms": 3.0,
                    "error_rate": 0.0,
                }
            },
        }

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        # count == 0 → throughput = 6471.0; max(6471.0, 100) = 6471.0
        assert profile.throughput_rps == pytest.approx(6471.0)

    async def test_profile_real_metrics_recorded_in_history(self):
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {
            "timestamp": 100.0,
            "operations": {
                "message_process": {
                    "count": 100,
                    "last_updated": 90.0,
                    "p50_ms": 0.5,
                    "p95_ms": 1.5,
                    "p99_ms": 3.0,
                    "error_rate": 0.0,
                }
            },
        }

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        assert len(agent.get_history()) == 1
        assert agent.get_history()[0] is profile

    async def test_profile_with_missing_optional_monitor_keys(self):
        """Handle missing optional keys gracefully via .get() defaults."""
        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {
            "operations": {
                "message_process": {
                    "count": 10,
                    # no timestamp, no last_updated, no p50_ms etc.
                }
            },
        }

        with patch(
            "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
            return_value=mock_monitor,
        ):
            agent = ApplicationPerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.APPLICATION
        # Falls back to default p50/p95/p99 values via .get()
        assert profile.latency_p50_ms == 0.5
        assert profile.latency_p95_ms == 1.5
        assert profile.latency_p99_ms == 3.25


# ---------------------------------------------------------------------------
# CachePerformanceAgent
# ---------------------------------------------------------------------------


class TestCachePerformanceAgentInit:
    def test_default_target_system(self):
        agent = CachePerformanceAgent()
        assert agent.target_system == "redis"

    def test_custom_target_system(self):
        agent = CachePerformanceAgent(target_system="memcached")
        assert agent.target_system == "memcached"

    def test_domain(self):
        agent = CachePerformanceAgent()
        assert agent.domain == OptimizationDomain.CACHE


class TestCachePerformanceAgentProfile:
    async def test_profile_success_path(self):
        """Test CachePerformanceAgent successful path."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_stats.return_value = {
            "aggregate": {
                "hit_ratio": 0.97,
                "total_hits": 9700,
            },
            "tiers": {"l1": {}, "l2": {}},
        }

        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.CACHE
        assert profile.latency_p50_ms == 0.1
        assert profile.latency_p95_ms == 0.3
        assert profile.latency_p99_ms == 0.8
        assert profile.throughput_rps == 50000.0
        assert profile.error_rate == 0.0001
        assert profile.resource_utilization == 0.6
        assert profile.cache_hit_rate == pytest.approx(0.97)
        assert profile.cpu_usage_percent == 5.0
        assert profile.memory_usage_mb is None
        assert profile.custom_metrics["simulated"] is False
        assert profile.custom_metrics["real_cache_manager"] is True
        assert profile.custom_metrics["total_hits"] == 9700

    async def test_profile_success_tier_stats_captured(self):
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_stats.return_value = {
            "aggregate": {
                "hit_ratio": 0.9,
                "total_hits": 900,
            },
            "tiers": {"l1": {"hits": 800}, "l2": {"hits": 100}},
        }

        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            profile = await agent.profile()

        assert profile.custom_metrics["tier_stats"] == {"l1": {"hits": 800}, "l2": {"hits": 100}}

    async def test_profile_success_recorded_in_history(self):
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_stats.return_value = {
            "aggregate": {"hit_ratio": 0.95, "total_hits": 500},
            "tiers": {},
        }
        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            profile = await agent.profile()

        assert len(agent.get_history()) == 1
        assert agent.get_history()[0] is profile

    async def test_profile_fallback_when_exception(self):
        """Test fallback when TieredCacheManager raises."""
        mock_manager_cls = MagicMock(side_effect=RuntimeError("cache unavailable"))

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            profile = await agent.profile()

        assert profile.domain == OptimizationDomain.CACHE
        assert profile.latency_p50_ms == 0.1
        assert profile.latency_p95_ms == 0.3
        assert profile.latency_p99_ms == 0.8
        assert profile.throughput_rps == 50000.0
        assert profile.error_rate == 0.0001
        assert profile.resource_utilization == 0.6
        assert profile.cache_hit_rate == 0.95
        assert profile.custom_metrics["simulated"] is True
        assert "error" in profile.custom_metrics
        assert "cache unavailable" in profile.custom_metrics["error"]

    async def test_profile_fallback_recorded_in_history(self):
        mock_manager_cls = MagicMock(side_effect=Exception("fail"))

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            profile = await agent.profile()

        assert len(agent.get_history()) == 1
        assert agent.get_history()[0] is profile

    async def test_profile_fallback_on_get_stats_exception(self):
        """Test fallback when get_stats raises."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_stats.side_effect = ValueError("stats error")
        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            profile = await agent.profile()

        assert profile.custom_metrics["simulated"] is True
        assert "stats error" in profile.custom_metrics["error"]

    async def test_profile_success_zero_hit_ratio(self):
        """Edge case: aggregate hit_ratio is 0."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_stats.return_value = {
            "aggregate": {"hit_ratio": 0.0, "total_hits": 0},
            "tiers": {},
        }
        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            profile = await agent.profile()

        assert profile.cache_hit_rate == 0.0

    async def test_profile_created_with_name_bus_validation(self):
        """Verify TieredCacheManager instantiated with 'bus_validation'."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_stats.return_value = {
            "aggregate": {"hit_ratio": 0.9, "total_hits": 100},
            "tiers": {},
        }
        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        with patch(
            "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
            mock_manager_cls,
        ):
            agent = CachePerformanceAgent()
            await agent.profile()

        mock_manager_cls.assert_called_once_with(name="bus_validation")


# ---------------------------------------------------------------------------
# AgentCoordinationProfiler
# ---------------------------------------------------------------------------


class TestAgentCoordinationProfilerInit:
    def test_domain(self):
        agent = AgentCoordinationProfiler()
        assert agent.domain == OptimizationDomain.AGENT_COORDINATION

    def test_initial_history_empty(self):
        agent = AgentCoordinationProfiler()
        assert agent.get_history() == []


class TestAgentCoordinationProfilerProfile:
    async def test_profile_returns_correct_domain(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.domain == OptimizationDomain.AGENT_COORDINATION

    async def test_profile_latency_values(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.latency_p50_ms == 2.0
        assert profile.latency_p95_ms == 8.0
        assert profile.latency_p99_ms == 15.0

    async def test_profile_throughput(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.throughput_rps == 500.0

    async def test_profile_error_rate(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.error_rate == 0.002

    async def test_profile_resource_utilization(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.resource_utilization == 0.85

    async def test_profile_cpu_and_memory(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.cpu_usage_percent == 30.0
        assert profile.memory_usage_mb == 384.0

    async def test_profile_custom_metrics(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.custom_metrics["parallel_efficiency"] == 0.85
        assert profile.custom_metrics["coordination_overhead_ms"] == 1.5
        assert profile.custom_metrics["message_queue_depth"] == 10
        assert profile.custom_metrics["active_agents"] == 8

    async def test_profile_bottlenecks_and_recommendations_empty(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.bottlenecks == []
        assert profile.recommendations == []

    async def test_profile_recorded_in_history(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        history = agent.get_history()
        assert len(history) == 1
        assert history[0] is profile

    async def test_profile_multiple_calls(self):
        agent = AgentCoordinationProfiler()
        p1 = await agent.profile()
        p2 = await agent.profile()
        history = agent.get_history()
        assert len(history) == 2
        assert history[0] is p1
        assert history[1] is p2

    async def test_profile_constitutional_hash(self):
        agent = AgentCoordinationProfiler()
        profile = await agent.profile()
        assert profile.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_profile_uses_asyncio_sleep(self):
        """asyncio.sleep(0.001) is called — verify it yields."""
        agent = AgentCoordinationProfiler()
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            profile = await agent.profile()
        mock_sleep.assert_called_once_with(0.001)
        assert profile is not None


# ---------------------------------------------------------------------------
# FrontendPerformanceAgent
# ---------------------------------------------------------------------------


class TestFrontendPerformanceAgentInit:
    def test_default_target_system(self):
        agent = FrontendPerformanceAgent()
        assert agent.target_system == "folo"

    def test_custom_target_system(self):
        agent = FrontendPerformanceAgent(target_system="react")
        assert agent.target_system == "react"

    def test_domain(self):
        agent = FrontendPerformanceAgent()
        assert agent.domain == OptimizationDomain.NETWORK

    def test_initial_history_empty(self):
        agent = FrontendPerformanceAgent()
        assert agent.get_history() == []


class TestFrontendPerformanceAgentProfile:
    async def test_profile_returns_network_domain(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.domain == OptimizationDomain.NETWORK

    async def test_profile_latency_values(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.latency_p50_ms == 100.0
        assert profile.latency_p95_ms == 180.0
        assert profile.latency_p99_ms == 250.0

    async def test_profile_throughput(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.throughput_rps == 100.0

    async def test_profile_error_rate(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.error_rate == 0.02

    async def test_profile_resource_utilization(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.resource_utilization == 0.3

    async def test_profile_cpu_and_memory(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.cpu_usage_percent == 10.0
        assert profile.memory_usage_mb == 64.0

    async def test_profile_custom_metrics(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.custom_metrics["lcp_ms"] == 1200
        assert profile.custom_metrics["fid_ms"] == 50
        assert profile.custom_metrics["cls_score"] == 0.05
        assert profile.custom_metrics["network_request_overhead_ms"] == 45.0

    async def test_profile_bottlenecks_and_recommendations_empty(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.bottlenecks == []
        assert profile.recommendations == []

    async def test_profile_recorded_in_history(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        history = agent.get_history()
        assert len(history) == 1
        assert history[0] is profile

    async def test_profile_multiple_calls(self):
        agent = FrontendPerformanceAgent()
        p1 = await agent.profile()
        p2 = await agent.profile()
        history = agent.get_history()
        assert len(history) == 2
        assert history[0] is p1
        assert history[1] is p2

    async def test_profile_constitutional_hash(self):
        agent = FrontendPerformanceAgent()
        profile = await agent.profile()
        assert profile.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_profile_uses_asyncio_sleep(self):
        """asyncio.sleep(0.001) is called."""
        agent = FrontendPerformanceAgent()
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            profile = await agent.profile()
        mock_sleep.assert_called_once_with(0.001)
        assert profile is not None


# ---------------------------------------------------------------------------
# PerformanceAgent alias
# ---------------------------------------------------------------------------


class TestPerformanceAgentAlias:
    def test_alias_is_same_as_profiler(self):
        assert PerformanceAgent is PerformanceProfiler

    def test_concrete_subclass_works_with_alias(self):
        class MyAgent(PerformanceAgent):
            @property
            def domain(self):
                return OptimizationDomain.ML_INFERENCE

            async def profile(self):
                p = PerformanceProfile(
                    domain=self.domain,
                    latency_p50_ms=10.0,
                    latency_p95_ms=50.0,
                    latency_p99_ms=100.0,
                    throughput_rps=10.0,
                    error_rate=0.005,
                    resource_utilization=0.8,
                )
                self._record_profile(p)
                return p

        agent = MyAgent()
        assert agent.domain == OptimizationDomain.ML_INFERENCE


# ---------------------------------------------------------------------------
# Import-level coverage (module-level constants)
# ---------------------------------------------------------------------------


class TestModuleLevelImports:
    def test_constitutional_hash_imported_from_shared(self):
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as shared_hash

        assert CONSTITUTIONAL_HASH == shared_hash

    def test_all_classes_importable(self):
        # Simply importing them is sufficient
        assert DatabasePerformanceAgent is not None
        assert ApplicationPerformanceAgent is not None
        assert CachePerformanceAgent is not None
        assert AgentCoordinationProfiler is not None
        assert FrontendPerformanceAgent is not None
        assert PerformanceProfiler is not None
        assert PerformanceMetrics is not None
        assert PerformanceProfile is not None
        assert OptimizationDomain is not None


# ---------------------------------------------------------------------------
# Cross-cutting: concurrent profiling
# ---------------------------------------------------------------------------


class TestConcurrentProfiling:
    async def test_agents_can_run_concurrently(self):
        """All agents profile concurrently without errors."""
        coord_agent = AgentCoordinationProfiler()
        frontend_agent = FrontendPerformanceAgent()

        mock_monitor = MagicMock()
        mock_monitor.get_metrics.return_value = {"operations": {}}

        mock_manager_instance = MagicMock()
        mock_manager_instance.get_stats.return_value = {
            "aggregate": {"hit_ratio": 0.9, "total_hits": 100},
            "tiers": {},
        }
        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        with (
            patch(
                "packages.enhanced_agent_bus.performance_monitor.get_performance_monitor",
                return_value=mock_monitor,
            ),
            patch(
                "enhanced_agent_bus._compat.cache.manager.TieredCacheManager",
                mock_manager_cls,
            ),
            patch.dict("sys.modules", {"enhanced_agent_bus._compat.database.session": None}),
        ):
            db_agent = DatabasePerformanceAgent()
            app_agent = ApplicationPerformanceAgent()
            cache_agent = CachePerformanceAgent()

            profiles = await asyncio.gather(
                db_agent.profile(),
                app_agent.profile(),
                cache_agent.profile(),
                coord_agent.profile(),
                frontend_agent.profile(),
            )

        assert len(profiles) == 5
        domains = {p.domain for p in profiles}
        assert OptimizationDomain.DATABASE in domains
        assert OptimizationDomain.APPLICATION in domains
        assert OptimizationDomain.CACHE in domains
        assert OptimizationDomain.AGENT_COORDINATION in domains
        assert OptimizationDomain.NETWORK in domains
