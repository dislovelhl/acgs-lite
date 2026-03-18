"""
ACGS-2 Enhanced Agent Bus - Usage Metering Integration
Constitutional Hash: cdd01ef066bc6cf2

Non-blocking async metering integration for production billing.
Designed to maintain P99 latency < 1.31ms by using fire-and-forget patterns.
"""

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import TypeVar

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import metering service with fallback
try:
    import importlib

    from src.core.shared.constants import CONSTITUTIONAL_HASH as _DEFAULT_HASH

    _models = importlib.import_module("src.core.services.metering.app.models")
    CONSTITUTIONAL_HASH = getattr(_models, "CONSTITUTIONAL_HASH", _DEFAULT_HASH)
    MeterableOperation = _models.MeterableOperation
    MeteringTier = _models.MeteringTier
    UsageEvent = _models.UsageEvent
    UsageMeteringService = importlib.import_module(
    "src.core.services.metering.app.service"
    ).UsageMeteringService

    METERING_AVAILABLE = True
except ImportError:
    try:
        import os
        import sys

        # Add services path for direct imports
        services_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "services", "metering"
        )
        if services_path not in sys.path:
            sys.path.insert(0, services_path)
        from app.models import (  # type: ignore[no-redef]
            CONSTITUTIONAL_HASH,
            MeterableOperation,
            MeteringTier,
            UsageEvent,
        )
        from app.service import UsageMeteringService  # type: ignore[no-redef]

        METERING_AVAILABLE = True  # type: ignore[no-redef]
    except ImportError:
        METERING_AVAILABLE = False  # type: ignore[no-redef]
        MeterableOperation: object | None = None  # type: ignore[no-redef]
        MeteringTier: object | None = None  # type: ignore[no-redef]
        UsageEvent: object | None = None  # type: ignore[no-redef]
        UsageMeteringService: object | None = None  # type: ignore[no-redef]
        from src.core.shared.constants import CONSTITUTIONAL_HASH  # type: ignore[no-redef]

# Import models for type checking
try:
    from .models import AgentMessage, MessageType
    from .validators import ValidationResult
except ImportError:
    try:
        from models import AgentMessage, MessageType  # type: ignore[no-redef]
        from validators import ValidationResult  # type: ignore[no-redef]
    except ImportError:
        AgentMessage: object | None = None  # type: ignore[no-redef]
        MessageType: object | None = None  # type: ignore[no-redef]
        ValidationResult: object | None = None  # type: ignore[no-redef]

logger = get_logger(__name__)
# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., object])
METERING_FLUSH_ERRORS = (RuntimeError, ConnectionError, TimeoutError, OSError, ValueError)
METERING_RECORD_ERRORS = (RuntimeError, ConnectionError, TimeoutError, OSError, ValueError)


