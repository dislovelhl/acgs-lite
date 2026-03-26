"""
ACGS-2 Standardized Error Handling Library
Constitutional Hash: 608508a9bd224290

This package provides a unified approach to error handling, retries, circuit breakers,
and structured error logging across all ACGS-2 services.

Modules:
    - exceptions: Base exception classes with constitutional context
    - retry: Retry utilities with exponential backoff
    - circuit_breaker: Circuit breaker wrapper for fault tolerance
    - logging: Standardized error logging with correlation ID propagation

Usage:
    from src.core.shared.errors import (
        # Exceptions
        ACGSBaseError,
        ConstitutionalViolationError,
        MACIEnforcementError,
        TenantIsolationError,
        ValidationError,
        ServiceUnavailableError,
        RateLimitExceededError,
        # Retry utilities
        retry,
        RetryConfig,
        # Circuit breaker
        circuit_breaker,
        CircuitBreakerConfig,
        # Logging
        log_error,
        ErrorContext,
    )

Example:
    @retry(max_retries=3, base_delay=1.0)
    @circuit_breaker("policy_registry")
    async def fetch_policy(policy_id: str) -> dict:
        try:
            return await policy_client.get(policy_id)
        except ConnectionError as e:
            raise ServiceUnavailableError(
                message="Policy Registry unavailable",
                service_name="policy_registry",
                cause=e,
            )
"""

from src.core.shared.constants import CONSTITUTIONAL_HASH

__version__ = "1.0.0"
__author__ = "ACGS-2 Team"

# Import all public APIs
from .circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    circuit_breaker,
    get_circuit_breaker,
)
from .exceptions import (
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
    ValidationError,
)
from .exceptions import (
    TimeoutError as ACGSTimeoutError,
)
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
    # Constants
    "CONSTITUTIONAL_HASH",
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    # Base exceptions
    "ACGSBaseError",
    "ACGSTimeoutError",
    "AuthenticationError",
    "AuthorizationError",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "ConfigurationError",
    "ConstitutionalViolationError",
    "DataIntegrityError",
    "MACIEnforcementError",
    "RateLimitExceededError",
    "ResourceNotFoundError",
    "RetryBudget",
    "RetryConfig",
    "RetryExhaustedError",
    "ServiceUnavailableError",
    "TenantIsolationError",
    "ValidationError",
    # Circuit breaker
    "circuit_breaker",
    "exponential_backoff",
    "get_circuit_breaker",
    # Retry utilities
    "retry",
    "retry_async",
    "retry_sync",
]
