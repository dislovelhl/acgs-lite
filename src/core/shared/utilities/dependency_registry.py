"""
ACGS-2 Dependency Registry
Constitutional Hash: cdd01ef066bc6cf2

Centralized registry for optional dependencies and feature flags.
Replaces scattered try/except import patterns across 611+ locations.

Usage:
    from src.core.shared.utilities import DependencyRegistry, FeatureFlag

    # Check feature availability
    if DependencyRegistry.is_available(FeatureFlag.METRICS):
        meter = DependencyRegistry.get("prometheus_meter")

    # Get with fallback
    client = DependencyRegistry.get("redis_client", default=MockRedisClient())
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import ClassVar, TypeVar

from src.core.shared.errors.exceptions import ServiceUnavailableError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)
T = TypeVar("T")


class FeatureFlag(Enum):
    """
    Feature flags for optional dependencies.

    Use these to check if a feature is available before using it.
    """

    # Observability
    METRICS = auto()  # Prometheus metrics
    OTEL = auto()  # OpenTelemetry tracing
    AUDIT = auto()  # Audit logging

    # Infrastructure
    REDIS = auto()  # Redis client
    KAFKA = auto()  # Kafka messaging
    OPA = auto()  # Open Policy Agent

    # Governance
    MACI = auto()  # MACI enforcement
    DELIBERATION = auto()  # Deliberation layer
    CIRCUIT_BREAKER = auto()  # Circuit breaker

    # Security
    CRYPTO = auto()  # Cryptographic services
    PQC = auto()  # Post-quantum crypto

    # Performance
    RUST = auto()  # Rust acceleration
    METERING = auto()  # Usage metering

    # AI/ML
    LLM = auto()  # LLM assistant
    IMPACT_SCORER = auto()  # Impact scoring


@dataclass
class DependencyInfo:
    """Information about a registered dependency."""

    name: str
    module_path: str
    import_name: str
    feature_flag: FeatureFlag
    fallback_paths: list[str] = field(default_factory=list)
    factory: Callable[[], object] | None = None
    singleton: bool = False
    _instance: object | None = field(default=None, repr=False)
    _loaded: bool = field(default=False, repr=False)
    _available: bool = field(default=False, repr=False)


class DependencyRegistry:
    """
    Centralized registry for optional dependencies.

    Provides:
    - Lazy loading of optional modules
    - Feature flag checking
    - Singleton management
    - Fallback handling
    - Import status reporting

    Thread-safe through lazy initialization.
    """

    _dependencies: ClassVar[dict[str, DependencyInfo]] = {}
    _feature_status: ClassVar[dict[FeatureFlag, bool]] = {}
    _initialized: bool = False

    @classmethod
    def register(
        cls,
        name: str,
        module_path: str,
        import_name: str,
        feature_flag: FeatureFlag,
        fallback_paths: list[str] | None = None,
        factory: Callable[[], object] | None = None,
        singleton: bool = False,
    ) -> None:
        """
        Register an optional dependency.

        Args:
            name: Unique name for the dependency
            module_path: Primary module path to import from
            import_name: Name to import from the module
            feature_flag: Feature flag this dependency enables
            fallback_paths: Alternative module paths to try
            factory: Optional factory function to create instance
            singleton: If True, cache the first instance

        Example:
            DependencyRegistry.register(
                name="prometheus_meter",
                module_path="prometheus_client",
                import_name="Counter",
                feature_flag=FeatureFlag.METRICS,
            )
        """
        cls._dependencies[name] = DependencyInfo(
            name=name,
            module_path=module_path,
            import_name=import_name,
            feature_flag=feature_flag,
            fallback_paths=fallback_paths or [],
            factory=factory,
            singleton=singleton,
        )

    @classmethod
    def get(
        cls,
        name: str,
        default: T | None = None,
        create: bool = True,
    ) -> T | None:
        """
        Get a registered dependency.

        Args:
            name: Name of the registered dependency
            default: Default value if not available
            create: If True and factory exists, create instance

        Returns:
            The dependency or default value

        Example:
            meter = DependencyRegistry.get("prometheus_meter")
            if meter:
                meter.inc()
        """
        if name not in cls._dependencies:
            logger.warning(f"Unknown dependency requested: {name}")
            return default

        info = cls._dependencies[name]

        # Return cached singleton if available
        if info.singleton and info._instance is not None:
            return info._instance  # type: ignore[no-any-return]

        # Load if not already loaded
        if not info._loaded:
            cls._load_dependency(info)

        if not info._available:
            return default

        # Use factory if available and create=True
        if create and info.factory:
            instance = info.factory()
            if info.singleton:
                info._instance = instance
            return instance  # type: ignore[no-any-return]

        # Return the imported class/function
        return info._instance

    @classmethod
    def _load_dependency(cls, info: DependencyInfo) -> None:
        """Load a dependency from its module path."""
        info._loaded = True
        paths_to_try = [info.module_path, *info.fallback_paths]

        for path in paths_to_try:
            try:
                module = importlib.import_module(path)
                info._instance = getattr(module, info.import_name)
                info._available = True
                cls._feature_status[info.feature_flag] = True
                logger.debug(f"Loaded dependency {info.name} from {path}")
                return
            except (ImportError, AttributeError) as e:
                logger.debug(f"Failed to load {info.name} from {path}: {e}")
                continue

        # All paths failed
        info._available = False
        if info.feature_flag not in cls._feature_status:
            cls._feature_status[info.feature_flag] = False
        logger.info(f"Optional dependency {info.name} not available")

    @classmethod
    def is_available(cls, feature: FeatureFlag) -> bool:
        """
        Check if a feature is available.

        Args:
            feature: Feature flag to check

        Returns:
            True if the feature's dependencies are available

        Example:
            if DependencyRegistry.is_available(FeatureFlag.REDIS):
                cache = get_redis_cache()
        """
        # Check cached status first
        if feature in cls._feature_status:
            return cls._feature_status[feature]

        # Load any dependencies for this feature to determine availability
        for info in cls._dependencies.values():
            if info.feature_flag == feature and not info._loaded:
                cls._load_dependency(info)

        return cls._feature_status.get(feature, False)

    @classmethod
    def require(cls, feature: FeatureFlag) -> None:
        """
        Require a feature to be available (raises if not).

        Args:
            feature: Feature flag to require

        Raises:
            ServiceUnavailableError: If feature is not available

        Example:
            DependencyRegistry.require(FeatureFlag.REDIS)
            # Safe to use Redis here
        """
        if not cls.is_available(feature):
            raise ServiceUnavailableError(
                f"Required feature {feature.name} is not available. "
                f"Please install the required dependencies.",
                error_code="DEPENDENCY_NOT_AVAILABLE",
            )

    @classmethod
    def get_status(cls) -> JSONDict:
        """
        Get the status of all registered dependencies.

        Returns:
            Dict with feature availability and dependency status

        Example:
            status = DependencyRegistry.get_status()
            logger.info(f"Feature status: {status['features']}")
        """
        # Ensure all dependencies are loaded
        for info in cls._dependencies.values():
            if not info._loaded:
                cls._load_dependency(info)

        return {
            "features": {
                feature.name: available for feature, available in cls._feature_status.items()
            },
            "dependencies": {
                name: {
                    "available": info._available,
                    "module": info.module_path,
                    "feature": info.feature_flag.name,
                }
                for name, info in cls._dependencies.items()
            },
            "available_features": [
                f.name for f, available in cls._feature_status.items() if available
            ],
            "missing_features": [
                f.name for f, available in cls._feature_status.items() if not available
            ],
        }

    @classmethod
    def initialize_defaults(cls) -> None:
        """
        Register default ACGS-2 dependencies.

        Call this at application startup to register all standard dependencies.
        This replaces the scattered try/except import patterns throughout the codebase.
        """
        if cls._initialized:
            return

        # =========================================================================
        # Observability Dependencies
        # =========================================================================

        # Prometheus Metrics
        cls.register(
            name="prometheus_counter",
            module_path="prometheus_client",
            import_name="Counter",
            feature_flag=FeatureFlag.METRICS,
        )
        cls.register(
            name="message_queue_depth",
            module_path="src.core.shared.metrics",
            import_name="MESSAGE_QUEUE_DEPTH",
            feature_flag=FeatureFlag.METRICS,
        )
        cls.register(
            name="set_service_info",
            module_path="src.core.shared.metrics",
            import_name="set_service_info",
            feature_flag=FeatureFlag.METRICS,
        )

        # OpenTelemetry
        cls.register(
            name="otel_tracer",
            module_path="opentelemetry.trace",
            import_name="get_tracer",
            feature_flag=FeatureFlag.OTEL,
        )
        cls.register(
            name="otel_meter",
            module_path="opentelemetry.metrics",
            import_name="get_meter",
            feature_flag=FeatureFlag.OTEL,
        )

        # Audit Client
        cls.register(
            name="audit_client",
            module_path="src.core.shared.audit_client",
            import_name="AuditClient",
            feature_flag=FeatureFlag.AUDIT,
            fallback_paths=[
                "packages.enhanced_agent_bus.audit_client",
                "audit_client",
            ],
        )

        # =========================================================================
        # Infrastructure Dependencies
        # =========================================================================

        # Redis
        cls.register(
            name="redis_client",
            module_path="redis.asyncio",
            import_name="Redis",
            feature_flag=FeatureFlag.REDIS,
            fallback_paths=["redis"],
        )
        cls.register(
            name="redis_config",
            module_path="src.core.shared.redis_config",
            import_name="get_redis_url",
            feature_flag=FeatureFlag.REDIS,
        )

        # Kafka
        cls.register(
            name="kafka_producer",
            module_path="kafka",
            import_name="KafkaProducer",
            feature_flag=FeatureFlag.KAFKA,
            fallback_paths=["confluent_kafka"],
        )

        # OPA Client
        cls.register(
            name="opa_client",
            module_path="packages.enhanced_agent_bus.opa_client",
            import_name="OPAClient",
            feature_flag=FeatureFlag.OPA,
            fallback_paths=["enhanced_agent_bus.opa_client", "opa_client"],
        )
        cls.register(
            name="get_opa_client",
            module_path="packages.enhanced_agent_bus.opa_client",
            import_name="get_opa_client",
            feature_flag=FeatureFlag.OPA,
            fallback_paths=["enhanced_agent_bus.opa_client", "opa_client"],
        )

        # Circuit Breaker
        cls.register(
            name="circuit_breaker",
            module_path="src.core.shared.circuit_breaker",
            import_name="get_circuit_breaker",
            feature_flag=FeatureFlag.CIRCUIT_BREAKER,
        )
        cls.register(
            name="circuit_breaker_config",
            module_path="src.core.shared.circuit_breaker",
            import_name="CircuitBreakerConfig",
            feature_flag=FeatureFlag.CIRCUIT_BREAKER,
        )
        cls.register(
            name="circuit_breaker_health_check",
            module_path="src.core.shared.circuit_breaker",
            import_name="circuit_breaker_health_check",
            feature_flag=FeatureFlag.CIRCUIT_BREAKER,
        )

        # =========================================================================
        # Governance Dependencies
        # =========================================================================

        # MACI Enforcement
        cls.register(
            name="maci_enforcer",
            module_path="packages.enhanced_agent_bus.maci_enforcement",
            import_name="MACIEnforcer",
            feature_flag=FeatureFlag.MACI,
            fallback_paths=["enhanced_agent_bus.maci_enforcement", "maci_enforcement"],
        )
        cls.register(
            name="maci_role",
            module_path="packages.enhanced_agent_bus.maci_enforcement",
            import_name="MACIRole",
            feature_flag=FeatureFlag.MACI,
            fallback_paths=["enhanced_agent_bus.maci_enforcement", "maci_enforcement"],
        )
        cls.register(
            name="maci_role_registry",
            module_path="packages.enhanced_agent_bus.maci_enforcement",
            import_name="MACIRoleRegistry",
            feature_flag=FeatureFlag.MACI,
            fallback_paths=["enhanced_agent_bus.maci_enforcement", "maci_enforcement"],
        )

        # Policy Client
        cls.register(
            name="policy_client",
            module_path="packages.enhanced_agent_bus.policy_client",
            import_name="PolicyClient",
            feature_flag=FeatureFlag.OPA,
            fallback_paths=["enhanced_agent_bus.policy_client", "policy_client"],
        )
        cls.register(
            name="get_policy_client",
            module_path="packages.enhanced_agent_bus.policy_client",
            import_name="get_policy_client",
            feature_flag=FeatureFlag.OPA,
            fallback_paths=["enhanced_agent_bus.policy_client", "policy_client"],
        )

        # Deliberation Layer
        cls.register(
            name="deliberation_queue",
            module_path="packages.enhanced_agent_bus.deliberation_layer.deliberation_queue",
            import_name="DeliberationQueue",
            feature_flag=FeatureFlag.DELIBERATION,
            fallback_paths=["deliberation_layer.deliberation_queue"],
        )
        cls.register(
            name="voting_service",
            module_path="packages.enhanced_agent_bus.deliberation_layer.voting_service",
            import_name="VotingService",
            feature_flag=FeatureFlag.DELIBERATION,
            fallback_paths=["deliberation_layer.voting_service"],
        )
        cls.register(
            name="impact_scorer",
            module_path="packages.enhanced_agent_bus.deliberation_layer.impact_scorer",
            import_name="get_impact_scorer",
            feature_flag=FeatureFlag.IMPACT_SCORER,
            fallback_paths=["deliberation_layer.impact_scorer"],
        )

        # =========================================================================
        # Security Dependencies
        # =========================================================================

        # Crypto Service
        cls.register(
            name="crypto_service",
            module_path="src.core.services.policy_registry.app.services.crypto_service",
            import_name="CryptoService",
            feature_flag=FeatureFlag.CRYPTO,
        )

        # PQC (Post-Quantum Crypto)
        cls.register(
            name="pqc_provider",
            module_path="src.core.shared.security.pqc",
            import_name="PQCProvider",
            feature_flag=FeatureFlag.PQC,
        )

        # =========================================================================
        # Performance Dependencies
        # =========================================================================

        # Rust Backend
        cls.register(
            name="rust_bus",
            module_path="enhanced_agent_bus_rust",
            import_name="RustBus",
            feature_flag=FeatureFlag.RUST,
        )

        # Metering
        cls.register(
            name="metering_hooks",
            module_path="packages.enhanced_agent_bus.metering_integration",
            import_name="MeteringHooks",
            feature_flag=FeatureFlag.METERING,
            fallback_paths=["metering_integration"],
        )
        cls.register(
            name="metering_config",
            module_path="packages.enhanced_agent_bus.metering_integration",
            import_name="MeteringConfig",
            feature_flag=FeatureFlag.METERING,
            fallback_paths=["metering_integration"],
        )

        # =========================================================================
        # AI/ML Dependencies
        # =========================================================================

        # LLM Assistant
        cls.register(
            name="llm_assistant",
            module_path="packages.enhanced_agent_bus.deliberation_layer.llm_assistant",
            import_name="get_llm_assistant",
            feature_flag=FeatureFlag.LLM,
            fallback_paths=["deliberation_layer.llm_assistant"],
        )

        cls._initialized = True
        logger.info("DependencyRegistry initialized with %d dependencies", len(cls._dependencies))

    @classmethod
    def reset(cls) -> None:
        """Reset the registry (useful for testing)."""
        cls._dependencies.clear()
        cls._feature_status.clear()
        cls._initialized = False


# Auto-initialize on import (can be disabled for testing)
# DependencyRegistry.initialize_defaults()
