# Constitutional Hash: cdd01ef066bc6cf2
"""Optional Circuit Breaker Protected Clients (T002 - Enhanced)."""

try:
    from .circuit_breaker_clients import (
        BufferedMessage,
        CircuitBreakerKafkaProducer,
        CircuitBreakerOPAClient,
        CircuitBreakerRedisClient,
        RetryBuffer,
        close_all_circuit_breaker_clients,
        create_circuit_breaker_client_router,
        get_all_circuit_health,
        get_circuit_breaker_kafka_producer,
        get_circuit_breaker_opa_client,
        get_circuit_breaker_redis_client,
        reset_circuit_breaker_clients,
    )

    CIRCUIT_BREAKER_CLIENTS_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_CLIENTS_AVAILABLE = False
    BufferedMessage = object  # type: ignore[assignment, misc]
    CircuitBreakerKafkaProducer = object  # type: ignore[assignment, misc]
    CircuitBreakerOPAClient = object  # type: ignore[assignment, misc]
    CircuitBreakerRedisClient = object  # type: ignore[assignment, misc]
    RetryBuffer = object  # type: ignore[assignment, misc]
    close_all_circuit_breaker_clients = object  # type: ignore[assignment, misc]
    create_circuit_breaker_client_router = object  # type: ignore[assignment, misc]
    get_all_circuit_health = object  # type: ignore[assignment, misc]
    get_circuit_breaker_kafka_producer = object  # type: ignore[assignment, misc]
    get_circuit_breaker_opa_client = object  # type: ignore[assignment, misc]
    get_circuit_breaker_redis_client = object  # type: ignore[assignment, misc]
    reset_circuit_breaker_clients = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "CIRCUIT_BREAKER_CLIENTS_AVAILABLE",
    "CircuitBreakerOPAClient",
    "CircuitBreakerRedisClient",
    "CircuitBreakerKafkaProducer",
    "BufferedMessage",
    "RetryBuffer",
    "get_circuit_breaker_opa_client",
    "get_circuit_breaker_redis_client",
    "get_circuit_breaker_kafka_producer",
    "close_all_circuit_breaker_clients",
    "reset_circuit_breaker_clients",
    "get_all_circuit_health",
    "create_circuit_breaker_client_router",
]
