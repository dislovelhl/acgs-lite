"""omalhc — Manifold-Constrained Constitutional Swarm Mesh.

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

from omalhc.dna import constitutional_dna, AgentDNA
from omalhc.capability import Capability, CapabilityRegistry
from omalhc.contract import TaskContract, ContractStatus
from omalhc.artifact import Artifact, ArtifactStore
from omalhc.swarm import SwarmExecutor, TaskDAG, TaskNode
from omalhc.mesh import ConstitutionalMesh, PeerAssignment, ValidationVote, MeshProof, MeshResult
from omalhc.manifold import GovernanceManifold, sinkhorn_knopp, ManifoldProjectionResult
from omalhc.compiler import DAGCompiler, GoalSpec
from omalhc.bench import SwarmBenchmark, BenchmarkResult

__all__ = [
    "constitutional_dna",
    "AgentDNA",
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
    "GovernanceManifold",
    "sinkhorn_knopp",
    "ManifoldProjectionResult",
    "DAGCompiler",
    "GoalSpec",
    "SwarmBenchmark",
    "BenchmarkResult",
]
