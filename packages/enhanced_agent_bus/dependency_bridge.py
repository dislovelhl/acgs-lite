"""
ACGS-2 Dependency Bridge
Constitutional Hash: cdd01ef066bc6cf2

Bridge module that integrates DependencyRegistry with the existing imports.py.
This provides a migration path from scattered try/except patterns to the centralized
DependencyRegistry, while maintaining backward compatibility.

Usage:
    from enhanced_agent_bus.dependency_bridge import (
        get_feature_flags,
        get_dependency,
        is_feature_available,
    )

    # Check if a feature is available
    if is_feature_available("MACI"):
        enforcer = get_dependency("maci_enforcer")

    # Get all feature flags for the legacy imports.py pattern
    flags = get_feature_flags()
    MACI_AVAILABLE = flags["MACI"]
"""

import sys

from typing import TypeVar, cast

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
from src.core.shared.utilities import DependencyRegistry, FeatureFlag

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.dependency_bridge", _module)
    sys.modules.setdefault("packages.enhanced_agent_bus.dependency_bridge", _module)

T = TypeVar("T")

# Feature name to FeatureFlag enum mapping
_FEATURE_MAP: dict[str, FeatureFlag] = {
    "METRICS": FeatureFlag.METRICS,
    "OTEL": FeatureFlag.OTEL,
    "AUDIT": FeatureFlag.AUDIT,
    "REDIS": FeatureFlag.REDIS,
    "KAFKA": FeatureFlag.KAFKA,
    "OPA": FeatureFlag.OPA,
    "MACI": FeatureFlag.MACI,
    "DELIBERATION": FeatureFlag.DELIBERATION,
    "CIRCUIT_BREAKER": FeatureFlag.CIRCUIT_BREAKER,
    "CRYPTO": FeatureFlag.CRYPTO,
    "PQC": FeatureFlag.PQC,
    "RUST": FeatureFlag.RUST,
    "METERING": FeatureFlag.METERING,
    "LLM": FeatureFlag.LLM,
    "IMPACT_SCORER": FeatureFlag.IMPACT_SCORER,
}

# Mapping from legacy names to new dependency names
_LEGACY_NAME_MAP: dict[str, str] = {
    # Metrics
    "MESSAGE_QUEUE_DEPTH": "message_queue_depth",
    "set_service_info": "set_service_info",
    # OTEL
    "tracer": "otel_tracer",
    "meter": "otel_meter",
    # Circuit Breaker
    "get_circuit_breaker": "circuit_breaker",
    "CircuitBreakerConfig": "circuit_breaker_config",
    "circuit_breaker_health_check": "circuit_breaker_health_check",
    # Policy
    "PolicyClient": "policy_client",
    "get_policy_client": "get_policy_client",
    # OPA
    "OPAClient": "opa_client",
    "get_opa_client": "get_opa_client",
    # MACI
    "MACIEnforcer": "maci_enforcer",
    "MACIRole": "maci_role",
    "MACIRoleRegistry": "maci_role_registry",
    # Deliberation
    "DeliberationQueue": "deliberation_queue",
    "VotingService": "voting_service",
    "get_impact_scorer": "impact_scorer",
    # Crypto
    "CryptoService": "crypto_service",
    # Audit
    "AuditClient": "audit_client",
    # LLM
    "get_llm_assistant": "llm_assistant",
    # Metering
    "MeteringHooks": "metering_hooks",
    "MeteringConfig": "metering_config",
    # Rust
    "rust_bus": "rust_bus",
}


def initialize() -> None:
    """Initialize the DependencyRegistry with ACGS-2 defaults.

    Call this at application startup before accessing dependencies.
    """
    DependencyRegistry.initialize_defaults()


def is_feature_available(feature_name: str) -> bool:
    """Check if a feature is available.

    Args:
        feature_name: Feature name (e.g., "MACI", "REDIS", "OTEL")

    Returns:
        True if the feature's dependencies are available
    """
    feature = _FEATURE_MAP.get(feature_name.upper())
    if feature is None:
        logger.warning(f"Unknown feature requested: {feature_name}")
        return False
    return bool(DependencyRegistry.is_available(feature))


def get_dependency(name: str, default: T | None = None) -> T | None:
    """Get a dependency by name.

    Supports both new names (e.g., "maci_enforcer") and legacy names
    (e.g., "MACIEnforcer") for backward compatibility.

    Args:
        name: Dependency name
        default: Default value if not available

    Returns:
        The dependency or default value
    """
    # Translate legacy name if needed
    registry_name = _LEGACY_NAME_MAP.get(name, name)
    return cast(T | None, DependencyRegistry.get(registry_name, default=default))


