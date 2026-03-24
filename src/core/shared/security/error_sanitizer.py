"""
ACGS-2 Centralized Error Sanitizer
Constitutional Hash: cdd01ef066bc6cf2

Provides a single, comprehensive error-sanitization function that replaces
fragile per-module regex scrubbing.  All infrastructure clients (Kafka, OPA,
ML governance, Redis, etc.) should delegate to `sanitize_error()` instead of
maintaining their own `_sanitize_error` method.
"""

import re

from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment

# Compiled once at module level for performance on hot paths.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Generic credential fields (key=, password=, token=, secret=)
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*'[^']*'", re.IGNORECASE), r"\1='REDACTED'"),
    (re.compile(r'(password|passwd|pwd)\s*[=:]\s*"[^"]*"', re.IGNORECASE), r'\1="REDACTED"'),
    (re.compile(r"(key|token|secret|bearer)\s*[=:]\s*'[^']*'", re.IGNORECASE), r"\1='REDACTED'"),
    (re.compile(r'(key|token|secret|bearer)\s*[=:]\s*"[^"]*"', re.IGNORECASE), r'\1="REDACTED"'),
    # Query-string style: key=VALUE&
    (re.compile(r"(key|token|secret|password)=[^&\s]+", re.IGNORECASE), r"\1=REDACTED"),
    # URL credentials  (proto://user:pass@host)  # pragma: allowlist secret
    (re.compile(r"(https?://)([^:]+):([^@]+)@"), r"\1REDACTED:REDACTED@"),
    # Bootstrap server details (Kafka)
    (re.compile(r"bootstrap_servers='[^']+'"), "bootstrap_servers='REDACTED'"),
    # Connection strings (PostgreSQL, Redis, AMQP)
    (
        re.compile(r"(postgres|redis|amqp|mysql)://[^@\s]+@", re.IGNORECASE),
        r"\1://REDACTED:REDACTED@",
    ),
    # Bearer tokens in headers
    (re.compile(r"(Authorization:\s*Bearer\s+)\S+", re.IGNORECASE), r"\1REDACTED"),
    # Absolute file-system paths (leaks internal layout in exception messages)
    (re.compile(r"/(?:home|root|usr|var|etc|opt|srv|app|code)/\S+"), "<path>"),
]


def sanitize_error(error: Exception | str | None) -> str:
    """Return a scrubbed string representation safe for logs and API responses.

    Args:
        error: The exception, string, or ``None`` to sanitize.

    Returns:
        Sanitized error message with all credential patterns redacted.
    """
    if error is None:
        return "Unknown error"

    msg = str(error)
    for pattern, replacement in _PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg

_PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod", "staging"})


def _is_production() -> bool:
    environment = resolve_runtime_environment(getattr(settings, "env", None))
    return environment in _PRODUCTION_ENVIRONMENTS


def safe_error_detail(error: Exception | str | None, operation: str = "operation") -> str:
    """Return a production-safe error message for API responses.

    In production environments, returns a generic message to prevent
    information leakage. In development/test, returns sanitized details
    for debugging purposes.

    Args:
        error: The exception or error string.
        operation: Description of the operation that failed (e.g., "create tenant").

    Returns:
        Sanitized error message safe for API responses.

    Usage:
        try:
            result = await some_operation()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=safe_error_detail(e, "create tenant")
            )
    """
    if _is_production():
        return f"{operation.capitalize()} failed. Please try again or contact support."
    return sanitize_error(error)


def safe_error_message(error: Exception | str | None, context: str = "request") -> str:
    """Return a production-safe error message with context.

    Similar to safe_error_detail but with a more user-friendly format.

    Args:
        error: The exception or error string.
        context: Context for the error (e.g., "tenant creation").

    Returns:
        User-friendly error message safe for API responses.
    """
    if _is_production():
        return f"An error occurred during {context}. Please try again."
    sanitized = sanitize_error(error)
    return f"{context} failed: {sanitized}"
