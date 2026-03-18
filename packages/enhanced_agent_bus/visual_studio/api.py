from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from src.core.shared.security.auth import UserClaims, get_current_user

from .models import (
    NodeType,
    WorkflowDefinition,
    WorkflowExportRequest,
    WorkflowExportResult,
    WorkflowListResponse,
    WorkflowNode,
    WorkflowSimulationResult,
    WorkflowSummary,
    WorkflowValidationResult,
)

router = APIRouter(
    prefix="/api/v1/visual",
    tags=["visual-studio"],
    dependencies=[Depends(get_current_user)],
)

_service: Any | None = None


class _DefaultService:
    async def create_workflow(self, **kwargs: Any) -> WorkflowDefinition:
        now = datetime.now(UTC)
        return WorkflowDefinition(
            id="wf-default",
            name=kwargs["name"],
            description=kwargs.get("description", ""),
            nodes=[
                WorkflowNode(id="start", type=NodeType.START, position={"x": 0.0, "y": 0.0}),
                WorkflowNode(id="end", type=NodeType.END, position={"x": 1.0, "y": 1.0}),
            ],
            edges=[],
            tenant_id=kwargs.get("tenant_id"),
            created_at=now,
            updated_at=now,
        )

    async def get_workflow(self, _workflow_id: str) -> WorkflowDefinition | None:
        return None

    async def save_workflow(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        return workflow

    async def delete_workflow(self, _workflow_id: str) -> bool:
        return False

    async def list_workflows(
        self, tenant_id: str | None, page: int, page_size: int
    ) -> tuple[list[WorkflowSummary], int]:
        return [], 0

    def validate_workflow(self, _workflow: WorkflowDefinition) -> WorkflowValidationResult:
        return WorkflowValidationResult(is_valid=True)

    async def simulate_workflow(
        self, workflow: WorkflowDefinition, input_data: dict
    ) -> WorkflowSimulationResult:
        return WorkflowSimulationResult(workflow_id=workflow.id, success=True, final_output=input_data)

    async def export_workflow(
        self, workflow: WorkflowDefinition, request: WorkflowExportRequest
    ) -> WorkflowExportResult:
        return WorkflowExportResult(
            workflow_id=workflow.id,
            format=request.format,
            content=workflow.model_dump_json(),
            filename=f"{workflow.id}.{request.format}",
        )


def get_service() -> Any:
    global _service
    if _service is None:
        _service = _DefaultService()
    return _service


def _resolve_tenant_id(user: UserClaims, tenant_id: str | None) -> str:
    if tenant_id is None:
        return user.tenant_id
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross-tenant denied")
    return tenant_id


@router.post("/workflows", status_code=201)
async def create_workflow(
    name: str,
    description: str | None = None,
    tenant_id: str | None = None,
    user: Annotated[UserClaims, Depends(get_current_user)] = None,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowDefinition:
    resolved_tenant = _resolve_tenant_id(user, tenant_id)
    return await service.create_workflow(name=name, description=description, tenant_id=resolved_tenant)


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowDefinition:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return workflow


@router.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    workflow: WorkflowDefinition,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowDefinition:
    if workflow_id != workflow.id:
        raise HTTPException(status_code=400, detail="workflow id mismatch")
    return await service.save_workflow(workflow)


@router.get("/workflows")
async def list_workflows(
    tenant_id: str | None = Query(default=None),
    page: int = 1,
    page_size: int = 20,
    user: Annotated[UserClaims, Depends(get_current_user)] = None,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowListResponse:
    resolved_tenant = _resolve_tenant_id(user, tenant_id)
    workflows, total = await service.list_workflows(resolved_tenant, page, page_size)
    return WorkflowListResponse(workflows=workflows, total=total, page=page, page_size=page_size)


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> dict[str, bool]:
    deleted = await service.delete_workflow(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"deleted": True}


@router.post("/workflows/{workflow_id}/validate")
async def validate_workflow(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> dict:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return service.validate_workflow(workflow).model_dump()


@router.post("/workflows/{workflow_id}/simulate")
async def simulate_workflow(
    workflow_id: str,
    input_data: dict,
    service: Annotated[Any, Depends(get_service)] = None,
) -> dict:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return (await service.simulate_workflow(workflow, input_data)).model_dump()


@router.post("/workflows/{workflow_id}/export")
async def export_workflow(
    workflow_id: str,
    request: WorkflowExportRequest,
    service: Annotated[Any, Depends(get_service)] = None,
) -> dict:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return (await service.export_workflow(workflow, request)).model_dump()


@router.get("/workflows/{workflow_id}/summary")
async def get_workflow_summary(
    workflow_id: str,
    service: Annotated[Any, Depends(get_service)] = None,
) -> WorkflowSummary:
    workflow = await service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
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
