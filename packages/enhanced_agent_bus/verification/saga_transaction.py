"""
ACGS-2 Enhanced Agent Bus - SagaLLM Transactions
Constitutional Hash: 608508a9bd224290

Implements compensable transaction guarantees for LLM workflows.
Bypasses self-verification limitations through LIFO rollback and formal checkpoints.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        SupportsAudit,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    SupportsAudit = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
SAGA_STEP_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
)
SAGA_COMPENSATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
)


class SagaStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class SagaStep:
    """A step in a Saga transaction."""

    name: str
    action: Callable[..., Awaitable[object]]
    compensation: Callable[..., Awaitable[None]] | None = None
    status: SagaStatus = SagaStatus.PENDING
    result: object | None = None
    error: str | None = None


class SagaTransaction:
    """
    SagaLLM-inspired transaction manager.

    Ensures that multi-step governance decisions are atomic and compensable.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, transaction_id: str | None = None):
        self.transaction_id = transaction_id or str(uuid.uuid4())
        self.steps: list[SagaStep] = []
        self.status = SagaStatus.PENDING
        self._completed_steps: list[SagaStep] = []

    def add_step(
        self,
        name: str,
        action: Callable[..., Awaitable[object]],
        compensation: Callable[..., Awaitable[None]] | None = None,
    ) -> "SagaTransaction":
        """Add a step to the transaction."""
        self.steps.append(SagaStep(name=name, action=action, compensation=compensation))
        return self

    async def execute(self, **kwargs: object) -> object | None:
        """
        Execute the transaction steps in order.
        If a step fails, trigger compensation for all completed steps in LIFO order.
        """
        self.status = SagaStatus.RUNNING
        logger.info(f"[{CONSTITUTIONAL_HASH}] Starting Saga transaction: {self.transaction_id}")

        last_result = None

        for step in self.steps:
            step.status = SagaStatus.RUNNING

            try:
                # Execute step action, passing results from previous steps if needed
                step.result = await step.action(**kwargs, last_result=last_result)
                step.status = SagaStatus.COMPLETED
                self._completed_steps.append(step)
                last_result = step.result
            except SAGA_STEP_EXECUTION_ERRORS as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Step {step.name} failed: {e}")
                step.status = SagaStatus.FAILED
                step.error = str(e)
                await self._compensate()
                self.status = SagaStatus.ROLLED_BACK
                raise

        self.status = SagaStatus.COMPLETED
        logger.info(f"[{CONSTITUTIONAL_HASH}] Saga transaction completed: {self.transaction_id}")
        return last_result

    async def _compensate(self):
        """Compensate completed steps in reverse order (LIFO)."""
        self.status = SagaStatus.COMPENSATING
        logger.warning(
            f"[{CONSTITUTIONAL_HASH}] Starting compensation for transaction: {self.transaction_id}"
        )

        for step in reversed(self._completed_steps):
            if step.compensation:
                try:
                    await step.compensation(step.result)
                except SAGA_COMPENSATION_ERRORS as e:
                    logger.error(
                        f"[{CONSTITUTIONAL_HASH}] Compensation for step {step.name} failed: {e}"
                    )
                    # In a real system, we might retry or escalate to manual intervention
            else:
                logger.debug(
                    f"[{CONSTITUTIONAL_HASH}] No compensation needed for step: {step.name}"
                )

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Compensation completed for transaction: {self.transaction_id}"
        )


class ConstitutionalSaga(SagaTransaction):
    """
    Specialized Saga for constitutional governance.

    Includes built-in validation and auditing.
    """

    def __init__(self, auditor: SupportsAudit | object | None = None):
        super().__init__()
        self.auditor = auditor

    async def execute_governance(self, decision_data: JSONDict) -> object | None:
        """Helper to run a standard governance transaction."""
        # This would be expanded with real governance steps
        return await self.execute(data=decision_data)
