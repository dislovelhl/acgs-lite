"""
Kafka consumer for ACGS-2 Online Learning feedback.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .adapter import RIVER_AVAILABLE
from .config import (
    KAFKA_AUTO_OFFSET_RESET,
    KAFKA_BOOTSTRAP,
    KAFKA_CONSUMER_GROUP,
    KAFKA_MAX_POLL_RECORDS,
    KAFKA_TOPIC_FEEDBACK,
)
from .models import ConsumerStats
from .pipeline import OnlineLearningPipeline

# Optional Kafka support
try:
    from aiokafka import AIOKafkaConsumer

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    AIOKafkaConsumer = None

logger = get_logger(__name__)
_CONSUMER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
)


class FeedbackKafkaConsumer:
    """
    Kafka consumer for feedback events to feed the online learning pipeline.
    """

    def __init__(
        self,
        pipeline: OnlineLearningPipeline | None = None,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
        group_id: str | None = None,
        auto_offset_reset: str = KAFKA_AUTO_OFFSET_RESET,
        max_poll_records: int = KAFKA_MAX_POLL_RECORDS,
        on_message_callback: Callable[[JSONDict], None] | None = None,
    ):
        self.bootstrap_servers = bootstrap_servers or KAFKA_BOOTSTRAP
        self.topic = topic or KAFKA_TOPIC_FEEDBACK
        self.group_id = group_id or KAFKA_CONSUMER_GROUP
        self.auto_offset_reset = auto_offset_reset
        self.max_poll_records = max_poll_records
        self.on_message_callback = on_message_callback

        self._pipeline = pipeline
        self._consumer: object | None = None
        self._running = False
        self._consume_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

        # Statistics tracking
        self._stats = ConsumerStats()

    def _check_dependencies(self) -> bool:
        if not KAFKA_AVAILABLE:
            logger.error(
                "aiokafka not installed. FeedbackKafkaConsumer unavailable. "
                "Install with: pip install aiokafka"
            )
            return False

        if not RIVER_AVAILABLE:
            logger.error(
                "River not installed. FeedbackKafkaConsumer requires River for online learning. "
                "Install with: pip install river"
            )
            return False

        return True

    async def start(self) -> bool:
        if not self._check_dependencies():
            return False

        async with self._lock:
            if self._running:
                return True

            try:
                # Initialize pipeline if not provided (factory call)
                if self._pipeline is None:
                    from .service import get_online_learning_pipeline

                    self._pipeline = get_online_learning_pipeline()

                # Create consumer
                self._consumer = AIOKafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.bootstrap_servers,
                    group_id=self.group_id,
                    auto_offset_reset=self.auto_offset_reset,
                    max_poll_records=self.max_poll_records,
                    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                    key_deserializer=lambda k: k.decode("utf-8") if k else None,
                    enable_auto_commit=True,
                    auto_commit_interval_ms=5000,
                )

                await self._consumer.start()
                self._running = True
                self._stats.status = "running"

                # Start consume loop in background
                self._consume_task = asyncio.create_task(self._consume_loop())

                logger.info(
                    f"FeedbackKafkaConsumer started: "
                    f"servers={self._sanitize_bootstrap(self.bootstrap_servers)}, "
                    f"topic={self.topic}, group_id={self.group_id}"
                )
                return True

            except _CONSUMER_OPERATION_ERRORS as e:
                logger.error(f"Failed to start FeedbackKafkaConsumer: {self._sanitize_error(e)}")
                self._consumer = None
                self._stats.status = "error"
                return False

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                return

            self._running = False
            self._stats.status = "stopping"

            if self._consume_task:
                self._consume_task.cancel()
                try:
                    await self._consume_task
                except asyncio.CancelledError:
                    pass
                self._consume_task = None

            if self._consumer:
                try:
                    await self._consumer.stop()
                    logger.info("FeedbackKafkaConsumer stopped")
                except _CONSUMER_OPERATION_ERRORS as e:
                    logger.warning(
                        f"Error stopping FeedbackKafkaConsumer: {self._sanitize_error(e)}"
                    )
                finally:
                    self._consumer = None

            self._stats.status = "stopped"

    async def _consume_loop(self) -> None:
        logger.info(f"Starting consume loop for topic {self.topic}")

        try:
            async for msg in self._consumer:
                if not self._running:
                    break

                try:
                    await self._process_message(msg)
                except _CONSUMER_OPERATION_ERRORS as e:
                    logger.error(f"Error processing message: {self._sanitize_error(e)}")
                    self._stats.messages_failed += 1

        except asyncio.CancelledError:
            logger.info("Consume loop cancelled")
            raise
        except _CONSUMER_OPERATION_ERRORS as e:
            logger.error(f"Consume loop error: {self._sanitize_error(e)}")
            self._stats.status = "error"

    async def _process_message(self, msg: object) -> None:
        self._stats.messages_received += 1
        self._stats.last_offset = msg.offset
        self._stats.last_message_at = datetime.now(UTC)

        try:
            event_data = msg.value
            if self.on_message_callback:
                self.on_message_callback(event_data)

            features = event_data.get("features")
            outcome = self._extract_outcome(event_data)
            decision_id = event_data.get("decision_id")

            if features and outcome is not None:
                result = self._pipeline.learn_from_feedback(
                    features=features,
                    outcome=outcome,
                    decision_id=decision_id,
                )

                if result.success:
                    self._stats.samples_learned += 1
                else:
                    logger.warning(
                        f"Failed to learn from feedback for decision {decision_id}: "
                        f"{result.error_message}"
                    )

            self._stats.messages_processed += 1

        except _CONSUMER_OPERATION_ERRORS as e:
            logger.error(f"Error processing feedback message: {self._sanitize_error(e)}")
            self._stats.messages_failed += 1
            raise

    def _extract_outcome(self, event_data: JSONDict) -> float | int | None:
        actual_impact = event_data.get("actual_impact")
        if actual_impact is not None:
            return float(actual_impact)

        outcome = event_data.get("outcome")
        if outcome:
            outcome_map = {
                "success": 1,
                "failure": 0,
                "partial": 0.5,
                "unknown": None,
            }
            return outcome_map.get(outcome)

        feedback_type = event_data.get("feedback_type")
        if feedback_type:
            feedback_map = {
                "positive": 1,
                "negative": 0,
                "neutral": 0.5,
                "correction": None,
            }
            return feedback_map.get(feedback_type)

        return None

    def _sanitize_error(self, error: Exception) -> str:
        error_msg = str(error)
        error_msg = re.sub(r"bootstrap_servers='[^']+'", "bootstrap_servers='REDACTED'", error_msg)
        error_msg = re.sub(r"password='[^']+'", "password='REDACTED'", error_msg)
        return error_msg

    def _sanitize_bootstrap(self, servers: str) -> str:
        parts = servers.split(",")
        sanitized = []
        for part in parts:
            host = part.split(":")[0] if ":" in part else part
            sanitized.append(f"{host}:****")
        return ",".join(sanitized)

    def get_stats(self) -> ConsumerStats:
        if self._pipeline:
            pipeline_stats = self._pipeline.get_stats()
            if isinstance(pipeline_stats, dict):
                ls = pipeline_stats.get("learning_stats", {})
                if isinstance(ls, dict):
                    self._stats.samples_learned = ls.get("samples_learned", 0)
                else:
                    self._stats.samples_learned = getattr(ls, "samples_learned", 0)
            else:
                self._stats.samples_learned = pipeline_stats.learning_stats.samples_learned

        return self._stats

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def pipeline(self) -> OnlineLearningPipeline | None:
        return self._pipeline
