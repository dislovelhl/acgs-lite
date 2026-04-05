"""
ACGS-2 LangGraph Orchestration - Data Models
Constitutional Hash: 608508a9bd224290

Core data models for graph-based workflow orchestration:
- State models for Memory Object Protocol
- Node and Edge definitions
- Execution context and results
- Checkpoint and interrupt models
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# Type variables
TState = TypeVar("TState", bound=JSONDict)
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")

# Node function type: (CurrentState) -> NewState
NodeFunction = Callable[[JSONDict], Awaitable[JSONDict]]
ConditionalFunction = Callable[[JSONDict], str]


# =============================================================================
# Enums
# =============================================================================


class NodeType(str, Enum):
    """Types of nodes in the execution graph.

    Constitutional Hash: 608508a9bd224290
    """

    START = "start"
    END = "end"
    FUNCTION = "function"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    SUBGRAPH = "subgraph"
    CHECKPOINT = "checkpoint"
    INTERRUPT = "interrupt"
    SUPERVISOR = "supervisor"
    WORKER = "worker"


class NodeStatus(str, Enum):
    """Execution status of a node.

    Constitutional Hash: 608508a9bd224290
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"
    WAITING = "waiting"


class EdgeType(str, Enum):
    """Types of edges in the execution graph.

    Constitutional Hash: 608508a9bd224290
    """

    SEQUENTIAL = "sequential"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    LOOP = "loop"


class ExecutionStatus(str, Enum):
    """Overall execution status of a graph.

    Constitutional Hash: 608508a9bd224290
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class CheckpointStatus(str, Enum):
    """Status of a checkpoint.

    Constitutional Hash: 608508a9bd224290
    """

    CREATED = "created"
    VALIDATED = "validated"
    FAILED = "failed"
    RESTORED = "restored"


class InterruptType(str, Enum):
    """Types of execution interrupts.

    Constitutional Hash: 608508a9bd224290
    """

    HITL = "hitl"  # Human-in-the-loop
    CHECKPOINT = "checkpoint"  # Checkpoint trigger
    TIMEOUT = "timeout"  # Timeout trigger
    CONSTITUTIONAL = "constitutional"  # Constitutional validation required
    ERROR = "error"  # Error condition
    USER = "user"  # User-initiated


# =============================================================================
# State Models (Memory Object Protocol)
# =============================================================================


class GraphState(BaseModel):
    """Graph execution state with typed JSON schema.

    Implements Memory Object Protocol with strictly typed mutations.
    Constitutional Hash: 608508a9bd224290
    """

    # State data
    data: JSONDict = Field(default_factory=dict, description="Current state data")

    # Metadata
    version: int = Field(default=0, description="State version for optimistic locking")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last update timestamp",
    )
    last_node_id: str | None = Field(default=None, description="Last node that modified state")

    # Constitutional compliance
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )

    # Audit trail
    mutation_history: list[JSONDict] = Field(
        default_factory=list, description="History of state mutations"
    )
    max_history_size: int = Field(default=100, description="Maximum mutation history size")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get(self, key: str, default: object = None) -> object:
        """Get a value from state data."""
        return self.data.get(key, default)

    def set(self, key: str, value: object, node_id: str | None = None) -> "GraphState":
        """Set a value in state data with mutation tracking."""
        old_value = self.data.get(key)
        new_data = self.data.copy()
        new_data[key] = value

        # Track mutation
        mutation = {
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "node_id": node_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": self.version + 1,
        }

        new_history = self.mutation_history.copy()
        new_history.append(mutation)
        if len(new_history) > self.max_history_size:
            new_history = new_history[-self.max_history_size :]

        return GraphState(
            data=new_data,
            version=self.version + 1,
            last_updated=datetime.now(UTC),
            last_node_id=node_id,
            constitutional_hash=self.constitutional_hash,
            mutation_history=new_history,
            max_history_size=self.max_history_size,
        )

    def merge(self, updates: JSONDict, node_id: str | None = None) -> "GraphState":
        """Merge updates into state data."""
        new_data = self.data.copy()
        new_data.update(updates)

        mutation = {
            "operation": "merge",
            "updates": updates,
            "node_id": node_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": self.version + 1,
        }

        new_history = self.mutation_history.copy()
        new_history.append(mutation)
        if len(new_history) > self.max_history_size:
            new_history = new_history[-self.max_history_size :]

        return GraphState(
            data=new_data,
            version=self.version + 1,
            last_updated=datetime.now(UTC),
            last_node_id=node_id,
            constitutional_hash=self.constitutional_hash,
            mutation_history=new_history,
            max_history_size=self.max_history_size,
        )

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "data": self.data,
            "version": self.version,
            "last_updated": self.last_updated.isoformat(),
            "last_node_id": self.last_node_id,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "GraphState":
        """Create from dictionary."""
        return cls(
            data=data.get("data", {}),
            version=data.get("version", 0),
            last_node_id=data.get("last_node_id"),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )


class StateSnapshot(BaseModel):
    """Snapshot of graph state for persistence and recovery.

    Constitutional Hash: 608508a9bd224290
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    state: GraphState
    node_id: str
    step_index: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    metadata: JSONDict = Field(default_factory=dict)


