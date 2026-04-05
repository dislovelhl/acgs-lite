"""
Message Router Component.

Constitutional Hash: 608508a9bd224290
MACI Role: EXECUTIVE (message routing and delivery)
"""

import asyncio
from collections.abc import Callable

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import AgentMessage
from enhanced_agent_bus.observability.structured_logging import get_logger

from ..interfaces import MessageRouter as MessageRouterInterface
from ..registry import DirectMessageRouter

logger = get_logger(__name__)
MESSAGE_DELIVERY_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)


class MessageRouter:
    """
    Handles physical message routing and delivery.
    Extracts routing logic from EnhancedAgentBus.
    """

    def __init__(
        self,
        config: JSONDict,
        router_backend: MessageRouterInterface | None = None,
        kafka_bus: object | None = None,
        callbacks: dict[str, Callable] | None = None,
    ):
        self.config = config
        self._router = router_backend or DirectMessageRouter()
        self._kafka_bus = kafka_bus
        self._callbacks = callbacks or {}

    async def initialize(self) -> None:
        """Initialize router resources (Kafka, etc)."""
        if self.config.get("use_kafka") is True and self._kafka_bus:
            if hasattr(self._kafka_bus, "start"):
                await self._kafka_bus.start()

    async def shutdown(self) -> None:
        """Shutdown router resources."""
        if self._kafka_bus:
            if hasattr(self._kafka_bus, "stop"):
                await self._kafka_bus.stop()

    async def route_and_deliver(self, msg: AgentMessage, registry: object) -> bool:
        """
        Route and deliver message.
        """
        # Logical routing (updating message routing info based on registry)
        await self._router.route(msg, registry)

        # Physical delivery
        success = False
        try:
            success = await self._deliver(msg)
        except MESSAGE_DELIVERY_ERRORS as e:
            logger.error(f"Message delivery failed: {e}")
            success = False

        # Callbacks for metrics
        if success:
            if "on_success" in self._callbacks:
                self._callbacks["on_success"]()
        else:
            if "on_failure" in self._callbacks:
                self._callbacks["on_failure"]()

        return success

    async def _deliver(self, msg: AgentMessage) -> bool:
        """Internal delivery logic."""
        if self._kafka_bus:
            if hasattr(self._kafka_bus, "send_message"):
                res = self._kafka_bus.send_message(msg)
                if asyncio.iscoroutine(res):
                    res = await res
                return bool(res)

        return True
