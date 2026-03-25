"""
ACGS-2 Circuit Breaker Enums

Constitutional Hash: 608508a9bd224290

This module defines the core enums for circuit breaker states,
fallback strategies, and service severity levels.
"""

from enum import Enum


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit tripped, requests are rejected/fallback used
    HALF_OPEN = "half_open"  # Testing if service recovered


class FallbackStrategy(str, Enum):
    """Fallback strategies when circuit is open."""

    FAIL_CLOSED = "fail_closed"  # Reject all requests (critical services)
    CACHED_VALUE = "cached_value"  # Return cached value
    QUEUE_FOR_RETRY = "queue_for_retry"  # Queue for later retry
    BYPASS = "bypass"  # Skip the service entirely
    DEFAULT_VALUE = "default_value"  # Return a default value


class ServiceSeverity(str, Enum):
    """Service criticality levels."""

    CRITICAL = "critical"  # Constitutional validation cannot be skipped
    HIGH = "high"  # Important but has fallback
    MEDIUM = "medium"  # Standard service
    LOW = "low"  # Non-essential service


__all__ = [
    "CircuitState",
    "FallbackStrategy",
    "ServiceSeverity",
]