class StateDelta(BaseModel):
    """Represents a state change (delta) for efficient transmission.

    Constitutional Hash: 608508a9bd224290
    """

    from_version: int
    to_version: int
    changes: list[JSONDict] = Field(default_factory=list)
    node_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class StateReducer(BaseModel):
    """Configuration for state reduction strategies.

    Constitutional Hash: 608508a9bd224290
    """

    strategy: str = Field(default="merge", description="merge, overwrite, or custom")
    merge_keys: list[str] = Field(
        default_factory=list, description="Keys to merge (for merge strategy)"
    )
    overwrite_keys: list[str] = Field(default_factory=list, description="Keys to overwrite")
    preserve_keys: list[str] = Field(
        default_factory=list, description="Keys to preserve from original"
    )


# =============================================================================
# Node Models
# =============================================================================


class GraphNode(BaseModel):
    """Node definition in the execution graph.

    Nodes are pure functions: (CurrentState) -> NewState
    Constitutional Hash: 608508a9bd224290
    """

    id: str
    name: str
    node_type: NodeType
    description: str = ""

    # Function reference (stored as module path string for serialization)
    function_path: str | None = None

    # Node configuration
    timeout_ms: float = Field(default=5000.0, description="Node execution timeout")
    retry_count: int = Field(default=3, description="Number of retries on failure")
    retry_delay_ms: float = Field(default=100.0, description="Delay between retries")

    # Constitutional compliance
    requires_maci_role: str | None = Field(
        default=None, description="Required MACI role for execution"
    )
    constitutional_checkpoint: bool = Field(
        default=False, description="Create checkpoint after execution"
    )

    # Interrupt configuration
    interrupt_before: bool = Field(default=False, description="Interrupt before execution")
    interrupt_after: bool = Field(default=False, description="Interrupt after execution")

    # Metadata
    metadata: JSONDict = Field(default_factory=dict)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(arbitrary_types_allowed=True)


class NodeResult(BaseModel):
    """Result of node execution.

    Constitutional Hash: 608508a9bd224290
    """

    node_id: str
    status: NodeStatus
    output_state: JSONDict | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    retries_used: int = 0
    constitutional_validated: bool = False
    checkpoint_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == NodeStatus.COMPLETED


# =============================================================================
# Edge Models
# =============================================================================


