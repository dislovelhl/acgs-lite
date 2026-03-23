"""Tests for kill switch (EU AI Act Art. 14(3)) and thread safety."""

from __future__ import annotations

import threading

import pytest
from acgs_lite import Constitution, ConstitutionalViolationError

from constitutional_swarm.dna import AgentDNA, DNADisabledError
from constitutional_swarm.mesh import ConstitutionalMesh, DuplicateVoteError, MeshHaltedError


# ---------------------------------------------------------------------------
# AgentDNA kill switch
# ---------------------------------------------------------------------------


class TestDNAKillSwitch:
    def test_disable_blocks_validation(self) -> None:
        dna = AgentDNA.default(agent_id="test-agent")
        dna.disable()
        with pytest.raises(DNADisabledError, match="disabled"):
            dna.validate("safe action")

    def test_enable_restores_validation(self) -> None:
        dna = AgentDNA.default(agent_id="test-agent")
        dna.disable()
        dna.enable()
        result = dna.validate("safe action")
        assert result.valid is True

    def test_is_disabled_property(self) -> None:
        dna = AgentDNA.default()
        assert dna.is_disabled is False
        dna.disable()
        assert dna.is_disabled is True
        dna.enable()
        assert dna.is_disabled is False

    def test_disable_blocks_govern_decorator(self) -> None:
        dna = AgentDNA.default(agent_id="governed")

        @dna.govern
        def my_agent(input: str) -> str:
            return f"processed: {input}"

        # Works before disable
        assert my_agent("hello") == "processed: hello"

        # Blocked after disable
        dna.disable()
        with pytest.raises(DNADisabledError):
            my_agent("hello")

    def test_double_disable_is_safe(self) -> None:
        dna = AgentDNA.default()
        dna.disable()
        dna.disable()  # No error
        assert dna.is_disabled is True

    def test_double_enable_is_safe(self) -> None:
        dna = AgentDNA.default()
        dna.enable()
        dna.enable()  # No error
        assert dna.is_disabled is False


# ---------------------------------------------------------------------------
# ConstitutionalMesh kill switch
# ---------------------------------------------------------------------------


class TestMeshKillSwitch:
    @pytest.fixture
    def mesh(self) -> ConstitutionalMesh:
        m = ConstitutionalMesh(Constitution.default(), seed=42)
        for i in range(5):
            m.register_agent(f"agent-{i:02d}")
        return m

    def test_halt_blocks_request_validation(self, mesh: ConstitutionalMesh) -> None:
        mesh.halt()
        with pytest.raises(MeshHaltedError):
            mesh.request_validation("agent-00", "safe content", "art-1")

    def test_halt_blocks_submit_vote(self, mesh: ConstitutionalMesh) -> None:
        # Create assignment before halt
        assignment = mesh.request_validation("agent-00", "safe content", "art-1")
        mesh.halt()
        with pytest.raises(MeshHaltedError):
            mesh.submit_vote(assignment.assignment_id, assignment.peers[0], approved=True)

    def test_halt_blocks_full_validation(self, mesh: ConstitutionalMesh) -> None:
        mesh.halt()
        with pytest.raises(MeshHaltedError):
            mesh.full_validation("agent-00", "safe content", "art-1")

    def test_resume_restores_operations(self, mesh: ConstitutionalMesh) -> None:
        mesh.halt()
        mesh.resume()
        result = mesh.full_validation("agent-00", "safe content", "art-1")
        assert result.accepted is True

    def test_is_halted_property(self, mesh: ConstitutionalMesh) -> None:
        assert mesh.is_halted is False
        mesh.halt()
        assert mesh.is_halted is True
        mesh.resume()
        assert mesh.is_halted is False

    def test_get_result_works_while_halted(self, mesh: ConstitutionalMesh) -> None:
        """Read-only operations still work during halt."""
        result = mesh.full_validation("agent-00", "safe output", "art-1")
        mesh.halt()
        # Can still read results
        fetched = mesh.get_result(result.assignment_id)
        assert fetched.accepted is True

    def test_register_works_while_halted(self, mesh: ConstitutionalMesh) -> None:
        """Agent registration still works during halt (admin operation)."""
        mesh.halt()
        mesh.register_agent("new-agent")
        assert mesh.agent_count == 6

    def test_summary_works_while_halted(self, mesh: ConstitutionalMesh) -> None:
        mesh.halt()
        summary = mesh.summary()
        assert summary["agents"] == 5


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestMeshThreadSafety:
    def test_concurrent_registrations(self) -> None:
        """Multiple threads registering agents concurrently."""
        mesh = ConstitutionalMesh(Constitution.default(), seed=1)
        errors: list[Exception] = []

        def register_batch(start: int, count: int) -> None:
            try:
                for i in range(start, start + count):
                    mesh.register_agent(f"agent-{i:04d}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_batch, args=(i * 20, 20))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert mesh.agent_count == 100

    def test_concurrent_validations(self) -> None:
        """Multiple threads running validations concurrently."""
        mesh = ConstitutionalMesh(Constitution.default(), seed=7)
        for i in range(20):
            mesh.register_agent(f"agent-{i:02d}")

        results: list[bool] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def validate_batch(start: int, count: int) -> None:
            try:
                for j in range(start, start + count):
                    producer = f"agent-{j % 20:02d}"
                    r = mesh.full_validation(producer, f"safe work {j}", f"art-{j}")
                    with lock:
                        results.append(r.accepted)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [
            threading.Thread(target=validate_batch, args=(i * 10, 10))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 40
        assert all(results)

    def test_concurrent_duplicate_vote_same_voter(self) -> None:
        mesh = ConstitutionalMesh(Constitution.default(), seed=11)
        for i in range(5):
            mesh.register_agent(f"agent-{i:02d}")

        assignment = mesh.request_validation("agent-00", "safe content", "art-dup")
        voter = assignment.peers[0]
        errors: list[Exception] = []
        successes = 0
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        def submit_vote() -> None:
            nonlocal successes
            try:
                barrier.wait()
                mesh.submit_vote(assignment.assignment_id, voter, approved=True)
                with lock:
                    successes += 1
            except DuplicateVoteError as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=submit_vote) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert successes == 1
        assert len(errors) == 1
