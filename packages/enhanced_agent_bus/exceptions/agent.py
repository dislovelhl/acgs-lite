"""
ACGS-2 Enhanced Agent Bus - Agent Exceptions
Constitutional Hash: 608508a9bd224290
"""

from .base import AgentError


class AgentNotRegisteredError(AgentError):
    """Raised when an operation requires a registered agent that doesn't exist."""

    def __init__(self, agent_id: str, operation: str | None = None) -> None:
        self.agent_id = agent_id
        self.operation = operation
        message = f"Agent '{agent_id}' is not registered"
        if operation:
            message += f" (required for {operation})"
        super().__init__(
            message=message,
            details={
                "agent_id": agent_id,
                "operation": operation,
            },
        )


class AgentAlreadyRegisteredError(AgentError):
    """Raised when attempting to register an agent that already exists."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(
            message=f"Agent '{agent_id}' is already registered",
            details={"agent_id": agent_id},
        )


class AgentCapabilityError(AgentError):
    """Raised when an agent lacks required capabilities."""

    def __init__(
        self,
        agent_id: str,
        required_capabilities: list[str],
        available_capabilities: list[str],
    ) -> None:
        self.agent_id = agent_id
        self.required_capabilities = required_capabilities
        self.available_capabilities = available_capabilities
        missing = set(required_capabilities) - set(available_capabilities)
        super().__init__(
            message=f"Agent '{agent_id}' missing capabilities: {', '.join(missing)}",
            details={
                "agent_id": agent_id,
                "required_capabilities": required_capabilities,
                "available_capabilities": available_capabilities,
                "missing_capabilities": list(missing),
            },
        )


__all__ = [
    "AgentAlreadyRegisteredError",
    "AgentCapabilityError",
    "AgentError",
    "AgentNotRegisteredError",
]
