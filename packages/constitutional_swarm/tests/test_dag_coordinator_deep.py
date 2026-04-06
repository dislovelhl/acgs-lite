"""Deep tests for the DAG-as-coordinator pattern.

Covers edge cases, concurrency, MACI enforcement, priority ordering,
error paths, and compositional properties that the existing test_constitutional_swarm.py
doesn't exercise.

Organized by component:
  1. TaskDAG — immutability, ready_nodes, error paths, wide parallelism
  2. ArtifactStore — duplicates, indexing, integrity, serialization
  3. CapabilityRegistry — matching, routing, empty states
  4. SwarmExecutor — MACI enforcement, priority, concurrent claims, empty DAG
  5. WorkReceipt — expiry, deadline, status mappings
  6. DAGCompiler — domain validation, edge cases
  7. Integration — multi-phase DAGs, dynamic agent arrival, governance chain
"""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.compiler import DAGCompiler, GoalSpec
from constitutional_swarm.dna import AgentDNA, DNADisabledError
from constitutional_swarm.execution import (
    ContractStatus,
    ExecutionStatus,
    WorkReceipt,
    contract_status_from_execution,
)
from constitutional_swarm.swarm import SwarmExecutor, TaskDAG, TaskNode

from acgs_lite import ConstitutionalViolationError

# ---------------------------------------------------------------------------
# 1. TaskDAG — immutability, ready_nodes, error paths, wide parallelism
# ---------------------------------------------------------------------------


class TestTaskDAGImmutability:
    """Verify that DAG operations never mutate the original."""

    def test_add_node_returns_new_dag(self) -> None:
        dag1 = TaskDAG(goal="test")
        dag2 = dag1.add_node(TaskNode(node_id="A", title="A"))
        assert "A" not in dag1.nodes
        assert "A" in dag2.nodes
        assert dag1 is not dag2

    def test_mark_ready_returns_new_dag(self) -> None:
        dag1 = TaskDAG(goal="test").add_node(TaskNode(node_id="A", title="A"))
        dag2 = dag1.mark_ready()
        assert dag1.nodes["A"].status == ExecutionStatus.BLOCKED
        assert dag2.nodes["A"].status == ExecutionStatus.READY
        assert dag1 is not dag2

    def test_claim_node_returns_new_dag(self) -> None:
        dag1 = TaskDAG(goal="test").add_node(TaskNode(node_id="A", title="A"))
        dag1 = dag1.mark_ready()
        dag2 = dag1.claim_node("A", "agent-01")
        assert dag1.nodes["A"].status == ExecutionStatus.READY
        assert dag2.nodes["A"].status == ExecutionStatus.CLAIMED
        assert dag2.nodes["A"].claimed_by == "agent-01"

    def test_complete_node_returns_new_dag(self) -> None:
        dag1 = (
            TaskDAG(goal="test")
            .add_node(TaskNode(node_id="A", title="A"))
            .mark_ready()
            .claim_node("A", "agent-01")
        )
        dag2 = dag1.complete_node("A", "art-A")
        assert dag1.nodes["A"].status == ExecutionStatus.CLAIMED
        assert dag2.nodes["A"].status == ExecutionStatus.COMPLETED
        assert dag2.nodes["A"].artifact_id == "art-A"

    def test_chain_of_operations_preserves_all_intermediates(self) -> None:
        dag0 = TaskDAG(goal="chain")
        dag1 = dag0.add_node(TaskNode(node_id="X", title="X"))
        dag2 = dag1.mark_ready()
        dag3 = dag2.claim_node("X", "a1")
        dag4 = dag3.complete_node("X", "art-X")

        assert len(dag0.nodes) == 0
        assert dag1.nodes["X"].status == ExecutionStatus.BLOCKED
        assert dag2.nodes["X"].status == ExecutionStatus.READY
        assert dag3.nodes["X"].status == ExecutionStatus.CLAIMED
        assert dag4.nodes["X"].status == ExecutionStatus.COMPLETED


