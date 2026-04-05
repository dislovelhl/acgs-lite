"""Shim for src.core.shared.security.error_sanitizer."""

from __future__ import annotations

try:
    from src.core.shared.security.error_sanitizer import *  # noqa: F403
except ImportError:

    def sanitize_error(exc: BaseException) -> str:
        """Return only the exception type name — never leak message details."""
        return type(exc).__name__

    def sanitize_error_message(message: str) -> str:
        """Return a generic error string."""
        return "An internal error occurred."

    def safe_error_response(exc: BaseException) -> dict[str, str]:
        """Build a safe error dict for API responses."""
        return {
            "error": type(exc).__name__,
            "message": "An internal error occurred.",
        }
