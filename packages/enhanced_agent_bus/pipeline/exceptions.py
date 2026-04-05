"""
Pipeline exceptions for ACGS-2 Message Processing.

Constitutional Hash: 608508a9bd224290
"""

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.exceptions import AgentBusError


class PipelineException(AgentBusError):
    """Base exception for pipeline errors."""

    http_status_code = 500
    error_code = "PIPELINE_ERROR"

    def __init__(
        self,
        message: str,
        middleware: str | None = None,
        retryable: bool = False,
        details: JSONDict | None = None,
    ):
        # Set instance attributes BEFORE calling super().__init__()
        self.middleware = middleware
        self.retryable = retryable

        # Forward details to parent class
        super().__init__(message, details=details or {})


class SecurityException(PipelineException):
    """Exception raised when security check fails."""

    def __init__(
        self,
        message: str,
        detection_method: str | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="SecurityMiddleware",
            retryable=False,
            details=details,
        )
        self.detection_method = detection_method


class VerificationException(PipelineException):
    """Exception raised when verification fails."""

    def __init__(
        self,
        message: str,
        verifier: str | None = None,
        details: JSONDict | None = None,
    ):
        super().__init__(
            message=message,
            middleware="VerificationMiddleware",
            retryable=False,
            details=details,
        )
        self.verifier = verifier


class TimeoutException(PipelineException):
    """Exception raised when middleware times out."""

    def __init__(
        self,
        message: str,
        middleware: str | None = None,
        timeout_ms: int | None = None,
    ):
        super().__init__(
            message=message,
            middleware=middleware,
            retryable=True,
            details={"timeout_ms": timeout_ms},
        )
        self.timeout_ms = timeout_ms
