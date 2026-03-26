from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .models import (
    NodeType,
    WorkflowDefinition,
    WorkflowExportRequest,
    WorkflowExportResult,
    WorkflowNode,
    WorkflowSimulationResult,
    WorkflowSummary,
    WorkflowValidationResult,
)


class VisualStudioService:
    """Default in-process implementation of the visual-studio service."""

    def __init__(self) -> None:
        self._store: dict[str, WorkflowDefinition] = {}

    async def create_workflow(
        self,
        name: str,
        description: str | None = None,
        tenant_id: str | None = None,
    ) -> WorkflowDefinition:
        now = datetime.now(UTC)
        wf = WorkflowDefinition(
            id=f"wf-{abs(hash(name)) % 100000000:08x}",
            name=name,
            description=description,
            nodes=[
                WorkflowNode(id="start", type=NodeType.START, position={"x": 0.0, "y": 0.0}),
                WorkflowNode(id="end", type=NodeType.END, position={"x": 1.0, "y": 1.0}),
            ],
            edges=[],
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
        self._store[wf.id] = wf
        return wf

    async def get_workflow(self, workflow_id: str) -> WorkflowDefinition | None:
        return self._store.get(workflow_id)

    async def save_workflow(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        self._store[workflow.id] = workflow
        return workflow

    async def delete_workflow(self, workflow_id: str) -> bool:
        if workflow_id not in self._store:
            return False
        del self._store[workflow_id]
        return True

    async def list_workflows(
        self,
        tenant_id: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[WorkflowSummary], int]:
        all_wfs = [
            wf for wf in self._store.values() if tenant_id is None or wf.tenant_id == tenant_id
        ]
        total = len(all_wfs)
        offset = (page - 1) * page_size
        page_wfs = all_wfs[offset : offset + page_size]
        summaries = [
            WorkflowSummary(
                id=wf.id,
                name=wf.name,
                description=wf.description,
                node_count=len(wf.nodes),
                edge_count=len(wf.edges),
                updated_at=wf.updated_at or datetime.now(UTC),
                version=wf.version,
                is_active=wf.is_active,
            )
            for wf in page_wfs
        ]
        return summaries, total

    def validate_workflow(self, workflow: WorkflowDefinition) -> WorkflowValidationResult:
        return WorkflowValidationResult(is_valid=True, errors=[], warnings=[])

    async def simulate_workflow(
        self,
        workflow: WorkflowDefinition,
        input_data: dict[str, Any],
    ) -> WorkflowSimulationResult:
        return WorkflowSimulationResult(
            workflow_id=workflow.id,
            success=True,
            steps=[],
            final_output=input_data,
        )

    async def export_workflow(
        self,
        workflow: WorkflowDefinition,
        request: WorkflowExportRequest,
    ) -> WorkflowExportResult:
        return WorkflowExportResult(
            workflow_id=workflow.id,
            format=request.format,
            content=workflow.model_dump_json(),
            filename=f"{workflow.name.replace(' ', '_').lower()}.{request.format}",
        )


_visual_studio_service: VisualStudioService | None = None


def get_visual_studio_service() -> VisualStudioService:
    global _visual_studio_service
    if _visual_studio_service is None:
        _visual_studio_service = VisualStudioService()
    return _visual_studio_service


__all__ = ["VisualStudioService", "get_visual_studio_service"]
