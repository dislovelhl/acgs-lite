"""
Rate Limiting Enums.

Constitutional Hash: cdd01ef066bc6cf2
"""

from enum import StrEnum


class RateLimitScope(StrEnum):
    """Scope for rate limiting."""

    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"
    GLOBAL = "global"
    TENANT = "tenant"


class RateLimitAlgorithm(StrEnum):
    """Rate limiting algorithms."""

    TOKEN_BUCKET = "token_bucket"  # noqa: S105
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
