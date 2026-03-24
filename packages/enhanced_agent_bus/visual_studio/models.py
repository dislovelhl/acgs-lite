from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class NodeType(StrEnum):
    START = "start"
    END = "end"
    POLICY = "policy"
    CONDITION = "condition"
    ACTION = "action"


class ExportFormat(StrEnum):
    JSON = "json"
    REGO = "rego"
    YAML = "yaml"


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: NodeType
    position: dict = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    data: dict = Field(default_factory=dict)
    width: float | None = None
    height: float | None = None
    selected: bool = False
    dragging: bool = False

    @field_validator("position")
    @classmethod
    def _validate_position(cls, value: dict) -> dict:
        if "x" not in value or "y" not in value:
            raise ValueError("Position must contain 'x' and 'y' coordinates")
        return value


class WorkflowEdge(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    source_handle: str | None = None
    target_handle: str | None = None
    label: str | None = None
    type: str | None = "smoothstep"
    animated: bool = False
    style: dict | None = None
    data: dict | None = None


class WorkflowDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    viewport: dict | None = None
    version: str = "1.0.0"
    tenant_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("updated_at", mode="before")
    @classmethod
    def _set_updated_at(cls, value: datetime | None) -> datetime:
        return datetime.now(UTC)


class VisualStudioValidationResult(BaseModel):
    message: str
    field: str | None = None
    node_id: str | None = None
    severity: str = "error"


class WorkflowValidationResult(BaseModel):
    is_valid: bool
    errors: list[VisualStudioValidationResult] = Field(default_factory=list)
    warnings: list[VisualStudioValidationResult] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SimulationStep(BaseModel):
    step_number: int
    node_id: str
    node_type: NodeType
    status: str
    input_data: dict = Field(default_factory=dict)
    output_data: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    execution_time_ms: float | None = None


class WorkflowSimulationResult(BaseModel):
    workflow_id: str
    success: bool
    steps: list[SimulationStep] = Field(default_factory=list)
    final_output: dict | None = None
    total_execution_time_ms: float | None = None
    error_message: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    node_count: int
    edge_count: int
    updated_at: datetime
    version: str
    is_active: bool


class WorkflowListResponse(BaseModel):
    workflows: list[WorkflowSummary]
    total: int
    page: int = 1
    page_size: int = 20


class WorkflowExportRequest(BaseModel):
    format: ExportFormat = ExportFormat.JSON
    include_metadata: bool = True


class WorkflowExportResult(BaseModel):
    workflow_id: str
    format: ExportFormat | str
    content: str
    filename: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "ExportFormat",
    "NodeType",
    "SimulationStep",
    "VisualStudioValidationResult",
    "WorkflowDefinition",
    "WorkflowEdge",
    "WorkflowExportRequest",
    "WorkflowExportResult",
    "WorkflowListResponse",
    "WorkflowNode",
    "WorkflowSimulationResult",
    "WorkflowSummary",
    "WorkflowValidationResult",
]
