"""
ACGS-2 Enhanced Agent Bus - Chaos Testing Framework
Constitutional Hash: 608508a9bd224290

This module provides controlled chaos injection for validating system resilience
under failure conditions while maintaining constitutional compliance.

Safety Features:
- Constitutional hash validation before any chaos injection
- Automatic cleanup/rollback after test duration
- Max chaos duration limits
- Blast radius controls (limit affected services)
- Emergency stop mechanism
"""

import asyncio
import inspect
import random
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from functools import wraps
from typing import NoReturn

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# SECURITY CONSTANTS (VULN-006)
MAX_LATENCY_MS = 5000  # Prevent total system lockout
MAX_ERROR_RATE = 1.0  # Allow deterministic failure testing
MAX_DURATION_S = 300.0  # 5 minutes absolute max

# Import centralized constitutional hash from shared module
try:
    from enhanced_agent_bus._compat.circuit_breaker import get_circuit_breaker
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    # Fallback for standalone usage
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    get_circuit_breaker = None

try:
    from .exceptions import (
        AgentBusError,
        ConstitutionalHashMismatchError,
        MessageTimeoutError,
    )
except ImportError:
    from exceptions import (  # type: ignore[no-redef]
        AgentBusError,
        ConstitutionalHashMismatchError,
    )

