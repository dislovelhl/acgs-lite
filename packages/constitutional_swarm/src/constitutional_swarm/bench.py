"""Benchmark Harness — measures swarm governance overhead at scale.

Creates synthetic DAGs, registers N agents across M domains, and runs
SwarmExecutor to completion. Measures coordination overhead, agent
utilization, and throughput to prove governance scales O(N), not O(N^2).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.compiler import DAGCompiler, GoalSpec
from constitutional_swarm.dna import AgentDNA
from constitutional_swarm.swarm import NodeStatus, SwarmExecutor


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Metrics from a benchmark run.

    Attributes:
        total_time_ms: Wall-clock time for the entire benchmark.
        avg_validation_ns: Average DNA validation latency in nanoseconds.
        coordination_overhead: Ratio of coordination time vs total time.
        throughput_tasks_per_sec: Tasks completed per second.
        agent_utilization: Fraction of time agents are doing work vs waiting.
        num_agents: Number of agents in the benchmark.
        num_domains: Number of domains.
        num_tasks: Total number of tasks in the DAG.
        dag_depth: Depth of the synthetic DAG.
    """

    total_time_ms: float
    avg_validation_ns: float
    coordination_overhead: float
    throughput_tasks_per_sec: float
    agent_utilization: float
    num_agents: int
    num_domains: int
    num_tasks: int
    dag_depth: int


def _build_synthetic_spec(
    num_domains: int,
    dag_depth: int,
    dag_width: int,
) -> GoalSpec:
    """Build a synthetic GoalSpec with layered dependencies.

    Creates a DAG with `dag_depth` levels, each containing `dag_width` tasks.
    Tasks at level N depend on all tasks at level N-1.
    """
    domains = [f"domain-{i}" for i in range(num_domains)]
    steps: list[dict[str, Any]] = []

    for level in range(dag_depth):
        for task_idx in range(dag_width):
            title = f"L{level}-T{task_idx}"
            domain = domains[task_idx % num_domains]
            deps: list[str] = []
            if level > 0:
                # Depend on a subset of previous level to avoid O(N^2) deps
                # Each task depends on its corresponding task in the previous level
                prev_idx = task_idx % dag_width
                deps = [f"L{level - 1}-T{prev_idx}"]
            steps.append({
                "title": title,
                "domain": domain,
                "depends_on": deps,
            })

    return GoalSpec(
        goal=f"Synthetic benchmark: {dag_depth}x{dag_width}",
        domains=domains,
        steps=steps,
    )


def _register_agents(
    registry: CapabilityRegistry,
    num_agents: int,
    num_domains: int,
) -> list[str]:
    """Register N agents with capabilities spread across M domains."""
    domains = [f"domain-{i}" for i in range(num_domains)]
    agent_ids: list[str] = []
    for i in range(num_agents):
        agent_id = f"agent-{i:04d}"
        domain = domains[i % num_domains]
        registry.register(
            agent_id,
            [Capability(name=f"work-{domain}", domain=domain)],
        )
        agent_ids.append(agent_id)
    return agent_ids


