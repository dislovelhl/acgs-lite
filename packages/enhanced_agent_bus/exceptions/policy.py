"""
ACGS-2 Enhanced Agent Bus - Policy Exceptions
Constitutional Hash: 608508a9bd224290
"""

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .base import PolicyError


class PolicyEvaluationError(PolicyError):
    """Raised when policy evaluation fails."""

    def __init__(
        self,
        policy_path: str,
        reason: str,
        input_data: JSONDict | None = None,
    ) -> None:
        self.policy_path = policy_path
        self.reason = reason
        self.input_data = input_data
        super().__init__(
            message=f"Policy evaluation failed for '{policy_path}': {reason}",
            details={
                "policy_path": policy_path,
                "reason": reason,
                "input_data": input_data,
            },
        )


class PolicyNotFoundError(PolicyError):
    """Raised when a required policy is not found."""

    def __init__(self, policy_path: str) -> None:
        self.policy_path = policy_path
        super().__init__(
            message=f"Policy not found: '{policy_path}'",
            details={"policy_path": policy_path},
        )


class OPAConnectionError(PolicyError):
    """Raised when connection to OPA server fails."""

    def __init__(self, opa_url: str, reason: str) -> None:
        self.opa_url = opa_url
        self.reason = reason
        super().__init__(
            message=f"Failed to connect to OPA at '{opa_url}': {reason}",
            details={
                "opa_url": opa_url,
                "reason": reason,
            },
        )


class OPANotInitializedError(PolicyError):
    """Raised when OPA client is not properly initialized."""

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(
            message=f"OPA client not initialized for operation: {operation}",
            details={"operation": operation},
        )


__all__ = [
    "OPAConnectionError",
    "OPANotInitializedError",
    "PolicyError",
    "PolicyEvaluationError",
    "PolicyNotFoundError",
]
