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

from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.bench import BenchmarkResult, SwarmBenchmark
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.compiler import DAGCompiler, GoalSpec
from constitutional_swarm.contract import ContractStatus, TaskContract
from constitutional_swarm.dna import AgentDNA, DNADisabledError, constitutional_dna
from constitutional_swarm.execution import ExecutionStatus, WorkReceipt
from constitutional_swarm.manifold import (
    GovernanceManifold,
    ManifoldProjectionResult,
    sinkhorn_knopp,
)
from constitutional_swarm.mesh import (
    ConstitutionalMesh,
    MeshHaltedError,
    MeshProof,
    MeshResult,
    PeerAssignment,
    ValidationVote,
)
from constitutional_swarm.swarm import SwarmExecutor, TaskDAG, TaskNode

__all__ = [
    "AgentDNA",
    "Artifact",
    "ArtifactStore",
    "BenchmarkResult",
    "Capability",
    "CapabilityRegistry",
    "ConstitutionalMesh",
    "ContractStatus",
    "DAGCompiler",
    "DNADisabledError",
    "ExecutionStatus",
    "GoalSpec",
    "GovernanceManifold",
    "ManifoldProjectionResult",
    "MeshHaltedError",
    "MeshProof",
    "MeshResult",
    "PeerAssignment",
    "SwarmBenchmark",
    "SwarmExecutor",
    "TaskContract",
    "TaskDAG",
    "TaskNode",
    "ValidationVote",
    "WorkReceipt",
    "constitutional_dna",
    "sinkhorn_knopp",
]
