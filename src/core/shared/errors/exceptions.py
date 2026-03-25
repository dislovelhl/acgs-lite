# pyright: reportMissingImports=false
"""
ACGS-2 Base Exception Classes
Constitutional Hash: 608508a9bd224290

Provides a hierarchy of standardized exceptions for ACGS-2 services with:
- Constitutional hash tracking for governance compliance
- Correlation ID propagation for distributed tracing
- Structured error details for observability
- HTTP status code mapping for API responses

Exception Hierarchy:
    ACGSBaseError
    ├── ConstitutionalViolationError  (403 Forbidden)
    ├── MACIEnforcementError          (403 Forbidden)
    ├── TenantIsolationError          (403 Forbidden)
    ├── ValidationError               (400 Bad Request)
    ├── ServiceUnavailableError       (503 Service Unavailable)
    ├── RateLimitExceededError        (429 Too Many Requests)
    ├── AuthenticationError           (401 Unauthorized)
    ├── AuthorizationError            (403 Forbidden)
    ├── ResourceNotFoundError         (404 Not Found)
    ├── DataIntegrityError            (409 Conflict)
    ├── ConfigurationError            (500 Internal Server Error)
    └── TimeoutError                  (504 Gateway Timeout)

Usage:
    from src.core.shared.errors.exceptions import (
        ACGSBaseError,
        ConstitutionalViolationError,
        ValidationError,
    )

    try:
        validate_policy(data)
    except ValidationError as e:
        log_error(e)
        raise HTTPException(status_code=e.http_status_code, detail=e.to_dict())
"""

from __future__ import annotations

import traceback
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import JSONResponse
from uuid import uuid4

from ..constants import CONSTITUTIONAL_HASH
from ..types import CorrelationID, JSONDict, JSONValue


