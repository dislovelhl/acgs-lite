"""
ACGS-2 Deliberation Layer - Vote Event Consumer
Constitutional Hash: 608508a9bd224290

Kafka consumer for processing vote events with exactly-once semantics.
Consumes vote events from Kafka, deduplicates, and updates Redis elections.
"""

import asyncio
import json
from datetime import UTC, datetime, timezone

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from aiokafka import AIOKafkaConsumer

    KAFKA_AVAILABLE = True
except ImportError:
    AIOKafkaConsumer = None
    KAFKA_AVAILABLE = False

try:
    from .redis_election_store import get_election_store
    from .voting_service import VotingService, VotingStrategy
except ImportError:
    get_election_store = None  # type: ignore[misc, assignment]
    VotingService = None  # type: ignore[misc, assignment]
    VotingStrategy = None  # type: ignore[misc, assignment]

try:
    from .vote_models import VoteDecision, VoteEvent
except ImportError:
    VoteEvent = None  # type: ignore[misc, assignment]
    VoteDecision = None  # type: ignore[misc, assignment]

try:
    from enhanced_agent_bus._compat.config import settings
except ImportError:
    from enhanced_agent_bus._compat.config import settings  # type: ignore[import-untyped]

logger = get_logger(__name__)
_VOTE_CONSUMER_OPERATION_ERRORS = (
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


class VoteEventConsumer:
    """
    Kafka consumer for vote events with exactly-once processing semantics.

    Processes vote events from Kafka vote topic, deduplicates by agent_id,
    updates Redis elections, checks resolution, and publishes audit records.
    """

    def __init__(
        self,
        tenant_id: str = "default",
        bootstrap_servers: str | None = None,
        voting_service: object | None = None,
    ):
        """
        Initialize vote event consumer.

        Args:
            tenant_id: Tenant identifier for topic isolation
            bootstrap_servers: Kafka bootstrap servers (defaults to settings.kafka.bootstrap_servers)
            voting_service: VotingService instance (creates new one if not provided)
        """
        self.tenant_id = tenant_id.replace(".", "_") if tenant_id else "default"
        self.bootstrap_servers = bootstrap_servers or settings.kafka.get(
            "bootstrap_servers", "localhost:9092"
        )
        self.voting_service = voting_service or VotingService()
        self.consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._vote_topic = settings.voting.vote_topic_pattern.format(tenant_id=self.tenant_id)

    async def start(self) -> bool:
        """Start the vote event consumer."""
        if not KAFKA_AVAILABLE:
            logger.warning("aiokafka not available, VoteEventConsumer cannot start")
            return False

        try:
            self.consumer = AIOKafkaConsumer(
                self._vote_topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=f"acgs-voting-group-{self.tenant_id}",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                enable_auto_commit=False,  # Manual commit for exactly-once semantics
                isolation_level="read_committed",  # Only read committed messages
                security_protocol=settings.kafka.get("security_protocol", "PLAINTEXT"),
            )

            await self.consumer.start()
            self._running = True
            logger.info(
                f"VoteEventConsumer started for tenant {self.tenant_id}, topic {self._vote_topic}"
            )

            # Start consume loop in background
            self._consume_task = asyncio.create_task(self._consume_loop())
            return True
        except _VOTE_CONSUMER_OPERATION_ERRORS as e:
            logger.error(f"Failed to start VoteEventConsumer: {e}")
            return False

    async def stop(self) -> None:
        """Stop the vote event consumer."""
        self._running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info("VoteEventConsumer stopped")

    async def _consume_loop(self) -> None:
        """Main consume loop for processing vote events."""
        if not self.consumer:
            return

        try:
            async for msg in self.consumer:
                if not self._running:
                    break

                try:
                    vote_event = msg.value
                    await self._handle_vote_event(vote_event)
                    # Manual commit after successful processing
                    await self.consumer.commit()
                except _VOTE_CONSUMER_OPERATION_ERRORS as e:
                    logger.error(f"Error processing vote event: {e}")
                    # Don't commit - message will be reprocessed
        except _VOTE_CONSUMER_OPERATION_ERRORS as e:
            logger.error(f"Error in consume loop: {e}")
        finally:
            if self.consumer:
                await self.consumer.stop()

    async def _handle_vote_event(self, vote_event: JSONDict) -> None:
        """
        Handle a vote event from Kafka.

        Process flow:
        1. Load election from Redis
        2. Deduplicate by agent_id
        3. Add vote to election
        4. Check resolution
        5. Update Redis
        6. Publish audit record (if kafka_bus available)
        """
        election_id = vote_event.get("election_id")
        agent_id = vote_event.get("agent_id")
        decision = vote_event.get("decision")

        if not election_id or not agent_id or not decision:
            logger.error(f"Invalid vote event: missing required fields {vote_event}")
            return

        # Load election from Redis
        election_store = await get_election_store()
        if not election_store:
            logger.error("Election store not available")
            return

        election_data = await election_store.get_election(election_id)
        if not election_data:
            logger.warning(f"Election {election_id} not found for vote event")
            return

        # Deduplicate: check if agent already voted
        existing_votes = election_data.get("votes", {})
        if agent_id in existing_votes:
            return

        # Convert vote_event to Vote dataclass
        from .voting_service import Vote

        vote = Vote(
            agent_id=agent_id,
            decision=decision,
            reason=vote_event.get("reasoning"),
            timestamp=(
                datetime.fromisoformat(vote_event["timestamp"].replace("Z", "+00:00"))
                if isinstance(vote_event.get("timestamp"), str)
                else vote_event.get("timestamp", datetime.now(UTC))
            ),
        )

        # Add vote via VotingService (which will update Redis and check resolution)
        success = await self.voting_service.cast_vote(election_id, vote)
        if not success:
            logger.warning(f"Failed to cast vote for election {election_id}")
            return

        logger.info(f"Processed vote event: {agent_id} -> {decision} for election {election_id}")

        # Publish audit record (if kafka_bus available)
        if hasattr(self.voting_service, "kafka_bus") and self.voting_service.kafka_bus:
            await self._publish_audit_record(election_id, vote_event, election_data)

    async def _publish_audit_record(
        self, election_id: str, vote_event: JSONDict, election_data: JSONDict
    ) -> None:
        """Publish audit record for vote event."""
        try:
            from .audit_signature import sign_audit_record
            from .vote_models import VoteEventType

            tenant_id = election_data.get("tenant_id", self.tenant_id)

            audit_payload = {
                "vote_event": vote_event,
                "election_id": election_id,
                "processed_at": datetime.now(UTC).isoformat(),
            }

            # Sign audit record
            signature_key = settings.voting.audit_signature_key
            if signature_key:
                signature = sign_audit_record(audit_payload, signature_key.get_secret_value())
            else:
                logger.warning("AUDIT_SIGNATURE_KEY not configured, audit record not signed")
                signature = ""

            audit_record = {
                "event_type": VoteEventType.VOTE_CAST.value,
                "election_id": election_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "signature": signature,
                "payload": audit_payload,
                "agent_id": vote_event.get("agent_id"),
            }

            await self.voting_service.kafka_bus.publish_audit_record(tenant_id, audit_record)
        except _VOTE_CONSUMER_OPERATION_ERRORS as e:
            logger.error(f"Failed to publish audit record: {e}")
