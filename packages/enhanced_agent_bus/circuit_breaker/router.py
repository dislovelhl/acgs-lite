"""
ACGS-2 Circuit Breaker FastAPI Router

Constitutional Hash: cdd01ef066bc6cf2

This module provides FastAPI endpoints for circuit breaker health monitoring.
"""

from datetime import UTC, datetime

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import CircuitState
from .registry import get_circuit_breaker_registry

logger = get_logger(__name__)


def create_circuit_health_router():
    """Create FastAPI router for circuit breaker health endpoints."""
    try:
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse

        router = APIRouter(prefix="/health", tags=["Health"])

        @router.get("/circuits")
        async def get_circuit_states():
            """
            Get status of all circuit breakers.

            Returns:
                JSONResponse with circuit breaker states and health summary
            """
            registry = get_circuit_breaker_registry()

            # Initialize default circuits if not already done
            await registry.initialize_default_circuits()

            summary = registry.get_health_summary()
            states = registry.get_all_states()

            return JSONResponse(
                content={
                    "summary": summary,
                    "circuits": states,
                },
                status_code=200 if summary["status"] != "critical" else 503,
            )

        @router.get("/circuits/{service_name}")
        async def get_circuit_state(service_name: str):
            """
            Get status of a specific circuit breaker.

            Args:
                service_name: Name of the service

            Returns:
                JSONResponse with circuit breaker status
            """
            registry = get_circuit_breaker_registry()
            cb = registry.get(service_name)

            if cb is None:
                return JSONResponse(
                    content={
                        "error": f"Circuit breaker '{service_name}' not found",
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                    status_code=404,
                )

            status = cb.get_status()
            return JSONResponse(
                content=status,
                status_code=200 if cb.state != CircuitState.OPEN else 503,
            )

        @router.post("/circuits/{service_name}/reset")
        async def reset_circuit(service_name: str):
            """
            Reset a specific circuit breaker to closed state.

            Args:
                service_name: Name of the service

            Returns:
                JSONResponse with reset confirmation
            """
            registry = get_circuit_breaker_registry()
            success = await registry.reset(service_name)

            if not success:
                return JSONResponse(
                    content={
                        "error": f"Circuit breaker '{service_name}' not found",
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                    status_code=404,
                )

            return JSONResponse(
                content={
                    "service": service_name,
                    "action": "reset",
                    "new_state": "closed",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                status_code=200,
            )

        @router.post("/circuits/reset-all")
        async def reset_all_circuits():
            """
            Reset all circuit breakers to closed state.

            Returns:
                JSONResponse with reset confirmation
            """
            registry = get_circuit_breaker_registry()
            await registry.reset_all()

            return JSONResponse(
                content={
                    "action": "reset_all",
                    "circuits_reset": list(registry.get_all_states().keys()),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                status_code=200,
            )

        return router

    except ImportError:
        logger.warning(
            f"[{CONSTITUTIONAL_HASH}] FastAPI not available, circuit health router not created"
        )
        return None


__all__ = [
    "create_circuit_health_router",
]
