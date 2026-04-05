"""
ACGS-2 Enhanced Agent Bus Health Routes
Constitutional Hash: 608508a9bd224290

This module provides health check and statistics endpoints.
"""

from __future__ import annotations

import hmac
import os
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ...api_models import (
    ErrorResponse,
    HealthResponse,
    LatencyTracker,
    ServiceUnavailableResponse,
)
from ..api_key_auth import require_api_key
from ..config import API_VERSION
from ..dependencies import get_agent_bus
from ..middleware import logger
from ..rate_limiting import RATE_LIMITING_AVAILABLE

try:
    from prometheus_client import Info as PrometheusInfo

    constitutional_info = PrometheusInfo(
        "acgs_constitutional_hash", "Constitutional hash loaded by this service"
    )
    constitutional_info.info({"hash": CONSTITUTIONAL_HASH, "service": "enhanced-agent-bus"})
except (ImportError, ValueError):
    # ValueError: metric already registered (e.g. api-gateway health registered it first)
    pass

SLA_P99_TARGET_MS = 100.0
DEFAULT_ACTIVE_CONNECTIONS = 0
DEFAULT_UPTIME_SECONDS = 0

if TYPE_CHECKING:
    from ...message_processor import MessageProcessor

router = APIRouter()

_latency_tracker = LatencyTracker()
STATS_CALCULATION_ERROR = "Failed to calculate statistics"


def _circuit_breaker_available() -> bool:
    """Check whether circuit breaker dependency is available."""
    try:
        import importlib.util
    except ImportError:
        return False

    return importlib.util.find_spec("pybreaker") is not None


async def _collect_stats_payload(bus: MessageProcessor | dict | None = None) -> JSONDict:
    """Collect latency metrics and build stats payload."""
    try:
        metrics = await _latency_tracker.get_metrics()
        total_messages = await _latency_tracker.get_total_messages()
        sla_p99_met = metrics.sample_count == 0 or metrics.p99_ms < SLA_P99_TARGET_MS
        payload: JSONDict = {
            "total_messages": total_messages,
            "latency_p50_ms": metrics.p50_ms,
            "latency_p95_ms": metrics.p95_ms,
            "latency_p99_ms": metrics.p99_ms,
            "latency_min_ms": metrics.min_ms,
            "latency_max_ms": metrics.max_ms,
            "latency_mean_ms": metrics.mean_ms,
            "latency_sample_count": metrics.sample_count,
            "latency_window_size": metrics.window_size,
            "sla_p99_target_ms": SLA_P99_TARGET_MS,
            "sla_p99_met": sla_p99_met,
            "active_connections": DEFAULT_ACTIVE_CONNECTIONS,
            "uptime_seconds": DEFAULT_UPTIME_SECONDS,
        }

        if bus is not None and hasattr(bus, "get_metrics"):
            try:
                bus_metrics = bus.get_metrics()
                if isinstance(bus_metrics, dict):
                    payload["opa_multipath_evaluation_count"] = bus_metrics.get(
                        "opa_multipath_evaluation_count", 0
                    )
                    payload["opa_multipath_last_path_count"] = bus_metrics.get(
                        "opa_multipath_last_path_count", 0
                    )
                    payload["opa_multipath_last_diversity_ratio"] = bus_metrics.get(
                        "opa_multipath_last_diversity_ratio", 0.0
                    )
                    payload["opa_multipath_last_support_family_count"] = bus_metrics.get(
                        "opa_multipath_last_support_family_count", 0
                    )
            except (AttributeError, TypeError, ValueError):
                payload["opa_multipath_evaluation_count"] = 0
                payload["opa_multipath_last_path_count"] = 0
                payload["opa_multipath_last_diversity_ratio"] = 0.0
                payload["opa_multipath_last_support_family_count"] = 0

        return payload
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=STATS_CALCULATION_ERROR) from e


CIRCUIT_BREAKER_AVAILABLE = _circuit_breaker_available()


def get_latency_tracker() -> LatencyTracker:
    """Get the latency tracker instance."""
    return _latency_tracker


