"""
ACGS-2 Enhanced Agent Bus - Operational Exceptions
Constitutional Hash: cdd01ef066bc6cf2
"""

from src.core.shared.types import JSONDict

from .base import AgentBusError, BusOperationError
from .messaging import RateLimitExceeded


class GovernanceError(AgentBusError):
    """Raised when governance operations fail."""

    def __init__(self, message: str, details: JSONDict | None = None) -> None:
        super().__init__(
            message=message,
            details=details or {},
        )


class ImpactAssessmentError(GovernanceError):
    """Raised when impact assessment operations fail."""

    def __init__(self, assessment_type: str, reason: str) -> None:
        self.assessment_type = assessment_type
        super().__init__(
            message=f"Impact assessment failed for {assessment_type}: {reason}",
            details={"assessment_type": assessment_type, "reason": reason},
        )


class DeliberationError(AgentBusError):
    """Base exception for deliberation layer errors."""

    pass


class DeliberationTimeoutError(DeliberationError):
    """Raised when deliberation process times out."""

    def __init__(
        self,
        decision_id: str,
        timeout_seconds: int,
        pending_reviews: int = 0,
        pending_signatures: int = 0,
    ) -> None:
        self.decision_id = decision_id
        self.timeout_seconds = timeout_seconds
        self.pending_reviews = pending_reviews
        self.pending_signatures = pending_signatures
        super().__init__(
            message=f"Deliberation '{decision_id}' timed out after {timeout_seconds}s",
            details={
                "decision_id": decision_id,
                "timeout_seconds": timeout_seconds,
                "pending_reviews": pending_reviews,
                "pending_signatures": pending_signatures,
            },
        )


class SignatureCollectionError(DeliberationError):
    """Raised when signature collection fails."""

    def __init__(
        self,
        decision_id: str,
        required_signers: list[str],
        collected_signers: list[str],
        reason: str,
    ) -> None:
        self.decision_id = decision_id
        self.required_signers = required_signers
        self.collected_signers = collected_signers
        self.reason = reason
        missing = set(required_signers) - set(collected_signers)
        super().__init__(
            message=f"Signature collection failed for '{decision_id}': {reason}",
            details={
                "decision_id": decision_id,
                "required_signers": required_signers,
                "collected_signers": collected_signers,
                "missing_signers": list(missing),
                "reason": reason,
            },
        )


class ReviewConsensusError(DeliberationError):
    """Raised when critic review consensus cannot be reached."""

    def __init__(
        self,
        decision_id: str,
        approval_count: int,
        rejection_count: int,
        escalation_count: int,
    ) -> None:
        self.decision_id = decision_id
        self.approval_count = approval_count
        self.rejection_count = rejection_count
        self.escalation_count = escalation_count
        super().__init__(
            message=f"Review consensus not reached for '{decision_id}': "
            f"{approval_count} approvals, {rejection_count} rejections, "
            f"{escalation_count} escalations",
            details={
                "decision_id": decision_id,
                "approval_count": approval_count,
                "rejection_count": rejection_count,
                "escalation_count": escalation_count,
            },
        )


class BusNotStartedError(BusOperationError):
    """Raised when operation requires a started bus."""

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(
            message=f"Agent bus not started for operation: {operation}",
            details={"operation": operation},
        )


class BusAlreadyStartedError(BusOperationError):
    """Raised when attempting to start an already running bus."""

    def __init__(self) -> None:
        super().__init__(
            message="Agent bus is already running",
            details={},
        )


class HandlerExecutionError(BusOperationError):
    """Raised when a message handler fails during execution."""

    def __init__(
        self,
        handler_name: str,
        message_id: str,
        original_error: Exception,
    ) -> None:
        self.handler_name = handler_name
        self.message_id = message_id
        self.original_error = original_error
        super().__init__(
            message=f"Handler '{handler_name}' failed for message '{message_id}': {original_error}",
            details={
                "handler_name": handler_name,
                "message_id": message_id,
                "original_error": str(original_error),
                "original_error_type": type(original_error).__name__,
            },
        )


class ConfigurationError(AgentBusError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, config_key: str, reason: str) -> None:
        self.config_key = config_key
        self.reason = reason
        super().__init__(
            message=f"Configuration error for '{config_key}': {reason}",
            details={
                "config_key": config_key,
                "reason": reason,
            },
        )


class AlignmentViolationError(AgentBusError):
    """Raised when an agent message or action violates constitutional alignment."""

    def __init__(
        self,
        reason: str,
        alignment_score: float | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.reason = reason
        self.alignment_score = alignment_score
        self.agent_id = agent_id
        message = f"Constitutional alignment violation: {reason}"
        if alignment_score is not None:
            message += f" (score: {alignment_score})"
        super().__init__(
            message=message,
            details={
                "reason": reason,
                "alignment_score": alignment_score,
                "agent_id": agent_id,
            },
        )


class AuthenticationError(AgentBusError):
    """Raised when authentication fails."""

    def __init__(
        self,
        agent_id: str,
        reason: str,
        details: JSONDict | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.reason = reason
        super().__init__(
            message=f"Authentication failed for agent '{agent_id}': {reason}",
            details={
                "agent_id": agent_id,
                "reason": reason,
                **(details or {}),
            },
        )


class AuthorizationError(AgentBusError):
    """Raised when authorization fails."""

    def __init__(
        self,
        agent_id: str,
        action: str,
        reason: str,
        details: JSONDict | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.action = action
        self.reason = reason
        super().__init__(
            message=f"Authorization failed for agent '{agent_id}' to perform '{action}': {reason}",
            details={
                "agent_id": agent_id,
                "action": action,
                "reason": reason,
                **(details or {}),
            },
        )


class DependencyError(AgentBusError):
    """Raised when an external dependency fails."""

    def __init__(
        self,
        dependency_name: str,
        reason: str,
        details: JSONDict | None = None,
    ) -> None:
        self.dependency_name = dependency_name
        self.reason = reason
        super().__init__(
            message=f"Dependency '{dependency_name}' failed: {reason}",
            details={
                "dependency_name": dependency_name,
                "reason": reason,
                **(details or {}),
            },
        )


class CircuitBreakerOpenError(BusOperationError):
    """Raised when circuit breaker prevents an operation."""


class RateLimitExceededError(RateLimitExceeded):
    """Alias for RateLimitExceeded."""


class ResourceNotFoundError(AgentBusError):
    """Raised when a requested resource is not found."""


class ServiceUnavailableError(AgentBusError):
    """Raised when a required service is unavailable."""


class TenantIsolationError(AgentBusError):
    """Raised when tenant isolation rules are violated."""


class ValidationError(AgentBusError):
    """Raised when validation fails (generic)."""


__all__ = [
    "AlignmentViolationError",
    "AuthenticationError",
    "AuthorizationError",
    "BusAlreadyStartedError",
    "BusNotStartedError",
    "BusOperationError",
    "CircuitBreakerOpenError",
    "ConfigurationError",
    "DeliberationError",
    "DeliberationTimeoutError",
    "DependencyError",
    "GovernanceError",
    "HandlerExecutionError",
    "ImpactAssessmentError",
    "RateLimitExceededError",
    "ResourceNotFoundError",
    "ReviewConsensusError",
    "ServiceUnavailableError",
    "SignatureCollectionError",
    "TenantIsolationError",
    "ValidationError",
]
