"""
ACGS-2 Feedback Handler - Handler Module
Constitutional Hash: 608508a9bd224290

Core feedback handler implementation for storing and querying feedback events.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Protocol

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import FeedbackType, OutcomeStatus
from .models import (
    FeedbackBatchRequest,
    FeedbackBatchResponse,
    FeedbackEvent,
    FeedbackResponse,
    FeedbackStats,
    StoredFeedbackEvent,
)
from .schema import FEEDBACK_TABLE_SCHEMA

logger = get_logger(__name__)
# Configuration from environment
POSTGRES_ML_HOST = os.getenv("POSTGRES_ML_HOST", "localhost")
POSTGRES_ML_PORT = int(os.getenv("POSTGRES_ML_PORT", "5432"))
POSTGRES_ML_DB = os.getenv("POSTGRES_ML_DB", "mlflow_db")
POSTGRES_ML_USER = os.getenv("POSTGRES_ML_USER", "mlflow")
POSTGRES_ML_PASSWORD = os.getenv("POSTGRES_ML_PASSWORD", "")


# DBConnection Protocol - represents a database connection
class DBConnection(Protocol):
    """Protocol for database connections."""

    def cursor(self) -> DBCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class DBCursor(Protocol):
    """Protocol for database cursors."""

    rowcount: int

    def __enter__(self) -> DBCursor: ...

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool | None: ...

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...

    def fetchone(self) -> tuple[object, ...] | None: ...


class FeedbackPublisher(Protocol):
    """Protocol for Kafka-like feedback publishers."""

    def publish(self, event: StoredFeedbackEvent) -> None: ...


class FeedbackHandler:
    """
    Handles user feedback collection and storage for governance decisions.

    Provides functionality to:
    - Store feedback events in PostgreSQL
    - Retrieve and query feedback history
    - Calculate feedback statistics
    - Publish events to Kafka (via integration with FeedbackKafkaPublisher)
    """

    def __init__(
        self,
        db_connection: DBConnection | None = None,
        auto_publish_kafka: bool = False,
    ):
        """
        Initialize the feedback handler.

        Args:
            db_connection: Optional database connection (creates new if None)
            auto_publish_kafka: Whether to automatically publish to Kafka on store
        """
        self._db_connection = db_connection
        self._auto_publish_kafka = auto_publish_kafka
        self._kafka_publisher: FeedbackPublisher | None = None
        self._initialized = False
        self._memory_store: list[StoredFeedbackEvent] = []  # Fallback for testing

    def _get_db_connection(self) -> DBConnection | None:
        """Get or create a database connection."""
        if self._db_connection is not None:
            return self._db_connection

        if not POSTGRES_ML_PASSWORD:
            logger.warning(
                "POSTGRES_ML_PASSWORD is not configured; using in-memory storage for feedback handler"
            )
            return None

        try:
            import psycopg2

            self._db_connection = psycopg2.connect(
                host=POSTGRES_ML_HOST,
                port=POSTGRES_ML_PORT,
                database=POSTGRES_ML_DB,
                user=POSTGRES_ML_USER,
                password=POSTGRES_ML_PASSWORD,
            )
            return self._db_connection

        except ImportError:
            logger.warning("psycopg2 not available, using in-memory storage")
            return None
        except (RuntimeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to connect to PostgreSQL: {e}, using in-memory storage")
            return None

    def initialize_schema(self) -> bool:
        """
        Initialize the database schema.

        Returns:
            True if schema was created successfully, False otherwise
        """
        conn = self._get_db_connection()
        if conn is None:
            logger.warning("No database connection, schema initialization skipped")
            self._initialized = True
            return False

        try:
            with conn.cursor() as cursor:
                cursor.execute(FEEDBACK_TABLE_SCHEMA)
            conn.commit()
            self._initialized = True
            logger.info("Feedback database schema initialized successfully")
            return True

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Failed to initialize feedback schema: {e}")
            conn.rollback()
            return False

    def store_feedback(self, event: FeedbackEvent) -> FeedbackResponse:
        """
        Store a feedback event.

        Args:
            event: FeedbackEvent to store

        Returns:
            FeedbackResponse with submission status
        """
        feedback_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC)

        # Create stored event
        stored_event = StoredFeedbackEvent(
            id=feedback_id,
            decision_id=event.decision_id,
            feedback_type=event.feedback_type,
            outcome=event.outcome,
            user_id=event.user_id,
            tenant_id=event.tenant_id,
            comment=event.comment,
            correction_data=event.correction_data,
            features=event.features,
            actual_impact=event.actual_impact,
            metadata=event.metadata,
            created_at=timestamp,
        )

        # Try to store in database
        conn = self._get_db_connection()
        if conn is not None:
            try:
                self._store_to_database(conn, stored_event)
                logger.info(f"Stored feedback {feedback_id} for decision {event.decision_id}")
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(f"Failed to store feedback to database: {e}")
                # Fall back to memory store
                self._memory_store.append(stored_event)
        else:
            # Use memory store
            self._memory_store.append(stored_event)

        # Auto-publish to Kafka if enabled
        if self._auto_publish_kafka and self._kafka_publisher:
            try:
                self._kafka_publisher.publish(stored_event)
                stored_event.published_to_kafka = True
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(f"Failed to publish feedback to Kafka: {e}")

        return FeedbackResponse(
            feedback_id=feedback_id,
            decision_id=event.decision_id,
            status="accepted",
            timestamp=timestamp.isoformat(),
            details={
                "feedback_type": event.feedback_type.value,
                "outcome": event.outcome.value,
            },
        )

    def _store_to_database(self, conn: DBConnection, event: StoredFeedbackEvent) -> None:
        """Store event to PostgreSQL database."""
        query = """
            INSERT INTO feedback_events (
                id, decision_id, feedback_type, outcome, user_id, tenant_id,
                comment, correction_data, features, actual_impact, metadata,
                created_at, processed, published_to_kafka
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        with conn.cursor() as cursor:
            cursor.execute(
                query,
                (
                    event.id,
                    event.decision_id,
                    event.feedback_type.value,
                    event.outcome.value,
                    event.user_id,
                    event.tenant_id,
                    event.comment,
                    json.dumps(event.correction_data) if event.correction_data else None,
                    json.dumps(event.features) if event.features else None,
                    event.actual_impact,
                    json.dumps(event.metadata) if event.metadata else None,
                    event.created_at,
                    event.processed,
                    event.published_to_kafka,
                ),
            )
        conn.commit()

    def store_batch(self, batch: FeedbackBatchRequest) -> FeedbackBatchResponse:
        """
        Store a batch of feedback events.

        Args:
            batch: FeedbackBatchRequest containing events

        Returns:
            FeedbackBatchResponse with results
        """
        accepted: list[str] = []
        errors: list[dict[str, str]] = []

        for event in batch.events:
            try:
                response = self.store_feedback(event)
                accepted.append(response.feedback_id)
            except (RuntimeError, ValueError, TypeError) as e:
                errors.append(
                    {
                        "decision_id": event.decision_id,
                        "error": str(e),
                    }
                )

        return FeedbackBatchResponse(
            total=len(batch.events),
            accepted=len(accepted),
            rejected=len(errors),
            feedback_ids=accepted,
            errors=errors if errors else None,
        )

    def get_feedback(
        self,
        decision_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoredFeedbackEvent]:
        """
        Retrieve feedback events.

        Args:
            decision_id: Optional filter by decision ID
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of StoredFeedbackEvent
        """
        conn = self._get_db_connection()
        if conn is None:
            # Return from memory store
            events = self._memory_store
            if decision_id:
                events = [e for e in events if e.decision_id == decision_id]
            return events[offset : offset + limit]

        try:
            return self._query_database(conn, decision_id, limit, offset)
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Failed to query feedback: {e}")
            return []

    def _query_database(
        self,
        conn: DBConnection,
        decision_id: str | None,
        limit: int,
        offset: int,
    ) -> list[StoredFeedbackEvent]:
        """Query feedback events from database."""
        query = """
            SELECT id, decision_id, feedback_type, outcome, user_id, tenant_id,
                   comment, correction_data, features, actual_impact, metadata,
                   created_at, processed, published_to_kafka
            FROM feedback_events
        """

        params: list[object] = []
        if decision_id:
            query += " WHERE decision_id = %s"
            params.append(decision_id)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        with conn.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row: tuple) -> StoredFeedbackEvent:
        """Convert database row to StoredFeedbackEvent."""
        return StoredFeedbackEvent(
            id=str(row[0]),
            decision_id=row[1],
            feedback_type=FeedbackType(row[2]),
            outcome=OutcomeStatus(row[3]),
            user_id=row[4],
            tenant_id=row[5],
            comment=row[6],
            correction_data=row[7],
            features=row[8],
            actual_impact=row[9],
            metadata=row[10],
            created_at=row[11],
            processed=row[12],
            published_to_kafka=row[13],
        )

    def get_feedback_stats(
        self,
        tenant_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> FeedbackStats:
        """
        Get feedback statistics.

        Args:
            tenant_id: Optional filter by tenant
            start_date: Optional start of period
            end_date: Optional end of period

        Returns:
            FeedbackStats with aggregated statistics
        """
        conn = self._get_db_connection()

        if conn is None:
            # Calculate from memory store
            return self._calculate_memory_stats(tenant_id, start_date, end_date)

        try:
            return self._calculate_db_stats(conn, tenant_id, start_date, end_date)
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Failed to calculate stats: {e}")
            return FeedbackStats()

    def _calculate_memory_stats(
        self,
        tenant_id: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> FeedbackStats:
        """Calculate stats from memory store."""
        events = self._memory_store

        # Apply filters
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if start_date:
            events = [e for e in events if e.created_at >= start_date]
        if end_date:
            events = [e for e in events if e.created_at <= end_date]

        if not events:
            return FeedbackStats(period_start=start_date, period_end=end_date)

        positive = sum(1 for e in events if e.feedback_type == FeedbackType.POSITIVE)
        negative = sum(1 for e in events if e.feedback_type == FeedbackType.NEGATIVE)
        neutral = sum(1 for e in events if e.feedback_type == FeedbackType.NEUTRAL)
        correction = sum(1 for e in events if e.feedback_type == FeedbackType.CORRECTION)
        success = sum(1 for e in events if e.outcome == OutcomeStatus.SUCCESS)

        impacts = [e.actual_impact for e in events if e.actual_impact is not None]
        avg_impact = sum(impacts) / len(impacts) if impacts else None

        return FeedbackStats(
            total_count=len(events),
            positive_count=positive,
            negative_count=negative,
            neutral_count=neutral,
            correction_count=correction,
            success_rate=success / len(events) if events else 0.0,
            average_impact=avg_impact,
            period_start=start_date,
            period_end=end_date,
        )

    def _calculate_db_stats(
        self,
        conn: DBConnection,
        tenant_id: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> FeedbackStats:
        """Calculate stats from database."""
        query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN feedback_type = 'positive' THEN 1 ELSE 0 END) as positive,
                SUM(CASE WHEN feedback_type = 'negative' THEN 1 ELSE 0 END) as negative,
                SUM(CASE WHEN feedback_type = 'neutral' THEN 1 ELSE 0 END) as neutral,
                SUM(CASE WHEN feedback_type = 'correction' THEN 1 ELSE 0 END) as correction,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as success_count,
                AVG(actual_impact) as avg_impact
            FROM feedback_events
            WHERE 1=1
        """

        params: list[object] = []
        if tenant_id:
            query += " AND tenant_id = %s"
            params.append(tenant_id)
        if start_date:
            query += " AND created_at >= %s"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= %s"
            params.append(end_date)

        with conn.cursor() as cursor:
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()

        if not row or row[0] == 0:
            return FeedbackStats(period_start=start_date, period_end=end_date)

        return FeedbackStats(
            total_count=row[0],
            positive_count=row[1],
            negative_count=row[2],
            neutral_count=row[3],
            correction_count=row[4],
            success_rate=row[5] / row[0] if row[0] > 0 else 0.0,
            average_impact=float(row[6]) if row[6] is not None else None,
            period_start=start_date,
            period_end=end_date,
        )

    def mark_as_processed(self, feedback_ids: list[str]) -> int:
        """
        Mark feedback events as processed.

        Args:
            feedback_ids: List of feedback IDs to mark

        Returns:
            Number of events marked
        """
        if not feedback_ids:
            return 0

        conn = self._get_db_connection()
        if conn is None:
            # Update memory store
            count = 0
            for event in self._memory_store:
                if event.id in feedback_ids:
                    event.processed = True
                    count += 1
            return count

        try:
            query = """
                UPDATE feedback_events
                SET processed = TRUE
                WHERE id = ANY(%s)
            """
            with conn.cursor() as cursor:
                cursor.execute(query, (feedback_ids,))
                count = cursor.rowcount
            conn.commit()
            return count

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Failed to mark feedback as processed: {e}")
            conn.rollback()
            return 0

    def get_unprocessed_feedback(self, limit: int = 100) -> list[StoredFeedbackEvent]:
        """
        Get unprocessed feedback events for training.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of unprocessed StoredFeedbackEvent
        """
        conn = self._get_db_connection()
        if conn is None:
            return [e for e in self._memory_store if not e.processed][:limit]

        try:
            query = """
                SELECT id, decision_id, feedback_type, outcome, user_id, tenant_id,
                       comment, correction_data, features, actual_impact, metadata,
                       created_at, processed, published_to_kafka
                FROM feedback_events
                WHERE processed = FALSE
                ORDER BY created_at ASC
                LIMIT %s
            """
            with conn.cursor() as cursor:
                cursor.execute(query, (limit,))
                rows = cursor.fetchall()

            return [self._row_to_event(row) for row in rows]

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Failed to get unprocessed feedback: {e}")
            return []

    def set_kafka_publisher(self, publisher: object) -> None:
        """
        Set the Kafka publisher for feedback events.

        Args:
            publisher: Kafka publisher instance with publish(event) method
        """
        self._kafka_publisher = publisher
        logger.info("Kafka publisher configured for feedback handler")

    @property
    def _publisher(self) -> FeedbackPublisher | None:
        """Alias for _kafka_publisher for backward compatibility."""
        return self._kafka_publisher

    @_publisher.setter
    def _publisher(self, value: FeedbackPublisher | None) -> None:
        """Alias setter for _kafka_publisher."""
        self._kafka_publisher = value

    @_publisher.deleter
    def _publisher(self) -> None:
        """Alias deleter for _kafka_publisher."""
        self._kafka_publisher = None

    def close(self) -> None:
        """Close database connection and clean up resources."""
        if self._db_connection is not None:
            try:
                self._db_connection.close()
                logger.info("Feedback handler database connection closed")
            except (RuntimeError, ValueError, TypeError) as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
                self._db_connection = None


# Module-level convenience functions

_feedback_handler: FeedbackHandler | None = None


def get_feedback_handler() -> FeedbackHandler:
    """
    Get the global feedback handler instance.

    Returns:
        Initialized FeedbackHandler
    """
    global _feedback_handler

    if _feedback_handler is None:
        _feedback_handler = FeedbackHandler()

    return _feedback_handler


def submit_feedback(event: FeedbackEvent | JSONDict) -> FeedbackResponse:
    """
    Submit a feedback event using the global handler.

    Args:
        event: FeedbackEvent or dict with event data

    Returns:
        FeedbackResponse with submission status
    """
    handler = get_feedback_handler()

    if isinstance(event, dict):
        event = FeedbackEvent(**event)

    return handler.store_feedback(event)


def get_feedback_for_decision(decision_id: str) -> list[StoredFeedbackEvent]:
    """
    Get all feedback for a specific decision.

    Args:
        decision_id: The decision ID to query

    Returns:
        List of StoredFeedbackEvent for the decision
    """
    handler = get_feedback_handler()
    return handler.get_feedback(decision_id=decision_id)


__all__ = [
    "POSTGRES_ML_DB",
    # Configuration
    "POSTGRES_ML_HOST",
    "POSTGRES_ML_PASSWORD",
    "POSTGRES_ML_PORT",
    "POSTGRES_ML_USER",
    # Protocol
    "DBConnection",
    # Handler Class
    "FeedbackHandler",
    "get_feedback_for_decision",
    # Convenience Functions
    "get_feedback_handler",
    "submit_feedback",
]
