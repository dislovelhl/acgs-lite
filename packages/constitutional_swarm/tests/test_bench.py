"""Tests for Benchmark Harness — swarm governance overhead measurement."""

from __future__ import annotations

import pytest
from constitutional_swarm.bench import BenchmarkResult, SwarmBenchmark, _build_synthetic_spec


class TestSyntheticSpec:
    """Test synthetic DAG generation."""

    def test_spec_dimensions(self) -> None:
        spec = _build_synthetic_spec(num_domains=4, dag_depth=3, dag_width=5)
        assert len(spec.steps) == 15  # 3 * 5
        assert len(spec.domains) == 4

    def test_spec_root_tasks_have_no_deps(self) -> None:
        spec = _build_synthetic_spec(num_domains=2, dag_depth=3, dag_width=4)
        root_steps = [s for s in spec.steps if s["title"].startswith("L0-")]
        assert all(len(s["depends_on"]) == 0 for s in root_steps)


class TestSwarmBenchmark:
    """Test the benchmark harness."""

    def test_small_run_completes(self) -> None:
        bench = SwarmBenchmark()
        result = bench.run(num_agents=10, num_domains=2, dag_depth=2, dag_width=3)
        assert isinstance(result, BenchmarkResult)
        assert result.num_agents == 10
        assert result.num_domains == 2
        assert result.num_tasks == 6  # 2 * 3
        assert result.dag_depth == 2

    def test_result_structure(self) -> None:
        bench = SwarmBenchmark()
        result = bench.run(num_agents=5, num_domains=2, dag_depth=2, dag_width=3)
        assert result.total_time_ms > 0
        assert result.avg_validation_ns > 0
        assert 0.0 <= result.coordination_overhead <= 1.0
        assert 0.0 <= result.agent_utilization <= 1.0

    def test_throughput_positive(self) -> None:
        bench = SwarmBenchmark()
        result = bench.run(num_agents=10, num_domains=2, dag_depth=2, dag_width=5)
        assert result.throughput_tasks_per_sec > 0

    def test_utilization_positive(self) -> None:
        bench = SwarmBenchmark()
        result = bench.run(num_agents=4, num_domains=2, dag_depth=2, dag_width=4)
        assert result.agent_utilization > 0

    def test_scaling_report(self) -> None:
        bench = SwarmBenchmark()
        results = bench.scaling_report(
            sizes=[5, 10],
            num_domains=2,
            dag_depth=2,
            dag_width=3,
        )
        assert len(results) == 2
        assert results[0].num_agents == 5
        assert results[1].num_agents == 10

    @pytest.mark.slow
    def test_100_agent_benchmark(self) -> None:
        bench = SwarmBenchmark()
        result = bench.run(num_agents=100, num_domains=10, dag_depth=5, dag_width=20)
        assert result.num_tasks == 100
        assert result.throughput_tasks_per_sec > 0
        assert result.total_time_ms < 30_000  # must complete in 30s

    @pytest.mark.slow
    def test_800_agent_benchmark_under_10s(self) -> None:
        bench = SwarmBenchmark()
        result = bench.run(num_agents=800, num_domains=10, dag_depth=5, dag_width=20)
        assert result.num_tasks == 100
        assert result.total_time_ms < 10_000, (
            f"800-agent benchmark took {result.total_time_ms:.0f}ms, must be under 10s"
        )
        assert result.throughput_tasks_per_sec > 0

    @pytest.mark.slow
    def test_scaling_linearity(self) -> None:
        """Governance overhead should scale O(N), not O(N^2).

        If we 10x the agents, the time should grow by less than 20x
        (allowing generous overhead for scheduling).
        """
        bench = SwarmBenchmark()
        small = bench.run(num_agents=10, num_domains=4, dag_depth=3, dag_width=5)
        large = bench.run(num_agents=100, num_domains=4, dag_depth=3, dag_width=5)

        ratio = large.total_time_ms / small.total_time_ms if small.total_time_ms > 0 else 0
        assert ratio < 20, (
            f"Scaling ratio {ratio:.1f}x for 10x agents — suggests O(N^2) overhead"
        )
