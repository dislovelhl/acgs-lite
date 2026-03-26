"""
ACGS-2 Enhanced Agent Bus - Fallback Stubs
Constitutional Hash: 608508a9bd224290

Centralized fallback stub definitions for optional dependencies.
These stubs allow api.py and other modules to run standalone or in
testing environments when optional dependencies are not available.

Usage:
    When the primary import fails, import from this module instead.
    All stubs provide minimal no-op implementations that preserve
    type signatures and allow code to run without errors.

Status:
    This module is ACTIVE (not deprecated).  It is consumed by:
      - src/core/enhanced_agent_bus/api_exceptions.py
      - src/core/enhanced_agent_bus/api/rate_limiting.py
      - src/core/enhanced_agent_bus/api/middleware.py
      - src/core/enhanced_agent_bus/api/routes/batch.py
    Do NOT remove or rename without migrating those callers.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import ACGSBaseError

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

# =============================================================================
# Environment Detection
# =============================================================================

ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
IS_PRODUCTION = ENVIRONMENT in ("production", "prod", "live")


class DependencyNotAvailableError(ACGSBaseError):
    """Raised when a required dependency is not available in production."""

    http_status_code = 500
    error_code = "DEPENDENCY_NOT_AVAILABLE"


def require_dependency(name: str, available: bool) -> None:
    """Enforce that a dependency is available in production.

    In production: raises DependencyNotAvailableError if not available
    In development: logs warning but continues (fail-open for dev convenience)
    """
    if not available:
        if IS_PRODUCTION:
            raise DependencyNotAvailableError(
                f"Required dependency '{name}' is not available. "
                f"This is a fatal error in production. "
                f"Please ensure all dependencies are properly installed."
            )
        else:
            import logging

            logging.getLogger(__name__).warning(
                f"Dependency '{name}' not available - using stub. "
                f"This would be a fatal error in production."
            )


# =============================================================================
# Rate Limiting Stubs (slowapi)
# =============================================================================


class _StubStorage:
    """Stub storage so test code can call limiter._limiter.storage.reset()."""

    def reset(self) -> None:
        pass


class _StubInnerLimiter:
    """Stub inner limiter so test code can access limiter._limiter."""

    def __init__(self) -> None:
        self.storage = _StubStorage()


class StubLimiter:
    """Mock Limiter for when slowapi is not available."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._limiter = _StubInnerLimiter()

    def limit(self, *args: object, **kwargs: object) -> Callable[[Callable], Callable]:
        def decorator(f: Callable) -> Callable:
            return f

        return decorator

    def reset(self) -> None:
        """No-op reset — slowapi is not available."""


def stub_get_remote_address() -> str:
    """Return localhost when slowapi is not available."""
    return "127.0.0.1"


def stub_rate_limit_exceeded_handler(*args: object, **kwargs: object) -> None:
    """No-op handler when slowapi is not available."""


