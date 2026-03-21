# Codex Handoff: DAG Compiler + Benchmark Harness

## Context

`constitutional_swarm` is a constitutional swarm mesh package at `packages/constitutional_swarm/`.
It governs multi-agent systems without orchestrators using:
- Agent DNA (embedded 443ns constitutional validation)
- Stigmergic task DAGs (agents self-select work from artifact store)
- All existing code passes 35/35 tests

You are implementing **P1: DAG Compiler** and **P3: Benchmark Harness**.

## Task 1: DAG Compiler (`src/constitutional_swarm/compiler.py`)

### Scope
Build a `DAGCompiler` that converts structured goal descriptions into `TaskDAG` objects.

### Requirements

```python
from constitutional_swarm.compiler import DAGCompiler, GoalSpec

# Input: structured goal spec
spec = GoalSpec(
    goal="Build user authentication feature",
    domains=["backend", "frontend", "security", "qa"],
    steps=[
        {"title": "Design auth schema", "domain": "backend", "depends_on": []},
        {"title": "Implement JWT middleware", "domain": "backend", "depends_on": ["Design auth schema"]},
        {"title": "Build login UI", "domain": "frontend", "depends_on": ["Design auth schema"]},
        {"title": "Security review", "domain": "security", "depends_on": ["Implement JWT middleware", "Build login UI"]},
        {"title": "Integration tests", "domain": "qa", "depends_on": ["Security review"]},
    ],
)

# Output: TaskDAG ready for SwarmExecutor
compiler = DAGCompiler()
dag = compiler.compile(spec)

assert len(dag.nodes) == 5
assert dag.goal == "Build user authentication feature"
ready = dag.mark_ready()
# Only "Design auth schema" should be ready (no deps)
```

### Implementation Details

- `GoalSpec`: dataclass with `goal: str`, `domains: list[str]`, `steps: list[dict]`
- Each step dict has: `title`, `domain`, `depends_on` (list of titles), optional `required_capabilities`, `priority`, `max_budget_tokens`
- `DAGCompiler.compile(spec) -> TaskDAG`: converts steps to `TaskNode` objects, resolves title-based dependencies to node IDs
- `DAGCompiler.compile_from_yaml(path) -> TaskDAG`: load GoalSpec from YAML file
- Validate: no cycles (raise `ValueError`), all dependency titles exist, all domains non-empty
- Generate deterministic `node_id` from title hash (so same spec always produces same DAG)

### Constraints
- Python 3.11+, ruff line-length 100
- Immutable patterns (no mutation)
- No external dependencies beyond PyYAML (already in environment)

### Required Checks
```bash
python -m pytest packages/constitutional_swarm/tests/ -v --import-mode=importlib
# Must pass all existing 35 tests + new compiler tests
```

### Deliverable
- `src/constitutional_swarm/compiler.py`
- `tests/test_compiler.py` (minimum 10 tests: happy path, cycle detection, missing deps, YAML loading, empty spec, single node, diamond DAG, linear chain, duplicate titles, large DAG with 100 nodes)
- Update `src/constitutional_swarm/__init__.py` to export `DAGCompiler, GoalSpec`

---

## Task 2: Benchmark Harness (`src/constitutional_swarm/bench.py`)

### Scope
Build a benchmark that simulates swarm execution at 10, 100, and 800 agent scale.

### Requirements

```python
from constitutional_swarm.bench import SwarmBenchmark, BenchmarkResult

bench = SwarmBenchmark()

# Simulate N agents across M domains executing a task DAG
result = bench.run(
    num_agents=100,
    num_domains=10,
    dag_depth=5,       # DAG has 5 levels of dependencies
    dag_width=20,      # 20 parallel tasks per level = 100 total nodes
)

assert isinstance(result, BenchmarkResult)
print(result.total_time_ms)
print(result.avg_validation_ns)      # DNA validation latency
print(result.coordination_overhead)   # ratio of coordination vs useful work
print(result.throughput_tasks_per_sec)
print(result.agent_utilization)       # % of time agents are doing work vs waiting
```

### Implementation Details

- `SwarmBenchmark`: creates synthetic DAGs, registers N agents with random capabilities across M domains, runs SwarmExecutor to completion
- `BenchmarkResult`: dataclass with metrics: `total_time_ms`, `avg_validation_ns`, `coordination_overhead`, `throughput_tasks_per_sec`, `agent_utilization`, `num_agents`, `num_domains`, `num_tasks`, `dag_depth`
- `bench.run()` simulates: each agent polls for available tasks, claims one, "executes" (sleep 0 — we measure overhead, not work), publishes artifact, DNA validates
- `bench.scaling_report(sizes=[10, 100, 800])` runs benchmarks at each scale and returns comparative results
- The key metric to prove: governance overhead stays O(N), not O(N^2)

### Constraints
- Python 3.11+, ruff line-length 100
- No external dependencies
- Must complete 800-agent benchmark in under 10 seconds (we're measuring framework overhead, not real work)

### Required Checks
```bash
python -m pytest packages/constitutional_swarm/tests/ -v --import-mode=importlib
# All tests pass including new benchmark tests
python -m pytest packages/constitutional_swarm/tests/test_bench.py -v --import-mode=importlib -m "not slow"
# Quick benchmark tests (10-agent only) pass fast
```

### Deliverable
- `src/constitutional_swarm/bench.py`
- `tests/test_bench.py` (minimum 5 tests: 10-agent run, result structure, scaling linearity check, utilization > 0, throughput > 0)
- Mark 100+ agent tests with `@pytest.mark.slow`

---

## File References

Read these before starting:
- `packages/constitutional_swarm/src/constitutional_swarm/swarm.py` — TaskDAG, TaskNode, SwarmExecutor
- `packages/constitutional_swarm/src/constitutional_swarm/dna.py` — AgentDNA, constitutional_dna
- `packages/constitutional_swarm/src/constitutional_swarm/capability.py` — CapabilityRegistry
- `packages/constitutional_swarm/src/constitutional_swarm/artifact.py` — ArtifactStore
- `packages/constitutional_swarm/src/constitutional_swarm/contract.py` — TaskContract
- `packages/constitutional_swarm/tests/test_constitutional_swarm.py` — existing test patterns
