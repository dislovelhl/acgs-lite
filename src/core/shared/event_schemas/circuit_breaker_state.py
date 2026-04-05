"""
ACGS-2 Circuit Breaker State Event Schemas
Constitutional Hash: 608508a9bd224290

Versioned schemas for circuit breaker state change events.
Records state transitions for fault tolerance monitoring and analysis.

Version History:
- V1 (1.0.0): Circuit breaker state change with metrics and recovery info
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import Field

from src.core.shared.schema_registry import (
    EventSchemaBase,
    SchemaCompatibility,
    SchemaStatus,
    SchemaVersion,
    get_schema_registry,
)
from src.core.shared.types import JSONDict

# =============================================================================
# Enums
# =============================================================================


class CircuitStateEnum(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit tripped, failing fast
    HALF_OPEN = "half_open"  # Testing recovery


class FallbackStrategyEnum(StrEnum):
    """Fallback strategies when circuit is open."""

    FAIL_CLOSED = "fail_closed"
    CACHED_VALUE = "cached_value"
    QUEUE_FOR_RETRY = "queue_for_retry"
    BYPASS = "bypass"
    DEFAULT_VALUE = "default_value"


class ServiceSeverityEnum(StrEnum):
    """Service criticality levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StateChangeReason(StrEnum):
    """Reason for state change."""

    FAILURE_THRESHOLD_REACHED = "failure_threshold_reached"
    TIMEOUT_EXPIRED = "timeout_expired"
    HALF_OPEN_SUCCESS = "half_open_success"
    HALF_OPEN_FAILURE = "half_open_failure"
    MANUAL_RESET = "manual_reset"
    MANUAL_OPEN = "manual_open"
    HEALTH_CHECK_FAILURE = "health_check_failure"
    HEALTH_CHECK_SUCCESS = "health_check_success"


# =============================================================================
# V1: Circuit Breaker State (1.0.0)
# =============================================================================


