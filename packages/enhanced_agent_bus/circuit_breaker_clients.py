"""
ACGS-2 Enhanced Agent Bus - Circuit Breaker Protected Clients
Constitutional Hash: 608508a9bd224290

Provides circuit breaker wrapped clients for external services:
- OPA Client: fail-closed for governance (constitutional validation cannot be skipped)
- Redis Cache Client: fail-open with degraded mode (graceful degradation)
- Kafka Producer: with retry buffer for guaranteed delivery

Expert Reference: Michael Nygard (Release It!)

T002 Requirements Implementation:
1. OPA client circuit breaker (fail-closed for governance)
2. Redis cache circuit breaker (fail-open with degraded mode)
3. Kafka producer circuit breaker (with retry buffer)
4. Health check endpoints for circuit state

NOTE: This file has been refactored. Classes are now organized into:
- retry_buffer.py: RetryBuffer and BufferedMessage
- cb_opa_client.py: CircuitBreakerOPAClient
- cb_redis_client.py: CircuitBreakerRedisClient
- cb_kafka_producer.py: CircuitBreakerKafkaProducer
- cb_factory.py: Factory functions and health check aggregator

This file re-exports all components for backward compatibility.
New code should import directly from the specific modules.
"""

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Re-export factory functions and health check
from .cb_factory import (
    close_all_circuit_breaker_clients,
    create_circuit_breaker_client_router,
    get_all_circuit_health,
    get_circuit_breaker_kafka_producer,
    get_circuit_breaker_opa_client,
    get_circuit_breaker_redis_client,
    reset_circuit_breaker_clients,
)
from .cb_kafka_producer import CircuitBreakerKafkaProducer

# Re-export circuit breaker protected clients
from .cb_opa_client import CircuitBreakerOPAClient
from .cb_redis_client import CircuitBreakerRedisClient

# Re-export retry buffer
from .retry_buffer import (
    BufferedMessage,
    RetryBuffer,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Retry Buffer
    "BufferedMessage",
    "CircuitBreakerKafkaProducer",
    # Circuit Breaker Protected Clients
    "CircuitBreakerOPAClient",
    "CircuitBreakerRedisClient",
    "RetryBuffer",
    "close_all_circuit_breaker_clients",
    # FastAPI Router
    "create_circuit_breaker_client_router",
    # Health Check
    "get_all_circuit_health",
    "get_circuit_breaker_kafka_producer",
    # Factory Functions
    "get_circuit_breaker_opa_client",
    "get_circuit_breaker_redis_client",
    "reset_circuit_breaker_clients",
]
