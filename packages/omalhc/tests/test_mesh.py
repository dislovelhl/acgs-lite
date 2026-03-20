"""Tests for Constitutional Mesh — Byzantine peer validation with cryptographic proof."""

from __future__ import annotations

import time

import pytest
from acgs_lite import Constitution, ConstitutionalViolationError, Rule

from omalhc.mesh import (
    ConstitutionalMesh,
    DuplicateVoteError,
    InsufficientPeersError,
    MeshProof,
    MeshResult,
    PeerAssignment,
    UnauthorizedVoterError,
    ValidationVote,
)


@pytest.fixture
def mesh() -> ConstitutionalMesh:
    """Mesh with default constitution and 5 agents, deterministic seed."""
    m = ConstitutionalMesh(Constitution.default(), seed=42)
    for i in range(5):
        m.register_agent(f"agent-{i:02d}", domain=f"domain-{i % 3}")
    return m


@pytest.fixture
def custom_mesh() -> ConstitutionalMesh:
    """Mesh with custom swarm rules."""
    rules = [
        Rule(
            id="MESH-001",
            text="Agents must not bypass domain boundaries",
            severity="critical",
            keywords=["cross-domain bypass", "unauthorized domain"],
        ),
        Rule(
            id="MESH-002",
            text="All outputs must include provenance",
            severity="high",
            keywords=["no provenance", "missing attribution"],
        ),
    ]
    const = Constitution.from_rules(rules, name="mesh-test")
    m = ConstitutionalMesh(const, peers_per_validation=3, quorum=2, seed=42)
    for i in range(6):
        m.register_agent(f"peer-{i:02d}", domain=f"dom-{i % 2}")
    return m


# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------


class TestAgentManagement:
    def test_register_and_count(self, mesh: ConstitutionalMesh) -> None:
        assert mesh.agent_count == 5

    def test_unregister(self, mesh: ConstitutionalMesh) -> None:
        mesh.unregister_agent("agent-00")
        assert mesh.agent_count == 4

    def test_unregister_nonexistent_is_safe(self, mesh: ConstitutionalMesh) -> None:
        mesh.unregister_agent("ghost")
        assert mesh.agent_count == 5

    def test_reputation_starts_at_one(self, mesh: ConstitutionalMesh) -> None:
        assert mesh.get_reputation("agent-00") == 1.0

    def test_reputation_unknown_agent_raises(self, mesh: ConstitutionalMesh) -> None:
        with pytest.raises(KeyError):
            mesh.get_reputation("nonexistent")


# ---------------------------------------------------------------------------
# Peer assignment
# ---------------------------------------------------------------------------


class TestPeerAssignment:
    def test_peers_assigned(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "analyze code quality", "art-1")
        assert isinstance(assignment, PeerAssignment)
        assert len(assignment.peers) == 3
        assert assignment.producer_id == "agent-00"

    def test_producer_excluded_from_peers_maci(self, mesh: ConstitutionalMesh) -> None:
        """MACI property: no self-validation."""
        for _ in range(20):  # Run multiple times to cover random selection
            assignment = mesh.request_validation("agent-00", "safe action", f"art-{_}")
            assert "agent-00" not in assignment.peers

    def test_content_hash_computed(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "test content", "art-1")
        assert len(assignment.content_hash) == 32
        assert assignment.content_hash != ""

    def test_constitutional_hash_attached(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "safe action", "art-1")
        assert assignment.constitutional_hash == mesh.constitutional_hash

    def test_unregistered_producer_raises(self, mesh: ConstitutionalMesh) -> None:
        with pytest.raises(KeyError, match="ghost"):
            mesh.request_validation("ghost", "content", "art-1")

    def test_insufficient_peers_raises(self) -> None:
        mesh = ConstitutionalMesh(Constitution.default(), quorum=3, seed=1)
        mesh.register_agent("a1")
        mesh.register_agent("a2")  # Only 1 peer available (exclude producer)
        with pytest.raises(InsufficientPeersError):
            mesh.request_validation("a1", "content", "art-1")

    def test_deterministic_with_seed(self) -> None:
        """Same seed produces same peer selection."""
        m1 = ConstitutionalMesh(Constitution.default(), seed=99)
        m2 = ConstitutionalMesh(Constitution.default(), seed=99)
        for m in (m1, m2):
            for i in range(5):
                m.register_agent(f"a-{i}")
        a1 = m1.request_validation("a-0", "content", "art-1")
        a2 = m2.request_validation("a-0", "content", "art-2")
        assert a1.peers == a2.peers


