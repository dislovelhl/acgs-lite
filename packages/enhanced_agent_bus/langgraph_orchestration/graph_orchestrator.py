"""
ACGS-2 LangGraph Orchestration - Graph Orchestrator
Constitutional Hash: 608508a9bd224290

Main orchestration engine for graph-based workflow execution:
- Cyclic state machine with configurable patterns
- Node execution with constitutional checkpoints
- Parallel and conditional execution support
- Human-in-the-loop integration
- Performance monitoring (target: P99 <5ms)
"""

import asyncio
import statistics
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .constitutional_checkpoints import (
    ConstitutionalCheckpointManager,
    create_checkpoint_manager,
)
from .exceptions import (
    CyclicDependencyError,
    GraphValidationError,
    NodeExecutionError,
    OrchestrationError,
)
from .hitl_integration import (
    HITLAction,
    HITLInterruptHandler,
    create_hitl_handler,
)
from .models import (
    ConditionalEdge,
    EdgeType,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    GraphDefinition,
    GraphEdge,
    GraphNode,
    GraphState,
    InterruptType,
    NodeResult,
    NodeStatus,
    NodeType,
)
from .node_executor import (
    AsyncNodeExecutor,
    ConditionalNodeExecutor,
    NodeExecutor,
    ParallelNodeExecutor,
)
from .persistence import InMemoryStatePersistence, StatePersistence
from .state_reducer import BaseStateReducer, create_state_reducer

logger = get_logger(__name__)
GRAPH_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)
ERROR_CHECKPOINT_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


@dataclass
class GraphOrchestratorConfig:
    """Configuration for the graph orchestrator.

    Constitutional Hash: 608508a9bd224290
    """

    # Execution settings
    max_iterations: int = 100
    global_timeout_ms: float = 30000.0
    node_timeout_ms: float = 5000.0

    # Constitutional settings
    constitutional_validation: bool = True
    maci_enforcement: bool = True

    # Checkpoint settings
    enable_checkpoints: bool = True
    checkpoint_interval: int = 5
    checkpoint_on_error: bool = True

    # HITL settings
    hitl_enabled: bool = True
    hitl_timeout_ms: float = 300000.0

    # Performance settings
    parallel_execution: bool = True
    max_parallel_nodes: int = 10

    # Persistence settings
    persist_state: bool = True
    state_ttl_seconds: int = 86400

    # State reducer settings
    reducer_strategy: str = "merge"
    deep_merge: bool = False

    constitutional_hash: str = CONSTITUTIONAL_HASH


