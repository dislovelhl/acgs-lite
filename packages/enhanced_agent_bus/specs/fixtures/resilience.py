"""
ACGS-2 Resilience Fixtures
Constitutional Hash: 608508a9bd224290

Fixtures for circuit breakers, chaos testing, and saga patterns.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import pytest

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class CircuitState(Enum):
    """Circuit breaker states per spec."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerEvent:
    """Recorded circuit breaker event."""

    timestamp: datetime
    event_type: str  # success, failure, state_change, timer_expires
    old_state: CircuitState | None
    new_state: CircuitState
    failure_count: int
    message: str = ""


class SpecCircuitBreaker:
    """
    Circuit breaker for executable specification testing.

    Implements the state machine defined in the executable specs:
    - CLOSED → OPEN on failure threshold
    - OPEN → HALF_OPEN on timer expiry
    - HALF_OPEN → CLOSED on success
    - HALF_OPEN → OPEN on failure
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self.failure_count = 0
        self._half_open_successes = 0
        self._last_failure_time: datetime | None = None
        self.events: list[CircuitBreakerEvent] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH

    @property
    def state(self) -> CircuitState:
        """Current circuit state, with automatic HALF_OPEN transition."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = (datetime.now(UTC) - self._last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout_s:
                    self._transition_to(CircuitState.HALF_OPEN, "timer_expires")
        return self._state

    def set_state(self, state: str) -> None:
        """Set state directly for testing (spec requirement)."""
        self._state = CircuitState(state)

    def _transition_to(self, new_state: CircuitState, event_type: str) -> None:
        """Record state transition."""
        event = CircuitBreakerEvent(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            old_state=self._state,
            new_state=new_state,
            failure_count=self.failure_count,
            message=f"Transition: {self._state.value} → {new_state.value}",
        )
        self.events.append(event)
        self._state = new_state

    def record_success(self) -> None:
        """Record successful operation."""
        event = CircuitBreakerEvent(
            timestamp=datetime.now(UTC),
            event_type="success",
            old_state=self._state,
            new_state=self._state,
            failure_count=self.failure_count,
        )

        if self._state == CircuitState.CLOSED:
            if self.failure_count > 0:
                self.failure_count -= 1
        elif self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.half_open_max_calls:
                self._transition_to(CircuitState.CLOSED, "success")
                self.failure_count = 0
                self._half_open_successes = 0

        self.events.append(event)

    def record_failure(self) -> None:
        """Record failed operation."""
        event = CircuitBreakerEvent(
            timestamp=datetime.now(UTC),
            event_type="failure",
            old_state=self._state,
            new_state=self._state,
            failure_count=self.failure_count,
        )

        if self._state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN, "failure")
                self._last_failure_time = datetime.now(UTC)
        elif self._state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN, "failure")
            self._last_failure_time = datetime.now(UTC)
            self._half_open_successes = 0

        self.events.append(event)

    def trigger_timer_expiry(self) -> None:
        """Simulate timer expiry for testing."""
        if self._state == CircuitState.OPEN:
            self._transition_to(CircuitState.HALF_OPEN, "timer_expires")

    def reset(self) -> None:
        """Reset to initial state."""
        self._state = CircuitState.CLOSED
        self.failure_count = 0
        self._half_open_successes = 0
        self._last_failure_time = None
        self.events.clear()


class FailureType(Enum):
    """Types of failures for chaos testing."""

    TIMEOUT = "timeout"
    ERROR = "error"
    LATENCY = "latency"
    CRASH = "crash"


@dataclass
class ChaosInjection:
    """Record of chaos injection."""

    component: str
    failure_type: FailureType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_s: float | None = None
    recovered: bool = False