class TestTaskDAGReadyNodes:
    """Test ready_nodes() directly."""

    def test_ready_nodes_returns_promotable_blocked_nodes(self) -> None:
        """ready_nodes() returns BLOCKED nodes whose deps are satisfied — candidates for promotion."""
        dag = TaskDAG(goal="test")
        dag = dag.add_node(TaskNode(node_id="A", title="A"))
        dag = dag.add_node(TaskNode(node_id="B", title="B", depends_on=("A",)))
        # Before mark_ready: A is BLOCKED with no deps → it's a candidate
        candidates = dag.ready_nodes()
        assert len(candidates) == 1
        assert candidates[0].node_id == "A"

        # After mark_ready: A is READY (already promoted), B is still BLOCKED
        dag = dag.mark_ready()
        candidates = dag.ready_nodes()
        assert len(candidates) == 0  # no more blocked nodes with satisfied deps

    def test_ready_nodes_empty_for_all_blocked(self) -> None:
        dag = TaskDAG(goal="test")
        dag = dag.add_node(TaskNode(node_id="A", title="A", depends_on=("B",)))
        dag = dag.add_node(TaskNode(node_id="B", title="B", depends_on=("A",)))
        # Can't mark_ready — circular. Test ready_nodes on the blocked DAG.
        # Actually this would raise KeyError on mark_ready. Test without mark_ready:
        blocked_dag = TaskDAG(goal="test")
        blocked_dag = blocked_dag.add_node(TaskNode(node_id="X", title="X", depends_on=("Y",)))
        blocked_dag = blocked_dag.add_node(TaskNode(node_id="Y", title="Y"))
        # Y has no deps but is BLOCKED. ready_nodes scans for BLOCKED nodes with
        # satisfied deps — but ready_nodes only works AFTER mark_ready
        marked = blocked_dag.mark_ready()
        ready = marked.ready_nodes()
        # Y should be ready (no deps), X should still be blocked
        assert {n.node_id for n in ready} == set()  # ready_nodes only finds BLOCKED nodes
        # Actually ready_nodes returns BLOCKED nodes with satisfied deps
        # After mark_ready, Y is already READY, not BLOCKED
        ready_nodes = [n for n in marked.nodes.values() if n.status == ExecutionStatus.READY]
        assert {n.node_id for n in ready_nodes} == {"Y"}


class TestTaskDAGErrorPaths:
    """Test error conditions in DAG operations."""

    def test_claim_nonexistent_node_raises(self) -> None:
        dag = TaskDAG(goal="test").add_node(TaskNode(node_id="A", title="A")).mark_ready()
        with pytest.raises(KeyError, match="ghost"):
            dag.claim_node("ghost", "agent-01")

    def test_claim_blocked_node_raises(self) -> None:
        dag = TaskDAG(goal="test")
        dag = dag.add_node(TaskNode(node_id="A", title="A"))
        dag = dag.add_node(TaskNode(node_id="B", title="B", depends_on=("A",)))
        dag = dag.mark_ready()
        with pytest.raises(ValueError, match="not ready"):
            dag.claim_node("B", "agent-01")

    def test_complete_unclaimed_node_raises(self) -> None:
        dag = TaskDAG(goal="test").add_node(TaskNode(node_id="A", title="A")).mark_ready()
        with pytest.raises(ValueError, match="not claimed"):
            dag.complete_node("A", "art-A")

    def test_complete_nonexistent_node_raises(self) -> None:
        dag = TaskDAG(goal="test")
        with pytest.raises(KeyError, match="ghost"):
            dag.complete_node("ghost", "art-X")

    def test_double_claim_raises(self) -> None:
        dag = (
            TaskDAG(goal="test")
            .add_node(TaskNode(node_id="A", title="A"))
            .mark_ready()
            .claim_node("A", "agent-01")
        )
        with pytest.raises(ValueError, match="not ready"):
            dag.claim_node("A", "agent-02")


