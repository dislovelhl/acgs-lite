"""Shim package for src.core.shared.errors.

This package marker enables ``from enhanced_agent_bus._compat.errors.exceptions import X``
patterns. It re-exports all names from the flat ``_compat/errors.py`` module.

NOTE: Python resolves ``_compat.errors`` as this directory package (not the sibling
``_compat/errors.py`` flat module) once the directory exists, so we must replicate
the flat module exports here.
"""
from __future__ import annotations

import traceback as _traceback
from datetime import UTC, datetime
from uuid import uuid4

try:
    from src.core.shared.errors.exceptions import *  # noqa: F403
    from src.core.shared.errors.exceptions import (  # explicit re-exports
        ACGSBaseError,
        AuthenticationError,
        AuthorizationError,
        ConfigurationError,
        ConstitutionalViolationError,
        DataIntegrityError,
        MACIEnforcementError,
        RateLimitExceededError,
        ResourceNotFoundError,
        ServiceUnavailableError,
        TenantIsolationError,
        TimeoutError,
        ValidationError,
        rate_limit_error_handler,
    )
except ImportError:
    _HASH = "608508a9bd224290"

    class ACGSBaseError(Exception):
        http_status_code: int = 500
        error_code: str = "ACGS_ERROR"

        def __init__(
            self,
            message: str,
            *,
            error_code: str | None = None,
            constitutional_hash: str = _HASH,
            correlation_id: str | None = None,
            details: dict | None = None,
            cause: BaseException | None = None,
            http_status_code: int | None = None,
        ) -> None:
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
            if cause is not None:
                self.__cause__ = cause

        def to_dict(self) -> dict:
            result: dict = {
                "error": self.error_code,
                "message": self.message,
                "constitutional_hash": self.constitutional_hash,
                "correlation_id": self.correlation_id,
                "timestamp": self.timestamp,
            }
            if self.details:
                result["details"] = self.details
            if self.cause is not None:
                result["cause"] = {"type": type(self.cause).__name__, "message": str(self.cause)}
            return result

        def to_log_dict(self) -> dict:
            result = self.to_dict()
            result["exception_type"] = type(self).__name__
            result["http_status_code"] = self.http_status_code
            if self.cause is not None:
                result["cause_traceback"] = _traceback.format_exception(
                    type(self.cause), self.cause, self.cause.__traceback__
                )
            return result

        def __str__(self) -> str:
            parts = [f"[{self.constitutional_hash}]", f"[{self.error_code}]", self.message]
            if self.correlation_id:
                parts.insert(1, f"[{self.correlation_id[:8]}...]")
            return " ".join(parts)

        def __repr__(self) -> str:
            return (
                f"{self.__class__.__name__}("
                f"message={self.message!r}, "
                f"error_code={self.error_code!r}, "
                f"correlation_id={self.correlation_id!r}, "
                f"http_status_code={self.http_status_code})"
            )

    class ConstitutionalViolationError(ACGSBaseError):
        http_status_code = 403
        error_code = "CONSTITUTIONAL_VIOLATION"

        def __init__(self, message: str, *, violations: list[str] | None = None,
                     policy_id: str | None = None, action: str | None = None, **kw) -> None:  # type: ignore[override]
            details = kw.pop("details", {}) or {}
            if violations:
                details["violations"] = violations
            if policy_id:
                details["policy_id"] = policy_id
            if action:
                details["action"] = action
            super().__init__(message, details=details, **kw)
            self.violations = violations or []
            self.policy_id = policy_id
            self.action = action

    class MACIEnforcementError(ACGSBaseError):
        http_status_code = 403
        error_code = "MACI_ENFORCEMENT_FAILURE"

    class TenantIsolationError(ACGSBaseError):
        http_status_code = 403
        error_code = "TENANT_ISOLATION_VIOLATION"

    class ValidationError(ACGSBaseError):
        http_status_code = 400
        error_code = "VALIDATION_ERROR"

    class ServiceUnavailableError(ACGSBaseError):
        http_status_code = 503
        error_code = "SERVICE_UNAVAILABLE"

    class RateLimitExceededError(ACGSBaseError):
        http_status_code = 429
        error_code = "RATE_LIMIT_EXCEEDED"

    class AuthenticationError(ACGSBaseError):
        http_status_code = 401
        error_code = "AUTHENTICATION_FAILED"

    class AuthorizationError(ACGSBaseError):
        http_status_code = 403
        error_code = "AUTHORIZATION_DENIED"

    class ResourceNotFoundError(ACGSBaseError):
        http_status_code = 404
        error_code = "RESOURCE_NOT_FOUND"

    class DataIntegrityError(ACGSBaseError):
        http_status_code = 409
        error_code = "DATA_INTEGRITY_VIOLATION"

    class ConfigurationError(ACGSBaseError):
        http_status_code = 500
        error_code = "CONFIGURATION_ERROR"

    class TimeoutError(ACGSBaseError):
        http_status_code = 504
        error_code = "OPERATION_TIMEOUT"

    async def rate_limit_error_handler(request: object, exc: RateLimitExceededError) -> object:
        """Stub rate-limit handler for standalone mode."""
        try:
            from fastapi.responses import JSONResponse
        except ImportError:
            class JSONResponse:  # type: ignore[no-redef]
                def __init__(self, **kw: object) -> None:
                    pass
        return JSONResponse(status_code=429, content={"error": "Too Many Requests", "message": exc.message})
