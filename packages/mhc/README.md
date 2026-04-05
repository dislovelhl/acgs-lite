# mhc

[![PyPI](https://img.shields.io/pypi/v/mhc)](https://pypi.org/project/mhc/)
[![Python](https://img.shields.io/pypi/pyversions/mhc)](https://pypi.org/project/mhc/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Short import path for the core `constitutional-swarm` primitives.**

`mhc` depends on `constitutional-swarm` and re-exports the core top-level DNA, mesh,
swarm, artifact, capability, and contract APIs under a shorter import namespace.

## Installation

`mhc` supports Python 3.11+.

```bash
pip install mhc
```

## Quick Start

```python
from mhc import AgentDNA, ConstitutionalMesh, TaskDAG
from constitutional_swarm import AgentDNA as ConstitutionalSwarmDNA

assert AgentDNA is ConstitutionalSwarmDNA
```

## Exported API

`mhc` currently re-exports these top-level symbols:

| Category | Symbols |
| --- | --- |
| DNA | `AgentDNA`, `constitutional_dna` |
| Swarm | `TaskDAG`, `TaskNode`, `SwarmExecutor` |
| Mesh | `ConstitutionalMesh`, `MeshProof`, `MeshResult`, `PeerAssignment`, `ValidationVote` |
| Artifacts | `Artifact`, `ArtifactStore` |
| Capabilities | `Capability`, `CapabilityRegistry` |
| Contracts | `TaskContract`, `ContractStatus` |

For compiler, benchmark, manifold, or Bittensor-specific modules, import directly from
`constitutional_swarm`.

## When to Use `mhc`

- Use `mhc` when you want the shorter import path for the core multi-agent primitives.
- Use `constitutional-swarm` when you want the full package surface and primary
  documentation.

## License

AGPL-3.0-or-later. Commercial licensing is available; contact `hello@acgs.ai`.

## Links

- [Homepage](https://acgs.ai)
- [Documentation](https://github.com/dislovelhl/acgs/tree/main/packages/mhc)
- [PyPI](https://pypi.org/project/mhc/)
- [Repository](https://github.com/dislovelhl/acgs)
- [Issues](https://github.com/dislovelhl/acgs/issues)
- [Changelog](https://github.com/dislovelhl/acgs/releases)

Constitutional Hash: `608508a9bd224290`
