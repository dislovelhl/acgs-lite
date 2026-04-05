"""
ACGS-2 Feedback Handler Package
Constitutional Hash: 608508a9bd224290

Modular feedback collection and storage for governance decision quality.
Supports feedback persistence to PostgreSQL and event publishing to Kafka.

This package provides:
- FeedbackEvent model for capturing user feedback
- FeedbackHandler for storing and querying feedback
- FeedbackKafkaPublisher for streaming events to downstream systems
"""

# Enums
from .enums import FeedbackType, OutcomeStatus

# Handler
from .handler import (
    DBConnection,
    FeedbackHandler,
    get_feedback_for_decision,
    get_feedback_handler,
    submit_feedback,
)

# Kafka Publisher
from .kafka_publisher import (
    KAFKA_AVAILABLE,
    FeedbackKafkaPublisher,
    get_feedback_kafka_publisher,
    publish_feedback_event,
)

# Models (Pydantic and dataclasses)
from .models import (
    FeedbackBatchRequest,
    FeedbackBatchResponse,
    FeedbackEvent,
    FeedbackQueryParams,
    FeedbackResponse,
    FeedbackStats,
    StoredFeedbackEvent,
)

# Schema
from .schema import FEEDBACK_TABLE_SCHEMA

__all__ = [
    # Schema
    "FEEDBACK_TABLE_SCHEMA",
    "KAFKA_AVAILABLE",
    # Protocol
    "DBConnection",
    "FeedbackBatchRequest",
    "FeedbackBatchResponse",
    # Pydantic Models
    "FeedbackEvent",
    # Handler Class
    "FeedbackHandler",
    # Kafka Publisher
    "FeedbackKafkaPublisher",
    "FeedbackQueryParams",
    "FeedbackResponse",
    "FeedbackStats",
    # Enums
    "FeedbackType",
    "OutcomeStatus",
    # Data Classes
    "StoredFeedbackEvent",
    "get_feedback_for_decision",
    # Convenience Functions
    "get_feedback_handler",
    "get_feedback_kafka_publisher",
    "publish_feedback_event",
    "submit_feedback",
]
