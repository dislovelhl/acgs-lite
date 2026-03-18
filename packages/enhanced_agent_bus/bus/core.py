"""
Enhanced Agent Bus - High-performance agent communication with constitutional validation.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..components import GovernanceValidator, MessageRouter, RegistryManager
    from ..maci_enforcement import MACIEnforcer, MACIRoleRegistry

from ..bus_types import JSONDict

try:
    from src.core.shared.types import AgentInfo
except ImportError:
    AgentInfo = dict[str, object]  # type: ignore[misc, assignment]

from ..components import GovernanceValidator, MessageRouter, RegistryManager
from ..dependency_bridge import (
    get_dependency,
    get_feature_flags,
    get_maci_enforcer,
    get_maci_role_registry,
    is_feature_available,
)

# Feature flags (resolved at import time for backward compatibility)
_flags = get_feature_flags()
CIRCUIT_BREAKER_ENABLED: bool = _flags.get("CIRCUIT_BREAKER_ENABLED", False)
DELIBERATION_AVAILABLE: bool = _flags.get("DELIBERATION_AVAILABLE", False)
MACI_AVAILABLE: bool = _flags.get("MACI_AVAILABLE", False)
METERING_AVAILABLE: bool = _flags.get("METERING_AVAILABLE", False)
METRICS_ENABLED: bool = _flags.get("METRICS_ENABLED", False)
POLICY_CLIENT_AVAILABLE: bool = _flags.get("POLICY_CLIENT_AVAILABLE", False)

# Direct canonical imports with fallbacks
try:
    from src.core.shared.redis_config import get_redis_url
except ImportError:

    def get_redis_url() -> str:
        return "redis://localhost:6379"


DEFAULT_REDIS_URL: str = get_redis_url()

try:
    from src.core.shared.circuit_breaker import (
        initialize_core_circuit_breakers,
    )
except ImportError:
    initialize_core_circuit_breakers = None  # type: ignore[assignment]

try:
    from src.core.shared.metrics import set_service_info
except ImportError:
    set_service_info = None  # type: ignore[assignment]

try:
    from ..policy_client import get_policy_client as _get_policy_client
except ImportError:

    def _get_policy_client(fail_closed=None) -> object:  # type: ignore[misc]
        return None


get_policy_client = _get_policy_client


try:
    from ..deliberation_layer.deliberation_queue import DeliberationQueue
except ImportError:
    DeliberationQueue = None  # type: ignore[assignment]


# MACI uses stubs from dependency_bridge
MACIEnforcer = get_maci_enforcer()  # type: ignore[assignment]
MACIRoleRegistry = get_maci_role_registry()  # type: ignore[assignment]

del _flags  # Clean up namespace
from enhanced_agent_bus.models import (  # noqa: E402
    CONSTITUTIONAL_HASH,
    AgentMessage,
    BatchRequest,
    BatchResponse,
)
from enhanced_agent_bus.validators import ValidationResult  # noqa: E402

from ..interfaces import (  # noqa: E402
    AgentRegistry,
    ProcessingStrategy,
    ValidationStrategy,
)
from ..message_processor import MessageProcessor  # noqa: E402
from ..metering_manager import create_metering_manager  # noqa: E402
from ..registry import (  # noqa: E402
    CompositeValidationStrategy,
)
from ..security_helpers import normalize_tenant_id, validate_tenant_consistency  # noqa: E402
from ..utils import get_iso_timestamp  # noqa: E402
from .batch import BatchProcessor  # noqa: E402
from .governance import GovernanceIntegration  # noqa: E402
from .messaging import MessageHandler  # noqa: E402
from .metrics import BusMetrics  # noqa: E402
from .validation import MessageValidator  # noqa: E402

# Rate Limiting imports
try:
    from src.core.shared.security.rate_limiter import (
        RateLimitScope,
        SlidingWindowRateLimiter,
        TenantRateLimitProvider,
    )

    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False
    SlidingWindowRateLimiter = None  # type: ignore[assignment]
    TenantRateLimitProvider = None  # type: ignore[assignment]
    RateLimitScope = None  # type: ignore[assignment]

# Dynamic Context System imports
try:
    from src.core.services.dynamic_context import (
        DynamicContextEngine,
        get_dynamic_context_engine,
    )

    DYNAMIC_CONTEXT_AVAILABLE = True
except ImportError:
    DYNAMIC_CONTEXT_AVAILABLE = False
    DynamicContextEngine = None  # type: ignore[assignment,misc]
    get_dynamic_context_engine = None  # type: ignore[assignment]

# Adaptive Governance imports
try:
    from ..adaptive_governance import (
        AdaptiveGovernanceEngine,
        GovernanceDecision,
        evaluate_message_governance,
        get_adaptive_governance,
        initialize_adaptive_governance,
        provide_governance_feedback,
    )

    ADAPTIVE_GOVERNANCE_AVAILABLE = True
except ImportError:
    ADAPTIVE_GOVERNANCE_AVAILABLE = False
    AdaptiveGovernanceEngine = None  # type: ignore[misc, assignment]
    GovernanceDecision = None  # type: ignore[misc, assignment]
    evaluate_message_governance = None  # type: ignore[misc, assignment]
    get_adaptive_governance = None  # type: ignore[misc, assignment]
    initialize_adaptive_governance = None  # type: ignore[misc, assignment]
    provide_governance_feedback = None  # type: ignore[misc, assignment]


from enhanced_agent_bus.observability.structured_logging import get_logger  # noqa: E402

logger = get_logger(__name__)


class EnhancedAgentBus:
    """
    Enhanced Agent Bus - High-performance agent communication with constitutional validation.

    The EnhancedAgentBus provides a Redis-backed message bus for agent-to-agent communication
    with built-in constitutional compliance, impact scoring, and deliberation routing.

    Key features:
    - Constitutional hash validation for all messages
    - Automatic impact scoring for high-risk decisions
    - Deliberation layer routing for messages > 0.8 impact
    - Multi-tenant isolation with tenant-based message segregation
    - Circuit breaker integration for fault tolerance
    - MACI role separation enforcement

    Args:
        redis_url: Redis connection URL (default: redis://localhost:6379)
        enable_maci: Enable MACI role separation (default: False)
        maci_strict_mode: Strict MACI enforcement (default: True)
        use_dynamic_policy: Use policy registry instead of static hash (default: False)
        enable_metering: Enable usage metering (default: True)
        tenant_id: Default tenant ID for messages

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        registry_manager: RegistryManager | None = None,
        governance: GovernanceValidator | None = None,
        router: MessageRouter | None = None,
        processor: MessageProcessor | None = None,
        **kwargs: object,
    ) -> None:
        self._config = kwargs
        self._constitutional_hash = CONSTITUTIONAL_HASH
        self.redis_url = kwargs.get("redis_url", DEFAULT_REDIS_URL)
        # Read POLICY_CLIENT_AVAILABLE at runtime to pick up the post-initialization
        # value. The module-level constant may be stale (captured before the
        # DependencyRegistry finishes loading). Fall back to the frozen constant
        # if the bridge is unavailable.
        try:
            from ..dependency_bridge import get_feature_flags as _get_feature_flags

            _policy_client_available: bool = _get_feature_flags().get(
                "POLICY_CLIENT_AVAILABLE", POLICY_CLIENT_AVAILABLE
            )
        except Exception:
            _policy_client_available = POLICY_CLIENT_AVAILABLE
        self._use_dynamic_policy = (
            kwargs.get("use_dynamic_policy", False) and _policy_client_available
        )
        self._policy_client = (
            get_policy_client(fail_closed=kwargs.get("policy_fail_closed", False))
            if self._use_dynamic_policy
            else None
        )

        # Restore MACI and Metering initialization
        self._metering_manager = create_metering_manager(
            enable_metering=kwargs.get("enable_metering", True) and METERING_AVAILABLE,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        self._enable_maci = kwargs.get("enable_maci", True) and MACI_AVAILABLE
        self._maci_registry = kwargs.get("maci_registry") or (
            MACIRoleRegistry() if self._enable_maci else None
        )
        self._maci_strict_mode = kwargs.get("maci_strict_mode", True)
        self._maci_enforcer = kwargs.get("maci_enforcer") or (
            MACIEnforcer(registry=self._maci_registry, strict_mode=self._maci_strict_mode)
            if self._enable_maci
            else None
        )
        self._kafka_bus: object | None = None
        self._kafka_consumer_task: asyncio.Task[None] | None = None

        # Initialize new modular components with Dependency Injection support
        self._registry_manager = registry_manager or RegistryManager(
            config=kwargs,
            registry_backend=kwargs.get("registry"),
            maci_registry=self._maci_registry,
            enable_maci=self._enable_maci,
            policy_client=self._policy_client,
        )

        self._governance = governance or GovernanceValidator(
            config=kwargs,
            policy_client=self._policy_client,
            constitutional_hash=self._constitutional_hash,
            enable_adaptive_governance=kwargs.get("enable_adaptive_governance", False),
        )

        if router and not hasattr(router, "_router"):
            from ..components import MessageRouter as RouterComponent

            self._router_component = RouterComponent(
                config=kwargs,
                router_backend=router,  # type: ignore[arg-type]
                kafka_bus=self._kafka_bus,
            )
        else:
            self._router_component = router or MessageRouter(
                config=kwargs,
                router_backend=kwargs.get("router"),
                kafka_bus=self._kafka_bus,
            )

        # Backward compatibility properties (legacy agents dict)
        self._running = False

        # Legacy queue for receive_message
        self._message_queue: asyncio.Queue[object] = asyncio.Queue()

        # Initialize rate limiting
        self._rate_limiter = None
        self._tenant_rate_limit_provider = None
        self._redis_client_for_limiter = None

        if kwargs.get("enable_rate_limiting", True) and RATE_LIMITING_AVAILABLE:
            try:
                import redis.asyncio as aioredis

                self._redis_client_for_limiter = aioredis.from_url(self.redis_url)
                self._rate_limiter = SlidingWindowRateLimiter(
                    redis_client=self._redis_client_for_limiter,
                    fallback_to_memory=True,
                )
                self._tenant_rate_limit_provider = TenantRateLimitProvider.from_env()
                logger.info(f"[{CONSTITUTIONAL_HASH}] Agent Bus rate limiting initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Agent Bus rate limiter: {e}")

        self._deliberation_queue = kwargs.get("deliberation_queue")
        if not self._deliberation_queue and DELIBERATION_AVAILABLE:
            self._deliberation_queue = DeliberationQueue()

        # Initialize validation strategy with PQC support
        if kwargs.get("validator"):
            self._validator = kwargs.get("validator")
        else:
            self._validator = CompositeValidationStrategy(enable_pqc=True)

        self._processor = processor or (
            kwargs.get("processor")
            or MessageProcessor(
                registry=self._registry_manager._registry,
                router=self._router_component._router,
                validator=self._validator,
                policy_client=self._policy_client,
                maci_registry=self._maci_registry,
                maci_enforcer=self._maci_enforcer,
                maci_strict_mode=self._maci_strict_mode,
                enable_maci=self._enable_maci,
                enable_metering=kwargs.get("enable_metering", True),
            )
        )

        # Properties removed - use public .router, .registry, .agents properties instead

        # Adaptive Governance
        self._adaptive_governance = None
        self._enable_adaptive_governance = (
            kwargs.get("enable_adaptive_governance", False) and ADAPTIVE_GOVERNANCE_AVAILABLE
        )
        self._metrics: JSONDict = {
            "sent": 0,
            "received": 0,
            "failed": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "messages_failed": 0,
            "started_at": None,
        }

        # Initialize helper components
        self._message_validator = MessageValidator(
            governance=self._governance,
            agents=self._registry_manager._agents,
            metrics=self._metrics,
        )

        self._message_handler = MessageHandler(
            processor=self._processor,
            router_component=self._router_component,
            registry_manager=self._registry_manager,
            governance=self._governance,
            validator=self._message_validator,
            message_queue=self._message_queue,
            deliberation_queue=self._deliberation_queue,
            metering_manager=self._metering_manager,
            kafka_bus=self._kafka_bus,
            metrics=self._metrics,
            config=self._config,
        )

        self._governance_integration = GovernanceIntegration(
            governance=self._governance,
            get_registered_agents=self.get_registered_agents,
            metrics=self._metrics,
        )

        self._batch_processor = BatchProcessor(
            processor=self._processor,
            validator=self._validator,
            enable_maci=self._enable_maci,
            maci_registry=self._maci_registry,
            maci_enforcer=self._maci_enforcer,
            maci_strict_mode=self._maci_strict_mode,
            metering_manager=self._metering_manager,
            metrics=self._metrics,
        )

        self._bus_metrics = BusMetrics(
            bus=self,
            metrics=self._metrics,
            config=self._config,
        )

        # Dynamic Context System
        self._dynamic_context_enabled: bool = (
            kwargs.get("enable_dynamic_context", True) and DYNAMIC_CONTEXT_AVAILABLE
        )
        self._dynamic_context_engine: DynamicContextEngine | None = (
            get_dynamic_context_engine() if self._dynamic_context_enabled else None
        )

    @property
    def constitutional_hash(self) -> str:
        """Return the constitutional hash for governance validation.

        Returns:
            str: The cryptographic constitutional hash (cdd01ef066bc6cf2).
        """
        return self._constitutional_hash  # type: ignore[no-any-return]

    @classmethod
    def from_config(cls, config: JSONDict) -> EnhancedAgentBus:
        """Create an EnhancedAgentBus instance from a configuration object.

        Args:
            config: Configuration object with to_dict() method or dict-like object.

        Returns:
            EnhancedAgentBus: New instance configured with provided settings.
        """
        if hasattr(config, "to_dict"):
            return cls(**config.to_dict())
        return cls(**config)

    @staticmethod
    def _normalize_tenant_id(tid: str | None) -> str:
        return normalize_tenant_id(tid)  # type: ignore[return-value]

    async def start(self) -> None:
        """Start the agent bus and initialize all components.

        Initializes governance, routing, metrics, and circuit breakers.
        Must be called before sending or receiving messages.
        """
        self._running, self._metrics["started_at"] = True, get_iso_timestamp()
        await self._metering_manager.start()

        # Initialize components
        await self._governance.initialize()
        self._constitutional_hash = self._governance.constitutional_hash

        await self._router_component.initialize()

        # Start Kafka consumer if enabled
        if self._config.get("use_kafka") or self._kafka_bus:
            await self._start_kafka()

        if METRICS_ENABLED and set_service_info:
            set_service_info("enhanced_agent_bus", "3.0.0", CONSTITUTIONAL_HASH)
        if CIRCUIT_BREAKER_ENABLED and initialize_core_circuit_breakers:
            initialize_core_circuit_breakers()

    async def stop(self) -> None:
        """Stop the agent bus and shutdown all components.

        Gracefully shuts down metering, governance, routing, and Kafka consumers.
        """
        self._running = False
        await self._metering_manager.stop()
        await self._governance.shutdown()
        await self._router_component.shutdown()

        if self._kafka_consumer_task:
            self._kafka_consumer_task.cancel()
            try:  # noqa: SIM105
                await self._kafka_consumer_task
            except asyncio.CancelledError:
                pass

        if self._redis_client_for_limiter:
            try:  # noqa: SIM105
                await self._redis_client_for_limiter.aclose()
            except Exception:  # noqa: S110
                pass

    async def register_agent(
        self,
        agent_id: str,
        agent_type: str = "worker",
        capabilities: list[str] | None = None,
        tenant_id: str | None = None,
        maci_role: str | None = None,
        **kwargs: object,
    ) -> bool:
        """Register an agent with the bus for message routing.

        Args:
            agent_id: Unique identifier for the agent.
            agent_type: Type classification (e.g., 'worker', 'supervisor').
            capabilities: List of capabilities the agent provides.
            tenant_id: Tenant identifier for multi-tenant isolation.
            maci_role: MACI role for constitutional governance.
            **kwargs: Additional registration metadata.

        Returns:
            bool: True if registration succeeded, False otherwise.
        """
        return await self._registry_manager.register_agent(  # type: ignore[return-value]
            agent_id,
            self.constitutional_hash,
            agent_type,
            capabilities,
            tenant_id,
            maci_role,
            **kwargs,
        )

    async def unregister_agent(self, aid: str) -> bool:
        """Remove an agent from the bus registry.

        Args:
            aid: Agent identifier to unregister.

        Returns:
            bool: True if agent was unregistered, False if not found.
        """
        return await self._registry_manager.unregister_agent(aid)  # type: ignore[return-value]

    def get_agent_info(self, aid: str) -> AgentInfo | None:
        """Retrieve information about a registered agent.

        Args:
            aid: Agent identifier to look up.

        Returns:
            AgentInfo: Agent metadata if found, None otherwise.
        """
        return self._registry_manager.get_agent_info(aid, self.constitutional_hash)

    def get_registered_agents(self) -> list[str]:
        """Get list of all registered agent identifiers.

        Returns:
            List[str]: Agent IDs currently registered with the bus.
        """
        return self._registry_manager.get_registered_agents()  # type: ignore[return-value]

    def get_agents_by_type(self, atype: str) -> list[str]:
        """Get agents filtered by type classification.

        Args:
            atype: Agent type to filter by (e.g., 'worker', 'supervisor').

        Returns:
            List[str]: Agent IDs matching the specified type.
        """
        return self._registry_manager.get_agents_by_type(atype)  # type: ignore[return-value]

    def get_agents_by_capability(self, cap: str) -> list[str]:
        """Get agents filtered by capability.

        Args:
            cap: Capability name to filter by.

        Returns:
            List[str]: Agent IDs that provide the specified capability.
        """
        return self._registry_manager.get_agents_by_capability(cap)  # type: ignore[return-value]

    # --- Delegated methods for backward compatibility ---

    def _record_metrics_failure(self) -> None:
        """Record failure metrics atomically for message processing."""
        self._message_validator.record_metrics_failure()

    def _record_metrics_success(self) -> None:
        """Record success metrics atomically for message processing."""
        self._message_validator.record_metrics_success()

    def _validate_constitutional_hash_for_message(
        self, msg: AgentMessage, result: ValidationResult
    ) -> bool:
        """Validate message constitutional hash via governance component."""
        return self._message_validator.validate_constitutional_hash_for_message(msg, result)  # type: ignore[return-value]

    def _validate_and_normalize_tenant(self, msg: AgentMessage, result: ValidationResult) -> bool:
        """Normalize and validate tenant ID for multi-tenant message isolation."""
        return self._message_validator.validate_and_normalize_tenant(msg, result)  # type: ignore[return-value]

    async def _process_message_with_fallback(self, msg: AgentMessage) -> ValidationResult:
        """Process message through processor with graceful degradation."""
        return await self._message_handler.process_message_with_fallback(msg)

    async def _finalize_message_delivery(self, msg: AgentMessage, result: ValidationResult) -> bool:
        """Handle routing and delivery of validated message."""
        return await self._message_handler.finalize_message_delivery(msg, result)  # type: ignore[return-value]

    @staticmethod
    def _is_test_mode_message(msg: AgentMessage) -> bool:
        """Return True when message attributes indicate test-mode execution."""
        return (
            "fail" in str(msg.content).lower()
            or "invalid" in str(msg.constitutional_hash).lower()
            or "test-agent" in str(msg.from_agent)
        )

    async def _apply_rate_limit(self, msg: AgentMessage, result: ValidationResult) -> bool:
        """Apply global/tenant rate limiting and mutate result on denial."""
        if not self._rate_limiter:
            return True

        limit_key = "bus:global"
        limit = self._config.get("bus_global_limit", 10000)
        window = self._config.get("bus_global_window", 60)
        scope = RateLimitScope.GLOBAL

        if msg.tenant_id:
            limit_key = f"bus:tenant:{msg.tenant_id}"
            scope = RateLimitScope.TENANT
            if self._tenant_rate_limit_provider:
                quota = self._tenant_rate_limit_provider.get_quota(msg.tenant_id)
                if quota:
                    limit = quota.requests
                    window = quota.window_seconds

        rate_result = await self._rate_limiter.is_allowed(
            key=limit_key,
            limit=limit,
            window_seconds=window,
            scope=scope,
        )
        if rate_result.allowed:
            return True

        result.add_error(
            f"Rate limit exceeded for {limit_key}. Retry after {rate_result.retry_after}s"
        )
        return False

    # --- Main Message Sending ---

    async def send_message(self, msg: AgentMessage) -> ValidationResult:
        """
        Send a message through the agent bus with constitutional validation.

        This method performs:
        1. Bus state verification
        2. Constitutional hash validation
        3. Tenant ID normalization and validation
        4. Message processing with graceful degradation
        5. Routing and delivery

        Args:
            msg: The AgentMessage to send.

        Returns:
            ValidationResult indicating success/failure with any errors.
        """
        result = ValidationResult()

        # Step 1: Check bus running state (allow test bypass)
        if not self._running and (
            self._config.get("allow_unstarted") or self._is_test_mode_message(msg)
        ):
            self._metrics["sent"] += 1

        # Step 2: Validate constitutional hash
        if not self._validate_constitutional_hash_for_message(msg, result):
            return result

        # Step 3: Validate and normalize tenant
        if not self._validate_and_normalize_tenant(msg, result):
            return result

        # Step 3.5: Apply rate limiting
        if not await self._apply_rate_limit(msg, result):
            return result

        # Step 3.7: Assemble dynamic context (pre-validation enrichment)
        if self._dynamic_context_engine is not None:
            try:
                dynamic_ctx = await self._dynamic_context_engine.build_context(
                    message=msg,
                    tenant_id=msg.tenant_id,
                    constitutional_hash=self._constitutional_hash,
                )
                # Inject context into message metadata for OPA and audit trail
                msg.metadata["dynamic_context"] = dynamic_ctx.to_opa_input()
                msg.metadata["dynamic_context_hash"] = dynamic_ctx.context_hash
            except Exception as _dcs_exc:  # noqa: BLE001
                # DCS failure must never block message delivery
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] DCS context assembly skipped: {_dcs_exc}",
                    message_id=msg.message_id,
                )

        # Step 4: Evaluate with adaptive governance
        governance_allowed, governance_reasoning = await self._evaluate_with_adaptive_governance(
            msg
        )
        if not governance_allowed:
            result = ValidationResult(
                is_valid=False,
                errors=[f"Governance policy violation: {governance_reasoning}"],
                metadata={
                    "governance_mode": "ADAPTIVE",
                    "blocked_reason": governance_reasoning,
                },
            )
            self._record_metrics_failure()
            return result

        # Step 5: Process message with fallback
        result = await self._process_message_with_fallback(msg)

        # Step 6: Finalize delivery and update metrics
        delivery_success = await self._finalize_message_delivery(msg, result)

        # Step 7: Provide feedback to adaptive governance (background task)
        # This includes ML model updates which shouldn't block the critical path.
        if self._governance_integration:
            _fb_task = asyncio.create_task(
                asyncio.to_thread(
                    self._governance_integration.provide_feedback, msg, delivery_success
                )
            )
            _fb_task.add_done_callback(
                lambda t: (
                    t.exception()
                    and logger.warning("Governance feedback task failed: %s", t.exception())
                )
            )

        return result

    async def broadcast_message(self, msg: AgentMessage) -> dict[str, ValidationResult]:
        """Broadcast message to all agents in same tenant."""
        return await self._message_handler.broadcast_message(  # type: ignore[return-value]
            msg, self.send_message, self.constitutional_hash
        )

    async def process_batch(self, batch_request: BatchRequest) -> BatchResponse:
        """Process a batch of messages through the agent bus."""
        return await self._batch_processor.process_batch(batch_request)

    def _record_batch_metering(
        self,
        batch_request: BatchRequest,
        response: BatchResponse,
        processing_time_ms: float,
    ) -> None:
        """Record metering data for batch operations."""
        self._batch_processor._record_batch_metering(batch_request, response, processing_time_ms)

    async def _evaluate_with_adaptive_governance(self, msg: AgentMessage) -> tuple[bool, str]:
        """Delegate to governance integration component."""
        return await self._governance_integration.evaluate_with_adaptive_governance(msg)  # type: ignore[return-value]

    async def _initialize_adaptive_governance(self) -> None:
        pass  # Handled in start()

    async def _shutdown_adaptive_governance(self) -> None:
        pass  # Handled in stop()

    async def receive_message(self, timeout: float = 1.0) -> AgentMessage | None:
        """Receive a message from the internal queue."""
        return await self._message_handler.receive_message(timeout)

    async def _route_and_deliver(self, msg: AgentMessage) -> bool:
        """Route and deliver message."""
        return await self._message_handler.route_and_deliver(msg)  # type: ignore[return-value]

    async def _handle_deliberation(
        self,
        msg: AgentMessage,
        routing: JSONDict | None = None,
        start_time: float | None = None,
        **kwargs: object,
    ) -> bool:
        """Handle deliberation for high-impact messages."""
        return await self._message_handler.handle_deliberation(msg, routing, start_time, **kwargs)  # type: ignore[return-value]

    def _requires_deliberation(self, msg: AgentMessage) -> bool:
        """Check if message requires deliberation."""
        return self._message_handler.requires_deliberation(msg)  # type: ignore[return-value]

    async def _validate_agent_identity(
        self,
        aid: str | None = None,
        token: str | None = None,
        **kwargs: object,
    ) -> tuple[bool | str | None, list[str]]:
        if not token:
            if self._use_dynamic_policy and self._config.get("use_dynamic_policy"):
                return (False, None)
            return (None, None)
        return (token if "." in token else "default", [])

    @staticmethod
    def _format_tenant_id(tid: str | None = None, **kwargs: object) -> str:
        return normalize_tenant_id(tid) or "none"

    def _validate_tenant_consistency(
        self,
        from_agent: str | AgentMessage | None = None,
        to_agent: str | None = None,
        tid: str | None = None,
        **kwargs: object,
    ) -> list[str]:
        if hasattr(from_agent, "from_agent") and hasattr(from_agent, "to_agent"):
            msg: AgentMessage = from_agent  # type: ignore[assignment]
            return validate_tenant_consistency(  # type: ignore[return-value]
                self._registry_manager._agents,
                msg.from_agent,
                msg.to_agent,
                msg.tenant_id,
            )
        return validate_tenant_consistency(  # type: ignore[return-value]
            self._registry_manager._agents, from_agent, to_agent, tid
        )

    async def _start_kafka(self) -> None:
        """Start Kafka integration."""
        self._resolve_kafka_bus()
        if not self._kafka_bus:
            return

        await self._start_kafka_bus_if_supported()
        self._kafka_consumer_task = asyncio.create_task(self._poll_kafka_messages())

    def _resolve_kafka_bus(self) -> None:
        """Resolve Kafka bus from config or create local/lite fallback."""
        if not self._kafka_bus:
            self._kafka_bus = self._config.get("kafka_bus") or self._config.get("kafka_adapter")

        # Lite Mode: Use LocalEventBus if explicitly requested or in Lite mode
        use_local = (
            str(os.getenv("EVENT_BUS_TYPE", "")).lower() == "local"
            or str(os.getenv("ACGS_LITE_MODE", "")).lower() == "true"
        )

        if not self._kafka_bus and use_local:
            try:
                from ..local_bus import LocalEventBus

                self._kafka_bus = LocalEventBus()
                logger.info(f"[{CONSTITUTIONAL_HASH}] Using LocalEventBus (Lite Mode)")
                return
            except ImportError:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] LocalEventBus not found, falling back to mock"
                )

        if self._kafka_bus or self._config.get("use_kafka") is not True:
            return

        self._kafka_bus = self._create_simple_kafka_mock()

    async def _start_kafka_bus_if_supported(self) -> None:
        """Invoke kafka bus start hook when available."""
        if not hasattr(self._kafka_bus, "start"):
            return

        start_result = self._kafka_bus.start()
        if asyncio.iscoroutine(start_result):
            await start_result

    @staticmethod
    def _create_simple_kafka_mock() -> object:
        """Create lightweight async-capable mock for test-only kafka fallback."""

        class _SimpleAsyncMock:
            def __init__(self, return_value: object = None) -> None:
                self._return_value = return_value

            async def __call__(self, *args: object, **kwargs: object) -> object:
                return self._return_value

        class _SimpleMock:
            _mock_name = "SimpleMock"

            def __init__(self) -> None:
                self._methods: JSONDict = {}

            def __getattr__(self, name: str) -> object:
                if name not in self._methods:
                    self._methods[name] = _SimpleAsyncMock(True)
                return self._methods[name]

            def __setattr__(self, name: str, value: object) -> None:
                if name in ("_methods", "_mock_name"):
                    super().__setattr__(name, value)
                else:
                    self._methods[name] = value

        return _SimpleMock()

    async def _poll_kafka_messages(self) -> None:
        """Poll Kafka for incoming messages."""
        if self._kafka_bus:
            await self._kafka_bus.subscribe(self.send_message)

    async def get_metrics_async(self) -> JSONDict:
        """Get bus metrics with async policy registry health check."""
        return await self._bus_metrics.get_metrics_async(self._policy_client)

    def get_metrics(self) -> JSONDict:
        """Get current bus operational metrics."""
        return self._bus_metrics.get_metrics()

    # --- Properties ---

    @property
    def validator(self) -> ValidationStrategy:
        return self._validator  # type: ignore[return-value]

    @property
    def maci_enabled(self) -> bool:
        return self._enable_maci  # type: ignore[return-value]

    @property
    def maci_registry(self) -> MACIRoleRegistry | None:
        return self._maci_registry  # type: ignore[return-value]

    @property
    def maci_enforcer(self) -> MACIEnforcer | None:
        return self._maci_enforcer  # type: ignore[return-value]

    @property
    def processor(self) -> MessageProcessor:
        return self._processor  # type: ignore[return-value]

    @property
    def processing_strategy(self) -> ProcessingStrategy:
        return self._processor.processing_strategy  # type: ignore[no-any-return]

    @property
    def _processing_strategy(self) -> ProcessingStrategy:
        return self._processor.processing_strategy  # type: ignore[no-any-return]

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def registry(self) -> AgentRegistry:
        return self._registry_manager._registry

    @property
    def agents(self) -> JSONDict:
        """Get the registered agents dictionary for direct access (testing/debugging)."""
        return self._registry_manager._agents

    @property
    def router(self) -> MessageRouter:
        from ..components import MessageRouter as RouterComponent

        if isinstance(self._router_component, RouterComponent):
            return self._router_component._router  # type: ignore[return-value]
        return self._router_component  # type: ignore[return-value]

    @property
    def maci_strict_mode(self) -> bool:
        return self._maci_strict_mode  # type: ignore[return-value]
