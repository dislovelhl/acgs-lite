"""omalhc — Constitutional Swarm Mesh.

Orchestrator-free multi-agent governance via embedded Agent DNA,
stigmergic task coordination, and constitutional peer validation.

Three breakthrough patterns:
  A. Agent DNA — embedded constitutional validation (443ns/check)
  B. Stigmergic Swarm — DAG-compiled task execution, no orchestrator
  C. Constitutional Mesh — peer-validated Byzantine tolerance
"""

from omalhc.dna import constitutional_dna, AgentDNA
from omalhc.capability import Capability, CapabilityRegistry
from omalhc.contract import TaskContract, ContractStatus
from omalhc.artifact import Artifact, ArtifactStore
from omalhc.swarm import SwarmExecutor, TaskDAG, TaskNode
from omalhc.mesh import ConstitutionalMesh, PeerAssignment, ValidationVote, MeshProof, MeshResult

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
