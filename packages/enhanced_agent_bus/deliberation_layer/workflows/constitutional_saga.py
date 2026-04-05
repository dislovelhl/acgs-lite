"""
ACGS-2 Constitutional Saga Workflow
Constitutional Hash: 608508a9bd224290

Implements the Saga pattern for distributed transactions with compensation.
Used for constitutional operations that require all-or-nothing semantics.

Saga Pattern:
    For each step:
        1. Register compensation BEFORE executing
        2. Execute the step (via activity)
        3. On failure, run all compensations in reverse order (LIFO)

Example: Multi-Service Constitutional Validation
    1. Reserve validation capacity (compensation: release capacity)
    2. Validate constitutional hash (compensation: log validation failure)
    3. Evaluate OPA policies (compensation: revert policy state)
    4. Record to audit trail (compensation: mark audit as failed)
    5. Deliver to target (compensation: recall message)

Reference: https://temporal.io/blog/saga-pattern-made-easy
"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import (
    Generic,
    TypeAlias,
    TypeVar,
)

import aiofiles

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.interfaces import ConstitutionalHashValidatorProtocol
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")

_CONSTITUTIONAL_SAGA_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class SagaStatus(Enum):
    """Status of the saga execution."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"
    PARTIALLY_COMPENSATED = "partially_compensated"


