# mhc

[![PyPI](https://img.shields.io/pypi/v/mhc)](https://pypi.org/project/mhc/)
[![Python](https://img.shields.io/pypi/pyversions/mhc)](https://pypi.org/project/mhc/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Short-import-path alias for `constitutional-swarm` — Multi-agent Hierarchical Constitutional governance.**

`mhc` is a re-export package. It installs `constitutional-swarm` and re-exports a curated subset of its public symbols under the `mhc` namespace. There is no new code in this package; it exists so you can write `from mhc import AgentDNA` instead of `from constitutional_swarm import AgentDNA`.

If you need the full `constitutional-swarm` API (including `GovernanceManifold`, `sinkhorn_knopp`, `SwarmBenchmark`, `DAGCompiler`, etc.), install `constitutional-swarm` directly.

## Installation

```bash
pip install mhc
```

Requires Python 3.11+.

## Quick Start

```python
from mhc import AgentDNA, ConstitutionalMesh, SwarmExecutor, TaskDAG

# Agent DNA — embedded constitutional validation
dna = AgentDNA.default(agent_id="worker-1")
result = dna.validate("propose deployment")
print(result.valid, result.latency_ns)

# Constitutional Mesh — Byzantine-tolerant peer validation
from acgs_lite import Constitution
constitution = Constitution.from_yaml("constitution.yaml")
mesh = ConstitutionalMesh(constitution, peers_per_validation=3, quorum=2)
```

All `mhc` symbols are identical to the same-named `constitutional_swarm` symbols:

```python
from mhc import AgentDNA
from constitutional_swarm import AgentDNA as _AgentDNA
assert AgentDNA is _AgentDNA  # True
```

## Exported Symbols

`mhc` re-exports exactly these symbols from `constitutional_swarm`:

| Symbol | Description |
|--------|-------------|
| `AgentDNA` | Embedded constitutional co-processor; `.from_rules()`, `.from_yaml()`, `.default(agent_id=...)`, `.validate()`, `.govern` decorator |
| `constitutional_dna` | Decorator factory for inline DNA governance |
| `ConstitutionalMesh` | Byzantine-tolerant peer validation mesh |
| `MeshProof` | Cryptographic proof of peer validation |
| `MeshResult` | Full settle result including proof and vote list |
| `PeerAssignment` | Links a producer's output to assigned peer validators |
| `ValidationVote` | A peer's signed vote on a producer's output |
| `SwarmExecutor` | Runs a `TaskDAG`; agents claim ready tasks by capability |
| `TaskDAG` | Directed acyclic graph of tasks compiled from a goal |
| `TaskNode` | Single unit of work in a `TaskDAG` |
| `Artifact` | Task output record |
| `ArtifactStore` | Stores and retrieves `Artifact`s by ID |
| `Capability` | Named capability |
| `CapabilityRegistry` | Maps agent IDs to their `Capability` sets |
| `TaskContract` | Agreement record between a task and a claiming agent |
| `ContractStatus` | Enum: `PENDING`, `ACTIVE`, `COMPLETED`, `FAILED` |

## What is NOT re-exported

The following `constitutional-swarm` symbols are not in `mhc.__all__` — import them from `constitutional_swarm` directly if needed:

- `GovernanceManifold`, `ManifoldProjectionResult`, `sinkhorn_knopp`
- `DAGCompiler`, `GoalSpec`
- `SwarmBenchmark`, `BenchmarkResult`
- `DNADisabledError`, `MeshHaltedError`
- `WorkReceipt`, `ExecutionStatus`

## Runtime dependencies

- `constitutional-swarm` (which requires `acgs-lite>=2.5`)

## License

AGPL-3.0-or-later.

## Links

- [Homepage](https://acgs.ai)
- [PyPI](https://pypi.org/project/mhc/)
- [constitutional-swarm on PyPI](https://pypi.org/project/constitutional-swarm/)
- [Issues](https://github.com/dislovelhl/mhc/issues)
