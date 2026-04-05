"""
ACGS-2 Enhanced Agent Bus - Graph-based Workflows (LangGraph Pattern)
Constitutional Hash: 608508a9bd224290

Implements stateful cyclic graphs for multi-agent governance orchestration.
Features conditional branching, state persistence, and human-in-the-loop interrupts.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .workflow_base import CONSTITUTIONAL_HASH, WorkflowContext

logger = get_logger(__name__)
GRAPH_NODE_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

TState = TypeVar("TState", bound=JSONDict)
# Also define at module level for use in non-Generic contexts
_TState = JSONDict  # Alias for concrete type when Generic not applicable


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GraphNode:
    """A node in the state graph representing an agent or a function."""

    name: str
    func: Callable[[TState], Awaitable[TState]]
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """An edge in the state graph."""

    source: str
    target: str
    condition: Callable[[TState], bool] | None = None
    metadata: JSONDict = field(default_factory=dict)


class StateGraph(Generic[TState]):
    """
    LangGraph-style state machine for multi-agent orchestration.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, state_schema: type):
        self.state_schema = state_schema
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.entry_point: str | None = None
        self.finish_point: str | None = "END"

        # State persistence and checkpointing
        self._checkpoints: list[TState] = []
        self._interrupts: set[str] = set()  # Node names where to interrupt

    def add_node(
        self, name: str, func: Callable[[TState], Awaitable[TState]]
    ) -> "StateGraph[TState]":
        """Add a node to the graph."""
        self.nodes[name] = GraphNode(name=name, func=func)  # type: ignore[arg-type]
        return self

    def add_edge(
        self, source: str, target: str, condition: Callable[[TState], bool] | None = None
    ) -> "StateGraph[TState]":
        """Add an edge between nodes."""
        if source not in self.nodes and source != "START":
            raise ValueError(f"Source node {source} not found")
        if target not in self.nodes and target != "END":
            raise ValueError(f"Target node {target} not found")

        self.edges.append(GraphEdge(source=source, target=target, condition=condition))  # type: ignore[arg-type]
        return self

    def set_entry_point(self, name: str) -> "StateGraph[TState]":
        """Set the starting node of the graph."""
        if name not in self.nodes:
            raise ValueError(f"Node {name} not found")
        self.entry_point = name
        return self

    def add_interrupt(self, node_name: str) -> "StateGraph[TState]":
        """Add an interrupt point for Human-in-the-Loop."""
        self._interrupts.add(node_name)
        return self

    async def execute(
        self, initial_state: TState, context: WorkflowContext | None = None
    ) -> TState:
        """
        Execute the state graph.

        Args:
            initial_state: The starting state
            context: Optional workflow context

        Returns:
            The final state
        """
        if not self.entry_point:
            raise ValueError("Entry point not set")

        current_node = self.entry_point
        state = initial_state
        self._checkpoints.append(state.copy())  # type: ignore[arg-type]

        logger.info(f"[{CONSTITUTIONAL_HASH}] Starting graph execution from {current_node}")

        while current_node != "END":
            # 1. Check for interrupts (Human-in-the-Loop)
            if current_node in self._interrupts:
                logger.info(f"[{CONSTITUTIONAL_HASH}] Interrupting execution at {current_node}")
                # In a real implementation, we would wait for a signal here
                if context:
                    await context.wait_for_signal(f"resume_{current_node}")

            # 2. Execute node
            node = self.nodes[current_node]

            try:
                state = await node.func(state)
                self._checkpoints.append(state.copy())  # type: ignore[arg-type]
            except GRAPH_NODE_EXECUTION_ERRORS as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Node {current_node} failed: {e}")
                raise

            # 3. Determine next node
            next_node = self._get_next_node(current_node, state)
            if not next_node:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] No valid edge from {current_node}, terminating."
                )
                break

            current_node = next_node

        logger.info(f"[{CONSTITUTIONAL_HASH}] Graph execution completed")
        return state

    def _get_next_node(self, current_node: str, state: TState) -> str | None:
        """Determine the next node based on edges and current state."""
        possible_edges = [e for e in self.edges if e.source == current_node]

        for edge in possible_edges:
            if edge.condition is None or edge.condition(state):
                return edge.target

        return None

    def get_history(self) -> list[TState]:
        """Get the history of state checkpoints."""
        return self._checkpoints


class GovernanceGraph(StateGraph):
    """
    Specialized graph for multi-agent governance.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self):
        super().__init__(state_schema={})
        self._build_standard_governance_graph()

    def _build_standard_governance_graph(self):
        """Build a standard governance workflow graph."""
        # Nodes
        self.add_node("classify", self._classify_node)
        self.add_node("validate", self._validate_node)
        self.add_node("deliberate", self._deliberate_node)
        self.add_node("execute", self._execute_node)
        self.add_node("audit", self._audit_node)

        # Edges
        self.set_entry_point("classify")

        self.add_edge("classify", "execute", condition=lambda s: s.get("complexity") == "simple")
        self.add_edge(
            "classify", "validate", condition=lambda s: s.get("complexity") == "requires_validation"
        )
        self.add_edge(
            "classify", "deliberate", condition=lambda s: s.get("complexity") == "complex"
        )

        self.add_edge("validate", "deliberate")
        self.add_edge("deliberate", "execute")
        self.add_edge("execute", "audit")
        self.add_edge("audit", "END")

    async def _classify_node(self, state: TState) -> TState:
        # Mock classification logic
        content = state.get("content", "")
        if "critical" in content:
            state["complexity"] = "complex"
        elif "validate" in content:
            state["complexity"] = "requires_validation"
        else:
            state["complexity"] = "simple"
        return state

    async def _validate_node(self, state: TState) -> TState:
        state["validated"] = True
        return state

    async def _deliberate_node(self, state: TState) -> TState:
        state["deliberated"] = True
        return state

    async def _execute_node(self, state: TState) -> TState:
        state["executed"] = True
        return state

    async def _audit_node(self, state: TState) -> TState:
        state["audited"] = True
        return state
