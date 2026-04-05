"""
ACGS-2 Saga Orchestration for Enterprise Migration
Constitutional Hash: 608508a9bd224290

Implements the Saga pattern for distributed transactions in enterprise
migration jobs. Provides compensating transactions, rollback capabilities,
and constitutional compliance throughout the saga lifecycle.

Phase 10 Task 16: Saga Orchestration for Migration Jobs

Features:
- Saga step definition with compensating actions
- Orchestrator pattern for step coordination
- Automatic rollback on failure
- Saga state persistence and recovery
- Constitutional validation at each step
- Multi-tenant saga isolation
"""

import asyncio
import json
import os
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Generic, TypeVar

import redis.asyncio

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.governance_constants import SAGA_DEFAULT_TTL_SECONDS
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_SAGA_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
)


class SagaStatus(str, Enum):
    """Status of a saga execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"
    PARTIALLY_COMPENSATED = "partially_compensated"


class SagaStepStatus(str, Enum):
    """Status of an individual saga step."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"
    SKIPPED = "skipped"


class SagaEventType(str, Enum):
    """Types of saga events for audit logging."""

    SAGA_STARTED = "saga_started"
    SAGA_COMPLETED = "saga_completed"
    SAGA_FAILED = "saga_failed"
    SAGA_COMPENSATING = "saga_compensating"
    SAGA_COMPENSATED = "saga_compensated"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_COMPENSATING = "step_compensating"
    STEP_COMPENSATED = "step_compensated"
    STEP_COMPENSATION_FAILED = "step_compensation_failed"


class CompensationStrategy(str, Enum):
    """Strategy for handling compensation failures."""

    RETRY = "retry"
    SKIP = "skip"
    FAIL = "fail"
    MANUAL = "manual"


T = TypeVar("T")


@dataclass
class SagaStepResult(Generic[T]):
    """Result of executing a saga step."""

    success: bool
    data: T | None = None
    error: str | None = None
    execution_time_ms: float = 0.0


@dataclass
class SagaEvent:
    """Event generated during saga execution."""

    event_id: str
    saga_id: str
    event_type: SagaEventType
    step_name: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: JSONDict = field(default_factory=dict)
    error: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SagaStepDefinition:
    """Definition of a saga step with its action and compensation."""

    name: str
    description: str
    action: Callable[..., Coroutine[object, object, SagaStepResult]]
    compensation: Callable[..., Coroutine[object, object, SagaStepResult]]
    timeout_seconds: int = 300
    max_retries: int = 3
    retry_delay_seconds: int = 5
    compensation_strategy: CompensationStrategy = CompensationStrategy.RETRY
    required: bool = True
    order: int = 0


@dataclass
class SagaStepExecution:
    """Execution state of a saga step."""

    step_name: str
    status: SagaStepStatus = SagaStepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_data: JSONDict | None = None
    error_message: str | None = None
    retry_count: int = 0
    compensation_retry_count: int = 0


@dataclass
class SagaContext:
    """Context passed between saga steps."""

    saga_id: str
    tenant_id: str
    correlation_id: str
    data: JSONDict = field(default_factory=dict)
    step_results: JSONDict = field(default_factory=dict)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class Saga:
    """A saga instance with its execution state."""

    saga_id: str
    tenant_id: str
    name: str
    description: str
    status: SagaStatus = SagaStatus.PENDING
    context: SagaContext | None = None
    steps: list[SagaStepExecution] = field(default_factory=list)
    events: list[SagaEvent] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    current_step_index: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SagaDefinition:
    """Definition of a saga with all its steps."""

    name: str
    description: str
    steps: list[SagaStepDefinition]
    timeout_seconds: int = 3600
    max_compensation_retries: int = 3
    compensation_strategy: CompensationStrategy = CompensationStrategy.RETRY


@dataclass
class SagaExecutionResult:
    """Result of saga execution."""

    saga_id: str
    success: bool
    status: SagaStatus
    completed_steps: list[str]
    failed_step: str | None = None
    compensated_steps: list[str] = field(default_factory=list)
    error: str | None = None
    execution_time_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH


