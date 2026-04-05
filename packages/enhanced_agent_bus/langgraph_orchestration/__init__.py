"""
ACGS-2 LangGraph-Style Orchestration Module
Constitutional Hash: 608508a9bd224290

Graph-based workflow execution engine implementing:
- Cyclic state machine patterns (Actor Model)
- Memory Object Protocol with typed JSON state mutations
- Human-in-the-loop interrupts at configurable checkpoints
- Constitutional compliance by design (MACI integration)
- Supervisor-Worker hierarchical orchestration

Reference: docs/ROADMAP_2025.md Phase 3.1 CEOS Architecture
"""

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__version__ = "1.0.0"
__constitutional_hash__ = CONSTITUTIONAL_HASH

# Core orchestration components
from .constitutional_checkpoints import (
    CheckpointValidator,
    ConstitutionalCheckpoint,
    ConstitutionalCheckpointManager,
    ConstitutionalHashValidator,
    MACIRoleValidator,
    StateIntegrityValidator,
    create_checkpoint_manager,
)
from .exceptions import (
    CheckpointError,
    ConstitutionalViolationError,
    CyclicDependencyError,
    GraphValidationError,
    InterruptError,
    MACIViolationError,
    NodeExecutionError,
    OrchestrationError,
    StateTransitionError,
)
from .exceptions import (
    TimeoutError as OrchestrationTimeoutError,
)
from .graph_orchestrator import (
    GraphOrchestrator,
    GraphOrchestratorConfig,
    create_graph_orchestrator,
)
from .hitl_integration import (
    HITLAction,
    HITLConfig,
    HITLInterruptHandler,
    HITLRequest,
    HITLResponse,
    InMemoryHITLHandler,
    create_hitl_handler,
)
from .models import (
    # Checkpoint models
    Checkpoint,
    CheckpointStatus,
    ConditionalEdge,
    # Edge definitions
    EdgeType,
    # Execution models
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    GraphConfig,
    # Graph definition
    GraphDefinition,
    GraphEdge,
    # Node definitions
    GraphNode,
    # State management
    GraphState,
    InterruptRequest,
    InterruptResponse,
    # Interrupt models
    InterruptType,
    NodeResult,
    NodeStatus,
    NodeType,
    StateDelta,
    StateReducer,
    StateSnapshot,
)
from .node_executor import (
    AsyncNodeExecutor,
    ConditionalNodeExecutor,
    NodeExecutor,
    ParallelNodeExecutor,
)
from .persistence import (
    InMemoryStatePersistence,
    RedisStatePersistence,
    StatePersistence,
    create_state_persistence,
)
from .state_reducer import (
    AccumulatorStateReducer,
    BaseStateReducer,
    CustomStateReducer,
    ImmutableStateReducer,
    MergeStateReducer,
    OverwriteStateReducer,
    create_state_reducer,
)
from .supervisor_worker import (
    SupervisorNode,
    SupervisorWorkerOrchestrator,
    TaskPriority,
    WorkerNode,
    WorkerPool,
    WorkerStatus,
    WorkerTask,
    WorkerTaskResult,
    create_supervisor_worker,
)

# Feature availability flags
LANGGRAPH_AVAILABLE = True

__all__ = [
    "CONSTITUTIONAL_HASH",
    "LANGGRAPH_AVAILABLE",
    # State Reducers
    "AccumulatorStateReducer",
    "AsyncNodeExecutor",
    "BaseStateReducer",
    # Models - Checkpoints
    "Checkpoint",
    "CheckpointError",
    "CheckpointStatus",
    "CheckpointValidator",
    "ConditionalEdge",
    "ConditionalNodeExecutor",
    # Constitutional Checkpoints
    "ConstitutionalCheckpoint",
    "ConstitutionalCheckpointManager",
    "ConstitutionalHashValidator",
    # Exceptions
    "ConstitutionalViolationError",
    "CustomStateReducer",
    "CyclicDependencyError",
    # Models - Edges
    "EdgeType",
    # Models - Execution
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionStatus",
    "GraphConfig",
    # Models - Graph
    "GraphDefinition",
    "GraphEdge",
    # Models - Nodes
    "GraphNode",
    # Graph Orchestrator
    "GraphOrchestrator",
    "GraphOrchestratorConfig",
    # Models - State
    "GraphState",
    "GraphValidationError",
    # HITL Integration
    "HITLAction",
    "HITLConfig",
    "HITLInterruptHandler",
    "HITLRequest",
    "HITLResponse",
    "ImmutableStateReducer",
    "InMemoryHITLHandler",
    "InMemoryStatePersistence",
    "InterruptError",
    "InterruptRequest",
    "InterruptResponse",
    # Models - Interrupts
    "InterruptType",
    "MACIRoleValidator",
    "MACIViolationError",
    "MergeStateReducer",
    "NodeExecutionError",
    # Node Executors
    "NodeExecutor",
    "NodeResult",
    "NodeStatus",
    "NodeType",
    "OrchestrationError",
    "OrchestrationTimeoutError",
    "OverwriteStateReducer",
    "ParallelNodeExecutor",
    "RedisStatePersistence",
    "StateDelta",
    "StateIntegrityValidator",
    # Persistence
    "StatePersistence",
    "StateReducer",
    "StateSnapshot",
    "StateTransitionError",
    # Supervisor-Worker
    "SupervisorNode",
    "SupervisorWorkerOrchestrator",
    "TaskPriority",
    "WorkerNode",
    "WorkerPool",
    "WorkerStatus",
    "WorkerTask",
    "WorkerTaskResult",
    "__constitutional_hash__",
    # Version and constants
    "__version__",
    "create_checkpoint_manager",
    "create_graph_orchestrator",
    "create_hitl_handler",
    "create_state_persistence",
    "create_state_reducer",
    "create_supervisor_worker",
]