class GraphEdge(BaseModel):
    """Edge definition connecting nodes in the graph.

    Constitutional Hash: 608508a9bd224290
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType = EdgeType.SEQUENTIAL
    condition: str | None = Field(
        default=None, description="Condition expression for conditional edges"
    )
    priority: int = Field(default=0, description="Edge priority for parallel execution")
    metadata: JSONDict = Field(default_factory=dict)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class ConditionalEdge(BaseModel):
    """Conditional edge with routing logic.

    Constitutional Hash: 608508a9bd224290
    """

    source_node_id: str
    conditions: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of condition values to target node IDs",
    )
    default_target: str | None = Field(
        default=None, description="Default target if no condition matches"
    )
    condition_function_path: str | None = Field(
        default=None, description="Path to condition evaluation function"
    )
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


# =============================================================================
# Graph Definition
# =============================================================================


class GraphConfig(BaseModel):
    """Configuration for graph execution.

    Constitutional Hash: 608508a9bd224290
    """

    # Execution settings
    max_iterations: int = Field(default=100, description="Maximum loop iterations")
    global_timeout_ms: float = Field(default=30000.0, description="Global execution timeout")
    enable_checkpoints: bool = Field(default=True, description="Enable checkpointing")
    checkpoint_interval: int = Field(default=5, description="Steps between automatic checkpoints")

    # Constitutional settings
    constitutional_validation: bool = Field(
        default=True, description="Enable constitutional validation"
    )
    maci_enforcement: bool = Field(default=True, description="Enable MACI enforcement")

    # HITL settings
    hitl_enabled: bool = Field(default=True, description="Enable HITL interrupts")
    hitl_timeout_ms: float = Field(default=300000.0, description="HITL response timeout")

    # Performance settings
    parallel_execution: bool = Field(default=True, description="Enable parallel node execution")
    max_parallel_nodes: int = Field(default=10, description="Maximum concurrent node executions")

    # Persistence settings
    persist_state: bool = Field(default=True, description="Persist state changes")
    state_ttl_seconds: int = Field(default=86400, description="State TTL in seconds")

    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class GraphDefinition(BaseModel):
    """Complete graph definition for workflow orchestration.

    Constitutional Hash: 608508a9bd224290
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    version: str = "1.0.0"

    # Graph structure
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    conditional_edges: list[ConditionalEdge] = Field(default_factory=list)

    # Special nodes
    start_node_id: str | None = None
    end_node_ids: list[str] = Field(default_factory=list)

    # Configuration
    config: GraphConfig = Field(default_factory=GraphConfig)

    # Initial state schema
    initial_state_schema: JSONDict = Field(default_factory=dict)

    # Metadata
    metadata: JSONDict = Field(default_factory=dict)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_node(self, node_id: str) -> GraphNode | None:
        """Get node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_outgoing_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source_node_id == node_id]

    def get_incoming_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all edges targeting a node."""
        return [e for e in self.edges if e.target_node_id == node_id]

    def validate_graph(self) -> list[str]:
        """Validate graph structure.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        node_ids = {n.id for n in self.nodes}

        # Validate basic graph structure
        errors.extend(self._validate_start_node())
        errors.extend(self._validate_end_nodes())
        errors.extend(self._validate_edge_references(node_ids))
        errors.extend(self._validate_conditional_edge_references(node_ids))

        return errors

    def _validate_start_node(self) -> list[str]:
        """Validate start node configuration."""
        errors = []
        if not self.start_node_id:
            errors.append("No start node defined")
        elif not self.get_node(self.start_node_id):
            errors.append(f"Start node '{self.start_node_id}' not found")
        return errors

    def _validate_end_nodes(self) -> list[str]:
        """Validate end nodes configuration."""
        errors = []
        if not self.end_node_ids:
            errors.append("No end nodes defined")

        for end_id in self.end_node_ids:
            if not self.get_node(end_id):
                errors.append(f"End node '{end_id}' not found")

        return errors

    def _validate_edge_references(self, node_ids: set[str]) -> list[str]:
        """Validate edge node references exist."""
        errors = []
        for edge in self.edges:
            if edge.source_node_id not in node_ids:
                errors.append(f"Edge source '{edge.source_node_id}' not found")
            if edge.target_node_id not in node_ids:
                errors.append(f"Edge target '{edge.target_node_id}' not found")
        return errors

    def _validate_conditional_edge_references(self, node_ids: set[str]) -> list[str]:
        """Validate conditional edge node references exist."""
        errors = []
        for cond_edge in self.conditional_edges:
            if cond_edge.source_node_id not in node_ids:
                errors.append(f"Conditional edge source '{cond_edge.source_node_id}' not found")
            for target in cond_edge.conditions.values():
                if target not in node_ids:
                    errors.append(f"Conditional edge target '{target}' not found")
        return errors


# =============================================================================
# Execution Models
# =============================================================================


class ExecutionContext(BaseModel):
    """Context for graph execution.

    Constitutional Hash: 608508a9bd224290
    """

    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    graph_id: str
    tenant_id: str = "default"

    # Execution state
    current_state: GraphState = Field(default_factory=GraphState)
    current_node_id: str | None = None
    step_count: int = 0
    iteration_count: int = 0

    # Status tracking
    status: ExecutionStatus = ExecutionStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Node execution history
    node_results: list[NodeResult] = Field(default_factory=list)

    # Checkpoints
    checkpoints: list[str] = Field(default_factory=list)
    last_checkpoint_id: str | None = None

    # Constitutional compliance
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    maci_session_id: str | None = None

    # Metadata
    metadata: JSONDict = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ExecutionResult(BaseModel):
    """Result of graph execution.

    Constitutional Hash: 608508a9bd224290
    """

    workflow_id: str
    run_id: str
    status: ExecutionStatus
    final_state: GraphState | None = None
    output: JSONDict | None = None
    error: str | None = None

    # Performance metrics
    total_execution_time_ms: float = 0.0
    node_count: int = 0
    step_count: int = 0
    p50_node_time_ms: float | None = None
    p99_node_time_ms: float | None = None

    # Constitutional compliance
    constitutional_validated: bool = False
    checkpoint_count: int = 0

    # Timestamps
    started_at: datetime | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


# =============================================================================
# Checkpoint Models
# =============================================================================


class Checkpoint(BaseModel):
    """Checkpoint for state persistence and recovery.

    Constitutional Hash: 608508a9bd224290
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    run_id: str
    node_id: str
    step_index: int

    # State snapshot
    state: GraphState

    # Validation
    status: CheckpointStatus = CheckpointStatus.CREATED
    constitutional_validated: bool = False
    maci_validated: bool = False

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    validated_at: datetime | None = None

    # Metadata
    metadata: JSONDict = Field(default_factory=dict)
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


