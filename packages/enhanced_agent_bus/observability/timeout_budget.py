"""
ACGS-2 Timeout Budget Management
Constitutional Hash: 608508a9bd224290

Layer-specific timeout allocation and enforcement for constitutional
compliance within latency SLAs.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .structured_logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")


class LayerTimeoutError(ACGSBaseError):
    """Raised when a layer exceeds its timeout budget."""

    http_status_code = 504
    error_code = "LAYER_TIMEOUT"

    def __init__(
        self,
        layer_name: str,
        budget_ms: float,
        elapsed_ms: float,
        operation: str | None = None,
    ):
        self.layer_name = layer_name
        self.budget_ms = budget_ms
        self.elapsed_ms = elapsed_ms
        self.operation = operation

        message = (
            f"Layer '{layer_name}' exceeded timeout budget: {elapsed_ms:.2f}ms > {budget_ms:.2f}ms"
        )
        if operation:
            message += f" during '{operation}'"

        super().__init__(
            message,
            details={
                "layer_name": layer_name,
                "budget_ms": budget_ms,
                "elapsed_ms": elapsed_ms,
                "operation": operation,
            },
        )

    def to_dict(self) -> JSONDict:
        """Serialize for logging/telemetry."""
        base = super().to_dict()
        base.update(
            {
                "layer_name": self.layer_name,
                "budget_ms": self.budget_ms,
                "elapsed_ms": self.elapsed_ms,
                "operation": self.operation,
            }
        )
        return base


class Layer(Enum):
    """Architecture layers with timeout budgets."""

    LAYER1_VALIDATION = "layer1_validation"
    LAYER2_DELIBERATION = "layer2_deliberation"
    LAYER3_POLICY = "layer3_policy"
    LAYER4_AUDIT = "layer4_audit"


@dataclass
class LayerTimeoutBudget:
    """
    Timeout budget configuration for a single layer.

    Default budgets (total 50ms SLA):
    - Layer 1 (Validation): 5ms
    - Layer 2 (Deliberation): 20ms
    - Layer 3 (Policy): 10ms
    - Layer 4 (Audit): 15ms
    """

    layer: Layer
    budget_ms: float
    soft_limit_pct: float = 0.8  # Warn at 80% of budget
    strict_enforcement: bool = True

    # Runtime tracking
    elapsed_ms: float = field(default=0.0, init=False)
    start_time: float | None = field(default=None, init=False)

    @property
    def remaining_ms(self) -> float:
        """Remaining budget in milliseconds."""
        return max(0.0, self.budget_ms - self.elapsed_ms)

    @property
    def is_exceeded(self) -> bool:
        """Check if budget is exceeded."""
        return self.elapsed_ms > self.budget_ms

    @property
    def is_soft_limit_exceeded(self) -> bool:
        """Check if soft limit (warning threshold) is exceeded."""
        return self.elapsed_ms > (self.budget_ms * self.soft_limit_pct)

    def start(self) -> None:
        """Start timing this layer."""
        self.start_time = time.perf_counter()

    def stop(self) -> float:
        """Stop timing and return elapsed milliseconds."""
        if self.start_time is not None:
            self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000
            self.start_time = None
        return self.elapsed_ms

    def reset(self) -> None:
        """Reset timing state."""
        self.elapsed_ms = 0.0
        self.start_time = None


@dataclass
class TimeoutBudgetManager:
    """
    Manages timeout budgets across all architectural layers.

    Ensures total operation completes within P99 latency SLA (50ms default).
    """

    total_budget_ms: float = 50.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    # Layer budgets (default allocation)
    layer_budgets: dict[Layer, LayerTimeoutBudget] = field(default_factory=dict)

    # Runtime state
    _total_start: float | None = field(default=None, init=False)
    _total_elapsed: float = field(default=0.0, init=False)

    def __post_init__(self):
        """Initialize default layer budgets if not provided."""
        if not self.layer_budgets:
            self.layer_budgets = {
                Layer.LAYER1_VALIDATION: LayerTimeoutBudget(
                    layer=Layer.LAYER1_VALIDATION,
                    budget_ms=5.0,
                    strict_enforcement=True,
                ),
                Layer.LAYER2_DELIBERATION: LayerTimeoutBudget(
                    layer=Layer.LAYER2_DELIBERATION,
                    budget_ms=20.0,
                    strict_enforcement=True,
                ),
                Layer.LAYER3_POLICY: LayerTimeoutBudget(
                    layer=Layer.LAYER3_POLICY,
                    budget_ms=10.0,
                    strict_enforcement=True,
                ),
                Layer.LAYER4_AUDIT: LayerTimeoutBudget(
                    layer=Layer.LAYER4_AUDIT,
                    budget_ms=15.0,
                    strict_enforcement=False,  # Audit can be async
                ),
            }

    def start_total(self) -> None:
        """Start tracking total operation time."""
        self._total_start = time.perf_counter()
        self._total_elapsed = 0.0

    def stop_total(self) -> float:
        """Stop tracking and return total elapsed milliseconds."""
        if self._total_start is not None:
            self._total_elapsed = (time.perf_counter() - self._total_start) * 1000
            self._total_start = None
        return self._total_elapsed

    @property
    def total_elapsed_ms(self) -> float:
        """Current total elapsed time in milliseconds."""
        if self._total_start is not None:
            return (time.perf_counter() - self._total_start) * 1000
        return self._total_elapsed

    @property
    def total_remaining_ms(self) -> float:
        """Remaining total budget in milliseconds."""
        return max(0.0, self.total_budget_ms - self.total_elapsed_ms)

    def get_layer_budget(self, layer: Layer) -> LayerTimeoutBudget:
        """Get budget for a specific layer."""
        if layer not in self.layer_budgets:
            raise ValueError(f"Unknown layer: {layer}")
        return self.layer_budgets[layer]

    async def execute_with_budget(
        self,
        layer: Layer,
        operation: Callable[[], Awaitable[T]],
        operation_name: str | None = None,
    ) -> T:
        """
        Execute an async operation within layer timeout budget.

        Args:
            layer: The architectural layer
            operation: Async callable to execute
            operation_name: Optional name for logging/errors

        Returns:
            Result of the operation

        Raises:
            LayerTimeoutError: If operation exceeds layer budget
            asyncio.TimeoutError: If operation times out
        """
        budget = self.get_layer_budget(layer)
        timeout_s = budget.budget_ms / 1000.0

        budget.start()

        try:
            result = await asyncio.wait_for(operation(), timeout=timeout_s)
            elapsed = budget.stop()

            # Log soft limit warning
            if budget.is_soft_limit_exceeded:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Layer {layer.value} approaching "
                    f"timeout: {elapsed:.2f}ms / {budget.budget_ms:.2f}ms"
                )

            return result

        except TimeoutError as e:
            elapsed = budget.stop()
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Layer {layer.value} timeout: "
                f"{elapsed:.2f}ms > {budget.budget_ms:.2f}ms"
            )

            if budget.strict_enforcement:
                raise LayerTimeoutError(
                    layer_name=layer.value,
                    budget_ms=budget.budget_ms,
                    elapsed_ms=elapsed,
                    operation=operation_name,
                ) from e
            raise

        except (OSError, RuntimeError, ValueError, TypeError) as e:
            budget.stop()
            raise e

    def execute_sync_with_budget(
        self,
        layer: Layer,
        operation: Callable[[], T],
        operation_name: str | None = None,
    ) -> T:
        """
        Execute a sync operation with timeout budget tracking.

        Note: This does not enforce timeout (sync operations can't be
        interrupted), but tracks timing and raises after completion
        if budget exceeded.

        Args:
            layer: The architectural layer
            operation: Callable to execute
            operation_name: Optional name for logging/errors

        Returns:
            Result of the operation

        Raises:
            LayerTimeoutError: If operation exceeds layer budget (post-execution)
        """
        budget = self.get_layer_budget(layer)
        budget.start()

        try:
            result = operation()
            elapsed = budget.stop()

            if budget.is_exceeded:
                logger.error(
                    f"[{CONSTITUTIONAL_HASH}] Layer {layer.value} exceeded budget: "
                    f"{elapsed:.2f}ms > {budget.budget_ms:.2f}ms"
                )

                if budget.strict_enforcement:
                    raise LayerTimeoutError(
                        layer_name=layer.value,
                        budget_ms=budget.budget_ms,
                        elapsed_ms=elapsed,
                        operation=operation_name,
                    )

            elif budget.is_soft_limit_exceeded:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Layer {layer.value} approaching "
                    f"timeout: {elapsed:.2f}ms / {budget.budget_ms:.2f}ms"
                )

            return result

        except LayerTimeoutError:
            raise
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            budget.stop()
            raise e

    def get_budget_report(self) -> JSONDict:
        """Generate a report of all layer budgets and timing."""
        layers = {}
        for layer, budget in self.layer_budgets.items():
            layers[layer.value] = {
                "budget_ms": budget.budget_ms,
                "elapsed_ms": budget.elapsed_ms,
                "remaining_ms": budget.remaining_ms,
                "is_exceeded": budget.is_exceeded,
                "is_soft_limit_exceeded": budget.is_soft_limit_exceeded,
            }

        return {
            "total_budget_ms": self.total_budget_ms,
            "total_elapsed_ms": self.total_elapsed_ms,
            "total_remaining_ms": self.total_remaining_ms,
            "layers": layers,
            "constitutional_hash": self.constitutional_hash,
        }

    def reset_all(self) -> None:
        """Reset all timing state."""
        self._total_start = None
        self._total_elapsed = 0.0
        for budget in self.layer_budgets.values():
            budget.reset()
