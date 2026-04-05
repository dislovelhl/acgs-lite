"""Shim for src.core.shared.errors.exceptions.

This is the most critical shim — ACGSBaseError is the root of the exception
hierarchy and is imported by fallback_stubs.py early in the boot chain.
The standalone fallback must be self-contained (no imports from other _compat modules).
"""

from __future__ import annotations

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
    import traceback
    from datetime import UTC, datetime
    from uuid import uuid4

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
                result["cause_traceback"] = traceback.format_exception(
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

        def __init__(
            self,
            message: str,
            *,
            violations: list[str] | None = None,
            policy_id: str | None = None,
            action: str | None = None,
            **kw,
        ) -> None:
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

        def __init__(
            self,
            message: str,
            *,
            agent_id: str | None = None,
            role: str | None = None,
            action: str | None = None,
            target_agent_id: str | None = None,
            **kw,
        ) -> None:
            details = kw.pop("details", {}) or {}
            for k, v in [
                ("agent_id", agent_id),
                ("role", role),
                ("action", action),
                ("target_agent_id", target_agent_id),
            ]:
                if v:
                    details[k] = v
            super().__init__(message, details=details, **kw)
            self.agent_id = agent_id
            self.role = role
            self.action = action
            self.target_agent_id = target_agent_id

    class TenantIsolationError(ACGSBaseError):
        http_status_code = 403
        error_code = "TENANT_ISOLATION_VIOLATION"

        def __init__(self, message: str, **kw) -> None:
            super().__init__(message, **kw)

    class ValidationError(ACGSBaseError):
        http_status_code = 400
        error_code = "VALIDATION_ERROR"

        def __init__(self, message: str, *, field: str | None = None, **kw) -> None:
            details = kw.pop("details", {}) or {}
            if field:
                details["field"] = field
            super().__init__(message, details=details, **kw)
            self.field = field
            self.validation_errors: list = []

    class ServiceUnavailableError(ACGSBaseError):
        http_status_code = 503
        error_code = "SERVICE_UNAVAILABLE"

    class RateLimitExceededError(ACGSBaseError):
        http_status_code = 429
        error_code = "RATE_LIMIT_EXCEEDED"

        def __init__(
            self, message: str, *, limit: int | None = None, retry_after: int | None = None, **kw
        ) -> None:
            super().__init__(message, **kw)
            self.limit = limit
            self.retry_after = retry_after
            self.window_seconds = kw.get("window_seconds")
            self.limit_type = kw.get("limit_type")

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

        return JSONResponse(
            status_code=429, content={"error": "Too Many Requests", "message": exc.message}
        )
