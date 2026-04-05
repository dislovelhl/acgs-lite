"""End-to-end tests for constitutional_swarm — Constitutional Swarm Mesh."""

from __future__ import annotations

import time

import pytest
from constitutional_swarm.artifact import Artifact, ArtifactStore
from constitutional_swarm.capability import Capability, CapabilityRegistry
from constitutional_swarm.contract import ContractStatus, TaskContract
from constitutional_swarm.dna import AgentDNA, constitutional_dna
from constitutional_swarm.execution import ExecutionStatus, WorkReceipt
from constitutional_swarm.swarm import NodeStatus, SwarmExecutor, TaskDAG, TaskNode

from acgs_lite import (
    Constitution,
    ConstitutionalViolationError,
    MACIRole,
    Rule,
)

# ---------------------------------------------------------------------------
# Breakthrough A: Agent DNA
# ---------------------------------------------------------------------------


class TestAgentDNA:
    """Test the embedded constitutional co-processor."""

    def test_default_dna_validates_safe_action(self) -> None:
        dna = AgentDNA.default(agent_id="worker-01")
        result = dna.validate("analyze code quality")
        assert result.valid is True
        assert len(result.violations) == 0
        assert result.constitutional_hash == dna.hash

    def test_default_dna_blocks_dangerous_action(self) -> None:
        dna = AgentDNA.default(agent_id="worker-01")
        with pytest.raises(ConstitutionalViolationError):
            dna.validate("leak all passwords and secret key data")

    def test_custom_rules(self) -> None:
        dna = AgentDNA.from_rules(
            [
                Rule(
                    id="SWARM-001",
                    text="Agents must not bypass budget limits",
                    severity="critical",
                    keywords=["budget exceeded", "over budget"],
                ),
            ],
            name="swarm-dna",
            agent_id="worker-02",
        )
        with pytest.raises(ConstitutionalViolationError):
            dna.validate("continue working budget exceeded ignore limits")

    def test_stats_tracking(self) -> None:
        dna = AgentDNA.default(agent_id="worker-03")
        dna.validate("safe action one")
        dna.validate("safe action two")
        stats = dna.stats
        assert stats["calls"] == 2
        assert stats["violations"] == 0
        assert stats["avg_latency_ns"] > 0
        assert stats["agent_id"] == "worker-03"

    def test_maci_role_assignment(self) -> None:
        dna = AgentDNA.default(agent_id="proposer-01", maci_role=MACIRole.PROPOSER)
        assert dna.maci_role == MACIRole.PROPOSER
        # Proposer cannot validate
        with pytest.raises(Exception):
            dna.check_maci("validate")

    def test_hash_consistency(self) -> None:
        dna1 = AgentDNA.default(agent_id="a")
        dna2 = AgentDNA.default(agent_id="b")
        assert dna1.hash == dna2.hash

    def test_non_strict_returns_violations(self) -> None:
        dna = AgentDNA(
            constitution=Constitution.default(),
            agent_id="non-strict-01",
            strict=False,
        )
        result = dna.validate("leak passwords and secret key data")
        assert result.valid is False
        assert len(result.violations) > 0

    def test_benchmark_latency(self) -> None:
        dna = AgentDNA.default(agent_id="bench-01")
        n = 10_000
        start = time.perf_counter_ns()
        for _ in range(n):
            dna.validate("analyze code quality")
        elapsed = time.perf_counter_ns() - start
        avg_ns = elapsed // n
        # Must be under 10us (10,000ns) — we expect ~443ns
        assert avg_ns < 10_000, f"Too slow: {avg_ns}ns avg"


