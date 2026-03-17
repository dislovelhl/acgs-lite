"""
ACGS-2 LangGraph Orchestration - Exceptions
Constitutional Hash: cdd01ef066bc6cf2

Custom exception types for graph-based workflow orchestration.
"""

from packages.enhanced_agent_bus.bus_types import JSONDict
from packages.enhanced_agent_bus.exceptions import AgentBusError
from src.core.shared.constants import CONSTITUTIONAL_HASH


class OrchestrationError(AgentBusError):
    """Base exception for all orchestration errors.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    http_status_code = 500
    error_code = "ORCHESTRATION_ERROR"

    def __init__(
        self,
        message: str,
        details: JSONDict | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        # Forward to AgentBusError which handles all attribute setting
        super().__init__(
            message,
            details=details,
            constitutional_hash=constitutional_hash,
        )

    def to_dict(self) -> JSONDict:
        """Convert exception to dictionary for logging/serialization."""
        result = super().to_dict()
        # Legacy 'error_type' field already added by AgentBusError.to_dict()
        return result  # type: ignore[no-any-return]


class StateTransitionError(OrchestrationError):
    """Raised when a state transition is invalid.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        from_state: str,
        to_state: str,
        reason: str,
        node_id: str | None = None,
    ) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        self.node_id = node_id
        message = f"Invalid state transition from '{from_state}' to '{to_state}': {reason}"
        if node_id:
            message = f"[Node: {node_id}] {message}"
        super().__init__(
            message=message,
            details={
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "node_id": node_id,
            },
        )


class NodeExecutionError(OrchestrationError):
    """Raised when node execution fails.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        node_id: str,
        node_type: str,
        original_error: Exception,
        execution_time_ms: float | None = None,
    ) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.original_error = original_error
        self.execution_time_ms = execution_time_ms
        message = f"Node '{node_id}' ({node_type}) execution failed: {original_error}"
        super().__init__(
            message=message,
            details={
                "node_id": node_id,
                "node_type": node_type,
                "original_error": str(original_error),
                "original_error_type": type(original_error).__name__,
                "execution_time_ms": execution_time_ms,
            },
        )


class GraphValidationError(OrchestrationError):
    """Raised when graph validation fails.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        validation_errors: list[str],
        graph_id: str | None = None,
    ) -> None:
        self.validation_errors = validation_errors
        self.graph_id = graph_id
        message = f"Graph validation failed: {'; '.join(validation_errors)}"
        if graph_id:
            message = f"[Graph: {graph_id}] {message}"
        super().__init__(
            message=message,
            details={
                "validation_errors": validation_errors,
                "graph_id": graph_id,
            },
        )


class CheckpointError(OrchestrationError):
    """Raised when checkpoint operations fail.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        checkpoint_id: str,
        operation: str,
        reason: str,
        workflow_id: str | None = None,
    ) -> None:
        self.checkpoint_id = checkpoint_id
        self.operation = operation
        self.reason = reason
        self.workflow_id = workflow_id
        message = f"Checkpoint '{checkpoint_id}' {operation} failed: {reason}"
        if workflow_id:
            message = f"[Workflow: {workflow_id}] {message}"
        super().__init__(
            message=message,
            details={
                "checkpoint_id": checkpoint_id,
                "operation": operation,
                "reason": reason,
                "workflow_id": workflow_id,
            },
        )


class InterruptError(OrchestrationError):
    """Raised when interrupt handling fails.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        interrupt_type: str,
        reason: str,
        node_id: str | None = None,
        workflow_id: str | None = None,
    ) -> None:
        self.interrupt_type = interrupt_type
        self.reason = reason
        self.node_id = node_id
        self.workflow_id = workflow_id
        message = f"Interrupt ({interrupt_type}) handling failed: {reason}"
        if node_id:
            message = f"[Node: {node_id}] {message}"
        if workflow_id:
            message = f"[Workflow: {workflow_id}] {message}"
        super().__init__(
            message=message,
            details={
                "interrupt_type": interrupt_type,
                "reason": reason,
                "node_id": node_id,
                "workflow_id": workflow_id,
            },
        )


class TimeoutError(OrchestrationError):
    """Raised when an operation times out.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        operation: str,
        timeout_ms: float,
        elapsed_ms: float | None = None,
        context: str | None = None,
    ) -> None:
        self.operation = operation
        self.timeout_ms = timeout_ms
        self.elapsed_ms = elapsed_ms
        self.context = context
        message = f"Operation '{operation}' timed out after {timeout_ms}ms"
        if elapsed_ms is not None:
            message += f" (elapsed: {elapsed_ms}ms)"
        if context:
            message += f" [{context}]"
        super().__init__(
            message=message,
            details={
                "operation": operation,
                "timeout_ms": timeout_ms,
                "elapsed_ms": elapsed_ms,
                "context": context,
            },
        )


class ConstitutionalViolationError(OrchestrationError):
    """Raised when constitutional constraints are violated.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        violations: list[str],
        node_id: str | None = None,
        transition: str | None = None,
    ) -> None:
        self.violations = violations
        self.node_id = node_id
        self.transition = transition
        message = f"Constitutional violation: {'; '.join(violations)}"
        if node_id:
            message = f"[Node: {node_id}] {message}"
        if transition:
            message = f"[Transition: {transition}] {message}"
        super().__init__(
            message=message,
            details={
                "violations": violations,
                "node_id": node_id,
                "transition": transition,
            },
        )


class CyclicDependencyError(OrchestrationError):
    """Raised when a non-allowed cycle is detected in the graph.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        cycle_path: list[str],
        graph_id: str | None = None,
    ) -> None:
        self.cycle_path = cycle_path
        self.graph_id = graph_id
        cycle_str = " -> ".join(cycle_path)
        message = f"Invalid cycle detected: {cycle_str}"
        if graph_id:
            message = f"[Graph: {graph_id}] {message}"
        super().__init__(
            message=message,
            details={
                "cycle_path": cycle_path,
                "graph_id": graph_id,
            },
        )


class MACIViolationError(OrchestrationError):
    """Raised when MACI role constraints are violated.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        agent_id: str,
        required_role: str,
        actual_role: str | None,
        action: str,
    ) -> None:
        self.agent_id = agent_id
        self.required_role = required_role
        self.actual_role = actual_role
        self.action = action
        message = f"MACI violation: Agent '{agent_id}' requires role '{required_role}' "
        message += f"(has '{actual_role or 'none'}') for action '{action}'"
        super().__init__(
            message=message,
            details={
                "agent_id": agent_id,
                "required_role": required_role,
                "actual_role": actual_role,
                "action": action,
            },
        )


__all__ = [
    "CheckpointError",
    "ConstitutionalViolationError",
    "CyclicDependencyError",
    "GraphValidationError",
    "InterruptError",
    "MACIViolationError",
    "NodeExecutionError",
    "OrchestrationError",
    "StateTransitionError",
    "TimeoutError",
]