class SpecChaosController:
    """
    Chaos controller for specification testing.

    Allows controlled injection of failures to test graceful degradation.
    """

    def __init__(self):
        self.active_failures: dict[str, ChaosInjection] = {}
        self.injection_history: list[ChaosInjection] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def fail(
        self,
        component: str,
        failure_type: FailureType = FailureType.ERROR,
        duration_s: float | None = None,
    ) -> ChaosInjection:
        """
        Inject a failure into a component.

        Args:
            component: Name of component to fail
            failure_type: Type of failure to inject
            duration_s: Optional duration for automatic recovery

        Returns:
            ChaosInjection record
        """
        injection = ChaosInjection(
            component=component,
            failure_type=failure_type,
            duration_s=duration_s,
        )
        self.active_failures[component] = injection
        self.injection_history.append(injection)
        return injection

    async def recover(self, component: str) -> ChaosInjection | None:
        """
        Recover a failed component.

        Args:
            component: Name of component to recover

        Returns:
            ChaosInjection record if component was failed, None otherwise
        """
        if component in self.active_failures:
            injection = self.active_failures.pop(component)
            injection.recovered = True
            return injection
        return None

    def is_failed(self, component: str) -> bool:
        """Check if a component is currently failed."""
        return component in self.active_failures

    def get_failure(self, component: str) -> ChaosInjection | None:
        """Get the current failure for a component."""
        return self.active_failures.get(component)

    async def reset(self) -> None:
        """Recover all failed components."""
        for component in list(self.active_failures.keys()):
            await self.recover(component)


@dataclass
class SagaStep:
    """A step in a saga transaction."""

    name: str
    executed: bool = False
    compensated: bool = False
    compensation: Callable[[], Awaitable[None]] | None = None


class SpecSagaManager:
    """
    Saga manager for specification testing.

    Implements LIFO compensation order as specified in executable specs.
    """

    def __init__(self):
        self.steps: list[SagaStep] = []
        self.compensation_log: list[str] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH
        self._in_transaction = False

    class Transaction:
        """Context manager for saga transaction."""

        def __init__(self, manager: "SpecSagaManager"):
            self.manager = manager

        async def __aenter__(self):
            self.manager._in_transaction = True
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.manager._in_transaction = False
            return False

        async def execute_step(self, name: str) -> None:
            """Execute a saga step."""
            step = SagaStep(name=name, executed=True)
            self.manager.steps.append(step)

        def on_compensate(self, name: str, callback: Callable[[], object]) -> None:
            """Register compensation callback for a step."""
            for step in reversed(self.manager.steps):
                if step.name == name:
                    step.compensation = callback
                    break

        async def compensate(self) -> list[str]:
            """Execute compensations in LIFO order."""
            compensation_order = []
            for step in reversed(self.manager.steps):
                if step.executed and not step.compensated:
                    if step.compensation:
                        result = step.compensation()
                        if asyncio.iscoroutine(result):
                            await result
                    step.compensated = True
                    compensation_order.append(step.name)
                    self.manager.compensation_log.append(step.name)
            return compensation_order

    def transaction(self) -> Transaction:
        """Start a saga transaction."""
        return self.Transaction(self)

    def reset(self) -> None:
        """Reset saga state."""
        self.steps.clear()
        self.compensation_log.clear()
        self._in_transaction = False


@pytest.fixture
def circuit_breaker() -> SpecCircuitBreaker:
    """
    Fixture providing a circuit breaker for spec testing.

    Use in tests verifying circuit breaker behavior:
        def test_circuit_opens(circuit_breaker):
            for _ in range(3):
                circuit_breaker.record_failure()
            assert circuit_breaker.state == CircuitState.OPEN
    """
    return SpecCircuitBreaker()


@pytest.fixture
def chaos_controller() -> SpecChaosController:
    """
    Fixture providing a chaos controller for spec testing.

    Use in tests verifying graceful degradation:
        async def test_degradation(chaos_controller):
            await chaos_controller.fail("z3_solver")
            # ... test fallback behavior
    """
    return SpecChaosController()


@pytest.fixture
def saga_manager() -> SpecSagaManager:
    """
    Fixture providing a saga manager for spec testing.

    Use in tests verifying LIFO compensation:
        async def test_compensation(saga_manager):
            async with saga_manager.transaction() as saga:
                await saga.execute_step("A")
                await saga.execute_step("B")
                order = await saga.compensate()
            assert order == ["B", "A"]
    """
    return SpecSagaManager()


def trigger_event(breaker: SpecCircuitBreaker, event: str) -> None:
    """Helper function to trigger circuit breaker events."""
    if event == "success":
        breaker.record_success()
    elif event == "failure":
        breaker.record_failure()
    elif event == "timer_expires":
        breaker.trigger_timer_expiry()
