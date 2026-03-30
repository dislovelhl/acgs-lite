"""Bittensor synapse definitions for constitutional governance subnet.

Three message types:
  1. DeliberationSynapse: SN Owner → Miner (escalated governance case)
  2. JudgmentSynapse: Miner → Validator (deliberation result + DNA pre-check)
  3. ValidationSynapse: Validator → SN Owner (grading + Merkle proof)

These are protocol-level data structures. The actual bittensor.Synapse
base class is lazy-imported so the package works without bittensor installed.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DeliberationSynapse:
    """SN Owner → Miner: an escalated governance case requiring human judgment.

    Contains the serialized TaskDAG, constitutional hash for verification,
    domain/capability requirements for routing, and a deadline.
    """

    task_id: str
    task_dag_json: str
    constitution_hash: str
    domain: str
    required_capabilities: tuple[str, ...] = ()
    deadline_seconds: int = 3600
    escalation_type: str = ""
    impact_score: float = 0.0
    impact_vector: dict[str, float] = field(default_factory=dict)
    context: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def content_hash(self) -> str:
        """Deterministic hash of the deliberation request."""
        payload = f"{self.task_id}:{self.constitution_hash}:{self.task_dag_json}"
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JudgmentSynapse:
    """Miner → Validator: deliberation result with DNA pre-validation.

    Contains the miner's governance judgment, written reasoning,
    the artifact hash for integrity, and the DNA pre-check result.
    The constitutional_hash must match the validator's constitution.
    """

    task_id: str
    miner_uid: str
    judgment: str
    reasoning: str
    artifact_hash: str
    constitutional_hash: str
    dna_valid: bool = True
    dna_violations: tuple[str, ...] = ()
    dna_latency_ns: int = 0
    domain: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def content_hash(self) -> str:
        """Deterministic hash of the judgment."""
        payload = f"{self.task_id}:{self.miner_uid}:{self.judgment}:{self.constitutional_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationSynapse:
    """Validator → SN Owner: grading result with cryptographic proof.

    Contains the MeshResult (accepted/rejected, vote counts, quorum),
    the MeshProof (Merkle chain), and optional manifold trust update.
    """

    task_id: str
    assignment_id: str
    accepted: bool
    votes_for: int
    votes_against: int
    quorum_met: bool
    proof_root_hash: str = ""
    proof_vote_hashes: tuple[str, ...] = ()
    proof_content_hash: str = ""
    constitutional_hash: str = ""
    trust_update: dict[str, Any] = field(default_factory=dict)
    authenticity_score: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_verified(self) -> bool:
        """Check if the proof can be locally verified."""
        return bool(self.proof_root_hash and self.proof_vote_hashes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
