"""
ACGS-2 Enhanced Agent Bus - Service-Specific Circuit Breaker Configuration

Task T002: Circuit Breaker Configuration
Expert Reference: Michael Nygard (Release It!)
Hash: 608508a9bd224290

This module implements the circuit breaker pattern for external service calls
with configurable thresholds, state tracking, and observability integration.

Circuit Breaker States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit tripped after failure threshold, requests fail-fast or use fallback
- HALF_OPEN: Testing if service recovered after timeout

State Transitions:
- CLOSED -> OPEN: When consecutive failures >= failure_threshold
- OPEN -> HALF_OPEN: After timeout_seconds expires
- HALF_OPEN -> CLOSED: When half_open_requests succeed
- HALF_OPEN -> OPEN: On any failure during half-open state

Service Configurations (T002 requirements):
- policy_registry: failure_threshold=3, timeout=10s, fallback=cached_policy (5m TTL)
- opa_evaluator: failure_threshold=5, timeout=5s, fallback=fail_closed (CRITICAL)
- blockchain_anchor: failure_threshold=10, timeout=60s, fallback=queue_for_retry
- redis_cache: failure_threshold=3, timeout=1s, fallback=graceful_skip
- kafka_producer: failure_threshold=5, timeout=30s, fallback=queue_for_retry
- audit_service: failure_threshold=5, timeout=30s, fallback=queue_for_retry
- deliberation_layer: failure_threshold=7, timeout=45s, fallback=fail_closed (CRITICAL)

Configuration Sources:
1. Environment variables via unified config (CB_* prefix)
2. Static SERVICE_CIRCUIT_CONFIGS dictionary (defaults)

Observability Integration:
- Prometheus metrics for state changes, failures, successes, rejections
- Health check endpoint at /health/circuits
- Structured logging with hash context

Usage:
    @with_service_circuit_breaker('policy_registry', cache_key='policies')
    async def get_policies():
        return await policy_service.list()

    # Or manual control:
    cb = await get_service_circuit_breaker('opa_evaluator')
    if await cb.can_execute():
        try:
            result = await opa_client.evaluate(input)
            await cb.record_success()
        except (RuntimeError, ValueError, TypeError, ConnectionError, TimeoutError) as e:
            await cb.record_failure(e, type(e).__name__)
            raise
"""

# Import centralized constitutional hash
# Models
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.circuit_breaker.models import CircuitBreakerMetrics, QueuedRequest

# Batch circuit breaker (rate-based, for batch processing)
from .batch import CircuitBreaker as BatchCircuitBreaker
from .batch import CircuitBreakerConfig as BatchCircuitBreakerConfig

# Core implementation
from .breaker import ServiceCircuitBreaker

# Configuration
from .config import SERVICE_CIRCUIT_CONFIGS, ServiceCircuitConfig, get_service_config

# Decorator
from .decorator import with_service_circuit_breaker

# Enums
from .enums import CircuitState, FallbackStrategy, ServiceSeverity

# Exceptions
from .exceptions import CircuitBreakerOpen

# Prometheus Metrics
from .metrics import (
    PROMETHEUS_AVAILABLE,
    acgs_circuit_breaker_failures_total,
    acgs_circuit_breaker_queue_size,
    acgs_circuit_breaker_rejections_total,
    acgs_circuit_breaker_state,
    acgs_circuit_breaker_state_changes_total,
    acgs_circuit_breaker_successes_total,
)

# Registry
from .registry import (
    ServiceCircuitBreakerRegistry,
    get_circuit_breaker_registry,
    get_service_circuit_breaker,
    reset_circuit_breaker_registry,
)

# Router
from .router import create_circuit_health_router

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Prometheus Metrics
    "PROMETHEUS_AVAILABLE",
    "SERVICE_CIRCUIT_CONFIGS",
    # Batch circuit breaker
    "BatchCircuitBreaker",
    "BatchCircuitBreakerConfig",
    "CircuitBreakerMetrics",
    "CircuitBreakerOpen",
    # Enums
    "CircuitState",
    "FallbackStrategy",
    "QueuedRequest",
    # Classes
    "ServiceCircuitBreaker",
    "ServiceCircuitBreakerRegistry",
    # Configuration
    "ServiceCircuitConfig",
    "ServiceSeverity",
    "acgs_circuit_breaker_failures_total",
    "acgs_circuit_breaker_queue_size",
    "acgs_circuit_breaker_rejections_total",
    "acgs_circuit_breaker_state",
    "acgs_circuit_breaker_state_changes_total",
    "acgs_circuit_breaker_successes_total",
    # FastAPI Router
    "create_circuit_health_router",
    # Functions
    "get_circuit_breaker_registry",
    "get_service_circuit_breaker",
    "get_service_config",
    "reset_circuit_breaker_registry",
    # Decorator
    "with_service_circuit_breaker",
]
