"""
ACGS-2 Centralized Input Validation Framework
Constitutional Hash: 608508a9bd224290

Provides utilities for sanitizing input, preventing path traversal,
enforcing size limits, and detecting injection patterns.

SECURITY NOTE: This is a defense-in-depth layer. Primary defenses are:
- Parameterized queries (SQL injection)
- Output encoding (XSS)
- Schema validation (Pydantic)
"""

import re
from pathlib import Path

from fastapi import HTTPException, Request

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
# SQL Injection patterns - expanded coverage
SQL_INJECTION_PATTERNS = [
    r"UNION\s+SELECT",
    r"UNION\s+ALL\s+SELECT",
    r"SELECT\s+.*\s+FROM",
    r"INSERT\s+INTO",
    r"UPDATE\s+.*\s+SET",
    r"DELETE\s+FROM",
    r"DROP\s+(TABLE|DATABASE|INDEX)",
    r"TRUNCATE\s+TABLE",
    r"ALTER\s+TABLE",
    r"CREATE\s+(TABLE|DATABASE|INDEX)",
    r"OR\s+['\"].*?['\"]\s*=\s*['\"].*?['\"]",
    r"OR\s+1\s*=\s*1",
    r"OR\s+TRUE",
    r";\s*--",  # SQL comment after statement
    r";\s*/\*",  # SQL block comment
    r"EXEC(\s+|\()",  # Stored procedure execution
    r"EXECUTE(\s+|\()",
    r"xp_cmdshell",  # SQL Server command execution
    r"WAITFOR\s+DELAY",  # Time-based SQL injection
    r"BENCHMARK\s*\(",  # MySQL time-based
    r"SLEEP\s*\(",  # Time-based injection
]

# NoSQL Injection patterns
NOSQL_INJECTION_PATTERNS = [
    r"\$gt",
    r"\$lt",
    r"\$ne",
    r"\$in",
    r"\$nin",
    r"\$or",
    r"\$and",
    r"\$regex",
    r"\$where",
    r"\$exists",
    r"\$type",
    r"\$expr",
]

# XSS patterns - expanded coverage
XSS_PATTERNS = [
    r"<script.*?>",
    r"</script>",
    r"javascript:",
    r"vbscript:",
    r"on\w+\s*=",  # Event handlers
    r"<iframe",
    r"<object",
    r"<embed",
    r"<svg.*?onload",
    r"<img.*?onerror",
    r"expression\s*\(",  # CSS expression
    r"url\s*\(\s*['\"]?\s*data:",  # Data URLs in CSS
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    r";\s*\w+",  # Command chaining
    r"\|\s*\w+",  # Pipe to command
    r"`[^`]+`",  # Backtick execution
    r"\$\([^)]+\)",  # Command substitution
]


class InputValidator:
    """Centralized input validation and sanitization."""

    @staticmethod
    def sanitize_string(text: str) -> str:
        """Basic string sanitization."""
        if not isinstance(text, str):
            return text
        # Remove null bytes
        text = text.replace("\x00", "")
        return text.strip()

    @staticmethod
    def validate_path(path_str: str, base_dir: str | Path) -> Path:
        """
        Prevent path traversal by ensuring the path is within base_dir.
        """
        base_path = Path(base_dir).resolve()
        target_path = Path(path_str).resolve()

        try:
            target_path.relative_to(base_path)
        except ValueError as e:
            logger.warning(f"Path traversal attempt detected: {path_str} outside of {base_dir}")
            raise HTTPException(status_code=400, detail="Invalid path") from e

        return target_path

    @staticmethod
    def check_injection(text: str, patterns: list[str] | None = None) -> bool:
        """
        Check if text matches any injection patterns.
        """
        if not isinstance(text, str):
            return False

        if patterns is None:
            patterns = SQL_INJECTION_PATTERNS + NOSQL_INJECTION_PATTERNS + XSS_PATTERNS

        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def enforce_size_limit(data: object, max_bytes: int):
        """Enforce size limit on input data."""
        import sys

        if sys.getsizeof(data) > max_bytes:
            raise HTTPException(status_code=413, detail="Payload too large")


async def validate_request_body(request: Request):
    """Middleware-style function to validate request body for injections."""
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
            if _contains_injection(body):
                logger.warning(f"Injection detected in request body from {request.client.host}")
                raise HTTPException(status_code=400, detail="Potential injection detected")
        except (ValueError, RuntimeError):
            pass  # Not a JSON body or already consumed


def _contains_injection(data: str | dict[str, object] | list[object] | object) -> bool:
    """Recursively check for injections in data structures."""
    if isinstance(data, str):
        return InputValidator.check_injection(data)
    elif isinstance(data, dict):
        return any(_contains_injection(v) for v in data.values())
    elif isinstance(data, list):
        return any(_contains_injection(item) for item in data)
    return False


__all__ = ["InputValidator", "validate_request_body"]
