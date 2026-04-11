"""Tests for GovernanceWorkflowCompiler (Phase 1).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

# Skip if constitutional_swarm is not installed
try:
    from constitutional_swarm import DAGCompiler, GoalSpec  # noqa: F401

    SWARM_AVAILABLE = True
except ImportError:
    SWARM_AVAILABLE = False

pytestmark = pytest.mark.skipif(not SWARM_AVAILABLE, reason="constitutional_swarm not installed")

from acgs_lite.integrations.workflow import (  # noqa: E402
    GOVERNANCE_DOMAINS,
    WORKFLOW_AVAILABLE,
    GovernanceWorkflowCompiler,
)

# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def test_workflow_available_matches_swarm_install() -> None:
    assert WORKFLOW_AVAILABLE is True


def test_governance_domains_non_empty() -> None:
    assert len(GOVERNANCE_DOMAINS) > 0
    assert "validation" in GOVERNANCE_DOMAINS
    assert "audit" in GOVERNANCE_DOMAINS
    assert "compliance" in GOVERNANCE_DOMAINS


# ---------------------------------------------------------------------------
# compile() — valid specs
# ---------------------------------------------------------------------------


def test_compile_single_step() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Validate a single action",
        domains=["validation"],
        steps=[{"title": "validate", "domain": "validation", "depends_on": []}],
    )
    dag = compiler.compile(spec)
    assert len(dag.nodes) == 1
    node = next(iter(dag.nodes.values()))
    assert node.title == "validate"
    assert node.domain == "validation"


def test_compile_linear_chain() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Validate then audit",
        domains=["validation", "audit"],
        steps=[
            {"title": "validate", "domain": "validation", "depends_on": []},
            {"title": "audit", "domain": "audit", "depends_on": ["validate"]},
        ],
    )
    dag = compiler.compile(spec)
    assert len(dag.nodes) == 2
    ready = dag.ready_nodes()
    assert len(ready) == 1
    assert ready[0].title == "validate"


def test_compile_parallel_branches() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Check compliance and stats in parallel, then audit",
        domains=["compliance", "stats", "audit"],
        steps=[
            {"title": "check-compliance", "domain": "compliance", "depends_on": []},
            {"title": "governance-stats", "domain": "stats", "depends_on": []},
            {
                "title": "audit-results",
                "domain": "audit",
                "depends_on": ["check-compliance", "governance-stats"],
            },
        ],
    )
    dag = compiler.compile(spec)
    assert len(dag.nodes) == 3
    ready = dag.ready_nodes()
    assert len(ready) == 2
    ready_titles = {n.title for n in ready}
    assert ready_titles == {"check-compliance", "governance-stats"}


# ---------------------------------------------------------------------------
# compile() — validation failures
# ---------------------------------------------------------------------------


def test_compile_rejects_unknown_domain() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Do something invalid",
        domains=["unknown-domain"],
        steps=[{"title": "step1", "domain": "unknown-domain", "depends_on": []}],
    )
    with pytest.raises(ValueError, match="unknown-domain"):
        compiler.compile(spec)


def test_compile_rejects_missing_domain() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Missing domain",
        domains=[],
        steps=[{"title": "step1", "depends_on": []}],  # no "domain" key
    )
    with pytest.raises(ValueError, match="missing a domain"):
        compiler.compile(spec)


def test_compile_rejects_empty_domain() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Empty domain",
        domains=[],
        steps=[{"title": "step1", "domain": "", "depends_on": []}],
    )
    with pytest.raises(ValueError, match="missing a domain"):
        compiler.compile(spec)


def test_compile_rejects_cycle() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Cyclic workflow",
        domains=["validation", "audit"],
        steps=[
            {"title": "a", "domain": "validation", "depends_on": ["b"]},
            {"title": "b", "domain": "audit", "depends_on": ["a"]},
        ],
    )
    with pytest.raises(ValueError, match="[Cc]ycle"):
        compiler.compile(spec)


def test_compile_rejects_missing_dependency() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(
        goal="Missing dep",
        domains=["validation"],
        steps=[
            {"title": "step1", "domain": "validation", "depends_on": ["nonexistent"]},
        ],
    )
    with pytest.raises(ValueError):
        compiler.compile(spec)


def test_compile_empty_steps_returns_empty_dag() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    spec = GoalSpec(goal="Empty workflow", domains=[], steps=[])
    dag = compiler.compile(spec)
    assert len(dag.nodes) == 0


# ---------------------------------------------------------------------------
# compile_from_dict()
# ---------------------------------------------------------------------------


def test_compile_from_dict_basic() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    data = {
        "goal": "Validate then explain",
        "domains": ["validation", "explain"],
        "steps": [
            {"title": "validate", "domain": "validation", "depends_on": []},
            {"title": "explain", "domain": "explain", "depends_on": ["validate"]},
        ],
    }
    dag = compiler.compile_from_dict(data)
    assert len(dag.nodes) == 2


def test_compile_from_dict_rejects_unknown_domain() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    data = {
        "goal": "Bad domain",
        "domains": ["bad-domain"],
        "steps": [{"title": "s", "domain": "bad-domain", "depends_on": []}],
    }
    with pytest.raises(ValueError, match="bad-domain"):
        compiler.compile_from_dict(data)


def test_compile_from_dict_missing_goal_uses_empty_string() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    data = {
        "domains": ["validation"],
        "steps": [{"title": "v", "domain": "validation", "depends_on": []}],
    }
    dag = compiler.compile_from_dict(data)
    assert dag.goal == ""


# ---------------------------------------------------------------------------
# Constitutional hash validation
# ---------------------------------------------------------------------------


def test_constitutional_hash_stored() -> None:
    compiler = GovernanceWorkflowCompiler("608508a9bd224290")
    assert compiler.constitutional_hash == "608508a9bd224290"
