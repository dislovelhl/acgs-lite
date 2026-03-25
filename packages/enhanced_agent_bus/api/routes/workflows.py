"""
Workflow Admin API routes.

Constitutional Hash: 608508a9bd224290
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from src.core.shared.security.auth import UserClaims, get_current_user

from enhanced_agent_bus.observability.structured_logging import get_logger

from ...persistence.executor import DurableWorkflowExecutor
from ...persistence.models import WorkflowStatus
from ..dependencies import get_workflow_executor

logger = get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["Workflows"])


def _enum_value(value: object) -> object:
    """Return enum .value when present, otherwise return the value as-is."""
    return value.value if hasattr(value, "value") else value


class WorkflowListResponse(BaseModel):
    workflows: list[dict[str, object]]
    total: int

    model_config = ConfigDict(from_attributes=True)


class WorkflowInspectResponse(BaseModel):
    instance: dict[str, object]
    steps: list[dict[str, object]]
    events: list[dict[str, object]]

    model_config = ConfigDict(from_attributes=True)


class CreateWorkflowRequest(BaseModel):
    workflow_type: str = "builtin.echo"
    workflow_id: str | None = None
    input_data: dict[str, object] | None = None
    execute_immediately: bool = True


class CreateWorkflowResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_type: str
    tenant_id: str
    status: object
    output: dict[str, object] | None = None

    model_config = ConfigDict(from_attributes=True)


class CancelRequest(BaseModel):
    reason: str = "User cancelled via Admin API"


def _resolve_tenant_id(user: UserClaims, requested_tenant_id: str | None) -> str:
    """Resolve tenant scope from JWT claims and reject cross-tenant requests."""
    if requested_tenant_id and requested_tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")
    return user.tenant_id  # type: ignore[no-any-return]


@router.post("", response_model=CreateWorkflowResponse)
async def create_workflow(
    req: CreateWorkflowRequest,
    tenant_id: str | None = Query(None, description="Tenant ID (must match authenticated tenant)"),
    user: UserClaims = Depends(get_current_user),
    executor: DurableWorkflowExecutor = Depends(get_workflow_executor),
):
    """Create a workflow instance and optionally execute it immediately."""
    scoped_tenant_id = _resolve_tenant_id(user, tenant_id)
    workflow_id = req.workflow_id or f"wf-{uuid4().hex[:12]}"

    try:
        instance = await executor.start_workflow(
            workflow_type=req.workflow_type,
            workflow_id=workflow_id,
            tenant_id=scoped_tenant_id,
            input_data=req.input_data,
        )
        if req.execute_immediately:
            instance = await executor.execute_workflow(instance)
    except ValueError as e:
        logger.error("Workflow create failed for %s: %s", workflow_id, e, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid workflow request") from e

    return {
        "id": str(instance.id),
        "workflow_id": instance.workflow_id,
        "workflow_type": instance.workflow_type,
        "tenant_id": instance.tenant_id,
        "status": _enum_value(instance.status),
        "output": instance.output,
    }


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    tenant_id: str | None = Query(None, description="Tenant ID (must match authenticated tenant)"),
    status: WorkflowStatus | None = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    user: UserClaims = Depends(get_current_user),
    executor: DurableWorkflowExecutor = Depends(get_workflow_executor),
):
    """List workflows with optional filtering."""
    scoped_tenant_id = _resolve_tenant_id(user, tenant_id)
    workflows = await executor.repository.list_workflows(scoped_tenant_id, status, limit)

    result = []
    for wf in workflows:
        result.append(
            {
                "id": str(wf.id),
                "workflow_id": wf.workflow_id,
                "workflow_type": wf.workflow_type,
                "status": _enum_value(wf.status),
                "created_at": wf.created_at.isoformat(),
                "updated_at": wf.updated_at.isoformat(),
            }
        )

    return {"workflows": result, "total": len(result)}


@router.get("/{workflow_id}", response_model=WorkflowInspectResponse)
async def inspect_workflow(
    workflow_id: str,
    tenant_id: str | None = Query(None, description="Tenant ID (must match authenticated tenant)"),
    user: UserClaims = Depends(get_current_user),
    executor: DurableWorkflowExecutor = Depends(get_workflow_executor),
):
    """Inspect full workflow state including steps and events."""
    scoped_tenant_id = _resolve_tenant_id(user, tenant_id)
    instance = await executor.repository.get_workflow_by_business_id(workflow_id, scoped_tenant_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow not found")

    steps = await executor.repository.get_steps(instance.id)
    events = await executor.repository.get_events(instance.id)

    return {
        "instance": {
            "id": str(instance.id),
            "workflow_id": instance.workflow_id,
            "workflow_type": instance.workflow_type,
            "status": _enum_value(instance.status),
            "input": instance.input,
            "output": instance.output,
            "error": instance.error,
            "created_at": instance.created_at.isoformat() if instance.created_at else None,
            "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
        },
        "steps": [
            {
                "id": str(s.id),
                "step_name": s.step_name,
                "status": _enum_value(s.status),
                "attempt_count": s.attempt_count,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "error": s.error,
            }
            for s in steps
        ],
        "events": [
            {
                "sequence": e.sequence_number,
                "event_type": _enum_value(e.event_type),
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "data": e.event_data,
            }
            for e in events
        ],
    }


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    req: CancelRequest,
    tenant_id: str | None = Query(None, description="Tenant ID (must match authenticated tenant)"),
    user: UserClaims = Depends(get_current_user),
    executor: DurableWorkflowExecutor = Depends(get_workflow_executor),
):
    """Cancel a running workflow."""
    scoped_tenant_id = _resolve_tenant_id(user, tenant_id)
    instance = await executor.cancel_workflow(workflow_id, scoped_tenant_id, req.reason)
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "id": str(instance.id),
        "workflow_id": instance.workflow_id,
        "status": _enum_value(instance.status),
        "message": "Workflow cancellation requested",
    }


@router.post("/{workflow_id}/retry")
async def retry_workflow(
    workflow_id: str,
    tenant_id: str | None = Query(None, description="Tenant ID (must match authenticated tenant)"),
    user: UserClaims = Depends(get_current_user),
    executor: DurableWorkflowExecutor = Depends(get_workflow_executor),
):
    """Retry a failed or cancelled workflow from its latest checkpoint/state."""
    try:
        scoped_tenant_id = _resolve_tenant_id(user, tenant_id)
        # resume_workflow operates on the current state and handles idempotency
        instance = await executor.resume_workflow(workflow_id, scoped_tenant_id)

        return {
            "id": str(instance.id),
            "workflow_id": instance.workflow_id,
            "status": _enum_value(instance.status),
            "message": "Workflow retry initiated",
        }
    except ValueError as e:
        logger.error(
            "Workflow retry failed for %s: %s",
            workflow_id,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Invalid request") from e