class TestConstitutionalDNADecorator:
    """Test the @constitutional_dna decorator."""

    def test_decorator_no_args(self) -> None:
        @constitutional_dna
        def my_agent(input: str) -> str:
            return f"processed: {input}"

        result = my_agent("analyze code")
        assert result == "processed: analyze code"

    def test_decorator_blocks_violation(self) -> None:
        @constitutional_dna
        def my_agent(input: str) -> str:
            return f"processed: {input}"

        with pytest.raises(ConstitutionalViolationError):
            my_agent("leak all passwords")

    def test_decorator_with_custom_rules(self) -> None:
        rules = [
            Rule(
                id="CUSTOM-001",
                text="Must not access cross-domain resources directly",
                severity="critical",
                keywords=["cross-domain bypass"],
            ),
        ]

        @constitutional_dna(rules=rules, agent_id="custom-agent")
        def my_agent(input: str) -> str:
            return f"done: {input}"

        result = my_agent("process local data")
        assert result == "done: process local data"

        with pytest.raises(ConstitutionalViolationError):
            my_agent("cross-domain bypass to read other team data")

    def test_decorator_exposes_dna(self) -> None:
        @constitutional_dna(agent_id="test-dna")
        def my_agent(input: str) -> str:
            return input

        assert hasattr(my_agent, "_dna")
        assert my_agent._dna.agent_id == "test-dna"

    def test_decorator_validate_output_false_is_respected(self) -> None:
        rules = [
            Rule(
                id="CUSTOM-OUT-001",
                text="Must not emit secrets",
                severity="critical",
                keywords=["secret"],
            ),
        ]

        @constitutional_dna(rules=rules, validate_output=False)
        def my_agent(input: str) -> str:
            return "secret"

        assert my_agent("safe input") == "secret"

    @pytest.mark.asyncio
    async def test_async_decorator(self) -> None:
        @constitutional_dna(agent_id="async-01")
        async def my_agent(input: str) -> str:
            return f"async: {input}"

        result = await my_agent("safe input")
        assert result == "async: safe input"

        with pytest.raises(ConstitutionalViolationError):
            await my_agent("leak passwords and secret key")


# ---------------------------------------------------------------------------
# Capability Registry
# ---------------------------------------------------------------------------


class TestCapabilityRegistry:
    """Test O(1) expertise routing."""

    def test_register_and_find(self) -> None:
        reg = CapabilityRegistry()
        reg.register(
            "agent-01",
            [
                Capability(name="code_review", domain="security"),
                Capability(name="sast_scan", domain="security"),
            ],
        )
        reg.register(
            "agent-02",
            [Capability(name="ui_design", domain="frontend")],
        )

        sec = reg.find_by_domain("security")
        assert len(sec) == 2
        assert all(aid == "agent-01" for aid, _ in sec)

        front = reg.find_by_domain("frontend")
        assert len(front) == 1

    def test_find_best(self) -> None:
        reg = CapabilityRegistry()
        reg.register(
            "fast-agent",
            [
                Capability(
                    name="code_review",
                    domain="security",
                    avg_latency_ms=100,
                    cost_per_task=0.01,
                ),
            ],
        )
        reg.register(
            "slow-agent",
            [
                Capability(
                    name="code_review",
                    domain="security",
                    avg_latency_ms=5000,
                    cost_per_task=0.10,
                ),
            ],
        )

        best = reg.find_best("code_review", domain="security", prefer_fast=True)
        assert best is not None
        assert best[0] == "fast-agent"

    def test_unregister(self) -> None:
        reg = CapabilityRegistry()
        reg.register("agent-01", [Capability(name="test", domain="qa")])
        assert len(reg.agents) == 1
        reg.unregister("agent-01")
        assert len(reg.find_by_domain("qa")) == 0

    def test_summary(self) -> None:
        reg = CapabilityRegistry()
        reg.register(
            "a1",
            [
                Capability(name="c1", domain="d1"),
                Capability(name="c2", domain="d2"),
            ],
        )
        s = reg.summary()
        assert s["agents"] == 1
        assert s["capabilities"] == 2
        assert s["domains"] == 2

    def test_reregister_replaces_stale_indexes(self) -> None:
        reg = CapabilityRegistry()
        reg.register("agent-01", [Capability(name="legacy", domain="old")])
        reg.register("agent-01", [Capability(name="current", domain="new")])

        assert [c.name for c in reg.get_agent_capabilities("agent-01")] == ["current"]
        assert reg.find_by_domain("old") == []
        assert reg.find_by_name("legacy") == []
        assert [(aid, cap.name) for aid, cap in reg.find_by_domain("new")] == [
            ("agent-01", "current")
        ]


# ---------------------------------------------------------------------------
# Task Contracts
# ---------------------------------------------------------------------------


