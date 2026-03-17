"""
ACGS-2 Feedback Handler - Enums Module
Constitutional Hash: cdd01ef066bc6cf2

Enumerations for feedback types and outcome statuses.
"""

from enum import Enum


class FeedbackType(str, Enum):  # noqa: UP042
    """Type of feedback provided by user."""

    POSITIVE = "positive"  # Thumbs up - decision was correct
    NEGATIVE = "negative"  # Thumbs down - decision was incorrect
    NEUTRAL = "neutral"  # No opinion
    CORRECTION = "correction"  # User provides explicit correction


class OutcomeStatus(str, Enum):  # noqa: UP042
    """Status of the governance decision outcome."""

    SUCCESS = "success"  # Decision led to successful outcome
    FAILURE = "failure"  # Decision led to failed outcome
    PARTIAL = "partial"  # Decision led to partial success
    UNKNOWN = "unknown"  # Outcome not yet determined


__all__ = [
    "FeedbackType",
    "OutcomeStatus",
]
