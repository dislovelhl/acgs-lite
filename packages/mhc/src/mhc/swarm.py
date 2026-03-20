"""Stigmergic Swarm — orchestrator-free task execution via compiled DAGs.

Goals are compiled into task DAGs. Agents self-select tasks based on
capability. Completed artifacts unlock downstream tasks. No orchestrator,
no coordination messages. Works identically for 8 or 800 agents.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from omalhc.artifact import Artifact, ArtifactStore
from omalhc.capability import Capability, CapabilityRegistry
from omalhc.contract import ContractStatus, TaskContract


class NodeStatus(Enum):
    """Execution status of a DAG node."""

    BLOCKED = "blocked"
    READY = "ready"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskNode:
    """A node in the task DAG.

    Each node represents a unit of work with typed inputs/outputs,
    dependencies on parent nodes, and capability requirements.
    """

    node_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    description: str = ""
    domain: str = ""
    required_capabilities: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    priority: int = 0
    max_budget_tokens: int = 0
    status: NodeStatus = NodeStatus.BLOCKED
    claimed_by: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskDAG:
    """A directed acyclic graph of tasks compiled from a goal.

    The DAG defines the execution plan. Agents claim and execute nodes
    whose dependencies are satisfied. No orchestrator needed — the DAG
    structure IS the coordination.
    """

    dag_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: str = ""
    nodes: dict[str, TaskNode] = field(default_factory=dict)

    def add_node(self, node: TaskNode) -> TaskDAG:
        """Add a node to the DAG. Returns new DAG (immutable pattern)."""
        new_nodes = dict(self.nodes)
        new_nodes[node.node_id] = node
        return TaskDAG(dag_id=self.dag_id, goal=self.goal, nodes=new_nodes)

    def ready_nodes(self) -> list[TaskNode]:
        """Get all nodes whose dependencies are satisfied and unclaimed.

        A node is ready when all its parents are COMPLETED.
        """
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.BLOCKED:
                continue
            deps_met = all(
                self.nodes[dep].status == NodeStatus.COMPLETED
                for dep in node.depends_on
                if dep in self.nodes
            )
            if deps_met:
                ready.append(node)
        return ready

    def mark_ready(self) -> TaskDAG:
        """Update all blocked nodes with satisfied dependencies to READY."""
        new_nodes = dict(self.nodes)
        for nid, node in new_nodes.items():
            if node.status != NodeStatus.BLOCKED:
                continue
            deps_met = all(
                new_nodes[dep].status == NodeStatus.COMPLETED
                for dep in node.depends_on
                if dep in new_nodes
            )
            if deps_met:
                new_nodes[nid] = TaskNode(
                    node_id=node.node_id,
                    title=node.title,
                    description=node.description,
                    domain=node.domain,
                    required_capabilities=node.required_capabilities,
                    depends_on=node.depends_on,
                    priority=node.priority,
                    max_budget_tokens=node.max_budget_tokens,
                    status=NodeStatus.READY,
                    metadata=dict(node.metadata),
                )
        return TaskDAG(dag_id=self.dag_id, goal=self.goal, nodes=new_nodes)

    def claim_node(self, node_id: str, agent_id: str) -> TaskDAG:
        """Claim a ready node for execution."""
        node = self.nodes.get(node_id)
        if node is None:
            raise KeyError(f"Node {node_id} not found")
        if node.status != NodeStatus.READY:
            raise ValueError(f"Node {node_id} is {node.status.value}, not ready")
        new_nodes = dict(self.nodes)
        new_nodes[node_id] = TaskNode(
            node_id=node.node_id,
            title=node.title,
            description=node.description,
            domain=node.domain,
            required_capabilities=node.required_capabilities,
            depends_on=node.depends_on,
            priority=node.priority,
            max_budget_tokens=node.max_budget_tokens,
            status=NodeStatus.CLAIMED,
            claimed_by=agent_id,
            metadata=dict(node.metadata),
        )
        return TaskDAG(dag_id=self.dag_id, goal=self.goal, nodes=new_nodes)

    def complete_node(self, node_id: str, artifact_id: str) -> TaskDAG:
        """Mark a node as completed with its output artifact."""
        node = self.nodes.get(node_id)
        if node is None:
            raise KeyError(f"Node {node_id} not found")
        new_nodes = dict(self.nodes)
        new_nodes[node_id] = TaskNode(
            node_id=node.node_id,
            title=node.title,
            description=node.description,
            domain=node.domain,
            required_capabilities=node.required_capabilities,
            depends_on=node.depends_on,
            priority=node.priority,
            max_budget_tokens=node.max_budget_tokens,
            status=NodeStatus.COMPLETED,
            claimed_by=node.claimed_by,
            artifact_id=artifact_id,
            metadata=dict(node.metadata),
        )
        return TaskDAG(dag_id=self.dag_id, goal=self.goal, nodes=new_nodes)

    @property
    def is_complete(self) -> bool:
        """Check if all nodes in the DAG are completed."""
        return all(n.status == NodeStatus.COMPLETED for n in self.nodes.values())

    @property
    def progress(self) -> dict[str, int]:
        """Count nodes by status."""
        counts: dict[str, int] = {}
        for node in self.nodes.values():
            counts[node.status.value] = counts.get(node.status.value, 0) + 1
        return counts

    def to_contracts(self, constitutional_hash: str = "") -> list[TaskContract]:
        """Convert DAG nodes to task contracts for the swarm."""
        return [
            TaskContract(
                task_id=node.node_id,
                title=node.title,
                description=node.description,
                domain=node.domain,
                required_capabilities=node.required_capabilities,
                priority=node.priority,
                max_budget_tokens=node.max_budget_tokens,
                constitutional_hash=constitutional_hash,
            )
            for node in self.nodes.values()
        ]


class SwarmExecutor:
    """Executes a task DAG using a swarm of agents.

    Agents self-select tasks based on capabilities. No orchestrator.
    The executor just manages the DAG state and artifact store.

    In production, this runs as a lightweight event loop. Agents
    poll for ready tasks or subscribe to notifications.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        store: ArtifactStore,
    ) -> None:
        self._registry = registry
        self._store = store
        self._dag: TaskDAG | None = None

    def load_dag(self, dag: TaskDAG) -> None:
        """Load a task DAG for execution."""
        self._dag = dag.mark_ready()

    def available_tasks(self, agent_id: str) -> list[TaskNode]:
        """Get tasks an agent can claim based on its capabilities.

        Matches agent capabilities against task requirements.
        Returns only READY (unclaimed) tasks.
        """
        if self._dag is None:
            return []
        agent_caps = self._registry._by_agent.get(agent_id, [])
        cap_names = {c.name.lower() for c in agent_caps}
        cap_domains = {c.domain for c in agent_caps}

        available = []
        for node in self._dag.nodes.values():
            if node.status != NodeStatus.READY:
                continue
            if not node.required_capabilities:
                available.append(node)
                continue
            has_caps = any(
                rc.lower() in cap_names for rc in node.required_capabilities
            )
            in_domain = node.domain in cap_domains
            if has_caps or in_domain:
                available.append(node)

        return sorted(available, key=lambda n: -n.priority)

    def claim(self, node_id: str, agent_id: str) -> TaskContract:
        """Agent claims a task. Returns the contract."""
        if self._dag is None:
            raise RuntimeError("No DAG loaded")
        self._dag = self._dag.claim_node(node_id, agent_id)
        node = self._dag.nodes[node_id]
        return TaskContract(
            task_id=node.node_id,
            title=node.title,
            description=node.description,
            domain=node.domain,
            required_capabilities=node.required_capabilities,
            status=ContractStatus.CLAIMED,
            claimed_by=agent_id,
            priority=node.priority,
        )

    def submit(self, node_id: str, artifact: Artifact) -> None:
        """Agent submits completed work. Artifact is stored, DAG updated."""
        if self._dag is None:
            raise RuntimeError("No DAG loaded")
        self._store.publish(artifact)
        self._dag = self._dag.complete_node(node_id, artifact.artifact_id)
        self._dag = self._dag.mark_ready()

    @property
    def is_complete(self) -> bool:
        """Check if the entire DAG is done."""
        return self._dag is not None and self._dag.is_complete

    @property
    def progress(self) -> dict[str, int]:
        """Current DAG progress by status."""
        if self._dag is None:
            return {}
        return self._dag.progress

    @property
    def dag(self) -> TaskDAG | None:
        """Current DAG state."""
        return self._dag
