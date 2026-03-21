"""constitutional_swarm — Constitutional Swarm Mesh.

Orchestrator-free multi-agent governance via embedded Agent DNA,
stigmergic task coordination, and constitutional peer validation.

Three breakthrough patterns:
  A. Agent DNA — embedded constitutional validation (443ns/check)
  B. Stigmergic Swarm — DAG-compiled task execution, no orchestrator
  C. Constitutional Mesh — peer-validated Byzantine tolerance
"""

from constitutional_swarm.dna import constitutional_dna, AgentDNA
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.contract import TaskContract, ContractStatus
from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.swarm import SwarmExecutor, TaskDAG, TaskNode
from constitutional_swarm.mesh import ConstitutionalMesh, PeerAssignment, ValidationVote, MeshProof, MeshResult

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
]
