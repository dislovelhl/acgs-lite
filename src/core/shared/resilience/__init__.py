"""
Canonical resilience patterns module for ACGS-2.
Constitutional Hash: 608508a9bd224290

This package is the canonical location for shared resilience patterns,
including retry, backoff, and retry budget utilities.
"""

from src.core.shared.constants import CONSTITUTIONAL_HASH

from .retry import (
    DEFAULT_RETRYABLE_EXCEPTIONS,
    RetryBudget,
    RetryConfig,
    RetryExhaustedError,
    exponential_backoff,
    retry,
    retry_async,
    retry_sync,
)

__all__ = [
    "CONSTITUTIONAL_HASH",
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    "RetryBudget",
    "RetryConfig",
    "RetryExhaustedError",
    "exponential_backoff",
    "retry",
    "retry_async",
    "retry_sync",
]
