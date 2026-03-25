"""
Retry and Backoff Utilities — Facade
Constitutional Hash: 608508a9bd224290

Canonical location: src.core.shared.resilience.retry
This module re-exports all symbols for backward compatibility.
"""

import importlib

_retry_module = importlib.import_module("src.core.shared.resilience.retry")

DEFAULT_RETRYABLE_EXCEPTIONS = _retry_module.DEFAULT_RETRYABLE_EXCEPTIONS
RetryBudget = _retry_module.RetryBudget
RetryConfig = _retry_module.RetryConfig
RetryExhaustedError = _retry_module.RetryExhaustedError
exponential_backoff = _retry_module.exponential_backoff
retry = _retry_module.retry
retry_async = _retry_module.retry_async
retry_sync = _retry_module.retry_sync

__all__ = [
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    "RetryBudget",
    "RetryConfig",
    "RetryExhaustedError",
    "exponential_backoff",
    "retry",
    "retry_async",
    "retry_sync",
]
