# constitutional-swarm

[![PyPI](https://img.shields.io/pypi/v/constitutional-swarm)](https://pypi.org/project/constitutional-swarm/)
[![Python](https://img.shields.io/pypi/pyversions/constitutional-swarm)](https://pypi.org/project/constitutional-swarm/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Orchestrator-free multi-agent governance.**

`constitutional-swarm` packages the core swarm patterns for governed multi-agent
systems: embedded agent DNA validation, task-DAG coordination, peer-validated mesh
consensus, and manifold-constrained trust propagation.

## Installation

`constitutional-swarm` supports Python 3.11+.

```bash
pip install constitutional-swarm
pip install constitutional-swarm[bittensor]
```

## Quick Start

### Agent DNA

```python
from constitutional_swarm import AgentDNA

dna = AgentDNA.default(agent_id="agent-1")
result = dna.validate("deploy to production")

print(result.valid, result.constitutional_hash)
```

### Stigmergic Task DAGs

```python
from constitutional_swarm import TaskDAG, TaskNode

dag = TaskDAG(goal="Build governed AI system")
dag = dag.add_node(
    TaskNode(
        node_id="research",
        title="Research requirements",
        domain="research",
        required_capabilities=("research",),
    )
)
dag = dag.add_node(
    TaskNode(
        node_id="implement",
        title="Implement core",
        domain="engineering",
        depends_on=("research",),
        required_capabilities=("coding",),
    )
)

dag = dag.mark_ready()
assert dag.nodes["research"].status.value == "ready"

dag = dag.claim_node("research", agent_id="agent-1")
dag = dag.complete_node("research", artifact_id="spec-001")
dag = dag.mark_ready()
assert dag.nodes["implement"].status.value == "ready"
```

### Constitutional Mesh Validation

```python
from acgs_lite import Constitution
from constitutional_swarm import ConstitutionalMesh

mesh = ConstitutionalMesh(Constitution.default(), peers_per_validation=3, quorum=2)
mesh.register_agent("agent-1", domain="platform")
mesh.register_agent("agent-2", domain="security")
mesh.register_agent("agent-3", domain="compliance")
mesh.register_agent("agent-4", domain="operations")

assignment = mesh.request_validation(
    producer_id="agent-1",
    content="deploy payment module",
    artifact_id="artifact-1",
)

mesh.validate_and_vote(assignment.assignment_id, "agent-2")
mesh.validate_and_vote(assignment.assignment_id, "agent-3")

result = mesh.get_result(assignment.assignment_id)
print(result.quorum_met, result.accepted, result.proof is not None)
```

### Governance Manifold

```python
from constitutional_swarm import GovernanceManifold

manifold = GovernanceManifold(num_agents=3)
manifold.update_trust(0, 1, 0.8)
manifold.update_trust(1, 2, 0.5)
projection = manifold.project()

print(projection.converged, projection.spectral_bound)
```

## Key Features

- Embedded `AgentDNA` validation with decorator support and halt/resume controls.
- DAG-based task coordination through `TaskDAG`, `TaskNode`, and `SwarmExecutor`.
- Peer-validated consensus and Merkle-style proof generation via `ConstitutionalMesh`.
- Trust-matrix projection and composition through `GovernanceManifold`.
- Supporting artifact, capability, contract, compiler, and benchmark primitives.

## Testing

```bash
python -m pytest packages/constitutional_swarm/tests/ -v --import-mode=importlib
python -m pytest packages/constitutional_swarm/tests/ -m "not slow" -v --import-mode=importlib
```

## License

AGPL-3.0-or-later. Commercial licensing is available; contact `hello@acgs.ai`.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://github.com/acgs2_admin/acgs/tree/main/packages/constitutional_swarm)
- [PyPI](https://pypi.org/project/constitutional-swarm/)
- [Repository](https://github.com/acgs2_admin/acgs)
- [Issues](https://github.com/acgs2_admin/acgs/issues)
- [Changelog](https://github.com/acgs2_admin/acgs/releases)

Constitutional Hash: `608508a9bd224290`