class MeteringConfig:
    """Configuration for metering integration."""

    def __init__(
        self,
        enabled: bool = True,
        redis_url: str | None = None,
        aggregation_interval_seconds: int = 60,
        max_queue_size: int = 10000,
        batch_size: int = 100,
        flush_interval_seconds: float = 1.0,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.enabled = enabled and METERING_AVAILABLE
        self.redis_url = redis_url
        self.aggregation_interval_seconds = aggregation_interval_seconds
        self.max_queue_size = max_queue_size
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_seconds
        self.constitutional_hash = constitutional_hash


class AsyncMeteringQueue:
    """
    Non-blocking async queue for metering events.

    Uses fire-and-forget pattern to ensure zero impact on P99 latency.
    Events are batched and flushed periodically to the metering service.
    """

    def __init__(
        self, config: MeteringConfig, metering_service: "UsageMeteringService" | None = None
    ):
        self.config = config
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=config.max_queue_size)
        self._metering_service = metering_service
        self._running = False
        self._flush_task: asyncio.Task | None = None
        self._events_queued = 0
        self._events_flushed = 0
        self._events_dropped = 0

    async def start(self) -> None:
        """Start the async queue processor."""
        if not self.config.enabled:
            logger.info("Metering integration disabled")
            return

        if self._running:
            return

        self._running = True

        # Initialize metering service if not provided
        if self._metering_service is None and METERING_AVAILABLE:
            self._metering_service = UsageMeteringService(
                redis_url=self.config.redis_url,
                aggregation_interval_seconds=self.config.aggregation_interval_seconds,
                constitutional_hash=self.config.constitutional_hash,
            )
            await self._metering_service.start()

        # Start background flush task
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(
            f"AsyncMeteringQueue started (constitutional_hash: {self.config.constitutional_hash})"
        )

    async def stop(self) -> None:
        """Stop the queue and flush remaining events."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:  # noqa: SIM105
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_batch()

        if self._metering_service:
            await self._metering_service.stop()

        logger.info(
            f"AsyncMeteringQueue stopped - queued: {self._events_queued}, "
            f"flushed: {self._events_flushed}, dropped: {self._events_dropped}"
        )

    def enqueue_nowait(
        self,
        tenant_id: str,
        operation: "MeterableOperation",
        tier: "MeteringTier" = None,
        agent_id: str | None = None,
        tokens_processed: int = 0,
        latency_ms: float = 0.0,
        compliance_score: float = 1.0,
        metadata: JSONDict | None = None,
    ) -> bool:
        """
        Enqueue a metering event without blocking.

        Returns True if event was queued, False if queue is full.
        This method NEVER blocks or raises exceptions to ensure
        zero impact on the critical path.
        """
        if not self.config.enabled or not METERING_AVAILABLE:
            return False

        if tier is None:
            tier = MeteringTier.STANDARD

        event_data = {
            "tenant_id": tenant_id,
            "operation": operation,
            "tier": tier,
            "agent_id": agent_id,
            "tokens_processed": tokens_processed,
            "latency_ms": latency_ms,
            "compliance_score": compliance_score,
            "metadata": metadata or {},
            "timestamp": datetime.now(UTC),
        }

        try:
            self._queue.put_nowait(event_data)
            self._events_queued += 1
            return True
        except asyncio.QueueFull:
            self._events_dropped += 1
            logger.warning("Metering queue full - dropping event")
            return False

    async def _flush_loop(self) -> None:
        """Background loop to flush events to metering service."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds)
                await self._flush_batch()
            except asyncio.CancelledError:
                break
            except METERING_FLUSH_ERRORS as e:
                logger.error(f"Metering flush error: {e}")

    async def _flush_batch(self) -> None:
        """Flush a batch of events to the metering service."""
        if not self._metering_service or self._queue.empty():
            return

        batch = []
        try:
            for _ in range(self.config.batch_size):
                if self._queue.empty():
                    break
                batch.append(self._queue.get_nowait())
        except asyncio.QueueEmpty:
            pass

        if not batch:
            return

        # Record events to metering service
        for event_data in batch:
            try:
                await self._metering_service.record_event(
                    tenant_id=event_data["tenant_id"],
                    operation=event_data["operation"],
                    tier=event_data["tier"],
                    agent_id=event_data["agent_id"],
                    tokens_processed=event_data["tokens_processed"],
                    latency_ms=event_data["latency_ms"],
                    compliance_score=event_data["compliance_score"],
                    metadata=event_data["metadata"],
                )
                self._events_flushed += 1
            except METERING_RECORD_ERRORS as e:
                logger.error(f"Failed to record metering event: {e}")

    def get_metrics(self) -> JSONDict:
        """Get queue metrics."""
        return {
            "events_queued": self._events_queued,
            "events_flushed": self._events_flushed,
            "events_dropped": self._events_dropped,
            "queue_size": self._queue.qsize(),
            "running": self._running,
            "enabled": self.config.enabled,
            "constitutional_hash": self.config.constitutional_hash,
        }


