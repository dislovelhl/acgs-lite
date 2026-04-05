"""
ACGS-2 Enhanced Agent Bus API Models
Pydantic models and Enums for the Enhanced Agent Bus API
Constitutional Hash: 608508a9bd224290

This module contains all Pydantic models and Enums extracted from api.py
for better code organization and maintainability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# =============================================================================
# Enums
# =============================================================================


class MessageTypeEnum(str, Enum):
    """Supported message types in the agent bus (12 types per spec)."""

    COMMAND = "command"
    QUERY = "query"
    RESPONSE = "response"
    EVENT = "event"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    GOVERNANCE_REQUEST = "governance_request"
    GOVERNANCE_RESPONSE = "governance_response"
    CONSTITUTIONAL_VALIDATION = "constitutional_validation"
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    AUDIT_LOG = "audit_log"
    CHAT = "chat"
    MESSAGE = "message"
    USER_REQUEST = "user_request"
    GOVERNANCE = "governance"
    CONSTITUTIONAL = "constitutional"
    INFO = "info"
    SECURITY_ALERT = "security_alert"
    AGENT_COMMAND = "agent_command"
    CONSTITUTIONAL_UPDATE = "constitutional_update"


class PriorityEnum(str, Enum):
    """Message priority levels."""

    LOW = "low"
    NORMAL = "normal"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MessageStatusEnum(str, Enum):
    """Message processing status."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


# =============================================================================
# Request/Response Models
# =============================================================================


class MessageRequest(BaseModel):
    """Request model for sending messages to the agent bus."""

    content: str = Field(
        ..., description="Message content", min_length=1, max_length=1048576
    )  # 1MB max
    message_type: MessageTypeEnum = Field(
        default=MessageTypeEnum.COMMAND, description="Type of message (one of 12 supported types)"
    )
    priority: PriorityEnum = Field(default=PriorityEnum.NORMAL, description="Message priority")
    sender: str = Field(..., description="Sender identifier", min_length=1, max_length=255)
    recipient: str | None = Field(default=None, description="Recipient identifier", max_length=255)
    tenant_id: str | None = Field(default=None, description="Tenant identifier", max_length=100)
    metadata: JSONDict | None = Field(default=None, description="Additional metadata")
    session_id: str | None = Field(
        default=None, description="Session identifier for multi-turn conversations"
    )
    idempotency_key: str | None = Field(
        default=None, description="Idempotency key to prevent duplicate processing"
    )

    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace only")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "content": "Analyze these system logs for security anomalies",
                "message_type": "query",
                "priority": "normal",
                "sender": "sec-monitor-01",
                "metadata": {"logs_count": 1250, "priority": "medium"},
            }
        }
    }


class MessageResponse(BaseModel):
    """Response model for message operations."""

    message_id: str = Field(..., description="Unique message identifier")
    status: MessageStatusEnum = Field(..., description="Current message status")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    details: JSONDict | None = Field(default=None, description="Additional response details")
    correlation_id: str | None = Field(default=None, description="Request correlation ID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "message_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "accepted",
                "timestamp": "2024-01-15T10:30:00Z",
                "correlation_id": "req-12345",
            }
        }
    }


class ValidationFinding(BaseModel):
    """A single validation finding."""

    severity: str = Field(..., description="Severity: critical, warning, or recommendation")
    code: str = Field(..., description="Finding code for programmatic handling")
    message: str = Field(..., description="Human-readable description")
    field: str | None = Field(default=None, description="Field that caused the finding")


class ValidationResponse(BaseModel):
    """Detailed validation response."""

    valid: bool = Field(..., description="Whether the request is valid")
    findings: dict[str, list[ValidationFinding]] = Field(
        default_factory=lambda: {  # type: ignore[arg-type]
            "critical": [],
            "warnings": [],
            "recommendations": [],
        },
        description="Categorized validation findings",
    )


class PolicyOverrideRequest(BaseModel):
    """Model for a single policy override."""

    policy_id: str = Field(..., description="Unique override identifier")
    name: str | None = Field(None, description="Human-readable name")
    description: str | None = Field(None, description="Detailed description")
    variables: dict[str, str] = Field(..., description="Variable declarations (name -> type)")
    constraints: list[str] = Field(..., description="Mathematical constraints")


class SessionOverridesRequest(BaseModel):
    """Request to load multiple overrides for a session."""

    overrides: list[PolicyOverrideRequest] = Field(..., description="List of policy overrides")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Overall health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    agent_bus_status: str = Field(..., description="Agent bus component status")
    rate_limiting_enabled: bool = Field(
        default=False, description="Whether rate limiting is active"
    )
    circuit_breaker_enabled: bool = Field(
        default=False, description="Whether circuit breaker is active"
    )


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: JSONDict | None = Field(default=None, description="Additional error details")
    correlation_id: str | None = Field(default=None, description="Request correlation ID")
    timestamp: str = Field(..., description="Error timestamp")


class ServiceUnavailableResponse(BaseModel):
    """Service unavailable response format."""

    status: str = Field(..., description="Service status")
    message: str = Field(..., description="Details on why the service is unavailable")


class ValidationErrorResponse(BaseModel):
    """Validation error response format."""

    valid: bool = Field(default=False)
    findings: dict[str, list[JSONDict]] = Field(default_factory=dict)
    message: str = Field(..., description="Validation failure message")


class StabilityMetricsResponse(BaseModel):
    """Real-time stability metrics from mHC layer."""

    spectral_radius_bound: float = Field(..., description="Spectral radius bound (<= 1.0)")
    divergence: float = Field(..., description="L2 divergence from previous state")
    max_weight: float = Field(..., description="Maximum single weight in aggregation matrix")
    stability_hash: str = Field(..., description="Cryptographic hash of stability state")
    input_norm: float = Field(..., description="L2 norm of input vector")
    output_norm: float = Field(..., description="L2 norm of stabilized output")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# =============================================================================
# Dataclasses for Metrics
# =============================================================================


@dataclass
class LatencyMetrics:
    """Standard latency metrics."""

    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    sample_count: int = 0
    window_size: int = 1000


class LatencyTracker:
    """Mock latency tracker for development."""

    async def get_metrics(self) -> LatencyMetrics:
        return LatencyMetrics()

    async def get_total_messages(self) -> int:
        return 0


# =============================================================================
# Rebuild models to resolve forward references
# =============================================================================

MessageRequest.model_rebuild()
MessageResponse.model_rebuild()
ValidationFinding.model_rebuild()
ValidationResponse.model_rebuild()
HealthResponse.model_rebuild()
ErrorResponse.model_rebuild()
ServiceUnavailableResponse.model_rebuild()
ValidationErrorResponse.model_rebuild()
StabilityMetricsResponse.model_rebuild()
PolicyOverrideRequest.model_rebuild()
SessionOverridesRequest.model_rebuild()