def _is_constitutional_hash_valid() -> bool:
    """Return True when runtime hash matches canonical hash."""
    configured_hash = os.getenv("CONSTITUTIONAL_HASH", CONSTITUTIONAL_HASH)
    return hmac.compare_digest(configured_hash, CONSTITUTIONAL_HASH)


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint for service monitoring.

    This endpoint MUST always return 200, even when the agent bus is not
    initialised.  It reads bus availability from ``request.app.state``
    directly (no ``Depends``) so that a missing bus never causes a 503.
    """
    bus = getattr(request.app.state, "agent_bus", None)
    agent_bus_status = "healthy" if bus else "unhealthy"

    return HealthResponse(
        status=agent_bus_status,
        service="enhanced-agent-bus",
        version=API_VERSION,
        agent_bus_status=agent_bus_status,
        rate_limiting_enabled=RATE_LIMITING_AVAILABLE,
        circuit_breaker_enabled=CIRCUIT_BREAKER_AVAILABLE,
    )


@router.get("/health/live", response_model=JSONDict)
async def liveness_check() -> JSONDict:
    """Kubernetes liveness probe."""
    return {
        "status": "alive",
        "service": "enhanced-agent-bus",
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }


@router.get("/health/ready", response_model=JSONDict)
async def readiness_check(request: Request, response: Response) -> JSONDict:
    """Kubernetes readiness probe with constitutional hash validation."""
    bus = getattr(request.app.state, "agent_bus", None)
    bus_ready = bus is not None
    runtime_hash_valid = _is_constitutional_hash_valid()
    probe_hash = request.headers.get("X-Constitutional-Hash")
    probe_hash_valid = probe_hash is None or hmac.compare_digest(probe_hash, CONSTITUTIONAL_HASH)
    ready = bus_ready and runtime_hash_valid and probe_hash_valid

    if not ready:
        response.status_code = 503

    return {
        "ready": ready,
        "service": "enhanced-agent-bus",
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "checks": {
            "agent_bus": "up" if bus_ready else "down",
            "constitutional_hash_runtime": "up" if runtime_hash_valid else "down",
            "constitutional_hash_probe_header": "up" if probe_hash_valid else "down",
        },
    }


@router.get("/health/startup", response_model=JSONDict)
@router.get("/startupz", response_model=JSONDict)
async def startup_check(request: Request, response: Response) -> JSONDict:
    """Kubernetes startup probe — lightweight, no external dependency calls.

    Verifies only that the application has initialised far enough for the
    ``agent_bus`` state marker to exist and that the constitutional hash
    constant is loaded and valid.
    """
    bus_initialised = getattr(request.app.state, "agent_bus", None) is not None
    hash_valid = _is_constitutional_hash_valid()
    ready = bus_initialised and hash_valid

    if not ready:
        response.status_code = 503
        return {
            "ready": False,
            "service": "enhanced-agent-bus",
            "checks": {
                "agent_bus_initialised": bus_initialised,
                "constitutional_hash_valid": hash_valid,
            },
        }

    return {
        "ready": True,
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "service": "enhanced-agent-bus",
    }


@router.get("/health/kafka", response_model=JSONDict)
async def kafka_health() -> JSONDict:
    """Kafka dependency health check."""
    try:
        from aiokafka.admin import AIOKafkaAdminClient

        kafka_url = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
        client = AIOKafkaAdminClient(bootstrap_servers=kafka_url)
        await client.start()
        await client.close()
        return {"status": "healthy", "dependency": "kafka"}
    except Exception:
        return {"status": "unavailable", "dependency": "kafka"}


@router.get("/health/redis", response_model=JSONDict)
async def redis_health() -> JSONDict:
    """Redis dependency health check."""
    try:
        import redis.asyncio as aioredis

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = aioredis.from_url(redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        return {"status": "healthy", "dependency": "redis"}
    except Exception:
        return {"status": "unavailable", "dependency": "redis"}


@router.get(
    "/api/v1/stats",
    responses={
        500: {
            "model": ErrorResponse,
            "description": "Internal Server Error - Failed to calculate statistics",
        },
        503: {
            "model": ServiceUnavailableResponse,
            "description": "Service Unavailable - Agent bus not initialized",
        },
    },
    summary="Get agent bus statistics",
    tags=["Statistics"],
)
async def get_stats(
    _api_key: str = Depends(require_api_key),
    bus: MessageProcessor | dict = Depends(get_agent_bus),
) -> JSONDict:
    """Get agent bus statistics including P99/P95/P50 latency metrics.

    Returns latency percentiles calculated from a sliding window of recent requests.
    Configure window size via LATENCY_WINDOW_SIZE environment variable (default: 1000).

    **Performance Metrics:**
    - latency_p50_ms: 50th percentile (median) latency
    - latency_p95_ms: 95th percentile latency
    - latency_p99_ms: 99th percentile latency (SLA target: <100ms)
    - latency_min_ms/latency_max_ms: Range of latencies
    - latency_mean_ms: Average latency

    **Message Statistics:**
    - total_messages: Total messages processed (all time)
    - latency_sample_count: Samples in current window
    - latency_window_size: Maximum samples retained

    **SLA Compliance:**
    - sla_p99_target_ms: P99 latency SLA target (100ms)
    - sla_p99_met: Boolean indicating if P99 meets target
    """
    return await _collect_stats_payload(bus)


__all__ = [
    "get_latency_tracker",
    "get_stats",
    "health_check",
    "kafka_health",
    "redis_health",
    "router",
    "startup_check",
]
