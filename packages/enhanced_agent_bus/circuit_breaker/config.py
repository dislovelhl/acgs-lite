"""
ACGS-2 Circuit Breaker Configuration

Constitutional Hash: cdd01ef066bc6cf2

This module defines circuit breaker configuration classes and service-specific
default configurations per T002 requirements.

Service Configurations (T002 requirements):
- policy_registry: failure_threshold=3, timeout=10s, fallback=cached_policy (5m TTL)
- opa_evaluator: failure_threshold=5, timeout=5s, fallback=fail_closed (CRITICAL)
- blockchain_anchor: failure_threshold=10, timeout=60s, fallback=queue_for_retry
- redis_cache: failure_threshold=3, timeout=1s, fallback=graceful_skip
- kafka_producer: failure_threshold=5, timeout=30s, fallback=queue_for_retry
- audit_service: failure_threshold=5, timeout=30s, fallback=queue_for_retry
- deliberation_layer: failure_threshold=7, timeout=45s, fallback=fail_closed (CRITICAL)
"""

from dataclasses import dataclass, field

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import FallbackStrategy, ServiceSeverity

logger = get_logger(__name__)


@dataclass
class ServiceCircuitConfig:
    """
    Service-specific circuit breaker configuration.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    name: str
    failure_threshold: int  # Number of failures before opening circuit
    timeout_seconds: float  # How long to keep circuit open
    half_open_requests: int = 3  # Requests to allow in half-open state
    fallback_strategy: FallbackStrategy = FallbackStrategy.FAIL_CLOSED
    fallback_ttl_seconds: int = 300  # TTL for cached fallback values
    fallback_max_queue_size: int = 10000  # Max items to queue for retry
    fallback_retry_interval_seconds: int = 300  # Retry interval (5 minutes)
    severity: ServiceSeverity = ServiceSeverity.MEDIUM
    description: str = ""
    constitutional_hash: str = field(default=CONSTITUTIONAL_HASH)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "failure_threshold": self.failure_threshold,
            "timeout_seconds": self.timeout_seconds,
            "half_open_requests": self.half_open_requests,
            "fallback_strategy": self.fallback_strategy.value,
            "fallback_ttl_seconds": self.fallback_ttl_seconds,
            "fallback_max_queue_size": self.fallback_max_queue_size,
            "fallback_retry_interval_seconds": self.fallback_retry_interval_seconds,
            "severity": self.severity.value,
            "description": self.description,
            "constitutional_hash": self.constitutional_hash,
        }


# Service-specific configurations per T002 requirements
SERVICE_CIRCUIT_CONFIGS: dict[str, ServiceCircuitConfig] = {
    "policy_registry": ServiceCircuitConfig(
        name="policy_registry",
        failure_threshold=3,
        timeout_seconds=10.0,
        half_open_requests=3,  # Increased from 2 for faster recovery probing
        fallback_strategy=FallbackStrategy.CACHED_VALUE,
        fallback_ttl_seconds=300,  # 5 minute cache TTL
        severity=ServiceSeverity.HIGH,
        description="Policy Registry Service - uses cached policies on failure",
    ),
    "opa_evaluator": ServiceCircuitConfig(
        name="opa_evaluator",
        failure_threshold=5,
        timeout_seconds=5.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.FAIL_CLOSED,
        severity=ServiceSeverity.CRITICAL,
        description="OPA Policy Evaluator - constitutional validation cannot be skipped",
    ),
    "blockchain_anchor": ServiceCircuitConfig(
        name="blockchain_anchor",
        failure_threshold=10,
        timeout_seconds=60.0,
        half_open_requests=5,
        fallback_strategy=FallbackStrategy.QUEUE_FOR_RETRY,
        fallback_max_queue_size=10000,
        fallback_retry_interval_seconds=300,  # 5 minute retry
        severity=ServiceSeverity.HIGH,
        description="Blockchain Anchor Service - queues governance decisions for retry",
    ),
    "redis_cache": ServiceCircuitConfig(
        name="redis_cache",
        failure_threshold=3,
        timeout_seconds=1.0,
        half_open_requests=5,
        fallback_strategy=FallbackStrategy.BYPASS,
        severity=ServiceSeverity.LOW,
        description="Redis Cache - bypasses cache on failure (graceful degradation)",
    ),
    # Kafka Producer (T002 requirement)
    "kafka_producer": ServiceCircuitConfig(
        name="kafka_producer",
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.QUEUE_FOR_RETRY,
        fallback_max_queue_size=10000,
        fallback_retry_interval_seconds=300,  # 5 minute retry
        severity=ServiceSeverity.HIGH,
        description="Kafka Producer - queues messages for retry on failure",
    ),
    # Additional commonly used services
    "audit_service": ServiceCircuitConfig(
        name="audit_service",
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.QUEUE_FOR_RETRY,
        fallback_max_queue_size=5000,
        severity=ServiceSeverity.HIGH,
        description="Audit Service - queues audit logs for retry",
    ),
    "deliberation_layer": ServiceCircuitConfig(
        name="deliberation_layer",
        failure_threshold=7,
        timeout_seconds=45.0,
        half_open_requests=3,  # Increased from 2 for faster recovery probing
        fallback_strategy=FallbackStrategy.FAIL_CLOSED,
        severity=ServiceSeverity.CRITICAL,
        description="Deliberation Layer - AI inference for high-impact decisions",
    ),
}


def get_service_config(service_name: str, use_unified_config: bool = True) -> ServiceCircuitConfig:
    """
    Get configuration for a service, with sensible defaults.

    Constitutional Hash: cdd01ef066bc6cf2

    Args:
        service_name: Name of the service to configure
        use_unified_config: If True, attempt to load from unified config (environment vars)

    Returns:
        ServiceCircuitConfig for the specified service
    """
    # Attempt to load from unified configuration if available
    if use_unified_config:
        try:
            from src.core.shared.config.unified import get_settings

            settings = get_settings()
            cb_settings = settings.circuit_breaker

            # Map service names to unified config attributes
            config_mapping = {
            "policy_registry": {
            "failure_threshold": cb_settings.policy_registry_failure_threshold,
            "timeout_seconds": cb_settings.policy_registry_timeout_seconds,
            "fallback_ttl_seconds": cb_settings.policy_registry_fallback_ttl_seconds,
            },
            "opa_evaluator": {
            "failure_threshold": cb_settings.opa_evaluator_failure_threshold,
            "timeout_seconds": cb_settings.opa_evaluator_timeout_seconds,
            },
            "blockchain_anchor": {
            "failure_threshold": cb_settings.blockchain_anchor_failure_threshold,
            "timeout_seconds": cb_settings.blockchain_anchor_timeout_seconds,
            "fallback_max_queue_size": cb_settings.blockchain_anchor_max_queue_size,
            "fallback_retry_interval_seconds": cb_settings.blockchain_anchor_retry_interval_seconds,  # noqa: E501
            },
            "redis_cache": {
            "failure_threshold": cb_settings.redis_cache_failure_threshold,
            "timeout_seconds": cb_settings.redis_cache_timeout_seconds,
            },
            "kafka_producer": {
            "failure_threshold": cb_settings.kafka_producer_failure_threshold,
            "timeout_seconds": cb_settings.kafka_producer_timeout_seconds,
            "fallback_max_queue_size": cb_settings.kafka_producer_max_queue_size,
            },
            "audit_service": {
            "failure_threshold": cb_settings.audit_service_failure_threshold,
            "timeout_seconds": cb_settings.audit_service_timeout_seconds,
            "fallback_max_queue_size": cb_settings.audit_service_max_queue_size,
            },
            "deliberation_layer": {
            "failure_threshold": cb_settings.deliberation_layer_failure_threshold,
            "timeout_seconds": cb_settings.deliberation_layer_timeout_seconds,
            },
            }

            if service_name in config_mapping:  # noqa: SIM102
                # Start with the base config from SERVICE_CIRCUIT_CONFIGS
                if service_name in SERVICE_CIRCUIT_CONFIGS:
                    base_config = SERVICE_CIRCUIT_CONFIGS[service_name]
                    # Override with unified config values
                    env_overrides = config_mapping[service_name]
                    return ServiceCircuitConfig(
                        name=base_config.name,
                        failure_threshold=int(
                            env_overrides.get("failure_threshold", base_config.failure_threshold)
                        ),
                        timeout_seconds=env_overrides.get(
                            "timeout_seconds", base_config.timeout_seconds
                        ),
                        half_open_requests=base_config.half_open_requests,
                        fallback_strategy=base_config.fallback_strategy,
                        fallback_ttl_seconds=int(
                            env_overrides.get(
                                "fallback_ttl_seconds", base_config.fallback_ttl_seconds
                            )
                        ),
                        fallback_max_queue_size=int(
                            env_overrides.get(
                                "fallback_max_queue_size", base_config.fallback_max_queue_size
                            )
                        ),
                        fallback_retry_interval_seconds=int(
                            env_overrides.get(
                                "fallback_retry_interval_seconds",
                                base_config.fallback_retry_interval_seconds,
                            )
                        ),
                        severity=base_config.severity,
                        description=base_config.description,
                    )
        except ImportError:
            # Unified config not available, fall through to static config
            pass
        except (ValueError, AttributeError, TypeError, KeyError) as e:
            logger.debug(
                f"[{CONSTITUTIONAL_HASH}] Failed to load unified config for {service_name}: {e}"
            )

    # Fall back to static configuration
    if service_name in SERVICE_CIRCUIT_CONFIGS:
        return SERVICE_CIRCUIT_CONFIGS[service_name]

    # Return default configuration for unknown services
    return ServiceCircuitConfig(
        name=service_name,
        failure_threshold=5,
        timeout_seconds=30.0,
        half_open_requests=3,
        fallback_strategy=FallbackStrategy.FAIL_CLOSED,
        severity=ServiceSeverity.MEDIUM,
        description=f"Auto-configured circuit breaker for {service_name}",
    )


__all__ = [
    "SERVICE_CIRCUIT_CONFIGS",
    "ServiceCircuitConfig",
    "get_service_config",
]
