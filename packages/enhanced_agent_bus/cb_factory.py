"""
ACGS-2 Enhanced Agent Bus - Circuit Breaker Client Factory
Constitutional Hash: cdd01ef066bc6cf2

Factory functions for creating and managing circuit breaker protected clients.
Split from circuit_breaker_clients.py for improved maintainability.
"""

import asyncio
from datetime import UTC, datetime

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import circuit breaker clients
from .cb_kafka_producer import CircuitBreakerKafkaProducer
from .cb_opa_client import CircuitBreakerOPAClient
from .cb_redis_client import CircuitBreakerRedisClient

# Import circuit breaker registry
from .circuit_breaker import get_circuit_breaker_registry

logger = get_logger(__name__)
# =============================================================================
# Singleton Instances
# =============================================================================

_opa_client: CircuitBreakerOPAClient | None = None
_redis_client: CircuitBreakerRedisClient | None = None
_kafka_producer: CircuitBreakerKafkaProducer | None = None
_singleton_lock = asyncio.Lock()


# =============================================================================
# Factory Functions
# =============================================================================


async def get_circuit_breaker_opa_client(
    opa_url: str = "http://localhost:8181",
    **kwargs,
) -> CircuitBreakerOPAClient:
    """Get or create singleton circuit breaker protected OPA client."""
    global _opa_client
    if _opa_client is not None:
        return _opa_client
    async with _singleton_lock:
        if _opa_client is None:
            client = CircuitBreakerOPAClient(opa_url=opa_url, **kwargs)
            await client.initialize()
            _opa_client = client
    return _opa_client


async def get_circuit_breaker_redis_client(
    redis_url: str = "redis://localhost:6379",
    **kwargs,
) -> CircuitBreakerRedisClient:
    """Get or create singleton circuit breaker protected Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    async with _singleton_lock:
        if _redis_client is None:
            client = CircuitBreakerRedisClient(redis_url=redis_url, **kwargs)
            await client.initialize()
            _redis_client = client
    return _redis_client


async def get_circuit_breaker_kafka_producer(
    bootstrap_servers: str = "localhost:9092",
    **kwargs,
) -> CircuitBreakerKafkaProducer:
    """Get or create singleton circuit breaker protected Kafka producer."""
    global _kafka_producer
    if _kafka_producer is not None:
        return _kafka_producer
    async with _singleton_lock:
        if _kafka_producer is None:
            producer = CircuitBreakerKafkaProducer(bootstrap_servers=bootstrap_servers, **kwargs)
            await producer.initialize()
            _kafka_producer = producer
    return _kafka_producer


async def close_all_circuit_breaker_clients() -> None:
    """Close all singleton circuit breaker clients."""
    global _opa_client, _redis_client, _kafka_producer

    if _opa_client:
        await _opa_client.close()
        _opa_client = None

    if _redis_client:
        await _redis_client.close()
        _redis_client = None

    if _kafka_producer:
        await _kafka_producer.close()
        _kafka_producer = None


def reset_circuit_breaker_clients() -> None:
    """Reset singleton instances (for testing)."""
    global _opa_client, _redis_client, _kafka_producer
    _opa_client = None
    _redis_client = None
    _kafka_producer = None


# =============================================================================
# Health Check Aggregator
# =============================================================================


async def get_all_circuit_health() -> JSONDict:
    """
    Get aggregated health status for all circuit breaker protected clients.

    Returns:
        Aggregated health status including all clients and overall status
    """
    registry = get_circuit_breaker_registry()
    await registry.initialize_default_circuits()

    # Get health from each client if available
    client_health = {}

    if _opa_client:
        client_health["opa"] = await _opa_client.health_check()

    if _redis_client:
        client_health["redis"] = await _redis_client.health_check()

    if _kafka_producer:
        client_health["kafka"] = await _kafka_producer.health_check()

    # Get registry summary
    registry_summary = registry.get_health_summary()

    # Determine overall status
    critical_issues = []
    if _opa_client and not client_health.get("opa", {}).get("healthy"):
        critical_issues.append("opa")
    if _kafka_producer and _kafka_producer._retry_buffer.get_size() > 5000:
        critical_issues.append("kafka_buffer_high")

    overall_status = "healthy"
    if critical_issues:
        overall_status = "degraded"
    if registry_summary.get("critical_services_open"):
        overall_status = "critical"

    return {
        "overall_status": overall_status,
        "critical_issues": critical_issues,
        "registry_summary": registry_summary,
        "clients": client_health,
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# FastAPI Router for Circuit Breaker Client Health
# =============================================================================


def _health_status_code(overall_status: str) -> int:
    """Map aggregated health status to HTTP status code."""
    if overall_status == "critical":
        return 503
    return 200


async def _single_client_health_response(client: object | None, name: str) -> tuple[dict, int]:
    """Build health response payload and status for a single optional client."""
    if client is None:
        return {"error": f"{name} client not initialized"}, 503

    health = await client.health_check()
    status_code = 200 if health.get("healthy") else 503
    return health, status_code


async def _kafka_flush_response() -> tuple[dict, int]:
    """Build flush response payload for Kafka retry buffer endpoint."""
    if _kafka_producer is None:
        return {"error": "Kafka producer not initialized"}, 503

    results = await _kafka_producer.flush_buffer()
    return results, 200


def create_circuit_breaker_client_router():
    """Create FastAPI router for circuit breaker client health endpoints."""
    try:
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse

        router = APIRouter(prefix="/health/circuit-clients", tags=["Health"])

        @router.get("")
        async def get_all_clients_health():
            health = await get_all_circuit_health()
            return JSONResponse(
                content=health,
                status_code=_health_status_code(health["overall_status"]),
            )

        @router.get("/opa")
        async def get_opa_health():
            payload, status_code = await _single_client_health_response(_opa_client, "OPA")
            return JSONResponse(content=payload, status_code=status_code)

        @router.get("/redis")
        async def get_redis_health():
            payload, status_code = await _single_client_health_response(_redis_client, "Redis")
            return JSONResponse(content=payload, status_code=status_code)

        @router.get("/kafka")
        async def get_kafka_health():
            payload, status_code = await _single_client_health_response(_kafka_producer, "Kafka")
            return JSONResponse(content=payload, status_code=status_code)

        @router.post("/kafka/flush")
        async def flush_kafka_buffer():
            payload, status_code = await _kafka_flush_response()
            return JSONResponse(content=payload, status_code=status_code)

        return router

    except ImportError:
        logger.warning(
            f"[{CONSTITUTIONAL_HASH}] FastAPI not available, "
            f"circuit breaker client router not created"
        )
        return None


__all__ = [
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