class CircuitBreakerStateV1(EventSchemaBase):
    """
    Circuit Breaker State Schema V1 - Records circuit breaker state changes.

    Constitutional Hash: 608508a9bd224290

    Captures state transitions with:
    - Previous and current state
    - Reason for transition
    - Service metrics and health
    - Recovery information
    - Fallback execution details
    """

    SCHEMA_NAME: ClassVar[str] = "CircuitBreakerState"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

    # Service identification
    service_name: str = Field(..., description="Name of the protected service")
    service_id: str | None = Field(
        default=None,
        description="Unique identifier for the service instance",
    )
    service_severity: ServiceSeverityEnum = Field(
        default=ServiceSeverityEnum.MEDIUM,
        description="Criticality level of the service",
    )

    # State transition
    previous_state: CircuitStateEnum = Field(
        ...,
        description="Previous circuit state",
    )
    current_state: CircuitStateEnum = Field(
        ...,
        description="Current circuit state",
    )
    change_reason: StateChangeReason = Field(
        ...,
        description="Reason for state change",
    )

    # Configuration
    failure_threshold: int = Field(
        default=5,
        description="Number of failures before opening",
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="Timeout before transitioning to half-open",
    )
    half_open_requests: int = Field(
        default=3,
        description="Requests allowed in half-open state",
    )
    fallback_strategy: FallbackStrategyEnum = Field(
        default=FallbackStrategyEnum.FAIL_CLOSED,
        description="Fallback strategy when circuit is open",
    )

    # Current metrics
    consecutive_failures: int = Field(
        default=0,
        description="Current consecutive failure count",
    )
    consecutive_successes: int = Field(
        default=0,
        description="Current consecutive success count",
    )
    total_calls: int = Field(
        default=0,
        description="Total calls through the circuit breaker",
    )
    successful_calls: int = Field(
        default=0,
        description="Total successful calls",
    )
    failed_calls: int = Field(
        default=0,
        description="Total failed calls",
    )
    rejected_calls: int = Field(
        default=0,
        description="Total rejected calls (when open)",
    )

    # Timing
    last_failure_time: datetime | None = Field(
        default=None,
        description="Timestamp of last failure",
    )
    last_success_time: datetime | None = Field(
        default=None,
        description="Timestamp of last success",
    )
    time_in_previous_state_ms: float | None = Field(
        default=None,
        description="Duration in previous state in milliseconds",
    )
    opened_at: datetime | None = Field(
        default=None,
        description="Timestamp when circuit opened",
    )
    will_try_half_open_at: datetime | None = Field(
        default=None,
        description="Timestamp when half-open will be attempted",
    )

    # Failure details
    last_failure_type: str | None = Field(
        default=None,
        description="Type of the last failure (exception class name)",
    )
    last_failure_message: str | None = Field(
        default=None,
        description="Message from the last failure",
    )
    recent_failures: list[JSONDict] = Field(
        default_factory=list,
        description="Recent failure details (last N failures)",
    )

    # Fallback information
    fallback_used_count: int = Field(
        default=0,
        description="Number of times fallback was used",
    )
    queue_size: int = Field(
        default=0,
        description="Current retry queue size (for QUEUE_FOR_RETRY)",
    )
    cached_fallback_available: bool = Field(
        default=False,
        description="Whether cached fallback value is available",
    )
    cached_fallback_age_seconds: float | None = Field(
        default=None,
        description="Age of cached fallback value in seconds",
    )

    # Recovery tracking
    recovery_attempts: int = Field(
        default=0,
        description="Number of recovery attempts (half-open cycles)",
    )
    last_recovery_attempt: datetime | None = Field(
        default=None,
        description="Timestamp of last recovery attempt",
    )
    successful_recoveries: int = Field(
        default=0,
        description="Number of successful recoveries",
    )

    # Health indicators
    error_rate_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Current error rate percentage",
    )
    avg_response_time_ms: float | None = Field(
        default=None,
        description="Average response time in milliseconds",
    )
    p99_response_time_ms: float | None = Field(
        default=None,
        description="P99 response time in milliseconds",
    )

    # Context
    tenant_id: str = Field(
        default="default",
        description="Tenant identifier",
    )
    environment: str = Field(
        default="production",
        description="Environment (production, staging, development)",
    )
    region: str | None = Field(
        default=None,
        description="Deployment region",
    )
    instance_id: str | None = Field(
        default=None,
        description="Instance identifier",
    )

    # Alert information
    alert_triggered: bool = Field(
        default=False,
        description="Whether an alert was triggered",
    )
    alert_id: str | None = Field(
        default=None,
        description="ID of triggered alert",
    )
    alert_severity: str | None = Field(
        default=None,
        description="Severity of triggered alert",
    )

    # Correlation
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for tracing",
    )
    triggering_request_id: str | None = Field(
        default=None,
        description="ID of request that triggered the state change",
    )

    model_config: ClassVar[dict[str, Any]] = {"from_attributes": True}

    @property
    def is_healthy(self) -> bool:
        """Check if circuit breaker is in healthy state."""
        return self.current_state == CircuitStateEnum.CLOSED

    @property
    def is_degraded(self) -> bool:
        """Check if circuit breaker is in degraded state."""
        return self.current_state == CircuitStateEnum.HALF_OPEN

    @property
    def is_failing(self) -> bool:
        """Check if circuit breaker is in failing state."""
        return self.current_state == CircuitStateEnum.OPEN


# =============================================================================
# Registration
# =============================================================================


def register_circuit_breaker_state_schemas() -> None:
    """Register all CircuitBreakerState schema versions with the registry."""
    registry = get_schema_registry()

    # Register V1
    registry.register(
        CircuitBreakerStateV1,
        status=SchemaStatus.ACTIVE,
        compatibility_mode=SchemaCompatibility.BACKWARD,
        description="Circuit breaker state change event with metrics and recovery tracking",
    )


__all__ = [
    "CircuitBreakerStateV1",
    "CircuitStateEnum",
    "FallbackStrategyEnum",
    "ServiceSeverityEnum",
    "StateChangeReason",
    "register_circuit_breaker_state_schemas",
]