# =============================================================================
# Interrupt Models
# =============================================================================


class InterruptRequest(BaseModel):
    """Request for execution interrupt.

    Constitutional Hash: 608508a9bd224290
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    node_id: str
    interrupt_type: InterruptType
    reason: str
    current_state: GraphState
    checkpoint_id: str | None = None
    timeout_ms: float = Field(default=300000.0)
    metadata: JSONDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class InterruptResponse(BaseModel):
    """Response to an interrupt request.

    Constitutional Hash: 608508a9bd224290
    """

    request_id: str
    action: str = Field(description="continue, abort, modify, retry")
    modified_state: GraphState | None = None
    user_input: JSONDict | None = None
    responded_by: str | None = None
    responded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


__all__ = [
    # Checkpoint Models
    "Checkpoint",
    "CheckpointStatus",
    "ConditionalEdge",
    "ConditionalFunction",
    "EdgeType",
    # Execution Models
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionStatus",
    # Graph Models
    "GraphConfig",
    "GraphDefinition",
    # Edge Models
    "GraphEdge",
    # Node Models
    "GraphNode",
    # State Models
    "GraphState",
    # Interrupt Models
    "InterruptRequest",
    "InterruptResponse",
    "InterruptType",
    # Type aliases
    "NodeFunction",
    "NodeResult",
    "NodeStatus",
    # Enums
    "NodeType",
    "StateDelta",
    "StateReducer",
    "StateSnapshot",
]
