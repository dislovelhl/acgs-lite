"""
ACGS-2 Feedback Handler - Models Module
Constitutional Hash: 608508a9bd224290

Pydantic models and dataclasses for feedback events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import FeedbackType, OutcomeStatus

logger = get_logger(__name__)
# Pydantic Models for API Validation


class FeedbackEvent(BaseModel):
    """
    User feedback event for a governance decision.

    Captures user feedback (thumbs up/down, outcome confirmation) on governance
    decisions made by the model. Used for continuous learning and model improvement.
    """

    decision_id: str = Field(
        ...,
        description="Unique identifier of the governance decision being rated",
        min_length=1,
        max_length=255,
    )

    feedback_type: FeedbackType = Field(
        ...,
        description="type of feedback: positive, negative, neutral, or correction",
    )

    outcome: OutcomeStatus = Field(
        default=OutcomeStatus.UNKNOWN,
        description="Outcome status of the decision: success, failure, partial, or unknown",
    )

    user_id: str | None = Field(
        default=None,
        description="Identifier of the user providing feedback",
        max_length=255,
    )

    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier for multi-tenant deployments",
        max_length=255,
    )

    comment: str | None = Field(
        default=None,
        description="Optional user comment explaining the feedback",
        max_length=2000,
    )

    correction_data: JSONDict | None = Field(
        default=None,
        description="Explicit correction data if feedback_type is 'correction'",
    )

    features: JSONDict | None = Field(
        default=None,
        description="Feature values at the time of the decision for training",
    )

    actual_impact: float | None = Field(
        default=None,
        description="Actual impact score observed (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )

    metadata: JSONDict | None = Field(
        default=None,
        description="Additional metadata for the feedback event",
    )

    @field_validator("decision_id")
    @classmethod
    def validate_decision_id(cls, v: str) -> str:
        """Validate decision_id is not empty and has no leading/trailing whitespace."""
        if not v or not v.strip():
            raise ValueError("decision_id cannot be empty or whitespace only")
        return v.strip()

    @model_validator(mode="after")
    def validate_correction_data(self) -> FeedbackEvent:
        """Validate correction_data is provided when feedback_type is correction."""
        if self.feedback_type == FeedbackType.CORRECTION and not self.correction_data:
            logger.warning(
                f"feedback_type is 'correction' but no correction_data provided "
                f"for decision_id={self.decision_id}"
            )
        return self


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    feedback_id: str = Field(..., description="Unique identifier for the feedback event")
    decision_id: str = Field(..., description="The decision ID the feedback was for")
    status: str = Field(..., description="Status of the feedback submission")
    timestamp: str = Field(..., description="ISO timestamp of when feedback was received")
    details: JSONDict | None = Field(default=None, description="Additional response details")


class FeedbackBatchRequest(BaseModel):
    """Request model for batch feedback submission."""

    events: list[FeedbackEvent] = Field(
        ...,
        description="list of feedback events to submit",
        min_length=1,
        max_length=100,
    )


class FeedbackBatchResponse(BaseModel):
    """Response model for batch feedback submission."""

    total: int = Field(..., description="Total number of events submitted")
    accepted: int = Field(..., description="Number of events successfully processed")
    rejected: int = Field(..., description="Number of events that failed processing")
    feedback_ids: list[str] = Field(..., description="IDs of accepted feedback events")
    errors: list[dict[str, str]] | None = Field(
        default=None, description="Details of rejected events"
    )


class FeedbackQueryParams(BaseModel):
    """Query parameters for feedback retrieval."""

    decision_id: str | None = Field(default=None, description="Filter by decision ID")
    user_id: str | None = Field(default=None, description="Filter by user ID")
    tenant_id: str | None = Field(default=None, description="Filter by tenant ID")
    feedback_type: FeedbackType | None = Field(default=None, description="Filter by feedback type")
    outcome: OutcomeStatus | None = Field(default=None, description="Filter by outcome status")
    start_date: datetime | None = Field(default=None, description="Filter by start date")
    end_date: datetime | None = Field(default=None, description="Filter by end date")
    limit: int = Field(default=100, description="Maximum number of results", ge=1, le=1000)
    offset: int = Field(default=0, description="Number of results to skip", ge=0)


# Internal Data Classes


@dataclass
class StoredFeedbackEvent:
    """Internal representation of a stored feedback event."""

    id: str
    decision_id: str
    feedback_type: FeedbackType
    outcome: OutcomeStatus
    user_id: str | None
    tenant_id: str | None
    comment: str | None
    correction_data: JSONDict | None
    features: JSONDict | None
    actual_impact: float | None
    metadata: JSONDict | None
    created_at: datetime
    processed: bool = False
    published_to_kafka: bool = False


@dataclass
class FeedbackStats:
    """Statistics for feedback events."""

    total_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    correction_count: int = 0
    success_rate: float = 0.0
    average_impact: float | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None


__all__ = [
    "FeedbackBatchRequest",
    "FeedbackBatchResponse",
    # Pydantic Models
    "FeedbackEvent",
    "FeedbackQueryParams",
    "FeedbackResponse",
    "FeedbackStats",
    # Data Classes
    "StoredFeedbackEvent",
]
