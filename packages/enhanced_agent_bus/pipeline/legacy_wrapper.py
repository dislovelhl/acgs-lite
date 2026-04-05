"""
Legacy MessageProcessor wrapper for backward compatibility.

This wrapper provides the same API as the legacy MessageProcessor
but delegates to the new PipelineMessageRouter internally.

Constitutional Hash: 608508a9bd224290
"""

from collections.abc import Callable

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..dependency_bridge import get_dependency, is_feature_available

POLICY_CLIENT_AVAILABLE: bool = is_feature_available("OPA")
get_opa_client = get_dependency("get_opa_client")
from enhanced_agent_bus.models import AgentMessage
from enhanced_agent_bus.validators import ValidationResult

from ..interfaces import ProcessingStrategy
from .middleware import MiddlewareConfig
from .router import PipelineConfig, PipelineMessageRouter

LEGACY_PIPELINE_PROCESS_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class MessageProcessor:
    """Legacy-compatible MessageProcessor using PipelineMessageRouter.

    This class provides the same API as the original MessageProcessor
    for backward compatibility while using the new pipeline internally.

    Example:
        # Legacy usage (still works)
        processor = MessageProcessor(
            isolated_mode=False,
            use_dynamic_policy=True,
            enable_maci=True,
        )
        result = await processor.process(message)

    Migration path:
        1. Use this wrapper during transition
        2. Migrate to PipelineMessageRouter directly
        3. Remove legacy dependencies
    """

    def __init__(self, **kwargs: object) -> None:
        """Initialize MessageProcessor with legacy-compatible options.

        Args:
            isolated_mode: Run without external dependencies
            use_dynamic_policy: Use policy registry
            enable_maci: Enable MACI role separation
            opa_client: Optional OPA client
            processing_strategy: Custom processing strategy
            enable_metering: Enable metering hooks
            use_rust: Use Rust processor
            policy_fail_closed: Fail closed on policy errors
        """
        self._isolated_mode = kwargs.get("isolated_mode", False)
        self._use_dynamic_policy = (
            kwargs.get("use_dynamic_policy", False)
            and POLICY_CLIENT_AVAILABLE
            and not self._isolated_mode
        )
        self._policy_fail_closed = kwargs.get("policy_fail_closed", False)
        self._use_rust = kwargs.get("use_rust", True)
        self._enable_metering = kwargs.get("enable_metering", True)
        self._enable_maci = kwargs.get("enable_maci", True) and not self._isolated_mode

        # Metrics counters (for backward compatibility)
        self._processed_count = 0
        self._failed_count = 0

        # Build pipeline configuration from legacy options
        pipeline_config = self._build_pipeline_config(kwargs)
        self._router = PipelineMessageRouter(pipeline_config)

    def _build_pipeline_config(self, kwargs: dict) -> PipelineConfig:
        """Build pipeline config from legacy kwargs.

        Args:
            kwargs: Legacy configuration options

        Returns:
            Pipeline configuration
        """
        from ..middlewares import (
            CacheMiddleware,
            MetricsMiddleware,
            SecurityMiddleware,
            SessionExtractionMiddleware,
            StrategyMiddleware,
            VerificationMiddleware,
        )
        from ..middlewares.verification import (
            OPAVerifier,
            PQCVerifier,
            SDPCVerifier,
        )

        middlewares = []

        # 1. Session Extraction
        if not self._isolated_mode:
            middlewares.append(
                SessionExtractionMiddleware(
                    config=MiddlewareConfig(timeout_ms=500),
                )
            )

        # 2. Security
        security_config = MiddlewareConfig(
            fail_closed=True,
            timeout_ms=100,
        )
        # Enable AI guardrails if not in isolated mode
        if not self._isolated_mode:
            from ..middlewares.security import AIGuardrailsConfig

            ai_config = AIGuardrailsConfig(
                threshold=0.85,
                fallback_to_regex=True,
            )
            middlewares.append(
                SecurityMiddleware(
                    config=security_config,
                    guardrails_config=ai_config,
                )
            )
        else:
            middlewares.append(SecurityMiddleware(config=security_config))

        # 3. Cache
        middlewares.append(CacheMiddleware(maxsize=1000))

        # 4. Verification (parallel)
        if not self._isolated_mode:
            verification_config = MiddlewareConfig(
                fail_closed=self._policy_fail_closed,
                timeout_ms=2000,
            )
            middlewares.append(
                VerificationMiddleware(
                    config=verification_config,
                    sdpc_verifier=SDPCVerifier(),
                    pqc_verifier=PQCVerifier(use_rust=self._use_rust),
                    opa_verifier=OPAVerifier() if self._use_dynamic_policy else None,
                    parallel=True,
                )
            )

        # 5. Strategy
        custom_strategy = kwargs.get("processing_strategy")
        middlewares.append(StrategyMiddleware(strategy=custom_strategy))

        # 6. Metrics
        middlewares.append(MetricsMiddleware())

        return PipelineConfig(
            middlewares=middlewares,
            max_concurrent=100,
            metrics_enabled=self._enable_metering,
        )

    async def process(self, msg: AgentMessage) -> ValidationResult:
        """Process a message (legacy API).

        Args:
            msg: Agent message to process

        Returns:
            Validation result
        """
        try:
            result = await self._router.process(msg)
            self._processed_count += 1
            return result
        except LEGACY_PIPELINE_PROCESS_ERRORS:
            self._failed_count += 1
            raise

    def register_handler(self, message_type: str, handler: Callable[..., object]) -> None:
        """Register message handler (legacy API).

        Args:
            message_type: Type of message to handle
            handler: Handler function
        """
        # PLACEHOLDER: Implement handler registration
        pass

    def unregister_handler(self, message_type: str) -> None:
        """Unregister message handler (legacy API).

        Args:
            message_type: Type of message to unregister
        """
        # PLACEHOLDER: Implement handler unregistration
        pass

    @property
    def processed_count(self) -> int:
        """Get processed message count (legacy API)."""
        return self._processed_count + int(self._router.get_metrics()["processed"])

    @property
    def failed_count(self) -> int:
        """Get failed message count (legacy API)."""
        return self._failed_count + int(self._router.get_metrics()["failed"])

    @property
    def processing_strategy(self) -> ProcessingStrategy | None:
        """Get processing strategy (legacy API)."""
        # PLACEHOLDER: Return actual strategy
        return None

    @property
    def opa_client(self) -> object | None:
        """Get OPA client (legacy API)."""
        client = get_opa_client() if not self._isolated_mode else None
        return client  # type: ignore[no-any-return]

    def get_metrics(self) -> JSONDict:
        """Get processor metrics (legacy API)."""
        router_metrics = self._router.get_metrics()
        return {
            "processed_count": self._processed_count + router_metrics["processed"],
            "failed_count": self._failed_count + router_metrics["failed"],
            "avg_latency_ms": router_metrics["avg_latency_ms"],
        }
