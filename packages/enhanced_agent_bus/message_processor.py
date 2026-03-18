"""
Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import hashlib
import random
import time
from collections.abc import Callable, Coroutine
from contextlib import AbstractContextManager, nullcontext
from typing import Literal, cast

try:
    from src.core.shared.types import (
        JSONDict,
        JSONValue,
    )  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Local imports
from .config import BusConfiguration
from .dependency_bridge import get_dependency, get_feature_flags, is_feature_available
from .governance_constants import (
    DEFAULT_CB_FAIL_MAX,
    DEFAULT_CB_RESET_TIMEOUT,
    DEFAULT_LRU_CACHE_SIZE,
    IMPACT_DELIBERATION_THRESHOLD,
)

# Feature flags
_flags = get_feature_flags()
CIRCUIT_BREAKER_ENABLED: bool = _flags.get("CIRCUIT_BREAKER_ENABLED", False)
METERING_AVAILABLE: bool = _flags.get("METERING_AVAILABLE", False)
METRICS_ENABLED: bool = _flags.get("METRICS_ENABLED", False)
POLICY_CLIENT_AVAILABLE: bool = _flags.get("POLICY_CLIENT_AVAILABLE", False)
USE_RUST: bool = _flags.get("USE_RUST", False)
MCP_ENABLED: bool = _flags.get("MCP_ENABLED", False)

# Direct canonical imports with fallbacks
try:
    from src.core.shared.circuit_breaker import (
        CircuitBreakerConfig,
        get_circuit_breaker,
    )
except ImportError:

    class CircuitBreakerConfig:  # type: ignore[misc, no-redef]
        def __init__(self, fail_max: int, reset_timeout: float) -> None:
            self.fail_max = fail_max
            self.reset_timeout = reset_timeout

    def get_circuit_breaker(*args: object, **kwargs: object) -> object:
        """Fallback circuit breaker stub when import fails.

        Returns:
            None (stub implementation).
        """
        return None


try:
    from .metering_integration import get_metering_hooks
except ImportError:
    get_metering_hooks = cast(object, lambda config=None: None)


try:
    from .opa_client import get_opa_client as _get_opa_client
except ImportError:
    _get_opa_client = cast(object, lambda fail_closed=True: None)


get_opa_client = _get_opa_client


try:
    from .policy_client import get_policy_client as _get_policy_client
except ImportError:
    _get_policy_client = cast(object, lambda fail_closed=None: None)


get_policy_client = _get_policy_client


try:
    import enhanced_agent_bus_rust as rust_bus  # type: ignore[import-untyped]
except ImportError:
    rust_bus = None  # type: ignore[assignment]

del _flags

# MCP integration — optional dependency; degrades gracefully when absent
try:
    from enhanced_agent_bus.mcp import (
        MCPClient,
        MCPClientConfig,
        MCPClientPool,
    )
    from enhanced_agent_bus.mcp.config import MCPConfig
    from enhanced_agent_bus.mcp.types import MCPToolResult

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    MCPClient = None  # type: ignore[assignment, misc]
    MCPClientPool = None  # type: ignore[assignment, misc]
    MCPClientConfig = None  # type: ignore[assignment, misc]
    MCPConfig = None  # type: ignore[assignment, misc]
    MCPToolResult = None  # type: ignore[assignment, misc]

from .interfaces import ProcessingStrategy  # noqa: E402
from .memory_profiler import ProfilingLevel, get_memory_profiler  # noqa: E402
from .message_processor_components import (  # noqa: E402
    apply_latency_metadata,
    apply_session_governance_metrics,
    build_dlq_entry,
    calculate_session_resolution_rate,
    compute_message_cache_key,
    enforce_autonomy_tier_rules,
    enrich_metrics_with_opa_stats,
    enrich_metrics_with_workflow_telemetry,
    extract_pqc_failure_result,
    extract_rejection_reason,
    extract_session_id_for_pacar,
    merge_verification_metadata,
    prepare_message_content_string,
    run_message_validation_gates,
    schedule_background_task,
)
from .models import (  # noqa: E402
    CONSTITUTIONAL_HASH,
    AgentMessage,
    AutonomyTier,
    MessageStatus,
    MessageType,
    Priority,
    get_enum_value,
)
from .performance_monitor import timed  # noqa: E402
from .runtime_security import get_runtime_security_scanner  # noqa: E402
from .security_scanner import (  # noqa: E402
    PROMPT_INJECTION_PATTERNS,
    MessageSecurityScanner,
)
from .session_context import SessionContext, SessionContextManager  # noqa: E402
from .session_context_resolver import SessionContextResolver  # noqa: E402
from .utils import LRUCache  # noqa: E402
from .validators import ValidationResult  # noqa: E402
from .verification_orchestrator import VerificationOrchestrator  # noqa: E402

logger = get_logger(__name__)
DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

try:
    from src.core.shared.agent_workflow_metrics import (
        get_agent_workflow_metrics_collector,
    )

    AGENT_WORKFLOW_METRICS_AVAILABLE = True
except ImportError:
    AGENT_WORKFLOW_METRICS_AVAILABLE = False

# Autonomy tier enforcement: message types blocked for advisory agents
_ADVISORY_BLOCKED_TYPES: frozenset[str] = frozenset(
    {"command", "governance_request", "task_request"}
)


class MessageProcessor:
    """
    Core message processing engine with constitutional validation and strategy selection.

    The MessageProcessor handles the validation and routing of agent messages through
    configurable processing strategies including constitutional hash validation,
    OPA policy evaluation, and MACI role separation.

    Processing flow:
    1. Auto-select appropriate processing strategy based on configuration
    2. Validate message against constitutional requirements
    3. Route through deliberation layer if impact score > 0.8
    4. Execute message handlers with proper error handling

    Args:
        isolated_mode: Run without external dependencies (default: False)
        use_dynamic_policy: Use policy registry instead of static validation (default: False)
        enable_maci: Enable MACI role separation enforcement (default: False)
        opa_client: Optional OPA client for policy evaluation
        processing_strategy: Custom processing strategy (auto-selected if None)
    """

    def __init__(self, **kwargs: object) -> None:
        self._isolated_mode = kwargs.get("isolated_mode", False)
        self.config = kwargs.get("config") or BusConfiguration.from_environment()
        self._use_dynamic_policy = (
            kwargs.get("use_dynamic_policy", self.config.use_dynamic_policy)
            and POLICY_CLIENT_AVAILABLE
            and not self._isolated_mode
        )
        self._policy_fail_closed = kwargs.get("policy_fail_closed", self.config.policy_fail_closed)
        self._use_rust = kwargs.get("use_rust", True)
        self._enable_metering = kwargs.get("enable_metering", True)
        cache_hash_mode = kwargs.get("cache_hash_mode", DEFAULT_CACHE_HASH_MODE)
        if not isinstance(cache_hash_mode, str) or cache_hash_mode not in _CACHE_HASH_MODES:
            raise ValueError(f"Invalid cache_hash_mode: {cache_hash_mode}")
        self._cache_hash_mode = cast(Literal["sha256", "fast"], cache_hash_mode)
        self._handlers: JSONDict = {}
        self._processed_count, self._failed_count = 0, 0
        self._background_tasks: set[asyncio.Task[object]] = set()
        self._metering_hooks = kwargs.get("metering_hooks") or (
            get_metering_hooks()
            if (self._enable_metering and METERING_AVAILABLE and not self._isolated_mode)
            else None
        )
        self._enable_maci = kwargs.get("enable_maci", True) and not self._isolated_mode
        self._maci_registry, self._maci_enforcer, self._maci_strict_mode = (
            kwargs.get("maci_registry"),
            kwargs.get("maci_enforcer"),
            kwargs.get("maci_strict_mode", True),
        )
        self._rust_processor = (
            rust_bus.MessageProcessor() if (USE_RUST and rust_bus and self._use_rust) else None
        )
        self._policy_client = (
            get_policy_client(fail_closed=self._policy_fail_closed)
            if self._use_dynamic_policy
            else None
        )
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._audit_client = kwargs.get("audit_client")
        self._opa_client = None
        if not self._isolated_mode:
            try:
                self._opa_client = get_opa_client()
            except Exception:
                logger.debug("OPA client unavailable during message processor initialization")
        self._constitutional_verifier = kwargs.get("constitutional_verifier")
        # OPTIMIZATION: Increased cache size from 1000 to 10000 for enterprise scale
        # At 6,471 RPS, 1000 entries caused high cache churn (~seconds to evict)
        self._validation_cache: object = LRUCache(maxsize=DEFAULT_LRU_CACHE_SIZE)

        # SDPC Phase 2/3 Verifiers
        from enhanced_agent_bus.builder import build_pqc_service, build_sdpc_verifiers

        sdpc = build_sdpc_verifiers(self.config)
        self.intent_classifier = kwargs.get("intent_classifier", sdpc.intent_classifier)
        self.asc_verifier = kwargs.get("asc_verifier", sdpc.asc_verifier)
        self.graph_check = kwargs.get("graph_check", sdpc.graph_check)
        self.pacar_verifier = kwargs.get("pacar_verifier", sdpc.pacar_verifier)
        self.evolution_controller = kwargs.get("evolution_controller", sdpc.evolution_controller)
        self.ampo_engine = kwargs.get("ampo_engine", sdpc.ampo_engine)
        self._IntentType = sdpc.IntentType

        # PQC Integration (Phase 4 - Constitutional Validation Integration)
        self._enable_pqc = kwargs.get("enable_pqc", self.config.enable_pqc)
        self._pqc_service = kwargs.get("pqc_service")
        self._pqc_config = None

        if self._enable_pqc and not self._pqc_service:
            self._pqc_service = build_pqc_service(self.config)
            if not self._pqc_service:
                self._enable_pqc = False

        if self._pqc_service:
            self._pqc_config = getattr(self._pqc_service, "config", None)

        self._processing_strategy = (
            kwargs.get("processing_strategy") or self._auto_select_strategy()
        )
        if CIRCUIT_BREAKER_ENABLED:
            self._process_cb = get_circuit_breaker(
                "message_processor",
                CircuitBreakerConfig(
                    fail_max=DEFAULT_CB_FAIL_MAX, reset_timeout=DEFAULT_CB_RESET_TIMEOUT
                ),
            )

        # Session governance integration (Phase 3)
        self._enable_session_governance = (
            self.config.enable_session_governance and not self._isolated_mode
        )
        self._session_context_manager: SessionContextManager | None = None
        if self._enable_session_governance:
            try:
                # Initialize session context manager with config TTL
                self._session_context_manager = SessionContextManager(
                    cache_size=1000,
                    cache_ttl=self.config.session_policy_cache_ttl,
                )
                logger.info("Session governance enabled for message processor")
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
                logger.warning(f"Failed to initialize session context manager: {e}")
                self._enable_session_governance = False

        # Session resolution metrics (GIL-protected, no lock needed for simple increments)
        self._session_resolved_count = 0
        self._session_not_found_count = 0
        self._session_error_count = 0
        self._require_independent_validator = kwargs.get(
            "require_independent_validator",
            getattr(self.config, "require_independent_validator", False),
        )
        self._independent_validator_threshold = float(
            kwargs.get(
                "independent_validator_threshold",
                getattr(
                    self.config,
                    "independent_validator_threshold",
                    IMPACT_DELIBERATION_THRESHOLD,
                ),
            )
        )
        self._agent_workflow_metrics = (
            get_agent_workflow_metrics_collector() if AGENT_WORKFLOW_METRICS_AVAILABLE else None
        )
        self._session_resolver = kwargs.get("session_resolver") or SessionContextResolver(
            config=self.config,
            manager=self._session_context_manager,
        )
        self._security_scanner = kwargs.get("security_scanner") or MessageSecurityScanner()
        self._verification_orchestrator = kwargs.get("verification_orchestrator")
        if self._verification_orchestrator is None:
            self._verification_orchestrator = VerificationOrchestrator(
                config=self.config,
                enable_pqc=self._enable_pqc,
            )
        self._verification_orchestrator.intent_classifier = self.intent_classifier
        self._verification_orchestrator.asc_verifier = self.asc_verifier
        self._verification_orchestrator.graph_check = self.graph_check
        self._verification_orchestrator.pacar_verifier = self.pacar_verifier
        self._verification_orchestrator.evolution_controller = self.evolution_controller
        self._verification_orchestrator.ampo_engine = self.ampo_engine
        self._verification_orchestrator._IntentType = self._IntentType
        self._verification_orchestrator._enable_pqc = self._enable_pqc
        self._verification_orchestrator._pqc_service = self._pqc_service
        self._verification_orchestrator._pqc_config = self._pqc_config

        # MCP integration — initialised lazily via initialize_mcp(); None until then
        self._mcp_pool: MCPClientPool | None = None  # type: ignore[type-arg]
        if self._cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

    def _record_agent_workflow_event(
        self,
        *,
        event_type: str,
        msg: AgentMessage,
        reason: str,
    ) -> None:
        """Best-effort workflow telemetry emission without blocking processing."""
        collector = getattr(self, "_agent_workflow_metrics", None)
        if collector is None:
            return
        try:
            collector.record_event(
                event_type=event_type,
                tenant_id=getattr(msg, "tenant_id", "default") or "default",
                source=getattr(msg, "from_agent", "unknown") or "unknown",
                reason=reason,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            logger.debug("Agent workflow telemetry emission failed", exc_info=True)

    def _auto_select_strategy(self) -> ProcessingStrategy:
        from enhanced_agent_bus.processing_strategies import (
            CompositeProcessingStrategy,
            MACIProcessingStrategy,
            OPAProcessingStrategy,
            PythonProcessingStrategy,
            RustProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import (
            ConstitutionalValidationStrategy,
            StaticHashValidationStrategy,
        )

        py_proc = PythonProcessingStrategy(StaticHashValidationStrategy(strict=True))
        if self._isolated_mode:
            return py_proc
        strategies: list[ProcessingStrategy] = []
        if self._rust_processor and self._use_rust:
            strategies.append(RustProcessingStrategy(self._rust_processor, rust_bus))
        if self._use_dynamic_policy and self._opa_client:
            strategies.append(OPAProcessingStrategy(self._opa_client))

        # Add Constitutional Verifier if available
        if self._constitutional_verifier:
            strategies.append(
                PythonProcessingStrategy(
                    StaticHashValidationStrategy(
                        strict=True
                    )  # ConstitutionalValidationStrategy not available as ValidStrategy
                )
            )

        strategies.append(py_proc)
        base = CompositeProcessingStrategy(strategies) if len(strategies) > 1 else strategies[0]
        if self._enable_maci:
            return MACIProcessingStrategy(
                base, self._maci_registry, self._maci_enforcer, self._maci_strict_mode
            )
        return base

    @timed("extract_session_context")
    async def _extract_session_context(self, msg: AgentMessage) -> SessionContext | None:
        """
        Extract and validate session context from message.

        Implements acceptance criteria for subtask 3.2:
        1. Extract session_id from message metadata
        2. Load session context from SessionContextManager
        3. Graceful fallback when session not found
        4. Metrics tracking for session resolution

        Args:
            msg: The agent message to extract session context from

        Returns:
            SessionContext if found and valid, None otherwise
        """
        if not self._enable_session_governance:
            return None

        session_context = await self._session_resolver.resolve(msg)

        resolver_metrics = self._session_resolver.get_metrics()
        self._session_resolved_count = int(resolver_metrics.get("resolved_count", 0))
        self._session_not_found_count = int(resolver_metrics.get("not_found_count", 0))
        self._session_error_count = int(resolver_metrics.get("error_count", 0))

        return session_context  # type: ignore[no-any-return]

    @timed("security_scan")
    async def _perform_security_scan(self, msg: AgentMessage) -> ValidationResult | None:
        """
        Perform runtime security scanning on the message.

        Args:
            msg: The agent message to scan.

        Returns:
            ValidationResult if security scan blocked the message, None otherwise.
        """
        security_res = await self._security_scanner.scan(msg)
        if security_res:
            self._failed_count += 1
            return security_res  # type: ignore[no-any-return]
        return None

    def _requires_independent_validation(self, msg: AgentMessage) -> bool:
        """Determine whether the message must include independent validation evidence."""
        impact_score = getattr(msg, "impact_score", 0.0)
        if impact_score is None:
            impact_score = 0.0
        if impact_score >= self._independent_validator_threshold:
            return True
        return msg.message_type in {
            MessageType.CONSTITUTIONAL_VALIDATION,
            MessageType.GOVERNANCE_REQUEST,
        }

    def _enforce_independent_validator_gate(self, msg: AgentMessage) -> ValidationResult | None:
        """Enforce independent-validator metadata for high-risk messages."""
        if not self._require_independent_validator:
            return None
        if not self._requires_independent_validation(msg):
            return None
        self._record_agent_workflow_event(
            event_type="intervention",
            msg=msg,
            reason="independent_validator_required",
        )

        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
        validator_id = metadata.get("validated_by_agent") or metadata.get(
            "independent_validator_id"
        )
        validation_stage = metadata.get("validation_stage")

        if not isinstance(validator_id, str) or not validator_id.strip():
            self._record_agent_workflow_event(
                event_type="gate_failure",
                msg=msg,
                reason="independent_validator_missing",
            )
            return ValidationResult(
                is_valid=False,
                errors=["Independent validator metadata is required for this message"],
                metadata={"rejection_reason": "independent_validator_missing"},
            )

        if validator_id == msg.from_agent:
            self._record_agent_workflow_event(
                event_type="gate_failure",
                msg=msg,
                reason="independent_validator_self_validation",
            )
            return ValidationResult(
                is_valid=False,
                errors=["Independent validator must not be the originating agent"],
                metadata={"rejection_reason": "independent_validator_self_validation"},
            )

        if validation_stage is not None and validation_stage != "independent":
            self._record_agent_workflow_event(
                event_type="gate_failure",
                msg=msg,
                reason="independent_validator_invalid_stage",
            )
            return ValidationResult(
                is_valid=False,
                errors=[
                    "validation_stage must be 'independent' when validator evidence is present"
                ],
                metadata={"rejection_reason": "independent_validator_invalid_stage"},
            )
        return None

    def _enforce_autonomy_tier(self, msg: AgentMessage) -> ValidationResult | None:
        """Enforce autonomy tier restrictions on messages (ACGS-AI-007).

        Rules:
        - ADVISORY: Can only send non-command messages (queries, events, etc.)
        - BOUNDED: Default tier — allowed for all message types (other policies still apply)
        - HUMAN_APPROVED: Requires validated_by_agent metadata evidence
        - UNRESTRICTED: Allowed for all (requires explicit grant)
        - None (unset): No autonomy tier restrictions applied

        Returns:
            ValidationResult rejection if tier rules are violated, None otherwise.
        """
        return enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=_ADVISORY_BLOCKED_TYPES)

    def _extract_message_session_id(self, msg: AgentMessage) -> str | None:
        """
        Extract session_id from message for multi-turn PACAR context tracking.

        Priority: session_id field > headers > content > payload.

        Args:
            msg: The agent message to extract session_id from.

        Returns:
            Session ID string if found, None otherwise.
        """
        return extract_session_id_for_pacar(msg)  # type: ignore[no-any-return]

    @timed("sdpc_verification")
    async def _perform_sdpc_verification(
        self, msg: AgentMessage, content_str: str
    ) -> tuple[JSONDict, JSONDict]:
        """Perform SDPC verification via the VerificationOrchestrator component."""
        return await self._verification_orchestrator._perform_sdpc(msg, content_str)  # type: ignore[no-any-return]

    @timed("pqc_validation")
    async def _perform_pqc_validation(
        self, msg: AgentMessage, sdpc_metadata: JSONDict
    ) -> ValidationResult | None:
        """Perform PQC validation via the VerificationOrchestrator component."""
        pqc_result, pqc_metadata = await self._verification_orchestrator.verify_pqc(msg)
        if pqc_metadata:
            sdpc_metadata.update(pqc_metadata)
        if pqc_result:
            self._failed_count += 1
        return pqc_result  # type: ignore[no-any-return]

    @timed("message_process")
    async def process(self, msg: AgentMessage, max_retries: int = 3) -> ValidationResult:
        """Process a message through constitutional validation pipeline with retry logic.

        Implements exponential backoff with jitter for transient failures.

        Args:
            msg: The agent message to process.
            max_retries: Maximum number of retry attempts (default 3).

        Returns:
            ValidationResult containing validation status and metadata.
        """
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                if CIRCUIT_BREAKER_ENABLED:
                    return await self._process_cb.call(self._do_process, msg)  # type: ignore[no-any-return]
                return await self._do_process(msg)
            except asyncio.CancelledError:
                raise
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as e:
                last_err = e
                if attempt < max_retries - 1:
                    base_wait = 0.1 * (2**attempt)
                    jitter = random.uniform(0, base_wait * 0.5)
                    wait = base_wait + jitter
                    logger.warning(
                        f"Process attempt {attempt + 1}/{max_retries} "
                        f"failed: {e}, retrying in {wait:.2f}s"
                    )
                    await asyncio.sleep(wait)
        logger.error(f"Message processing failed after {max_retries} attempts")
        return ValidationResult(
            is_valid=False,
            errors=[f"Processing failed after {max_retries} retries: {last_err}"],
            metadata={"rejection_reason": "max_retries_exceeded"},
        )

    @timed("message_do_process")
    async def _do_process(self, msg: AgentMessage) -> ValidationResult:
        """
        Process a message through constitutional validation pipeline.

        Pipeline stages:
        1. Memory profiling context setup
        2. Session context extraction and attachment
        3. Security scanning (early return if blocked)
        4. Cache check (early return if cached)
        5. Parallel SDPC and PQC verification
        6. Strategy-based processing
        7. Result caching and metrics

        Args:
            msg: The agent message to process.

        Returns:
            ValidationResult with validation status and metadata.
        """
        start = time.perf_counter()

        async with self._setup_memory_profiling_context(msg):
            # Phase 1: Extract and attach session context for governance
            await self._attach_session_context(msg)

            # Phase 2: Run validation gates (early returns)
            gate_result = await self._run_validation_gates(msg)
            if gate_result:
                return gate_result

        # Phase 3: Check validation cache
        cache_key = self._compute_cache_key(msg)
        cached = self._validation_cache.get(cache_key)
        if cached:
            return cached  # type: ignore[no-any-return]

        # Phase 4-6: Verification and processing
        return await self._execute_verification_and_processing(msg, cache_key, start)

    def _setup_memory_profiling_context(self, msg: AgentMessage) -> AbstractContextManager[None]:
        """set up memory profiling context for message processing."""
        profiler = get_memory_profiler()
        operation_name = f"message_processing_{msg.message_type.value}_{msg.priority.value}"
        return (
            profiler.profile_async(operation_name, trace_id=msg.message_id)
            if profiler and profiler.config.enabled
            else nullcontext()
        )

    async def _attach_session_context(self, msg: AgentMessage) -> None:
        """Extract and attach session context to message."""
        session_context = await self._extract_session_context(msg)
        if session_context:
            if hasattr(msg, "session_context"):
                msg.session_context = session_context  # type: ignore[assignment]
            if hasattr(msg, "session_id") and not msg.session_id:
                msg.session_id = session_context.session_id
            logger.debug(
                f"Attached session context to message {msg.message_id}: "
                f"session_id={session_context.session_id}"
            )

    def _increment_failed_count(self) -> None:
        self._failed_count += 1

    async def _run_validation_gates(self, msg: AgentMessage) -> ValidationResult | None:
        return await run_message_validation_gates(
            msg=msg,
            autonomy_gate=self._enforce_autonomy_tier,
            security_scan=self._perform_security_scan,
            independent_validator_gate=self._enforce_independent_validator_gate,
            prompt_injection_gate=self._detect_prompt_injection,
            increment_failure=self._increment_failed_count,
        )

    def _compute_cache_key(self, msg: AgentMessage) -> str:
        """Compute SHA-256 cache key with security dimensions for tenant isolation."""
        return compute_message_cache_key(
            msg,
            cache_hash_mode=self._cache_hash_mode,
            fast_hash_available=FAST_HASH_AVAILABLE,
            fast_hash_func=fast_hash if FAST_HASH_AVAILABLE else None,
        )

    async def _execute_verification_and_processing(
        self, msg: AgentMessage, cache_key: str, start_time: float
    ) -> ValidationResult:
        """Execute verification orchestration and strategy processing."""
        # Run verification orchestration
        content_str = prepare_message_content_string(msg)
        verification_result = await self._verification_orchestrator.verify(msg, content_str)

        # Merge verification metadata
        sdpc_metadata = merge_verification_metadata(
            verification_result.sdpc_metadata,
            verification_result.pqc_metadata,
        )

        # Check for PQC verification failure
        pqc_failure_result = extract_pqc_failure_result(verification_result)
        if pqc_failure_result:
            self._failed_count += 1
            return pqc_failure_result  # type: ignore[no-any-return]

        # Strategy-based processing
        res = await self._processing_strategy.process(msg, self._handlers)
        res.metadata.update(sdpc_metadata)

        # Calculate latency and handle results
        latency_ms = (time.perf_counter() - start_time) * 1000
        apply_latency_metadata(res, latency_ms)

        if res.is_valid:
            await self._handle_successful_processing(msg, res, cache_key, latency_ms)
        else:
            await self._handle_failed_processing(msg, res)

        return res  # type: ignore[no-any-return]

    async def _handle_successful_processing(
        self, msg: AgentMessage, result: ValidationResult, cache_key: str, latency_ms: float
    ) -> None:
        """Handle successful message processing with caching and metrics."""
        self._validation_cache.set(cache_key, result)
        self._processed_count += 1

        if not self._requires_independent_validation(msg):
            self._record_agent_workflow_event(
                event_type="autonomous_action",
                msg=msg,
                reason="no_independent_validation_required",
            )

        if self._metering_hooks:
            schedule_background_task(
                self._async_metering_callback(msg, latency_ms), self._background_tasks
            )

    async def _handle_failed_processing(self, msg: AgentMessage, result: ValidationResult) -> None:
        """Handle failed message processing with DLQ and metrics."""
        self._failed_count += 1
        rejection_reason = self._extract_rejection_reason(result)

        self._record_agent_workflow_event(
            event_type="gate_failure",
            msg=msg,
            reason=rejection_reason,
        )

        if msg.priority == Priority.CRITICAL:
            self._record_agent_workflow_event(
                event_type="rollback_trigger",
                msg=msg,
                reason="critical_message_rejected",
            )

        schedule_background_task(self._send_to_dlq(msg, result), self._background_tasks)

    @staticmethod
    def _extract_rejection_reason(result: ValidationResult) -> str:
        """Extract rejection reason from validation result metadata."""
        return extract_rejection_reason(result)

    async def _async_metering_callback(self, msg: AgentMessage, lat: float) -> None:
        """Asynchronous wrapper for metering callback to prevent latency spikes."""
        try:
            self._metering_hooks.on_constitutional_validation(
                tenant_id=msg.tenant_id, agent_id=msg.from_agent, is_valid=True, latency_ms=lat
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.warning(f"Metering callback failed: {e}")

    async def _get_dlq_redis(self) -> object:
        """Get or create a cached Redis client for DLQ writes."""
        if getattr(self, "_dlq_redis", None) is not None:
            return self._dlq_redis
        import redis.asyncio as aioredis

        redis_url = getattr(self, "_redis_url", None) or "redis://localhost:6379/0"
        self._dlq_redis = aioredis.from_url(redis_url, decode_responses=True)
        return self._dlq_redis

    async def _send_to_dlq(self, msg: AgentMessage, result: ValidationResult) -> None:
        """Send failed message to dead letter queue via cached Redis client."""
        try:
            import json

            client = await self._get_dlq_redis()
            dlq_entry = build_dlq_entry(msg, result, time.time())
            await client.lpush("acgs:dlq:messages", json.dumps(dlq_entry))
            await client.ltrim("acgs:dlq:messages", 0, 9999)
            logger.info("dlq_message_stored", message_id=msg.message_id)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.warning(f"DLQ write failed (non-fatal): {e}")
            self._dlq_redis = None

    def _detect_prompt_injection(self, msg: AgentMessage) -> ValidationResult | None:
        return self._security_scanner.detect_prompt_injection(msg)  # type: ignore[no-any-return]

    @property
    def processed_count(self) -> int:
        """Get the total count of successfully processed messages.

        Returns:
            Number of messages processed successfully.
        """
        return self._processed_count

    @property
    def failed_count(self) -> int:
        """Get the total count of failed message processing attempts.

        Returns:
            Number of messages that failed validation or processing.
        """
        return self._failed_count

    @property
    def processing_strategy(self) -> ProcessingStrategy:
        """Get the current message processing strategy.

        Returns:
            The active ProcessingStrategy instance.
        """
        return self._processing_strategy

    @property
    def opa_client(self) -> object | None:
        """Get the OPA client instance for policy evaluation.

        Returns:
            OPA client instance or None if not initialized.
        """
        return self._opa_client  # type: ignore[no-any-return]

    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], Coroutine[object, object, AgentMessage | None]],
    ) -> None:
        """Register a message handler for a specific message type.

        Args:
            message_type: The MessageType to handle.
            handler: Async callable that processes messages of this type.
        """
        if message_type not in self._handlers:
            self._handlers[message_type] = []  # type: ignore[index]
        self._handlers[message_type].append(handler)  # type: ignore[index]

    def unregister_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], Coroutine[object, object, AgentMessage | None]],
    ) -> bool:
        """Unregister a message handler for a specific message type.

        Args:
            message_type: The MessageType to stop handling.
            handler: The handler to remove.

        Returns:
            True if handler was found and removed, False otherwise.
        """
        if message_type in self._handlers and handler in self._handlers[message_type]:  # type: ignore[index]
            self._handlers[message_type].remove(handler)  # type: ignore[index]
            return True
        return False

    def get_metrics(self) -> JSONDict:
        """Get message processor metrics and statistics.

        Returns:
            Dictionary containing processed count, failed count, success rate,
            strategy information, and feature flags.
        """
        total = self._processed_count + self._failed_count
        success_rate = self._processed_count / max(1, total) if total > 0 else 0.0

        # Calculate session resolution metrics
        session_resolution_rate = calculate_session_resolution_rate(
            self._session_resolved_count,
            self._session_not_found_count,
            self._session_error_count,
        )

        metrics = {
            "processed_count": self._processed_count,
            "failed_count": self._failed_count,
            "success_rate": success_rate,
            "rust_enabled": self._use_rust and self._rust_processor is not None,
            "dynamic_policy_enabled": self._use_dynamic_policy,
            "opa_enabled": self._opa_client is not None,
            "processing_strategy": (
                self._processing_strategy.get_name() if self._processing_strategy else "none"
            ),
            "metering_enabled": self._enable_metering and self._metering_hooks is not None,
            "pqc_enabled": self._enable_pqc,
            "pqc_mode": self._pqc_config.pqc_mode if self._pqc_config else None,
            "pqc_verification_mode": (
                self._pqc_config.verification_mode if self._pqc_config else None
            ),
            "pqc_migration_phase": self._pqc_config.migration_phase if self._pqc_config else None,
        }

        # Add session governance metrics
        apply_session_governance_metrics(
            metrics,
            enabled=self._enable_session_governance,
            resolved_count=self._session_resolved_count,
            not_found_count=self._session_not_found_count,
            error_count=self._session_error_count,
            resolution_rate=session_resolution_rate,
        )

        enrich_metrics_with_opa_stats(metrics, self._opa_client)

        collector = getattr(self, "_agent_workflow_metrics", None)
        if collector is not None and not enrich_metrics_with_workflow_telemetry(metrics, collector):
            logger.debug("Unable to enrich metrics with workflow telemetry", exc_info=True)

        return metrics

    def _set_strategy(self, strategy: ProcessingStrategy) -> None:
        self._processing_strategy = strategy

    def _log_decision(
        self, msg: AgentMessage, result: ValidationResult, span: object = None
    ) -> None:
        logger.info(f"Decision for {msg.message_id}: {result.is_valid}")
        if span and hasattr(span, "set_attribute"):
            span.set_attribute("msg.id", msg.message_id)
            span.set_attribute("msg.valid", result.is_valid)
            if hasattr(span, "get_span_context"):
                ctx = span.get_span_context()
                if hasattr(ctx, "trace_id"):
                    logger.info(f"Trace ID: {ctx.trace_id:x}")

    def _get_compliance_tags(self, msg: AgentMessage, result: ValidationResult) -> list[str]:
        tags = ["constitutional_validated"]
        if result.is_valid:
            tags.append("approved")
        else:
            tags.append("rejected")
        if hasattr(msg, "priority") and msg.priority == Priority.CRITICAL:
            tags.append("high_priority")
        return tags

    # ------------------------------------------------------------------
    # MCP Integration
    # ------------------------------------------------------------------

    async def initialize_mcp(self, config: object) -> None:
        """Initialise the MCP client pool from a config object.

        Registers Neural-MCP and Toolbox clients found in *config* and
        eagerly connects them.  No-ops when the ``MCP_ENABLED`` feature
        flag is ``False`` or when MCP dependencies are not installed.

        Args:
            config: An :class:`~packages.enhanced_agent_bus.mcp.MCPConfig`
                instance describing the servers to register.  A plain
                ``dict`` is also accepted and converted automatically.
        """
        if not MCP_ENABLED:
            logger.info("mcp_initialize_skipped_feature_flag_disabled")
            return

        if not _MCP_AVAILABLE:
            logger.warning(
                "mcp_initialize_skipped_dependencies_unavailable",
                detail="Install optional MCP dependencies to enable MCP support.",
            )
            return

        # Normalise plain dict → MCPConfig
        mcp_config: MCPConfig  # type: ignore[type-arg]
        if isinstance(config, dict):
            try:
                mcp_config = MCPConfig(**config)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                logger.error("mcp_initialize_invalid_config_dict", error=str(exc))
                return
        elif isinstance(config, MCPConfig):  # type: ignore[arg-type]
            mcp_config = config  # type: ignore[assignment]
        else:
            logger.error(
                "mcp_initialize_invalid_config_type",
                config_type=type(config).__name__,
            )
            return

        if not mcp_config.enabled:
            logger.info("mcp_initialize_skipped_config_disabled")
            return

        pool: MCPClientPool = MCPClientPool()  # type: ignore[misc]

        for srv in mcp_config.servers:
            if not srv.enabled:
                logger.info("mcp_server_skipped_disabled", server_name=srv.name)
                continue

            # Map MCPServerConfig → MCPClientConfig → MCPClient
            server_url: str = srv.url or "stdio"
            client_cfg: MCPClientConfig = MCPClientConfig(  # type: ignore[misc]
                server_url=server_url,
                server_id=srv.name,
                call_timeout=srv.timeout,
                metadata={"transport": srv.transport},
            )
            client: MCPClient = MCPClient(config=client_cfg)  # type: ignore[misc]
            pool.register_client(client)
            logger.info(
                "mcp_server_registered",
                server_name=srv.name,
                transport=srv.transport,
                server_url=server_url,
            )

        await pool.connect_all()
        self._mcp_pool = pool

        logger.info(
            "mcp_pool_initialized",
            total_clients=pool.client_count,
            constitutional_hash=self.constitutional_hash,
        )

    async def handle_tool_request(
        self,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, object] | None = None,
    ) -> object:
        """Dispatch an MCP tool request on behalf of an agent.

        Fetches the agent's MACI role from the registry, enforces
        constitutional separation-of-powers via the pool's MACI gate, then
        forwards the call to the appropriate MCP server.

        Args:
            agent_id: ID of the requesting agent (used for MACI role lookup
                and audit trail).
            tool_name: Name of the MCP tool to invoke.
            arguments: Input arguments for the tool.  Defaults to ``{}``.

        Returns:
            :class:`~packages.enhanced_agent_bus.mcp.types.MCPToolResult`
            describing the outcome.  Returns an error result (not an
            exception) when MCP is not available or not initialised.
        """
        if not _MCP_AVAILABLE or MCPToolResult is None:
            logger.warning(
                "handle_tool_request_mcp_unavailable",
                agent_id=agent_id,
                tool_name=tool_name,
            )
            # Return a lightweight error dict when MCPToolResult type is absent
            return {
                "tool_name": tool_name,
                "status": "error",
                "error": "MCP dependencies not available",
                "agent_id": agent_id,
                "maci_role": "",
                "constitutional_hash": self.constitutional_hash,
            }

        if self._mcp_pool is None:
            logger.warning(
                "handle_tool_request_pool_not_initialized",
                agent_id=agent_id,
                tool_name=tool_name,
                hint="Call initialize_mcp(config) before invoking handle_tool_request.",
            )
            return MCPToolResult.error_result(  # type: ignore[union-attr]
                tool_name,
                "MCP pool not initialised — call initialize_mcp(config) first",
                agent_id=agent_id,
            )

        # Look up agent MACI role from the registry (async; handles None gracefully)
        maci_role: str = ""
        if self._maci_registry is not None:
            try:
                agent_record = await self._maci_registry.get_agent(agent_id)
                if agent_record is not None:
                    maci_role = agent_record.role.value
                    logger.debug(
                        "handle_tool_request_maci_role_resolved",
                        agent_id=agent_id,
                        maci_role=maci_role,
                    )
                else:
                    logger.debug(
                        "handle_tool_request_agent_not_in_registry",
                        agent_id=agent_id,
                        fallback="no MACI role enforcement for this call",
                    )
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                logger.warning(
                    "handle_tool_request_registry_lookup_failed",
                    agent_id=agent_id,
                    error=str(exc),
                    fallback="proceeding without MACI role",
                )

        result = await self._mcp_pool.call_tool(
            tool_name,
            arguments=arguments,
            agent_id=agent_id,
            agent_role=maci_role,
        )

        logger.info(
            "handle_tool_request_complete",
            agent_id=agent_id,
            tool_name=tool_name,
            maci_role=maci_role,
            status=result.status.value,
            constitutional_hash=self.constitutional_hash,
        )
        return result
