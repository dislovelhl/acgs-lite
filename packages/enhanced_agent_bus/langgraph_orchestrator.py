"""
ACGS-2 LangGraph-Style Orchestration

Implements stateful cyclic graphs for complex multi-agent governance workflows
with conditional branching and state persistence, inspired by LangGraph patterns.

Constitutional Hash: 608508a9bd224290
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Generic type variable for state values
T = TypeVar("T")

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

logger = get_logger(__name__)
_LANGGRAPH_ORCHESTRATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class NodeState(Enum):
    """States for graph nodes."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowState(Enum):
    """States for workflow execution."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class NodeExecutionResult:
    """Result of executing a single node."""

    node_id: str
    state: NodeState
    output: object = None
    error: str | None = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class GlobalState:
    """
    Global state object that flows through the workflow graph.

    This replaces message passing with persistent state mutations.
    Constitutional Hash: 608508a9bd224290
    """

    # Core state
    workflow_id: str
    current_node: str | None = None
    state_data: JSONDict = field(default_factory=dict)

    # Execution tracking
    executed_nodes: set[str] = field(default_factory=set)
    pending_nodes: set[str] = field(default_factory=set)
    failed_nodes: set[str] = field(default_factory=set)

    # Results and history
    node_results: dict[str, NodeExecutionResult] = field(default_factory=dict)
    execution_history: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def update(self, key: str, value: object) -> None:
        """Update state data."""
        self.state_data[key] = value
        self.updated_at = datetime.now(UTC)

    def get(self, key: str, default: T = None) -> T:
        """Get state data."""
        return self.state_data.get(key, default)  # type: ignore[no-any-return]

    def record_node_execution(self, result: NodeExecutionResult) -> None:
        """Record node execution result."""
        self.node_results[result.node_id] = result
        self.executed_nodes.add(result.node_id)
        if result.node_id in self.pending_nodes:
            self.pending_nodes.remove(result.node_id)
        if result.state == NodeState.FAILED:
            self.failed_nodes.add(result.node_id)
        self.execution_history.append(result.node_id)
        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "workflow_id": self.workflow_id,
            "current_node": self.current_node,
            "state_data": self.state_data,
            "executed_nodes": list(self.executed_nodes),
            "pending_nodes": list(self.pending_nodes),
            "failed_nodes": list(self.failed_nodes),
            "node_results": {k: v.to_dict() for k, v in self.node_results.items()},
            "execution_history": self.execution_history,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }


class BaseNode(ABC):
    """
    Abstract base class for workflow nodes.

    All nodes function as state reducers: (CurrentState) -> NewState
    """

    def __init__(self, node_id: str, name: str | None = None):
        self.node_id = node_id
        self.name = name or node_id
        self.dependencies: list[str] = []
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def execute(self, state: GlobalState) -> NodeExecutionResult:
        """
        Execute this node.

        Args:
            state: Current global state

        Returns:
            Execution result
        """
        pass

    def get_dependencies(self) -> list[str]:
        """Get node dependencies."""
        return self.dependencies

    def add_dependency(self, node_id: str) -> None:
        """Add a dependency."""
        if node_id not in self.dependencies:
            self.dependencies.append(node_id)


class ConditionalNode(BaseNode):
    """
    Node that can conditionally route execution.

    Similar to LangGraph conditional edges.
    """

    def __init__(self, node_id: str, condition_func: Callable[[GlobalState], str]):
        super().__init__(node_id, f"conditional_{node_id}")
        self.condition_func = condition_func

    async def execute(self, state: GlobalState) -> NodeExecutionResult:
        """Execute conditional routing."""
        import time

        start_time = time.monotonic()

        try:
            next_node = self.condition_func(state)
            execution_time = (time.monotonic() - start_time) * 1000

            return NodeExecutionResult(
                node_id=self.node_id,
                state=NodeState.COMPLETED,
                output={"next_node": next_node},
                execution_time_ms=execution_time,
                metadata={"routing_decision": next_node},
            )
        except _LANGGRAPH_ORCHESTRATOR_OPERATION_ERRORS as e:
            execution_time = (time.monotonic() - start_time) * 1000
            return NodeExecutionResult(
                node_id=self.node_id,
                state=NodeState.FAILED,
                error=str(e),
                execution_time_ms=execution_time,
            )


class GovernanceWorkflowNode(BaseNode):
    """
    Node for governance-specific operations.

    Integrates with ACGS-2 constitutional governance.
    """

    def __init__(self, node_id: str, operation: str, config: JSONDict = None):
        super().__init__(node_id, f"governance_{operation}")
        self.operation = operation
        self.config = config or {}

    async def execute(self, state: GlobalState) -> NodeExecutionResult:
        """Execute governance operation."""
        import time

        start_time = time.monotonic()

        try:
            # Import governance components dynamically to avoid circular imports
            if self.operation == "validate_compliance":
                from constitutional_classifier import classify_constitutional_compliance

                text = state.get("input_text", "")
                result = await classify_constitutional_compliance(text)
                output = result.to_dict()

            elif self.operation == "check_security":
                from runtime_security import scan_content

                content = state.get("content", "")
                result = await scan_content(content)
                output = result.to_dict()

            elif self.operation == "route_by_complexity":
                # Simple complexity routing
                text = state.get("input_text", "")
                complexity = len(text.split()) / 100  # Words per 100 as complexity score
                next_node = "complex_deliberation" if complexity > 0.5 else "simple_execution"
                output = {"next_node": next_node, "complexity_score": complexity}

            else:
                output = {"operation": self.operation, "status": "completed"}

            execution_time = (time.monotonic() - start_time) * 1000

            return NodeExecutionResult(
                node_id=self.node_id,
                state=NodeState.COMPLETED,
                output=output,
                execution_time_ms=execution_time,
                metadata={"operation": self.operation},
            )

        except _LANGGRAPH_ORCHESTRATOR_OPERATION_ERRORS as e:
            execution_time = (time.monotonic() - start_time) * 1000
            return NodeExecutionResult(
                node_id=self.node_id,
                state=NodeState.FAILED,
                error=str(e),
                execution_time_ms=execution_time,
                metadata={"operation": self.operation},
            )


@dataclass
class WorkflowDefinition:
    """Definition of a workflow graph."""

    workflow_id: str
    name: str
    description: str = ""
    nodes: dict[str, BaseNode] = field(default_factory=dict)
    edges: dict[str, list[str]] = field(default_factory=dict)  # node -> [next_nodes]
    conditional_edges: dict[str, ConditionalNode] = field(default_factory=dict)
    entry_point: str = "classifier"
    max_execution_time_ms: int = 30000  # 30 seconds
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def add_node(self, node: BaseNode) -> None:
        """Add a node to the workflow."""
        self.nodes[node.node_id] = node

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add a directed edge between nodes."""
        if from_node not in self.edges:
            self.edges[from_node] = []
        if to_node not in self.edges[from_node]:
            self.edges[from_node].append(to_node)

    def add_conditional_edge(self, from_node: str, condition_node: ConditionalNode) -> None:
        """Add a conditional edge."""
        self.conditional_edges[from_node] = condition_node
        self.add_node(condition_node)

    async def get_next_nodes(self, node_id: str, state: GlobalState) -> list[str]:
        """Get next nodes to execute after the given node."""
        next_nodes = []

        # Check for conditional edge first
        if node_id in self.conditional_edges:
            condition_result = await self.conditional_edges[node_id].execute(state)
            if condition_result.state == NodeState.COMPLETED:
                next_node = condition_result.output.get("next_node")
                if next_node:
                    next_nodes.append(next_node)
        else:
            # Use regular edges
            next_nodes.extend(self.edges.get(node_id, []))

        return next_nodes


