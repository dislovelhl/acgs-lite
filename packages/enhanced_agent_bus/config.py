"""
ACGS-2 Enhanced Agent Bus - Configuration
Constitutional Hash: cdd01ef066bc6cf2

Configuration dataclass for the Enhanced Agent Bus.
Follows the Builder pattern for clean configuration management.
"""

import os
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from enhanced_agent_bus.bus_types import JSONDict

# Import types conditionally to avoid circular imports
if TYPE_CHECKING:
    pass

# Import centralized constitutional hash with fallback
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# Default Redis URL with fallback
try:
    from src.core.shared.redis_config import get_redis_url

    DEFAULT_REDIS_URL = get_redis_url()
except ImportError:
    DEFAULT_REDIS_URL = "redis://localhost:6379"


@dataclass
class BusConfiguration:
    """Configuration for EnhancedAgentBus.

    Consolidates all configuration options into a single, immutable dataclass.
    This follows the Configuration Object pattern for clean dependency management.

    Example usage:
        # Default configuration
        config = BusConfiguration()

        # Custom configuration
        config = BusConfiguration(
            use_dynamic_policy=True,
            policy_fail_closed=True,
            enable_metering=True,
        )

        # Build configuration from environment
        config = BusConfiguration.from_environment()
    """

    # Connection settings
    redis_url: str = DEFAULT_REDIS_URL
    kafka_bootstrap_servers: str = "localhost:9092"
    audit_service_url: str = "http://localhost:8001"

    # Feature flags
    use_dynamic_policy: bool = False
    # SECURITY FIX (2025-12): Default to fail-closed for security-first behavior
    policy_fail_closed: bool = True
    use_kafka: bool = False
    use_redis_registry: bool = False
    use_rust: bool = True
    enable_metering: bool = True

    # MACI role separation settings
    # SECURITY FIX (audit finding 2025-12): MACI enabled by default to prevent
    # Gödel bypass attacks through role separation enforcement.
    # Set enable_maci=False only for legacy/testing - see for_testing() method.
    enable_maci: bool = True
    maci_strict_mode: bool = True

    # PQC (Post-Quantum Cryptography) settings
    # Enable PQC for quantum-resistant constitutional validation
    enable_pqc: bool = False
    pqc_mode: str = "classical_only"  # classical_only, hybrid, pqc_only
    pqc_verification_mode: str = "strict"  # strict, classical_only, pqc_only
    pqc_key_algorithm: str = "dilithium3"  # dilithium2, dilithium3, dilithium5
    pqc_migration_phase: int = 0  # 0-5 (0=classical, 1-3=hybrid, 4-5=pqc_only)

    # LLM Configuration for high-ambiguity intent classification
    # Added for Spec 001
    llm_model: str = "openclaw/claude-opus-4-6"
    llm_cache_ttl: int = 3600
    llm_confidence_threshold: float = 0.8
    llm_max_tokens: int = 100
    llm_use_cache: bool = True
    llm_enabled: bool = False

    # A/B Testing Configuration
    enable_ab_testing: bool = False
    ab_test_llm_percentage: float = 0.0

    # Session Governance Configuration
    # Added for Spec 003: Dynamic Per-Session Governance Configuration
    enable_session_governance: bool = False
    session_policy_cache_ttl: int = 300  # 5 minutes in seconds
    session_context_ttl: int = 3600  # 1 hour in seconds

    # Independent validator gate settings (high-impact MACI safeguard)
    require_independent_validator: bool = False
    independent_validator_threshold: float = 0.8

    # DTMC trajectory risk scoring (Pro2Guard-inspired)
    # Feature flag -- safe default off; zero behaviour change until activated.
    enable_dtmc: bool = False
    # P(unsafe) threshold above which trajectory risk escalates to HIGH.
    # Calibrated to match the HITL trigger at impact_score >= 0.8.
    dtmc_intervention_threshold: float = 0.8
    # Continuous additive weight for DTMC risk blending into risk_score (Sprint 3).
    # Set to 0.0 by default -- no change until operator explicitly opts in.
    # Recommended range: 0.05-0.20 once DTMC has been trained on >= 50 trajectories.
    dtmc_impact_weight: float = 0.0

    # OPAL (Open Policy Administration Layer) Configuration
    # Enables sub-60-second live policy distribution to OPA instances.
    opal_enabled: bool = True
    opal_server_url: str = "http://opal-server:7002"
    opal_client_token: str = ""
    opal_propagation_timeout: int = 60  # seconds

    # Wuying AgentBay SDK Configuration
    wuying_enabled: bool = False
    wuying_api_key: str | None = None
    wuying_access_key_id: str | None = None
    wuying_access_key_secret: str | None = None
    wuying_region_id: str = "cn-hangzhou"

    # Optional dependency injections (set to None for defaults)
    # Note: These are typed as object to avoid circular imports at runtime
    registry: object | None = None
    router: object | None = None
    validator: object | None = None
    processor: object | None = None
    metering_config: object | None = None

    # Queue backpressure settings
    max_queue_size: int = 10_000
    max_message_size_bytes: int = 1_048_576  # 1 MiB
    queue_full_behavior: str = "reject"  # "reject" (429) or "drop_oldest"

    # Constitutional settings
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Ensure constitutional hash is always set
        if not self.constitutional_hash:
            self.constitutional_hash = CONSTITUTIONAL_HASH

    @staticmethod
    def _parse_bool(value: object) -> bool:
        """Parse various representations of boolean values."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        s = str(value).lower()
        return s in ("true", "1", "yes", "on", "y", "t")

    @staticmethod
    def _parse_int(value: str | None, default: int) -> int:
        """Parse integer value with fallback to default."""
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_float(value: str | None, default: float) -> float:
        """Parse float value with fallback to default."""
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @classmethod
    def from_environment(cls) -> "BusConfiguration":
        """Load configuration from environment variables."""
        config = cls(
            redis_url=os.getenv("REDIS_URL", DEFAULT_REDIS_URL),
            kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            audit_service_url=os.getenv("AUDIT_SERVICE_URL", "http://localhost:8001"),
            use_dynamic_policy=cls._parse_bool(os.getenv("USE_DYNAMIC_POLICY", "false")),
            policy_fail_closed=cls._parse_bool(os.getenv("POLICY_FAIL_CLOSED", "true")),
            use_kafka=cls._parse_bool(os.getenv("USE_KAFKA", "false")),
            use_redis_registry=cls._parse_bool(os.getenv("USE_REDIS_REGISTRY", "false")),
            use_rust=cls._parse_bool(os.getenv("USE_RUST", "true")),
            enable_metering=cls._parse_bool(os.getenv("ENABLE_METERING", "true")),
            enable_maci=cls._parse_bool(os.getenv("ENABLE_MACI", "true")),
            maci_strict_mode=cls._parse_bool(os.getenv("MACI_STRICT_MODE", "true")),
            enable_pqc=cls._parse_bool(os.getenv("ENABLE_PQC", "false")),
            pqc_mode=os.getenv("PQC_MODE", "classical_only"),
            pqc_verification_mode=os.getenv("PQC_VERIFICATION_MODE", "strict"),
            pqc_key_algorithm=os.getenv("PQC_KEY_ALGORITHM", "dilithium3"),
            pqc_migration_phase=cls._parse_int(os.getenv("PQC_MIGRATION_PHASE"), 0),
            llm_model=os.getenv("LLM_MODEL", "openclaw/claude-opus-4-6"),
            llm_cache_ttl=int(os.getenv("LLM_CACHE_TTL", "3600")),
            llm_confidence_threshold=float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.8")),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "100")),
            llm_use_cache=cls._parse_bool(os.getenv("LLM_USE_CACHE", "true")),
            llm_enabled=cls._parse_bool(os.getenv("LLM_ENABLED", "false")),
            enable_ab_testing=cls._parse_bool(os.getenv("ENABLE_AB_TESTING", "false")),
            ab_test_llm_percentage=float(os.getenv("AB_TEST_LLM_PERCENTAGE", "0.0")),
            # Session governance settings
            enable_session_governance=cls._parse_bool(
                os.getenv("ENABLE_SESSION_GOVERNANCE", "false")
            ),
            session_policy_cache_ttl=cls._parse_int(os.getenv("SESSION_POLICY_CACHE_TTL"), 300),
            session_context_ttl=cls._parse_int(os.getenv("SESSION_CONTEXT_TTL"), 3600),
            require_independent_validator=cls._parse_bool(
                os.getenv("REQUIRE_INDEPENDENT_VALIDATOR", "false")
            ),
            independent_validator_threshold=cls._parse_float(
                os.getenv("INDEPENDENT_VALIDATOR_THRESHOLD"), 0.8
            ),
            # Queue backpressure settings
            max_queue_size=cls._parse_int(os.getenv("MAX_QUEUE_SIZE"), 10_000),
            max_message_size_bytes=cls._parse_int(os.getenv("MAX_MESSAGE_SIZE_BYTES"), 1_048_576),
            queue_full_behavior=os.getenv("QUEUE_FULL_BEHAVIOR", "reject"),
            # OPAL settings
            opal_enabled=cls._parse_bool(os.getenv("OPAL_ENABLED", "true")),
            opal_server_url=os.getenv("OPAL_SERVER_URL", "http://opal-server:7002"),
            opal_client_token=os.getenv("OPAL_CLIENT_TOKEN", ""),
            opal_propagation_timeout=cls._parse_int(
                os.getenv("OPAL_PROPAGATION_TIMEOUT_SECONDS"), 60
            ),
            # Wuying AgentBay SDK settings
            wuying_enabled=cls._parse_bool(os.getenv("WUYING_ENABLED", "false")),
            wuying_api_key=os.getenv("WUYING_API_KEY"),
            wuying_access_key_id=os.getenv("WUYING_ACCESS_KEY_ID"),
            wuying_access_key_secret=os.getenv("WUYING_ACCESS_KEY_SECRET"),
            wuying_region_id=os.getenv("WUYING_REGION_ID", "cn-hangzhou"),
        )

        # Initialize LiteLLM Cache if enabled
        if config.llm_use_cache and not os.getenv("PYTEST_CURRENT_TEST"):
            try:
                import litellm
                from litellm.caching import Cache

                parsed_url = urlparse(config.redis_url)
                litellm.cache = Cache(
                    type="redis",  # type: ignore[arg-type]
                    host=parsed_url.hostname or "localhost",
                    port=str(parsed_url.port or 6379),
                    password=parsed_url.password,
                )
            except (ImportError, ConnectionError, ValueError) as e:
                # Fallback to in-memory if redis fails or isn't available
                logger.debug(f"Redis cache setup failed, using in-memory: {e}")
                try:
                    import litellm
                    from litellm.caching import Cache

                    litellm.cache = Cache()
                except ImportError:
                    logger.debug("LiteLLM not available, skipping cache initialization")

        return config

    @classmethod
    def for_testing(cls) -> "BusConfiguration":
        """Create a minimal configuration for unit testing.

        Disables all optional features for fast, isolated testing.
        """
        return cls(
            use_dynamic_policy=False,
            policy_fail_closed=False,
            use_kafka=False,
            use_redis_registry=False,
            use_rust=False,
            enable_metering=False,
            enable_maci=False,
            maci_strict_mode=False,
            # Disable LLM for testing to avoid external API calls
            llm_enabled=False,
            enable_ab_testing=False,
            # Disable session governance for testing
            enable_session_governance=False,
            require_independent_validator=False,
            independent_validator_threshold=0.8,
            # Relaxed backpressure for testing
            max_queue_size=100_000,
        )

    @classmethod
    def for_production(cls) -> "BusConfiguration":
        """Create a configuration suitable for production use.

        Enables all production features with fail-closed security.
        """
        return cls(
            use_dynamic_policy=True,
            policy_fail_closed=True,
            use_kafka=True,
            use_redis_registry=True,
            use_rust=True,
            enable_metering=True,
            enable_maci=True,
            maci_strict_mode=True,
            # Enable LLM classification for production
            llm_enabled=True,
            llm_confidence_threshold=0.7,
            enable_ab_testing=False,
            # Enable session governance for production
            enable_session_governance=True,
            require_independent_validator=True,
            independent_validator_threshold=0.8,
            # Strict backpressure for production
            max_queue_size=10_000,
            max_message_size_bytes=1_048_576,
            queue_full_behavior="reject",
        )

    def with_registry(self, registry: object) -> "BusConfiguration":
        """Return a new configuration with the specified registry.

        Builder pattern method for fluent configuration.
        Uses dataclasses.replace() for immutable field updates.
        """
        return replace(self, registry=registry)

    def with_validator(self, validator: object) -> "BusConfiguration":
        """Return a new configuration with the specified validator.

        Builder pattern method for fluent configuration.
        Uses dataclasses.replace() for immutable field updates.
        """
        return replace(self, validator=validator)

    @staticmethod
    def _redact_url(url: str | None) -> str | None:
        """Redact credentials from a connection URL for safe logging."""
        if not url:
            return url
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            if parsed.password:
                netloc = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
                if parsed.username:
                    netloc = f"{parsed.username}:***@{netloc}"
                redacted = parsed._replace(netloc=netloc)
                return urlunparse(redacted)
        except Exception:
            return "<redacted>"
        return url

    def __repr__(self) -> str:
        """Suppress secret fields in repr output."""
        return (
            f"BusConfiguration("
            f"redis_url={self._redact_url(self.redis_url)!r}, "
            f"has_wuying_api_key={self.wuying_api_key is not None}, "
            f"has_wuying_access_key_id={self.wuying_access_key_id is not None}, "
            f"has_wuying_access_key_secret={self.wuying_access_key_secret is not None}, "
            f"constitutional_hash={self.constitutional_hash!r})"
        )

    def to_dict(self) -> JSONDict:
        """Convert configuration to dictionary for logging/serialization."""
        return {
            "redis_url": self._redact_url(self.redis_url),
            "kafka_bootstrap_servers": self._redact_url(self.kafka_bootstrap_servers)
            if self.kafka_bootstrap_servers
            else self.kafka_bootstrap_servers,
            "audit_service_url": self._redact_url(self.audit_service_url),
            "use_dynamic_policy": self.use_dynamic_policy,
            "policy_fail_closed": self.policy_fail_closed,
            "use_kafka": self.use_kafka,
            "use_redis_registry": self.use_redis_registry,
            "use_rust": self.use_rust,
            "enable_metering": self.enable_metering,
            "enable_maci": self.enable_maci,
            "maci_strict_mode": self.maci_strict_mode,
            "constitutional_hash": self.constitutional_hash,
            # LLM classification settings
            "llm_enabled": self.llm_enabled,
            "llm_model_version": self.llm_model,
            "llm_cache_ttl": self.llm_cache_ttl,
            "llm_confidence_threshold": self.llm_confidence_threshold,
            "llm_max_tokens": self.llm_max_tokens,
            # A/B testing settings
            "enable_ab_testing": self.enable_ab_testing,
            "ab_test_llm_percentage": self.ab_test_llm_percentage,
            # Session governance settings
            "enable_session_governance": self.enable_session_governance,
            "session_policy_cache_ttl": self.session_policy_cache_ttl,
            "session_context_ttl": self.session_context_ttl,
            "require_independent_validator": self.require_independent_validator,
            "independent_validator_threshold": self.independent_validator_threshold,
            # Queue backpressure settings
            "max_queue_size": self.max_queue_size,
            "max_message_size_bytes": self.max_message_size_bytes,
            "queue_full_behavior": self.queue_full_behavior,
            # OPAL settings
            "opal_enabled": self.opal_enabled,
            "opal_server_url": self.opal_server_url,
            "opal_propagation_timeout": self.opal_propagation_timeout,
            # never emit opal_client_token
            # Wuying AgentBay SDK status (never emit secrets)
            "wuying_enabled": self.wuying_enabled,
            "has_wuying_api_key": self.wuying_api_key is not None,
            "has_wuying_access_key_id": self.wuying_access_key_id is not None,
            "has_wuying_access_key_secret": self.wuying_access_key_secret is not None,
            "wuying_region": self.wuying_region_id,
            # Dependency injection status
            "has_custom_registry": self.registry is not None,
            "has_custom_router": self.router is not None,
            "has_custom_validator": self.validator is not None,
            "has_custom_processor": self.processor is not None,
            "has_metering_config": self.metering_config is not None,
        }


try:
    from src.core.shared.config import settings
except ImportError:
    settings = BusConfiguration()  # type: ignore[assignment]  # Use as fallback if shared settings not available