class MeteringHooks:
    """
    Non-blocking metering hooks for EnhancedAgentBus and MessageProcessor.

    All hooks use fire-and-forget pattern to ensure zero latency impact.
    """

    def __init__(self, queue: AsyncMeteringQueue):
        self._queue = queue

    def on_constitutional_validation(
        self,
        tenant_id: str,
        agent_id: str | None,
        is_valid: bool,
        latency_ms: float,
        tier: "MeteringTier" = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Record constitutional validation event.

        Called after each constitutional hash validation.
        """
        if tier is None and METERING_AVAILABLE:
            tier = MeteringTier.STANDARD

        self._queue.enqueue_nowait(
            tenant_id=tenant_id or "default",
            operation=MeterableOperation.CONSTITUTIONAL_VALIDATION if METERING_AVAILABLE else None,
            tier=tier,
            agent_id=agent_id,
            latency_ms=latency_ms,
            compliance_score=1.0 if is_valid else 0.0,
            metadata={
                "is_valid": is_valid,
                **(metadata or {}),
            },
        )

    def on_agent_message(
        self,
        tenant_id: str,
        from_agent: str,
        to_agent: str | None,
        message_type: str,
        latency_ms: float,
        is_valid: bool,
        tier: "MeteringTier" = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Record agent message event.

        Called after each message is processed through the bus.
        """
        if tier is None and METERING_AVAILABLE:
            tier = MeteringTier.STANDARD

        self._queue.enqueue_nowait(
            tenant_id=tenant_id or "default",
            operation=MeterableOperation.AGENT_MESSAGE if METERING_AVAILABLE else None,
            tier=tier,
            agent_id=from_agent,
            latency_ms=latency_ms,
            compliance_score=1.0 if is_valid else 0.0,
            metadata={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "message_type": message_type,
                "is_valid": is_valid,
                **(metadata or {}),
            },
        )

    def on_policy_evaluation(
        self,
        tenant_id: str,
        agent_id: str | None,
        policy_name: str,
        decision: str,
        latency_ms: float,
        tier: "MeteringTier" = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Record policy evaluation event.

        Called after each OPA/policy evaluation.
        """
        if tier is None and METERING_AVAILABLE:
            tier = MeteringTier.ENHANCED

        self._queue.enqueue_nowait(
            tenant_id=tenant_id or "default",
            operation=MeterableOperation.POLICY_EVALUATION if METERING_AVAILABLE else None,
            tier=tier,
            agent_id=agent_id,
            latency_ms=latency_ms,
            compliance_score=1.0 if decision == "allow" else 0.0,
            metadata={
                "policy_name": policy_name,
                "decision": decision,
                **(metadata or {}),
            },
        )

    def on_deliberation_request(
        self,
        tenant_id: str,
        agent_id: str | None,
        impact_score: float,
        latency_ms: float,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Record deliberation request event.

        Called when a message triggers deliberation layer.
        """
        if not METERING_AVAILABLE:
            return

        self._queue.enqueue_nowait(
            tenant_id=tenant_id or "default",
            operation=MeterableOperation.DELIBERATION_REQUEST,
            tier=MeteringTier.DELIBERATION,
            agent_id=agent_id,
            latency_ms=latency_ms,
            compliance_score=impact_score,
            metadata={
                "impact_score": impact_score,
                **(metadata or {}),
            },
        )

    def on_hitl_approval(
        self,
        tenant_id: str,
        agent_id: str | None,
        approver_id: str,
        approved: bool,
        latency_ms: float,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Record human-in-the-loop approval event.

        Called when HITL decision is made.
        """
        if not METERING_AVAILABLE:
            return

        self._queue.enqueue_nowait(
            tenant_id=tenant_id or "default",
            operation=MeterableOperation.HITL_APPROVAL,
            tier=MeteringTier.DELIBERATION,
            agent_id=agent_id,
            latency_ms=latency_ms,
            compliance_score=1.0 if approved else 0.0,
            metadata={
                "approver_id": approver_id,
                "approved": approved,
                **(metadata or {}),
            },
        )


# Global metering instance (lazy initialized)
_metering_queue: AsyncMeteringQueue | None = None
_metering_hooks: MeteringHooks | None = None


def get_metering_queue(config: MeteringConfig | None = None) -> AsyncMeteringQueue:
    """Get or create the global metering queue singleton."""
    global _metering_queue
    if _metering_queue is None:
        _metering_queue = AsyncMeteringQueue(config or MeteringConfig())
    return _metering_queue


def get_metering_hooks(config: MeteringConfig | None = None) -> MeteringHooks:
    """Get or create the global metering hooks singleton."""
    global _metering_hooks
    if _metering_hooks is None:
        queue = get_metering_queue(config)
        _metering_hooks = MeteringHooks(queue)
    return _metering_hooks


def reset_metering() -> None:
    """Reset metering singletons (for testing)."""
    global _metering_queue, _metering_hooks
    _metering_queue = None
    _metering_hooks = None


def metered_operation(
    operation: "MeterableOperation",
    tier: "MeteringTier" = None,
    extract_tenant: Callable[..., str] | None = None,
    extract_agent: Callable[..., str | None] | None = None,
) -> Callable[[F], F]:
    """
    Decorator for metering async operations.

    Args:
        operation: The operation type to meter
        tier: The metering tier (defaults to STANDARD)
        extract_tenant: Function to extract tenant_id from args/kwargs
        extract_agent: Function to extract agent_id from args/kwargs

    Example:
        @metered_operation(
            MeterableOperation.CONSTITUTIONAL_VALIDATION,
            extract_tenant=lambda msg: msg.tenant_id,
            extract_agent=lambda msg: msg.from_agent,
        )
        async def validate(self, message: AgentMessage) -> ValidationResult:
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            timing_context = _MeteringTimingContext()

            try:
                result = await func(*args, **kwargs)
                is_valid = _extract_validity_from_result(result)
                return result
            except (RuntimeError, ValueError, TypeError) as e:
                is_valid = False
                raise e
            finally:
                _record_metering_event(
                    operation=operation,
                    tier=tier,
                    func=func,
                    args=args,
                    extract_tenant=extract_tenant,
                    extract_agent=extract_agent,
                    latency_ms=timing_context.get_latency_ms(),
                    is_valid=is_valid,
                )

        return wrapper  # type: ignore[return-value]

    return decorator


class _MeteringTimingContext:
    """Helper class to track timing for metered operations."""

    def __init__(self) -> None:
        self._start_time = time.perf_counter()

    def get_latency_ms(self) -> float:
        """Calculate latency in milliseconds since context creation."""
        return (time.perf_counter() - self._start_time) * 1000


def _extract_validity_from_result(result: object) -> bool:
    """Extract validity from operation result if possible."""
    if hasattr(result, "is_valid"):
        return bool(result.is_valid)  # type: ignore[attr-defined]
    return True


def _extract_identifiers_from_args(
    args: tuple,
    extract_tenant: Callable[..., str] | None,
    extract_agent: Callable[..., str | None] | None,
) -> tuple[str, str | None]:
    """Extract tenant_id and agent_id from function arguments."""
    tenant_id = "default"
    agent_id = None

    if not args:
        return tenant_id, agent_id

    # Get first argument, skipping 'self' if present
    first_arg = _get_first_non_self_arg(args)
    if first_arg is None:
        return tenant_id, agent_id

    tenant_id = _extract_tenant_id(first_arg, extract_tenant)
    agent_id = _extract_agent_id(first_arg, extract_agent)

    return tenant_id, agent_id


def _get_first_non_self_arg(args: tuple) -> object | None:
    """Get the first argument that isn't a 'self' instance."""
    if not args:
        return None

    first_arg = args[0]
    if hasattr(first_arg, "__self__"):
        # This is likely a bound method, get the next argument
        return args[1] if len(args) > 1 else None  # type: ignore[no-any-return]

    return first_arg  # type: ignore[no-any-return]


def _extract_tenant_id(arg: object, extract_tenant: Callable[..., str] | None) -> str:
    """Extract tenant_id from argument using extractor function or attribute."""
    if extract_tenant:
        try:
            return extract_tenant(arg) or "default"
        except (AttributeError, KeyError, TypeError):
            pass

    if hasattr(arg, "tenant_id"):
        return arg.tenant_id or "default"  # type: ignore[attr-defined]

    return "default"


def _extract_agent_id(arg: object, extract_agent: Callable[..., str | None] | None) -> str | None:
    """Extract agent_id from argument using extractor function or attribute."""
    if extract_agent:
        try:
            return extract_agent(arg)
        except (AttributeError, KeyError, TypeError):
            pass

    if hasattr(arg, "from_agent"):
        return str(arg.from_agent)  # type: ignore[attr-defined]

    return None


def _record_metering_event(
    operation: "MeterableOperation",
    tier: "MeteringTier | None",
    func: Callable,  # type: ignore[type-arg]
    args: tuple,
    extract_tenant: Callable[..., str] | None,
    extract_agent: Callable[..., str | None] | None,
    latency_ms: float,
    is_valid: bool,
) -> None:
    """Record a metering event with extracted parameters."""
    if not METERING_AVAILABLE or operation is None:
        return

    tenant_id, agent_id = _extract_identifiers_from_args(args, extract_tenant, extract_agent)

    hooks = get_metering_hooks()
    hooks._queue.enqueue_nowait(
        tenant_id=tenant_id,
        operation=operation,
        tier=tier or MeteringTier.STANDARD,
        agent_id=agent_id,
        latency_ms=latency_ms,
        compliance_score=1.0 if is_valid else 0.0,
        metadata={
            "function": func.__name__,
            "is_valid": is_valid,
        },
    )


class MeteringMixin:
    """
    Mixin class for adding metering capabilities to EnhancedAgentBus or MessageProcessor.

    Usage:
        class MeteredAgentBus(MeteringMixin, EnhancedAgentBus):
            async def start(self):
                await self.start_metering()
                await super().start()

            async def stop(self):
                await super().stop()
                await self.stop_metering()
    """

    _metering_queue: AsyncMeteringQueue | None = None
    _metering_hooks: MeteringHooks | None = None
    _metering_config: MeteringConfig | None = None

    def configure_metering(self, config: MeteringConfig | None = None) -> None:
        """Configure metering for this instance."""
        self._metering_config = config or MeteringConfig()
        self._metering_queue = AsyncMeteringQueue(self._metering_config)
        self._metering_hooks = MeteringHooks(self._metering_queue)

    async def start_metering(self) -> None:
        """Start the metering queue."""
        if self._metering_queue is None:
            self.configure_metering()
        if self._metering_queue:
            await self._metering_queue.start()

    async def stop_metering(self) -> None:
        """Stop the metering queue."""
        if self._metering_queue:
            await self._metering_queue.stop()

    def get_metering_metrics(self) -> JSONDict:
        """Get metering metrics."""
        if self._metering_queue:
            return self._metering_queue.get_metrics()
        return {"enabled": False}

    def meter_constitutional_validation(
        self,
        tenant_id: str,
        agent_id: str | None,
        is_valid: bool,
        latency_ms: float,
        metadata: JSONDict | None = None,
    ) -> None:
        """Record a constitutional validation event."""
        if self._metering_hooks:
            self._metering_hooks.on_constitutional_validation(
                tenant_id=tenant_id,
                agent_id=agent_id,
                is_valid=is_valid,
                latency_ms=latency_ms,
                metadata=metadata,
            )

    def meter_agent_message(
        self,
        tenant_id: str,
        from_agent: str,
        to_agent: str | None,
        message_type: str,
        latency_ms: float,
        is_valid: bool,
        metadata: JSONDict | None = None,
    ) -> None:
        """Record an agent message event."""
        if self._metering_hooks:
            self._metering_hooks.on_agent_message(
                tenant_id=tenant_id,
                from_agent=from_agent,
                to_agent=to_agent,
                message_type=message_type,
                latency_ms=latency_ms,
                is_valid=is_valid,
                metadata=metadata,
            )

    def meter_policy_evaluation(
        self,
        tenant_id: str,
        agent_id: str | None,
        policy_name: str,
        decision: str,
        latency_ms: float,
        metadata: JSONDict | None = None,
    ) -> None:
        """Record a policy evaluation event."""
        if self._metering_hooks:
            self._metering_hooks.on_policy_evaluation(
                tenant_id=tenant_id,
                agent_id=agent_id,
                policy_name=policy_name,
                decision=decision,
                latency_ms=latency_ms,
                metadata=metadata,
            )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "METERING_AVAILABLE",
    "AsyncMeteringQueue",
    "MeteringConfig",
    "MeteringHooks",
    "MeteringMixin",
    "get_metering_hooks",
    "get_metering_queue",
    "metered_operation",
    "reset_metering",
]
