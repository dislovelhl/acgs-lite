"""
ACGS-2 Kafka Event Bus Implementation
Constitutional Hash: 608508a9bd224290
Provides high-throughput, multi-tenant isolated messaging.
"""

import asyncio
import json
import ssl
from collections.abc import Callable

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

try:
    from enhanced_agent_bus.exceptions import MessageDeliveryError

    from .models import AgentMessage, MessageType
except ImportError:
    from .exceptions import (
        MessageDeliveryError,  # type: ignore[import-untyped]
    )
    from .models import (  # type: ignore[import-untyped]
        AgentMessage,
        MessageType,
    )

try:
    from enhanced_agent_bus._compat.config import settings
except ImportError:
    from enhanced_agent_bus._compat.config import settings  # type: ignore[import-untyped]

logger = get_logger(__name__)
_KAFKA_BUS_OPERATION_ERRORS = (
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


class KafkaEventBus:
    """
    Kafka-based event bus for high-performance multi-agent orchestration.
    Supports topic-level multi-tenant isolation.
    """

    def __init__(self, bootstrap_servers: str = "localhost:9092", client_id: str = "acgs2-bus"):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.producer: AIOKafkaProducer | None = None
        self._consumers: dict[str, AIOKafkaConsumer] = {}
        self._running = False
        self._ssl_context: ssl.SSLContext | None = self._create_ssl_context()
        self._background_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the Kafka producer."""
        if not KAFKA_AVAILABLE:
            logger.error("aiokafka not installed. KafkaEventBus unavailable.")
            return

        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            client_id=self.client_id,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            acks="all",  # Ensure durability for production
            enable_idempotence=True,  # Prevent duplicate votes
            retry_backoff_ms=500,
            security_protocol=settings.kafka.get("security_protocol", "PLAINTEXT"),
            ssl_context=self._ssl_context,
        )
        await self.producer.start()
        self._running = True
        logger.info(f"KafkaEventBus started on {self.bootstrap_servers}")

    async def stop(self) -> None:
        """Stop the Kafka producer and all consumers."""
        self._running = False
        if self.producer:
            await self.producer.flush()  # Ensure all messages are sent
            await self.producer.stop()
        for consumer in self._consumers.values():
            await consumer.stop()
        logger.info("KafkaEventBus stopped")

    def _create_ssl_context(self) -> ssl.SSLContext | None:
        """Create SSL context for Kafka if security protocol is SSL."""
        security_protocol = settings.kafka.get("security_protocol", "PLAINTEXT")
        if security_protocol != "SSL":
            return None

        context = ssl.create_default_context(cafile=settings.kafka.get("ssl_ca_location"))

        cert_file = settings.kafka.get("ssl_certificate_location")
        key_file = settings.kafka.get("ssl_key_location")
        password = settings.kafka.get("ssl_password")

        if cert_file and key_file:
            context.load_cert_chain(certfile=cert_file, keyfile=key_file, password=password)

        return context

    def _get_topic_name(self, tenant_id: str, message_type: str) -> str:
        """
        Generate a multi-tenant isolated topic name.
        Format: acgs.tenant.{tenant_id}.{message_type}
        """
        safe_tenant = tenant_id.replace(".", "_") if tenant_id else "default"
        return f"acgs.tenant.{safe_tenant}.{message_type.lower()}"

    def _get_vote_topic(self, tenant_id: str) -> str:
        """
        Get vote topic name for a tenant.
        Format: acgs.tenant.{tenant_id}.votes
        """
        safe_tenant = tenant_id.replace(".", "_") if tenant_id else "default"
        pattern = settings.voting.vote_topic_pattern
        return str(pattern.format(tenant_id=safe_tenant))

    def _get_audit_topic(self, tenant_id: str) -> str:
        """
        Get audit topic name for a tenant.
        Format: acgs.tenant.{tenant_id}.audit.votes
        """
        safe_tenant = tenant_id.replace(".", "_") if tenant_id else "default"
        pattern = settings.voting.audit_topic_pattern
        return str(pattern.format(tenant_id=safe_tenant))

    async def send_message(self, message: AgentMessage) -> bool:
        """Send a message to the appropriate Kafka topic."""
        if not self.producer or not self._running:
            raise MessageDeliveryError(
                message_id=message.message_id,
                target_agent=message.to_agent or "unknown",
                reason="Kafka producer not started",
            )

        topic = self._get_topic_name(message.tenant_id, message.message_type.name)

        # Use conversation_id as partition key to ensure ordering within a session
        key = message.conversation_id.encode("utf-8") if message.conversation_id else None

        try:
            # Re-convert to dict ensuring all fields are present
            msg_dict = message.to_dict_raw()

            await self.producer.send_and_wait(topic, value=msg_dict, key=key)

            return True
        except _KAFKA_BUS_OPERATION_ERRORS as e:
            logger.error(
                f"Failed to send message to Kafka (topic={topic}): {self._sanitize_error(e)}"
            )
            return False

    async def subscribe(
        self, tenant_id: str, message_types: list[MessageType], handler: Callable
    ) -> None:
        """Subscribe to topics and process messages."""
        if not KAFKA_AVAILABLE:
            return

        topics = [self._get_topic_name(tenant_id, mt.name) for mt in message_types]
        consumer_id = f"{tenant_id}-{''.join([mt.name for mt in message_types])}"

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=f"{self.client_id}-group-{tenant_id}",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            security_protocol=settings.kafka.get("security_protocol", "PLAINTEXT"),
            ssl_context=self._ssl_context,
        )

        self._consumers[consumer_id] = consumer
        await consumer.start()

        async def consume_loop() -> None:
            try:
                async for msg in consumer:
                    if not self._running:
                        break
                    try:
                        # Reconstruct AgentMessage
                        message_data = msg.value
                        # In a real implementation, we'd have a from_dict method
                        # For now, we'll assume the handler can take the dict or we wrap it
                        await handler(message_data)
                    except _KAFKA_BUS_OPERATION_ERRORS as e:
                        logger.error(f"Error in Kafka message handler: {self._sanitize_error(e)}")
            finally:
                await consumer.stop()

        task = asyncio.create_task(consume_loop())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        logger.info(f"Subscribed to topics: {topics}")

    def _sanitize_error(self, error: Exception) -> str:
        """Strip sensitive metadata from error messages (VULN-008)."""
        from enhanced_agent_bus._compat.security.error_sanitizer import sanitize_error

        return str(sanitize_error(error))

    async def publish_vote_event(self, tenant_id: str, vote_event: JSONDict) -> bool:
        """
        Publish a vote event to Kafka vote topic with guaranteed delivery.

        Args:
            tenant_id: Tenant identifier for topic isolation
            vote_event: VoteEvent dictionary (must include election_id)

        Returns:
            True if published successfully, False otherwise
        """
        if not self.producer or not self._running:
            logger.error("Kafka producer not started, cannot publish vote event")
            return False

        topic = self._get_vote_topic(tenant_id)
        election_id = vote_event.get("election_id", "")

        # Use election_id as partition key to ensure all votes for one election
        # go to the same partition (maintains ordering)
        key = election_id.encode("utf-8") if election_id else None

        try:
            await self.producer.send_and_wait(topic, value=vote_event, key=key)

            return True
        except _KAFKA_BUS_OPERATION_ERRORS as e:
            logger.error(
                f"Failed to publish vote event to Kafka (topic={topic}): {self._sanitize_error(e)}"
            )
            return False

    async def publish_audit_record(self, tenant_id: str, audit_record: JSONDict) -> bool:
        """
        Publish an audit record to Kafka audit topic (compacted).

        Args:
            tenant_id: Tenant identifier for topic isolation
            audit_record: AuditRecord dictionary with signature

        Returns:
            True if published successfully, False otherwise
        """
        if not self.producer or not self._running:
            logger.error("Kafka producer not started, cannot publish audit record")
            return False

        topic = self._get_audit_topic(tenant_id)
        election_id = audit_record.get("election_id", "")

        # Use election_id as partition key for audit records too
        key = election_id.encode("utf-8") if election_id else None

        try:
            await self.producer.send_and_wait(topic, value=audit_record, key=key)

            return True
        except _KAFKA_BUS_OPERATION_ERRORS as e:
            logger.error(
                f"Failed to publish audit record to Kafka (topic={topic}): {self._sanitize_error(e)}"
            )
            return False


class Orchestrator:
    """Base class for Orchestrator-Worker pattern."""

    def __init__(self, bus: KafkaEventBus, tenant_id: str):
        self.bus = bus
        self.tenant_id = tenant_id

    async def dispatch_task(self, task_data: JSONDict, worker_type: str) -> None:
        """Dispatch a task to a specific worker type."""
        message = AgentMessage(
            message_type=MessageType.TASK_REQUEST,
            content=task_data,
            tenant_id=self.tenant_id,
            to_agent=f"worker-{worker_type}",
        )
        await self.bus.send_message(message)


class Blackboard:
    """Implementation of the Blackboard pattern using Kafka Compacted Topics."""

    def __init__(self, bus: KafkaEventBus, tenant_id: str, board_name: str):
        self.bus = bus
        self.tenant_id = tenant_id
        self.topic = f"acgs.blackboard.{tenant_id}.{board_name}"
        self.state: JSONDict = {}

    async def update(self, key: str, value: object) -> None:
        """Update a value on the blackboard."""
        message = AgentMessage(
            message_type=MessageType.EVENT,
            content={"key": key, "value": value},
            tenant_id=self.tenant_id,
            payload={"blackboard_update": True},
        )
        # In a real implementation, we'd use a specific Kafka key for compaction
        await self.bus.send_message(message)