class StubRateLimitExceeded(ACGSBaseError):
    """Fallback RateLimitExceeded when slowapi is not available."""

    http_status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(
        self,
        agent_id: str = "",
        message: str = "",
        retry_after_ms: int | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.retry_after_ms = retry_after_ms
        super().__init__(
            message or "Rate limit exceeded",
            details={"agent_id": agent_id, "retry_after_ms": retry_after_ms},
        )


class RateLimitExceededWrapper:
    """Wrapper for slowapi's RateLimitExceeded to add custom attributes."""

    def __new__(
        cls,
        agent_id: str = "",
        message: str = "",
        retry_after_ms: int | None = None,
    ) -> object:
        """Create a RateLimitExceeded instance with custom attributes."""
        try:
            from slowapi.errors import RateLimitExceeded as SlowAPIRateLimitExceeded

            # Create a basic exception object by subclassing
            class CustomRateLimitExceeded(SlowAPIRateLimitExceeded):
                def __init__(self, agent_id: str, message: str, retry_after_ms: int | None) -> None:
                    # Initialize HTTPException attributes
                    self.status_code = 429
                    self.detail = message or "Rate limit exceeded"
                    # Add custom attributes
                    self.agent_id = agent_id
                    self.message = message
                    self.retry_after_ms = retry_after_ms

            return CustomRateLimitExceeded(agent_id, message, retry_after_ms)
        except (ImportError, TypeError):
            # Fallback to stub if slowapi is not available or if there's an issue
            return StubRateLimitExceeded(agent_id, message, retry_after_ms)


# =============================================================================
# Security Stubs (shared.security)
# =============================================================================


def stub_get_cors_config() -> JSONDict:
    """Fail-closed CORS fallback: deny all cross-origin requests."""
    import logging

    logging.getLogger(__name__).warning(
        "Using CORS stub: all cross-origin requests will be denied. "
        "Install src.core.shared.security.cors_config for proper CORS."
    )
    return {
        "allow_origins": [],
        "allow_credentials": False,
        "allow_methods": ["GET"],
        "allow_headers": [],
    }


class StubSecurityHeadersConfig:
    """Fallback SecurityHeadersConfig when import fails."""

    @classmethod
    def for_development(cls) -> StubSecurityHeadersConfig:
        return cls()

    @classmethod
    def for_production(cls) -> StubSecurityHeadersConfig:
        return cls()


class StubSecurityHeadersMiddleware:
    """Fallback SecurityHeadersMiddleware when import fails."""

    def __init__(self, app: ASGIApp, config: StubSecurityHeadersConfig | None = None) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class StubTenantContextConfig:
    """Fallback stub for TenantContextConfig when import fails."""

    required: bool = True
    fail_open: bool = False
    exempt_paths: ClassVar[list[str]] = []

    def __init__(
        self,
        required: bool = True,
        fail_open: bool = False,
        exempt_paths: list[str] | None = None,
    ) -> None:
        if IS_PRODUCTION and fail_open:
            import logging

            logging.getLogger(__name__).warning(
                "fail_open=True requested but BLOCKED in production. "
                "Forcing fail_open=False for security."
            )
            fail_open = False
        self.required = required
        self.fail_open = fail_open
        self.exempt_paths = exempt_paths or ["/health", "/metrics", "/docs"]

    @classmethod
    def from_env(cls) -> StubTenantContextConfig:
        return cls(required=True, fail_open=False)


class StubTenantContextMiddleware:
    """Fallback stub for TenantContextMiddleware when import fails."""

    def __init__(self, app: ASGIApp, config: StubTenantContextConfig | None = None) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and self.config
            and self.config.required
            and not self.config.fail_open
        ):
            # P0-5: Harden fallback stub to fail-closed in production/secure modes
            from starlette.responses import JSONResponse

            response = JSONResponse(
                status_code=400,
                content={
                    "error": "Security validation required",
                    "message": "Tenant context middleware fallback reached. Production deployment must use shared security package.",
                    "code": "SECURITY_FALLBACK_REJECTED",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# =============================================================================
# Logging Stubs (acgs_logging)
# =============================================================================


def stub_create_correlation_middleware() -> Callable | None:
    """Return None when acgs_logging is not available."""
    return None


# =============================================================================
# Exception Stubs (minimal fallbacks when exceptions.py import fails)
# =============================================================================


class StubAgentBusError(ACGSBaseError):
    """Base fallback exception for agent bus errors."""

    http_status_code = 500
    error_code = "AGENT_BUS_ERROR"

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, details=kwargs)


class StubConstitutionalError(StubAgentBusError):
    """Fallback constitutional error."""


class StubMessageError(StubAgentBusError):
    """Fallback message error."""


class StubMessageTimeoutError(StubMessageError):
    """Fallback message timeout error."""

    def __init__(self, message_id: str = "", message: str = "", **kwargs: object) -> None:
        self.message_id = message_id
        super().__init__(message, **kwargs)


class StubBusNotStartedError(StubAgentBusError):
    """Fallback bus not started error."""

    def __init__(self, operation: str = "", message: str = "", **kwargs: object) -> None:
        self.operation = operation
        super().__init__(message, **kwargs)


class StubBusOperationError(StubAgentBusError):
    """Fallback bus operation error."""


class StubOPAConnectionError(StubAgentBusError):
    """Fallback OPA connection error."""


class StubMACIError(StubAgentBusError):
    """Fallback MACI error."""


class StubPolicyError(StubAgentBusError):
    """Fallback policy error."""


class StubAgentError(StubAgentBusError):
    """Fallback agent error."""


# =============================================================================
# Model Stubs (Pydantic models when models.py import fails)
# =============================================================================


from pydantic import BaseModel, Field


class StubBatchRequestItem(BaseModel):
    """Stub for BatchRequestItem when models.py is not available."""

    request_id: str = ""
    content: str = ""
    from_agent: str = ""
    to_agent: str = ""
    message_type: str = "QUERY"
    tenant_id: str = ""
    priority: str = "NORMAL"


class StubBatchRequest(BaseModel):
    """Stub for BatchRequest when models.py is not available."""

    batch_id: str = ""
    items: list[StubBatchRequestItem] = Field(default_factory=list)
    tenant_id: str = ""
    options: JSONDict = Field(default_factory=dict)

    def validate_tenant_consistency(self) -> str | None:
        """Stub: tenant_id is overwritten by caller before this check."""
        if not self.tenant_id:
            return None
        mismatched = [
            item.tenant_id
            for item in self.items
            if item.tenant_id and item.tenant_id != "default" and item.tenant_id != self.tenant_id
        ]
        if mismatched:
            return f"Items have mismatched tenant IDs: {mismatched[:3]}"
        return None


class StubBatchResponseItem(BaseModel):
    """Stub for BatchResponseItem when models.py is not available."""

    request_id: str = ""
    success: bool = False
    error: str | None = None
    result: JSONDict | None = None


class StubBatchStats(BaseModel):
    """Stub for BatchStats when models.py is not available."""

    total_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    processing_time_ms: float = 0.0


class StubBatchResponse(BaseModel):
    """Stub for BatchResponse when models.py is not available."""

    batch_id: str = ""
    results: list[StubBatchResponseItem] = Field(default_factory=list)
    stats: StubBatchStats = Field(default_factory=StubBatchStats)
    warnings: list[str] = Field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH


# =============================================================================
# Convenience Exports
# =============================================================================

# Model aliases
BatchRequestItem = StubBatchRequestItem
BatchRequest = StubBatchRequest
BatchResponseItem = StubBatchResponseItem
BatchStats = StubBatchStats
BatchResponse = StubBatchResponse

# These aliases allow simple replacement in import statements
Limiter = StubLimiter
get_remote_address = stub_get_remote_address
_rate_limit_exceeded_handler = stub_rate_limit_exceeded_handler
RateLimitExceeded = StubRateLimitExceeded
get_cors_config = stub_get_cors_config
SecurityHeadersConfig = StubSecurityHeadersConfig
SecurityHeadersMiddleware = StubSecurityHeadersMiddleware
TenantContextConfig = StubTenantContextConfig
TenantContextMiddleware = StubTenantContextMiddleware
create_correlation_middleware = stub_create_correlation_middleware

# Exception aliases
AgentBusError = StubAgentBusError
ConstitutionalError = StubConstitutionalError
MessageError = StubMessageError
MessageTimeoutError = StubMessageTimeoutError
BusNotStartedError = StubBusNotStartedError
BusOperationError = StubBusOperationError
OPAConnectionError = StubOPAConnectionError
MACIError = StubMACIError
PolicyError = StubPolicyError
AgentError = StubAgentError


__all__ = [
    "ENVIRONMENT",
    # Environment detection
    "IS_PRODUCTION",
    # Exceptions
    "AgentBusError",
    "AgentError",
    "BatchRequest",
    # Models
    "BatchRequestItem",
    "BatchResponse",
    "BatchResponseItem",
    "BatchStats",
    "BusNotStartedError",
    "BusOperationError",
    "ConstitutionalError",
    "DependencyNotAvailableError",
    # Rate limiting
    "Limiter",
    "MACIError",
    "MessageError",
    "MessageTimeoutError",
    "OPAConnectionError",
    "PolicyError",
    "RateLimitExceeded",
    "RateLimitExceededWrapper",
    "SecurityHeadersConfig",
    "SecurityHeadersMiddleware",
    "StubAgentBusError",
    "StubAgentError",
    "StubBatchRequest",
    "StubBatchRequestItem",
    "StubBatchResponse",
    "StubBatchResponseItem",
    "StubBatchStats",
    "StubBusNotStartedError",
    "StubBusOperationError",
    "StubConstitutionalError",
    "StubLimiter",
    "StubMACIError",
    "StubMessageError",
    "StubMessageTimeoutError",
    "StubOPAConnectionError",
    "StubPolicyError",
    "StubRateLimitExceeded",
    "StubSecurityHeadersConfig",
    "StubSecurityHeadersMiddleware",
    "StubTenantContextConfig",
    "StubTenantContextMiddleware",
    "TenantContextConfig",
    "TenantContextMiddleware",
    "_rate_limit_exceeded_handler",
    # Logging
    "create_correlation_middleware",
    # Security
    "get_cors_config",
    "get_remote_address",
    "require_dependency",
    "stub_create_correlation_middleware",
    "stub_get_cors_config",
    "stub_get_remote_address",
    "stub_rate_limit_exceeded_handler",
]
