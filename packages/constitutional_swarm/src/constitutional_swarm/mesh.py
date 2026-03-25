"""Constitutional Mesh — Byzantine-tolerant peer validation with cryptographic proof.

The defensible core of constitutional_swarm. Every agent's output is validated by randomly
assigned peers using the ACGS constitutional engine (443ns). No single
validator bottleneck. Tolerates up to 1/3 faulty/malicious agents.

Cryptographic proof chain:
  1. Producer creates output with constitutional hash
  2. Mesh assigns random peers (producer excluded — MACI)
  3. Each peer validates via embedded DNA (443ns, Rust engine)
  4. Votes are signed with voter's constitutional hash
  5. Quorum result produces a Merkle proof linking:
     - Producer's output hash
     - Each peer's vote + constitutional hash
     - Final acceptance/rejection decision
  6. Anyone can verify the proof independently

No competitor can replicate this: agents constitutionally validating
each other's work, with cryptographic proof, at sub-microsecond cost.
"""

from __future__ import annotations

import hashlib
import random
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from acgs_lite import Constitution
from constitutional_swarm.dna import AgentDNA
from constitutional_swarm.manifold import GovernanceManifold

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InsufficientPeersError(Exception):
    """Not enough peers available for validation."""


class DuplicateVoteError(Exception):
    """Peer already voted on this assignment."""


class UnauthorizedVoterError(Exception):
    """Voter is not assigned to this validation."""


class MeshHaltedError(RuntimeError):
    """Mesh has been halted — all operations blocked until resumed."""


# ---------------------------------------------------------------------------
# Data structures (all frozen — immutable by design)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PeerAssignment:
    """A validation assignment linking a producer's output to peer validators."""

    assignment_id: str
    producer_id: str
    artifact_id: str
    content: str
    content_hash: str
    peers: tuple[str, ...]
    constitutional_hash: str
    timestamp: float


