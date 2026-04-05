"""
ACGS-2 Enhanced Agent Bus - Workflow Base Abstractions
Constitutional Hash: 608508a9bd224290

Base classes and protocols for workflow orchestration.
Provides abstractions compatible with Temporal patterns.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import (
    Generic,
    Protocol,
    TypeVar,
    runtime_checkable,
)

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import (
    ResourceNotFoundError,
    ServiceUnavailableError,
)
from enhanced_agent_bus._compat.errors import (
    ValidationError as ACGSValidationError,
)

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
WORKFLOW_RUN_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

# Type variables for generic workflow definitions
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")
TState = TypeVar("TState")


class WorkflowStatus(Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class WorkflowContext:
    """Context for workflow execution.

    Provides workflow-scoped information and utilities.
    Constitutional Hash: 608508a9bd224290
    """

    workflow_id: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_workflow_id: str | None = None
    tenant_id: str = "default"  # Valid default for backward compatibility
    constitutional_hash: str = CONSTITUTIONAL_HASH
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)

    # Event signaling
    _signals: dict[str, asyncio.Queue] = field(default_factory=dict)
    _signal_data: dict[str, list[JSONValue]] = field(default_factory=dict)

    # Workflow state
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: JSONValue | None = None
    error: str | None = None

    def get_signal_queue(self, signal_name: str) -> asyncio.Queue:
        """Get or create a signal queue."""
        if signal_name not in self._signals:
            self._signals[signal_name] = asyncio.Queue()
        return self._signals[signal_name]

    async def wait_for_signal(self, signal_name: str, timeout: float | None = None) -> JSONValue:
        """Wait for a signal with optional timeout."""
        queue = self.get_signal_queue(signal_name)
        try:
            if timeout:
                return await asyncio.wait_for(queue.get(), timeout=timeout)
            return await queue.get()
        except TimeoutError:
            return None

    async def send_signal(self, signal_name: str, data: JSONValue = None) -> None:
        """Send a signal to the workflow."""
        queue = self.get_signal_queue(signal_name)
        await queue.put(data)
        # Store signal data for query access
        if signal_name not in self._signal_data:
            self._signal_data[signal_name] = []
        self._signal_data[signal_name].append(data)


@runtime_checkable
class Activity(Protocol[TInput, TOutput]):  # type: ignore[misc]
    """Protocol for workflow activities.

    Activities are the building blocks of workflows that perform
    actual work (I/O, computations, external calls).
    Constitutional Hash: 608508a9bd224290
    """

    async def execute(self, input_data: TInput, context: WorkflowContext) -> TOutput:
        """Execute the activity.

        Args:
            input_data: Activity input
            context: Workflow context

        Returns:
            Activity output
        """
        ...

    @property
    def name(self) -> str:
        """Activity name for registration and logging."""
        ...

    @property
    def timeout_seconds(self) -> float:
        """Activity timeout in seconds."""
        ...


@dataclass
class Signal:
    """Signal definition for workflow communication.

    Signals allow external events to be sent to running workflows.
    Constitutional Hash: 608508a9bd224290
    """

    name: str
    handler: Callable[[JSONValue], Awaitable[None]] | None = None
    description: str = ""


@dataclass
class Query:
    """Query definition for workflow state inspection.

    Queries allow read-only access to workflow state.
    Constitutional Hash: 608508a9bd224290
    """

    name: str
    handler: Callable[[], JSONValue]
    description: str = ""


class WorkflowDefinition(ABC, Generic[TInput, TOutput]):
    """Abstract base class for workflow definitions.

    Workflows define long-running business processes with
    signals for external input and queries for state inspection.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self) -> None:
        self._signals: dict[str, Signal] = {}
        self._queries: dict[str, Query] = {}
        self._context: WorkflowContext | None = None
        self._register_signals_and_queries()

    @property
    def context(self) -> WorkflowContext:
        """Get the workflow context."""
        if self._context is None:
            raise ServiceUnavailableError(
                "Workflow context not initialized",
                error_code="WORKFLOW_CONTEXT_NOT_INITIALIZED",
            )
        return self._context

    @context.setter
    def context(self, value: WorkflowContext) -> None:
        """Set the workflow context."""
        self._context = value

    @abstractmethod
    async def run(self, input_data: TInput) -> TOutput:
        """Main workflow execution logic.

        Args:
            input_data: Workflow input

        Returns:
            Workflow output
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Workflow name for registration."""
        ...

    def _register_signals_and_queries(self) -> None:
        """Register signals and queries from decorated methods."""
        # Skip properties that may raise errors when accessed
        skip_attrs = {"context", "name", "state", "config"}
        for attr_name in dir(self):
            if attr_name.startswith("_") or attr_name in skip_attrs:
                continue
            try:
                attr = getattr(self, attr_name, None)
            except (RuntimeError, AttributeError):
                # Skip attributes that raise errors when accessed
                continue
            if hasattr(attr, "_is_signal"):
                signal = Signal(name=attr._signal_name, handler=attr)
                self._signals[signal.name] = signal
            if hasattr(attr, "_is_query"):
                query = Query(name=attr._query_name, handler=attr)
                self._queries[query.name] = query

    async def execute_activity(
        self,
        activity: Activity[TInput, TOutput],
        input_data: TInput,
        **kwargs: object,
    ) -> TOutput:
        """Execute an activity within the workflow.

        Args:
            activity: The activity to execute
            input_data: Activity input
            **kwargs: Additional activity options

        Returns:
            Activity output
        """
        timeout = kwargs.get("timeout", activity.timeout_seconds)
        try:
            return await asyncio.wait_for(
                activity.execute(input_data, self.context),
                timeout=timeout,
            )
        except TimeoutError as e:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Activity {activity.name} timed out after {timeout}s"
            )
            raise e

    async def wait_condition(
        self,
        condition: Callable[[], bool],
        timeout: float | None = None,
        poll_interval: float = 0.1,
    ) -> bool:
        """Wait for a condition to become true.

        Args:
            condition: Callable returning bool
            timeout: Maximum wait time in seconds
            poll_interval: How often to check condition

        Returns:
            True if condition was met, False if timed out
        """
        start_time = datetime.now(UTC)
        while not condition():
            if timeout:
                elapsed = (datetime.now(UTC) - start_time).total_seconds()
                if elapsed >= timeout:
                    return False
            await asyncio.sleep(poll_interval)
        return True

    def get_signals(self) -> dict[str, Signal]:
        """Get registered signals."""
        return self._signals.copy()

    def get_queries(self) -> dict[str, Query]:
        """Get registered queries."""
        return self._queries.copy()


