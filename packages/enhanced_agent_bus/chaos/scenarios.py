"""
ACGS-2 Enhanced Agent Bus - Chaos Scenarios
Constitutional Hash: cdd01ef066bc6cf2

Predefined failure scenarios for chaos engineering experiments.
Each scenario simulates a specific type of infrastructure failure
while maintaining constitutional compliance.

Scenarios:
- NetworkPartitionScenario: Simulate network partitions between services
- LatencyInjectionScenario: Inject latency into service calls
- MemoryPressureScenario: Simulate memory pressure/exhaustion
- CPUStressScenario: Simulate CPU load spikes
- DependencyFailureScenario: Simulate dependency failures (Redis, OPA down)

Expert Reference: Michael Nygard (Release It!)
"""

import asyncio
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Import centralized constitutional hash
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Safety limits
MAX_DURATION_S = 300.0  # 5 minutes max
MAX_LATENCY_MS = 5000  # 5 seconds max latency injection
MAX_MEMORY_PERCENT = 80.0  # Don't exceed 80% memory pressure
MAX_CPU_PERCENT = 90.0  # Don't exceed 90% CPU stress


class ScenarioStatus(str, Enum):  # noqa: UP042
    """Status of a chaos scenario."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class PartitionType(str, Enum):  # noqa: UP042
    """Types of network partitions."""

    FULL = "full"  # Complete isolation
    PARTIAL = "partial"  # Intermittent connectivity
    ONE_WAY = "one_way"  # One direction works, other doesn't
    SLOW = "slow"  # Extreme latency (not packet loss)


class DependencyType(str, Enum):  # noqa: UP042
    """Types of dependencies that can fail."""

    REDIS = "redis"
    OPA = "opa"
    KAFKA = "kafka"
    DATABASE = "database"
    EXTERNAL_API = "external_api"
    BLOCKCHAIN = "blockchain"


@dataclass
class ScenarioResult:
    """
    Result of executing a chaos scenario.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    scenario_name: str
    status: ScenarioStatus
    started_at: datetime
    ended_at: datetime | None = None
    duration_s: float = 0.0
    events: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    rollback_performed: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "scenario_name": self.scenario_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_s": self.duration_s,
            "events": self.events,
            "errors": self.errors,
            "metrics": self.metrics,
            "rollback_performed": self.rollback_performed,
            "constitutional_hash": self.constitutional_hash,
        }


