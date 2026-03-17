# Constitutional Hash: cdd01ef066bc6cf2
"""
Optional circuit breaker imports for enhanced_agent_bus.
Service-Specific Circuit Breaker Configuration (T002).
"""

try:
    from .circuit_breaker import (
        SERVICE_CIRCUIT_CONFIGS,
        CircuitBreakerMetrics,
        CircuitBreakerOpen,
        CircuitState,
        FallbackStrategy,
        QueuedRequest,
        ServiceCircuitBreaker,
        ServiceCircuitBreakerRegistry,
        ServiceCircuitConfig,
        ServiceSeverity,
        create_circuit_health_router,
        get_circuit_breaker_registry,
        get_service_circuit_breaker,
        get_service_config,
        reset_circuit_breaker_registry,
        with_service_circuit_breaker,
    )

    SERVICE_CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    SERVICE_CIRCUIT_BREAKER_AVAILABLE = False
    CircuitBreakerMetrics = object  # type: ignore[assignment, misc]
    CircuitBreakerOpen = object  # type: ignore[assignment, misc]
    CircuitState = object  # type: ignore[assignment, misc]
    FallbackStrategy = object  # type: ignore[assignment, misc]
    QueuedRequest = object  # type: ignore[assignment, misc]
    SERVICE_CIRCUIT_CONFIGS = {}  # type: ignore[assignment, misc]
    ServiceCircuitBreaker = object  # type: ignore[assignment, misc]
    ServiceCircuitBreakerRegistry = object  # type: ignore[assignment, misc]
    ServiceCircuitConfig = object  # type: ignore[assignment, misc]
    ServiceSeverity = object  # type: ignore[assignment, misc]
    create_circuit_health_router = object  # type: ignore[assignment, misc]
    get_circuit_breaker_registry = object  # type: ignore[assignment, misc]
    get_service_circuit_breaker = object  # type: ignore[assignment, misc]
    get_service_config = object  # type: ignore[assignment, misc]
    reset_circuit_breaker_registry = object  # type: ignore[assignment, misc]
    with_service_circuit_breaker = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "SERVICE_CIRCUIT_BREAKER_AVAILABLE",
    "SERVICE_CIRCUIT_CONFIGS",
    "ServiceCircuitConfig",
    "ServiceCircuitBreaker",
    "ServiceCircuitBreakerRegistry",
    "ServiceSeverity",
    "FallbackStrategy",
    "CircuitState",
    "CircuitBreakerOpen",
    "CircuitBreakerMetrics",
    "QueuedRequest",
    "get_service_config",
    "get_service_circuit_breaker",
    "get_circuit_breaker_registry",
    "reset_circuit_breaker_registry",
    "with_service_circuit_breaker",
    "create_circuit_health_router",
]