def signal(name: str | None = None) -> Callable:
    """Decorator to mark a method as a signal handler.

    Args:
        name: Optional signal name (defaults to method name)

    Returns:
        Decorated method
    """

    def decorator(func: Callable) -> Callable:
        func._is_signal = True  # type: ignore[attr-defined]
        func._signal_name = name or func.__name__  # type: ignore[attr-defined]
        return func

    return decorator


def query(name: str | None = None) -> Callable:
    """Decorator to mark a method as a query handler.

    Args:
        name: Optional query name (defaults to method name)

    Returns:
        Decorated method
    """

    def decorator(func: Callable) -> Callable:
        func._is_query = True  # type: ignore[attr-defined]
        func._query_name = name or func.__name__  # type: ignore[attr-defined]
        return func

    return decorator


class InMemoryWorkflowExecutor:
    """In-memory workflow executor for testing and development.

    Runs workflows in-process without external dependencies.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._contexts: dict[str, WorkflowContext] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, JSONValue] = {}
        self._errors: dict[str, str] = {}

    async def start(
        self,
        workflow: WorkflowDefinition[TInput, TOutput],
        workflow_id: str,
        input_data: TInput,
        **kwargs: JSONValue,
    ) -> str:
        """Start a workflow execution."""
        # Create context
        tenant_id = kwargs.get("tenant_id", "")
        metadata = kwargs.get("metadata", {})
        context = WorkflowContext(
            workflow_id=workflow_id,
            tenant_id=str(tenant_id) if tenant_id else "",
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )
        context.status = WorkflowStatus.RUNNING

        # Register workflow
        workflow.context = context
        self._workflows[workflow_id] = workflow
        self._contexts[workflow_id] = context

        # Start workflow task
        async def run_workflow() -> None:
            try:
                result = await workflow.run(input_data)
                self._results[workflow_id] = result  # type: ignore[assignment]
                context.result = result  # type: ignore[assignment]
                context.status = WorkflowStatus.COMPLETED
            except asyncio.CancelledError:
                context.status = WorkflowStatus.CANCELLED
                raise
            except WORKFLOW_RUN_ERRORS as e:
                context.status = WorkflowStatus.FAILED
                context.error = str(e)
                self._errors[workflow_id] = str(e)
                logger.error(f"[{CONSTITUTIONAL_HASH}] Workflow {workflow_id} failed: {e}")

        task = asyncio.create_task(run_workflow())
        self._tasks[workflow_id] = task

        return context.run_id

    async def send_signal(self, workflow_id: str, signal_name: str, data: JSONValue = None) -> None:
        """Send a signal to a running workflow."""
        if workflow_id not in self._workflows:
            raise ResourceNotFoundError(
                f"Workflow {workflow_id} not found",
                error_code="WORKFLOW_NOT_FOUND",
            )

        workflow = self._workflows[workflow_id]
        context = self._contexts[workflow_id]

        # Check if workflow has this signal registered
        if signal_name in workflow.get_signals():
            signal_handler = workflow.get_signals()[signal_name].handler
            if signal_handler:
                await signal_handler(data)

        # Also send to context queue for wait_for_signal
        await context.send_signal(signal_name, data)

    async def query(self, workflow_id: str, query_name: str) -> JSONValue:
        """Query workflow state."""
        if workflow_id not in self._workflows:
            raise ResourceNotFoundError(
                f"Workflow {workflow_id} not found",
                error_code="WORKFLOW_NOT_FOUND",
            )

        workflow = self._workflows[workflow_id]
        queries = workflow.get_queries()

        if query_name not in queries:
            raise ACGSValidationError(
                f"Query {query_name} not found in workflow",
                error_code="WORKFLOW_QUERY_NOT_FOUND",
            )

        return queries[query_name].handler()

    async def get_result(self, workflow_id: str, timeout: float | None = None) -> JSONValue:
        """Get workflow result."""
        if workflow_id not in self._tasks:
            raise ResourceNotFoundError(
                f"Workflow {workflow_id} not found",
                error_code="WORKFLOW_NOT_FOUND",
            )

        task = self._tasks[workflow_id]

        try:
            if timeout:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            else:
                await task
        except TimeoutError:
            pass
        except asyncio.CancelledError:
            pass

        context = self._contexts[workflow_id]
        if context.status == WorkflowStatus.FAILED:
            raise ServiceUnavailableError(
                context.error or "Workflow failed",
                error_code="WORKFLOW_EXECUTION_FAILED",
            )

        return self._results.get(workflow_id)

    async def cancel(self, workflow_id: str) -> None:
        """Cancel a running workflow."""
        if workflow_id not in self._tasks:
            raise ResourceNotFoundError(
                f"Workflow {workflow_id} not found",
                error_code="WORKFLOW_NOT_FOUND",
            )

        task = self._tasks[workflow_id]
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        context = self._contexts[workflow_id]
        context.status = WorkflowStatus.CANCELLED

    def get_status(self, workflow_id: str) -> WorkflowStatus:
        """Get workflow status."""
        if workflow_id not in self._contexts:
            raise ResourceNotFoundError(
                f"Workflow {workflow_id} not found",
                error_code="WORKFLOW_NOT_FOUND",
            )
        return self._contexts[workflow_id].status

    def get_context(self, workflow_id: str) -> WorkflowContext:
        """Get workflow context."""
        if workflow_id not in self._contexts:
            raise ResourceNotFoundError(
                f"Workflow {workflow_id} not found",
                error_code="WORKFLOW_NOT_FOUND",
            )
        return self._contexts[workflow_id]


__all__ = [
    "Activity",
    "InMemoryWorkflowExecutor",
    "Query",
    "Signal",
    "WorkflowContext",
    "WorkflowDefinition",
    "WorkflowStatus",
    "query",
    "signal",
]