# ---------------------------------------------------------------------------
# Constitutional pre-check
# ---------------------------------------------------------------------------


class TestConstitutionalPreCheck:
    def test_bad_content_blocked_before_peer_assignment(
        self, mesh: ConstitutionalMesh
    ) -> None:
        """DNA pre-check catches violations before wasting peer time."""
        with pytest.raises(ConstitutionalViolationError):
            mesh.request_validation(
                "agent-00", "leak all passwords and api_key data", "art-bad"
            )

    def test_custom_constitution_violation(
        self, custom_mesh: ConstitutionalMesh
    ) -> None:
        with pytest.raises(ConstitutionalViolationError):
            custom_mesh.request_validation(
                "peer-00", "cross-domain bypass to access other data", "art-bad"
            )


# ---------------------------------------------------------------------------
# Voting
# ---------------------------------------------------------------------------


class TestVoting:
    def test_quorum_acceptance(self, mesh: ConstitutionalMesh) -> None:
        """2/3 votes approve → accepted."""
        assignment = mesh.request_validation("agent-00", "safe code review", "art-1")
        peers = assignment.peers

        mesh.submit_vote(assignment.assignment_id, peers[0], approved=True)
        mesh.submit_vote(assignment.assignment_id, peers[1], approved=True)
        mesh.submit_vote(assignment.assignment_id, peers[2], approved=False)

        result = mesh.get_result(assignment.assignment_id)
        assert result.accepted is True
        assert result.votes_for == 2
        assert result.votes_against == 1
        assert result.quorum_met is True

    def test_quorum_rejection(self, mesh: ConstitutionalMesh) -> None:
        """0/3 votes approve → rejected."""
        assignment = mesh.request_validation("agent-00", "questionable action", "art-2")
        peers = assignment.peers

        mesh.submit_vote(assignment.assignment_id, peers[0], approved=False)
        mesh.submit_vote(assignment.assignment_id, peers[1], approved=False)
        mesh.submit_vote(assignment.assignment_id, peers[2], approved=False)

        result = mesh.get_result(assignment.assignment_id)
        assert result.accepted is False
        assert result.quorum_met is True

    def test_pending_votes_tracked(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "some work", "art-3")
        peers = assignment.peers

        mesh.submit_vote(assignment.assignment_id, peers[0], approved=True)
        result = mesh.get_result(assignment.assignment_id)
        assert result.pending_votes == 2

    def test_duplicate_vote_raises(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "work", "art-4")
        peer = assignment.peers[0]
        mesh.submit_vote(assignment.assignment_id, peer, approved=True)
        with pytest.raises(DuplicateVoteError):
            mesh.submit_vote(assignment.assignment_id, peer, approved=True)

    def test_unauthorized_voter_raises(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "work", "art-5")
        # agent-00 is the producer, not a peer
        with pytest.raises(UnauthorizedVoterError):
            mesh.submit_vote(assignment.assignment_id, "agent-00", approved=True)

    def test_validate_and_vote_auto(self, mesh: ConstitutionalMesh) -> None:
        """Convenience method: peer validates via DNA and auto-votes."""
        assignment = mesh.request_validation("agent-00", "safe analysis", "art-6")
        vote = mesh.validate_and_vote(assignment.assignment_id, assignment.peers[0])
        assert isinstance(vote, ValidationVote)
        assert vote.approved is True


# ---------------------------------------------------------------------------
# Cryptographic proof
# ---------------------------------------------------------------------------