def get_feature_flags() -> dict[str, bool]:
    """Get all feature availability flags.

    Returns a dict compatible with the legacy imports.py flags:
        {
            "METRICS_ENABLED": True/False,
            "OTEL_ENABLED": True/False,
            ...
        }

    Returns:
        Dict mapping legacy flag names to availability status
    """
    # Initialize if not already done
    if not DependencyRegistry._initialized:
        initialize()

    return {
        "METRICS_ENABLED": DependencyRegistry.is_available(FeatureFlag.METRICS),
        "OTEL_ENABLED": DependencyRegistry.is_available(FeatureFlag.OTEL),
        "CIRCUIT_BREAKER_ENABLED": DependencyRegistry.is_available(FeatureFlag.CIRCUIT_BREAKER),
        "POLICY_CLIENT_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.OPA),
        "DELIBERATION_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.DELIBERATION),
        "CRYPTO_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.CRYPTO),
        "CONFIG_AVAILABLE": True,  # Always assume config is available
        "AUDIT_CLIENT_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.AUDIT),
        "OPA_CLIENT_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.OPA),
        "USE_RUST": DependencyRegistry.is_available(FeatureFlag.RUST),
        "METERING_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.METERING),
        "MACI_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.MACI),
        "REDIS_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.REDIS),
        "KAFKA_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.KAFKA),
        "LLM_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.LLM),
        "IMPACT_SCORER_AVAILABLE": DependencyRegistry.is_available(FeatureFlag.IMPACT_SCORER),
    }


def require_feature(feature_name: str) -> None:
    """Require a feature to be available (raises if not).

    Args:
        feature_name: Feature name to require

    Raises:
        RuntimeError: If feature is not available
    """
    feature = _FEATURE_MAP.get(feature_name.upper())
    if feature is None:
        raise RuntimeError(f"Unknown feature: {feature_name}")
    DependencyRegistry.require(feature)


def get_status() -> JSONDict:
    """Get complete dependency status.

    Returns:
        Dict with feature availability and dependency status
    """
    return DependencyRegistry.get_status()


# Convenience function for common pattern
def optional_import(
    module_path: str,
    name: str,
    feature: str,
    default: T | None = None,
) -> T | None:
    """Import a dependency with feature flag check.

    This provides a cleaner pattern than try/except:

    Old pattern:
        try:
            from module import Something
            FEATURE_AVAILABLE = True
        except ImportError:
            FEATURE_AVAILABLE = False
            Something = None

    New pattern:
        Something = optional_import("module", "Something", "FEATURE")

    Args:
        module_path: Module to import from
        name: Name to import
        feature: Feature flag name
        default: Default value if not available

    Returns:
        Imported object or default
    """
    if not is_feature_available(feature):
        return default
    return get_dependency(name, default=default)


# Stub classes for when features are unavailable
class StubMACIRole:
    """Stub MACI role for when MACI enforcement is unavailable."""

    WORKER = "worker"
    CRITIC = "critic"
    SECURITY_AUDITOR = "security_auditor"
    MONITOR = "monitor"
    EXECUTIVE = "executive"
    LEGISLATIVE = "legislative"
    JUDICIAL = "judicial"


class StubMACIEnforcer:
    """Stub MACI enforcer for when MACI enforcement is unavailable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def validate_action(self, *args: object, **kwargs: object) -> bool:
        return True

    async def check_permission(self, *args: object, **kwargs: object) -> bool:
        return True


class StubMACIRoleRegistry:
    """Stub MACI role registry for when MACI enforcement is unavailable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def register_agent(self, *args: object, **kwargs: object) -> None:
        pass

    async def get_role(self, *args: object, **kwargs: object) -> str:
        return "worker"


def get_maci_enforcer() -> object:
    """Get MACI enforcer, returning stub if unavailable."""
    enforcer: object | None = get_dependency("maci_enforcer")
    if enforcer is None:
        return StubMACIEnforcer
    return enforcer


def get_maci_role() -> object:
    """Get MACI role, returning stub if unavailable."""
    role: object | None = get_dependency("maci_role")
    if role is None:
        return StubMACIRole
    return role


def get_maci_role_registry() -> object:
    """Get MACI role registry, returning stub if unavailable."""
    registry: object | None = get_dependency("maci_role_registry")
    if registry is None:
        return StubMACIRoleRegistry
    return registry


# Initialize on import for backward compatibility
initialize()
