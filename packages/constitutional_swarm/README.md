# constitutional-swarm

[![PyPI](https://img.shields.io/pypi/v/constitutional-swarm)](https://pypi.org/project/constitutional-swarm/)
[![Python](https://img.shields.io/pypi/pyversions/constitutional-swarm)](https://pypi.org/project/constitutional-swarm/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Orchestrator-free multi-agent governance via embedded Agent DNA, stigmergic task coordination, constitutional peer validation, and manifold-constrained trust.**

`constitutional-swarm` provides four composable patterns for governed multi-agent systems. All governance is local (443 ns/check), embedded in each agent — no central bus, no orchestrator, no network round-trips. The package depends only on `acgs-lite`.

## Installation

```bash
pip install constitutional-swarm
```

Requires Python 3.11+.

## Quick Start

### Pattern A — Agent DNA (embedded validation)

Every agent carries an immutable constitutional validator. Governance is O(1) and local.

```python
from constitutional_swarm import AgentDNA
from acgs_lite import Rule, Severity

dna = AgentDNA.from_rules([
    Rule(id="no-pii", pattern="SSN|date of birth", severity=Severity.CRITICAL,
         description="Block PII"),
])

result = dna.validate("summarize patient notes")
print(result.valid, result.latency_ns)  # True, ~443

# Use as a decorator
@dna.govern
def my_agent(text: str) -> str:
    return f"processed: {text}"
```

Load from YAML or use defaults:

```python
dna = AgentDNA.from_yaml("constitution.yaml")
dna = AgentDNA.default(agent_id="worker-1")  # permissive defaults
```

### Pattern B — Stigmergic Swarm (DAG-compiled task execution)

Compile a goal into a `TaskDAG`. Agents self-select ready tasks by capability — no orchestrator.

```python
from constitutional_swarm import DAGCompiler, GoalSpec, SwarmExecutor, CapabilityRegistry

spec = GoalSpec(
    goal="Analyse and summarise quarterly reports",
    subtasks=[
        {"title": "fetch-reports", "domain": "data", "required_capabilities": ["fetch"]},
        {"title": "analyse",       "domain": "analytics", "required_capabilities": ["analyse"],
         "depends_on": ["fetch-reports"]},
        {"title": "summarise",     "domain": "writing", "required_capabilities": ["write"],
         "depends_on": ["analyse"]},
    ],
)

dag = DAGCompiler().compile(spec)
registry = CapabilityRegistry()
executor = SwarmExecutor(registry=registry)
results = executor.run(dag)
```

### Pattern C — Constitutional Mesh (Byzantine-tolerant peer validation)

Every output is validated by randomly assigned peers. Quorum acceptance produces a cryptographic `MeshProof`.

```python
from constitutional_swarm import ConstitutionalMesh
from acgs_lite import Constitution

constitution = Constitution.from_yaml("constitution.yaml")

mesh = ConstitutionalMesh(
    constitution,
    peers_per_validation=3,  # peers assigned per output
    quorum=2,                 # votes needed to accept
)

mesh.register_agent("agent-a", domain="writing")
mesh.register_agent("agent-b", domain="writing")
mesh.register_agent("agent-c", domain="writing")

# Assign peers and collect votes
assignment = mesh.assign_peers("agent-a", artifact_id="doc-1", content="Draft report…")
vote_a = mesh.validate_and_vote("agent-b", assignment.assignment_id)
vote_b = mesh.validate_and_vote("agent-c", assignment.assignment_id)

proof: MeshProof = mesh.settle(assignment.assignment_id)
print(proof.accepted, proof.quorum_reached)
```

### Pattern D — Governance Manifold (bounded trust propagation)

Projects raw agent interaction matrices onto the Birkhoff polytope (doubly stochastic) via Sinkhorn-Knopp, guaranteeing bounded influence at any scale.

```python
from constitutional_swarm import GovernanceManifold, sinkhorn_knopp

# Raw trust matrix (3 agents)
raw = [[1.0, 0.5, 0.2],
       [0.3, 1.0, 0.7],
       [0.1, 0.4, 1.0]]

result = sinkhorn_knopp(raw, max_iterations=20, epsilon=1e-6)
print(result.converged, result.spectral_bound)  # True, ≤1.0

# Or use the stateful GovernanceManifold (tracks interaction history)
manifold = GovernanceManifold(num_agents=3)
manifold.record_interaction(producer=0, validator=1, trust=0.8)
projection = manifold.project()
```

## Key Features

- **Agent DNA** — `AgentDNA` embeds a constitutional co-processor in every agent; 443 ns/validation via the ACGS Rust engine
- **Stigmergic DAGs** — `DAGCompiler` + `SwarmExecutor` for orchestrator-free task execution; agents claim `ready_nodes()` by capability
- **Constitutional Mesh** — `ConstitutionalMesh` provides Byzantine-tolerant peer validation with cryptographic `MeshProof` chains; MACI prevents self-validation
- **Sinkhorn-Knopp manifold** — `GovernanceManifold` and `sinkhorn_knopp()` project trust matrices onto the Birkhoff polytope; spectral norm ≤ 1
- **Artifact store** — `ArtifactStore` tracks task outputs (`Artifact`) by ID
- **Capability registry** — `CapabilityRegistry` maps agents to `Capability` sets for task claiming
- **Benchmarking** — `SwarmBenchmark` for measuring validation throughput at scale

## API Reference

| Symbol | Description |
|--------|-------------|
| `AgentDNA` | Constitutional co-processor; `.from_rules()`, `.from_yaml()`, `.default(agent_id=...)`, `.validate(action)`, `.govern` decorator |
| `DNAValidationResult` | `valid`, `action`, `violations`, `latency_ns`, `constitutional_hash`, `risk_score` |
| `DNADisabledError` | Raised when validate() is called on a disabled `AgentDNA` |
| `constitutional_dna` | Decorator factory for inline DNA governance |
| `ConstitutionalMesh` | `ConstitutionalMesh(constitution, peers_per_validation=3, quorum=2)` |
| `MeshProof` | Cryptographic proof of peer validation; `accepted`, `quorum_reached`, `votes` |
| `MeshResult` | Full settle result including proof and vote list |
| `MeshHaltedError` | Raised when mesh is halted and a new operation is attempted |
| `PeerAssignment` | Immutable assignment linking a producer's output to peer validators |
| `ValidationVote` | A peer's signed vote on a producer's output |
| `SwarmExecutor` | Runs a `TaskDAG`; agents self-select tasks by capability |
| `TaskDAG` | DAG of `TaskNode`s compiled from a `GoalSpec` |
| `TaskNode` | Single unit of work: `title`, `required_capabilities`, `depends_on`, `status` |
| `DAGCompiler` | `.compile(GoalSpec)` → `TaskDAG`; `.compile_from_yaml(path)` |
| `GoalSpec` | Goal description with subtask list |
| `GovernanceManifold` | Tracks agent interactions; `.project()` → `ManifoldProjectionResult` |
| `ManifoldProjectionResult` | `matrix`, `iterations`, `converged`, `max_deviation`, `spectral_bound` |
| `sinkhorn_knopp` | Projects any non-negative matrix onto the Birkhoff polytope |
| `Artifact` | Task output record |
| `ArtifactStore` | Stores and retrieves `Artifact`s by ID |
| `Capability` | Named capability (string + metadata) |
| `CapabilityRegistry` | Maps agent IDs to their `Capability` sets |
| `TaskContract` | Records the agreement between a task and a claiming agent |
| `ContractStatus` | Enum: `PENDING`, `ACTIVE`, `COMPLETED`, `FAILED` |
| `WorkReceipt` | Receipt issued when an agent completes a task node |
| `ExecutionStatus` | Enum: `BLOCKED`, `READY`, `ACTIVE`, `COMPLETED`, `FAILED` |
| `SwarmBenchmark` | Measures DNA validation throughput at scale |
| `BenchmarkResult` | Benchmark output: `agents`, `validations_per_second`, `p99_ns` |

## Runtime dependencies

- `acgs-lite>=2.5`

## License

AGPL-3.0-or-later.

## Links

- [Homepage](https://acgs.ai)
- [PyPI](https://pypi.org/project/constitutional-swarm/)
- [Issues](https://github.com/dislovelhl/constitutional-swarm/issues)
