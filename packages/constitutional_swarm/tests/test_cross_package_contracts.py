"""Stable cross-package contracts for constitutional_swarm."""

from __future__ import annotations

import pytest
from constitutional_swarm import AgentDNA, ConstitutionalMesh, MeshProof, MeshResult, PeerAssignment

from acgs_lite import Constitution

pytestmark = pytest.mark.contract


def _register_mesh_agents(mesh: ConstitutionalMesh, count: int = 5) -> None:
    for index in range(count):
        mesh.register_agent(f"agent-{index}", domain=f"domain-{index % 2}")


def test_public_api_accepts_acgs_lite_constitution_instances() -> None:
    constitution = Constitution.default()
    dna = AgentDNA(constitution=constitution, agent_id="contract-agent")
    mesh = ConstitutionalMesh(constitution, seed=13)

    assert dna.hash == constitution.hash
    assert mesh.constitutional_hash == constitution.hash


def test_assignment_and_result_preserve_constitutional_hash_contract() -> None:
    constitution = Constitution.default()
    mesh = ConstitutionalMesh(constitution, seed=17)
    _register_mesh_agents(mesh)

    assignment = mesh.request_validation("agent-0", "safe governance contract check", "art-4")
    result = mesh.full_validation("agent-1", "safe governance contract verification", "art-5")

    assert isinstance(assignment, PeerAssignment)
    assert assignment.constitutional_hash == constitution.hash
    assert isinstance(result, MeshResult)
    assert result.constitutional_hash == constitution.hash
    assert isinstance(result.proof, MeshProof)
    assert result.proof.constitutional_hash == constitution.hash
    assert result.proof.verify() is True