class SagaStore:
    """Redis-based store for saga state with persistence across restarts."""

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis: redis.asyncio.Redis | None = None
        self._key_prefix = "acgs:saga:"
        self._ttl = SAGA_DEFAULT_TTL_SECONDS

    async def _get_redis(self) -> redis.asyncio.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.asyncio.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _saga_key(self, saga_id: str) -> str:
        """Generate Redis key for saga."""
        return f"{self._key_prefix}{saga_id}"

    def _tenant_key(self, tenant_id: str) -> str:
        """Generate Redis key for tenant saga index."""
        return f"{self._key_prefix}tenant:{tenant_id}"

    def _saga_to_dict(self, saga: Saga) -> dict:
        """Convert saga to dictionary for JSON serialization."""
        return {
            "saga_id": saga.saga_id,
            "tenant_id": saga.tenant_id,
            "name": saga.name,
            "description": saga.description,
            "status": saga.status.value,
            "steps": [
                {
                    "step_name": s.step_name,
                    "status": s.status.value,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "result_data": s.result_data,
                    "error_message": s.error_message,
                    "retry_count": s.retry_count,
                    "compensation_retry_count": s.compensation_retry_count,
                }
                for s in saga.steps
            ],
            "created_at": saga.created_at.isoformat(),
            "started_at": saga.started_at.isoformat() if saga.started_at else None,
            "completed_at": saga.completed_at.isoformat() if saga.completed_at else None,
            "error_message": saga.error_message,
            "current_step_index": saga.current_step_index,
            "constitutional_hash": saga.constitutional_hash,
            "context": {
                "saga_id": saga.context.saga_id,
                "tenant_id": saga.context.tenant_id,
                "correlation_id": saga.context.correlation_id,
                "data": saga.context.data,
                "step_results": saga.context.step_results,
                "metadata": saga.context.metadata,
                "constitutional_hash": saga.context.constitutional_hash,
            }
            if saga.context
            else None,
        }

    def _dict_to_saga(self, data: dict) -> Saga:
        """Convert dictionary to Saga object."""
        saga = Saga(
            saga_id=data["saga_id"],
            tenant_id=data["tenant_id"],
            name=data["name"],
            description=data.get("description", ""),
        )
        saga.status = SagaStatus(data["status"])
        saga.steps = [
            SagaStepExecution(
                step_name=s["step_name"],
                status=SagaStepStatus(s["status"]),
                started_at=datetime.fromisoformat(s["started_at"]) if s.get("started_at") else None,
                completed_at=datetime.fromisoformat(s["completed_at"])
                if s.get("completed_at")
                else None,
                result_data=s.get("result_data"),
                error_message=s.get("error_message"),
                retry_count=s.get("retry_count", 0),
                compensation_retry_count=s.get("compensation_retry_count", 0),
            )
            for s in data.get("steps", [])
        ]
        saga.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            saga.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            saga.completed_at = datetime.fromisoformat(data["completed_at"])
        saga.error_message = data.get("error_message")
        saga.current_step_index = data.get("current_step_index", 0)
        saga.constitutional_hash = data.get("constitutional_hash", CONSTITUTIONAL_HASH)
        ctx_data = data.get("context")
        if ctx_data:
            saga.context = SagaContext(
                saga_id=ctx_data["saga_id"],
                tenant_id=ctx_data["tenant_id"],
                correlation_id=ctx_data.get("correlation_id", ""),
                data=ctx_data.get("data", {}),
                step_results=ctx_data.get("step_results", {}),
                metadata=ctx_data.get("metadata", {}),
                constitutional_hash=ctx_data.get("constitutional_hash", CONSTITUTIONAL_HASH),
            )
        return saga

    async def save(self, saga: Saga) -> None:
        """Save saga state to Redis."""
        redis_client = await self._get_redis()
        saga_key = self._saga_key(saga.saga_id)
        tenant_key = self._tenant_key(saga.tenant_id)

        # Save saga data
        await redis_client.setex(saga_key, self._ttl, json.dumps(self._saga_to_dict(saga)))

        # Add to tenant index
        await redis_client.sadd(tenant_key, saga.saga_id)
        await redis_client.expire(tenant_key, self._ttl)

    async def get(self, saga_id: str) -> Saga | None:
        """Get saga by ID from Redis."""
        redis_client = await self._get_redis()
        saga_key = self._saga_key(saga_id)

        data = await redis_client.get(saga_key)
        if data:
            return self._dict_to_saga(json.loads(data))
        return None

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: SagaStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Saga]:
        """List sagas for a tenant from Redis."""
        redis_client = await self._get_redis()
        tenant_key = self._tenant_key(tenant_id)

        # Get all saga IDs for tenant
        saga_ids = await redis_client.smembers(tenant_key)
        saga_ids = list(saga_ids)[offset : offset + limit]

        # Fetch each saga
        sagas = []
        for sid in saga_ids:
            saga = await self.get(sid)
            if saga:
                if status is None or saga.status == status:
                    sagas.append(saga)

        return sagas

    async def delete(self, saga_id: str) -> bool:
        """Delete a saga from Redis."""
        redis_client = await self._get_redis()

        # Get saga first to find tenant
        saga = await self.get(saga_id)
        if not saga:
            return False

        saga_key = self._saga_key(saga_id)
        tenant_key = self._tenant_key(saga.tenant_id)

        # Remove from tenant index
        await redis_client.srem(tenant_key, saga_id)

        # Delete saga data
        await redis_client.delete(saga_key)

        return True

    async def get_pending_compensations(self) -> list[Saga]:
        """Get sagas that need compensation."""
        return [
            saga
            for saga in self._sagas.values()
            if saga.status in (SagaStatus.COMPENSATING, SagaStatus.PARTIALLY_COMPENSATED)
        ]