logger = get_logger(__name__)
CHAOS_OPERATION_ERRORS = (
    AttributeError,
    KeyError,
    LookupError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class ChaosType(Enum):
    """Types of chaos scenarios that can be injected."""

    LATENCY = "latency"
    ERROR = "error"
    CIRCUIT_BREAKER = "circuit_breaker"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"
    TIMEOUT = "timeout"


class ResourceType(Enum):
    """Types of resources that can be exhausted."""

    CPU = "cpu"
    MEMORY = "memory"
    CONNECTIONS = "connections"
    DISK_IO = "disk_io"
    NETWORK_BANDWIDTH = "network_bandwidth"


@dataclass
class ChaosScenario:
    """
    Defines a chaos testing scenario with safety controls.

    Constitutional Hash: 608508a9bd224290
    """

    name: str
    chaos_type: ChaosType
    target: str  # Service/component to affect

    # Chaos parameters (specific to chaos_type)
    delay_ms: int = 0  # For LATENCY
    error_rate: float = 0.0  # For ERROR (0.0 - 1.0)
    error_type: type = Exception  # For ERROR
    resource_type: ResourceType | None = None  # For RESOURCE_EXHAUSTION
    resource_level: float = 0.0  # For RESOURCE_EXHAUSTION (0.0 - 1.0)

    # Safety controls
    duration_s: float = 10.0  # Max duration in seconds
    blast_radius: set[str] = field(default_factory=set)  # Allowed targets

    # Constitutional compliance
    constitutional_hash: str = CONSTITUTIONAL_HASH
    require_hash_validation: bool = True

    # Tracking
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    active: bool = False

    def __post_init__(self) -> None:
        """Validate scenario configuration - SECURITY: VULN-006."""
        # Enforce max duration limit
        if self.duration_s > MAX_DURATION_S:
            logger.warning(
                f"Duration {self.duration_s}s exceeds max {MAX_DURATION_S}s, capping to max"
            )
            self.duration_s = MAX_DURATION_S

        # Validate latency (VULN-006)
        if self.delay_ms > MAX_LATENCY_MS:
            logger.warning(
                f"Latency {self.delay_ms}ms exceeds safety limit {MAX_LATENCY_MS}ms, "
                f"capping to limit"
            )
            self.delay_ms = MAX_LATENCY_MS

        # Validate error rate (VULN-006)
        if not 0.0 <= self.error_rate <= 1.0:
            raise ValueError("error_rate must be between 0.0 and 1.0")

        if self.error_rate > MAX_ERROR_RATE:
            logger.warning(
                f"Error rate {self.error_rate} exceeds safety limit {MAX_ERROR_RATE}, "
                f"capping to limit"
            )
            self.error_rate = MAX_ERROR_RATE

        # Validate resource level
        if not 0.0 <= self.resource_level <= 1.0:
            raise ValueError(
                f"resource_level must be between 0.0 and 1.0, got {self.resource_level}"
            )

        # Validate constitutional hash if required
        if self.require_hash_validation and self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ConstitutionalHashMismatchError(
                expected_hash=CONSTITUTIONAL_HASH,
                actual_hash=self.constitutional_hash,
                context=f"ChaosScenario '{self.name}'",
            )

        # Add target to blast radius if not specified
        if not self.blast_radius:
            self.blast_radius = {self.target}

    def is_target_allowed(self, target: str) -> bool:
        """Check if a target is within the blast radius."""
        return target in self.blast_radius

    @property
    def max_duration_s(self) -> float:
        """Safety limit for chaos duration."""
        return MAX_DURATION_S

    def to_dict(self) -> JSONDict:
        """Convert scenario to dictionary."""
        return {
            "name": self.name,
            "chaos_type": self.chaos_type.value,
            "target": self.target,
            "delay_ms": self.delay_ms,
            "error_rate": self.error_rate,
            "error_type": self.error_type.__name__,
            "resource_type": self.resource_type.value if self.resource_type else None,
            "resource_level": self.resource_level,
            "duration_s": self.duration_s,
            "blast_radius": list(self.blast_radius),
            "constitutional_hash": self.constitutional_hash,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }


class ChaosEngine:
    """
    Central engine for injecting controlled chaos into the agent bus.

    Constitutional Hash: 608508a9bd224290

    Features:
    - Constitutional hash validation
    - Automatic cleanup after duration
    - Emergency stop mechanism
    - Blast radius enforcement
    - Metrics collection
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        """Initialize chaos engine with constitutional validation."""
        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ConstitutionalHashMismatchError(
                expected_hash=CONSTITUTIONAL_HASH,
                actual_hash=constitutional_hash,
                context="ChaosEngine initialization",
            )

        self.constitutional_hash = constitutional_hash
        self._active_scenarios: dict[str, ChaosScenario] = {}
        self._cleanup_tasks: dict[str, asyncio.Task] = {}
        self._emergency_stop = False
        self._lock = threading.Lock()

        # Metrics
        self._metrics = {
            "total_scenarios_run": 0,
            "total_latency_injected_ms": 0,
            "total_errors_injected": 0,
            "total_circuit_breakers_forced": 0,
            "active_scenarios": 0,
        }

        logger.info(
            f"[{self.constitutional_hash}] ChaosEngine initialized with constitutional compliance"
        )

    def emergency_stop(self) -> None:
        """Emergency stop all chaos injection immediately."""
        logger.critical(
            f"[{self.constitutional_hash}] EMERGENCY STOP activated - stopping all chaos scenarios"
        )
        self._emergency_stop = True

        with self._lock:
            # Deactivate all scenarios
            for scenario in self._active_scenarios.values():
                scenario.active = False

            # Cancel all cleanup tasks
            for task in self._cleanup_tasks.values():
                if not task.done():
                    task.cancel()

            self._active_scenarios.clear()
            self._cleanup_tasks.clear()
            self._metrics["active_scenarios"] = 0

    def is_stopped(self) -> bool:
        """Check if emergency stop is active."""
        return self._emergency_stop

    def reset(self) -> None:
        """Reset emergency stop and clear all scenarios."""
        logger.info(f"[{self.constitutional_hash}] Resetting chaos engine")
        self._emergency_stop = False
        self._active_scenarios.clear()
        self._cleanup_tasks.clear()
        self._metrics["active_scenarios"] = 0

    def get_metrics(self) -> JSONDict:
        """Get chaos injection metrics."""
        return {
            **self._metrics,
            "constitutional_hash": self.constitutional_hash,
            "emergency_stop_active": self._emergency_stop,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def inject_latency(
        self, target: str, delay_ms: int, duration_s: float, blast_radius: set[str] | None = None
    ) -> ChaosScenario:
        """
        Inject latency into target component.

        Args:
            target: Component to inject latency into
            delay_ms: Delay in milliseconds
            duration_s: How long to inject latency
            blast_radius: Optional set of allowed targets

        Returns:
            Active ChaosScenario
        """
        scenario = ChaosScenario(
            name=f"latency_{target}_{delay_ms}ms",
            chaos_type=ChaosType.LATENCY,
            target=target,
            delay_ms=delay_ms,
            duration_s=duration_s,
            blast_radius=blast_radius or {target},
            constitutional_hash=self.constitutional_hash,
        )

        return await self._activate_scenario(scenario)

    async def inject_errors(
        self,
        target: str,
        error_rate: float,
        error_type: type = Exception,
        duration_s: float = 10.0,
        blast_radius: set[str] | None = None,
    ) -> ChaosScenario:
        """
        Inject random errors into target component.

        Args:
            target: Component to inject errors into
            error_rate: Error rate (0.0 - 1.0)
            error_type: type of exception to raise
            duration_s: How long to inject errors
            blast_radius: Optional set of allowed targets

        Returns:
            Active ChaosScenario
        """
        scenario = ChaosScenario(
            name=f"errors_{target}_{error_rate}",
            chaos_type=ChaosType.ERROR,
            target=target,
            error_rate=error_rate,
            error_type=error_type,
            duration_s=duration_s,
            blast_radius=blast_radius or {target},
            constitutional_hash=self.constitutional_hash,
        )

        return await self._activate_scenario(scenario)

    async def force_circuit_open(
        self, breaker_name: str, duration_s: float, blast_radius: set[str] | None = None
    ) -> ChaosScenario:
        """
        Force a circuit breaker to open state.

        Args:
            breaker_name: Name of circuit breaker to open
            duration_s: How long to keep circuit open
            blast_radius: Optional set of allowed targets

        Returns:
            Active ChaosScenario
        """
        scenario = ChaosScenario(
            name=f"circuit_open_{breaker_name}",
            chaos_type=ChaosType.CIRCUIT_BREAKER,
            target=breaker_name,
            duration_s=duration_s,
            blast_radius=blast_radius or {breaker_name},
            constitutional_hash=self.constitutional_hash,
        )

        # Force circuit breaker open if available
        if get_circuit_breaker:
            try:
                cb = get_circuit_breaker(breaker_name)
                cb.open()
                logger.warning(
                    f"[{self.constitutional_hash}] Forced circuit breaker "
                    f"'{breaker_name}' to OPEN state"
                )
                self._metrics["total_circuit_breakers_forced"] += 1
            except CHAOS_OPERATION_ERRORS as e:
                logger.error(
                    f"[{self.constitutional_hash}] Failed to force circuit "
                    f"breaker '{breaker_name}': {e}"
                )

        return await self._activate_scenario(scenario)

    async def simulate_resource_exhaustion(
        self,
        resource_type: ResourceType,
        level: float,
        target: str = "system",
        duration_s: float = 10.0,
        blast_radius: set[str] | None = None,
    ) -> ChaosScenario:
        """
        Simulate resource exhaustion.

        Args:
            resource_type: type of resource to exhaust
            level: Exhaustion level (0.0 - 1.0)
            target: Target component
            duration_s: How long to simulate exhaustion
            blast_radius: Optional set of allowed targets

        Returns:
            Active ChaosScenario
        """
        scenario = ChaosScenario(
            name=f"resource_{resource_type.value}_{level}",
            chaos_type=ChaosType.RESOURCE_EXHAUSTION,
            target=target,
            resource_type=resource_type,
            resource_level=level,
            duration_s=duration_s,
            blast_radius=blast_radius or {target},
            constitutional_hash=self.constitutional_hash,
        )

        return await self._activate_scenario(scenario)

    async def _activate_scenario(self, scenario: ChaosScenario) -> ChaosScenario:
        """Activate a chaos scenario with automatic cleanup."""
        if self._emergency_stop:
            raise AgentBusError(
                "Cannot activate chaos scenario: emergency stop is active",
                constitutional_hash=self.constitutional_hash,
            )

        with self._lock:
            scenario.active = True
            self._active_scenarios[scenario.name] = scenario
            self._metrics["active_scenarios"] = len(self._active_scenarios)
            self._metrics["total_scenarios_run"] += 1

        logger.warning(
            f"[{self.constitutional_hash}] Activated chaos scenario: "
            f"{scenario.name} (duration: {scenario.duration_s}s)"
        )

        # Schedule automatic cleanup
        cleanup_task = asyncio.create_task(self._schedule_cleanup(scenario))
        self._cleanup_tasks[scenario.name] = cleanup_task

        return scenario

    async def _schedule_cleanup(self, scenario: ChaosScenario) -> None:
        """Schedule automatic cleanup after scenario duration."""
        try:
            await asyncio.sleep(scenario.duration_s)
            await self.deactivate_scenario(scenario.name)
        except asyncio.CancelledError:
            logger.info(
                f"[{self.constitutional_hash}] Cleanup cancelled for scenario: {scenario.name}"
            )
        except CHAOS_OPERATION_ERRORS as e:
            logger.error(
                f"[{self.constitutional_hash}] Error during cleanup for "
                f"scenario {scenario.name}: {e}"
            )

    async def deactivate_scenario(self, scenario_name: str) -> None:
        """Deactivate a chaos scenario and perform cleanup."""
        with self._lock:
            if scenario_name not in self._active_scenarios:
                logger.warning(
                    f"[{self.constitutional_hash}] Scenario '{scenario_name}' "
                    f"not found in active scenarios"
                )
                return

            scenario = self._active_scenarios[scenario_name]
            scenario.active = False

            # Cleanup based on scenario type
            if scenario.chaos_type == ChaosType.CIRCUIT_BREAKER:
                if get_circuit_breaker:
                    try:
                        cb = get_circuit_breaker(scenario.target)
                        cb.close()
                        logger.info(
                            f"[{self.constitutional_hash}] Reset circuit "
                            f"breaker '{scenario.target}' to CLOSED state"
                        )
                    except CHAOS_OPERATION_ERRORS as e:
                        logger.error(
                            f"[{self.constitutional_hash}] Failed to reset "
                            f"circuit breaker '{scenario.target}': {e}"
                        )

            del self._active_scenarios[scenario_name]
            self._metrics["active_scenarios"] = len(self._active_scenarios)

            # Cancel cleanup task if exists
            if scenario_name in self._cleanup_tasks:
                task = self._cleanup_tasks[scenario_name]
                if not task.done():
                    task.cancel()
                del self._cleanup_tasks[scenario_name]

        logger.info(f"[{self.constitutional_hash}] Deactivated chaos scenario: {scenario_name}")

    def get_active_scenarios(self) -> list[ChaosScenario]:
        """Get list of active chaos scenarios."""
        return list(self._active_scenarios.values())

    def should_inject_latency(self, target: str) -> int:
        """
        Check if latency should be injected for target.

        Returns:
            Delay in milliseconds, or 0 if no latency injection
        """
        if self._emergency_stop:
            return 0

        for scenario in self._active_scenarios.values():
            if (
                scenario.active
                and scenario.chaos_type == ChaosType.LATENCY
                and scenario.is_target_allowed(target)
            ):
                self._metrics["total_latency_injected_ms"] += scenario.delay_ms
                return scenario.delay_ms

        return 0

    def should_inject_error(self, target: str) -> type | None:
        """
        Check if error should be injected for target.

        Returns:
            Exception type to raise, or None if no error injection
        """
        if self._emergency_stop:
            return None

        for scenario in self._active_scenarios.values():
            if (
                scenario.active
                and scenario.chaos_type == ChaosType.ERROR
                and scenario.is_target_allowed(target)
            ):
                import secrets

                if secrets.SystemRandom().random() < scenario.error_rate:
                    self._metrics["total_errors_injected"] += 1
                    return scenario.error_type

        return None

    @asynccontextmanager
    async def chaos_context(self, scenario: ChaosScenario) -> AsyncIterator[ChaosScenario]:
        """
        Context manager for chaos scenario lifecycle.

        Usage:
            async with engine.chaos_context(scenario):
                # Chaos is active here
                await run_tests()
            # Chaos is automatically cleaned up here
        """
        activated_scenario = await self._activate_scenario(scenario)
        try:
            yield activated_scenario
        finally:
            await self.deactivate_scenario(scenario.name)


# Global chaos engine instance
_chaos_engine: ChaosEngine | None = None


def get_chaos_engine() -> ChaosEngine:
    """Get or create global chaos engine instance."""
    global _chaos_engine
    if _chaos_engine is None:
        _chaos_engine = ChaosEngine()
    return _chaos_engine


def reset_chaos_engine() -> None:
    """Reset global chaos engine instance."""
    global _chaos_engine
    if _chaos_engine:
        _chaos_engine.reset()
    _chaos_engine = None


# Decorator for chaos testing
def chaos_test(
    scenario_type: str = "latency", target: str = "message_processor", **kwargs: object
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """
    Pytest decorator for easy chaos test creation.

    Usage:
        @chaos_test(scenario_type="latency", target="message_processor", delay_ms=100)
        async def test_latency_resilience():
            # Test runs with latency injection
            ...
    """

    def decorator(func: Callable[..., object]) -> Callable[..., object]:
        @wraps(func)
        async def async_wrapper(*args: object, **kwargs_inner: object) -> object:
            engine = get_chaos_engine()

            # Create scenario based on type
            if scenario_type == "latency":
                scenario = await engine.inject_latency(
                    target=target,
                    delay_ms=kwargs.get("delay_ms", 100),
                    duration_s=kwargs.get("duration_s", 10.0),
                )
            elif scenario_type == "errors":
                scenario = await engine.inject_errors(
                    target=target,
                    error_rate=kwargs.get("error_rate", 0.5),
                    error_type=kwargs.get("error_type", Exception),
                    duration_s=kwargs.get("duration_s", 10.0),
                )
            elif scenario_type == "circuit_breaker":
                scenario = await engine.force_circuit_open(
                    breaker_name=target,
                    duration_s=kwargs.get("duration_s", 10.0),
                )
            else:
                raise ValueError(f"Unknown scenario type: {scenario_type}")

            try:
                result = await func(*args, **kwargs_inner)
                return result
            finally:
                await engine.deactivate_scenario(scenario.name)

        @wraps(func)
        def sync_wrapper(*_args: object, **_kwargs_inner: object) -> NoReturn:
            raise RuntimeError("chaos_test decorator only supports async functions")

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "ChaosEngine",
    # Classes
    "ChaosScenario",
    # Enums
    "ChaosType",
    "ResourceType",
    # Decorators
    "chaos_test",
    # Functions
    "get_chaos_engine",
    "reset_chaos_engine",
]