class SwarmBenchmark:
    """Benchmark harness for measuring swarm governance overhead.

    Usage:
        bench = SwarmBenchmark()
        result = bench.run(num_agents=100, num_domains=10, dag_depth=5, dag_width=20)
        report = bench.scaling_report(sizes=[10, 100, 800])
    """

    def run(
        self,
        num_agents: int = 10,
        num_domains: int = 4,
        dag_depth: int = 3,
        dag_width: int = 5,
    ) -> BenchmarkResult:
        """Run a benchmark with synthetic DAG and agents.

        Creates a layered DAG, registers agents, and runs SwarmExecutor
        to completion. Agents claim one task at a time, "execute" instantly
        (zero-cost work), and submit artifacts. DNA validation runs on each
        submit cycle.

        Returns:
            BenchmarkResult with timing and utilization metrics.
        """
        num_tasks = dag_depth * dag_width

        # Build synthetic DAG
        compiler = DAGCompiler()
        spec = _build_synthetic_spec(num_domains, dag_depth, dag_width)
        dag = compiler.compile(spec)

        # Register agents
        registry = CapabilityRegistry()
        agent_ids = _register_agents(registry, num_agents, num_domains)

        # Create a single shared DNA for validation measurement
        dna = AgentDNA.default(agent_id="bench-dna")

        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)
        executor.load_dag(dag)

        # Track timing
        total_validation_ns = 0
        validation_count = 0
        total_work_time_ns = 0
        total_idle_time_ns = 0

        start_ns = time.perf_counter_ns()

        # Simulation loop: round-robin agents claiming available tasks
        max_iterations = num_tasks * num_agents + num_tasks * 10
        iteration = 0

        while not executor.is_complete and iteration < max_iterations:
            iteration += 1
            any_claimed = False

            for agent_id in agent_ids:
                if executor.is_complete:
                    break

                idle_start = time.perf_counter_ns()
                tasks = executor.available_tasks(agent_id)
                idle_end = time.perf_counter_ns()
                total_idle_time_ns += idle_end - idle_start

                if not tasks:
                    continue

                task = tasks[0]
                any_claimed = True

                # Claim
                work_start = time.perf_counter_ns()
                executor.claim(task.node_id, agent_id)

                # DNA validation (the governance overhead we measure)
                val_start = time.perf_counter_ns()
                dna.validate(f"execute task {task.title}")
                val_end = time.perf_counter_ns()
                total_validation_ns += val_end - val_start
                validation_count += 1

                # Submit artifact (zero-cost work simulation)
                executor.submit(
                    task.node_id,
                    Artifact(
                        artifact_id=f"art-{task.node_id}",
                        task_id=task.node_id,
                        agent_id=agent_id,
                        content_type="benchmark",
                        content=f"result-{task.node_id}",
                        domain=task.domain,
                        constitutional_hash=dna.hash,
                    ),
                )
                work_end = time.perf_counter_ns()
                total_work_time_ns += work_end - work_start

            if not any_claimed and not executor.is_complete:
                break

        elapsed_ns = time.perf_counter_ns() - start_ns
        total_time_ms = elapsed_ns / 1_000_000

        avg_validation_ns = (
            total_validation_ns / validation_count if validation_count > 0 else 0.0
        )

        throughput = (
            (num_tasks / (total_time_ms / 1000)) if total_time_ms > 0 else 0.0
        )

        total_possible_ns = elapsed_ns * num_agents if elapsed_ns > 0 else 1
        agent_utilization = min(
            total_work_time_ns / total_possible_ns, 1.0
        ) if total_possible_ns > 0 else 0.0

        coordination_overhead = (
            (elapsed_ns - total_work_time_ns) / elapsed_ns
            if elapsed_ns > 0
            else 0.0
        )
        coordination_overhead = max(0.0, min(1.0, coordination_overhead))

        return BenchmarkResult(
            total_time_ms=total_time_ms,
            avg_validation_ns=avg_validation_ns,
            coordination_overhead=coordination_overhead,
            throughput_tasks_per_sec=throughput,
            agent_utilization=agent_utilization,
            num_agents=num_agents,
            num_domains=num_domains,
            num_tasks=num_tasks,
            dag_depth=dag_depth,
        )

    def scaling_report(
        self,
        sizes: list[int] | None = None,
        *,
        num_domains: int = 4,
        dag_depth: int = 3,
        dag_width: int = 5,
    ) -> list[BenchmarkResult]:
        """Run benchmarks at multiple agent scales and return comparative results.

        Args:
            sizes: List of agent counts to benchmark. Defaults to [10, 100, 800].
            num_domains: Number of domains per run.
            dag_depth: DAG depth per run.
            dag_width: DAG width per run.

        Returns:
            List of BenchmarkResult, one per agent count.
        """
        if sizes is None:
            sizes = [10, 100, 800]

        return [
            self.run(
                num_agents=size,
                num_domains=num_domains,
                dag_depth=dag_depth,
                dag_width=dag_width,
            )
            for size in sizes
        ]