class ACGSBaseError(Exception):
    """
    Base exception for all ACGS-2 errors.

    All ACGS-2 exceptions inherit from this class and provide:
    - Constitutional hash for governance tracking
    - Correlation ID for distributed tracing
    - Structured error details for observability
    - HTTP status code for API responses
    - Timestamp for audit logging

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error code (e.g., "VALIDATION_001").
        constitutional_hash: Hash for governance validation.
        correlation_id: Request correlation ID for tracing.
        details: Additional structured error context.
        http_status_code: HTTP status code for API responses.
        timestamp: ISO format timestamp when error occurred.
        cause: Original exception that caused this error.
    """

    http_status_code: int = 500
    error_code: str = "ACGS_ERROR"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        correlation_id: CorrelationID | None = None,
        details: JSONDict | None = None,
        cause: BaseException | None = None,
        http_status_code: int | None = None,
    ) -> None:
        """
        Initialize ACGS base error.

        Args:
            message: Human-readable error description.
            error_code: Machine-readable error code. Defaults to class error_code.
            constitutional_hash: Hash for governance validation.
            correlation_id: Request correlation ID. Auto-generated if not provided.
            details: Additional structured error context.
            cause: Original exception that caused this error.
            http_status_code: Override default HTTP status code.
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.error_code
        self.constitutional_hash = constitutional_hash
        self.correlation_id = correlation_id or str(uuid4())
        self.details = details or {}
        self.cause = cause
        self.timestamp = datetime.now(UTC).isoformat()

        if http_status_code is not None:
            self.http_status_code = http_status_code

        # Preserve cause chain
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> JSONDict:
        """
        Convert exception to structured dictionary for API responses.

        Returns:
            Dictionary with error details suitable for JSON serialization.
        """
        result: JSONDict = {
            "error": self.error_code,
            "message": self.message,
            "constitutional_hash": self.constitutional_hash,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }

        if self.details:
            result["details"] = self.details

        if self.cause is not None:
            result["cause"] = {
                "type": type(self.cause).__name__,
                "message": str(self.cause),
            }

        return result

    def to_log_dict(self) -> JSONDict:
        """
        Convert exception to dictionary for structured logging.

        Includes stack trace information for debugging.

        Returns:
            Dictionary with comprehensive error details for logging.
        """
        result = self.to_dict()
        result["exception_type"] = type(self).__name__
        result["http_status_code"] = self.http_status_code

        # Add stack trace for logging
        if self.cause is not None:
            result["cause_traceback"] = traceback.format_exception(
                type(self.cause), self.cause, self.cause.__traceback__
            )

        return result

    def __str__(self) -> str:
        """Return human-readable error string."""
        parts = [f"[{self.constitutional_hash}]", f"[{self.error_code}]", self.message]
        if self.correlation_id:
            parts.insert(1, f"[{self.correlation_id[:8]}...]")
        return " ".join(parts)

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code!r}, "
            f"correlation_id={self.correlation_id!r}, "
            f"http_status_code={self.http_status_code})"
        )


class ConstitutionalViolationError(ACGSBaseError):
    """
    Raised when an operation violates constitutional governance rules.

    This error indicates that an action, message, or decision has failed
    constitutional validation against the governance policies defined by
    the constitutional hash.

    Attributes:
        violations: List of specific rule violations detected.
        policy_id: ID of the policy that was violated.
        action: The action that triggered the violation.
    """

    http_status_code = 403
    error_code = "CONSTITUTIONAL_VIOLATION"

    def __init__(
        self,
        message: str,
        *,
        violations: list[str] | None = None,
        policy_id: str | None = None,
        action: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize constitutional violation error.

        Args:
            message: Human-readable error description.
            violations: List of specific rule violations detected.
            policy_id: ID of the policy that was violated.
            action: The action that triggered the violation.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if violations:
            details["violations"] = violations
        if policy_id:
            details["policy_id"] = policy_id
        if action:
            details["action"] = action

        super().__init__(message, details=details, **kwargs)
        self.violations = violations or []
        self.policy_id = policy_id
        self.action = action


class MACIEnforcementError(ACGSBaseError):
    """
    Raised when MACI (Multi-Agent Constitutional Intelligence) enforcement fails.

    This error indicates a violation of the separation of powers (Trias Politica)
    implemented by MACI, such as:
    - Agent attempting to validate its own output (Godel prevention)
    - Invalid role-based access control
    - Unauthorized cross-role validation

    Attributes:
        agent_id: ID of the agent that caused the violation.
        role: MACI role of the agent.
        action: The MACI action that was attempted.
        target_agent_id: ID of the target agent (for cross-role actions).
    """

    http_status_code = 403
    error_code = "MACI_ENFORCEMENT_FAILURE"

    def __init__(
        self,
        message: str,
        *,
        agent_id: str | None = None,
        role: str | None = None,
        action: str | None = None,
        target_agent_id: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize MACI enforcement error.

        Args:
            message: Human-readable error description.
            agent_id: ID of the agent that caused the violation.
            role: MACI role of the agent (EXECUTIVE, JUDICIAL, etc.).
            action: The MACI action that was attempted.
            target_agent_id: ID of the target agent for cross-role actions.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if agent_id:
            details["agent_id"] = agent_id
        if role:
            details["role"] = role
        if action:
            details["action"] = action
        if target_agent_id:
            details["target_agent_id"] = target_agent_id

        super().__init__(message, details=details, **kwargs)
        self.agent_id = agent_id
        self.role = role
        self.action = action
        self.target_agent_id = target_agent_id


class TenantIsolationError(ACGSBaseError):
    """
    Raised when tenant isolation is violated.

    This error indicates an attempt to access resources belonging to a
    different tenant, violating multi-tenancy security boundaries.

    Attributes:
        tenant_id: ID of the requesting tenant.
        resource_tenant_id: ID of the tenant that owns the resource.
        resource_type: Type of resource being accessed.
        resource_id: ID of the resource being accessed.
    """

    http_status_code = 403
    error_code = "TENANT_ISOLATION_VIOLATION"

    def __init__(
        self,
        message: str,
        *,
        tenant_id: str | None = None,
        resource_tenant_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize tenant isolation error.

        Args:
            message: Human-readable error description.
            tenant_id: ID of the requesting tenant.
            resource_tenant_id: ID of the tenant that owns the resource.
            resource_type: Type of resource being accessed.
            resource_id: ID of the resource being accessed.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if tenant_id:
            details["tenant_id"] = tenant_id
        if resource_tenant_id:
            details["resource_tenant_id"] = resource_tenant_id
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(message, details=details, **kwargs)
        self.tenant_id = tenant_id
        self.resource_tenant_id = resource_tenant_id
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(ACGSBaseError):
    """
    Raised when input validation fails.

    This error indicates that request data, configuration, or other input
    failed validation against defined schemas or business rules.

    Attributes:
        field: Name of the field that failed validation.
        value: The invalid value (may be redacted for security).
        constraint: The validation constraint that was violated.
        validation_errors: List of all validation errors if multiple.
    """

    http_status_code = 400
    error_code = "VALIDATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: JSONValue | None = None,
        constraint: str | None = None,
        validation_errors: list[dict[str, str]] | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize validation error.

        Args:
            message: Human-readable error description.
            field: Name of the field that failed validation.
            value: The invalid value (will be stringified).
            constraint: The validation constraint that was violated.
            validation_errors: List of all validation errors if multiple.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if field:
            details["field"] = field
        if value is not None:
            # Stringify and truncate value for safety
            str_value = str(value)
            details["value"] = str_value[:100] + "..." if len(str_value) > 100 else str_value
        if constraint:
            details["constraint"] = constraint
        if validation_errors:
            details["validation_errors"] = validation_errors

        super().__init__(message, details=details, **kwargs)
        self.field = field
        self.value = value
        self.constraint = constraint
        self.validation_errors = validation_errors or []


class ServiceUnavailableError(ACGSBaseError):
    """
    Raised when an external service is unavailable.

    This error indicates that a dependent service (policy registry, OPA,
    audit service, etc.) cannot be reached or is responding with errors.

    Attributes:
        service_name: Name of the unavailable service.
        endpoint: The endpoint that was called.
        retry_after: Suggested retry delay in seconds.
    """

    http_status_code = 503
    error_code = "SERVICE_UNAVAILABLE"

    def __init__(
        self,
        message: str,
        *,
        service_name: str | None = None,
        endpoint: str | None = None,
        retry_after: int | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize service unavailable error.

        Args:
            message: Human-readable error description.
            service_name: Name of the unavailable service.
            endpoint: The endpoint that was called.
            retry_after: Suggested retry delay in seconds.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if service_name:
            details["service_name"] = service_name
        if endpoint:
            details["endpoint"] = endpoint
        if retry_after:
            details["retry_after"] = retry_after

        super().__init__(message, details=details, **kwargs)
        self.service_name = service_name
        self.endpoint = endpoint
        self.retry_after = retry_after


class RateLimitExceededError(ACGSBaseError):
    """
    Raised when rate limits are exceeded.

    This error indicates that the request rate has exceeded configured
    limits for an endpoint, tenant, or user.

    Attributes:
        limit: The rate limit that was exceeded.
        window_seconds: The time window for the limit.
        retry_after: Seconds until rate limit resets.
        limit_type: Type of limit (per_user, per_tenant, per_endpoint).
    """

    http_status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(
        self,
        message: str,
        *,
        limit: int | None = None,
        window_seconds: int | None = None,
        retry_after: int | None = None,
        limit_type: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize rate limit error.

        Args:
            message: Human-readable error description.
            limit: The rate limit that was exceeded.
            window_seconds: The time window for the limit.
            retry_after: Seconds until rate limit resets.
            limit_type: Type of limit (per_user, per_tenant, per_endpoint).
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if limit:
            details["limit"] = limit
        if window_seconds:
            details["window_seconds"] = window_seconds
        if retry_after:
            details["retry_after"] = retry_after
        if limit_type:
            details["limit_type"] = limit_type

        super().__init__(message, details=details, **kwargs)
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after
        self.limit_type = limit_type


async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
    """Standardized rate limit error handler for FastAPI applications.

    This handler provides consistent error responses for rate limit violations
    across all ACGS-2 services, including proper HTTP headers and JSON response
    format.

    Args:
        request: FastAPI request object
        exc: RateLimitExceededError exception

    Returns:
        JSONResponse with 429 status code and rate limit headers

    Example:
        from fastapi import FastAPI
        from src.core.shared.errors.exceptions import (
            RateLimitExceededError,
            rate_limit_error_handler,
        )

        app = FastAPI()
        app.add_exception_handler(RateLimitExceededError, rate_limit_error_handler)
    """
    from fastapi.responses import JSONResponse

    headers: dict[str, str] = {
        "X-RateLimit-Limit": str(exc.limit or 60),
        "X-RateLimit-Remaining": "0",
        "Content-Type": "application/json",
    }

    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
        headers["X-RateLimit-Retry-After"] = str(exc.retry_after)

    content: dict[str, str | int | None] = {
        "error": "Too Many Requests",
        "message": exc.message,
        "error_code": exc.error_code,
        "constitutional_hash": exc.constitutional_hash,
    }

    if exc.limit:
        content["limit"] = exc.limit
    if exc.window_seconds:
        content["window_seconds"] = exc.window_seconds
    if exc.retry_after:
        content["retry_after"] = exc.retry_after
    if exc.limit_type:
        content["limit_type"] = exc.limit_type

    return JSONResponse(
        status_code=429,
        headers=headers,
        content=content,
    )


class AuthenticationError(ACGSBaseError):
    """
    Raised when authentication fails.

    This error indicates that the request lacks valid authentication
    credentials or the provided credentials are invalid.

    Attributes:
        auth_method: The authentication method that failed (jwt, api_key, etc.).
        reason: Specific reason for authentication failure.
    """

    http_status_code = 401
    error_code = "AUTHENTICATION_FAILED"

    def __init__(
        self,
        message: str,
        *,
        auth_method: str | None = None,
        reason: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize authentication error.

        Args:
            message: Human-readable error description.
            auth_method: The authentication method that failed.
            reason: Specific reason for authentication failure.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if auth_method:
            details["auth_method"] = auth_method
        if reason:
            details["reason"] = reason

        super().__init__(message, details=details, **kwargs)
        self.auth_method = auth_method
        self.reason = reason


class AuthorizationError(ACGSBaseError):
    """
    Raised when authorization fails.

    This error indicates that the authenticated user lacks permission
    to perform the requested action on the specified resource.

    Attributes:
        action: The action that was attempted.
        resource: The resource that was accessed.
        required_permission: The permission that is required.
    """

    http_status_code = 403
    error_code = "AUTHORIZATION_DENIED"

    def __init__(
        self,
        message: str,
        *,
        action: str | None = None,
        resource: str | None = None,
        required_permission: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize authorization error.

        Args:
            message: Human-readable error description.
            action: The action that was attempted.
            resource: The resource that was accessed.
            required_permission: The permission that is required.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if action:
            details["action"] = action
        if resource:
            details["resource"] = resource
        if required_permission:
            details["required_permission"] = required_permission

        super().__init__(message, details=details, **kwargs)
        self.action = action
        self.resource = resource
        self.required_permission = required_permission


class ResourceNotFoundError(ACGSBaseError):
    """
    Raised when a requested resource is not found.

    Attributes:
        resource_type: Type of resource that was not found.
        resource_id: ID of the resource that was not found.
    """

    http_status_code = 404
    error_code = "RESOURCE_NOT_FOUND"

    def __init__(
        self,
        message: str,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize resource not found error.

        Args:
            message: Human-readable error description.
            resource_type: Type of resource that was not found.
            resource_id: ID of the resource that was not found.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(message, details=details, **kwargs)
        self.resource_type = resource_type
        self.resource_id = resource_id


class DataIntegrityError(ACGSBaseError):
    """
    Raised when data integrity constraints are violated.

    This error indicates conflicts such as duplicate keys, foreign key
    violations, or hash mismatches in audit data.

    Attributes:
        entity_type: Type of entity with integrity issue.
        entity_id: ID of the entity with integrity issue.
        constraint_name: Name of the violated constraint.
    """

    http_status_code = 409
    error_code = "DATA_INTEGRITY_VIOLATION"

    def __init__(
        self,
        message: str,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        constraint_name: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize data integrity error.

        Args:
            message: Human-readable error description.
            entity_type: Type of entity with integrity issue.
            entity_id: ID of the entity with integrity issue.
            constraint_name: Name of the violated constraint.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if entity_type:
            details["entity_type"] = entity_type
        if entity_id:
            details["entity_id"] = entity_id
        if constraint_name:
            details["constraint_name"] = constraint_name

        super().__init__(message, details=details, **kwargs)
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.constraint_name = constraint_name


class ConfigurationError(ACGSBaseError):
    """
    Raised when there is a configuration error.

    This error indicates missing or invalid configuration that prevents
    the system from operating correctly.

    Attributes:
        config_key: The configuration key that is invalid or missing.
        expected_type: The expected type for the configuration value.
        actual_value: The actual value found (redacted if sensitive).
    """

    http_status_code = 500
    error_code = "CONFIGURATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        config_key: str | None = None,
        expected_type: str | None = None,
        actual_value: str | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize configuration error.

        Args:
            message: Human-readable error description.
            config_key: The configuration key that is invalid or missing.
            expected_type: The expected type for the configuration value.
            actual_value: The actual value found (should be redacted).
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if config_key:
            details["config_key"] = config_key
        if expected_type:
            details["expected_type"] = expected_type
        if actual_value:
            details["actual_value"] = actual_value

        super().__init__(message, details=details, **kwargs)
        self.config_key = config_key
        self.expected_type = expected_type
        self.actual_value = actual_value


class TimeoutError(ACGSBaseError):
    """
    Raised when an operation times out.

    Attributes:
        operation: The operation that timed out.
        timeout_seconds: The timeout duration that was exceeded.
    """

    http_status_code = 504
    error_code = "OPERATION_TIMEOUT"

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        timeout_seconds: float | None = None,
        **kwargs,
    ) -> None:
        """
        Initialize timeout error.

        Args:
            message: Human-readable error description.
            operation: The operation that timed out.
            timeout_seconds: The timeout duration that was exceeded.
            **kwargs: Additional arguments passed to ACGSBaseError.
        """
        details = kwargs.pop("details", {}) or {}
        if operation:
            details["operation"] = operation
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds

        super().__init__(message, details=details, **kwargs)
        self.operation = operation
        self.timeout_seconds = timeout_seconds


__all__ = [
    "ACGSBaseError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "ConstitutionalViolationError",
    "DataIntegrityError",
    "MACIEnforcementError",
    "RateLimitExceededError",
    "ResourceNotFoundError",
    "ServiceUnavailableError",
    "TenantIsolationError",
    "TimeoutError",
    "ValidationError",
    "rate_limit_error_handler",
]