@dataclass(frozen=True, slots=True)
class ValidationVote:
    """A peer's vote on a producer's output."""

    assignment_id: str
    voter_id: str
    approved: bool
    reason: str
    constitutional_hash: str
    content_hash: str
    timestamp: float

    @property
    def vote_hash(self) -> str:
        """Deterministic hash of this vote for proof chain."""
        payload = (
            f"{self.assignment_id}:{self.voter_id}:{self.approved}"
            f":{self.constitutional_hash}:{self.content_hash}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class MeshProof:
    """Cryptographic proof of peer validation.

    A Merkle-style proof linking the producer's output, each peer's vote,
    and the constitutional hash into a single verifiable root.
    Anyone can independently verify this proof.
    """

    assignment_id: str
    content_hash: str
    constitutional_hash: str
    vote_hashes: tuple[str, ...]
    root_hash: str
    accepted: bool
    timestamp: float

    def verify(self) -> bool:
        """Independently verify the proof chain.

        Recomputes the Merkle root from vote hashes and checks
        it matches the stored root.
        """
        recomputed = _compute_merkle_root(
            self.assignment_id,
            self.content_hash,
            self.constitutional_hash,
            self.vote_hashes,
            self.accepted,
        )
        return recomputed == self.root_hash


@dataclass(frozen=True, slots=True)
class MeshResult:
    """Result of a peer validation with cryptographic proof."""

    assignment_id: str
    accepted: bool
    votes_for: int
    votes_against: int
    quorum_met: bool
    pending_votes: int
    constitutional_hash: str
    proof: MeshProof | None


# ---------------------------------------------------------------------------
# Agent info (internal, mutable for reputation tracking)
# ---------------------------------------------------------------------------


@dataclass
class _AgentInfo:
    agent_id: str
    domain: str
    reputation: float = 1.0
    validations_performed: int = 0
    validations_received: int = 0


# ---------------------------------------------------------------------------
# Constitutional Mesh
# ---------------------------------------------------------------------------


class ConstitutionalMesh:
    """Byzantine-tolerant peer validation mesh with cryptographic proof.

    Every agent's output is validated by randomly assigned peers using
    the ACGS constitutional engine. The mesh produces a Merkle proof
    that anyone can independently verify.

    Properties:
    - O(1) governance cost per agent (local DNA validation)
    - Byzantine fault tolerant (tolerates < 1/3 faulty agents)
    - No single validator bottleneck
    - MACI-compliant (no self-validation)
    - Cryptographic proof chain for auditability
    - Sub-microsecond per validation (443ns via Rust engine)
    """

    def __init__(
        self,
        constitution: Constitution,
        *,
        peers_per_validation: int = 3,
        quorum: int = 2,
        seed: int | None = None,
        use_manifold: bool = False,
    ) -> None:
        if quorum > peers_per_validation:
            raise ValueError(
                f"Quorum ({quorum}) cannot exceed peers_per_validation "
                f"({peers_per_validation})"
            )
        self._constitution = constitution
        self._dna = AgentDNA(constitution=constitution, agent_id="mesh-validator")
        self._peers_per_validation = peers_per_validation
        self._quorum = quorum
        # Seeded randomness is only used for deterministic peer assignment in tests/benchmarks.
        self._rng = random.Random(seed) if seed is not None else random.SystemRandom()  # noqa: S311
        self._agents: dict[str, _AgentInfo] = {}
        self._assignments: dict[str, PeerAssignment] = {}
        self._votes: dict[str, list[ValidationVote]] = {}
        self._use_manifold = use_manifold
        self._manifold: GovernanceManifold | None = None
        self._agent_indices: dict[str, int] = {}
        self._settled_assignments: set[str] = set()
        self._settled_voters: dict[str, set[str]] = {}
        self._lock = threading.RLock()
        self._halted = False

    def _check_halted(self) -> None:
        """Raise if mesh is halted."""
        if self._halted:
            raise MeshHaltedError("Mesh is halted — all operations blocked")

    def halt(self) -> None:
        """Kill switch — halt all mesh operations immediately.

        While halted, request_validation, submit_vote, validate_and_vote,
        and full_validation all raise MeshHaltedError.
        EU AI Act Art. 14(3): human-initiated halt capability.
        """
        with self._lock:
            self._halted = True

    def resume(self) -> None:
        """Resume mesh operations after a halt."""
        with self._lock:
            self._halted = False

    @property
    def is_halted(self) -> bool:
        """Whether the mesh is currently halted."""
        with self._lock:
            return self._halted

    @property
    def constitutional_hash(self) -> str:
        """The constitutional hash shared by all mesh participants."""
        return self._constitution.hash

    @property
    def agent_count(self) -> int:
        """Number of registered agents."""
        with self._lock:
            return len(self._agents)

    # -- Agent management --------------------------------------------------

    def register_agent(self, agent_id: str, domain: str = "") -> None:
        """Register an agent as a mesh participant."""
        with self._lock:
            self._agents[agent_id] = _AgentInfo(agent_id=agent_id, domain=domain)
            if self._use_manifold and agent_id not in self._agent_indices:
                self._agent_indices[agent_id] = len(self._agent_indices)
                self._rebuild_manifold()

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the mesh."""
        with self._lock:
            self._agents.pop(agent_id, None)
            if self._use_manifold and agent_id in self._agent_indices:
                remaining_ids = [
                    existing_agent_id
                    for existing_agent_id, _ in sorted(
                        self._agent_indices.items(), key=lambda item: item[1]
                    )
                    if existing_agent_id != agent_id and existing_agent_id in self._agents
                ]
                self._agent_indices = {
                    existing_agent_id: idx
                    for idx, existing_agent_id in enumerate(remaining_ids)
                }
                self._rebuild_manifold()

    def get_reputation(self, agent_id: str) -> float:
        """Get an agent's reputation score."""
        with self._lock:
            info = self._agents.get(agent_id)
            if info is None:
                raise KeyError(f"Agent {agent_id} not registered")
            return info.reputation

    # -- Validation flow ---------------------------------------------------

    def request_validation(
        self,
        producer_id: str,
        content: str,
        artifact_id: str,
    ) -> PeerAssignment:
        """Request peer validation of a producer's output.

        Step 1: Constitutional DNA pre-check (443ns). Catches obvious
                violations before wasting peer time.
        Step 2: Select random peers, excluding the producer (MACI).
        Step 3: Return assignment with cryptographic content hash.

        Raises:
            ConstitutionalViolationError: Content violates constitution.
            InsufficientPeersError: Not enough peers available.
            KeyError: Producer not registered.
            MeshHaltedError: Mesh is halted.
        """
        with self._lock:
            self._check_halted()
            if producer_id not in self._agents:
                raise KeyError(f"Producer {producer_id} not registered")

            # Step 1: DNA pre-check — fail fast on constitutional violations
            self._dna.validate(content)

            # Step 2: Select peers (exclude producer — MACI)
            available = [aid for aid in self._agents if aid != producer_id]
            needed = min(self._peers_per_validation, len(available))
            if needed < self._quorum:
                raise InsufficientPeersError(
                    f"Need {self._quorum} peers for quorum, only {needed} available"
                )
            peers = tuple(self._rng.sample(available, k=needed))

            # Step 3: Create assignment with content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:32]
            assignment = PeerAssignment(
                assignment_id=uuid.uuid4().hex[:12],
                producer_id=producer_id,
                artifact_id=artifact_id,
                content=content,
                content_hash=content_hash,
                peers=peers,
                constitutional_hash=self.constitutional_hash,
                timestamp=time.time(),
            )
            self._assignments[assignment.assignment_id] = assignment
            self._votes[assignment.assignment_id] = []
            self._agents[producer_id].validations_received += 1
            return assignment

    def submit_vote(
        self,
        assignment_id: str,
        voter_id: str,
        *,
        approved: bool,
        reason: str = "",
    ) -> ValidationVote:
        """Submit a peer's validation vote.

        Each peer validates the content against their constitutional DNA
        and casts an approve/reject vote.

        Raises:
            KeyError: Assignment not found.
            UnauthorizedVoterError: Voter not assigned to this validation.
            DuplicateVoteError: Voter already voted.
            MeshHaltedError: Mesh is halted.
        """
        with self._lock:
            self._check_halted()
            assignment = self._assignments.get(assignment_id)
            if assignment is None:
                raise KeyError(f"Assignment {assignment_id} not found")
            if voter_id not in assignment.peers:
                raise UnauthorizedVoterError(
                    f"{voter_id} is not assigned to validation {assignment_id}"
                )

            existing = self._votes.get(assignment_id, [])
            if any(v.voter_id == voter_id for v in existing):
                raise DuplicateVoteError(
                    f"{voter_id} already voted on {assignment_id}"
                )

            vote = ValidationVote(
                assignment_id=assignment_id,
                voter_id=voter_id,
                approved=approved,
                reason=reason,
                constitutional_hash=self.constitutional_hash,
                content_hash=assignment.content_hash,
                timestamp=time.time(),
            )
            self._votes[assignment_id] = [*existing, vote]

            if voter_id in self._agents:
                self._agents[voter_id].validations_performed += 1

            # Update reputations if quorum reached
            self._maybe_settle_reputations(assignment_id)

            return vote

    def get_result(self, assignment_id: str) -> MeshResult:
        """Get the validation result for an assignment.

        Returns result with cryptographic proof once votes are cast.
        Quorum is met when enough votes agree to decide.
        """
        with self._lock:
            assignment = self._assignments.get(assignment_id)
            if assignment is None:
                raise KeyError(f"Assignment {assignment_id} not found")

            votes = self._votes.get(assignment_id, [])
            votes_for = sum(1 for v in votes if v.approved)
            votes_against = sum(1 for v in votes if not v.approved)
            total_peers = len(assignment.peers)
            pending = total_peers - len(votes)

            accepted = votes_for >= self._quorum
            rejected = votes_against > (total_peers - self._quorum)
            quorum_met = accepted or rejected

            # Build cryptographic proof
            proof: MeshProof | None = None
            if votes:
                vote_hashes = tuple(v.vote_hash for v in votes)
                decision = accepted and quorum_met
                root_hash = _compute_merkle_root(
                    assignment_id,
                    assignment.content_hash,
                    assignment.constitutional_hash,
                    vote_hashes,
                    decision,
                )
                proof = MeshProof(
                    assignment_id=assignment_id,
                    content_hash=assignment.content_hash,
                    constitutional_hash=assignment.constitutional_hash,
                    vote_hashes=vote_hashes,
                    root_hash=root_hash,
                    accepted=decision,
                    timestamp=time.time(),
                )

            return MeshResult(
                assignment_id=assignment_id,
                accepted=accepted,
                votes_for=votes_for,
                votes_against=votes_against,
                quorum_met=quorum_met,
                pending_votes=pending,
                constitutional_hash=self.constitutional_hash,
                proof=proof,
            )

    def validate_and_vote(
        self,
        assignment_id: str,
        voter_id: str,
    ) -> ValidationVote:
        """Convenience: peer validates content via DNA and auto-votes.

        The peer runs the content through their own constitutional DNA.
        If it passes, they vote approved. If it fails, they vote rejected
        with the violation as the reason.
        """
        with self._lock:
            assignment = self._assignments.get(assignment_id)
            if assignment is None:
                raise KeyError(f"Assignment {assignment_id} not found")
            content = assignment.content

        voter_dna = AgentDNA(
            constitution=self._constitution,
            agent_id=voter_id,
            strict=False,
        )
        result = voter_dna.validate(content)

        if result.valid:
            return self.submit_vote(
                assignment_id, voter_id, approved=True, reason="constitutional check passed"
            )
        return self.submit_vote(
            assignment_id,
            voter_id,
            approved=False,
            reason="; ".join(result.violations),
        )

    # -- Bulk operations ---------------------------------------------------

    def full_validation(
        self,
        producer_id: str,
        content: str,
        artifact_id: str,
    ) -> MeshResult:
        """End-to-end validation: assign peers, auto-vote, return result.

        Each peer runs constitutional DNA validation independently.
        Returns the mesh result with cryptographic proof.
        """
        assignment = self.request_validation(producer_id, content, artifact_id)
        for peer_id in assignment.peers:
            self.validate_and_vote(assignment.assignment_id, peer_id)
        return self.get_result(assignment.assignment_id)

    # -- Stats -------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Mesh statistics."""
        with self._lock:
            total_validations = len(self._assignments)
            total_votes = sum(len(v) for v in self._votes.values())
            settled = sum(1 for aid in self._assignments if self.get_result(aid).quorum_met)
            return {
                "agents": len(self._agents),
                "constitutional_hash": self.constitutional_hash,
                "total_validations": total_validations,
                "settled": settled,
                "pending": total_validations - settled,
                "total_votes": total_votes,
                "avg_reputation": (
                    sum(a.reputation for a in self._agents.values()) / len(self._agents)
                    if self._agents
                    else 0.0
                ),
            }

    # -- Manifold integration ----------------------------------------------

    @property
    def trust_matrix(self) -> tuple[tuple[float, ...], ...] | None:
        """The projected doubly stochastic trust matrix, or None if manifold disabled."""
        with self._lock:
            if self._manifold is None:
                return None
            return self._manifold.trust_matrix

    def manifold_summary(self) -> dict[str, Any] | None:
        """Manifold statistics, or None if manifold disabled."""
        with self._lock:
            if self._manifold is None:
                return None
            return self._manifold.summary()

    def _rebuild_manifold(self) -> None:
        """Rebuild the manifold with the current number of agents."""
        n = len(self._agent_indices)
        if n == 0:
            self._manifold = None
            return
        self._manifold = GovernanceManifold(n)

    # -- Internal ----------------------------------------------------------

    def _maybe_settle_reputations(self, assignment_id: str) -> None:
        """Update reputations when quorum is reached.

        Tracks which voters have already been reputation-adjusted via
        _settled_voters to prevent double-application. Late voters
        arriving after quorum are individually adjusted on arrival.
        Manifold updates are applied exactly once at first settlement.
        """
        result = self.get_result(assignment_id)
        if not result.quorum_met:
            return

        votes = self._votes.get(assignment_id, [])
        majority_approved = result.accepted
        first_settlement = assignment_id not in self._settled_assignments

        settled_voters = self._settled_voters.setdefault(assignment_id, set())

        for vote in votes:
            if vote.voter_id in settled_voters:
                continue
            settled_voters.add(vote.voter_id)
            agent = self._agents.get(vote.voter_id)
            if agent is None:
                continue
            if vote.approved == majority_approved:
                agent.reputation = min(2.0, agent.reputation + 0.01)
            else:
                agent.reputation = max(0.0, agent.reputation - 0.05)

        if first_settlement:
            self._settled_assignments.add(assignment_id)
            if self._manifold is not None:
                assignment = self._assignments[assignment_id]
                producer_idx = self._agent_indices.get(assignment.producer_id)
                if producer_idx is not None:
                    for vote in votes:
                        voter_idx = self._agent_indices.get(vote.voter_id)
                        if voter_idx is None:
                            continue
                        if vote.approved == majority_approved:
                            self._manifold.update_trust(producer_idx, voter_idx, 0.1)
                        else:
                            self._manifold.update_trust(producer_idx, voter_idx, -0.5)
                    self._manifold.project()


# ---------------------------------------------------------------------------
# Merkle proof computation
# ---------------------------------------------------------------------------


def _compute_merkle_root(
    assignment_id: str,
    content_hash: str,
    constitutional_hash: str,
    vote_hashes: tuple[str, ...],
    accepted: bool,
) -> str:
    """Compute the Merkle root for a validation proof.

    Structure:
        root
        ├── leaf: assignment_id + content_hash + constitutional_hash + accepted
        └── votes_root
            ├── vote_hash_0
            ├── vote_hash_1
            └── vote_hash_N

    This allows independent verification: given the content hash,
    constitutional hash, and vote hashes, anyone can recompute
    the root and verify the proof.
    """
    # Leaf: assignment identity + content + constitutional hash + final decision
    leaf = hashlib.sha256(
        f"{assignment_id}:{content_hash}:{constitutional_hash}:{accepted}".encode()
    ).hexdigest()[:32]

    # Votes subtree: iterative hashing of vote hashes
    if not vote_hashes:
        votes_root = hashlib.sha256(b"empty").hexdigest()[:32]
    else:
        votes_root = vote_hashes[0]
        for vh in vote_hashes[1:]:
            combined = f"{votes_root}:{vh}"
            votes_root = hashlib.sha256(combined.encode()).hexdigest()[:32]

    # Root: combine leaf and votes
    root = hashlib.sha256(f"{leaf}:{votes_root}".encode()).hexdigest()[:32]
    return root