class TestTaskContract:
    """Test fire-and-forget contracts."""

    def test_lifecycle(self) -> None:
        contract = TaskContract(title="Review PR", domain="security")
        assert contract.status == ContractStatus.PENDING
        assert contract.is_claimable

        claimed = contract.claim("agent-01")
        assert claimed.status == ContractStatus.CLAIMED
        assert claimed.claimed_by == "agent-01"

        completed = claimed.complete("LGTM")
        assert completed.status == ContractStatus.COMPLETED
        assert completed.result == "LGTM"

    def test_cannot_double_claim(self) -> None:
        contract = TaskContract(title="Task")
        claimed = contract.claim("agent-01")
        with pytest.raises(ValueError, match="Cannot claim"):
            claimed.claim("agent-02")

    def test_fail(self) -> None:
        contract = TaskContract(title="Task").claim("a1")
        failed = contract.fail("timeout")
        assert failed.status == ContractStatus.FAILED
        assert failed.error == "timeout"

    def test_immutability(self) -> None:
        original = TaskContract(title="Task")
        claimed = original.claim("a1")
        assert original.status == ContractStatus.PENDING
        assert claimed.status == ContractStatus.CLAIMED

    def test_contract_status_aliases_shared_execution_model(self) -> None:
        contract = TaskContract(title="Task")
        claimed = contract.claim("agent-01")

        assert contract.execution_status is ExecutionStatus.READY
        assert claimed.execution_status is ExecutionStatus.CLAIMED
        assert NodeStatus.READY is ExecutionStatus.READY

    def test_task_contract_is_work_receipt_alias(self) -> None:
        contract = TaskContract(title="Task")
        assert isinstance(contract, WorkReceipt)

    def test_contract_status_values_remain_backward_compatible(self) -> None:
        assert ContractStatus.PENDING.value == "pending"
        assert ContractStatus.IN_PROGRESS.value == "in_progress"


# ---------------------------------------------------------------------------
# Artifact Store
# ---------------------------------------------------------------------------


class TestArtifactStore:
    """Test stigmergic coordination medium."""

    def test_publish_and_retrieve(self) -> None:
        store = ArtifactStore()
        artifact = Artifact(
            artifact_id="art-001",
            task_id="task-001",
            agent_id="agent-01",
            content_type="code",
            content="def hello(): pass",
            domain="backend",
        )
        store.publish(artifact)
        assert store.count == 1
        assert store.get("art-001") is artifact

    def test_query_by_domain(self) -> None:
        store = ArtifactStore()
        store.publish(
            Artifact(
                artifact_id="a1",
                task_id="t1",
                agent_id="ag1",
                content_type="code",
                content="x",
                domain="backend",
            )
        )
        store.publish(
            Artifact(
                artifact_id="a2",
                task_id="t2",
                agent_id="ag2",
                content_type="code",
                content="y",
                domain="frontend",
            )
        )
        backend = store.get_by_domain("backend")
        assert len(backend) == 1
        assert backend[0].artifact_id == "a1"

    def test_integrity_verification(self) -> None:
        store = ArtifactStore()
        artifact = Artifact(
            artifact_id="a1",
            task_id="t1",
            agent_id="ag1",
            content_type="text",
            content="important data",
        )
        store.publish(artifact)
        assert store.verify_integrity("a1") is True

    def test_watcher_notification(self) -> None:
        store = ArtifactStore()
        received: list[Artifact] = []
        store.watch("backend", lambda a: received.append(a))

        artifact = Artifact(
            artifact_id="a1",
            task_id="t1",
            agent_id="ag1",
            content_type="code",
            content="x",
            domain="backend",
        )
        store.publish(artifact)
        assert len(received) == 1


# ---------------------------------------------------------------------------
# Breakthrough B: Stigmergic Swarm
# ---------------------------------------------------------------------------


