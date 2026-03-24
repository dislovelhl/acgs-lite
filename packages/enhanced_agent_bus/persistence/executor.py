"""
Durable Workflow Executor

Constitutional Hash: cdd01ef066bc6cf2
Version: 1.0.0

Provides durable workflow execution with:
- Persistent state across restarts
- Deterministic replay for recovery
- Saga compensation for rollback
- Checkpoint-based snapshots
"""

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    tracer = trace.get_tracer(__name__)
    _TELEMETRY_AVAILABLE = True
except ImportError:
    _TELEMETRY_AVAILABLE = False
    tracer = None

from src.core.shared.cache import workflow_cache

from .metrics import (
    WORKFLOW_CANCELLED_TOTAL,
    WORKFLOW_COMPENSATION_FAILED_TOTAL,
    WORKFLOW_COMPENSATION_TOTAL,
    WORKFLOW_COMPLETED_TOTAL,
    WORKFLOW_DURATION_SECONDS,
    WORKFLOW_FAILED_TOTAL,
    WORKFLOW_STARTED_TOTAL,
    WORKFLOW_STEP_COMPLETED_TOTAL,
    WORKFLOW_STEP_DURATION_SECONDS,
    WORKFLOW_STEP_FAILED_TOTAL,
)
from .models import (
    CONSTITUTIONAL_HASH,
    CheckpointData,
    EventType,
    StepStatus,
    StepType,
    WorkflowCompensation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from .repository import WorkflowRepository

logger = get_logger(__name__)
T = TypeVar("T")

_WORKFLOW_EXECUTOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class WorkflowContext:
    """
    Context passed to workflow activities.

    Provides access to workflow state and utilities for
    idempotent execution and compensation registration.
    """

    def __init__(
        self,
        workflow_instance: WorkflowInstance,
        repository: "WorkflowRepository",
        executor: "DurableWorkflowExecutor",
    ):
        self.workflow_instance = workflow_instance
        self.repository = repository
        self.executor = executor
        self._compensation_stack: list[WorkflowCompensation] = []
        self._compensation_handlers: dict[str, Callable] = {}

    @property
    def workflow_id(self) -> str:
        return self.workflow_instance.workflow_id

    @property
    def tenant_id(self) -> str:
        return self.workflow_instance.tenant_id

    @property
    def input(self) -> dict | None:
        return self.workflow_instance.input

    def get_idempotency_key(self, step_name: str, *args: object) -> str:
        """Generate idempotency key for step deduplication."""
        key_parts = [self.workflow_id, step_name, *[str(a) for a in args]]
        key_string = ":".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]

    async def register_compensation(
        self,
        step_id: UUID,
        name: str,
        handler: Callable[["WorkflowContext", dict], object],
        input_data: dict | None = None,
    ) -> None:
        """
        Register compensation BEFORE executing step.

        CRITICAL: Must be called before step execution.
        Compensations run in LIFO order on failure.
        """
        compensation = WorkflowCompensation(
            workflow_instance_id=self.workflow_instance.id,
            step_id=step_id,
            compensation_name=name,
            input=input_data,
        )
        self._compensation_stack.append(compensation)
        self._compensation_handlers[name] = handler
        await self.repository.save_compensation(compensation)
        logger.debug(f"Registered compensation: {name} for step {step_id}")


