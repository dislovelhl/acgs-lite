"""
ACGS-2 Deliberation Layer - Integration
Main integration point for the deliberation layer components.
Constitutional Hash: 608508a9bd224290

Supports dependency injection for all major components:
- ImpactScorer: Impact score calculation
- AdaptiveRouter: Message routing decisions
- DeliberationQueue: Deliberation processing
- LLMAssistant: AI-powered analysis
- OPAGuard: Policy-based verification
- Redis components: Persistent storage
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timezone
from importlib import import_module
from typing import TYPE_CHECKING, cast

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.plugin_registry import available, require

if TYPE_CHECKING:
    # Import protocols directly from interfaces for proper type checking
    from .interfaces import (
        AdaptiveRouterProtocol,
        DeliberationQueueProtocol,
        ImpactScorerProtocol,
        LLMAssistantProtocol,
        OPAGuardProtocol,
        RedisQueueProtocol,
        RedisVotingProtocol,
    )
    from .opa_guard_models import GuardResult


# Lazy imports to avoid circular dependency
def _get_imports():
    from .adaptive_router import get_adaptive_router
    from .deliberation_queue import DeliberationQueue, DeliberationStatus, VoteType
    from .impact_scorer import get_impact_scorer
    from .interfaces import (
        AdaptiveRouterProtocol,
        DeliberationQueueProtocol,
        ImpactScorerProtocol,
        LLMAssistantProtocol,
        OPAGuardProtocol,
        RedisQueueProtocol,
        RedisVotingProtocol,
    )
    from .llm_assistant import get_llm_assistant
    from .opa_guard import OPAGuard
    from .opa_guard_models import GuardDecision, GuardResult
    from .redis_integration import get_redis_deliberation_queue, get_redis_voting_system

    if available("dfc_metrics"):
        _dfc_module = import_module(require("dfc_metrics"))
        DFCCalculator = _dfc_module.DFCCalculator
        DFCComponents = _dfc_module.DFCComponents
        get_dfc_components_from_context = _dfc_module.get_dfc_components_from_context
    else:
        DFCCalculator = None
        DFCComponents = None

        def get_dfc_components_from_context(_context):
            return None

    def get_deliberation_queue():
        return DeliberationQueue()

    return {
        "AdaptiveRouterProtocol": AdaptiveRouterProtocol,
        "DeliberationQueueProtocol": DeliberationQueueProtocol,
        "DeliberationStatus": DeliberationStatus,
        "DFCCalculator": DFCCalculator,
        "DFCComponents": DFCComponents,
        "GuardDecision": GuardDecision,
        "GuardResult": GuardResult,
        "ImpactScorerProtocol": ImpactScorerProtocol,
        "LLMAssistantProtocol": LLMAssistantProtocol,
        "OPAGuard": OPAGuard,
        "OPAGuardProtocol": OPAGuardProtocol,
        "RedisQueueProtocol": RedisQueueProtocol,
        "RedisVotingProtocol": RedisVotingProtocol,
        "VoteType": VoteType,
        "get_adaptive_router": get_adaptive_router,
        "get_deliberation_queue": get_deliberation_queue,
        "get_dfc_components_from_context": get_dfc_components_from_context,
        "get_impact_scorer": get_impact_scorer,
        "get_llm_assistant": get_llm_assistant,
        "get_redis_deliberation_queue": get_redis_deliberation_queue,
        "get_redis_voting_system": get_redis_voting_system,
    }


# Cache for lazy imports
_imports_cache = None


def _lazy_import(name):
    global _imports_cache
    if _imports_cache is None:
        _imports_cache = _get_imports()
    return _imports_cache[name]


def _truncate_content_for_hotl(content: object, limit: int = 500) -> str:
    """Convert arbitrary message content to a bounded HOTL action string."""
    if isinstance(content, str):
        return content[:limit]
    if content is None:
        return ""
    return str(content)[:limit]


try:
    from src.core.shared.types import (
        JSONDict,
        JSONList,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONList = list  # type: ignore[misc,assignment]

try:
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageStatus
except ImportError:
    try:
        from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageStatus
    except ImportError:
        from enhanced_agent_bus.models import (
            CONSTITUTIONAL_HASH,
            AgentMessage,
            MessageStatus,
        )

logger = get_logger(__name__)
OPA_GUARD_VERIFICATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)
DFC_DIAGNOSTIC_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

if available("opa_guard_mixin"):
    OPAGuardMixin = import_module(require("opa_guard_mixin")).OPAGuardMixin
else:
    class OPAGuardMixin:  # type: ignore[no-redef]
        """Fallback empty mixin when opa_guard_mixin unavailable."""

        pass


class DeliberationLayer(OPAGuardMixin):
    """
    Main integration class for the deliberation layer.

    Integrates OPA policy guard for VERIFY-BEFORE-ACT pattern,
    multi-signature collection, and critic agent reviews.
    Constitutional Hash: 608508a9bd224290

    Supports dependency injection for testing and customization.
    All major components can be injected via constructor parameters.

    OPA Guard methods are provided by OPAGuardMixin.
    """

    # Instance variable type annotations for mypy
    impact_scorer: ImpactScorerProtocol | None
    adaptive_router: AdaptiveRouterProtocol | None
    deliberation_queue: DeliberationQueueProtocol | None
    llm_assistant: LLMAssistantProtocol | None
    opa_guard: OPAGuardProtocol | None  # type: ignore[assignment]
    redis_queue: RedisQueueProtocol | None
    redis_voting: RedisVotingProtocol | None
    _graphrag_enricher: object | None  # GraphRAGContextEnricher | None

    def __init__(
        self,
        impact_threshold: float = 0.8,
        deliberation_timeout: int = 300,
        enable_redis: bool = False,
        enable_learning: bool = True,
        enable_llm: bool = True,
        enable_opa_guard: bool = True,
        high_risk_threshold: float = 0.8,
        critical_risk_threshold: float = 0.95,
        # Dependency injection parameters
        impact_scorer: ImpactScorerProtocol | None = None,
        adaptive_router: AdaptiveRouterProtocol | None = None,
        deliberation_queue: DeliberationQueueProtocol | None = None,
        llm_assistant: LLMAssistantProtocol | None = None,
        opa_guard: OPAGuardProtocol | None = None,
        redis_queue: RedisQueueProtocol | None = None,
        redis_voting: RedisVotingProtocol | None = None,
        graphrag_enricher: object | None = None,
    ):
        """
        Initialize the deliberation layer.

        Args:
            impact_threshold: Threshold for routing to deliberation
            deliberation_timeout: Timeout for deliberation in seconds
            enable_redis: Whether to use Redis for persistence
            enable_learning: Whether to enable adaptive learning
            enable_llm: Whether to enable LLM assistance
            enable_opa_guard: Whether to enable OPA policy guard
            high_risk_threshold: Threshold for requiring signatures
            critical_risk_threshold: Threshold for requiring full review
            impact_scorer: Optional injected impact scorer
            adaptive_router: Optional injected adaptive router
            deliberation_queue: Optional injected deliberation queue
            llm_assistant: Optional injected LLM assistant
            opa_guard: Optional injected OPA guard
            redis_queue: Optional injected Redis queue
            redis_voting: Optional injected Redis voting system
            graphrag_enricher: Optional GraphRAGContextEnricher for policy retrieval.
                When provided, policy context is retrieved and added to the processing
                context before impact scoring and routing decisions.
        """
        self._initialize_basic_config(
            impact_threshold,
            deliberation_timeout,
            enable_redis,
            enable_learning,
            enable_llm,
            enable_opa_guard,
            high_risk_threshold,
            critical_risk_threshold,
        )

        self._initialize_core_components(
            impact_scorer, adaptive_router, deliberation_queue, redis_queue, redis_voting
        )
        self._initialize_optional_components(
            llm_assistant,
            enable_llm,
            opa_guard,
            enable_opa_guard,
            deliberation_timeout,
            high_risk_threshold,
            critical_risk_threshold,
        )
        self._initialize_callbacks()
        self._initialize_dfc_calculator()
        self._graphrag_enricher = graphrag_enricher

        logger.info(
            "Initialized ACGS-2 Deliberation Layer with OPA Guard: "
            f"{enable_opa_guard}, DI: impact_scorer={impact_scorer is not None}, "
            f"router={adaptive_router is not None}, queue={deliberation_queue is not None}"
        )

    def _initialize_basic_config(
        self,
        impact_threshold: float,
        deliberation_timeout: int,
        enable_redis: bool,
        enable_learning: bool,
        enable_llm: bool,
        enable_opa_guard: bool,
        high_risk_threshold: float,
        critical_risk_threshold: float,
    ):
        """Initialize basic configuration parameters."""
        self.impact_threshold = impact_threshold
        self.deliberation_timeout = deliberation_timeout
        self.enable_redis = enable_redis
        self.enable_learning = enable_learning
        self.enable_llm = enable_llm
        self.enable_opa_guard = enable_opa_guard
        self.high_risk_threshold = high_risk_threshold
        self.critical_risk_threshold = critical_risk_threshold

    def _initialize_core_components(
        self,
        impact_scorer: ImpactScorerProtocol | None,
        adaptive_router: AdaptiveRouterProtocol | None,
        deliberation_queue: DeliberationQueueProtocol | None,
        redis_queue: RedisQueueProtocol | None,
        redis_voting: RedisVotingProtocol | None,
    ):
        """Initialize core components with dependency injection."""
        # Setup impact scorer and router
        get_impact_scorer_func = _lazy_import("get_impact_scorer")
        get_adaptive_router_func = _lazy_import("get_adaptive_router")

        self.impact_scorer = impact_scorer or get_impact_scorer_func()
        self.adaptive_router = adaptive_router or get_adaptive_router_func()

        # Sync threshold
        if hasattr(self.adaptive_router, "set_impact_threshold"):
            self.adaptive_router.set_impact_threshold(self.impact_threshold)  # type: ignore[attr-defined]

        # Setup deliberation queue and Redis components
        self._setup_queue_and_redis_components(deliberation_queue, redis_queue, redis_voting)

    def _setup_queue_and_redis_components(
        self,
        deliberation_queue: DeliberationQueueProtocol | None,
        redis_queue: RedisQueueProtocol | None,
        redis_voting: RedisVotingProtocol | None,
    ):
        """Setup deliberation queue and Redis components with proper dependency injection."""
        if self.enable_redis:
            # Redis feature flag is authoritative: only wire Redis components when enabled.
            self.redis_queue = redis_queue
            self.redis_voting = redis_voting

            # Redis is enabled - create defaults if not injected
            if self.redis_queue is None:
                get_redis_deliberation_queue_func = _lazy_import("get_redis_deliberation_queue")
                self.redis_queue = get_redis_deliberation_queue_func()

            if self.redis_voting is None:
                get_redis_voting_system_func = _lazy_import("get_redis_voting_system")
                self.redis_voting = get_redis_voting_system_func()

            # Use Redis as deliberation queue if no specific deliberation queue provided
            self.deliberation_queue = deliberation_queue or self.redis_queue  # type: ignore[assignment]
        else:
            # Keep Redis components disabled even when dependencies are injected.
            self.redis_queue = None
            self.redis_voting = None

            # Redis not enabled - use provided deliberation queue or create default
            if deliberation_queue is not None:
                self.deliberation_queue = deliberation_queue
            else:
                get_deliberation_queue_func = _lazy_import("get_deliberation_queue")
                self.deliberation_queue = get_deliberation_queue_func()

    def _initialize_optional_components(
        self,
        llm_assistant: LLMAssistantProtocol | None,
        enable_llm: bool,
        opa_guard: OPAGuardProtocol | None,
        enable_opa_guard: bool,
        deliberation_timeout: int,
        high_risk_threshold: float,
        critical_risk_threshold: float,
    ):
        """Initialize optional components based on feature flags."""
        # LLM assistant setup
        self.llm_assistant = self._setup_llm_assistant(llm_assistant, enable_llm)

        # OPA Guard setup
        self.opa_guard = self._setup_opa_guard(
            opa_guard,
            enable_opa_guard,
            deliberation_timeout,
            high_risk_threshold,
            critical_risk_threshold,
        )

    def _setup_llm_assistant(
        self, llm_assistant: LLMAssistantProtocol | None, enable_llm: bool
    ) -> LLMAssistantProtocol | None:
        """Setup LLM assistant if enabled."""
        if llm_assistant is not None:
            return llm_assistant
        elif enable_llm:
            get_llm_assistant_func = _lazy_import("get_llm_assistant")
            return get_llm_assistant_func()  # type: ignore[no-any-return]
        return None

    def _setup_opa_guard(
        self,
        opa_guard: OPAGuardProtocol | None,
        enable_opa_guard: bool,
        deliberation_timeout: int,
        high_risk_threshold: float,
        critical_risk_threshold: float,
    ) -> OPAGuardProtocol | None:
        """Setup OPA Guard if enabled."""
        if opa_guard is not None:
            return opa_guard
        elif enable_opa_guard:
            OPAGuard_class = _lazy_import("OPAGuard")
            return OPAGuard_class(  # type: ignore[no-any-return]
                enable_signatures=True,
                enable_critic_review=True,
                signature_timeout=deliberation_timeout,
                review_timeout=deliberation_timeout,
                high_risk_threshold=high_risk_threshold,
                critical_risk_threshold=critical_risk_threshold,
            )
        return None

    def _initialize_callbacks(self):
        """Initialize processing callbacks."""
        self.fast_lane_callback: Callable | None = None
        self.deliberation_callback: Callable | None = None
        self.guard_callback: Callable | None = None

    def _initialize_dfc_calculator(self):
        """Initialize DFC Diagnostic Calculator if available."""
        DFCCalculator_class = _lazy_import("DFCCalculator")
        if DFCCalculator_class:
            self.dfc_calculator = DFCCalculator_class(threshold=0.7)
        else:
            self.dfc_calculator = None

    # Property accessors for injected dependencies
    @property
    def injected_impact_scorer(self) -> ImpactScorerProtocol | None:
        """Get the impact scorer (injected or default)."""
        return self.impact_scorer

    @property
    def injected_router(self) -> AdaptiveRouterProtocol | None:
        """Get the adaptive router (injected or default)."""
        return self.adaptive_router

    @property
    def injected_queue(self) -> DeliberationQueueProtocol | None:
        """Get the deliberation queue (injected or default)."""
        return self.deliberation_queue

    async def initialize(self) -> None:
        """Initialize async components."""
        if self.enable_redis:
            if self.redis_queue:
                await self.redis_queue.connect()  # type: ignore[attr-defined]
            if self.redis_voting:
                await self.redis_voting.connect()  # type: ignore[attr-defined]

        # Initialize OPA Guard
        if self.opa_guard:
            await self.opa_guard.initialize()
            logger.info("OPA Guard initialized")

    async def process_message(self, message: AgentMessage) -> JSONDict:
        """
        Process a message through the deliberation layer.

        Implements VERIFY-BEFORE-ACT pattern with OPA guard integration.

        Returns:
            Processing result with routing decision and guard result
        """
        start_time = datetime.now(UTC)

        try:
            # 1. Prepare context for multi-dimensional analysis
            context = self._prepare_processing_context(message)

            # 1a. Optionally enrich context with GraphRAG policy retrieval
            if self._graphrag_enricher is not None:
                graphrag_ctx = await self._graphrag_enricher.enrich(  # type: ignore[union-attr]
                    query=str(message.content),
                    tenant_id=message.tenant_id or "",
                )
                if graphrag_ctx:
                    context.update(graphrag_ctx)

            # 2. Ensure impact score is calculated
            self._ensure_impact_score(message, context)

            # 3. OPA Guard pre-action verification (VERIFY-BEFORE-ACT)
            guard_result = await self._evaluate_opa_guard(message, start_time)
            if guard_result is not None:
                if guard_result.get("success") is False:
                    return guard_result
                return await self._finalize_processing(message, guard_result, start_time)

            # 4. Route and execute (Dual-path Routing)
            result = await self._execute_routing(message, context)

            # 5. Finalize and record metrics
            return await self._finalize_processing(message, result, start_time)

        except asyncio.CancelledError:
            logger.info(f"Message processing cancelled for {message.message_id}")
            raise
        except TimeoutError as e:
            logger.error(f"Timeout processing message {message.message_id}: {e}")
            elapsed = datetime.now(UTC) - start_time
            return {
                "success": False,
                "error": f"Timeout: {e}",
                "processing_time": elapsed.total_seconds(),
            }
        except (ValueError, KeyError, TypeError) as e:
            logger.error(
                f"Data error processing message {message.message_id}: {type(e).__name__}: {e}"
            )
            elapsed = datetime.now(UTC) - start_time
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
                "processing_time": elapsed.total_seconds(),
            }
        except (AttributeError, RuntimeError) as e:
            logger.error(
                f"Runtime error processing message {message.message_id}: {type(e).__name__}: {e}"
            )
            elapsed = datetime.now(UTC) - start_time
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
                "processing_time": elapsed.total_seconds(),
            }

    def _prepare_processing_context(self, message: AgentMessage) -> JSONDict:
        """Prepare context for multi-dimensional analysis."""
        return {
            "agent_id": message.from_agent or message.sender_id,
            "tenant_id": message.tenant_id,
            "priority": message.priority,
            "message_type": message.message_type,
            "constitutional_hash": message.constitutional_hash,
        }

    def _ensure_impact_score(self, message: AgentMessage, context: JSONDict) -> None:
        """Ensure impact score is calculated if not present."""
        if message.impact_score is None and self.impact_scorer is not None:
            message.impact_score = self.impact_scorer.calculate_impact_score(
                message.content, context
            )
            logger.debug(
                f"Calculated impact score {message.impact_score:.3f} "
                f"for message {message.message_id}"
            )

    async def _evaluate_opa_guard(
        self, message: AgentMessage, start_time: datetime
    ) -> JSONDict | None:
        """Evaluate message with OPA Guard and handle early returns."""
        if not self.opa_guard:
            return None

        guard_result = await self._verify_with_opa_guard(message)
        if guard_result is not None:
            message._guard_result = guard_result  # type: ignore[attr-defined]

        # If guard denies, return immediate rejection dictionary
        GuardDecision_enum = _lazy_import("GuardDecision")
        if guard_result and not guard_result.is_allowed:  # type: ignore[attr-defined]
            if guard_result.decision == GuardDecision_enum.DENY:  # type: ignore[attr-defined]
                return await self._handle_guard_denial(message, guard_result, start_time)
            elif guard_result.decision == GuardDecision_enum.REQUIRE_SIGNATURES:  # type: ignore[attr-defined]
                return await self._handle_signature_requirement(message, guard_result, start_time)
            elif guard_result.decision == GuardDecision_enum.REQUIRE_REVIEW:  # type: ignore[attr-defined]
                return await self._handle_review_requirement(message, guard_result, start_time)

        return None

    async def _execute_routing(self, message: AgentMessage, context: JSONDict) -> JSONDict:
        """Determine route and execute lane-specific processing.

        Routing tiers (Constitutional Hash: 608508a9bd224290):
          LOW  (score < 0.3)    → fast lane
          MEDIUM (0.3 - <0.8)  -> HOTL: auto-remediate + 15-min override window
          HIGH (score >= 0.8)  → existing deliberation / full HITL gate
        """
        if self.adaptive_router is None:
            return {"lane": "fast", "error": "No router available"}
        routing_decision = await self.adaptive_router.route_message(message, context)

        impact_score: float = message.impact_score or 0.0

        if routing_decision.get("lane") == "fast":
            # Score < low_max — always fast lane regardless
            return await self._process_fast_lane(message, routing_decision)

        # Check medium-risk tier before committing to full deliberation
        if available("hotl_manager"):
            from src.core.shared.constants import RISK_TIER_HIGH_MIN, RISK_TIER_LOW_MAX

            get_hotl_manager = import_module(require("hotl_manager")).get_hotl_manager
            if RISK_TIER_LOW_MAX <= impact_score < RISK_TIER_HIGH_MIN:
                return await self._process_medium_risk(message, routing_decision, impact_score)

        return await self._process_deliberation(message, routing_decision)

    async def _process_medium_risk(
        self,
        message: AgentMessage,
        routing_decision: JSONDict,
        impact_score: float,
    ) -> JSONDict:
        """Route medium-risk (0.3-0.8) decisions to HOTL.

        The action is auto-remediated immediately; the human reviewer
        receives a webhook notification and has 15 minutes to override.
        """
        from src.core.services.hitl_approvals.hotl_manager import get_hotl_manager

        manager = get_hotl_manager()
        tenant_id: str = getattr(message, "tenant_id", None) or "unknown"
        decision = await manager.handle_medium_risk(
            action=_truncate_content_for_hotl(message.content),
            impact_score=impact_score,
            tenant_id=tenant_id,
            decision_id=str(message.message_id),
            metadata={
                "message_type": message.message_type.value
                if hasattr(message.message_type, "value")
                else str(message.message_type),
                "agent_id": str(getattr(message, "agent_id", "")),
            },
        )

        logger.info(
            "HOTL: medium-risk message routed",
            message_id=str(message.message_id),
            impact_score=impact_score,
            decision_id=decision.decision_id,
        )

        return {
            "lane": "hotl",
            "status": "auto_remediated",
            "impact_score": impact_score,
            "decision_id": decision.decision_id,
            "override_deadline": decision.deadline.isoformat(),
            "override_window_seconds": decision.seconds_remaining(),
            "routing_decision": routing_decision,
        }

    async def _finalize_processing(
        self, message: AgentMessage, result: JSONDict, start_time: datetime
    ) -> JSONDict:
        """Finalize processing, record metrics and return result."""
        elapsed = datetime.now(UTC) - start_time
        processing_time = elapsed.total_seconds()

        await self._record_performance_feedback(message, result, processing_time)

        # Run DFC diagnostics if in deliberation lane
        if result.get("lane") == "deliberation":
            await self._run_dfc_diagnostics(message, result)

        result["processing_time"] = processing_time
        result["success"] = True

        # Include guard result if available in result or message
        if "guard_result" not in result and hasattr(message, "_guard_result"):
            result["guard_result"] = message._guard_result

        logger.info(
            f"Processed message {message.message_id} in "
            f"{processing_time:.2f}s: {result.get('lane')}"
        )

        return result

    async def _verify_with_opa_guard(self, message: AgentMessage) -> GuardResult | None:
        """
        Verify message with OPA Guard before processing.

        Args:
            message: Message to verify

        Returns:
            GuardResult with verification outcome
        """
        if not self.opa_guard:
            return None

        try:
            action = {
                "type": message.message_type.value,
                "content": message.content,
                "impact_score": message.impact_score,
                "constitutional_hash": message.constitutional_hash,
            }

            context = {
                "from_agent": message.from_agent,
                "to_agent": message.to_agent,
                "tenant_id": message.tenant_id,
                "priority": (
                    message.priority.value
                    if hasattr(message.priority, "value")
                    else str(message.priority)
                ),
            }

            guard_result = await self.opa_guard.verify_action(
                agent_id=message.from_agent or message.sender_id,
                action=action,
                context=context,
            )

            # Execute guard callback if provided
            if self.guard_callback:
                await self.guard_callback(message, guard_result)

            return guard_result

        except OPA_GUARD_VERIFICATION_ERRORS as e:
            logger.error(f"OPA Guard verification error: {e}")
            # FAIL-CLOSED: Deny on error for security-critical operations (VULN-002)
            GuardResult_class = _lazy_import("GuardResult")
            GuardDecision_enum = _lazy_import("GuardDecision")
            return cast(
                "GuardResult",
                GuardResult_class(
                    decision=GuardDecision_enum.DENY,
                    is_allowed=False,
                    validation_errors=[f"Guard verification failed: {e!s}"],
                    validation_warnings=[],
                ),
            )

    async def _handle_guard_denial(
        self, message: AgentMessage, guard_result, start_time: datetime
    ) -> JSONDict:
        """Handle guard denial of action."""
        message.status = MessageStatus.FAILED

        elapsed = datetime.now(UTC) - start_time
        processing_time = elapsed.total_seconds()

        logger.warning(
            f"Message {message.message_id} denied by OPA Guard: {guard_result.validation_errors}"
        )

        return {
            "success": False,
            "lane": "denied",
            "status": "denied_by_guard",
            "guard_result": guard_result.to_dict(),
            "errors": guard_result.validation_errors,
            "processing_time": processing_time,
        }

    async def _handle_signature_requirement(
        self, message: AgentMessage, guard_result, start_time: datetime
    ) -> JSONDict:
        """Handle requirement for multi-signature collection."""
        # Create signature request
        decision_id = f"sig_{message.message_id}"

        signature_result = await self.opa_guard.collect_signatures(
            decision_id=decision_id,
            required_signers=guard_result.required_signers,
            threshold=1.0,
            timeout=self.deliberation_timeout,
        )

        elapsed = datetime.now(UTC) - start_time
        processing_time = elapsed.total_seconds()

        if signature_result.is_valid:
            # Signatures collected, proceed with processing
            logger.info(f"Signatures collected for message {message.message_id}")
            result = await self._route_verified_message(message)
            result["signature_result"] = signature_result.to_dict()
            result["processing_time"] = processing_time
            return result
        else:
            message.status = MessageStatus.FAILED
            logger.warning(
                f"Signature collection failed for message "
                f"{message.message_id}: {signature_result.status.value}"
            )
            return {
                "success": False,
                "lane": "signature_required",
                "status": "signature_collection_failed",
                "guard_result": guard_result.to_dict(),
                "signature_result": signature_result.to_dict(),
                "processing_time": processing_time,
            }

    async def _handle_review_requirement(
        self, message: AgentMessage, guard_result, start_time: datetime
    ) -> JSONDict:
        """Handle requirement for critic agent review."""
        decision = {
            "id": f"review_{message.message_id}",
            "message": message.to_dict(),
            "guard_result": guard_result.to_dict(),
        }

        review_result = await self.opa_guard.submit_for_review(
            decision=decision,
            critic_agents=guard_result.required_reviewers,
            review_types=["safety", "ethics", "compliance"],
            timeout=self.deliberation_timeout,
        )

        elapsed = datetime.now(UTC) - start_time
        processing_time = elapsed.total_seconds()

        if review_result.consensus_verdict == "approve":
            # Review approved, proceed with processing
            logger.info(f"Review approved for message {message.message_id}")
            result = await self._route_verified_message(message)
            result["review_result"] = review_result.to_dict()
            result["processing_time"] = processing_time
            return result
        else:
            message.status = MessageStatus.FAILED
            logger.warning(
                f"Review rejected for message {message.message_id}: "
                f"{review_result.consensus_verdict}"
            )
            return {
                "success": False,
                "lane": "review_required",
                "status": f"review_{review_result.consensus_verdict}",
                "guard_result": guard_result.to_dict(),
                "review_result": review_result.to_dict(),
                "processing_time": processing_time,
            }

    async def _route_verified_message(self, message: AgentMessage) -> JSONDict:
        """Continue processing after a guard-approved verification step."""
        if self.adaptive_router is None:
            return {"success": False, "error": "No router available"}

        routing = await self.adaptive_router.route_message(message)
        if routing.get("lane") == "fast":
            return await self._process_fast_lane(message, routing)
        return await self._process_deliberation(message, routing)

    async def _process_fast_lane(
        self, message: AgentMessage, routing_decision: JSONDict
    ) -> JSONDict:
        """Process message through fast lane."""
        # Update message status
        message.status = MessageStatus.DELIVERED

        # Execute fast lane callback if provided
        if self.fast_lane_callback:
            await self.fast_lane_callback(message)

        return {
            "lane": "fast",
            "status": "delivered",
            "impact_score": message.impact_score,
            "routing_decision": routing_decision,
        }

    async def _process_deliberation(
        self, message: AgentMessage, routing_decision: JSONDict
    ) -> JSONDict:
        """Process message through deliberation queue."""
        # Enqueue for deliberation
        item_id = await self.deliberation_queue.enqueue_for_deliberation(  # type: ignore[attr-defined]
            message=message,
            requires_human_review=True,
            requires_multi_agent_vote=routing_decision.get("impact_score", 0) > 0.9,
            timeout_seconds=self.deliberation_timeout,
        )

        # Store in Redis if enabled
        if self.enable_redis and self.redis_queue:
            await self.redis_queue.enqueue_deliberation_item(  # type: ignore[attr-defined]
                message=message, item_id=item_id, metadata=routing_decision
            )

        # Execute deliberation callback if provided
        if self.deliberation_callback:
            await self.deliberation_callback(message, routing_decision)

        return {
            "lane": "deliberation",
            "item_id": item_id,
            "status": "queued",
            "impact_score": message.impact_score,
            "routing_decision": routing_decision,
            "estimated_wait_time": self.deliberation_timeout,
        }

    async def _record_performance_feedback(
        self, message: AgentMessage, result: JSONDict, processing_time: float
    ):
        """Record performance feedback for learning."""
        if not self.enable_learning or self.adaptive_router is None:
            return

        try:
            # Determine outcome
            if result.get("lane") == "fast":
                outcome = "fast_lane"
                feedback_score = 0.8 if result.get("success") else 0.2
            else:
                # For deliberation, we'll need to track the final outcome
                outcome = "deliberation_queued"
                feedback_score = None  # Will be updated when deliberation completes

            await self.adaptive_router.update_performance_feedback(
                message_id=message.message_id,
                actual_outcome=outcome,
                processing_time=processing_time,
                feedback_score=feedback_score,
            )

        except asyncio.CancelledError:
            raise
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Failed to record performance feedback: {type(e).__name__}: {e}")

    async def _run_dfc_diagnostics(self, message: AgentMessage, result: JSONDict) -> None:
        """Run DFC diagnostic heuristic to detect possible normative divergence."""
        # Check if DFC calculator and helper are available
        get_dfc_components_from_context_func = _lazy_import("get_dfc_components_from_context")
        if not self.dfc_calculator or not get_dfc_components_from_context_func:
            return

        try:
            # Derive components from deliberation result or context
            # This is a diagnostic step, not used for decision making.

            # Use message/result data to populate DFC context
            dfc_context = {
                "participation_rate": 1.0,  # Assumption for start
                "engagement_quality": 1.0 - (message.impact_score or 0.0),  # Inverse of risk
                "evolution_index": 1.0,  # Baseline
                "transparency_score": 1.0 if self.enable_opa_guard else 0.5,
            }

            components = get_dfc_components_from_context_func(dfc_context)
            score = self.dfc_calculator.calculate(components)

            result["dfc_diagnostic_score"] = score
            logger.debug(f"DFC Diagnostic Score for {message.message_id}: {score:.3f}")

        except DFC_DIAGNOSTIC_ERRORS as e:
            logger.warning(f"Failed to calculate DFC diagnostic: {e}")

    async def submit_human_decision(
        self, item_id: str, reviewer: str, decision: str, reasoning: str
    ) -> bool:
        """
        Submit human review decision.

        Args:
            item_id: Deliberation item ID
            reviewer: Human reviewer identifier
            decision: Decision ('approved', 'rejected', 'escalated')
            reasoning: Review reasoning

        Returns:
            True if decision submitted successfully
        """
        try:
            # Handle enum objects by extracting value (avoids cross-module enum identity issues)
            if hasattr(decision, "value"):
                decision_str = decision.value
            else:
                decision_str = str(decision).lower()

            DeliberationStatus_enum = _lazy_import("DeliberationStatus")
            decision_map = {
                "approved": DeliberationStatus_enum.APPROVED,
                "rejected": DeliberationStatus_enum.REJECTED,
                "escalated": DeliberationStatus_enum.UNDER_REVIEW,
                "under_review": DeliberationStatus_enum.UNDER_REVIEW,
            }
            deliberation_decision = decision_map.get(decision_str, DeliberationStatus_enum.REJECTED)

            success = await self.deliberation_queue.submit_human_decision(  # type: ignore[attr-defined]
                item_id=item_id,
                reviewer=reviewer,
                decision=deliberation_decision,
                reasoning=reasoning,
            )

            if success:
                logger.info(
                    f"Human decision submitted for item {item_id}: {decision} by {reviewer}"
                )

                # Update performance feedback
                await self._update_deliberation_outcome(item_id, decision, reasoning)

            return success

        except asyncio.CancelledError:
            raise
        except (ValueError, KeyError, TypeError) as e:
            logger.error(
                f"Failed to submit human decision for item {item_id}: {type(e).__name__}: {e}"
            )
            return False
        except (AttributeError, RuntimeError) as e:
            logger.error(f"Runtime error submitting human decision for item {item_id}: {e}")
            return False

    async def submit_agent_vote(
        self, item_id: str, agent_id: str, vote: str, reasoning: str, confidence: float = 1.0
    ) -> bool:
        """
        Submit agent vote for deliberation item.

        Returns:
            True if vote submitted successfully
        """
        try:
            # Map vote string to VoteType enum
            VoteType_enum = _lazy_import("VoteType")
            vote_map = {
                "approve": VoteType_enum.APPROVE,
                "reject": VoteType_enum.REJECT,
                "abstain": VoteType_enum.ABSTAIN,
            }
            vote_enum = vote_map.get(vote.lower(), VoteType_enum.ABSTAIN)

            success = await self.deliberation_queue.submit_agent_vote(  # type: ignore[attr-defined]
                item_id=item_id,
                agent_id=agent_id,
                vote=vote_enum,
                reasoning=reasoning,
                confidence=confidence,
            )

            if success:
                logger.info(f"Agent vote submitted for item {item_id}: {vote} by {agent_id}")

                # Submit to Redis voting if enabled
                if self.enable_redis and self.redis_voting:
                    await self.redis_voting.submit_vote(
                        item_id=item_id,
                        agent_id=agent_id,
                        vote=vote,
                        reasoning=reasoning,
                        confidence=confidence,
                    )

            return success

        except asyncio.CancelledError:
            raise
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"Failed to submit agent vote for item {item_id}: {type(e).__name__}: {e}")
            return False
        except (AttributeError, RuntimeError) as e:
            logger.error(f"Runtime error submitting agent vote for item {item_id}: {e}")
            return False

    async def _update_deliberation_outcome(
        self, item_id: str, decision: str, reasoning: str
    ) -> None:
        """Update performance feedback for completed deliberation."""
        if not self.enable_learning or self.adaptive_router is None:
            return

        try:
            # Find the message ID from the deliberation item
            if self.deliberation_queue is None:
                return
            item_details = self.deliberation_queue.get_item_details(item_id)  # type: ignore[union-attr]
            if not item_details:
                return

            message_id = item_details.get("message_id")
            if not message_id:
                return

            # Map decision to outcome
            outcome_map = {"approved": "approved", "rejected": "rejected", "escalated": "escalated"}

            outcome = outcome_map.get(decision, "rejected")

            # Calculate feedback score based on decision confidence
            feedback_score = (
                0.9 if decision == "approved" else 0.7 if decision == "escalated" else 0.5
            )

            await self.adaptive_router.update_performance_feedback(  # type: ignore[attr-defined]
                message_id=message_id,
                actual_outcome=outcome,
                processing_time=0,  # Will be calculated from history
                feedback_score=feedback_score,
            )

        except asyncio.CancelledError:
            raise
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Failed to update deliberation outcome: {type(e).__name__}: {e}")

    def get_layer_stats(self) -> JSONDict:
        """Get comprehensive statistics for the deliberation layer."""
        try:
            if self.adaptive_router is None or self.deliberation_queue is None:
                return {"layer_status": "not_initialized", "error": "Missing required components"}
            router_stats = self.adaptive_router.get_routing_stats()
            queue_stats = self.deliberation_queue.get_queue_status()  # type: ignore[union-attr]

            stats = {
                "layer_status": "operational",
                "impact_threshold": self.impact_threshold,
                "deliberation_timeout": self.deliberation_timeout,
                "features": {
                    "redis_enabled": self.enable_redis,
                    "learning_enabled": self.enable_learning,
                    "llm_enabled": self.enable_llm,
                    "opa_guard_enabled": self.enable_opa_guard,
                },
                "router_stats": router_stats,
                "queue_stats": queue_stats["stats"],
                "queue_size": queue_stats["queue_size"],
                "processing_count": queue_stats["processing_count"],
            }

            # Include OPA Guard stats if enabled
            if self.opa_guard:
                stats["opa_guard_stats"] = self.opa_guard.get_stats()

            if self.enable_redis and self.redis_queue:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is not None and loop.is_running():
                    # Inside an async context — cannot call asyncio.run()
                    stats["redis_info"] = None
                else:
                    try:
                        stats["redis_info"] = asyncio.run(
                            self.redis_queue.get_stream_info()  # type: ignore[attr-defined]
                        )
                    except RuntimeError:
                        stats["redis_info"] = None

            return stats

        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Failed to get layer stats: {type(e).__name__}: {e}")
            return {"error": f"{type(e).__name__}: {e}"}
        except RuntimeError as e:
            logger.error(f"Runtime error getting layer stats: {e}")
            return {"error": f"RuntimeError: {e}"}

    def set_fast_lane_callback(self, callback: Callable[..., object]) -> None:
        """Set callback for fast lane processing."""
        self.fast_lane_callback = callback

    def set_deliberation_callback(self, callback: Callable[..., object]) -> None:
        """Set callback for deliberation processing."""
        self.deliberation_callback = callback

    def set_guard_callback(self, callback: Callable[..., object]) -> None:
        """Set callback for OPA guard verification events."""
        self.guard_callback = callback

    # OPA Guard methods are provided by OPAGuardMixin:
    # - verify_action(), collect_signatures(), submit_signature()
    # - submit_for_review(), submit_critic_review()
    # - register_critic_agent(), unregister_critic_agent()
    # - get_guard_audit_log()

    async def close(self) -> None:
        """Close the deliberation layer and cleanup resources."""
        if self.opa_guard:
            await self.opa_guard.close()

        if self.redis_queue:
            await self.redis_queue.close()  # type: ignore[attr-defined]

        if self.redis_voting:
            await self.redis_voting.close()  # type: ignore[attr-defined]

        logger.info("Deliberation layer closed")

    async def analyze_trends(self) -> JSONDict:
        """Analyze deliberation trends for optimization."""
        if not self.llm_assistant:
            return {"error": "LLM assistant not enabled"}

        try:
            # Get deliberation history (simplified)
            history: JSONList = []  # Would need to implement history collection

            analysis = await self.llm_assistant.analyze_deliberation_trends(history)
            return analysis

        except asyncio.CancelledError:
            raise
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Failed to analyze trends: {type(e).__name__}: {e}")
            return {"error": f"{type(e).__name__}: {e}"}
        except RuntimeError as e:
            logger.error(f"Runtime error analyzing trends: {e}")
            return {"error": f"RuntimeError: {e}"}

    async def force_deliberation(
        self, message: AgentMessage, reason: str = "manual_override"
    ) -> JSONDict:
        """Force a message into deliberation regardless of impact score."""
        logger.info(f"Forcing message {message.message_id} into deliberation: {reason}")

        if self.adaptive_router is None:
            return {"success": False, "error": "No router available"}

        # Temporarily override impact score
        original_score = message.impact_score
        message.impact_score = 1.0

        result = await self.adaptive_router.force_deliberation(message, reason)

        # Restore original score
        message.impact_score = original_score

        return result

    async def resolve_deliberation_item(
        self, item_id: str, approved: bool, feedback_score: float | None = None
    ) -> JSONDict:
        """
        Resolve a pending deliberation item and update learning model.

        Args:
            item_id: ID of the deliberation item/task
            approved: Whether the action was approved
            feedback_score: Optional feedback score (0.0-1.0)

        Returns:
            Resolution result
        """
        if not self.deliberation_queue:
            return {"status": "error", "message": "No deliberation queue configured"}

        # 1. Resolve in queue
        await self.deliberation_queue.resolve_task(item_id, approved)  # type: ignore[attr-defined]

        # 2. Get task details for feedback
        # Note: DeliberationQueue.get_task must be available
        if hasattr(self.deliberation_queue, "get_task"):
            task = self.deliberation_queue.get_task(item_id)  # type: ignore[attr-defined]
        else:
            task = None

        if not task:
            logger.warning(f"Resolved task {item_id} not found for feedback provided")
            return {"status": "resolved_no_feedback"}

        # 3. Calculate processing time
        now = datetime.now(UTC)
        processing_time = (now - task.created_at).total_seconds()

        # 4. Update adaptive router
        if self.adaptive_router:
            actual_outcome = "approved" if approved else "rejected"
            await self.adaptive_router.update_performance_feedback(  # type: ignore[attr-defined]
                message_id=task.message.message_id,
                actual_outcome=actual_outcome,
                processing_time=processing_time,
                feedback_score=feedback_score,
            )

        return {
            "status": "resolved",
            "outcome": "approved" if approved else "rejected",
            "processing_time": processing_time,
        }


# Global deliberation layer instance
_deliberation_layer = None


def get_deliberation_layer() -> DeliberationLayer:
    """Get or create global deliberation layer instance."""
    global _deliberation_layer
    if _deliberation_layer is None:
        _deliberation_layer = DeliberationLayer()
    return _deliberation_layer


def reset_deliberation_layer() -> None:
    """Reset the global deliberation layer instance.

    Used primarily for test isolation to prevent state leakage between tests.
    Constitutional Hash: 608508a9bd224290
    """
    global _deliberation_layer
    _deliberation_layer = None


DeliberationEngine = DeliberationLayer
