"""
ACGS-2 Enhanced Agent Bus - Base Exceptions
Constitutional Hash: 608508a9bd224290
"""

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError as _ACGSBaseError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class AgentBusError(_ACGSBaseError):
    """
    Base exception for all Enhanced Agent Bus errors.

    Inherits from ACGSBaseError to gain:
    - Constitutional hash tracking
    - Correlation ID for distributed tracing
    - Structured error details and logging
    - HTTP status code mapping
    - Timestamp for audit logging

    All custom exceptions in the agent bus inherit from this class,
    allowing for catch-all error handling when needed.
    """

    http_status_code = 500
    error_code = "AGENT_BUS_ERROR"

    def __init__(
        self,
        message: str,
        details: JSONDict | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        **kwargs,
    ) -> None:
        # Preserve backward-compatible signature while forwarding to ACGSBaseError
        super().__init__(
            message, details=details, constitutional_hash=constitutional_hash, **kwargs
        )

    def to_dict(self) -> JSONDict:
        """
        Convert exception to dictionary for logging/serialization.

        Returns ACGSBaseError format (superset of old format):
        - Includes: error_code, message, constitutional_hash, correlation_id, timestamp, details
        - Compatible with old code expecting: error_type, message, details, constitutional_hash
        """
        result = super().to_dict()
        # Add legacy 'error_type' field for backward compatibility
        result["error_type"] = self.__class__.__name__
        return result


class ConstitutionalError(AgentBusError):
    """Base exception for constitutional compliance failures."""

    pass


class MessageError(AgentBusError):
    """Base exception for message-related errors."""

    pass


class AgentError(AgentBusError):
    """Base exception for agent-related errors."""

    pass


class PolicyError(AgentBusError):
    """Base exception for policy-related errors."""

    pass


class MACIError(AgentBusError):
    """Base exception for MACI role separation errors."""

    pass


class BusOperationError(AgentBusError):
    """Base exception for bus operation errors."""

    pass


__all__ = [
    "CONSTITUTIONAL_HASH",
    "AgentBusError",
    "AgentError",
    "BusOperationError",
    "ConstitutionalError",
    "MACIError",
    "MessageError",
    "PolicyError",
]
