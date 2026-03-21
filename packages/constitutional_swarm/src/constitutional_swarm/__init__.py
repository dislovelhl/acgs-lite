"""constitutional_swarm — Manifold-Constrained Constitutional Swarm Mesh.

Orchestrator-free multi-agent governance via embedded Agent DNA,
stigmergic task coordination, constitutional peer validation,
and manifold-constrained trust propagation.

Four breakthrough patterns:
  A. Agent DNA — embedded constitutional validation (443ns/check)
  B. Stigmergic Swarm — DAG-compiled task execution, no orchestrator
  C. Constitutional Mesh — peer-validated Byzantine tolerance
  D. Governance Manifold — Sinkhorn-Knopp projected trust matrices
     guaranteeing bounded influence and compositional stability
     (inspired by mHC, arXiv:2512.24880)
"""

from constitutional_swarm.dna import constitutional_dna, AgentDNA, DNADisabledError
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.contract import TaskContract, ContractStatus
from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.swarm import SwarmExecutor, TaskDAG, TaskNode
from constitutional_swarm.mesh import ConstitutionalMesh, PeerAssignment, ValidationVote, MeshProof, MeshResult, MeshHaltedError
from constitutional_swarm.manifold import GovernanceManifold, sinkhorn_knopp, ManifoldProjectionResult
from constitutional_swarm.compiler import DAGCompiler, GoalSpec
from constitutional_swarm.bench import SwarmBenchmark, BenchmarkResult

__all__ = [
    "constitutional_dna",
    "AgentDNA",
    "DNADisabledError",
    "Capability",
    "CapabilityRegistry",
    "TaskContract",
    "ContractStatus",
    "Artifact",
    "ArtifactStore",
    "SwarmExecutor",
    "TaskDAG",
    "TaskNode",
    "ConstitutionalMesh",
    "PeerAssignment",
    "ValidationVote",
    "MeshProof",
    "MeshResult",
    "MeshHaltedError",
    "GovernanceManifold",
    "sinkhorn_knopp",
    "ManifoldProjectionResult",
    "DAGCompiler",
    "GoalSpec",
    "SwarmBenchmark",
    "BenchmarkResult",
]