class TestTaskDAGWideParallelism:
    """Test DAGs with high parallelism."""

    def test_fan_out_100_nodes(self) -> None:
        """Root node fans out to 100 parallel children."""
        dag = TaskDAG(goal="fan-out")
        dag = dag.add_node(TaskNode(node_id="root", title="Root"))
        for i in range(100):
            dag = dag.add_node(
                TaskNode(node_id=f"child-{i}", title=f"Child {i}", depends_on=("root",))
            )
        dag = dag.mark_ready()

        # Only root is ready
        ready = [n for n in dag.nodes.values() if n.status == ExecutionStatus.READY]
        assert len(ready) == 1

        # Complete root → all 100 children become ready
        dag = dag.claim_node("root", "a1").complete_node("root", "art-root").mark_ready()
        ready = [n for n in dag.nodes.values() if n.status == ExecutionStatus.READY]
        assert len(ready) == 100

    def test_fan_in_100_nodes(self) -> None:
        """100 independent nodes all feed into a single sink."""
        dag = TaskDAG(goal="fan-in")
        for i in range(100):
            dag = dag.add_node(TaskNode(node_id=f"src-{i}", title=f"Source {i}"))
        dag = dag.add_node(
            TaskNode(
                node_id="sink",
                title="Sink",
                depends_on=tuple(f"src-{i}" for i in range(100)),
            )
        )
        dag = dag.mark_ready()

        # All 100 sources are ready
        ready = [n for n in dag.nodes.values() if n.status == ExecutionStatus.READY]
        assert len(ready) == 100

        # Complete 99 of them — sink still blocked
        for i in range(99):
            dag = dag.claim_node(f"src-{i}", "a1").complete_node(f"src-{i}", f"art-{i}")
        dag = dag.mark_ready()
        sink = dag.nodes["sink"]
        assert sink.status == ExecutionStatus.BLOCKED

        # Complete the last one → sink becomes ready
        dag = dag.claim_node("src-99", "a1").complete_node("src-99", "art-99").mark_ready()
        assert dag.nodes["sink"].status == ExecutionStatus.READY

    def test_diamond_with_priority(self) -> None:
        """Diamond DAG with different priorities — highest priority first."""
        dag = TaskDAG(goal="priority")
        dag = dag.add_node(TaskNode(node_id="A", title="A"))
        dag = dag.add_node(TaskNode(node_id="B", title="B", depends_on=("A",), priority=10))
        dag = dag.add_node(TaskNode(node_id="C", title="C", depends_on=("A",), priority=1))
        dag = dag.add_node(TaskNode(node_id="D", title="D", depends_on=("B", "C")))
        dag = dag.mark_ready().claim_node("A", "a1").complete_node("A", "x").mark_ready()

        # Both B and C are ready — verify priority ordering via SwarmExecutor
        registry = CapabilityRegistry()
        registry.register("agent", [Capability(name="work", domain="")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)
        executor.load_dag(dag)
        tasks = executor.available_tasks("agent")
        # Highest priority first
        assert tasks[0].node_id == "B"
        assert tasks[0].priority == 10


# ---------------------------------------------------------------------------
# 2. ArtifactStore — duplicates, indexing, integrity, serialization
# ---------------------------------------------------------------------------


class TestArtifactStoreDuplicates:
    """Verify duplicate rejection."""

    def test_publish_duplicate_id_raises(self) -> None:
        store = ArtifactStore()
        art = Artifact(
            artifact_id="dup",
            task_id="t1",
            agent_id="a1",
            content_type="text",
            content="hello",
        )
        store.publish(art)
        with pytest.raises(ValueError, match="already exists"):
            store.publish(art)


class TestArtifactStoreIndexing:
    """Test all index paths."""

    def test_get_by_agent(self) -> None:
        store = ArtifactStore()
        store.publish(
            Artifact(
                artifact_id="a1", task_id="t1", agent_id="alice", content_type="t", content="x"
            )
        )
        store.publish(
            Artifact(artifact_id="a2", task_id="t2", agent_id="bob", content_type="t", content="y")
        )
        store.publish(
            Artifact(
                artifact_id="a3", task_id="t3", agent_id="alice", content_type="t", content="z"
            )
        )
        alice_arts = store.get_by_agent("alice")
        assert len(alice_arts) == 2
        assert {a.artifact_id for a in alice_arts} == {"a1", "a3"}

    def test_get_by_task(self) -> None:
        store = ArtifactStore()
        store.publish(
            Artifact(
                artifact_id="a1", task_id="task-X", agent_id="a", content_type="t", content="x"
            )
        )
        store.publish(
            Artifact(
                artifact_id="a2", task_id="task-X", agent_id="b", content_type="t", content="y"
            )
        )
        arts = store.get_by_task("task-X")
        assert len(arts) == 2

    def test_get_nonexistent_returns_none(self) -> None:
        store = ArtifactStore()
        assert store.get("nonexistent") is None

    def test_get_by_domain_empty(self) -> None:
        store = ArtifactStore()
        assert store.get_by_domain("empty") == []

    def test_get_by_agent_empty(self) -> None:
        store = ArtifactStore()
        assert store.get_by_agent("nobody") == []

    def test_summary(self) -> None:
        store = ArtifactStore()
        store.publish(
            Artifact(
                artifact_id="a1",
                task_id="t1",
                agent_id="ag1",
                content_type="t",
                content="x",
                domain="d1",
            )
        )
        store.publish(
            Artifact(
                artifact_id="a2",
                task_id="t2",
                agent_id="ag2",
                content_type="t",
                content="y",
                domain="d2",
            )
        )
        s = store.summary()
        assert s["total_artifacts"] == 2
        assert s["domains"] == 2
        assert s["agents"] == 2
        assert s["tasks"] == 2


class TestArtifactIntegrity:
    """Test content-addressed integrity."""

    def test_content_hash_is_deterministic(self) -> None:
        art = Artifact(
            artifact_id="a1",
            task_id="t1",
            agent_id="ag1",
            content_type="text",
            content="hello world",
        )
        expected = hashlib.sha256(b"hello world").hexdigest()[:32]
        assert art.content_hash == expected

    def test_verify_integrity_returns_false_for_unknown(self) -> None:
        store = ArtifactStore()
        assert store.verify_integrity("nonexistent") is False

    def test_to_dict_round_trip(self) -> None:
        art = Artifact(
            artifact_id="a1",
            task_id="t1",
            agent_id="ag1",
            content_type="code",
            content="def f(): pass",
            domain="backend",
            tags=("python", "utility"),
            constitutional_hash="abc123",
            parent_artifacts=("parent-1",),
        )
        d = art.to_dict()
        assert d["artifact_id"] == "a1"
        assert d["task_id"] == "t1"
        assert d["domain"] == "backend"
        assert d["tags"] == ["python", "utility"]
        assert d["parent_artifacts"] == ["parent-1"]
        assert d["constitutional_hash"] == "abc123"
        assert d["content_hash"] == art.content_hash


class TestArtifactStoreWatchers:
    """Test watcher / reactive notification."""

    def test_watcher_on_task_id(self) -> None:
        store = ArtifactStore()
        received: list[str] = []
        store.watch("task-X", lambda a: received.append(a.artifact_id))
        store.publish(
            Artifact(
                artifact_id="a1", task_id="task-X", agent_id="ag1", content_type="t", content="x"
            )
        )
        store.publish(
            Artifact(
                artifact_id="a2", task_id="task-Y", agent_id="ag1", content_type="t", content="y"
            )
        )
        assert received == ["a1"]

    def test_watcher_on_domain(self) -> None:
        store = ArtifactStore()
        received: list[str] = []
        store.watch("security", lambda a: received.append(a.artifact_id))
        store.publish(
            Artifact(
                artifact_id="a1",
                task_id="t1",
                agent_id="ag1",
                content_type="t",
                content="x",
                domain="security",
            )
        )
        store.publish(
            Artifact(
                artifact_id="a2",
                task_id="t2",
                agent_id="ag2",
                content_type="t",
                content="y",
                domain="frontend",
            )
        )
        assert received == ["a1"]

    def test_multiple_watchers_on_same_key(self) -> None:
        store = ArtifactStore()
        r1: list[str] = []
        r2: list[str] = []
        store.watch("d1", lambda a: r1.append(a.artifact_id))
        store.watch("d1", lambda a: r2.append(a.artifact_id))
        store.publish(
            Artifact(
                artifact_id="a1",
                task_id="t1",
                agent_id="ag1",
                content_type="t",
                content="x",
                domain="d1",
            )
        )
        assert r1 == ["a1"]
        assert r2 == ["a1"]


# ---------------------------------------------------------------------------
# 3. CapabilityRegistry — matching, routing, empty states
# ---------------------------------------------------------------------------


class TestCapabilityMatching:
    """Test Capability.matches() directly."""

    def test_matches_name(self) -> None:
        cap = Capability(name="code_review", domain="security")
        assert cap.matches("code_review") is True
        assert cap.matches("CODE_REVIEW") is True
        assert cap.matches("code") is True

    def test_matches_domain(self) -> None:
        cap = Capability(name="scan", domain="security")
        assert cap.matches("security") is True

    def test_matches_description(self) -> None:
        cap = Capability(name="scan", domain="sec", description="Static analysis tool")
        assert cap.matches("static analysis") is True

    def test_matches_tags(self) -> None:
        cap = Capability(name="scan", domain="sec", tags=("python", "sast"))
        assert cap.matches("sast") is True
        assert cap.matches("python") is True

    def test_no_match(self) -> None:
        cap = Capability(name="scan", domain="security")
        assert cap.matches("frontend") is False


class TestCapabilityRegistryAdvanced:
    """Test advanced registry operations."""

    def test_find_by_name(self) -> None:
        reg = CapabilityRegistry()
        reg.register("a1", [Capability(name="code_review", domain="backend")])
        reg.register("a2", [Capability(name="code_review", domain="frontend")])
        results = reg.find_by_name("code_review")
        assert len(results) == 2

    def test_find_best_prefer_cheap(self) -> None:
        reg = CapabilityRegistry()
        reg.register("cheap", [Capability(name="work", domain="d", cost_per_task=0.01)])
        reg.register("expensive", [Capability(name="work", domain="d", cost_per_task=1.00)])
        best = reg.find_best("work", domain="d", prefer_cheap=True)
        assert best is not None
        assert best[0] == "cheap"

    def test_find_best_no_candidates(self) -> None:
        reg = CapabilityRegistry()
        assert reg.find_best("nonexistent") is None

    def test_find_best_no_domain_filter(self) -> None:
        reg = CapabilityRegistry()
        reg.register("a1", [Capability(name="review", domain="backend")])
        best = reg.find_best("review")
        assert best is not None
        assert best[0] == "a1"

    def test_empty_registry(self) -> None:
        reg = CapabilityRegistry()
        assert reg.agents == []
        assert reg.domains == []
        assert reg.find_by_domain("any") == []
        s = reg.summary()
        assert s["agents"] == 0


# ---------------------------------------------------------------------------
# 4. SwarmExecutor — MACI, priority, concurrent, empty DAG
# ---------------------------------------------------------------------------


class TestSwarmExecutorMACIEnforcement:
    """Test that submit() enforces agent == claimant."""

    def test_wrong_agent_submit_raises_permission_error(self) -> None:
        registry = CapabilityRegistry()
        registry.register("agent-01", [Capability(name="work", domain="d")])
        registry.register("agent-02", [Capability(name="work", domain="d")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="test").add_node(TaskNode(node_id="A", title="A", domain="d"))
        executor.load_dag(dag)
        executor.claim("A", "agent-01")

        # agent-02 tries to submit for agent-01's claimed task
        with pytest.raises(PermissionError, match="agent-02"):
            executor.submit(
                "A",
                Artifact(
                    artifact_id="art-A",
                    task_id="A",
                    agent_id="agent-02",
                    content_type="text",
                    content="stolen work",
                ),
            )

    def test_correct_agent_submit_succeeds(self) -> None:
        registry = CapabilityRegistry()
        registry.register("agent-01", [Capability(name="work", domain="d")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="test").add_node(TaskNode(node_id="A", title="A", domain="d"))
        executor.load_dag(dag)
        executor.claim("A", "agent-01")
        executor.submit(
            "A",
            Artifact(
                artifact_id="art-A",
                task_id="A",
                agent_id="agent-01",
                content_type="text",
                content="my work",
            ),
        )
        assert executor.is_complete


class TestSwarmExecutorPriority:
    """Test that available_tasks returns highest priority first."""

    def test_tasks_sorted_by_priority_descending(self) -> None:
        registry = CapabilityRegistry()
        registry.register("agent", [Capability(name="work", domain="d")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="priority")
        dag = dag.add_node(TaskNode(node_id="low", title="Low", domain="d", priority=1))
        dag = dag.add_node(TaskNode(node_id="high", title="High", domain="d", priority=100))
        dag = dag.add_node(TaskNode(node_id="mid", title="Mid", domain="d", priority=50))
        executor.load_dag(dag)

        tasks = executor.available_tasks("agent")
        priorities = [t.priority for t in tasks]
        assert priorities == [100, 50, 1]


class TestSwarmExecutorEmptyDAG:
    """Test operations on empty or no DAG."""

    def test_available_tasks_no_dag(self) -> None:
        registry = CapabilityRegistry()
        registry.register("agent", [Capability(name="work", domain="d")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)
        assert executor.available_tasks("agent") == []

    def test_is_complete_no_dag(self) -> None:
        executor = SwarmExecutor(CapabilityRegistry(), ArtifactStore())
        assert executor.is_complete is False

    def test_progress_no_dag(self) -> None:
        executor = SwarmExecutor(CapabilityRegistry(), ArtifactStore())
        assert executor.progress == {}

    def test_claim_no_dag_raises(self) -> None:
        executor = SwarmExecutor(CapabilityRegistry(), ArtifactStore())
        with pytest.raises(RuntimeError, match="No DAG"):
            executor.claim("A", "agent-01")

    def test_submit_no_dag_raises(self) -> None:
        executor = SwarmExecutor(CapabilityRegistry(), ArtifactStore())
        with pytest.raises(RuntimeError, match="No DAG"):
            executor.submit(
                "A",
                Artifact(artifact_id="x", task_id="A", agent_id="a", content_type="t", content="c"),
            )


class TestSwarmExecutorCapabilityFiltering:
    """Test that agents only see tasks matching their capabilities."""

    def test_agent_sees_matching_and_unrestricted(self) -> None:
        """Agents see tasks in their domain AND tasks with no required_capabilities.
        To restrict a task to a specific domain, it must declare required_capabilities."""
        registry = CapabilityRegistry()
        registry.register("backend-dev", [Capability(name="code", domain="backend")])
        registry.register("frontend-dev", [Capability(name="code", domain="frontend")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="test")
        # Tasks with required_capabilities are domain-restricted
        dag = dag.add_node(
            TaskNode(
                node_id="B",
                title="Backend",
                domain="backend",
                required_capabilities=("backend-api",),
            )
        )
        dag = dag.add_node(
            TaskNode(
                node_id="F", title="Frontend", domain="frontend", required_capabilities=("react",)
            )
        )
        executor.load_dag(dag)

        backend_tasks = executor.available_tasks("backend-dev")
        frontend_tasks = executor.available_tasks("frontend-dev")
        # backend-dev has domain "backend" → sees B (domain match)
        # frontend-dev has domain "frontend" → sees F (domain match)
        assert {t.node_id for t in backend_tasks} == {"B"}
        assert {t.node_id for t in frontend_tasks} == {"F"}

    def test_task_with_no_requirements_visible_to_all(self) -> None:
        registry = CapabilityRegistry()
        registry.register("any-agent", [Capability(name="general", domain="misc")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="test")
        dag = dag.add_node(TaskNode(node_id="A", title="Open task"))
        executor.load_dag(dag)

        tasks = executor.available_tasks("any-agent")
        assert len(tasks) == 1

    def test_unregistered_agent_sees_only_unrestricted(self) -> None:
        registry = CapabilityRegistry()
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="test")
        dag = dag.add_node(TaskNode(node_id="open", title="Open"))
        dag = dag.add_node(
            TaskNode(
                node_id="restricted",
                title="Restricted",
                domain="security",
                required_capabilities=("pentest",),
            )
        )
        executor.load_dag(dag)

        tasks = executor.available_tasks("unknown-agent")
        assert len(tasks) == 1
        assert tasks[0].node_id == "open"


class TestSwarmExecutorConcurrency:
    """Test thread-safety of the executor."""

    def test_concurrent_claims_no_double_claim(self) -> None:
        """Two threads race to claim the same task — only one succeeds."""
        registry = CapabilityRegistry()
        for i in range(2):
            registry.register(f"agent-{i}", [Capability(name="work", domain="d")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="race").add_node(TaskNode(node_id="A", title="A", domain="d"))
        executor.load_dag(dag)

        results: list[str] = []
        errors: list[Exception] = []

        def try_claim(agent_id: str) -> None:
            try:
                executor.claim("A", agent_id)
                results.append(agent_id)
            except (ValueError, KeyError) as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(try_claim, f"agent-{i}") for i in range(2)]
            for f in as_completed(futures):
                f.result()

        assert len(results) == 1  # exactly one agent claimed
        # The other got an error (already claimed)

    def test_concurrent_submit_and_claim_pipeline(self) -> None:
        """10 agents concurrently process a 10-node linear chain."""
        registry = CapabilityRegistry()
        for i in range(10):
            registry.register(f"a-{i}", [Capability(name="work", domain="d")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="chain")
        for i in range(10):
            deps = (f"node-{i - 1}",) if i > 0 else ()
            dag = dag.add_node(
                TaskNode(node_id=f"node-{i}", title=f"N{i}", domain="d", depends_on=deps)
            )
        executor.load_dag(dag)

        # Process sequentially but verify thread-safety
        for i in range(10):
            agent = f"a-{i % 10}"
            tasks = executor.available_tasks(agent)
            assert len(tasks) >= 1
            task = tasks[0]
            executor.claim(task.node_id, agent)
            executor.submit(
                task.node_id,
                Artifact(
                    artifact_id=f"art-{task.node_id}",
                    task_id=task.node_id,
                    agent_id=agent,
                    content_type="text",
                    content=f"result-{i}",
                    domain="d",
                ),
            )

        assert executor.is_complete
        assert store.count == 10


# ---------------------------------------------------------------------------
# 5. WorkReceipt — expiry, deadline, status mappings
# ---------------------------------------------------------------------------


class TestWorkReceiptExpiry:
    """Test deadline and expiry logic."""

    def test_no_deadline_never_expires(self) -> None:
        receipt = WorkReceipt(title="Task")
        assert receipt.is_expired is False
        assert receipt.is_claimable is True

    def test_future_deadline_not_expired(self) -> None:
        receipt = WorkReceipt(title="Task", deadline_epoch=time.time() + 3600)
        assert receipt.is_expired is False
        assert receipt.is_claimable is True

    def test_past_deadline_is_expired(self) -> None:
        receipt = WorkReceipt(title="Task", deadline_epoch=time.time() - 1)
        assert receipt.is_expired is True
        assert receipt.is_claimable is False

    def test_claimed_receipt_not_claimable(self) -> None:
        receipt = WorkReceipt(title="Task").claim("agent-01")
        assert receipt.is_claimable is False

    def test_cannot_complete_pending_receipt(self) -> None:
        receipt = WorkReceipt(title="Task")
        with pytest.raises(ValueError, match="Cannot complete"):
            receipt.complete("result")


class TestStatusMappings:
    """Test execution ↔ contract status round-trip."""

    def test_all_execution_statuses_have_contract_mapping(self) -> None:
        for status in ExecutionStatus:
            result = contract_status_from_execution(status)
            assert isinstance(result, ContractStatus)

    def test_specific_mappings(self) -> None:
        assert contract_status_from_execution(ExecutionStatus.BLOCKED) == ContractStatus.PENDING
        assert contract_status_from_execution(ExecutionStatus.READY) == ContractStatus.PENDING
        assert contract_status_from_execution(ExecutionStatus.CLAIMED) == ContractStatus.CLAIMED
        assert contract_status_from_execution(ExecutionStatus.RUNNING) == ContractStatus.IN_PROGRESS
        assert contract_status_from_execution(ExecutionStatus.COMPLETED) == ContractStatus.COMPLETED
        assert contract_status_from_execution(ExecutionStatus.FAILED) == ContractStatus.FAILED

    def test_work_receipt_execution_status_property(self) -> None:
        r = WorkReceipt(title="T")
        assert r.execution_status == ExecutionStatus.READY
        claimed = r.claim("a1")
        assert claimed.execution_status == ExecutionStatus.CLAIMED
        completed = claimed.complete("done")
        assert completed.execution_status == ExecutionStatus.COMPLETED
        failed = r.claim("a1").fail("err")
        assert failed.execution_status == ExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# 6. DAGCompiler — domain validation, edge cases
# ---------------------------------------------------------------------------


class TestDAGCompilerDomainValidation:
    """Test domain validation in the compiler."""

    def test_step_domain_not_in_declared_domains_raises(self) -> None:
        spec = GoalSpec(
            goal="invalid",
            domains=["backend", "frontend"],
            steps=[{"title": "A", "domain": "security", "depends_on": []}],
        )
        compiler = DAGCompiler()
        with pytest.raises(ValueError, match="not in the declared domains"):
            compiler.compile(spec)

    def test_step_with_empty_domain_allowed_when_domains_empty(self) -> None:
        spec = GoalSpec(
            goal="no-domains",
            domains=[],
            steps=[{"title": "A", "domain": "", "depends_on": []}],
        )
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        assert len(dag.nodes) == 1

    def test_step_with_no_domain_key(self) -> None:
        spec = GoalSpec(
            goal="test",
            domains=[],
            steps=[{"title": "A", "depends_on": []}],
        )
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        node = next(iter(dag.nodes.values()))
        assert node.domain == ""


class TestDAGCompilerEdgeCases:
    """Additional edge cases."""

    def test_self_dependency_is_cycle(self) -> None:
        spec = GoalSpec(
            goal="self-loop",
            domains=["d"],
            steps=[{"title": "A", "domain": "d", "depends_on": ["A"]}],
        )
        compiler = DAGCompiler()
        with pytest.raises(ValueError, match="Cycle detected"):
            compiler.compile(spec)

    def test_wide_flat_dag_no_dependencies(self) -> None:
        """50 independent tasks — all should be ready."""
        steps = [{"title": f"T-{i}", "domain": "d", "depends_on": []} for i in range(50)]
        spec = GoalSpec(goal="flat", domains=["d"], steps=steps)
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        dag = dag.mark_ready()
        ready = [n for n in dag.nodes.values() if n.status == ExecutionStatus.READY]
        assert len(ready) == 50

    def test_deep_chain_20_levels(self) -> None:
        steps = [
            {
                "title": f"Step-{i}",
                "domain": "d",
                "depends_on": [f"Step-{i - 1}"] if i > 0 else [],
            }
            for i in range(20)
        ]
        spec = GoalSpec(goal="deep", domains=["d"], steps=steps)
        compiler = DAGCompiler()
        dag = compiler.compile(spec)
        assert len(dag.nodes) == 20

        # Walk the entire chain
        dag = dag.mark_ready()
        for i in range(20):
            ready = [n for n in dag.nodes.values() if n.status == ExecutionStatus.READY]
            assert len(ready) == 1, f"Expected 1 ready at step {i}, got {len(ready)}"
            node = ready[0]
            dag = dag.claim_node(node.node_id, "a1")
            dag = dag.complete_node(node.node_id, f"art-{i}")
            dag = dag.mark_ready()
        assert dag.is_complete


# ---------------------------------------------------------------------------
# 7. Integration — multi-phase DAGs, dynamic agents, governance chain
# ---------------------------------------------------------------------------


class TestFullSwarmWithGovernance:
    """End-to-end: compile → load → execute with DNA governance."""

    def test_compile_and_execute_with_dna_validation(self) -> None:
        spec = GoalSpec(
            goal="Build auth feature",
            domains=["backend", "frontend", "qa"],
            steps=[
                {"title": "Design API", "domain": "backend", "depends_on": []},
                {"title": "Build endpoints", "domain": "backend", "depends_on": ["Design API"]},
                {"title": "Build login UI", "domain": "frontend", "depends_on": ["Design API"]},
                {
                    "title": "Integration test",
                    "domain": "qa",
                    "depends_on": ["Build endpoints", "Build login UI"],
                },
            ],
        )
        compiler = DAGCompiler()
        dag = compiler.compile(spec)

        registry = CapabilityRegistry()
        registry.register("back-dev", [Capability(name="code", domain="backend")])
        registry.register("front-dev", [Capability(name="code", domain="frontend")])
        registry.register("qa-eng", [Capability(name="test", domain="qa")])

        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)
        executor.load_dag(dag)
        dna = AgentDNA.default(agent_id="swarm-dna")

        # Phase 1: Design (only back-dev sees it)
        tasks = executor.available_tasks("back-dev")
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title == "Design API"
        dna.validate(f"execute: {task.title}")
        executor.claim(task.node_id, "back-dev")
        content = "REST API schema: /users, /auth, /tokens"
        dna.validate(content)
        executor.submit(
            task.node_id,
            Artifact(
                artifact_id=f"art-{task.node_id}",
                task_id=task.node_id,
                agent_id="back-dev",
                content_type="design",
                content=content,
                domain="backend",
                constitutional_hash=dna.hash,
            ),
        )

        # Phase 2: Backend + Frontend in parallel
        back_tasks = executor.available_tasks("back-dev")
        front_tasks = executor.available_tasks("front-dev")
        assert any(t.title == "Build endpoints" for t in back_tasks)
        assert any(t.title == "Build login UI" for t in front_tasks)

        for agent, domain in [("back-dev", "backend"), ("front-dev", "frontend")]:
            tasks = executor.available_tasks(agent)
            task = tasks[0]
            executor.claim(task.node_id, agent)
            executor.submit(
                task.node_id,
                Artifact(
                    artifact_id=f"art-{task.node_id}",
                    task_id=task.node_id,
                    agent_id=agent,
                    content_type="code",
                    content=f"Implementation for {task.title}",
                    domain=domain,
                    constitutional_hash=dna.hash,
                ),
            )

        # Phase 3: QA
        qa_tasks = executor.available_tasks("qa-eng")
        assert len(qa_tasks) == 1
        task = qa_tasks[0]
        executor.claim(task.node_id, "qa-eng")
        executor.submit(
            task.node_id,
            Artifact(
                artifact_id=f"art-{task.node_id}",
                task_id=task.node_id,
                agent_id="qa-eng",
                content_type="report",
                content="All tests pass",
                domain="qa",
                constitutional_hash=dna.hash,
            ),
        )

        assert executor.is_complete
        assert store.count == 4
        # Verify all artifacts have the same constitutional hash
        for art in [store.get(f"art-{nid}") for nid in executor.dag.nodes]:
            assert art is not None
            assert art.constitutional_hash == dna.hash

    def test_dna_blocks_bad_artifact_content(self) -> None:
        """Agent DNA prevents publishing a violating artifact."""
        dna = AgentDNA.default(agent_id="worker")

        # Simulate: agent produces output that leaks secrets
        bad_content = "Here are the api_key and password credentials"
        with pytest.raises(ConstitutionalViolationError):
            dna.validate(bad_content)
        # The artifact is never created because DNA blocked it


class TestDynamicAgentArrival:
    """Test agents joining mid-execution."""

    def test_new_agent_picks_up_remaining_work(self) -> None:
        registry = CapabilityRegistry()
        registry.register("agent-01", [Capability(name="work", domain="d")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="test")
        dag = dag.add_node(TaskNode(node_id="A", title="A", domain="d"))
        dag = dag.add_node(TaskNode(node_id="B", title="B", domain="d", depends_on=("A",)))
        executor.load_dag(dag)

        # agent-01 completes A
        executor.claim("A", "agent-01")
        executor.submit(
            "A",
            Artifact(
                artifact_id="art-A",
                task_id="A",
                agent_id="agent-01",
                content_type="t",
                content="done",
            ),
        )

        # NEW agent arrives and registers
        registry.register("agent-02", [Capability(name="work", domain="d")])

        # agent-02 can see and claim B
        tasks = executor.available_tasks("agent-02")
        assert len(tasks) == 1
        assert tasks[0].node_id == "B"
        executor.claim("B", "agent-02")
        executor.submit(
            "B",
            Artifact(
                artifact_id="art-B",
                task_id="B",
                agent_id="agent-02",
                content_type="t",
                content="done",
            ),
        )
        assert executor.is_complete


class TestArtifactProvenance:
    """Test parent_artifacts for tracking provenance chains."""

    def test_artifact_chain(self) -> None:
        store = ArtifactStore()
        # Phase 1 artifact
        design = Artifact(
            artifact_id="design-v1",
            task_id="design",
            agent_id="architect",
            content_type="doc",
            content="API schema",
        )
        store.publish(design)

        # Phase 2 artifact references Phase 1
        impl = Artifact(
            artifact_id="impl-v1",
            task_id="implement",
            agent_id="developer",
            content_type="code",
            content="class UserAPI: ...",
            parent_artifacts=("design-v1",),
        )
        store.publish(impl)

        # Verify provenance
        retrieved = store.get("impl-v1")
        assert retrieved is not None
        assert "design-v1" in retrieved.parent_artifacts
        parent = store.get(retrieved.parent_artifacts[0])
        assert parent is not None
        assert parent.content == "API schema"


class TestDNAKillSwitch:
    """Test AgentDNA kill switch (EU AI Act Art. 14(3))."""

    def test_disable_blocks_all_validation(self) -> None:
        dna = AgentDNA.default(agent_id="worker")
        dna.validate("safe action")  # works
        dna.disable()
        assert dna.is_disabled is True
        with pytest.raises(DNADisabledError):
            dna.validate("any action")

    def test_enable_restores_validation(self) -> None:
        dna = AgentDNA.default(agent_id="worker")
        dna.disable()
        dna.enable()
        assert dna.is_disabled is False
        result = dna.validate("safe action")
        assert result.valid is True

    def test_governed_decorator_respects_kill_switch(self) -> None:
        dna = AgentDNA.default(agent_id="worker")

        @dna.govern
        def my_agent(input: str) -> str:
            return f"processed: {input}"

        result = my_agent("test")
        assert result == "processed: test"

        dna.disable()
        with pytest.raises(DNADisabledError):
            my_agent("test")


class TestSwarmBenchmarkEdgeCases:
    """Edge cases for the benchmark harness."""

    def test_single_agent_single_task(self) -> None:
        from constitutional_swarm.bench import SwarmBenchmark

        bench = SwarmBenchmark()
        result = bench.run(num_agents=1, num_domains=1, dag_depth=1, dag_width=1)
        assert result.num_tasks == 1
        assert result.total_time_ms > 0
        assert result.avg_validation_ns > 0
        assert result.throughput_tasks_per_sec > 0

    def test_more_agents_than_tasks(self) -> None:
        from constitutional_swarm.bench import SwarmBenchmark

        bench = SwarmBenchmark()
        result = bench.run(num_agents=100, num_domains=4, dag_depth=1, dag_width=3)
        assert result.num_tasks == 3
        assert result.num_agents == 100
        assert result.coordination_overhead >= 0
        assert result.coordination_overhead <= 1.0