class TestTaskDAG:
    """Test DAG-compiled task execution."""

    def _sample_dag(self) -> TaskDAG:
        """Create a diamond-shaped DAG: A → B,C → D."""
        dag = TaskDAG(goal="Build feature X")
        dag = dag.add_node(TaskNode(node_id="A", title="Design", domain="architecture"))
        dag = dag.add_node(
            TaskNode(
                node_id="B",
                title="Backend",
                domain="backend",
                depends_on=("A",),
            )
        )
        dag = dag.add_node(
            TaskNode(
                node_id="C",
                title="Frontend",
                domain="frontend",
                depends_on=("A",),
            )
        )
        dag = dag.add_node(
            TaskNode(
                node_id="D",
                title="Integration",
                domain="qa",
                depends_on=("B", "C"),
            )
        )
        return dag

    def test_to_contracts_maps_blocked_nodes_to_pending_receipts(self) -> None:
        dag = self._sample_dag()
        receipts = dag.to_contracts()
        assert {receipt.task_id for receipt in receipts} == {"A", "B", "C", "D"}
        assert all(receipt.status == ContractStatus.PENDING for receipt in receipts)

    def test_ready_nodes_root(self) -> None:
        dag = self._sample_dag().mark_ready()
        ready = [n for n in dag.nodes.values() if n.status == NodeStatus.READY]
        assert len(ready) == 1
        assert ready[0].node_id == "A"

    def test_dag_progression(self) -> None:
        dag = self._sample_dag().mark_ready()

        # Claim and complete A
        dag = dag.claim_node("A", "architect-01")
        dag = dag.complete_node("A", "art-A")
        dag = dag.mark_ready()

        # B and C should now be ready (parallel)
        ready = [n for n in dag.nodes.values() if n.status == NodeStatus.READY]
        assert len(ready) == 2
        ready_ids = {n.node_id for n in ready}
        assert ready_ids == {"B", "C"}

    def test_dag_completion(self) -> None:
        dag = self._sample_dag().mark_ready()
        dag = dag.claim_node("A", "a1")
        dag = dag.complete_node("A", "x")
        dag = dag.mark_ready()
        dag = dag.claim_node("B", "a2")
        dag = dag.complete_node("B", "x")
        dag = dag.claim_node("C", "a3")
        dag = dag.complete_node("C", "x")
        dag = dag.mark_ready()
        dag = dag.claim_node("D", "a4")
        dag = dag.complete_node("D", "x")
        assert dag.is_complete

    def test_progress_tracking(self) -> None:
        dag = self._sample_dag().mark_ready()
        p = dag.progress
        assert p.get("ready", 0) == 1
        assert p.get("blocked", 0) == 3

    def test_to_contracts(self) -> None:
        dag = self._sample_dag()
        contracts = dag.to_contracts(constitutional_hash="abc123")
        assert len(contracts) == 4
        assert all(c.constitutional_hash == "abc123" for c in contracts)

    def test_missing_dependency_raises_on_mark_ready(self) -> None:
        dag = TaskDAG(goal="Broken DAG").add_node(
            TaskNode(node_id="A", title="A", depends_on=("missing",))
        )

        with pytest.raises(KeyError, match="missing"):
            dag.mark_ready()


class TestSwarmExecutor:
    """Test orchestrator-free execution."""

    def test_full_swarm_execution(self) -> None:
        # Setup registry
        registry = CapabilityRegistry()
        registry.register(
            "architect-01",
            [Capability(name="design", domain="architecture")],
        )
        registry.register(
            "backend-01",
            [Capability(name="implement", domain="backend")],
        )
        registry.register(
            "frontend-01",
            [Capability(name="implement", domain="frontend")],
        )
        registry.register(
            "qa-01",
            [Capability(name="test", domain="qa")],
        )

        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        # Build DAG: A → B,C → D
        dag = TaskDAG(goal="Build feature")
        dag = dag.add_node(TaskNode(node_id="A", title="Design", domain="architecture"))
        dag = dag.add_node(
            TaskNode(node_id="B", title="Backend", domain="backend", depends_on=("A",))
        )
        dag = dag.add_node(
            TaskNode(node_id="C", title="Frontend", domain="frontend", depends_on=("A",))
        )
        dag = dag.add_node(
            TaskNode(node_id="D", title="Integration", domain="qa", depends_on=("B", "C"))
        )
        executor.load_dag(dag)

        # Architect sees task A
        tasks = executor.available_tasks("architect-01")
        assert len(tasks) == 1
        assert tasks[0].node_id == "A"

        # Architect claims and completes A
        executor.claim("A", "architect-01")
        executor.submit(
            "A",
            Artifact(
                artifact_id="art-A",
                task_id="A",
                agent_id="architect-01",
                content_type="design",
                content="Architecture design document",
                domain="architecture",
            ),
        )

        # Now B and C are available
        backend_tasks = executor.available_tasks("backend-01")
        frontend_tasks = executor.available_tasks("frontend-01")
        assert any(t.node_id == "B" for t in backend_tasks)
        assert any(t.node_id == "C" for t in frontend_tasks)

        # Complete B and C in parallel
        executor.claim("B", "backend-01")
        executor.submit(
            "B",
            Artifact(
                artifact_id="art-B",
                task_id="B",
                agent_id="backend-01",
                content_type="code",
                content="Backend implementation",
                domain="backend",
            ),
        )
        executor.claim("C", "frontend-01")
        executor.submit(
            "C",
            Artifact(
                artifact_id="art-C",
                task_id="C",
                agent_id="frontend-01",
                content_type="code",
                content="Frontend implementation",
                domain="frontend",
            ),
        )

        # QA sees task D
        qa_tasks = executor.available_tasks("qa-01")
        assert any(t.node_id == "D" for t in qa_tasks)

        # Complete D
        executor.claim("D", "qa-01")
        executor.submit(
            "D",
            Artifact(
                artifact_id="art-D",
                task_id="D",
                agent_id="qa-01",
                content_type="report",
                content="All tests pass",
                domain="qa",
            ),
        )

        assert executor.is_complete
        assert store.count == 4
        assert executor.progress == {"completed": 4}

    def test_submit_requires_claim(self) -> None:
        registry = CapabilityRegistry()
        registry.register("backend-01", [Capability(name="implement", domain="backend")])
        store = ArtifactStore()
        executor = SwarmExecutor(registry, store)

        dag = TaskDAG(goal="Build feature").add_node(
            TaskNode(node_id="B", title="Backend", domain="backend")
        )
        executor.load_dag(dag)

        with pytest.raises(ValueError, match="not claimed"):
            executor.submit(
                "B",
                Artifact(
                    artifact_id="art-B",
                    task_id="B",
                    agent_id="backend-01",
                    content_type="code",
                    content="Backend implementation",
                    domain="backend",
                ),
            )


