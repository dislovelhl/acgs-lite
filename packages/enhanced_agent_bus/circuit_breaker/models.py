"""
ACGS-2 Circuit Breaker Models

Constitutional Hash: 608508a9bd224290

This module defines data models for circuit breaker metrics and queued requests.
"""

from dataclasses import dataclass


@dataclass
class CircuitBreakerMetrics:
    """Metrics for a circuit breaker instance."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    last_state_change_time: float | None = None
    fallback_used_count: int = 0
    queue_size: int = 0


@dataclass
class QueuedRequest:
    """A request queued for retry."""

    id: str
    args: tuple
    kwargs: dict
    queued_at: float
    retry_count: int = 0
    max_retries: int = 3


__all__ = [
    "CircuitBreakerMetrics",
    "QueuedRequest",
]
