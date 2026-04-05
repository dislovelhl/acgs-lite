"""
ACGS-2 Enhanced Agent Bus - Messaging Exceptions
Constitutional Hash: 608508a9bd224290
"""

from .base import MessageError


class MessageValidationError(MessageError):
    """Raised when message validation fails."""

    def __init__(
        self,
        message_id: str,
        errors: list[str],
        warnings: list[str] | None = None,
    ) -> None:
        self.message_id = message_id
        self.errors = errors
        self.warnings = warnings or []
        error_text = f"Message validation failed for '{message_id}': {'; '.join(errors)}"
        super().__init__(
            message=error_text,
            details={
                "message_id": message_id,
                "errors": errors,
                "warnings": self.warnings,
            },
        )


class MessageDeliveryError(MessageError):
    """Raised when message delivery fails."""

    def __init__(
        self,
        message_id: str,
        target_agent: str,
        reason: str,
    ) -> None:
        self.message_id = message_id
        self.target_agent = target_agent
        self.reason = reason
        super().__init__(
            message=f"Failed to deliver message '{message_id}' to agent '{target_agent}': {reason}",
            details={
                "message_id": message_id,
                "target_agent": target_agent,
                "reason": reason,
            },
        )


class MessageTimeoutError(MessageError):
    """Raised when message processing times out."""

    def __init__(
        self,
        message_id: str,
        timeout_ms: int,
        operation: str | None = None,
    ) -> None:
        self.message_id = message_id
        self.timeout_ms = timeout_ms
        self.operation = operation
        message = f"Message '{message_id}' timed out after {timeout_ms}ms"
        if operation:
            message += f" during {operation}"
        super().__init__(
            message=message,
            details={
                "message_id": message_id,
                "timeout_ms": timeout_ms,
                "operation": operation,
            },
        )


class MessageRoutingError(MessageError):
    """Raised when message routing fails."""

    def __init__(
        self,
        message_id: str,
        source_agent: str,
        target_agent: str,
        reason: str,
    ) -> None:
        self.message_id = message_id
        self.source_agent = source_agent
        self.target_agent = target_agent
        self.reason = reason
        super().__init__(
            message=(
                f"Failed to route message '{message_id}' from '{source_agent}' "
                f"to '{target_agent}': {reason}"
            ),
            details={
                "message_id": message_id,
                "source_agent": source_agent,
                "target_agent": target_agent,
                "reason": reason,
            },
        )


class RateLimitExceeded(MessageError):
    """Raised when an agent exceeds its message rate limit."""

    def __init__(
        self,
        agent_id: str,
        limit: int,
        window_seconds: int,
        retry_after_ms: int | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after_ms = retry_after_ms
        message = (
            f"Agent '{agent_id}' exceeded rate limit of {limit} messages per {window_seconds}s"
        )
        if retry_after_ms is not None:
            message += f" (retry after {retry_after_ms}ms)"
        super().__init__(
            message=message,
            details={
                "agent_id": agent_id,
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after_ms": retry_after_ms,
            },
        )


class MessageFormatError(MessageError):
    """Raised when message format/parsing fails."""


__all__ = [
    "MessageDeliveryError",
    "MessageError",
    "MessageFormatError",
    "MessageRoutingError",
    "MessageTimeoutError",
    "MessageValidationError",
    "RateLimitExceeded",
]