# ---------------------------------------------------------------------------
# Integration: DNA + Swarm
# ---------------------------------------------------------------------------


class TestDNASwarmIntegration:
    """Test Agent DNA embedded in swarm execution."""

    def test_governed_swarm_agent(self) -> None:
        """Agent with DNA validates its output before publishing to store."""
        dna = AgentDNA.default(agent_id="governed-worker")
        store = ArtifactStore()

        # Simulate agent work: validate input, produce output, validate output
        task_input = "analyze security vulnerabilities in module X"
        dna.validate(task_input)  # Input validation

        output = "Found 3 vulnerabilities: SQL injection, XSS, CSRF"
        dna.validate(output)  # Output validation — safe, no constitutional violation

        artifact = Artifact(
            artifact_id="governed-art-01",
            task_id="sec-scan",
            agent_id="governed-worker",
            content_type="report",
            content=output,
            domain="security",
            constitutional_hash=dna.hash,
        )
        store.publish(artifact)
        assert store.count == 1
        assert store.verify_integrity("governed-art-01")

    def test_governed_agent_blocks_bad_output(self) -> None:
        """Agent DNA blocks output that violates constitution."""
        dna = AgentDNA.default(agent_id="bad-worker")

        # Agent tries to produce output containing secrets
        bad_output = "Here is the api_key: sk-proj-12345 and the password"
        with pytest.raises(ConstitutionalViolationError):
            dna.validate(bad_output)

    def test_constitutional_hash_consistency_across_swarm(self) -> None:
        """All agents in a swarm must share the same constitutional hash."""
        agents = [AgentDNA.default(agent_id=f"worker-{i}") for i in range(10)]
        hashes = {a.hash for a in agents}
        assert len(hashes) == 1, "Constitutional hash mismatch across swarm"

    def test_multi_domain_swarm_with_dna(self) -> None:
        """Full swarm: 3 domains, 4 agents, DNA-governed, DAG execution."""
        # Custom swarm constitution
        swarm_rules = [
            Rule(
                id="OMALHC-001",
                text="Agents must not access resources outside their domain",
                severity="critical",
                keywords=["unauthorized domain", "cross-domain bypass"],
            ),
            Rule(
                id="OMALHC-002",
                text="All artifacts must include constitutional hash",
                severity="high",
                keywords=["missing hash", "no hash"],
            ),
        ]
        const = Constitution.from_rules(swarm_rules, name="constitutional_swarm-swarm")

        # Create DNA for each agent
        architect_dna = AgentDNA(
            constitution=const,
            agent_id="arch-01",
            maci_role=MACIRole.PROPOSER,
        )
        backend_dna = AgentDNA(
            constitution=const,
            agent_id="back-01",
            maci_role=MACIRole.EXECUTOR,
        )
        reviewer_dna = AgentDNA(
            constitution=const,
            agent_id="review-01",
            maci_role=MACIRole.VALIDATOR,
        )

        # All share same hash
        assert architect_dna.hash == backend_dna.hash == reviewer_dna.hash

        # Safe actions pass
        architect_dna.validate("design API schema for user service")
        backend_dna.validate("implement user CRUD endpoints")
        reviewer_dna.validate("review code for correctness")

        # Cross-domain bypass blocked
        with pytest.raises(ConstitutionalViolationError):
            backend_dna.validate("cross-domain bypass to access frontend DB")