class DurableWorkflowExecutor:
    """
    Durable workflow executor with persistence and replay.

    Features:
    - Persistent state storage
    - Deterministic replay for recovery
    - Saga compensation for rollback
    - Checkpoint snapshots
    - Constitutional hash validation

    Example:
        executor = DurableWorkflowExecutor(repository)

        @executor.workflow("order-processing")
        async def process_order(ctx: WorkflowContext) -> dict:
            # Step 1: Reserve inventory
            inventory = await ctx.execute_activity(
                "reserve_inventory",
                reserve_inventory,
                {"order_id": ctx.input["order_id"]},
                compensation=release_inventory,
            )

            # Step 2: Charge payment
            payment = await ctx.execute_activity(
                "charge_payment",
                charge_payment,
                {"amount": ctx.input["amount"]},
                compensation=refund_payment,
            )

            return {"inventory": inventory, "payment": payment}
    """

    def __init__(
        self,
        repository: WorkflowRepository,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        checkpoint_interval: int = 5,
    ):
        self.repository = repository
        self.constitutional_hash = constitutional_hash
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.checkpoint_interval = checkpoint_interval
        self._workflows: dict[str, Callable] = {}

    def workflow(self, name: str) -> Callable:
        """Decorator to register a workflow."""

        def decorator(func: Callable) -> Callable:
            self._workflows[name] = func
            return func

        return decorator

    async def start_workflow(
        self,
        workflow_type: str,
        workflow_id: str,
        tenant_id: str,
        input_data: dict | None = None,
    ) -> WorkflowInstance:
        """
        Start a new workflow instance.

        Args:
            workflow_type: Registered workflow type name
            workflow_id: Business identifier for the workflow
            tenant_id: Tenant isolation identifier
            input_data: Input data for the workflow

        Returns:
            Created workflow instance

        Raises:
            ValueError: If workflow type not registered
        """
        if workflow_type not in self._workflows:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        existing = await self.repository.get_workflow_by_business_id(workflow_id, tenant_id)
        if existing and existing.status in (
            WorkflowStatus.PENDING,
            WorkflowStatus.RUNNING,
        ):
            logger.warning(f"Workflow {workflow_id} already running, returning existing")
            return existing

        instance = WorkflowInstance(
            workflow_type=workflow_type,
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            input=input_data,
            constitutional_hash=self.constitutional_hash,
        )
        await self.repository.save_workflow(instance)

        await self._record_event(
            instance.id,
            EventType.WORKFLOW_STARTED,
            {"workflow_type": workflow_type, "input": input_data},
        )

        WORKFLOW_STARTED_TOTAL.labels(workflow_type=workflow_type, tenant_id=tenant_id).inc()

        logger.info(f"Started workflow {workflow_id} ({workflow_type})")
        return instance

    async def _finalize_workflow_success(
        self, instance: WorkflowInstance, result: object, span: object
    ) -> None:
        """Record completed workflow state, metrics, and close span."""
        instance.status = WorkflowStatus.COMPLETED
        instance.output = result
        instance.completed_at = datetime.now(UTC)
        await self.repository.save_workflow(instance)
        await self._record_event(instance.id, EventType.WORKFLOW_COMPLETED, {"output": result})
        logger.info(f"Completed workflow {instance.workflow_id}")
        WORKFLOW_COMPLETED_TOTAL.labels(
            workflow_type=instance.workflow_type, tenant_id=instance.tenant_id
        ).inc()
        if instance.started_at:
            duration = (instance.completed_at - instance.started_at).total_seconds()
            WORKFLOW_DURATION_SECONDS.labels(
                workflow_type=instance.workflow_type, tenant_id=instance.tenant_id
            ).observe(duration)
        if span:
            span.set_status(Status(StatusCode.OK))
            span.end()

    async def _finalize_workflow_cancelled(
        self, instance: WorkflowInstance, exc: Exception, span: object
    ) -> None:
        """Record cancelled workflow state and close span."""
        instance.status = WorkflowStatus.CANCELLED
        instance.error = str(exc)
        instance.completed_at = datetime.now(UTC)
        await self.repository.save_workflow(instance)
        WORKFLOW_CANCELLED_TOTAL.labels(
            workflow_type=instance.workflow_type, tenant_id=instance.tenant_id
        ).inc()
        if span:
            span.set_status(Status(StatusCode.ERROR, "Cancelled"))
            span.end()

    async def _finalize_workflow_failed(
        self, instance: WorkflowInstance, context: object, exc: Exception, span: object
    ) -> None:
        """Record failed workflow state, run compensations, update metrics, close span."""
        await self._record_event(instance.id, EventType.WORKFLOW_FAILED, {"error": str(exc)})
        await self._run_compensations(context)
        instance.status = WorkflowStatus.FAILED
        instance.error = str(exc)
        instance.completed_at = datetime.now(UTC)
        await self.repository.save_workflow(instance)
        WORKFLOW_FAILED_TOTAL.labels(
            workflow_type=instance.workflow_type, tenant_id=instance.tenant_id
        ).inc()
        if instance.started_at:
            duration = (instance.completed_at - instance.started_at).total_seconds()
            WORKFLOW_DURATION_SECONDS.labels(
                workflow_type=instance.workflow_type, tenant_id=instance.tenant_id
            ).observe(duration)
        if span:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.end()

    async def execute_workflow(self, instance: WorkflowInstance) -> WorkflowInstance:
        """
        Execute a workflow instance to completion.

        Handles retries, compensation, and checkpointing.

        Args:
            instance: Workflow instance to execute

        Returns:
            Updated workflow instance with result
        """
        if instance.constitutional_hash != self.constitutional_hash:
            raise ValueError(
                f"Constitutional hash mismatch: "
                f"expected {self.constitutional_hash}, "
                f"got {instance.constitutional_hash}"
            )

        workflow_func = self._workflows.get(instance.workflow_type)
        if not workflow_func:
            raise ValueError(f"Unknown workflow type: {instance.workflow_type}")

        instance.status = WorkflowStatus.RUNNING
        instance.started_at = datetime.now(UTC)
        await self.repository.save_workflow(instance)

        context = WorkflowContext(instance, self.repository, self)

        if _TELEMETRY_AVAILABLE and tracer:
            span = tracer.start_span(
                f"Workflow: {instance.workflow_type}",
                attributes={
                    "workflow.type": instance.workflow_type,
                    "workflow.id": instance.workflow_id,
                    "tenant.id": instance.tenant_id,
                },
            )
        else:
            span = None

        try:
            result = await workflow_func(context)
            await self._finalize_workflow_success(instance, result, span)
            return instance

        except asyncio.CancelledError as e:
            logger.info(f"Workflow {instance.workflow_id} cancelled: {e}")
            await self._finalize_workflow_cancelled(instance, e, span)
            return instance

        except _WORKFLOW_EXECUTOR_OPERATION_ERRORS as e:
            logger.error(f"Workflow {instance.workflow_id} failed: {e}")
            await self._finalize_workflow_failed(instance, context, e, span)
            return instance

    async def resume_workflow(
        self, workflow_id: str, tenant_id: str, checkpoint_id: str | None = None
    ) -> WorkflowInstance:
        """
        Resume a workflow from the latest checkpoint or a specific checkpoint.

        Args:
            workflow_id: Business identifier for the workflow
            tenant_id: Tenant isolation identifier
            checkpoint_id: Optional specific checkpoint to resume from

        Returns:
            Updated workflow instance with result
        """
        instance = await self.repository.get_workflow_by_business_id(workflow_id, tenant_id)
        if not instance:
            raise ValueError(f"Workflow not found: {workflow_id}")

        if instance.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED):
            logger.info(f"Workflow {workflow_id} is already in terminal state: {instance.status}")
            return instance

        if checkpoint_id:
            # Note: A real implementation would fetch the checkpoint state
            # and inject it into the context/engine.
            pass
        else:
            checkpoint = await self.repository.get_latest_checkpoint(instance.id)
            if checkpoint:
                logger.info(
                    f"Resuming workflow {workflow_id} from checkpoint {checkpoint.checkpoint_id}"
                )

        # The actual resumption relies on execute_activity being idempotent
        # Activities already completed will be skipped via idempotency keys
        return await self.execute_workflow(instance)

    async def _get_cached_step_result(
        self, context: WorkflowContext, step_name: str, idempotency_key: str
    ) -> tuple[bool, object]:
        """Return (found, result) from cache or repository for a completed step."""
        cached = await workflow_cache.get_step_result(context.workflow_id, idempotency_key)
        if cached:
            logger.debug(f"Returning cached result from Redis for step {step_name}")
            return True, cached
        existing = await self.repository.get_step_by_idempotency_key(
            context.workflow_instance.id, idempotency_key
        )
        if existing and existing.status == StepStatus.COMPLETED:
            logger.debug(f"Returning cached result for step {step_name}")
            if existing.output:
                await workflow_cache.set_step_result(
                    context.workflow_id, idempotency_key, existing.output
                )
            return True, existing.output
        return False, None

    async def _complete_step(
        self,
        context: WorkflowContext,
        step: WorkflowStep,
        step_name: str,
        result: object,
        idempotency_key: str,
        span: object,
    ) -> None:
        """Persist completed step, update cache, emit events and metrics."""
        step.status = StepStatus.COMPLETED
        step.output = result if isinstance(result, dict) else {"result": result}
        step.completed_at = datetime.now(UTC)
        await self.repository.save_step(step)
        await workflow_cache.set_step_result(context.workflow_id, idempotency_key, step.output)
        await self._record_event(
            context.workflow_instance.id,
            EventType.STEP_COMPLETED,
            {"step_name": step_name, "output": step.output},
        )
        WORKFLOW_STEP_COMPLETED_TOTAL.labels(
            workflow_type=context.workflow_instance.workflow_type, step_name=step_name
        ).inc()
        if step.started_at:
            duration = (step.completed_at - step.started_at).total_seconds()
            WORKFLOW_STEP_DURATION_SECONDS.labels(
                workflow_type=context.workflow_instance.workflow_type, step_name=step_name
            ).observe(duration)
        if span:
            span.set_status(Status(StatusCode.OK))
            span.end()

    async def _fail_step(
        self,
        context: WorkflowContext,
        step: WorkflowStep,
        step_name: str,
        last_error: Exception,
        span: object,
    ) -> None:
        """Persist failed step, emit events, update metrics, close span."""
        step.status = StepStatus.FAILED
        step.error = str(last_error)
        step.completed_at = datetime.now(UTC)
        await self.repository.save_step(step)
        await self._record_event(
            context.workflow_instance.id,
            EventType.STEP_FAILED,
            {"step_name": step_name, "error": str(last_error)},
        )
        WORKFLOW_STEP_FAILED_TOTAL.labels(
            workflow_type=context.workflow_instance.workflow_type, step_name=step_name
        ).inc()
        if step.started_at:
            duration = (step.completed_at - step.started_at).total_seconds()
            WORKFLOW_STEP_DURATION_SECONDS.labels(
                workflow_type=context.workflow_instance.workflow_type, step_name=step_name
            ).observe(duration)
        if span:
            span.record_exception(last_error)
            span.set_status(Status(StatusCode.ERROR, str(last_error)))
            span.end()

    async def execute_activity(
        self,
        context: WorkflowContext,
        step_name: str,
        activity: Callable[..., object],
        input_data: dict | None = None,
        compensation: Callable[..., object] | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ) -> object:
        """
        Execute a single activity within a workflow.

        Args:
            context: Workflow execution context
            step_name: Name of the activity step
            activity: Async function to execute
            input_data: Input data for the activity
            compensation: Optional compensation function
            idempotency_key: Optional deduplication key
            timeout: Optional execution timeout in seconds

        Returns:
            Activity result
        """
        if not idempotency_key:
            idempotency_key = context.get_idempotency_key(step_name)

        found, cached_result = await self._get_cached_step_result(
            context, step_name, idempotency_key
        )
        if found:
            return cached_result

        step = WorkflowStep(
            workflow_instance_id=context.workflow_instance.id,
            step_name=step_name,
            step_type=StepType.ACTIVITY,
            input=input_data,
            idempotency_key=idempotency_key,
        )
        await self.repository.save_step(step)

        if compensation:
            await context.register_compensation(
                step.id,
                f"compensate_{step_name}",
                compensation,
                input_data,
            )

        span = (
            tracer.start_span(
                f"Activity: {step_name}",
                attributes={
                    "workflow.id": context.workflow_id,
                    "step.name": step_name,
                    "idempotency_key": idempotency_key,
                },
            )
            if _TELEMETRY_AVAILABLE and tracer
            else None
        )

        ok, result, last_error = await self._run_activity_with_retry(
            context, step, step_name, activity, input_data, idempotency_key, timeout, span
        )
        if ok:
            return result
        await self._fail_step(context, step, step_name, last_error, span)
        raise last_error  # type: ignore[misc]

    async def _run_activity_with_retry(
        self,
        context: WorkflowContext,
        step: WorkflowStep,
        step_name: str,
        activity: Callable[..., object],
        input_data: dict | None,
        idempotency_key: str,
        timeout: float | None,
        span: object,
    ) -> tuple[bool, object, Exception | None]:
        """Run activity with retries; return (success, result, last_error)."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                current_instance = await self.repository.get_workflow(context.workflow_instance.id)
                if current_instance and current_instance.status == WorkflowStatus.CANCELLED:
                    raise asyncio.CancelledError(f"Workflow {context.workflow_id} was cancelled")

                step.status = StepStatus.EXECUTING
                step.attempt_count = attempt + 1
                step.started_at = datetime.now(UTC)
                await self.repository.save_step(step)
                await self._record_event(
                    context.workflow_instance.id,
                    EventType.STEP_STARTED,
                    {"step_name": step_name, "attempt": attempt + 1},
                )

                result = (
                    await asyncio.wait_for(activity(context, input_data or {}), timeout=timeout)
                    if timeout
                    else await activity(context, input_data or {})
                )

                current_instance = await self.repository.get_workflow(context.workflow_instance.id)
                if current_instance and current_instance.status == WorkflowStatus.CANCELLED:
                    raise asyncio.CancelledError(
                        f"Workflow {context.workflow_instance.workflow_id} was cancelled during step {step_name}"
                    )

                await self._complete_step(context, step, step_name, result, idempotency_key, span)
                return True, result, None

            except TimeoutError:
                last_error = TimeoutError(f"Step {step_name} timed out after {timeout} seconds")
                logger.warning(f"Step {step_name} timed out (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
            except asyncio.CancelledError as e:
                last_error = e
                break
            except _WORKFLOW_EXECUTOR_OPERATION_ERRORS as e:
                last_error = e
                logger.warning(
                    f"Step {step_name} failed (attempt {attempt + 1}): {e}", exc_info=True
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
        return False, None, last_error

    async def _run_compensations(self, context: WorkflowContext) -> None:
        """Run compensations in LIFO order."""
        context.workflow_instance.status = WorkflowStatus.COMPENSATING
        await self.repository.save_workflow(context.workflow_instance)

        # Invalidate cache for this workflow as state is changing
        await workflow_cache.invalidate_workflow_state(context.workflow_id)

        compensations = await self.repository.get_compensations(context.workflow_instance.id)
        compensations.reverse()

        for comp in compensations:
            if comp.status != StepStatus.PENDING:
                continue

            try:
                if _TELEMETRY_AVAILABLE and tracer:
                    comp_span = tracer.start_span(
                        f"Compensation: {comp.compensation_name}",
                        attributes={
                            "workflow.id": context.workflow_id,
                            "step.id": str(comp.step_id),
                        },
                    )
                else:
                    comp_span = None

                await self._record_event(
                    context.workflow_instance.id,
                    EventType.COMPENSATION_STARTED,
                    {"compensation_name": comp.compensation_name},
                )

                comp.status = StepStatus.COMPENSATING
                comp.executed_at = datetime.now(UTC)
                await self.repository.save_compensation(comp)

                logger.info(f"Executing compensation: {comp.compensation_name}")

                handler = context._compensation_handlers.get(comp.compensation_name)
                if handler:
                    result = await handler(context, comp.input or {})
                    comp.output = result if isinstance(result, dict) else {"result": result}
                else:
                    logger.warning(f"No handler found for compensation: {comp.compensation_name}")

                comp.status = StepStatus.COMPENSATED
                await self.repository.save_compensation(comp)

                await self._record_event(
                    context.workflow_instance.id,
                    EventType.COMPENSATION_COMPLETED,
                    {"compensation_name": comp.compensation_name},
                )

                WORKFLOW_COMPENSATION_TOTAL.labels(
                    workflow_type=context.workflow_instance.workflow_type
                ).inc()

                if comp_span:
                    comp_span.set_status(Status(StatusCode.OK))
                    comp_span.end()

            except _WORKFLOW_EXECUTOR_OPERATION_ERRORS as e:
                logger.error(f"Compensation {comp.compensation_name} failed: {e}")
                comp.status = StepStatus.COMPENSATION_FAILED
                comp.error = str(e)
                await self.repository.save_compensation(comp)

                await self._record_event(
                    context.workflow_instance.id,
                    EventType.COMPENSATION_FAILED,
                    {"compensation_name": comp.compensation_name, "error": str(e)},
                )

                WORKFLOW_COMPENSATION_FAILED_TOTAL.labels(
                    workflow_type=context.workflow_instance.workflow_type
                ).inc()

                if "comp_span" in locals() and comp_span:
                    comp_span.record_exception(e)
                    comp_span.set_status(Status(StatusCode.ERROR, str(e)))
                    comp_span.end()

        context.workflow_instance.status = WorkflowStatus.COMPENSATED
        await self.repository.save_workflow(context.workflow_instance)

    async def create_checkpoint(self, context: WorkflowContext, step_index: int) -> CheckpointData:
        """Create a checkpoint snapshot."""
        checkpoint = CheckpointData(
            workflow_instance_id=context.workflow_instance.id,
            step_index=step_index,
            state={
                "workflow_input": context.workflow_instance.input,
                "compensation_stack": [c.model_dump() for c in context._compensation_stack],
            },
        )
        await self.repository.save_checkpoint(checkpoint)

        await self._record_event(
            context.workflow_instance.id,
            EventType.CHECKPOINT_CREATED,
            {"checkpoint_id": str(checkpoint.checkpoint_id), "step_index": step_index},
        )

        return checkpoint

    async def _record_event(
        self, workflow_instance_id: UUID, event_type: EventType, event_data: dict
    ) -> None:
        """Record an event for replay."""
        sequence = await self.repository.get_next_sequence(workflow_instance_id)
        event = WorkflowEvent(
            workflow_instance_id=workflow_instance_id,
            event_type=event_type,
            event_data=event_data,
            sequence_number=sequence,
        )
        await self.repository.save_event(event)

    async def get_workflow_status(
        self, workflow_id: str, tenant_id: str
    ) -> WorkflowInstance | None:
        """Get workflow status by business ID."""
        return await self.repository.get_workflow_by_business_id(workflow_id, tenant_id)

    async def cancel_workflow(
        self, workflow_id: str, tenant_id: str, reason: str = "User cancelled"
    ) -> WorkflowInstance | None:
        """Cancel a running workflow."""
        instance = await self.repository.get_workflow_by_business_id(workflow_id, tenant_id)
        if not instance:
            return None

        if instance.status not in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
            logger.warning(f"Cannot cancel workflow in status {instance.status}")
            return instance

        instance.status = WorkflowStatus.CANCELLED
        instance.error = reason
        instance.completed_at = datetime.now(UTC)
        await self.repository.save_workflow(instance)

        await self._record_event(
            instance.id,
            EventType.WORKFLOW_CANCELLED,
            {"reason": reason},
        )

        return instance
