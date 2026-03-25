"""Tests for DAG Compiler — GoalSpec to TaskDAG compilation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from constitutional_swarm.compiler import DAGCompiler, GoalSpec, _deterministic_node_id
from constitutional_swarm.swarm import NodeStatus


class TestGoalSpec:
    """Test GoalSpec dataclass."""

    def test_goalspec_frozen(self) -> None:
        spec = GoalSpec(goal="test", domains=["d1"], steps=[])
        assert spec.goal == "test"
        assert list(spec.domains) == ["d1"]

    def test_goalspec_with_steps(self) -> None:
        steps = [{"title": "Step A", "domain": "d1", "depends_on": []}]
        spec = GoalSpec(goal="g", domains=["d1"], steps=steps)
        assert len(spec.steps) == 1


class TestDeterministicNodeId:
    """Test deterministic ID generation."""

    def test_same_title_same_id(self) -> None:
        assert _deterministic_node_id("hello") == _deterministic_node_id("hello")

    def test_different_titles_different_ids(self) -> None:
        assert _deterministic_node_id("hello") != _deterministic_node_id("world")

    def test_id_is_8_hex_chars(self) -> None:
        node_id = _deterministic_node_id("test title")
        assert len(node_id) == 8
        int(node_id, 16)  # must be valid hex


class TestDAGCompiler:
    """Test DAGCompiler.compile()."""

    def _auth_spec(self) -> GoalSpec:
        return GoalSpec(
            goal="Build user authentication feature",
            domains=["backend", "frontend", "security", "qa"],
            steps=[
                {"title": "Design auth schema", "domain": "backend", "depends_on": []},
                {
                    "title": "Implement JWT middleware",
                    "domain": "backend",
                    "depends_on": ["Design auth schema"],
                },
                {
                    "title": "Build login UI",
                    "domain": "frontend",
                    "depends_on": ["Design auth schema"],
                },
                {
                    "title": "Security review",
                    "domain": "security",
                    "depends_on": ["Implement JWT middleware", "Build login UI"],
                },
                {
                    "title": "Integration tests",
                    "domain": "qa",
                    "depends_on": ["Security review"],
                },
            ],
        )

    def test_happy_path_compile(self) -> None:
        compiler = DAGCompiler()
        dag = compiler.compile(self._auth_spec())
        assert len(dag.nodes) == 5
        assert dag.goal == "Build user authentication feature"

    def test_ready_nodes_are_roots(self) -> None:
        compiler = DAGCompiler()
        dag = compiler.compile(self._auth_spec())
        dag = dag.mark_ready()
        ready = [n for n in dag.nodes.values() if n.status == NodeStatus.READY]
        assert len(ready) == 1
        assert ready[0].title == "Design auth schema"

    def test_deterministic_ids(self) -> None:
        compiler = DAGCompiler()
        dag1 = compiler.compile(self._auth_spec())
        dag2 = compiler.compile(self._auth_spec())
        ids1 = sorted(dag1.nodes.keys())
        ids2 = sorted(dag2.nodes.keys())
        assert ids1 == ids2

    def test_cycle_detection_simple(self) -> None:
        spec = GoalSpec(
            goal="cyclic",
            domains=["d"],
            steps=[
                {"title": "A", "domain": "d", "depends_on": ["B"]},
                {"title": "B", "domain": "d", "depends_on": ["A"]},
            ],
        )
        compiler = DAGCompiler()
        with pytest.raises(ValueError, match="Cycle detected"):
            compiler.compile(spec)

    def test_cycle_detection_three_node(self) -> None:
        spec = GoalSpec(
            goal="cyclic3",
            domains=["d"],
            steps=[
                {"title": "A", "domain": "d", "depends_on": ["C"]},
                {"title": "B", "domain": "d", "depends_on": ["A"]},
                {"title": "C", "domain": "d", "depends_on": ["B"]},
            ],
        )
        compiler = DAGCompiler()
        with pytest.raises(ValueError, match="Cycle detected"):
            compiler.compile(spec)

    def test_missing_dependency(self) -> None:
        spec = GoalSpec(
            goal="missing",
            domains=["d"],
            steps=[
                {"title": "A", "domain": "d", "depends_on": ["Nonexistent"]},
            ],
        )
        compiler = DAGCompiler()
        with pytest.raises(ValueError, match="does not exist"):
            compiler.compile(spec)

    def test_empty_spec(self) -> None:
        spec = GoalSpec(goal="empty", domains=[], steps=[])
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        assert len(dag.nodes) == 0
        assert dag.goal == "empty"

    def test_single_node(self) -> None:
        spec = GoalSpec(
            goal="single",
            domains=["d"],
            steps=[{"title": "Only task", "domain": "d", "depends_on": []}],
        )
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        assert len(dag.nodes) == 1
        dag = dag.mark_ready()
        ready = [n for n in dag.nodes.values() if n.status == NodeStatus.READY]
        assert len(ready) == 1

    def test_diamond_dag(self) -> None:
        """A -> B, C -> D (diamond shape)."""
        spec = GoalSpec(
            goal="diamond",
            domains=["d"],
            steps=[
                {"title": "A", "domain": "d", "depends_on": []},
                {"title": "B", "domain": "d", "depends_on": ["A"]},
                {"title": "C", "domain": "d", "depends_on": ["A"]},
                {"title": "D", "domain": "d", "depends_on": ["B", "C"]},
            ],
        )
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        assert len(dag.nodes) == 4

        # Only A should be ready initially
        dag = dag.mark_ready()
        ready = [n for n in dag.nodes.values() if n.status == NodeStatus.READY]
        assert len(ready) == 1
        assert ready[0].title == "A"

    def test_linear_chain(self) -> None:
        steps = [
            {"title": f"Step-{i}", "domain": "d", "depends_on": (
                [f"Step-{i - 1}"] if i > 0 else []
            )}
            for i in range(5)
        ]
        spec = GoalSpec(goal="linear", domains=["d"], steps=steps)
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        assert len(dag.nodes) == 5

        # Walk the chain
        dag = dag.mark_ready()
        ready = [n for n in dag.nodes.values() if n.status == NodeStatus.READY]
        assert len(ready) == 1
        assert ready[0].title == "Step-0"

    def test_duplicate_titles_rejected(self) -> None:
        spec = GoalSpec(
            goal="dupes",
            domains=["d"],
            steps=[
                {"title": "Same", "domain": "d", "depends_on": []},
                {"title": "Same", "domain": "d", "depends_on": []},
            ],
        )
        compiler = DAGCompiler()
        with pytest.raises(ValueError, match="Duplicate step title"):
            compiler.compile(spec)

    def test_large_dag_100_nodes(self) -> None:
        """100-node DAG compiles without error."""
        steps = [
            {"title": f"Task-{i}", "domain": "d", "depends_on": (
                [f"Task-{i - 1}"] if i > 0 else []
            )}
            for i in range(100)
        ]
        spec = GoalSpec(goal="large", domains=["d"], steps=steps)
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        assert len(dag.nodes) == 100

    def test_optional_fields_propagated(self) -> None:
        spec = GoalSpec(
            goal="optional",
            domains=["d"],
            steps=[
                {
                    "title": "A",
                    "domain": "d",
                    "depends_on": [],
                    "required_capabilities": ["code_review"],
                    "priority": 5,
                    "max_budget_tokens": 1000,
                },
            ],
        )
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        node = next(iter(dag.nodes.values()))
        assert node.required_capabilities == ("code_review",)
        assert node.priority == 5
        assert node.max_budget_tokens == 1000

    def test_empty_domain_rejected(self) -> None:
        spec = GoalSpec(goal="bad", domains=["", "d"], steps=[])
        compiler = DAGCompiler()
        with pytest.raises(ValueError, match="non-empty"):
            compiler.compile(spec)


class TestDAGCompilerYAML:
    """Test YAML loading."""

    def test_compile_from_yaml(self) -> None:
        yaml_content = """\
goal: Build feature
domains:
  - backend
  - frontend
steps:
  - title: Design API
    domain: backend
    depends_on: []
  - title: Build UI
    domain: frontend
    depends_on:
      - Design API
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            path = Path(f.name)

        try:
            compiler = DAGCompiler()
            dag = compiler.compile_from_yaml(path)
            assert len(dag.nodes) == 2
            assert dag.goal == "Build feature"
        finally:
            path.unlink()

    def test_yaml_file_not_found(self) -> None:
        compiler = DAGCompiler()
        with pytest.raises(FileNotFoundError):
            compiler.compile_from_yaml("/nonexistent/path.yaml")

    def test_yaml_invalid_content(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("just a string, not a mapping")
            f.flush()
            path = Path(f.name)

        try:
            compiler = DAGCompiler()
            with pytest.raises(ValueError, match="mapping"):
                compiler.compile_from_yaml(path)
        finally:
            path.unlink()