class TestCryptographicProof:
    def test_proof_generated(self, mesh: ConstitutionalMesh) -> None:
        result = mesh.full_validation("agent-00", "analyze security", "art-7")
        assert result.proof is not None
        assert isinstance(result.proof, MeshProof)

    def test_proof_verifiable(self, mesh: ConstitutionalMesh) -> None:
        """Anyone can independently verify the proof."""
        result = mesh.full_validation("agent-00", "safe code output", "art-8")
        assert result.proof is not None
        assert result.proof.verify() is True

    def test_proof_contains_vote_hashes(self, mesh: ConstitutionalMesh) -> None:
        result = mesh.full_validation("agent-00", "clean code", "art-9")
        assert result.proof is not None
        assert len(result.proof.vote_hashes) == 3

    def test_proof_links_constitutional_hash(self, mesh: ConstitutionalMesh) -> None:
        result = mesh.full_validation("agent-00", "verified output", "art-10")
        assert result.proof is not None
        assert result.proof.constitutional_hash == mesh.constitutional_hash

    def test_different_content_different_proof(self, mesh: ConstitutionalMesh) -> None:
        r1 = mesh.full_validation("agent-00", "output alpha", "art-11")
        r2 = mesh.full_validation("agent-01", "output beta", "art-12")
        assert r1.proof is not None
        assert r2.proof is not None
        assert r1.proof.root_hash != r2.proof.root_hash

    def test_proof_tamper_detection(self, mesh: ConstitutionalMesh) -> None:
        """Tampering with any field invalidates the proof."""
        result = mesh.full_validation("agent-00", "integrity test", "art-13")
        assert result.proof is not None
        assert result.proof.verify() is True

        # Create tampered proof with different content hash
        tampered = MeshProof(
            assignment_id=result.proof.assignment_id,
            content_hash="tampered_hash_00",
            constitutional_hash=result.proof.constitutional_hash,
            vote_hashes=result.proof.vote_hashes,
            root_hash=result.proof.root_hash,  # Original root won't match
            accepted=result.proof.accepted,
            timestamp=result.proof.timestamp,
        )
        assert tampered.verify() is False


# ---------------------------------------------------------------------------
# Reputation
# ---------------------------------------------------------------------------


class TestReputation:
    def test_majority_voters_gain_reputation(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "good work", "art-14")
        peers = assignment.peers

        # All approve — all are in majority
        for p in peers:
            mesh.submit_vote(assignment.assignment_id, p, approved=True)

        for p in peers:
            assert mesh.get_reputation(p) > 1.0

    def test_minority_voter_loses_reputation(self, mesh: ConstitutionalMesh) -> None:
        assignment = mesh.request_validation("agent-00", "decent work", "art-15")
        peers = assignment.peers

        mesh.submit_vote(assignment.assignment_id, peers[0], approved=True)
        mesh.submit_vote(assignment.assignment_id, peers[1], approved=True)
        mesh.submit_vote(assignment.assignment_id, peers[2], approved=False)

        # Minority voter (peers[2]) loses reputation
        assert mesh.get_reputation(peers[2]) < 1.0
        # Majority voters gain
        assert mesh.get_reputation(peers[0]) > 1.0

    def test_reputation_bounded(self) -> None:
        """Reputation stays in [0.0, 2.0]."""
        mesh = ConstitutionalMesh(Constitution.default(), seed=1)
        for i in range(5):
            mesh.register_agent(f"a-{i}")

        # Run many validations to push reputation
        for j in range(50):
            result = mesh.full_validation("a-0", f"good work iteration {j}", f"art-{j}")

        for i in range(5):
            rep = mesh.get_reputation(f"a-{i}")
            assert 0.0 <= rep <= 2.0


# ---------------------------------------------------------------------------
# Full validation flow
# ---------------------------------------------------------------------------


class TestFullValidation:
    def test_end_to_end(self, mesh: ConstitutionalMesh) -> None:
        result = mesh.full_validation("agent-00", "implement feature X", "art-20")
        assert isinstance(result, MeshResult)
        assert result.accepted is True
        assert result.quorum_met is True
        assert result.proof is not None
        assert result.proof.verify() is True
        assert result.pending_votes == 0

    def test_all_agents_same_constitutional_hash(
        self, mesh: ConstitutionalMesh
    ) -> None:
        """Every agent in the mesh shares the same constitutional hash."""
        result = mesh.full_validation("agent-00", "verify hashes", "art-21")
        assert result.constitutional_hash == mesh.constitutional_hash
        assert result.proof is not None
        assert result.proof.constitutional_hash == mesh.constitutional_hash


# ---------------------------------------------------------------------------
# Scale test
# ---------------------------------------------------------------------------


