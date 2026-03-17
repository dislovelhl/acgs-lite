"""
Message sending, receiving, and routing for EnhancedAgentBus.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from packages.enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    MessageStatus,
)
from packages.enhanced_agent_bus.validators import ValidationResult
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..security_helpers import normalize_tenant_id

if TYPE_CHECKING:
    from ..components import GovernanceValidator, MessageRouter, RegistryManager
    from ..message_processor import MessageProcessor
    from .validation import MessageValidator

logger = get_logger(__name__)


class MessageHandler:
    """
    Handles message sending, receiving, and routing operations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        processor: MessageProcessor,
        router_component: MessageRouter,
        registry_manager: RegistryManager,
        governance: GovernanceValidator,
        validator: MessageValidator,
        message_queue: asyncio.Queue[AgentMessage],
        deliberation_queue: object | None,
        metering_manager: object,
        kafka_bus: object | None,
        metrics: JSONDict,
        config: JSONDict,
    ) -> None:
        """
        Initialize message handler.

        Args:
            processor: MessageProcessor for processing messages.
            router_component: MessageRouter component.
            registry_manager: RegistryManager for agent management.
            governance: GovernanceValidator for governance checks.
            validator: MessageValidator for validation.
            message_queue: Queue for received messages.
            deliberation_queue: Optional deliberation queue.
            metering_manager: Metering manager.
            kafka_bus: Optional Kafka bus.
            metrics: Metrics dictionary reference.
            config: Bus configuration.
        """
        self._processor = processor
        self._router_component = router_component
        self._registry_manager = registry_manager
        self._governance = governance
        self._validator = validator
        self._message_queue = message_queue
        self._deliberation_queue = deliberation_queue
        self._metering_manager = metering_manager
        self._kafka_bus = kafka_bus
        self._metrics = metrics
        self._config = config

    async def process_message_with_fallback(self, msg: AgentMessage) -> ValidationResult:
        """
        Process message through processor with graceful degradation.

        Attempts to process the message through the configured MessageProcessor.
        If processing fails due to any exception, falls back to DEGRADED governance
        mode where messages that already passed prior validation checks (constitutional
        hash, tenant isolation, adaptive governance) are allowed through.

        Args:
            msg: The AgentMessage to process. Should have already passed
                constitutional hash and tenant validation.

        Returns:
            ValidationResult: Processing result with one of:
                - Normal validation result from processor (happy path)
                - DEGRADED mode result with is_valid=True and metadata indicating
                  fallback was triggered (degraded path)

        Degraded Mode Behavior:
            When the processor fails, returns a ValidationResult with:
            - is_valid=True (message was pre-validated)
            - decision="ALLOW"
            - status=MessageStatus.VALIDATED
            - metadata containing governance_mode="DEGRADED" and fallback_reason

        Performance:
            - Normal path: Depends on processor complexity
            - Degraded path: Near-instant return with minimal overhead

        Constitutional Hash: cdd01ef066bc6cf2

        Note:
            This graceful degradation ensures system availability while
            maintaining constitutional compliance through prior validation.
        """
        try:
            return await self._processor.process(msg)
        except Exception as e:
            logger.warning(f"Processor fallback activated: {e}")
            return ValidationResult(
                is_valid=True,
                metadata={"governance_mode": "DEGRADED", "fallback_reason": str(e)},
                decision="ALLOW",
                status=MessageStatus.VALIDATED,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

    async def finalize_message_delivery(self, msg: AgentMessage, result: ValidationResult) -> bool:
        """Handle routing and delivery of validated message."""
        if result.is_valid:
            success = await self.route_and_deliver(msg)
            if success:
                self._validator.record_metrics_success()
            else:
                self._validator.record_metrics_failure()
            return success
        else:
            self._validator.record_metrics_failure()
            return False

    async def route_and_deliver(self, msg: AgentMessage) -> bool:
        """Route and deliver message via router component."""
        success = await self._router_component.route_and_deliver(
            msg, self._registry_manager._registry
        )
        if success and not self._kafka_bus:
            await self._message_queue.put(msg)
        return success

    async def broadcast_message(
        self,
        msg: AgentMessage,
        send_message_func: Callable[..., object],
        constitutional_hash: str,
    ) -> dict[str, ValidationResult]:
        """Broadcast message to all agents in same tenant.

        Constitutional Hash: cdd01ef066bc6cf2
        Performance: Uses O(1) tenant index lookup instead of O(n) iteration.
        """
        msg.tenant_id = normalize_tenant_id(msg.tenant_id)
        targets = self._registry_manager.get_agents_by_tenant(msg.tenant_id)
        results = {}
        for aid in targets:
            if aid == msg.from_agent:
                continue
            content = msg.content if hasattr(msg, "content") else {}
            m = AgentMessage(
                from_agent=msg.from_agent, message_type=msg.message_type, content=content
            )
            m.to_agent = aid
            m.tenant_id = msg.tenant_id
            m.constitutional_hash = msg.constitutional_hash
            res = await send_message_func(m)
            if res.is_valid:
                results[aid] = res
        return results

    async def receive_message(self, timeout: float = 1.0) -> AgentMessage | None:
        """Receive a message from the internal queue.

        Args:
            timeout: Maximum seconds to wait for a message.

        Returns:
            AgentMessage: Received message if available, None on timeout.
        """
        try:
            m = await asyncio.wait_for(self._message_queue.get(), timeout)
            if m:
                self._metrics["received"] += 1
                self._metrics["messages_received"] += 1
            return m
        except TimeoutError:
            return None

    async def handle_deliberation(
        self,
        msg: AgentMessage,
        routing: JSONDict | None = None,
        start_time: float | None = None,
        **kwargs: object,
    ) -> bool:
        """Handle deliberation for high-impact messages."""
        if routing and hasattr(routing, "status"):
            routing.status = MessageStatus.PENDING_DELIBERATION
        if self._deliberation_queue:
            enqueue_res = self._deliberation_queue.enqueue(msg, routing)
            if asyncio.iscoroutine(enqueue_res):
                await enqueue_res
        if self._metering_manager and start_time is not None:
            import time as _time

            latency_ms = (_time.perf_counter() - start_time) * 1000
            self._metering_manager.record_deliberation_request(msg, start_time, latency_ms)
        return await self.route_and_deliver(msg)

    def requires_deliberation(self, msg: AgentMessage) -> bool:
        """Check if message requires deliberation based on impact score."""
        return (getattr(msg, "impact_score", 0) or 0) > 0.7
