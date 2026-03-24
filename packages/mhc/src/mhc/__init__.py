"""constitutional_swarm — Constitutional Swarm Mesh.

Orchestrator-free multi-agent governance via embedded Agent DNA,
stigmergic task coordination, and constitutional peer validation.

Three breakthrough patterns:
  A. Agent DNA — embedded constitutional validation (443ns/check)
  B. Stigmergic Swarm — DAG-compiled task execution, no orchestrator
  C. Constitutional Mesh — peer-validated Byzantine tolerance
"""

from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.contract import ContractStatus, TaskContract
from constitutional_swarm.dna import AgentDNA, constitutional_dna
from constitutional_swarm.mesh import (
    ConstitutionalMesh,
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
    "Capability",
    "CapabilityRegistry",
    "ConstitutionalMesh",
    "ContractStatus",
    "MeshProof",
    "MeshResult",
    "PeerAssignment",
    "SwarmExecutor",
    "TaskContract",
    "TaskDAG",
    "TaskNode",
    "ValidationVote",
    "constitutional_dna",
]
