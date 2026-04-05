"""
ACGS-2 Enhanced Agent Bus API Exception Handlers
Exception handlers and middleware for the Enhanced Agent Bus API
Constitutional Hash: 608508a9bd224290

This module contains all exception handlers and error response utilities
extracted from api.py for better code organization and maintainability.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from enhanced_agent_bus._compat.acgs_logging import init_service_logging

    logger = init_service_logging("enhanced-agent-bus", level="INFO", json_format=True)
except ImportError:
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO)
    logger = get_logger(__name__)  # type: ignore[assignment]

try:
    from .exceptions import (
        AgentBusError,
        AgentError,
        BusNotStartedError,
        BusOperationError,
        ConstitutionalError,
        MACIError,
        MessageError,
        MessageTimeoutError,
        OPAConnectionError,
        PolicyError,
    )
except (ImportError, ValueError):
    try:
        from exceptions import (  # type: ignore[no-redef]
            AgentBusError,
            AgentError,
            BusNotStartedError,
            BusOperationError,
            ConstitutionalError,
            MACIError,
            MessageError,
            MessageTimeoutError,
            OPAConnectionError,
            PolicyError,
        )
    except (ImportError, ValueError):
        from .fallback_stubs import (  # type: ignore[assignment, no-redef]
            AgentBusError,
            AgentError,
            BusNotStartedError,
            BusOperationError,
            ConstitutionalError,
            MACIError,
            MessageError,
            MessageTimeoutError,
            OPAConnectionError,
            PolicyError,
        )

try:
    from slowapi.errors import RateLimitExceeded
except ImportError:
    from .fallback_stubs import RateLimitExceeded

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="unknown")

RATE_LIMIT_REQUESTS_PER_MINUTE = 60


def create_error_response(
    exc: Exception, _status_code: int, request_id: str | None = None
) -> JSONDict:
    """Helper to create standardized error responses."""
    return {
        "status": "error",
        "code": getattr(exc, "code", getattr(exc, "error_code", "INTERNAL_ERROR")),
        "message": str(exc),
        "details": getattr(exc, "details", {}),
        "request_id": request_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded errors with 429 status and RFC 6585 rate limit headers."""
    status_code = 429
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )

    # Calculate reset time as epoch timestamp (seconds since Unix epoch)
    reset_seconds = exc.retry_after_ms // 1000 if exc.retry_after_ms else 60
    reset_epoch = int(datetime.now(UTC).timestamp()) + reset_seconds

    # RFC 6585 rate limit headers
    headers = {
        "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS_PER_MINUTE),
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(reset_epoch),
        "Retry-After": str(reset_seconds),
    }

    logger.warning(f"Rate limit exceeded for agent '{exc.agent_id}': {exc.message}")
    return JSONResponse(status_code=status_code, content=response, headers=headers)


async def message_timeout_handler(request: Request, exc: MessageTimeoutError) -> JSONResponse:
    """Handle message timeout errors with 504 status."""
    status_code = 504
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.error(f"Message timeout for '{exc.message_id}': {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def bus_not_started_handler(request: Request, exc: BusNotStartedError) -> JSONResponse:
    """Handle bus not started errors with 503 status."""
    status_code = 503
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.error(f"Bus not started for operation '{exc.operation}': {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def opa_connection_handler(request: Request, exc: OPAConnectionError) -> JSONResponse:
    """Handle OPA connection errors with 503 status."""
    status_code = 503
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.error(f"OPA connection error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def constitutional_error_handler(request: Request, exc: ConstitutionalError) -> JSONResponse:
    """Handle constitutional validation errors with 400 status."""
    status_code = 400
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.warning(f"Constitutional error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def maci_error_handler(request: Request, exc: MACIError) -> JSONResponse:
    """Handle MACI role separation errors."""
    status_code = 403
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.warning(f"MACI error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def policy_error_handler(request: Request, exc: PolicyError) -> JSONResponse:
    """Handle policy evaluation errors."""
    status_code = 400
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.error(f"Policy error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
    """Handle agent-related errors."""
    status_code = 400
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.warning(f"Agent error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def message_error_handler(request: Request, exc: MessageError) -> JSONResponse:
    """Handle message-related errors."""
    status_code = 400
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.warning(f"Message error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def bus_operation_error_handler(request: Request, exc: BusOperationError) -> JSONResponse:
    """Handle bus operation errors with 503 status."""
    status_code = 400
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.error(f"Bus operation error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def agent_bus_error_handler(request: Request, exc: AgentBusError) -> JSONResponse:
    """Handle generic AgentBusError (catch-all for bus errors)."""
    status_code = 400
    response = create_error_response(
        exc,
        status_code,
        request_id=request.headers.get("X-Request-ID"),
    )
    logger.error(f"Agent bus error: {exc.message}")
    return JSONResponse(status_code=status_code, content=response)


async def global_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions with structured error response."""
    correlation_id = correlation_id_var.get()
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "correlation_id": correlation_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


async def correlation_id_middleware(request: Request, call_next: Callable[..., object]) -> Response:
    """Add correlation ID to all requests for distributed tracing."""
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    correlation_id_var.set(correlation_id)

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers with the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(MessageTimeoutError, message_timeout_handler)
    app.add_exception_handler(BusNotStartedError, bus_not_started_handler)
    app.add_exception_handler(OPAConnectionError, opa_connection_handler)
    app.add_exception_handler(ConstitutionalError, constitutional_error_handler)
    app.add_exception_handler(MACIError, maci_error_handler)
    app.add_exception_handler(PolicyError, policy_error_handler)
    app.add_exception_handler(AgentError, agent_error_handler)
    app.add_exception_handler(MessageError, message_error_handler)
    app.add_exception_handler(BusOperationError, bus_operation_error_handler)
    app.add_exception_handler(AgentBusError, agent_bus_error_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    logger.info("All exception handlers registered successfully")
