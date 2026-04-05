"""
Swarm Intelligence - Message Bus

Inter-agent communication bus with advanced messaging features.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import fnmatch
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import AgentMessage, MessageEnvelope

logger = get_logger(__name__)
ROUTING_RULE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

# Configuration constants
DEFAULT_MAX_DEAD_LETTERS = 10000
DEFAULT_TTL_SECONDS = 300
DEFAULT_MAX_ACKNOWLEDGED_MESSAGES = 10000


class MessageBus:
    """
    Inter-agent communication bus v3.1.

    Enhanced with:
    - Message TTL (time-to-live) with automatic expiration
    - Priority-based message queues
    - Message persistence and replay
    - Dead letter queue for failed deliveries
    - Pattern-based topic subscriptions (wildcards)
    - Message filtering and routing rules

    Supports point-to-point, broadcast, and pub/sub messaging.
    """

    def __init__(
        self,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_dead_letters: int = DEFAULT_MAX_DEAD_LETTERS,
        max_acknowledged_messages: int = DEFAULT_MAX_ACKNOWLEDGED_MESSAGES,
    ):
        # Thread safety lock
        self._lock = asyncio.Lock()

        # Message storage (protected by _lock)
        self._messages: dict[str, list[MessageEnvelope]] = defaultdict(list)
        self._subscribers: dict[str, set[str]] = defaultdict(set)
        self._pattern_subscribers: dict[str, set[str]] = defaultdict(set)  # Wildcard patterns
        self._message_handlers: dict[str, Callable] = {}
        self._persistent_messages: dict[str, list[MessageEnvelope]] = defaultdict(list)
        self._dead_letter_queue: list[MessageEnvelope] = []
        self._acknowledged_messages: OrderedDict[str, datetime] = OrderedDict()
        self._routing_rules: dict[str, list[Callable]] = defaultdict(list)

        # Configuration
        self._default_ttl = default_ttl_seconds
        self._max_dead_letters = max_dead_letters
        self._max_acknowledged_messages = max_acknowledged_messages

    async def send(
        self,
        sender_id: str,
        recipient_id: str,
        message_type: str,
        payload: JSONDict,
        priority: int = 5,
        ttl_seconds: int | None = None,
        persistent: bool = False,
    ) -> str:
        """
        Send a point-to-point message with enhanced metadata.

        Args:
            sender_id: The sender agent ID.
            recipient_id: The recipient agent ID.
            message_type: Type of message.
            payload: Message payload.
            priority: Message priority (lower = higher priority).
            ttl_seconds: Time-to-live in seconds.
            persistent: Whether to persist the message.

        Returns:
            The message ID.
        """
        message = AgentMessage(
            id=str(uuid4()),
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            payload=payload,
        )

        envelope = MessageEnvelope(
            message=message,
            priority=priority,
            ttl_seconds=ttl_seconds or self._default_ttl,
            persistent=persistent,
        )

        # Apply routing rules
        await self._apply_routing_rules(envelope)

        async with self._lock:
            self._messages[recipient_id].append(envelope)

            if persistent:
                self._persistent_messages[recipient_id].append(envelope)
                logger.debug(f"Persisted message {message.id[:8]}... for {recipient_id}")

        logger.debug(
            f"Sent {message_type} message from {sender_id} to {recipient_id} (priority={priority})"
        )
        return message.id

    async def broadcast(
        self,
        sender_id: str,
        message_type: str,
        payload: JSONDict,
        recipients: list[str] | None = None,
        priority: int = 5,
        ttl_seconds: int | None = None,
    ) -> str:
        """
        Broadcast a message to multiple agents with enhanced options.

        Args:
            sender_id: The sender agent ID.
            message_type: Type of message.
            payload: Message payload.
            recipients: Optional list of recipient IDs. If None, stored in broadcast queue.
            priority: Message priority (lower = higher priority).
            ttl_seconds: Time-to-live in seconds.

        Returns:
            The message ID.
        """
        message = AgentMessage(
            id=str(uuid4()),
            sender_id=sender_id,
            recipient_id=None,  # Broadcast
            message_type=message_type,
            payload=payload,
        )

        envelope = MessageEnvelope(
            message=message,
            priority=priority,
            ttl_seconds=ttl_seconds or self._default_ttl,
            persistent=False,
        )

        async with self._lock:
            if recipients:
                for recipient_id in recipients:
                    self._messages[recipient_id].append(envelope)
            else:
                # Store in special broadcast queue
                self._messages["__broadcast__"].append(envelope)

        logger.debug(
            f"Broadcast {message_type} message from {sender_id} to {len(recipients) if recipients else 'all'} agents"
        )
        return message.id

    async def subscribe(self, agent_id: str, topic: str, pattern: bool = False) -> None:
        """
        Subscribe an agent to a topic or pattern.

        Args:
            agent_id: The agent ID to subscribe.
            topic: The topic or pattern to subscribe to.
            pattern: If True, treat topic as a wildcard pattern.
        """
        async with self._lock:
            if pattern:
                self._pattern_subscribers[topic].add(agent_id)
                logger.debug(f"Agent {agent_id} subscribed to pattern: {topic}")
            else:
                self._subscribers[topic].add(agent_id)
                logger.debug(f"Agent {agent_id} subscribed to topic: {topic}")

    async def unsubscribe(self, agent_id: str, topic: str, pattern: bool = False) -> None:
        """
        Unsubscribe an agent from a topic or pattern.

        Args:
            agent_id: The agent ID to unsubscribe.
            topic: The topic or pattern to unsubscribe from.
            pattern: If True, treat topic as a wildcard pattern.
        """
        async with self._lock:
            if pattern:
                self._pattern_subscribers[topic].discard(agent_id)
            else:
                self._subscribers[topic].discard(agent_id)

    async def publish(
        self,
        sender_id: str,
        topic: str,
        payload: JSONDict,
        priority: int = 5,
        ttl_seconds: int | None = None,
    ) -> int:
        """
        Publish a message to topic subscribers with priority.

        Args:
            sender_id: The sender agent ID.
            topic: The topic to publish to.
            payload: Message payload.
            priority: Message priority (lower = higher priority).
            ttl_seconds: Time-to-live in seconds.

        Returns:
            Number of subscribers the message was sent to.
        """
        async with self._lock:
            # Match exact topic subscriptions
            exact_subscribers = self._subscribers.get(topic, set()).copy()

            # Match pattern subscriptions
            pattern_subscribers: set[str] = set()

            for pattern, agents in self._pattern_subscribers.items():
                if fnmatch.fnmatch(topic, pattern):
                    pattern_subscribers.update(agents)

            all_subscribers = exact_subscribers | pattern_subscribers

            if not all_subscribers:
                logger.warning(f"No subscribers for topic: {topic}")
                return 0

            message = AgentMessage(
                id=str(uuid4()),
                sender_id=sender_id,
                recipient_id=None,
                message_type=f"topic:{topic}",
                payload=payload,
            )

            envelope = MessageEnvelope(
                message=message,
                priority=priority,
                ttl_seconds=ttl_seconds or self._default_ttl,
                persistent=False,
            )

            for subscriber_id in all_subscribers:
                self._messages[subscriber_id].append(envelope)

        logger.debug(
            f"Published message to topic '{topic}' ({len(all_subscribers)} subscribers, priority={priority})"
        )
        return len(all_subscribers)

    async def receive(
        self,
        agent_id: str,
        message_type: str | None = None,
        max_messages: int = 100,
        include_expired: bool = False,
    ) -> list[AgentMessage]:
        """Receive messages for an agent with priority sorting and expiration filtering."""
        # Cleanup expired messages first
        await self._cleanup_expired_messages(agent_id)

        envelopes = self._messages.get(agent_id, [])

        # Filter by message type if specified
        if message_type:
            envelopes = [e for e in envelopes if e.message.message_type == message_type]

        # Filter out expired messages unless requested
        if not include_expired:
            envelopes = [e for e in envelopes if not e.is_expired()]

        # Sort by priority (lower number = higher priority)
        envelopes.sort(key=lambda e: e.priority)

        # Mark as delivered
        for envelope in envelopes[:max_messages]:
            envelope.delivered_at = datetime.now(UTC)

        return [e.message for e in envelopes[:max_messages]]

    async def acknowledge(self, message_id: str) -> bool:
        """
        Acknowledge receipt of a message.

        Args:
            message_id: The ID of the message to acknowledge.

        Returns:
            True if the message was found and acknowledged.
        """
        async with self._lock:
            for envelopes in self._messages.values():
                for envelope in envelopes:
                    if envelope.message.id == message_id:
                        envelope.message.acknowledged = True
                        self._acknowledged_messages[message_id] = datetime.now(UTC)
                        self._trim_acknowledged_messages()
                        return True
        return False

    async def replay_persistent_messages(
        self,
        agent_id: str,
        since: datetime | None = None,
    ) -> list[AgentMessage]:
        """Replay persistent messages for an agent."""
        persistent = self._persistent_messages.get(agent_id, [])

        if since:
            persistent = [e for e in persistent if e.created_at >= since]

        return [e.message for e in persistent]

    async def add_routing_rule(self, message_type: str, rule: Callable) -> None:
        """
        Add a custom routing rule for message processing.

        Args:
            message_type: The message type this rule applies to.
            rule: The routing rule callable.
        """
        async with self._lock:
            self._routing_rules[message_type].append(rule)

    async def _apply_routing_rules(self, envelope: MessageEnvelope) -> None:
        """Apply all routing rules for a message type."""
        message_type = envelope.message.message_type
        rules = self._routing_rules.get(message_type, [])

        for rule in rules:
            try:
                await rule(envelope)
            except ROUTING_RULE_ERRORS as e:
                logger.warning(f"Routing rule failed for {message_type}: {e}")

    async def _cleanup_expired_messages(self, agent_id: str) -> int:
        """
        Remove expired messages for an agent.

        Uses immutable list operations to avoid modification during iteration.
        Prunes dead letter queue if it exceeds max size.

        Args:
            agent_id: The agent ID to cleanup messages for.

        Returns:
            Number of expired messages removed.
        """
        async with self._lock:
            envelopes = self._messages.get(agent_id, [])
            expired = [e for e in envelopes if e.is_expired() and not e.persistent]

            if not expired:
                return 0

            # Create new list without expired messages (immutable operation)
            self._messages[agent_id] = [e for e in envelopes if e not in expired]

            # Add unacknowledged messages to dead letter queue
            for envelope in expired:
                if not envelope.message.acknowledged:
                    self._dead_letter_queue.append(envelope)

            # Prune dead letter queue if it exceeds max size
            if len(self._dead_letter_queue) > self._max_dead_letters:
                excess = len(self._dead_letter_queue) - self._max_dead_letters
                self._dead_letter_queue = self._dead_letter_queue[excess:]
                logger.warning(f"Dead letter queue pruned: removed {excess} oldest messages")

        return len(expired)

    async def get_dead_letter_queue(self) -> list[AgentMessage]:
        """Get messages that expired without acknowledgment."""
        return [e.message for e in self._dead_letter_queue]

    async def get_message_stats(self, agent_id: str | None = None) -> JSONDict:
        """Get message statistics for a specific agent or globally."""
        if agent_id:
            envelopes = self._messages.get(agent_id, [])
            return {
                "total_messages": len(envelopes),
                "acknowledged": len([e for e in envelopes if e.message.acknowledged]),
                "expired": len([e for e in envelopes if e.is_expired()]),
                "persistent": len(self._persistent_messages.get(agent_id, [])),
            }
        else:
            total = sum(len(e) for e in self._messages.values())
            return {
                "total_messages": total,
                "acknowledged": len(self._acknowledged_messages),
                "dead_letter_queue": len(self._dead_letter_queue),
                "total_subscribers": sum(len(s) for s in self._subscribers.values()),
                "persistent_messages": sum(len(e) for e in self._persistent_messages.values()),
            }

    def _trim_acknowledged_messages(self) -> None:
        """
        Trim acknowledged messages when exceeding max size.

        Removes oldest entries (FIFO) when the collection exceeds the limit.
        """
        if len(self._acknowledged_messages) > self._max_acknowledged_messages:
            excess = len(self._acknowledged_messages) - self._max_acknowledged_messages
            for _ in range(excess):
                self._acknowledged_messages.popitem(last=False)
            logger.warning(
                f"Acknowledged messages trimmed: removed {excess} oldest entries "
                f"(limit: {self._max_acknowledged_messages})"
            )

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a message type."""
        self._message_handlers[message_type] = handler


__all__ = [
    "MessageBus",
]