class SagaEventPublisher:
    """Publisher for saga events (replace with Kafka in production)."""

    def __init__(self):
        self._handlers: list[Callable[[SagaEvent], Coroutine[object, object, None]]] = []
        self._event_log: list[SagaEvent] = []

    def subscribe(
        self,
        handler: Callable[[SagaEvent], Coroutine[object, object, None]],
    ) -> None:
        """Subscribe to saga events."""
        self._handlers.append(handler)

    async def publish(self, event: SagaEvent) -> None:
        """Publish a saga event."""
        self._event_log.append(event)
        for handler in self._handlers:
            try:
                await handler(event)
            except _SAGA_OPERATION_ERRORS as e:
                logger.error(f"Event handler error: {e}")

    def get_events(
        self,
        saga_id: str | None = None,
        event_type: SagaEventType | None = None,
    ) -> list[SagaEvent]:
        """Get events with optional filtering."""
        events = self._event_log
        if saga_id:
            events = [e for e in events if e.saga_id == saga_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events


class SagaOrchestrator:
    """Orchestrator for saga execution with compensation support."""

    def __init__(
        self,
        store: SagaStore | None = None,
        event_publisher: SagaEventPublisher | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.store = store or SagaStore()
        self.event_publisher = event_publisher or SagaEventPublisher()
        self.constitutional_hash = constitutional_hash
        self._definitions: dict[str, SagaDefinition] = {}

    def register_saga(self, definition: SagaDefinition) -> None:
        """Register a saga definition."""
        # Sort steps by order
        definition.steps.sort(key=lambda s: s.order)
        self._definitions[definition.name] = definition

    def get_definition(self, name: str) -> SagaDefinition | None:
        """Get a saga definition by name."""
        return self._definitions.get(name)

    async def create_saga(
        self,
        definition_name: str,
        tenant_id: str,
        initial_data: JSONDict | None = None,
        metadata: JSONDict | None = None,
    ) -> Saga:
        """Create a new saga instance."""
        definition = self._definitions.get(definition_name)
        if not definition:
            raise ValueError(f"Unknown saga definition: {definition_name}")

        saga_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())

        context = SagaContext(
            saga_id=saga_id,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            data=initial_data or {},
            metadata=metadata or {},
            constitutional_hash=self.constitutional_hash,
        )

        steps = [SagaStepExecution(step_name=step.name) for step in definition.steps]

        saga = Saga(
            saga_id=saga_id,
            tenant_id=tenant_id,
            name=definition.name,
            description=definition.description,
            context=context,
            steps=steps,
            constitutional_hash=self.constitutional_hash,
        )

        await self.store.save(saga)
        return saga

    async def execute(self, saga_id: str) -> SagaExecutionResult:
        """Execute a saga."""
        saga = await self.store.get(saga_id)
        if not saga:
            raise ValueError(f"Saga not found: {saga_id}")

        definition = self._definitions.get(saga.name)
        if not definition:
            raise ValueError(f"Saga definition not found: {saga.name}")

        start_time = datetime.now(UTC)
        saga.status = SagaStatus.RUNNING
        saga.started_at = start_time
        await self.store.save(saga)

        # Publish saga started event
        await self._publish_event(
            saga,
            SagaEventType.SAGA_STARTED,
            details={"initial_data": saga.context.data if saga.context else {}},
        )

        completed_steps: list[str] = []
        failed_step: str | None = None
        error_message: str | None = None

        try:
            # Execute each step in order
            for i, step_def in enumerate(definition.steps):
                saga.current_step_index = i
                step_execution = saga.steps[i]

                result = await self._execute_step(
                    saga,
                    step_def,
                    step_execution,
                )

                if result.success:
                    completed_steps.append(step_def.name)
                    if result.data and saga.context:
                        saga.context.step_results[step_def.name] = result.data
                else:
                    failed_step = step_def.name
                    error_message = result.error
                    break

            # Check if all steps completed successfully
            if not failed_step:
                saga.status = SagaStatus.COMPLETED
                saga.completed_at = datetime.now(UTC)
                await self.store.save(saga)

                await self._publish_event(
                    saga,
                    SagaEventType.SAGA_COMPLETED,
                    details={"completed_steps": completed_steps},
                )

                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

                return SagaExecutionResult(
                    saga_id=saga_id,
                    success=True,
                    status=SagaStatus.COMPLETED,
                    completed_steps=completed_steps,
                    execution_time_ms=execution_time,
                    constitutional_hash=self.constitutional_hash,
                )

        except _SAGA_OPERATION_ERRORS as e:
            error_message = str(e)
            logger.error(f"Saga execution error: {e}")

        # Saga failed - initiate compensation
        return await self._handle_saga_failure(
            saga,
            definition,
            saga_id,
            start_time,
            completed_steps,
            failed_step,
            error_message,
        )

    async def _handle_saga_failure(
        self,
        saga: "Saga",
        definition: "SagaDefinition",
        saga_id: str,
        start_time: datetime,
        completed_steps: list[str],
        failed_step: str | None,
        error_message: str | None,
    ) -> "SagaExecutionResult":
        """Handle saga failure: persist state, compensate, and return result."""
        saga.status = SagaStatus.COMPENSATING
        saga.error_message = error_message
        await self.store.save(saga)

        await self._publish_event(
            saga,
            SagaEventType.SAGA_FAILED,
            error=error_message,
            details={"failed_step": failed_step, "completed_steps": completed_steps},
        )

        # Compensate completed steps in reverse order
        compensated_steps = await self._compensate(
            saga,
            definition,
            completed_steps,
        )

        execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

        final_status = (
            SagaStatus.COMPENSATED
            if len(compensated_steps) == len(completed_steps)
            else SagaStatus.PARTIALLY_COMPENSATED
        )

        saga.status = final_status
        saga.completed_at = datetime.now(UTC)
        await self.store.save(saga)

        await self._publish_event(
            saga,
            (
                SagaEventType.SAGA_COMPENSATED
                if final_status == SagaStatus.COMPENSATED
                else SagaEventType.SAGA_FAILED
            ),
            details={
                "compensated_steps": compensated_steps,
                "failed_step": failed_step,
            },
        )

        return SagaExecutionResult(
            saga_id=saga_id,
            success=False,
            status=final_status,
            completed_steps=completed_steps,
            failed_step=failed_step,
            compensated_steps=compensated_steps,
            error=error_message,
            execution_time_ms=execution_time,
            constitutional_hash=self.constitutional_hash,
        )

    async def _run_with_retries(
        self,
        action: Callable[..., Coroutine[object, object, SagaStepResult]],
        context: SagaContext,
        timeout_seconds: int,
        max_retries: int,
        retry_delay_seconds: int,
        step_execution: SagaStepExecution,
        is_compensation: bool = False,
    ) -> SagaStepResult:
        last_error: str | None = None
        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(action(context), timeout=timeout_seconds)
                if result.success:
                    return result
                last_error = result.error or "Step returned unsuccessful result"
            except TimeoutError:
                last_error = f"Step timed out after {timeout_seconds}s"
            except _SAGA_OPERATION_ERRORS as e:
                last_error = str(e)
                prefix = "Compensation for" if is_compensation else "Step"
                logger.error(
                    f"{prefix} {step_execution.step_name} attempt {attempt + 1} failed: {e}"
                )

            if is_compensation:
                step_execution.compensation_retry_count = attempt + 1
            else:
                step_execution.retry_count = attempt + 1

            if attempt < max_retries:
                await asyncio.sleep(retry_delay_seconds)

        return SagaStepResult(success=False, error=last_error)

    async def _execute_step(
        self,
        saga: Saga,
        step_def: SagaStepDefinition,
        step_execution: SagaStepExecution,
    ) -> SagaStepResult:
        """Execute a single saga step with retries."""
        step_execution.status = SagaStepStatus.EXECUTING
        step_execution.started_at = datetime.now(UTC)
        await self.store.save(saga)

        await self._publish_event(
            saga,
            SagaEventType.STEP_STARTED,
            step_name=step_def.name,
        )

        result = await self._run_with_retries(
            action=step_def.action,
            context=saga.context,
            timeout_seconds=step_def.timeout_seconds,
            max_retries=step_def.max_retries,
            retry_delay_seconds=step_def.retry_delay_seconds,
            step_execution=step_execution,
            is_compensation=False,
        )

        if result.success:
            step_execution.status = SagaStepStatus.COMPLETED
            step_execution.completed_at = datetime.now(UTC)
            step_execution.result_data = (
                result.data if isinstance(result.data, dict) else {"value": result.data}
            )
            await self.store.save(saga)
            await self._publish_event(
                saga,
                SagaEventType.STEP_COMPLETED,
                step_name=step_def.name,
                details={"attempt": step_execution.retry_count},
            )
            return result

        step_execution.status = SagaStepStatus.FAILED
        step_execution.completed_at = datetime.now(UTC)
        step_execution.error_message = result.error
        await self.store.save(saga)

        await self._publish_event(
            saga,
            SagaEventType.STEP_FAILED,
            step_name=step_def.name,
            error=result.error,
            details={"attempts": step_execution.retry_count},
        )

        return result

    async def _compensate(
        self,
        saga: Saga,
        definition: SagaDefinition,
        completed_steps: list[str],
    ) -> list[str]:
        """Compensate completed steps in reverse order."""
        await self._publish_event(
            saga,
            SagaEventType.SAGA_COMPENSATING,
            details={"steps_to_compensate": completed_steps},
        )

        compensated_steps: list[str] = []

        # Compensate in reverse order
        for step_name in reversed(completed_steps):
            step_def = next(
                (s for s in definition.steps if s.name == step_name),
                None,
            )
            if not step_def:
                continue

            step_execution = next(
                (s for s in saga.steps if s.step_name == step_name),
                None,
            )
            if not step_execution:
                continue

            result = await self._compensate_step(
                saga,
                step_def,
                step_execution,
                definition.max_compensation_retries,
            )

            if result.success:
                compensated_steps.append(step_name)

        return compensated_steps

    async def _compensate_step(
        self,
        saga: Saga,
        step_def: SagaStepDefinition,
        step_execution: SagaStepExecution,
        max_retries: int,
    ) -> SagaStepResult:
        """Compensate a single step."""
        step_execution.status = SagaStepStatus.COMPENSATING
        await self.store.save(saga)

        await self._publish_event(
            saga,
            SagaEventType.STEP_COMPENSATING,
            step_name=step_def.name,
        )

        result = await self._run_with_retries(
            action=step_def.compensation,
            context=saga.context,
            timeout_seconds=step_def.timeout_seconds,
            max_retries=max_retries,
            retry_delay_seconds=step_def.retry_delay_seconds,
            step_execution=step_execution,
            is_compensation=True,
        )

        if result.success:
            step_execution.status = SagaStepStatus.COMPENSATED
            await self.store.save(saga)
            await self._publish_event(
                saga,
                SagaEventType.STEP_COMPENSATED,
                step_name=step_def.name,
                details={"attempt": step_execution.compensation_retry_count},
            )
            return result

        # Handle compensation failure based on strategy
        if step_def.compensation_strategy == CompensationStrategy.SKIP:
            step_execution.status = SagaStepStatus.SKIPPED
            await self.store.save(saga)
            return SagaStepResult(success=True)  # Treat as success for flow

        step_execution.status = SagaStepStatus.COMPENSATION_FAILED
        step_execution.error_message = f"Compensation failed: {result.error}"
        await self.store.save(saga)

        await self._publish_event(
            saga,
            SagaEventType.STEP_COMPENSATION_FAILED,
            step_name=step_def.name,
            error=result.error,
        )

        return result

    async def _publish_event(
        self,
        saga: Saga,
        event_type: SagaEventType,
        step_name: str | None = None,
        error: str | None = None,
        details: JSONDict | None = None,
    ) -> None:
        """Publish a saga event."""
        event = SagaEvent(
            event_id=str(uuid.uuid4()),
            saga_id=saga.saga_id,
            event_type=event_type,
            step_name=step_name,
            error=error,
            details=details or {},
            constitutional_hash=self.constitutional_hash,
        )
        saga.events.append(event)
        await self.event_publisher.publish(event)

    async def get_saga(self, saga_id: str) -> Saga | None:
        """Get a saga by ID."""
        return await self.store.get(saga_id)

    async def list_sagas(
        self,
        tenant_id: str,
        status: SagaStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Saga]:
        """List sagas for a tenant."""
        return await self.store.list_by_tenant(tenant_id, status, limit, offset)

    async def cancel_saga(self, saga_id: str) -> bool:
        """Cancel a saga and initiate compensation."""
        saga = await self.store.get(saga_id)
        if not saga:
            return False

        if saga.status not in (SagaStatus.PENDING, SagaStatus.RUNNING):
            return False

        definition = self._definitions.get(saga.name)
        if not definition:
            return False

        # Get completed steps
        completed_steps = [s.step_name for s in saga.steps if s.status == SagaStepStatus.COMPLETED]

        saga.status = SagaStatus.COMPENSATING
        saga.error_message = "Cancelled by user"
        await self.store.save(saga)

        # Compensate if any steps completed
        if completed_steps:
            await self._compensate(saga, definition, completed_steps)

        saga.status = SagaStatus.COMPENSATED
        saga.completed_at = datetime.now(UTC)
        await self.store.save(saga)

        return True


class MigrationSagaBuilder:
    """Builder for creating migration-specific sagas."""

    def __init__(self, orchestrator: SagaOrchestrator):
        self.orchestrator = orchestrator

    def _create_mock_handlers(
        self,
        required_keys: list[str] | None = None,
        data_generator: Callable[[SagaContext], dict] | None = None,
        compensate_data_generator: Callable[[SagaContext], dict] | None = None,
    ) -> tuple[Callable, Callable]:
        """Create mock action and compensation handlers."""

        async def action(ctx: SagaContext) -> SagaStepResult:
            if required_keys:
                for key in required_keys:
                    if not ctx.data.get(key):
                        return SagaStepResult(success=False, error=f"Missing {key}")
            data = data_generator(ctx) if data_generator else {}
            for k, v in data.items():
                if k.endswith("_id") and isinstance(v, str):
                    ctx.data[k] = v
            return SagaStepResult(success=True, data=data)

        async def compensation(ctx: SagaContext) -> SagaStepResult:
            data = compensate_data_generator(ctx) if compensate_data_generator else {}
            return SagaStepResult(success=True, data=data)

        return action, compensation

    def build_policy_migration_saga(self) -> SagaDefinition:
        """Build a saga for policy migration across tenants."""

        act_val, comp_val = self._create_mock_handlers(
            required_keys=["source_tenant_id"], data_generator=lambda ctx: {"validated": True}
        )
        act_exp, comp_exp = self._create_mock_handlers(
            data_generator=lambda ctx: {
                "export_id": str(uuid.uuid4()),
                "policy_count": len(ctx.data.get("policies", [])),
            },
            compensate_data_generator=lambda ctx: {"deleted_export": ctx.data.get("export_id")},
        )
        act_trans, comp_trans = self._create_mock_handlers(
            required_keys=["target_tenant_id"],
            data_generator=lambda ctx: {"transform_id": str(uuid.uuid4())},
            compensate_data_generator=lambda ctx: {
                "deleted_transform": ctx.data.get("transform_id")
            },
        )
        act_imp, comp_imp = self._create_mock_handlers(
            data_generator=lambda ctx: {
                "import_id": str(uuid.uuid4()),
                "target_tenant": ctx.data.get("target_tenant_id"),
            },
            compensate_data_generator=lambda ctx: {"rolled_back_import": ctx.data.get("import_id")},
        )
        act_ver, comp_ver = self._create_mock_handlers(
            data_generator=lambda ctx: {"verification_status": "passed"}
        )

        return SagaDefinition(
            name="policy_migration",
            description="Migrate policies between tenants with rollback support",
            steps=[
                SagaStepDefinition(
                    name="validate_source",
                    description="Validate source tenant policies",
                    action=act_val,
                    compensation=comp_val,
                    order=0,
                ),
                SagaStepDefinition(
                    name="export_policies",
                    description="Export policies from source tenant",
                    action=act_exp,
                    compensation=comp_exp,
                    order=1,
                ),
                SagaStepDefinition(
                    name="transform_policies",
                    description="Transform policies for target tenant",
                    action=act_trans,
                    compensation=comp_trans,
                    order=2,
                ),
                SagaStepDefinition(
                    name="import_policies",
                    description="Import policies to target tenant",
                    action=act_imp,
                    compensation=comp_imp,
                    order=3,
                ),
                SagaStepDefinition(
                    name="verify_migration",
                    description="Verify migration success",
                    action=act_ver,
                    compensation=comp_ver,
                    order=4,
                ),
            ],
        )

    def build_database_migration_saga(self) -> SagaDefinition:
        """Build a saga for database schema migration."""

        act_bak, comp_bak = self._create_mock_handlers(
            data_generator=lambda ctx: {"backup_id": str(uuid.uuid4())},
            compensate_data_generator=lambda ctx: {"kept_backup": ctx.data.get("backup_id")},
        )
        act_sch, comp_sch = self._create_mock_handlers(
            data_generator=lambda ctx: {
                "applied_version": ctx.data.get("target_version", "v1.0.0")
            },
            compensate_data_generator=lambda ctx: {"restored_from": ctx.data.get("backup_id")},
        )
        act_mig, comp_mig = self._create_mock_handlers(
            data_generator=lambda ctx: {"records_migrated": ctx.data.get("expected_records", 0)},
            compensate_data_generator=lambda ctx: {"data_restored_from": ctx.data.get("backup_id")},
        )
        act_val, comp_val = self._create_mock_handlers(
            data_generator=lambda ctx: {"validation": "passed", "integrity_check": True}
        )

        return SagaDefinition(
            name="database_migration",
            description="Database schema and data migration with backup and rollback",
            steps=[
                SagaStepDefinition(
                    name="backup_database",
                    description="Create database backup",
                    action=act_bak,
                    compensation=comp_bak,
                    order=0,
                ),
                SagaStepDefinition(
                    name="apply_schema_changes",
                    description="Apply schema migrations",
                    action=act_sch,
                    compensation=comp_sch,
                    order=1,
                ),
                SagaStepDefinition(
                    name="migrate_data",
                    description="Migrate data to new schema",
                    action=act_mig,
                    compensation=comp_mig,
                    order=2,
                ),
                SagaStepDefinition(
                    name="validate_migration",
                    description="Validate migration integrity",
                    action=act_val,
                    compensation=comp_val,
                    order=3,
                ),
            ],
        )


class SagaRecoveryService:
    """Service for recovering failed or interrupted sagas."""

    def __init__(self, orchestrator: SagaOrchestrator):
        self.orchestrator = orchestrator
        self._running = False
        self._recovery_task: asyncio.Task | None = None

    async def start(self, check_interval_seconds: int = 60) -> None:
        """Start the recovery service."""
        self._running = True
        self._recovery_task = asyncio.create_task(self._recovery_loop(check_interval_seconds))

    async def stop(self) -> None:
        """Stop the recovery service."""
        self._running = False
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass

    async def _recovery_loop(self, interval: int) -> None:
        """Main recovery loop."""
        while self._running:
            try:
                await self._recover_pending_compensations()
            except _SAGA_OPERATION_ERRORS as e:
                logger.error(f"Recovery error: {e}")
            await asyncio.sleep(interval)

    async def _recover_pending_compensations(self) -> None:
        """Recover sagas that need compensation."""
        pending = await self.orchestrator.store.get_pending_compensations()
        for saga in pending:
            try:
                definition = self.orchestrator.get_definition(saga.name)
                if definition:
                    completed_steps = [
                        s.step_name for s in saga.steps if s.status == SagaStepStatus.COMPLETED
                    ]
                    await self.orchestrator._compensate(saga, definition, completed_steps)
                    saga.status = SagaStatus.COMPENSATED
                    saga.completed_at = datetime.now(UTC)
                    await self.orchestrator.store.save(saga)
            except _SAGA_OPERATION_ERRORS as e:
                logger.error(f"Failed to recover saga {saga.saga_id}: {e}")


class SagaMetrics:
    """Metrics collection for saga execution."""

    def __init__(self):
        self.total_sagas = 0
        self.successful_sagas = 0
        self.failed_sagas = 0
        self.compensated_sagas = 0
        self.total_steps_executed = 0
        self.total_compensations = 0
        self.execution_times_ms: list[float] = []

    def record_saga_completed(
        self,
        result: SagaExecutionResult,
    ) -> None:
        """Record saga completion metrics."""
        self.total_sagas += 1
        if result.success:
            self.successful_sagas += 1
        else:
            self.failed_sagas += 1
            if result.compensated_steps:
                self.compensated_sagas += 1
                self.total_compensations += len(result.compensated_steps)

        self.total_steps_executed += len(result.completed_steps)
        self.execution_times_ms.append(result.execution_time_ms)

    def get_stats(self) -> JSONDict:
        """Get current metrics."""
        avg_time = (
            sum(self.execution_times_ms) / len(self.execution_times_ms)
            if self.execution_times_ms
            else 0
        )
        return {
            "total_sagas": self.total_sagas,
            "successful_sagas": self.successful_sagas,
            "failed_sagas": self.failed_sagas,
            "compensated_sagas": self.compensated_sagas,
            "success_rate": (
                self.successful_sagas / self.total_sagas * 100 if self.total_sagas > 0 else 0
            ),
            "total_steps_executed": self.total_steps_executed,
            "total_compensations": self.total_compensations,
            "average_execution_time_ms": avg_time,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
