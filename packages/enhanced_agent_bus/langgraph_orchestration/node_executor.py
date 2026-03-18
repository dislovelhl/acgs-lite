"""
ACGS-2 LangGraph Orchestration - Node Executors
Constitutional Hash: cdd01ef066bc6cf2

Node executors handle the execution of graph nodes:
- Async execution with timeout handling
- Parallel execution with dependency tracking
- Conditional routing based on state
- Retry logic with exponential backoff
"""

import asyncio
import importlib
import inspect
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

from .exceptions import TimeoutError
from .models import (
    ConditionalEdge,
    GraphNode,
    GraphState,
    NodeResult,
    NodeStatus,
    NodeType,
)
from .state_reducer import BaseStateReducer, MergeStateReducer

logger = get_logger(__name__)
NodeFunction = Callable[[JSONDict], object]

_NODE_EXECUTOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


@dataclass
class _ExecutionConfig:
    """Configuration for node execution."""

    timeout_ms: float
    max_retries: int
    retry_delay: float


class NodeExecutor(ABC):
    """Abstract base class for node executors.

    Node executors handle the actual execution of graph nodes,
    including timeout handling, retries, and error management.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        state_reducer: BaseStateReducer | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.state_reducer = state_reducer or MergeStateReducer()
        self.constitutional_hash = constitutional_hash
        self._function_cache: dict[str, NodeFunction] = {}

    @abstractmethod
    async def execute(
        self,
        node: GraphNode,
        state: GraphState,
        context: JSONDict | None = None,
    ) -> NodeResult:
        """Execute a single node.

        Args:
            node: Node to execute
            state: Current graph state
            context: Optional execution context

        Returns:
            NodeResult with execution outcome
        """
        ...

    def get_function(self, node: GraphNode) -> NodeFunction | None:
        """Get or load node function.

        Args:
            node: Node definition

        Returns:
            Callable function or None
        """
        if not node.function_path:
            return None

        if node.function_path in self._function_cache:
            return self._function_cache[node.function_path]

        try:
            # Parse module path and function name
            parts = node.function_path.rsplit(".", 1)
            if len(parts) != 2:
                logger.error(f"Invalid function path: {node.function_path}")
                return None

            module_path, func_name = parts
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)

            self._function_cache[node.function_path] = func
            return func  # type: ignore[no-any-return]

        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load function {node.function_path}: {e}")
            return None

    def register_function(self, path: str, func: NodeFunction) -> None:
        """Register a function directly.

        Args:
            path: Function path identifier
            func: Function to register
        """
        self._function_cache[path] = func


class AsyncNodeExecutor(NodeExecutor):
    """Async node executor with timeout and retry support.

    Executes nodes asynchronously with configurable timeout
    and retry behavior.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        state_reducer: BaseStateReducer | None = None,
        default_timeout_ms: float = 5000.0,
        default_retries: int = 3,
        retry_backoff_factor: float = 2.0,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(state_reducer, constitutional_hash)
        self.default_timeout_ms = default_timeout_ms
        self.default_retries = default_retries
        self.retry_backoff_factor = retry_backoff_factor

    async def execute(
        self,
        node: GraphNode,
        state: GraphState,
        context: JSONDict | None = None,
    ) -> NodeResult:
        """Execute a node with timeout and retry handling."""
        start_time = time.perf_counter()
        execution_config = self._prepare_execution_config(node)

        # Early validation
        func = self.get_function(node)
        validation_result = self._validate_node_execution(node, func, start_time)
        if validation_result:
            return validation_result

        # Execute with retry
        last_error: Exception | None = None
        retries_used = 0

        for attempt in range(execution_config.max_retries + 1):
            try:
                output = await self._execute_node_operation(
                    node, state, context, func, execution_config.timeout_ms
                )

                execution_time = (time.perf_counter() - start_time) * 1000
                return self._create_success_result(node, output, execution_time, retries_used)

            except (TimeoutError, *_NODE_EXECUTOR_OPERATION_ERRORS) as e:
                last_error = e
                retries_used = attempt + 1

                should_retry = await self._handle_execution_error(
                    e, node, execution_config, attempt, start_time
                )
                if not should_retry:
                    break

        execution_time = (time.perf_counter() - start_time) * 1000
        return self._create_failure_result(node, last_error, execution_time, retries_used)

    def _prepare_execution_config(self, node: GraphNode) -> "_ExecutionConfig":
        """Prepare execution configuration from node settings."""
        return _ExecutionConfig(
            timeout_ms=node.timeout_ms or self.default_timeout_ms,
            max_retries=node.retry_count if node.retry_count >= 0 else self.default_retries,
            retry_delay=node.retry_delay_ms / 1000.0,
        )

    def _validate_node_execution(
        self, node: GraphNode, func: NodeFunction | None, start_time: float
    ) -> NodeResult | None:
        """Validate node can be executed, return error result if not."""
        if not func and node.node_type == NodeType.FUNCTION:
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.FAILED,
                error=f"Function not found: {node.function_path}",
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
                constitutional_hash=self.constitutional_hash,
            )
        return None

    async def _execute_node_operation(
        self,
        node: GraphNode,
        state: GraphState,
        context: JSONDict | None,
        func: NodeFunction | None,
        timeout_ms: float,
    ) -> JSONDict:
        """Execute the core node operation based on node type."""
        # Handle special node types
        if node.node_type == NodeType.START:
            return state.data.copy()  # type: ignore[no-any-return]
        elif node.node_type == NodeType.END:
            return state.data.copy()  # type: ignore[no-any-return]
        elif node.node_type == NodeType.CHECKPOINT:
            return {"checkpoint_triggered": True, "node_id": node.id}
        elif node.node_type == NodeType.INTERRUPT:
            return {"interrupt_triggered": True, "node_id": node.id}
        elif func:
            return await self._execute_function_node(func, state, context, timeout_ms)
        else:
            # Passthrough node
            return state.data.copy()  # type: ignore[no-any-return]

    async def _execute_function_node(
        self,
        func: NodeFunction,
        state: GraphState,
        context: JSONDict | None,
        timeout_ms: float,
    ) -> JSONDict:
        """Execute a function node with proper async/sync handling."""
        input_data = state.data.copy()
        if context:
            input_data["_context"] = context

        if inspect.iscoroutinefunction(func):
            output = await asyncio.wait_for(
                func(input_data),
                timeout=timeout_ms / 1000.0,
            )
        else:
            # Run sync function in thread pool
            loop = asyncio.get_running_loop()
            output = await asyncio.wait_for(
                loop.run_in_executor(None, func, input_data),
                timeout=timeout_ms / 1000.0,
            )

        # Ensure output is a dict
        if not isinstance(output, dict):
            output = {"result": output}

        return output

    async def _handle_execution_error(
        self,
        error: Exception,
        node: GraphNode,
        config: _ExecutionConfig,
        attempt: int,
        start_time: float,
    ) -> bool:
        """Handle execution error and determine if retry should occur."""
        # Convert asyncio.TimeoutError to our TimeoutError if needed
        if isinstance(error, asyncio.TimeoutError):
            # Create TimeoutError for logging/debugging purposes
            TimeoutError(
                operation=f"node:{node.id}",
                timeout_ms=config.timeout_ms,
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )

        if attempt < config.max_retries:
            await asyncio.sleep(config.retry_delay * (self.retry_backoff_factor**attempt))
            return True
        return False

    def _create_success_result(
        self, node: GraphNode, output: JSONDict, execution_time: float, retries_used: int
    ) -> NodeResult:
        """Create a successful execution result."""
        return NodeResult(
            node_id=node.id,
            status=NodeStatus.COMPLETED,
            output_state=output,
            execution_time_ms=execution_time,
            retries_used=retries_used,
            constitutional_validated=True,
            constitutional_hash=self.constitutional_hash,
        )

    def _create_failure_result(
        self,
        node: GraphNode,
        error: Exception | None,
        execution_time: float,
        retries_used: int,
    ) -> NodeResult:
        """Create a failed execution result."""
        return NodeResult(
            node_id=node.id,
            status=NodeStatus.FAILED,
            error=str(error) if error else "Unknown error",
            execution_time_ms=execution_time,
            retries_used=retries_used,
            constitutional_hash=self.constitutional_hash,
        )


