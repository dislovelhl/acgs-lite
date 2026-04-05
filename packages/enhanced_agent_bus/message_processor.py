"""
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import copy
import hashlib
import random
import time
from collections.abc import Callable, Coroutine
from contextlib import AbstractContextManager, nullcontext
from typing import Literal, cast

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Local imports
from .config import BusConfiguration
from .dependency_bridge import get_dependency, get_feature_flags, is_feature_available
from .gate_coordinator import GateCoordinator
from .governance_constants import (
    DEFAULT_CB_FAIL_MAX,
    DEFAULT_CB_RESET_TIMEOUT,
    DEFAULT_LRU_CACHE_SIZE,
    IMPACT_DELIBERATION_THRESHOLD,
)
from .governance_coordinator import GovernanceCoordinator
from .governance_core import (
    GovernanceDecision,
    GovernanceInput,
    GovernanceReceipt,
    LegacyGovernanceCore,
    SwarmGovernanceCore,
    normalize_governance_core_mode,
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
    from enhanced_agent_bus._compat.circuit_breaker import (
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

try:
    from .opa_client import OPAClient as _OPAClient
except ImportError:
    _OPAClient = None  # type: ignore[assignment]


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

from .interfaces import ProcessingStrategy
from .memory_profiler import ProfilingLevel, get_memory_profiler
from .message_processor_components import (
    compute_message_cache_key,
    enforce_autonomy_tier_rules,
    enrich_metrics_with_opa_stats,
    enrich_metrics_with_workflow_telemetry,
    extract_rejection_reason,
    extract_session_id_for_pacar,
    schedule_background_task,
)
from .models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    AutonomyTier,
    MessageStatus,
    MessageType,
    Priority,
    get_enum_value,
)
from .performance_monitor import timed
from .processing_context import MessageProcessingContext
from .result_finalizer import ResultFinalizer
from .runtime_security import get_runtime_security_scanner
from .security_scanner import (
    PROMPT_INJECTION_PATTERNS,
    MessageSecurityScanner,
)
from .session_context import SessionContext, SessionContextManager
from .session_context_resolver import SessionContextResolver
from .session_coordinator import SessionCoordinator
from .utils import LRUCache
from .validators import ValidationResult
from .verification_coordinator import VerificationCoordinator
from .verification_orchestrator import (
    VerificationOrchestrator,
    VerificationRuntimeDependencies,
)

logger = get_logger(__name__)
DEFAULT_CACHE_HASH_MODE = "sha256"
_CACHE_HASH_MODES = {"sha256", "fast"}

try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

try:
    from enhanced_agent_bus._compat.agent_workflow_metrics import (
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
        self._governance_core_mode = normalize_governance_core_mode(
            kwargs.get(
                "governance_core_mode",
                getattr(self.config, "governance_core_mode", "legacy"),
            )
        )
        self._governance_peer_validation_enabled = bool(
            kwargs.get(
                "governance_swarm_peer_validation_enabled",
                getattr(self.config, "governance_swarm_peer_validation_enabled", True),
            )
        )
        self._governance_manifold_enabled = bool(
            kwargs.get(
                "governance_swarm_use_manifold",
                getattr(self.config, "governance_swarm_use_manifold", False),
            )
        )
        self._legacy_governance_core = LegacyGovernanceCore(
            expected_constitutional_hash=self.constitutional_hash
        )
        self._swarm_governance_core = kwargs.get("governance_core") or SwarmGovernanceCore(
            expected_constitutional_hash=self.constitutional_hash,
            enable_peer_validation=self._governance_peer_validation_enabled,
            use_manifold=self._governance_manifold_enabled,
        )
        self._audit_client = kwargs.get("audit_client")
        self._workflow_repository = kwargs.get("workflow_repository")
        self._opa_client = self._initialize_opa_client()
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

        self._configure_pqc(build_pqc_service)

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
        requested_session_governance = (
            self.config.enable_session_governance and not self._isolated_mode
        )
        (
            self._enable_session_governance,
            self._session_context_manager,
        ) = SessionCoordinator.initialize_runtime(
            self.config,
            enable_session_governance=requested_session_governance,
        )

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
        self._session_resolver = kwargs.get(
            "session_resolver"
        ) or SessionCoordinator.build_session_resolver(
            self.config,
            self._session_context_manager,
        )
        self._session_coordinator = kwargs.get("session_coordinator") or SessionCoordinator(
            enable_session_governance=self._enable_session_governance,
            session_context_manager=self._session_context_manager,
            session_resolver=self._session_resolver,
            session_resolved_count=self._session_resolved_count,
            session_not_found_count=self._session_not_found_count,
            session_error_count=self._session_error_count,
        )
        self._security_scanner = kwargs.get("security_scanner") or MessageSecurityScanner()
        self._gate_coordinator = kwargs.get("gate_coordinator") or GateCoordinator(
            require_independent_validator=self._require_independent_validator,
            independent_validator_threshold=self._independent_validator_threshold,
            security_scanner=self._security_scanner,
            record_agent_workflow_event=self._record_agent_workflow_event,
            increment_failed_count=self._increment_failed_count,
            advisory_blocked_types=_ADVISORY_BLOCKED_TYPES,
        )
        self._verification_orchestrator = self._build_verification_orchestrator(
            kwargs.get("verification_orchestrator")
        )
        self._governance_coordinator = kwargs.get(
            "governance_coordinator"
        ) or GovernanceCoordinator(
            governance_core_mode=self._governance_core_mode,
            constitutional_hash=self.constitutional_hash,
            require_independent_validator=self._require_independent_validator,
            requires_independent_validation=self._gate_coordinator.requires_independent_validation,
            legacy_governance_core=self._legacy_governance_core,
            swarm_governance_core=self._swarm_governance_core,
            increment_failed_count=self._increment_failed_count,
        )
        self._result_finalizer = kwargs.get("result_finalizer") or ResultFinalizer()
        self._verification_coordinator = kwargs.get(
            "verification_coordinator"
        ) or VerificationCoordinator(
            verification_orchestrator=self._verification_orchestrator,
            processing_strategy=self._processing_strategy,
            handlers=self._handlers,
            attach_governance_metadata=lambda context, result: (
                self._governance_coordinator.attach_governance_metadata(
                    context=context,
                    result=result,
                )
            ),
            increment_failed_count=self._increment_failed_count,
            handle_successful_processing=self._handle_successful_processing,
            handle_failed_processing=self._handle_failed_processing,
        )

        # MCP integration — initialised lazily via initialize_mcp(); None until then
        self._mcp_pool: MCPClientPool | None = None  # type: ignore[type-arg]
        if self._cache_hash_mode == "fast" and not FAST_HASH_AVAILABLE:
            logger.warning(
                "cache_hash_mode=fast requested but acgs2_perf.fast_hash unavailable; "
                "falling back to sha256"
            )

    def _initialize_opa_client(self) -> object | None:
        if self._isolated_mode:
            return None
        try:
            return get_opa_client()
        except Exception:
            if _OPAClient is not None:
                try:
                    return _OPAClient()
                except Exception:
                    logger.debug("OPA client unavailable during message processor initialization")
                    return None
            logger.debug("OPA client unavailable during message processor initialization")
            return None

    def _configure_pqc(
        self,
        build_pqc_service_func: Callable[[BusConfiguration], object | None],
    ) -> None:
        if self._enable_pqc and not self._pqc_service:
            self._pqc_service = build_pqc_service_func(self.config)
            if not self._pqc_service:
                self._enable_pqc = False

        if self._pqc_service:
            self._pqc_config = getattr(self._pqc_service, "config", None)

    def _build_verification_orchestrator(
        self,
        orchestrator: object | None,
    ) -> VerificationOrchestrator:
        verification_orchestrator = orchestrator
        if verification_orchestrator is None:
            verification_orchestrator = VerificationOrchestrator(
                config=self.config,
                enable_pqc=self._enable_pqc,
            )
        runtime_dependencies = self._build_verification_runtime_dependencies()
        configure_runtime_dependencies = getattr(
            type(verification_orchestrator),
            "configure_runtime_dependencies",
            None,
        )
        if callable(configure_runtime_dependencies):
            configure_runtime_dependencies(verification_orchestrator, runtime_dependencies)
        else:
            self._apply_verification_runtime_dependencies_legacy(
                verification_orchestrator,
                runtime_dependencies,
            )
        return verification_orchestrator  # type: ignore[return-value]

    def _build_verification_runtime_dependencies(self) -> VerificationRuntimeDependencies:
        return VerificationRuntimeDependencies(
            intent_classifier=self.intent_classifier,
            asc_verifier=self.asc_verifier,
            graph_check=self.graph_check,
            pacar_verifier=self.pacar_verifier,
            evolution_controller=self.evolution_controller,
            ampo_engine=self.ampo_engine,
            intent_type=self._IntentType,
            enable_pqc=self._enable_pqc,
            pqc_service=self._pqc_service,
            pqc_config=self._pqc_config,
        )

    @staticmethod
    def _apply_verification_runtime_dependencies_legacy(
        verification_orchestrator: object,
        runtime_dependencies: VerificationRuntimeDependencies,
    ) -> None:
        verification_orchestrator.intent_classifier = runtime_dependencies.intent_classifier
        verification_orchestrator.asc_verifier = runtime_dependencies.asc_verifier
        verification_orchestrator.graph_check = runtime_dependencies.graph_check
        verification_orchestrator.pacar_verifier = runtime_dependencies.pacar_verifier
        verification_orchestrator.evolution_controller = runtime_dependencies.evolution_controller
        verification_orchestrator.ampo_engine = runtime_dependencies.ampo_engine
        verification_orchestrator._IntentType = runtime_dependencies.intent_type
        verification_orchestrator._enable_pqc = runtime_dependencies.enable_pqc
        verification_orchestrator._pqc_service = runtime_dependencies.pqc_service
        verification_orchestrator._pqc_config = runtime_dependencies.pqc_config

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
        base = self._build_base_processing_strategy(
            default_strategy=py_proc,
            composite_strategy_cls=CompositeProcessingStrategy,
            rust_strategy_cls=RustProcessingStrategy,
            opa_strategy_cls=OPAProcessingStrategy,
            python_strategy_cls=PythonProcessingStrategy,
            static_hash_validation_cls=StaticHashValidationStrategy,
        )
        return self._wrap_processing_strategy_with_maci(
            base_strategy=base,
            maci_strategy_cls=MACIProcessingStrategy,
        )

    def _build_base_processing_strategy(
        self,
        *,
        default_strategy: ProcessingStrategy,
        composite_strategy_cls: type,
        rust_strategy_cls: type,
        opa_strategy_cls: type,
        python_strategy_cls: type,
        static_hash_validation_cls: type,
    ) -> ProcessingStrategy:
        strategies: list[ProcessingStrategy] = []
        if self._rust_processor and self._use_rust:
            strategies.append(rust_strategy_cls(self._rust_processor, rust_bus))
        if self._use_dynamic_policy and self._opa_client:
            strategies.append(opa_strategy_cls(self._opa_client))
        if self._constitutional_verifier:
            strategies.append(
                python_strategy_cls(
                    static_hash_validation_cls(
                        strict=True
                    )  # ConstitutionalValidationStrategy not available as ValidStrategy
                )
            )
        strategies.append(default_strategy)
        return composite_strategy_cls(strategies) if len(strategies) > 1 else strategies[0]

    def _wrap_processing_strategy_with_maci(
        self,
        *,
        base_strategy: ProcessingStrategy,
        maci_strategy_cls: type,
    ) -> ProcessingStrategy:
        if not self._enable_maci:
            return base_strategy
        return maci_strategy_cls(
            base_strategy,
            self._maci_registry,
            self._maci_enforcer,
            self._maci_strict_mode,
        )

    # ------------------------------------------------------------------
    # Transitional facade wrappers
    # ------------------------------------------------------------------
    # These private helpers are kept as compatibility shims for existing tests and
    # downstream monkeypatching. New orchestration should delegate to the extracted
    # coordinator/finalizer components directly.

    def _sync_coordinator_runtime(self) -> None:
        self._session_coordinator.sync_runtime(
            enable_session_governance=self._enable_session_governance,
            session_context_manager=self._session_context_manager,
            session_resolver=self._session_resolver,
            session_resolved_count=self._session_resolved_count,
            session_not_found_count=self._session_not_found_count,
            session_error_count=self._session_error_count,
        )
        self._gate_coordinator.sync_runtime(
            require_independent_validator=self._require_independent_validator,
            independent_validator_threshold=self._independent_validator_threshold,
            security_scanner=self._security_scanner,
            record_agent_workflow_event=self._record_agent_workflow_event,
        )
        self._governance_coordinator.sync_runtime(
            constitutional_hash=self.constitutional_hash,
            require_independent_validator=self._require_independent_validator,
            requires_independent_validation=self._gate_coordinator.requires_independent_validation,
        )
        self._verification_coordinator.sync_runtime(
            verification_orchestrator=self._verification_orchestrator,
            processing_strategy=self._processing_strategy,
            handlers=self._handlers,
            attach_governance_metadata=lambda context, result: (
                self._governance_coordinator.attach_governance_metadata(
                    context=context,
                    result=result,
                )
            ),
            handle_successful_processing=self._handle_successful_processing,
            handle_failed_processing=self._handle_failed_processing,
        )

    def _sync_runtime_state_from_coordinators(self) -> None:
        (
            self._enable_session_governance,
            self._session_context_manager,
            self._session_resolver,
            self._session_resolved_count,
            self._session_not_found_count,
            self._session_error_count,
        ) = self._session_coordinator.export_runtime_state()

    @timed("extract_session_context")
    async def _extract_session_context(self, msg: AgentMessage) -> SessionContext | None:
        """Transitional wrapper around SessionCoordinator.extract_session_context."""
        self._sync_coordinator_runtime()
        session_context = await self._session_coordinator.extract_session_context(msg)
        self._sync_runtime_state_from_coordinators()
        return session_context

    @timed("security_scan")
    async def _perform_security_scan(self, msg: AgentMessage) -> ValidationResult | None:
        """Transitional wrapper around GateCoordinator.perform_security_scan."""
        self._sync_coordinator_runtime()
        return await self._gate_coordinator.perform_security_scan(msg)

    def _requires_independent_validation(self, msg: AgentMessage) -> bool:
        """Transitional wrapper around GateCoordinator.requires_independent_validation."""
        self._sync_coordinator_runtime()
        return self._gate_coordinator.requires_independent_validation(msg)

    def _enforce_independent_validator_gate(self, msg: AgentMessage) -> ValidationResult | None:
        """Transitional wrapper around GateCoordinator.enforce_independent_validator_gate."""
        self._sync_coordinator_runtime()
        return self._gate_coordinator.enforce_independent_validator_gate(msg)

    def _enforce_autonomy_tier(self, msg: AgentMessage) -> ValidationResult | None:
        """Transitional facade wrapper for autonomy-tier enforcement."""
        return enforce_autonomy_tier_rules(msg=msg, advisory_blocked_types=_ADVISORY_BLOCKED_TYPES)

    def _extract_message_session_id(self, msg: AgentMessage) -> str | None:
        """Transitional facade wrapper for PACAR session-id extraction."""
        return extract_session_id_for_pacar(msg)  # type: ignore[no-any-return]

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
        2. SessionCoordinator resolves and attaches session context
        3. GateCoordinator runs pre-processing gates and governance gating
        4. Cache check (early return if cached)
        5. VerificationCoordinator performs SDPC/PQC orchestration
        6. Strategy-based processing
        7. ResultFinalizer handles caching, audit, DLQ, and metering sinks

        Args:
            msg: The agent message to process.

        Returns:
            ValidationResult with validation status and metadata.
        """
        context = MessageProcessingContext(message=msg, start_time=time.perf_counter())

        async with self._setup_memory_profiling_context(msg):
            # Phase 1: SessionCoordinator attaches explicit session state to the context/message.
            # Mainline processing now calls the coordinator directly; the facade wrapper remains
            # only for backward-compatible helper/coverage callers.
            self._sync_coordinator_runtime()
            await self._session_coordinator.attach_session_context(context)
            self._sync_runtime_state_from_coordinators()

            # Phase 2: GateCoordinator executes fail-closed gates before deeper processing.
            self._sync_coordinator_runtime()
            gate_result = await self._gate_coordinator.run(
                context, self._governance_coordinator.run
            )
            if gate_result:
                self._governance_coordinator.attach_governance_metadata(
                    context=context,
                    result=gate_result,
                )
                await self._handle_failed_processing(
                    msg,
                    gate_result,
                    increment_failed_count=False,
                    failure_stage="gate",
                )
                return gate_result

        # Phase 3: Check validation cache
        context.cache_key = self._compute_cache_key(msg)
        cached = self._validation_cache.get(context.cache_key)
        if cached:
            cached_result = self._clone_validation_result(cached)
            context.cached_result = cached_result
            self._governance_coordinator.attach_governance_metadata(
                context=context,
                result=cached_result,
            )
            return cached_result  # type: ignore[no-any-return]

        # Phase 4-6: Verification and processing. Mainline processing now calls the
        # coordinator directly; the facade wrapper remains only for compatibility callers.
        self._sync_coordinator_runtime()
        return await self._verification_coordinator.execute(context)

    def _setup_memory_profiling_context(self, msg: AgentMessage) -> AbstractContextManager[None]:
        """set up memory profiling context for message processing."""
        profiler = get_memory_profiler()
        operation_name = f"message_processing_{msg.message_type.value}_{msg.priority.value}"
        return (
            profiler.profile_async(operation_name, trace_id=msg.message_id)
            if profiler and profiler.config.enabled
            else nullcontext()
        )

    async def _attach_session_context(
        self,
        context: MessageProcessingContext | AgentMessage,
    ) -> None:
        """Compatibility wrapper around SessionCoordinator.attach_session_context.

        The main processing pipeline now calls `SessionCoordinator` directly. This method remains
        only for legacy helper/coverage tests and any downstream callers still using the old facade
        surface.

        Accepts both the explicit MessageProcessingContext and the legacy AgentMessage shape used
        by older helper/coverage tests.
        """
        self._sync_coordinator_runtime()
        await self._session_coordinator.attach_session_context(context)
        self._sync_runtime_state_from_coordinators()

    def _increment_failed_count(self) -> None:
        self._failed_count += 1

    @staticmethod
    def _clone_validation_result(result: ValidationResult) -> ValidationResult:
        return ValidationResult(
            is_valid=result.is_valid,
            errors=list(result.errors),
            warnings=list(result.warnings),
            metadata=copy.deepcopy(result.metadata),
            decision=result.decision,
            status=result.status,
            constitutional_hash=result.constitutional_hash,
            pqc_metadata=copy.deepcopy(result.pqc_metadata),
        )

    def _compute_cache_key(self, msg: AgentMessage) -> str:
        """Compute SHA-256 cache key with security dimensions for tenant isolation."""
        base_key = compute_message_cache_key(
            msg,
            cache_hash_mode=self._cache_hash_mode,
            fast_hash_available=FAST_HASH_AVAILABLE,
            fast_hash_func=fast_hash if FAST_HASH_AVAILABLE else None,
        )
        return (
            f"{base_key}:{self._governance_core_mode}:"
            f"{int(self._governance_peer_validation_enabled)}:"
            f"{int(self._governance_manifold_enabled)}"
        )

    async def _handle_successful_processing(
        self, msg: AgentMessage, result: ValidationResult, cache_key: str, latency_ms: float
    ) -> None:
        """Handle successful message processing with caching and metrics."""
        self._sync_coordinator_runtime()

        async def emit_governance_audit_event(
            audit_msg: AgentMessage,
            audit_result: ValidationResult,
        ) -> None:
            await self._result_finalizer.emit_governance_audit_event(
                msg=audit_msg,
                result=audit_result,
                audit_client=self._audit_client,
                extract_rejection_reason=self._extract_rejection_reason,
                governance_core_mode=self._governance_core_mode,
            )

        def schedule_governance_audit_event(
            audit_msg: AgentMessage,
            audit_result: ValidationResult,
        ) -> None:
            self._result_finalizer.schedule_governance_audit_event(
                msg=audit_msg,
                result=audit_result,
                audit_client=self._audit_client,
                schedule_background_task_fn=schedule_background_task,
                background_tasks=self._background_tasks,
                emit_governance_audit_event=emit_governance_audit_event,
            )

        async def persist_flywheel_decision_event(
            persist_msg: AgentMessage,
            persist_result: ValidationResult,
        ) -> None:
            await self._result_finalizer.persist_flywheel_decision_event(
                msg=persist_msg,
                result=persist_result,
                workflow_repository=getattr(self, "_workflow_repository", None),
            )

        await self._result_finalizer.handle_successful_processing(
            msg=msg,
            result=result,
            cache_key=cache_key,
            latency_ms=latency_ms,
            validation_cache=self._validation_cache,
            clone_validation_result=self._clone_validation_result,
            processed_counter_increment=self._increment_processed_count,
            schedule_governance_audit_event=schedule_governance_audit_event,
            persist_flywheel_decision_event=persist_flywheel_decision_event,
            requires_independent_validation=self._gate_coordinator.requires_independent_validation,
            record_agent_workflow_event=self._record_agent_workflow_event,
            metering_hooks=self._metering_hooks,
            async_metering_callback=self._async_metering_callback,
            schedule_background_task_fn=schedule_background_task,
            background_tasks=self._background_tasks,
        )

    async def _handle_failed_processing(
        self,
        msg: AgentMessage,
        result: ValidationResult,
        *,
        increment_failed_count: bool = True,
        failure_stage: str = "strategy",
    ) -> None:
        """Handle failed message processing with consistent audit, persistence, and DLQ sinks."""
        self._sync_coordinator_runtime()

        async def emit_governance_audit_event(
            audit_msg: AgentMessage,
            audit_result: ValidationResult,
        ) -> None:
            await self._result_finalizer.emit_governance_audit_event(
                msg=audit_msg,
                result=audit_result,
                audit_client=self._audit_client,
                extract_rejection_reason=self._extract_rejection_reason,
                governance_core_mode=self._governance_core_mode,
            )

        def schedule_governance_audit_event(
            audit_msg: AgentMessage,
            audit_result: ValidationResult,
        ) -> None:
            self._result_finalizer.schedule_governance_audit_event(
                msg=audit_msg,
                result=audit_result,
                audit_client=self._audit_client,
                schedule_background_task_fn=schedule_background_task,
                background_tasks=self._background_tasks,
                emit_governance_audit_event=emit_governance_audit_event,
            )

        async def persist_flywheel_decision_event(
            persist_msg: AgentMessage,
            persist_result: ValidationResult,
        ) -> None:
            await self._result_finalizer.persist_flywheel_decision_event(
                msg=persist_msg,
                result=persist_result,
                workflow_repository=getattr(self, "_workflow_repository", None),
            )

        async def send_to_dlq(dlq_msg: AgentMessage, dlq_result: ValidationResult) -> None:
            try:
                await self._result_finalizer.send_to_dlq(
                    msg=dlq_msg,
                    result=dlq_result,
                    get_dlq_redis=self._get_dlq_redis,
                )
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                self._dlq_redis = None

        await self._result_finalizer.handle_failed_processing(
            msg=msg,
            result=result,
            increment_failed_count=increment_failed_count,
            failed_counter_increment=self._increment_failed_count,
            failure_stage=failure_stage,
            extract_rejection_reason=self._extract_rejection_reason,
            schedule_governance_audit_event=schedule_governance_audit_event,
            persist_flywheel_decision_event=persist_flywheel_decision_event,
            record_agent_workflow_event=self._record_agent_workflow_event,
            send_to_dlq=send_to_dlq,
            schedule_background_task_fn=schedule_background_task,
            background_tasks=self._background_tasks,
        )

    @staticmethod
    def _extract_rejection_reason(result: ValidationResult) -> str:
        """Extract rejection reason from validation result metadata."""
        return extract_rejection_reason(result)

    def _increment_processed_count(self) -> None:
        self._processed_count += 1

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
        """Transitional wrapper around ResultFinalizer.send_to_dlq."""
        try:
            await self._result_finalizer.send_to_dlq(
                msg=msg,
                result=result,
                get_dlq_redis=self._get_dlq_redis,
            )
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            self._dlq_redis = None

    def _detect_prompt_injection(self, msg: AgentMessage) -> ValidationResult | None:
        """Transitional facade wrapper for prompt-injection detection."""
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
        metrics = self._build_base_metrics()
        self._apply_metrics_enrichment(metrics)
        return metrics

    async def shutdown(self) -> None:
        """Cancel and drain processor-owned background tasks."""
        tasks = tuple(self._background_tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

        dlq_redis = getattr(self, "_dlq_redis", None)
        if dlq_redis is not None:
            try:
                await dlq_redis.aclose()
            except Exception:
                logger.debug("message_processor_dlq_redis_close_failed", exc_info=True)
            finally:
                self._dlq_redis = None

    def _build_base_metrics(self) -> JSONDict:
        total = self._processed_count + self._failed_count
        success_rate = self._processed_count / max(1, total) if total > 0 else 0.0
        return {
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
            "governance_core_mode": self._governance_core_mode,
            "governance_swarm_available": self._governance_coordinator.is_swarm_available(),
            "governance_swarm_peer_validation_enabled": self._governance_peer_validation_enabled,
            "governance_swarm_use_manifold": self._governance_manifold_enabled,
            "governance_shadow_matches": self._governance_coordinator.shadow_matches,
            "governance_shadow_mismatches": self._governance_coordinator.shadow_mismatches,
            "governance_shadow_errors": self._governance_coordinator.shadow_errors,
        }

    def _apply_metrics_enrichment(self, metrics: JSONDict) -> None:
        self._sync_coordinator_runtime()
        self._session_coordinator.apply_metrics(metrics)
        self._sync_runtime_state_from_coordinators()
        enrich_metrics_with_opa_stats(metrics, self._opa_client)
        collector = getattr(self, "_agent_workflow_metrics", None)
        if collector is not None and not enrich_metrics_with_workflow_telemetry(metrics, collector):
            logger.debug("Unable to enrich metrics with workflow telemetry", exc_info=True)

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
