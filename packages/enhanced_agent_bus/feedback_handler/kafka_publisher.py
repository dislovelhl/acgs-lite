"""
ACGS-2 Feedback Handler - Kafka Publisher Module
Constitutional Hash: 608508a9bd224290

Kafka publisher for streaming feedback events to downstream systems.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import StoredFeedbackEvent

logger = get_logger(__name__)
# Optional Kafka support
try:
    from aiokafka import AIOKafkaProducer

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# Configuration from environment
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC_FEEDBACK = os.getenv("KAFKA_TOPIC_FEEDBACK", "governance.feedback.v1")


class FeedbackKafkaPublisher:
    """
    Kafka publisher for feedback events.

    Publishes feedback events to the governance.feedback.v1 topic for
    downstream processing by ML training pipelines and analytics systems.
    """

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
        client_id: str = "acgs2-feedback-publisher",
    ):
        """
        Initialize the Kafka publisher for feedback events.

        Args:
            bootstrap_servers: Kafka bootstrap servers (defaults to KAFKA_BOOTSTRAP env var)
            topic: Kafka topic to publish to (defaults to KAFKA_TOPIC_FEEDBACK env var)
            client_id: Client identifier for Kafka connection
        """
        self.bootstrap_servers = bootstrap_servers or KAFKA_BOOTSTRAP
        self.topic = topic or KAFKA_TOPIC_FEEDBACK
        self.client_id = client_id
        self._producer: object | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task] = set()

    async def start(self) -> bool:
        """
        Start the Kafka producer.

        Returns:
            True if producer started successfully, False otherwise
        """
        if not KAFKA_AVAILABLE:
            logger.error(
                "aiokafka not installed. FeedbackKafkaPublisher unavailable. "
                "Install with: pip install aiokafka"
            )
            return False

        async with self._lock:
            if self._running:
                return True

            try:
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    client_id=self.client_id,
                    value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    acks="all",  # Ensure durability
                    retry_backoff_ms=500,
                )
                await self._producer.start()
                self._running = True
                logger.info(
                    f"FeedbackKafkaPublisher started: servers={self._sanitize_bootstrap(self.bootstrap_servers)}, "
                    f"topic={self.topic}"
                )
                return True

            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(f"Failed to start FeedbackKafkaPublisher: {self._sanitize_error(e)}")
                self._producer = None
                return False

    async def stop(self) -> None:
        """Stop the Kafka producer and clean up resources."""
        async with self._lock:
            if not self._running:
                return

            self._running = False
            if self._producer:
                try:
                    await self._producer.flush()
                    await self._producer.stop()
                    logger.info("FeedbackKafkaPublisher stopped")
                except (RuntimeError, ValueError, TypeError) as e:
                    logger.warning(
                        f"Error stopping FeedbackKafkaPublisher: {self._sanitize_error(e)}"
                    )
                finally:
                    self._producer = None

    async def publish(self, event: StoredFeedbackEvent) -> bool:
        """
        Publish a feedback event to Kafka.

        Args:
            event: The StoredFeedbackEvent to publish

        Returns:
            True if published successfully, False otherwise
        """
        if not self._running or not self._producer:
            logger.warning("FeedbackKafkaPublisher not running, cannot publish event")
            return False

        try:
            # Convert event to dict for serialization
            event_dict = self._serialize_event(event)

            # Use decision_id as partition key to ensure ordering per decision
            key = event.decision_id

            await self._producer.send_and_wait(
                self.topic,
                value=event_dict,
                key=key,
            )

            logger.debug(
                f"Published feedback event {event.id} for decision {event.decision_id} "
                f"to topic {self.topic}"
            )
            return True

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Failed to publish feedback event {event.id}: {self._sanitize_error(e)}")
            return False

    async def publish_batch(self, events: list[StoredFeedbackEvent]) -> dict[str, bool]:
        """
        Publish multiple feedback events to Kafka.

        Args:
            events: List of StoredFeedbackEvent to publish

        Returns:
            Dict mapping event IDs to publish success status
        """
        results: dict[str, bool] = {}

        for event in events:
            success = await self.publish(event)
            results[event.id] = success

        return results

    def _serialize_event(self, event: StoredFeedbackEvent) -> JSONDict:
        """
        Serialize a StoredFeedbackEvent to a dictionary for Kafka.

        Args:
            event: The event to serialize

        Returns:
            Dict representation of the event
        """
        # Convert dataclass to dict
        event_dict = {
            "id": event.id,
            "decision_id": event.decision_id,
            "feedback_type": (
                event.feedback_type.value
                if isinstance(event.feedback_type, Enum)
                else event.feedback_type
            ),
            "outcome": event.outcome.value if isinstance(event.outcome, Enum) else event.outcome,
            "user_id": event.user_id,
            "tenant_id": event.tenant_id,
            "comment": event.comment,
            "correction_data": event.correction_data,
            "features": event.features,
            "actual_impact": event.actual_impact,
            "metadata": event.metadata,
            "created_at": (
                event.created_at.isoformat()
                if isinstance(event.created_at, datetime)
                else event.created_at
            ),
            "processed": event.processed,
            "published_to_kafka": True,  # Mark as published
            "schema_version": "v1",  # Add schema version for future compatibility
        }

        return event_dict

    def _sanitize_error(self, error: Exception) -> str:
        """Strip sensitive metadata from error messages."""
        error_msg = str(error)
        # Remove potential bootstrap server details if they contain secrets
        error_msg = re.sub(r"bootstrap_servers='[^']+'", "bootstrap_servers='REDACTED'", error_msg)
        error_msg = re.sub(r"password='[^']+'", "password='REDACTED'", error_msg)
        return error_msg

    def _sanitize_bootstrap(self, servers: str) -> str:
        """Sanitize bootstrap servers for logging (show host, hide port details)."""
        # Only show host names, not detailed connection info
        parts = servers.split(",")
        sanitized = []
        for part in parts:
            host = part.split(":")[0] if ":" in part else part
            sanitized.append(f"{host}:****")
        return ",".join(sanitized)

    @property
    def is_running(self) -> bool:
        """Check if the publisher is running."""
        return self._running

    def publish_sync(self, event: StoredFeedbackEvent) -> bool:
        """
        Synchronous wrapper to publish a feedback event.

        This method is intended for use in synchronous code paths.
        It creates an event loop if necessary.

        Args:
            event: The StoredFeedbackEvent to publish

        Returns:
            True if published successfully, False otherwise
        """
        try:
            asyncio.get_running_loop()
            task = asyncio.create_task(self.publish(event))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return False  # Can't wait for result in running loop
        except RuntimeError:
            # No running event loop in this thread, execute synchronously.
            return asyncio.run(self.publish(event))


# Module-level Kafka publisher instance
_feedback_kafka_publisher: FeedbackKafkaPublisher | None = None


async def get_feedback_kafka_publisher() -> FeedbackKafkaPublisher:
    """
    Get or create the global FeedbackKafkaPublisher instance.

    Returns:
        Initialized FeedbackKafkaPublisher
    """
    global _feedback_kafka_publisher

    if _feedback_kafka_publisher is None:
        _feedback_kafka_publisher = FeedbackKafkaPublisher()
        await _feedback_kafka_publisher.start()

    return _feedback_kafka_publisher


async def publish_feedback_event(event: StoredFeedbackEvent) -> bool:
    """
    Publish a feedback event using the global publisher.

    Args:
        event: StoredFeedbackEvent to publish

    Returns:
        True if published successfully, False otherwise
    """
    publisher = await get_feedback_kafka_publisher()
    return await publisher.publish(event)


__all__ = [
    "KAFKA_AVAILABLE",
    # Configuration
    "KAFKA_BOOTSTRAP",
    "KAFKA_TOPIC_FEEDBACK",
    # Kafka Publisher
    "FeedbackKafkaPublisher",
    # Convenience Functions
    "get_feedback_kafka_publisher",
    "publish_feedback_event",
]