class ParallelNodeExecutor(NodeExecutor):
    """Executor for parallel node execution.

    Executes multiple nodes concurrently while respecting
    dependency constraints.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        base_executor: NodeExecutor | None = None,
        max_concurrent: int = 10,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(constitutional_hash=constitutional_hash)
        self.base_executor = base_executor or AsyncNodeExecutor()
        self.max_concurrent = max_concurrent

    async def execute(
        self,
        node: GraphNode,
        state: GraphState,
        context: JSONDict | None = None,
    ) -> NodeResult:
        """Execute a single node using base executor."""
        return await self.base_executor.execute(node, state, context)

    async def execute_parallel(
        self,
        nodes: list[GraphNode],
        state: GraphState,
        context: JSONDict | None = None,
    ) -> list[NodeResult]:
        """Execute multiple nodes in parallel.

        Args:
            nodes: List of nodes to execute
            state: Current graph state
            context: Optional execution context

        Returns:
            List of NodeResult for each node
        """
        if not nodes:
            return []

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def execute_with_semaphore(node: GraphNode) -> NodeResult:
            async with semaphore:
                return await self.base_executor.execute(node, state, context)

        # Execute all nodes concurrently
        tasks = [execute_with_semaphore(node) for node in nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    NodeResult(
                        node_id=nodes[i].id,
                        status=NodeStatus.FAILED,
                        error=str(result),
                        constitutional_hash=self.constitutional_hash,
                    )
                )
            else:
                final_results.append(cast(NodeResult, result))

        return final_results

    async def execute_with_dependencies(
        self,
        nodes: list[GraphNode],
        dependencies: dict[str, set[str]],
        state: GraphState,
        context: JSONDict | None = None,
    ) -> tuple[list[NodeResult], GraphState]:
        """Execute nodes respecting dependencies.

        Args:
            nodes: List of all nodes to execute
            dependencies: Map of node_id -> set of dependency node_ids
            state: Initial graph state
            context: Optional execution context

        Returns:
            Tuple of (all results, final state)
        """
        {n.id: n for n in nodes}
        completed: set[str] = set()
        results: list[NodeResult] = []
        current_state = state

        while len(completed) < len(nodes):
            # Find ready nodes (all dependencies satisfied)
            ready = []
            for node in nodes:
                if node.id in completed:
                    continue
                node_deps = dependencies.get(node.id, set())
                if node_deps.issubset(completed):
                    ready.append(node)

            if not ready:
                # No progress - check for cycles
                remaining = [n.id for n in nodes if n.id not in completed]
                logger.error(f"No ready nodes but {len(remaining)} remaining: {remaining}")
                break

            # Execute ready nodes in parallel
            batch_results = await self.execute_parallel(ready, current_state, context)

            # Process results and update state
            for result in batch_results:
                results.append(result)
                completed.add(result.node_id)

                if result.status == NodeStatus.COMPLETED and result.output_state:
                    current_state = self.state_reducer.reduce(
                        current_state,
                        result.output_state,
                        result.node_id,
                    )

        return results, current_state


class ConditionalNodeExecutor(NodeExecutor):
    """Executor for conditional routing nodes.

    Evaluates conditions to determine next node in the graph.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        base_executor: NodeExecutor | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(constitutional_hash=constitutional_hash)
        self.base_executor = base_executor or AsyncNodeExecutor()
        self._condition_cache: dict[str, Callable[[JSONDict], str]] = {}

    async def execute(
        self,
        node: GraphNode,
        state: GraphState,
        context: JSONDict | None = None,
    ) -> NodeResult:
        """Execute a node using base executor."""
        return await self.base_executor.execute(node, state, context)

    def register_condition(self, path: str, func: Callable[[JSONDict], str]) -> None:
        """Register a condition function.

        Args:
            path: Condition path identifier
            func: Function that takes state and returns next node ID
        """
        self._condition_cache[path] = func

    def get_condition_function(
        self,
        cond_edge: ConditionalEdge,
    ) -> Callable[[JSONDict], str] | None:
        """Get condition function for conditional edge."""
        if not cond_edge.condition_function_path:
            return None

        if cond_edge.condition_function_path in self._condition_cache:
            return self._condition_cache[cond_edge.condition_function_path]

        try:
            parts = cond_edge.condition_function_path.rsplit(".", 1)
            if len(parts) != 2:
                return None

            module_path, func_name = parts
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)

            self._condition_cache[cond_edge.condition_function_path] = func
            return func  # type: ignore[no-any-return]

        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load condition function: {e}")
            return None

    async def evaluate_condition(
        self,
        cond_edge: ConditionalEdge,
        state: GraphState,
    ) -> str | None:
        """Evaluate a conditional edge to get next node ID.

        Args:
            cond_edge: Conditional edge definition
            state: Current graph state

        Returns:
            Next node ID or None if no match
        """
        # Try function-based condition first
        func = self.get_condition_function(cond_edge)
        if func:
            try:
                if inspect.iscoroutinefunction(func):
                    condition_result = await func(state.data)
                else:
                    condition_result = func(state.data)

                # Look up result in conditions map
                if condition_result in cond_edge.conditions:
                    return str(cond_edge.conditions[condition_result])  # type: ignore[arg-type]
                return cond_edge.default_target  # type: ignore[no-any-return]

            except _NODE_EXECUTOR_OPERATION_ERRORS as e:
                logger.error(f"Condition evaluation error: {e}")
                return cond_edge.default_target  # type: ignore[no-any-return]

        # Try expression-based conditions
        for condition_value, target_node in cond_edge.conditions.items():
            try:
                # Simple key=value condition
                if "=" in condition_value and "==" not in condition_value:
                    key, expected = condition_value.split("=", 1)
                    actual = state.data.get(key.strip())
                    if str(actual) == expected.strip():
                        return str(target_node)  # type: ignore[arg-type]

                # Boolean key condition
                elif state.data.get(condition_value) is True:
                    return str(target_node)  # type: ignore[arg-type]

            except _NODE_EXECUTOR_OPERATION_ERRORS as e:
                logger.warning(f"Condition parse error for '{condition_value}': {e}")

        return cond_edge.default_target  # type: ignore[no-any-return]

    async def route(
        self,
        cond_edges: list[ConditionalEdge],
        current_node_id: str,
        state: GraphState,
    ) -> str | None:
        """Route to next node based on conditional edges.

        Args:
            cond_edges: List of conditional edges from current node
            current_node_id: Current node ID
            state: Current graph state

        Returns:
            Next node ID or None
        """
        for cond_edge in cond_edges:
            if cond_edge.source_node_id == current_node_id:
                next_node = await self.evaluate_condition(cond_edge, state)
                if next_node:
                    return next_node

        return None


__all__ = [
    "AsyncNodeExecutor",
    "ConditionalNodeExecutor",
    "NodeExecutor",
    "ParallelNodeExecutor",
]