class WorkflowExecutor:
    """
    Executes workflows using LangGraph-style orchestration.

    Manages state persistence, error handling, and execution flow.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.logger = get_logger(f"{__name__}.WorkflowExecutor")

        # Execution state
        self.execution_state: WorkflowState | None = None
        self.current_state: GlobalState | None = None

        # Metrics
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0

    async def execute(
        self, initial_state_data: JSONDict, workflow_id: str | None = None
    ) -> GlobalState:
        """
        Execute the workflow.

        Args:
            initial_state_data: Initial state data
            workflow_id: Optional workflow ID

        Returns:
            Final global state
        """
        import time

        start_time = time.monotonic()

        # Generate workflow ID if not provided
        if workflow_id is None:
            workflow_id = f"workflow_{int(time.time() * 1000)}"

        # Initialize global state
        self.current_state = GlobalState(
            workflow_id=workflow_id, state_data=initial_state_data.copy()
        )

        self.execution_state = WorkflowState.RUNNING
        self.total_executions += 1

        try:
            # Initialize pending nodes
            self.current_state.pending_nodes.add(self.workflow.entry_point)

            # Execute workflow
            await self._execute_workflow()

            # Mark as completed
            self.execution_state = WorkflowState.COMPLETED
            self.successful_executions += 1

            execution_time = (time.monotonic() - start_time) * 1000
            self.logger.info(
                f"Workflow {workflow_id} completed successfully in {execution_time:.2f}ms"
            )

            return self.current_state

        except _LANGGRAPH_ORCHESTRATOR_OPERATION_ERRORS as e:
            self.execution_state = WorkflowState.FAILED
            self.failed_executions += 1

            execution_time = (time.monotonic() - start_time) * 1000
            self.logger.error(f"Workflow {workflow_id} failed after {execution_time:.2f}ms: {e}")

            # Record failure in state
            self.current_state.update("execution_error", str(e))

            raise

    async def _execute_workflow(self) -> None:
        """Execute the workflow graph."""
        max_iterations = 100  # Prevent infinite loops
        iteration = 0

        while (
            self.current_state.pending_nodes
            and iteration < max_iterations
            and self.execution_state == WorkflowState.RUNNING
        ):
            iteration += 1

            # Get next node to execute (simple FIFO for now)
            next_node_id = next(iter(self.current_state.pending_nodes))
            self.current_state.pending_nodes.remove(next_node_id)

            # Execute node
            node = self.workflow.nodes.get(next_node_id)
            if not node:
                self.logger.warning(f"Node {next_node_id} not found in workflow")
                continue

            self.logger.debug(f"Executing node: {next_node_id}")
            self.current_state.current_node = next_node_id

            result = await node.execute(self.current_state)
            self.current_state.record_node_execution(result)

            # Handle execution result
            if result.state == NodeState.FAILED:
                # Fail the entire workflow on node failure
                raise Exception(f"Node {next_node_id} failed: {result.error}")

            # Add next nodes to pending
            next_nodes = await self.workflow.get_next_nodes(next_node_id, self.current_state)
            for next_node in next_nodes:
                if next_node not in self.current_state.executed_nodes:
                    self.current_state.pending_nodes.add(next_node)

        if iteration >= max_iterations:
            raise Exception(f"Workflow exceeded maximum iterations ({max_iterations})")

    def pause(self) -> None:
        """Pause workflow execution."""
        if self.execution_state == WorkflowState.RUNNING:
            self.execution_state = WorkflowState.PAUSED
            self.logger.info(f"Workflow {self.current_state.workflow_id} paused")

    def resume(self) -> None:
        """Resume workflow execution."""
        if self.execution_state == WorkflowState.PAUSED:
            self.execution_state = WorkflowState.RUNNING
            self.logger.info(f"Workflow {self.current_state.workflow_id} resumed")

    def cancel(self) -> None:
        """Cancel workflow execution."""
        self.execution_state = WorkflowState.CANCELLED
        self.logger.info(f"Workflow {self.current_state.workflow_id} cancelled")

    def get_metrics(self) -> JSONDict:
        """Get executor metrics."""
        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": (
                self.successful_executions / self.total_executions
                if self.total_executions > 0
                else 0
            ),
            "current_state": self.execution_state.value if self.execution_state else None,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# Pre-built workflow templates
def create_governance_workflow() -> WorkflowDefinition:
    """
    Create a standard governance workflow.

    This implements the pattern shown in the roadmap:
    classifier → validator → deliberator → executor → auditor
    """
    workflow = WorkflowDefinition(
        workflow_id="governance_standard",
        name="Standard Governaflow",
        description="Complete governance workflow with classification, validation, deliberation, and execution",
    )

    # Create nodes
    classifier = GovernanceWorkflowNode("classifier", "route_by_complexity")
    validator = GovernanceWorkflowNode("validator", "validate_compliance")
    deliberator = GovernanceWorkflowNode("deliberator", "check_security")
    executor = GovernanceWorkflowNode("executor", "execute_decision")
    auditor = GovernanceWorkflowNode("auditor", "audit_decision")

    # Create conditional routing
    def route_by_complexity(state: GlobalState) -> str:
        complexity = state.get("complexity_score", 0)
        return "deliberator" if complexity > 0.5 else "executor"

    complexity_router = ConditionalNode("complexity_router", route_by_complexity)

    # Add nodes
    workflow.add_node(classifier)
    workflow.add_node(validator)
    workflow.add_node(complexity_router)
    workflow.add_node(deliberator)
    workflow.add_node(executor)
    workflow.add_node(auditor)

    # Define edges
    workflow.add_edge("classifier", "complexity_router")
    workflow.add_conditional_edge("complexity_router", complexity_router)
    workflow.add_edge("validator", "deliberator")
    workflow.add_edge("deliberator", "executor")
    workflow.add_edge("executor", "auditor")

    return workflow


# Global workflow registry
_workflow_registry: dict[str, WorkflowDefinition] = {}


def register_workflow(workflow: WorkflowDefinition) -> None:
    """Register a workflow definition."""
    _workflow_registry[workflow.workflow_id] = workflow


def get_workflow(workflow_id: str) -> WorkflowDefinition | None:
    """Get a registered workflow."""
    return _workflow_registry.get(workflow_id)


# Initialize standard workflows
register_workflow(create_governance_workflow())

__all__ = [
    "CONSTITUTIONAL_HASH",
    "BaseNode",
    "ConditionalNode",
    "GlobalState",
    "GovernanceWorkflowNode",
    "NodeExecutionResult",
    "NodeState",
    "WorkflowDefinition",
    "WorkflowExecutor",
    "WorkflowState",
    "create_governance_workflow",
    "get_workflow",
    "register_workflow",
]


def create_governance_workflow() -> WorkflowDefinition:  # type: ignore[no-redef]
    """
    Create a standard governance workflow.

    This implements the pattern shown in the roadmap:
    classifier → validator → deliberator → executor → auditor
    """
    workflow = WorkflowDefinition(
        workflow_id="governance_standard",
        name="Standard Governance Workflow",
        description="Complete governance workflow with classification, validation, deliberation, and execution",
        entry_point="classifier",  # Set proper entry point
    )

    # Create nodes
    classifier = GovernanceWorkflowNode("classifier", "route_by_complexity")
    validator = GovernanceWorkflowNode("validator", "validate_compliance")
    deliberator = GovernanceWorkflowNode("deliberator", "check_security")
    executor = GovernanceWorkflowNode("executor", "execute_decision")
    auditor = GovernanceWorkflowNode("auditor", "audit_decision")

    # Create conditional routing
    def route_by_complexity(state: GlobalState) -> str:
        complexity = state.get("complexity_score", 0)
        return "deliberator" if complexity > 0.5 else "executor"

    complexity_router = ConditionalNode("complexity_router", route_by_complexity)

    # Add nodes
    workflow.add_node(classifier)
    workflow.add_node(validator)
    workflow.add_node(complexity_router)
    workflow.add_node(deliberator)
    workflow.add_node(executor)
    workflow.add_node(auditor)

    # Define edges
    workflow.add_edge("classifier", "complexity_router")
    workflow.add_conditional_edge("complexity_router", complexity_router)
    workflow.add_edge("validator", "deliberator")
    workflow.add_edge("deliberator", "executor")
    workflow.add_edge("executor", "auditor")

    return workflow
