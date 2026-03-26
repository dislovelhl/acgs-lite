"""Cross-package integration tests for constitutional_swarm and acgs_lite."""

from __future__ import annotations

import pytest
from constitutional_swarm import AgentDNA, ConstitutionalMesh

from acgs_lite import Constitution, Rule

pytestmark = pytest.mark.integration


def _register_mesh_agents(mesh: ConstitutionalMesh, count: int = 5) -> None:
    for index in range(count):
        mesh.register_agent(f"agent-{index}", domain=f"domain-{index % 2}")


def test_default_constitution_flows_through_dna_and_mesh() -> None:
    constitution = Constitution.default()
    dna = AgentDNA(constitution=constitution, agent_id="dna-agent", strict=False)
    mesh = ConstitutionalMesh(constitution, seed=7)
    _register_mesh_agents(mesh)

    validation = dna.validate("safe collaborative planning update")
    assignment = mesh.request_validation("agent-0", "safe governance planning update", "art-1")
    result = mesh.full_validation("agent-1", "safe peer-reviewed governance note", "art-2")

    assert validation.constitutional_hash == constitution.hash
    assert assignment.constitutional_hash == constitution.hash
    assert result.constitutional_hash == constitution.hash
    assert result.proof is not None
    assert result.proof.constitutional_hash == constitution.hash


def test_custom_acgs_lite_rules_drive_mesh_validation_flow() -> None:
    constitution = Constitution.from_rules(
        [
            Rule(
                id="SWARM-001",
                text="Outputs must not omit provenance",
                severity="high",
                keywords=["missing provenance"],
            ),
            Rule(
                id="SWARM-002",
                text="Outputs must not propose unsafe bypasses",
                severity="critical",
                keywords=["unsafe bypass"],
            ),
        ],
        name="constitutional-swarm-integration",
    )
    mesh = ConstitutionalMesh(constitution, seed=11)
    _register_mesh_agents(mesh)

    result = mesh.full_validation(
        "agent-0",
        "safe governance review with clear provenance",
        "art-3",
    )

    assert result.accepted is True
    assert result.quorum_met is True
    assert result.proof is not None
    assert result.proof.constitutional_hash == constitution.hash
    assert result.proof.verify() is True