class BaseScenario(ABC):
    """
    Abstract base class for chaos scenarios.

    Constitutional Hash: cdd01ef066bc6cf2

    All scenarios must:
    - Validate constitutional hash before execution
    - Provide rollback capability
    - Respect safety limits
    - Log all actions for audit
    """

    def __init__(
        self,
        name: str,
        duration_s: float = 30.0,
        blast_radius: set[str] | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """
        Initialize base scenario.

        Args:
            name: Scenario name
            duration_s: Duration in seconds
            blast_radius: Set of allowed targets
            constitutional_hash: Constitutional hash for validation
        """
        if constitutional_hash != CONSTITUTIONAL_HASH:
            from packages.enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

            raise ConstitutionalHashMismatchError(
                expected_hash=CONSTITUTIONAL_HASH,
                actual_hash=constitutional_hash,
                context=f"Scenario '{name}'",
            )

        # Enforce max duration
        if duration_s > MAX_DURATION_S:
            logger.warning(f"Duration {duration_s}s exceeds max {MAX_DURATION_S}s, capping")
            duration_s = MAX_DURATION_S

        self.name = name
        self.duration_s = duration_s
        self.blast_radius = blast_radius or set()
        self.constitutional_hash = constitutional_hash
        self._status = ScenarioStatus.PENDING
        self._result: ScenarioResult | None = None
        self._lock = threading.Lock()
        self._cancelled = False

    @property
    def status(self) -> ScenarioStatus:
        """Get current scenario status."""
        return self._status

    @property
    def result(self) -> ScenarioResult | None:
        """Get scenario result."""
        return self._result

    def is_target_allowed(self, target: str) -> bool:
        """Check if a target is within blast radius."""
        if not self.blast_radius:
            return True  # No restrictions
        return target in self.blast_radius

    @abstractmethod
    async def execute(self) -> ScenarioResult:
        """Execute the chaos scenario."""
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback any changes made by the scenario."""
        pass

    def cancel(self) -> None:
        """Cancel the scenario."""
        self._cancelled = True
        self._status = ScenarioStatus.CANCELLED
        logger.info(f"[{self.constitutional_hash}] Scenario '{self.name}' cancelled")

    def to_dict(self) -> JSONDict:
        """Convert scenario to dictionary."""
        return {
            "name": self.name,
            "type": self.__class__.__name__,
            "duration_s": self.duration_s,
            "blast_radius": list(self.blast_radius),
            "status": self._status.value,
            "constitutional_hash": self.constitutional_hash,
        }


class NetworkPartitionScenario(BaseScenario):
    """
    Simulate network partition between services.

    Constitutional Hash: cdd01ef066bc6cf2

    This scenario simulates network issues by:
    - Tracking which services should be "partitioned"
    - Providing hooks for services to check connectivity
    - Simulating various partition types (full, partial, one-way)
    """

    def __init__(
        self,
        target_service: str,
        duration_s: float = 30.0,
        partition_type: PartitionType = PartitionType.FULL,
        affected_services: list[str] | None = None,
        packet_loss_rate: float = 1.0,  # For partial partitions
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        super().__init__(
            name=f"network_partition_{target_service}",
            duration_s=duration_s,
            blast_radius={target_service} | set(affected_services or []),
            constitutional_hash=constitutional_hash,
        )
        self.target_service = target_service
        self.partition_type = partition_type
        self.affected_services = affected_services or []
        self.packet_loss_rate = min(packet_loss_rate, 1.0)
        self._partitioned = False

    def is_partitioned(self, source: str, target: str) -> bool:
        """
        Check if communication between source and target is partitioned.

        Returns True if the request should be blocked/failed.
        """
        if not self._partitioned:
            return False

        # Check if either endpoint is in the partition
        is_affected = (
            source == self.target_service
            or target == self.target_service
            or source in self.affected_services
            or target in self.affected_services
        )

        if not is_affected:
            return False

        if self.partition_type == PartitionType.FULL:
            return True

        elif self.partition_type == PartitionType.PARTIAL:
            # Probabilistic packet loss
            import secrets

            return secrets.SystemRandom().random() < self.packet_loss_rate

        elif self.partition_type == PartitionType.ONE_WAY:
            # Only block requests TO the target service
            return target == self.target_service

        elif self.partition_type == PartitionType.SLOW:
            return False  # Handled by latency injection

        return False

    async def execute(self) -> ScenarioResult:
        """Execute network partition scenario."""
        started_at = datetime.now(UTC)
        events: list[str] = []
        errors: list[str] = []

        try:
            self._status = ScenarioStatus.RUNNING
            events.append(f"Starting network partition for {self.target_service}")
            events.append(f"Partition type: {self.partition_type.value}")
            events.append(f"Duration: {self.duration_s}s")

            logger.warning(
                f"[{self.constitutional_hash}] Network partition active: "
                f"{self.target_service} ({self.partition_type.value})"
            )

            # Activate partition
            self._partitioned = True

            # Wait for duration or cancellation
            elapsed = 0.0
            while elapsed < self.duration_s and not self._cancelled:
                await asyncio.sleep(0.1)
                elapsed += 0.1

            if self._cancelled:
                events.append("Scenario cancelled before completion")
                self._status = ScenarioStatus.CANCELLED
            else:
                events.append("Partition duration completed")
                self._status = ScenarioStatus.COMPLETED

        except (TimeoutError, RuntimeError, ValueError, TypeError) as e:
            errors.append(f"Scenario error ({type(e).__name__}): {e!s}")
            self._status = ScenarioStatus.FAILED
            logger.error(f"[{self.constitutional_hash}] Network partition scenario failed: {e}")

        finally:
            # Always deactivate partition
            self._partitioned = False
            events.append("Network partition deactivated")

        ended_at = datetime.now(UTC)
        self._result = ScenarioResult(
            scenario_name=self.name,
            status=self._status,
            started_at=started_at,
            ended_at=ended_at,
            duration_s=(ended_at - started_at).total_seconds(),
            events=events,
            errors=errors,
        )
        return self._result

    async def rollback(self) -> None:
        """Rollback network partition."""
        self._partitioned = False
        logger.info(
            f"[{self.constitutional_hash}] Network partition rolled back: {self.target_service}"
        )


class LatencyInjectionScenario(BaseScenario):
    """
    Inject latency into service calls.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        target_service: str,
        latency_ms: int = 100,
        duration_s: float = 30.0,
        latency_variance_ms: int = 0,  # Random variance
        affected_operations: list[str] | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        super().__init__(
            name=f"latency_injection_{target_service}",
            duration_s=duration_s,
            blast_radius={target_service},
            constitutional_hash=constitutional_hash,
        )

        # Enforce max latency
        if latency_ms > MAX_LATENCY_MS:
            logger.warning(f"Latency {latency_ms}ms exceeds max, capping to {MAX_LATENCY_MS}ms")
            latency_ms = MAX_LATENCY_MS

        self.target_service = target_service
        self.latency_ms = latency_ms
        self.latency_variance_ms = latency_variance_ms
        self.affected_operations = affected_operations or []
        self._active = False

    def get_latency(self, operation: str | None = None) -> int:
        """
        Get the latency to inject for a given operation.

        Returns 0 if injection is not active or operation is not affected.
        """
        if not self._active:
            return 0

        if self.affected_operations and operation not in self.affected_operations:
            return 0

        base_latency = self.latency_ms
        if self.latency_variance_ms > 0:
            import secrets

            variance = secrets.SystemRandom().randint(
                -self.latency_variance_ms, self.latency_variance_ms
            )
            base_latency = max(0, base_latency + variance)

        return base_latency

    async def execute(self) -> ScenarioResult:
        """Execute latency injection scenario."""
        started_at = datetime.now(UTC)
        events: list[str] = []
        errors: list[str] = []

        try:
            self._status = ScenarioStatus.RUNNING
            events.append(f"Injecting {self.latency_ms}ms latency to {self.target_service}")

            logger.warning(
                f"[{self.constitutional_hash}] Latency injection active: "
                f"{self.target_service} +{self.latency_ms}ms"
            )

            self._active = True

            # Wait for duration
            elapsed = 0.0
            while elapsed < self.duration_s and not self._cancelled:
                await asyncio.sleep(0.1)
                elapsed += 0.1

            if self._cancelled:
                events.append("Scenario cancelled")
                self._status = ScenarioStatus.CANCELLED
            else:
                self._status = ScenarioStatus.COMPLETED

        except (TimeoutError, RuntimeError, ValueError) as e:
            errors.append(f"{type(e).__name__}: {e}")
            self._status = ScenarioStatus.FAILED

        finally:
            self._active = False
            events.append("Latency injection deactivated")

        ended_at = datetime.now(UTC)
        self._result = ScenarioResult(
            scenario_name=self.name,
            status=self._status,
            started_at=started_at,
            ended_at=ended_at,
            duration_s=(ended_at - started_at).total_seconds(),
            events=events,
            errors=errors,
        )
        return self._result

    async def rollback(self) -> None:
        """Rollback latency injection."""
        self._active = False


class MemoryPressureScenario(BaseScenario):
    """
    Simulate memory pressure.

    Constitutional Hash: cdd01ef066bc6cf2

    NOTE: This scenario simulates memory pressure by signaling to components
    that memory is constrained. It does NOT actually consume memory to avoid
    destabilizing the system.
    """

    def __init__(
        self,
        target_percent: float = 80.0,
        duration_s: float = 30.0,
        ramp_up_s: float = 5.0,  # Gradual pressure increase
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        super().__init__(
            name=f"memory_pressure_{target_percent}%",
            duration_s=duration_s,
            constitutional_hash=constitutional_hash,
        )

        # Enforce max memory percent
        if target_percent > MAX_MEMORY_PERCENT:
            logger.warning(f"Target {target_percent}% exceeds max {MAX_MEMORY_PERCENT}%, capping")
            target_percent = MAX_MEMORY_PERCENT

        self.target_percent = target_percent
        self.ramp_up_s = ramp_up_s
        self._current_pressure = 0.0
        self._active = False

    @property
    def current_pressure(self) -> float:
        """Get current simulated memory pressure level."""
        return self._current_pressure

    def is_memory_constrained(self) -> bool:
        """Check if memory is currently constrained."""
        return self._active and self._current_pressure >= 70.0

    async def execute(self) -> ScenarioResult:
        """Execute memory pressure scenario."""
        started_at = datetime.now(UTC)
        events: list[str] = []
        errors: list[str] = []

        try:
            self._status = ScenarioStatus.RUNNING
            self._active = True
            events.append(f"Starting memory pressure simulation to {self.target_percent}%")

            logger.warning(
                f"[{self.constitutional_hash}] Memory pressure simulation active: "
                f"target {self.target_percent}%"
            )

            # Ramp up phase
            if self.ramp_up_s > 0:
                steps = int(self.ramp_up_s * 10)
                increment = self.target_percent / steps
                for i in range(steps):
                    if self._cancelled:
                        break
                    self._current_pressure = min(self.target_percent, (i + 1) * increment)
                    await asyncio.sleep(0.1)

            events.append(f"Reached target pressure: {self._current_pressure:.1f}%")

            # Maintain pressure
            hold_duration = self.duration_s - self.ramp_up_s
            elapsed = 0.0
            while elapsed < hold_duration and not self._cancelled:
                await asyncio.sleep(0.1)
                elapsed += 0.1

            if self._cancelled:
                events.append("Scenario cancelled")
                self._status = ScenarioStatus.CANCELLED
            else:
                self._status = ScenarioStatus.COMPLETED

        except (TimeoutError, RuntimeError, ValueError) as e:
            errors.append(f"{type(e).__name__}: {e}")
            self._status = ScenarioStatus.FAILED

        finally:
            self._current_pressure = 0.0
            self._active = False
            events.append("Memory pressure released")

        ended_at = datetime.now(UTC)
        self._result = ScenarioResult(
            scenario_name=self.name,
            status=self._status,
            started_at=started_at,
            ended_at=ended_at,
            duration_s=(ended_at - started_at).total_seconds(),
            events=events,
            errors=errors,
            metrics={"peak_pressure_percent": self.target_percent},
        )
        return self._result

    async def rollback(self) -> None:
        """Rollback memory pressure."""
        self._current_pressure = 0.0
        self._active = False


class CPUStressScenario(BaseScenario):
    """
    Simulate CPU stress.

    Constitutional Hash: cdd01ef066bc6cf2

    NOTE: Similar to memory pressure, this signals CPU constraint without
    actually consuming CPU cycles.
    """

    def __init__(
        self,
        target_percent: float = 80.0,
        duration_s: float = 30.0,
        cores_affected: int = 1,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        super().__init__(
            name=f"cpu_stress_{target_percent}%",
            duration_s=duration_s,
            constitutional_hash=constitutional_hash,
        )

        if target_percent > MAX_CPU_PERCENT:
            logger.warning(f"Target {target_percent}% exceeds max {MAX_CPU_PERCENT}%, capping")
            target_percent = MAX_CPU_PERCENT

        self.target_percent = target_percent
        self.cores_affected = cores_affected
        self._current_load = 0.0
        self._active = False

    @property
    def current_load(self) -> float:
        """Get current simulated CPU load."""
        return self._current_load

    def is_cpu_constrained(self) -> bool:
        """Check if CPU is currently constrained."""
        return self._active and self._current_load >= 70.0

    async def execute(self) -> ScenarioResult:
        """Execute CPU stress scenario."""
        started_at = datetime.now(UTC)
        events: list[str] = []
        errors: list[str] = []

        try:
            self._status = ScenarioStatus.RUNNING
            self._active = True
            self._current_load = self.target_percent
            events.append(
                f"CPU stress active: {self.target_percent}% on {self.cores_affected} cores"
            )

            logger.warning(
                f"[{self.constitutional_hash}] CPU stress simulation active: {self.target_percent}%"
            )

            # Maintain stress
            elapsed = 0.0
            while elapsed < self.duration_s and not self._cancelled:
                await asyncio.sleep(0.1)
                elapsed += 0.1

            if self._cancelled:
                events.append("Scenario cancelled")
                self._status = ScenarioStatus.CANCELLED
            else:
                self._status = ScenarioStatus.COMPLETED

        except (TimeoutError, RuntimeError, ValueError) as e:
            errors.append(f"{type(e).__name__}: {e}")
            self._status = ScenarioStatus.FAILED

        finally:
            self._current_load = 0.0
            self._active = False
            events.append("CPU stress released")

        ended_at = datetime.now(UTC)
        self._result = ScenarioResult(
            scenario_name=self.name,
            status=self._status,
            started_at=started_at,
            ended_at=ended_at,
            duration_s=(ended_at - started_at).total_seconds(),
            events=events,
            errors=errors,
            metrics={"peak_load_percent": self.target_percent},
        )
        return self._result

    async def rollback(self) -> None:
        """Rollback CPU stress."""
        self._current_load = 0.0
        self._active = False


class DependencyFailureScenario(BaseScenario):
    """
    Simulate dependency failures (Redis, OPA, Kafka down).

    Constitutional Hash: cdd01ef066bc6cf2

    This scenario simulates external dependency failures by providing
    hooks that services can use to check dependency health.
    """

    def __init__(
        self,
        dependency: DependencyType | str,
        failure_mode: str = "complete",  # complete, intermittent, slow
        duration_s: float = 30.0,
        error_message: str = "Connection refused",
        intermittent_rate: float = 0.5,  # For intermittent failures
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        # Determine the dependency value
        self.dependency: DependencyType | str  # Can be enum or string
        if isinstance(dependency, DependencyType):
            dependency_value = dependency.value
            self.dependency = dependency
        else:
            # Convert string to DependencyType if possible
            try:
                dependency_enum = DependencyType(dependency.lower())
                dependency_value = dependency_enum.value
                self.dependency = dependency_enum
            except ValueError:
                # Use the string directly for unknown dependencies
                dependency_value = dependency.lower()
                self.dependency = dependency

        self._dependency_value = dependency_value

        super().__init__(
            name=f"dependency_failure_{dependency_value}",
            duration_s=duration_s,
            blast_radius={dependency_value},
            constitutional_hash=constitutional_hash,
        )
        self.failure_mode = failure_mode
        self.error_message = error_message
        self.intermittent_rate = intermittent_rate
        self._active = False
        self._call_count = 0
        self._failure_count = 0

    def should_fail(self) -> bool:
        """
        Check if the dependency call should fail.

        Returns True if the call should be failed.
        """
        if not self._active:
            return False

        self._call_count += 1

        if self.failure_mode == "complete":
            self._failure_count += 1
            return True

        elif self.failure_mode == "intermittent":
            import secrets

            if secrets.SystemRandom().random() < self.intermittent_rate:
                self._failure_count += 1
                return True
            return False

        elif self.failure_mode == "slow":
            return False  # Handled by latency

        return False

    def get_failure_error(self) -> Exception:
        """Get the exception to raise for a failure."""
        dep_name = (
            self._dependency_value
            if hasattr(self, "_dependency_value")
            else (
                self.dependency.value
                if isinstance(self.dependency, DependencyType)
                else str(self.dependency)
            )
        )
        return ConnectionError(f"{dep_name}: {self.error_message}")

    async def execute(self) -> ScenarioResult:
        """Execute dependency failure scenario."""
        started_at = datetime.now(UTC)
        events: list[str] = []
        errors: list[str] = []

        try:
            self._status = ScenarioStatus.RUNNING
            self._active = True
            self._call_count = 0
            self._failure_count = 0
            events.append(f"Simulating {self._dependency_value} failure ({self.failure_mode})")

            logger.warning(
                f"[{self.constitutional_hash}] Dependency failure active: "
                f"{self._dependency_value} ({self.failure_mode})"
            )

            # Maintain failure
            elapsed = 0.0
            while elapsed < self.duration_s and not self._cancelled:
                await asyncio.sleep(0.1)
                elapsed += 0.1

            if self._cancelled:
                events.append("Scenario cancelled")
                self._status = ScenarioStatus.CANCELLED
            else:
                self._status = ScenarioStatus.COMPLETED

        except (TimeoutError, RuntimeError, ValueError) as e:
            errors.append(f"{type(e).__name__}: {e}")
            self._status = ScenarioStatus.FAILED

        finally:
            self._active = False
            events.append(
                f"Dependency restored. Calls: {self._call_count}, Failures: {self._failure_count}"
            )

        ended_at = datetime.now(UTC)
        self._result = ScenarioResult(
            scenario_name=self.name,
            status=self._status,
            started_at=started_at,
            ended_at=ended_at,
            duration_s=(ended_at - started_at).total_seconds(),
            events=events,
            errors=errors,
            metrics={
                "total_calls": float(self._call_count),
                "failed_calls": float(self._failure_count),
                "failure_rate": (
                    self._failure_count / self._call_count if self._call_count > 0 else 0.0
                ),
            },
        )
        return self._result

    async def rollback(self) -> None:
        """Rollback dependency failure."""
        self._active = False


class ScenarioExecutor:
    """
    Executes chaos scenarios with safety controls.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH) -> None:
        if constitutional_hash != CONSTITUTIONAL_HASH:
            from packages.enhanced_agent_bus.exceptions import ConstitutionalHashMismatchError

            raise ConstitutionalHashMismatchError(
                expected_hash=CONSTITUTIONAL_HASH,
                actual_hash=constitutional_hash,
                context="ScenarioExecutor",
            )

        self.constitutional_hash = constitutional_hash
        self._active_scenarios: dict[str, BaseScenario] = {}
        self._results: list[ScenarioResult] = []
        self._lock = threading.Lock()

    async def execute(self, scenario: BaseScenario) -> ScenarioResult:
        """Execute a chaos scenario with safety controls."""
        with self._lock:
            if scenario.name in self._active_scenarios:
                raise ValueError(f"Scenario '{scenario.name}' is already running")
            self._active_scenarios[scenario.name] = scenario

        try:
            logger.info(f"[{self.constitutional_hash}] Executing scenario: {scenario.name}")
            result = await scenario.execute()
            self._results.append(result)
            return result

        finally:
            with self._lock:
                self._active_scenarios.pop(scenario.name, None)

    async def rollback_all(self) -> None:
        """Rollback all active scenarios."""
        with self._lock:
            scenarios = list(self._active_scenarios.values())

        for scenario in scenarios:
            try:
                await scenario.rollback()
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(
                    f"[{self.constitutional_hash}] Rollback failed for "
                    f"'{scenario.name}' ({type(e).__name__}): {e}"
                )

    def cancel_all(self) -> None:
        """Cancel all active scenarios."""
        with self._lock:
            for scenario in self._active_scenarios.values():
                scenario.cancel()

    def get_active_scenarios(self) -> list[BaseScenario]:
        """Get list of active scenarios."""
        with self._lock:
            return list(self._active_scenarios.values())

    def get_results(self) -> list[ScenarioResult]:
        """Get all scenario results."""
        return self._results.copy()


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "MAX_CPU_PERCENT",
    "MAX_DURATION_S",
    "MAX_LATENCY_MS",
    "MAX_MEMORY_PERCENT",
    # Base class
    "BaseScenario",
    "CPUStressScenario",
    "DependencyFailureScenario",
    "DependencyType",
    "LatencyInjectionScenario",
    "MemoryPressureScenario",
    # Scenario implementations
    "NetworkPartitionScenario",
    "PartitionType",
    # Executor
    "ScenarioExecutor",
    # Data classes
    "ScenarioResult",
    # Enums
    "ScenarioStatus",
]
