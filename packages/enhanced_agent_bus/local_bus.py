"""
ACGS-2 Local Event Bus Implementation (Lite)
Constitutional Hash: 608508a9bd224290
Provides in-memory isolated messaging for local/Lite deployments using asyncio.Queue.
"""

import asyncio
from collections import defaultdict
from collections.abc import Callable

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from enhanced_agent_bus.exceptions import MessageDeliveryError

    from .models import AgentMessage, MessageType
except ImportError:
    from .exceptions import MessageDeliveryError  # type: ignore[import-untyped]
    from .models import AgentMessage, MessageType  # type: ignore[import-untyped]

logger = get_logger(__name__)


class LocalEventBus:
    """
    In-memory event bus replacement for Kafka.
    Uses asyncio.Queues organized by tenant and message type.
    """

    def __init__(self):
        # tenant_id -> message_type -> list[asyncio.Queue]
        self._queues: dict[str, dict[str, list[asyncio.Queue]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._running = False
        self._background_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the local bus."""
        self._running = True
        logger.info("[Lite] LocalEventBus initialized")

    async def stop(self) -> None:
        """Stop the local bus and clear queues."""
        self._running = False
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        self._queues.clear()
        logger.info("[Lite] LocalEventBus stopped")

    def _get_topic_key(self, tenant_id: str, message_type: str) -> str:
        return f"{tenant_id}:{message_type.lower()}"

    async def send_message(self, message: AgentMessage) -> bool:
        """Dispatch a message to all local subscribers for the tenant/type."""
        if not self._running:
            raise MessageDeliveryError(
                message_id=message.message_id,
                target_agent=message.to_agent or "unknown",
                reason="Local bus not started",
            )

        msg_dict = message.to_dict_raw()
        tenant_id = message.tenant_id or "default"
        msg_type_name = message.message_type.name

        # Route to specific tenant subscribers AND global 'all' subscribers
        subscribers = self._queues[tenant_id][msg_type_name] + self._queues["all"][msg_type_name]

        if not subscribers:
            logger.debug(f"[Lite] No local subscribers for {tenant_id}/{msg_type_name}")
            return True

        for q in subscribers:
            await q.put(msg_dict)

        return True

    async def subscribe(
        self,
        tenant_id: str | Callable,
        message_types: list[MessageType] | None = None,
        handler: Callable | None = None,
    ) -> None:
        """Register a handler for specific message types or all messages."""
        # Handle single argument call: subscribe(handler)
        if callable(tenant_id) and message_types is None and handler is None:
            handler = tenant_id
            tenant_id = "all"
            message_types = [MessageType.COMMAND, MessageType.EVENT, MessageType.TASK_REQUEST]

        target_tenant = tenant_id if isinstance(tenant_id, str) else "all"

        for mt in message_types or []:
            q: asyncio.Queue = asyncio.Queue()
            self._queues[target_tenant][mt.name].append(q)

            # Spawn a dedicated consumer task for this subscription
            task = asyncio.create_task(self._consume_queue(q, handler))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        logger.info(f"[Lite] Subscribed to {message_types} for tenant {target_tenant}")

    async def _consume_queue(self, q: asyncio.Queue, handler: Callable) -> None:
        """Internal loop to pump messages from queue to handler."""
        while True:
            try:
                msg_data = await q.get()
            except asyncio.CancelledError:
                break
            try:
                await handler(msg_data)
            except Exception as e:
                logger.error(f"[Lite] Error in local message handler: {e}")
            finally:
                q.task_done()

    async def publish_vote_event(self, tenant_id: str, vote_event: JSONDict) -> bool:
        """Mimic Kafka vote publishing."""
        # For Lite, we treat votes as standard events
        tenant_id = tenant_id or "default"
        subscribers = self._queues[tenant_id]["EVENT"]
        for q in subscribers:
            await q.put(vote_event)
        return True

    async def publish_audit_record(self, tenant_id: str, audit_record: JSONDict) -> bool:
        """Mimic Kafka audit publishing."""
        tenant_id = tenant_id or "default"
        # In Lite mode, we may want a dedicated 'audit' internal topic
        subscribers = self._queues[tenant_id]["AUDIT"]  # Custom type for Lite
        for q in subscribers:
            await q.put(audit_record)
        return True


__all__ = ["LocalEventBus"]
