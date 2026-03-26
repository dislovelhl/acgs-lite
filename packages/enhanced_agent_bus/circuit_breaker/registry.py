"""
ACGS-2 Circuit Breaker Registry

Constitutional Hash: cdd01ef066bc6cf2

This module implements the circuit breaker registry for managing service-specific
circuit breakers and provides global access functions.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timezone

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .breaker import ServiceCircuitBreaker
from .config import SERVICE_CIRCUIT_CONFIGS, ServiceCircuitConfig, get_service_config
from .enums import CircuitState, ServiceSeverity

logger = get_logger(__name__)


class ServiceCircuitBreakerRegistry:
    """
    Registry for managing service-specific circuit breakers.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    _instance: "ServiceCircuitBreakerRegistry" | None = None
    _circuits: dict[str, ServiceCircuitBreaker]
    _initialized: bool

    def __new__(cls) -> "ServiceCircuitBreakerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._circuits = {}
            cls._instance._initialized = False
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def get_or_create(
        self, service_name: str, config: ServiceCircuitConfig | None = None
    ) -> ServiceCircuitBreaker:
        """Get or create a circuit breaker for a service."""
        if service_name in self._circuits:
            return self._circuits[service_name]
        async with self._lock:
            # Double-checked: another coroutine may have created it while we waited
            if service_name not in self._circuits:
                config = config or get_service_config(service_name)
                self._circuits[service_name] = ServiceCircuitBreaker(config)
        return self._circuits[service_name]

    def get(self, service_name: str) -> ServiceCircuitBreaker | None:
        """Get a circuit breaker by name (if exists)."""
        return self._circuits.get(service_name)

    def get_all_states(self) -> dict[str, JSONDict]:
        """Get states of all circuit breakers."""
        return {name: cb.get_status() for name, cb in self._circuits.items()}

    async def reset(self, service_name: str) -> bool:
        """Reset a specific circuit breaker."""
        if service_name in self._circuits:
            await self._circuits[service_name].reset()
            return True
        return False

    async def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._circuits.values():
            await cb.reset()

    async def initialize_default_circuits(self) -> None:
        """Initialize circuit breakers for all configured services."""
        if self._initialized:
            return

        for service_name, config in SERVICE_CIRCUIT_CONFIGS.items():
            await self.get_or_create(service_name, config)

        self._initialized = True
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Initialized {len(SERVICE_CIRCUIT_CONFIGS)} "
            f"service circuit breakers"
        )

    def get_health_summary(self) -> JSONDict:
        """Get overall circuit breaker health summary."""
        total = len(self._circuits)
        closed_count = 0
        half_open_count = 0
        open_count = 0
        critical_open = []

        for name, cb in self._circuits.items():
            if cb.state == CircuitState.CLOSED:
                closed_count += 1
            elif cb.state == CircuitState.HALF_OPEN:
                half_open_count += 1
            else:
                open_count += 1
                if cb.config.severity == ServiceSeverity.CRITICAL:
                    critical_open.append(name)

        # Calculate health score
        if total == 0:  # noqa: SIM108
            health_score = 1.0
        else:
            health_score = (closed_count + (half_open_count * 0.5)) / total

        # Determine overall status
        if critical_open:
            status = "critical"
        elif health_score >= 0.7:
            status = "healthy"
        elif health_score >= 0.5:
            status = "degraded"
        else:
            status = "critical"

        return {
            "status": status,
            "health_score": round(health_score, 3),
            "total_circuits": total,
            "closed": closed_count,
            "half_open": half_open_count,
            "open": open_count,
            "critical_services_open": critical_open,
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


# Global registry instance
_registry: ServiceCircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> ServiceCircuitBreakerRegistry:
    """Get or create the global circuit breaker registry."""
    global _registry
    if _registry is None:
        _registry = ServiceCircuitBreakerRegistry()
    return _registry


def reset_circuit_breaker_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
    ServiceCircuitBreakerRegistry._instance = None


async def get_service_circuit_breaker(
    service_name: str, config: ServiceCircuitConfig | None = None
) -> ServiceCircuitBreaker:
    """Get or create a circuit breaker for a service."""
    registry = get_circuit_breaker_registry()
    return await registry.get_or_create(service_name, config)


__all__ = [
    "ServiceCircuitBreakerRegistry",
    "get_circuit_breaker_registry",
    "get_service_circuit_breaker",
    "reset_circuit_breaker_registry",
]
