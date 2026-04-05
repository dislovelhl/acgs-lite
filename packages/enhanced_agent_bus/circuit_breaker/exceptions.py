"""
ACGS-2 Circuit Breaker Exceptions

Constitutional Hash: 608508a9bd224290

This module defines exceptions for circuit breaker operations.
"""

from enhanced_agent_bus._compat.errors import ACGSBaseError


class CircuitBreakerOpen(ACGSBaseError):
    """Exception raised when circuit breaker is open and fallback not available."""

    http_status_code = 503
    error_code = "CIRCUIT_BREAKER_OPEN"

    def __init__(
        self,
        service_name: str,
        message: str = "Circuit breaker is open",
        fallback_strategy: str = "fail_closed",
    ):
        self.service_name = service_name
        self.fallback_strategy = fallback_strategy
        super().__init__(
            f"{service_name}: {message} (fallback={fallback_strategy})",
            details={"service_name": service_name, "fallback_strategy": fallback_strategy},
        )


__all__ = [
    "CircuitBreakerOpen",
]