class GraphOrchestrator:
    """Main orchestration engine for graph-based workflow execution.

    Implements the cyclic state machine pattern from LangGraph:
    - Nodes are pure functions: (CurrentState) -> NewState
    - Conditional routing based on state
    - Human-in-the-loop interrupts at configurable points
    - Constitutional compliance at transition boundaries

    Performance targets:
    - P99 latency < 5ms for state transitions
    - Support for 1000+ concurrent workflows

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        graph: GraphDefinition,
        config: GraphOrchestratorConfig | None = None,
        executor: NodeExecutor | None = None,
        state_reducer: BaseStateReducer | None = None,
        persistence: StatePersistence | None = None,
        checkpoint_manager: ConstitutionalCheckpointManager | None = None,
        hitl_handler: HITLInterruptHandler | None = None,
        maci_enforcer: object | None = None,
    ):
        self.graph = graph
        self.config = config or GraphOrchestratorConfig()
        self.constitutional_hash = self.config.constitutional_hash

        # Initialize components
        self.executor = executor or AsyncNodeExecutor(
            default_timeout_ms=self.config.node_timeout_ms,
        )
        self.parallel_executor = ParallelNodeExecutor(
            base_executor=self.executor,
            max_concurrent=self.config.max_parallel_nodes,
        )
        self.conditional_executor = ConditionalNodeExecutor(
            base_executor=self.executor,
        )

        self.state_reducer = state_reducer or create_state_reducer(
            strategy=self.config.reducer_strategy,
            deep_merge=self.config.deep_merge,
        )

        self.persistence = persistence
        if self.config.persist_state and not self.persistence:
            self.persistence = InMemoryStatePersistence()

        self.checkpoint_manager = checkpoint_manager
        if self.config.enable_checkpoints and not self.checkpoint_manager:
            self.checkpoint_manager = create_checkpoint_manager(
                persistence=self.persistence,
                maci_enforcer=maci_enforcer,
            )

        self.hitl_handler = hitl_handler
        if self.config.hitl_enabled and not self.hitl_handler:
            self.hitl_handler = create_hitl_handler(
                checkpoint_manager=self.checkpoint_manager,
            )

        self.maci_enforcer = maci_enforcer

        # Validate graph
        self._validate_graph()

        # Build execution structures
        self._node_map: dict[str, GraphNode] = {n.id: n for n in self.graph.nodes}
        self._outgoing_edges: dict[str, list[GraphEdge]] = {}
        self._incoming_edges: dict[str, list[GraphEdge]] = {}
        self._conditional_edges: dict[str, list[ConditionalEdge]] = {}
        self._build_edge_maps()

        # Metrics
        self._execution_times: list[float] = []
        self._executions: int = 0

    def _validate_graph(self) -> None:
        """Validate graph structure."""
        errors = self.graph.validate_graph()
        if errors:
            raise GraphValidationError(
                validation_errors=errors,
                graph_id=self.graph.id,
            )

        # Check for invalid cycles
        # Note: Some cycles are valid in LangGraph (loops), but self-loops without conditions are not
        for node in self.graph.nodes:
            for edge in self.graph.edges:
                if edge.source_node_id == node.id and edge.target_node_id == node.id:
                    if edge.edge_type not in (EdgeType.LOOP, EdgeType.CONDITIONAL):
                        raise CyclicDependencyError(
                            cycle_path=[node.id, node.id],
                            graph_id=self.graph.id,
                        )

    def _build_edge_maps(self) -> None:
        """Build edge lookup maps for efficient traversal."""
        for edge in self.graph.edges:
            if edge.source_node_id not in self._outgoing_edges:
                self._outgoing_edges[edge.source_node_id] = []
            self._outgoing_edges[edge.source_node_id].append(edge)

            if edge.target_node_id not in self._incoming_edges:
                self._incoming_edges[edge.target_node_id] = []
            self._incoming_edges[edge.target_node_id].append(edge)

        for cond_edge in self.graph.conditional_edges:
            if cond_edge.source_node_id not in self._conditional_edges:
                self._conditional_edges[cond_edge.source_node_id] = []
            self._conditional_edges[cond_edge.source_node_id].append(cond_edge)

    def register_function(self, path: str, func: Callable) -> None:
        """Register a node function.

        Args:
            path: Function path identifier
            func: Function to register
        """
        self.executor.register_function(path, func)
        if isinstance(self.parallel_executor.base_executor, AsyncNodeExecutor):
            self.parallel_executor.base_executor.register_function(path, func)

    def register_condition(self, path: str, func: Callable[[JSONDict], str]) -> None:
        """Register a condition function.

        Args:
            path: Condition path identifier
            func: Condition function (state -> next_node_id)
        """
        self.conditional_executor.register_condition(path, func)

    async def run(
        self,
        input_data: JSONDict | None = None,
        initial_state: GraphState | None = None,
        workflow_id: str | None = None,
        tenant_id: str = "default",
        metadata: JSONDict | None = None,
    ) -> ExecutionResult:
        """Execute the graph workflow.

        Args:
            input_data: Initial input data (used if no initial_state)
            initial_state: Optional starting state
            workflow_id: Optional workflow identifier
            tenant_id: Tenant identifier
            metadata: Optional execution metadata

        Returns:
            Execution result with final state and metrics

        Constitutional Hash: 608508a9bd224290
        """
        start_time = time.perf_counter()
        workflow_id = workflow_id or str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # Initialize state
        if initial_state:
            state = initial_state
        else:
            state = GraphState(
                data=input_data or {},
                constitutional_hash=self.constitutional_hash,
            )

        # Create execution context
        context = ExecutionContext(
            workflow_id=workflow_id,
            run_id=run_id,
            graph_id=self.graph.id,
            tenant_id=tenant_id,
            current_state=state,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(UTC),
            metadata=metadata or {},
            constitutional_hash=self.constitutional_hash,
        )

        try:
            # Execute graph
            state, node_results = await self._execute_graph(state, context)

            # Calculate metrics
            execution_time = (time.perf_counter() - start_time) * 1000
            self._execution_times.append(execution_time)
            self._executions += 1

            exec_times = [r.execution_time_ms for r in node_results if r.execution_time_ms > 0]
            p50 = statistics.median(exec_times) if exec_times else None
            p99 = (
                sorted(exec_times)[int(len(exec_times) * 0.99)]
                if len(exec_times) > 1
                else (exec_times[0] if exec_times else None)
            )

            result = ExecutionResult(
                workflow_id=workflow_id,
                run_id=run_id,
                status=ExecutionStatus.COMPLETED,
                final_state=state,
                output=state.data,
                total_execution_time_ms=execution_time,
                node_count=len(node_results),
                step_count=context.step_count,
                p50_node_time_ms=p50,
                p99_node_time_ms=p99,
                constitutional_validated=True,
                checkpoint_count=len(context.checkpoints),
                started_at=context.started_at,
                completed_at=datetime.now(UTC),
                constitutional_hash=self.constitutional_hash,
            )

            # Persist result
            if self.persistence:
                await self.persistence.save_execution_result(result)

            return result

        except GRAPH_EXECUTION_ERRORS as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"Graph execution failed: {e}")

            # Create checkpoint on error if enabled
            if self.config.checkpoint_on_error and self.checkpoint_manager:
                try:
                    await self.checkpoint_manager.create_checkpoint(
                        context=context,
                        node_id=context.current_node_id or "error",
                        state=state,
                        metadata={"error": str(e)},
                    )
                except ERROR_CHECKPOINT_ERRORS as cp_error:
                    logger.error(f"Failed to create error checkpoint: {cp_error}")

            return ExecutionResult(
                workflow_id=workflow_id,
                run_id=run_id,
                status=ExecutionStatus.FAILED,
                final_state=state,
                error=str(e),
                total_execution_time_ms=execution_time,
                step_count=context.step_count,
                checkpoint_count=len(context.checkpoints),
                started_at=context.started_at,
                completed_at=datetime.now(UTC),
                constitutional_hash=self.constitutional_hash,
            )

    async def _execute_graph(
        self,
        state: GraphState,
        context: ExecutionContext,
    ) -> tuple[GraphState, list[NodeResult]]:
        """Execute the graph from start to end nodes.

        Args:
            state: Initial state
            context: Execution context

        Returns:
            Tuple of (final_state, all_node_results)
        """
        all_results: list[NodeResult] = []
        current_node_id = self.graph.start_node_id

        while current_node_id and context.iteration_count < self.config.max_iterations:
            context.iteration_count += 1
            context.current_node_id = current_node_id

            node = self._get_node_or_raise(current_node_id)

            # Handle end nodes
            if current_node_id in self.graph.end_node_ids:
                result = await self._execute_node(node, state, context)
                all_results.append(result)
                if result.output_state:
                    state = self.state_reducer.reduce(state, result.output_state, node.id)
                break

            # Execute node with full lifecycle
            state, result = await self._execute_node_with_lifecycle(
                node, state, context, all_results
            )
            current_node_id = await self._determine_next_node_and_persist(node, state, context)

        self._check_execution_timeout(context)
        return state, all_results

    def _get_node_or_raise(self, node_id: str) -> GraphNode:
        """Get node by ID or raise OrchestrationError."""
        node = self._node_map.get(node_id)
        if not node:
            raise OrchestrationError(
                message=f"Node '{node_id}' not found",
                details={"node_id": node_id},
            )
        return node

    async def _execute_node_with_lifecycle(
        self,
        node: GraphNode,
        state: GraphState,
        context: ExecutionContext,
        all_results: list[NodeResult],
    ) -> tuple[GraphState, NodeResult]:
        """Execute node with full lifecycle including interrupts and checkpoints."""
        # Handle interrupt before
        if node.interrupt_before:
            state = await self._handle_interrupt(node, state, context, before=True)

        # Execute node
        result = await self._execute_node(node, state, context)
        all_results.append(result)
        context.node_results.append(result)
        context.step_count += 1

        # Handle execution result
        await self._process_execution_result(result, context)

        # Update state
        if result.output_state:
            state = self.state_reducer.reduce(state, result.output_state, node.id)
            context.current_state = state

        # Handle interrupt after
        if node.interrupt_after:
            state = await self._handle_interrupt(node, state, context, before=False)

        # Create checkpoint if needed
        await self._create_checkpoint_if_needed(node, state, context)

        return state, result

    async def _process_execution_result(
        self, result: NodeResult, context: ExecutionContext
    ) -> None:
        """Process node execution result and handle failures."""
        if result.status != NodeStatus.COMPLETED:
            if result.status == NodeStatus.INTERRUPTED:
                context.status = ExecutionStatus.INTERRUPTED
            else:
                raise NodeExecutionError(
                    node_id=result.node_id,
                    node_type=self._node_map[result.node_id].node_type.value,
                    original_error=Exception(result.error or "Unknown error"),
                    execution_time_ms=result.execution_time_ms,
                )

    async def _create_checkpoint_if_needed(
        self, node: GraphNode, state: GraphState, context: ExecutionContext
    ) -> None:
        """Create checkpoint if required by node or interval."""
        should_checkpoint = node.constitutional_checkpoint or (
            self.config.enable_checkpoints
            and context.step_count % self.config.checkpoint_interval == 0
        )

        if should_checkpoint and self.checkpoint_manager:
            await self.checkpoint_manager.create_checkpoint(
                context=context,
                node_id=node.id,
                state=state,
            )

    async def _determine_next_node_and_persist(
        self, node: GraphNode, state: GraphState, context: ExecutionContext
    ) -> str | None:
        """Determine next node and persist state."""
        # Determine next node
        next_node_id = await self._get_next_node(node.id, state)

        # Save state
        if self.persistence:
            await self.persistence.save_state(
                workflow_id=context.workflow_id,
                run_id=context.run_id,
                state=state,
                node_id=node.id,
                step_index=context.step_count,
            )

        return next_node_id

    def _check_execution_timeout(self, context: ExecutionContext) -> None:
        """Check if execution reached max iterations."""
        if context.iteration_count >= self.config.max_iterations:
            logger.warning(f"Graph execution reached max iterations ({self.config.max_iterations})")

    async def _execute_node(
        self,
        node: GraphNode,
        state: GraphState,
        context: ExecutionContext,
    ) -> NodeResult:
        """Execute a single node.

        Args:
            node: Node to execute
            state: Current state
            context: Execution context

        Returns:
            Node execution result
        """
        exec_context = {
            "workflow_id": context.workflow_id,
            "run_id": context.run_id,
            "step_count": context.step_count,
            "tenant_id": context.tenant_id,
            "constitutional_hash": self.constitutional_hash,
        }

        # Check for parallel nodes
        if node.node_type == NodeType.PARALLEL:
            # Get parallel target nodes
            outgoing = self._outgoing_edges.get(node.id, [])
            parallel_nodes = [
                self._node_map[e.target_node_id]
                for e in outgoing
                if e.edge_type == EdgeType.PARALLEL
            ]

            if parallel_nodes:
                results = await self.parallel_executor.execute_parallel(
                    parallel_nodes, state, exec_context
                )
                # Aggregate results
                combined_output: JSONDict = {}
                total_time = 0.0
                for r in results:
                    if r.output_state:
                        combined_output.update(r.output_state)
                    total_time = max(total_time, r.execution_time_ms)

                return NodeResult(
                    node_id=node.id,
                    status=NodeStatus.COMPLETED,
                    output_state=combined_output,
                    execution_time_ms=total_time,
                    constitutional_validated=True,
                    constitutional_hash=self.constitutional_hash,
                )

        # Standard execution
        return await self.executor.execute(node, state, exec_context)

    async def _get_next_node(
        self,
        current_node_id: str,
        state: GraphState,
    ) -> str | None:
        """Determine the next node to execute.

        Args:
            current_node_id: Current node ID
            state: Current state

        Returns:
            Next node ID or None if done
        """
        # Check conditional edges first
        cond_edges = self._conditional_edges.get(current_node_id, [])
        if cond_edges:
            next_node = await self.conditional_executor.route(cond_edges, current_node_id, state)
            if next_node:
                return next_node

        # Check regular edges
        outgoing = self._outgoing_edges.get(current_node_id, [])
        for edge in outgoing:
            if edge.edge_type == EdgeType.SEQUENTIAL:
                return edge.target_node_id

        return None

    async def _handle_interrupt(
        self,
        node: GraphNode,
        state: GraphState,
        context: ExecutionContext,
        before: bool,
    ) -> GraphState:
        """Handle HITL interrupt.

        Args:
            node: Current node
            state: Current state
            context: Execution context
            before: True if interrupt is before node execution

        Returns:
            Potentially modified state
        """
        if not self.hitl_handler or not self.config.hitl_enabled:
            return state

        interrupt_type = InterruptType.HITL
        reason = f"Interrupt {'before' if before else 'after'} node {node.id}"

        request = await self.hitl_handler.create_interrupt(
            context=context,
            node_id=node.id,
            interrupt_type=interrupt_type,
            reason=reason,
            state=state,
            timeout_ms=self.config.hitl_timeout_ms,
        )

        response = await self.hitl_handler.handle_interrupt(request)

        if response.action == HITLAction.ABORT:
            raise OrchestrationError(
                message="Workflow aborted by HITL response",
                details={"node_id": node.id, "reason": response.reason},
            )
        elif response.action == HITLAction.MODIFY and response.modified_state:
            return response.modified_state

        return state

    async def resume_from_checkpoint(
        self,
        checkpoint_id: str,
        workflow_id: str,
        tenant_id: str = "default",
    ) -> ExecutionResult:
        """Resume execution from a checkpoint.

        Args:
            checkpoint_id: Checkpoint to resume from
            workflow_id: Workflow identifier
            tenant_id: Tenant identifier

        Returns:
            Execution result
        """
        if not self.checkpoint_manager:
            raise OrchestrationError(
                message="Checkpoints not enabled",
                details={"checkpoint_id": checkpoint_id},
            )

        # Create new context for resume
        context = ExecutionContext(
            workflow_id=workflow_id,
            run_id=str(uuid.uuid4()),
            graph_id=self.graph.id,
            tenant_id=tenant_id,
            status=ExecutionStatus.PENDING,
            constitutional_hash=self.constitutional_hash,
        )

        # Restore checkpoint
        checkpoint, state = await self.checkpoint_manager.restore_checkpoint(checkpoint_id, context)

        # Resume from checkpoint node
        context.current_node_id = checkpoint.node_id
        context.step_count = checkpoint.step_index
        context.current_state = state
        context.status = ExecutionStatus.RUNNING
        context.started_at = datetime.now(UTC)

        # Continue execution
        return await self.run(
            initial_state=state,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            metadata={"resumed_from_checkpoint": checkpoint_id},
        )

    def get_metrics(self) -> JSONDict:
        """Get orchestrator metrics.

        Returns:
            Dictionary of performance metrics
        """
        if not self._execution_times:
            return {
                "executions": 0,
                "constitutional_hash": self.constitutional_hash,
            }

        sorted_times = sorted(self._execution_times)
        return {
            "executions": self._executions,
            "avg_execution_time_ms": statistics.mean(self._execution_times),
            "p50_execution_time_ms": statistics.median(self._execution_times),
            "p95_execution_time_ms": (
                sorted_times[int(len(sorted_times) * 0.95)]
                if len(sorted_times) > 1
                else sorted_times[0]
            ),
            "p99_execution_time_ms": (
                sorted_times[int(len(sorted_times) * 0.99)]
                if len(sorted_times) > 1
                else sorted_times[0]
            ),
            "min_execution_time_ms": min(self._execution_times),
            "max_execution_time_ms": max(self._execution_times),
            "constitutional_hash": self.constitutional_hash,
        }


def create_graph_orchestrator(
    graph: GraphDefinition,
    config: GraphOrchestratorConfig | None = None,
    persistence_backend: str = "memory",
    redis_url: str | None = None,
    maci_enforcer: object | None = None,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
) -> GraphOrchestrator:
    """Factory function to create a graph orchestrator.

    Args:
        graph: Graph definition to execute
        config: Optional orchestrator configuration
        persistence_backend: Persistence backend (memory, redis)
        redis_url: Redis URL for redis backend
        maci_enforcer: Optional MACI enforcer
        constitutional_hash: Constitutional hash to enforce

    Returns:
        Configured graph orchestrator

    Constitutional Hash: 608508a9bd224290
    """
    from .persistence import create_state_persistence

    # Create configuration
    if config is None:
        config = GraphOrchestratorConfig(constitutional_hash=constitutional_hash)

    # Create persistence
    persistence = None
    if config.persist_state:
        persistence = create_state_persistence(
            backend=persistence_backend,
            redis_url=redis_url,
            constitutional_hash=constitutional_hash,
        )

    # Create checkpoint manager
    checkpoint_manager = None
    if config.enable_checkpoints:
        checkpoint_manager = create_checkpoint_manager(
            persistence=persistence,
            maci_enforcer=maci_enforcer,
            constitutional_hash=constitutional_hash,
        )

    # Create HITL handler
    hitl_handler = None
    if config.hitl_enabled:
        hitl_handler = create_hitl_handler(
            checkpoint_manager=checkpoint_manager,
            constitutional_hash=constitutional_hash,
        )

    return GraphOrchestrator(
        graph=graph,
        config=config,
        persistence=persistence,
        checkpoint_manager=checkpoint_manager,
        hitl_handler=hitl_handler,
        maci_enforcer=maci_enforcer,
    )


__all__ = [
    "GraphOrchestrator",
    "GraphOrchestratorConfig",
    "create_graph_orchestrator",
]
