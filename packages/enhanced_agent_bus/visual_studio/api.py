from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import Field

from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user

from .models import (
    WorkflowDefinition,
    WorkflowExportRequest,
    WorkflowExportResult,
    WorkflowListResponse,
    WorkflowSimulationResult,
    WorkflowSummary,
    WorkflowValidationResult,
)
from .service import VisualStudioService, get_visual_studio_service

VISUAL_STUDIO_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

router = APIRouter(
    prefix="/api/v1/visual",
    tags=["Visual Studio"],
    dependencies=[Depends(get_current_user)],
)


def get_service() -> VisualStudioService:
    return get_visual_studio_service()


def _resolve_tenant_id(user: UserClaims, tenant_id: str | None) -> str:
    if tenant_id is None:
        return user.tenant_id
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross-tenant denied")
    return tenant_id


@router.post("/workflows", status_code=201, response_model=WorkflowDefinition)
async def create_workflow(
    name: str = Query(..., min_length=1),
    description: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    user: Annotated[UserClaims, Depends(get_current_user)] = None,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowDefinition:
    resolved_tenant = _resolve_tenant_id(user, tenant_id)
    try:
        return await service.create_workflow(
            name=name, description=description, tenant_id=resolved_tenant
        )
    except VISUAL_STUDIO_OPERATION_ERRORS as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {exc}") from exc


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    tenant_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: Annotated[UserClaims, Depends(get_current_user)] = None,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowListResponse:
    resolved_tenant = _resolve_tenant_id(user, tenant_id)
    workflows, total = await service.list_workflows(resolved_tenant, page, page_size)
    return WorkflowListResponse(workflows=workflows, total=total, page=page, page_size=page_size)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowDefinition:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.put("/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def update_workflow(
    workflow_id: str,
    workflow: WorkflowDefinition,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowDefinition:
    if workflow_id != workflow.id:
        raise HTTPException(
            status_code=400,
            detail=f"Path id {workflow_id!r} does not match body id {workflow.id!r}",
        )
    existing = await service.get_workflow(workflow_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        return await service.save_workflow(workflow)
    except VISUAL_STUDIO_OPERATION_ERRORS as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update workflow: {exc}") from exc


@router.post("/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def save_workflow(
    workflow_id: str,
    workflow: WorkflowDefinition,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowDefinition:
    if workflow_id != workflow.id:
        raise HTTPException(
            status_code=400,
            detail=f"Path id {workflow_id!r} does not match body id {workflow.id!r}",
        )
    existing = await service.get_workflow(workflow_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await service.save_workflow(workflow)


@router.delete("/workflows/{workflow_id}", status_code=204, response_class=Response)
async def delete_workflow(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> Response:
    deleted = await service.delete_workflow(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(status_code=204)


@router.post("/workflows/{workflow_id}/validate", response_model=WorkflowValidationResult)
async def validate_workflow(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowValidationResult:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return service.validate_workflow(workflow)


@router.post("/workflows/{workflow_id}/simulate", response_model=WorkflowSimulationResult)
async def simulate_workflow(
    workflow_id: str,
    input_data: dict = Body(default_factory=dict),
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowSimulationResult:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await service.simulate_workflow(workflow, input_data)


@router.post("/workflows/{workflow_id}/export", response_model=WorkflowExportResult)
async def export_workflow(
    workflow_id: str,
    request: WorkflowExportRequest,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowExportResult:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await service.export_workflow(workflow, request)


@router.get("/workflows/{workflow_id}/summary", response_model=WorkflowSummary)
async def get_workflow_summary(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowSummary:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowSummary(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        node_count=len(workflow.nodes),
        edge_count=len(workflow.edges),
        updated_at=workflow.updated_at,
        version=workflow.version,
        is_active=workflow.is_active,
    )


__all__ = [
    "create_workflow",
    "delete_workflow",
    "export_workflow",
    "get_workflow",
    "list_workflows",
    "router",
    "simulate_workflow",
    "update_workflow",
    "validate_workflow",
]