class StepStatus(Enum):
    """Status of individual saga step."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"


@dataclass
class SagaCompensation:
    """
    Represents a compensation action for a saga step.

    Compensations are idempotent operations that undo the effects of a step.
    They must be safe to call multiple times.

    Attributes:
        name: Unique name for the compensation
        execute: Async function that performs the compensation
        description: Human-readable description
        idempotency_key: Key for deduplication
    """

    name: str
    execute: Callable[[JSONDict], Awaitable[bool]]
    description: str = ""
    idempotency_key: str | None = None
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


@dataclass
class SagaStep(Generic[T]):
    """
    Represents a single step in a saga.

    Each step has:
    - An execution function (activity)
    - A compensation function (for rollback)
    - Configuration for retries and timeouts

    IMPORTANT: Register compensation BEFORE executing the step.

    Attributes:
        name: Unique step name
        execute: Async function that performs the step
        compensation: Compensation to run if this or later steps fail
        description: Human-readable description
    """

    name: str
    execute: Callable[[JSONDict], Awaitable[T]]
    compensation: SagaCompensation | None = None
    description: str = ""
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    is_optional: bool = False
    requires_previous: bool = True

    # Runtime state
    status: StepStatus = StepStatus.PENDING
    result: T | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_time_ms: float = 0.0


@dataclass
class SagaContext:
    """
    Context passed through saga execution.

    Accumulates results from each step and provides shared state.
    """

    saga_id: str
    constitutional_hash: str = CONSTITUTIONAL_HASH
    tenant_id: str | None = None
    correlation_id: str | None = None
    step_results: JSONDict = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    errors: list[str] = field(default_factory=list)

    def get_step_result(self, step_name: str) -> object | None:
        """Get result from a previous step."""
        return self.step_results.get(step_name)  # type: ignore[no-any-return]

    def set_step_result(self, step_name: str, result: object):
        """Store result from a step."""
        self.step_results[step_name] = result


@dataclass
class SagaResult:
    """Result of saga execution."""

    saga_id: str
    status: SagaStatus
    completed_steps: list[str]
    failed_step: str | None
    compensated_steps: list[str]
    failed_compensations: list[str]
    total_execution_time_ms: float
    context: SagaContext
    version: str = "1.0.0"
    constitutional_hash: str = CONSTITUTIONAL_HASH
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "saga_id": self.saga_id,
            "status": self.status.value,
            "completed_steps": self.completed_steps,
            "failed_step": self.failed_step,
            "compensated_steps": self.compensated_steps,
            "failed_compensations": self.failed_compensations,
            "total_execution_time_ms": self.total_execution_time_ms,
            "version": self.version,
            "constitutional_hash": self.constitutional_hash,
            "errors": self.errors,
            "step_results": self.context.step_results,
        }


@dataclass
class SagaState:
    """Serializable state of a saga for persistence."""

    saga_id: str
    status: SagaStatus
    completed_steps: list[str]
    failed_step: str | None
    compensated_steps: list[str]
    failed_compensations: list[str]
    context: JSONDict
    version: str = "1.0.0"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        data["status"] = self.status.value
        data["updated_at"] = self.updated_at.isoformat()
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "SagaState":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        data["status"] = SagaStatus(data["status"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


class FileSagaPersistenceProvider:
    """File-based persistence provider for saga state."""

    def __init__(self, base_path: str | Path = "storage/workflow_states"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_path(self, saga_id: str) -> Path:
        return self.base_path / f"{saga_id}.json"

    async def save_state(self, state: SagaState) -> None:
        path = self._get_path(state.saga_id)
        async with aiofiles.open(path, "w") as f:
            await f.write(state.to_json())

    async def load_state(self, saga_id: str) -> SagaState | None:
        path = self._get_path(saga_id)
        if not path.exists():
            return None
        async with aiofiles.open(path) as f:
            return SagaState.from_json(await f.read())

    async def delete_state(self, saga_id: str) -> None:
        path = self._get_path(saga_id)
        if path.exists():
            path.unlink()


class DefaultSagaActivities:
    """Default implementation of saga activities."""

    def __init__(
        self,
        hash_validator: ConstitutionalHashValidatorProtocol | None = None,
    ) -> None:
        if hash_validator is None:
            validators_module = import_module("enhanced_agent_bus.validators")
            hash_validator = validators_module.ConstitutionalHashValidator()
        self._hash_validator = hash_validator

    async def reserve_capacity(self, saga_id: str, resource_type: str, amount: int) -> JSONDict:
        reservation_id = str(uuid.uuid4())
        logger.info(
            f"Saga {saga_id}: Reserved {amount} {resource_type} (reservation: {reservation_id})"
        )
        return {
            "reservation_id": reservation_id,
            "resource_type": resource_type,
            "amount": amount,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def release_capacity(self, saga_id: str, reservation_id: str) -> bool:
        logger.info(f"Saga {saga_id}: Released reservation {reservation_id}")
        return True

    async def validate_constitutional_compliance(
        self, saga_id: str, data: JSONDict, constitutional_hash: str
    ) -> JSONDict:
        provided_hash = data.get("constitutional_hash")
        provided_hash_value = provided_hash if isinstance(provided_hash, str) else ""
        is_valid, error_message = await self._hash_validator.validate_hash(
            provided_hash=provided_hash_value,
            expected_hash=constitutional_hash,
            context={"saga_id": saga_id},
        )
        validation_id = str(uuid.uuid4())
        return {
            "validation_id": validation_id,
            "is_valid": is_valid,
            "errors": [] if is_valid else [error_message],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def log_validation_failure(self, saga_id: str, validation_id: str, reason: str) -> bool:
        logger.warning(f"Saga {saga_id}: Validation {validation_id} failed - {reason}")
        return True

    async def apply_policy_decision(
        self, saga_id: str, policy_path: str, decision_data: JSONDict
    ) -> JSONDict:
        decision_id = str(uuid.uuid4())
        logger.info(f"Saga {saga_id}: Applied policy {policy_path} (decision: {decision_id})")
        return {
            "decision_id": decision_id,
            "policy_path": policy_path,
            "applied": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def revert_policy_decision(self, saga_id: str, decision_id: str) -> bool:
        logger.info(f"Saga {saga_id}: Reverted policy decision {decision_id}")
        return True

    async def record_audit_entry(self, saga_id: str, entry_type: str, entry_data: JSONDict) -> str:
        audit_id = str(uuid.uuid4())
        logger.info(f"Saga {saga_id}: Recorded audit entry {audit_id} ({entry_type})")
        return audit_id

    async def mark_audit_failed(self, saga_id: str, audit_id: str, reason: str) -> bool:
        logger.warning(f"Saga {saga_id}: Marked audit {audit_id} as failed - {reason}")
        return True

    async def deliver_to_target(self, saga_id: str, target_id: str, payload: JSONDict) -> JSONDict:
        delivery_id = str(uuid.uuid4())
        logger.info(f"Saga {saga_id}: Delivered to {target_id} (delivery: {delivery_id})")
        return {
            "delivery_id": delivery_id,
            "target_id": target_id,
            "delivered": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def recall_from_target(self, saga_id: str, delivery_id: str, target_id: str) -> bool:
        logger.warning(f"Saga {saga_id}: Recalled delivery {delivery_id} from {target_id}")
        return True

    async def audit_llm_reasoning(
        self, saga_id: str, reasoning: str, constitutional_hash: str
    ) -> JSONDict:
        audit_id = str(uuid.uuid4())
        # Simulated reasoning audit
        is_safe = "ignore previous instructions" not in reasoning.lower()
        logger.info(f"Saga {saga_id}: Audited reasoning trace {audit_id} (Safe: {is_safe})")
        return {
            "audit_id": audit_id,
            "is_safe": is_safe,
            "timestamp": datetime.now(UTC).isoformat(),
        }


class ConstitutionalSagaWorkflow:
    """
    Saga workflow for constitutional operations with compensation.

    This workflow executes a series of steps with automatic compensation
    on failure. It follows the saga pattern:

    1. For each step:
       a. Register compensation BEFORE execution
       b. Execute the step
       c. Store result in context

    2. On failure at any step:
       a. Stop forward execution
       b. Execute compensations in REVERSE order (LIFO)
       c. Report partial completion

    Example Usage:
        saga = ConstitutionalSagaWorkflow("saga-123")

        # Define steps with compensations
        saga.add_step(SagaStep(
            name="reserve_capacity",
            execute=activities.reserve_capacity,
            compensation=SagaCompensation(
                name="release_capacity",
                execute=activities.release_capacity
            )
        ))

        # Execute saga
        result = await saga.execute(context)
    """

    def __init__(
        self,
        saga_id: str,
        activities: DefaultSagaActivities | None = None,
        persistence_provider: FileSagaPersistenceProvider | None = None,
        version: str = "1.0.0",
    ):
        self.saga_id = saga_id
        self.activities = activities or DefaultSagaActivities()
        self.persistence_provider = persistence_provider
        self.version = version

        self._steps: list[SagaStep] = []
        self._compensations: list[SagaCompensation] = []
        self._status = SagaStatus.PENDING
        self._completed_steps: list[str] = []
        self._failed_step: str | None = None
        self._compensated_steps: list[str] = []
        self._failed_compensations: list[str] = []
        self._start_time: datetime | None = None

    def add_step(self, step: SagaStep) -> "ConstitutionalSagaWorkflow":
        """Add a step to the saga. Returns self for chaining."""
        self._steps.append(step)
        return self

    async def _save_current_state(self, context: SagaContext):
        """Save the current saga state if a persistence provider is configured."""
        if self.persistence_provider:
            state = SagaState(
                saga_id=self.saga_id,
                status=self._status,
                completed_steps=self._completed_steps.copy(),
                failed_step=self._failed_step,
                compensated_steps=self._compensated_steps.copy(),
                failed_compensations=self._failed_compensations.copy(),
                context=context.step_results.copy(),
                version=self.version,
            )
            await self.persistence_provider.save_state(state)

    async def execute(self, context: SagaContext | None = None) -> SagaResult:
        """
        Execute the saga with automatic compensation on failure.

        Returns SagaResult with execution details.
        """
        self._start_time = datetime.now(UTC)
        self._status = SagaStatus.EXECUTING

        if context is None:
            context = SagaContext(saga_id=self.saga_id)

        # Save initial state
        await self._save_current_state(context)

        try:
            # Execute steps in order
            for step in self._steps:
                success = await self._execute_step(step, context)

                if not success and not step.is_optional:
                    self._failed_step = step.name
                    break

            if self._failed_step:
                # Failure occurred - run compensations
                await self._run_compensations(context)
                self._status = (
                    SagaStatus.COMPENSATED
                    if not self._failed_compensations
                    else SagaStatus.PARTIALLY_COMPENSATED
                )
            else:
                self._status = SagaStatus.COMPLETED

            # Final state save
            await self._save_current_state(context)

        except _CONSTITUTIONAL_SAGA_OPERATION_ERRORS as e:
            logger.error(f"Saga {self.saga_id} failed with exception: {e}")
            context.errors.append(str(e))
            self._status = SagaStatus.FAILED

            # Attempt compensations even on exception
            await self._run_compensations(context)

        return self._build_result(context)

    async def _execute_step(self, step: SagaStep, context: SagaContext) -> bool:
        """Execute a single saga step with retries."""
        step.status = StepStatus.EXECUTING
        step.started_at = datetime.now(UTC)

        # CRITICAL: Register compensation BEFORE executing
        if step.compensation:
            self._compensations.append(step.compensation)

        for attempt in range(step.max_retries):
            try:
                # Build step input from context
                step_input = {
                    "saga_id": self.saga_id,
                    "step_name": step.name,
                    "attempt": attempt + 1,
                    "context": context.step_results.copy(),
                    "metadata": context.metadata.copy(),
                    "constitutional_hash": context.constitutional_hash,
                }

                # Execute with timeout
                result = await asyncio.wait_for(
                    step.execute(step_input), timeout=step.timeout_seconds
                )

                step.result = result
                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.now(UTC)
                step.execution_time_ms = (
                    step.completed_at - step.started_at
                ).total_seconds() * 1000

                # Store result in context
                context.set_step_result(step.name, result)
                self._completed_steps.append(step.name)

                # Save state after each step
                await self._save_current_state(context)

                logger.info(
                    f"Saga {self.saga_id}: Step '{step.name}' completed "
                    f"(attempt {attempt + 1}, {step.execution_time_ms:.2f}ms)"
                )

                return True

            except TimeoutError:
                step.error = f"Timeout after {step.timeout_seconds}s"
                logger.warning(
                    f"Saga {self.saga_id}: Step '{step.name}' timed out (attempt {attempt + 1})"
                )

            except _CONSTITUTIONAL_SAGA_OPERATION_ERRORS as e:
                step.error = str(e)
                logger.warning(
                    f"Saga {self.saga_id}: Step '{step.name}' failed (attempt {attempt + 1}): {e}"
                )

            # Wait before retry
            if attempt < step.max_retries - 1:
                await asyncio.sleep(step.retry_delay_seconds)

        # All retries exhausted
        step.status = StepStatus.FAILED
        context.errors.append(f"Step '{step.name}' failed: {step.error}")
        return False

    async def _run_compensations(self, context: SagaContext):
        """Run compensations in reverse order (LIFO)."""
        self._status = SagaStatus.COMPENSATING

        # Reverse order - most recent first
        for compensation in reversed(self._compensations):
            success = await self._execute_compensation(compensation, context)

            if success:
                self._compensated_steps.append(compensation.name)
            else:
                self._failed_compensations.append(compensation.name)

            # Save state after each compensation
            await self._save_current_state(context)

    async def _execute_compensation(
        self, compensation: SagaCompensation, context: SagaContext
    ) -> bool:
        """Execute a single compensation with retries."""
        logger.info(f"Saga {self.saga_id}: Running compensation '{compensation.name}'")

        for attempt in range(compensation.max_retries):
            try:
                # Build compensation input
                comp_input = {
                    "saga_id": self.saga_id,
                    "compensation_name": compensation.name,
                    "attempt": attempt + 1,
                    "context": context.step_results.copy(),
                    "idempotency_key": compensation.idempotency_key
                    or f"{self.saga_id}:{compensation.name}",
                }

                result = await compensation.execute(comp_input)

                if result:
                    logger.info(
                        f"Saga {self.saga_id}: Compensation '{compensation.name}' "
                        f"completed (attempt {attempt + 1})"
                    )
                    return True

            except _CONSTITUTIONAL_SAGA_OPERATION_ERRORS as e:
                logger.warning(
                    f"Saga {self.saga_id}: Compensation '{compensation.name}' "
                    f"failed (attempt {attempt + 1}): {e}"
                )

            if attempt < compensation.max_retries - 1:
                await asyncio.sleep(compensation.retry_delay_seconds)

        logger.error(
            f"Saga {self.saga_id}: Compensation '{compensation.name}' "
            f"failed after {compensation.max_retries} attempts"
        )
        context.errors.append(f"Compensation '{compensation.name}' failed")
        return False

    def _build_result(self, context: SagaContext) -> SagaResult:
        """Build saga result from current state."""
        execution_time = 0.0
        if self._start_time:
            execution_time = (datetime.now(UTC) - self._start_time).total_seconds() * 1000

        return SagaResult(
            saga_id=self.saga_id,
            status=self._status,
            completed_steps=self._completed_steps.copy(),
            failed_step=self._failed_step,
            compensated_steps=self._compensated_steps.copy(),
            failed_compensations=self._failed_compensations.copy(),
            total_execution_time_ms=execution_time,
            context=context,
            version=self.version,
            constitutional_hash=context.constitutional_hash,
            errors=context.errors.copy(),
        )

    @staticmethod
    async def resume(
        saga_id: str,
        persistence_provider: FileSagaPersistenceProvider,
        activities: DefaultSagaActivities | None = None,
    ) -> "ConstitutionalSagaWorkflow" | None:
        """
        Resume a saga from persistent storage.

        This recreates the workflow instance and populates its state.
        Caller must re-add all steps to the workflow before calling execute().
        """
        state = await persistence_provider.load_state(saga_id)
        if not state:
            return None

        saga = ConstitutionalSagaWorkflow(
            saga_id=saga_id,
            activities=activities,
            persistence_provider=persistence_provider,
            version=state.version,
        )

        saga._status = state.status
        saga._completed_steps = state.completed_steps.copy()
        saga._failed_step = state.failed_step
        saga._compensated_steps = state.compensated_steps.copy()
        saga._failed_compensations = state.failed_compensations.copy()

        return saga

    def get_status(self) -> SagaStatus:
        """Query current saga status."""
        return self._status


def create_constitutional_validation_saga(
    saga_id: str, activities: DefaultSagaActivities | None = None
) -> ConstitutionalSagaWorkflow:
    """
    Factory function to create a standard constitutional validation saga.

    Steps:
    1. Reserve validation capacity
    2. Validate constitutional hash
    3. Evaluate OPA policies
    4. Record audit trail
    5. Deliver to target

    Each step has corresponding compensation.
    """
    acts = activities or DefaultSagaActivities()
    saga = ConstitutionalSagaWorkflow(saga_id, acts)

    # Add all steps to the saga
    _add_capacity_reservation_step(saga, acts)
    _add_compliance_validation_step(saga, acts)
    _add_reasoning_audit_step(saga, acts)
    _add_policy_application_step(saga, acts)
    _add_audit_recording_step(saga, acts)

    return saga


def _add_capacity_reservation_step(saga: ConstitutionalSagaWorkflow, acts: DefaultSagaActivities):
    """Add capacity reservation step to saga."""

    async def reserve_capacity(input: JSONDict) -> JSONDict:
        return await acts.reserve_capacity(
            saga_id=input["saga_id"], resource_type="validation_slots", amount=1
        )

    async def release_capacity(input: JSONDict) -> bool:
        reservation = input["context"].get("reserve_capacity", {})
        return await acts.release_capacity(
            saga_id=input["saga_id"], reservation_id=reservation.get("reservation_id", "unknown")
        )

    saga.add_step(
        SagaStep(
            name="reserve_capacity",
            description="Reserve validation capacity",
            execute=reserve_capacity,
            compensation=SagaCompensation(
                name="release_capacity",
                description="Release reserved capacity",
                execute=release_capacity,
            ),
        )
    )


def _add_compliance_validation_step(saga: ConstitutionalSagaWorkflow, acts: DefaultSagaActivities):
    """Add constitutional compliance validation step to saga."""

    async def validate_compliance(input: JSONDict) -> JSONDict:
        return await acts.validate_constitutional_compliance(
            saga_id=input["saga_id"],
            data=input["context"],
            constitutional_hash=input["constitutional_hash"],
        )

    async def log_validation_failure(input: JSONDict) -> bool:
        validation = input["context"].get("validate_compliance", {})
        return await acts.log_validation_failure(
            saga_id=input["saga_id"],
            validation_id=validation.get("validation_id", "unknown"),
            reason="Saga compensated",
        )

    saga.add_step(
        SagaStep(
            name="validate_compliance",
            description="Validate constitutional compliance",
            execute=validate_compliance,
            compensation=SagaCompensation(
                name="log_validation_failure",
                description="Log validation as failed",
                execute=log_validation_failure,
            ),
        )
    )


def _add_reasoning_audit_step(saga: ConstitutionalSagaWorkflow, acts: DefaultSagaActivities):
    """Add LLM reasoning audit step to saga."""

    async def audit_reasoning(input: JSONDict) -> JSONDict:
        reasoning = input["context"].get("llm_reasoning", "")
        if not reasoning:
            return {"audit_id": "none", "is_safe": True, "skipped": True}

        return await acts.audit_llm_reasoning(
            saga_id=input["saga_id"],
            reasoning=reasoning,
            constitutional_hash=input["constitutional_hash"],
        )

    saga.add_step(
        SagaStep(
            name="audit_reasoning",
            description="Audit LLM thinking traces",
            execute=audit_reasoning,
            is_optional=True,
        )
    )


def _add_policy_application_step(saga: ConstitutionalSagaWorkflow, acts: DefaultSagaActivities):
    """Add policy application step to saga."""

    async def apply_policy(input: JSONDict) -> JSONDict:
        return await acts.apply_policy_decision(
            saga_id=input["saga_id"],
            policy_path="acgs/constitutional/allow",
            decision_data=input["context"],
        )

    async def revert_policy(input: JSONDict) -> bool:
        decision = input["context"].get("apply_policy", {})
        return await acts.revert_policy_decision(
            saga_id=input["saga_id"], decision_id=decision.get("decision_id", "unknown")
        )

    saga.add_step(
        SagaStep(
            name="apply_policy",
            description="Apply policy decision",
            execute=apply_policy,
            compensation=SagaCompensation(
                name="revert_policy", description="Revert policy decision", execute=revert_policy
            ),
        )
    )


def _add_audit_recording_step(saga: ConstitutionalSagaWorkflow, acts: DefaultSagaActivities):
    """Add audit recording step to saga."""

    async def record_audit(input: JSONDict) -> str:
        return await acts.record_audit_entry(
            saga_id=input["saga_id"],
            entry_type="constitutional_validation",
            entry_data=input["context"],
        )

    async def mark_audit_failed(input: JSONDict) -> bool:
        audit_id = input["context"].get("record_audit", "unknown")
        return await acts.mark_audit_failed(
            saga_id=input["saga_id"], audit_id=audit_id, reason="Saga compensated"
        )

    saga.add_step(
        SagaStep(
            name="record_audit",
            description="Record to audit trail",
            execute=record_audit,
            compensation=SagaCompensation(
                name="mark_audit_failed",
                description="Mark audit as failed",
                execute=mark_audit_failed,
            ),
        )
    )