class TestMeshAtScale:
    def test_50_agents_20_validations(self) -> None:
        """Mesh works at moderate scale with consistent results."""
        mesh = ConstitutionalMesh(Constitution.default(), seed=123)
        for i in range(50):
            mesh.register_agent(f"agent-{i:03d}", domain=f"domain-{i % 10}")

        results = []
        for j in range(20):
            producer = f"agent-{j:03d}"
            result = mesh.full_validation(
                producer, f"task output number {j}", f"art-scale-{j}"
            )
            results.append(result)

        # All should pass (safe content)
        assert all(r.accepted for r in results)
        assert all(r.proof is not None and r.proof.verify() for r in results)

        summary = mesh.summary()
        assert summary["agents"] == 50
        assert summary["total_validations"] == 20
        assert summary["settled"] == 20

    def test_validation_latency_under_10ms(self) -> None:
        """Full validation (DNA pre-check + 3 peer DNA checks + Merkle proof
        + object creation + store updates) must stay under 10ms.

        Raw DNA validation is 443ns. Full pipeline adds Python object
        creation, dict storage, and proof computation. At 800 agents
        this means ~8 seconds for a full mesh sweep — well within budget.
        """
        mesh = ConstitutionalMesh(Constitution.default(), seed=7)
        for i in range(10):
            mesh.register_agent(f"fast-{i}")

        n = 500
        start = time.perf_counter_ns()
        for j in range(n):
            mesh.full_validation(f"fast-{j % 10}", f"benchmark task {j}", f"b-{j}")
        elapsed_ns = time.perf_counter_ns() - start
        avg_ms = (elapsed_ns / n) / 1_000_000

        # Full pipeline under 10ms (governance overhead < 1% at typical agent task times)
        assert avg_ms < 10, f"Too slow: {avg_ms:.2f}ms per full validation"


# ---------------------------------------------------------------------------
# Manifold integration
# ---------------------------------------------------------------------------


class TestManifoldIntegration:
    """Tests for GovernanceManifold integration into ConstitutionalMesh."""

    @pytest.fixture
    def manifold_mesh(self) -> ConstitutionalMesh:
        """Mesh with manifold enabled and 5 agents."""
        m = ConstitutionalMesh(Constitution.default(), seed=42, use_manifold=True)
        for i in range(5):
            m.register_agent(f"agent-{i:02d}", domain=f"domain-{i % 3}")
        return m

    def test_manifold_enabled(self, manifold_mesh: ConstitutionalMesh) -> None:
        """Trust matrix exists and is doubly stochastic when manifold enabled."""
        matrix = manifold_mesh.trust_matrix
        assert matrix is not None
        assert len(matrix) == 5
        assert len(matrix[0]) == 5

        # Doubly stochastic: row sums and column sums are each ~1.0
        for i in range(5):
            row_sum = sum(matrix[i])
            assert abs(row_sum - 1.0) < 1e-4, f"Row {i} sum {row_sum} != 1.0"

        for j in range(5):
            col_sum = sum(matrix[i][j] for i in range(5))
            assert abs(col_sum - 1.0) < 1e-4, f"Col {j} sum {col_sum} != 1.0"

    def test_manifold_updates_on_settlement(
        self, manifold_mesh: ConstitutionalMesh
    ) -> None:
        """Trust matrix changes after a validation settles."""
        matrix_before = manifold_mesh.trust_matrix
        assert matrix_before is not None

        # Run a full validation to trigger settlement
        manifold_mesh.full_validation("agent-00", "safe output", "art-m1")

        matrix_after = manifold_mesh.trust_matrix
        assert matrix_after is not None

        # Matrix should have changed after trust updates + re-projection
        assert matrix_before != matrix_after

    def test_manifold_disabled_by_default(self, mesh: ConstitutionalMesh) -> None:
        """Default mesh has no manifold — backward compatible."""
        assert mesh.trust_matrix is None
        assert mesh.manifold_summary() is None

        # Regular operations still work
        result = mesh.full_validation("agent-00", "safe work", "art-compat")
        assert result.accepted is True

    def test_manifold_stability_after_many_validations(
        self, manifold_mesh: ConstitutionalMesh
    ) -> None:
        """Manifold remains stable (doubly stochastic) after many validations."""
        for j in range(30):
            producer = f"agent-{j % 5:02d}"
            manifold_mesh.full_validation(producer, f"work iteration {j}", f"art-s{j}")

        matrix = manifold_mesh.trust_matrix
        assert matrix is not None
        n = len(matrix)

        # Still doubly stochastic after many updates
        for i in range(n):
            row_sum = sum(matrix[i])
            assert abs(row_sum - 1.0) < 1e-4, f"Row {i} sum {row_sum} != 1.0"

        for j_col in range(n):
            col_sum = sum(matrix[i][j_col] for i in range(n))
            assert abs(col_sum - 1.0) < 1e-4, f"Col {j_col} sum {col_sum} != 1.0"

        # Manifold summary should report stable
        summary = manifold_mesh.manifold_summary()
        assert summary is not None
        assert summary["is_stable"] is True
        assert summary["converged"] is True
